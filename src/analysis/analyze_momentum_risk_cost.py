from __future__ import annotations

import argparse
import math
import os
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv
from scipy import stats


ROOT = Path(__file__).resolve().parents[2]

REPORT_PATH = (
    ROOT / "reports" / "analysis" / "momentum_risk_cost_analysis.txt"
)
RISK_FREE_MONTHLY_PATH = (
    ROOT / "reports" / "analysis" / "momentum_risk_free_monthly.csv"
)
RISK_ADJUSTED_PATH = (
    ROOT / "reports" / "analysis" / "momentum_risk_adjusted_summary.csv"
)
CAPM_PATH = (
    ROOT / "reports" / "analysis" / "momentum_capm_summary.csv"
)
TRANSACTION_COST_PATH = (
    ROOT / "reports" / "analysis" / "momentum_transaction_cost_summary.csv"
)
WML_SENSITIVITY_PATH = (
    ROOT / "reports" / "analysis" / "momentum_wml_cost_borrow_sensitivity.csv"
)
FRED_CACHE_PATH = (
    ROOT / "data" / "external" / "fred_dgs1mo_daily_2020_2025.csv"
)

FRED_SERIES_ID = "DGS1MO"
FRED_SOURCE_NAME = (
    "Market Yield on U.S. Treasury Securities at 1-Month Constant "
    "Maturity, Quoted on an Investment Basis"
)
FRED_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv"
    "?id=DGS1MO&cosd=2020-12-01&coed=2025-12-31"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
SCRIPT_VERSION = "2026-08-24-v2-datetime-normalization"

EXPECTED_PANEL_ROWS = 767
EXPECTED_OBSERVED_MONTHS = 59
EXPECTED_FIRST_ANALYSIS_MONTH = 1
EXPECTED_LAST_ANALYSIS_MONTH = 59
EXPECTED_SERIES = {
    "D01", "D02", "D03", "D04", "D05",
    "D06", "D07", "D08", "D09", "D10",
    "WML", "SPY", "SP500",
}
EXPECTED_TURNOVER_ROWS = 590
EXPECTED_TURNOVER_MONTHS = 59

TRANSACTION_COST_BPS = (5, 10, 20)
WML_BORROW_FEE_BPS_ANNUAL = (0, 50, 100, 200)
HAC_LAG = 3
ALPHA = 0.05

# Risk-free convention:
# DGS1MO is observed at or before portfolio formation.  It is an annualized
# market yield in percent.  We convert it to a simple holding-period return
# over the actual calendar days in the one-month portfolio holding window.
DAYS_IN_YEAR = 365.0


def rule() -> str:
    return "=" * 118


def section(title: str) -> list[str]:
    return ["", rule(), title, rule()]


def pct(value: float | None, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return "N/A"
    return f"{float(value) * 100:.{digits}f}%"


def num(value: float | None, digits: int = 4) -> str:
    if value is None or not math.isfinite(float(value)):
        return "N/A"
    return f"{float(value):.{digits}f}"


def p_text(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "N/A"
    value = float(value)
    if value < 0.0001:
        return "<0.0001"
    return f"{value:.4f}"


def environment() -> tuple[str, str, str, str]:
    load_dotenv(ROOT / ".env")

    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )
    values = tuple(os.getenv(name) for name in names)

    missing = [
        name
        for name, value in zip(names, values)
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )

    return values  # type: ignore[return-value]


def odbc_escape(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def connect_with_retry(
    server: str,
    database: str,
    username: str,
    password: str,
):
    if ODBC_DRIVER not in pyodbc.drivers():
        raise RuntimeError(
            f"{ODBC_DRIVER} is not installed. "
            f"Available drivers: {pyodbc.drivers()}"
        )

    connection_string = (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={odbc_escape(database)};"
        f"UID={odbc_escape(username)};"
        f"PWD={odbc_escape(password)};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )

    maximum_attempts = 5
    wait_seconds = 15
    retryable_terms = (
        "08001",
        "08s01",
        "hyt00",
        "40613",
        "timeout",
        "not currently available",
        "unable to establish connection",
        "temporarily unavailable",
        "communication link failure",
        "10053",
    )

    for attempt in range(1, maximum_attempts + 1):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(
                f"ODBC connection established on attempt "
                f"{attempt} / {maximum_attempts}."
            )
            return connection
        except pyodbc.Error as error:
            retryable = any(
                term in str(error).lower()
                for term in retryable_terms
            )
            if not retryable or attempt == maximum_attempts:
                raise

            print(
                f"ODBC connection attempt {attempt} / "
                f"{maximum_attempts} failed. Retrying in "
                f"{wait_seconds} seconds."
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        "ODBC connection retry loop ended unexpectedly."
    )


def fetch_df(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


def download_fred_cache(refresh: bool) -> tuple[pd.DataFrame, str]:
    FRED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if FRED_CACHE_PATH.exists() and not refresh:
        frame = pd.read_csv(FRED_CACHE_PATH)
        source_mode = "EXISTING LOCAL CACHE"
    else:
        print("Downloading FRED DGS1MO risk-free-rate series...")
        request = urllib.request.Request(
            FRED_CSV_URL,
            headers={
                "User-Agent": (
                    "sp500-momentum-performance-analysis/1.0 "
                    "(academic research)"
                )
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            if FRED_CACHE_PATH.exists():
                frame = pd.read_csv(FRED_CACHE_PATH)
                source_mode = (
                    "LOCAL CACHE FALLBACK AFTER DOWNLOAD FAILURE"
                )
            else:
                raise RuntimeError(
                    "Unable to download FRED DGS1MO and no local "
                    "cache exists. Retry with internet access or "
                    f"place the FRED CSV at {FRED_CACHE_PATH}."
                ) from exc
        else:
            frame = pd.read_csv(BytesIO(raw))
            frame.to_csv(FRED_CACHE_PATH, index=False)
            source_mode = "DOWNLOADED AND CACHED"

    date_column = None
    for candidate in ("DATE", "observation_date", "date"):
        if candidate in frame.columns:
            date_column = candidate
            break

    if date_column is None or FRED_SERIES_ID not in frame.columns:
        raise RuntimeError(
            "Unexpected FRED CSV schema. Expected a date column and "
            f"{FRED_SERIES_ID}."
        )

    cleaned = frame[[date_column, FRED_SERIES_ID]].copy()
    cleaned.columns = ["rf_observation_date", "annual_yield_percent"]
    cleaned["rf_observation_date"] = pd.to_datetime(
        cleaned["rf_observation_date"],
        errors="raise",
    )
    cleaned["annual_yield_percent"] = pd.to_numeric(
        cleaned["annual_yield_percent"],
        errors="coerce",
    )
    cleaned = (
        cleaned.dropna(subset=["annual_yield_percent"])
        .sort_values("rf_observation_date")
        .drop_duplicates("rf_observation_date", keep="last")
        .reset_index(drop=True)
    )

    if cleaned.empty:
        raise RuntimeError(
            "FRED DGS1MO cache contains no usable observations."
        )

    return cleaned, source_mode


def build_risk_free_panel(
    formation: pd.DataFrame,
    fred: pd.DataFrame,
) -> pd.DataFrame:
    left = formation.sort_values(
        "ranking_month_end_date"
    ).copy()
    right = fred.sort_values(
        "rf_observation_date"
    ).copy()

    # pandas.merge_asof requires the two merge keys to use the exact same
    # datetime resolution.  pyodbc/pandas may materialize SQL dates as
    # datetime64[s] while the FRED CSV is parsed as datetime64[us] or [ns].
    # Normalize both explicitly to nanosecond resolution before matching.
    left["ranking_month_end_date"] = pd.to_datetime(
        left["ranking_month_end_date"],
        errors="raise",
    ).astype("datetime64[ns]")

    right["rf_observation_date"] = pd.to_datetime(
        right["rf_observation_date"],
        errors="raise",
    ).astype("datetime64[ns]")

    aligned = pd.merge_asof(
        left,
        right,
        left_on="ranking_month_end_date",
        right_on="rf_observation_date",
        direction="backward",
        allow_exact_matches=True,
    )

    if aligned["annual_yield_percent"].isna().any():
        missing = aligned[
            aligned["annual_yield_percent"].isna()
        ]["ranking_month_end_date"].dt.date.tolist()
        raise RuntimeError(
            "Missing ex-ante DGS1MO yield for ranking dates: "
            + ", ".join(map(str, missing))
        )

    aligned["rf_observation_age_days"] = (
        aligned["ranking_month_end_date"]
        - aligned["rf_observation_date"]
    ).dt.days

    if (aligned["rf_observation_age_days"] < 0).any():
        raise RuntimeError(
            "Risk-free alignment used a future observation."
        )

    if (aligned["rf_observation_age_days"] > 7).any():
        stale = aligned[
            aligned["rf_observation_age_days"] > 7
        ][
            [
                "ranking_month_end_date",
                "rf_observation_date",
                "rf_observation_age_days",
            ]
        ]
        raise RuntimeError(
            "Risk-free observation is more than seven calendar "
            "days older than ranking date:\n"
            + stale.to_string(index=False)
        )

    aligned["holding_days"] = (
        aligned["return_period_end_date"]
        - aligned["ranking_month_end_date"]
    ).dt.days

    if (aligned["holding_days"] <= 0).any():
        raise RuntimeError(
            "At least one holding period has nonpositive calendar days."
        )

    aligned["risk_free_return"] = (
        aligned["annual_yield_percent"] / 100.0
        * aligned["holding_days"]
        / DAYS_IN_YEAR
    )

    return aligned


def annualized_geometric_return(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if np.any(1.0 + values <= 0):
        return math.nan
    wealth = float(np.prod(1.0 + values))
    return wealth ** (12.0 / len(values)) - 1.0


def final_wealth(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if np.any(1.0 + values <= 0):
        return math.nan
    return float(np.prod(1.0 + values))


def annualized_sharpe(excess_returns: np.ndarray) -> float:
    values = np.asarray(excess_returns, dtype=float)
    sd = float(np.std(values, ddof=1))
    if sd <= 0:
        return math.nan
    return float(
        np.mean(values) / sd * math.sqrt(12.0)
    )


def newey_west_ols(
    y: np.ndarray,
    x: np.ndarray,
    lag: int = HAC_LAG,
) -> dict[str, float]:
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)

    if len(y) != len(x):
        raise ValueError("y and x lengths differ.")

    n = len(y)
    X = np.column_stack([np.ones(n), x])
    k = X.shape[1]

    xtx_inv = np.linalg.inv(X.T @ X)
    beta_hat = xtx_inv @ X.T @ y
    residual = y - X @ beta_hat

    meat = np.zeros((k, k), dtype=float)

    for t in range(n):
        xt = X[t][:, None]
        meat += (residual[t] ** 2) * (xt @ xt.T)

    max_lag = min(lag, n - 1)
    for ell in range(1, max_lag + 1):
        weight = 1.0 - ell / (max_lag + 1.0)
        gamma = np.zeros((k, k), dtype=float)

        for t in range(ell, n):
            xt = X[t][:, None]
            xlag = X[t - ell][:, None]
            gamma += (
                residual[t]
                * residual[t - ell]
                * (xt @ xlag.T)
            )

        meat += weight * (gamma + gamma.T)

    covariance = xtx_inv @ meat @ xtx_inv

    # Small-sample degrees-of-freedom scaling.
    covariance *= n / (n - k)

    se = np.sqrt(
        np.maximum(np.diag(covariance), 0.0)
    )

    alpha_monthly = float(beta_hat[0])
    beta_market = float(beta_hat[1])
    alpha_se = float(se[0])
    beta_se = float(se[1])

    alpha_z = (
        alpha_monthly / alpha_se
        if alpha_se > 0
        else math.nan
    )
    beta_z = (
        beta_market / beta_se
        if beta_se > 0
        else math.nan
    )

    alpha_p = (
        float(2.0 * stats.norm.sf(abs(alpha_z)))
        if math.isfinite(alpha_z)
        else math.nan
    )
    beta_p = (
        float(2.0 * stats.norm.sf(abs(beta_z)))
        if math.isfinite(beta_z)
        else math.nan
    )

    ss_res = float(np.sum(residual ** 2))
    centered = y - np.mean(y)
    ss_tot = float(np.sum(centered ** 2))
    r_squared = (
        1.0 - ss_res / ss_tot
        if ss_tot > 0
        else math.nan
    )

    return {
        "alpha_monthly": alpha_monthly,
        "alpha_annualized_arithmetic": alpha_monthly * 12.0,
        "beta": beta_market,
        "alpha_hac_se": alpha_se,
        "beta_hac_se": beta_se,
        "alpha_hac_z": alpha_z,
        "beta_hac_z": beta_z,
        "alpha_hac_p": alpha_p,
        "beta_hac_p": beta_p,
        "r_squared": r_squared,
        "observations": float(n),
    }


def build_turnover_schedule(
    turnover: pd.DataFrame,
    decile: int,
    performance_months: list[int],
) -> np.ndarray:
    # At analysis month 1 there is no prior portfolio.  For a live
    # implementation, initial formation is treated as 100% one-way turnover.
    mapping = {
        int(row.analysis_month_number): float(
            row.target_weight_one_way_turnover
        )
        for row in turnover[
            turnover["momentum_decile"] == decile
        ].itertuples(index=False)
    }

    values: list[float] = []

    for month in performance_months:
        if month == EXPECTED_FIRST_ANALYSIS_MONTH:
            values.append(1.0)
        else:
            if month not in mapping:
                raise RuntimeError(
                    f"Missing turnover for D{decile:02d}, "
                    f"analysis month {month}."
                )
            values.append(mapping[month])

    return np.asarray(values, dtype=float)


def long_only_net_returns(
    gross_returns: np.ndarray,
    turnover: np.ndarray,
    cost_bps: int,
) -> np.ndarray:
    rate = float(cost_bps) / 10_000.0
    trading_cost_fraction = rate * turnover

    if np.any(trading_cost_fraction >= 1.0):
        raise RuntimeError(
            "Transaction-cost assumption creates an invalid "
            "100%+ formation/rebalance cost."
        )

    # Cost is paid at formation/rebalance, then the remaining capital earns
    # the monthly gross portfolio return.
    return (
        (1.0 - trading_cost_fraction)
        * (1.0 + gross_returns)
        - 1.0
    )


def wml_cost_adjusted_returns(
    gross_wml: np.ndarray,
    long_turnover: np.ndarray,
    short_turnover: np.ndarray,
    holding_days: np.ndarray,
    trading_cost_bps: int,
    annual_borrow_fee_bps: int,
) -> np.ndarray:
    trade_rate = float(trading_cost_bps) / 10_000.0
    annual_borrow_rate = (
        float(annual_borrow_fee_bps) / 10_000.0
    )

    # WML is a zero-cost spread return normalized to $1 of long notional
    # and $1 of short notional. Trading costs therefore apply to both legs.
    trading_cost_return = trade_rate * (
        long_turnover + short_turnover
    )

    # Borrow-fee scenario applies to the $1 short notional. Adjusted-close
    # short returns already capture dividends paid by the short seller;
    # this term is only an additional borrow-fee sensitivity.
    borrow_cost_return = (
        annual_borrow_rate
        * holding_days
        / DAYS_IN_YEAR
    )

    return (
        gross_wml
        - trading_cost_return
        - borrow_cost_return
    )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    parser = argparse.ArgumentParser(
        description=(
            "Read-only risk-adjusted, CAPM, transaction-cost, "
            "and WML implementation analysis."
        )
    )
    parser.add_argument(
        "--refresh-risk-free",
        action="store_true",
        help=(
            "Redownload DGS1MO from FRED even if a local cache exists."
        ),
    )
    args = parser.parse_args()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        rule(),
        "S&P 500 MOMENTUM — RISK, CAPM, AND TRANSACTION-COST ANALYSIS",
        rule(),
        "Mode: READ-ONLY with respect to Azure SQL",
        "Analytical sample: corrected 2021-2025 momentum experiment",
        "Observable completed holding months: 59",
        "Risk-free proxy: FRED DGS1MO",
        (
            "Risk-free timing: latest available DGS1MO observation "
            "on or before each portfolio ranking date"
        ),
        (
            "Risk-free holding-period conversion: annualized yield / 100 "
            "x actual holding days / 365"
        ),
        f"CAPM inference: Newey-West/HAC, lag {HAC_LAG}",
        (
            "Long-only transaction-cost scenarios: "
            + ", ".join(f"{x} bps" for x in TRANSACTION_COST_BPS)
            + " per unit of one-way turnover"
        ),
        (
            "WML short-borrow sensitivity: "
            + ", ".join(
                f"{x} bps/year"
                for x in WML_BORROW_FEE_BPS_ANNUAL
            )
        ),
        "Database modifications performed: 0",
    ]

    connection = None

    try:
        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        connection.timeout = 600
        cursor = connection.cursor()

        print("Reading corrected 59-month return panel...")
        panel = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_start_date,
                ranking_month_end_date,
                return_period_end_date,
                series_code,
                series_name,
                series_type,
                momentum_decile,
                series_sort_order,
                monthly_return
            FROM analytics.v_momentum_monthly_return_panel
            ORDER BY analysis_month_number, series_sort_order;
            """,
        )

        turnover = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                momentum_decile,
                momentum_portfolio,
                target_weight_one_way_turnover,
                security_overlap_rate
            FROM analytics.v_momentum_decile_turnover
            ORDER BY analysis_month_number, momentum_decile;
            """,
        )

        panel["analysis_month_number"] = pd.to_numeric(
            panel["analysis_month_number"],
            errors="raise",
        ).astype(int)
        panel["ranking_month_end_date"] = pd.to_datetime(
            panel["ranking_month_end_date"],
            errors="raise",
        )
        panel["return_period_end_date"] = pd.to_datetime(
            panel["return_period_end_date"],
            errors="raise",
        )
        panel["monthly_return"] = pd.to_numeric(
            panel["monthly_return"],
            errors="raise",
        )

        turnover["analysis_month_number"] = pd.to_numeric(
            turnover["analysis_month_number"],
            errors="raise",
        ).astype(int)
        turnover["momentum_decile"] = pd.to_numeric(
            turnover["momentum_decile"],
            errors="raise",
        ).astype(int)
        turnover["target_weight_one_way_turnover"] = pd.to_numeric(
            turnover["target_weight_one_way_turnover"],
            errors="raise",
        )
        turnover["security_overlap_rate"] = pd.to_numeric(
            turnover["security_overlap_rate"],
            errors="raise",
        )

        lines += section("1. CORRECTED SOURCE CONTROLS")

        if len(panel) != EXPECTED_PANEL_ROWS:
            raise RuntimeError(
                f"Return panel contains {len(panel):,} rows; "
                f"expected {EXPECTED_PANEL_ROWS:,}."
            )

        months = sorted(
            panel["analysis_month_number"].unique().tolist()
        )
        expected_months = list(
            range(
                EXPECTED_FIRST_ANALYSIS_MONTH,
                EXPECTED_LAST_ANALYSIS_MONTH + 1,
            )
        )

        if months != expected_months:
            raise RuntimeError(
                f"Unexpected performance months: {months}"
            )

        actual_series = set(
            panel["series_code"].astype(str).str.strip()
        )
        if actual_series != EXPECTED_SERIES:
            raise RuntimeError(
                "Unexpected series population: "
                + ", ".join(sorted(actual_series))
            )

        if panel.duplicated(
            ["analysis_month_number", "series_code"]
        ).any():
            raise RuntimeError(
                "Duplicate month/series keys in return panel."
            )

        if len(turnover) != EXPECTED_TURNOVER_ROWS:
            raise RuntimeError(
                f"Turnover contains {len(turnover):,} rows; "
                f"expected {EXPECTED_TURNOVER_ROWS:,}."
            )

        if turnover["analysis_month_number"].nunique() != (
            EXPECTED_TURNOVER_MONTHS
        ):
            raise RuntimeError(
                "Turnover month count is not 59."
            )

        lines += [
            "PASS: Corrected monthly return panel contains 767 rows.",
            "PASS: Exactly 59 completed holding months are present.",
            "PASS: All 13 analytical series are present.",
            "PASS: Month/series keys are unique.",
            "PASS: Turnover layer contains 590 month/decile rows.",
            "PASS: Azure SQL is queried read-only.",
        ]

        formation = (
            panel[
                panel["series_code"] == "SPY"
            ][
                [
                    "analysis_month_number",
                    "ranking_month_end_date",
                    "return_period_end_date",
                ]
            ]
            .sort_values("analysis_month_number")
            .reset_index(drop=True)
        )

        fred, fred_mode = download_fred_cache(
            args.refresh_risk_free
        )
        rf_panel = build_risk_free_panel(
            formation,
            fred,
        )

        RISK_FREE_MONTHLY_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        rf_panel.to_csv(
            RISK_FREE_MONTHLY_PATH,
            index=False,
        )

        lines += section("2. RISK-FREE-RATE METHODOLOGY AND CONTROLS")
        lines += [
            f"Series: {FRED_SERIES_ID}",
            f"Name: {FRED_SOURCE_NAME}",
            "Source: Federal Reserve Board H.15 via FRED",
            f"Cache mode: {fred_mode}",
            f"Cached file: {FRED_CACHE_PATH.relative_to(ROOT)}",
            f"Monthly alignment rows: {len(rf_panel)}",
            (
                "Earliest aligned ranking date: "
                f"{rf_panel['ranking_month_end_date'].min().date()}"
            ),
            (
                "Latest aligned ranking date: "
                f"{rf_panel['ranking_month_end_date'].max().date()}"
            ),
            (
                "DGS1MO annual-yield range used: "
                f"{rf_panel['annual_yield_percent'].min():.3f}% "
                "to "
                f"{rf_panel['annual_yield_percent'].max():.3f}%"
            ),
            (
                "Risk-free holding-return range: "
                f"{pct(float(rf_panel['risk_free_return'].min()))} "
                "to "
                f"{pct(float(rf_panel['risk_free_return'].max()))}"
            ),
            (
                "Maximum FRED observation age at formation: "
                f"{int(rf_panel['rf_observation_age_days'].max())} days"
            ),
            "PASS: Every risk-free observation date is on or before the ranking date.",
            "PASS: All 59 holding periods have an ex-ante DGS1MO proxy.",
        ]

        # Join risk-free data to every analytical series.
        enriched = panel.merge(
            rf_panel[
                [
                    "analysis_month_number",
                    "annual_yield_percent",
                    "risk_free_return",
                    "holding_days",
                ]
            ],
            on="analysis_month_number",
            how="left",
            validate="many_to_one",
        )

        if enriched["risk_free_return"].isna().any():
            raise RuntimeError(
                "Risk-free merge produced null values."
            )

        # -----------------------------------------------------------------
        # Sharpe ratios for long-only / investable series.
        # -----------------------------------------------------------------
        long_only_codes = [
            "D01", "D02", "D03", "D04", "D05",
            "D06", "D07", "D08", "D09", "D10",
            "SPY", "SP500",
        ]

        risk_rows: list[dict[str, Any]] = []

        for code in long_only_codes:
            group = (
                enriched[
                    enriched["series_code"] == code
                ]
                .sort_values("analysis_month_number")
                .copy()
            )

            gross = group[
                "monthly_return"
            ].to_numpy(dtype=float)
            rf = group[
                "risk_free_return"
            ].to_numpy(dtype=float)
            excess = gross - rf

            risk_rows.append(
                {
                    "series_code": code,
                    "series_name": str(
                        group["series_name"].iloc[0]
                    ),
                    "observations": len(group),
                    "gross_annualized_return": (
                        annualized_geometric_return(gross)
                    ),
                    "annualized_volatility": (
                        float(
                            np.std(
                                gross,
                                ddof=1,
                            )
                        )
                        * math.sqrt(12.0)
                    ),
                    "mean_monthly_excess_return": float(
                        np.mean(excess)
                    ),
                    "annualized_arithmetic_excess_return": (
                        float(np.mean(excess)) * 12.0
                    ),
                    "annualized_sharpe": annualized_sharpe(
                        excess
                    ),
                }
            )

        risk_summary = pd.DataFrame(risk_rows)
        risk_summary.to_csv(
            RISK_ADJUSTED_PATH,
            index=False,
        )

        lines += section("3. RISK-ADJUSTED PERFORMANCE — SHARPE")

        for code in ["D01", "D03", "D10", "SPY", "SP500"]:
            row = risk_summary[
                risk_summary["series_code"] == code
            ].iloc[0]
            lines.append(
                f"{code:<5} | "
                f"Ann Return {pct(row['gross_annualized_return'])} | "
                f"Ann Vol {pct(row['annualized_volatility'])} | "
                f"Ann Excess {pct(row['annualized_arithmetic_excess_return'])} | "
                f"Sharpe {num(row['annualized_sharpe'], 3)}"
            )

        d10_sharpe = float(
            risk_summary.loc[
                risk_summary["series_code"] == "D10",
                "annualized_sharpe",
            ].iloc[0]
        )
        spy_sharpe = float(
            risk_summary.loc[
                risk_summary["series_code"] == "SPY",
                "annualized_sharpe",
            ].iloc[0]
        )

        lines += [
            "",
            f"D10 annualized Sharpe: {num(d10_sharpe, 3)}",
            f"SPY annualized Sharpe: {num(spy_sharpe, 3)}",
            (
                "D10 Sharpe minus SPY Sharpe: "
                f"{num(d10_sharpe - spy_sharpe, 3)}"
            ),
            (
                "Interpretation flag: "
                + (
                    "D10 has the higher sample Sharpe."
                    if d10_sharpe > spy_sharpe
                    else "SPY has the higher sample Sharpe."
                )
            ),
        ]

        # -----------------------------------------------------------------
        # CAPM / market-model regressions.
        # -----------------------------------------------------------------
        spy_group = (
            enriched[
                enriched["series_code"] == "SPY"
            ]
            .sort_values("analysis_month_number")
            .copy()
        )
        spy_excess = (
            spy_group["monthly_return"].to_numpy(dtype=float)
            - spy_group["risk_free_return"].to_numpy(dtype=float)
        )

        capm_rows: list[dict[str, Any]] = []

        for code in [
            "D01", "D02", "D03", "D04", "D05",
            "D06", "D07", "D08", "D09", "D10",
            "WML", "SP500",
        ]:
            group = (
                enriched[
                    enriched["series_code"] == code
                ]
                .sort_values("analysis_month_number")
                .copy()
            )

            returns = group[
                "monthly_return"
            ].to_numpy(dtype=float)
            rf = group[
                "risk_free_return"
            ].to_numpy(dtype=float)

            # Long-only portfolios use excess returns.  WML is already a
            # zero-cost long-short spread, so subtracting RF again would be
            # conceptually inappropriate.
            if code == "WML":
                dependent = returns
                dependent_convention = (
                    "zero-cost spread return"
                )
            else:
                dependent = returns - rf
                dependent_convention = (
                    "portfolio return minus risk-free"
                )

            result = newey_west_ols(
                dependent,
                spy_excess,
                lag=HAC_LAG,
            )

            capm_rows.append(
                {
                    "series_code": code,
                    "series_name": str(
                        group["series_name"].iloc[0]
                    ),
                    "dependent_return_convention": (
                        dependent_convention
                    ),
                    **result,
                }
            )

        capm_summary = pd.DataFrame(capm_rows)
        capm_summary.to_csv(
            CAPM_PATH,
            index=False,
        )

        lines += section("4. CAPM / MARKET REGRESSION WITH HAC INFERENCE")
        lines += [
            (
                "Long-only equation: (R_portfolio - R_f) = "
                "alpha + beta * (R_SPY - R_f) + error"
            ),
            (
                "WML equation: R_WML = alpha + beta * "
                "(R_SPY - R_f) + error"
            ),
            f"HAC lag: {HAC_LAG}",
            "",
        ]

        for code in ["D01", "D03", "D10", "WML", "SP500"]:
            row = capm_summary[
                capm_summary["series_code"] == code
            ].iloc[0]
            lines.append(
                f"{code:<5} | "
                f"Alpha/mo {pct(row['alpha_monthly'])} | "
                f"Alpha/yr {pct(row['alpha_annualized_arithmetic'])} | "
                f"Alpha p {p_text(row['alpha_hac_p'])} | "
                f"Beta {num(row['beta'], 3)} | "
                f"Beta p {p_text(row['beta_hac_p'])} | "
                f"R2 {num(row['r_squared'], 3)}"
            )

        d10_capm = capm_summary[
            capm_summary["series_code"] == "D10"
        ].iloc[0]
        wml_capm = capm_summary[
            capm_summary["series_code"] == "WML"
        ].iloc[0]

        lines += [
            "",
            (
                "D10 alpha significance at 5%: "
                + (
                    "YES"
                    if float(d10_capm["alpha_hac_p"]) < ALPHA
                    else "NO"
                )
            ),
            (
                "WML alpha significance at 5%: "
                + (
                    "YES"
                    if float(wml_capm["alpha_hac_p"]) < ALPHA
                    else "NO"
                )
            ),
        ]

        # -----------------------------------------------------------------
        # Transaction-cost sensitivity.
        # -----------------------------------------------------------------
        performance_months = expected_months

        turnover_schedules = {
            decile: build_turnover_schedule(
                turnover,
                decile,
                performance_months,
            )
            for decile in range(1, 11)
        }

        transaction_rows: list[dict[str, Any]] = []

        for decile in range(1, 11):
            code = f"D{decile:02d}"
            group = (
                enriched[
                    enriched["series_code"] == code
                ]
                .sort_values("analysis_month_number")
            )
            gross = group[
                "monthly_return"
            ].to_numpy(dtype=float)
            schedule = turnover_schedules[decile]

            gross_ann = annualized_geometric_return(gross)
            gross_wealth = final_wealth(gross)

            for cost_bps in TRANSACTION_COST_BPS:
                net = long_only_net_returns(
                    gross,
                    schedule,
                    cost_bps,
                )
                net_ann = annualized_geometric_return(net)
                net_wealth = final_wealth(net)

                transaction_rows.append(
                    {
                        "series_code": code,
                        "momentum_decile": decile,
                        "transaction_cost_bps": cost_bps,
                        "initial_formation_turnover": 1.0,
                        "mean_monthly_turnover_including_initial": (
                            float(np.mean(schedule))
                        ),
                        "gross_final_wealth": gross_wealth,
                        "net_final_wealth": net_wealth,
                        "gross_annualized_return": gross_ann,
                        "net_annualized_return": net_ann,
                        "annualized_return_drag": (
                            gross_ann - net_ann
                        ),
                    }
                )

        transaction_summary = pd.DataFrame(
            transaction_rows
        )
        transaction_summary.to_csv(
            TRANSACTION_COST_PATH,
            index=False,
        )

        lines += section("5. LONG-ONLY TRANSACTION-COST SENSITIVITY")
        lines += [
            (
                "Convention: analysis month 1 initial portfolio "
                "formation = 100% one-way turnover."
            ),
            (
                "Months 2-59 use the validated target-weight "
                "one-way turnover for the ranking portfolio."
            ),
            (
                "SPY is shown gross as the benchmark; no artificial "
                "monthly SPY turnover is imposed."
            ),
            "",
            "D10:",
        ]

        for cost_bps in TRANSACTION_COST_BPS:
            row = transaction_summary[
                (transaction_summary["series_code"] == "D10")
                & (
                    transaction_summary[
                        "transaction_cost_bps"
                    ]
                    == cost_bps
                )
            ].iloc[0]
            lines.append(
                f"  {cost_bps:>2} bps | "
                f"Net wealth {row['net_final_wealth']:.4f} | "
                f"Net ann return {pct(row['net_annualized_return'])} | "
                f"Ann return drag {pct(row['annualized_return_drag'])}"
            )

        lines += ["", "D01:"]
        for cost_bps in TRANSACTION_COST_BPS:
            row = transaction_summary[
                (transaction_summary["series_code"] == "D01")
                & (
                    transaction_summary[
                        "transaction_cost_bps"
                    ]
                    == cost_bps
                )
            ].iloc[0]
            lines.append(
                f"  {cost_bps:>2} bps | "
                f"Net wealth {row['net_final_wealth']:.4f} | "
                f"Net ann return {pct(row['net_annualized_return'])} | "
                f"Ann return drag {pct(row['annualized_return_drag'])}"
            )

        # -----------------------------------------------------------------
        # WML trading + short-borrow sensitivity.
        # -----------------------------------------------------------------
        wml_group = (
            enriched[
                enriched["series_code"] == "WML"
            ]
            .sort_values("analysis_month_number")
            .copy()
        )
        gross_wml = wml_group[
            "monthly_return"
        ].to_numpy(dtype=float)
        holding_days = wml_group[
            "holding_days"
        ].to_numpy(dtype=float)

        long_turnover = turnover_schedules[10]
        short_turnover = turnover_schedules[1]

        wml_rows: list[dict[str, Any]] = []

        for trading_bps in TRANSACTION_COST_BPS:
            for borrow_bps in WML_BORROW_FEE_BPS_ANNUAL:
                net_wml = wml_cost_adjusted_returns(
                    gross_wml,
                    long_turnover,
                    short_turnover,
                    holding_days,
                    trading_bps,
                    borrow_bps,
                )

                wml_rows.append(
                    {
                        "transaction_cost_bps_per_turnover": (
                            trading_bps
                        ),
                        "annual_short_borrow_fee_bps": (
                            borrow_bps
                        ),
                        "gross_final_wealth_index": final_wealth(
                            gross_wml
                        ),
                        "net_final_wealth_index": final_wealth(
                            net_wml
                        ),
                        "gross_annualized_return": (
                            annualized_geometric_return(
                                gross_wml
                            )
                        ),
                        "net_annualized_return": (
                            annualized_geometric_return(
                                net_wml
                            )
                        ),
                        "mean_monthly_total_leg_turnover": (
                            float(
                                np.mean(
                                    long_turnover
                                    + short_turnover
                                )
                            )
                        ),
                    }
                )

        wml_sensitivity = pd.DataFrame(wml_rows)
        wml_sensitivity.to_csv(
            WML_SENSITIVITY_PATH,
            index=False,
        )

        lines += section("6. WML IMPLEMENTATION / SHORT-LEG SENSITIVITY")
        lines += [
            (
                "WML is analyzed separately because it is a "
                "zero-cost long D10 / short D01 spread."
            ),
            (
                "Adjusted-close returns already include distributions, "
                "so the short leg's negative total return captures the "
                "economic effect of dividends paid by the short seller."
            ),
            (
                "Additional modeled implementation frictions: trading "
                "costs on both legs plus an illustrative annual stock-"
                "borrow fee on the short notional."
            ),
            (
                "Not modeled: security-specific borrow availability, "
                "hard-to-borrow spikes, margin requirements, short "
                "rebates, financing spreads, taxes, or market impact."
            ),
            "",
        ]

        for trading_bps in TRANSACTION_COST_BPS:
            lines.append(
                f"Trading cost = {trading_bps} bps per turnover unit:"
            )
            subset = wml_sensitivity[
                wml_sensitivity[
                    "transaction_cost_bps_per_turnover"
                ]
                == trading_bps
            ]
            for row in subset.itertuples(index=False):
                lines.append(
                    f"  Borrow {int(row.annual_short_borrow_fee_bps):>3} "
                    f"bps/year | Net wealth "
                    f"{row.net_final_wealth_index:.4f} | "
                    f"Net ann return "
                    f"{pct(row.net_annualized_return)}"
                )

        # -----------------------------------------------------------------
        # Final integrated interpretation flags.
        # -----------------------------------------------------------------
        spy_gross_ann = float(
            risk_summary.loc[
                risk_summary["series_code"] == "SPY",
                "gross_annualized_return",
            ].iloc[0]
        )

        d10_net_5 = float(
            transaction_summary.loc[
                (transaction_summary["series_code"] == "D10")
                & (
                    transaction_summary[
                        "transaction_cost_bps"
                    ]
                    == 5
                ),
                "net_annualized_return",
            ].iloc[0]
        )
        d10_net_10 = float(
            transaction_summary.loc[
                (transaction_summary["series_code"] == "D10")
                & (
                    transaction_summary[
                        "transaction_cost_bps"
                    ]
                    == 10
                ),
                "net_annualized_return",
            ].iloc[0]
        )
        d10_net_20 = float(
            transaction_summary.loc[
                (transaction_summary["series_code"] == "D10")
                & (
                    transaction_summary[
                        "transaction_cost_bps"
                    ]
                    == 20
                ),
                "net_annualized_return",
            ].iloc[0]
        )

        lines += section("7. INTEGRATED DECISION CHECKPOINT")
        lines += [
            (
                "This section combines the corrected gross results, "
                "risk-free adjustment, market regression, and "
                "implementation-cost sensitivity."
            ),
            "",
            f"SPY gross annualized return: {pct(spy_gross_ann)}",
            f"D10 annualized Sharpe: {num(d10_sharpe, 3)}",
            f"SPY annualized Sharpe: {num(spy_sharpe, 3)}",
            (
                "D10 CAPM alpha (annualized arithmetic): "
                f"{pct(float(d10_capm['alpha_annualized_arithmetic']))}"
            ),
            (
                "D10 CAPM alpha HAC p-value: "
                f"{p_text(float(d10_capm['alpha_hac_p']))}"
            ),
            (
                "D10 CAPM beta: "
                f"{num(float(d10_capm['beta']), 3)}"
            ),
            (
                "WML CAPM alpha (annualized arithmetic): "
                f"{pct(float(wml_capm['alpha_annualized_arithmetic']))}"
            ),
            (
                "WML CAPM alpha HAC p-value: "
                f"{p_text(float(wml_capm['alpha_hac_p']))}"
            ),
            "",
            f"D10 net annualized return @ 5 bps:  {pct(d10_net_5)}",
            f"D10 net annualized return @ 10 bps: {pct(d10_net_10)}",
            f"D10 net annualized return @ 20 bps: {pct(d10_net_20)}",
            "",
            (
                "Risk-adjusted outcome: "
                + (
                    "D10 sample Sharpe exceeds SPY."
                    if d10_sharpe > spy_sharpe
                    else "D10 sample Sharpe does not exceed SPY."
                )
            ),
            (
                "Alpha outcome: "
                + (
                    "D10 alpha is statistically significant at 5%."
                    if float(d10_capm["alpha_hac_p"]) < ALPHA
                    else "D10 alpha is not statistically significant at 5%."
                )
            ),
            (
                "Implementation outcome: positive transaction costs "
                "can only reduce the already-observed gross return."
            ),
            (
                "WML implementation outcome: the reported trading/"
                "borrow scenarios remain sensitivity analyses rather "
                "than a claim about realized shorting costs."
            ),
        ]

        lines += section("8. INTERPRETATION BOUNDARIES")
        lines += [
            (
                "DGS1MO is a constant-maturity market-yield proxy, "
                "not a realized return from purchasing a specific bill."
            ),
            (
                "The monthly risk-free holding return uses an explicit "
                "simple day-count conversion for reproducibility."
            ),
            (
                "Sharpe ratios describe this 59-month sample and are "
                "not statistical proof of future risk-adjusted performance."
            ),
            (
                "CAPM alpha controls only for SPY market exposure; it "
                "does not control for size, value, profitability, "
                "investment, industry, or other factor exposures."
            ),
            (
                "Transaction costs are scenarios, not security-level "
                "historical execution estimates."
            ),
            (
                "WML borrow fees are illustrative scenarios and do not "
                "resolve historical borrow availability or margin financing."
            ),
            (
                "All inference remains exploratory/post-selection because "
                "the gross results were inspected before these tests."
            ),
        ]

        lines += section("9. FINAL CONTROL")
        lines += [
            "Azure SQL modifications performed: 0",
            "Validated source rows modified: 0",
            f"Risk-free monthly output: {RISK_FREE_MONTHLY_PATH.relative_to(ROOT)}",
            f"Risk-adjusted output: {RISK_ADJUSTED_PATH.relative_to(ROOT)}",
            f"CAPM output: {CAPM_PATH.relative_to(ROOT)}",
            f"Transaction-cost output: {TRANSACTION_COST_PATH.relative_to(ROOT)}",
            f"WML sensitivity output: {WML_SENSITIVITY_PATH.relative_to(ROOT)}",
            "",
            "MOMENTUM_RISK_COST_ANALYSIS_COMPLETE",
        ]

        risk_summary = risk_summary.sort_values(
            "series_code"
        ).reset_index(drop=True)
        capm_summary = capm_summary.sort_values(
            "series_code"
        ).reset_index(drop=True)

        cursor.close()

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    report_text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report_text,
        encoding="utf-8",
    )
    print(report_text, end="")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
