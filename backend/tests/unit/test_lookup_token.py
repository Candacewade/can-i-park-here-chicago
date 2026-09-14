"""Signed, stateless "find my watches" lookup tokens."""

from __future__ import annotations

from app.monitor import lookup_token as lt


def test_round_trip_returns_normalized_email():
    token = lt.create_lookup_token("  Driver@Example.COM  ")
    assert lt.verify_lookup_token(token) == "driver@example.com"


def test_tampered_signature_rejected():
    token = lt.create_lookup_token("driver@example.com")
    body, sig = token.split(".", 1)
    bad_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert lt.verify_lookup_token(f"{body}.{bad_sig}") is None


def test_tampered_payload_rejected():
    token = lt.create_lookup_token("driver@example.com")
    _, sig = token.split(".", 1)
    other = lt.create_lookup_token("someone-else@example.com")
    other_body, _ = other.split(".", 1)
    assert lt.verify_lookup_token(f"{other_body}.{sig}") is None


def test_malformed_token_rejected():
    assert lt.verify_lookup_token("not-a-real-token") is None
    assert lt.verify_lookup_token("") is None


def test_expired_token_rejected(monkeypatch):
    token = lt.create_lookup_token("driver@example.com")
    monkeypatch.setattr(lt.time, "time", lambda: 10**12)  # far future
    assert lt.verify_lookup_token(token) is None


def test_not_yet_expired(monkeypatch):
    real_time = lt.time.time()
    token = lt.create_lookup_token("driver@example.com")
    monkeypatch.setattr(lt.time, "time", lambda: real_time + 60)  # 1 min later, still valid
    assert lt.verify_lookup_token(token) == "driver@example.com"
