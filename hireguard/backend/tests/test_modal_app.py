"""Guards on the Modal deployment (T7.1), read from source: no modal install, no network, no deploy."""
import ast
import re

from app.config import ROOT

SRC = ROOT / "infra" / "modal_ollama.py"


def _decorator_kwargs(name: str) -> dict:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ollama")
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and getattr(d.func, "attr", None) == name:
            return {k.arg: ast.literal_eval(k.value) for k in d.keywords if isinstance(k.value, ast.Constant)}
    raise AssertionError(f"@{name} missing")


def test_endpoint_is_never_public():
    assert _decorator_kwargs("web_server")["requires_proxy_auth"] is True


def test_budget_guards():
    kw = _decorator_kwargs("function")
    assert kw["gpu"] == "L4"
    assert kw["max_containers"] == 1  # never more than one GPU billing at a time
    assert kw["scaledown_window"] <= 300  # scale to zero after 5 idle minutes
    assert kw["timeout"] <= 3600


def test_no_secrets_in_source():
    """Modal proxy tokens look like wk-xxxx / ws-xxxx: none may be committed."""
    text = SRC.read_text(encoding="utf-8")
    assert not re.search(r"\bw[ks]-[A-Za-z0-9]{8,}", text)
