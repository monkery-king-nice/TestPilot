"""Batch lifecycle, mutual exclusion, background scheduling and recovery."""

import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Sequence

import httpx

from .dependencies import (
    EnvironmentChanged,
    EnvironmentVersionConflict,
    PreflightRejected,
    RunDependencies,
)
from .executor import DeterministicExecutor
from .models import CaseRef, CaseResult, RunDetail, StepResult
from .repository import RunRepository


@dataclass(frozen=True)
class RunSettings:
    demo_base_url: str = "http://127.0.0.1:8010"
    request_timeout_seconds: float = 3.0


class RunService:
    def __init__(
        self,
        repository: RunRepository,
        dependencies: RunDependencies,
        settings: RunSettings | None = None,
        *,
        background: bool = True,
        transport: httpx.BaseTransport | None = None,
        recover_on_start: bool = True,
    ):
        self.repository = repository
        self.dependencies = dependencies
        self.settings = settings or RunSettings()
        self.background = background
        self.transport = transport
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="testpilot-runs")
        self._futures: set[Future] = set()
        self._lock = threading.Lock()
        if recover_on_start:
            self.repository.recover_interrupted()

    def create_run(
        self,
        project_id: str,
        cases: Sequence[CaseRef],
        environment_version: int | None = None,
    ) -> str:
        ids = [case.id for case in cases]
        if len(ids) != len(set(ids)):
            raise PreflightRejected(["同一批次不能重复选择同一个用例"])
        snapshots = self.dependencies.preflight(project_id, cases)
        self._validate_snapshots(cases, snapshots)
        snapshots = [{**snapshot, "project_id": project_id} for snapshot in snapshots]
        configured = self.dependencies.read_execution_target(project_id)
        # 页面展示的环境版本与当前环境不一致时拒绝创建，避免把请求发到用户未确认的服务。
        if (
            environment_version is not None
            and configured.get("environment_version") != environment_version
        ):
            raise EnvironmentVersionConflict(
                "项目测试环境已变更，请刷新页面确认最新环境后重新执行"
            )
        target = self._resolve_target(configured)
        run_id = self.repository.create_run(project_id, snapshots, target)
        if self.background:
            future = self._pool.submit(self.execute_run, run_id)
            with self._lock:
                self._futures.add(future)
            future.add_done_callback(self._forget)
        return run_id

    def _resolve_target(self, configured: dict) -> dict:
        kind = configured.get("target")
        if kind not in {"demo", "local"}:
            raise PreflightRejected(["项目测试环境目标无效，不能回退到默认演示服务"])
        if kind == "local" and (
            not configured.get("service_id") or not configured.get("base_url")
        ):
            raise PreflightRejected(["项目本地测试服务缺少服务标识或地址"])
        environment_version = configured.get("environment_version")
        if type(environment_version) is not int or environment_version < 1:
            raise PreflightRejected(["项目测试环境缺少有效版本，请重新保存环境配置"])
        if kind == "demo":
            return {
                "kind": "demo",
                "service_id": "demo",
                "base_url": self.settings.demo_base_url,
                "environment_version": environment_version,
            }
        return {
            "kind": "local",
            "service_id": configured["service_id"],
            "base_url": configured["base_url"],
            "environment_version": environment_version,
        }

    def _forget(self, future: Future) -> None:
        with self._lock:
            self._futures.discard(future)
        future.exception()

    def execute_run(self, run_id: str) -> None:
        self.repository.mark_running(run_id)
        target = self.repository.get_run_target(run_id)
        legacy_target = target is None
        if legacy_target:
            # Only runs created before project targets existed retain legacy demo behavior.
            target = {
                "kind": "demo",
                "service_id": "demo",
                "base_url": self.settings.demo_base_url,
                "environment_version": None,
            }
        snapshots = self.repository.get_snapshots_for_execution(run_id)
        environment = None
        environment_error = None
        try:
            if not legacy_target and target["environment_version"] is None:
                raise EnvironmentChanged("批次缺少环境版本，请重新预检并创建运行批次")
            environment = self.dependencies.read_environment(
                snapshots[0]["project_id"],
                target["kind"],
                expected_version=target["environment_version"],
            )
        except EnvironmentChanged as error:
            environment_error = ("environment_changed", str(error))
        except Exception:
            environment_error = (
                "environment",
                "测试环境读取失败，未发送任何请求；请检查配置后重新执行",
            )
        if environment_error:
            stage, summary = environment_error
            for snapshot in snapshots:
                self.repository.save_case_result(
                    run_id, self._environment_error_result(snapshot, stage, summary)
                )
            self.repository.complete_run(run_id)
            return

        executor = DeterministicExecutor(
            target["base_url"],
            self.settings.request_timeout_seconds,
            self.transport,
        )
        for snapshot in snapshots:
            try:
                result = executor.execute(
                    snapshot,
                    environment,
                    on_sent=lambda index, s=snapshot: self.repository.mark_step_sent(
                        run_id, s["case_id"], index
                    ),
                    on_result=lambda index, result, s=snapshot: self.repository.save_step_result(
                        run_id, s["case_id"], index, result
                    ),
                )
            except Exception:
                result = self._internal_error_result(snapshot)
            self.repository.save_case_result(run_id, result)
        self.repository.complete_run(run_id)

    @staticmethod
    def _environment_error_result(snapshot: dict, stage: str, summary: str) -> CaseResult:
        return CaseResult(
            case_id=snapshot["case_id"],
            title=snapshot["title"],
            outcome="ERROR",
            steps=[
                StepResult(
                    name=step["name"],
                    phase=step["phase"],
                    error_stage=stage,
                    response_summary=summary,
                )
                for step in snapshot["steps"]
            ],
        )

    @staticmethod
    def _internal_error_result(snapshot: dict) -> CaseResult:
        return CaseResult(
            case_id=snapshot["case_id"],
            title=snapshot["title"],
            outcome="ERROR",
            steps=[
                StepResult(
                    name=step["name"],
                    phase=step["phase"],
                    error_stage="execution",
                    response_summary="执行器内部错误，未保留敏感细节",
                )
                for step in snapshot["steps"]
            ],
        )

    @staticmethod
    def _validate_snapshots(cases: Sequence[CaseRef], snapshots: list[dict]) -> None:
        if len(snapshots) != len(cases):
            raise PreflightRejected(["预检返回的用例数量与请求不一致"])
        for selected, snapshot in zip(cases, snapshots):
            reasons: list[str] = []
            if snapshot.get("case_id") != selected.id:
                reasons.append("预检返回的用例 ID 不一致")
            if snapshot.get("version") != selected.version:
                reasons.append(f"用例 {selected.id} 的版本已变化")
            steps = snapshot.get("steps")
            if not isinstance(steps, list) or not 1 <= len(steps) <= 5:
                reasons.append(f"用例 {selected.id} 必须包含 1–5 个步骤")
                steps = []
            names = [step.get("name") for step in steps]
            if len(names) != len(set(names)) or not all(names):
                reasons.append(f"用例 {selected.id} 的步骤名必须非空且唯一")
            endpoints = snapshot.get("endpoints")
            if not isinstance(endpoints, dict):
                reasons.append(f"用例 {selected.id} 缺少冻结端点快照")
            elif any(step.get("endpoint_id") not in endpoints for step in steps):
                reasons.append(f"用例 {selected.id} 引用了无效端点")
            if reasons:
                raise PreflightRejected(reasons)

    def get_run(self, project_id: str, run_id: str) -> RunDetail:
        return self.repository.get_detail(project_id, run_id)

    def get_frozen_snapshot(self, project_id: str, run_id: str) -> dict:
        return self.repository.get_frozen_snapshot(project_id, run_id)

    def wait_for_idle(self, timeout: float = 10) -> None:
        with self._lock:
            futures = list(self._futures)
        if futures:
            done, not_done = wait(futures, timeout=timeout)
            if not_done:
                raise TimeoutError("后台运行批次未在测试时限内结束")
            for future in done:
                future.result()

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=False)
