"""Cross-module acceptance with real SQLite and loopback HTTP targets."""

import json
import secrets
import time
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from threading import Thread
from zipfile import ZipFile

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.agent import clarify, workflow
from backend.scripts.acceptance_sample_service import make_server
from backend.scripts.verify_project_imports import write_samples

BOOK = "book-catalog"
ROOM = "room-schedule"
BOOK_ANSWER = "未传 limit 时最多返回 1 本图书。"
ROOM_ANSWER = "节假日返回 200 和空时段列表。"


def call(client, method, path, status=200, **kwargs):
    response = client.request(method, path, **kwargs)
    assert response.status_code == status, (
        f"{method} {path}: expected {status}, got {response.status_code}: {response.text}"
    )
    return response.json()


@contextmanager
def live_target(sample, service_id, **kwargs):
    with make_server(sample, service_id, 0, **kwargs) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=3)


def upload(client, project, package, status=201):
    return call(
        client,
        "POST",
        project + "/imports",
        status,
        params={"filename": package.name},
        content=package.read_bytes(),
        headers={"Content-Type": "application/zip"},
    )


def import_project(client, sample, *, automatic):
    project = call(client, "POST", "/api/projects", 201, json={"name": sample.stem})
    base = f"/api/projects/{project['id']}"
    manifest = upload(client, base, sample)
    assert manifest["project_id"] == project["id"]
    archive = f"{base}/imports/{manifest['id']}"
    document = manifest["documents"][0]["path"]
    preview = call(client, "POST", archive + "/preview", json={"path": document})
    source = {key: preview[key] for key in ("import_id", "path", "start", "end")}
    # Keep the ambiguous line only in the selected original to exercise source citations.
    first_rule = next(line for line in preview["text"].splitlines() if "200" in line)
    requirement = call(
        client, "POST", base + "/requirements", 201, json={"text": first_rule, "source": source}
    )
    assert requirement["version"] == 1 and requirement["source"] == source
    assert call(client, "GET", base + "/requirements") == [requirement]
    assert manifest["needs_manual_endpoints"] is not automatic
    if automatic:
        ids = [item["candidate_id"] for item in manifest["endpoint_candidates"]]
        confirmed = call(
            client, "POST", archive + "/confirm-endpoints", json={"candidate_ids": ids}
        )
        endpoint = confirmed["endpoints"][0]["endpoint"]
    else:
        assert manifest["endpoint_candidates"] == []
        endpoint = call(
            client, "POST", base + "/endpoints", 201, json={"method": "GET", "path": "/rooms"}
        )
    assert endpoint["method"] == "GET"
    assert endpoint["path"] == ("/books" if automatic else "/rooms")
    assert call(client, "GET", base + "/endpoints") == [endpoint]
    return base, archive, requirement, endpoint


def bind(client, base, service_id, server, check=None):
    env = {
        "target": "local",
        "service_id": service_id,
        "base_url": f"http://127.0.0.1:{server.server_port}",
    }
    if check:
        env["secrets"] = {"username": "acceptance-account", "password": check}
    saved = call(client, "PUT", base + "/environment", json=env)
    assert "secrets" not in saved
    return saved


def case_step(endpoint, assertions, *, check=False):
    return {
        "name": "query",
        "phase": "test",
        "endpoint_id": endpoint["id"],
        "endpoint_version": endpoint["version"],
        "headers": {"X-Sample-Check": "{{env.password}}"} if check else {},
        "assertions": [{"type": "status", "expected": 200}, *assertions],
    }


def create_run(client, base, env, cases, status=202):
    return call(
        client,
        "POST",
        base + "/runs",
        status,
        json={
            "environment_version": env["environment_version"],
            "cases": [{key: case[key] for key in ("id", "version")} for case in cases],
        },
    )


def verify_run(client, base, env, cases, outcomes, evidence, label):
    run = create_run(client, base, env, cases)
    route = f"{base}/runs/{run['run_id']}"
    deadline = time.monotonic() + 10
    while (detail := call(client, "GET", route))["status"] != "COMPLETED":
        assert time.monotonic() < deadline, detail
        time.sleep(0.05)
    assert [result["outcome"] for result in detail["results"]] == outcomes
    assert sum(detail["counts"].values()) == len(cases)
    assert detail["target"] == {
        "kind": env["target"],
        **{key: env[key] for key in ("service_id", "base_url", "environment_version")},
    }
    report = client.get(route + "/report")
    assert report.status_code == 200
    assert (
        report.headers["Content-Disposition"]
        == f'attachment; filename="testpilot-{run["run_id"]}.html"'
    )
    for value in (
        run["run_id"],
        base.rsplit("/", 1)[-1],
        env["base_url"],
        env["service_id"],
        f"环境 v{env['environment_version']}",
    ):
        assert value in report.text
    for case, result in zip(cases, detail["results"]):
        for value in (
            case["title"],
            case["requirement_id"],
            f"版本 {case['requirement_version']}",
            result["outcome"],
        ):
            assert value in report.text
    (evidence / f"{label}.html").write_bytes(report.content)
    return {**detail, "report_path": route + "/report"}


def confirm(client, base, case):
    confirmed = call(
        client, "POST", f"{base}/cases/{case['id']}/confirm", json={"version": case["version"]}
    )
    assert confirmed["status"] == "CONFIRMED"
    return confirmed


def test_import_to_real_execution_and_frozen_report(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    samples = write_samples(evidence)
    password = secrets.token_urlsafe()
    next_password = secrets.token_urlsafe()
    response_token = secrets.token_urlsafe()
    app = create_app(Settings(database_path=tmp_path / "testpilot.sqlite3"))
    with ExitStack() as stack:
        client = stack.enter_context(TestClient(app))
        a1 = stack.enter_context(
            live_target(BOOK, "catalog-a1", check=password, token=response_token)
        )
        a2 = stack.enter_context(live_target(BOOK, "catalog-a2", check=next_password))
        with live_target(ROOM, "rooms-b") as b:
            pa, archive_a, req_a, ep_a = import_project(client, samples[BOOK], automatic=True)
            pb, archive_b, req_b, ep_b = import_project(client, samples[ROOM], automatic=False)
            env_a = bind(client, pa, "catalog-a1", a1, password)
            env_b = bind(client, pb, "rooms-b", b)
            for path in (archive_a.replace(pa, pb), archive_b.replace(pb, pa)):
                call(client, "GET", path, 404)
            call(
                client,
                "POST",
                pb + "/agent/clarify",
                404,
                json={"requirement_id": req_a["id"], "requirement_version": 1},
            )

            seed = {
                "title": "图书列表 v1",
                "requirement_id": req_a["id"],
                "requirement_version": 1,
                "expected_basis": req_a["text"],
                "steps": [case_step(ep_a, [], check=True)],
            }
            for foreign in (
                {**seed, "requirement_id": req_b["id"]},
                {**seed, "steps": [case_step(ep_b, [])]},
            ):
                call(client, "POST", pa + "/cases", 404, json=foreign)
            old = call(client, "POST", pa + "/cases", 201, json=seed)
            rejected_unconfirmed = create_run(client, pa, env_a, [old], 422)
            assert "尚未确认" in rejected_unconfirmed["detail"] and a1.received == []
            old = confirm(client, pa, old)
            before = verify_run(client, pa, env_a, [old], ["PASS"], evidence, "A-v1")
            assert "catalog-a1" in before["results"][0]["steps"][0]["response_summary"]
            assert len(a1.received) == 1 and b.received == []

            model_contexts = {
                req_a["id"]: (
                    ep_a,
                    req_a,
                    "limit 分页",
                    BOOK_ANSWER,
                    "未传 limit 时最多返回几本图书？",
                    {"type": "json_equals", "path": "books", "expected": ["软件工程"]},
                ),
                req_b["id"]: (
                    ep_b,
                    req_b,
                    "节假日",
                    ROOM_ANSWER,
                    "节假日返回什么状态和时段列表？",
                    {"type": "json_equals", "path": "slots", "expected": []},
                ),
            }

            def mock_model(_prompt, raw, *, max_tokens=None):
                context = json.loads(raw)
                req = context["requirement"]
                endpoint, original, keyword, answer, question, assertion = model_contexts[req["id"]]
                assert context["endpoints"] == [endpoint]
                assert context["source_excerpt"]["path"] == original["source"]["path"]
                quote = next(
                    line
                    for line in context["source_excerpt"]["text"].splitlines()
                    if keyword in line
                )
                if max_tokens is None:
                    return {
                        "questions": []
                        if answer in req["text"]
                        else [{"quote": quote, "question": question}]
                    }
                assert req["version"] == 2 and answer in req["text"]
                return {
                    "drafts": [
                        {
                            "title": "图书分页 v2" if endpoint == ep_a else "节假日时段 v2",
                            "expected_basis": answer,
                            "steps": [case_step(endpoint, [assertion], check=endpoint == ep_a)],
                        }
                    ]
                }

            monkeypatch.setattr(clarify, "ask_json", mock_model)
            monkeypatch.setattr(workflow, "ask_json", mock_model)

            def revise(base, req, answer):
                payload = {"requirement_id": req["id"], "requirement_version": 1}
                clarification = call(client, "POST", base + "/agent/clarify", json=payload)
                (question,) = clarification["questions"]
                assert question["source_path"] == req["source"]["path"]
                text = req["text"] + f"\n\n用户补充：{answer}"
                resource = base + "/requirements/" + req["id"]
                updated = call(
                    client, "PATCH", resource, json={"text": text, "expected_version": 1}
                )
                assert updated["version"] == 2 and updated["source"] == req["source"]
                assert call(client, "GET", base + "/requirements") == [updated]
                for action in ("clarify", "generate"):
                    call(client, "POST", base + "/agent/" + action, 409, json=payload)
                call(
                    client,
                    "PATCH",
                    resource,
                    409,
                    json={"text": "失效的答案", "expected_version": 1},
                )
                payload["requirement_version"] = 2
                assert (
                    call(client, "POST", base + "/agent/clarify", json=payload)["questions"] == []
                )
                (draft,) = call(client, "POST", base + "/agent/generate", json=payload)["drafts"]
                assert draft["requirement_version"] == 2 and draft["expected_basis"] == answer
                return question, updated, draft

            question_a, v2_a, draft_a = revise(pa, req_a, BOOK_ANSWER)
            question_b, v2_b, draft_b = revise(pb, req_b, ROOM_ANSWER)
            stale = create_run(client, pa, env_a, [old], 422)
            assert "需求版本已过期" in stale["detail"] and len(a1.received) == 1
            case_a = call(client, "PATCH", pa + "/cases/" + old["id"], json=draft_a)
            assert case_a["status"] == "NEEDS_REVIEW" and case_a["version"] > old["version"]
            create_run(client, pa, env_a, [case_a], 422)
            case_a = confirm(client, pa, case_a)
            new_env_a = bind(client, pa, "catalog-a2", a2, next_password)
            stale_env = create_run(client, pa, env_a, [case_a], 409)
            assert "环境" in stale_env["detail"] and a2.received == []
            after = verify_run(client, pa, new_env_a, [case_a], ["PASS"], evidence, "A-v2")
            assert len(a1.received) == len(a2.received) == 1 and b.received == []
            assert "catalog-a2" in after["results"][0]["steps"][0]["response_summary"]
            redownload = client.get(before["report_path"])
            assert redownload.status_code == 200
            assert redownload.content == (evidence / "A-v1.html").read_bytes()
            assert (
                BOOK_ANSWER not in redownload.text and new_env_a["base_url"] not in redownload.text
            )
            (evidence / "A-v1-redownload.html").write_bytes(redownload.content)
            call(client, "GET", before["report_path"].replace(pa, pb), 404)

            assert call(client, "GET", pb + "/environment") == env_b
            assert call(client, "GET", pb + "/cases") == []
            case_b = confirm(client, pb, call(client, "POST", pb + "/cases", 201, json=draft_b))
            bad_draft = deepcopy(draft_b)
            bad_draft["title"] = "故意错断言：节假日仍有时段"
            bad_draft["expected_basis"] = "验收专用反例，期望值故意与需求相反"
            bad_draft["steps"][0]["assertions"][1]["expected"] = ["09:00"]
            wrong = confirm(client, pb, call(client, "POST", pb + "/cases", 201, json=bad_draft))
            mixed = verify_run(
                client, pb, env_b, [case_b, wrong], ["PASS", "FAIL"], evidence, "B-v2"
            )
            failure = mixed["results"][1]["steps"][0]
            assert "实际 []" in failure["assertion_diffs"][0]
            assert "rooms-b" in failure["response_summary"] and len(b.received) == 2
            assert len(a1.received) == len(a2.received) == 1
            endpoint_b_requests = list(b.received)

        stopped = verify_run(client, pb, env_b, [case_b], ["ERROR"], evidence, "B-stopped")
        assert stopped["results"][0]["steps"][0]["error_stage"] == "connection"
        record = {
            "model": "替身，仅替换供应商响应；HTTP 被测服务真实运行",
            "A": {
                "question": question_a,
                "requirement_v1": req_a,
                "requirement_v2": v2_a,
                "v1": before,
                "v2": after,
                "old_report_byte_identical": True,
                "a1_requests": a1.received,
                "a2_requests": a2.received,
            },
            "B": {
                "question": question_b,
                "requirement_v1": req_b,
                "requirement_v2": v2_b,
                "mixed": mixed,
                "stopped": stopped,
                "requests": endpoint_b_requests,
            },
            "rejections": {
                "unconfirmed": rejected_unconfirmed,
                "stale_case": stale,
                "stale_environment": stale_env,
            },
        }
        serialized = json.dumps(record, ensure_ascii=False, indent=2)
        assert "[REDACTED]" in (evidence / "A-v1.html").read_text(encoding="utf-8")
        for value in (password, next_password, response_token):
            assert value not in serialized
            assert all(value.encode() not in path.read_bytes() for path in evidence.glob("*.html"))
        (evidence / "run-evidence.json").write_text(serialized, encoding="utf-8")


def test_import_recovery_and_missing_model(tmp_path, monkeypatch):
    # No outbound call: exercise the deployed provider's missing-key error path.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TESTPILOT_MODEL_KEY", raising=False)
    monkeypatch.delenv("TESTPILOT_MODEL_URL", raising=False)
    monkeypatch.delenv("TESTPILOT_MODEL", raising=False)
    app = create_app(Settings(database_path=tmp_path / "recover.sqlite3"))
    with TestClient(app) as client:
        project = call(client, "POST", "/api/projects", 201, json={"name": "缺文档项目"})
        base = f"/api/projects/{project['id']}"
        no_docs = tmp_path / "no-docs.zip"
        with ZipFile(no_docs, "w") as archive:
            archive.writestr("data/example.json", "{}")
        manifest = upload(client, base, no_docs)
        assert manifest["documents"] == [] and manifest["needs_manual_endpoints"]
        saved = call(client, "POST", base + "/requirements", 201, json={"text": "手工补录需求"})
        endpoint = call(
            client, "POST", base + "/endpoints", 201, json={"method": "GET", "path": "/rooms"}
        )
        bad_zip = tmp_path / "corrupt.zip"
        bad_zip.write_bytes(b"this file is not a ZIP")
        bad = upload(client, base, bad_zip, 422)
        assert "ZIP" in bad["detail"]
        payload = {"requirement_id": saved["id"], "requirement_version": 1}
        errors = {}
        for action in ("clarify", "generate"):
            errors[action] = call(client, "POST", base + "/agent/" + action, 502, json=payload)
            assert "DEEPSEEK_API_KEY" in errors[action]["detail"]
        assert call(client, "GET", base + "/requirements") == [saved]
        assert call(client, "GET", base + "/endpoints") == [endpoint]
        assert call(client, "GET", base + "/cases") == []
        (tmp_path / "negative-evidence.json").write_text(
            json.dumps(
                {
                    "no_documents": manifest,
                    "manual_requirement": saved,
                    "manual_endpoint": endpoint,
                    "invalid_zip": {"status": 422, **bad},
                    "missing_model": {"status": 502, **errors},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
