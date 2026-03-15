import json
import pandas as pd
from flask import Flask, render_template, request, jsonify
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
    if not ticker:
        return jsonify({"error": "Ticker symbol is required."}), 400
    try:
        income_df, bs_df, cf_df, ttm = fetch_all_financials(ticker)
        summary        = sanitize(compute_summary_metrics(income_df, bs_df, cf_df, ttm, ticker))
        annual_metrics = df_to_rows(compute_annual_metrics(income_df, bs_df, cf_df, ttm, ticker))
        val_context    = sanitize(compute_valuation_context(
                             pd.DataFrame(annual_metrics), summary
                         ))
        return jsonify({
            "ticker":              ticker,
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
        return jsonify({"error": f"Unexpected error: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)
