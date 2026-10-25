import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db_connection, init_db
from app.scheduler import ACTIVE_JOBS

@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_api.db")
    monkeypatch.setattr("app.database.get_db_path", lambda: test_db)
    init_db()

    # Seed test data
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO turniere (id, turnier_id, datum, datum_sort, titel, klub, bundesland, tags, links)
            VALUES (1, 555, '15.10.2026', '2026-10-15', 'Herbstturnier Wien', 'TSC Musterverein', 'Wien', '["Standard", "Latein"]', '{"homepage":"https://example.com"}');
        """)
        cursor.execute("""
            INSERT INTO turniere (id, turnier_id, datum, datum_sort, titel, klub, bundesland, tags, links)
            VALUES (2, 777, '10.01.2020', '2020-01-10', 'Altes Turnier', 'Klub Alt', 'Tirol', '["Latein"]', '{}');
        """)
        cursor.execute("""
            INSERT INTO nennungen (id, nennungs_id, paar_name, min_partner_1, min_partner_2, klub, turnier_id, turnier_db_id)
            VALUES (1, 'NEN-1', 'Max Mustermann & Maria Mustermann', '101', '102', 'TSC Musterverein', 555, 1);
        """)
        cursor.execute("""
            INSERT INTO nennungs_klassen (id, nennung_db_id, datum, klasse)
            VALUES (1, 1, '15.10.2026', 'Allg. Kl. Latein A');
        """)
        conn.commit()

    with TestClient(app) as c:
        yield c

def test_static_html_served(client):
    # Main portal
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "pivitLABS ÖTSV Tool" in res_index.text
    assert "https://pivitlabs.com" in res_index.text
    assert "Disclaimer" in res_index.text

    # Admin portal
    res_admin = client.get("/adsi-admin")
    assert res_admin.status_code == 200
    assert "Admin Control Center" in res_admin.text
    assert "Verein einstellen" in res_admin.text
    assert "https://pivitlabs.com" in res_admin.text

def test_api_version(client):
    res = client.get("/api/version")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["backend"] == "FastAPI"

def test_api_turniere_includes_paare(client):
    res = client.get("/api/turniere?only_current_year=false")
    assert res.status_code == 200
    turniere = res.json()
    assert len(turniere) == 2

    t = next(item for item in turniere if item["id"] == 1)
    assert t["titel"] == "Herbstturnier Wien"
    assert t["utsc_paare_anzahl"] == 1
    assert len(t["utsc_paare"]) == 1

    paar = t["utsc_paare"][0]
    assert paar["paar_name"] == "Max Mustermann & Maria Mustermann"
    assert paar["min_partner_1"] == "101"
    assert len(paar["klassen"]) == 1
    assert paar["klassen"][0]["klasse"] == "Allg. Kl. Latein A"

def test_api_turniere_only_current_year(client):
    res = client.get("/api/turniere?only_current_year=true")
    assert res.status_code == 200
    turniere = res.json()
    # Should exclude tournament from 2020
    ids = [t["id"] for t in turniere]
    assert 1 in ids
    assert 2 not in ids

def test_api_sync_status(client):
    res = client.get("/api/sync-status")
    assert res.status_code == 200
    data = res.json()
    keys = [item["key"] for item in data]
    assert "scraper" in keys
    assert "fetcher" in keys

def test_admin_api_status(client):
    res = client.get("/adsi-admin/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["turniere_gesamt"] == 2
    assert data["nennungen_gesamt"] == 1
    assert data["klassen_gesamt"] == 1

def test_admin_api_data(client):
    res = client.get("/adsi-admin/api/data")
    assert res.status_code == 200
    data = res.json()
    assert len(data["turniere"]) == 2
    assert len(data["nennungen"]) == 1

def test_admin_api_logs(client):
    res = client.get("/adsi-admin/api/logs?target=system")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)

def test_admin_trigger_invalid_job(client):
    res = client.post("/adsi-admin/api/trigger/invalid_job")
    assert res.status_code == 400

def test_admin_trigger_job_lock(client):
    # Simulate already running job
    ACTIVE_JOBS["scraper"] = True
    try:
        res = client.post("/adsi-admin/api/trigger/scraper")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "already_running"
    finally:
        ACTIVE_JOBS["scraper"] = False

def test_admin_changelog(client):
    res = client.get("/adsi-admin/api/changelog")
    assert res.status_code == 200
    changelog = res.json()
    assert len(changelog) >= 1
    assert changelog[0]["version"] == "1.5.0"

def test_admin_password_protection(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.ADMIN_PASSWORD", "super_secret_admin_pw")
    # Unauthenticated request -> 401
    res_unauth = client.get("/adsi-admin/api/status")
    assert res_unauth.status_code == 401

    # Wrong password -> 401
    res_wrong = client.get("/adsi-admin/api/status", auth=("admin", "wrong"))
    assert res_wrong.status_code == 401

    # Correct password -> 200
    res_ok = client.get("/adsi-admin/api/status", auth=("admin", "super_secret_admin_pw"))
    assert res_ok.status_code == 200

def test_admin_imap_test_blocks_password_exfiltration_on_server_change(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.IMAP_SERVER", "imap.my-club.at")
    monkeypatch.setattr("app.config.settings.IMAP_PORT", 993)
    monkeypatch.setattr("app.config.settings.IMAP_USER", "turniere@my-club.at")
    monkeypatch.setattr("app.config.settings.IMAP_PASSWORD", "stored_secret_pw")

    # Attempt to test against a different server without providing a password
    payload = {
        "imap_enabled": True,
        "imap_server": "attacker.example.com",
        "imap_port": 993,
        "imap_user": "turniere@my-club.at",
        "imap_password": "",
        "imap_mailbox": "INBOX",
        "imap_fetch_interval_minutes": 15,
        "imap_allowed_senders": "oetsv.at",
        "imap_mock": False
    }
    res = client.post("/adsi-admin/api/config/imap/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "Sicherheitsgründen" in data["message"]

def test_admin_get_imap_config(client):
    res = client.get("/adsi-admin/api/config/imap")
    assert res.status_code == 200
    data = res.json()
    assert "imap_enabled" in data
    assert "imap_server" in data
    assert "has_password" in data

def test_admin_update_imap_config(client, monkeypatch):
    from app.config import settings
    orig_senders = settings.IMAP_ALLOWED_SENDERS
    orig_server = settings.IMAP_SERVER
    orig_user = settings.IMAP_USER
    orig_pwd = settings.IMAP_PASSWORD

    monkeypatch.setattr("app.services.config_service.update_env_file", lambda kv, **kwargs: None)
    payload = {
        "imap_enabled": True,
        "imap_server": "imap.test-verein.at",
        "imap_port": 993,
        "imap_user": "turniere@test-verein.at",
        "imap_password": "new_secret_password",
        "imap_mailbox": "INBOX",
        "imap_fetch_interval_minutes": 20,
        "imap_allowed_senders": "noreply@tanzsportverband.at",
        "imap_mock": False
    }
    try:
        res = client.post("/adsi-admin/api/config/imap", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["imap_enabled"] is True
        assert data["imap_server"] == "imap.test-verein.at"
        assert data["imap_user"] == "turniere@test-verein.at"
        assert data["has_password"] is True
    finally:
        settings.IMAP_ALLOWED_SENDERS = orig_senders
        settings.IMAP_SERVER = orig_server
        settings.IMAP_USER = orig_user
        settings.IMAP_PASSWORD = orig_pwd

def test_admin_test_imap_connection_mock(client):
    payload = {
        "imap_enabled": True,
        "imap_server": "imap.test.at",
        "imap_port": 993,
        "imap_user": "test@test.at",
        "imap_mailbox": "INBOX",
        "imap_fetch_interval_minutes": 15,
        "imap_allowed_senders": "noreply@tanzsportverband.at",
        "imap_mock": True
    }
    res = client.post("/adsi-admin/api/config/imap/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "Mock-Modus" in data["message"]

def test_admin_get_and_update_club_config(client, monkeypatch):
    from app.config import settings
    orig_name = settings.CLUB_NAME
    orig_short = settings.CLUB_SHORT
    orig_keywords = settings.CLUB_KEYWORDS

    monkeypatch.setattr("app.services.config_service.update_env_file", lambda kv, **kwargs: None)
    try:
        res_get = client.get("/adsi-admin/api/config/club")
        assert res_get.status_code == 200
        assert "club_name" in res_get.json()

        payload = {
            "club_name": "TSC Schwarz Gold Wien",
            "club_short": "Schwarz-Gold",
            "club_keywords": "schwarz, gold, wien"
        }
        res_post = client.post("/adsi-admin/api/config/club", json=payload)
        assert res_post.status_code == 200
        data = res_post.json()
        assert data["club_name"] == "TSC Schwarz Gold Wien"
        assert data["club_short"] == "Schwarz-Gold"
        assert data["effective_tokens"] == ["schwarz", "gold", "wien"]

        # Verify /api/version reflects new club
        res_ver = client.get("/api/version")
        assert res_ver.status_code == 200
        assert res_ver.json()["club_name"] == "TSC Schwarz Gold Wien"
        assert res_ver.json()["club_short"] == "Schwarz-Gold"
    finally:
        settings.CLUB_NAME = orig_name
        settings.CLUB_SHORT = orig_short
        settings.CLUB_KEYWORDS = orig_keywords


