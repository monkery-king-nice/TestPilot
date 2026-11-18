"""Server configuration; never accept target URLs from the public API."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    database_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("TESTPILOT_DATABASE", "backend/data/testpilot.sqlite3")
        )
    )
    demo_base_url: str = field(
        default_factory=lambda: os.getenv("DEMO_BASE_URL", "http://127.0.0.1:8010")
    )

    def __post_init__(self):
        database = Path(self.database_path)
        if str(database) == ":memory:":
            raise ValueError("请使用 SQLite 文件路径，以便重启后保留数据")
        if not database.is_absolute():
            database = REPOSITORY_ROOT / database
        object.__setattr__(self, "database_path", database.resolve())
        target = urlsplit(self.demo_base_url)
        if (
            target.scheme not in {"http", "https"}
            or not target.hostname
            or target.username is not None
            or target.password is not None
            or target.query
            or target.fragment
            or target.path not in {"", "/"}
        ):
            raise ValueError("DEMO_BASE_URL 必须是无凭证、路径或查询参数的 HTTP(S) 服务地址")
        object.__setattr__(self, "demo_base_url", self.demo_base_url.rstrip("/"))
