"""Browser regression fixture: real API/SQLite, deterministic model substitute."""
import json
import argparse
import sys
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import uvicorn  # noqa: E402

from backend.app.main import create_app  # noqa: E402
from backend.app.modules.agent import workflow  # noqa: E402


def clarify(raw):
    context = json.loads(raw) if raw.startswith("{") else {"requirement": {"text": raw}}
    text = context["requirement"]["text"]
    if "用户补充" in text:
        return {"questions": []}
    source = context.get("source_excerpt", {}).get("text", text)
    quote = next(line for line in source.splitlines() if line.strip() and not line.startswith("#"))
    return {"questions": [{"quote": quote, "question": "失败时预期返回什么？"}]}


def generate(_prompt, context, **_kwargs):
    endpoint = context["endpoints"][0]
    return {"drafts": [{
        "title": "接口响应检查（模型替身）",
        "expected_basis": context["requirement"]["text"],
        "steps": [{
            "name": "query", "phase": "test", "endpoint_id": endpoint["id"],
            "endpoint_version": endpoint["version"],
            "headers": {}, "body": None,
            "assertions": [{"type": "status", "expected": 200}], "extract": {},
        }],
    }]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-dir", type=Path)
    args = parser.parse_args()
    if args.samples_dir:
        from backend.scripts.verify_project_imports import write_samples

        write_samples(args.samples_dir)
        with ZipFile(args.samples_dir / "no-docs.zip", "w") as archive:
            archive.writestr("src/main.py", 'print("fixture")')
        with ZipFile(args.samples_dir / "long-doc.zip", "w") as archive:
            archive.writestr("long.txt", "中" * 16010)
        # Stored binary payload exercises actual upload bytes without a large expansion ratio.
        with ZipFile(args.samples_dir / "large-project.zip", "w") as archive:
            archive.writestr("assets/padding.bin", b"\0" * int(32.7 * 1024 * 1024))
            archive.writestr("docs/requirements.md", "# 大包上传回归样本\n\n预览此需求文档。\n")
        print("Created project UI regression samples")
        raise SystemExit(0)
    workflow.model_response = generate
    uvicorn.run(create_app(agent_provider=clarify), host="127.0.0.1", port=8000)
