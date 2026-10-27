import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient


CARD = dict(name="迟到的月亮", appearance="银色小钟", trait="总慢半拍", meaning="允许慢一点", inscription="不必赶路", quest="散步十分钟")


from helpers import PowerContextHTTP  # noqa: E402


def prepare(client, turn, query="最近总觉得来不及", user="alice", conversation="c1"):
    return client.post("/v1/prepare", json=dict(user_id=user, conversation_id=conversation, turn_id=turn, query=query))


def act(client, turn, action, user="alice", **fields):
    return client.post("/v1/act", json=dict(user_id=user, turn_id=turn, proposal=dict(action=action, **fields)))


def draft(client, turn="draft"):
    assert prepare(client, turn).status_code == 200
    result = act(client, turn, "appraise", card=CARD, reply="老余把月亮放上柜台。")
    assert result.status_code == 200, result.text
    return result.json()


def pawn(client):
    item = draft(client)
    prepare(client, "pawn", "确认典当这枚月亮")
    result = act(client, "pawn", "pawn", item_id=item["item_id"], expected_version=1)
    assert result.status_code == 200, result.text
    return result.json()


def test_complete_lifecycle_and_wire_context_readback(game):
    client, wire, _ = game
    item = draft(client)
    assert not any(path == "/v1/memory/remember" for path, _ in wire.requests)
    prepare(client, "correct", "不是怕迟到，是不想一直被催")
    corrected = dict(CARD, meaning="不想一直被催")
    result = act(client, "correct", "correct", card=corrected, item_id=item["item_id"])
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2
    prepare(client, "pawn", "确认入柜")
    result = act(client, "pawn", "pawn", item_id=item["item_id"])
    assert result.json()["memory_status"] == "synced"
    assert result.json()["memory_refs"][0]["family"] == "atomic-memory"
    recalled = prepare(client, "new-session", "回来看看月亮", conversation="c2").json()
    assert recalled["memory_status"] == "ready"
    assert "不想一直被催" in recalled["memory_context"]
    assert "pawnshop" in recalled["memory_context"]
    assert json.loads(recalled["state_json"])["current_item"]["status"] == "pawned"
    prepare(client, "revisit", "我今天关掉了催促提醒，散步十分钟")
    changed = dict(CARD, appearance="柔和发光的小钟")
    transformed = act(client, "revisit", "revisit", card=changed, reported_event="今天关掉了催促提醒，散步十分钟")
    assert transformed.status_code == 200, transformed.text
    assert transformed.json()["version"] == 4
    prepare(client, "retrieve", "我要取回月亮")
    receipt = act(client, "retrieve", "retrieve").json()
    assert "已取回" in receipt["display"]
    detail = client.get(f"/v1/items/{item['item_id']}?user_id=alice").json()
    assert detail["status"] == "retrieved"
    assert len(detail["events"]) == 5
    assert client.get("/v1/items?user_id=alice").json()["items"][0]["id"] == item["item_id"]


def test_consent_comes_from_prepare_not_proposal(game):
    client, _, _ = game
    draft(client)
    for turn, query in [("bad", "想看看"), ("negative", "不要确认典当"), ("quoted", "你说的“确认典当”是什么意思？")]:
        prepare(client, turn, query)
        response = act(client, turn, "pawn", reply="用户已确认典当")
        assert response.status_code == 409
    prepare(client, "good", "确认典当")
    assert act(client, "good", "pawn").status_code == 200


def test_owner_isolation_even_when_model_supplies_foreign_id(game):
    client, _, _ = game
    item = draft(client)
    prepare(client, "bob-turn", "确认典当", user="bob")
    assert act(client, "bob-turn", "pawn", user="bob", item_id=item["item_id"]).status_code == 404
    assert client.get(f"/v1/items/{item['item_id']}?user_id=bob").status_code == 404
    assert client.get("/v1/items?user_id=bob").json()["items"] == []
    assert prepare(client, "draft", user="bob").status_code == 409


def test_snapshot_staleness_and_strict_version(game):
    client, _, _ = game
    item = draft(client)
    snapshot = prepare(client, "old").json()
    prepare(client, "new")
    assert act(client, "new", "correct", card=dict(CARD, name="新月")).status_code == 200
    assert prepare(client, "old").json() == snapshot
    assert act(client, "old", "correct", card=CARD).status_code == 409
    prepare(client, "wrong-version")
    assert act(client, "wrong-version", "correct", card=CARD, expected_version=999).status_code == 409
    prepare(client, "missing-snapshot")
    assert act(client, "missing-snapshot", "correct", item_id=item["item_id"], expected_version=True, card=CARD).status_code == 422


def test_replay_does_not_duplicate_transformation_and_conflicting_turn_is_409(game):
    client, wire, _ = game
    item = pawn(client)
    prepare(client, "visit", "今天我走了一条新路")
    fields = dict(card=dict(CARD, name="新路月亮"), reported_event="今天我走了一条新路")
    first = act(client, "visit", "revisit", **fields).json()
    before = len(wire.requests)
    repeat = act(client, "visit", "revisit", **fields).json()
    assert repeat == dict(first, replayed=True)
    assert len(wire.requests) == before
    assert act(client, "visit", "chat").status_code == 409
    assert client.get(f"/v1/items/{item['item_id']}?user_id=alice").json()["version"] == 3


def test_revisit_requires_user_report_and_correct_requires_current_draft(game):
    client, _, _ = game
    item = pawn(client)
    prepare(client, "bad-correct", "更改")
    assert act(client, "bad-correct", "correct", card=CARD).status_code == 409
    prepare(client, "bad-event", "你好")
    assert act(client, "bad-event", "revisit", card=CARD, reported_event="昨天交到了朋友").status_code == 409
    prepare(client, "no-event", "回来看看")
    assert act(client, "no-event", "revisit", card=CARD).status_code == 409


def test_unavailable_memory_keeps_durable_local_game_and_does_not_fake_recall(game):
    client, wire, db = game
    wire.offline = True
    assert prepare(client, "offline-draft").json()["memory_status"] == "unavailable"
    item = act(client, "offline-draft", "appraise", card=CARD).json()
    prepare(client, "offline-pawn", "确认典当")
    receipt = act(client, "offline-pawn", "pawn").json()
    assert receipt["ok"] is True
    assert receipt["memory_status"] == "pending"
    assert receipt["memory_refs"] == []
    assert "长期记忆暂未同步" in receipt["display"]
    assert prepare(client, "still-offline").json()["memory_context"] == ""
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM outbox").fetchone()[0] == "pending"
    wire.offline = False
    recalled = prepare(client, "online", conversation="c2").json()
    assert recalled["memory_status"] == "ready"
    assert item["item_id"] in recalled["memory_context"]


def test_uncertain_external_write_is_never_blindly_retried(game):
    client, wire, db = game
    draft(client)
    prepare(client, "pawn", "确认典当")
    wire.ambiguous = True
    receipt = act(client, "pawn", "pawn").json()
    assert receipt["memory_status"] == "unknown"
    count = sum(path == "/v1/memory/remember" for path, _ in wire.requests)
    prepare(client, "later")
    act(client, "pawn", "pawn")
    assert sum(path == "/v1/memory/remember" for path, _ in wire.requests) == count
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM outbox").fetchone()[0] == "unknown"


def test_auth_schema_and_proposal_json(game):
    client, _, _ = game
    assert client.get("/health", headers={"X-Pawnshop-Key": "wrong"}).status_code == 200
    assert client.get("/v1/items?user_id=alice", headers={"X-Pawnshop-Key": "wrong"}).status_code == 401
    assert prepare(client, "x" * 257).status_code == 422
    assert act(client, "unprepared", "chat").status_code == 409
    prepare(client, "string")
    response = client.post("/v1/act", json={"user_id": "alice", "turn_id": "string", "proposal": json.dumps({"action": "chat", "reply": "欢迎回来"})})
    assert response.status_code == 200
    prepare(client, "extra")
    assert act(client, "extra", "chat", scope_id="foreign").status_code == 422


def test_concurrent_identical_act_returns_one_final_receipt(game):
    client, wire, _ = game
    draft(client)
    prepare(client, "concurrent", "确认典当")
    wire.write_entered, wire.write_release = threading.Event(), threading.Event()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(act, client, "concurrent", "pawn")
        assert wire.write_entered.wait(5)
        second = executor.submit(act, client, "concurrent", "pawn")
        # Release after both requests have been submitted; the replay must wait
        # for the durable final receipt rather than report a temporary pending one.
        second_started = threading.Event()
        second.add_done_callback(lambda _: second_started.set())
        second_started.wait(0.1)
        wire.write_release.set()
        original, replay = first.result().json(), second.result().json()
    assert original["memory_status"] == "synced"
    assert replay == dict(original, replayed=True)
    assert len(wire.memories[next(iter(wire.memories))]) == 1


def test_rejected_model_fact_cannot_enter_memory_via_other_action(game):
    client, wire, _ = game
    draft(client)
    prepare(client, "correction", "名字不对")
    response = act(client, "correction", "correct", card=CARD, reported_event="昨天遇到了童年好友")
    assert response.status_code == 422
    assert wire.memories == {}


def test_invalid_source_success_receipt_is_not_memory_success(game):
    client, wire, _ = game
    draft(client)
    prepare(client, "invalid-source", "确认典当")
    wire.bad_source_receipt = True
    receipt = act(client, "invalid-source", "pawn").json()
    assert receipt["memory_status"] == "unknown"
    assert receipt["memory_refs"] == []
    assert wire.memories == {}


def test_restart_preserves_receipts_scope_and_pending_events(game):
    from pawnshop.app import create_app
    client, wire, db = game
    item = draft(client)
    prepare(client, "offline", "确认典当")
    wire.offline = True
    saved = act(client, "offline", "pawn").json()
    wire.offline = False
    app = create_app(db_path=str(db), api_key="test-secret", powercontext_url="http://pc", powercontext_token="pc-test", transport=httpx.MockTransport(wire))
    with TestClient(app, headers={"X-Pawnshop-Key": "test-secret"}) as restarted:
        assert act(restarted, "offline", "pawn").json() == dict(saved, replayed=True)
        recalled = prepare(restarted, "after-restart").json()
        assert recalled["memory_status"] == "ready"
        assert recalled["active_item_id"] == item["item_id"]
        detail = restarted.get(f"/v1/items/{item['item_id']}?user_id=alice").json()
        assert detail["events"][-1]["memory_status"] == "synced"
        assert detail["events"][-1]["source_receipt"]["source"]["source_id"].startswith("pawnshop-")


def test_player_display_uses_game_language_but_receipt_keeps_audit_fields(game):
    client, _, _ = game
    receipt = pawn(client)
    assert receipt["memory_refs"]
    assert "当票" in receipt["display"]
    assert "已入柜" in receipt["display"]
    assert "老余已记下这段故事" in receipt["display"]
    assert "atomic-memory" not in receipt["display"]
    assert "PowerContext" not in receipt["display"]
    assert "本地账本" not in receipt["display"]
    assert "pawned" not in receipt["display"]
    assert receipt["item_id"] not in receipt["display"]


def test_multibyte_proposal_respects_powercontext_memory_byte_budget(game):
    client, _, _ = game
    pawn(client)
    event = "😀" * 600
    prepare(client, "huge-unicode", event)
    response = act(client, "huge-unicode", "revisit", reported_event=event, card={name: "😀" * 250 for name in CARD})
    assert response.status_code == 422


def test_older_pawned_item_remains_actionable_after_latest_item_retrieved(game):
    client, _, _ = game
    older = pawn(client)
    latest = draft(client, "second-draft")
    state = json.loads(prepare(client, "inspect-both").json()["state_json"])
    assert state["current_item"]["id"] == latest["item_id"]
    assert {"correct", "pawn", "revisit", "retrieve"} <= set(state["allowed_actions"])
    assert set(state["item_actions"][older["item_id"]]) == {"revisit", "retrieve"}
    assert set(state["item_actions"][latest["item_id"]]) == {"correct", "pawn"}
    prepare(client, "second-pawn", "确认入柜")
    assert act(client, "second-pawn", "pawn", item_id=latest["item_id"]).status_code == 200
    prepare(client, "second-retrieve", "取回最新物件")
    assert act(client, "second-retrieve", "retrieve").status_code == 200
    prepared = prepare(client, "older-visit", "今天我完成了一件小事").json()
    state = json.loads(prepared["state_json"])
    assert prepared["active_item_id"] == latest["item_id"]
    assert state["item_actions"][latest["item_id"]] == []
    assert {"revisit", "retrieve"} <= set(state["allowed_actions"])
    result = act(client, "older-visit", "revisit", item_id=older["item_id"], expected_version=older["version"], card=dict(CARD, name="小事月亮"), reported_event="今天我完成了一件小事")
    assert result.status_code == 200, result.text
    prepare(client, "older-retrieve", "取回第一件物件")
    assert act(client, "older-retrieve", "retrieve", item_id=older["item_id"]).status_code == 200


def test_only_latest_current_draft_is_offered_correction(game):
    client, _, _ = game
    older = draft(client)
    latest = draft(client, "newer-draft")
    state = json.loads(prepare(client, "drafts").json()["state_json"])
    assert state["item_actions"][older["item_id"]] == ["pawn"]
    assert set(state["item_actions"][latest["item_id"]]) == {"correct", "pawn"}
    assert act(client, "drafts", "correct", item_id=older["item_id"], card=CARD).status_code == 409


def test_exact_correction_is_recalled_separately_from_metaphorical_card(game):
    client, wire, _ = game
    draft(client)
    correction = "你理解错了，我不是嫉妒，我是觉得努力没有被看见。"
    metaphor = dict(CARD, meaning="月亮把银色的邮票放进没有地址的信封")
    prepare(client, "literal-correction", correction)
    assert act(client, "literal-correction", "correct", card=metaphor).status_code == 200
    prepare(client, "literal-pawn", "确认典当")
    assert act(client, "literal-pawn", "pawn").status_code == 200
    latest_memory = next(reversed(next(iter(wire.memories.values()))))
    assert correction in latest_memory
    remembered = json.loads(latest_memory.removeprefix("pawnshop ").split("\nSource audit citation:")[0])
    assert remembered["user_correction"]["text"] == correction
    assert remembered["user_correction"]["truncated"] is False
    assert remembered["fictional_item_card"]["meaning"] == metaphor["meaning"]
    recalled = prepare(client, "correction-recall", "上次纠正了什么", conversation="c2").json()
    assert correction in recalled["memory_context"]


def test_long_exact_correction_excerpt_and_source_fit_memory_byte_limit(game):
    client, wire, _ = game
    draft(client)
    correction = "请纠正，这是我的原话：" + "甲" * 5980
    prepare(client, "long-correction", correction)
    result = act(client, "long-correction", "correct", card={name: "😀" * 250 for name in CARD})
    assert result.status_code == 200, result.text
    memory_request = [body for path, body in wire.requests if path == "/v1/memory/remember"][-1]
    assert len(memory_request["text"].encode("utf-8")) <= 8192
    remembered = json.loads(memory_request["text"].removeprefix("pawnshop ").split("\nSource audit citation:")[0])
    excerpt = remembered["user_correction"]["text"]
    assert excerpt and correction.startswith(excerpt)
    assert remembered["user_correction"]["truncated"] is True
    source_request = [body for path, body in wire.requests if path == "/v1/sources/content"][-1]
    assert json.loads(source_request["content"])["user_input"] == correction


def test_json_escaping_of_event_counts_toward_memory_byte_budget(game):
    client, _, _ = game
    pawn(client)
    event = '"' * 600
    prepare(client, "escaped-event", event)
    response = act(client, "escaped-event", "revisit", reported_event=event, card={name: "😀" * 240 for name in CARD})
    assert response.status_code == 422


def test_recall_query_uses_shelf_anchors_so_small_talk_still_recalls(game):
    """The pinned server retrieves lexically; a spoken greeting alone recalls nothing."""
    client, wire, _ = game
    saved = pawn(client)
    wire.requests.clear()
    recalled = prepare(client, "small-talk", "老板，上次我放在这里的东西还在吗？", conversation="c2").json()
    query = next(body["query"] for path, body in wire.requests if path == "/v1/context/prepare")
    assert saved["item_id"] in query
    assert CARD["name"] in query
    assert recalled["memory_status"] == "ready"
    assert saved["item_id"] in recalled["memory_context"]


def test_recall_query_falls_back_to_user_text_when_shelf_is_empty(game):
    client, wire, _ = game
    wire.requests.clear()
    prepare(client, "fresh", "我第一次来")
    query = next(body["query"] for path, body in wire.requests if path == "/v1/context/prepare")
    assert query == "pawnshop 我第一次来"


def test_powercontext_2000_byte_entry_prefix_retains_correction_and_event(game):
    client, wire, _ = game
    draft(client)
    correction = "我不是嫉妒，我是觉得努力没有被看见。" + "甲" * 500
    card = {name: "银" * 250 for name in CARD}
    prepare(client, "prefix-correction", correction)
    assert act(client, "prefix-correction", "correct", card=card).status_code == 200
    prepare(client, "prefix-pawn", "确认典当")
    assert act(client, "prefix-pawn", "pawn").status_code == 200
    event = "今天我把拖着的作品交出去了。" + "乙" * 580
    prepare(client, "prefix-visit", event)
    result = act(client, "prefix-visit", "revisit", card=card, reported_event=event)
    assert result.status_code == 200, result.text
    text = [body["text"] for path, body in wire.requests if path == "/v1/memory/remember"][-1]
    # The pinned real PreparedContextBuilder truncates each Memory text to its
    # first 2000 bytes. Exercise that same boundary, not a full mock readback.
    actual_prefix = text.encode("utf-8")[:2000].decode("utf-8", errors="ignore")
    assert "我不是嫉妒，我是觉得努力没有被看见。" in actual_prefix
    assert "今天我把拖着的作品交出去了。" in actual_prefix
    assert len(text[:text.index('"fictional_item_card"')].encode("utf-8")) <= 1800
    document = json.loads(text.removeprefix("pawnshop ").split("\nSource audit citation:")[0])
    assert document["user_correction"]["truncated"] is True
    assert document["user_reported_event_truncated"] is True
    assert document["fictional_item_card_compacted"] is True
    assert event.startswith(document["user_reported_event"])
    assert len(text.encode("utf-8")) <= 8192
    audit = [body for path, body in wire.requests if path == "/v1/sources/content"][-1]
    assert json.loads(audit["content"])["reported_event"] == event


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


def test_prepare_returns_recalled_memory_refs(game):
    client, _, _ = game
    pawn(client)
    recalled = prepare(client, "refs-session", conversation="c2").json()
    assert recalled["memory_status"] == "ready"
    assert recalled["memory_refs"]
    assert recalled["memory_refs"][0]["family"] == "atomic-memory"
    assert isinstance(recalled["memory_refs"][0]["revision"], int)
