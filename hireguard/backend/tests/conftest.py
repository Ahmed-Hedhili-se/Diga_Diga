"""Point every test run at a throwaway DB before any test module imports app.config."""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="hg_test_"))
os.environ.setdefault("HG_DB_PATH", str(_tmp / "test.db"))
os.environ.setdefault("HG_UPLOAD_DIR", str(_tmp / "uploads"))
