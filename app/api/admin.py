import os
import json
import secrets
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Depends, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings
from app.database import get_db_connection
from app.services.log_service import get_logs
from app.services import config_service
from app.services.teilnehmer_scraper import recalculate_teilnehmer_club_matches
from app.scheduler import (
    get_job_info, execute_scraper_job, execute_fetcher_job,
    execute_results_scraper_job, execute_teilnehmer_scraper_job, ACTIVE_JOBS
)
from app.models import (
    AdminStatusModel, SyncStatusModel, ChangelogEntry,
    ImapConfigModel, ImapConfigUpdateModel, ClubConfigModel, ClubConfigUpdateModel
)

security = HTTPBasic(auto_error=False)

def verify_admin_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    """Enforce HTTP Basic Auth on admin routes if ADMIN_PASSWORD is set in settings."""
    configured_pwd = (settings.ADMIN_PASSWORD or "").strip()
    if not configured_pwd:
        return True
    if not credentials or not secrets.compare_digest(credentials.password.encode("utf-8"), configured_pwd.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung erforderlich.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

router = APIRouter(prefix="/adsi-admin", tags=["admin"], dependencies=[Depends(verify_admin_auth)])

CHANGELOG: List[Dict[str, Any]] = [
    {
        "version": "1.4.0",
        "date": "16.10.2026",
        "changes": [
            "Rebranding auf 'pivitLABS ÖTSV Tool' (Open-Source & Self-Hosted Edition).",
            "Neue Admin-Funktion 'Verein einstellen': Beliebiger Tanzsportklub (Name, Badge-Kürzel, Suchbegriffe) frei konfigurierbar mit sofortiger Neuberechnung der Teilnehmerlisten.",
            "Security-Hardening: Schutz gegen .env-Newline-Injection, eingeschränkte CORS-Policies, URL-Schema-Validierung, strikter E-Mail-Absenderabgleich, Schutz gespeicherter IMAP-Passwörter bei Serverwechsel sowie optionaler Passwortschutz (ADMIN_PASSWORD)."
        ]
    },
    {
        "version": "1.3.0",
        "date": "01.10.2026",
        "changes": [
            "Import der offiziellen ÖTSV-Teilnehmerlisten pro Turnier (4-mal täglich automatisiert).",
            "Detail-Modal für Teilnehmerlisten mit Live-Filterung nach Startklassen und Suche.",
            "Prominente optische Hervorhebung von Paaren des eigenen Vereins (TSC Musterverein).",
            "Direktlink auf die originale ÖTSV-Teilnehmerliste am Kopf des Modals.",
            "Manuelle Ausführung und Statusanzeige für den Teilnehmerlisten-Scraper im Admin Center."
        ]
    },
    {
        "version": "1.2.0",
        "date": "20.09.2026",
        "changes": [
            "Automatisierter ÖTSV-Ergebnisse Scraper (TopTurnier-Berichte) für Turniere mit Vereinsbeteiligung integriert.",
            "Relationale Persistierung der Turnierergebnisse (Platzierung 'Platz X von Y', Endrunde/Vorrunde, Verein, Startnummer).",
            "Auszeichnung im Turnierkalender mit 🏆-Badge, Medaillen (🥇, 🥈, 🥉) für Podestplätze und Direktlink zum offiziellen ÖTSV-Turnierbericht.",
            "Manueller Trigger & Statusanzeige für Ergebnisse-Scraper im Admin Control Center."
        ]
    },
    {
        "version": "1.1.0",
        "date": "11.09.2026",
        "changes": [
            "Interaktive IMAP Postfach-Konfiguration direkt im Admin-Portal integriert.",
            "Komfortables Bearbeiten und Speichern von Server, Port, User, Passwort, Intervall und Whitelist in die .env-Datei mit sofortiger Live-Anwendung.",
            "Integrierte Verbindungstest-Funktion ('Verbindung testen') zur direkten Überprüfung der IMAP-Zugangsdaten.",
            "Mock-Modus Toggle zur Simulation von Turniernennungen ohne reales Postfach."
        ]
    },
    {
        "version": "1.0.0",
        "date": "09.09.2026",
        "changes": [
            "Initiale Neuimplementierung des ADSI Portals für den vereinsinternen Betrieb.",
            "ÖTSV Web-Scraper für 12 Monate rollierenden Kalenderabruf mit Upsert & Tag-Normalisierung.",
            "IMAP Mail-Fetcher mit Absender-Whitelist und automatischem relationalen Nennungsabgleich.",
            "Responsive Benutzeroberfläche mit Dark/Light Mode, 7-Tage-Kulanz und Nennungs-Modal.",
            "Integriertes Administrations- und Monitoring-Center unter /adsi-admin ohne Passwortschranke."
        ]
    }
]

@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def serve_admin_page():
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    return FileResponse(os.path.join(static_dir, "admin.html"))

@router.get("/api/status", response_model=AdminStatusModel)
def get_admin_status():
    """Retrieve comprehensive system metrics, database counts, and job statuses."""
    now_vienna = datetime.now(ZoneInfo(settings.TIMEZONE))
    server_time = now_vienna.strftime("%d.%m.%Y %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM turniere;")
        t_cnt = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM nennungen;")
        n_cnt = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM nennungs_klassen;")
        k_cnt = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM turnier_ergebnisse;")
        e_cnt = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM turnier_teilnehmer;")
        teilnehmer_cnt = cursor.fetchone()["cnt"]

        cursor.execute("SELECT key, last_run, added_count, updated_count, status, message FROM sync_status;")
        sync_rows = cursor.fetchall()
        sync_dict = {
            r["key"]: SyncStatusModel(
                key=r["key"],
                last_run=r["last_run"],
                added_count=r["added_count"],
                updated_count=r["updated_count"],
                status=r["status"],
                message=r["message"]
            )
            for r in sync_rows
        }

    job_info = get_job_info()

    return AdminStatusModel(
        status="operational",
        version=settings.APP_VERSION,
        server_time=server_time,
        turniere_gesamt=t_cnt,
        nennungen_gesamt=n_cnt,
        klassen_gesamt=k_cnt,
        ergebnisse_gesamt=e_cnt,
        teilnehmer_gesamt=teilnehmer_cnt,
        running_jobs=job_info["running_jobs"],
        next_runs=job_info["next_runs"],
        sync_status=sync_dict
    )

@router.get("/api/data")
def get_admin_data(limit: int = 50):
    """Retrieve raw extracts of recent tournaments and registrations with classes."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Last tournaments
        cursor.execute("""
            SELECT id, turnier_id, datum, datum_sort, titel, klub, bundesland, tags, links, created_at, updated_at
            FROM turniere
            ORDER BY datum_sort DESC
            LIMIT ?;
        """, (limit,))
        turniere = []
        for r in cursor.fetchall():
            turniere.append({
                "id": r["id"],
                "turnier_id": r["turnier_id"],
                "datum": r["datum"],
                "datum_sort": r["datum_sort"],
                "titel": r["titel"],
                "klub": r["klub"],
                "bundesland": r["bundesland"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "links": json.loads(r["links"]) if r["links"] else {},
                "created_at": r["created_at"],
                "updated_at": r["updated_at"]
            })

        # Last registrations
        cursor.execute("""
            SELECT id, nennungs_id, paar_name, min_partner_1, min_partner_2, klub, turnier_id, turnier_db_id, created_at
            FROM nennungen
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        nennungen = []
        for r in cursor.fetchall():
            nid = r["id"]
            cursor.execute("SELECT id, datum, klasse FROM nennungs_klassen WHERE nennung_db_id = ? ORDER BY id ASC;", (nid,))
            k_rows = [{"id": kr["id"], "datum": kr["datum"], "klasse": kr["klasse"]} for kr in cursor.fetchall()]

            nennungen.append({
                "id": r["id"],
                "nennungs_id": r["nennungs_id"],
                "paar_name": r["paar_name"],
                "min_partner_1": r["min_partner_1"],
                "min_partner_2": r["min_partner_2"],
                "klub": r["klub"],
                "turnier_id": r["turnier_id"],
                "turnier_db_id": r["turnier_db_id"],
                "created_at": r["created_at"],
                "klassen": k_rows
            })

        # Last results
        cursor.execute("""
            SELECT id, turnier_id, turnier_db_id, klasse_name, klasse_slug, platz, total_paare,
                   paar_name, startnr, klub, runde, bericht_url, created_at
            FROM turnier_ergebnisse
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        ergebnisse = [dict(r) for r in cursor.fetchall()]

        # Last participants
        cursor.execute("""
            SELECT id, turnier_id, turnier_db_id, klasse, paar_name, klub, is_utsc, sort_order, created_at
            FROM turnier_teilnehmer
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        teilnehmer = [dict(r) for r in cursor.fetchall()]

    return {
        "turniere": turniere,
        "nennungen": nennungen,
        "ergebnisse": ergebnisse,
        "teilnehmer": teilnehmer
    }

@router.get("/api/logs")
def get_admin_logs(target: str = Query(default="system", pattern="^(system|scraper|fetcher|results_scraper|teilnehmer_scraper)$"), limit: int = 150):
    """Retrieve tail of logs for requested target."""
    lines = get_logs(target=target, limit=limit)
    return {
        "target": target,
        "count": len(lines),
        "logs": lines
    }

@router.post("/api/trigger/{job_name}")
async def trigger_job(job_name: str, background_tasks: BackgroundTasks):
    """Trigger background execution of scraper, mail fetcher, results scraper, or teilnehmer scraper with lock protection."""
    norm_job = job_name.replace("-", "_")
    if norm_job not in ["scraper", "fetcher", "results_scraper", "teilnehmer_scraper"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannter Job: {job_name}. Erlaubt: 'scraper', 'fetcher', 'results-scraper', 'teilnehmer-scraper'"
        )

    if ACTIVE_JOBS.get(norm_job, False):
        return {
            "status": "already_running",
            "message": f"Der Job '{job_name}' läuft bereits. Bitte warten."
        }

    if norm_job == "scraper":
        background_tasks.add_task(execute_scraper_job)
    elif norm_job == "fetcher":
        background_tasks.add_task(execute_fetcher_job)
    elif norm_job == "results_scraper":
        background_tasks.add_task(execute_results_scraper_job)
    elif norm_job == "teilnehmer_scraper":
        background_tasks.add_task(execute_teilnehmer_scraper_job)

    return {
        "status": "triggered",
        "message": f"Job '{job_name}' wurde im Hintergrund gestartet."
    }

@router.get("/api/changelog", response_model=List[ChangelogEntry])
def get_changelog():
    """Retrieve application changelog."""
    return CHANGELOG

@router.get("/api/config/imap", response_model=ImapConfigModel)
def get_imap_config():
    """Retrieve current IMAP settings (password masked)."""
    return ImapConfigModel(
        imap_enabled=settings.IMAP_ENABLED,
        imap_server=settings.IMAP_SERVER,
        imap_port=settings.IMAP_PORT,
        imap_user=settings.IMAP_USER,
        has_password=bool(settings.IMAP_PASSWORD),
        imap_mailbox=settings.IMAP_MAILBOX,
        imap_fetch_interval_minutes=settings.IMAP_FETCH_INTERVAL_MINUTES,
        imap_allowed_senders=settings.IMAP_ALLOWED_SENDERS,
        imap_mock=settings.IMAP_MOCK
    )

@router.post("/api/config/imap", response_model=ImapConfigModel)
def update_imap_config(data: ImapConfigUpdateModel):
    """Save IMAP configuration to .env and apply live to settings."""
    env_updates = {
        "IMAP_ENABLED": "true" if data.imap_enabled else "false",
        "IMAP_SERVER": data.imap_server,
        "IMAP_PORT": str(data.imap_port),
        "IMAP_USER": data.imap_user,
        "IMAP_MAILBOX": data.imap_mailbox,
        "IMAP_FETCH_INTERVAL_MINUTES": str(data.imap_fetch_interval_minutes),
        "IMAP_ALLOWED_SENDERS": data.imap_allowed_senders,
        "IMAP_MOCK": "true" if data.imap_mock else "false"
    }

    # Only update password if provided
    if data.imap_password is not None and data.imap_password.strip():
        env_updates["IMAP_PASSWORD"] = data.imap_password
        settings.IMAP_PASSWORD = data.imap_password

    # Save to .env
    config_service.update_env_file(env_updates)

    # Update in-memory settings
    settings.IMAP_ENABLED = data.imap_enabled
    settings.IMAP_SERVER = data.imap_server
    settings.IMAP_PORT = data.imap_port
    settings.IMAP_USER = data.imap_user
    settings.IMAP_MAILBOX = data.imap_mailbox
    settings.IMAP_FETCH_INTERVAL_MINUTES = data.imap_fetch_interval_minutes
    settings.IMAP_ALLOWED_SENDERS = data.imap_allowed_senders
    settings.IMAP_MOCK = data.imap_mock

    return ImapConfigModel(
        imap_enabled=settings.IMAP_ENABLED,
        imap_server=settings.IMAP_SERVER,
        imap_port=settings.IMAP_PORT,
        imap_user=settings.IMAP_USER,
        has_password=bool(settings.IMAP_PASSWORD),
        imap_mailbox=settings.IMAP_MAILBOX,
        imap_fetch_interval_minutes=settings.IMAP_FETCH_INTERVAL_MINUTES,
        imap_allowed_senders=settings.IMAP_ALLOWED_SENDERS,
        imap_mock=settings.IMAP_MOCK
    )

@router.post("/api/config/imap/test")
def test_imap_connection_endpoint(data: ImapConfigUpdateModel):
    """Test connection with the supplied or currently saved credentials."""
    if data.imap_mock:
        return {
            "success": True,
            "message": "Mock-Modus ist aktiv. In diesem Modus werden Test-Nennungen ohne reales Postfach simuliert (OK)."
        }

    supplied_password = data.imap_password.strip() if (data.imap_password is not None and data.imap_password.strip()) else None
    if supplied_password:
        effective_password = supplied_password
    else:
        # Security: Only allow fallback to stored password if server, port, and user match the stored config
        if (
            data.imap_server.strip() != settings.IMAP_SERVER.strip()
            or data.imap_port != settings.IMAP_PORT
            or data.imap_user.strip() != settings.IMAP_USER.strip()
        ):
            return {
                "success": False,
                "message": "Bei Änderung von Server, Port oder Benutzername muss das Passwort aus Sicherheitsgründen neu eingegeben werden."
            }
        effective_password = settings.IMAP_PASSWORD

    if not effective_password:
        return {
            "success": False,
            "message": "Kein Passwort angegeben oder im System hinterlegt."
        }

    success, message = config_service.test_imap_connection(
        server=data.imap_server,
        port=data.imap_port,
        user=data.imap_user,
        password=effective_password,
        mailbox=data.imap_mailbox,
        timeout=settings.IMAP_TIMEOUT
    )
    return {"success": success, "message": message}

@router.get("/api/config/club", response_model=ClubConfigModel)
def get_club_config():
    """Retrieve current club settings ('Verein einstellen')."""
    return ClubConfigModel(
        club_name=settings.CLUB_NAME,
        club_short=settings.club_short_label,
        club_keywords=settings.CLUB_KEYWORDS,
        effective_tokens=settings.club_matching_tokens
    )

@router.post("/api/config/club", response_model=ClubConfigModel)
def update_club_config(data: ClubConfigUpdateModel):
    """Save club configuration to .env, apply live to settings, and recalculate participant highlights."""
    clean_name = data.club_name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Vereinsname darf nicht leer sein.")

    clean_short = data.club_short.strip() if data.club_short else ""
    if not clean_short:
        clean_short = clean_name.split()[0]

    clean_keywords = data.club_keywords.strip() if data.club_keywords else ""

    env_updates = {
        "CLUB_NAME": clean_name,
        "CLUB_SHORT": clean_short,
        "CLUB_KEYWORDS": clean_keywords
    }
    config_service.update_env_file(env_updates)

    settings.CLUB_NAME = clean_name
    settings.CLUB_SHORT = clean_short
    settings.CLUB_KEYWORDS = clean_keywords

    # Immediately update existing participant list highlights in DB
    recalculate_teilnehmer_club_matches()

    return ClubConfigModel(
        club_name=settings.CLUB_NAME,
        club_short=settings.club_short_label,
        club_keywords=settings.CLUB_KEYWORDS,
        effective_tokens=settings.club_matching_tokens
    )


