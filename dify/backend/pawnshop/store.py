"""SQLite is the game source of truth; it is never presented as recalled memory."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS owners(user_id TEXT PRIMARY KEY, scope_id TEXT);
            CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, owner TEXT NOT NULL,
              version INTEGER NOT NULL, status TEXT NOT NULL, card TEXT NOT NULL,
              sequence INTEGER NOT NULL, FOREIGN KEY(owner) REFERENCES owners(user_id));
            CREATE INDEX IF NOT EXISTS items_owner ON items(owner,sequence DESC);
            CREATE TABLE IF NOT EXISTS prepares(turn_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
              conversation TEXT NOT NULL, query TEXT NOT NULL, snapshot TEXT NOT NULL,
              response TEXT, FOREIGN KEY(owner) REFERENCES owners(user_id));
            CREATE TABLE IF NOT EXISTS receipts(turn_id TEXT PRIMARY KEY, proposal TEXT NOT NULL,
              response TEXT NOT NULL, FOREIGN KEY(turn_id) REFERENCES prepares(turn_id));
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, item_id TEXT NOT NULL,
              turn_id TEXT NOT NULL UNIQUE, action TEXT NOT NULL, version INTEGER NOT NULL,
              payload TEXT NOT NULL, FOREIGN KEY(item_id) REFERENCES items(id));
            CREATE TABLE IF NOT EXISTS outbox(event_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
              status TEXT NOT NULL, content TEXT NOT NULL, memory_text TEXT NOT NULL,
              source_receipt TEXT, memory_receipt TEXT, memory_refs TEXT NOT NULL DEFAULT '[]',
              error TEXT, FOREIGN KEY(event_id) REFERENCES events(id));
            """)

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
    return {"id": row["id"], "owner": row["owner"], "version": row["version"], "status": row["status"], "card": json.loads(row["card"])}


def shelf(conn, owner):
    return [item_dict(row) for row in conn.execute("SELECT * FROM items WHERE owner=? ORDER BY sequence DESC", (owner,))]
