"""Browser BFF: signed 当票 sessions, Dify chat proxy and read-only game views.

The browser never sees the Dify app key or the game service key. It talks to
this router only; the Chatflow still runs the model and orchestration inside
Dify, and the game ledger remains the authority for every state change.
"""
import base64
import hashlib
import hmac
import re
import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, StringConstraints

COOKIE = "pawnshop_ticket"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TICKET_CHARS = 10
MAX_AGE = 400 * 24 * 3600

OPENING = ("进来坐。我是老余，这里收的是烦恼的故事，不收利息。"
           "说一件最近硌着你的事，我先出张草稿；鉴定错了随时纠正，单独说「确认典当」才正式入柜。")
CHIPS = ["鉴定一件烦恼", "查看货架", "纠正鉴定", "确认典当", "报告近况", "取回物件"]


class Claim(BaseModel):
    ticket: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class Chat(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
    conversation_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""


def new_player_id():
    return "guest-" + "".join(secrets.choice(ALPHABET) for _ in range(TICKET_CHARS)).lower()


def display_ticket(player):
    code = player.removeprefix("guest-").upper()
    return f"{code[:5]}-{code[5:]}"


def normalize_ticket(value):
    raw = re.sub(r"[^A-Z0-9]", "", value.upper())
    if len(raw) != TICKET_CHARS or any(char not in ALPHABET for char in raw):
        raise HTTPException(422, "当票号格式不对")
    return "guest-" + raw.lower()


def _sign(secret, value):
    digest = hmac.new(secret.encode(), value.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def cookie_value(secret, player):
    return f"{player}.{_sign(secret, player)}"


def read_cookie(secret, value):
    if not value or "." not in value:
        return None
    player, _, signature = value.rpartition(".")
    if not re.fullmatch(r"guest-[a-z2-9]{10}", player):
        return None
    if not hmac.compare_digest(signature, _sign(secret, player)):
        return None
    return player


def create_web_router(game, limiter, *, secret, dify_url="", dify_key="", transport=None):
    router = APIRouter()

    def current(ticket):
        player = read_cookie(secret, ticket)
        if not player:
            raise HTTPException(401, "还没有当票")
        return player

    def set_ticket(response, player):
        response.set_cookie(COOKIE, cookie_value(secret, player), max_age=MAX_AGE,
                            httponly=True, samesite="lax", path="/")

    @router.get("/api/config")
    def config():
        return {"opening": OPENING, "chips": CHIPS, "dify_ready": bool(dify_key and dify_url)}

    @router.post("/api/session")
    def session(response: Response, request: Request,
                ticket: Annotated[str | None, Cookie(alias=COOKIE)] = None):
        limiter.check(f"session-ip:{request.client.host if request.client else 'unknown'}")
        player = read_cookie(secret, ticket)
        if player:
            return {"player": player, "ticket": display_ticket(player), "new": False}
        for _ in range(5):
            candidate = new_player_id()
            if not game.player_exists(candidate):
                break
        game.register_player(candidate)
        set_ticket(response, candidate)
        return {"player": candidate, "ticket": display_ticket(candidate), "new": True}

    @router.post("/api/session/claim")
    def claim(body: Claim, response: Response):
        player = normalize_ticket(body.ticket)
        if not game.player_exists(player):
            raise HTTPException(404, "没有找到这张当票")
        set_ticket(response, player)
        return {"player": player, "ticket": display_ticket(player), "new": False}

    @router.post("/api/chat")
    def chat(body: Chat, request: Request,
             ticket: Annotated[str | None, Cookie(alias=COOKIE)] = None):
        limiter.check(f"chat-ip:{request.client.host if request.client else 'unknown'}")
        player = current(ticket)
        limiter.check(f"chat:{player}")
        if not dify_key or not dify_url:
            raise HTTPException(503, "还没有接上模型，请先在 Dify 配置并填写 DIFY_APP_API_KEY")
        payload = {"inputs": {}, "query": body.query, "response_mode": "blocking",
                   "user": player, "conversation_id": body.conversation_id}
        try:
            with httpx.Client(transport=transport, timeout=httpx.Timeout(180.0, connect=5.0)) as client:
                answer = client.post(dify_url.rstrip("/") + "/chat-messages", json=payload,
                                     headers={"Authorization": f"Bearer {dify_key}"})
        except httpx.HTTPError as error:
            raise HTTPException(502, "柜台暂时连不上，请稍后再试") from error
        if answer.status_code != 200:
            raise HTTPException(502, "这次请求没有走完，请稍后再试")
        data = answer.json()
        return {"answer": data.get("answer", ""),
                "conversation_id": data.get("conversation_id", body.conversation_id),
                "message_id": data.get("message_id", "")}

    @router.get("/api/shelf")
    def shelf(ticket: Annotated[str | None, Cookie(alias=COOKIE)] = None):
        player = current(ticket)
        return game.items(player, 50, None)

    @router.get("/api/items/{item_id}")
    def item(item_id: str, ticket: Annotated[str | None, Cookie(alias=COOKIE)] = None):
        player = current(ticket)
        if len(item_id) > 256:
            raise HTTPException(422, "item_id too long")
        return game.detail(player, item_id)

    return router