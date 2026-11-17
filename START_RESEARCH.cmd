@echo off
setlocal
cd /d "%~dp0CardioResearch_3.0"
echo CardioResearch 3.0: http://127.0.0.1:8000/#experiments
echo Keep this window open. Stop with Ctrl+C.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn cardio.api:app --host 127.0.0.1 --port 8000 --no-access-log
) else if exist "%~dp0tmp\cardio-runtime\Scripts\python.exe" (
  "%~dp0tmp\cardio-runtime\Scripts\python.exe" -m uvicorn cardio.api:app --host 127.0.0.1 --port 8000 --no-access-log
) else (
  echo Run CardioResearch_3.0\setup.ps1 with Python 3.12 first.
)
pause
