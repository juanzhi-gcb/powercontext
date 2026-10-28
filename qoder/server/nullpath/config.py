from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    seekdb_host: str = "127.0.0.1"
    seekdb_port: int = 2881
    seekdb_user: str = "root"
    seekdb_password: str = ""
    seekdb_database: str = "nullpath"
    powercontext_url: str = "http://127.0.0.1:8000"
    powercontext_scope_id: str = ""
    powercontext_token: str = ""
    embedding_dimensions: int = 64
    request_timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_]+", self.seekdb_database):
            raise ValueError("SEEKDB_DATABASE may contain only letters, numbers, and underscores")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            seekdb_host=os.getenv("SEEKDB_HOST", "127.0.0.1"),
            seekdb_port=int(os.getenv("SEEKDB_PORT", "2881")),
            seekdb_user=os.getenv("SEEKDB_USER", "root"),
            seekdb_password=os.getenv("SEEKDB_PASSWORD", ""),
            seekdb_database=os.getenv("SEEKDB_DATABASE", "nullpath"),
            powercontext_url=os.getenv("POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/"),
            powercontext_scope_id=os.getenv("POWERCONTEXT_SCOPE_ID", ""),
            powercontext_token=os.getenv("POWERCONTEXT_TOKEN", ""),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "64")),
            request_timeout_seconds=float(os.getenv("POWERCONTEXT_TIMEOUT_SECONDS", "3")),
        )
