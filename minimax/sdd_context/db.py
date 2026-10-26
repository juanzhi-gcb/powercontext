"""Database access for the SDD context module.

Two deployment shapes are supported:

``embedded``
    ``pylibseekdb`` opens a local seekdb runtime (an OceanBase-derived engine)
    inside the process and exposes a MySQL-protocol endpoint over a Unix socket.

``server``
    A plain MySQL/OceanBase DSN, for example
    ``mysql://root:@127.0.0.1:2881/sdd_context``.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from .config import Settings
from .schema import DROP_ORDER, STATEMENTS


class DatabaseError(RuntimeError):
    """Raised when the database cannot be opened or queried."""


@dataclass
class QueryLog:
    """One captured SQL statement, kept for the evidence log."""

    statement: str
    params: tuple[Any, ...] | None
    rows: int
    elapsed_ms: float


class Database:
    """Thin synchronous wrapper around a DB-API connection."""

    def __init__(self, connection: Any, *, log_sink: list[QueryLog] | None = None) -> None:
        self._connection = connection
        self.log_sink = log_sink

    # -- query helpers -------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        started = time.perf_counter()
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params) if params else None)
            affected = cursor.rowcount
        self._log(sql, params, affected, started)
        return affected

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> int:
        if not rows:
            return 0
        started = time.perf_counter()
        with self._connection.cursor() as cursor:
            cursor.executemany(sql, [tuple(row) for row in rows])
            affected = cursor.rowcount
        self._log(sql, ("<many>",), affected, started)
        return affected

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        started = time.perf_counter()
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params) if params else None)
            rows = list(cursor.fetchall())
        self._log(sql, params, len(rows), started)
        return rows

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        rows = self.query(sql, params)
        if not rows:
            return None
        return next(iter(rows[0].values()))

    def script(self, statements: Sequence[str]) -> None:
        with self._connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    @property
    def raw(self) -> Any:
        return self._connection

    def _log(self, sql: str, params: Sequence[Any] | None, rows: int, started: float) -> None:
        if self.log_sink is None:
            return
        self.log_sink.append(
            QueryLog(
                statement=" ".join(sql.split()),
                params=tuple(params) if params else None,
                rows=rows,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        )


@contextlib.contextmanager
def open_database(settings: Settings, *, log_sink: list[QueryLog] | None = None) -> Iterator[Database]:
    """Open the configured database for the duration of a command."""

    try:
        import pymysql
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise DatabaseError("PyMySQL is required: pip install pymysql") from exc

    if settings.db_mode == "embedded":
        try:
            import pylibseekdb
        except ModuleNotFoundError as exc:
            raise DatabaseError(
                "SDDCTX_DB_MODE=embedded needs pylibseekdb (pip install pylibseekdb), "
                "or set SDDCTX_DSN to an OceanBase/MySQL server"
            ) from exc

        settings.db_dir.mkdir(parents=True, exist_ok=True)
        instance = pylibseekdb.open(str(settings.db_dir))
        options = dict(instance.connection_options())
        connection = pymysql.connect(
            database="test",
            autocommit=True,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            **options,
        )
        try:
            yield Database(connection, log_sink=log_sink)
        finally:
            connection.close()
            instance.close()
        return

    if not settings.db_dsn:
        raise DatabaseError("SDDCTX_DB_MODE=server requires SDDCTX_DSN")

    parsed = urlparse(settings.db_dsn)
    if parsed.scheme not in ("mysql", "oceanbase"):
        raise DatabaseError(f"unsupported DSN scheme: {parsed.scheme}")
    connection = pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 2881,
        user=unquote(parsed.username or "root"),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/sdd_context").lstrip("/"),
        autocommit=True,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        yield Database(connection, log_sink=log_sink)
    finally:
        connection.close()


def init_schema(database: Database, *, drop: bool = False) -> None:
    if drop:
        database.script(DROP_ORDER)
    database.script(STATEMENTS)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))