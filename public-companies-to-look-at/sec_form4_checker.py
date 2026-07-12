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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
import yfinance as yf
from dotenv import load_dotenv

# Load .env from script directory or parent (root) directory
script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(script_dir, ".env")
if not os.path.exists(dotenv_path):
    dotenv_path = os.path.join(os.path.dirname(script_dir), ".env")
load_dotenv(dotenv_path=dotenv_path)

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
    Return all Form 4 filings for target_date by parsing the daily index file directly.
    Bypasses efts.sec.gov and edgartools index downloads which trigger 403 Forbidden in production.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    date_nodash = target_date.strftime("%Y%m%d")
    year = target_date.year
    qtr = (target_date.month - 1) // 3 + 1
    
    url = f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/form.{date_nodash}.idx"
    log.info("Fetching daily form index from %s", url)
    
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
        if resp.status_code == 403:
            log.warning("Direct fetch failed (403 Forbidden). Retrying through proxy...")
            proxy_url = f"https://api.allorigins.win/raw?url={url}"
            resp = requests.get(proxy_url, headers=EDGAR_HEADERS, timeout=30)
            
        if resp.status_code == 404:
            log.info("Daily form index not found (404) for %s", date_str)
            return []
        resp.raise_for_status()
        
        lines = resp.text.splitlines()
        filings = []
        header_ended = False
        for line in lines:
            if not header_ended:
                if line.startswith("---"):
                    header_ended = True
                continue
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            if parts[0] == "4":
                file_name = parts[-1]
                cik = parts[-3]
                accession = file_name.split("/")[-1].replace(".txt", "")
                company_name = line[12:74].strip()
                
                filings.append({
                    "adsh": accession,
                    "cik": cik,
                    "company_name": company_name,
                    "raw_url": "https://www.sec.gov/Archives/" + file_name,
                    "filing_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}-index.html"
                })
        log.info("Found %d Form 4 filings for %s", len(filings), date_str)
        return filings
    except Exception as e:
        log.error("Failed to parse daily form index for %s: %s", date_str, e)
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


class RateLimiter:
    def __init__(self, requests_per_second=9):
        self.delay = 1.0 / requests_per_second
        self.lock = threading.Lock()
        self.last_request_time = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_request_time = time.time()


seen_tickers_lock = threading.Lock()


def process_filing(filing: dict, target_date: date, idx: int, total: int, session: requests.Session, limiter: RateLimiter, seen_tickers: dict, strict: bool) -> list[dict]:
    """Worker function to process a single filing."""
    log.info("[%s %d/%d] %s", target_date, idx + 1, total, filing["adsh"])
    
    limiter.wait()
    try:
        txt_resp = session.get(filing["raw_url"], headers=EDGAR_HEADERS, timeout=10)
        if txt_resp.status_code == 403:
            log.debug("Direct download of raw text failed (403). Retrying via proxy...")
            proxy_url = f"https://api.allorigins.win/raw?url={filing['raw_url']}"
            limiter.wait()
            txt_resp = session.get(proxy_url, headers=EDGAR_HEADERS, timeout=20)
            
        txt_resp.raise_for_status()
        txt_content = txt_resp.text
        
        if "<ownershipDocument>" in txt_content:
            xml_text = "<ownershipDocument>" + txt_content.split("<ownershipDocument>")[1].split("</ownershipDocument>")[0] + "</ownershipDocument>"
        else:
            xml_text = None
    except Exception as e:
        log.warning("Could not download raw text filing for %s: %s", filing["adsh"], e)
        xml_text = None

    if not xml_text:
        return []

    purchases = parse_purchases(xml_text)
    if not purchases:
        return []

    # OPTIMIZATION: Filter purchases by value before making slow get_market_cap (yfinance) requests
    min_val = 100_000 if strict else 5_000
    valid_purchases = [p for p in purchases if p["total_value"] >= min_val]
    if not valid_purchases:
        return []

    ticker = valid_purchases[0]["ticker"]
    
    with seen_tickers_lock:
        in_cache = ticker in seen_tickers
        if in_cache:
            cap = seen_tickers[ticker]

    if not in_cache:
        cap = get_market_cap(ticker)
        with seen_tickers_lock:
            seen_tickers[ticker] = cap

    if strict and cap is not None and cap >= MARKET_CAP_LIMIT:
        return []

    qualifying = []
    for p in valid_purchases:
        p["market_cap"] = cap
        p["filing_url"] = filing["filing_url"]
        qualifying.append(p)

    return qualifying


def process_date(target_date: date, seen_tickers: dict, strict: bool = True) -> list[dict]:
    """Fetch and filter Form 4 purchases for a single date. Returns qualifying rows."""
    filings = fetch_form4_filings(target_date)
    if not filings:
        return []

    qualifying = []
    limiter = RateLimiter(requests_per_second=9)

    with requests.Session() as session:
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(
                    process_filing,
                    filing,
                    target_date,
                    idx,
                    len(filings),
                    session,
                    limiter,
                    seen_tickers,
                    strict
                )
                for idx, filing in enumerate(filings)
            ]

            for future in as_completed(futures):
                try:
                    result = future.result()
                    qualifying.extend(result)
                except Exception as e:
                    log.error("Filing processing thread raised an exception: %s", e)

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
