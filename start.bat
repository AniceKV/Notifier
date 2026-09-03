@echo off
TITLE Notifier Local Server Manager
echo ===================================================
echo       Starting Notifier Local Full-Stack Suite
echo ===================================================

:: Ensure Redis is running in WSL as root (prevents sudo password hang)
echo [1/4] Starting Redis Server in WSL...
wsl -u root service redis-server start >nul 2>&1

cd /d "%~dp0djangoproj"

:: Check if virtualenv exists and activate if present
if exist "..\.venv\Scripts\activate.bat" (
    call "..\.venv\Scripts\activate.bat"
)

:: 2. Start Celery Worker in a new window
echo [2/4] Starting Celery Worker...
start "Notifier Celery Worker" cmd /k "cd /d "%~dp0djangoproj" && if exist "..\.venv\Scripts\activate.bat" call "..\.venv\Scripts\activate.bat" && celery -A djangoproj worker -l info --pool=solo"

:: 3. Start Celery Beat Scheduler in a new window
echo [3/4] Starting Celery Beat Scheduler...
start "Notifier Celery Beat" cmd /k "cd /d "%~dp0djangoproj" && if exist "..\.venv\Scripts\activate.bat" call "..\.venv\Scripts\activate.bat" && celery -A djangoproj beat -l info"

:: 4. Start Django Development Server
echo [4/4] Starting Django Web Server on http://127.0.0.1:8000 ...
python manage.py runserver
