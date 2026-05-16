import pytest
from nautilus_alpaca.common.credentials import get_api_key, get_api_secret


def test_get_api_key_explicit():
    assert get_api_key(explicit="my_key") == "my_key"


def test_get_api_secret_explicit():
    assert get_api_secret(explicit="my_secret") == "my_secret"


def test_get_api_key_from_paper_env(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "paper_key")
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    assert get_api_key(paper=True) == "paper_key"


def test_get_api_key_fallback_to_generic(monkeypatch):
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.setenv("ALPACA_API_KEY", "generic_key")
    assert get_api_key(paper=True) == "generic_key"


def test_get_api_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="API key not found"):
        get_api_key(paper=True)


def test_get_api_secret_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ALPACA_PAPER_API_SECRET", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="API secret not found"):
        get_api_secret(paper=True)
