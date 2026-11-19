"""Synchronous deterministic executor; RunService supplies sequential scheduling."""

import re
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from .models import CaseResult, StepResult
from .redaction import (
    REDACTED,
    evidence_summary,
    is_sensitive_path,
    redact_structure,
    replace_secrets,
)

_TEMPLATE = re.compile(r"\{\{(env|steps)\.([A-Za-z0-9_.-]+)\}\}")
_FULL_TEMPLATE = re.compile(r"^\{\{(env|steps)\.([A-Za-z0-9_.-]+)\}\}$")
_MISSING = object()


class StepPreparationError(Exception):
    pass


class DeterministicExecutor:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 3.0,
        transport: httpx.BaseTransport | None = None,
    ):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("测试目标必须是服务端配置的 HTTP 地址")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def execute(
        self,
        snapshot: dict,
        environment: Mapping[str, str],
        on_sent: Callable[[int], None] | None = None,
        on_result: Callable[[int, StepResult], None] | None = None,
    ) -> CaseResult:
        extracted: dict[str, dict[str, Any]] = {}
        secrets = {str(value) for value in environment.values() if value}
        results: list[StepResult] = []
        stopped = False
        forced_outcome: str | None = None

        with httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
            transport=self.transport,
            trust_env=False,
        ) as client:
            for index, step in enumerate(snapshot["steps"]):
                if stopped:
                    result = StepResult(
                        name=step["name"],
                        phase=step["phase"],
                        error_stage="setup_failed" if forced_outcome == "BLOCKED" else "not_started",
                        response_summary="前序步骤未完成，本步骤未发送请求",
                    )
                    results.append(result)
                    if on_result:
                        on_result(index, result)
                    continue

                result, values, failure = self._execute_step(
                    client, snapshot, step, environment, extracted, secrets, index, on_sent
                )
                results.append(result)
                if on_result:
                    on_result(index, result)
                extracted[step["name"]] = values
                secrets.update(str(value) for value in values.values() if value)

                if failure == "BLOCKED" or (
                    step["phase"] == "setup" and (result.error_stage or result.assertion_diffs)
                ):
                    stopped = True
                    forced_outcome = "BLOCKED"
                elif result.error_stage and result.error_stage != "assertion":
                    stopped = True
                    forced_outcome = "ERROR"
                elif result.assertion_diffs and forced_outcome != "ERROR":
                    forced_outcome = "FAIL"

        if forced_outcome:
            outcome = forced_outcome
        elif any(result.error_stage == "assertion" or result.assertion_diffs for result in results):
            outcome = "FAIL"
        elif any(result.error_stage for result in results):
            outcome = "ERROR"
        else:
            outcome = "PASS"
        return CaseResult(
            case_id=snapshot["case_id"], title=snapshot["title"], outcome=outcome, steps=results
        )

    def _execute_step(
        self,
        client: httpx.Client,
        snapshot: dict,
        step: dict,
        environment: Mapping[str, str],
        extracted: dict[str, dict[str, Any]],
        secrets: set[str],
        index: int,
        on_sent: Callable[[int], None] | None,
    ) -> tuple[StepResult, dict[str, Any], str | None]:
        name, phase = step["name"], step["phase"]
        try:
            endpoint = snapshot["endpoints"][step["endpoint_id"]]
            method = endpoint["method"].upper()
            url = self._target_url(endpoint["path"])
            headers = self._render(step.get("headers") or {}, environment, extracted)
            body = self._render(step.get("body"), environment, extracted)
            if not isinstance(headers, dict):
                raise StepPreparationError("请求头必须是对象")
            request_summary = evidence_summary(
                f"{method} {endpoint['path']} ",
                {"headers": headers, "body": body},
                secrets,
            )
        except (KeyError, StepPreparationError, ValueError) as error:
            message = str(error) if isinstance(error, StepPreparationError) else "步骤引用或请求目标无效"
            return (
                StepResult(
                    name=name,
                    phase=phase,
                    error_stage="render",
                    response_summary=replace_secrets(message, secrets),
                ),
                {},
                "BLOCKED" if phase == "setup" else "ERROR",
            )

        started = time.perf_counter()
        if on_sent:
            on_sent(index)
        try:
            response = client.request(
                method,
                url,
                headers={str(key): str(value) for key, value in headers.items()},
                json=body,
            )
        except httpx.TimeoutException:
            return (
                StepResult(
                    name=name,
                    phase=phase,
                    elapsed_ms=self._elapsed(started),
                    request_summary=request_summary,
                    error_stage="timeout",
                    response_summary=f"请求超过 {self.timeout_seconds:g} 秒超时上限",
                ),
                {},
                "BLOCKED" if phase == "setup" else "ERROR",
            )
        except httpx.HTTPError:
            return (
                StepResult(
                    name=name,
                    phase=phase,
                    elapsed_ms=self._elapsed(started),
                    request_summary=request_summary,
                    error_stage="connection",
                    response_summary="无法连接团队测试服务或响应传输失败",
                ),
                {},
                "BLOCKED" if phase == "setup" else "ERROR",
            )

        elapsed_ms = self._elapsed(started)
        response_body: Any
        try:
            response_body = response.json()
        except (ValueError, UnicodeDecodeError):
            response_body = response.text
        response_summary = evidence_summary(
            f"HTTP {response.status_code} ", response_body, secrets
        )
        diffs = self._assertions(
            step.get("assertions") or [], response.status_code, response_body, elapsed_ms, secrets
        )
        values: dict[str, Any] = {}
        error_stage = "assertion" if diffs else None
        failure = "FAIL" if diffs else None
        if not diffs:
            try:
                values = self._extract(step.get("extract") or {}, response_body)
            except StepPreparationError as error:
                error_stage = "extract"
                failure = "BLOCKED" if phase == "setup" else "ERROR"
                diffs = []
                response_summary = replace_secrets(str(error), secrets)
        return (
            StepResult(
                name=name,
                phase=phase,
                http_status=response.status_code,
                elapsed_ms=elapsed_ms,
                request_summary=request_summary,
                response_summary=response_summary,
                assertion_diffs=diffs,
                error_stage=error_stage,
            ),
            values,
            failure,
        )

    def _target_url(self, path: str) -> str:
        if not isinstance(path, str) or not path or path.startswith("//"):
            raise ValueError("invalid endpoint path")
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or ".." in parsed.path.split("/"):
            raise ValueError("endpoint must be a local relative path")
        return self.base_url + "/" + path.lstrip("/")

    @staticmethod
    def _elapsed(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))

    def _render(
        self,
        value: Any,
        environment: Mapping[str, str],
        extracted: dict[str, dict[str, Any]],
    ) -> Any:
        if isinstance(value, dict):
            return {key: self._render(item, environment, extracted) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render(item, environment, extracted) for item in value]
        if not isinstance(value, str):
            return value

        full = _FULL_TEMPLATE.fullmatch(value)
        if full:
            return self._variable(full.group(1), full.group(2), environment, extracted)

        def substitute(match: re.Match) -> str:
            resolved = self._variable(match.group(1), match.group(2), environment, extracted)
            if not isinstance(resolved, (str, int, float, bool)):
                raise StepPreparationError("嵌入字符串的变量必须是标量")
            return str(resolved)

        return _TEMPLATE.sub(substitute, value)

    @staticmethod
    def _variable(
        kind: str,
        path: str,
        environment: Mapping[str, str],
        extracted: dict[str, dict[str, Any]],
    ) -> Any:
        parts = path.split(".")
        if kind == "env":
            if len(parts) != 1 or parts[0] not in environment:
                raise StepPreparationError(f"环境变量 env.{path} 不可用")
            return environment[parts[0]]
        if len(parts) != 2:
            raise StepPreparationError("步骤变量必须使用 steps.<步骤名>.<变量>")
        step_name, key = parts
        if step_name not in extracted or key not in extracted[step_name]:
            raise StepPreparationError(f"步骤变量 steps.{path} 不可用")
        return extracted[step_name][key]

    @staticmethod
    def _path(document: Any, path: str) -> Any:
        current = document
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                return _MISSING
            current = current[key]
        return current

    def _assertions(
        self,
        assertions: list[dict],
        status: int,
        body: Any,
        elapsed_ms: int,
        secrets: set[str],
    ) -> list[str]:
        diffs: list[str] = []
        for assertion in assertions:
            kind = assertion.get("type")
            expected = assertion.get("expected")
            if kind == "status":
                if status != expected:
                    diffs.append(f"HTTP 状态：期望 {expected}，实际 {status}")
            elif kind == "nonempty_string":
                actual = self._path(body, assertion.get("path", ""))
                if not isinstance(actual, str) or not actual:
                    diffs.append(f"{assertion.get('path')}：期望非空字符串")
            elif kind == "json_equals":
                path = assertion.get("path", "")
                actual = self._path(body, path)
                if actual is _MISSING or actual != expected:
                    if is_sensitive_path(path):
                        diffs.append(f"{path}：期望 {REDACTED}，实际 {REDACTED}")
                        continue
                    safe_actual = "字段不存在" if actual is _MISSING else redact_structure(actual, secrets)
                    safe_expected = redact_structure(expected, secrets)
                    diffs.append(f"{path}：期望 {safe_expected!r}，实际 {safe_actual!r}")
            elif kind == "elapsed_ms_lte":
                if not isinstance(expected, (int, float)) or elapsed_ms > expected:
                    diffs.append(f"耗时：期望不超过 {expected} ms，实际 {elapsed_ms} ms")
            else:
                diffs.append(f"不支持的断言类型：{kind}")
        return [replace_secrets(diff, secrets) for diff in diffs]

    def _extract(self, rules: dict, body: Any) -> dict[str, Any]:
        values = {}
        for name, path in rules.items():
            value = self._path(body, path)
            if value is _MISSING:
                raise StepPreparationError(f"提取字段 {path} 不存在")
            values[name] = value
        return values
