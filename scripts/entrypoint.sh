#!/bin/sh
set -eu
alembic upgrade head
exec uvicorn ponkan.main:app --host 0.0.0.0 --port "${PONKAN_PORT:-8080}" --proxy-headers --forwarded-allow-ips="${PONKAN_FORWARDED_ALLOW_IPS:-127.0.0.1}"
