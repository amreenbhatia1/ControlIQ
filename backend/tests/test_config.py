import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG_SECRET = "x" * 48


def test_production_rejects_placeholder_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production", secret_key="dev-only-change-me", cookie_secure=True)


def test_production_rejects_short_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production", secret_key="short-secret", cookie_secure=True)


def test_production_requires_secure_cookies():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(environment="production", secret_key=STRONG_SECRET, cookie_secure=False)


def test_production_accepts_hardened_settings():
    s = Settings(environment="production", secret_key=STRONG_SECRET, cookie_secure=True)
    assert s.environment == "production"


def test_development_allows_local_defaults():
    s = Settings(environment="development", secret_key="dev-only-change-me", cookie_secure=False)
    assert s.secret_key == "dev-only-change-me"
