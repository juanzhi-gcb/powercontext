"""Ordered, idempotent schema migrations for the game ledger."""
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def has_table(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _v1_base(conn):
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


def _v2_claim_rate_lineage(conn):
    item_columns = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    for name, ddl in (
        ("created_at", "ALTER TABLE items ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"),
        ("lineage", "ALTER TABLE items ADD COLUMN lineage TEXT NOT NULL DEFAULT '[]'"),
        ("note", "ALTER TABLE items ADD COLUMN note TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in item_columns:
            conn.execute(ddl)
    prepare_columns = {row[1] for row in conn.execute("PRAGMA table_info(prepares)")}
    if "created_at" not in prepare_columns:
        conn.execute("ALTER TABLE prepares ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    conn.execute("UPDATE items SET created_at=? WHERE created_at=''", (now(),))
    conn.execute("UPDATE prepares SET created_at=? WHERE created_at=''", (now(),))
    conn.execute("""CREATE TABLE IF NOT EXISTS turn_claims(
        turn_id TEXT PRIMARY KEY, claimed_at REAL NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS rate_limits(
        key TEXT PRIMARY KEY, window_start INTEGER NOT NULL, count INTEGER NOT NULL)""")


def _v3_coins(conn):
    owner_columns = {row[1] for row in conn.execute("PRAGMA table_info(owners)")}
    if "coins" not in owner_columns:
        conn.execute("ALTER TABLE owners ADD COLUMN coins INTEGER NOT NULL DEFAULT 0")
    conn.execute("""CREATE TABLE IF NOT EXISTS coin_events(
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, event_id TEXT NOT NULL,
        action TEXT NOT NULL, amount INTEGER NOT NULL, created_at TEXT NOT NULL)""")


MIGRATIONS = (
    (1, "base", _v1_base),
    (2, "claim-rate-lineage", _v2_claim_rate_lineage),
    (3, "coins", _v3_coins),
)