import json
import re

import httpx
from fastapi.testclient import TestClient

from helpers import PowerContextHTTP


def build(tmp_path, dify_status=200):
    wire = PowerContextHTTP()
    seen = []

    def dify(request):
        seen.append(json.loads(request.content))
        if dify_status != 200:
            return httpx.Response(dify_status, json={"code": "error"})
        body = json.loads(request.content)
        return httpx.Response(200, json={"answer": "老余：进来坐。", "conversation_id": "conv-" + body["user"],
                                         "message_id": "m1"})

    from pawnshop.app import create_app
    app = create_app(db_path=str(tmp_path / "web.sqlite3"), api_key="test-secret",
                     powercontext_url="http://pc", powercontext_token="pc-test",
                     transport=httpx.MockTransport(wire), session_secret="browser-test",
                     dify_url="http://dify/v1", dify_key="app-key",
                     dify_transport=httpx.MockTransport(dify),
                     frontend_dir=tmp_path / "missing")
    return app, wire, seen


def test_session_ticket_chat_and_claim(tmp_path):
    app, wire, seen = build(tmp_path)
    with TestClient(app) as browser:
        session = browser.post("/api/session").json()
        assert re.fullmatch(r"[A-Z2-9]{5}-[A-Z2-9]{5}", session["ticket"])
        assert session["new"] is True
        assert browser.get("/api/shelf").json()["items"] == []

        chat = browser.post("/api/chat", json={"query": "我最近总拿自己和别人比较", "conversation_id": ""})
        assert chat.status_code == 200
        assert chat.json()["answer"].startswith("老余：")
        assert chat.json()["conversation_id"] == "conv-" + session["player"]
        assert seen[-1]["user"] == session["player"]

        claimed = browser.post("/api/session/claim", json={"ticket": session["ticket"].lower()})
        assert claimed.status_code == 200
        assert claimed.json()["player"] == session["player"]

    with TestClient(app) as other_browser:
        assert other_browser.get("/api/shelf").status_code == 401
        restored = other_browser.post("/api/session/claim", json={"ticket": session["ticket"]})
        assert restored.json()["player"] == session["player"]
        assert other_browser.get("/api/shelf").status_code == 200


def test_invalid_and_unknown_tickets_are_rejected(tmp_path):
    app, _, _ = build(tmp_path)
    with TestClient(app) as browser:
        assert browser.post("/api/session/claim", json={"ticket": "!!!!"}).status_code == 422
        assert browser.post("/api/session/claim", json={"ticket": "ABCDE-FGHJK"}).status_code == 404


def test_chat_requires_session_and_reports_dify_failure(tmp_path):
    app, _, _ = build(tmp_path, dify_status=500)
    with TestClient(app) as browser:
        assert browser.post("/api/chat", json={"query": "你好"}).status_code == 401
        browser.post("/api/session")
        response = browser.post("/api/chat", json={"query": "你好"})
        assert response.status_code == 502


def test_chat_is_unavailable_without_dify_credentials(tmp_path):
    wire = PowerContextHTTP()
    from pawnshop.app import create_app
    app = create_app(db_path=str(tmp_path / "nodify.sqlite3"), api_key="test-secret",
                     powercontext_url="http://pc", powercontext_token="pc-test",
                     transport=httpx.MockTransport(wire), session_secret="browser-test",
                     dify_url="", dify_key="", frontend_dir=tmp_path / "missing")
    with TestClient(app) as browser:
        browser.post("/api/session")
        assert browser.post("/api/chat", json={"query": "你好"}).status_code == 503