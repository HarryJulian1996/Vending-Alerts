"""
Vending Alerts Notifier
Sends sale alerts via Email, SMS (Twilio), and/or Push (ntfy.sh / Pushover).
Configure channels in config.json or environment variables.
"""

import smtplib
import json
import logging
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict
import requests

logger = logging.getLogger(__name__)


def load_config(path: str = "config.json") -> Dict:
    """Load notification config from file or environment variables."""
    config = {}
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.warning(f"Config file '{path}' not found. Using environment variables.")
    return {
        "email": {
            "enabled": config.get("email", {}).get("enabled", bool(os.getenv("EMAIL_ENABLED"))),
            "smtp_host": config.get("email", {}).get("smtp_host", os.getenv("SMTP_HOST", "smtp.gmail.com")),
            "smtp_port": int(config.get("email", {}).get("smtp_port", os.getenv("SMTP_PORT", 587))),
            "username": config.get("email", {}).get("username", os.getenv("EMAIL_USERNAME", "")),
            "password": config.get("email", {}).get("password", os.getenv("EMAIL_PASSWORD", "")),
            "from_address": config.get("email", {}).get("from_address", os.getenv("EMAIL_FROM", "")),
            "to_addresses": config.get("email", {}).get("to_addresses", os.getenv("EMAIL_TO", "").split(",")),
        },
        "sms": {
            "enabled": config.get("sms", {}).get("enabled", bool(os.getenv("SMS_ENABLED"))),
            "account_sid": config.get("sms", {}).get("account_sid", os.getenv("TWILIO_ACCOUNT_SID", "")),
            "auth_token": config.get("sms", {}).get("auth_token", os.getenv("TWILIO_AUTH_TOKEN", "")),
            "from_number": config.get("sms", {}).get("from_number", os.getenv("TWILIO_FROM", "")),
            "to_numbers": config.get("sms", {}).get("to_numbers", os.getenv("SMS_TO", "").split(",")),
        },
        "push": {
            "enabled": config.get("push", {}).get("enabled", bool(os.getenv("PUSH_ENABLED"))),
            "provider": config.get("push", {}).get("provider", os.getenv("PUSH_PROVIDER", "ntfy")),
            "ntfy_topic": config.get("push", {}).get("ntfy_topic", os.getenv("NTFY_TOPIC", "vending-alerts")),
            "ntfy_server": config.get("push", {}).get("ntfy_server", os.getenv("NTFY_SERVER", "https://ntfy.sh")),
            "pushover_user_key": config.get("push", {}).get("pushover_user_key", os.getenv("PUSHOVER_USER_KEY", "")),
            "pushover_api_token": config.get("push", {}).get("pushover_api_token", os.getenv("PUSHOVER_API_TOKEN", "")),
        },
    }


def format_alerts_text(alerts: List[Dict]) -> str:
    """Format alerts as plain text."""
    if not alerts:
        return "No sale alerts today."
    now = datetime.now().strftime("%d %b %Y %H:%M")
    lines = [f"VENDING MACHINE SALE ALERTS - {now}", "=" * 50, ""]
    for a in alerts:
        price_str = f"${a['found_price']:.2f}"
        was_str = f" (was ${a['was_price']:.2f})" if a.get("was_price") else ""
        discount_str = f" - {a['discount_pct']}% OFF" if a.get("discount_pct") else ""
        beats = " BEATS TARGET" if a.get("beats_target") else ""
        saving = f"  Save ${a['saving_per_unit']:.2f}/unit" if a.get("saving_per_unit") else ""
        lines.append(f"[{a['source']}] {a['catalogue_name']}")
        lines.append(f"  Found: {a.get('product_name', a['catalogue_name'])}")
        lines.append(f"  Price: {price_str}{was_str}{discount_str}{beats}")
        if saving:
            lines.append(saving)
        lines.append(f"  Link:  {a['url']}")
        lines.append("")
    lines.append(f"Total alerts: {len(alerts)}")
    return "\n".join(lines)


def format_alerts_html(alerts: List[Dict]) -> str:
    """Format alerts as HTML email."""
    if not alerts:
        return "<p>No sale alerts today.</p>"
    now = datetime.now().strftime("%d %b %Y %H:%M")
    rows = ""
    for a in alerts:
        price_str = f"${a['found_price']:.2f}"
        was_str = f"<s>${a['was_price']:.2f}</s> " if a.get("was_price") else ""
        disc = f'<span style="background:#e74c3c;color:white;padding:2px 6px;border-radius:3px">{a["discount_pct"]}% OFF</span>' if a.get("discount_pct") else ""
        beats = '<span style="background:#27ae60;color:white;padding:2px 6px;border-radius:3px">BEATS TARGET</span>' if a.get("beats_target") else ""
        saving = f'<br><small>Saves ${a["saving_per_unit"]:.2f} per unit</small>' if a.get("saving_per_unit") else ""
        rows += (
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="padding:10px"><strong>{a["source"]}</strong></td>'
            f'<td style="padding:10px">{a["catalogue_name"]}<br><small>{a.get("product_name","")}</small></td>'
            f'<td style="padding:10px">{was_str}<strong>{price_str}</strong><br>{disc} {beats}{saving}</td>'
            f'<td style="padding:10px"><a href="{a["url"]}">View Deal</a></td>'
            "</tr>"
        )
    return (
        "<!DOCTYPE html><html><body style='font-family:Arial;max-width:700px;margin:auto'>"
        f"<h2>Vending Machine Sale Alerts</h2><p>{now} - {len(alerts)} deal(s)</p>"
        "<table style='width:100%;border-collapse:collapse;border:1px solid #ddd'>"
        "<thead><tr style='background:#2c3e50;color:white'>"
        "<th style='padding:10px'>Source</th><th style='padding:10px'>Product</th>"
        "<th style='padding:10px'>Price</th><th style='padding:10px'>Link</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>"
    )


def send_email(alerts: List[Dict], config: Dict) -> bool:
    """Send alert email via SMTP."""
    cfg = config.get("email", {})
    if not cfg.get("enabled"):
        return False
    recipients = [a.strip() for a in cfg.get("to_addresses", []) if a.strip()]
    if not recipients:
        logger.warning("[Email] No recipients configured")
        return False
    count = len(alerts)
    subject = f"Vending Alert: {count} sale(s) found - {datetime.now().strftime('%d %b %Y')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_address", cfg.get("username"))
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(format_alerts_text(alerts), "plain"))
    msg.attach(MIMEText(format_alerts_html(alerts), "html"))
    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.sendmail(msg["From"], recipients, msg.as_string())
        logger.info(f"[Email] Sent to {recipients}")
        return True
    except Exception as e:
        logger.error(f"[Email] Failed: {e}")
        return False


def send_sms(alerts: List[Dict], config: Dict) -> bool:
    """Send SMS via Twilio."""
    cfg = config.get("sms", {})
    if not cfg.get("enabled") or not alerts:
        return False
    top = alerts[:3]
    summary = ", ".join(f"{a['catalogue_name']} @ ${a['found_price']:.2f}" for a in top)
    if len(alerts) > 3:
        summary += f" +{len(alerts) - 3} more"
    body = f"VENDING ALERT: {len(alerts)} deal(s)! {summary}. Check email for details."
    numbers = [n.strip() for n in cfg.get("to_numbers", []) if n.strip()]
    success = True
    for num in numbers:
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg['account_sid']}/Messages.json"
            r = requests.post(url, data={"From": cfg["from_number"], "To": num, "Body": body},
                              auth=(cfg["account_sid"], cfg["auth_token"]), timeout=10)
            r.raise_for_status()
            logger.info(f"[SMS] Sent to {num}")
        except Exception as e:
            logger.error(f"[SMS] Failed: {e}")
            success = False
    return success


def send_push(alerts: List[Dict], config: Dict) -> bool:
    """Send push notification via ntfy.sh or Pushover."""
    cfg = config.get("push", {})
    if not cfg.get("enabled") or not alerts:
        return False
    title = f"Vending Alert: {len(alerts)} deal(s) found!"
    lines = [f"- {a['catalogue_name']} @ ${a['found_price']:.2f} [{a['source']}]" for a in alerts[:5]]
    body = "\n".join(lines)
    if cfg.get("provider", "ntfy") == "ntfy":
        server = cfg.get("ntfy_server", "https://ntfy.sh")
        topic = cfg.get("ntfy_topic", "vending-alerts")
        try:
            r = requests.post(f"{server}/{topic}", data=body.encode(),
                              headers={"Title": title, "Priority": "high", "Tags": "shopping_cart"},
                              timeout=10)
            r.raise_for_status()
            logger.info(f"[Push/ntfy] Sent to {server}/{topic}")
            return True
        except Exception as e:
            logger.error(f"[Push/ntfy] Failed: {e}")
            return False
    else:
        try:
            r = requests.post("https://api.pushover.net/1/messages.json", data={
                "token": cfg["pushover_api_token"], "user": cfg["pushover_user_key"],
                "title": title, "message": body, "priority": 1,
            }, timeout=10)
            r.raise_for_status()
            logger.info("[Push/Pushover] Sent")
            return True
        except Exception as e:
            logger.error(f"[Push/Pushover] Failed: {e}")
            return False


def notify(alerts: List[Dict], config_path: str = "config.json") -> Dict:
    """Send alerts via all configured channels."""
    if not alerts:
        logger.info("[Notifier] No alerts to send")
        return {}
    config = load_config(config_path)
    results = {
        "email": send_email(alerts, config),
        "sms": send_sms(alerts, config),
        "push": send_push(alerts, config),
    }
    sent = [k for k, v in results.items() if v]
    logger.info(f"[Notifier] Sent via: {sent or ['none']}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_alerts = [{
        "catalogue_id": "coca-cola-375ml",
        "catalogue_name": "Coca-Cola 375ml Can",
        "target_buy_price": 1.20,
        "found_price": 0.99,
        "was_price": 1.50,
        "discount_pct": 34.0,
        "beats_target": True,
        "saving_per_unit": 0.21,
        "source": "Woolworths",
        "url": "https://www.woolworths.com.au/shop/productdetails/12345",
        "product_name": "Coca-Cola 375mL 30 Pack",
        "pack_description": "30 x 375mL",
    }]
    print(format_alerts_text(test_alerts))
