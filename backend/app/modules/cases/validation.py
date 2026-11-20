"""Static checks only: no eval, scripts, model calls or target HTTP requests."""

import math
import re
from collections.abc import Iterator
from typing import Any

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
PATH = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\Z")
TEMPLATE = re.compile(r"\{\{(env|steps)\.([A-Za-z0-9_.-]+)\}\}")


def strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def validate_draft(draft: dict, environment_keys: set[str]) -> list[str]:
    reasons = []
    if not draft["title"].strip():
        reasons.append("用例标题不能为空白")
    if not draft["expected_basis"].strip():
        reasons.append("缺少预期依据，请补充对应的需求或验收条件")
    steps = draft["steps"]
    if not 1 <= len(steps) <= 5:
        reasons.append("用例必须包含 1–5 个步骤")
    if not any(step["phase"] == "test" for step in steps):
        reasons.append("至少需要一个 test 主测试步骤")
    sources: set[str] = set()
    names: set[str] = set()
    started_test = False
    for index, step in enumerate(steps, 1):
        label = f"步骤 {index}（{step['name']}）"
        if not NAME.fullmatch(step["name"]):
            reasons.append(f"{label}：步骤名仅支持字母、数字、下划线和短横线，不能以数字开头")
        if step["name"] in names:
            reasons.append(f"{label}：步骤名重复")
        names.add(step["name"])
        if step["phase"] == "test":
            started_test = True
        elif started_test:
            reasons.append(f"{label}：setup 准备步骤必须位于主测试之前")
        for header, value in step["headers"].items():
            if not header or any(c in header + value for c in "\r\n\x00"):
                reasons.append(f"{label}：请求头名称或值无效")
        for text in strings([step["headers"], step["body"]]):
            remainder = TEMPLATE.sub("", text)
            if "{{" in remainder or "}}" in remainder or "${" in text:
                reasons.append(f"{label}：变量必须使用 {{{{env.<key>}}}} 或 "
                               "{{steps.<步骤名>.<变量>}}")
            for kind, path in TEMPLATE.findall(text):
                parts = path.split(".")
                if kind == "env":
                    if len(parts) != 1 or path not in environment_keys:
                        reasons.append(f"{label}：环境变量 env.{path} 未定义或未配置")
                elif len(parts) != 2 or path not in sources:
                    reasons.append(f"{label}：变量 steps.{path} 未由前序步骤定义")
        if not step["assertions"]:
            reasons.append(f"{label}：缺少断言，无法判断测试是否通过")
        for number, assertion in enumerate(step["assertions"], 1):
            prefix = f"{label} 断言 {number}"
            kind, expected = assertion["type"], assertion.get("expected")
            if kind == "status":
                if type(expected) is not int or not 100 <= expected <= 599:
                    reasons.append(f"{prefix}：预期 HTTP 状态码必须为 100–599 的整数")
            elif kind == "elapsed_ms_lte":
                if (type(expected) not in (int, float) or not math.isfinite(expected)
                        or expected < 0):
                    reasons.append(f"{prefix}：预期耗时上限必须是非负有限数字")
            elif kind in {"json_equals", "nonempty_string"}:
                if not PATH.fullmatch(assertion.get("path") or ""):
                    reasons.append(f"{prefix}：字段路径仅支持点分隔的对象键或数组下标")
                if kind == "json_equals" and "expected" not in assertion:
                    reasons.append(f"{prefix}：缺少字段预期值")
            else:
                reasons.append(f"{prefix}：不支持的断言类型")
            if any("{{" in text or "${" in text for text in strings(expected)):
                reasons.append(f"{prefix}：断言预期值不支持变量或表达式")
        for key, path in step["extract"].items():
            if not NAME.fullmatch(key) or not PATH.fullmatch(path):
                reasons.append(f"{label}：提取变量名或字段路径无效")
            else:
                sources.add(f"{step['name']}.{key}")
    return list(dict.fromkeys(reasons))
