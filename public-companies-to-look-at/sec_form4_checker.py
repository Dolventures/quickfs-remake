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
EDGAR_HEADERS = {"User-Agent": os.environ["EDGAR_USER_AGENT"]}  # required by SEC
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]  # app password if using Gmail
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_BASE_URL = "https://www.sec.gov"

# ── SEC EDGAR helpers ─────────────────────────────────────────────────────────


def fetch_form4_filings(target_date: date) -> list[dict]:
    """
    Return all Form 4 filings for target_date.

    EDGAR EFTS _id format: "{adsh}:{xml_filename}"
    ciks[-1] is always the issuer (company) CIK for Form 4.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    params = {
        "q": "",
        "forms": "4",
        "dateRange": "custom",
        "startdt": date_str,
        "enddt": date_str,
        "from": 0,
        "size": 100,
    }

    filings = []
    while True:
        resp = requests.get(EDGAR_SEARCH_URL, params=params, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break

        for hit in hits:
            src = hit.get("_source", {})
            # _id = "{adsh}:{xml_filename}", e.g. "0000921895-26-000687:form408106003_03132026.xml"
            hit_id = hit["_id"]
            if ":" in hit_id:
                adsh, xml_filename = hit_id.rsplit(":", 1)
            else:
                adsh = src.get("adsh", hit_id)
                xml_filename = None

            # issuer CIK is always last in the ciks list for Form 4
            ciks = src.get("ciks", [])
            issuer_cik = ciks[-1].lstrip("0") if ciks else None

            if not issuer_cik or not xml_filename:
                continue

            acc_nodash = adsh.replace("-", "")
            xsl = src.get("xsl", "")
            base = f"{EDGAR_BASE_URL}/Archives/edgar/data/{issuer_cik}/{acc_nodash}"
            raw_url = f"{base}/{xml_filename}"
            viewer_url = f"{base}/{xsl}/{xml_filename}" if xsl else raw_url

            # company name is the last display_name entry
            display_names = src.get("display_names", [])
            company_name = display_names[-1].split("(CIK")[0].strip() if display_names else ""

            filings.append({
                "adsh": adsh,
                "xml_url": raw_url,
                "filing_url": viewer_url,
                "company_name": company_name,
            })

        total = data.get("hits", {}).get("total", {}).get("value", 0)
        params["from"] += len(hits)
        if params["from"] >= total:
            break

        time.sleep(0.1)  # be polite to EDGAR

    log.info("Found %d Form 4 filings for %s", len(filings), date_str)
    return filings


def fetch_form4_xml(xml_url: str) -> str | None:
    """Download Form 4 XML directly by URL."""
    try:
        resp = requests.get(xml_url, headers=EDGAR_HEADERS, timeout=15)
        if resp.status_code != 200:
            log.debug("XML not found: %s (HTTP %s)", xml_url, resp.status_code)
            return None
        return resp.text
    except Exception as exc:
        log.debug("Error fetching XML %s: %s", xml_url, exc)
        return None


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

    # Group by ticker
    grouped: dict[str, dict] = {}
    for r in results:
        t = r["ticker"]
        if t not in grouped:
            grouped[t] = {
                "ticker":       t,
                "issuer_name":  r["issuer_name"],
                "market_cap":   r.get("market_cap"),
                "total_shares": 0.0,
                "total_value":  0.0,
                "insiders":     [],
                "filing_urls":  [],
            }
        g = grouped[t]
        g["total_shares"] += r["shares"]
        g["total_value"]  += r["total_value"]
        insider_label = f"{r['insider_name']} ({r['insider_title']})"
        if insider_label not in g["insiders"]:
            g["insiders"].append(insider_label)
        url = r.get("filing_url", "")
        if url and url not in g["filing_urls"]:
            g["filing_urls"].append(url)

    rows = sorted(grouped.values(), key=lambda x: x["total_value"], reverse=True)

    rows_html = ""
    rows_text = []
    for idx, g in enumerate(rows, 1):
        cap_str = f"${g['market_cap'] / 1e6:.0f}M" if g.get("market_cap") else "N/A"

        # Ticker cell: link each filing separately if multiple
        urls = g["filing_urls"]
        if len(urls) == 0:
            ticker_cell = f'<b>{g["ticker"]}</b>'
        elif len(urls) == 1:
            ticker_cell = f'<a href="{urls[0]}"><b>{g["ticker"]}</b></a>'
        else:
            links = " ".join(
                f'<a href="{u}">[{i+1}]</a>' for i, u in enumerate(urls)
            )
            ticker_cell = f'<b>{g["ticker"]}</b> {links}'

        insiders_cell = "<br>".join(g["insiders"])
        rows_html += f"""
        <tr>
          <td style="text-align:center">{idx}</td>
          <td>{g['issuer_name']}</td>
          <td>{ticker_cell}</td>
          <td>{cap_str}</td>
          <td>{insiders_cell}</td>
          <td style="text-align:right">{g['total_shares']:,.0f}</td>
          <td style="text-align:right"><b>${g['total_value']:,.0f}</b></td>
        </tr>"""

        filing_links = "  ".join(urls)
        rows_text.append(
            f"  {idx:>3}. {g['ticker']:8s} {g['issuer_name'][:35]:35s} ${g['total_value']:>12,.0f}"
            + (f"\n       {filing_links}" if filing_links else "")
        )

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;font-size:14px">
<h2>SEC Form 4 Insider Purchases — {date_label}</h2>
<p>Companies with market cap &lt; $2B | Transaction code <b>P</b> (open-market buy) | {len(rows)} company/companies</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
<thead style="background:#f0f0f0">
  <tr>
    <th>#</th><th>Company</th><th>Ticker</th><th>Mkt Cap</th>
    <th>Insider(s)</th><th>Total Shares</th><th>Total Value</th>
  </tr>
</thead>
<tbody>{rows_html}</tbody>
</table>
<p style="color:gray;font-size:12px">
  Data sourced from SEC EDGAR. Market cap from Yahoo Finance.
  This is not investment advice.
</p>
</body>
</html>"""

    text = (
        f"SEC Form 4 Insider Purchases — {date_label}\n"
        f"Companies <$2B market cap | Code P (open-market buy) | {len(rows)} company/companies\n\n"
        f"{'Ticker':8s} {'Company':35s} {'Total Bought':>12s}\n"
        + "-" * 60 + "\n"
        + "\n".join(rows_text)
    )

    return subject, html, text


# ── Core logic ────────────────────────────────────────────────────────────────


def process_date(target_date: date, seen_tickers: dict, strict: bool = True) -> list[dict]:
    """Fetch and filter Form 4 purchases for a single date. Returns qualifying rows."""
    filings = fetch_form4_filings(target_date)
    qualifying = []

    for i, filing in enumerate(filings):
        log.info("[%s %d/%d] %s", target_date, i + 1, len(filings), filing["adsh"])

        xml_text = fetch_form4_xml(filing["xml_url"])
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
