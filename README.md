# pivitLABS ÖTSV Tool – Tanzsportkalender & Nennungs-Aggregator

> **Entwickelt von:** [pivitlabs](https://pivitlabs.com)  
> **Einsatzbereich:** Leichtgewichtiges Open-Source- & Self-Hosted-Informationsportal für österreichische Tanzsportklubs (Localhost & LAN).  
> **Ziel-Infrastruktur:** Lokale Ausführung (macOS/Linux/Windows) oder schlanker Linux-Container (Debian/Ubuntu) ohne externe Datenbankdienste.

---

## 🌟 Hauptfunktionen

1. **Frei konfigurierbarer Tanzsportverein (`Verein einstellen`):**
   - Beliebiger österreichischer Tanzsportklub direkt im Admin-Portal (`/adsi-admin`) oder via `.env` einstellbar (`CLUB_NAME`, `CLUB_SHORT`, `CLUB_KEYWORDS`).
   - Sofortige Neuberechnung der Vereins-Hervorhebungen in bestehenden Teilnehmerlisten bei Vereinswechsel.

2. **ÖTSV Web-Scraper (FA-1):**
   - Autonomer Abruf des offiziellen Turnierkalenders für 12 Monate rollierend.
   - Entflechtung von Turniertiteln, Klubs, Bundesländern und Tags.
   - Erkennung von Verbands-IDs (`TKNr`, `TASNr`) aus Ausschreibungs-Links.
   - Idempotenter Upsert in SQLite (WAL-Modus).
   - Tägliche Ausführung um 04:00 Uhr lokaler Zeit (`Europe/Vienna`).

3. **IMAP E-Mail Fetcher (FA-2):**
   - Überwachung des vereinsinternen Postfachs auf Nennungsbestätigungen.
   - Strikte Absender-Whitelist (exakte E-Mail-Adresse oder Domain) zur Vermeidung unbefugter oder fehlerhafter Datensätze.
   - Regex-basierte Extraktion: Paarname, Nennungs-ID, MIN 1 & 2, Klub, Turnier-ID und gemeldete Startklassen mit Datum.
   - Relationale Verknüpfung (`turniere.turnier_id == nennungen.turnier_id`).
   - Zyklischer Abruf alle 15 Minuten.

4. **ÖTSV Teilnehmerlisten- & Ergebnisse-Scraper:**
   - 4-mal täglicher autonomer Import der offiziellen ÖTSV-Teilnehmerlisten für alle anstehenden Turniere.
   - Automatischer TopTurnier-Ergebnisimport für Turniere mit Vereinsbeteiligung inkl. HTML-Export für Vereins-Newsblogs.
   - Filterbares Detail-Modal nach Startklassen und Volltextsuche mit prominenter Hervorhebung der Paare des eingestellten Vereins.

5. **Responsive Benutzeroberfläche (FA-5):**
   - **Echtzeitfilter:** Volltextsuche, Bundesland-Filter (Wien, NÖ, OÖ etc.), Disziplinen (Standard, Latein, Kombi, Formationen) und Altersklassen mit semantischem Alias-Mapping.
   - **Zeitliche Tabs (7-Tage-Kulanz):** "Aktuelle Turniere" (chronologisch aufsteigend) und "Vergangene Turniere" (chronologisch absteigend).
   - **Dark / Light Mode:** Automatische Erkennung der System-Präferenz mit manuellem Umschalter und `localStorage`-Persistierung.

6. **Integriertes Administrations-Center (FA-6):**
   - Erreichbar unter `/adsi-admin` (optional geschützt via HTTP Basic Auth über `ADMIN_PASSWORD` in `.env`).
   - **Verein einstellen:** Konfiguration von Vereinsname, Badge-Kürzel und Suchbegriffen.
   - **IMAP-Konfiguration:** Komfortables Bearbeiten und Testen der Postfach-Zugangsdaten.
   - Live-KPIs, manuelle Job-Trigger, Log-Konsole und Daten-Inspektor.

---

## 🚀 Schnellstart (Localhost & Desktop)

### Option A: 1-Klick-Start per Desktop-Symbol (macOS & Windows)
- **macOS:** Doppelklick auf [`Start_OETSV_Tool.command`](Start_OETSV_Tool.command) (oder Alias davon auf den Schreibtisch ziehen).
- **Windows:** Doppelklick auf [`Start_OETSV_Tool.bat`](Start_OETSV_Tool.bat) (oder Rechtsklick → *Verknüpfung auf dem Desktop erstellen*).

Beim ersten Start wird automatisch die Python-Umgebung (`.venv`) eingerichtet, die Konfiguration (`.env`) angelegt, der lokale Server gestartet und `http://127.0.0.1:8000` im Standard-Browser geöffnet. Alle Daten (`data/adsi.db`) und Einstellungen (`.env`) bleiben dauerhaft gespeichert.

### Option B: Eigenständige Desktop-App bauen (`.app` / `.exe` ohne Python-Installation beim Kunden)
Mit [`build_desktop_app.py`](build_desktop_app.py) lässt sich eine fertige Desktop-App erzeugen:
```bash
.venv/bin/python build_desktop_app.py
```
- **macOS:** Erzeugt `dist/pivitLABS OETSV Tool.app` (Daten werden dauerhaft unter `~/Library/Application Support/pivitLABS-OETSV-Tool/` gespeichert).
- **Windows:** Erzeugt `dist/pivitLABS OETSV Tool/pivitLABS OETSV Tool.exe` (Daten werden dauerhaft unter `%APPDATA%\pivitLABS-OETSV-Tool\` gespeichert).

### Option C: Manuell über Terminal (Entwicklung)
```bash
# 1. Virtual Environment erstellen & aktivieren
python3 -m venv .venv
source .venv/bin/activate

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. Konfiguration anlegen
cp .env.example .env

# 4. Tests ausführen
pytest -v

# 5. Server + Browser über Launcher starten
python launcher.py
```

Aufruf im Browser:
- **Turnierportal:** `http://127.0.0.1:8000/`
- **Admin Center:** `http://127.0.0.1:8000/adsi-admin`
- **API Dokumentation:** `http://127.0.0.1:8000/docs`

---

## 📦 Deployment im LXC Container / Linux Server

1. Erstelle einen schlanken LXC-Container (Debian 12 oder Ubuntu 24.04).
2. Klone das Repository nach `/opt/adsi-portal`:
   ```bash
   git clone <repo-url> /opt/adsi-portal
   cd /opt/adsi-portal
   ```
3. Führe das automatisierte Setup-Skript aus (richtet einen unprivilegierten Systembenutzer `oetsv` und den systemd-Service ein):
   ```bash
   chmod +x scripts/*.sh
   ./scripts/setup_lxc.sh
   ```

---

## 📡 API-Schnittstellen

| Methode | Pfad | Beschreibung |
| :--- | :--- | :--- |
| `GET` | `/api/turniere` | Alle Turniere inkl. gemeldeter Vereinspaare, Klassen und Teilnehmeranzahl |
| `GET` | `/api/turniere/{id}/teilnehmer` | Vollständige Teilnehmerliste eines Turniers nach Klassen gruppiert |
| `GET` | `/api/sync-status` | Status und letzter Lauf von Scrapern und Fetcher |
| `GET` | `/api/version` | Systemzustand, Versionsnummer und aktiver Verein |
| `GET` | `/adsi-admin` | Administrations-Oberfläche |
| `GET` | `/adsi-admin/api/status` | KPIs, Serverzeit, nächste Job-Laufzeiten |
| `GET/POST` | `/adsi-admin/api/config/club` | Verein einstellen (Name, Kürzel, Suchbegriffe) |
| `GET/POST` | `/adsi-admin/api/config/imap` | IMAP-Postfach konfigurieren |
| `POST` | `/adsi-admin/api/config/imap/test` | IMAP-Verbindung testen |
| `GET` | `/adsi-admin/api/data` | Rohdaten-Auszug (Turniere, Nennungen, Ergebnisse, Teilnehmer) |
| `GET` | `/adsi-admin/api/logs` | Ausführungsprotokolle (System, Scraper, Teilnehmer, Ergebnisse, Fetcher) |
| `POST` | `/adsi-admin/api/trigger/{job}` | Manuelle Ausführung (`scraper`, `teilnehmer-scraper`, `results-scraper`, `fetcher`) |
| `GET` | `/adsi-admin/api/changelog` | Release-Historie |

---

## ⚠️ Disclaimer / Haftungsausschluss

Das **pivitLABS ÖTSV Tool** ist ein unabhängiges, selbstgehostetes Open-Source-Projekt von **[pivitlabs](https://pivitlabs.com)** und steht in **keiner offiziellen Verbindung zum Österreichischen TanzSport-Verband (ÖTSV)** oder dessen Landesverbänden und Vereinen.

- **Keine Gewähr:** Die Software sowie alle automatisiert abgerufenen Turnier-, Teilnehmer- und Ergebnisdaten werden „wie besehen“ (*AS IS*) und ohne jegliche ausdrückliche oder stillschweigende Gewährleistung auf Richtigkeit, Vollständigkeit, Aktualität oder Verfügbarkeit bereitgestellt.
- **Verbindlichkeit:** Maßgeblich für Turnierausschreibungen, Nennschlüsse, Startklassen, Teilnehmerlisten und Ergebnisse sind ausschließlich die offiziellen Veröffentlichungen des Österreichischen TanzSport-Verbandes (ÖTSV).
- **Eigenverantwortung beim Betrieb:** Die Nutzung des Tools (insbesondere das automatisierte Abrufen öffentlich zugänglicher Webseiten sowie die Anbindung eines eigenen E-Mail-Postfachs und die Einhaltung datenschutzrechtlicher Vorgaben wie der DSGVO innerhalb des Vereins) erfolgt auf eigene Verantwortung des jeweiligen Betreibers.

---

## ⚖ Lizenz & Copyright

Copyright &copy; 2026 **[pivitlabs](https://pivitlabs.com)** – Alle Rechte im Rahmen der MIT-Lizenz vorbehalten.  
Weitere Informationen unter **[https://pivitlabs.com](https://pivitlabs.com)**.

