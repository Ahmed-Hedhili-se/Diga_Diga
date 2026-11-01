# LAN development setup (frontend on one machine, backend + GPU model on another)

```
browser (any machine)  ──http──▶  Vite :5173  ──/api proxy──▶  FastAPI :8000  ──Modal-Key/Secret──▶  Modal Ollama (qwen3:8b)
                                   (frontend)                   (backend machine)                     (GPU, cloud)
```

The browser never calls the Modal URL. It answers `401 missing credentials for proxy authorization`
to anything without the Modal proxy-auth headers, and those credentials live only in the backend's
`.env.modal`. All model traffic goes through the backend, which also sanitizes CVs and validates the
model's output before anything is scored.

## Backend machine (runs the backend and serves the frontend to teammates)

1. `copy .env.modal.example .env.modal` in `hireguard/` and fill `HG_OLLAMA_MODAL_KEY` and
   `HG_OLLAMA_MODAL_SECRET` (Modal dashboard → Settings → Proxy Auth Tokens). The file is git-ignored.
2. From `hireguard/`: `.\run.ps1` (add `-Setup` the first time, `-Seed` for demo data).
   It binds the backend to `0.0.0.0:8000` and Vite to `0.0.0.0:5173`, loads `.env.modal` into the
   backend process only, and prints the URL to share, e.g. `http://192.168.80.79:5173`.
   `.\run.ps1 -LocalOnly` binds both to `127.0.0.1` instead.
3. Check: `http://<backend-ip>:8000/api/health` → `{"ok": true}`. The Security Center shows whether the
   model is reachable.
4. If teammates cannot connect, run PowerShell as Administrator once:

```powershell
New-NetFirewallRule -DisplayName "HireGuard Frontend 5173" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "HireGuard Backend 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

## Frontend developer

- Just using the app: open `http://<backend-ip>:5173`. Both machines must be on the same network.
- Developing the frontend on your own machine against the shared backend:

```powershell
cd hireguard\frontend
$env:VITE_BACKEND_URL = "http://<backend-ip>:8000"; npm run dev
```

  then open `http://localhost:5173`. Vite proxies `/api` to the backend, so the session cookie stays
  same-origin. Do not put the Modal URL or credentials in any frontend file or `VITE_*` variable:
  `VITE_*` values are bundled into the JavaScript every visitor downloads.
