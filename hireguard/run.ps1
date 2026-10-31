# HireGuard dev run script (Windows). Usage: .\run.ps1 [-Setup] [-Seed]
param([switch]$Setup, [switch]$Seed)
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
if ($Seed) { Push-Location "$root\backend"; & $py -m app.seed; Pop-Location }

Start-Process -NoNewWindow -WorkingDirectory "$root\backend" $py "-m uvicorn app.main:app --port 8000 --reload"
Push-Location "$root\frontend"; npm run dev; Pop-Location
