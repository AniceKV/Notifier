#!/bin/bash

echo "==================================================="
echo "      Starting Notifier Local Full-Stack Suite"
echo "==================================================="

if ! command -v xfce4-terminal &>/dev/null; then
    echo "ERROR: xfce4-terminal is not installed."
    exit 1
fi

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$BASE_DIR/djangoproj"
VENV="$BASE_DIR/.venv"

echo "Preparing Redis Server..."

sudo systemctl stop redis-server 2>/dev/null
sudo pkill -9 redis-server 2>/dev/null

echo "Launching terminal with 4 service tabs..."

xfce4-terminal \
    --tab --title="Django Web Server" \
    --command="bash -c 'cd \"$PROJECT_DIR\" && source \"$VENV/bin/activate\" && python manage.py runserver; exec bash'" \
    --tab --title="Redis Server" \
    --command="bash -c 'redis-server; exec bash'" \
    --tab --title="Celery Worker" \
    --command="bash -c 'cd \"$PROJECT_DIR\" && source \"$VENV/bin/activate\" && sleep 2 && celery -A djangoproj worker -l info --pool=solo; exec bash'" \
    --tab --title="Celery Beat" \
    --command="bash -c 'cd \"$PROJECT_DIR\" && source \"$VENV/bin/activate\" && sleep 2 && celery -A djangoproj beat -l info; exec bash'"

if [ $? -eq 0 ]; then
    echo "All services launched successfully!"
else
    echo "ERROR: Failed to launch XFCE Terminal."
    exit 1
fi