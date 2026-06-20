import sys
from pathlib import Path
import json
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for p in (PROJECT_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from flask import Flask
from routes import all_blueprints


@pytest.fixture
def app():
    app = Flask(__name__)
    for bp in all_blueprints:
        app.register_blueprint(bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_ok(monkeypatch):
    """Bypass Firebase auth: any Bearer token resolves to a fixed uid."""
    monkeypatch.setattr("utils.firebase.auth.verify_id_token", lambda *a, **k: {"uid": "user-1"})
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def fake_firestore(monkeypatch):
    """Patch firestore.client() to a MagicMock; return it for per-test wiring."""
    from unittest.mock import MagicMock
    db = MagicMock()
    monkeypatch.setattr("firebase_admin.firestore.client", lambda *a, **k: db)
    return db


def parse_sse(response):
    """Split an SSE response body into a list of parsed JSON event payloads."""
    text = response.get_data(as_text=True) if hasattr(response, "get_data") else response
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("data: "):
            events.append(json.loads(block.removeprefix("data: ")))
    return events
