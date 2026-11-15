@echo off
chcp 65001 > nul
title Avito PC Builder & Sniper
cd /d "%~dp0"

echo ========================================================
echo    🎯 ЗАПУСК AVITO PC BUILDER & SNIPER
echo ========================================================
echo.
echo Открытие веб-интерфейса в браузере...
start http://127.0.0.1:8000

echo.
echo Сервер слушает на:
echo   - http://127.0.0.1:8000
echo   - http://localhost:8000
echo.
echo ВНИМАНИЕ: Не закрывайте это окно, пока пользуетесь сайтом!
echo (Для остановки нажмите Ctrl+C или закройте окно)
echo.

python web_app.py

pause
