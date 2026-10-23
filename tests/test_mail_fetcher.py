import pytest
from app.services.mail_fetcher import parse_nennung_content, save_nennung_atomic
from app.database import get_db_connection, init_db

SAMPLE_CONFIRMATION_EMAIL = """
Liebes Paar Max Mustermann & Maria Mustermann,

vielen Dank für Ihre Nennung.
Ihre Nennungs-ID lautet N-2026-98765

Hier sind die Details Ihrer Nennung:
MIN Partner:in 1: 45012 / MIN Partner:in 2: 45013
Klub: TSC Musterverein
Turnier-Nr: TASNr=1777

Gemeldete Klassen:
19.09.2026: Allg. Kl. Standard B
19.09.2026: Allg. Kl. Latein B

Mit sportlichen Grüßen,
ÖTSV Meldewesen
"""

SAMPLE_CONFIRMATION_EMAIL_VARIANT = """
Liebes Paar Max Mustermann und Maria Mustermann
Ihre Nennungs-ID lautet N-112233
MIN Partner 1: 99001
MIN Partner 2: 99002
Klub: TSC Forum Wien
TASNr=1780

12.10.2026: Sen. II Standard A
"""

def test_parse_nennung_content():
    data = parse_nennung_content(SAMPLE_CONFIRMATION_EMAIL)
    assert data is not None
    assert data["paar_name"] == "Max Mustermann & Maria Mustermann"
    assert data["nennungs_id"] == "N-2026-98765"
    assert data["min_partner_1"] == "45012"
    assert data["min_partner_2"] == "45013"
    assert data["klub"] == "TSC Musterverein"
    assert data["turnier_id"] == 1777
    assert len(data["klassen"]) == 2
    assert data["klassen"][0] == ("19.09.2026", "Allg. Kl. Standard B")
    assert data["klassen"][1] == ("19.09.2026", "Allg. Kl. Latein B")

def test_parse_nennung_content_variant():
    data = parse_nennung_content(SAMPLE_CONFIRMATION_EMAIL_VARIANT)
    assert data is not None
    assert data["paar_name"] == "Max Mustermann und Maria Mustermann"
    assert data["nennungs_id"] == "N-112233"
    assert data["min_partner_1"] == "99001"
    assert data["min_partner_2"] == "99002"
    assert data["turnier_id"] == 1780
    assert len(data["klassen"]) == 1
    assert data["klassen"][0] == ("12.10.2026", "Sen. II Standard A")

REAL_USER_SAMPLE_EMAIL = """
Fwd: Nennungsbestätigung (Sammelbestätigung) 20.09.2026 - Tiroler Meisterschaft Senioren (LFV Tirol)
Posteingang
Turnierwart Verein <turniere@mein-tanzklub.at>
Mo., 7. Sept., 23:20 (vor 4 Tagen)
an mich
------- Weitergeleitete Nachricht ------
Von: <nennungen@oetsv.at>
Datum: So. 6. Sep. 2026 um 19:54
Betreff: Nennungsbestätigung (Sammelbestätigung) 20.09.2026 - Tiroler Meisterschaft Senioren (LFV Tirol)
An: turniere@mein-tanzklub.at <turniere@mein-tanzklub.at>
Liebes Paar Max Mustermann - Maria Mustermann,Ihre Nennungs-ID lautet 39002
MIN Partner:in 1: 10001 / MIN Partner:in 2: 10002
Nation:
Klub: Musterverein
Folgende Eintragungen wurden gespeichert (06.09.2026 / 19:54):
20. 09. 2026: Sen. III La C
20. 09. 2026: Sen. III Sta C
20. 09. 2026: Sen. IV La C
20. 09. 2026: Sen. IV Sta C
Um Ihre Nennung zu verändern folgen Sie bitte folgendem Link:
https://www.tanzsportverband.at/portal/nennungen/nennungen.php?entryid=00000000000000000000000000000000&lang=DE&TASNr=1778&source=mail
Mehr Informationen über diese Veranstaltung finden Sie auf http://www.tsc-kufstein.at.
Wir freuen uns, dass Sie an unserem Turnier teilnehmen werden und verbleiben bis dahin
mit freundlichen Grüßen
Ihr turnier@tsc-kufstein.at
"""

def test_parse_real_user_sample_email():
    data = parse_nennung_content(REAL_USER_SAMPLE_EMAIL)
    assert data is not None
    assert data["paar_name"] == "Max Mustermann & Maria Mustermann"
    assert data["nennungs_id"] == "39002"
    assert data["min_partner_1"] == "10001"
    assert data["min_partner_2"] == "10002"
    assert data["klub"] == "TSC Musterverein"
    assert data["turnier_id"] == 1778
    assert len(data["klassen"]) == 4
    assert data["klassen"][0] == ("20.09.2026", "Sen. III La C")
    assert data["klassen"][1] == ("20.09.2026", "Sen. III Sta C")
    assert data["klassen"][2] == ("20.09.2026", "Sen. IV La C")
    assert data["klassen"][3] == ("20.09.2026", "Sen. IV Sta C")

def test_strict_sender_whitelist():
    from app.services.mail_fetcher import is_sender_whitelisted
    allowed = ["noreply@tanzsportverband.at", "oetsv.at"]
    assert is_sender_whitelisted("noreply@tanzsportverband.at", allowed) is True
    assert is_sender_whitelisted("nennungen@oetsv.at", allowed) is True
    assert is_sender_whitelisted("mail@sub.oetsv.at", allowed) is True
    # Substring bypass attempts must fail
    assert is_sender_whitelisted("fake-oetsv.at@evil.com", allowed) is False
    assert is_sender_whitelisted("attacker@not-oetsv.at", allowed) is False
    assert is_sender_whitelisted("noreply@tanzsportverband.at.evil.com", allowed) is False


def test_save_nennung_atomic(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr("app.database.get_db_path", lambda: test_db)
    init_db()

    # Pre-insert tournament with turnier_id 1777
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO turniere (turnier_id, datum, datum_sort, titel, klub, bundesland)
            VALUES (1777, '19.09.2026', '2026-09-19', 'Tiroler Meisterschaft', 'TSC Kufstein', 'Tirol');
        """)
        conn.commit()

    data = parse_nennung_content(SAMPLE_CONFIRMATION_EMAIL)
    assert data is not None

    # First save -> True
    saved = save_nennung_atomic(data)
    assert saved is True

    # Check relational link
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, turnier_db_id FROM nennungen WHERE nennungs_id = 'N-2026-98765';")
        row = cursor.fetchone()
        assert row is not None
        assert row["turnier_db_id"] is not None

        cursor.execute("SELECT COUNT(*) as cnt FROM nennungs_klassen WHERE nennung_db_id = ?;", (row["id"],))
        assert cursor.fetchone()["cnt"] == 2

    # Duplicate save -> False (Idempotency)
    saved_again = save_nennung_atomic(data)
    assert saved_again is False

def test_run_mock_mail_fetcher(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_mock.db")
    monkeypatch.setattr("app.database.get_db_path", lambda: test_db)
    monkeypatch.setattr("app.config.settings.IMAP_MOCK", True)
    monkeypatch.setattr("app.config.settings.IMAP_ALLOWED_SENDERS", "noreply@tanzsportverband.at,office@tanzsportverband.at,nennungen@tanzsportverband.at")
    init_db()

    from app.services.mail_fetcher import run_mail_fetcher
    res = run_mail_fetcher()
    assert res["status"] == "success"
    assert res["mode"] == "mock"
    assert res["added_count"] == 3

    # Verify rows in DB
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM nennungen;")
        assert cursor.fetchone()["cnt"] == 3

