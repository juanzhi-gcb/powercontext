"""Configuration for the SDD context module."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    """All paths and endpoints resolved from the environment.

    ``workspace`` is the ``minimax/`` directory of the submission; everything the
    module reads or writes lives below it unless a DSN points at a server.
    """

    workspace: Path
    project_id: str = "ordermesh"
    db_mode: str = "embedded"          # embedded | server
    db_dir: Path = field(default_factory=Path)
    db_dsn: str | None = None
    powercontext_url: str = "http://127.0.0.1:8000"
    powercontext_token: str | None = None
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_api_key: str | None = None
    minimax_model: str = "MiniMax-M3.1-Flash"
    minimax_timeout: float = 180.0

    @property
    def specs_dir(self) -> Path:
        return self.workspace / "specs"

    @property
    def demo_project(self) -> Path:
        return self.workspace / "demo_project"

    @property
    def evidence_dir(self) -> Path:
        return self.workspace / "evidence"

    @property
    def state_dir(self) -> Path:
        return self.workspace / ".sdd_state"

    @classmethod
    def load(cls, workspace: str | os.PathLike[str] | None = None) -> Settings:
        root = Path(workspace) if workspace else Path(__file__).resolve().parent.parent
        root = root.resolve()
        db_dir = Path(_env("SDDCTX_DB_DIR") or (root / ".seekdb"))
        return cls(
            workspace=root,
            project_id=_env("SDDCTX_PROJECT_ID", "ordermesh") or "ordermesh",
            db_mode=(_env("SDDCTX_DB_MODE", "embedded") or "embedded").lower(),
            db_dir=db_dir,
            db_dsn=_env("SDDCTX_DSN"),
            powercontext_url=_env("POWERCONTEXT_URL", "http://127.0.0.1:8000") or "http://127.0.0.1:8000",
            powercontext_token=_env("POWERCONTEXT_CLIENT_API_TOKEN"),
            minimax_base_url=(_env("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1") or "").rstrip("/"),
            minimax_api_key=_env("MINIMAX_API_KEY"),
            minimax_model=_env("MINIMAX_MODEL", "MiniMax-M3.1-Flash") or "MiniMax-M3.1-Flash",
            minimax_timeout=float(_env("MINIMAX_TIMEOUT", "180") or "180"),
        )

    def as_public_dict(self) -> dict[str, str]:
        """Configuration safe to print or log (no credentials)."""

        return {
            "workspace": str(self.workspace),
            "project_id": self.project_id,
            "db_mode": self.db_mode,
            "db_dir": str(self.db_dir),
            "db_dsn": _redact_dsn(self.db_dsn),
            "powercontext_url": self.powercontext_url,
            "minimax_base_url": self.minimax_base_url,
            "minimax_model": self.minimax_model,
            "minimax_api_key": "***" if self.minimax_api_key else "",
        }


def _redact_dsn(dsn: str | None) -> str:
    if not dsn:
        return ""
    if "@" in dsn and "://" in dsn:
        scheme, rest = dsn.split("://", 1)
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"
    return dsn
