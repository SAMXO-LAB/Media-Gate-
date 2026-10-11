import pytest

from app.core import crypto
from app.core.errors import AppError, Gone
from app.core.logging import redact


def test_sign_verify_roundtrip():
    t = crypto.sign({"k": "v"}, 60)
    assert crypto.verify(t)["k"] == "v"


def test_expired_link():
    t = crypto.sign({"k": "v"}, 60, now=1000)
    with pytest.raises(Gone):
        crypto.verify(t, now=2000)


def test_tampered_link():
    t = crypto.sign({"k": "v"}, 60)
    raw, sig = t.split(".")
    with pytest.raises(AppError):
        crypto.verify(raw + "x." + sig)
    with pytest.raises(AppError):
        crypto.verify("garbage")


def test_token_encryption_roundtrip():
    enc = crypto.encrypt("secret-token")
    assert "secret-token" not in enc
    assert crypto.decrypt(enc) == "secret-token"


@pytest.mark.parametrize("raw,leak", [
    ("GET https://api.x.com/?access_token=abc123&x=1", "abc123"),
    ("Authorization: Bearer eyJhbGciOi.secret.sig", "eyJhbGciOi"),
    ('{"access_token": "zzz999"}', "zzz999"),
    ("youtube key=AIzaSyFAKE", "AIzaSyFAKE"),
])
def test_log_redaction(raw, leak):
    assert leak not in redact(raw)


def test_cors_origins_comma_separated(monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]
