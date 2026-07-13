import json
import os
import sys
import sqlite3
import threading
from datetime import datetime, timedelta
import pandas as pd
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

from pull_cash_flow import fetch_all_financials, compute_summary_metrics, compute_annual_metrics, compute_valuation_context

# Clear old cache files on startup to prevent format mismatch crashes
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
if os.path.exists(CACHE_DIR):
    for filename in os.listdir(CACHE_DIR):
        file_path = os.path.join(CACHE_DIR, filename)
        try:
            if os.path.isfile(file_path) and filename.startswith("trades_"):
                os.unlink(file_path)
        except Exception as e:
            print("Failed to delete cache file:", e)

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
    host = request.host.split(':')[0]
    is_local = host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168.")
    return render_template("index.html", ga_id=os.getenv("GOOGLE_ANALYTICS_ID"), is_local=is_local)



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
    host = request.host.split(':')[0]
    if host not in ("localhost", "127.0.0.1", "0.0.0.0") and not host.startswith("192.168."):
        return jsonify({"error": "Insider buys are only available in development environment."}), 403
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
        
    from flask import Response
    from queue import Queue
    import threading

    def filter_trades(raw_trades):
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
        return filtered

    def generate():
        cache_file = os.path.join(CACHE_DIR, f"trades_{date_str}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    raw_trades = json.load(f)
                filtered = filter_trades(raw_trades)
                yield f"data: {json.dumps({'type': 'results', 'data': {'date': date_str, 'total': len(filtered), 'results': filtered}})}\n\n"
                return
            except Exception:
                pass

        q = Queue()
        
        def run_checker():
            try:
                sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-companies-to-look-at"))
                import sec_form4_checker
                import importlib
                importlib.reload(sec_form4_checker)
                
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                
                def cb(current, total):
                    q.put({"type": "progress", "current": current, "total": total})
                    
                results = sec_form4_checker.run(target_date, target_date, send=False, progress_callback=cb)
                
                try:
                    with open(cache_file, "w") as f:
                        json.dump(results, f)
                except Exception as e:
                    print("Failed to save daily trades to cache:", e)
                    
                q.put({"type": "done", "results": results})
            except Exception as e:
                import traceback
                q.put({"type": "error", "error": str(e), "traceback": traceback.format_exc()})

        # Start thread
        t = threading.Thread(target=run_checker)
        t.start()
        
        while True:
            try:
                item = q.get(timeout=1.0)
            except Exception:
                # Keep-alive
                yield ": keepalive\n\n"
                continue

            if item["type"] == "progress":
                yield f"data: {json.dumps({'type': 'progress', 'current': item['current'], 'total': item['total']})}\n\n"
            elif item["type"] == "done":
                filtered = filter_trades(item["results"])
                yield f"data: {json.dumps({'type': 'results', 'data': {'date': date_str, 'total': len(filtered), 'results': filtered}})}\n\n"
                break
            elif item["type"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': item['error']})}\n\n"
                break

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(debug=True, port=8080)
