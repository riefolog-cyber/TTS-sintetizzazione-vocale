#!/usr/bin/env bash
# ============================================================
#  Avvio (Linux / macOS)
#  - libera la porta 8885 da un'istanza precedente
#  - avvia il server in primo piano (Ctrl+C per fermarlo)
#  - apre il browser quando il server e' pronto
# ============================================================
cd "$(dirname "$0")" || exit 1

URL="http://localhost:8885"
PORTA=8885

if [ ! -x ".venv/bin/python" ]; then
  echo "[ERRORE] Ambiente .venv non trovato."
  echo "Esegui prima ./installa.sh"
  exit 1
fi

# True se qualcuno sta ascoltando sulla porta (solo bash, senza tool esterni)
porta_in_ascolto() {
  (exec 3<>"/dev/tcp/127.0.0.1/$PORTA") 2>/dev/null
}

# PID in ascolto sulla porta: lsof (Linux/macOS) -> ss (Linux) -> fuser
pids_da_porta() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$PORTA" -sTCP:LISTEN 2>/dev/null
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v port=":$PORTA" \
      '$4 ~ port"$" { if (match($0, /pid=[0-9]+/)) print substr($0, RSTART+4, RLENGTH-4) }'
  elif command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$PORTA" 2>/dev/null
  fi
}

apri_browser() {
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1" >/dev/null 2>&1
  elif command -v open >/dev/null 2>&1; then
    open "$1" >/dev/null 2>&1          # macOS
  elif command -v wslview >/dev/null 2>&1; then
    wslview "$1" >/dev/null 2>&1       # WSL
  else
    echo "Apri il browser su: $1"
  fi
}

# --- Libera la porta da un'istanza precedente ---
if porta_in_ascolto; then
  pids=$(pids_da_porta | sort -u)
  if [ -n "$pids" ]; then
    for p in $pids; do
      echo "Porta $PORTA occupata dal processo $p: la termino."
      kill "$p" 2>/dev/null
    done
    sleep 1
    # Se il kill non e' riuscito (permessi, oppure shell su un altro SO),
    # meglio mollare subito che far crashare il nuovo avvio sulla porta.
    if porta_in_ascolto; then
      echo "[ERRORE] La porta $PORTA e' ancora occupata dopo il tentativo di kill." >&2
      echo "         Termina quel processo a mano e riprova." >&2
      exit 1
    fi
  else
    echo "[AVVISO] La porta $PORTA e' occupata ma nessun tool (lsof/ss/fuser)" >&2
    echo "         puo' identificare il processo: liberala a mano e riprova." >&2
    exit 1
  fi
fi

# --- Quando il server e' pronto: scrivi il PID ed apri il browser ---
(
  for _ in {1..120}; do
    if porta_in_ascolto; then
      pids=$(pids_da_porta | sort -u)
      [ -n "$pids" ] && echo "${pids%%$'\n'*}" > server.pid
      echo "Server pronto: apro $URL"
      apri_browser "$URL"
      exit 0
    fi
    sleep 1
  done
  echo "[ERRORE] Il server non e' partito entro 120 secondi." >&2
) &

echo "Avvio Kokoro TTS... apri $URL"
exec .venv/bin/python kokoro_app.py