@echo off
REM ============================================================
REM  Avvia Kokoro TTS usando l'ambiente .venv (Python 3.11 x64)
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRORE] Ambiente .venv non trovato.
    echo Esegui prima "installa.bat".
    pause
    exit /b 1
)

REM Libera la porta 8885 se occupata da un'istanza precedente
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8885" ^| findstr "LISTENING"') do (
    echo Porta 8885 occupata dal processo %%P: la termino.
    taskkill /PID %%P /F >nul 2>&1
)

echo Avvio Kokoro TTS in una nuova finestra...
start "Kokoro TTS - console" ".venv\Scripts\python.exe" kokoro_app.py

REM Attende che il server sia pronto (max 120 secondi) e apre il browser
set /a attese=0
:attesa
ping -n 2 127.0.0.1 >nul
set /a attese+=1
netstat -ano | findstr ":8885" | findstr "LISTENING" >nul
if not errorlevel 1 goto apri
if %attese% LSS 120 goto attesa
echo [ERRORE] Il server non e' partito entro 120 secondi.
echo Controlla la finestra "Kokoro TTS - console" per il dettaglio.
pause
exit /b 1

:apri
echo Server pronto: apro http://localhost:8885
start "" http://localhost:8885
exit /b 0
