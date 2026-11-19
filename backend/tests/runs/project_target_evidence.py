"""Generate redacted evidence for project-scoped loopback HTTP execution."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.tests.runs.test_project_targets import verify_project_targets  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/project-target-run-outcomes")
    )
    args = parser.parse_args()
    result = verify_project_targets(args.output_dir)
    print(
        json.dumps(
            {"summary": result["summary"], "output_dir": str(args.output_dir.resolve())},
            ensure_ascii=False,
        )
    )
