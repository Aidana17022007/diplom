@echo off
cd /d "%~dp0CardioResearch_3.0\deployment\cardio-site"
if not exist "dist\server\index.js" (
  echo Build the web demo first: npm ci, npm --prefix client ci, npm run build.
  pause
  exit /b 1
)
node scripts/preview.mjs
pause
