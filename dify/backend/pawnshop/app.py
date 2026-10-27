"""Run with: uvicorn pawnshop.app:create_app --factory --host 0.0.0.0 --port 8080."""
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from .models import ActRequest, Identity, PrepareRequest
from .powercontext import PowerContext
from .ratelimit import RateLimiter
from .service import Game
from .store import Store
from .web import create_web_router


def create_app(db_path=None, api_key=None, powercontext_url=None, powercontext_token=None,
               transport=None, rate_limit=None, dify_url=None, dify_key=None,
               session_secret=None, dify_transport=None, frontend_dir=None):
    secret = api_key if api_key is not None else os.environ.get("PAWNSHOP_API_KEY", "")
    if not secret:
        raise RuntimeError("PAWNSHOP_API_KEY must be configured")
    store = Store(db_path or os.environ.get("PAWNSHOP_DB_PATH", "/data/pawnshop.sqlite3"))
    pc = PowerContext(powercontext_url or os.environ.get("POWERCONTEXT_URL", "http://powercontext:8000"), powercontext_token if powercontext_token is not None else os.environ.get("POWERCONTEXT_TOKEN", ""), transport)
    game = Game(store, pc)
    limiter = RateLimiter(store, limit=int(rate_limit if rate_limit is not None
                                           else os.environ.get("PAWNSHOP_RATE_LIMIT", "120")))
    browser_secret = (session_secret if session_secret is not None
                      else os.environ.get("PAWNSHOP_SESSION_SECRET", "")) or secrets.token_urlsafe(32)
    dify_url = dify_url if dify_url is not None else os.environ.get("DIFY_API_URL", "")
    dify_key = dify_key if dify_key is not None else os.environ.get("DIFY_APP_API_KEY", "")

    @asynccontextmanager
    async def lifespan(app):
        yield
        pc.client.close()

    app = FastAPI(title="烦恼典当行", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.game = game

    def authenticate(x_pawnshop_key: Annotated[str | None, Header()] = None):
        if x_pawnshop_key is None or not hmac.compare_digest(x_pawnshop_key.encode(), secret.encode()):
            raise HTTPException(401, "invalid pawnshop service key")

    authenticated = [Depends(authenticate)]

    @app.get("/health")
    def health():
        with store.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"ok": True, "service": "pawnshop", "storage": "sqlite"}

    @app.post("/v1/prepare", dependencies=authenticated)
    def prepare(request: PrepareRequest):
        limiter.check(f"prepare:{request.user_id}")
        return game.prepare(request)

    @app.post("/v1/act", dependencies=authenticated)
    def act(request: ActRequest):
        limiter.check(f"act:{request.user_id}")
        return game.act(request)

    @app.get("/v1/items", dependencies=authenticated)
    def items(user_id: Annotated[Identity, Query()],
              limit: Annotated[int, Query(ge=1, le=100)] = 50,
              cursor: Annotated[str | None, Query()] = None):
        return game.items(user_id, limit, cursor)

    @app.get("/v1/items/{item_id}", dependencies=authenticated)
    def detail(item_id: str, user_id: Annotated[Identity, Query()]):
        if len(item_id) > 256:
            raise HTTPException(422, "item_id too long")
        return game.detail(user_id, item_id)

    @app.get("/v1/export", dependencies=authenticated)
    def export(user_id: Annotated[Identity, Query()]):
        return game.export(user_id)

    app.include_router(create_web_router(game, limiter, secret=browser_secret,
                                         dify_url=dify_url, dify_key=dify_key,
                                         transport=dify_transport))

    frontend = Path(frontend_dir or os.environ.get("PAWNSHOP_FRONTEND")
                    or Path(__file__).resolve().parents[2] / "frontend")
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app