import json
import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import init_db, get_db_connection
from app.services import storage_service


def test_working_copy_cloud_seed_and_pull(tmp_path, monkeypatch):
    """
    Verify Working-Copy Principle:
    1. Configure cloud folder when local DB has data -> seeds adsi.db and cloud_config.json into cloud folder.
    2. Club settings are always stored in cloud_config.json; IMAP settings only when sync_imap=True.
    3. Pulling from cloud into a fresh local DB restores both tournament data and club/IMAP settings.
    """
    local_db = tmp_path / "local_data" / "adsi.db"
    cloud_dir = tmp_path / "icloud_drive" / "pivitLABS-OETSV-Tool"
    env_file = tmp_path / ".env"

    monkeypatch.setattr(settings, "DATABASE_PATH", str(local_db))
    monkeypatch.setattr("app.database.get_db_path", lambda: str(local_db))
    monkeypatch.setattr("app.services.config_service.update_env_file", lambda kv, env_path=str(env_file): None)

    init_db()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO turniere (turnier_id, datum, datum_sort, titel, klub, bundesland) VALUES (999, '01.11.2026', '2026-11-01', 'Cloud Test Turnier', 'TSC Cloud', 'Wien');"
        )
        conn.commit()

    settings.CLUB_NAME = "UTSC Dance"
    settings.CLUB_SHORT = "UTSC"
    settings.IMAP_SERVER = "imap.utsc.at"
    settings.IMAP_USER = "nennungen@utsc.at"

    # 1. Configure cloud mode with sync_imap=False (default: only DB + Club info)
    st = storage_service.configure_storage(
        storage_mode="cloud",
        cloud_dir=str(cloud_dir),
        sync_imap=False,
    )
    assert st["storage_mode"] == "cloud"
    assert (cloud_dir / "adsi.db").exists()
    assert (cloud_dir / "cloud_config.json").exists()
    assert (cloud_dir / "adsi.lock").exists()

    cloud_cfg_1 = json.loads((cloud_dir / "cloud_config.json").read_text(encoding="utf-8"))
    assert cloud_cfg_1["club"]["CLUB_NAME"] == "UTSC Dance"
    assert "imap" not in cloud_cfg_1

    # 2. Enable sync_imap=True -> IMAP settings are now included in cloud_config.json
    st2 = storage_service.configure_storage(
        storage_mode="cloud",
        cloud_dir=str(cloud_dir),
        sync_imap=True,
    )
    assert st2["sync_imap"] is True
    cloud_cfg_2 = json.loads((cloud_dir / "cloud_config.json").read_text(encoding="utf-8"))
    assert "imap" in cloud_cfg_2
    assert cloud_cfg_2["imap"]["IMAP_SERVER"] == "imap.utsc.at"

    # 3. Simulate a second machine connecting to the same cloud folder after first machine shuts down
    storage_service.shutdown_storage()
    assert not (cloud_dir / "adsi.lock").exists()

    second_local_db = tmp_path / "pc2_data" / "adsi.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(second_local_db))
    monkeypatch.setattr("app.database.get_db_path", lambda: str(second_local_db))
    settings.CLUB_NAME = "TSC Musterverein"
    settings.IMAP_SERVER = ""

    pull_res = storage_service.pull_from_cloud()
    assert pull_res["status"] == "ok"
    assert pull_res["action"] == "pulled"
    assert settings.CLUB_NAME == "UTSC Dance"
    assert settings.IMAP_SERVER == "imap.utsc.at"

    with sqlite3.connect(str(second_local_db)) as conn2:
        row = conn2.execute("SELECT titel FROM turniere WHERE turnier_id = 999;").fetchone()
        assert row is not None
        assert row[0] == "Cloud Test Turnier"


def test_multi_device_lock_conflict_and_resolution(tmp_path, monkeypatch):
    """Verify that a lock held by another machine triggers read-only cloud mode until resolved."""
    local_db = tmp_path / "local" / "adsi.db"
    cloud_dir = tmp_path / "gdrive" / "pivitLABS-OETSV-Tool"
    cloud_dir.mkdir(parents=True)

    monkeypatch.setattr(settings, "DATABASE_PATH", str(local_db))
    monkeypatch.setattr("app.database.get_db_path", lambda: str(local_db))
    init_db()

    # Simulate another machine holding adsi.lock
    foreign_lock = {
        "hostname": "MacBook-Trainer",
        "pid": 999999,
        "started_at": "25.10.2026 08:30:00",
        "updated_at": "25.10.2026 08:35:00",
    }
    (cloud_dir / "adsi.lock").write_text(json.dumps(foreign_lock), encoding="utf-8")

    st = storage_service.configure_storage(storage_mode="cloud", cloud_dir=str(cloud_dir), sync_imap=False)
    assert st["lock_conflict"] is True
    assert st["read_only_cloud"] is True
    assert st["lock_holder"]["hostname"] == "MacBook-Trainer"

    # While in read-only mode, push_to_cloud must not overwrite the cloud folder
    push_res = storage_service.push_to_cloud(reason="test")
    assert push_res["status"] == "read_only"

    # Resolve via takeover
    resolved = storage_service.resolve_lock_conflict("takeover")
    assert resolved["lock_conflict"] is False
    assert resolved["read_only_cloud"] is False


def test_pwa_manifest_and_storage_endpoints(tmp_path, monkeypatch):
    """Verify PWA manifest, service worker, and storage API endpoints respond properly."""
    local_db = tmp_path / "api_test.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(local_db))
    monkeypatch.setattr("app.database.get_db_path", lambda: str(local_db))
    init_db()

    with TestClient(app) as client:
        res_manifest = client.get("/manifest.webmanifest")
        assert res_manifest.status_code == 200
        assert res_manifest.json()["display"] == "standalone"

        res_sw = client.get("/sw.js")
        assert res_sw.status_code == 200
        assert "CACHE_NAME" in res_sw.text

        res_setup = client.get("/api/storage-setup")
        assert res_setup.status_code == 200
        assert res_setup.json()["storage_mode"] == "local"

        res_admin_storage = client.get("/adsi-admin/api/config/storage")
        assert res_admin_storage.status_code == 200
        assert "detected_providers" in res_admin_storage.json()
