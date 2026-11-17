@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -CheckOnly %*
set "cardio_exit=%ERRORLEVEL%"
if not "%cardio_exit%"=="0" echo CardioResearch checks failed. See the error above.
pause
exit /b %cardio_exit%
