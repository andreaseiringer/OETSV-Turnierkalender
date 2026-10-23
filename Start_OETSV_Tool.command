#!/bin/bash
# ============================================================================
# pivitLABS ÖTSV Tool – 1-Klick Desktop-Starter (macOS)
# Doppelklick startet das Tool und öffnet http://127.0.0.1:8000 im Browser.
# Alle Daten in data/adsi.db und Einstellungen in .env bleiben gespeichert!
# ============================================================================

cd "$(dirname "$0")" || exit 1

if [ ! -d ".venv" ]; then
    echo "Ersteinrichtung: Erstelle virtuelle Python-Umgebung (.venv)..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    chmod 600 .env
fi

exec .venv/bin/python launcher.py
