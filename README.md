# Vending-Alerts

**Automated sale alert system for vending machine operators.**

Monitors Woolworths, Coles, Campbells Wholesale, and manual distributor price lists for sales on your vending machine product catalogue. Sends alerts via **email**, **SMS**, and/or **push notification** (ntfy.sh / Pushover) when products you stock go on sale, so you can buy at the right time and reduce your cost of goods.

---

## What It Does

- Scrapes Woolworths and Coles product search APIs for current sale prices
- Supports Campbells Wholesale (with optional login for wholesale pricing)
- Manual CSV import for distributors without a scrapeable website
- Compares found prices against your **target buy price** per product
- Deduplicates results (best price wins across all sources)
- Sends a formatted alert email, SMS summary, and/or phone push notification
- Logs all alert history to `alerts_history.json`
- Runs on a schedule (APScheduler or cron)

---

## Product Catalogue

The default catalogue (`catalogue.json`) includes 20 products across all key vending categories:

| Category | Products |
|---|---|
| Drinks | Coca-Cola, Pepsi, Schweppes, Sprite, Powerade |
| Water | Mount Franklin 600ml |
| Energy Drinks | Red Bull, Monster, V Energy |
| Snacks | Smiths Chips, Twisties |
| Chocolate | Kit Kat, Snickers, Mars Bar, Twix |
| Noodles | Indomie Mi Goreng, Maggi 2 Minute |
| Jerky | Jack Links, Bepps Beef Jerky |

Each product has:
- **keywords** — search terms used to find the product across retailers
- **target_buy_price** — your maximum acceptable unit buy price (alerts flag if sale price beats this)
- **vending_sell_price** — your sell price (for margin reference)
- **pack_sizes** — common pack sizes at retail/wholesale

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/HarryJulian1996/Vending-Alerts.git
cd Vending-Alerts
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

Copy the example config and fill in your notification settings:

```bash
cp config.example.json config.json
```

Edit `config.json` with your email, SMS (Twilio), or push notification credentials.

> **Note:** `config.json` is in `.gitignore` so your credentials are never committed.

### 3. Run manually

```bash
# Check all sources, send notifications
python main.py

# Check all sources, print results without sending notifications
python main.py --dry-run

# Only check Woolworths
python main.py --source woolworths

# Only alert if discount is 15% or more
python main.py --min-discount 15

# Only alert on products that beat your target buy price
python main.py --beats-target-only
```

### 4. Run on a schedule

**Option A: Built-in scheduler (recommended)**
```bash
python scheduler.py
```
Runs at 7am, 2pm Mon-Fri and 9am weekends (AEST) by default. Configurable in `config.json`.

**Option B: Cron job**
```
# Add to crontab (crontab -e)
# Run at 7am and 6pm every day
0 7,18 * * * cd /path/to/Vending-Alerts && /path/to/venv/bin/python main.py >> logs/cron.log 2>&1
```

---

## Notification Channels

### Email
Full HTML email with a formatted table of all sale alerts. Configure in `config.json`:
- Works with Gmail, Outlook, or any SMTP server
- For Gmail: use an [App Password](https://support.google.com/accounts/answer/185833), not your account password

### Push Notification (ntfy.sh — free, recommended)
Free, no account required. Install the [ntfy app](https://ntfy.sh) on your phone, subscribe to your topic:
1. Set `push.provider` to `"ntfy"` in config.json
2. Set `push.ntfy_topic` to a unique string (e.g. `"my-vending-alerts-abc123"`)
3. In the ntfy app, subscribe to the same topic

### SMS (Twilio)
Sends a brief SMS summary with top deals. Requires a [Twilio account](https://www.twilio.com) (free trial available).

---

## Distributor / Manual Prices

For distributors without a scrapeable website (e.g. Campbells Cash & Carry in-store, PFD, Metcash, Costco):

1. Copy `manual_prices.example.csv` to `manual_prices.csv`
2. Fill in prices as you receive them (from emails, catalogues, in-store visits)
3. The system will check this file on every run

CSV format:
```csv
supplier,product_name,price,was_price,url,notes
Campbells Wholesale,Coca-Cola 375ml 30 Pack,28.50,36.00,https://...,Sale ends Friday
```

---

## Adding / Editing Products

Edit `catalogue.json` to add your own products:

```json
{
  "id": "my-product-id",
  "name": "Product Display Name",
  "category": "drinks",
  "brand": "Brand Name",
  "keywords": ["search term 1", "search term 2"],
  "target_buy_price": 1.50,
  "vending_sell_price": 4.00,
  "unit": "can",
  "pack_sizes": [24, 30]
}
```

**Keywords** are the most important field — these are the search terms used on each retailer.
Use specific terms that match product names on Woolworths/Coles (e.g. `"coca cola 375 can"` not just `"coke"`).

---

## File Structure

```
Vending-Alerts/
├── main.py                      # Main runner (orchestrates scrapers + notifications)
├── scheduler.py                 # Long-running scheduled process
├── notifier.py                  # Email / SMS / Push notification sender
├── catalogue.json               # Your vending machine product catalogue
├── config.json                  # YOUR credentials (not in git)
├── config.example.json          # Template — copy to config.json
├── manual_prices.csv            # Manual distributor prices (not in git)
├── manual_prices.example.csv    # Template — copy to manual_prices.csv
├── alerts_history.json          # Auto-generated alert log
├── requirements.txt             # Python dependencies
├── .gitignore                   # Keeps credentials out of git
└── scrapers/
    ├── woolworths.py            # Woolworths product search + specials
    ├── coles.py                 # Coles product search + specials
    └── campbells.py             # Campbells Wholesale + manual CSV importer
```

---

## Scraper Notes

| Source | Method | Auth Required | Notes |
|---|---|---|---|
| Woolworths | Public JSON API | No | Uses product search + specials endpoints |
| Coles | Next.js data API | No | Auto-fetches current build ID |
| Campbells | HTML scraping | Optional | Magento-based site; login improves pricing |
| Manual CSV | File import | No | Use for any source without a website |

**Respectful scraping:** The scrapers include timeout handling and error recovery. Do not run more frequently than every 2 hours to be respectful to retailer servers.

---

## Sample Alert Output

```
VENDING MACHINE SALE ALERTS - 24 Jun 2026 07:02
==================================================

[Woolworths] Coca-Cola 375ml Can
  Found: Coca-Cola Soft Drink Cans 375mL 30 Pack
  Price: $28.50 (was $36.00) - 20.8% OFF BEATS TARGET
  Save $0.30/unit
  Link:  https://www.woolworths.com.au/shop/productdetails/12345

[Coles] Red Bull Energy Drink 250ml
  Found: Red Bull Energy Drink 250mL 24 Pack
  Price: $44.00 (was $55.00) - 20.0% OFF BEATS TARGET
  Save $0.17/unit
  Link:  https://www.coles.com.au/product/red-bull-250ml-24pk

Total alerts: 2
```

---

## Roadmap

- [ ] Aldi scraper (limited but useful for bulk buys)
- [ ] Price history tracking and trend charts
- [ ] Minimum stock threshold alerts (integrate with inventory system)
- [ ] Telegram bot notification channel
- [ ] Web dashboard (Flask) to view alert history
- [ ] Automatic optimal buy quantity calculator (based on storage capacity)

---

*Built to help vending machine operators buy smarter and reduce cost of goods.*
