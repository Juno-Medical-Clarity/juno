"""Tests for utils/rate_limit.py — the trial route's per-IP Firestore counter."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from utils.rate_limit import get_client_ip, _hash_ip, check_rate_limit, rate_limit_trial
from utils.constants import Constants


# ---------------------------------------------------------------------------
# get_client_ip
# ---------------------------------------------------------------------------

def test_get_client_ip_uses_last_xff_value(app):
    with app.test_request_context(headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}):
        assert get_client_ip() == "5.6.7.8"


def test_get_client_ip_ignores_spoofed_first_value():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(headers={"X-Forwarded-For": "attacker-spoofed, 9.9.9.9"}):
        assert get_client_ip() == "9.9.9.9"


def test_get_client_ip_falls_back_to_remote_addr():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(environ_base={"REMOTE_ADDR": "10.0.0.1"}):
        assert get_client_ip() == "10.0.0.1"


# ---------------------------------------------------------------------------
# _hash_ip
# ---------------------------------------------------------------------------

def test_hash_ip_deterministic_same_ip_and_salt(monkeypatch):
    monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-a")
    assert _hash_ip("1.2.3.4") == _hash_ip("1.2.3.4")


def test_hash_ip_differs_across_ips(monkeypatch):
    monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-a")
    assert _hash_ip("1.2.3.4") != _hash_ip("5.6.7.8")


def test_hash_ip_differs_across_salts(monkeypatch):
    monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-a")
    h1 = _hash_ip("1.2.3.4")
    monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-b")
    h2 = _hash_ip("1.2.3.4")
    assert h1 != h2


# ---------------------------------------------------------------------------
# check_rate_limit — uses fake_firestore-style in-memory counter, not the
# emulator (no emulator is configured in this test suite's CI setup).
# ---------------------------------------------------------------------------

class _FakeSnapshot:
    def __init__(self, count):
        self._count = count
        self.exists = count is not None

    def get(self, field):
        return self._count if field == "count" else None


class _FakeRef:
    """Minimal Firestore doc-ref stand-in with an in-memory count."""
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self, transaction=None):
        return _FakeSnapshot(self._store.get(self._key))


class _FakeTransaction:
    """Minimal Firestore-transaction stand-in. Besides the in-memory `.set()`
    the real code path exercises, this also carries the small attribute/method
    surface the installed google-cloud-firestore's `@firestore.transactional`
    decorator's retry/commit protocol touches (`_read_only`, `_max_attempts`,
    `_clean_up`, `_begin`, `_commit`, `_rollback`, `_id`) so it can drive this
    fake as a single-attempt, always-succeeds transaction."""
    _read_only = False
    _max_attempts = 1

    def __init__(self):
        self._id = b"fake-transaction-id"

    def _clean_up(self):
        pass

    def _begin(self, retry_id=None):
        pass

    def _commit(self):
        return []

    def _rollback(self):
        pass

    def set(self, ref, data, merge=True):
        ref._store[ref._key] = data["count"]


@pytest.fixture
def fake_rate_limit_firestore(monkeypatch):
    """Patch firestore_client() so check_rate_limit() operates on an
    in-memory dict keyed by doc_id, simulating Firestore's transactional
    read-then-write without needing a real emulator."""
    store: dict[str, int] = {}

    def _fake_client():
        db = MagicMock()

        def _doc(doc_id):
            return _FakeRef(store, doc_id)

        db.collection.return_value.document.side_effect = _doc
        db.transaction.return_value = _FakeTransaction()
        return db

    monkeypatch.setattr("utils.rate_limit.firestore_client", _fake_client)
    return store


def test_check_rate_limit_allows_up_to_limit_and_blocks_the_next(fake_rate_limit_firestore, monkeypatch):
    monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt")
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(environ_base={"REMOTE_ADDR": "1.1.1.1"}):
        results = [check_rate_limit() for _ in range(Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR + 1)]
    assert results == [True] * Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR + [False]


def test_check_rate_limit_resets_in_next_hour_window(fake_rate_limit_firestore, monkeypatch):
    monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt")
    from flask import Flask
    app = Flask(__name__)

    with app.test_request_context(environ_base={"REMOTE_ADDR": "2.2.2.2"}):
        for _ in range(Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR):
            assert check_rate_limit() is True
        assert check_rate_limit() is False

    # Simulate the next hour-aligned window by freezing datetime.now().
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
            return base if tz is None else base.astimezone(tz)

    with patch("utils.rate_limit.datetime", _FrozenDatetime):
        with app.test_request_context(environ_base={"REMOTE_ADDR": "2.2.2.2"}):
            assert check_rate_limit() is True


# ---------------------------------------------------------------------------
# rate_limit_trial decorator
# ---------------------------------------------------------------------------

def test_rate_limit_trial_fails_open_on_exception(monkeypatch):
    monkeypatch.setattr("utils.rate_limit.check_rate_limit", MagicMock(side_effect=RuntimeError("firestore down")))

    @rate_limit_trial
    def _handler():
        return "ok", 200

    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context("/trial/jobs", method="POST"):
        body, status = _handler()
    assert status == 200
    assert body == "ok"


def test_rate_limit_trial_returns_429_when_blocked(monkeypatch):
    monkeypatch.setattr("utils.rate_limit.check_rate_limit", MagicMock(return_value=False))

    @rate_limit_trial
    def _handler():
        return "ok", 200

    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context("/trial/jobs", method="POST"):
        body, status = _handler()
    assert status == 429
