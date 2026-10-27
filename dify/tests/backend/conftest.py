import httpx
import pytest

from helpers import PowerContextHTTP


@pytest.fixture
def game(tmp_path):
    from pawnshop.app import create_app
    wire = PowerContextHTTP()
    db = tmp_path / "ledger.sqlite3"
    app = create_app(db_path=str(db), api_key="test-secret", powercontext_url="http://pc",
                     powercontext_token="pc-test", transport=httpx.MockTransport(wire),
                     session_secret="browser-test")
    from fastapi.testclient import TestClient
    with TestClient(app, headers={"X-Pawnshop-Key": "test-secret"}) as client:
        yield client, wire, db