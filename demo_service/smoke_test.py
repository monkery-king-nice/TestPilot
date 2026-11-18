"""Run four real HTTP checks. Exit nonzero on the first mismatch."""
import json
import os
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

opener = build_opener(ProxyHandler({}))


def request(base, path, body=None, token=None):
    headers = {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = opener.open(Request(base + path, data=data, headers=headers), timeout=4)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def check(label, status, expected, matches):
    if status != expected or not matches:
        raise SystemExit(f"FAIL {label}: HTTP {status}, expected HTTP {expected} and matching JSON")
    print(f"PASS {label}: HTTP {status}")


def run(base):
    username, password = os.getenv("DEMO_USERNAME", "demo-user"), os.environ["DEMO_PASSWORD"]
    status, body = request(base, "/auth/login", {"username": username, "password": password})
    token = body.get("token")
    check("valid login + nonempty token", status, 200, isinstance(token, str) and bool(token))
    status, body = request(base, "/auth/login", {"username": username, "password": password + "!"})
    check("wrong password + INVALID_CREDENTIALS", status, 401, body.get("code") == "INVALID_CREDENTIALS")
    status, body = request(base, "/me", token=token)
    check("bearer token + user.id=demo-user", status, 200, body.get("user", {}).get("id") == "demo-user")
    status, body = request(base, "/me")
    check("missing token + UNAUTHORIZED", status, 401, body.get("code") == "UNAUTHORIZED")


if __name__ == "__main__":
    run("http://127.0.0.1:8010")
