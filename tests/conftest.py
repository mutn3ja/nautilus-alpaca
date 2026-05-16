"""
Pytest configuration and shared fixtures.

Python 3.13 added ssl.VERIFY_X509_STRICT to the default SSL context, which
rejects CA certificates missing the keyUsage extension.  Alpaca's intermediate
CA triggers this check.

urllib3 explicitly ORs in VERIFY_X509_STRICT for Python 3.13+ inside
create_urllib3_context(), and connection.py imports that function by name at
module load time.  We must patch every live binding, not just the source module,
to ensure the flag is cleared before any HTTPS handshake.
"""
import ssl
import urllib3.util.ssl_ as _urllib3_ssl_mod
import urllib3.util as _urllib3_util
import urllib3.connection as _urllib3_conn

_orig = _urllib3_ssl_mod.create_urllib3_context


def _patched(*args, **kwargs):
    ctx = _orig(*args, **kwargs)
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


# Patch every binding that was created via `from .util.ssl_ import ...`
_urllib3_ssl_mod.create_urllib3_context = _patched
_urllib3_util.create_urllib3_context = _patched
_urllib3_conn.create_urllib3_context = _patched
