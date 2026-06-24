"""
Vending Machine Sale Alert System - Main Runner

Orchestrates scrapers across all configured retailers/distributors,
deduplicates results, and fires notifications when deals are found.

Run manually:  python main.py
Run on a schedule: see scheduler.py or use a cron job

Usage:
  python main.py                    # run once immediately
  python main.py --dry-run          # show alerts without sending notifications
  python main.py --source woolworths  # only check one source
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.woolworths import WoolworthsScraper
from scrapers.coles import ColesScraper
from scrapers.campbells import CampbellsScraper, ManualPriceScraper
from notifier import notify, format_alerts_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CATALOGUE_PATH = os.path.join(os.path.dirname(__file__), "catalogue.json")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
ALERTS_LOG_PATH = os.path.join(os.path.dirname(__file__), "alerts_history.json")


def load_catalogue() -> List[Dict]:
    """Load vending machine product catalogue."""
    with open(CATALOGUE_PATH) as f:
        return json.load(f)["catalogue"]


def deduplicate_alerts(alerts: List[Dict]) -> List[Dict]:
    """
    Remove duplicate alerts for the same product across sources.
    Keeps the lowest price for each catalogue_id.
    """
    best = {}
    for alert in alerts:
        cid = alert["catalogue_id"]
        if cid not in best or alert["found_price"] < best[cid]["found_price"]:
            best[cid] = alert
    return sorted(best.values(), key=lambda x: x.get("discount_pct", 0), reverse=True)


def save_alerts_log(alerts: List[Dict]) -> None:
    """Append alerts to a local JSON history log."""
    history = []
    if os.path.exists(ALERTS_LOG_PATH):
        try:
            with open(ALERTS_LOG_PATH) as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []

    entry = {
        "run_at": datetime.now().isoformat(),
        "alerts": alerts,
    }
    history.append(entry)
    # Keep last 30 days of history
    history = history[-30:]

    with open(ALERTS_LOG_PATH, "w") as f:
        json.dump(history, f, indent=2)
    logger.info(f"[Main] Saved {len(alerts)} alerts to {ALERTS_LOG_PATH}")


def run(
    sources: List[str] = None,
    dry_run: bool = False,
    min_discount_pct: float = 0.0,
    beats_target_only: bool = False,
) -> List[Dict]:
    """
    Run the full sale alert check cycle.

    Args:
        sources: List of sources to check. None = all sources.
                 Options: "woolworths", "coles", "campbells", "manual"
        dry_run: If True, print alerts but do not send notifications.
        min_discount_pct: Only alert if discount is >= this percentage.
        beats_target_only: Only alert on products that beat your target buy price.

    Returns:
        List of de-duplicated sale alerts.
    """
    all_sources = sources or ["woolworths", "coles", "campbells", "manual"]
    logger.info(f"[Main] Starting check for sources: {all_sources}")

    catalogue = load_catalogue()
    logger.info(f"[Main] Loaded {len(catalogue)} products from catalogue")

    all_alerts = []

    # ── Woolworths ──
    if "woolworths" in all_sources:
        try:
            logger.info("[Main] Checking Woolworths...")
            scraper = WoolworthsScraper()
            alerts = scraper.check_catalogue_items(catalogue)
            logger.info(f"[Main] Woolworths: {len(alerts)} alerts")
            all_alerts.extend(alerts)
        except Exception as e:
            logger.error(f"[Main] Woolworths scraper failed: {e}")

    # ── Coles ──
    if "coles" in all_sources:
        try:
            logger.info("[Main] Checking Coles...")
            scraper = ColesScraper()
            alerts = scraper.check_catalogue_items(catalogue)
            logger.info(f"[Main] Coles: {len(alerts)} alerts")
            all_alerts.extend(alerts)
        except Exception as e:
            logger.error(f"[Main] Coles scraper failed: {e}")

    # ── Campbells Wholesale ──
    if "campbells" in all_sources:
        try:
            logger.info("[Main] Checking Campbells...")
            # Pass credentials from config if available
            cfg = {}
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH) as f:
                    cfg = json.load(f)
            scraper = CampbellsScraper(
                username=cfg.get("campbells", {}).get("username"),
                password=cfg.get("campbells", {}).get("password"),
            )
            alerts = scraper.check_catalogue_items(catalogue)
            logger.info(f"[Main] Campbells: {len(alerts)} alerts")
            all_alerts.extend(alerts)
        except Exception as e:
            logger.error(f"[Main] Campbells scraper failed: {e}")

    # ── Manual price CSV ──
    if "manual" in all_sources:
        try:
            logger.info("[Main] Checking manual prices...")
            scraper = ManualPriceScraper()
            alerts = scraper.check_catalogue_items(catalogue)
            logger.info(f"[Main] Manual: {len(alerts)} alerts")
            all_alerts.extend(alerts)
        except Exception as e:
            logger.error(f"[Main] Manual price scraper failed: {e}")

    # ── Filter ──
    if min_discount_pct > 0:
        all_alerts = [a for a in all_alerts if a.get("discount_pct", 0) >= min_discount_pct]
    if beats_target_only:
        all_alerts = [a for a in all_alerts if a.get("beats_target")]

    # ── Deduplicate ──
    alerts = deduplicate_alerts(all_alerts)
    logger.info(f"[Main] Total unique alerts after dedup: {len(alerts)}")

    if not alerts:
        logger.info("[Main] No sale alerts found this run.")
        return []

    # ── Log to file ──
    save_alerts_log(alerts)

    # ── Display ──
    print(format_alerts_text(alerts))

    # ── Notify ──
    if dry_run:
        logger.info("[Main] Dry run mode - skipping notifications")
    else:
        results = notify(alerts, config_path=CONFIG_PATH)
        if not any(results.values()):
            logger.warning("[Main] No notification channels sent successfully. Check config.json.")

    return alerts


def main():
    parser = argparse.ArgumentParser(description="Vending Machine Sale Alert System")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Check for sales but do not send notifications"
    )
    parser.add_argument(
        "--source", type=str, default=None,
        choices=["woolworths", "coles", "campbells", "manual"],
        help="Check only a specific source"
    )
    parser.add_argument(
        "--min-discount", type=float, default=0.0,
        help="Minimum discount %% to trigger an alert (default: 0 = any sale)"
    )
    parser.add_argument(
        "--beats-target-only", action="store_true",
        help="Only alert on products that beat your target buy price"
    )
    args = parser.parse_args()

    sources = [args.source] if args.source else None
    run(
        sources=sources,
        dry_run=args.dry_run,
        min_discount_pct=args.min_discount,
        beats_target_only=args.beats_target_only,
    )


if __name__ == "__main__":
    main()
