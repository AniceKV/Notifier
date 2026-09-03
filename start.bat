@echo off
TITLE Notifier Local Server Manager
echo ===================================================
echo       Starting Notifier Local Full-Stack Suite
echo ===================================================

:: 1. Stop any background Redis daemon in WSL to avoid port conflicts
echo Preparing Redis Server in WSL...
wsl -u root bash -c "systemctl stop redis-server 2>/dev/null; pkill -9 redis-server 2>/dev/null"

:: 2. Launch Windows Terminal with 4 tabs for Django, Redis, Celery Worker, and Celery Beat
echo Launching Windows Terminal with 4 service tabs...

wt.exe --title "Django Web Server" -d "%~dp0djangoproj" cmd /k "if exist ..\.venv\Scripts\activate.bat (call ..\.venv\Scripts\activate.bat) & python manage.py runserver" ^; ^
new-tab --title "Redis Server" cmd /k "wsl redis-server" ^; ^
new-tab --title "Celery Worker" -d "%~dp0djangoproj" cmd /k "if exist ..\.venv\Scripts\activate.bat (call ..\.venv\Scripts\activate.bat) & timeout /t 2 /nobreak >nul & celery -A djangoproj worker -l info --pool=solo" ^; ^
new-tab --title "Celery Beat" -d "%~dp0djangoproj" cmd /k "if exist ..\.venv\Scripts\activate.bat (call ..\.venv\Scripts\activate.bat) & timeout /t 2 /nobreak >nul & celery -A djangoproj beat -l info"

echo All services launched in a single Windows Terminal window!
