"""Run as python -m backend.app.modules.agent.demo [--live]."""
import argparse
import json
from pathlib import Path
from .clarify import ModelError, clarify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="call the configured model")
    parser.add_argument('--text', help='analyze custom requirement text in live mode')
    args = parser.parse_args()
    if args.text is not None and not args.live:
        parser.error('--text requires --live')
    print("LIVE MODEL" if args.live else "FIXTURE - recorded example responses for UI integration")
    cases = json.loads(Path(__file__).with_name("examples.json").read_text(encoding="utf-8"))
    if args.text is not None:
        cases = [{'text': args.text}]
    for case in cases:
        try:
            output = clarify(case["text"]) if args.live else clarify(case["text"], lambda _: case["response"])
        except ModelError as exc:
            parser.exit(1, str(exc) + "\n")
        print(json.dumps({"text": case["text"], **output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
