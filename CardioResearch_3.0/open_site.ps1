$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'First run setup.ps1 with Python 3.12.' }
$url = 'http://127.0.0.1:8003'
$ready = $false
try {
    $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
    $ready = $health.status -eq 'ok' -and $health.models.brfss -and $health.models.uci
} catch {}
if (-not $ready) {
    Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','cardio.api:app','--host','127.0.0.1','--port','8003','--no-access-log') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput 'reports/local_3_0_stdout.log' -RedirectStandardError 'reports/local_3_0_stderr.log'
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
            $ready = $health.status -eq 'ok' -and $health.models.brfss -and $health.models.uci
            if ($ready) { break }
        } catch {}
    }
}
if (-not $ready) { throw 'Site startup failed. See reports/local_3_0_stderr.log.' }
Start-Process $url
