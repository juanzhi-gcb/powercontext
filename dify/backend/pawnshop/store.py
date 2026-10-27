"""SQLite is the game source of truth; it is never presented as recalled memory."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .migrations import MIGRATIONS, has_table, now


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)""")
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            if 1 not in applied and has_table(conn, "items"):
                # Databases created before migrations existed are already at v1.
                conn.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(1,?)", (now(),))
                applied.add(1)
            for version, _name, migrate in MIGRATIONS:
                if version in applied:
                    continue
                migrate(conn)
                conn.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)", (version, now()))

    @contextmanager
    def connect(self, write=False):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def item_dict(row):
    if row is None:
        return None
    return {"id": row["id"], "owner": row["owner"], "version": row["version"], "status": row["status"],
            "card": json.loads(row["card"]), "note": row["note"], "lineage": json.loads(row["lineage"]),
            "created_at": row["created_at"]}


def shelf(conn, owner):
    return [item_dict(row) for row in conn.execute("SELECT * FROM items WHERE owner=? ORDER BY sequence DESC", (owner,))]


def shelf_page(conn, owner, limit, cursor=None):
    if cursor is None:
        rows = conn.execute(
            "SELECT * FROM items WHERE owner=? ORDER BY sequence DESC LIMIT ?",
            (owner, limit + 1),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM items WHERE owner=? AND sequence<? ORDER BY sequence DESC LIMIT ?",
            (owner, int(cursor), limit + 1),
        ).fetchall()
    items = [item_dict(row) for row in rows[:limit]]
    # The cursor is the sequence of the last returned item, so the next page
    # continues strictly below it instead of skipping it.
    next_cursor = str(rows[limit - 1]["sequence"]) if len(rows) > limit else None
    return items, next_cursor