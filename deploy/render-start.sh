#!/usr/bin/env bash
set -euo pipefail

# Run AI worker in background so queue processing works on free single-service deploy.
python manage.py run_worker &

# Start Django web process in foreground.
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 180
