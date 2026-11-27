import json

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.agent import workflow
from backend.app.modules.projects.archives import request_fields


def test_schema_names_are_available_without_example_values():
    spec = {"components": {"schemas": {"C": {"required": ["units"], "properties": {
        "units": {"type": "integer", "example": 353},
        "access_key": {"type": "string", "default": "private-fixture"},
    }}}}}
    operation = {"requestBody": {"content": {"application/json": {
        "schema": {"$ref": "#/components/schemas/C"},
    }}}}
    fields = request_fields(spec, operation)
    assert fields == [
        {"name": "units", "type": "integer", "required": True},
        {"name": "access_key", "type": "string", "required": False},
    ]
    assert request_fields({}, operation) == []


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database_path=tmp_path / 'beta.sqlite3'))) as session:
        yield session


def test_preview_digest_and_unmatched_candidate(client, monkeypatch):
    project = client.post("/api/projects", json={"name": "仓储"}).json()["id"]
    base = f"/api/projects/{project}"
    rule = "停用的货位应当拒绝入库。"
    req = client.post(base + "/requirements", json={"text": rule + "\nAPI_KEY=private-fixture"}).json()
    payload = {"requirement_id": req["id"], "requirement_version": 1}
    ep = client.post(base + "/endpoints", json={"method": "POST", "path": "/intake"}).json()
    preview = client.post(base + "/agent/preview", json=payload).json()
    assert "private-fixture" not in json.dumps(preview)
    observed = []
    def fake_model(prompt, context, **kwargs):
        observed.append(context)
        return {"drafts": [{"title": "拒绝入库", "expected_basis": basis, "steps": [{
            "phase": "test", "endpoint_id": ep["id"], "endpoint_version": 1,
            "name": "send", "assertions": [{"type": "status", "expected": 409}],
        }]} for basis in (rule, "ABXYZ6789")]}
    monkeypatch.setattr(workflow, "model_response", fake_model)
    payload["context_digest"] = preview["digest"]
    generated = client.post(base + "/agent/generate", json=payload).json()
    assert observed == [preview["context"]]
    assert [item["source"] for item in generated["reviews"]] == ["requirement", "unverified"]
    assert client.post(base + "/cases", json=generated["drafts"][0]).status_code == 201
    client.post(base + "/endpoints", json={"method": "GET", "path": "/stock"})
    for action in ("generate", "clarify"):
        assert client.post(base + "/agent/" + action, json=payload).status_code == 409
    assert len(observed) == 1
