import pytest
from starlette.testclient import TestClient
from app.main import app
from app.database import get_db_connection, init_db
from app.services.teilnehmer_scraper import (
    build_teilnehmer_url, is_utsc_linz, parse_teilnehmer_html, save_teilnehmer_entries
)

SAMPLE_HTML = """
<HTML>
<HEAD>
<title>Nennungen</title>
</HEAD>
<BODY>
<div align='center'><h2>
Teilnehmerliste - 10.10.2026 - Landesmeisterschaft Standard Oberösterreich
</h2>
<table width='100%'>Bisher sind <b>5</b> Anmeldungen von 5 Paaren/Personen eingelangt<p>
<tr>
<td colspan=4 bgcolor=#FFFFBB><b><i>Allg.Kl. Sta B</b></i></td>
</tr>
<tr><td width='4%' align='right'>&nbsp;</td><td width='4%'>&nbsp;</td><td width='45%'>Clemens Kern - Viola Windsperger</td><td width='40%'>TSC Schwarz Gold / Wien </td><td>&nbsp;
</tr><tr><td width='4%' align='right'>&nbsp;</td><td width='4%'>&nbsp;</td><td width='45%'>Max Mustermann - Maria Mustermann</td><td width='40%'>TSC Musterverein / Oberösterreich </td><td>&nbsp;
</tr><tr><td width='4%' align='right'>&nbsp;</td><td width='4%'>&nbsp;</td><td width='45%'>Max Zimmermann - Jeannette Nischan</td><td width='40%'>TSC Dance Unity / Steiermark </td><td>&nbsp;
</tr><tr><td colspan=4>3 Paare in dieser Klasse</tr><tr><td colspan=4>&nbsp;</tr>
<tr>
<td colspan=4 bgcolor=#FFFFBB><b><i>Allg. Kl. Solo Sta SE</b></i></td>
</tr>
<tr><td width='4%' align='right'>&nbsp;</td><td width='4%'>&nbsp;</td><td width='45%'>Hannah Kammerlander</td><td width='40%'>TSC Danceteam Salzburg / Salzburg </td><td>&nbsp;
</tr><tr><td width='4%' align='right'>&nbsp;</td><td width='4%'>&nbsp;</td><td width='45%'>Maria Mustermann</td><td width='40%'>TSC Musterverein / Oberösterreich </td><td>&nbsp;
</tr><tr><td colspan=4>2 Paare in dieser Klasse</tr><tr><td colspan=4>&nbsp;</tr>
</table>
</BODY>
</HTML>
"""


def test_build_teilnehmer_url():
    url = build_teilnehmer_url(1775)
    assert "TASNr=1775" in url
    assert "sort=KLASSE" in url
    assert "https://www.tanzsportverband.at/portal/nennungen/nennungen_liste_002.php" in url


def test_is_utsc_linz():
    assert is_utsc_linz("TSC Musterverein / Oberösterreich") is True
    assert is_utsc_linz("TSC Musterverein") is True
    assert is_utsc_linz("TSC-Musterverein") is True
    # Other clubs with TSC should NOT match
    assert is_utsc_linz("TSC Forum - Wien / Wien") is False
    assert is_utsc_linz("TSC Dance Unity / Steiermark") is False
    assert is_utsc_linz("TSC Schwarz Gold / Wien") is False
    assert is_utsc_linz("TSK Blau - Gelb / Oberösterreich") is False
    # Registered couple fallback
    assert is_utsc_linz("", "Max Mustermann - Maria Mustermann", ["Max Mustermann / Maria Mustermann"]) is True


def test_parse_teilnehmer_html():
    parsed = parse_teilnehmer_html(SAMPLE_HTML, turnier_id=1775, turnier_db_id=11)
    assert parsed["turnier_id"] == 1775
    assert parsed["turnier_db_id"] == 11
    assert parsed["total_anmeldungen"] == 5
    assert parsed["total_paare"] == 5
    assert len(parsed["classes"]) == 2
    assert "Allg.Kl. Sta B" in parsed["classes"]
    assert "Allg. Kl. Solo Sta SE" in parsed["classes"]

    entries = parsed["entries"]
    assert len(entries) == 5

    # Check TSC Musterverein highlighting
    utsc_entries = [e for e in entries if e["is_utsc"] == 1]
    assert len(utsc_entries) == 2
    names = [e["paar_name"] for e in utsc_entries]
    assert "Max Mustermann - Maria Mustermann" in names
    assert "Maria Mustermann" in names

    non_utsc_entries = [e for e in entries if e["is_utsc"] == 0]
    assert len(non_utsc_entries) == 3


def test_save_teilnehmer_entries_and_api(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_teilnehmer.db")
    monkeypatch.setattr("app.config.settings.DATABASE_PATH", test_db)
    init_db()

    # Insert test tournament
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO turniere (id, turnier_id, datum, datum_sort, titel, klub, bundesland, tags, links)
            VALUES (1, 1775, '10.10.2026', '2026-10-10', 'LM Standard OÖ', 'TSC Musterverein', 'Oberösterreich', '[]', '{}');
        """)
        conn.commit()

    parsed = parse_teilnehmer_html(SAMPLE_HTML, turnier_id=1775, turnier_db_id=1)
    saved_cnt, prev_cnt = save_teilnehmer_entries(turnier_db_id=1, turnier_id=1775, entries=parsed["entries"])
    assert saved_cnt == 5
    assert prev_cnt == 0

    # Test re-saving (idempotent replace)
    saved_cnt2, prev_cnt2 = save_teilnehmer_entries(turnier_db_id=1, turnier_id=1775, entries=parsed["entries"])
    assert saved_cnt2 == 5
    assert prev_cnt2 == 5

    with TestClient(app) as client:
        # Test GET /api/turniere includes participant count
        res = client.get("/api/turniere?only_current_year=false")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        t = next(item for item in data if item["id"] == 1)
        assert t["teilnehmer_anzahl"] == 5
        assert t["teilnehmer_utsc_anzahl"] == 2
        assert "TASNr=1775" in t["teilnehmer_url"]

        # Test GET /api/turniere/{id}/teilnehmer
        res_t = client.get("/api/turniere/1/teilnehmer")
        assert res_t.status_code == 200
        t_data = res_t.json()
        assert t_data["turnier_id"] == 1775
        assert t_data["titel"] == "LM Standard OÖ"
        assert t_data["total_anmeldungen"] == 5
        assert t_data["utsc_paare_anzahl"] == 2
        assert t_data["klassen_anzahl"] == 2
        assert len(t_data["klassen"]) == 2

        class_b = next(k for k in t_data["klassen"] if k["klasse"] == "Allg.Kl. Sta B")
        assert class_b["paare_anzahl"] == 3
        assert class_b["utsc_anzahl"] == 1
        assert any(p["is_utsc"] for p in class_b["paare"])

        # Test admin status includes teilnehmer_gesamt
        admin_res = client.get("/adsi-admin/api/status")
        assert admin_res.status_code == 200
        admin_data = admin_res.json()
        assert admin_data["teilnehmer_gesamt"] == 5

        # Test admin trigger teilnehmer-scraper
        trig_res = client.post("/adsi-admin/api/trigger/teilnehmer-scraper")
        assert trig_res.status_code == 200
        assert trig_res.json()["status"] == "triggered"
