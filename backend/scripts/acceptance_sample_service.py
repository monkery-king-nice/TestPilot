"""Run one of the two project-import acceptance APIs on a local port."""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def make_server(sample, service_id, port, *, check=None, token=None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            check_ok = check is None or self.headers.get("X-Sample-Check") == check
            status, payload = 404, {"error": "UNKNOWN_ROUTE"}
            if sample == "book-catalog" and url.path == "/books":
                if check_ok:
                    params = parse_qs(url.query)
                    books = ["软件工程", "数据库系统"]
                    query = params.get("q", [""])[0]
                    matches = [title for title in books if query in title]
                    limit = params.get("limit", ["1"])[0]
                    if limit in ("1", "2"):
                        status, payload = 200, {"books": matches[: int(limit)]}
                    else:
                        status, payload = 400, {"error": "INVALID_LIMIT"}
                else:
                    status, payload = 401, {"error": "INVALID_SAMPLE_CHECK"}
            elif sample == "room-schedule" and url.path == "/rooms":
                status, payload = 200, {"slots": []}
            payload["service"] = service_id
            if token is not None and status == 200:
                payload["token"] = token
            server.received.append({"method": "GET", "path": self.path, "status": status})
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            print(f"[{service_id}] {format % args}", flush=True)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.received = []
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", choices=("book-catalog", "room-schedule"))
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--service-id")
    args = parser.parse_args()
    service_id = args.service_id or args.sample
    with make_server(
        args.sample, service_id, args.port, check=os.getenv("TESTPILOT_SAMPLE_CHECK")
    ) as server:
        print(f"{service_id}: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
