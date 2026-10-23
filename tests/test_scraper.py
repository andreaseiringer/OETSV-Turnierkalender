import pytest
import os
import json
import sqlite3
from app.services.scraper import parse_html_table, normalize_tags, parse_iso_date
from app.database import get_db_connection, init_db
from app.config import settings

SAMPLE_OETSV_HTML = """
<table class='oetsvTable'>
<tr>
  <td class='label'>Datum</td>
  <td class='label'>Bezeichnung</td>
  <td class='label'>Disziplin / Alter</td>
  <td class='label'>Bundesland</td>
  <td class='label'>Ausschreibung / Links</td>
</tr>
<tr class='row1'>
  <td>19.09.2026</td>
  <td><b>Landesmeisterschaft Standard Tirol</b><br>TSC Kufstein</td>
  <td>Standard<br>Allg. Klasse</td>
  <td>Tirol</td>
  <td class='small'>
    &raquo; <a href='https://www.tanzsportverband.at/portal/ausschreibung/ausschreibung_drucken.php?TKNr=1777&art=IN' target=_blank>Ausschreibung</a><br>
    &raquo; <a href='https://www.tsc-kufstein.at' target=_blank>Homepage</a>
  </td>
</tr>
<tr class='row2'>
  <td>26.09.2026 - 27.09.2026</td>
  <td><b>Mehrfl&auml;chenturnier - Tanzsportwochenende</b><br>Klub: ATSC Imperial Wien</td>
  <td>Standard/Latein<br>Allg. Klasse, Senioren, SCH/JUN/JUG</td>
  <td>Nieder&ouml;sterreich</td>
  <td class='small'>
    &raquo; <a href='https://www.tanzsportverband.at/portal/ausschreibung/drucken.php?TASNr=1780' target=_blank>Ausschreibung</a>
  </td>
</tr>
<tr class='row1'>
  <td>05.10.2026</td>
  <td><b>Freundschaftsturnier ohne Verbands-ID</b></td>
  <td>Latein</td>
  <td>Wien</td>
  <td class='small'>
    Keine Links verf&uuml;gbar
  </td>
</tr>
</table>
"""

def test_parse_iso_date():
    assert parse_iso_date("19.09.2026") == "2026-09-19"
    assert parse_iso_date("26.09.2026 - 27.09.2026") == "2026-09-26"
    assert parse_iso_date("Kein Datum") == "9999-12-31"

def test_normalize_tags():
    raw = "Standard/Latein<br>Schüler, Junioren, Jugend, Allg. Klasse, ; | a"
    tags = normalize_tags(raw)
    assert "Standard" in tags
    assert "Latein" in tags
    assert "Schüler" in tags
    assert "Junioren" in tags
    assert "Jugend" in tags
    assert "Allg. Klasse" in tags
    # Single letter 'a' should be removed
    assert "a" not in tags

def test_parse_html_table():
    tournaments = parse_html_table(SAMPLE_OETSV_HTML)
    assert len(tournaments) == 3

    # Tournament 1
    t1 = tournaments[0]
    assert t1["turnier_id"] == 1777
    assert t1["datum"] == "19.09.2026"
    assert t1["datum_sort"] == "2026-09-19"
    assert t1["titel"] == "Landesmeisterschaft Standard Tirol"
    assert t1["klub"] == "TSC Kufstein"
    assert t1["bundesland"] == "Tirol"
    assert "Standard" in t1["tags"]
    assert "ausschreibung" in t1["links"]
    assert "homepage" in t1["links"]

    # Tournament 2
    t2 = tournaments[1]
    assert t2["turnier_id"] == 1780
    assert t2["datum"] == "26.09.2026 - 27.09.2026"
    assert t2["datum_sort"] == "2026-09-26"
    assert "Mehrflächenturnier" in t2["titel"]
    assert t2["klub"] == "ATSC Imperial Wien"
    assert t2["bundesland"] == "Niederösterreich"

    # Tournament 3 (no turnier_id)
    t3 = tournaments[2]
    assert t3["turnier_id"] is None
    assert t3["titel"] == "Freundschaftsturnier ohne Verbands-ID"
    assert t3["bundesland"] == "Wien"
