"""
Campbells Cash and Carry / Distributor Scraper
Scrapes wholesale distributor sites for sale prices on vending machine products.
Supports: Campbells Wholesale, PFD Food Services, and a manual price entry fallback.

Note: Distributor sites often require login. This module handles:
  1. Public price pages (no login needed)
  2. Authenticated sessions (if credentials are configured)
  3. Manual CSV/price-list import as a fallback
"""

import requests
import json
import logging
import csv
import io
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-AU,en;q=0.9",
}

# Campbells Wholesale base URL
CAMPBELLS_BASE_URL = "https://www.campbellswholesale.com.au"
CAMPBELLS_SEARCH_URL = "https://www.campbellswholesale.com.au/catalogsearch/result/"

# PFD Food Services
PFD_BASE_URL = "https://www.pfd.com.au"
PFD_SEARCH_URL = "https://www.pfd.com.au/search"


class CampbellsScraper:
    """
    Scrapes Campbells Wholesale / Cash and Carry for sale pricing.
    Falls back to manual price import if live scraping is unavailable.
    """

    def __init__(self, session=None, username=None, password=None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.source_name = "Campbells Wholesale"
        self.username = username
        self.password = password
        self._logged_in = False

    def login(self) -> bool:
        """Attempt to authenticate with Campbells wholesale site."""
        if not self.username or not self.password:
            logger.info("[Campbells] No credentials provided, using guest mode")
            return False

        login_url = f"{CAMPBELLS_BASE_URL}/customer/account/loginPost/"
        payload = {
            "login[username]": self.username,
            "login[password]": self.password,
        }
        try:
            r = self.session.post(login_url, data=payload, timeout=15)
            r.raise_for_status()
            self._logged_in = "My Account" in r.text or "logout" in r.text.lower()
            if self._logged_in:
                logger.info("[Campbells] Login successful")
            else:
                logger.warning("[Campbells] Login may have failed - check credentials")
            return self._logged_in
        except Exception as e:
            logger.error(f"[Campbells] Login failed: {e}")
            return False

    def search_product(self, query: str) -> List[Dict]:
        """
        Search Campbells for a product and return price data.
        Works in both guest and authenticated modes.
        """
        try:
            params = {"q": query}
            r = self.session.get(CAMPBELLS_SEARCH_URL, params=params, timeout=15)
            r.raise_for_status()
            return self._parse_html_results(r.text, query)
        except Exception as e:
            logger.error(f"[Campbells] Search failed for '{query}': {e}")
            return []

    def _parse_html_results(self, html: str, query: str) -> List[Dict]:
        """
        Parse product listings from Campbells HTML search results.
        Uses simple string parsing to avoid BeautifulSoup dependency
        (add bs4 to requirements for a more robust implementation).
        """
        import re
        products = []

        # Pattern to find product blocks with price
        # Campbells uses standard Magento-style product listing HTML
        price_pattern = re.compile(
            r'data-product-price="([0-9.]+)"[^>]*>.*?<span[^>]*class="[^"]*product-name[^"]*"[^>]*>([^<]+)<',
            re.DOTALL
        )

        for m in price_pattern.finditer(html):
            try:
                price = float(m.group(1))
                name = m.group(2).strip()
                if any(kw.lower() in name.lower() for kw in query.split()):
                    products.append({
                        "source": self.source_name,
                        "name": name,
                        "price": price,
                        "was_price": None,
                        "is_on_sale": False,
                        "discount_pct": 0.0,
                        "url": f"{CAMPBELLS_BASE_URL}/catalogsearch/result/?q={query}",
                        "pack_description": "",
                    })
            except (IndexError, ValueError):
                continue

        return products

    def check_catalogue_items(self, catalogue: List[Dict]) -> List[Dict]:
        """
        Check catalogue items against Campbells pricing.
        Returns alerts where current price beats target buy price.
        """
        if not self._logged_in and self.username:
            self.login()

        alerts = []
        for item in catalogue:
            best_match = None
            best_saving = 0.0

            for keyword in item.get("keywords", [item["name"]]):
                for result in self.search_product(keyword):
                    target = item.get("target_buy_price", float("inf"))
                    saving = target - result["price"]
                    if saving > best_saving:
                        best_match = result
                        best_saving = saving

            if best_match and best_saving > 0:
                alerts.append({
                    "catalogue_id": item["id"],
                    "catalogue_name": item["name"],
                    "target_buy_price": item.get("target_buy_price"),
                    "found_price": best_match["price"],
                    "was_price": best_match["was_price"],
                    "discount_pct": best_match["discount_pct"],
                    "beats_target": True,
                    "saving_per_unit": round(best_saving, 2),
                    "source": self.source_name,
                    "url": best_match["url"],
                    "product_name": best_match["name"],
                    "pack_description": best_match["pack_description"],
                })

        return alerts


class ManualPriceScraper:
    """
    Import prices from a manual CSV file (distributor price lists, emails, etc.)
    Use this when a distributor doesn't have a scrapeable website.

    CSV format:
        supplier,product_name,price,was_price,url,notes
        MetcashCandC,Coke 24pk 375ml,28.00,32.00,https://...,Expires Fri
    """

    def __init__(self, csv_path: str = "manual_prices.csv"):
        self.csv_path = csv_path
        self.source_name = "Manual Import"

    def load_prices(self) -> List[Dict]:
        """Load prices from the CSV file."""
        prices = []
        try:
            with open(self.csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        price = float(row.get("price", 0))
                        was_price_str = row.get("was_price", "")
                        was_price = float(was_price_str) if was_price_str else None
                        is_on_sale = was_price is not None and was_price > price
                        discount_pct = 0.0
                        if is_on_sale:
                            discount_pct = round((was_price - price) / was_price * 100, 1)
                        prices.append({
                            "source": row.get("supplier", "Manual"),
                            "name": row.get("product_name", ""),
                            "price": price,
                            "was_price": was_price,
                            "is_on_sale": is_on_sale,
                            "discount_pct": discount_pct,
                            "url": row.get("url", ""),
                            "pack_description": row.get("notes", ""),
                            "loaded_at": datetime.now().isoformat(),
                        })
                    except (ValueError, KeyError) as e:
                        logger.warning(f"[ManualPrice] Skipping row: {e}")
        except FileNotFoundError:
            logger.info(f"[ManualPrice] No manual price file found at {self.csv_path}")
        return prices

    def check_catalogue_items(self, catalogue: List[Dict]) -> List[Dict]:
        prices = self.load_prices()
        alerts = []

        for item in catalogue:
            keywords = item.get("keywords", [item["name"]])
            best_match = None
            best_saving = 0.0

            for price_entry in prices:
                name = price_entry["name"].lower()
                if any(kw.lower() in name for kw in keywords):
                    target = item.get("target_buy_price", float("inf"))
                    saving = target - price_entry["price"]
                    if saving > best_saving:
                        best_match = price_entry
                        best_saving = saving

            if best_match and best_saving > 0:
                alerts.append({
                    "catalogue_id": item["id"],
                    "catalogue_name": item["name"],
                    "target_buy_price": item.get("target_buy_price"),
                    "found_price": best_match["price"],
                    "was_price": best_match["was_price"],
                    "discount_pct": best_match["discount_pct"],
                    "beats_target": True,
                    "saving_per_unit": round(best_saving, 2),
                    "source": best_match["source"],
                    "url": best_match["url"],
                    "product_name": best_match["name"],
                    "pack_description": best_match["pack_description"],
                })

        return alerts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json as _json
    with open("../catalogue.json") as f:
        catalogue = _json.load(f)["catalogue"]

    # Test manual price scraper
    manual = ManualPriceScraper("../manual_prices.csv")
    alerts = manual.check_catalogue_items(catalogue[:5])
    print("Manual Price Alerts:", _json.dumps(alerts, indent=2))
