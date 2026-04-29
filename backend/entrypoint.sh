#!/bin/bash
set -e

# Run database migrations
cd /app
alembic -c backend/alembic.ini upgrade head

# Start the application
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
