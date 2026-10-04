@echo off
REM ============================================================
REM  Installa l'ambiente per Kokoro TTS (solo la prima volta)
REM  Usa Python 3.11 a 64 bit (x64).
REM  NOTA: su Windows on ARM (Snapdragon) il Python ARM64 NON
REM  puo' installare PyTorch, quindi va usato Python x64.
REM ============================================================
cd /d "%~dp0"

py -3.11 -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERRORE] Python 3.11 a 64 bit non trovato.
    echo Installa "Python 3.11 (64-bit)" da https://www.python.org/downloads/release/python-3119/
    echo e riprova.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creazione ambiente virtuale .venv ...
    py -3.11 -m venv .venv
)

echo Aggiornamento pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo Installazione dipendenze (puo' richiedere alcuni minuti) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo ============================================================
echo  Installazione completata! Ora avvia con: avvia.bat
echo ============================================================
pause
