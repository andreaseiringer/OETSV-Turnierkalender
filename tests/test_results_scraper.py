import pytest
import os
import sqlite3
from unittest.mock import patch, AsyncMock
import httpx

from app.database import get_db_connection, init_db
from app.config import settings
from app.services.results_scraper import (
    parse_topturnier_erg,
    is_our_club_entry,
    normalize_class_name,
    run_results_scraper
)

SAMPLE_INDEX_HTML = """
<!DOCTYPE HTML>
<html>
<head><title>Turnierbericht 01778</title></head>
<body>
<a href="0-mdb_sen1dstd/index.htm">Sen.I D Standard</a>
<a href="11-mdb_sen3cstd/index.htm">Sen.III C Standard</a>
</body>
</html>
"""

SAMPLE_ERG_HTML_ENDRUNDE = """
<!DOCTYPE html>
<html>
<head>
  <TITLE>20.09.2026 Sen.I D Standard</TITLE>
</head>
<body>
<div class="eventhead">
<table border=0><tr><td>20.09.2026 - MdB, Sen.I D Standard</td></tr></table>
</div>
<div class="extract">
   <TABLE class="tab1">
    <TR><TD class="td1" colspan="7">Endrunde</TD></TR>
    <TR>
     <TD class="td3r">1.</TD>
     <TD class="td5">Matthias Letsch / Barbara Broschek (32)<BR><i>1. TTK GOLD WEISS Innsbruck</i></TD>
    </TR>
    <TR>
     <TD class="td3r">2.</TD>
     <TD class="td5">Georg Hasibeder / Agnes Plankensteiner (19)<BR><i>1. TTK GOLD WEISS Innsbruck</i></TD>
    </TR>
    <TR>
     <TD class="td3r">3.</TD>
     <TD class="td5">Max Mustermann / Maria Mustermann (7)<BR><i>TSC Musterverein</i></TD>
    </TR>
   </TABLE>
</div>
</body>
</html>
"""

SAMPLE_ERG_HTML_MIXED = """
<!DOCTYPE html>
<html>
<head><title>20.09.2026 Sen.III C Standard</title></head>
<body>
<div class="eventhead">
<table><tr><td>20.09.2026 - MdB, Sen.III C Standard</td></tr></table>
</div>
<div class="extract">
   <TABLE class="tab1">
    <TR><TD class="td1" colspan="8">Endrunde</TD></TR>
    <TR>
     <TD class="td3r">1.</TD>
     <TD class="td5">Michael Tinhof / Johanna Tinhof (60)<BR><i>TSC Dance Salzburg</i></TD>
    </TR>
    <TR>
     <TD class="td3r">6.</TD>
     <TD class="td5">Max Mustermann / Maria Mustermann (53)<BR><i>TSC Musterverein</i></TD>
    </TR>
   </TABLE>
   <TABLE class="tab2">
    <TR><TD class="td1" colspan="3">Vorrunde</TD></TR>
    <TR>
     <TD class="td3r" width="45px">7.</TD>
     <TD class="td5">Johann Schinninger / Eva Maria Schinninger (52)</TD>
     <TD class="td6">TSK Blau - Gelb</TD>
    </TR>
    <TR>
     <TD class="td3r" width="45px">8.</TD>
     <TD class="td5">Karl-Heinz Keusch / Elisabeth Schernthaner (25)</TD>
     <TD class="td6">TSC Eleganza</TD>
    </TR>
   </TABLE>
</div>
</body>
</html>
"""


def test_normalize_class_name():
    assert normalize_class_name("20.09.2026 - MdB, Sen.III C Standard", "Sen.III C Standard", "slug") == "MdB, Sen.III C Standard"
    assert normalize_class_name("", "Title Only", "slug") == "Title Only"
    assert normalize_class_name("", "", "slug-fallback") == "slug-fallback"


def test_parse_topturnier_erg_endrunde():
    class_name, total, entries = parse_topturnier_erg(SAMPLE_ERG_HTML_ENDRUNDE, 1778, "0-mdb_sen1dstd")
    assert class_name == "MdB, Sen.I D Standard"
    assert total == 3
    assert len(entries) == 3

    # Check 3rd entry (our couple)
    third = entries[2]
    assert third["platz"] == "3."
    assert third["platz_sort"] == 3
    assert third["paar_name"] == "Max Mustermann / Maria Mustermann"
    assert third["startnr"] == "7"
    assert third["klub"] == "TSC Musterverein"
    assert third["runde"] == "Endrunde"


def test_parse_topturnier_erg_mixed():
    class_name, total, entries = parse_topturnier_erg(SAMPLE_ERG_HTML_MIXED, 1778, "11-mdb_sen3cstd")
    assert total == 4
    assert len(entries) == 4

    mustermann = next(e for e in entries if "Mustermann" in e["paar_name"])
    assert mustermann["platz"] == "6."
    assert mustermann["platz_sort"] == 6
    assert mustermann["klub"] == "TSC Musterverein"
    assert mustermann["runde"] == "Endrunde"

    vorrunde_entry = next(e for e in entries if "Schinninger" in e["paar_name"])
    assert vorrunde_entry["platz"] == "7."
    assert vorrunde_entry["platz_sort"] == 7
    assert vorrunde_entry["klub"] == "TSK Blau - Gelb"
    assert vorrunde_entry["runde"] == "Vorrunde/Zwischenrunde"


def test_parse_topturnier_erg_variant_b_4col():
    sample_4col = """
    <!DOCTYPE html>
    <html>
    <head><TITLE>26/Sep/2026 Sen.I D Standard</TITLE></head>
    <body>
    <div class="eventhead">
    <table><tr><td>26/Sep/2026 - BT, Sen.I D Standard &#34;1&#34;</td></tr></table>
    </div>
    <TABLE class="tab1">
      <TR><TD class="td1" colspan="4">Final</TD></TR>
      <TR><TD class="td2c">Rank</TD><TD class="td2c">No.</TD><TD class="td2">Participant</TD><TD class="td2">Country</TD></TR>
      <TR>
        <TD class="td3c">1.</TD>
        <TD class="td2c" nowrap>31</TD>
        <TD class="td5">Alexander HOLY / Paulina WINIARSKA</TD>
        <TD class="td5"><i>TSC Raiffeisenbank G&auml;nserndorf</i></TD>
      </TR>
      <TR>
        <TD class="td3c">2.</TD>
        <TD class="td2c" nowrap>30</TD>
        <TD class="td5">Max MUSTERMANN / Maria MUSTERMANN</TD>
        <TD class="td5"><i>TSC Musterverein</i></TD>
      </TR>
    </TABLE>
    </body>
    </html>
    """
    name, total, entries = parse_topturnier_erg(sample_4col, 1780, "8-bt_sen1dstd")
    assert "Sen.I D Standard" in name
    assert total == 2
    assert entries[0]["platz"] == "1."
    assert entries[0]["startnr"] == "31"
    assert entries[0]["paar_name"] == "Alexander Holy / Paulina Winiarska"
    assert entries[1]["platz"] == "2."
    assert entries[1]["startnr"] == "30"
    assert entries[1]["paar_name"] == "Max Mustermann / Maria Mustermann"
    assert entries[1]["klub"] == "TSC Musterverein"


def test_is_our_club_entry():
    registered_couples = [
        "Max Mustermann & Maria Mustermann"
    ]

    # Direct TSC Musterverein club match
    assert is_our_club_entry("TSC Musterverein", "Random Couple", registered_couples) is True
    assert is_our_club_entry("TSC-Musterverein", "Random Couple", registered_couples) is True

    # Couple match even if club string has subtle difference
    assert is_our_club_entry("Tanzsportklub", "Max Mustermann / Maria Mustermann", registered_couples) is True

    # TSK Blau-Gelb without TSC Musterverein and without our couple -> False
    assert is_our_club_entry("TSK Blau - Gelb", "Johann Schinninger / Eva Maria", registered_couples) is False

    # Foreign club & non-matching couple
    assert is_our_club_entry("TSC Schwarz Gold Wien", "Other Couple", registered_couples) is False
    assert is_our_club_entry("TSK Turnerschaft Innsbruck", "Hendryk Schwarz / Martina Folladore", registered_couples) is False
    assert is_our_club_entry("TSC Dance Unity", "Other Couple", registered_couples) is False
    assert is_our_club_entry("TSC Raiffeisenbank Gänserndorf", "Other Couple", registered_couples) is False


@pytest.mark.asyncio
async def test_run_results_scraper_end_to_end(tmp_path):
    test_db = tmp_path / "test_adsi.db"
    settings.DATABASE_PATH = str(test_db)
    init_db()

    # Seed tournament and registration
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO turniere (id, turnier_id, datum, datum_sort, titel, klub, bundesland)
            VALUES (1, 1778, '20.09.2026', '2026-09-20', 'Tiroler Meisterschaft Senioren', 'LFV Tirol', 'Tirol');
        """)
        conn.execute("""
            INSERT INTO nennungen (id, nennungs_id, paar_name, klub, turnier_id, turnier_db_id)
            VALUES (1, '39002', 'Max Mustermann & Maria Mustermann', 'TSC Musterverein', 1778, 1);
        """)
        conn.commit()

    # Mock HTTP requests
    async def mock_get(url, *args, **kwargs):
        req = httpx.Request("GET", url)
        if url.endswith("/01778/index.htm"):
            return httpx.Response(200, text=SAMPLE_INDEX_HTML, request=req)
        elif url.endswith("/0-mdb_sen1dstd/erg.htm"):
            return httpx.Response(200, text=SAMPLE_ERG_HTML_ENDRUNDE, request=req)
        elif url.endswith("/11-mdb_sen3cstd/erg.htm"):
            return httpx.Response(200, text=SAMPLE_ERG_HTML_MIXED, request=req)
        return httpx.Response(404, request=req)

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        res1 = await run_results_scraper()
        assert res1["status"] == "success"
        assert res1["added"] == 2
        assert res1["updated"] == 0

        # Check DB rows
        with get_db_connection() as conn:
            cur = conn.execute("SELECT * FROM turnier_ergebnisse ORDER BY platz_sort ASC")
            rows = cur.fetchall()
            assert len(rows) == 2
            assert rows[0]["platz"] == "3."
            assert "Mustermann" in rows[0]["paar_name"]
            assert rows[1]["platz"] == "6."
            assert "Mustermann" in rows[1]["paar_name"]

        # Run 2nd time: must update (idempotent, no duplicates)
        res2 = await run_results_scraper()
        assert res2["status"] == "success"
        assert res2["added"] == 0
        assert res2["updated"] == 2

        with get_db_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) as cnt FROM turnier_ergebnisse")
            assert cur.fetchone()["cnt"] == 2
