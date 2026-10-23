import os
import re
import imaplib
from typing import Dict, Optional, Tuple
from app.config import settings

def sanitize_env_value(val: str) -> str:
    """Strip CR/LF characters to prevent .env newline injection."""
    return str(val).replace("\r", "").replace("\n", "")

def update_env_file(key_values: Dict[str, str], env_path: str = ".env") -> None:
    """Safely update or add key-value pairs in the .env file."""
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    keys_to_set = {}
    for k, v in key_values.items():
        if not re.match(r"^[A-Z0-9_]+$", k):
            raise ValueError(f"Invalid environment variable key: {k}")
        keys_to_set[k] = sanitize_env_value(v)

    new_lines = []

    for line in lines:
        stripped = line.strip()
        matched_key = None
        for k in keys_to_set:
            if re.match(rf"^{re.escape(k)}\s*=", stripped):
                matched_key = k
                break

        if matched_key:
            new_lines.append(f"{matched_key}={keys_to_set.pop(matched_key)}\n")
        else:
            new_lines.append(line)

    # Append any remaining new keys at the end
    if keys_to_set:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        for k, v in keys_to_set.items():
            new_lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass

def test_imap_connection(
    server: str,
    port: int,
    user: str,
    password: str,
    mailbox: str = "INBOX",
    timeout: float = 10.0
) -> Tuple[bool, str]:
    """Test connection and credentials to the IMAP server."""
    if not server:
        return False, "Server-Adresse darf nicht leer sein."
    if not user:
        return False, "Benutzername darf nicht leer sein."

    try:
        mail = imaplib.IMAP4_SSL(server, port, timeout=timeout)
        try:
            mail.login(user, password)
        except imaplib.IMAP4.error as auth_err:
            return False, f"Authentifizierungsfehler: {auth_err}"

        status, _ = mail.select(mailbox)
        if status != "OK":
            mail.logout()
            return False, f"Login erfolgreich, aber Mailbox '{mailbox}' konnte nicht geöffnet werden."

        mail.logout()
        return True, f"Verbindung erfolgreich! Login für '{user}' an '{server}:{port}' (Postfach: {mailbox}) war erfolgreich."
    except Exception as e:
        return False, f"Verbindungsfehler zu {server}:{port}: {str(e)}"
