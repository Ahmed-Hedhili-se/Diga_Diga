# HireGuard dev run script (Windows). Usage: .\run.ps1 [-Setup] [-Seed] [-Test] [-LocalOnly]
#   -Test: backend tests (throwaway DB) + frontend type check and build, then exit. Nothing is started.
#   Default: backend on 0.0.0.0:8000 and Vite on 0.0.0.0:5173 so a teammate on the same network can open
#   http://<this-ip>:5173 (docs/lan_setup.md). -LocalOnly binds both to 127.0.0.1.
#   .env.modal (HG_OLLAMA_HOSTS, HG_OLLAMA_MODAL_KEY, HG_OLLAMA_MODAL_SECRET) is given to the backend process
#   only: the browser never sees the Modal URL or credentials, it talks to /api through the Vite proxy.
param([switch]$Setup, [switch]$Seed, [switch]$Test, [switch]$LocalOnly)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if ($Setup) {
    python -m venv "$root\backend\.venv"
    & "$root\backend\.venv\Scripts\python.exe" -m pip install -r "$root\backend\requirements.txt"
    Push-Location "$root\frontend"; npm install; Pop-Location
}

if (Test-Path "$root\.env") {
    Get-Content "$root\.env" | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
        $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim()
    }
}

$py = "$root\backend\.venv\Scripts\python.exe"
if ($Test) {
    Push-Location "$root\backend"; & $py -m pytest -q; $backend = $LASTEXITCODE; Pop-Location
    Push-Location "$root\frontend"; npx tsc --noEmit; $types = $LASTEXITCODE; npx vite build; $build = $LASTEXITCODE; Pop-Location
    $status = { param($code) if ($code) { "FAIL" } else { "ok" } }
    Write-Host "backend tests: $(& $status $backend) | types: $(& $status $types) | build: $(& $status $build)"
    exit ($backend -bor $types -bor $build)
}
if ($Seed) { Push-Location "$root\backend"; & $py -m app.seed; Pop-Location }

$bind = if ($LocalOnly) { "127.0.0.1" } else { "0.0.0.0" }

# Backend-only secrets: set for the uvicorn child process, then removed before Vite starts.
$modalKeys = @()
if (Test-Path "$root\.env.modal") {
    Get-Content "$root\.env.modal" | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
        $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim(); $modalKeys += $k.Trim()
    }
    Write-Host "Loaded .env.modal for the backend only ($($modalKeys -join ', '))"
}
Start-Process -NoNewWindow -WorkingDirectory "$root\backend" $py "-m uvicorn app.main:app --host $bind --port 8000 --reload"
foreach ($k in $modalKeys) { Remove-Item "env:$k" -ErrorAction SilentlyContinue }

if (-not $LocalOnly) {
    # The adapter with a default gateway is the real network; WSL/Hyper-V virtual adapters have none.
    $ip = Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.IPv4DefaultGateway } |
        ForEach-Object { $_.IPv4Address.IPAddress } | Select-Object -First 1
    if ($ip) {
        Write-Host "Share with teammates: http://${ip}:5173   (API health: http://${ip}:8000/api/health)"
        Write-Host "If they cannot connect, allow TCP 5173 and 8000 in Windows Firewall (docs/lan_setup.md)."
    }
}
$env:HG_VITE_HOST = $bind
Push-Location "$root\frontend"; npm run dev; Pop-Location
