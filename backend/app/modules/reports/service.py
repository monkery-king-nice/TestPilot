"""Escape all user-controlled content; never look up current cases or sources."""

import json
from html import escape

from fastapi import HTTPException

from ..runs.redaction import REDACTED, is_sensitive_path, redact_structure
from ..runs.service import RunService


def text(value) -> str:
    return escape("—" if value is None else str(value), quote=True)


def block(value) -> str:
    return "<pre>" + text(json.dumps(value, ensure_ascii=False, indent=2)) + "</pre>"


def redact_assertions(assertions: list[dict]) -> list[dict]:
    safe = redact_structure(assertions)
    for assertion in safe:
        if "expected" in assertion and is_sensitive_path(assertion.get("path")):
            assertion["expected"] = REDACTED
    return safe


def redact_saved_diff(diff: str) -> str:
    # Older batches stored JSON equality differences as "path：期望 value，实际 value".
    path, separator, _ = diff.partition("：期望 ")
    if separator and is_sensitive_path(path):
        return f"{path}：期望 {REDACTED}，实际 {REDACTED}"
    return diff


class ReportService:
    def __init__(self, runs: RunService):
        self.runs = runs

    def render(self, project_id: str, run_id: str) -> str:
        frozen = self.runs.get_frozen_snapshot(project_id, run_id)
        if frozen["status"] not in {"COMPLETED", "INTERRUPTED"}:
            raise HTTPException(409, "批次尚未结束，请等待执行完成后下载报告")
        detail = self.runs.get_run(project_id, run_id).model_dump()
        results = {item["case_id"]: item for item in detail["results"]}
        counts = detail["counts"]
        total = len(frozen["cases"])
        rate = counts["PASS"] / total * 100 if total else 0
        parts = [
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<meta http-equiv="Content-Security-Policy" '
            'content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'">',
            '<title>TestPilot 测试报告</title><style>',
            'body{font:16px/1.7 system-ui,sans-serif;color:#22352d;max-width:1100px;'
            'margin:40px auto;padding:0 24px}h1,h2,h3{line-height:1.4}'
            'table{border-collapse:collapse;width:100%;margin:16px 0}'
            'th,td{border:1px solid #c9d5ce;padding:10px;text-align:left;vertical-align:top}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f2;'
            'padding:12px;border-radius:6px}section{border-top:2px solid #c9d5ce;'
            'padding-top:16px;margin-top:28px}p{overflow-wrap:anywhere}'
            '@media print{body{margin:0;max-width:none}section{break-before:auto}}',
            '</style></head><body><h1>TestPilot · 测试报告</h1>',
            f'<p>运行批次：{text(run_id)}<br>项目：{text(project_id)}'
            f'<br>批次状态：{text(frozen["status"])}</p>',
            '<table><thead><tr><th>用例总数</th><th>PASS 通过</th><th>FAIL 失败</th>'
            '<th>ERROR 错误</th><th>BLOCKED 阻塞</th></tr></thead><tbody>',
            '<tr>' + ''.join(f'<td>{text(n)}</td>' for n in [total, *counts.values()])
            + '</tr></tbody></table>',
            f'<p>本批通过率：{rate:.1f}%（PASS / 全部所选用例，分母 {total}）。'
            '统计仅针对本批次，不代表软件整体质量。人工检查记录独立保存，未混入自动执行统计。</p>',
        ]
        for snapshot in frozen["cases"]:
            result = results.get(snapshot["case_id"])
            if result is None:
                raise HTTPException(409, "批次证据尚不完整，暂不能生成最终报告")
            source = snapshot.get("requirement", {})
            parts.extend([
                f'<section><h2>{text(snapshot["title"])}</h2>',
                f'<p>用例：{text(snapshot["case_id"])} · 版本 {text(snapshot["version"])}'
                f'<br>确认时间：{text(snapshot.get("confirmed_at"))}'
                f'<br>结果：<strong>{text(result["outcome"])}</strong></p>',
                '<h3>执行时的需求与预期依据</h3>',
                f'<p>需求：{text(snapshot["requirement_id"])} · '
                f'版本 {text(snapshot["requirement_version"])}</p>',
                f'<pre>{text(source.get("text", "历史快照未保存需求原文"))}</pre>',
                f'<p>预期依据：{text(snapshot["expected_basis"])}</p>',
            ])
            evidence = {step["name"]: step for step in result["steps"]}
            for step in snapshot["steps"]:
                endpoint = snapshot["endpoints"][step["endpoint_id"]]
                actual = evidence.get(step["name"], {})
                parts.extend([
                    f'<h3>步骤 {text(step["name"])} · {text(step["phase"])}</h3>',
                    f'<p>接口：{text(endpoint["method"])} {text(endpoint["path"])}'
                    f' · 版本 {text(endpoint["version"])}'
                    f'<br>HTTP 状态：{text(actual.get("http_status"))}'
                    f' · 耗时：{text(actual.get("elapsed_ms"))} ms'
                    f'<br>错误阶段：{text(actual.get("error_stage"))}</p>',
                    '<p>冻结的断言：</p>' + block(redact_assertions(step["assertions"])),
                    '<p>请求摘要（已脱敏）：</p><pre>'
                    + text(actual.get("request_summary")) + '</pre>',
                    '<p>响应摘要（已脱敏）：</p><pre>'
                    + text(actual.get("response_summary")) + '</pre>',
                    '<p>断言差异：</p>' + block([
                        redact_saved_diff(diff) for diff in actual.get("assertion_diffs", [])
                    ]),
                ])
            parts.append('</section>')
        parts.append('<p>本报告读取执行器保存的快照和证据；当前需求与用例的后续修改不会改写本报告。</p>'
                     '</body></html>')
        return ''.join(parts)
