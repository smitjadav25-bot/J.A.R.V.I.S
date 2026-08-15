#!/bin/zsh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/Backend"
BRIDGE_DIR="$ROOT_DIR/whatsapp-bridge"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="/tmp/jarvis"
PIDFILE="$LOG_DIR/pids"

mkdir -p "$LOG_DIR"

PY="python3"
if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  PY="$BACKEND_DIR/.venv/bin/python"
fi

# ── Backend ──────────────────────────────────────────────────────────
if ! pgrep -f "uvicorn main:app" >/dev/null 2>&1; then
  cd "$BACKEND_DIR"
  nohup "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000 \
    >"$LOG_DIR/backend.log" 2>&1 &
  echo $! >>"$PIDFILE"
  echo "  ✓ Backend starting on port 8000"
else
  echo "  • Backend already running"
fi

# ── Frontend (Vite dev server) ──────────────────────────────────────
if [ -d "$FRONTEND_DIR" ]; then
  if ! pgrep -f "vite" >/dev/null 2>&1; then
    cd "$FRONTEND_DIR"
    if [ -f package.json ]; then
      if [ ! -d node_modules ]; then
        npm install --silent >"$LOG_DIR/frontend-install.log" 2>&1 &
      fi
      nohup npx vite --host 127.0.0.1 --port 5173 \
        >"$LOG_DIR/frontend.log" 2>&1 &
      echo "  ✓ Frontend starting on http://127.0.0.1:5173"
    fi
  else
    echo "  • Frontend already running"
  fi
fi

# ── WhatsApp Bridge ─────────────────────────────────────────────────
if [ -d "$BRIDGE_DIR" ] && command -v node >/dev/null 2>&1; then
  if ! pgrep -f "whatsapp-bridge/server.js" >/dev/null 2>&1; then
    cd "$BRIDGE_DIR"
    if [ -f package.json ] && [ ! -d node_modules ]; then
      npm install --silent >"$LOG_DIR/bridge-install.log" 2>&1 &
    fi
    nohup node server.js >"$LOG_DIR/whatsapp-bridge.log" 2>&1 &
    echo "  ✓ WhatsApp bridge starting on port 4545"
  else
    echo "  • WhatsApp bridge already running"
  fi
fi

# ── Spoken Greeting ──────────────────────────────────────────────────
cd "$BACKEND_DIR"
"$PY" startup_greeting.py >/dev/null 2>&1

