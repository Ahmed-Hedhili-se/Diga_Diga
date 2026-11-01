"""Point every test run at a throwaway DB before any test module imports app.config."""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="hg_test_"))
os.environ.setdefault("HG_DB_PATH", str(_tmp / "test.db"))
os.environ.setdefault("HG_UPLOAD_DIR", str(_tmp / "uploads"))

# scrypt at production cost takes a few hundred ms per hash; tests create many users, so they use a cheap cost.
# (tests that check the real cost set their own parameters)
from app.auth import core as _auth_core  # noqa: E402

_auth_core.SCRYPT_N, _auth_core.SCRYPT_P = 2**10, 1
