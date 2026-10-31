# Real model on Modal (Ollama + Qwen3-8B)

The extractor normally runs on a laptop GPU. For a full evaluation we rent one L4 GPU on Modal. You run every command below yourself; nothing in the repo deploys or calls Modal on its own.

**Fictional test data only.** Modal runs in the US. In production, Ollama runs on-prem in Tunisia (Law 2004-63: personal data doesn't leave the country without INPDP authorization).

## Budget

| Fact | Value |
|---|---|
| L4 GPU (24 GB) | $0.000222/s, about **$0.80/hour**, billed per second, $0 when scaled to zero ([modal.com/pricing](https://modal.com/pricing)) |
| Model | Qwen3-8B, 4-bit, about 5 GB: fits easily |
| Our credit | $10 ≈ 12 GPU-hours |
| One full eval (50 CVs + 40 attacks + 40 twins + 100 emails) | well under 1 hour ≈ $1 |
| Guards | `max_containers=1`, scale to zero after 5 idle minutes, proxy auth required, `--max-requests` cap in the runner |

## Commands (Windows PowerShell, from the repo root)

```powershell
pip install modal
modal setup                                    # browser login, once
modal deploy hireguard/infra/modal_ollama.py   # prints the URL (https://...modal.run)

# Modal dashboard > Settings > Proxy Auth Tokens > New token: copy the key and the secret
$env:HG_OLLAMA_HOSTS="https://<your-url>.modal.run"
$env:HG_OLLAMA_MODAL_KEY="wk-..."
$env:HG_OLLAMA_MODAL_SECRET="ws-..."
$env:HG_EXTRACT_MODE="model"
$env:HG_LLM_TIMEOUT="300"                      # the first call waits for the cold start

cd hireguard/backend
.\.venv\Scripts\python.exe scripts/run_model_eval.py --cvs --limit 3                          # smoke test
.\.venv\Scripts\python.exe scripts/run_model_eval.py --cvs --attacks --emails --max-requests 400

modal app stop hireguard-ollama                # when finished: stop paying
```

1. **After the smoke test**, open the Modal dashboard and check the spend. The first deploy also downloads the model once (about 5 GB) into the `hireguard-ollama-models` volume.
2. **Set a workspace budget** in the Modal dashboard (Settings > Usage and billing) so a forgotten container can't spend more than the credit.
3. **Never put the key or the secret in a file that git tracks.** They live only in environment variables (or in `.env`, which is git-ignored). The client never logs them.

## What the endpoint is

`modal_ollama.py` runs `ollama serve` on port 11434 inside an L4 container and exposes it as a Modal web server with `requires_proxy_auth=True`. A request without valid `Modal-Key` / `Modal-Secret` headers is refused by Modal before it reaches Ollama. It is the same quarantined extractor as the local one: it reads text and returns typed JSON, with no tools, no database and no authority.
