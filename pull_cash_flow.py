import numpy as np
import pandas as pd
import yfinance as yf
from edgar import set_identity, Company

set_identity("daniellandy1@gmail.com")

ANNUAL_FORMS = {"10-K", "10-K405", "10-KSB", "20-F", "20-F/A"}

CASH_FLOW_CONCEPTS = {
    "NetCashProvidedByUsedInOperatingActivities": "OperatingCF",
    "NetCashProvidedByUsedInInvestingActivities": "InvestingCF",
    "NetCashProvidedByUsedInFinancingActivities": "FinancingCF",
    "PaymentsToAcquirePropertyPlantAndEquipment": "CapEx",
    "ShareBasedCompensation":                     "StockBasedCompensation",
    "AllocatedShareBasedCompensationExpense":      "StockBasedCompensation",
    "PaymentsToAcquireBusinessesNetOfCashAcquired": "Acquisitions",
    "PaymentsToAcquireBusinessesGross":            "Acquisitions",
    "PaymentsForRepurchaseOfCommonStock":          "ShareRepurchases",
    "PaymentsForRepurchaseOfEquity":               "ShareRepurchases",
    "PaymentsOfDividends":                         "DividendsPaid",
    "PaymentsOfDividendsCommonStock":              "DividendsPaid",
}

# IFRS equivalents for cash flow (ifrs-full: prefix)
CASH_FLOW_CONCEPTS_IFRS = {
    "CashFlowsFromUsedInOperatingActivities":                             "OperatingCF",
    "CashFlowsFromOperations":                                            "OperatingCF",
    "CashFlowsFromUsedInInvestingActivities":                             "InvestingCF",
    "CashFlowsFromUsedInFinancingActivities":                             "FinancingCF",
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": "CapEx",
    "AcquisitionOfPropertyPlantAndEquipment":                             "CapEx",
    "PurchaseOfPropertyPlantAndEquipment":                                "CapEx",
    "AdjustmentsForSharebasedPayments":                                   "StockBasedCompensation",
    "CashFlowsFromUsedInAcquiringControlOfSubsidiariesOrOtherBusinesses": "Acquisitions",
    "PaymentsToAcquireOrRedeemEntitysShares":                             "ShareRepurchases",
    "DividendsPaidClassifiedAsFinancingActivities":                        "DividendsPaid",
    "DividendsPaid":                                                       "DividendsPaid",
}

INCOME_CONCEPTS = {
    "Revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "RegulatedAndUnregulatedOperatingRevenue",
        "RevenuesNetOfInterestExpense",
    ],
    "CostOfSales": [
        "CostOfRevenue",
        "CostOfGoodsSold",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsAndServiceExcludingDepletionDepreciationAndAmortization",
        "CostOfServices",
    ],
    "OperatingExpenses": [
        "OperatingExpenses",
        "CostsAndExpenses",
        "OperatingCostsAndExpenses",
    ],
    "OperatingIncome": [
        "OperatingIncomeLoss",
    ],
    "DA": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
        "DepreciationAmortizationAndAccretionNet",
        "OtherDepreciationAndAmortization",
    ],
    "InterestExpense": [
        "InterestExpense",
        "InterestAndDebtExpense",
        "InterestExpenseDebt",
        "InterestExpenseNonoperating",
    ],
    "TaxExpense": [
        "IncomeTaxExpense",
    ],
    "PreTaxIncome": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    ],
    "NetIncome": [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "NetIncomeLossAvailableToCommonStockholdersDiluted",
        "ProfitLoss",
        "IncomeLossFromContinuingOperations",
        "NetIncomeLossAttributableToParent",
    ],
    "DilutedShares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    ],
    "EPSDiluted": [
        "EarningsPerShareDiluted",
        "IncomeLossFromContinuingOperationsPerDilutedShare",
        "EarningsPerShareBasicAndDiluted",
    ],
}

BALANCE_SHEET_CONCEPTS = {
    "Cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
        "CashAndCashEquivalentsAndShortTermInvestments",
        "CashAndDueFromBanks",
    ],
    "CurrentAssets": ["AssetsCurrent"],
    "TotalAssets":   ["Assets"],
    "CurrentLiabilities": ["LiabilitiesCurrent"],
    "CurrentDebt": [
        "LongTermDebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "DebtCurrent",
        "NotesPayableCurrent",
        "ShortTermBorrowings",
        "CommercialPaper",
    ],
    "LongTermDebt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermNotesPayable",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "OperatingLeaseLiabilityNoncurrent": [
        "OperatingLeaseLiabilityNoncurrent",
    ],
    "OperatingLeaseLiabilityCurrent": [
        "OperatingLeaseLiabilityCurrent",
    ],
    "TotalLiabilities": [
        "Liabilities",
        "LiabilitiesOtherThanLongtermDebtNoncurrent",
    ],
    "TotalLiabilitiesAndEquity": [
        "LiabilitiesAndStockholdersEquity",
        "LiabilitiesAndPartnersCapital",
    ],
    "StockholdersEquity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "MembersEquity",
        "PartnersCapital",
    ],
}

# ── IFRS concept equivalents (for 20-F filers) ────────────────────────────────
# These use the ifrs-full: taxonomy instead of us-gaap:

INCOME_CONCEPTS_IFRS = {
    "Revenue": [
        "Revenue",
        "RevenueFromContractsWithCustomers",
        "RevenueFromSaleOfGoods",
        "RevenueFromRenderingOfServices",
        "RevenueFromRoyalties",
    ],
    "CostOfSales": [
        "CostOfSales",
        "CostOfGoodsAndServicesRendered",
    ],
    "OperatingExpenses": [
        "OperatingExpense",
        "SellingGeneralAndAdministrativeExpense",
        "OtherExpenseByNature",
    ],
    "OperatingIncome": [
        "ProfitLossFromOperatingActivities",
        "OperatingProfit",
        "ProfitLossBeforeFinanceCostsAndIncomeTax",
    ],
    "DA": [
        "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
        "DepreciationAndAmortisationExpense",
        "AdjustmentsForDepreciationAndAmortisationExpense",
        "DepreciationAmortisationAndImpairmentLoss",
    ],
    "InterestExpense": [
        "FinanceCosts",
        "InterestExpense",
        "FinanceIncomeCost",
    ],
    "TaxExpense": [
        "IncomeTaxExpenseContinuingOperations",
        "IncomeTaxExpense",
    ],
    "PreTaxIncome": [
        "ProfitLossBeforeTax",
    ],
    "NetIncome": [
        "ProfitLossAttributableToOwnersOfParent",
        "ProfitLossAttributableToEquityHoldersOfParent",
        "ProfitLoss",
    ],
    "DilutedShares": [
        "WeightedAverageNumberOfSharesOutstandingDiluted",
        "WeightedAverageShares",
        "AdjustedWeightedAverageShares",
    ],
    "EPSDiluted": [
        "DilutedEarningsLossPerShare",
        "BasicEarningsLossPerShare",
    ],
}

BALANCE_SHEET_CONCEPTS_IFRS = {
    "Cash": [
        "CashAndCashEquivalents",
        "CashAndBankBalancesAtCentralBanks",
    ],
    "CurrentAssets": ["CurrentAssets"],
    "TotalAssets":   ["Assets"],
    "CurrentLiabilities": ["CurrentLiabilities"],
    "CurrentDebt": [
        "CurrentPortionOfNoncurrentBorrowings",
        "CurrentBorrowings",
        "ShorttermBorrowings",
    ],
    "LongTermDebt": [
        "NoncurrentPortionOfNoncurrentBorrowings",
        "NoncurrentBorrowings",
        "BorrowingsNoncurrent",
        "NoncurrentLiabilitiesFromFinancingActivities",
    ],
    "OperatingLeaseLiabilityNoncurrent": [
        "NoncurrentLeaseLiabilities",
        "NoncurrentOperatingLeaseLiabilities",
    ],
    "OperatingLeaseLiabilityCurrent": [
        "CurrentLeaseLiabilities",
        "CurrentOperatingLeaseLiabilities",
    ],
    "TotalLiabilities": ["Liabilities"],
    "TotalLiabilitiesAndEquity": ["EquityAndLiabilities"],
    "StockholdersEquity": [
        "EquityAttributableToOwnersOfParent",
        "Equity",
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prep_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["period_end"]   = pd.to_datetime(df["period_end"])
    df["filing_date"]  = pd.to_datetime(df["filing_date"])
    return df


def _filter_annual_flow(df: pd.DataFrame) -> pd.DataFrame:
    df = _prep_dates(df[df["form_type"].isin(ANNUAL_FORMS)])
    days = (df["period_end"] - df["period_start"]).dt.days
    return df[(days >= 340) & (days <= 390)].copy()


def _filter_annual_instant(df: pd.DataFrame) -> pd.DataFrame:
    df = _prep_dates(df[df["form_type"].isin(ANNUAL_FORMS)])
    return df[df["period_start"].isna()].copy()


def _filter_quarterly_flow(df: pd.DataFrame) -> pd.DataFrame:
    # Include 10-Q and 10-K (for Q4/Annual)
    forms = ANNUAL_FORMS | {"10-Q", "10-Q/A"}
    df = _prep_dates(df[df["form_type"].isin(forms)])
    days = (df["period_end"] - df["period_start"]).dt.days
    # Filter for ~3, ~6, ~9, or ~12 months
    # (Q1/3m, Q2_YTD/6m, Q3_YTD/9m, Annual/12m)
    return df[(days >= 80) & (days <= 400)].copy()


def _filter_quarterly_instant(df: pd.DataFrame) -> pd.DataFrame:
    forms = ANNUAL_FORMS | {"10-Q", "10-Q/A"}
    df = _prep_dates(df[df["form_type"].isin(forms)])
    return df[df["period_start"].isna()].copy()


def _dedup_and_pivot(df: pd.DataFrame, fact_cols: list, frequency: str = "annual") -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return pd.DataFrame(columns=fact_cols)

    if frequency == "annual":
        df["bucket"] = df["period_end"].dt.year
    else:
        # Use Period for quarterly bucketing to handle slight date shifts
        df["bucket"] = df["period_end"].dt.to_period("Q")

    df = (
        df.sort_values("filing_date")
        .drop_duplicates(subset=["fact", "bucket"], keep="last")
    )
    canonical_end = df.groupby("bucket")["period_end"].max()
    if not canonical_end.empty:
        df["period_end"] = df["bucket"].map(canonical_end)
    pivot = df.pivot(index="period_end", columns="fact", values="numeric_value")
    pivot = pivot.sort_index()
    for col in fact_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    return pivot[fact_cols]


def _derive_quarterly_flow(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derives missing 3-month values (especially Q4) from YTD values.
    Expects df with columns: fact, period_start, period_end, numeric_value, filing_date
    """
    if df.empty:
        return df
    
    # Ensure datetimes
    df = df.copy()
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    
    # Instant data (Balance Sheet) has no period_start; no derivation possible/needed
    if df["period_start"].isnull().all():
        return df
    
    # Sort for consistent processing
    df = df.sort_values(["fact", "period_start", "period_end", "filing_date"])
    
    final_records = []
    
    for fact, f_df in df.groupby("fact"):
        f_df = f_df.copy()
        f_df["days"] = (f_df["period_end"] - f_df["period_start"]).dt.days
        
        # Identify explicit 3m records
        explicit_3m = f_df[(f_df["days"] >= 80) & (f_df["days"] <= 105)].copy()
        
        # Identify YTD records (3m, 6m, 9m, 12m)
        # Group by period_start (fiscal year start)
        for p_start, g in f_df.groupby("period_start"):
            # Best value for each period_end
            g = g.sort_values("filing_date").drop_duplicates("period_end", keep="last")
            
            ytd = {} # duration_bin -> (value, period_end, row)
            for _, row in g.iterrows():
                d = row["days"]
                if 80 <= d <= 105:   ytd[3] = (row["numeric_value"], row["period_end"], row)
                elif 160 <= d <= 200: ytd[6] = (row["numeric_value"], row["period_end"], row)
                elif 250 <= d <= 300: ytd[9] = (row["numeric_value"], row["period_end"], row)
                elif 340 <= d <= 400: ytd[12] = (row["numeric_value"], row["period_end"], row)
            
            # Now derive missing quarters
            # Q2 = 6m - 3m
            if 6 in ytd and 3 in ytd:
                val6, end6, row6 = ytd[6]
                val3, end3, row3 = ytd[3]
                if explicit_3m[explicit_3m["period_end"] == end6].empty:
                    new_row = row6.copy()
                    new_row["numeric_value"] = val6 - val3
                    # Set period_start to ~90 days before period_end to mark it as 3m
                    new_row["period_start"] = end6 - pd.DateOffset(days=90)
                    explicit_3m = pd.concat([explicit_3m, pd.DataFrame([new_row])], ignore_index=True)
            
            # Q3 = 9m - 6m
            if 9 in ytd and 6 in ytd:
                val9, end9, row9 = ytd[9]
                val6, end6, row6 = ytd[6]
                if explicit_3m[explicit_3m["period_end"] == end9].empty:
                    new_row = row9.copy()
                    new_row["numeric_value"] = val9 - val6
                    new_row["period_start"] = end9 - pd.DateOffset(days=90)
                    explicit_3m = pd.concat([explicit_3m, pd.DataFrame([new_row])], ignore_index=True)

            # Q4 = 12m - 9m
            if 12 in ytd and 9 in ytd:
                val12, end12, row12 = ytd[12]
                val9, end9, row9 = ytd[9]
                if explicit_3m[explicit_3m["period_end"] == end12].empty:
                    new_row = row12.copy()
                    new_row["numeric_value"] = val12 - val9
                    new_row["period_start"] = end12 - pd.DateOffset(days=90)
                    explicit_3m = pd.concat([explicit_3m, pd.DataFrame([new_row])], ignore_index=True)

        final_records.append(explicit_3m)
        
    if not final_records:
        return pd.DataFrame()
        
    return pd.concat(final_records, ignore_index=True)


def _build_from_concepts(df_raw, concepts: dict, ifrs_concepts: dict = None, frequency: str = "annual") -> pd.DataFrame:
    frames = []
    for metric, candidates in concepts.items():
        prefixed = [f"us-gaap:{c}" for c in candidates]
        if ifrs_concepts and metric in ifrs_concepts:
            prefixed += [f"ifrs-full:{c}" for c in ifrs_concepts[metric]]
        sub = df_raw[df_raw["concept"].isin(prefixed)].copy()
        if not sub.empty:
            concept_priority = {c: i for i, c in enumerate(prefixed)}
            sub["_priority"] = sub["concept"].map(concept_priority)
            sub["fact"] = metric
            frames.append(sub)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)

    if frequency == "annual":
        combined["_bucket"] = pd.to_datetime(combined["period_end"]).dt.year
        # Within each (fact, bucket, priority), keep the most recent filing
        combined = (combined.sort_values("filing_date")
                    .drop_duplicates(subset=["fact", "_bucket", "_priority"], keep="last"))
        # Among priorities, prefer the highest-priority concept
        combined = (combined.sort_values("_priority")
                    .drop_duplicates(subset=["fact", "_bucket"], keep="first"))
        combined = combined.drop(columns=["_bucket", "_priority"])
    else:
        # Quarterly: Need to preserve multiple durations for derivation
        # Within each (fact, period_start, period_end, priority), keep the most recent filing
        combined = (combined.sort_values("filing_date")
                    .drop_duplicates(subset=["fact", "period_start", "period_end", "_priority"], keep="last"))
        # Among priorities, prefer the highest-priority concept
        combined = (combined.sort_values("_priority")
                    .drop_duplicates(subset=["fact", "period_start", "period_end"], keep="first"))
        
        combined = _derive_quarterly_flow(combined)

    pivot = _dedup_and_pivot(combined, list(concepts.keys()), frequency=frequency)
    pivot.index.name = "period_end"
    pivot.reset_index(inplace=True)
    return pivot


def _safe(val):
    """Return float or None — never NaN."""
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except Exception:
        return None


# ── TTM computation ───────────────────────────────────────────────────────────

def _compute_ttm(raw: pd.DataFrame,
                 income_pivot: pd.DataFrame,
                 bs_pivot: pd.DataFrame,
                 cf_pivot_full: pd.DataFrame) -> dict | None:
    """
    TTM (Trailing Twelve Months) using the formula:
        TTM = Latest Annual + Current YTD - Prior Year Same YTD

    This naturally accounts for seasonality — no naive ×4 multiplication.
    Returns None if the most recent 10-K is already more current than any 10-Q.
    """

    # ── Build flat concept lookups (US-GAAP + IFRS) ───────────────────────────
    income_lookup = {
        f"us-gaap:{c}": metric
        for metric, candidates in INCOME_CONCEPTS.items()
        for c in candidates
    }
    income_lookup.update({
        f"ifrs-full:{c}": metric
        for metric, candidates in INCOME_CONCEPTS_IFRS.items()
        for c in candidates
    })
    cf_lookup = {f"us-gaap:{k}": v for k, v in CASH_FLOW_CONCEPTS.items()}
    cf_lookup.update({f"ifrs-full:{k}": v for k, v in CASH_FLOW_CONCEPTS_IFRS.items()})
    all_flow_lookup = {**income_lookup, **cf_lookup}

    bs_lookup = {
        f"us-gaap:{c}": metric
        for metric, candidates in BALANCE_SHEET_CONCEPTS.items()
        for c in candidates
    }
    bs_lookup.update({
        f"ifrs-full:{c}": metric
        for metric, candidates in BALANCE_SHEET_CONCEPTS_IFRS.items()
        for c in candidates
    })

    # ── Filter 10-Q duration (flow) data ─────────────────────────────────────
    q_flow = _prep_dates(raw[raw["form_type"] == "10-Q"].copy())
    q_flow = q_flow[q_flow["period_start"].notna()].copy()
    q_flow["dur"] = (q_flow["period_end"] - q_flow["period_start"]).dt.days
    # Q1 (~90d), Q2 YTD (~180d), Q3 YTD (~270d)
    q_flow = q_flow[(q_flow["dur"] >= 80) & (q_flow["dur"] <= 285)].copy()
    q_flow = q_flow[q_flow["concept"].isin(all_flow_lookup)].copy()
    q_flow["fact"] = q_flow["concept"].map(all_flow_lookup)

    if q_flow.empty:
        return None

    # Most recent 10-Q period end
    latest_q_end = q_flow["period_end"].max()

    # If the most recent annual already covers this period, no TTM needed
    if not income_pivot.empty:
        latest_annual_end = pd.to_datetime(income_pivot["period_end"]).max()
        if latest_annual_end >= latest_q_end:
            return None

    # YTD duration of the latest 10-Q (determines which quarter it is)
    latest_entries = q_flow[q_flow["period_end"] == latest_q_end]
    ytd_dur = (latest_entries["period_end"] - latest_entries["period_start"]).dt.days.median()

    def best_ytd(df, target_end, dur_tolerance=35):
        """Get deduplicated fact values for the period closest to target_end."""
        mask = (
            (df["period_end"] >= target_end - pd.DateOffset(days=dur_tolerance)) &
            (df["period_end"] <= target_end + pd.DateOffset(days=dur_tolerance)) &
            (np.abs(df["dur"] - ytd_dur) <= dur_tolerance)
        )
        sub = df[mask].copy()
        if sub.empty:
            return pd.Series(dtype=float)
        # Pick the period_end that's closest to target
        best_end = sub["period_end"].iloc[
            np.abs((sub["period_end"] - target_end).dt.total_seconds()).argmin()
        ]
        return (
            sub[sub["period_end"] == best_end]
            .sort_values("filing_date")
            .drop_duplicates(subset=["fact"], keep="last")
            .set_index("fact")["numeric_value"]
        )

    curr_ytd  = best_ytd(q_flow, latest_q_end)
    prior_ytd = best_ytd(q_flow, latest_q_end - pd.DateOffset(years=1))

    if curr_ytd.empty or prior_ytd.empty:
        return None

    # Most recent annual rows
    annual_income = income_pivot.sort_values("period_end").iloc[-1]
    annual_cf     = cf_pivot_full.sort_values("period_end").iloc[-1]

    def ttm(annual_val, curr_val, prior_val):
        a, c, p = _safe(annual_val), _safe(curr_val), _safe(prior_val)
        if None in (a, c, p):
            return None
        return a + c - p

    # Quarter label (e.g. "Q1 FY2026")
    quarter_num = max(1, round(ytd_dur / 91))
    period_label = f"Q{quarter_num} TTM"

    # ── Income statement TTM ──────────────────────────────────────────────────
    inc = {}
    for metric in INCOME_CONCEPTS:
        inc[metric] = ttm(annual_income.get(metric),
                          curr_ytd.get(metric),
                          prior_ytd.get(metric))

    rev, cogs = _safe(inc.get("Revenue")), _safe(inc.get("CostOfSales"))
    inc["GrossMargin"]    = ((rev - cogs) / rev * 100) if rev and cogs else None
    opinc                 = _safe(inc.get("OperatingIncome"))
    inc["OperatingMargin"] = (opinc / rev * 100) if opinc is not None and rev else None

    # EBITDA
    da     = _safe(inc.get("DA"))
    ebitda = (opinc + da) if (opinc is not None and da is not None) else None
    inc["EBITDA"]       = ebitda
    inc["EBITDAMargin"] = (ebitda / rev * 100) if (ebitda is not None and rev) else None

    # YoY growth: TTM vs most recent full annual year
    ann_rev   = _safe(annual_income.get("Revenue"))
    ann_opinc = _safe(annual_income.get("OperatingIncome"))
    inc["RevenueGrowth"]          = ((rev / ann_rev) - 1) * 100 if (rev and ann_rev and ann_rev > 0) else None
    inc["OperatingIncomeGrowth"]  = ((opinc / ann_opinc) - 1) * 100 if (opinc is not None and ann_opinc and ann_opinc != 0) else None

    # ── Cash flow TTM ─────────────────────────────────────────────────────────
    cf = {}
    for metric in ["OperatingCF", "InvestingCF", "FinancingCF", "CapEx",
                   "StockBasedCompensation", "Acquisitions", "ShareRepurchases", "DividendsPaid"]:
        cf[metric] = ttm(annual_cf.get(metric),
                         curr_ytd.get(metric),
                         prior_ytd.get(metric))

    op, capex = _safe(cf.get("OperatingCF")), _safe(cf.get("CapEx"))
    inv = _safe(cf.get("InvestingCF"))
    if op is not None and capex is not None:
        cf["FreeCashFlow"] = op - capex
    elif op is not None and inv is not None:
        cf["FreeCashFlow"] = op + inv
    else:
        cf["FreeCashFlow"] = None
    # CapEx is kept in cf dict (do not pop it)

    # ── Balance sheet: latest 10-Q instant values (no annualization) ─────────
    q_inst = _prep_dates(raw[raw["form_type"] == "10-Q"].copy())
    q_inst = q_inst[q_inst["period_start"].isna()].copy()
    q_inst = q_inst[q_inst["concept"].isin(bs_lookup)].copy()
    q_inst["fact"] = q_inst["concept"].map(bs_lookup)

    bs = {}
    if not q_inst.empty:
        latest_bs_end = q_inst["period_end"].max()
        latest_bs_vals = (
            q_inst[q_inst["period_end"] == latest_bs_end]
            .sort_values("filing_date")
            .drop_duplicates(subset=["fact"], keep="last")
            .set_index("fact")["numeric_value"]
        )
        for metric in BALANCE_SHEET_CONCEPTS:
            bs[metric] = _safe(latest_bs_vals.get(metric))

        # Back-fill TotalLiabilities
        if bs.get("TotalLiabilities") is None:
            tle = bs.get("TotalLiabilitiesAndEquity")
            eq  = bs.get("StockholdersEquity")
            if tle and eq:
                bs["TotalLiabilities"] = tle - eq
        bs.pop("TotalLiabilitiesAndEquity", None)

        ltdebt  = bs.get("LongTermDebt") or 0
        stdebt  = bs.get("CurrentDebt") or 0
        ol_nc   = bs.get("OperatingLeaseLiabilityNoncurrent") or 0
        ol_cur  = bs.get("OperatingLeaseLiabilityCurrent") or 0
        cash    = bs.get("Cash") or 0
        bs["TotalDebt"]                = ltdebt + stdebt
        bs["OperatingLeaseLiabilities"] = ol_nc + ol_cur
        bs["NetDebt"]                  = bs["TotalDebt"] - cash

    return {
        "period_label": period_label,
        "income":        inc,
        "balance_sheet": bs,
        "cash_flow":     cf,
    }


def _post_process_pivots(income_pivot, bs_pivot, cf_pivot_full, frequency: str = "annual"):
    # ── Income statement post-processing ──────────────────────────────────────
    if not income_pivot.empty:
        # Fix DilutedShares unit inconsistency
        if "DilutedShares" in income_pivot.columns:
            shares = income_pivot["DilutedShares"].dropna()
            if len(shares) >= 2:
                median_shares = shares.median()
                mask = income_pivot["DilutedShares"] < (median_shares * 0.01)
                income_pivot.loc[mask, "DilutedShares"] *= 1000

        income_pivot["GrossMargin"] = (
            (income_pivot.get("Revenue", 0) - income_pivot.get("CostOfSales", 0))
            / income_pivot.get("Revenue", np.nan) * 100
        )
        income_pivot["OperatingMargin"] = (
            income_pivot.get("OperatingIncome", 0) / income_pivot.get("Revenue", np.nan) * 100
        )
        income_pivot["EBITDA"] = income_pivot.get("OperatingIncome", 0) + income_pivot.get("DA", 0)
        income_pivot["EBITDAMargin"] = income_pivot.get("EBITDA", 0) / income_pivot.get("Revenue", np.nan) * 100

        income_pivot = income_pivot.sort_values("period_end").reset_index(drop=True)
        if frequency == "quarterly":
            # YoY growth for quarterly: pct_change(4) assumes 4 quarters per year
            income_pivot["RevenueGrowth"] = income_pivot["Revenue"].pct_change(4) * 100
            income_pivot["OperatingIncomeGrowth"] = income_pivot["OperatingIncome"].pct_change(4) * 100
        else:
            income_pivot["RevenueGrowth"] = income_pivot["Revenue"].pct_change() * 100
            income_pivot["OperatingIncomeGrowth"] = income_pivot["OperatingIncome"].pct_change() * 100

    # ── Balance sheet post-processing ─────────────────────────────────────────
    if not bs_pivot.empty:
        if "TotalLiabilities" not in bs_pivot.columns and "TotalLiabilitiesAndEquity" in bs_pivot.columns:
            bs_pivot["TotalLiabilities"] = (
                bs_pivot["TotalLiabilitiesAndEquity"] - bs_pivot["StockholdersEquity"]
            )
        bs_pivot.drop(columns=["TotalLiabilitiesAndEquity"], errors="ignore", inplace=True)
        bs_pivot["TotalDebt"] = bs_pivot.get("LongTermDebt", 0).fillna(0) + bs_pivot.get("CurrentDebt", 0).fillna(0)
        bs_pivot["OperatingLeaseLiabilities"] = (
            bs_pivot.get("OperatingLeaseLiabilityNoncurrent", 0).fillna(0)
            + bs_pivot.get("OperatingLeaseLiabilityCurrent", 0).fillna(0)
        )
        bs_pivot["NetDebt"]   = bs_pivot["TotalDebt"] - bs_pivot.get("Cash", 0).fillna(0)

    # ── Cash flow post-processing ─────────────────────────────────────────────
    if not cf_pivot_full.empty:
        has_capex = cf_pivot_full.get("CapEx").notna() if "CapEx" in cf_pivot_full.columns else pd.Series([False]*len(cf_pivot_full))
        cf_pivot_full["FreeCashFlow"] = np.where(
            has_capex,
            cf_pivot_full.get("OperatingCF", 0) - cf_pivot_full.get("CapEx", 0),
            np.where(
                cf_pivot_full.get("InvestingCF").notna() if "InvestingCF" in cf_pivot_full.columns else False,
                cf_pivot_full.get("OperatingCF", 0) + cf_pivot_full.get("InvestingCF", 0),
                np.nan
            )
        )
    
    return income_pivot, bs_pivot, cf_pivot_full


# ── Main fetch ────────────────────────────────────────────────────────────────

def fetch_all_financials(ticker: str, frequency: str = "annual", raw_facts=None):
    if raw_facts is not None:
        raw = raw_facts
    else:
        company = Company(ticker)
        facts   = company.get_facts()
        if facts is None:
            raise ValueError(f"No facts found for ticker: {ticker}")
        raw = facts.to_dataframe(include_metadata=True)
    
    if frequency == "annual":
        flow_raw    = _filter_annual_flow(raw)
        instant_raw = _filter_annual_instant(raw)
    else:
        flow_raw    = _filter_quarterly_flow(raw)
        instant_raw = _filter_quarterly_instant(raw)

    if flow_raw.empty and instant_raw.empty:
        raise ValueError(f"No {frequency} filing data found for ticker: {ticker}")

    # ── Income statement ──────────────────────────────────────────────────────
    income_pivot = _build_from_concepts(flow_raw, INCOME_CONCEPTS, INCOME_CONCEPTS_IFRS, frequency=frequency)
    if income_pivot.empty:
        raise ValueError(f"No income statement data found for {frequency} for ticker: {ticker}")

    # ── Balance sheet ─────────────────────────────────────────────────────────
    bs_pivot = _build_from_concepts(instant_raw, BALANCE_SHEET_CONCEPTS, BALANCE_SHEET_CONCEPTS_IFRS, frequency=frequency)

    # ── Cash flow ─────────────────────────────────────────────────────────────
    # Convert CASH_FLOW_CONCEPTS to the same format as INCOME_CONCEPTS for _build_from_concepts
    # Mapping from metric to list of concepts
    cf_concepts = {}
    for concept, metric in CASH_FLOW_CONCEPTS.items():
        if metric not in cf_concepts: cf_concepts[metric] = []
        cf_concepts[metric].append(concept)
    
    cf_concepts_ifrs = {}
    for concept, metric in CASH_FLOW_CONCEPTS_IFRS.items():
        if metric not in cf_concepts_ifrs: cf_concepts_ifrs[metric] = []
        cf_concepts_ifrs[metric].append(concept)

    cf_pivot_full = _build_from_concepts(flow_raw, cf_concepts, cf_concepts_ifrs, frequency=frequency)
    if cf_pivot_full.empty:
        raise ValueError(f"No cash flow data found for {frequency} for ticker: {ticker}")

    # Post-process
    income_pivot, bs_pivot, cf_pivot_full = _post_process_pivots(income_pivot, bs_pivot, cf_pivot_full, frequency=frequency)

    # ── TTM (always computed from raw) ────────────────────────────────────────
    # For TTM we need the annual income_pivot to know where the annuals end
    if frequency == "annual":
        ann_income = income_pivot
        ann_bs     = bs_pivot
        ann_cf     = cf_pivot_full
    else:
        # Fetch annual if we are doing quarterly, because TTM needs them
        flow_ann    = _filter_annual_flow(raw)
        inst_ann    = _filter_annual_instant(raw)
        ann_income  = _build_from_concepts(flow_ann, INCOME_CONCEPTS, INCOME_CONCEPTS_IFRS, frequency="annual")
        ann_bs      = _build_from_concepts(inst_ann, BALANCE_SHEET_CONCEPTS, BALANCE_SHEET_CONCEPTS_IFRS, frequency="annual")
        ann_cf      = _build_from_concepts(flow_ann, cf_concepts, cf_concepts_ifrs, frequency="annual")
        ann_income, ann_bs, ann_cf = _post_process_pivots(ann_income, ann_bs, ann_cf, frequency="annual")

    ttm = _compute_ttm(raw, ann_income, ann_bs, ann_cf)

    return income_pivot, bs_pivot, cf_pivot_full, ttm


# ── Summary metrics ───────────────────────────────────────────────────────────

def _cagr(start_val, end_val, years) -> float | None:
    if None in (start_val, end_val) or start_val <= 0 or end_val <= 0 or years <= 0:
        return None
    return ((end_val / start_val) ** (1 / years) - 1) * 100


def _row_nearest_to_years_ago(df: pd.DataFrame, years: int):
    df = df.copy()
    df["_pe"] = pd.to_datetime(df["period_end"])
    latest_date = df["_pe"].max()
    target_date = latest_date - pd.DateOffset(years=years)
    idx = (df["_pe"] - target_date).abs().idxmin()
    return df.loc[idx]


def compute_summary_metrics(income_df, bs_df, cf_df, ttm, ticker):
    try:
        info        = yf.Ticker(ticker).info
        market_cap  = info.get("marketCap") or None
        share_price = info.get("currentPrice") or info.get("regularMarketPrice") or None
        beta        = info.get("beta") or None
        avg_vol     = info.get("averageVolume") or None
        shares_out  = info.get("sharesOutstanding") or None
        share_turnover = (avg_vol * 252 / shares_out) if (avg_vol and shares_out) else None
    except Exception:
        market_cap = share_price = beta = share_turnover = None

    result = {
        "market_cap":     market_cap,
        "share_price":    share_price,
        "beta":           beta,
        "share_turnover": share_turnover,
    }

    # FCF yields (use TTM FCF if available, else latest annual)
    ttm_fcf = _safe(ttm["cash_flow"].get("FreeCashFlow")) if ttm else None
    latest_annual_fcf = _safe(
        cf_df.sort_values("period_end")["FreeCashFlow"].dropna().iloc[-1]
        if not cf_df["FreeCashFlow"].dropna().empty else None
    )
    fcf_for_yield = ttm_fcf if ttm_fcf is not None else latest_annual_fcf

    all_fcf = cf_df.sort_values("period_end")["FreeCashFlow"].dropna()

    if market_cap and market_cap > 0:
        avg_fcf = all_fcf.mean() if not all_fcf.empty else None
        result["current_fcf_yield"]   = (fcf_for_yield / market_cap * 100) if fcf_for_yield else None
        result["avg_fcf_yield"]       = (avg_fcf / market_cap * 100) if avg_fcf else None
        result["fcf_yield_n_years"]   = int(len(all_fcf))
    else:
        result["current_fcf_yield"] = result["avg_fcf_yield"] = None
        result["fcf_yield_n_years"] = None

    # EV / Sales — use same methodology as annual table (market_cap + total debt - cash)
    ttm_rev = _safe(ttm["income"].get("Revenue")) if ttm else None
    latest_rev = _safe(
        income_df.sort_values("period_end")["Revenue"].dropna().iloc[-1]
        if not income_df["Revenue"].dropna().empty else None
    )
    rev_for_ev = ttm_rev if ttm_rev is not None else latest_rev

    # Pick most recent balance sheet: prefer TTM BS, fall back to latest annual
    if ttm and ttm.get("balance_sheet"):
        bs_for_ev  = ttm["balance_sheet"]
        totdebt_ev = _safe(bs_for_ev.get("TotalDebt")) or 0
        ol_ev      = _safe(bs_for_ev.get("OperatingLeaseLiabilities")) or 0
        cash_ev    = _safe(bs_for_ev.get("Cash")) or 0
    elif not bs_df.empty:
        latest_bs  = bs_df.sort_values("period_end").iloc[-1]
        totdebt_ev = _safe(latest_bs.get("TotalDebt")) or 0
        ol_ev      = _safe(latest_bs.get("OperatingLeaseLiabilities")) or 0
        cash_ev    = _safe(latest_bs.get("Cash")) or 0
    else:
        totdebt_ev = ol_ev = cash_ev = 0

    ev_computed = (market_cap + totdebt_ev + ol_ev - cash_ev) if market_cap else None
    result["ev"] = ev_computed
    result["ev_to_sales"] = (ev_computed / rev_for_ev) if (ev_computed and rev_for_ev) else None

    # Full-history CAGRs
    for key, col, df_ in [
        ("revenue_cagr", "Revenue",       income_df),
        ("share_cagr",   "DilutedShares", income_df),
        ("asset_cagr",   "TotalAssets",   bs_df),
        ("fcf_cagr",     "FreeCashFlow",  cf_df),
    ]:
        s = df_.sort_values("period_end").dropna(subset=[col]) if not df_.empty else pd.DataFrame()
        # For FCF, if the last value is negative fall back to the most recent positive year
        if col == "FreeCashFlow" and len(s) >= 1 and _safe(s.iloc[-1][col]) is not None and s.iloc[-1][col] <= 0:
            s_pos = s[s[col] > 0]
            s = s_pos if len(s_pos) >= 2 else s
        if len(s) >= 2:
            first = s.iloc[0]
            last  = s.iloc[-1]
            years = (pd.to_datetime(last["period_end"]) - pd.to_datetime(first["period_end"])).days / 365.25
            result[key]              = _cagr(_safe(first[col]), _safe(last[col]), years)
            result[key + "_n_years"] = round(years)
        else:
            result[key]              = None
            result[key + "_n_years"] = None

    # ── Additional summary metrics ─────────────────────────────────────────────
    latest_income  = income_df.sort_values("period_end").iloc[-1]
    latest_bs_row  = bs_df.sort_values("period_end").iloc[-1] if not bs_df.empty else None

    def _ttm_or_annual(ttm_dict, key, annual_row):
        v = _safe(ttm_dict.get(key)) if ttm_dict else None
        return v if v is not None else (_safe(annual_row.get(key)) if annual_row is not None else None)

    ttm_inc = ttm["income"] if ttm else {}
    ttm_bs  = ttm["balance_sheet"] if ttm else {}

    op_income  = _ttm_or_annual(ttm_inc, "OperatingIncome", latest_income)
    net_income = _ttm_or_annual(ttm_inc, "NetIncome",       latest_income)
    ebitda_val = _ttm_or_annual(ttm_inc, "EBITDA",          latest_income)
    int_exp    = _ttm_or_annual(ttm_inc, "InterestExpense",  latest_income)
    tax_exp    = _ttm_or_annual(ttm_inc, "TaxExpense",       latest_income)
    pretax     = _ttm_or_annual(ttm_inc, "PreTaxIncome",     latest_income)

    equity       = _ttm_or_annual(ttm_bs, "StockholdersEquity", latest_bs_row)
    total_assets = _ttm_or_annual(ttm_bs, "TotalAssets",        latest_bs_row)
    net_debt_val = _ttm_or_annual(ttm_bs, "NetDebt",            latest_bs_row)

    # EV/EBITDA
    result["ev_to_ebitda"] = (ev_computed / ebitda_val) if (ev_computed and ebitda_val and ebitda_val > 0) else None

    # Net Debt / EBITDA
    result["net_debt_to_ebitda"] = (net_debt_val / ebitda_val) if (net_debt_val is not None and ebitda_val and ebitda_val != 0) else None

    # Interest Coverage (EBIT / Interest Expense)
    result["interest_coverage"] = (op_income / abs(int_exp)) if (op_income is not None and int_exp and int_exp != 0) else None

    # Avg ROIC, ROE, ROA — computed per year then averaged
    if not income_df.empty and not bs_df.empty:
        def _yr(df):
            d = df.copy()
            d["_y"] = pd.to_datetime(d["period_end"]).dt.year
            return d.sort_values("period_end").drop_duplicates("_y", keep="last").set_index("_y")

        inc_y = _yr(income_df)
        bs_y  = _yr(bs_df)
        shared = inc_y.index.intersection(bs_y.index)

        roic_vals, roe_vals, roa_vals = [], [], []
        for yr in shared:
            i_row = inc_y.loc[yr]
            b_row = bs_y.loc[yr]
            ni    = _safe(i_row.get("NetIncome"))
            oi    = _safe(i_row.get("OperatingIncome"))
            tx    = _safe(i_row.get("TaxExpense"))
            pt    = _safe(i_row.get("PreTaxIncome"))
            eq    = _safe(b_row.get("StockholdersEquity"))
            ta    = _safe(b_row.get("TotalAssets"))
            nd    = _safe(b_row.get("NetDebt"))
            if oi is not None and eq is not None and nd is not None:
                tr = max(0.0, min(0.5, tx / pt)) if (tx is not None and pt and pt > 0) else 0.21
                ic = eq + (nd or 0)
                if ic and ic != 0:
                    roic_vals.append(oi * (1 - tr) / ic * 100)
            if ni is not None and eq and eq != 0:
                roe_vals.append(ni / eq * 100)
            if ni is not None and ta and ta != 0:
                roa_vals.append(ni / ta * 100)

        result["avg_roic"]       = float(np.mean(roic_vals)) if roic_vals else None
        result["avg_roe"]        = float(np.mean(roe_vals))  if roe_vals  else None
        result["avg_roa"]        = float(np.mean(roa_vals))  if roa_vals  else None
        result["returns_n_years"] = int(len(shared))
    else:
        result["avg_roic"] = result["avg_roe"] = result["avg_roa"] = None
        result["returns_n_years"] = None

    return result


# ── Annual valuation metrics ──────────────────────────────────────────────────

def compute_annual_metrics(income_df, bs_df, cf_df, ttm, ticker):
    def with_year(df):
        d = df.copy()
        d["_year"] = pd.to_datetime(d["period_end"]).dt.year
        return d

    inc_cols = ["_year", "period_end", "Revenue", "DilutedShares", "OperatingIncome",
                "NetIncome", "EBITDA", "InterestExpense", "TaxExpense", "PreTaxIncome"]
    inc = with_year(income_df)[[c for c in inc_cols if c in with_year(income_df).columns or c in ["_year", "period_end"]]]
    # Ensure all expected income cols present
    for c in inc_cols:
        if c not in inc.columns:
            inc[c] = float("nan")

    bs_cols = ["_year", "Cash", "CurrentDebt", "LongTermDebt", "TotalDebt",
               "OperatingLeaseLiabilities",
               "CurrentAssets", "TotalLiabilities", "TotalAssets", "StockholdersEquity", "NetDebt"]
    if not bs_df.empty:
        bs = with_year(bs_df)
        for c in bs_cols:
            if c not in bs.columns:
                bs[c] = float("nan")
        bs = bs[[c for c in bs_cols if c in bs.columns]]
    else:
        bs = pd.DataFrame(columns=bs_cols)

    cf_cols = ["_year", "FreeCashFlow", "CapEx"]
    cf = with_year(cf_df)
    for c in cf_cols:
        if c not in cf.columns:
            cf[c] = float("nan")
    cf = cf[[c for c in cf_cols if c in cf.columns]]

    merged = inc.merge(bs, on="_year", how="left").merge(cf, on="_year", how="left")

    try:
        hist = yf.Ticker(ticker).history(
            start=(pd.to_datetime(merged["period_end"]).min() - pd.DateOffset(days=10)).strftime("%Y-%m-%d"),
            end=(pd.to_datetime(merged["period_end"]).max() + pd.DateOffset(days=10)).strftime("%Y-%m-%d"),
        )
        hist.index = hist.index.tz_convert(None)

        def price_near(date_str):
            dt = pd.to_datetime(date_str)
            diffs = np.abs((hist.index - dt).total_seconds())
            return float(hist.iloc[diffs.argmin()]["Close"]) if len(diffs) > 0 else None

        merged["_price"] = merged["period_end"].apply(price_near)
    except Exception:
        merged["_price"] = None

    merged["MarketCap"]  = merged["DilutedShares"] * merged["_price"]
    merged["EV"]         = merged["MarketCap"] + merged["TotalDebt"].fillna(0) + merged["OperatingLeaseLiabilities"].fillna(0) - merged["Cash"].fillna(0)
    merged["EVToSales"]  = merged["EV"] / merged["Revenue"]
    merged["EVToEBITDA"] = merged["EV"] / merged["EBITDA"]
    merged["FCFToEV"]    = merged["FreeCashFlow"] / merged["EV"] * 100
    merged["FCFToMarketCap"]             = merged["FreeCashFlow"] / merged["MarketCap"] * 100
    merged["NetDebtToEBITDA"]            = merged["NetDebt"] / merged["EBITDA"]
    merged["InterestCoverage"]           = merged["OperatingIncome"] / merged["InterestExpense"].abs()
    merged["CurrentAssetsToLiabilities"] = merged["CurrentAssets"] / merged["TotalLiabilities"]
    merged["FCFPerShare"]                = merged["FreeCashFlow"] / merged["DilutedShares"]

    _tax_rate = (merged["TaxExpense"] / merged["PreTaxIncome"]).clip(0, 0.5)
    _nopat    = merged["OperatingIncome"] * (1 - _tax_rate.fillna(0.21))
    _inv_cap  = merged["StockholdersEquity"] + merged["TotalDebt"].fillna(0) - merged["Cash"].fillna(0)
    merged["ROIC"] = _nopat / _inv_cap * 100
    merged["ROE"]  = merged["NetIncome"] / merged["StockholdersEquity"] * 100
    merged["ROA"]  = merged["NetIncome"] / merged["TotalAssets"] * 100

    keep_cols = ["period_end", "MarketCap", "EV", "EVToSales", "EVToEBITDA",
                 "FCFToEV", "FCFToMarketCap", "NetDebtToEBITDA", "InterestCoverage",
                 "CurrentAssetsToLiabilities", "ROIC", "ROE", "ROA", "FCFPerShare"]
    result = (merged[keep_cols]
              .copy()
              .dropna(subset=["period_end"])
              .sort_values("period_end"))
    result["period_end"] = result["period_end"].astype(str)

    # Prepend TTM row if available
    if ttm:
        try:
            info       = yf.Ticker(ticker).info
            market_cap = info.get("marketCap") or None
        except Exception:
            market_cap = None

        ttm_inc = ttm["income"]
        ttm_bs  = ttm["balance_sheet"]
        ttm_cf  = ttm["cash_flow"]

        ttm_rev      = _safe(ttm_inc.get("Revenue"))
        ttm_ebitda   = _safe(ttm_inc.get("EBITDA"))
        ttm_opinc    = _safe(ttm_inc.get("OperatingIncome"))
        ttm_netinc   = _safe(ttm_inc.get("NetIncome"))
        ttm_int_exp  = _safe(ttm_inc.get("InterestExpense"))
        ttm_tax      = _safe(ttm_inc.get("TaxExpense"))
        ttm_pretax   = _safe(ttm_inc.get("PreTaxIncome"))
        ttm_shares   = _safe(ttm_inc.get("DilutedShares"))
        ttm_ca       = _safe(ttm_bs.get("CurrentAssets"))
        ttm_tl       = _safe(ttm_bs.get("TotalLiabilities"))
        ttm_ta       = _safe(ttm_bs.get("TotalAssets"))
        ttm_equity   = _safe(ttm_bs.get("StockholdersEquity"))
        ttm_fcf      = _safe(ttm_cf.get("FreeCashFlow"))
        ttm_ltdebt   = _safe(ttm_bs.get("LongTermDebt")) or 0
        ttm_stdebt   = _safe(ttm_bs.get("CurrentDebt")) or 0
        ttm_totdebt  = ttm_ltdebt + ttm_stdebt
        ttm_ol       = _safe(ttm_bs.get("OperatingLeaseLiabilities")) or 0
        ttm_cash     = _safe(ttm_bs.get("Cash")) or 0
        ttm_ev       = (market_cap + ttm_totdebt + ttm_ol - ttm_cash) if market_cap else None
        ttm_netdebt  = ttm_totdebt - ttm_cash

        # ROIC for TTM
        if ttm_opinc is not None and ttm_equity is not None:
            _tr = (ttm_tax / ttm_pretax) if (ttm_tax is not None and ttm_pretax and ttm_pretax > 0) else 0.21
            _tr = max(0.0, min(0.5, _tr))
            _nopat_ttm = ttm_opinc * (1 - _tr)
            _ic_ttm    = ttm_equity + ttm_totdebt - ttm_cash
            ttm_roic   = (_nopat_ttm / _ic_ttm * 100) if _ic_ttm and _ic_ttm != 0 else None
        else:
            ttm_roic = None

        ttm_row = {
            "period_end":                 ttm["period_label"],
            "MarketCap":                  market_cap,
            "EV":                         ttm_ev,
            "EVToSales":                  (ttm_ev / ttm_rev) if ttm_ev and ttm_rev else None,
            "EVToEBITDA":                 (ttm_ev / ttm_ebitda) if ttm_ev and ttm_ebitda and ttm_ebitda != 0 else None,
            "FCFToEV":                    (ttm_fcf / ttm_ev * 100) if ttm_fcf and ttm_ev else None,
            "FCFToMarketCap":             (ttm_fcf / market_cap * 100) if ttm_fcf and market_cap else None,
            "NetDebtToEBITDA":            (ttm_netdebt / ttm_ebitda) if ttm_ebitda and ttm_ebitda != 0 else None,
            "InterestCoverage":           (ttm_opinc / abs(ttm_int_exp)) if ttm_opinc is not None and ttm_int_exp and ttm_int_exp != 0 else None,
            "CurrentAssetsToLiabilities": (ttm_ca / ttm_tl) if ttm_ca and ttm_tl else None,
            "ROIC":                       ttm_roic,
            "ROE":                        (ttm_netinc / ttm_equity * 100) if ttm_netinc is not None and ttm_equity and ttm_equity != 0 else None,
            "ROA":                        (ttm_netinc / ttm_ta * 100) if ttm_netinc is not None and ttm_ta and ttm_ta != 0 else None,
            "FCFPerShare":                (ttm_fcf / ttm_shares) if ttm_fcf is not None and ttm_shares and ttm_shares != 0 else None,
        }
        result = pd.concat([pd.DataFrame([ttm_row]), result], ignore_index=True)

    return result


# ── Valuation context ─────────────────────────────────────────────────────────

def compute_valuation_context(annual_metrics_df: pd.DataFrame, summary: dict = None) -> list:
    """
    For each key valuation multiple, return current value vs full historical
    average and median so users can judge whether the stock is cheap/expensive
    relative to its own history.
    """
    df = annual_metrics_df.copy()

    # Separate TTM row (period_end is a label, not a date) from annual rows
    is_date = df["period_end"].str.match(r"^\d{4}")
    hist = df[is_date].copy()
    ttm_rows = df[~is_date]
    current_row = ttm_rows.iloc[0] if not ttm_rows.empty else (
        hist.sort_values("period_end").iloc[-1] if not hist.empty else None
    )

    # Real-time current multiples from summary (uses current market cap, not historical price)
    realtime = {}
    if summary:
        if summary.get("ev_to_ebitda") is not None:
            realtime["EVToEBITDA"] = summary["ev_to_ebitda"]
        if summary.get("ev_to_sales") is not None:
            realtime["EVToSales"] = summary["ev_to_sales"]

    # Only EV-based multiples where lower = cheaper
    METRICS = [
        ("EVToEBITDA", "EV / EBITDA", "ratio"),
        ("EVToSales",  "EV / Sales",  "ratio"),
    ]

    rows = []
    for key, label, fmt in METRICS:
        if key not in hist.columns:
            continue
        vals = pd.to_numeric(hist[key], errors="coerce").dropna()
        if len(vals) < 2:
            continue

        avg    = float(vals.mean())
        median = float(vals.median())
        lo     = float(vals.min())
        hi     = float(vals.max())

        curr = realtime.get(key) or (_safe(current_row[key]) if current_row is not None else None)
        if curr is None or median == 0 or curr == 0:
            vs_median = None
        else:
            # For ratio metrics lower = cheaper, so positive = cheap vs median
            vs_median = (median / curr - 1) * 100

        rows.append({
            "key":         key,
            "label":       label,
            "fmt":         fmt,
            "current":     curr,
            "hist_avg":    avg,
            "hist_median": median,
            "hist_min":    lo,
            "hist_max":    hi,
            "vs_median_pct": vs_median,
            "n_years":     int(len(vals)),
        })

    return rows


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ticker = input("Enter ticker symbol: ").strip().upper()
    if not ticker:
        raise ValueError("Ticker symbol cannot be empty.")
    print(f"Fetching financials for {ticker} from SEC EDGAR...")
    income_df, bs_df, cf_df, ttm = fetch_all_financials(ticker)
    income_df.to_csv(f"{ticker}_income.csv", index=False)
    bs_df.to_csv(f"{ticker}_balance_sheet.csv", index=False)
    cf_df.to_csv(f"{ticker}_cash_flow.csv", index=False)
    if ttm:
        print("TTM period:", ttm["period_label"])
    print(income_df.to_string(index=False))


if __name__ == "__main__":
    main()
