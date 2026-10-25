import os
import sys
import json
import time
import socket
import shutil
import sqlite3
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple

from app.config import settings
from app.services import config_service

logger = logging.getLogger("system")

STORAGE_SETTINGS_FILE = "data/storage_settings.json"
CLOUD_SUBFOLDER_NAME = "pivitLABS-OETSV-Tool"
CLOUD_DB_FILENAME = "adsi.db"
CLOUD_CONFIG_FILENAME = "cloud_config.json"
CLOUD_LOCK_FILENAME = "adsi.lock"

# Runtime state for active lock conflict / read-only mode
_RUNTIME_STATE: Dict[str, Any] = {
    "lock_conflict": False,
    "lock_holder": None,
    "read_only_cloud": False,
    "last_cloud_sync": None,
    "last_cloud_error": None,
    "webview_window": None,
}


def register_webview_window(window: Any) -> None:
    """Register the active pywebview window instance for native folder dialogs."""
    _RUNTIME_STATE["webview_window"] = window


def _now_iso() -> str:
    try:
        tz = ZoneInfo(settings.TIMEZONE)
    except Exception:
        tz = None
    return datetime.now(tz).strftime("%d.%m.%Y %H:%M:%S")


def get_storage_settings_path() -> Path:
    return Path(STORAGE_SETTINGS_FILE).resolve()


def load_storage_settings() -> Dict[str, Any]:
    """Load local machine storage configuration from data/storage_settings.json."""
    path = get_storage_settings_path()
    default_cfg = {
        "setup_completed": False,
        "storage_mode": "local",  # "local" or "cloud"
        "cloud_dir": "",
        "sync_imap": False,
        "last_sync": None,
    }
    if not path.exists():
        return default_cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in default_cfg.items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        logger.warning(f"Konnte storage_settings.json nicht lesen: {e}")
        return default_cfg


def save_storage_settings(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Persist local machine storage configuration to data/storage_settings.json."""
    path = get_storage_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def detect_cloud_providers() -> List[Dict[str, str]]:
    """
    Detect installed cloud sync folders (iCloud Drive, OneDrive, Google Drive, Dropbox)
    on macOS and Windows.
    """
    home = Path.home()
    providers: List[Dict[str, str]] = []
    seen_paths = set()

    def _add(provider_id: str, name: str, base_path: Path):
        try:
            resolved = str(base_path.resolve())
        except Exception:
            resolved = str(base_path)
        if resolved in seen_paths:
            return
        seen_paths.add(resolved)
        target_path = base_path / CLOUD_SUBFOLDER_NAME
        providers.append({
            "id": provider_id,
            "name": name,
            "base_path": str(base_path),
            "suggested_path": str(target_path),
            "existing_db": (target_path / CLOUD_DB_FILENAME).exists() or (base_path / CLOUD_DB_FILENAME).exists()
        })

    # 1. macOS iCloud Drive
    icloud_mac = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if icloud_mac.exists() and icloud_mac.is_dir():
        _add("icloud", "iCloud Drive", icloud_mac)

    # 2. Windows iCloud Drive
    icloud_win = home / "iCloudDrive"
    if icloud_win.exists() and icloud_win.is_dir():
        _add("icloud", "iCloud Drive", icloud_win)

    # 3. macOS CloudStorage (Google Drive, OneDrive, Dropbox, Box on modern macOS)
    cloud_storage_mac = home / "Library" / "CloudStorage"
    if cloud_storage_mac.exists() and cloud_storage_mac.is_dir():
        try:
            for entry in sorted(cloud_storage_mac.iterdir()):
                if not entry.is_dir():
                    continue
                ename = entry.name
                if ename.startswith("GoogleDrive"):
                    # Google Drive often has "Meine Ablage" or "My Drive" inside
                    sub = entry
                    for candidate in ["Meine Ablage", "My Drive"]:
                        if (entry / candidate).exists():
                            sub = entry / candidate
                            break
                    _add("gdrive", f"Google Drive ({ename.replace('GoogleDrive-', '')})", sub)
                elif ename.startswith("OneDrive"):
                    _add("onedrive", f"OneDrive ({ename.replace('OneDrive-', '')})", entry)
                elif ename.startswith("Dropbox"):
                    _add("dropbox", "Dropbox", entry)
        except OSError:
            pass

    # 4. Windows / Classic OneDrive & Google Drive & Dropbox
    for env_key, label in [("OneDrive", "OneDrive"), ("OneDriveCommercial", "OneDrive (Business)"), ("OneDriveConsumer", "OneDrive (Personal)")]:
        env_val = os.environ.get(env_key)
        if env_val and Path(env_val).exists():
            _add("onedrive", label, Path(env_val))

    for folder_name, pid, label in [
        ("OneDrive", "onedrive", "OneDrive"),
        ("Google Drive", "gdrive", "Google Drive"),
        ("My Drive", "gdrive", "Google Drive"),
        ("Meine Ablage", "gdrive", "Google Drive"),
        ("Dropbox", "dropbox", "Dropbox"),
    ]:
        candidate = home / folder_name
        if candidate.exists() and candidate.is_dir():
            _add(pid, label, candidate)

    return providers


def _get_hostname() -> str:
    try:
        return socket.gethostname() or "Unbekannter-PC"
    except Exception:
        return "Unbekannter-PC"


def check_cloud_lock(cloud_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Check if another machine currently holds an active lock in cloud_dir.
    Returns the lock dictionary if held by ANOTHER machine/process, or None if free/ours.
    """
    lock_file = cloud_dir / CLOUD_LOCK_FILENAME
    if not lock_file.exists():
        return None
    try:
        info = json.loads(lock_file.read_text(encoding="utf-8"))
        my_host = _get_hostname()
        my_pid = os.getpid()
        if info.get("hostname") == my_host and info.get("pid") == my_pid:
            return None
        # If same host, check if the PID is still alive
        if info.get("hostname") == my_host and info.get("pid"):
            other_pid = int(info["pid"])
            try:
                os.kill(other_pid, 0)
            except OSError:
                # Process on same host is dead -> stale lock
                return None
        return info
    except Exception:
        return None


def acquire_cloud_lock(cloud_dir: Path, force: bool = False) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Attempt to acquire the lock file in cloud_dir.
    If another machine holds it and force=False, sets lock_conflict state and returns (False, holder).
    """
    cloud_dir.mkdir(parents=True, exist_ok=True)
    holder = check_cloud_lock(cloud_dir)
    if holder and not force:
        _RUNTIME_STATE["lock_conflict"] = True
        _RUNTIME_STATE["lock_holder"] = holder
        _RUNTIME_STATE["read_only_cloud"] = True
        logger.warning(f"Cloud-Sperre erkannt von {holder.get('hostname')} ({holder.get('started_at')}). Starte im Nur-Lesen-Cloud-Modus.")
        return False, holder

    lock_data = {
        "hostname": _get_hostname(),
        "pid": os.getpid(),
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        (cloud_dir / CLOUD_LOCK_FILENAME).write_text(
            json.dumps(lock_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        _RUNTIME_STATE["lock_conflict"] = False
        _RUNTIME_STATE["lock_holder"] = None
        _RUNTIME_STATE["read_only_cloud"] = False
        return True, None
    except Exception as e:
        logger.error(f"Konnte Cloud-Lockdatei nicht schreiben: {e}")
        return False, None


def release_cloud_lock(cloud_dir: Optional[Path] = None) -> None:
    """Remove our lock file from the cloud folder on shutdown or folder switch."""
    if cloud_dir is None:
        cfg = load_storage_settings()
        if cfg.get("storage_mode") != "cloud" or not cfg.get("cloud_dir"):
            return
        cloud_dir = Path(cfg["cloud_dir"])

    lock_file = cloud_dir / CLOUD_LOCK_FILENAME
    if not lock_file.exists():
        return
    try:
        info = json.loads(lock_file.read_text(encoding="utf-8"))
        if info.get("hostname") == _get_hostname():
            lock_file.unlink(missing_ok=True)
            logger.info("Cloud-Lockdatei sauber entfernt.")
    except Exception as e:
        logger.warning(f"Fehler beim Entfernen der Cloud-Lockdatei: {e}")


def build_cloud_config_payload(sync_imap: bool) -> Dict[str, Any]:
    """Build the configuration dictionary to store in cloud_config.json."""
    payload: Dict[str, Any] = {
        "updated_at": _now_iso(),
        "updated_by": _get_hostname(),
        "club": {
            "CLUB_NAME": settings.CLUB_NAME,
            "CLUB_SHORT": settings.CLUB_SHORT,
            "CLUB_KEYWORDS": settings.CLUB_KEYWORDS,
        },
        "sync_imap": bool(sync_imap),
    }
    if sync_imap:
        payload["imap"] = {
            "IMAP_ENABLED": settings.IMAP_ENABLED,
            "IMAP_SERVER": settings.IMAP_SERVER,
            "IMAP_PORT": settings.IMAP_PORT,
            "IMAP_USER": settings.IMAP_USER,
            "IMAP_PASSWORD": settings.IMAP_PASSWORD,
            "IMAP_MAILBOX": settings.IMAP_MAILBOX,
            "IMAP_FETCH_INTERVAL_MINUTES": settings.IMAP_FETCH_INTERVAL_MINUTES,
            "IMAP_ALLOWED_SENDERS": settings.IMAP_ALLOWED_SENDERS,
            "IMAP_MOCK": settings.IMAP_MOCK,
        }
    return payload


def apply_cloud_config_to_local(cloud_dir: Path) -> Tuple[bool, bool]:
    """
    Read cloud_config.json from cloud_dir and apply club settings (and optionally IMAP settings)
    to local settings & .env.
    Returns (club_applied, imap_applied).
    """
    cfg_file = cloud_dir / CLOUD_CONFIG_FILENAME
    if not cfg_file.exists():
        return False, False

    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Konnte cloud_config.json nicht lesen: {e}")
        return False, False

    env_updates: Dict[str, str] = {}
    club_applied = False
    imap_applied = False

    club = data.get("club")
    if isinstance(club, dict) and club.get("CLUB_NAME"):
        settings.CLUB_NAME = str(club.get("CLUB_NAME", settings.CLUB_NAME))
        settings.CLUB_SHORT = str(club.get("CLUB_SHORT", settings.CLUB_SHORT))
        settings.CLUB_KEYWORDS = str(club.get("CLUB_KEYWORDS", settings.CLUB_KEYWORDS))
        env_updates["CLUB_NAME"] = settings.CLUB_NAME
        env_updates["CLUB_SHORT"] = settings.CLUB_SHORT
        env_updates["CLUB_KEYWORDS"] = settings.CLUB_KEYWORDS
        club_applied = True

    imap = data.get("imap")
    if isinstance(imap, dict):
        settings.IMAP_ENABLED = bool(imap.get("IMAP_ENABLED", settings.IMAP_ENABLED))
        settings.IMAP_SERVER = str(imap.get("IMAP_SERVER", settings.IMAP_SERVER))
        settings.IMAP_PORT = int(imap.get("IMAP_PORT", settings.IMAP_PORT))
        settings.IMAP_USER = str(imap.get("IMAP_USER", settings.IMAP_USER))
        if imap.get("IMAP_PASSWORD") is not None:
            settings.IMAP_PASSWORD = str(imap.get("IMAP_PASSWORD"))
            env_updates["IMAP_PASSWORD"] = settings.IMAP_PASSWORD
        settings.IMAP_MAILBOX = str(imap.get("IMAP_MAILBOX", settings.IMAP_MAILBOX))
        settings.IMAP_FETCH_INTERVAL_MINUTES = int(imap.get("IMAP_FETCH_INTERVAL_MINUTES", settings.IMAP_FETCH_INTERVAL_MINUTES))
        settings.IMAP_ALLOWED_SENDERS = str(imap.get("IMAP_ALLOWED_SENDERS", settings.IMAP_ALLOWED_SENDERS))
        settings.IMAP_MOCK = bool(imap.get("IMAP_MOCK", settings.IMAP_MOCK))

        env_updates.update({
            "IMAP_ENABLED": "true" if settings.IMAP_ENABLED else "false",
            "IMAP_SERVER": settings.IMAP_SERVER,
            "IMAP_PORT": str(settings.IMAP_PORT),
            "IMAP_USER": settings.IMAP_USER,
            "IMAP_MAILBOX": settings.IMAP_MAILBOX,
            "IMAP_FETCH_INTERVAL_MINUTES": str(settings.IMAP_FETCH_INTERVAL_MINUTES),
            "IMAP_ALLOWED_SENDERS": settings.IMAP_ALLOWED_SENDERS,
            "IMAP_MOCK": "true" if settings.IMAP_MOCK else "false",
        })
        imap_applied = True

    if env_updates:
        try:
            config_service.update_env_file(env_updates)
        except Exception as e:
            logger.warning(f"Konnte lokale .env nicht aus Cloud-Config aktualisieren: {e}")

    return club_applied, imap_applied


def _sqlite_safe_copy(src_db: Path, dst_db: Path, single_file_journal: bool = False) -> None:
    """
    Use SQLite online backup API to copy src_db to dst_db safely and atomically,
    even if WAL files are present on src_db.
    """
    dst_db.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst_db.parent / f".{dst_db.name}.tmp.{os.getpid()}"
    if tmp_dst.exists():
        tmp_dst.unlink(missing_ok=True)

    src_conn = sqlite3.connect(str(src_db), timeout=10.0)
    dst_conn = sqlite3.connect(str(tmp_dst), timeout=10.0)
    try:
        src_conn.backup(dst_conn)
        if single_file_journal:
            dst_conn.execute("PRAGMA journal_mode=DELETE;")
            dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()

    os.replace(str(tmp_dst), str(dst_db))


def pull_from_cloud(force_lock: bool = False) -> Dict[str, Any]:
    """
    Working-Copy Startup:
    If cloud storage mode is enabled, copy adsi.db and cloud_config.json from the cloud folder
    into the local working copy (data/adsi.db).
    If the cloud folder does not yet have adsi.db, initialize the cloud folder from the local DB.
    """
    cfg = load_storage_settings()
    if cfg.get("storage_mode") != "cloud" or not cfg.get("cloud_dir"):
        _RUNTIME_STATE["lock_conflict"] = False
        _RUNTIME_STATE["lock_holder"] = None
        _RUNTIME_STATE["read_only_cloud"] = False
        return {"status": "local", "message": "Lokaler Speichermodus aktiv."}

    cloud_dir = Path(cfg["cloud_dir"])
    try:
        cloud_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        msg = f"Cloud-Ordner '{cloud_dir}' ist nicht erreichbar: {e}"
        _RUNTIME_STATE["last_cloud_error"] = msg
        logger.error(msg)
        return {"status": "error", "message": msg}

    # Acquire or check lock
    acquired, holder = acquire_cloud_lock(cloud_dir, force=force_lock)

    cloud_db = cloud_dir / CLOUD_DB_FILENAME
    local_db = Path(settings.DATABASE_PATH).resolve()
    local_db.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Pull cloud_config.json if it exists
        club_applied, imap_applied = apply_cloud_config_to_local(cloud_dir)
        if imap_applied and not cfg.get("sync_imap"):
            cfg["sync_imap"] = True

        # 2. Pull or seed database
        if cloud_db.exists() and cloud_db.stat().st_size > 0:
            _sqlite_safe_copy(cloud_db, local_db, single_file_journal=False)
            logger.info(f"Datenbank-Arbeitskopie erfolgreich aus Cloud geladen: {cloud_db}")
            action = "pulled"
        else:
            # Cloud folder is empty -> if we have a local DB and write permission, seed the cloud folder
            if local_db.exists() and not _RUNTIME_STATE["read_only_cloud"]:
                _sqlite_safe_copy(local_db, cloud_db, single_file_journal=True)
                cfg_payload = build_cloud_config_payload(sync_imap=bool(cfg.get("sync_imap", False)))
                (cloud_dir / CLOUD_CONFIG_FILENAME).write_text(
                    json.dumps(cfg_payload, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                logger.info(f"Lokale Datenbank initial in den Cloud-Ordner übertragen: {cloud_db}")
            action = "seeded"

        now_str = _now_iso()
        cfg["last_sync"] = now_str
        save_storage_settings(cfg)
        _RUNTIME_STATE["last_cloud_sync"] = now_str
        _RUNTIME_STATE["last_cloud_error"] = None

        return {
            "status": "ok",
            "action": action,
            "lock_acquired": acquired,
            "lock_holder": holder,
            "club_applied": club_applied,
            "imap_applied": imap_applied,
            "last_sync": now_str,
        }
    except Exception as e:
        msg = f"Fehler beim Laden aus dem Cloud-Ordner: {e}"
        _RUNTIME_STATE["last_cloud_error"] = msg
        logger.error(msg)
        return {"status": "error", "message": msg}


def push_to_cloud(reason: str = "manual") -> Dict[str, Any]:
    """
    Working-Copy Sync Back:
    Safely export the local working database (data/adsi.db) and cloud_config.json
    as clean single-file snapshots into the configured cloud folder.
    """
    cfg = load_storage_settings()
    if cfg.get("storage_mode") != "cloud" or not cfg.get("cloud_dir"):
        return {"status": "local", "message": "Lokaler Speichermodus aktiv (kein Cloud-Push erforderlich)."}

    if _RUNTIME_STATE.get("read_only_cloud"):
        msg = "Cloud-Synchronisation übersprungen (Nur-Lesen-Modus wegen aktiver Sitzung auf anderem Gerät)."
        logger.warning(msg)
        return {"status": "read_only", "message": msg}

    cloud_dir = Path(cfg["cloud_dir"])
    local_db = Path(settings.DATABASE_PATH).resolve()

    if not local_db.exists():
        return {"status": "skipped", "message": "Lokale Datenbank existiert noch nicht."}

    try:
        cloud_dir.mkdir(parents=True, exist_ok=True)
        cloud_db = cloud_dir / CLOUD_DB_FILENAME

        # 1. Copy local SQLite DB to cloud folder as clean single-file DB (journal_mode=DELETE)
        _sqlite_safe_copy(local_db, cloud_db, single_file_journal=True)

        # 2. Save cloud_config.json (Club always + IMAP if sync_imap=True)
        cfg_payload = build_cloud_config_payload(sync_imap=bool(cfg.get("sync_imap", False)))
        (cloud_dir / CLOUD_CONFIG_FILENAME).write_text(
            json.dumps(cfg_payload, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # 3. Refresh heartbeat in lock file
        lock_file = cloud_dir / CLOUD_LOCK_FILENAME
        lock_data = {
            "hostname": _get_hostname(),
            "pid": os.getpid(),
            "started_at": (_RUNTIME_STATE.get("lock_holder") or {}).get("started_at") or _now_iso(),
            "updated_at": _now_iso(),
        }
        lock_file.write_text(json.dumps(lock_data, indent=2, ensure_ascii=False), encoding="utf-8")

        now_str = _now_iso()
        cfg["last_sync"] = now_str
        save_storage_settings(cfg)
        _RUNTIME_STATE["last_cloud_sync"] = now_str
        _RUNTIME_STATE["last_cloud_error"] = None

        logger.info(f"Cloud-Backup erfolgreich abgeschlossen ({reason}) -> {cloud_db}")
        return {
            "status": "ok",
            "last_sync": now_str,
            "cloud_dir": str(cloud_dir),
            "message": f"Datenbank & Einstellungen erfolgreich in den Cloud-Ordner synchronisiert ({now_str})."
        }
    except Exception as e:
        msg = f"Fehler beim Schreiben in den Cloud-Ordner ({reason}): {e}"
        _RUNTIME_STATE["last_cloud_error"] = msg
        logger.error(msg)
        return {"status": "error", "message": msg}


def configure_storage(
    storage_mode: str,
    cloud_dir: str = "",
    sync_imap: bool = False,
    force_lock: bool = False,
) -> Dict[str, Any]:
    """
    Update storage settings (from First-Run Wizard or Admin Center).
    When switching to cloud mode:
      - If the selected cloud folder already contains an `adsi.db`, pulls it (and `cloud_config.json`)
        into the local working copy and recalculates club highlights.
      - Otherwise, pushes the current local working copy into the cloud folder.
    """
    old_cfg = load_storage_settings()
    old_mode = old_cfg.get("storage_mode")
    old_dir = old_cfg.get("cloud_dir")

    # Release lock in previous cloud folder if switching away
    if old_mode == "cloud" and old_dir and (storage_mode != "cloud" or old_dir != cloud_dir):
        release_cloud_lock(Path(old_dir))

    norm_mode = "cloud" if storage_mode == "cloud" else "local"
    clean_dir = cloud_dir.strip() if norm_mode == "cloud" else ""

    if norm_mode == "cloud":
        if not clean_dir:
            raise ValueError("Bitte wähle einen gültigen Cloud-Ordner aus.")
        target_path = Path(clean_dir).expanduser().resolve()
        target_path.mkdir(parents=True, exist_ok=True)
        clean_dir = str(target_path)

    new_cfg = {
        "setup_completed": True,
        "storage_mode": norm_mode,
        "cloud_dir": clean_dir,
        "sync_imap": bool(sync_imap),
        "last_sync": old_cfg.get("last_sync"),
    }
    save_storage_settings(new_cfg)

    if norm_mode == "local":
        _RUNTIME_STATE["lock_conflict"] = False
        _RUNTIME_STATE["lock_holder"] = None
        _RUNTIME_STATE["read_only_cloud"] = False
        return get_storage_status()

    # In cloud mode: check if cloud folder already has an existing adsi.db
    target_path = Path(clean_dir)
    cloud_db = target_path / CLOUD_DB_FILENAME
    if cloud_db.exists() and cloud_db.stat().st_size > 0:
        pull_from_cloud(force_lock=force_lock)
        try:
            from app.services.teilnehmer_scraper import recalculate_teilnehmer_club_matches
            recalculate_teilnehmer_club_matches()
        except Exception as e:
            logger.warning(f"Teilnehmer-Neuberechnung nach Cloud-Pull fehlgeschlagen: {e}")
        # If the user just enabled sync_imap or changed settings and we have write lock, also update cloud_config.json
        if not _RUNTIME_STATE.get("read_only_cloud"):
            push_to_cloud(reason="config_update")
    else:
        acquire_cloud_lock(target_path, force=force_lock)
        push_to_cloud(reason="initial_seed")

    return get_storage_status()


def resolve_lock_conflict(action: str) -> Dict[str, Any]:
    """
    Resolve a multi-PC lock conflict:
      - action == "read_only": keep read_only_cloud = True, dismiss warning banner
      - action == "takeover": force-acquire the lock file and disable read_only_cloud
    """
    cfg = load_storage_settings()
    if cfg.get("storage_mode") != "cloud" or not cfg.get("cloud_dir"):
        return get_storage_status()

    cloud_dir = Path(cfg["cloud_dir"])
    if action == "takeover":
        acquire_cloud_lock(cloud_dir, force=True)
        pull_from_cloud(force_lock=True)
    else:
        # Acknowledge read-only mode
        _RUNTIME_STATE["lock_conflict"] = False
        _RUNTIME_STATE["read_only_cloud"] = True

    return get_storage_status()


def get_storage_status() -> Dict[str, Any]:
    """Return full status of local & cloud storage for UI and Admin Center."""
    cfg = load_storage_settings()
    local_db = Path(settings.DATABASE_PATH).resolve()
    cloud_dir_str = cfg.get("cloud_dir") or ""
    cloud_db_exists = False
    cloud_config_exists = False

    if cfg.get("storage_mode") == "cloud" and cloud_dir_str:
        cpath = Path(cloud_dir_str)
        cloud_db_exists = (cpath / CLOUD_DB_FILENAME).exists()
        cloud_config_exists = (cpath / CLOUD_CONFIG_FILENAME).exists()

    return {
        "setup_completed": bool(cfg.get("setup_completed", False)),
        "storage_mode": cfg.get("storage_mode", "local"),
        "cloud_dir": cloud_dir_str,
        "sync_imap": bool(cfg.get("sync_imap", False)),
        "local_db_path": str(local_db),
        "cloud_db_exists": cloud_db_exists,
        "cloud_config_exists": cloud_config_exists,
        "last_sync": _RUNTIME_STATE.get("last_cloud_sync") or cfg.get("last_sync"),
        "last_error": _RUNTIME_STATE.get("last_cloud_error"),
        "lock_conflict": bool(_RUNTIME_STATE.get("lock_conflict", False)),
        "lock_holder": _RUNTIME_STATE.get("lock_holder"),
        "read_only_cloud": bool(_RUNTIME_STATE.get("read_only_cloud", False)),
        "detected_providers": detect_cloud_providers(),
    }


def shutdown_storage() -> None:
    """Called when the application window closes or the FastAPI server shuts down."""
    cfg = load_storage_settings()
    if cfg.get("storage_mode") == "cloud" and cfg.get("cloud_dir"):
        if not _RUNTIME_STATE.get("read_only_cloud"):
            push_to_cloud(reason="shutdown")
        release_cloud_lock(Path(cfg["cloud_dir"]))


def open_native_folder_dialog(initial_dir: str = "") -> Optional[str]:
    """
    Open a native OS folder selection dialog:
    1. If running inside pywebview, use window.create_file_dialog(webview.FOLDER_DIALOG).
    2. On macOS fallback to osascript (`choose folder`).
    3. On Windows fallback to PowerShell FolderBrowserDialog.
    """
    window = _RUNTIME_STATE.get("webview_window")
    if window is not None:
        try:
            import webview
            dialog_type = getattr(webview, "FOLDER_DIALOG", 20)
            kwargs = {}
            if initial_dir and Path(initial_dir).exists():
                kwargs["directory"] = initial_dir
            result = window.create_file_dialog(dialog_type, **kwargs)
            if result:
                chosen = result[0] if isinstance(result, (list, tuple)) else str(result)
                if chosen:
                    return str(Path(chosen) / CLOUD_SUBFOLDER_NAME) if Path(chosen).name != CLOUD_SUBFOLDER_NAME else str(chosen)
            return None
        except Exception as e:
            logger.warning(f"pywebview Folder-Dialog Fallback: {e}")

    if sys.platform == "darwin":
        try:
            script = 'POSIX path of (choose folder with prompt "Wähle den Cloud-Ordner (z.B. iCloud Drive, Google Drive, OneDrive) für das pivitLABS ÖTSV Tool:")'
            out = subprocess.check_output(["osascript", "-e", script], text=True, timeout=120).strip()
            if out:
                chosen_path = Path(out)
                if chosen_path.name != CLOUD_SUBFOLDER_NAME and not (chosen_path / CLOUD_DB_FILENAME).exists():
                    return str(chosen_path / CLOUD_SUBFOLDER_NAME)
                return str(chosen_path)
        except Exception:
            return None
    elif sys.platform == "win32":
        try:
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = 'Cloud-Ordner fuer pivitLABS OETSV Tool waehlen'; "
                "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
            )
            out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps_script], text=True, timeout=120).strip()
            if out:
                chosen_path = Path(out)
                if chosen_path.name != CLOUD_SUBFOLDER_NAME and not (chosen_path / CLOUD_DB_FILENAME).exists():
                    return str(chosen_path / CLOUD_SUBFOLDER_NAME)
                return str(chosen_path)
        except Exception:
            return None

    return None
