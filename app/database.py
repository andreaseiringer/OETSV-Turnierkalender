import os
import sqlite3
from typing import Generator
from contextlib import contextmanager
from app.config import settings

def get_db_path() -> str:
    return settings.DATABASE_PATH

def init_db():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")

        cursor = conn.cursor()

        # 1. turniere
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS turniere (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turnier_id INTEGER,
                datum TEXT NOT NULL,
                datum_sort TEXT NOT NULL,
                titel TEXT NOT NULL,
                klub TEXT,
                bundesland TEXT,
                tags TEXT DEFAULT '[]',
                links TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_turniere_turnier_id ON turniere(turnier_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_turniere_datum_sort ON turniere(datum_sort);")

        # 2. nennungen
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nennungen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nennungs_id TEXT NOT NULL,
                paar_name TEXT NOT NULL,
                min_partner_1 TEXT,
                min_partner_2 TEXT,
                klub TEXT,
                turnier_id INTEGER NOT NULL,
                turnier_db_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (turnier_db_id) REFERENCES turniere(id) ON DELETE SET NULL,
                UNIQUE (nennungs_id, turnier_id)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nennungen_turnier_id ON nennungen(turnier_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nennungen_turnier_db_id ON nennungen(turnier_db_id);")

        # 3. nennungs_klassen
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nennungs_klassen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nennung_db_id INTEGER NOT NULL,
                datum TEXT NOT NULL,
                klasse TEXT NOT NULL,
                FOREIGN KEY (nennung_db_id) REFERENCES nennungen(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nennungs_klassen_nennung ON nennungs_klassen(nennung_db_id);")

        # 4. turnier_ergebnisse
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS turnier_ergebnisse (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turnier_db_id INTEGER NOT NULL,
                turnier_id INTEGER NOT NULL,
                klasse_name TEXT NOT NULL,
                klasse_slug TEXT NOT NULL,
                platz TEXT NOT NULL,
                platz_sort INTEGER,
                total_paare INTEGER DEFAULT 0,
                paar_name TEXT NOT NULL,
                startnr TEXT,
                klub TEXT,
                runde TEXT,
                bericht_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (turnier_db_id) REFERENCES turniere(id) ON DELETE CASCADE,
                UNIQUE (turnier_id, klasse_slug, paar_name)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ergebnisse_turnier_id ON turnier_ergebnisse(turnier_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ergebnisse_turnier_db_id ON turnier_ergebnisse(turnier_db_id);")

        # 5. turnier_teilnehmer
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS turnier_teilnehmer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turnier_db_id INTEGER NOT NULL,
                turnier_id INTEGER NOT NULL,
                klasse TEXT NOT NULL,
                paar_name TEXT NOT NULL,
                klub TEXT,
                is_utsc INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (turnier_db_id) REFERENCES turniere(id) ON DELETE CASCADE,
                UNIQUE (turnier_db_id, klasse, paar_name)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_teilnehmer_turnier_id ON turnier_teilnehmer(turnier_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_teilnehmer_turnier_db_id ON turnier_teilnehmer(turnier_db_id);")

        # 6. sync_status
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_status (
                key TEXT PRIMARY KEY,
                last_run TEXT,
                added_count INTEGER DEFAULT 0,
                updated_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'idle',
                message TEXT DEFAULT ''
            );
        """)

        # Ensure default rows in sync_status
        for key in ["scraper", "fetcher", "results_scraper", "teilnehmer_scraper"]:
            cursor.execute("""
                INSERT OR IGNORE INTO sync_status (key, last_run, added_count, updated_count, status, message)
                VALUES (?, NULL, 0, 0, 'idle', 'Initialisiert');
            """, (key,))

        conn.commit()

@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager providing a configured SQLite connection."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
    finally:
        conn.close()
