#!/bin/bash
set -e

echo "⏳ Waiting for database to be reachable..."
for i in $(seq 1 30); do
    if python -c "
import socket, sys
try:
    s = socket.create_connection(('db', 5432), timeout=2)
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "✅ Database is reachable"
        break
    fi
    echo "  attempt $i/30 — retrying in 2s..."
    sleep 2
done

echo "⏳ Running migrations..."
alembic upgrade head
echo "✅ Migrations done"

echo "🚀 Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
