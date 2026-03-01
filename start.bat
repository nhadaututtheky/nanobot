@echo off
title NanoBot Launcher
cd /d D:\Project\NanoBot
echo.
echo  NanoBot Launcher
echo  ================
echo.

echo [1] Starting NanoBot with PM2...
call pm2 start nanobot 2>nul || call pm2 start "python -m nanobot" --name nanobot --cwd "D:\Project\NanoBot" --interpreter none 2>nul
echo.

echo [2] Starting Dashboard on port 5174...
cd /d D:\Project\NanoBot\dashboard
start "Dashboard" /min cmd /c "npm run dev 2>&1"
cd /d D:\Project\NanoBot
echo.

echo [3] Waiting 4 seconds...
timeout /t 4 /nobreak >nul
echo.

call pm2 status nanobot 2>nul
echo.
echo  -----------------------------------
echo   NanoBot:   ws://localhost:18790
echo   Dashboard: http://localhost:5174
echo  -----------------------------------
echo.

start http://localhost:5174

echo Press any key to exit...
pause >nul
