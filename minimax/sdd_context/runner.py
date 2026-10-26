"""Run the target and regression suites and record the results."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings

_COUNT = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped)")


@dataclass
class TestRun:
    scope: str
    command: list[str]
    exit_code: int
    passed: int
    failed: int
    errors: int
    duration_s: float
    output: str
    log_path: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.failed == 0 and self.errors == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "command": self.command,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "duration_s": round(self.duration_s, 2),
            "log_path": self.log_path,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def summary(self) -> str:
        return f"{self.scope}: exit={self.exit_code} passed={self.passed} failed={self.failed} errors={self.errors}"


def run_pytest(settings: Settings, scope: str, node_ids: list[str], *, timeout: float = 300.0) -> TestRun:
    if not node_ids:
        raise ValueError(f"no {scope} tests selected")

    logs = settings.evidence_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = logs / f"{stamp}-{scope}.log"

    command = [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *node_ids]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(settings.demo_project) + os.pathsep + environment.get("PYTHONPATH", "")
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=settings.demo_project,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    duration = time.perf_counter() - started
    output = (completed.stdout or "") + (completed.stderr or "")

    passed = failed = errors = 0
    for count, word in _COUNT.findall(output):
        if word == "passed":
            passed = int(count)
        elif word == "failed":
            failed = int(count)
        elif word in ("error", "errors"):
            errors = int(count)

    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        handle.write(f"# cwd: {settings.demo_project}\n")
        handle.write(f"# exit: {completed.returncode}\n\n")
        handle.write(output)

    return TestRun(
        scope=scope,
        command=command,
        exit_code=completed.returncode,
        passed=passed,
        failed=failed,
        errors=errors,
        duration_s=duration,
        output=output,
        log_path=str(log_path.relative_to(settings.workspace)),
    )


def node_ids_from_context(context: dict[str, Any], scope: str) -> list[str]:
    return [item["node_id"] for item in context["tests"][scope]]
