#!/usr/bin/env bash
# AeroRF — start script
#   ./start.sh [dev|prod|stop|test]

set -euo pipefail

MODE="${1:-dev}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo
echo " [AeroRF] Modo: $MODE"
echo

# ── Load .env ────────────────────────────────────────────────────────────────
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo " Configuración cargada desde .env"
else
  echo " No se encontró .env. Copie .env.example a .env (opcional para el mapa)."
fi

PORT="${PORT:-8000}"
VITE_PORT="${VITE_PORT:-5173}"
VITE_API_TARGET="${VITE_API_TARGET:-http://127.0.0.1:${PORT}}"

echo " Backend:  $VITE_API_TARGET"
echo " Frontend: http://localhost:${VITE_PORT}"
echo

# ── Virtualenv ───────────────────────────────────────────────────────────────
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo " AVISO: no se encontró .venv"
  echo "   python3 -m venv .venv"
  echo "   .venv/bin/pip install -r requirements.txt"
  echo
fi

case "$MODE" in
  stop)
    echo " Deteniendo AeroRF..."
    pkill -f "uvicorn app.main:app" || true
    ;;

  test)
    echo " Ejecutando pruebas..."
    python -m pytest tests app/rf_engine -q
    node tests/geo_parity.mjs
    ;;

  dev)
    echo " Iniciando backend (uvicorn)..."
    python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload \
      > "$ROOT/backend.log" 2>&1 &
    sleep 3
    echo " Iniciando frontend (Vite)..."
    cd frontend
    [ -d node_modules ] || npm install
    VITE_API_TARGET="$VITE_API_TARGET" VITE_PORT="$VITE_PORT" npm run dev
    ;;

  prod)
    echo " Iniciando backend (uvicorn, sin recarga)..."
    python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
      > "$ROOT/backend.log" 2>&1 &
    echo " Construyendo frontend..."
    cd frontend
    npm run build
    echo
    echo " Sirva dist/ con un servidor con fallback SPA, por ejemplo:"
    echo "   npx serve -s dist -l ${VITE_PORT}"
    ;;

  *)
    echo " Uso: ./start.sh [dev|prod|stop|test]"
    exit 1
    ;;
esac
