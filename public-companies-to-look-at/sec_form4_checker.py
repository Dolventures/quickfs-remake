#!/usr/bin/env python3
"""
SEC Form 4 Checker — finds insider open-market purchases (code P)
for public companies with market cap < $2B, then emails a summary.

Usage:
  python3 sec_form4_checker.py                        # today
  python3 sec_form4_checker.py 2025-03-10             # single date
  python3 sec_form4_checker.py 2025-03-01 2025-03-14  # date range → one email
"""

import os
import sys
import time
import smtplib
import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

MARKET_CAP_LIMIT = 2_000_000_000  # $2B
EDGAR_HEADERS = {"User-Agent": os.getenv("EDGAR_USER_AGENT", "Anonymous contact@example.com")}  # required by SEC
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # app password if using Gmail
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# ── SEC EDGAR helpers ─────────────────────────────────────────────────────────


def fetch_form4_filings(target_date: date) -> list[dict]:
    """
    Return all Form 4 filings for target_date using edgartools index downloads.
    Avoids efts.sec.gov search-index which blocks cloud hosting IPs.
    """
    from edgar import get_filings, set_identity
    
    set_identity(os.getenv("EDGAR_USER_AGENT", "TickerFS contact@historysbestsellers.com"))
    date_str = target_date.strftime("%Y-%m-%d")
    
    try:
        filings = get_filings(filing_date=date_str, form="4")
        if not filings:
            log.info("No Form 4 filings found for %s", date_str)
            return []
            
        results = []
        for filing in filings:
            results.append({
                "adsh": filing.accession_no,
                "cik": str(filing.cik),
                "filing_url": filing.homepage_url,
                "filing_obj": filing
            })
            
        log.info("Found %d Form 4 filings for %s", len(results), date_str)
        return results
    except Exception as e:
        log.error("Failed to fetch Form 4 filings via edgartools: %s", e)
        return []


def parse_purchases(xml_text: str) -> list[dict]:
    """
    Parse Form 4 XML and return transactions with code P (open-market purchase).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Strip namespace if present (some filers include xmlns="...")
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]

    def txt(node, path, default=""):
        el = node.find(path)
        return el.text.strip() if el is not None and el.text else default

    ticker      = txt(root, "issuer/issuerTradingSymbol")
    issuer_name = txt(root, "issuer/issuerName")
    insider_name  = txt(root, "reportingOwner/reportingOwnerId/rptOwnerName")
    insider_title = txt(root, "reportingOwner/reportingOwnerRelationship/officerTitle")

    purchases = []
    for txn in root.iter("nonDerivativeTransaction"):
        code = txt(txn, "transactionCoding/transactionCode")
        if code != "P":
            continue

        shares_str = txt(txn, "transactionAmounts/transactionShares/value")
        price_str  = txt(txn, "transactionAmounts/transactionPricePerShare/value")
        txn_date   = txt(txn, "transactionDate/value")

        try:
            shares = float(shares_str.replace(",", "")) if shares_str else 0.0
            price  = float(price_str.replace(",", ""))  if price_str  else 0.0
        except ValueError:
            shares, price = 0.0, 0.0

        total = shares * price
        if total <= 0:
            continue

        purchases.append({
            "issuer_name":    issuer_name,
            "ticker":         ticker,
            "insider_name":   insider_name,
            "insider_title":  insider_title,
            "transaction_date": txn_date,
            "shares":           shares,
            "price_per_share":  price,
            "total_value":      total,
        })

    return purchases


# ── Market cap filter ─────────────────────────────────────────────────────────


def get_market_cap(ticker: str) -> float | None:
    """Return market cap in dollars, or None if unavailable."""
    if not ticker:
        return None
    try:
        info = yf.Ticker(ticker).info
        cap = info.get("marketCap")
        return float(cap) if cap else None
    except Exception:
        return None


# ── Email ─────────────────────────────────────────────────────────────────────


def send_email(subject: str, html_body: str, text_body: str) -> None:
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD]):
        log.error("Email variables (EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD) not configured. Skipping email send.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

    log.info("Email sent to %s", EMAIL_TO)


def build_email(results: list[dict], start: date, end: date) -> tuple[str, str, str]:
    if start == end:
        date_label = start.strftime("%B %d, %Y")
        subject = f"SEC Form 4 Insider Purchases — {date_label}"
    else:
        date_label = f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
        subject = f"SEC Form 4 Insider Purchases — {date_label}"

    if not results:
        text = f"No insider open-market purchases (code P) found for companies under $2B market cap ({date_label})."
        html = f"<p>{text}</p>"
        return subject, html, text

    link_url = f"https://tickerfs.com/?tab=insider-buys&date={start.isoformat()}"

    # Simple email prompting the user to view results on their dashboard
    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;font-size:14px;color:#0f172a;line-height:1.5;">
  <h2>SEC Form 4 Insider Purchases</h2>
  <p>We detected <b>{len(results)}</b> qualifying insider open-market purchases (code P) on <b>{date_label}</b>.</p>
  <p>To preserve privacy and keep code history clean, you can view the complete list and run full financial statement analysis directly on your site:</p>
  <p style="margin: 20px 0;">
    <a href="{link_url}" style="display:inline-block;padding:10px 20px;background-color:#2563eb;color:#ffffff;text-decoration:none;border-radius:4px;font-weight:bold;font-size:13px;">View Insider Purchases on TickerFS</a>
  </p>
  <p style="color:#64748b;font-size:12px;margin-top:40px;">
    Data sourced from SEC EDGAR.
  </p>
</body>
</html>"""

    text = (
        f"SEC Form 4 Insider Purchases — {date_label}\n\n"
        f"We detected {len(results)} qualifying insider purchases on this date.\n\n"
        f"View the complete list and run financial analysis directly on TickerFS:\n"
        f"{link_url}\n\n"
        f"Data sourced from SEC EDGAR."
    )

    return subject, html, text


# ── Core logic ────────────────────────────────────────────────────────────────


def process_date(target_date: date, seen_tickers: dict, strict: bool = True) -> list[dict]:
    """Fetch and filter Form 4 purchases for a single date. Returns qualifying rows."""
    filings = fetch_form4_filings(target_date)
    qualifying = []

    for i, filing in enumerate(filings):
        log.info("[%s %d/%d] %s", target_date, i + 1, len(filings), filing["adsh"])

        try:
            xml_text = filing["filing_obj"].xml()
        except Exception as e:
            log.warning("Could not download XML for filing %s: %s", filing["adsh"], e)
            xml_text = None

        if not xml_text:
            continue

        purchases = parse_purchases(xml_text)
        if not purchases:
            continue

        ticker = purchases[0]["ticker"]
        if ticker not in seen_tickers:
            seen_tickers[ticker] = get_market_cap(ticker)
        cap = seen_tickers[ticker]

        if strict and cap is not None and cap >= MARKET_CAP_LIMIT:
            continue

        for p in purchases:
            min_val = 100_000 if strict else 5_000
            if p["total_value"] < min_val:
                continue
            p["market_cap"] = cap
            p["filing_url"] = filing["filing_url"]
            qualifying.append(p)

        time.sleep(0.15)  # stay within EDGAR's ~10 req/sec limit

    return qualifying


def run(start_date: date, end_date: date, send: bool = True) -> list[dict]:
    """Run the checker for a date range. Sends one combined email."""
    all_results = []
    seen_tickers: dict[str, float | None] = {}

    current = start_date
    while current <= end_date:
        log.info("=== Processing %s ===", current)
        rows = process_date(current, seen_tickers, strict=send)
        all_results.extend(rows)
        log.info("  → %d qualifying purchases so far", len(all_results))
        current += timedelta(days=1)

    log.info("Total qualifying purchases: %d", len(all_results))
    subject, html, text = build_email(all_results, start_date, end_date)
    print(text)

    if send:
        if all_results:
            send_email(subject, html, text)
        else:
            log.info("No qualifying purchases found; skipping email.")

    return all_results


# ── Entry point ───────────────────────────────────────────────────────────────

STAMP_FILE = os.path.join(os.path.dirname(__file__), ".last_run")


def last_run_date() -> date | None:
    try:
        return date.fromisoformat(open(STAMP_FILE).read().strip())
    except FileNotFoundError:
        return None


def already_ran_today() -> bool:
    last = last_run_date()
    return last == date.today()


def mark_ran_today() -> None:
    open(STAMP_FILE, "w").write(date.today().isoformat())


if __name__ == "__main__":
    args = sys.argv[1:]

    if len(args) == 0:
        if already_ran_today():
            log.info("Already ran today, exiting.")
            sys.exit(0)
        yesterday = date.today() - timedelta(days=1)
        last = last_run_date()
        if last is not None and last < yesterday:
            start = last + timedelta(days=1)
            log.info(f"Catching up from {start} to {yesterday}")
        else:
            start = yesterday
        run(start, yesterday)
        mark_ran_today()
    elif len(args) == 1:
        d = datetime.strptime(args[0], "%Y-%m-%d").date()
        run(d, d)
    elif len(args) == 2:
        d1 = datetime.strptime(args[0], "%Y-%m-%d").date()
        d2 = datetime.strptime(args[1], "%Y-%m-%d").date()
        run(d1, d2)
    else:
        print("Usage: python3 sec_form4_checker.py [START_DATE [END_DATE]]")
        sys.exit(1)
