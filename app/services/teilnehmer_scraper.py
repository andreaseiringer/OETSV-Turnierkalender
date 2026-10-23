import re
import html
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.database import get_db_connection
from app.services.results_scraper import match_couple_names

logger = logging.getLogger("teilnehmer_scraper")

BASE_TEILNEHMER_URL = "https://www.tanzsportverband.at/portal/nennungen/nennungen_liste_002.php"


def build_teilnehmer_url(turnier_id: int) -> str:
    """Build the official ÖTSV participant list URL for a tournament."""
    return f"{BASE_TEILNEHMER_URL}?lang=DE&TASNr={turnier_id}&sort=KLASSE&aktion=list"


def is_utsc_linz(klub: Optional[str], paar_name: Optional[str] = None, registered_couples: Optional[List[str]] = None) -> bool:
    """Check if club matches the configured club or couple is registered for our club."""
    klub_lower = (klub or "").lower()
    tokens = settings.club_matching_tokens
    if tokens and klub_lower and all(t in klub_lower for t in tokens):
        return True

    if registered_couples and paar_name:
        if any(match_couple_names(paar_name, reg) for reg in registered_couples):
            return True

    return False


is_our_club = is_utsc_linz


def parse_teilnehmer_html(
    html_text: str,
    turnier_id: int,
    turnier_db_id: int,
    registered_couples: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Parse the official ÖTSV participant list HTML table.
    Returns parsed metadata, distinct classes, and couple entries.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    h2 = soup.find("h2")
    header_text = html.unescape(h2.get_text(strip=True)) if h2 else ""

    # Parse counts if present: e.g. "Bisher sind <b>48</b> Anmeldungen von 45 Paaren/Personen eingelangt"
    count_m = re.search(r'Bisher sind <b>(\d+)</b> Anmeldungen von (\d+) Paaren', html_text)
    total_anmeldungen_header = int(count_m.group(1)) if count_m else None
    total_paare_header = int(count_m.group(2)) if count_m else None

    classes: List[str] = []
    seen_classes = set()
    current_class: Optional[str] = None
    entries: List[Dict[str, Any]] = []
    sort_counter = 0

    for tr in soup.find_all("tr"):
        # Check for class header: <td colspan=4 bgcolor=#FFFFBB><b><i>...</i></b></td>
        bg_td = tr.find(lambda el: el.name == "td" and el.get("bgcolor", "").lower() == "#ffffbb")
        if bg_td:
            current_class = html.unescape(bg_td.get_text(strip=True))
            if current_class and current_class not in seen_classes:
                seen_classes.add(current_class)
                classes.append(current_class)
            continue

        tds = tr.find_all("td")
        if len(tds) >= 4 and current_class:
            txt = tr.get_text(strip=True)
            if "Paare in dieser Klasse" in txt:
                continue

            paar_raw = tds[2].get_text(strip=True)
            klub_raw = tds[3].get_text(strip=True)

            if paar_raw and paar_raw != "&nbsp;" and paar_raw != "\xa0":
                paar_clean = html.unescape(paar_raw).strip()
                klub_clean = html.unescape(klub_raw).strip() if klub_raw and klub_raw != "&nbsp;" else ""

                sort_counter += 1
                is_utsc = is_utsc_linz(klub_clean, paar_clean, registered_couples)

                entries.append({
                    "turnier_db_id": turnier_db_id,
                    "turnier_id": turnier_id,
                    "klasse": current_class,
                    "paar_name": paar_clean,
                    "klub": klub_clean,
                    "is_utsc": 1 if is_utsc else 0,
                    "sort_order": sort_counter
                })

    # In-memory distinct couples count
    distinct_couples = {e["paar_name"] for e in entries}
    total_anmeldungen = total_anmeldungen_header if total_anmeldungen_header is not None else len(entries)
    total_paare = total_paare_header if total_paare_header is not None else len(distinct_couples)

    return {
        "turnier_id": turnier_id,
        "turnier_db_id": turnier_db_id,
        "original_url": build_teilnehmer_url(turnier_id),
        "header_text": header_text,
        "total_anmeldungen": total_anmeldungen,
        "total_paare": total_paare,
        "classes": classes,
        "entries": entries
    }


def save_teilnehmer_entries(turnier_db_id: int, turnier_id: int, entries: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Atomically replace participant list for tournament in SQLite."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Count existing
        cursor.execute("SELECT COUNT(*) as cnt FROM turnier_teilnehmer WHERE turnier_db_id = ?;", (turnier_db_id,))
        previous_count = cursor.fetchone()["cnt"]

        # Delete previous entries to handle cancellations/changes cleanly
        cursor.execute("DELETE FROM turnier_teilnehmer WHERE turnier_db_id = ?;", (turnier_db_id,))

        # Insert new
        now_str = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%d.%m.%Y %H:%M:%S")
        for e in entries:
            cursor.execute("""
                INSERT OR REPLACE INTO turnier_teilnehmer (
                    turnier_db_id, turnier_id, klasse, paar_name, klub, is_utsc, sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                turnier_db_id, turnier_id, e["klasse"], e["paar_name"],
                e["klub"], e["is_utsc"], e["sort_order"], now_str, now_str
            ))

        conn.commit()
        return len(entries), previous_count


def recalculate_teilnehmer_club_matches() -> int:
    """Re-evaluate is_utsc flag for all existing participant entries after club config change."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, turnier_db_id, turnier_id, paar_name, klub FROM turnier_teilnehmer;")
        rows = cursor.fetchall()
        if not rows:
            return 0

        cursor.execute("SELECT turnier_db_id, turnier_id, paar_name FROM nennungen;")
        nennung_rows = cursor.fetchall()

        reg_by_db_id: Dict[int, List[str]] = {}
        reg_by_vid: Dict[int, List[str]] = {}
        for nr in nennung_rows:
            if nr["turnier_db_id"]:
                reg_by_db_id.setdefault(nr["turnier_db_id"], []).append(nr["paar_name"])
            if nr["turnier_id"]:
                reg_by_vid.setdefault(nr["turnier_id"], []).append(nr["paar_name"])

        matched_count = 0
        for r in rows:
            regs = list(set(
                reg_by_db_id.get(r["turnier_db_id"], []) +
                reg_by_vid.get(r["turnier_id"], [])
            ))
            matched = 1 if is_utsc_linz(r["klub"], r["paar_name"], regs) else 0
            if matched:
                matched_count += 1
            cursor.execute("UPDATE turnier_teilnehmer SET is_utsc = ? WHERE id = ?;", (matched, r["id"]))

        conn.commit()
        return matched_count


async def fetch_tournament_teilnehmer(
    client: httpx.AsyncClient,
    turnier_db_id: int,
    turnier_id: int,
    registered_couples: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Fetch and parse participant list for a single tournament."""
    url = build_teilnehmer_url(turnier_id)
    resp = await client.get(url, timeout=settings.TEILNEHMER_TIMEOUT)
    if resp.status_code != 200:
        return {"status": "http_error", "status_code": resp.status_code, "entries": []}

    try:
        content = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        content = resp.content.decode("iso-8859-1", errors="replace")

    parsed = parse_teilnehmer_html(content, turnier_id, turnier_db_id, registered_couples)
    return parsed


async def run_teilnehmer_scraper() -> Dict[str, Any]:
    """
    Run participant list scraper for all current and upcoming tournaments with turnier_id.
    Executes 4 times daily via scheduler or on demand.
    """
    logger.info("Starting ÖTSV Teilnehmerlisten-Scraper...")
    now_vienna = datetime.now(ZoneInfo(settings.TIMEZONE))
    now_str = now_vienna.strftime("%d.%m.%Y %H:%M:%S")

    # Cutoff: Today - 7 days (grace period)
    cutoff_date = (now_vienna - timedelta(days=7)).strftime("%Y-%m-%d")

    # Update status to running
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE sync_status
            SET status = 'running', message = 'Teilnehmerlisten werden importiert...', last_run = ?
            WHERE key = 'teilnehmer_scraper';
        """, (now_str,))
        conn.commit()

        # Find all tournaments with turnier_id starting from cutoff
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, turnier_id, datum, datum_sort, titel
            FROM turniere
            WHERE turnier_id IS NOT NULL AND datum_sort >= ?
            ORDER BY datum_sort ASC;
        """, (cutoff_date,))
        tournaments = [dict(r) for r in cursor.fetchall()]

    if not tournaments:
        msg = "Keine aktuellen Turniere mit Verbands-ID gefunden."
        logger.info(msg)
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE sync_status
                SET status = 'success', message = ?, last_run = ?
                WHERE key = 'teilnehmer_scraper';
            """, (msg, now_str))
            conn.commit()
        return {"status": "success", "imported": 0, "message": msg}

    total_entries_count = 0
    total_tournaments_scraped = 0
    utsc_entries_found = 0

    try:
        async with httpx.AsyncClient(headers={"User-Agent": "pivitLABS-OETSV-Tool/1.4 (+https://pivitlabs.com)"}) as client:
            for t in tournaments:
                t_db_id = t["id"]
                t_vid = t["turnier_id"]

                # Registered club couples for this tournament
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT paar_name FROM nennungen WHERE turnier_db_id = ? OR turnier_id = ?;", (t_db_id, t_vid))
                    reg_couples = [r["paar_name"] for r in cur.fetchall()]

                try:
                    result = await fetch_tournament_teilnehmer(client, t_db_id, t_vid, reg_couples)
                    entries = result.get("entries", [])
                    if entries:
                        count_saved, _ = save_teilnehmer_entries(t_db_id, t_vid, entries)
                        total_entries_count += count_saved
                        utsc_count = sum(1 for e in entries if e.get("is_utsc"))
                        utsc_entries_found += utsc_count
                        total_tournaments_scraped += 1
                        logger.debug(f"Turnier {t_vid} ({t['titel']}): {count_saved} Nennungen ({utsc_count} {settings.club_short_label}).")
                    else:
                        # Even if 0 entries, ensure DB is cleared if it had old test data
                        save_teilnehmer_entries(t_db_id, t_vid, [])
                except Exception as e:
                    logger.warning(f"Error fetching Teilnehmerliste for tournament {t_vid}: {e}")

                await asyncio.sleep(settings.TEILNEHMER_RATE_LIMIT_DELAY)

        summary_msg = f"{total_entries_count} Nennungen in {total_tournaments_scraped} Turnieren importiert ({utsc_entries_found} {settings.club_short_label}-Beteiligungen)"
        logger.info(f"Teilnehmerlisten-Scraper finished: {summary_msg}")

        with get_db_connection() as conn:
            conn.execute("""
                UPDATE sync_status
                SET status = 'success',
                    message = ?,
                    added_count = ?,
                    updated_count = ?,
                    last_run = ?
                WHERE key = 'teilnehmer_scraper';
            """, (summary_msg, total_entries_count, total_tournaments_scraped, now_str))
            conn.commit()

        return {
            "status": "success",
            "total_entries": total_entries_count,
            "tournaments_scraped": total_tournaments_scraped,
            "utsc_entries": utsc_entries_found,
            "message": summary_msg
        }

    except Exception as e:
        logger.exception(f"Teilnehmerlisten-Scraper failed: {e}")
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE sync_status
                SET status = 'error',
                    message = ?
                WHERE key = 'teilnehmer_scraper';
            """, (str(e),))
            conn.commit()
        return {"status": "error", "message": str(e)}
