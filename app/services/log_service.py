import os
import logging
from logging.handlers import RotatingFileHandler
from collections import deque
from typing import List, Dict
from app.config import settings

# Memory ring buffers for fast dashboard retrieval
LOG_BUFFERS: Dict[str, deque] = {
    "system": deque(maxlen=200),
    "scraper": deque(maxlen=200),
    "fetcher": deque(maxlen=200),
    "results_scraper": deque(maxlen=200),
    "teilnehmer_scraper": deque(maxlen=200),
}

class RingBufferHandler(logging.Handler):
    def __init__(self, buffer_key: str):
        super().__init__()
        self.buffer_key = buffer_key

    def emit(self, record):
        try:
            msg = self.format(record)
            if self.buffer_key in LOG_BUFFERS:
                LOG_BUFFERS[self.buffer_key].append(msg)
            # Also push to general system log buffer if distinct
            if self.buffer_key != "system":
                LOG_BUFFERS["system"].append(f"[{self.buffer_key.upper()}] {msg}")
        except Exception:
            self.handleError(record)

def setup_logging():
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler for main app
    app_log_path = os.path.join(settings.LOG_DIR, "adsi.log")
    file_handler = RotatingFileHandler(app_log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # System ring buffer
    root_logger.addHandler(RingBufferHandler("system"))

    # Dedicated Scraper logger
    scraper_logger = logging.getLogger("scraper")
    scraper_log_path = os.path.join(settings.LOG_DIR, "scraper.log")
    scraper_file = RotatingFileHandler(scraper_log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    scraper_file.setFormatter(formatter)
    scraper_logger.addHandler(scraper_file)
    scraper_logger.addHandler(RingBufferHandler("scraper"))

    # Dedicated Mail Fetcher logger
    fetcher_logger = logging.getLogger("fetcher")
    fetcher_log_path = os.path.join(settings.LOG_DIR, "mail_fetcher.log")
    fetcher_file = RotatingFileHandler(fetcher_log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    fetcher_file.setFormatter(formatter)
    fetcher_logger.addHandler(fetcher_file)
    fetcher_logger.addHandler(RingBufferHandler("fetcher"))

    # Dedicated Results Scraper logger
    results_logger = logging.getLogger("results_scraper")
    results_log_path = os.path.join(settings.LOG_DIR, "results_scraper.log")
    results_file = RotatingFileHandler(results_log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    results_file.setFormatter(formatter)
    results_logger.addHandler(results_file)
    results_logger.addHandler(RingBufferHandler("results_scraper"))

    # Dedicated Teilnehmer Scraper logger
    teilnehmer_logger = logging.getLogger("teilnehmer_scraper")
    teilnehmer_log_path = os.path.join(settings.LOG_DIR, "teilnehmer_scraper.log")
    teilnehmer_file = RotatingFileHandler(teilnehmer_log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    teilnehmer_file.setFormatter(formatter)
    teilnehmer_logger.addHandler(teilnehmer_file)
    teilnehmer_logger.addHandler(RingBufferHandler("teilnehmer_scraper"))

def get_logs(target: str = "system", limit: int = 100) -> List[str]:
    """Retrieve the latest log lines for target ('system', 'scraper', 'fetcher', 'results_scraper', 'teilnehmer_scraper')."""
    buf = LOG_BUFFERS.get(target, LOG_BUFFERS["system"])
    logs = list(buf)
    return logs[-limit:]
