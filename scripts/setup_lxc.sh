#!/usr/bin/env bash
# ==============================================================================
# pivitLABS ÖTSV Tool - Automatisches Setup-Skript (Debian/Ubuntu)
# https://pivitlabs.com
# ==============================================================================
set -euo pipefail

APP_DIR="/opt/adsi-portal"
SERVICE_USER="oetsv"

echo "==> 1. System-Pakete aktualisieren und Python 3 installieren..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl sqlite3

echo "==> 2. Dedizierten System-Benutzer ($SERVICE_USER) und Verzeichnisse vorbereiten..."
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/logs"

echo "==> 3. Virtualenv einrichten..."
if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi

echo "==> 4. Abhängigkeiten installieren..."
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> 5. Konfiguration (.env) und Dateiberechtigungen prüfen..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "HINWEIS: .env wurde aus .env.example erstellt. Bitte Verein & IMAP-Zugangsdaten anpassen!"
fi
chmod 600 "$APP_DIR/.env"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

echo "==> 6. Systemd Service installieren..."
cp "$APP_DIR/scripts/adsi-portal.service" /etc/systemd/system/adsi-portal.service
systemctl daemon-reload
systemctl enable adsi-portal.service
systemctl restart adsi-portal.service

echo "==> Status prüfen..."
systemctl status adsi-portal.service --no-pager

echo ""
echo "=============================================================================="
echo " pivitLABS ÖTSV Tool erfolgreich installiert!"
echo " Portal:      http://localhost:8000/"
echo " Admin:       http://localhost:8000/adsi-admin"
echo " Logs:        journalctl -u adsi-portal.service -f"
echo " Website:     https://pivitlabs.com"
echo "=============================================================================="
