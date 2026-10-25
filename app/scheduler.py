import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import get_db_connection
from app.services.scraper import run_scraper
from app.services.mail_fetcher import run_mail_fetcher
from app.services.results_scraper import run_results_scraper
from app.services.teilnehmer_scraper import run_teilnehmer_scraper
from app.services.storage_service import push_to_cloud

logger = logging.getLogger("scheduler")

scheduler: Optional[AsyncIOScheduler] = None

# Concurrency locks and active job tracking
JOB_LOCKS = {
    "scraper": asyncio.Lock(),
    "fetcher": asyncio.Lock(),
    "results_scraper": asyncio.Lock(),
    "teilnehmer_scraper": asyncio.Lock()
}

ACTIVE_JOBS = {
    "scraper": False,
    "fetcher": False,
    "results_scraper": False,
    "teilnehmer_scraper": False
}

async def execute_scraper_job():
    """Execute scraper protected by lock to prevent concurrent runs."""
    if ACTIVE_JOBS["scraper"]:
        logger.warning("Scraper job is already running, skipping execution.")
        return {"status": "skipped", "message": "Scraper läuft bereits."}

    async with JOB_LOCKS["scraper"]:
        ACTIVE_JOBS["scraper"] = True
        try:
            res = await run_scraper()
            push_to_cloud(reason="scraper")
            return res
        finally:
            ACTIVE_JOBS["scraper"] = False

async def execute_fetcher_job():
    """Execute mail fetcher in threadpool protected by lock."""
    if ACTIVE_JOBS["fetcher"]:
        logger.warning("Fetcher job is already running, skipping execution.")
        return {"status": "skipped", "message": "Mail-Fetcher läuft bereits."}

    async with JOB_LOCKS["fetcher"]:
        ACTIVE_JOBS["fetcher"] = True
        try:
            # run synchronous IMAP fetcher in asyncio threadpool to avoid blocking event loop
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, run_mail_fetcher)
            push_to_cloud(reason="fetcher")
            return res
        finally:
            ACTIVE_JOBS["fetcher"] = False

async def execute_results_scraper_job():
    """Execute results scraper protected by lock to prevent concurrent runs."""
    if ACTIVE_JOBS["results_scraper"]:
        logger.warning("Results scraper job is already running, skipping execution.")
        return {"status": "skipped", "message": "Ergebnisse-Scraper läuft bereits."}

    async with JOB_LOCKS["results_scraper"]:
        ACTIVE_JOBS["results_scraper"] = True
        try:
            res = await run_results_scraper()
            push_to_cloud(reason="results_scraper")
            return res
        finally:
            ACTIVE_JOBS["results_scraper"] = False

async def execute_teilnehmer_scraper_job():
    """Execute participant list scraper protected by lock to prevent concurrent runs."""
    if ACTIVE_JOBS["teilnehmer_scraper"]:
        logger.warning("Teilnehmer scraper job is already running, skipping execution.")
        return {"status": "skipped", "message": "Teilnehmer-Scraper läuft bereits."}

    async with JOB_LOCKS["teilnehmer_scraper"]:
        ACTIVE_JOBS["teilnehmer_scraper"] = True
        try:
            res = await run_teilnehmer_scraper()
            push_to_cloud(reason="teilnehmer_scraper")
            return res
        finally:
            ACTIVE_JOBS["teilnehmer_scraper"] = False

def start_scheduler():
    """Initialize and start background jobs."""
    global scheduler
    if scheduler is not None and scheduler.running:
        return

    tz = ZoneInfo(settings.TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)

    # 1. Scraper: Täglich um 04:00 Uhr Wien (FA-3.2)
    scraper_trigger = CronTrigger(
        hour=settings.SCRAPER_CRON_HOUR,
        minute=settings.SCRAPER_CRON_MINUTE,
        timezone=tz
    )
    scheduler.add_job(
        execute_scraper_job,
        trigger=scraper_trigger,
        id="scraper_daily",
        name="ÖTSV Web Scraper",
        replace_existing=True
    )

    # 2. Mail Fetcher: Alle 15 Minuten (FA-3.1)
    fetcher_trigger = IntervalTrigger(
        minutes=settings.IMAP_FETCH_INTERVAL_MINUTES,
        timezone=tz
    )
    scheduler.add_job(
        execute_fetcher_job,
        trigger=fetcher_trigger,
        id="mail_fetcher_interval",
        name="IMAP Mail Fetcher",
        replace_existing=True
    )

    # 3. Results Scraper: Täglich um 06:00 und 20:00 Uhr Wien
    results_trigger = CronTrigger(
        hour="6,20",
        minute=0,
        timezone=tz
    )
    scheduler.add_job(
        execute_results_scraper_job,
        trigger=results_trigger,
        id="results_scraper_daily",
        name="ÖTSV Ergebnisse Scraper",
        replace_existing=True
    )

    # 4. Teilnehmerlisten Scraper: 4x täglich (02:00, 08:00, 14:00, 20:00 Uhr Wien)
    teilnehmer_trigger = CronTrigger(
        hour=settings.TEILNEHMER_CRON_HOURS,
        minute=settings.TEILNEHMER_CRON_MINUTE,
        timezone=tz
    )
    scheduler.add_job(
        execute_teilnehmer_scraper_job,
        trigger=teilnehmer_trigger,
        id="teilnehmer_scraper_4daily",
        name="ÖTSV Teilnehmerlisten Scraper",
        replace_existing=True
    )

    scheduler.start()
    logger.info("APScheduler started successfully.")

    # Catch-up check for desktop app usage: if the database has no tournaments yet or
    # the last calendar scrape is older than 24h, trigger a background catch-up only when running in production.
    if settings.APP_ENV == "production":
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_startup_catchup_check())
        except RuntimeError:
            pass


async def _startup_catchup_check():
    """When launched as a desktop app, check if a stale sync (>24h) should be caught up."""
    await asyncio.sleep(3.0)
    try:
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        need_scraper = False
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM turniere;")
            t_cnt = cur.fetchone()["cnt"]
            cur.execute("SELECT last_run FROM sync_status WHERE key = 'scraper';")
            row = cur.fetchone()
            last_run_str = row["last_run"] if row else None

        if t_cnt == 0:
            need_scraper = True
        elif last_run_str:
            try:
                dt = datetime.strptime(last_run_str, "%d.%m.%Y %H:%M:%S").replace(tzinfo=tz)
                if (now - dt).total_seconds() > 86400:
                    need_scraper = True
            except Exception:
                pass

        if need_scraper:
            logger.info("Desktop Catch-Up: Starte Kalender-Scraper im Hintergrund (Daten älter als 24h oder leer).")
            await execute_scraper_job()
    except Exception as e:
        logger.debug(f"Startup Catch-Up Check übersprungen: {e}")

def shutdown_scheduler():
    global scheduler
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down.")

def get_job_info() -> Dict[str, Any]:
    """Retrieve running jobs and next execution timestamps."""
    running = [k for k, v in ACTIVE_JOBS.items() if v]
    next_runs: Dict[str, Optional[str]] = {
        "scraper": None,
        "fetcher": None,
        "results_scraper": None,
        "teilnehmer_scraper": None
    }

    if scheduler and scheduler.running:
        scraper_job = scheduler.get_job("scraper_daily")
        if scraper_job and scraper_job.next_run_time:
            next_runs["scraper"] = scraper_job.next_run_time.strftime("%d.%m.%Y %H:%M:%S")

        fetcher_job = scheduler.get_job("mail_fetcher_interval")
        if fetcher_job and fetcher_job.next_run_time:
            next_runs["fetcher"] = fetcher_job.next_run_time.strftime("%d.%m.%Y %H:%M:%S")

        results_job = scheduler.get_job("results_scraper_daily")
        if results_job and results_job.next_run_time:
            next_runs["results_scraper"] = results_job.next_run_time.strftime("%d.%m.%Y %H:%M:%S")

        teilnehmer_job = scheduler.get_job("teilnehmer_scraper_4daily")
        if teilnehmer_job and teilnehmer_job.next_run_time:
            next_runs["teilnehmer_scraper"] = teilnehmer_job.next_run_time.strftime("%d.%m.%Y %H:%M:%S")

    return {
        "running_jobs": running,
        "next_runs": next_runs
    }
