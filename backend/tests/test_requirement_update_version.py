from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def test_stale_requirement_answer_cannot_overwrite_new_version(tmp_path):
    with TestClient(create_app(Settings(database_path=tmp_path / "version.sqlite3"))) as client:
        project = client.post("/api/projects", json={"name": "并发版本校验"}).json()["id"]
        base = f"/api/projects/{project}/requirements"
        requirement = client.post(base, json={"text": "原文"}).json()
        url = base + "/" + requirement["id"]
        updated = client.patch(url, json={"text": "最新原文", "expected_version": 1})
        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        stale = client.patch(url, json={"text": "旧版本答案", "expected_version": 1})
        assert stale.status_code == 409
        assert client.get(base).json() == [updated.json()]
        compatible = client.patch(url, json={"text": "兼容原客户端"})
        assert compatible.status_code == 200
        assert compatible.json()["version"] == 3
