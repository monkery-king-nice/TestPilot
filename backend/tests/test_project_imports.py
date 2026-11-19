import json
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.projects import archives, router


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "imports.sqlite3")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def project(client):
    pid = client.post("/api/projects", json={"name": "导入验收"}).json()["id"]
    return f"/api/projects/{pid}"


def zip_bytes(*files):
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for path, content in files:
            archive.writestr(path, content)
    return buffer.getvalue()


def upload(client, base, data, **kwargs):
    return client.post(
        f"{base}/imports",
        params={"filename": "示例.zip"},
        content=data,
        headers={"content-type": "application/zip", **kwargs},
    )


def api_description():
    return json.dumps(
        {
            "openapi": "3.1.0",
            "servers": [{"url": "https://docs.example.invalid"}],
            "paths": {
                "/catalog": {
                    "parameters": [{"$ref": "#/components/parameters/Limit"}],
                    "get": {
                        "summary": "查看目录",
                        "responses": {"200": {"$ref": "#/components/responses/Ok"}},
                    },
                    "post": {"responses": {"201": {"description": "创建成功"}}},
                },
            },
            "components": {
                "parameters": {
                    "Limit": {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 10},
                    }
                },
                "responses": {"Ok": {"description": "返回目录列表"}},
            },
        }
    )


def checked_upload(client, base, data):
    response = upload(client, base, data)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_preview_confirm_and_restore_after_restart(settings):
    spec = api_description()
    raw = "\ufeff😀略过\r\n选定的需求。\r\n保留空白  "
    with TestClient(create_app(settings)) as client:
        base = project(client)
        archive = checked_upload(
            client,
            base,
            zip_bytes(
                ("docs/项目需求.md", raw),
                ("spec.json", spec),
                ("copy.json", spec),
                ("code.py", "ignored"),
            ),
        )
        path = f"{base}/imports/{archive['id']}"
        assert archive["documents"] == [{"path": "docs/项目需求.md", "size": len(raw.encode())}]
        assert archive["needs_manual_endpoints"] is False
        assert archive["confirmed_endpoints"] == []
        assert client.get(f"{base}/requirements").json() == []
        assert client.get(f"{base}/endpoints").json() == []
        first, second, duplicate, _ = archive["endpoint_candidates"]
        assert (first["method"], first["path"], first["source_path"]) == (
            "GET",
            "/catalog",
            "spec.json",
        )
        assert first["parameters"] == [
            {
                "name": "limit",
                "in": "query",
                "required": False,
                "type": "integer",
                "description": "",
            }
        ]
        assert first["responses"] == [{"status": "200", "description": "返回目录列表"}]
        assert duplicate["source_path"] == "copy.json"
        manual = client.post(f"{base}/endpoints", json={"method": "GET", "path": "/catalog"}).json()
        selection = {
            "candidate_ids": [
                first["candidate_id"],
                duplicate["candidate_id"],
                second["candidate_id"],
            ]
        }
        result = client.post(f"{path}/confirm-endpoints", json=selection).json()["endpoints"]
        assert result[0]["endpoint"] == result[1]["endpoint"] == manual
        assert result[2]["endpoint"]["version"] == 1
        assert result[2]["endpoint"]["method"] == "POST"
        assert (
            client.post(f"{path}/confirm-endpoints", json=selection).json()["endpoints"] == result
        )
        assert len(client.get(f"{base}/endpoints").json()) == 2

        selection = {"path": "docs/项目需求.md", "start": 5, "end": 12}
        preview = client.post(f"{path}/preview", json=selection).json()
        assert preview["text"] == "选定的需求。\r"
        source = {"import_id": archive["id"], **selection}
        saved = client.post(
            f"{base}/requirements", json={"text": "编辑后的需求正文", "source": source}
        ).json()
        assert saved["version"] == 1 and saved["source"] == source
        updated = client.patch(
            f"{base}/requirements/{saved['id']}", json={"text": "补充答案"}
        ).json()
        assert updated["version"] == 2 and updated["source"] == source

    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path).json()["confirmed_endpoints"] == result
        assert restarted.get(f"{base}/requirements").json() == [updated]
        assert restarted.post(f"{path}/preview", json=selection).json() == preview
        repository = restarted.app.state.project_repository
        assert repository.get_requirement_source(base.split("/")[-1], saved["id"]) == source
        assert (
            repository.get_requirement_version(base.split("/")[-1], saved["id"], 1)["text"]
            == saved["text"]
        )


def test_project_without_openapi_allows_manual_entry_and_long_document_selection(client):
    base = project(client)
    archive = checked_upload(client, base, zip_bytes(("notes.txt", "字" * 17000 + "末尾")))
    path = f"{base}/imports/{archive['id']}"
    assert archive["endpoint_candidates"] == [] and archive["needs_manual_endpoints"]
    first = client.post(f"{path}/preview", json={"path": "notes.txt"}).json()
    assert first["end"] == 16000 and first["total_chars"] == 17002
    tail = client.post(f"{path}/preview", json={"path": "notes.txt", "start": 17000}).json()
    assert tail["text"] == "末尾"
    assert (
        client.post(f"{path}/preview", json={"path": "notes.txt", "end": 16001}).status_code == 422
    )
    assert (
        client.post(f"{base}/endpoints", json={"method": "GET", "path": "/hours"}).status_code
        == 201
    )
    saved = client.post(f"{base}/requirements", json={"text": "手工填写正文"}).json()
    assert saved["version"] == 1 and "source" not in saved


def test_project_isolation_and_atomic_confirmation(client):
    first, second = project(client), project(client)
    data = zip_bytes(("readme.md", "需求"), ("openapi.json", api_description()))
    archive = checked_upload(client, first, data)
    path, wrong_path = (f"{base}/imports/{archive['id']}" for base in (first, second))
    candidate = archive["endpoint_candidates"][0]["candidate_id"]
    assert client.get(wrong_path).status_code == 404
    assert client.post(f"{wrong_path}/preview", json={"path": "readme.md"}).status_code == 404
    assert (
        client.post(
            f"{wrong_path}/confirm-endpoints", json={"candidate_ids": [candidate]}
        ).status_code
        == 404
    )
    source = {"import_id": archive["id"], "path": "readme.md", "start": 0, "end": 2}
    assert (
        client.post(
            f"{second}/requirements", json={"text": "跨项目引用", "source": source}
        ).status_code
        == 404
    )
    assert client.get(f"{second}/requirements").json() == []
    assert (
        client.post(
            f"{path}/confirm-endpoints", json={"candidate_ids": [candidate, "absent"]}
        ).status_code
        == 422
    )
    assert client.get(f"{first}/endpoints").json() == []
    assert client.get(path).json()["confirmed_endpoints"] == []

    other_archive = checked_upload(client, second, data)
    endpoint_ids = []
    for base, manifest in [(first, archive), (second, other_archive)]:
        result = client.post(
            f"{base}/imports/{manifest['id']}/confirm-endpoints",
            json={"candidate_ids": [candidate]},
        )
        endpoint_ids.append(result.json()["endpoints"][0]["endpoint"]["id"])
    assert endpoint_ids[0] != endpoint_ids[1]


def test_concurrent_confirmation_reuses_one_endpoint_id(client):
    base = project(client)
    archive = checked_upload(client, base, zip_bytes(("api.json", api_description())))
    path = f"{base}/imports/{archive['id']}/confirm-endpoints"
    payload = {"candidate_ids": [archive["endpoint_candidates"][0]["candidate_id"]]}

    def confirm(_):
        response = client.post(path, json=payload)
        assert response.status_code == 200
        return response.json()["endpoints"][0]["endpoint"]["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(confirm, range(8)))) == 1
    assert len(client.get(f"{base}/endpoints").json()) == 1


def test_template_is_visible_but_requires_concrete_path(client):
    base = project(client)
    spec = json.dumps({"openapi": "3.0.3", "paths": {"/stock/{sku}": {"get": {}}}})
    archive = checked_upload(client, base, zip_bytes(("api.json", spec)))
    candidate = archive["endpoint_candidates"][0]
    assert candidate["path"] == "/stock/{sku}" and candidate["requires_manual_registration"]
    assert archive["needs_manual_endpoints"]
    result = client.post(
        f"{base}/imports/{archive['id']}/confirm-endpoints",
        json={"candidate_ids": [candidate["candidate_id"]]},
    )
    assert result.status_code == 422 and "手工" in result.json()["detail"]
    assert client.get(f"{base}/endpoints").json() == []


def test_invalid_uploads_leave_no_rows(client):
    base = project(client)
    symlink = ZipInfo("notes.md")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    invalid = [
        b"invalid zip",
        zip_bytes(("../notes.md", "body")),
        zip_bytes((symlink, "target")),
        zip_bytes(("A.txt", "a"), ("a.txt", "b")),
    ]
    for data in invalid:
        response = upload(client, base, data)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)
    with client.app.state.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM project_imports").fetchone()[0] == 0
    assert client.get(f"{base}/endpoints").json() == []
    assert client.get(f"{base}/requirements").json() == []


def test_selected_text_decode_failure_does_not_create_requirement(client):
    base = project(client)
    archive = checked_upload(
        client, base, zip_bytes(("notes.txt", b"\xff\xfe"), ("etc.bin", b"other"))
    )
    path = f"{base}/imports/{archive['id']}/preview"
    assert client.post(path, json={"path": "etc.bin"}).status_code == 404
    response = client.post(path, json={"path": "notes.txt"})
    assert response.status_code == 422 and "UTF-8" in response.json()["detail"]
    source = {"import_id": archive["id"], "path": "notes.txt", "start": 0, "end": 1}
    assert (
        client.post(f"{base}/requirements", json={"text": "不能落库", "source": source}).status_code
        == 422
    )
    assert client.get(f"{base}/requirements").json() == []


def test_request_and_declared_inflation_limits(client, monkeypatch):
    base = project(client)
    monkeypatch.setattr(router, "MAX_UPLOAD", 300)
    assert upload(client, base, b"x" * 301).status_code == 413
    # httpx sends this iterable without Content-Length. Limit the bytes as consumed.
    assert upload(client, base, iter((b"x" * 200, b"x" * 101))).status_code == 413
    monkeypatch.setattr(archives, "MAX_EXPANDED", 200)
    compressed = zip_bytes(("notes.txt", "a" * 201))
    assert len(compressed) < 300
    assert upload(client, base, compressed).status_code == 413
    monkeypatch.setattr(archives, "MAX_ENTRIES", 1)
    assert upload(client, base, zip_bytes(("a.txt", "a"), ("b.txt", "b"))).status_code == 413
    with client.app.state.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM project_imports").fetchone()[0] == 0


def test_old_database_keeps_existing_rows_and_accepts_import(settings):
    with sqlite3.connect(settings.database_path) as conn:
        conn.executescript("""
            CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE requirements(id TEXT PRIMARY KEY, project_id TEXT, text TEXT, version INTEGER);
            CREATE TABLE endpoints(id TEXT PRIMARY KEY, project_id TEXT, method TEXT, path TEXT, version INTEGER);
            INSERT INTO projects VALUES ('legacy', '旧项目');
            INSERT INTO requirements VALUES ('legacy-req', 'legacy', '旧需求', 1);
            INSERT INTO endpoints VALUES ('legacy-endpoint', 'legacy', 'GET', '/catalog', 1);
        """)
    with TestClient(create_app(settings)) as client:
        base = "/api/projects/legacy"
        assert client.get(f"{base}/requirements").json() == [
            {"id": "legacy-req", "text": "旧需求", "version": 1}
        ]
        archive = checked_upload(client, base, zip_bytes(("spec.json", api_description())))
        path = f"{base}/imports/{archive['id']}/confirm-endpoints"
        confirmed = client.post(
            path, json={"candidate_ids": [archive["endpoint_candidates"][0]["candidate_id"]]}
        ).json()
        assert confirmed["endpoints"][0]["endpoint"]["id"] == "legacy-endpoint"
