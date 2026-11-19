import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app

from . import clarify, workflow


@pytest.mark.parametrize("name,path,rule,answer,expected", [
    ("图书目录", "/books", "按书名查询图书", "书名为空返回 422", 422),
    ("教室预约", "/rooms", "查询教室预约", "教室不存在返回 404", 404),
])
def test_imported_context_and_saved_answer_drive_candidate(
    tmp_path, monkeypatch, name, path, rule, answer, expected
):
    app = create_app(Settings(database_path=tmp_path / "project.sqlite3"))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": name}).json()["id"]
        base = f"/api/projects/{project}"
        buffer = BytesIO()
        with ZipFile(buffer, "w") as package:
            package.writestr("docs/requirements.md", rule + "\nAPI_KEY=secret-fixture")
            package.writestr("docs/unselected.md", "unselected-fixture")
            package.writestr("openapi.json", json.dumps({
                "openapi": "3.0.3", "paths": {path: {"get": {"summary": name}}},
            }))
        manifest = client.post(
            base + "/imports?filename=sample.zip", content=buffer.getvalue(),
            headers={"Content-Type": "application/zip"},
        ).json()
        import_route = base + "/imports/" + manifest["id"]
        confirm = client.post(import_route + "/confirm-endpoints", json={
            "candidate_ids": [manifest["endpoint_candidates"][0]["candidate_id"]],
        })
        endpoint = confirm.json()["endpoints"][0]["endpoint"]
        source = client.post(import_route + "/preview", json={"path": "docs/requirements.md"}).json()
        saved = client.post(base + "/requirements", json={
            "text": "需要明确失败条件",
            "source": {key: source[key] for key in ("import_id", "path", "start", "end")},
        }).json()
        payload = {"requirement_id": saved["id"], "requirement_version": 1}

        def inspect(raw, version):
            context = json.loads(raw)
            assert context["requirement"]["version"] == version
            assert rule in context["source_excerpt"]["text"]
            assert context["endpoints"] == [endpoint]
            assert context["interface_descriptions"][0]["summary"] == name
            assert "secret-fixture" not in raw and "unselected-fixture" not in raw
            return context

        def ask_clarifying(_prompt, raw):
            context = json.loads(raw)
            inspect(raw, context["requirement"]["version"])
            if answer in context["requirement"]["text"]:
                return {"questions": []}
            return {"questions": [{"quote": rule, "question": "失败时预期返回什么？"}]}

        monkeypatch.setattr(clarify, "ask_json", ask_clarifying)
        response = client.post(base + "/agent/clarify", json=payload)
        assert response.json()["questions"][0]["source_path"] == "docs/requirements.md"
        updated = client.patch(base + "/requirements/" + saved["id"], json={"text": answer}).json()
        assert updated["version"] == 2
        for route in ("/agent/clarify", "/agent/generate"):
            assert client.post(base + route, json=payload).status_code == 409
        payload["requirement_version"] = 2
        assert client.post(base + "/agent/clarify", json=payload).json()["status"] == "READY"

        def generate(_prompt, raw, **_):
            assert inspect(raw, 2)["requirement"]["text"] == answer
            return {"drafts": [{
                "title": name,
                "expected_basis": answer,
                "steps": [{
                    "name": "query", "phase": "test", "endpoint_id": endpoint["id"],
                    "endpoint_version": endpoint["version"],
                    "assertions": [{"type": "status", "expected": expected}],
                }],
            }]}

        monkeypatch.setattr(workflow, "ask_json", generate)
        response = client.post(base + "/agent/generate", json=payload)
        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        assert draft["requirement_version"] == 2
        assert draft["steps"][0]["assertions"][0]["expected"] == expected
        assert client.get(base + "/cases").json() == []
