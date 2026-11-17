@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run setup.ps1 to install the recorded Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "deployment\cardio-site\scripts\verify-research.py" --project-root . --source-dir "data\source-cache" --download
set "verificationExitCode=%ERRORLEVEL%"
pause
exit /b %verificationExitCode%
