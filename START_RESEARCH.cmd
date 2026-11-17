@echo off
setlocal
cd /d "%~dp0CardioResearch_3.0"
call START.cmd -StartPage "#experiments" %*
exit /b %ERRORLEVEL%
