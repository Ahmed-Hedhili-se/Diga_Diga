# HireGuard dev run script (Windows). Usage: .\run.ps1 [-Setup] [-Seed] [-Test]
#   -Test: backend tests (throwaway DB) + frontend type check and build, then exit. Nothing is started.
param([switch]$Setup, [switch]$Seed, [switch]$Test)
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

Start-Process -NoNewWindow -WorkingDirectory "$root\backend" $py "-m uvicorn app.main:app --port 8000 --reload"
Push-Location "$root\frontend"; npm run dev; Pop-Location
