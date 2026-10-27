import sqlite3

from pawnshop.store import Store

LEGACY_V1_SQL = """
CREATE TABLE owners(user_id TEXT PRIMARY KEY, scope_id TEXT);
CREATE TABLE items(id TEXT PRIMARY KEY, owner TEXT NOT NULL,
  version INTEGER NOT NULL, status TEXT NOT NULL, card TEXT NOT NULL,
  sequence INTEGER NOT NULL, FOREIGN KEY(owner) REFERENCES owners(user_id));
CREATE TABLE prepares(turn_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
  conversation TEXT NOT NULL, query TEXT NOT NULL, snapshot TEXT NOT NULL,
  response TEXT, FOREIGN KEY(owner) REFERENCES owners(user_id));
CREATE TABLE receipts(turn_id TEXT PRIMARY KEY, proposal TEXT NOT NULL,
  response TEXT NOT NULL, FOREIGN KEY(turn_id) REFERENCES prepares(turn_id));
CREATE TABLE events(id TEXT PRIMARY KEY, item_id TEXT NOT NULL,
  turn_id TEXT NOT NULL UNIQUE, action TEXT NOT NULL, version INTEGER NOT NULL,
  payload TEXT NOT NULL, FOREIGN KEY(item_id) REFERENCES items(id));
CREATE TABLE outbox(event_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
  status TEXT NOT NULL, content TEXT NOT NULL, memory_text TEXT NOT NULL,
  source_receipt TEXT, memory_receipt TEXT, memory_refs TEXT NOT NULL DEFAULT '[]',
  error TEXT, FOREIGN KEY(event_id) REFERENCES events(id));
"""


def test_fresh_database_gets_all_migrations_once(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    Store(str(path))
    with sqlite3.connect(path) as conn:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        assert versions == [1, 2]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
        assert {"created_at", "lineage", "note"} <= columns
    Store(str(path))
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2


def test_existing_version_one_database_is_upgraded_without_data_loss(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(LEGACY_V1_SQL)
        conn.execute("INSERT INTO owners(user_id) VALUES('alice')")
        conn.execute("INSERT INTO items(id,owner,version,status,card,sequence) "
                     "VALUES('i1','alice',1,'draft','{\"name\":\"月亮\"}',1)")
    Store(str(path))
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT card FROM items WHERE id='i1'").fetchone()[0] == '{"name":"月亮"}'
        assert conn.execute("SELECT created_at FROM items WHERE id='i1'").fetchone()[0] != ""
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2