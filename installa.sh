#!/usr/bin/env bash
# ============================================================
#  Installazione (Linux / macOS) - solo la prima volta
# ============================================================
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[ERRORE] Python non trovato."
  echo "Installa Python 3.10 o 3.11:"
  echo "  Debian/Ubuntu: sudo apt install python3 python3-venv"
  echo "  Fedora        : sudo dnf install python3"
  echo "  macOS         : brew install python@3.11"
  exit 1
fi

echo "Python: $("$PY" --version 2>&1)"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "[AVVISO] ffmpeg non trovato nel PATH."
  echo "  Video, MP3 e normalizzazione non saranno disponibili (il WAV funziona lo stesso)."
  echo "  Debian/Ubuntu: sudo apt install ffmpeg"
  echo "  Fedora        : sudo dnf install ffmpeg"
  echo "  macOS         : brew install ffmpeg"
  echo ""
fi

if [ ! -d ".venv" ]; then
  echo "Creazione ambiente virtuale .venv ..."
  "$PY" -m venv .venv
fi

echo "Aggiornamento pip ..."
.venv/bin/python -m pip install --upgrade pip

echo "Installazione dipendenze (puo' richiedere alcuni minuti) ..."
.venv/bin/python -m pip install -r requirements.txt

# su alcuni sistemi serve espeak-ng per la sintesi offline Kokoro
if ! .venv/bin/python -c "import espeakng_loader" >/dev/null 2>&1; then
  echo "[AVVISO] Se la sintesi offline (Kokoro) segnala errori con espeak-ng:"
  echo "  sudo apt install espeak-ng"
fi

echo ""
echo "============================================================"
echo " Installazione completata! Ora avvia con: ./avvia.sh"
echo "============================================================"