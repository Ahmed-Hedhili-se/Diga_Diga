"""The eval scripts are not imported by the app, so a syntax error there would reach a commit unnoticed."""
import py_compile

import pytest

from app.config import ROOT


@pytest.mark.parametrize("script", sorted((ROOT / "eval").glob("*.py")), ids=lambda p: p.name)
def test_eval_script_compiles(script):
    py_compile.compile(str(script), doraise=True)
