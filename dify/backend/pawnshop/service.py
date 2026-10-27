import html
import json
import re
import time
import uuid
from datetime import datetime, timezone
from threading import Lock
from weakref import WeakValueDictionary

import httpx
from fastapi import HTTPException

from .powercontext import ProtocolError
from .store import dump, item_dict, shelf, shelf_page


EXTERNAL_ERRORS = (httpx.HTTPError, ProtocolError, ValueError)
# The adapter appends a ~110-byte Source citation after this body, and the
# pinned PreparedContextBuilder keeps the first 2000 UTF-8 bytes of an entry.
MEMORY_BODY_BUDGET = 1850
STATUS_TEXT = {"not_required": "", "synced": "老余已记下这段故事。", "pending": "交易已保存，长期记忆暂未同步。稍后回来看看，老余会再试着记下。", "unknown": "交易已保存，长期记忆同步结果待核对。请稍后查看货架，无需重复典当。", "failed": "交易已保存，长期记忆暂未同步。请稍后查看货架。"}
ACTION_TEXT = {"appraise": "鉴定完成", "correct": "鉴定已纠正", "pawn": "已确认典当", "revisit": "回访已记录", "retrieve": "物件已取回", "shelf": "你的货架", "chat": "柜台小叙"}
ITEM_STATUS_TEXT = {"draft": "鉴定草稿，尚未入柜", "pawned": "已入柜", "transformed": "回访后有了新变化", "retrieved": "已取回，故事留档"}


def item_actions(item, current_id):
    actions = []
    if item and item["status"] == "draft":
        if item["id"] == current_id:
            actions.append("correct")
        actions.append("pawn")
    elif item and item["status"] in ("pawned", "transformed"):
        actions += ["revisit", "retrieve"]
    return actions


def snapshot_for(items):
    current = items[0] if items else None
    actions_by_item = {item["id"]: item_actions(item, current["id"]) for item in items}
    actions = ["appraise", "shelf", "chat"]
    for action in ("correct", "pawn", "revisit", "retrieve"):
        if any(action in allowed for allowed in actions_by_item.values()):
            actions.append(action)
    return {"current_item": current, "shelf": items, "item_actions": actions_by_item, "allowed_actions": actions}


def correction_excerpt(text, budget):
    """Longest exact prefix within a JSON-encoded UTF-8 budget, without splitting
    Unicode characters or treating quote/newline escaping as free bytes.
    """
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(text[:middle], ensure_ascii=False).encode("utf-8")) - 2 <= budget:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def recall_query(snapshot, user_query):
    """Build a lexical anchor query from the player's own shelf.

    PowerContext retrieval is lexical (jieba terms plus a minimum query-term
    coverage floor), so a natural-language greeting such as "上次我放在这里的
    东西还在吗" shares too few terms with the stored story and comes back empty.
    The ledger already knows which items belong to this scope, so ask with their
    ids and names: those terms appear verbatim in every stored memory of the
    item and pass the admission floor deterministically. The raw user query is
    still handed to the model by the Chatflow; it is not a retrieval key.
    """
    anchors = []
    for item in snapshot["shelf"][:5]:
        anchors.append(item["id"])
        name = (item["card"].get("name") or "").strip()
        if name:
            anchors.append(name)
    return " ".join(anchors)[:2000] if anchors else user_query[:1000]


def memory_text(event_id, action, item, payload, correction):
    # The pinned PreparedContextBuilder may keep only the first 2000 UTF-8 bytes
    # of an entry. Put compact, backend-owned evidence before the verbose card.
    # Each exact excerpt gets an independent JSON-encoded 512-byte allowance so
    # neither a long correction nor a long report can crowd out the other.
    document = {"event_id": event_id, "action": action, "item_id": item["id"], "version": item["version"], "status": item["status"]}
    if correction:
        raw_text = json.loads(correction["payload"])["user_input"]
        excerpt = correction_excerpt(raw_text, 512)
        document["user_correction"] = {"event_id": correction["id"], "text": excerpt, "truncated": excerpt != raw_text, "kind": "user_verbatim_excerpt"}
    reported = payload["reported_event"]
    event_excerpt = correction_excerpt(reported, 512)
    document["user_reported_event"] = event_excerpt
    document["user_reported_event_truncated"] = event_excerpt != reported
    document["notice"] = "以上为用户原话摘录，完整原文见来源；以下物件卡为虚构故事，不是用户事实。"
    document["fictional_item_card"] = item["card"]
    # Preserve this deliberate order. The ledger's sort_keys=True serializer is
    # suitable for canonical receipts, but would bury these facts after the card.
    text = _render_memory(document)
    if len(text.encode("utf-8")) <= MEMORY_BODY_BUDGET - 100:
        return text
    # The pinned server truncates one Memory text at 2000 UTF-8 bytes, and the
    # adapter appends its Source citation afterwards. Keep the player's verbatim
    # facts and replace the six-field card with a digest that fits, so recall
    # never silently loses corrections or reported events.
    fixed = _render_memory({**document, "fictional_item_card": {}})
    budget = max(64, MEMORY_BODY_BUDGET - 100 - len(fixed.encode("utf-8")))
    document["fictional_item_card"] = compact_card(item["card"], budget)
    document["fictional_item_card_compacted"] = True
    text = _render_memory(document)
    while len(text.encode("utf-8")) > MEMORY_BODY_BUDGET and document["fictional_item_card"]:
        document["fictional_item_card"].popitem()
        text = _render_memory(document)
    return text


def _render_memory(document):
    return "pawnshop " + json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def compact_card(card, budget):
    """Keep whole fields in priority order; shorten the last one to fit the budget."""
    ordered = ["name", "meaning", "inscription", "trait", "appearance", "quest"]
    kept = {}
    used = 2  # braces
    for field in ordered:
        value = card[field]
        size = (len(json.dumps(field, ensure_ascii=False).encode())
                + len(json.dumps(value, ensure_ascii=False).encode()) + 2)
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


def consent(query):
    # Conservative explicit acknowledgement. Quotes, questions, conditionals and
    # negation do not constitute consent, even when a model proposes pawn.
    if re.search(r"不|别|未|没|取消|拒绝|如果|假设|能否|是否|什么|怎么|[?？\"“”‘’']", query):
        return False
    return bool(re.search(r"确认(?:典当|入柜)", query))


def safe_text(value):
    value = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", value)


def render(proposal, item, memory_status, refs, items=None):
    lines = []
    if proposal.reply:
        lines += ["老余：", "", "> " + safe_text(proposal.reply).replace("\n", "\n> "), ""]
    lines += ["**" + ACTION_TEXT[proposal.action] + "**"]
    if item:
        lines += ["", f"当票 `{item['id'][:8]}` · {ITEM_STATUS_TEXT[item['status']]}", "", "**" + safe_text(item["card"]["name"]) + "**（奇幻藏品）", ""]
        for field, label in [("appearance", "外观"), ("trait", "特性"), ("meaning", "寓意"), ("inscription", "铭文"), ("quest", "小任务")]:
            lines.append(f"- {label}：{safe_text(item['card'][field])}")
    if items is not None:
        lines += [""]
        lines += [f"- {safe_text(i['card']['name'])} · 当票 `{i['id'][:8]}` · {ITEM_STATUS_TEXT[i['status']]}" for i in items] or ["货架暂时空着。"]
    if STATUS_TEXT[memory_status]:
        lines += ["", STATUS_TEXT[memory_status]]
    options = ["描述新烦恼", "查看货架"]
    if item and item["status"] == "draft":
        options += ["纠正鉴定", "确认典当 / 确认入柜"]
    elif item and item["status"] in ("pawned", "transformed"):
        options += ["报告近况，让物件变化", "取回物件"]
    lines += ["", "可以输入：" + "；".join(options) + "。"]
    return "\n".join(lines)


class Game:
    CLAIM_LEASE_SECONDS = 120

    def __init__(self, store, pc):
        self.store, self.pc = store, pc
        self._turn_locks = WeakValueDictionary()
        self._locks_guard = Lock()

    def player_exists(self, user):
        with self.store.connect() as conn:
            return conn.execute("SELECT 1 FROM owners WHERE user_id=?", (user,)).fetchone() is not None

    def register_player(self, user):
        with self.store.connect(write=True) as conn:
            conn.execute("INSERT OR IGNORE INTO owners(user_id) VALUES(?)", (user,))

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
                # A receipt written before the external sync is not final; the
                # owner removes its claim only after the final receipt is stored.
                claim = conn.execute("SELECT 1 FROM turn_claims WHERE turn_id=?", (turn_id,)).fetchone()
                if row and not claim:
                    if row["proposal"] != canonical:
                        raise HTTPException(409, "同一 turn 已提交不同提案")
                    return dict(json.loads(row["response"]), replayed=True)
            time.sleep(0.1)
        return None

    def ensure_scope(self, user):
        with self.store.connect(write=True) as conn:
            conn.execute("INSERT OR IGNORE INTO owners(user_id) VALUES (?)", (user,))
            row = conn.execute("SELECT scope_id FROM owners WHERE user_id=?", (user,)).fetchone()
        if row["scope_id"]:
            return row["scope_id"]
        # Scope API explicitly supports idempotency_key, so this call is safe on
        # retry even when an earlier scope-create response was lost.
        scope = self.pc.create_scope(user)
        with self.store.connect(write=True) as conn:
            conn.execute("UPDATE owners SET scope_id=? WHERE user_id=? AND scope_id IS NULL", (scope, user))
            return conn.execute("SELECT scope_id FROM owners WHERE user_id=?", (user,)).fetchone()[0]

    def prepare(self, request):
        with self.store.connect(write=True) as conn:
            prior = conn.execute("SELECT * FROM prepares WHERE turn_id=?", (request.turn_id,)).fetchone()
            if prior:
                if (prior["owner"], prior["conversation"], prior["query"]) != (request.user_id, request.conversation_id, request.query):
                    raise HTTPException(409, "turn 已绑定另一份身份或输入")
                if prior["response"]:
                    return json.loads(prior["response"])
                snapshot = json.loads(prior["snapshot"])
            else:
                conn.execute("INSERT OR IGNORE INTO owners(user_id) VALUES (?)", (request.user_id,))
                items = shelf(conn, request.user_id)
                snapshot = snapshot_for(items)
                conn.execute("INSERT INTO prepares(turn_id,owner,conversation,query,snapshot) VALUES (?,?,?,?,?)", (request.turn_id, request.user_id, request.conversation_id, request.query, dump(snapshot)))
        status, content, refs = "unavailable", "", []
        try:
            scope = self.ensure_scope(request.user_id)
            self.sync(request.user_id, scope)
            status, content, refs = self.pc.prepare(scope, recall_query(snapshot, request.query))
        except EXTERNAL_ERRORS:
            pass
        current = snapshot["current_item"]
        response = {"turn_id": request.turn_id, "state_json": dump(snapshot), "memory_context": content,
                    "memory_status": status, "memory_refs": refs,
                    "active_item_id": current["id"] if current else "", "active_version": current["version"] if current else 0}
        with self.store.connect(write=True) as conn:
            conn.execute("UPDATE prepares SET response=COALESCE(response,?) WHERE turn_id=?", (dump(response), request.turn_id))
            return json.loads(conn.execute("SELECT response FROM prepares WHERE turn_id=?", (request.turn_id,)).fetchone()[0])

    def act(self, request):
        # The in-process lock avoids database churn for duplicate submissions in
        # one worker. The durable claim makes the same guarantee across workers:
        # whoever does not own the turn waits for the final receipt instead of
        # writing external memory twice.
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
            try:
                return self._act(request)
            finally:
                with self.store.connect(write=True) as conn:
                    conn.execute("DELETE FROM turn_claims WHERE turn_id=?", (request.turn_id,))

    def _act(self, request):
        proposal = request.proposal
        canonical = dump(proposal.model_dump())
        event_id = None
        with self.store.connect(write=True) as conn:
            prepared = conn.execute("SELECT * FROM prepares WHERE turn_id=? AND owner=?", (request.turn_id, request.user_id)).fetchone()
            if not prepared or not prepared["response"]:
                raise HTTPException(409, "请先完成此 turn 的 prepare")
            prior = conn.execute("SELECT * FROM receipts WHERE turn_id=?", (request.turn_id,)).fetchone()
            if prior:
                if prior["proposal"] != canonical:
                    raise HTTPException(409, "同一 turn 已提交不同提案")
                return dict(json.loads(prior["response"]), replayed=True)
            snapshot = json.loads(prepared["snapshot"])
            target = proposal.item_id or (snapshot["current_item"]["id"] if snapshot["current_item"] else "")
            item = None
            if target:
                item = item_dict(conn.execute("SELECT * FROM items WHERE id=? AND owner=?", (target, request.user_id)).fetchone())
                if not item:
                    raise HTTPException(404, "藏品不存在")
            action = proposal.action
            mutation = action in ("appraise", "correct", "pawn", "revisit", "retrieve")
            if mutation and action != "appraise":
                if not item:
                    raise HTTPException(409, "当前没有可操作藏品")
                old = next((i for i in snapshot["shelf"] if i["id"] == item["id"]), None)
                if not old or old["version"] != item["version"] or proposal.expected_version not in (0, item["version"]):
                    raise HTTPException(409, "藏品版本已变化，请重新读取")
            if action == "appraise":
                if proposal.item_id or proposal.expected_version != 0 or not proposal.card:
                    raise HTTPException(409, "新鉴定需要完整藏品卡，且不能覆盖已有物件")
                item = {"id": uuid.uuid4().hex, "owner": request.user_id, "version": 1, "status": "draft",
                        "card": proposal.card.model_dump(), "note": "", "lineage": [],
                        "created_at": datetime.now(timezone.utc).isoformat()}
            elif action == "correct":
                live = shelf(conn, request.user_id)
                if item["status"] != "draft" or not live or live[0]["id"] != item["id"] or not snapshot["current_item"] or snapshot["current_item"]["id"] != item["id"] or not proposal.card:
                    raise HTTPException(409, "只能纠正当前鉴定草稿，并提供完整藏品卡")
                item["card"] = proposal.card.model_dump()
            elif action == "pawn":
                if item["status"] != "draft" or not consent(prepared["query"]):
                    raise HTTPException(409, "典当需要草稿与用户原文明确确认：确认典当 / 确认入柜")
                if proposal.card and proposal.card.model_dump() != item["card"]:
                    raise HTTPException(409, "确认入柜不能偷偷更改草稿，请先纠正鉴定")
                item["status"] = "pawned"
            elif action in ("revisit", "retrieve"):
                if item["status"] not in ("pawned", "transformed"):
                    raise HTTPException(409, "只有已典当或已转化藏品可以回访/取回")
                if action == "revisit":
                    event = proposal.reported_event.strip()
                    if not event or event not in prepared["query"] or not proposal.card:
                        raise HTTPException(409, "回访需要用户原文中明确报告的经历（逐字片段）与完整变化卡")
                    item["card"], item["status"] = proposal.card.model_dump(), "transformed"
                else:
                    item["status"] = "retrieved"
            if mutation:
                if action != "appraise":
                    item["version"] += 1
                sequence = conn.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM items").fetchone()[0]
                conn.execute("INSERT INTO items(id,owner,version,status,card,sequence,created_at,note,lineage) "
                             "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                             "version=excluded.version,status=excluded.status,card=excluded.card,"
                             "sequence=excluded.sequence,note=excluded.note,lineage=excluded.lineage",
                             (item["id"], request.user_id, item["version"], item["status"], dump(item["card"]),
                              sequence, item.get("created_at") or datetime.now(timezone.utc).isoformat(),
                              item.get("note", ""), dump(item.get("lineage", []))))
                event_id = uuid.uuid4().hex
                payload = {"item": item, "user_input": prepared["query"], "reported_event": proposal.reported_event if action == "revisit" else "", "fiction_notice": "物件卡为虚构游戏设定，不是用户人格或健康事实"}
                conn.execute("INSERT INTO events(id,item_id,turn_id,action,version,payload) VALUES (?,?,?,?,?,?)", (event_id, item["id"], request.turn_id, action, item["version"], dump(payload)))
                if action != "appraise":
                    correction = conn.execute("SELECT id,payload FROM events WHERE item_id=? AND action='correct' ORDER BY version DESC LIMIT 1", (item["id"],)).fetchone()
                    memory = memory_text(event_id, action, item, payload, correction)
                    conn.execute("INSERT INTO outbox(event_id,owner,status,content,memory_text) VALUES (?,?,'pending',?,?)", (event_id, request.user_id, dump(payload), memory))
            memory_status = "pending" if mutation and action != "appraise" else "not_required"
            items = shelf(conn, request.user_id) if action == "shelf" else None
            response = self.receipt(proposal, item, memory_status, [], items)
            conn.execute("INSERT INTO receipts(turn_id,proposal,response) VALUES (?,?,?)", (request.turn_id, canonical, dump(response)))
        if memory_status == "pending":
            try:
                self.sync(request.user_id, self.ensure_scope(request.user_id))
            except EXTERNAL_ERRORS:
                pass
            with self.store.connect(write=True) as conn:
                row = conn.execute("SELECT status,memory_refs FROM outbox WHERE event_id=?", (event_id,)).fetchone()
                status = self.public_sync_status(row["status"])
                response = self.receipt(proposal, item, status, json.loads(row["memory_refs"]), items)
                conn.execute("UPDATE receipts SET response=? WHERE turn_id=?", (dump(response), request.turn_id))
        return response

    @staticmethod
    def receipt(proposal, item, status, refs, items):
        return {"ok": True, "action": proposal.action, "reply": proposal.reply, "display": render(proposal, item, status, refs, items), "item_id": item["id"] if item else "", "version": item["version"] if item else 0, "memory_status": status, "memory_refs": refs, "replayed": False}

    @staticmethod
    def public_sync_status(status):
        return "unknown" if status in ("writing_source", "writing_memory", "unknown") else "pending" if status == "source_ready" else status

    def sync(self, owner, scope):
        # Claim each stage in a short transaction; never hold SQLite's write lock
        # while waiting for the network. In-flight/crash remnants are not retried.
        with self.store.connect() as conn:
            ids = [row[0] for row in conn.execute("SELECT event_id FROM outbox WHERE owner=? AND status IN ('pending','source_ready') ORDER BY rowid LIMIT 20", (owner,))]
        for event_id in ids:
            with self.store.connect(write=True) as conn:
                row = conn.execute("SELECT * FROM outbox WHERE event_id=?", (event_id,)).fetchone()
                if row["status"] not in ("pending", "source_ready"):
                    continue
                previous = row["status"]
                conn.execute("UPDATE outbox SET status=? WHERE event_id=?", ("writing_source" if previous == "pending" else "writing_memory", event_id))
            try:
                source = json.loads(row["source_receipt"]) if row["source_receipt"] else None
                if previous == "pending":
                    source = self.pc.capture(scope, event_id, row["content"])
                    with self.store.connect(write=True) as conn:
                        conn.execute("UPDATE outbox SET status='writing_memory',source_receipt=? WHERE event_id=?", (dump(source), event_id))
                    previous = "source_ready"
                refs, memory_receipt = self.pc.remember(scope, row["memory_text"], source)
                with self.store.connect(write=True) as conn:
                    conn.execute("UPDATE outbox SET status='synced',memory_receipt=?,memory_refs=?,error=NULL WHERE event_id=?", (dump(memory_receipt), dump(refs), event_id))
            except EXTERNAL_ERRORS as error:
                # A connect failure establishes that no request reached the peer.
                # Read/write timeouts, HTTP failures, invalid success receipts and
                # process interruption have an uncertain write outcome.
                status = previous if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)) else "unknown"
                with self.store.connect(write=True) as conn:
                    conn.execute("UPDATE outbox SET status=?,error=? WHERE event_id=?", (status, type(error).__name__, event_id))
                if status in ("pending", "source_ready"):
                    break

    def items(self, owner, limit=50, cursor=None):
        limit = max(1, min(int(limit), 100))
        if cursor is not None:
            try:
                cursor = int(cursor)
            except (TypeError, ValueError):
                raise HTTPException(422, "cursor 无效")
            if cursor < 1:
                raise HTTPException(422, "cursor 无效")
        with self.store.connect() as conn:
            items, next_cursor = shelf_page(conn, owner, limit, cursor)
        return {"items": items, "next_cursor": next_cursor}

    def export(self, owner):
        with self.store.connect() as conn:
            items = shelf(conn, owner)
        return {"user_id": owner, "exported_at": datetime.now(timezone.utc).isoformat(),
                "items": [self.detail(owner, item["id"]) for item in items]}

    def detail(self, owner, item_id):
        with self.store.connect() as conn:
            item = item_dict(conn.execute("SELECT * FROM items WHERE id=? AND owner=?", (item_id, owner)).fetchone())
            if not item:
                raise HTTPException(404, "藏品不存在")
            item["events"] = []
            for row in conn.execute("SELECT e.*,o.status AS sync_status,o.source_receipt,o.memory_refs FROM events e LEFT JOIN outbox o ON o.event_id=e.id WHERE e.item_id=? ORDER BY e.version", (item_id,)):
                item["events"].append({"event_id": row["id"], "action": row["action"], "version": row["version"], "payload": json.loads(row["payload"]), "memory_status": self.public_sync_status(row["sync_status"]) if row["sync_status"] else "not_required", "source_receipt": json.loads(row["source_receipt"]) if row["source_receipt"] else None, "memory_refs": json.loads(row["memory_refs"] or "[]")})
        return item
