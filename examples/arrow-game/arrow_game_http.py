"""Expose the reviewed Arrow Game rules to TestPilot on the local machine."""

import argparse
from dataclasses import asdict
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import module_from_spec
import json
from pathlib import Path
import sys
from zipfile import ZipFile
import zipimport

# 只核对游戏规则代码本身：需求文档、清单等材料允许重编写，规则不允许改。
# 该值取自交付包 manifest.json 中 game_logic.py 的 sha256。
RULES_HASH = "ac49834f742ef21a25ad4c0d29eb87ddf87301102097b6012eb3091f16c11d2c"


def load_rules(archive):
    with ZipFile(archive) as package:
        module_path = next(name for name in package.namelist() if name.endswith("/game_logic.py"))
        rules_bytes = package.read(module_path)
    if sha256(rules_bytes).hexdigest() != RULES_HASH:
        raise ValueError("ZIP 里的 game_logic.py 与已核对的游戏规则不一致")
    folder = module_path.rsplit("/", 1)[0]
    importer = zipimport.zipimporter(f"{archive}/{folder}")
    spec = importer.find_spec("game_logic")
    if spec is None or spec.loader is None:
        raise ValueError("项目 ZIP 缺少 game_logic.py")
    rules = module_from_spec(spec)
    sys.modules[spec.name] = rules
    spec.loader.exec_module(rules)
    return rules


def test_move(rules, request):
    board = request["board"]
    row, col = request["row"], request["col"]
    if (
        not isinstance(board, list)
        or not 1 <= len(board) <= 10
        or any(not isinstance(line, str) or not 1 <= len(line) <= 10 for line in board)
        or type(row) is not int
        or type(col) is not int
    ):
        raise ValueError("board 必须是 1–10 行字符串，row 和 col 必须是整数")
    rules.validate_board(board)
    game = rules.Game([rules.Level("TestPilot", "", tuple(board))])
    game.start()
    result = asdict(game.click(row, col))
    return {
        **result,
        "lives": game.lives,
        "board": ["".join(line) for line in game.board],
        "state": game.state.value,
    }


def make_handler(rules):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, response):
            body = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"status": "ok", "project": "arrow-game"})
            else:
                self.send_json(404, {"detail": "接口不存在"})

        def do_POST(self):
            if self.path != "/game/move":
                self.send_json(404, {"detail": "接口不存在"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("请求体大小必须在 1–4096 字节内")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("请求必须是 JSON 对象")
                result = test_move(rules, payload)
            except (KeyError, TypeError, ValueError) as exc:
                self.send_json(422, {"detail": str(exc)})
                return
            self.send_json(200, result)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--port", type=int, default=18085)
    args = parser.parse_args()
    rules = load_rules(args.archive.resolve())
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(rules)) as server:
        print(f"Arrow Game rules listening on http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
