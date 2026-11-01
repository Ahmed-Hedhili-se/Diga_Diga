# Records the backup demo video on a throwaway database. Usage: .\demo_video\record.ps1 [-Offline] [-Headed] [-Pace 1]
#   Fresh DB and uploads in demo_video\work\, seed (passwords captured, never printed), backend on 127.0.0.1:8010,
#   Vite on 127.0.0.1:5180 (so a running .\run.ps1 on 8000/5173 is untouched), then record.mjs, then both stop.
#   The model: .env and .env.modal are read like run.ps1 does (Modal keys reach the backend only). With
#   HG_LLM_PROVIDER=gemini in .env the seeded CVs go through Gemini instead. -Offline records the backup path
#   (ground-truth extraction, every candidate badged "offline extraction").
#   Output: demo_video\out\hireguard_demo.webm (not committed) and demo_video\out\report.md (commit this one).
param([switch]$Offline, [switch]$Headed, [double]$Pace = 1)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = Split-Path $here -Parent
$py = "$root\backend\.venv\Scripts\python.exe"
$work = "$here\work"

if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Force "$work\uploads", "$here\out" | Out-Null

foreach ($f in @("$root\.env") + $(if ($Offline) { @() } else { @("$root\.env.modal") })) {
    if (Test-Path $f) {
        Get-Content $f | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
            $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim()
        }
        Write-Host "Loaded $(Split-Path $f -Leaf)"
    }
}
$env:HG_DB_PATH = "$work\demo.db"
$env:HG_UPLOAD_DIR = "$work\uploads"
if ($Offline) {
    $env:HG_EXTRACT_MODE = "ground_truth"
    $env:HG_LLM_PROVIDER = "ollama"
    $env:HG_OLLAMA_HOSTS = "http://127.0.0.1:9"   # nothing listens: every CV falls back to ground truth at once
}

Write-Host "Seeding a fresh database (with the model this takes a few minutes)..."
Push-Location "$root\backend"
$ErrorActionPreference = "Continue"   # PowerShell 5.1 turns the seed's stderr lines into errors under "Stop"
$seed = & $py -m app.seed 2>&1 | ForEach-Object { "$_" }
$seedCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Pop-Location
if ($seedCode) { $seed | ForEach-Object { Write-Host $_ }; throw "Seed failed (exit $seedCode)" }
$passwords = @{}
foreach ($line in $seed) {
    if ($line -match '^\s+\S+\s+(\S+@hireguard\.demo)\s+(\S+)\s*$') { $passwords[$Matches[1]] = $Matches[2] }
    elseif ($line -notmatch '@hireguard\.demo') { Write-Host $line }
}
if ($passwords.Count -lt 3) { throw "Seed did not print the demo passwords (is demo_video\work\demo.db fresh?)" }
$passwords | ConvertTo-Json | Set-Content -Encoding utf8 "$work\passwords.json"

$procs = @()
try {
    $procs += Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory "$root\backend" $py `
        "-m uvicorn app.main:app --host 127.0.0.1 --port 8010" `
        -RedirectStandardOutput "$work\backend.log" -RedirectStandardError "$work\backend.err.log"
    foreach ($k in "HG_OLLAMA_MODAL_KEY", "HG_OLLAMA_MODAL_SECRET", "GEMINI_API_KEY", "GROQ_API_KEY") {
        Remove-Item "env:$k" -ErrorAction SilentlyContinue   # Vite and the browser never get model credentials
    }
    $env:VITE_BACKEND_URL = "http://127.0.0.1:8010"
    $env:HG_VITE_HOST = "127.0.0.1"
    $procs += Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory "$root\frontend" "cmd.exe" `
        "/c npx vite --port 5180 --strictPort --host 127.0.0.1" `
        -RedirectStandardOutput "$work\vite.log" -RedirectStandardError "$work\vite.err.log"

    $up = $false
    foreach ($i in 1..60) {
        try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:5180/api/health" -TimeoutSec 2 | Out-Null; $up = $true; break }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $up) { throw "App did not come up on :5180; see demo_video\work\backend.err.log and vite.err.log" }

    Push-Location $here
    if (-not (Test-Path "node_modules\playwright")) { npm install --no-audit --no-fund }
    $env:HG_DEMO_URL = "http://127.0.0.1:5180"
    $env:HG_DEMO_PASSWORDS = "$work\passwords.json"
    $env:HG_DEMO_PACE = "$Pace"
    $env:HG_DEMO_HEADED = $(if ($Headed) { "1" } else { "0" })
    node record.mjs
    $code = $LASTEXITCODE
    Pop-Location
} finally {
    foreach ($p in $procs) { if ($p -and -not $p.HasExited) { taskkill /T /F /PID $p.Id | Out-Null } }
}
Write-Host "Video: demo_video\out\hireguard_demo.webm   Report: demo_video\out\report.md"
exit $code
