"""Ollama + Qwen3-8B on one Modal L4 GPU, behind Modal proxy auth (P1, T7.1).

    modal deploy hireguard/infra/modal_ollama.py     # prints the https://...modal.run URL
    modal app stop hireguard-ollama                  # stop paying

FICTIONAL TEST DATA ONLY: Modal runs in the US. In production Ollama runs on-prem in Tunisia
(Law 2004-63: personal data does not leave the country without INPDP authorization).

The container is the same quarantined extractor as the local one: it reads text and returns typed JSON.
It has no tools, no database and no authority. Budget guards: one container at most, scaled to zero after
5 idle minutes, every request needs a proxy-auth token (Modal-Key / Modal-Secret headers).
"""
import json
import os
import subprocess
import time
import urllib.request

import modal

APP_NAME = "hireguard-ollama"
MODEL = "qwen3:8b"
PORT = 11434
OLLAMA_DIR = "/root/.ollama"  # the volume: the model is downloaded once and kept across cold starts

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "ca-certificates", "zstd")
    .run_commands("curl -fsSL https://ollama.com/install.sh | sh")
)
models = modal.Volume.from_name("hireguard-ollama-models", create_if_missing=True)
app = modal.App(APP_NAME, image=image)


def _api(path: str, body: dict | None = None, timeout: float = 10) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _wait_until_serving(seconds: int = 120):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            return _api("/api/tags")
        except OSError:
            time.sleep(1)
    raise RuntimeError("ollama serve did not start")


@app.function(gpu="L4", volumes={OLLAMA_DIR: models}, max_containers=1, scaledown_window=300, timeout=3600)
@modal.web_server(port=PORT, startup_timeout=600, requires_proxy_auth=True)
def ollama():
    env = os.environ | {"OLLAMA_HOST": f"0.0.0.0:{PORT}", "OLLAMA_MODELS": f"{OLLAMA_DIR}/models",
                        "OLLAMA_KEEP_ALIVE": "10m"}
    subprocess.Popen(["ollama", "serve"], env=env)
    tags = _wait_until_serving()
    if not any(m.get("name") == MODEL for m in tags.get("models", [])):
        _api("/api/pull", {"model": MODEL, "stream": False}, timeout=540)  # first deploy only (~5 GB)
        models.commit()
    _api("/api/generate", {"model": MODEL, "keep_alive": "10m"}, timeout=300)  # load weights into the GPU now
