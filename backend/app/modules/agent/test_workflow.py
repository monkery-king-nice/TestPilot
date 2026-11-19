import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.runs.models import RunDetail

from . import workflow


def test_drafts_use_current_project_sources_without_creating_cases(tmp_path, monkeypatch):
    app = create_app(Settings(database_path=tmp_path / "alpha.sqlite3"))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Alpha"}).json()["id"]
        base = f"/api/projects/{project}"
        text = "错误密码返回 HTTP 401"
        requirement = client.post(base + "/requirements", json={"text": text}).json()
        payload = {"requirement_id": requirement["id"]}
        endpoint = client.post(base + "/endpoints", json={"method": "POST", "path": "/auth/login"}).json()
        result = {"drafts": [{
            "title": "错误密码",
            "expected_basis": text,
            "steps": [{
                "name": "login", "phase": "test", "endpoint_id": endpoint["id"],
                "endpoint_version": 1, "assertions": [{"type": "status", "expected": 401}],
            }],
        }]}

        def model(prompt, raw, **_):
            assert prompt == workflow.GENERATE_PROMPT
            assert json.loads(raw) == {"requirement": requirement, "endpoints": [endpoint]}
            return result

        monkeypatch.setattr(workflow, "ask_json", model)
        response = client.post(base + "/agent/generate", json=payload)
        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        assert draft["requirement_id"] == requirement["id"]
        assert draft["requirement_version"] == requirement["version"]
        assert client.get(base + "/cases").json() == []
        assert client.post(base + "/cases", json=draft).status_code == 201

        result["drafts"][0]["steps"][0]["endpoint_id"] = "unknown"
        assert client.post(base + "/agent/generate", json=payload).status_code == 502
        assert len(client.get(base + "/cases").json()) == 1


def test_analysis_uses_only_selected_case_evidence(tmp_path, monkeypatch):
    app = create_app(Settings(database_path=tmp_path / "alpha.sqlite3"))
    sample = RunDetail.model_validate({
        "run_id": "existing", "status": "COMPLETED", "counts": {"FAIL": 1},
        "results": [{
            "case_id": "c1", "title": "case", "outcome": "FAIL",
            "steps": [{
                "name": "login", "phase": "test", "http_status": 200,
                "request_summary": "not needed for analysis",
                "assertion_diffs": ["预期 401，实际 200"],
            }],
        }],
    })
    result = {
        "category": "断言失败", "reason": "状态码异常", "suggestion": "检查登录失败分支",
        "evidence_indices": [0],
    }

    def model(prompt, raw, **_):
        assert prompt == workflow.ANALYSIS_PROMPT
        assert "not needed" not in raw
        assert "预期 401，实际 200" in raw
        return result

    monkeypatch.setattr(workflow, "ask_json", model)
    with TestClient(app) as client:
        original = app.state.run_service
        app.state.run_service = SimpleNamespace(get_run=lambda _p, _r: sample)
        try:
            route = "/api/projects/p/runs/existing/analysis"
            response = client.post(route, json={"case_id": "c1"})
            assert response.status_code == 200
            assert "预期 401，实际 200" in response.json()["evidence"][0]
            assert client.post(route, json={"case_id": "missing"}).status_code == 404
            result["evidence_indices"] = [1]
            assert client.post(route, json={"case_id": "c1"}).status_code == 502
        finally:
            app.state.run_service = original
