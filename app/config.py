import os
import re
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: str = "production"
    APP_VERSION: str = "1.4.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    TIMEZONE: str = "Europe/Vienna"

    # Security Settings
    ADMIN_PASSWORD: str = ""
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Club Configuration ("Verein einstellen")
    CLUB_NAME: str = "TSC Musterverein"
    CLUB_SHORT: str = "Musterverein"
    CLUB_KEYWORDS: str = ""

    # Paths
    DATABASE_PATH: str = "data/adsi.db"
    LOG_DIR: str = "logs"

    # Scraper
    SCRAPER_CALENDAR_URL: str = "https://www.tanzsportverband.at/kalender/daten.html"
    SCRAPER_MONTHS_AHEAD: int = 12
    SCRAPER_CRON_HOUR: int = 4
    SCRAPER_CRON_MINUTE: int = 0
    SCRAPER_RATE_LIMIT_DELAY: float = 0.5
    SCRAPER_TIMEOUT: float = 15.0

    # Teilnehmer Scraper (4x daily)
    TEILNEHMER_CRON_HOURS: str = "2,8,14,20"
    TEILNEHMER_CRON_MINUTE: int = 0
    TEILNEHMER_RATE_LIMIT_DELAY: float = 0.3
    TEILNEHMER_TIMEOUT: float = 15.0

    # IMAP Fetcher
    IMAP_ENABLED: bool = False
    IMAP_SERVER: str = ""
    IMAP_PORT: int = 993
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""
    IMAP_MAILBOX: str = "INBOX"
    IMAP_FETCH_INTERVAL_MINUTES: int = 15
    IMAP_ALLOWED_SENDERS: str = "noreply@tanzsportverband.at,office@tanzsportverband.at,nennungen@tanzsportverband.at,nennungen@oetsv.at,office@oetsv.at,oetsv.at"
    IMAP_TIMEOUT: float = 20.0
    IMAP_MOCK: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def allowed_senders_list(self) -> List[str]:
        return [s.strip().lower() for s in self.IMAP_ALLOWED_SENDERS.split(",") if s.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def club_short_label(self) -> str:
        if self.CLUB_SHORT and self.CLUB_SHORT.strip():
            return self.CLUB_SHORT.strip()
        return self.CLUB_NAME.split()[0] if self.CLUB_NAME.strip() else "Verein"

    @property
    def club_matching_tokens(self) -> List[str]:
        raw = self.CLUB_KEYWORDS.strip() if (self.CLUB_KEYWORDS and self.CLUB_KEYWORDS.strip()) else self.CLUB_NAME
        return [t.strip().lower() for t in re.split(r"[\s,;/\-]+", raw) if len(t.strip()) >= 2]

settings = Settings()
