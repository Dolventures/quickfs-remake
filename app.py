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
    return render_template("index.html")


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


# ── Database & Checker integration ───────────────────────────────────────────

def get_db_connection():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS insider_buys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            issuer_name TEXT,
            insider_name TEXT,
            insider_title TEXT,
            transaction_date TEXT,
            shares REAL,
            price_per_share REAL,
            total_value REAL,
            market_cap REAL,
            filing_url TEXT,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, insider_name, transaction_date, shares, price_per_share)
        )
    """)
    conn.commit()
    conn.close()


# Background thread lock and status
checker_status = {
    "running": False,
    "message": "Idle",
    "last_run": None,
    "error": None
}
checker_lock = threading.Lock()


def bg_run_checker(start_date, end_date):
    global checker_status
    try:
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-companies-to-look-at"))
        import sec_form4_checker
        
        # Parse dates
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        checker_status["message"] = f"Running checker from {start_date} to {end_date}..."
        sec_form4_checker.run(start_d, end_d, send=False)
        checker_status["message"] = f"Successfully finished checking {start_date} to {end_date}."
        checker_status["last_run"] = datetime.now().isoformat()
        checker_status["error"] = None
    except Exception as e:
        import traceback
        traceback.print_exc()
        checker_status["message"] = "Error occurred during checker run."
        checker_status["error"] = str(e)
    finally:
        with checker_lock:
            checker_status["running"] = False


@app.route("/api/insider-buys")
def get_insider_buys():
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    sort_by = request.args.get("sort_by", "transaction_date")
    order = request.args.get("order", "DESC")
    
    # Restrict sort_by to allowed columns to prevent SQL injection
    allowed_cols = {"transaction_date", "total_value", "ticker", "market_cap", "shares", "price_per_share"}
    if sort_by not in allowed_cols:
        sort_by = "transaction_date"
    
    if order.upper() not in ("ASC", "DESC"):
        order = "DESC"
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get count
        count_row = cursor.execute("SELECT COUNT(*) as total FROM insider_buys").fetchone()
        total_count = count_row["total"] if count_row else 0
        
        # Get records
        query = f"""
            SELECT * FROM insider_buys 
            ORDER BY {sort_by} {order} 
            LIMIT ? OFFSET ?
        """
        rows = cursor.execute(query, (limit, offset)).fetchall()
        
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "ticker": r["ticker"],
                "issuer_name": r["issuer_name"],
                "insider_name": r["insider_name"],
                "insider_title": r["insider_title"],
                "transaction_date": r["transaction_date"],
                "shares": r["shares"],
                "price_per_share": r["price_per_share"],
                "total_value": r["total_value"],
                "market_cap": r["market_cap"],
                "filing_url": r["filing_url"],
                "processed_at": r["processed_at"]
            })
        conn.close()
        
        return jsonify({
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "results": results
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Database error: {e}"}), 500


@app.route("/api/insider-buys/run", methods=["POST"])
def run_insider_buys_checker():
    global checker_status
    with checker_lock:
        if checker_status["running"]:
            return jsonify({"error": "Checker is already running in background."}), 400
        
        # Get start/end date from request
        data = request.get_json(silent=True) or {}
        today = datetime.today()
        # Default to last 7 days (yesterday - 7 days to yesterday)
        default_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        default_end = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        
        start_date = data.get("start_date") or request.args.get("start_date") or default_start
        end_date = data.get("end_date") or request.args.get("end_date") or default_end
        
        # Validate date format
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
            
        checker_status["running"] = True
        checker_status["message"] = "Initializing..."
        checker_status["error"] = None
        
        t = threading.Thread(target=bg_run_checker, args=(start_date, end_date), daemon=True)
        t.start()
        
        return jsonify({"status": "started", "start_date": start_date, "end_date": end_date})


@app.route("/api/insider-buys/status")
def insider_buys_status():
    return jsonify(checker_status)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=8080)
