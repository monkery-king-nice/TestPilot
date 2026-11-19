"""Private child hosts: stdin newline/EOF requests graceful service shutdown."""

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))


def main():
    if sys.argv[1] == "api":
        import uvicorn

        service = uvicorn.Server(
            uvicorn.Config(
                "app.main:app",
                host="127.0.0.1",
                port=8000,
                access_log=False,
                log_level="warning",
            )
        )

        def stop():
            sys.stdin.readline()
            service.should_exit = True

        threading.Thread(target=stop, daemon=True).start()
        service.run()
    elif sys.argv[1] == "demo":
        from demo_service.server import make_server

        with make_server(
            os.getenv("DEMO_USERNAME", "demo-user"), os.environ["DEMO_PASSWORD"]
        ) as service:

            def stop():
                sys.stdin.readline()
                service.shutdown()

            threading.Thread(target=stop, daemon=True).start()
            service.serve_forever(poll_interval=0.1)
    else:
        raise SystemExit("Unknown local service")


if __name__ == "__main__":
    main()
