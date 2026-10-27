"""Run with: uvicorn pawnshop.app:create_app --factory --host 0.0.0.0 --port 8080."""
import hmac
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from .models import ActRequest, Identity, PrepareRequest
from .powercontext import PowerContext
from .service import Game
from .store import Store


def create_app(db_path=None, api_key=None, powercontext_url=None, powercontext_token=None, transport=None):
    secret = api_key if api_key is not None else os.environ.get("PAWNSHOP_API_KEY", "")
    if not secret:
        raise RuntimeError("PAWNSHOP_API_KEY must be configured")
    store = Store(db_path or os.environ.get("PAWNSHOP_DB_PATH", "/data/pawnshop.sqlite3"))
    pc = PowerContext(powercontext_url or os.environ.get("POWERCONTEXT_URL", "http://powercontext:8000"), powercontext_token if powercontext_token is not None else os.environ.get("POWERCONTEXT_TOKEN", ""), transport)
    game = Game(store, pc)

    @asynccontextmanager
    async def lifespan(app):
        yield
        pc.client.close()

    app = FastAPI(title="烦恼典当行", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
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
        return game.prepare(request)

    @app.post("/v1/act", dependencies=authenticated)
    def act(request: ActRequest):
        return game.act(request)

    @app.get("/v1/items", dependencies=authenticated)
    def items(user_id: Annotated[Identity, Query()]):
        return game.items(user_id)

    @app.get("/v1/items/{item_id}", dependencies=authenticated)
    def detail(item_id: str, user_id: Annotated[Identity, Query()]):
        if len(item_id) > 256:
            raise HTTPException(422, "item_id too long")
        return game.detail(user_id, item_id)

    return app
