"""Local preview for frontend integration; seeded in memory, no writes."""
import json
import os
from pathlib import Path
from fastapi import FastAPI
from .router import build_router

examples = json.loads(Path(__file__).with_name("examples.json").read_text(encoding="utf-8"))
texts = {("demo", f"req-{index}"): case["text"] for index, case in enumerate(examples, 1)}
answers = {case["text"]: case["response"] for case in examples}
live = os.getenv("TESTPILOT_PREVIEW_MODE") == "live"
app = FastAPI(title="Clarify preview: " + ("live model" if live else "fixed examples"))
app.include_router(build_router(lambda project, req: texts.get((project, req)),
                                None if live else answers.__getitem__))
