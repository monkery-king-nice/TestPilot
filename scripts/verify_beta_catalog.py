"""Exercise the private Beta workflow with synthetic sensor data and a real HTTP target."""
import argparse
from functools import partial
from getpass import getpass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.app.core.config import Settings
from backend.app.main import create_app


def verify(directory, output, live):
    rule = "本次只测正常读取。在本机测试环境中，无需登录，使用 GET /reading.json，不传查询参数、请求头或请求体。响应为 HTTP 200，JSON 对象的 unit 字段等于字符串 C。"
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.write(ROOT / "examples/station/station.md", arcname="station.md")
    web = directory / "site"
    web.mkdir()
    (web / "reading.json").write_text('{"unit":"C","temperature":21}', encoding="utf-8")
    target = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(web)))
    thread = Thread(target=target.serve_forever, daemon=True)
    thread.start()
    evidence = {"sample": "合成气象站 / Python 标准库 HTTP 服务，无 OpenAPI", "live_model": live}
    try:
        with TestClient(create_app(Settings(database_path=directory / "qa.sqlite3"))) as client:
            def post(path, body):
                response = client.post(path, json=body)
                if response.is_error:
                    raise ValueError(f"HTTP {response.status_code}: {response.json().get('detail')}")
                return response.json()
            base = "/api/projects/" + post("/api/projects", {"name": "气象观测站"})["id"]
            res = client.post(base + "/imports", params={"filename": "station.zip"},
                              content=stream.getvalue(), headers={"Content-Type": "application/zip"})
            res.raise_for_status()
            manifest = res.json()
            assert not manifest["endpoint_candidates"]
            excerpt = post(base + "/imports/" + manifest["id"] + "/preview", {"path": "station.md"})
            source = {k: excerpt[k] for k in ("import_id", "path", "start", "end")}
            req = post(base + "/requirements", {"text": excerpt["text"], "source": source})
            ep = post(base + "/endpoints", {"method": "GET", "path": "/reading.json"})
            def agent(action, version):
                payload = {"requirement_id": req["id"], "requirement_version": version}
                preview = post(base + "/agent/preview", payload)
                return post(base + "/agent/" + action, {**payload, "context_digest": preview["digest"]})
            if live:
                evidence["clarification"] = agent("clarify", 1)
                output.mkdir(exist_ok=True, parents=True)
                (output / "clarification.json").write_text(json.dumps(evidence["clarification"], ensure_ascii=False, indent=2), encoding="utf-8")
            res = client.patch(base + "/requirements/" + req["id"], json={"expected_version": 1, "text": rule})
            res.raise_for_status()
            if live:
                evidence["generation"] = agent("generate", 2)
            res = client.put(base + "/environment", json={"target":"local", "service_id":"station",
                             "base_url":f"http://127.0.0.1:{target.server_port}"})
            res.raise_for_status()
            cases = []
            for title, expected in [("读取摄氏温度", "C"), ("人为改错预期", "F")]:
                case = post(base + "/cases", {"title":title, "expected_basis":rule,
                    "requirement_id":req["id"], "requirement_version":2,
                    "steps":[{"name":"read","phase":"test","endpoint_id":ep["id"],"endpoint_version":1,
                              "assertions":[{"type":"status","expected":200},
                                            {"type":"json_equals","path":"unit","expected":expected}]}]})
                item = post(base + "/cases/" + case["id"] + "/confirm", {"version":case["version"]})
                cases.append({"id":item["id"],"version":item["version"]})
            run = post(base + "/runs", {"cases": cases})
            path = base + "/runs/" + run["run_id"]
            deadline = monotonic() + 20
            while monotonic() < deadline:
                detail = client.get(path).json()
                if detail["status"] == "COMPLETED":
                    break
                sleep(0.1)
            assert detail["counts"]["PASS"] == detail["counts"]["FAIL"] == 1, detail["counts"]
            evidence["counts"] = detail["counts"]
            fail = next(item for item in detail["results"] if item["outcome"] == "FAIL")
            evidence["difference"] = fail["steps"][0]["assertion_diffs"]
            report = client.get(path + "/report")
            report.raise_for_status()
            output.mkdir(exist_ok=True, parents=True)
            (output / "station-report.html").write_bytes(report.content)
            if live:
                body = {"case_id":fail["case_id"]}
                preview = post(path + "/analysis/preview", body)
                evidence["analysis"] = post(path + "/analysis", {**body,"context_digest":preview["digest"]})
                assert report.content == client.get(path + "/report").content
            (output / "station.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Verified sensor station:", evidence["counts"], "real model:", live)
    finally:
        target.shutdown()
        target.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send only the synthetic fixture to the official DeepSeek API")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/beta-station")
    args = parser.parse_args()
    if args.live:
        os.environ["TESTPILOT_MODEL_URL"] = "https://api.deepseek.com/chat/completions"
        if not os.getenv("DEEPSEEK_API_KEY"):
            os.environ["DEEPSEEK_API_KEY"] = getpass("DeepSeek key (hidden): ")
    with TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        verify(Path(temp), args.output, args.live)
