param([string]$PythonPath, [switch]$NoBrowser)
# Use the same checked startup path as START.cmd; keep its window for Ctrl+C.
& (Join-Path $PSScriptRoot 'run.ps1') -PythonPath $PythonPath -Port 8003 -NoBrowser:$NoBrowser
