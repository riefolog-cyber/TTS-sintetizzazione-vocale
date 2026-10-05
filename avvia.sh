#!/usr/bin/env bash
# ============================================================
#  Avvio (Linux / macOS)
# ============================================================
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "[ERRORE] Ambiente .venv non trovato."
  echo "Esegui prima ./installa.sh"
  exit 1
fi

echo "Avvio in corso... apri http://localhost:8885"
exec .venv/bin/python kokoro_app.py