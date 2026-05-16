import os


def get_api_key(explicit: str | None = None, paper: bool = True) -> str:
    if explicit:
        return explicit
    if paper:
        key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    else:
        key = os.environ.get("ALPACA_API_KEY")
    if not key:
        env_var = "ALPACA_PAPER_API_KEY or ALPACA_API_KEY" if paper else "ALPACA_API_KEY"
        raise RuntimeError(f"Alpaca API key not found. Set {env_var} environment variable.")
    return key


def get_api_secret(explicit: str | None = None, paper: bool = True) -> str:
    if explicit:
        return explicit
    if paper:
        secret = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_API_SECRET")
    else:
        secret = os.environ.get("ALPACA_API_SECRET")
    if not secret:
        env_var = "ALPACA_PAPER_API_SECRET or ALPACA_API_SECRET" if paper else "ALPACA_API_SECRET"
        raise RuntimeError(f"Alpaca API secret not found. Set {env_var} environment variable.")
    return secret
