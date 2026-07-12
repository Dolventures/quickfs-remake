import json
import os
import sys
import sqlite3
import threading
from datetime import datetime, timedelta
import pandas as pd
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Load env variables from public-companies-to-look-at/.env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-companies-to-look-at", ".env")
load_dotenv(dotenv_path=env_path)

from pull_cash_flow import fetch_all_financials, compute_summary_metrics, compute_annual_metrics, compute_valuation_context

app = Flask(__name__)


def df_to_rows(df):
    """Convert a DataFrame to JSON-safe records (NaN → null)."""
    df = df.copy()
    df["period_end"] = df["period_end"].astype(str)
    return json.loads(df.to_json(orient="records"))


def sanitize(obj):
    """Recursively replace float NaN/Inf with None for JSON safety."""
    import math
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


@app.route("/")
def index():
    return render_template("index.html", ga_id=os.getenv("GOOGLE_ANALYTICS_ID"))


@app.route("/api/version")
def version():
    import os
    import sys
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-companies-to-look-at"))
    import sec_form4_checker
    return jsonify({
        "version": "v1.2",
        "edgar_user_agent": os.getenv("EDGAR_USER_AGENT"),
        "checker_headers": sec_form4_checker.EDGAR_HEADERS
    })


@app.route("/api/test-proxy")
def test_proxy():
    import requests
    url = "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260708.idx"
    try:
        direct_resp = requests.get(url, headers={"User-Agent": "TickerFS contact@historysbestsellers.com"}, timeout=10)
        direct_status = direct_resp.status_code
    except Exception as e:
        direct_status = f"Error: {e}"
        
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={url}"
        proxy_resp = requests.get(proxy_url, headers={"User-Agent": "TickerFS contact@historysbestsellers.com"}, timeout=15)
        proxy_status = proxy_resp.status_code
        proxy_len = len(proxy_resp.text)
        proxy_final_url = proxy_resp.url
    except Exception as e:
        proxy_status = f"Error: {e}"
        proxy_len = 0
        proxy_final_url = ""
        
    return jsonify({
        "direct_status": direct_status,
        "proxy_status": proxy_status,
        "proxy_len": proxy_len,
        "proxy_final_url": proxy_final_url
    })


@app.route("/api/test-checker")
def test_checker():
    import os
    import sys
    from datetime import date
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-companies-to-look-at"))
    import sec_form4_checker
    try:
        filings = sec_form4_checker.fetch_form4_filings(date(2026, 7, 8))
        return jsonify({
            "status": "success",
            "count": len(filings),
            "filings_sample": [f["raw_url"] for f in filings[:3]] if filings else []
        })
    except Exception as e:
        import traceback
        return jsonify({
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        })


@app.route("/api/financials")
def financials():
    ticker = request.args.get("ticker", "").strip().upper()
    frequency = request.args.get("frequency", "annual").strip().lower()
    if not ticker:
        return jsonify({"error": "Ticker symbol is required."}), 400
    try:
        from edgar import Company
        company = Company(ticker)
        facts = company.get_facts()
        if facts is None:
            return jsonify({"error": f"No facts found for ticker: {ticker}"}), 404
        raw = facts.to_dataframe(include_metadata=True)

        # Always fetch annual for metrics and summary
        income_ann, bs_ann, cf_ann, ttm = fetch_all_financials(ticker, frequency="annual", raw_facts=raw)
        
        if frequency == "quarterly":
            income_df, bs_df, cf_df, _ = fetch_all_financials(ticker, frequency="quarterly", raw_facts=raw)
        else:
            income_df, bs_df, cf_df = income_ann, bs_ann, cf_ann

        summary        = sanitize(compute_summary_metrics(income_ann, bs_ann, cf_ann, ttm, ticker))
        annual_metrics = df_to_rows(compute_annual_metrics(income_ann, bs_ann, cf_ann, ttm, ticker))
        val_context    = sanitize(compute_valuation_context(
                             pd.DataFrame(annual_metrics), summary
                         ))
        return jsonify({
            "ticker":              ticker,
            "frequency":           frequency,
            "summary":             summary,
            "income":              df_to_rows(income_df),
            "balance_sheet":       df_to_rows(bs_df),
            "cash_flow":           df_to_rows(cf_df),
            "annual_metrics":      annual_metrics,
            "ttm":                 sanitize(ttm) if ttm else None,
            "valuation_context":   val_context,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Unexpected error: {e}"}), 500


# ── Stateless JSON Caching & Dynamic Filtering ───────────────────────────────

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def get_market_cap_cached(ticker):
    """Gets market cap for a ticker, using cache/market_caps.json if available."""
    import json
    import yfinance as yf
    
    cache_path = os.path.join(CACHE_DIR, "market_caps.json")
    caps = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                caps = json.load(f)
        except Exception:
            pass
            
    if ticker in caps:
        return caps[ticker]
        
    try:
        info = yf.Ticker(ticker).info
        cap = info.get("marketCap")
        cap_val = float(cap) if cap else None
        caps[ticker] = cap_val
        
        with open(cache_path, "w") as f:
            json.dump(caps, f)
        return cap_val
    except Exception:
        return None


def load_daily_trades(date_str):
    """Loads trades from cache/trades_{date_str}.json or fetches from SEC."""
    import json
    from datetime import datetime
    
    cache_file = os.path.join(CACHE_DIR, f"trades_{date_str}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
            
    # Fetch dynamically from SEC Form 4 Checker
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-companies-to-look-at"))
    import sec_form4_checker
    import importlib
    importlib.reload(sec_form4_checker)
    
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    results = sec_form4_checker.run(target_date, target_date, send=False)
    
    try:
        with open(cache_file, "w") as f:
            json.dump(results, f)
    except Exception as e:
        print("Failed to save daily trades to cache:", e)
        
    return results


@app.route("/api/insider-buys")
def get_insider_buys():
    from datetime import datetime, timedelta
    
    today = datetime.today()
    default_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    
    date_str = request.args.get("date", default_date).strip()
    min_value = request.args.get("min_value", 100000, type=float)
    max_market_cap = request.args.get("max_market_cap", 2000000000, type=float)
    
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
        
    try:
        raw_trades = load_daily_trades(date_str)
        
        filtered = []
        for t in raw_trades:
            if t.get("total_value", 0) < min_value:
                continue
                
            cap = t.get("market_cap")
            if cap is None:
                cap = get_market_cap_cached(t["ticker"])
                t["market_cap"] = cap
                
            if max_market_cap > 0:
                if cap is not None and cap >= max_market_cap:
                    continue
                    
            filtered.append(t)
            
        filtered.sort(key=lambda x: x.get("total_value", 0), reverse=True)
        
        return jsonify({
            "date": date_str,
            "total": len(filtered),
            "results": filtered
        })
    except Exception as e:
        import traceback
        return jsonify({
            "error": f"Failed to fetch insider buys: {e}",
            "traceback": traceback.format_exc()
        }), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)
