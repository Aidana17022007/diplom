$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Сначала запустите setup.ps1' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Сначала соберите интерфейс: cd frontend; npm.cmd install; npm.cmd run build' }
Write-Host 'CardioResearch: http://127.0.0.1:8000'
& $projectPython -m uvicorn cardio.api:app --host 127.0.0.1 --port 8000 --no-access-log
