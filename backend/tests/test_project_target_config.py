import sqlite3

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.main import create_app
from backend.app.modules.projects.repository import ProjectRepository


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database_path=tmp_path / "targets.sqlite3"))) as client:
        yield client


def create_project(client, name="本地服务项目"):
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def secrets():
    return {"username": "local-user", "password": "private-local-password"}


def test_local_environment_round_trip_without_secret_leak(client):
    project_id = create_project(client)
    route = f"/api/projects/{project_id}/environment"
    response = client.put(
        route,
        json={
            "target": "local",
            "service_id": " service-b ",
            "base_url": "http://127.0.0.1:18082/",
            "secrets": secrets(),
        },
    )
    assert response.status_code == 200, response.text
    expected = {
        "target": "local",
        "service_id": "service-b",
        "base_url": "http://127.0.0.1:18082",
        "environment_version": 1,
        "configured_keys": ["password", "username"],
    }
    assert response.json() == expected
    assert client.get(route).json() == expected
    assert "local-user" not in response.text
    assert "private-local-password" not in response.text

    repository = client.app.state.project_repository
    assert repository.read_execution_target(project_id) == {
        "target": "local",
        "service_id": "service-b",
        "base_url": "http://127.0.0.1:18082",
        "environment_version": 1,
    }
    assert repository.read_environment(project_id, "local", 1) == secrets()
    with pytest.raises(HTTPException) as error:
        repository.read_environment(project_id, "local", 2)
    assert error.value.status_code == 409
    assert "重新预检" in error.value.detail
    with pytest.raises(HTTPException) as error:
        repository.read_environment(project_id, "demo")
    assert error.value.status_code == 422


def test_demo_contract_and_ipv6_loopback_remain_supported(client):
    project_id = create_project(client)
    route = f"/api/projects/{project_id}/environment"
    response = client.put(
        route,
        json={
            "target": "local",
            "service_id": "ipv6-service",
            "base_url": "http://[::1]:18083",
            "secrets": secrets(),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["base_url"] == "http://[::1]:18083"

    response = client.put(route, json={"target": "demo", "secrets": secrets()})
    assert response.status_code == 200
    assert response.json() == {
        "target": "demo",
        "service_id": "demo",
        "base_url": None,
        "environment_version": 2,
        "configured_keys": ["password", "username"],
    }
    repository = client.app.state.project_repository
    assert repository.read_execution_target(project_id)["target"] == "demo"
    assert repository.read_environment(project_id) == secrets()


@pytest.mark.parametrize(
    "overrides",
    [
        {"service_id": "service-b", "base_url": "http://example.invalid:8000"},
        {"service_id": "service-b", "base_url": "http://127.0.0.1"},
        {"service_id": "service-b", "base_url": "http://127.0.0.1:8000/path"},
        {"service_id": "service-b", "base_url": "http://127.0.0.1:8000?x=1"},
        {"service_id": "service-b", "base_url": "http://127.0.0.1:8000#fragment"},
        {"service_id": "service-b", "base_url": "http://user:pass@127.0.0.1:8000"},
        {"service_id": "service-b", "base_url": "ftp://127.0.0.1:8000"},
        {"service_id": "service-b", "base_url": "http://127.0.0.1:not-a-port"},
        {"service_id": "service-b", "base_url": "http://127.0.0.1:8000\n"},
        {"service_id": "service b", "base_url": "http://127.0.0.1:8000"},
        {"service_id": "", "base_url": "http://127.0.0.1:8000"},
        {"base_url": "http://127.0.0.1:8000"},
        {"service_id": "service-b"},
    ],
)
def test_invalid_local_target_rejected_without_replacing_existing_config(client, overrides):
    project_id = create_project(client)
    route = f"/api/projects/{project_id}/environment"
    original = {"target": "demo", "secrets": secrets()}
    assert client.put(route, json=original).status_code == 200
    response = client.put(
        route, json={"target": "local", **overrides, "secrets": secrets()}
    )
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], str)
    assert "private-local-password" not in response.text
    repository = client.app.state.project_repository
    assert repository.read_execution_target(project_id)["target"] == "demo"
    assert repository.read_environment(project_id, "demo") == secrets()


@pytest.mark.parametrize(
    "extra",
    [
        {"service_id": "custom-demo"},
        {"base_url": "http://127.0.0.1:8010"},
    ],
)
def test_demo_rejects_custom_target_fields(client, extra):
    project_id = create_project(client)
    response = client.put(
        f"/api/projects/{project_id}/environment",
        json={"target": "demo", **extra, "secrets": secrets()},
    )
    assert response.status_code == 422


def test_missing_environment_is_explicit_and_cross_project_isolated(client):
    configured = create_project(client, "已配置")
    missing = create_project(client, "未配置")
    repository = client.app.state.project_repository
    assert client.put(
        f"/api/projects/{configured}/environment",
        json={
            "target": "local",
            "service_id": "only-a",
            "base_url": "http://127.0.0.1:18084",
            "secrets": secrets(),
        },
    ).status_code == 200
    with pytest.raises(HTTPException) as error:
        repository.read_execution_target(missing)
    assert error.value.status_code == 422
    assert "不能回退" in error.value.detail
    with pytest.raises(HTTPException) as error:
        repository.read_environment(missing, "local")
    assert error.value.status_code == 422


def test_legacy_demo_environment_table_is_migrated_without_losing_secrets(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            INSERT INTO projects VALUES ('legacy-project', '旧项目');
            CREATE TABLE environments (
                project_id TEXT PRIMARY KEY REFERENCES projects(id),
                target TEXT NOT NULL CHECK(target = 'demo'),
                secrets_json TEXT NOT NULL
            );
            INSERT INTO environments VALUES (
                'legacy-project', 'demo',
                '{"username":"legacy-user","password":"legacy-password"}'
            );
            """
        )
    repository = ProjectRepository(Database(path))
    repository.initialize()
    assert repository.read_execution_target("legacy-project") == {
        "target": "demo",
        "service_id": "demo",
        "base_url": None,
        "environment_version": 1,
    }
    assert repository.read_environment("legacy-project") == {
        "username": "legacy-user",
        "password": "legacy-password",
    }
    repository.put_environment(
        "legacy-project",
        "local",
        {"username": "new-user", "password": "new-password"},
        service_id="new-local",
        base_url="http://localhost:18085",
    )
    assert repository.read_execution_target("legacy-project") == {
        "target": "local",
        "service_id": "new-local",
        "base_url": "http://localhost:18085",
        "environment_version": 2,
    }
