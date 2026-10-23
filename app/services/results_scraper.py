import re
import html
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx

from app.config import settings
from app.database import get_db_connection

logger = logging.getLogger("results_scraper")

BASE_REPORTS_URL = "https://www.tanzsportverband.at/upload/turnierberichte"


def normalize_class_name(raw_comp: str, title: str, slug: str) -> str:
    """Extract clean, descriptive class name from raw TopTurnier strings."""
    candidate = raw_comp if raw_comp else title
    # Often formatted as: "20.09.2026 - MdB, Sen.III C Standard"
    if " - " in candidate:
        parts = candidate.split(" - ", 1)
        candidate = parts[1].strip()
    return candidate if candidate else slug


def clean_couple_name(raw_name: str) -> str:
    """Normalize capitalization and unescape couple name."""
    name = html.unescape(raw_name).strip()
    # Normalize uppercase words: "Christian SCHLAGER / Rosmarie SCHLAGER" -> "Christian Schlager / Rosmarie Schlager"
    name = re.sub(r'\b([A-ZÄÖÜ]{2,})\b', lambda m: m.group(1).capitalize(), name)
    return name


def parse_topturnier_erg(raw_html: str, turnier_id: int, class_slug: str) -> Tuple[str, int, List[Dict[str, Any]]]:
    """
    Parse a single TopTurnier erg.htm file.
    Returns: (class_title, total_couples, list_of_couple_entries)
    """
    title_m = re.search(r'<TITLE>([^<]+)</TITLE>', raw_html, re.I)
    title = html.unescape(title_m.group(1).strip()) if title_m else class_slug

    comp_m = re.search(r'<tr><td>([^<]+)</td>', raw_html, re.I)
    comp_name = html.unescape(comp_m.group(1).strip()) if comp_m else title
    clean_class_name = normalize_class_name(comp_name, title, class_slug)

    entries: List[Dict[str, Any]] = []

    # Pattern 1: Variant B (4 columns: Rank | No. | Participant | Club/Country)
    # E.g. <TR><TD class="td3c">1.</TD><TD class="td2c" nowrap>31</TD><TD class="td5">Max MUSTERMANN / Maria MUSTERMANN</TD><TD class="td5"><i>TSC Musterverein</i></TD></TR>
    v4_pattern = re.compile(
        r'<TR[^>]*>\s*<TD class=[\"\']td3[a-z]?[\"\'][^>]*>\s*([0-9]+(?:\s*[\.\-]\s*[0-9]+)*\.?)\s*</TD>'
        r'\s*<TD class=[\"\']td2[a-z]?[\"\'][^>]*>\s*([0-9]+)\s*</TD>'
        r'\s*<TD class=[\"\']td5[\"\'][^>]*>(.*?)</TD>'
        r'\s*<TD class=[\"\']td[56][\"\'][^>]*>(.*?)</TD>\s*</TR>',
        re.I | re.S
    )
    for m in v4_pattern.finditer(raw_html):
        platz_str = m.group(1).strip()
        startnr = m.group(2).strip()
        names = clean_couple_name(re.sub(r'<[^>]+>', '', m.group(3)).strip())
        klub = html.unescape(re.sub(r'<[^>]+>', '', m.group(4)).strip())
        
        rank_m = re.search(r'\d+', platz_str)
        platz_sort = int(rank_m.group(0)) if rank_m else 999

        entries.append({
            "platz": platz_str,
            "platz_sort": platz_sort,
            "paar_name": names,
            "startnr": startnr,
            "klub": klub,
            "runde": "Ergebnis"
        })

    # Pattern 2: Variant A Endrunde (<TD class="td3r">1.</TD><TD class="td5">Name / Name (Nr)<BR><i>Klub</i></TD>)
    if not entries:
        endrunde_pattern = re.compile(
            r'<TD class=["\']td3[a-z]?["\'][^>]*>\s*([0-9]+(?:\s*[\.\-]\s*[0-9]+)*\.?)\s*</TD>\s*<TD class=["\']td5["\'][^>]*>([^<]+)\s*\(([0-9]+)\)<BR><i>([^<]+)</i>',
            re.I
        )
        for m in endrunde_pattern.finditer(raw_html):
            platz_str = m.group(1).strip()
            names = clean_couple_name(m.group(2).strip())
            startnr = m.group(3).strip()
            klub = html.unescape(m.group(4).strip())
            
            rank_m = re.search(r'\d+', platz_str)
            platz_sort = int(rank_m.group(0)) if rank_m else 999

            entries.append({
                "platz": platz_str,
                "platz_sort": platz_sort,
                "paar_name": names,
                "startnr": startnr,
                "klub": klub,
                "runde": "Endrunde"
            })

        # Pattern 3: Variant A Vorrunde / Zwischenrunde (<TD class="td3r">7.</TD><TD class="td5">Name / Name (Nr)</TD><TD class="td6">Klub</TD>)
        pre_round_pattern = re.compile(
            r'<TD class=["\']td3[a-z]?["\'][^>]*>\s*([0-9]+(?:\s*[\.\-]\s*[0-9]+)*\.?)\s*</TD>\s*<TD class=["\']td5["\'][^>]*>([^<]+)\s*\(([0-9]+)\)</TD>\s*<TD class=["\']td6["\'][^>]*>([^<]+)</TD>',
            re.I
        )
        for m in pre_round_pattern.finditer(raw_html):
            platz_str = m.group(1).strip()
            names = clean_couple_name(m.group(2).strip())
            startnr = m.group(3).strip()
            klub = html.unescape(m.group(4).strip())

            rank_m = re.search(r'\d+', platz_str)
            platz_sort = int(rank_m.group(0)) if rank_m else 999

            entries.append({
                "platz": platz_str,
                "platz_sort": platz_sort,
                "paar_name": names,
                "startnr": startnr,
                "klub": klub,
                "runde": "Vorrunde/Zwischenrunde"
            })

    total_paare = len(entries)
    return clean_class_name, total_paare, entries


def extract_couple_surnames(name: str) -> List[str]:
    """Extract significant surnames from couple string."""
    parts = re.split(r'\s*(?:&|/|\bund\b|-)\s*', name)
    surnames = []
    for part in parts:
        tokens = [t.strip().lower() for t in part.split() if len(t.strip()) > 2]
        if tokens:
            surnames.append(tokens[-1])
    return list(set(surnames))

def match_couple_names(entry_name: str, registered_name: str) -> bool:
    """Check if all significant surnames of registered couple match entry name."""
    surnames_reg = extract_couple_surnames(registered_name)
    if not surnames_reg:
        return False
    entry_lower = entry_name.lower()
    return all(re.search(rf'\b{re.escape(s)}\b', entry_lower) for s in surnames_reg)

def is_our_club_entry(klub: str, paar_name: str, registered_couples: List[str]) -> bool:
    """Check if entry belongs to configured club or matches registered couples."""
    klub_lower = (klub or "").lower()
    tokens = settings.club_matching_tokens
    if tokens and klub_lower and all(t in klub_lower for t in tokens):
        return True

    return any(match_couple_names(paar_name, reg) for reg in registered_couples)


async def run_results_scraper() -> Dict[str, Any]:
    """
    Scrape TopTurnier tournament reports for all tournaments with registered club couples.
    Saves parsed results into turnier_ergebnisse table.
    """
    logger.info("Starting ÖTSV tournament results scraper...")
    now_str = datetime.now(ZoneInfo("Europe/Vienna")).strftime("%d.%m.%Y %H:%M:%S")

    # Update sync_status to running
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE sync_status
            SET status = 'running', message = 'Ergebnisse-Scraping läuft...', last_run = ?
            WHERE key = 'results_scraper'
        """, (now_str,))
        conn.commit()

        # Find tournaments with registered pairs
        cursor = conn.execute("""
            SELECT DISTINCT t.id, t.turnier_id, t.datum, t.datum_sort, t.titel
            FROM turniere t
            JOIN nennungen n ON n.turnier_db_id = t.id
            WHERE t.turnier_id IS NOT NULL
            ORDER BY t.datum_sort DESC
        """)
        tournaments = [dict(row) for row in cursor.fetchall()]

    if not tournaments:
        logger.info("No tournaments with registered couples found.")
        msg = "Keine Turniere mit gemeldeten Paaren vorhanden."
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE sync_status
                SET status = 'success', message = ?, last_run = ?
                WHERE key = 'results_scraper'
            """, (msg, now_str))
            conn.commit()
        return {"status": "success", "imported": 0, "message": msg}

    total_added = 0
    total_updated = 0
    scanned_count = 0

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for t in tournaments:
            turnier_db_id = t["id"]
            turnier_id = t["turnier_id"]
            report_index_url = f"{BASE_REPORTS_URL}/{turnier_id:05d}/index.htm"

            # Check if report exists
            try:
                resp = await client.get(report_index_url)
                if resp.status_code != 200:
                    continue
            except Exception as e:
                logger.debug(f"Report not available for tournament {turnier_id}: {e}")
                continue

            scanned_count += 1
            index_html = resp.text
            class_slugs = re.findall(r'href=["\']([^"\']+)/index\.htm["\']', index_html)

            # Get registered couples and their surnames for this tournament
            with get_db_connection() as conn:
                cur = conn.execute("SELECT paar_name, klub FROM nennungen WHERE turnier_db_id = ?", (turnier_db_id,))
                registered_rows = cur.fetchall()

            registered_couples = [r["paar_name"] for r in registered_rows]

            # Parse each class
            for slug in class_slugs:
                erg_url = f"{BASE_REPORTS_URL}/{turnier_id:05d}/{slug}/erg.htm"
                try:
                    erg_resp = await client.get(erg_url)
                    if erg_resp.status_code != 200:
                        continue
                except Exception as e:
                    logger.debug(f"Could not fetch {erg_url}: {e}")
                    continue

                class_name, total_paare, entries = parse_topturnier_erg(erg_resp.text, turnier_id, slug)
                class_report_url = f"{BASE_REPORTS_URL}/{turnier_id:05d}/{slug}/index.htm"

                # Filter for our couples
                for entry in entries:
                    if is_our_club_entry(entry["klub"], entry["paar_name"], registered_couples):
                        with get_db_connection() as conn:
                            cur = conn.cursor()
                            # Check if exists
                            cur.execute("""
                                SELECT id FROM turnier_ergebnisse
                                WHERE turnier_id = ? AND klasse_slug = ? AND paar_name = ?
                            """, (turnier_id, slug, entry["paar_name"]))
                            existing = cur.fetchone()

                            if existing:
                                cur.execute("""
                                    UPDATE turnier_ergebnisse
                                    SET turnier_db_id = ?,
                                        klasse_name = ?,
                                        platz = ?,
                                        platz_sort = ?,
                                        total_paare = ?,
                                        startnr = ?,
                                        klub = ?,
                                        runde = ?,
                                        bericht_url = ?,
                                        updated_at = ?
                                    WHERE id = ?
                                """, (
                                    turnier_db_id, class_name, entry["platz"], entry["platz_sort"],
                                    total_paare, entry["startnr"], entry["klub"], entry["runde"],
                                    class_report_url, now_str, existing["id"]
                                ))
                                total_updated += 1
                            else:
                                cur.execute("""
                                    INSERT INTO turnier_ergebnisse (
                                        turnier_db_id, turnier_id, klasse_name, klasse_slug,
                                        platz, platz_sort, total_paare, paar_name,
                                        startnr, klub, runde, bericht_url, created_at, updated_at
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    turnier_db_id, turnier_id, class_name, slug,
                                    entry["platz"], entry["platz_sort"], total_paare, entry["paar_name"],
                                    entry["startnr"], entry["klub"], entry["runde"], class_report_url,
                                    now_str, now_str
                                ))
                                total_added += 1
                            conn.commit()

    summary_msg = f"{total_added} neu, {total_updated} aktualisiert ({scanned_count} Berichte gescannt)"
    logger.info(f"Tournament results scraper complete: {summary_msg}")

    with get_db_connection() as conn:
        conn.execute("""
            UPDATE sync_status
            SET status = 'success',
                message = ?,
                added_count = ?,
                updated_count = ?,
                last_run = ?
            WHERE key = 'results_scraper'
        """, (summary_msg, total_added, total_updated, now_str))
        conn.commit()

    return {
        "status": "success",
        "added": total_added,
        "updated": total_updated,
        "scanned_tournaments": scanned_count,
        "message": summary_msg
    }
