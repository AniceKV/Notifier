import sys
from pathlib import Path

# Ensure project root is in sys.path
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ('celery_app',)