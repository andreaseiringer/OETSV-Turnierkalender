#!/usr/bin/env bash
# ==============================================================================
# pivitLABS ÖTSV Tool - Release Workflow Helper (https://pivitlabs.com)
# ==============================================================================
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Verwendung: $0 <neue_version> [changelog_meldung]"
    echo "Beispiel:   $0 1.1.0 'Optimierung der Tag-Normalisierung'"
    exit 1
fi

NEW_VERSION="$1"
MESSAGE="${2:-Update auf Version $NEW_VERSION}"
TODAY=$(date +"%d.%m.%Y")

echo "Aktualisiere Version auf: $NEW_VERSION ($TODAY)"

# 1. Update app/__init__.py
sed -i.bak "s/__version__ = .*/__version__ = \"$NEW_VERSION\"/" app/__init__.py
rm -f app/__init__.py.bak

# 2. Update app/config.py
sed -i.bak "s/APP_VERSION: str = .*/APP_VERSION: str = \"$NEW_VERSION\"/" app/config.py
rm -f app/config.py.bak

# 3. Update index.html badge
sed -i.bak "s/id=\"app-version-badge\" class=\"badge-count\">v[^<]*/id=\"app-version-badge\" class=\"badge-count\">v$NEW_VERSION/" app/static/index.html
rm -f app/static/index.html.bak

echo "Version erfolgreich aktualisiert auf $NEW_VERSION."
