param(
    [string]$PythonPath,
    [ValidateRange(1024,65535)][int]$Port = 8000,
    [switch]$NoBrowser,
    [switch]$CheckOnly,
    [string]$StartPage = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')
$projectPython = Resolve-CardioPython $PythonPath
Write-Host 'Checking the runtime, saved models and interface before startup...'
& $projectPython -X utf8 scripts/verify_runtime.py
if ($LASTEXITCODE -ne 0) { throw 'Runtime check failed. The server was not started.' }
if ($CheckOnly) { return }
$origin = "http://127.0.0.1:$Port"
$url = $origin + '/' + $StartPage.TrimStart('/')
$probe = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
try { $probe.Start() } catch {
    throw "Port $Port is already in use. Close the other server or run .\run.ps1 -Port 8001."
} finally { $probe.Stop() }
$logDir = Join-Path $PSScriptRoot 'reports'
$stdout = Join-Path $logDir "local_${Port}_stdout.log"
$stderr = Join-Path $logDir "local_${Port}_stderr.log"
$server = $null
try {
    $server = Start-Process -FilePath $projectPython -ArgumentList @('-X','utf8','-m','uvicorn','cardio.api:app','--host','127.0.0.1','--port',"$Port",'--no-access-log') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $server.Refresh()
        if ($server.HasExited) { break }
        try {
            $health = Invoke-RestMethod "$origin/api/health" -TimeoutSec 1
            if ($health.status -eq 'ok' -and $health.models.brfss -and $health.models.uci) { $ready = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "Server startup failed. See $stderr" }
    & $projectPython -X utf8 scripts/verify_runtime.py --url $origin --server-only
    if ($LASTEXITCODE -ne 0) { throw 'The running server failed its prediction/interface check.' }
    Write-Host "CardioResearch: $url"
    Write-Host 'Keep this window open. Stop with Ctrl+C.'
    Write-Host "Server log: $stderr"
    if (-not $NoBrowser) { Start-Process $url }
    # WaitForExit() blocks PowerShell's Ctrl+C handling. Polling lets finally
    # stop this child server when the user interrupts the launcher.
    while (-not $server.HasExited) {
        Start-Sleep -Milliseconds 500
        $server.Refresh()
    }
    if ($server.ExitCode -ne 0) { throw "Server exited with code $($server.ExitCode). See $stderr" }
} catch {
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 25 | Write-Host }
    throw
} finally {
    if ($server) {
        $server.Refresh()
        if (-not $server.HasExited) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
    }
}
