import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from .clarify import ModelError
from .router import build_router


class RouterTest(unittest.TestCase):
    def client(self, provider):
        app = FastAPI()
        app.include_router(build_router(lambda p, r: "登录" if (p, r) == ("demo", "r1") else None, provider))
        return TestClient(app)

    def test_project_boundary_and_normal_request(self):
        client = self.client(lambda text: {"questions": [{"quote": text, "question": "成功条件是什么？"}]})
        for project, expected in (("demo", 200), ("other", 404)):
            response = client.post(f"/api/projects/{project}/agent/clarify", json={"requirement_id":"r1"})
            self.assertEqual(response.status_code, expected)
            if expected == 200:
                self.assertEqual(response.json()["status"], "NEEDS_INFO")

    def test_model_failure_is_visible(self):
        def fail(_):
            raise ModelError("模型服务不可用")
        response = self.client(fail).post("/api/projects/demo/agent/clarify", json={"requirement_id":"r1"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "模型服务不可用")
