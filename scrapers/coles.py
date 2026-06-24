"""
Coles Sale Scraper
Fetches current sale/specials prices from Coles Australia.
Uses Coles Next.js data API to find on-sale products.
"""

import requests
import json
import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.coles.com.au/",
}


class ColesScraper:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.source_name = "Coles"
        self._build_id = None

    def _get_build_id(self):
        if self._build_id:
            return self._build_id
        try:
            r = self.session.get("https://www.coles.com.au/", timeout=10)
            r.raise_for_status()
            m = re.search(r'"buildId"\s*:\s*"([^"]+)"', r.text)
            if m:
                self._build_id = m.group(1)
                return self._build_id
        except Exception as e:
            logger.error(f"[Coles] build ID fetch failed: {e}")
        return None

    def search_product(self, query, page=1):
        build_id = self._get_build_id()
        if not build_id:
            return []
        url = f"https://www.coles.com.au/_next/data/{build_id}/en/search.json"
        try:
            r = self.session.get(url, params={"q": query, "page": page}, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"[Coles] search failed for '{query}': {e}")
            return []
        products = []
        results = data.get("pageProps", {}).get("searchResults", {}).get("results", [])
        for item in results:
            p = self._parse_product(item)
            if p:
                products.append(p)
        return products

    def fetch_specials_category(self, slug="drinks", page=1):
        build_id = self._get_build_id()
        if not build_id:
            return []
        url = f"https://www.coles.com.au/_next/data/{build_id}/en/on-special.json"
        try:
            r = self.session.get(url, params={"slug": [slug], "page": page}, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"[Coles] specials fetch failed: {e}")
            return []
        products = []
        results = data.get("pageProps", {}).get("searchResults", {}).get("results", [])
        for item in results:
            p = self._parse_product(item)
            if p and p["is_on_sale"]:
                products.append(p)
        return products

    def _parse_product(self, item):
        try:
            pricing = item.get("pricing", {})
            now_price = pricing.get("now")
            was_price = pricing.get("was")
            if now_price is None:
                return None
            is_on_sale = pricing.get("isOnSpecial", False) or (was_price and was_price > now_price)
            discount_pct = 0.0
            if was_price and was_price > now_price:
                discount_pct = round((was_price - now_price) / was_price * 100, 1)
            product_id = item.get("id", "")
            return {
                "source": self.source_name,
                "name": item.get("name", ""),
                "product_id": str(product_id),
                "price": float(now_price),
                "was_price": float(was_price) if was_price else None,
                "is_on_sale": bool(is_on_sale),
                "discount_pct": discount_pct,
                "url": f"https://www.coles.com.au/product/{item.get('slug', product_id)}",
                "pack_description": item.get("size", ""),
            }
        except Exception as e:
            logger.debug(f"[Coles] skipping product: {e}")
            return None

    def check_catalogue_items(self, catalogue):
        alerts = []
        for item in catalogue:
            best_match = None
            best_discount = 0.0
            for keyword in item.get("keywords", [item["name"]]):
                for result in self.search_product(keyword):
                    if result["is_on_sale"] and result["discount_pct"] > best_discount:
                        best_match = result
                        best_discount = result["discount_pct"]
            if best_match:
                alerts.append({
                    "catalogue_id": item["id"],
                    "catalogue_name": item["name"],
                    "target_buy_price": item.get("target_buy_price"),
                    "found_price": best_match["price"],
                    "was_price": best_match["was_price"],
                    "discount_pct": best_discount,
                    "beats_target": best_match["price"] <= item.get("target_buy_price", float("inf")),
                    "source": self.source_name,
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
    scraper = ColesScraper()
    alerts = scraper.check_catalogue_items(catalogue[:3])
    print(_json.dumps(alerts, indent=2))
