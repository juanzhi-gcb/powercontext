import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi.testclient import TestClient

from test_game import PowerContextHTTP, act, draft, prepare


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


def test_rate_limit_returns_429_after_budget(tmp_path):
    from pawnshop.app import create_app
    wire = PowerContextHTTP()
    app = create_app(db_path=str(tmp_path / "rate.sqlite3"), api_key="test-secret",
                     powercontext_url="http://pc", powercontext_token="pc-test",
                     transport=httpx.MockTransport(wire), rate_limit=2)
    with TestClient(app, headers={"X-Pawnshop-Key": "test-secret"}) as client:
        accepted = [prepare(client, f"t{index}").status_code for index in range(2)]
        blocked = prepare(client, "t9")
    assert accepted == [200, 200]
    assert blocked.status_code == 429


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