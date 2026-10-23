import re
import json
import html
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import httpx
from bs4 import BeautifulSoup, Tag
from zoneinfo import ZoneInfo

from app.config import settings
from app.database import get_db_connection

logger = logging.getLogger("scraper")

def parse_iso_date(datum_text: str) -> str:
    """Extract first DD.MM.YYYY from string and return ISO YYYY-MM-DD for sorting."""
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', datum_text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    return "9999-12-31"

def normalize_tags(raw_tags_text: str) -> List[str]:
    """Clean, split, deduplicate and normalize tags while preserving order."""
    if not raw_tags_text:
        return []
    # Replace <br> or newlines with comma
    text = raw_tags_text.replace("\n", ",").replace("<br>", ",").replace("<br/>", ",")
    # Unescape HTML entities
    text = html.unescape(text)

    # Split by comma, slash, semicolon, pipe
    tokens = re.split(r'[,/;|]', text)
    cleaned_tags = []
    seen = set()

    for token in tokens:
        t = token.strip()
        # Remove single character fragments or empty strings
        if not t or len(t) <= 1:
            continue
        # Normalize casing for common tags if desired, or keep display casing
        t_lower = t.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            cleaned_tags.append(t)

    return cleaned_tags

def extract_links_and_id(cell: Tag) -> Tuple[Dict[str, str], Optional[int]]:
    """Extract categorized links and tournament ID (TKNr or TASNr)."""
    links: Dict[str, str] = {}
    turnier_id: Optional[int] = None

    for a in cell.find_all("a", href=True):
        href = a["href"].strip()
        link_text = a.get_text(strip=True)
        if not href:
            continue

        if href.startswith("/"):
            href = "https://www.tanzsportverband.at" + href

        # Security: Only allow http:// and https:// URLs (reject javascript:, data:, etc.)
        if not href.lower().startswith(("https://", "http://")):
            continue

        # Check for TKNr or TASNr in query string
        id_match = re.search(r'[?&](?:TKNr|TASNr)=(\d+)', href, re.IGNORECASE)
        if id_match and not turnier_id:
            turnier_id = int(id_match.group(1))

        # Categorize
        text_lower = link_text.lower()
        href_lower = href.lower()

        if "ausschreibung" in text_lower or "ausschreibung" in href_lower or href_lower.endswith(".pdf"):
            links["ausschreibung"] = href
        elif "homepage" in text_lower or "web" in text_lower:
            links["homepage"] = href
        elif "nennung" in text_lower or "anmeldung" in text_lower:
            links["anmeldung"] = href
        elif "info" in text_lower or "information" in text_lower:
            links["information"] = href
        else:
            slug = re.sub(r'[^a-zA-Z0-9_]', '', link_text.lower()) or f"link_{len(links)+1}"
            links[slug] = href

    return links, turnier_id

def parse_bezeichnung_cell(cell: Tag) -> Tuple[str, Optional[str]]:
    """Separate tournament title from club name."""
    # Convert <br> to newline
    for br in cell.find_all(["br", "p"]):
        br.replace_with("\n")

    full_text = cell.get_text().strip()
    full_text = html.unescape(full_text)

    lines = [line.strip() for line in full_text.split("\n") if line.strip()]
    if not lines:
        return ("Unbekanntes Turnier", None)

    title = lines[0]
    klub = None

    if len(lines) > 1:
        klub_candidate = " ".join(lines[1:]).strip()
        # Clean prefix like "Klub:", "Club:", "Ausrichter:"
        klub_candidate = re.sub(r'^(?:Klub|Club|Ausrichter)\s*:\s*', '', klub_candidate, flags=re.IGNORECASE).strip()
        if klub_candidate:
            klub = klub_candidate
    else:
        # Check if "Klub:" is in the title line
        m = re.search(r'^(.*?)(?:\s*-\s*|\s*\|\s*|\s+)(?:Klub|Club|Ausrichter)\s*:\s*(.*)$', title, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            klub = m.group(2).strip()

    return title, klub

def parse_html_table(html_content: str) -> List[Dict[str, Any]]:
    """Parse tournaments from ÖTSV HTML table."""
    # Handle encoding
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", class_="oetsvTable")
    if not table:
        table = soup.find("table")
    if not table:
        return []

    tournaments = []
    rows = table.find_all("tr")

    for row in rows:
        tds = row.find_all("td")
        # Ensure it's not a header row
        if len(tds) < 4 or any("label" in td.get("class", []) for td in tds):
            continue

        datum_text = tds[0].get_text(strip=True)
        if not re.search(r'\d{1,2}\.\d{1,2}\.\d{4}', datum_text):
            continue

        title, klub = parse_bezeichnung_cell(tds[1])

        # Col 2: Tags (Disziplin / Alter)
        for br in tds[2].find_all("br"):
            br.replace_with(", ")
        raw_tags = tds[2].get_text(strip=True)
        tags = normalize_tags(raw_tags)

        # Col 3: Bundesland
        bundesland = tds[3].get_text(strip=True)
        bundesland = html.unescape(bundesland) if bundesland else None

        # Col 4: Links & Turnier-ID
        links: Dict[str, str] = {}
        turnier_id = None
        if len(tds) > 4:
            links, turnier_id = extract_links_and_id(tds[4])

        datum_sort = parse_iso_date(datum_text)

        tournaments.append({
            "turnier_id": turnier_id,
            "datum": datum_text,
            "datum_sort": datum_sort,
            "titel": title,
            "klub": klub,
            "bundesland": bundesland,
            "tags": tags,
            "links": links
        })

    return tournaments

async def fetch_month_data(client: httpx.AsyncClient, monat: int, jahr: int) -> str:
    """Fetch daten.html for a given month and year with resilient decoding."""
    url = f"{settings.SCRAPER_CALENDAR_URL}?monat={monat:02d}&jahr={jahr}"
    logger.info(f"Fetching calendar: {url}")
    resp = await client.get(url, timeout=settings.SCRAPER_TIMEOUT)
    resp.raise_for_status()

    # Try ISO-8859-1 first as ÖTSV serves ISO-8859-1, fallback to utf-8
    try:
        content = resp.content.decode("iso-8859-1")
    except UnicodeDecodeError:
        content = resp.content.decode("utf-8", errors="replace")
    return content

async def run_scraper() -> Dict[str, Any]:
    """Execute complete calendar scraping for rolling 12 months with idempotent upsert."""
    logger.info("Starting ÖTSV calendar scraping...")
    now_vienna = datetime.now(ZoneInfo(settings.TIMEZONE))
    start_month = now_vienna.month
    start_year = now_vienna.year

    # Update status to running
    with get_db_connection() as conn:
        conn.execute("UPDATE sync_status SET status = 'running', message = 'Scraping läuft...' WHERE key = 'scraper';")
        conn.commit()

    all_scraped = []
    added_count = 0
    updated_count = 0

    try:
        async with httpx.AsyncClient(headers={"User-Agent": "pivitLABS-OETSV-Tool/1.4 (+https://pivitlabs.com)"}) as client:
            for i in range(settings.SCRAPER_MONTHS_AHEAD):
                m = ((start_month - 1 + i) % 12) + 1
                y = start_year + ((start_month - 1 + i) // 12)
                try:
                    html_data = await fetch_month_data(client, m, y)
                    parsed = parse_html_table(html_data)
                    all_scraped.extend(parsed)
                except Exception as e:
                    logger.error(f"Error scraping month {m:02d}/{y}: {e}")

                if i < settings.SCRAPER_MONTHS_AHEAD - 1:
                    await asyncio.sleep(settings.SCRAPER_RATE_LIMIT_DELAY)

        # In-memory deduplication before saving
        unique_tournaments: Dict[str, Dict[str, Any]] = {}
        for t in all_scraped:
            key = f"{t['turnier_id']}" if t['turnier_id'] else f"{t['datum']}_{t['titel']}"
            unique_tournaments[key] = t

        # Idempotent database upsert
        with get_db_connection() as conn:
            cursor = conn.cursor()

            for t in unique_tournaments.values():
                turnier_id = t["turnier_id"]
                datum = t["datum"]
                datum_sort = t["datum_sort"]
                titel = t["titel"]
                klub = t["klub"]
                bundesland = t["bundesland"]
                tags_json = json.dumps(t["tags"], ensure_ascii=False)
                links_json = json.dumps(t["links"], ensure_ascii=False)

                existing_row = None
                if turnier_id is not None:
                    cursor.execute("SELECT id, turnier_id FROM turniere WHERE turnier_id = ?;", (turnier_id,))
                    existing_row = cursor.fetchone()

                if not existing_row:
                    cursor.execute("SELECT id, turnier_id FROM turniere WHERE datum = ? AND titel = ?;", (datum, titel))
                    existing_row = cursor.fetchone()

                if existing_row:
                    db_id = existing_row["id"]
                    cursor.execute("""
                        UPDATE turniere SET
                            turnier_id = COALESCE(?, turnier_id),
                            datum = ?,
                            datum_sort = ?,
                            titel = ?,
                            klub = ?,
                            bundesland = ?,
                            tags = ?,
                            links = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                    """, (turnier_id, datum, datum_sort, titel, klub, bundesland, tags_json, links_json, db_id))
                    updated_count += 1

                    # Relational match: link existing unlinked nennungen
                    effective_tid = turnier_id or existing_row["turnier_id"]
                    if effective_tid:
                        cursor.execute("""
                            UPDATE nennungen SET turnier_db_id = ? WHERE turnier_id = ? AND turnier_db_id IS NULL;
                        """, (db_id, effective_tid))
                else:
                    cursor.execute("""
                        INSERT INTO turniere (turnier_id, datum, datum_sort, titel, klub, bundesland, tags, links)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, (turnier_id, datum, datum_sort, titel, klub, bundesland, tags_json, links_json))
                    db_id = cursor.lastrowid
                    added_count += 1

                    if turnier_id:
                        cursor.execute("""
                            UPDATE nennungen SET turnier_db_id = ? WHERE turnier_id = ? AND turnier_db_id IS NULL;
                        """, (db_id, turnier_id))

            # Update sync_status
            last_run_str = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%d.%m.%Y %H:%M:%S")
            msg = f"{added_count} neu, {updated_count} aktualisiert ({len(unique_tournaments)} gescannt)"
            cursor.execute("""
                UPDATE sync_status SET
                    last_run = ?,
                    added_count = ?,
                    updated_count = ?,
                    status = 'success',
                    message = ?
                WHERE key = 'scraper';
            """, (last_run_str, added_count, updated_count, msg))
            conn.commit()

        logger.info(f"Calendar scraping complete: {added_count} added, {updated_count} updated.")
        return {
            "status": "success",
            "added_count": added_count,
            "updated_count": updated_count,
            "scanned": len(unique_tournaments)
        }

    except Exception as e:
        logger.exception(f"Scraper execution failed: {e}")
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE sync_status SET
                    status = 'error',
                    message = ?
                WHERE key = 'scraper';
            """, (str(e),))
            conn.commit()
        return {"status": "error", "message": str(e)}
