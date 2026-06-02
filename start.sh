#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE=${1:-dev}

activate_venv() {
  if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
    # Unix-style venv
    source "$ROOT_DIR/.venv/bin/activate"
  elif [ -f "$ROOT_DIR/.venv/Scripts/activate" ]; then
    # Windows Git Bash / MSYS-style venv
    source "$ROOT_DIR/.venv/Scripts/activate"
  else
    echo "No virtualenv found at .venv; backend will use system Python if available."
  fi
}

start_backend() {
  echo "[backend] Starting uvicorn on :8000... (logs -> backend.log)"
  # run in background and store pid
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > "$ROOT_DIR/backend.log" 2>&1 &
  echo $! > "$ROOT_DIR/.backend.pid"
  echo "[backend] PID $(cat $ROOT_DIR/.backend.pid)"
}

start_frontend_dev() {
  echo "[frontend] Starting Vite dev server..."
  cd "$ROOT_DIR/frontend"
  npm run dev
}

start_frontend_prod() {
  echo "[frontend] Serving built frontend (port 5173)..."
  cd "$ROOT_DIR/frontend"
  if [ ! -d dist ]; then
    echo "[frontend] Building frontend..."
    npm run build
  fi
  # use npx serve if available
  if command -v npx >/dev/null 2>&1; then
    npx serve -s dist -l 5173
  else
    echo "npx not found — using Python http.server as fallback (not SPA-friendly)"
    cd dist
    python -m http.server 5173
  fi
}

stop_backend() {
  if [ -f "$ROOT_DIR/.backend.pid" ]; then
    PID=$(cat "$ROOT_DIR/.backend.pid")
    echo "[backend] Stopping PID $PID"
    kill -TERM "$PID" || kill -9 "$PID" || true
    rm -f "$ROOT_DIR/.backend.pid"
    echo "[backend] stopped"
  else
    echo "[backend] no PID file found"
  fi
}

case "$MODE" in
  dev)
    activate_venv
    start_backend
    start_frontend_dev
    ;;
  prod)
    activate_venv
    start_backend
    start_frontend_prod
    ;;
  stop)
    stop_backend
    ;;
  *)
    echo "Usage: $0 {dev|prod|stop}"
    exit 1
    ;;
esac
