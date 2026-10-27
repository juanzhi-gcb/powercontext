# 烦恼典当行 第二阶段·后端地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把首版后端从“单机演示级”补到“多进程可扩展、可运维、记忆不受 2000 字节截断影响”的状态，为后续记忆治理玩法和自定义前端提供稳定接口。

**Architecture:** 保留 FastAPI + SQLite 单库。新增版本化迁移、数据库级 turn 认领（跨进程幂等）、按玩家的速率限制、货架分页与导出、记忆文本压缩到单条上限以内、prepare 返回本次召回的记忆引用白名单。模型仍只在 Dify 中调用。

**Tech Stack:** Python 3.12、FastAPI、pydantic v2、httpx、SQLite（WAL）、pytest、Docker Compose。

**范围说明：** 本计划只做地基。后续两份独立计划分别是「记忆治理与玩法创新」（退票/修订、合成、玩家铭文、时间灰尘、溯源）和「自定义前端 + 当票号身份」。每份计划都能单独交付并验证。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/pawnshop/store.py` | 连接、迁移、表结构、分页查询 |
| `backend/pawnshop/migrations.py`（新建） | 版本化迁移步骤，纯函数 |
| `backend/pawnshop/ratelimit.py`（新建） | 基于 SQLite 的滑动窗口限流 |
| `backend/pawnshop/service.py` | 游戏状态机、turn 认领、记忆文本、导出 |
| `backend/pawnshop/powercontext.py` | 解析 prepare 返回的记忆引用 |
| `backend/pawnshop/app.py` | 路由、限流、分页参数 |
| `backend/pawnshop/models.py` | 请求模型（本阶段只加限流无关字段，无破坏性改动） |
| `tests/backend/test_store.py`（新建） | 迁移测试 |
| `tests/backend/test_limits.py`（新建） | 认领、限流、分页、导出 |
| `tests/backend/test_game.py` | 记忆压缩与 prepare 引用的回归测试 |

---

### Task 1: 版本化数据库迁移

**Files:**
- Create: `backend/pawnshop/migrations.py`
- Modify: `backend/pawnshop/store.py`
- Test: `tests/backend/test_store.py`

- [ ] **Step 1: 写失败测试**

```python
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
        conn.execute("INSERT INTO items(id,owner,version,status,card,sequence) VALUES('i1','alice',1,'draft','{\"name\":\"月亮\"}',1)")
    Store(str(path))
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT card FROM items WHERE id='i1'").fetchone()[0] == '{"name":"月亮"}'
        assert conn.execute("SELECT created_at FROM items WHERE id='i1'").fetchone()[0] != ""
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
```

- [ ] **Step 2: 运行并确认失败**

Run: `uv run --project backend --group dev pytest tests/backend/test_store.py -q`
Expected: FAIL，`sqlite3.OperationalError: no such table: schema_migrations`

- [ ] **Step 3: 新建迁移模块**

`backend/pawnshop/migrations.py`：

```python
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


MIGRATIONS = (
    (1, "base", _v1_base),
    (2, "claim-rate-lineage", _v2_claim_rate_lineage),
)
```

- [ ] **Step 4: 改 `store.py` 使用迁移**

把 `Store.__init__` 中现有的 `executescript` 整段替换为：

```python
from .migrations import MIGRATIONS, has_table, now


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
```

`store.py` 顶部的 `json/sqlite3/contextmanager/Path` 导入保持不变。

- [ ] **Step 5: 运行测试**

Run: `uv run --project backend --group dev pytest tests/backend/test_store.py tests/backend/test_game.py -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add dify/backend/pawnshop/migrations.py dify/backend/pawnshop/store.py dify/tests/backend/test_store.py
git commit -m "refactor(backend): versioned SQLite migrations"
```

---

### Task 2: 跨进程 turn 认领

**Files:**
- Modify: `backend/pawnshop/service.py`
- Test: `tests/backend/test_limits.py`

- [ ] **Step 1: 写失败测试**

```python
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi.testclient import TestClient

from test_game import CARD, PowerContextHTTP, act, draft, prepare


def test_two_app_instances_share_one_durable_turn_claim(game):
    client, wire, db = game
    draft(client)
    prepare(client, "shared-turn", "确认典当")
    wire.write_entered, wire.write_release = threading.Event(), threading.Event()

    from pawnshop.app import create_app
    second_app = create_app(db_path=str(db), api_key="test-secret", powercontext_url="http://pc",
                            powercontext_token="pc-test", transport=httpx.MockTransport(wire))
    with TestClient(second_app, headers={"X-Pawnshop-Key": "test-secret"}) as second_client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(act, client, "shared-turn", "pawn")
            assert wire.write_entered.wait(5)
            second = executor.submit(act, second_client, "shared-turn", "pawn")
            started = threading.Event()
            second.add_done_callback(lambda _: started.set())
            started.wait(0.1)
            wire.write_release.set()
            original, replay = first.result().json(), second.result().json()

    assert original["memory_status"] == "synced"
    assert replay == dict(original, replayed=True)
    assert len(wire.memories[next(iter(wire.memories))]) == 1
```

- [ ] **Step 2: 运行并确认失败**

Run: `uv run --project backend --group dev pytest tests/backend/test_limits.py::test_two_app_instances_share_one_durable_turn_claim -q`
Expected: FAIL，两个实例各自执行一次，`wire.memories` 出现 2 条或第二个请求返回 409

- [ ] **Step 3: 实现认领与等待**

在 `service.py` 顶部加：

```python
import time
```

在 `Game` 中加：

```python
CLAIM_LEASE_SECONDS = 120

def _claim_turn(self, turn_id):
    """Claim an act before touching external memory. A fresh claim means another
    worker owns this turn; an expired claim is a crashed attempt and may be taken over."""
    with self.store.connect(write=True) as conn:
        row = conn.execute("SELECT claimed_at FROM turn_claims WHERE turn_id=?", (turn_id,)).fetchone()
        current = time.time()
        if row is None:
            conn.execute("INSERT INTO turn_claims(turn_id,claimed_at) VALUES(?,?)", (turn_id, current))
            return True
        if current - row["claimed_at"] > self.CLAIM_LEASE_SECONDS:
            conn.execute("UPDATE turn_claims SET claimed_at=? WHERE turn_id=?", (current, turn_id))
            return True
        return False

def _wait_for_receipt(self, turn_id, canonical, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with self.store.connect() as conn:
            row = conn.execute("SELECT proposal,response FROM receipts WHERE turn_id=?", (turn_id,)).fetchone()
            if row:
                if row["proposal"] != canonical:
                    raise HTTPException(409, "同一 turn 已提交不同提案")
                return dict(json.loads(row["response"]), replayed=True)
        time.sleep(0.1)
    return None
```

把 `act` 改为：

```python
def act(self, request):
    canonical = dump(request.proposal.model_dump())
    with self._locks_guard:
        turn_lock = self._turn_locks.get(request.turn_id)
        if turn_lock is None:
            turn_lock = Lock()
            self._turn_locks[request.turn_id] = turn_lock
    with turn_lock:
        if not self._claim_turn(request.turn_id):
            replayed = self._wait_for_receipt(request.turn_id, canonical)
            if replayed is not None:
                return replayed
            raise HTTPException(409, "同一 turn 正在处理中，请稍后重试")
        return self._act(request)
```

- [ ] **Step 4: 运行测试**

Run: `uv run --project backend --group dev pytest tests/backend/test_limits.py tests/backend/test_game.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add dify/backend/pawnshop/service.py dify/tests/backend/test_limits.py
git commit -m "fix(backend): durable cross-process act claim"
```

---

### Task 3: 按玩家限流

**Files:**
- Create: `backend/pawnshop/ratelimit.py`
- Modify: `backend/pawnshop/app.py`
- Test: `tests/backend/test_limits.py`

- [ ] **Step 1: 写失败测试**

在 `tests/backend/test_limits.py` 追加：

```python
def test_rate_limit_returns_429_after_budget(tmp_path):
    from pawnshop.app import create_app
    wire = PowerContextHTTP()
    app = create_app(db_path=str(tmp_path / "rate.sqlite3"), api_key="test-secret",
                     powercontext_url="http://pc", powercontext_token="pc-test",
                     transport=httpx.MockTransport(wire), rate_limit=2)
    with TestClient(app, headers={"X-Pawnshop-Key": "test-secret"}) as client:
        accepted = [prepare(client, f"t{i}").status_code for i in range(2)]
        blocked = prepare(client, "t9")
    assert accepted == [200, 200]
    assert blocked.status_code == 429
```

- [ ] **Step 2: 运行并确认失败**

Run: `uv run --project backend --group dev pytest tests/backend/test_limits.py::test_rate_limit_returns_429_after_budget -q`
Expected: FAIL，`create_app()` 不接受 `rate_limit`

- [ ] **Step 3: 新建限流器**

`backend/pawnshop/ratelimit.py`：

```python
"""Per-player fixed-window limiter stored in SQLite so every worker agrees."""
import time

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, store, limit, window_seconds=60):
        self.store, self.limit, self.window_seconds = store, limit, window_seconds

    def check(self, key):
        if self.limit <= 0:
            return
        window = int(time.time()) // self.window_seconds
        with self.store.connect(write=True) as conn:
            row = conn.execute("SELECT window_start,count FROM rate_limits WHERE key=?", (key,)).fetchone()
            if row is None or row["window_start"] != window:
                conn.execute("INSERT INTO rate_limits(key,window_start,count) VALUES(?,?,1) "
                             "ON CONFLICT(key) DO UPDATE SET window_start=excluded.window_start,count=1",
                             (key, window))
                count = 1
            else:
                count = row["count"] + 1
                conn.execute("UPDATE rate_limits SET count=? WHERE key=?", (count, key))
        if count > self.limit:
            raise HTTPException(429, "请求过于频繁，请稍后再试")
```

- [ ] **Step 4: 接入 `app.py`**

`create_app` 增加参数 `rate_limit=None`，并在 `game = Game(store, pc)` 后加：

```python
from .ratelimit import RateLimiter
limiter = RateLimiter(store, limit=int(rate_limit if rate_limit is not None
                                       else os.environ.get("PAWNSHOP_RATE_LIMIT", "120")))
```

`prepare` 与 `act` 路由改为：

```python
@app.post("/v1/prepare", dependencies=authenticated)
def prepare(request: PrepareRequest):
    limiter.check(f"prepare:{request.user_id}")
    return game.prepare(request)


@app.post("/v1/act", dependencies=authenticated)
def act(request: ActRequest):
    limiter.check(f"act:{request.user_id}")
    return game.act(request)
```

- [ ] **Step 5: 运行测试**

Run: `uv run --project backend --group dev pytest tests/backend -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add dify/backend/pawnshop/ratelimit.py dify/backend/pawnshop/app.py dify/tests/backend/test_limits.py
git commit -m "feat(backend): per-player request limiting"
```

---

### Task 4: 货架分页与导出

**Files:**
- Modify: `backend/pawnshop/store.py`
- Modify: `backend/pawnshop/service.py`
- Modify: `backend/pawnshop/app.py`
- Test: `tests/backend/test_limits.py`

- [ ] **Step 1: 写失败测试**

在 `tests/backend/test_limits.py` 追加：

```python
def test_shelf_pagination_and_export(game):
    client, _, _ = game
    for index in range(3):
        draft(client, f"draft-{index}")
    first = client.get("/v1/items?user_id=alice&limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    rest = client.get(f"/v1/items?user_id=alice&limit=2&cursor={first['next_cursor']}").json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    export = client.get("/v1/export?user_id=alice").json()
    assert export["user_id"] == "alice"
    assert len(export["items"]) == 3
    assert export["items"][0]["events"][0]["action"] == "appraise"
```

- [ ] **Step 2: 运行并确认失败**

Run: `uv run --project backend --group dev pytest tests/backend/test_limits.py::test_shelf_pagination_and_export -q`
Expected: FAIL，`next_cursor` 为 None 或 `/v1/export` 返回 404

- [ ] **Step 3: 加分页查询**

在 `store.py` 追加：

```python
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
    next_cursor = str(rows[limit]["sequence"]) if len(rows) > limit else None
    return items, next_cursor
```

- [ ] **Step 4: 服务与路由**

`Game.items` 改为：

```python
def items(self, owner, limit=50, cursor=None):
    limit = max(1, min(int(limit), 100))
    if cursor is not None:
        try:
            cursor = int(cursor)
        except ValueError:
            raise HTTPException(422, "cursor 无效")
        if cursor < 1:
            raise HTTPException(422, "cursor 无效")
    with self.store.connect() as conn:
        items, next_cursor = shelf_page(conn, owner, limit, cursor)
    return {"items": items, "next_cursor": next_cursor}
```

新增 `Game.export`：

```python
def export(self, owner):
    with self.store.connect() as conn:
        items = shelf(conn, owner)
    exported = [self.detail(owner, item["id"]) for item in items]
    return {"user_id": owner, "exported_at": datetime.now(timezone.utc).isoformat(),
            "items": exported}
```

`service.py` 顶部补 `from datetime import datetime, timezone` 和 `from .store import shelf_page`。

`app.py` 路由：

```python
@app.get("/v1/items", dependencies=authenticated)
def items(user_id: Annotated[Identity, Query()],
          limit: Annotated[int, Query(ge=1, le=100)] = 50,
          cursor: Annotated[str | None, Query()] = None):
    return game.items(user_id, limit, cursor)


@app.get("/v1/export", dependencies=authenticated)
def export(user_id: Annotated[Identity, Query()]):
    return game.export(user_id)
```

- [ ] **Step 5: 运行测试**

Run: `uv run --project backend --group dev pytest tests/backend -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add dify/backend/pawnshop/store.py dify/backend/pawnshop/service.py dify/backend/pawnshop/app.py dify/tests/backend/test_limits.py
git commit -m "feat(backend): shelf pagination and player export"
```

---

### Task 5: 记忆文本压缩，消除 2000 字节截断

**Files:**
- Modify: `backend/pawnshop/service.py`
- Test: `tests/backend/test_game.py`

- [ ] **Step 1: 写失败测试**

在 `test_game.py` 追加：

```python
def test_memory_entry_is_compacted_instead_of_truncated(game):
    client, wire, _ = game
    draft(client)
    card = {name: "银" * 250 for name in CARD}
    prepare(client, "compact-correction", "我不是嫉妒，我是觉得努力没有被看见。")
    assert act(client, "compact-correction", "correct", card=card).status_code == 200
    prepare(client, "compact-pawn", "确认典当")
    assert act(client, "compact-pawn", "pawn").status_code == 200
    text = [body["text"] for path, body in wire.requests if path == "/v1/memory/remember"][-1]
    assert len(text.encode("utf-8")) <= 2000
    document = json.loads(text.removeprefix("pawnshop ").split("\nSource audit citation:")[0])
    assert document["user_correction"]["text"] == "我不是嫉妒，我是觉得努力没有被看见。"
    assert document["fictional_item_card_compacted"] is True
    assert document["fictional_item_card"]["name"].startswith("银")
```

- [ ] **Step 2: 运行并确认失败**

Run: `uv run --project backend --group dev pytest tests/backend/test_game.py::test_memory_entry_is_compacted_instead_of_truncated -q`
Expected: FAIL，`len(text)` 大于 2000 或缺少 `fictional_item_card_compacted`

- [ ] **Step 3: 实现压缩**

在 `service.py` 的 `memory_text` 中，把最后一行 `return "pawnshop " + json.dumps(...)` 替换为下面这段（保持 4 空格缩进，直接位于 `memory_text` 内）：

```python
    text = _render_memory(document)
    if len(text.encode("utf-8")) <= 1900:
        return text
    # PowerContext truncates one Memory text at 2000 UTF-8 bytes. Keep the
    # player's verbatim facts and replace the six-field card with a digest that
    # fits, so recall never silently loses corrections or reported events.
    fixed = _render_memory({**document, "fictional_item_card": {}})
    budget = max(64, 1900 - len(fixed.encode("utf-8")))
    document["fictional_item_card"] = compact_card(item["card"], budget)
    document["fictional_item_card_compacted"] = True
    text = _render_memory(document)
    while len(text.encode("utf-8")) > 2000 and document["fictional_item_card"]:
        document["fictional_item_card"].popitem()
        text = _render_memory(document)
    return text
```

在 `memory_text` 之前加：

```python
def _render_memory(document):
    return "pawnshop " + json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def compact_card(card, budget):
    """Keep whole fields in priority order; shorten the last one to fit the budget."""
    ordered = ["name", "meaning", "inscription", "trait", "appearance", "quest"]
    kept = {}
    used = 2  # braces
    for field in ordered:
        value = card[field]
        size = len(json.dumps(field, ensure_ascii=False).encode()) + len(json.dumps(value, ensure_ascii=False).encode()) + 2
        if used + size <= budget:
            kept[field] = value
            used += size
            continue
        remaining = budget - used
        if remaining > 80:
            encoded = value.encode("utf-8")[: remaining - 64].decode("utf-8", errors="ignore")
            kept[field] = encoded + "…"
        break
    return kept
```

- [ ] **Step 4: 更新既有断言的语义**

`test_powercontext_2000_byte_entry_prefix_retains_correction_and_event` 仍应保留；若它断言整卡字段完整，改为：

```python
    assert "我不是嫉妒，我是觉得努力没有被看见。" in actual_prefix
    assert "今天我把拖着的作品交出去了。" in actual_prefix
    assert document["fictional_item_card_compacted"] is True
```

- [ ] **Step 5: 运行测试**

Run: `uv run --project backend --group dev pytest tests/backend/test_game.py -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add dify/backend/pawnshop/service.py dify/tests/backend/test_game.py
git commit -m "fix(backend): compact memory text instead of losing facts to truncation"
```

---

### Task 6: prepare 返回记忆引用白名单

**Files:**
- Modify: `backend/pawnshop/powercontext.py`
- Modify: `backend/pawnshop/service.py`
- Modify: `tests/backend/test_game.py`

- [ ] **Step 1: 写失败测试**

在 `test_game.py` 追加：

```python
def test_prepare_returns_recalled_memory_refs(game):
    client, _, _ = game
    pawn(client)
    recalled = prepare(client, "refs-session", conversation="c2").json()
    assert recalled["memory_status"] == "ready"
    assert recalled["memory_refs"]
    assert recalled["memory_refs"][0]["family"] == "atomic-memory"
    assert isinstance(recalled["memory_refs"][0]["revision"], int)
```

- [ ] **Step 2: 运行并确认失败**

Run: `uv run --project backend --group dev pytest tests/backend/test_game.py::test_prepare_returns_recalled_memory_refs -q`
Expected: FAIL，`KeyError: 'memory_refs'`

- [ ] **Step 3: 解析引用**

在 `powercontext.py` 加：

```python
def prepared_refs(content):
    """Exact Atomic Memory refs the pinned builder returned in this context."""
    if not content:
        return []
    begin = content.find("BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n")
    end = content.find("\nEND_POWERCONTEXT_PREPARED_CONTEXT_V1")
    if begin < 0 or end < 0:
        return []
    try:
        envelope = json.loads(content[begin + len("BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n") : end])
    except ValueError:
        return []
    refs = []
    for entry in envelope.get("items", []):
        citation = entry.get("citation") or {}
        ref = citation.get("artifact_ref")
        if not isinstance(ref, dict):
            artifact = citation.get("artifact") or {}
            ref = artifact.get("artifact")
        if isinstance(ref, dict) and ref.get("family") == "atomic-memory":
            refs.append({"family": "atomic-memory", "artifact_id": ref.get("artifact_id"),
                         "revision": ref.get("revision")})
    return refs
```

把 `PowerContext.prepare` 的返回改为 `(status, content or "", prepared_refs(content or ""))`。

- [ ] **Step 4: 服务返回引用**

`Game.prepare` 中：

```python
status, content, refs = "unavailable", "", []
try:
    ...
    status, content, refs = self.pc.prepare(scope, recall_query(snapshot, request.query))
except EXTERNAL_ERRORS:
    pass
...
response = {"turn_id": request.turn_id, "state_json": dump(snapshot),
            "memory_context": content, "memory_status": status,
            "memory_refs": refs,
            "active_item_id": current["id"] if current else "",
            "active_version": current["version"] if current else 0}
```

并把测试桩的 prepare 分支改为返回真实信封：

```python
        if request.url.path == "/v1/context/prepare":
            tokens = [token for token in body["query"].split() if token != "pawnshop"]
            admitted = [text for text in self.memories.get(body["scope_id"], [])
                        if any(len(token) >= 5 and token in text for token in tokens)]
            entries = [{"citation": {"artifact_ref": {"family": "atomic-memory",
                        "artifact_id": f"m{index + 1}", "revision": 1}}, "content": text}
                       for index, text in enumerate(admitted)]
            content = ("untrusted history\n\nBEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n"
                       + json.dumps({"trust": "untrusted_history", "items": entries}, ensure_ascii=False)
                       + "\nEND_POWERCONTEXT_PREPARED_CONTEXT_V1") if entries else ""
            assert body["query"].startswith("pawnshop ")
            return httpx.Response(200, json={"schema": "powercontext.prepared-context.v1",
                "status": "ready" if content else "empty", "content": content or None,
                "content_bytes": len(content.encode())})
```

- [ ] **Step 5: 运行全部后端测试**

Run: `uv run --project backend --group dev pytest tests/backend -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add dify/backend/pawnshop/powercontext.py dify/backend/pawnshop/service.py dify/tests/backend/test_game.py
git commit -m "feat(backend): return recalled memory refs with prepare"
```

---

## 验证清单

```powershell
cd D:/DifyPawnshop/submission/dify
uv run --project backend --group dev pytest tests/backend -q
uv run --project backend python scripts/verify_services.py
docker compose -p pawnshop-game --env-file deploy/.env -f deploy/compose.yaml config --quiet
```

期望：后端测试全部通过；`verify_services.py` 输出 `result: passed`；compose 校验无输出。

## 执行记录（2026-10-27）

Task 1–6 已实现并通过测试：版本化迁移、跨进程 turn 认领（认领释放后才算最终回执）、SQLite 限流、货架分页与玩家导出、记忆正文压缩到 1850 字节以内、prepare 返回召回记忆引用白名单。同一次改动还落地了浏览器 BFF（签名当票、Dify 代理、只读货架与来历）和自定义前端；后续又补了勇气币（后端发放、持久余额、重放不重复）和四套表情/盖章动作。`pytest tests` 共 97 项通过，真实 `verify_services.py`、`verify_e2e.py` 与 `npm run verify:ui` 均通过。

尚未实现、转交下一份计划：退票（Atomic lifecycle forgotten + 条件替换）、物品遗忘、两件藏品合成、玩家铭文、时间灰尘、`docs/powercontext-integration.md`、语义召回评估。

## 后续计划（不在本文件内）

1. `docs/plans/2026-10-27-phase2-memory-gameplay.md`：退票（Atomic lifecycle `forgotten` + 条件替换）、物品遗忘删除（软删除并同步退休记忆）、两件藏品合成、玩家铭文、时间灰尘、记忆溯源接口与 Dify 分支。退票需要本计划 Task 6 的 `memory_refs` 白名单，所以必须排在其后。
2. `docs/plans/2026-10-27-phase2-frontend.md`：等待用户提供视觉风格后，制作完整人物交互前端、当票号身份（跨浏览器/设备）与 BFF（浏览器 → 后端 → Dify，保持 Dify 编排地位）。
3. `docs/powercontext-integration.md`：单独讲清楚本项目如何使用 PowerContext 的四个层次——Source 审计、Atomic Memory、PreparedContext、生命周期治理，以及为什么检索用账本锚点、中断时如何如实降级。这份文档在 Plan 2 落地后写，因为届时的说法才能覆盖 revise/forget。
4. 语义召回评估（Plan 2 之后）：PowerContext 支持配置 embedding 模型；若用户的百炼账号提供 embedding 接口，可在独立计划里启用 hybrid 检索并用同一套 e2e 复测。没有 embedding 时维持锚点词法召回，并在文档中写明边界。