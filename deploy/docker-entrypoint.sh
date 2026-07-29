#!/bin/sh
set -eu

: "${SECRET_KEY:?La variable SECRET_KEY est obligatoire}"
: "${GM_PASSWORD_HASH:?La variable GM_PASSWORD_HASH est obligatoire}"

flask --app app init-db

exec gunicorn \
    --workers 1 \
    --threads "${GUNICORN_THREADS:-4}" \
    --bind "0.0.0.0:${PORT:-8000}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile - \
    "app:create_app()"
