import re
import html
import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header
from typing import Dict, List, Optional, Tuple, Any
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

from app.config import settings
from app.database import get_db_connection

logger = logging.getLogger("fetcher")

def decode_mime_header(raw_header: Optional[str]) -> str:
    """Decode encoded MIME header fields."""
    if not raw_header:
        return ""
    decoded_fragments = []
    for part, enc in decode_header(raw_header):
        if isinstance(part, bytes):
            decoded_fragments.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded_fragments.append(str(part))
    return " ".join(decoded_fragments)

def extract_email_body(msg: email.message.Message) -> str:
    """Extract plain text or cleaned HTML body from an email message."""
    plain_text = ""
    html_text = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue

            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if not payload:
                continue

            try:
                decoded = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                decoded = payload.decode("latin-1", errors="replace")

            if content_type == "text/plain":
                plain_text += "\n" + decoded
            elif content_type == "text/html":
                html_text += "\n" + decoded
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                decoded = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                decoded = payload.decode("latin-1", errors="replace")
            if msg.get_content_type() == "text/html":
                html_text = decoded
            else:
                plain_text = decoded

    if plain_text.strip():
        return plain_text.strip()

    if html_text.strip():
        soup = BeautifulSoup(html_text, "html.parser")
        for br in soup.find_all(["br", "p", "div", "tr"]):
            br.replace_with("\n")
        return soup.get_text().strip()

    return ""

def parse_nennung_content(text: str) -> Optional[Dict[str, Any]]:
    """Parse registration details from tournament confirmation email text according to FA-2.3."""
    # 1. Paarname: "Liebes Paar <Name>"
    m_paar = re.search(r'Liebes\s+Paar\s+([^\n\r]+)', text, re.IGNORECASE)
    if not m_paar:
        return None
    raw_paar = m_paar.group(1).strip()
    # Split off inline "Ihre Nennungs-ID" or "Nennungs-ID" if on the same line
    raw_paar = re.split(r',?\s*Ihre\s+Nennungs-ID', raw_paar, flags=re.IGNORECASE)[0]
    raw_paar = re.split(r',?\s*Nennungs-ID', raw_paar, flags=re.IGNORECASE)[0]
    paar_name = raw_paar.rstrip(',. -').strip()
    # If " - " separates the partners, normalize to " & "
    if " - " in paar_name and " & " not in paar_name:
        paar_name = paar_name.replace(" - ", " & ")

    # 2. Nennungs-ID: "Ihre Nennungs-ID lautet <ID>" or "Nennungs-ID: <ID>"
    m_nid = re.search(r'(?:Ihre\s+Nennungs-ID\s+lautet|Nennungs-ID\s*:?)\s*([A-Za-z0-9\-]+)', text, re.IGNORECASE)
    nennungs_id = m_nid.group(1).strip() if m_nid else None
    if not nennungs_id:
        return None

    # 3. MIN Partner 1 & MIN Partner 2
    min_1 = None
    min_2 = None
    m_min1 = re.search(r'MIN\s+Partner(?:(?::in)|\.|\s+in)?\s*1\s*:\s*([A-Za-z0-9\-]+)', text, re.IGNORECASE)
    if m_min1:
        min_1 = m_min1.group(1).strip()
    m_min2 = re.search(r'MIN\s+Partner(?:(?::in)|\.|\s+in)?\s*2\s*:\s*([A-Za-z0-9\-]+)', text, re.IGNORECASE)
    if m_min2:
        min_2 = m_min2.group(1).strip()

    # 4. Klub: "Klub: <Name>"
    m_klub = re.search(r'Klub\s*:\s*([^\n\r]+)', text, re.IGNORECASE)
    klub = m_klub.group(1).strip() if m_klub else None
    if klub and settings.CLUB_NAME:
        # If email only states city/short part (e.g. "Musterverein" for "TSC Musterverein"), normalize to configured club name
        tokens = settings.club_matching_tokens
        if klub.lower() in [t.lower() for t in tokens] or klub.lower() == settings.CLUB_NAME.lower():
            klub = settings.CLUB_NAME

    # 5. Verbands-Turnier-ID: "TASNr=<ID>" or "TKNr=<ID>" or "Turnier-Nr: <ID>"
    m_tid = re.search(r'[?&]?(?:TASNr|TKNr)\s*=\s*(\d+)', text, re.IGNORECASE)
    if not m_tid:
        m_tid = re.search(r'Turnier(?:-|\s+)?(?:Nr|Nummer|ID)?\s*:\s*(\d+)', text, re.IGNORECASE)
    if not m_tid:
        return None
    turnier_id = int(m_tid.group(1))

    # 6. Startklassen mit Datum: "<DD. MM. YYYY>: <Klassenbezeichnung>" or "<DD.MM.YYYY>: <Klassenbezeichnung>"
    klassen: List[Tuple[str, str]] = []
    klasse_matches = re.finditer(r'(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*:\s*([^\n\r]+)', text)
    for km in klasse_matches:
        day, month, year = int(km.group(1)), int(km.group(2)), km.group(3)
        datum_str = f"{day:02d}.{month:02d}.{year}"
        klasse_str = km.group(4).strip()
        # Clean up any trailing punctuation or unwanted words
        klasse_str = re.sub(r'[\r\n]+', ' ', klasse_str).strip()
        if klasse_str and not klasse_str.lower().startswith("liebes") and not klasse_str.lower().startswith("um ihre nennung"):
            klassen.append((datum_str, klasse_str))

    return {
        "paar_name": paar_name,
        "nennungs_id": nennungs_id,
        "min_partner_1": min_1,
        "min_partner_2": min_2,
        "klub": klub,
        "turnier_id": turnier_id,
        "klassen": klassen
    }

def save_nennung_atomic(data: Dict[str, Any]) -> bool:
    """Idempotently and atomically save registration and start classes to the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check for duplicate / existing
        cursor.execute(
            "SELECT id FROM nennungen WHERE nennungs_id = ? AND turnier_id = ?;",
            (data["nennungs_id"], data["turnier_id"])
        )
        existing_row = cursor.fetchone()

        if existing_row:
            nennung_db_id = existing_row["id"]
            # Check if classes changed or were added (Sammelbestätigung)
            cursor.execute("SELECT datum, klasse FROM nennungs_klassen WHERE nennung_db_id = ?;", (nennung_db_id,))
            existing_classes = {(r["datum"], r["klasse"]) for r in cursor.fetchall()}
            new_classes = set(data["klassen"])

            if new_classes and new_classes != existing_classes:
                cursor.execute("DELETE FROM nennungs_klassen WHERE nennung_db_id = ?;", (nennung_db_id,))
                for datum, klasse in data["klassen"]:
                    cursor.execute("""
                        INSERT INTO nennungs_klassen (nennung_db_id, datum, klasse)
                        VALUES (?, ?, ?);
                    """, (nennung_db_id, datum, klasse))
                conn.commit()
                logger.info(f"Updated classes for registration {data['nennungs_id']}: {len(data['klassen'])} classes")
                return True

            logger.info(f"Existing registration up-to-date: Nennung {data['nennungs_id']} for tournament {data['turnier_id']}")
            return False

        # Find matching tournament
        cursor.execute("SELECT id FROM turniere WHERE turnier_id = ?;", (data["turnier_id"],))
        tournament_row = cursor.fetchone()
        turnier_db_id = tournament_row["id"] if tournament_row else None

        # Insert nennung
        cursor.execute("""
            INSERT INTO nennungen (nennungs_id, paar_name, min_partner_1, min_partner_2, klub, turnier_id, turnier_db_id)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            data["nennungs_id"],
            data["paar_name"],
            data["min_partner_1"],
            data["min_partner_2"],
            data["klub"],
            data["turnier_id"],
            turnier_db_id
        ))
        nennung_db_id = cursor.lastrowid

        # Insert klassen
        for datum, klasse in data["klassen"]:
            cursor.execute("""
                INSERT INTO nennungs_klassen (nennung_db_id, datum, klasse)
                VALUES (?, ?, ?);
            """, (nennung_db_id, datum, klasse))

        conn.commit()
        logger.info(f"Inserted registration {data['nennungs_id']} for couple {data['paar_name']} ({len(data['klassen'])} classes)")
        return True

MOCK_EMAILS = [
    """From: nennungen@tanzsportverband.at
Subject: Nennungsbestaetigung ÖTSV TASNr 1777

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
""",
    """From: nennungen@tanzsportverband.at
Subject: Nennungsbestaetigung ÖTSV TASNr 1776

Liebes Paar Max Mustermann & Maria Mustermann,

Ihre Nennungs-ID lautet N-2026-55443
MIN Partner:in 1: 45012 / MIN Partner:in 2: 45013
Klub: TSC Musterverein
Turnier-Nr: TASNr=1776

Gemeldete Klassen:
19.09.2026: Allg. Kl. Latein A

Mit sportlichen Grüßen,
ÖTSV Meldewesen
""",
    """From: office@tanzsportverband.at
Subject: Nennung Turniersport TASNr 1780

Liebes Paar Max Mustermann & Maria Mustermann
Ihre Nennungs-ID lautet N-2026-11223
MIN Partner:in 1: 45012 / MIN Partner:in 2: 45013
Klub: TSC Musterverein
Turnier-Nr: TASNr=1780

Gemeldete Klassen:
26.09.2026: Sen. II Standard S
27.09.2026: Sen. II Latein S
"""
]

def is_sender_whitelisted(sender_email: str, allowed_senders: List[str]) -> bool:
    """Strictly verify if an email address matches an allowed address or domain."""
    if not allowed_senders:
        return True
    sender = (sender_email or "").strip().lower()
    if not sender or "@" not in sender:
        return False
    _, sender_domain = sender.rsplit("@", 1)
    for raw_allowed in allowed_senders:
        allowed = raw_allowed.strip().lower()
        if not allowed:
            continue
        if "@" in allowed:
            if sender == allowed:
                return True
        else:
            domain = allowed.lstrip("@.")
            if sender_domain == domain or sender_domain.endswith("." + domain):
                return True
    return False


def run_mock_mail_fetcher() -> Dict[str, Any]:
    """Import mock tournament registration emails for local development and testing."""
    logger.info("Executing mock mail fetcher (IMAP_MOCK=True)...")
    with get_db_connection() as conn:
        conn.execute("UPDATE sync_status SET status = 'running', message = 'Mock-Mail-Abruf läuft...' WHERE key = 'fetcher';")
        conn.commit()

    added_count = 0
    allowed_senders = settings.allowed_senders_list

    for raw_email_str in MOCK_EMAILS:
        msg = email.message_from_string(raw_email_str)
        from_header = decode_mime_header(msg.get("From", ""))
        sender_match = re.search(r'<([^>]+)>', from_header)
        sender_email = sender_match.group(1).lower() if sender_match else from_header.lower().strip()

        if not is_sender_whitelisted(sender_email, allowed_senders):
            logger.warning(f"[MOCK] Ignored email from non-whitelisted sender: {sender_email}")
            continue

        body_text = extract_email_body(msg)
        parsed_data = parse_nennung_content(body_text)
        if parsed_data:
            if settings.CLUB_NAME:
                parsed_data["klub"] = settings.CLUB_NAME
            if save_nennung_atomic(parsed_data):
                added_count += 1
            else:
                logger.info(f"[MOCK] Nennung {parsed_data['nennungs_id']} bereits in Datenbank vorhanden.")

    last_run_str = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%d.%m.%Y %H:%M:%S")
    msg = f"{added_count} Test-Nennung(en) importiert (Mock-Modus)"
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE sync_status SET
                last_run = ?,
                added_count = ?,
                status = 'success',
                message = ?
            WHERE key = 'fetcher';
        """, (last_run_str, added_count, msg))
        conn.commit()

    logger.info(f"Mock mail fetcher complete: {added_count} newly imported.")
    return {"status": "success", "added_count": added_count, "mode": "mock"}

def run_mail_fetcher() -> Dict[str, Any]:
    """Execute IMAP email fetching, filtering, parsing, and database persistence."""
    logger.info("Starting mail fetcher check...")

    if settings.IMAP_MOCK:
        return run_mock_mail_fetcher()

    if not settings.IMAP_ENABLED or not settings.IMAP_SERVER or not settings.IMAP_USER:
        logger.info("IMAP is disabled or not configured in settings. Skipping fetch.")
        with get_db_connection() as conn:
            last_run_str = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%d.%m.%Y %H:%M:%S")
            conn.execute("""
                UPDATE sync_status SET
                    last_run = ?,
                    status = 'idle',
                    message = 'IMAP deaktiviert / nicht konfiguriert'
                WHERE key = 'fetcher';
            """, (last_run_str,))
            conn.commit()
        return {"status": "skipped", "message": "IMAP not configured"}

    with get_db_connection() as conn:
        conn.execute("UPDATE sync_status SET status = 'running', message = 'Mail-Abruf läuft...' WHERE key = 'fetcher';")
        conn.commit()

    added_count = 0
    allowed_senders = settings.allowed_senders_list

    try:
        mail = imaplib.IMAP4_SSL(settings.IMAP_SERVER, settings.IMAP_PORT, timeout=settings.IMAP_TIMEOUT)
        mail.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
        mail.select(settings.IMAP_MAILBOX)

        # Search for ALL emails (both unread and read, as requested)
        status, response = mail.search(None, 'ALL')
        if status != "OK" or not response or not response[0]:
            mail.logout()
            last_run_str = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%d.%m.%Y %H:%M:%S")
            with get_db_connection() as conn:
                conn.execute("""
                    UPDATE sync_status SET
                        last_run = ?,
                        added_count = 0,
                        status = 'success',
                        message = 'Keine E-Mails im Postfach'
                    WHERE key = 'fetcher';
                """, (last_run_str,))
                conn.commit()
            return {"status": "success", "added_count": 0}

        email_ids = response[0].split()
        email_ids.reverse()  # Check newest emails first
        logger.info(f"Checking {len(email_ids)} email(s) in mailbox (ALL)...")

        for eid in email_ids:
            res, msg_data = mail.fetch(eid, '(RFC822)')
            if res != "OK" or not msg_data:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            from_header = decode_mime_header(msg.get("From", ""))
            sender_match = re.search(r'<([^>]+)>', from_header)
            sender_email = sender_match.group(1).lower() if sender_match else from_header.lower().strip()

            body_text = extract_email_body(msg)

            # Check if forwarded email, extract original sender if present
            fwd_match = re.search(r'(?:Von|From)\s*:\s*<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?', body_text, re.IGNORECASE)
            fwd_sender = fwd_match.group(1).lower() if fwd_match else ""

            # Strict Whitelist verification
            is_allowed = is_sender_whitelisted(sender_email, allowed_senders) or (
                bool(fwd_sender) and is_sender_whitelisted(fwd_sender, allowed_senders)
            )

            if not is_allowed:
                continue

            parsed_data = parse_nennung_content(body_text)

            if parsed_data:
                if save_nennung_atomic(parsed_data):
                    added_count += 1
                # Mark as seen in mailbox (FA-2.4)
                mail.store(eid, '+FLAGS', '\\Seen')
            else:
                if fwd_sender or any(s in sender_email for s in ["oetsv", "tanzsportverband"]):
                    logger.debug(f"Email {eid.decode()} from {sender_email} (fwd: {fwd_sender}) did not match nennung format.")

        mail.logout()

        last_run_str = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%d.%m.%Y %H:%M:%S")
        msg = f"{added_count} Nennung(en) importiert"
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE sync_status SET
                    last_run = ?,
                    added_count = ?,
                    status = 'success',
                    message = ?
                WHERE key = 'fetcher';
            """, (last_run_str, added_count, msg))
            conn.commit()

        logger.info(f"Mail fetcher completed: {added_count} imported.")
        return {"status": "success", "added_count": added_count}

    except Exception as e:
        logger.exception(f"Mail fetcher failed: {e}")
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE sync_status SET
                    status = 'error',
                    message = ?
                WHERE key = 'fetcher';
            """, (str(e),))
            conn.commit()
        return {"status": "error", "message": str(e)}
