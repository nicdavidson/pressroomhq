#!/bin/bash
# Start Pressroom — backend + frontend dev servers
set -e

cd "$(dirname "$0")"

echo "═══════════════════════════════════════"
echo "  PRESSROOM HQ — Starting up..."
echo "═══════════════════════════════════════"

# Backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Frontend
cd frontend
npm run dev &
FRONTEND_PID=$!

cd ..

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "  The wire is open. Stories are waiting."
echo "═══════════════════════════════════════"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
