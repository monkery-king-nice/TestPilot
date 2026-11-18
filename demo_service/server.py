"""Local TestPilot fixture. Run with Python 3.9+."""
import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 8010
USER_ID = "demo-user"


def same(value, expected):
    return isinstance(value, str) and hmac.compare_digest(value.encode(), expected.encode())


class DemoHandler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/auth/login":
            return self.respond(404, {"code": "NOT_FOUND"})
        if self.headers.get_content_type() != "application/json":
            return self.respond(415, {"code": "EXPECTED_JSON"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                raise ValueError()
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            return self.respond(400, {"code": "INVALID_JSON"})
        if not (same(body.get("username"), self.server.username)
                and same(body.get("password"), self.server.password)):
            return self.respond(401, {"code": "INVALID_CREDENTIALS"})
        return self.respond(200, {"token": self.server.token})

    def do_GET(self):
        if self.path != "/me":
            return self.respond(404, {"code": "NOT_FOUND"})
        if not same(self.headers.get("Authorization"), "Bearer " + self.server.token):
            return self.respond(401, {"code": "UNAUTHORIZED"})
        return self.respond(200, {"user": {"id": USER_ID}})


def make_server(username, password, port=PORT):
    server = ThreadingHTTPServer((HOST, port), DemoHandler)
    server.username, server.password = username, password
    server.token = secrets.token_urlsafe(32)
    return server


if __name__ == "__main__":
    password = os.getenv("DEMO_PASSWORD")
    if not password:
        raise SystemExit("Set DEMO_PASSWORD before starting the demo.")
    with make_server(os.getenv("DEMO_USERNAME", USER_ID), password) as server:
        print(f"TestPilot demo listening on http://{HOST}:{PORT}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
