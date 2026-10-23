@echo off
REM ============================================================================
REM pivitLABS ÖTSV Tool – 1-Klick Desktop-Starter (Windows)
REM Doppelklick startet das Tool und öffnet http://127.0.0.1:8000 im Browser.
REM Alle Daten in data\adsi.db und Einstellungen in .env bleiben gespeichert!
REM ============================================================================

cd /d "%~dp0"

if not exist ".venv" (
    echo Ersteinrichtung: Erstelle virtuelle Python-Umgebung ^(.venv^)...
    python -m venv .venv
    call .venv\Scripts\pip install --upgrade pip
    call .venv\Scripts\pip install -r requirements.txt
)

if not exist ".env" (
    if exist ".env.example" copy .env.example .env
)

call .venv\Scripts\python launcher.py
pause
