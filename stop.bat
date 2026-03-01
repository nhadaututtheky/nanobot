@echo off
title NanoBot Stop
echo Stopping NanoBot...
pm2 stop nanobot 2>nul
pm2 delete nanobot 2>nul
echo       OK

echo Stopping Dashboard...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5174" ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
echo       OK

echo.
echo All stopped.
echo.
pause
