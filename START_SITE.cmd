@echo off
setlocal
cd /d "%~dp0CardioResearch_3.0\deployment\cardio-site"
if defined CARDIO_NODE (set "cardio_node=%CARDIO_NODE%") else (set "cardio_node=node")
"%cardio_node%" -e "if(Number(process.versions.node.split('.')[0])<20)process.exit(1)" >nul 2>&1
if errorlevel 1 (
  echo Node.js 20 or newer is required. Install it or set CARDIO_NODE to node.exe.
  pause
  exit /b 1
)
if not exist "dist\server\index.js" (
  echo Build the web demo first: npm ci, npm --prefix client ci, npm run build.
  pause
  exit /b 1
)
"%cardio_node%" scripts/preview.mjs
set "cardio_exit=%ERRORLEVEL%"
if not "%cardio_exit%"=="0" echo Preview failed. Check the error above and whether port 8787 is in use.
pause
exit /b %cardio_exit%
