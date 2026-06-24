"""
Vending Alerts Scheduler

Runs the sale alert check on a configurable schedule.
Uses APScheduler for reliable in-process scheduling.

Alternatively, use system cron instead of this file.
Example cron (run at 7am and 6pm daily):
  0 7,18 * * * cd /path/to/Vending-Alerts && python main.py >> logs/cron.log 2>&1

Run this scheduler as a long-running process:
  python scheduler.py
"""

import logging
import os
import json
from datetime import datetime

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_SCHEDULE = {
    "morning_check": {"hour": 7, "minute": 0, "day_of_week": "mon-fri"},
    "afternoon_check": {"hour": 14, "minute": 0, "day_of_week": "mon-fri"},
    "weekend_check": {"hour": 9, "minute": 0, "day_of_week": "sat,sun"},
}


def load_schedule_config() -> dict:
    """Load schedule config from config.json, fall back to defaults."""
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        return config.get("schedule", DEFAULT_SCHEDULE)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SCHEDULE


def run_check():
    """Run a single sale check cycle (called by scheduler)."""
    logger.info(f"[Scheduler] Triggered check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        from main import run
        alerts = run()
        logger.info(f"[Scheduler] Check complete. {len(alerts)} alert(s) found.")
    except Exception as e:
        logger.error(f"[Scheduler] Check failed: {e}", exc_info=True)


def start_scheduler():
    """Start the APScheduler-based scheduler."""
    if not HAS_APSCHEDULER:
        print("APScheduler not installed. Run: pip install apscheduler")
        print("Alternatively, set up a cron job with: python main.py")
        return

    schedule_config = load_schedule_config()
    scheduler = BlockingScheduler(timezone="Australia/Sydney")

    for job_name, cron_args in schedule_config.items():
        trigger = CronTrigger(
            hour=cron_args.get("hour", 9),
            minute=cron_args.get("minute", 0),
            day_of_week=cron_args.get("day_of_week", "*"),
            timezone="Australia/Sydney",
        )
        scheduler.add_job(
            run_check,
            trigger=trigger,
            id=job_name,
            name=f"Vending Alert Check - {job_name}",
            misfire_grace_time=300,
        )
        logger.info(f"[Scheduler] Scheduled job '{job_name}': {cron_args}")

    logger.info("[Scheduler] Scheduler started. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[Scheduler] Stopped.")


def start_simple_scheduler():
    """
    Simple fallback scheduler using Python stdlib only.
    Checks every N hours. No APScheduler required.
    """
    import time

    check_interval_hours = 12

    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        check_interval_hours = cfg.get("schedule", {}).get("interval_hours", 12)
    except Exception:
        pass

    interval_seconds = check_interval_hours * 3600
    logger.info(f"[Scheduler] Simple scheduler: checking every {check_interval_hours} hours")

    # Run immediately on start
    run_check()

    while True:
        import time
        logger.info(f"[Scheduler] Next check in {check_interval_hours} hours")
        time.sleep(interval_seconds)
        run_check()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if HAS_APSCHEDULER:
        print("Starting APScheduler-based scheduler...")
        start_scheduler()
    else:
        print("APScheduler not found. Using simple interval scheduler.")
        start_simple_scheduler()
