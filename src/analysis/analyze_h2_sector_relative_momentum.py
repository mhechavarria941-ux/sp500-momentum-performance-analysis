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

SCRIPT_VERSION = "2026-08-24-v2-h2-risk-free-datetime-normalization"

REPORT_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_sector_relative_momentum_analysis.txt"
)
PRIMARY_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_primary_inference.csv"
)
SECTOR_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_sector_inference.csv"
)
QUINTILE_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_quintile_monotonicity.csv"
)
RISK_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_risk_adjusted_summary.csv"
)
CAPM_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_capm_summary.csv"
)
TURNOVER_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_turnover_monthly.csv"
)
COST_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_cost_borrow_sensitivity.csv"
)
LOO_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_leave_one_sector_out.csv"
)
CONTRIBUTION_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_sector_contribution.csv"
)
RF_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_risk_free_monthly.csv"
)

FRED_CACHE_PATH = (
    ROOT
    / "data"
    / "external"
    / "fred_dgs1mo_daily_2020_2025.csv"
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

EXPECTED_MONTHS = 59
EXPECTED_WML_ROWS = 59
EXPECTED_SECTOR_EXTREME_ROWS = 1_298
EXPECTED_SECTOR_QUINTILE_ROWS = 3_245
EXPECTED_BENCHMARK_ROWS = 118
EXPECTED_H2_ASSIGNMENTS = 30_121

ALPHA = 0.05
HAC_LAG = 3
BOOTSTRAP_REPLICATIONS = 50_000
BOOTSTRAP_SEED = 20260824
DAYS_IN_YEAR = 365.0

TRANSACTION_COST_BPS = (5, 10, 20)
BORROW_BPS_ANNUAL = (0, 50, 100, 200)
BASE_CASE_TRADING_BPS = 10
BASE_CASE_BORROW_BPS = 100

CANONICAL_SECTORS = [
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
]


def rule() -> str:
    return "=" * 122


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

    for attempt in range(1, 6):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(
                f"ODBC connection established on attempt {attempt} / 5."
            )
            return connection
        except pyodbc.Error as error:
            retryable = any(
                term in str(error).lower()
                for term in retryable_terms
            )
            if not retryable or attempt == 5:
                raise
            print(
                f"ODBC connection attempt {attempt} / 5 failed. "
                "Retrying in 10 seconds."
            )
            time.sleep(10)

    raise RuntimeError("ODBC retry loop ended unexpectedly.")


def fetch_df(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    return pd.DataFrame.from_records(
        cursor.fetchall(),
        columns=columns,
    )


def download_fred_cache(
    refresh: bool,
) -> tuple[pd.DataFrame, str]:
    FRED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if FRED_CACHE_PATH.exists() and not refresh:
        frame = pd.read_csv(FRED_CACHE_PATH)
        source_mode = "EXISTING LOCAL CACHE"
    else:
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
                    "Unable to download DGS1MO and no local cache exists."
                ) from exc
        else:
            frame = pd.read_csv(BytesIO(raw))
            frame.to_csv(
                FRED_CACHE_PATH,
                index=False,
            )
            source_mode = "DOWNLOADED AND CACHED"

    date_column = next(
        (
            column
            for column in ("DATE", "observation_date", "date")
            if column in frame.columns
        ),
        None,
    )

    if date_column is None or FRED_SERIES_ID not in frame.columns:
        raise RuntimeError(
            "Unexpected FRED cache schema."
        )

    cleaned = frame[
        [date_column, FRED_SERIES_ID]
    ].copy()
    cleaned.columns = [
        "rf_observation_date",
        "annual_yield_percent",
    ]
    cleaned["rf_observation_date"] = pd.to_datetime(
        cleaned["rf_observation_date"],
        errors="raise",
    )
    cleaned["annual_yield_percent"] = pd.to_numeric(
        cleaned["annual_yield_percent"],
        errors="coerce",
    )
    cleaned = (
        cleaned
        .dropna(subset=["annual_yield_percent"])
        .sort_values("rf_observation_date")
        .drop_duplicates(
            "rf_observation_date",
            keep="last",
        )
        .reset_index(drop=True)
    )

    return cleaned, source_mode


def build_risk_free_panel(
    formation: pd.DataFrame,
    fred: pd.DataFrame,
) -> pd.DataFrame:
    left = formation.copy()
    right = fred.copy()

    # pandas 2.x/3.x can preserve different datetime resolutions from
    # different inputs (for example datetime64[s] from pyodbc and
    # datetime64[us] from CSV parsing). merge_asof requires the join
    # keys to have the exact same dtype, even when the timestamps are
    # otherwise identical. Normalize all risk-free alignment dates to
    # datetime64[ns] before sorting and joining.
    left["ranking_month_end_date"] = (
        pd.to_datetime(
            left["ranking_month_end_date"],
            errors="raise",
        )
        .astype("datetime64[ns]")
    )
    left["return_period_end_date"] = (
        pd.to_datetime(
            left["return_period_end_date"],
            errors="raise",
        )
        .astype("datetime64[ns]")
    )
    right["rf_observation_date"] = (
        pd.to_datetime(
            right["rf_observation_date"],
            errors="raise",
        )
        .astype("datetime64[ns]")
    )

    left = left.sort_values(
        "ranking_month_end_date"
    ).reset_index(drop=True)
    right = right.sort_values(
        "rf_observation_date"
    ).reset_index(drop=True)

    if (
        str(left["ranking_month_end_date"].dtype)
        != str(right["rf_observation_date"].dtype)
    ):
        raise RuntimeError(
            "Risk-free asof join datetime dtypes still differ after "
            "normalization: "
            f"{left['ranking_month_end_date'].dtype} vs "
            f"{right['rf_observation_date'].dtype}."
        )

    aligned = pd.merge_asof(
        left,
        right,
        left_on="ranking_month_end_date",
        right_on="rf_observation_date",
        direction="backward",
        allow_exact_matches=True,
    )

    if aligned["annual_yield_percent"].isna().any():
        raise RuntimeError(
            "At least one ranking month has no ex-ante DGS1MO value."
        )

    aligned["rf_observation_age_days"] = (
        aligned["ranking_month_end_date"]
        - aligned["rf_observation_date"]
    ).dt.days

    if (
        (aligned["rf_observation_age_days"] < 0).any()
        or (aligned["rf_observation_age_days"] > 7).any()
    ):
        raise RuntimeError(
            "DGS1MO ex-ante timing control failed."
        )

    aligned["holding_days"] = (
        aligned["return_period_end_date"]
        - aligned["ranking_month_end_date"]
    ).dt.days

    if (aligned["holding_days"] <= 0).any():
        raise RuntimeError(
            "Nonpositive holding-period length detected."
        )

    aligned["risk_free_return"] = (
        aligned["annual_yield_percent"]
        / 100.0
        * aligned["holding_days"]
        / DAYS_IN_YEAR
    )

    return aligned


def annualized_geometric_return(
    values: np.ndarray,
) -> float:
    x = np.asarray(values, dtype=float)
    if np.any(1.0 + x <= 0):
        return math.nan
    wealth = float(np.prod(1.0 + x))
    return wealth ** (12.0 / len(x)) - 1.0


def final_wealth(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    if np.any(1.0 + x <= 0):
        return math.nan
    return float(np.prod(1.0 + x))


def annualized_volatility(values: np.ndarray) -> float:
    return float(
        np.std(
            np.asarray(values, dtype=float),
            ddof=1,
        )
        * math.sqrt(12.0)
    )


def maximum_drawdown(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    wealth = np.cumprod(1.0 + x)
    peak = np.maximum.accumulate(wealth)
    drawdown = wealth / peak - 1.0
    return float(np.min(drawdown))


def annualized_sharpe(
    excess_returns: np.ndarray,
) -> float:
    x = np.asarray(excess_returns, dtype=float)
    sd = float(np.std(x, ddof=1))
    if sd <= 0:
        return math.nan
    return float(
        np.mean(x)
        / sd
        * math.sqrt(12.0)
    )


def one_sample_t(
    values: np.ndarray,
) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    n = len(x)
    mean = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    se = sd / math.sqrt(n)
    t_stat = mean / se if se > 0 else math.nan
    p_value = (
        float(
            2.0
            * stats.t.sf(
                abs(t_stat),
                df=n - 1,
            )
        )
        if math.isfinite(t_stat)
        else math.nan
    )
    critical = float(
        stats.t.ppf(
            0.975,
            df=n - 1,
        )
    )
    return {
        "n": float(n),
        "mean": mean,
        "sd": sd,
        "t_stat": t_stat,
        "t_p": p_value,
        "ci_low": mean - critical * se,
        "ci_high": mean + critical * se,
    }


def bootstrap_mean_ci(
    values: np.ndarray,
    seed: int,
) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    n = len(x)
    chunks: list[np.ndarray] = []
    remaining = BOOTSTRAP_REPLICATIONS

    while remaining > 0:
        current = min(5_000, remaining)
        idx = rng.integers(
            0,
            n,
            size=(current, n),
        )
        chunks.append(
            np.mean(
                x[idx],
                axis=1,
            )
        )
        remaining -= current

    means = np.concatenate(chunks)
    low, high = np.percentile(
        means,
        [2.5, 97.5],
    )
    return float(low), float(high)


def wilcoxon_test(
    values: np.ndarray,
) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)

    if np.allclose(x, 0.0):
        return 0.0, 1.0

    result = stats.wilcoxon(
        x,
        zero_method="wilcox",
        correction=False,
        alternative="two-sided",
        mode="auto",
    )
    return float(
        result.statistic
    ), float(
        result.pvalue
    )


def sign_test(
    values: np.ndarray,
) -> tuple[int, int, float]:
    x = np.asarray(values, dtype=float)
    positives = int(np.sum(x > 0))
    negatives = int(np.sum(x < 0))
    nonzero = positives + negatives

    if nonzero == 0:
        return positives, negatives, 1.0

    result = stats.binomtest(
        positives,
        n=nonzero,
        p=0.5,
        alternative="two-sided",
    )
    return (
        positives,
        negatives,
        float(result.pvalue),
    )


def newey_west_mean_test(
    values: np.ndarray,
    lag: int = HAC_LAG,
) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    n = len(x)
    mean = float(np.mean(x))
    residual = x - mean

    gamma0 = float(
        np.dot(
            residual,
            residual,
        )
        / n
    )
    long_run_variance = gamma0

    max_lag = min(
        lag,
        n - 1,
    )

    for k in range(
        1,
        max_lag + 1,
    ):
        gamma_k = float(
            np.dot(
                residual[k:],
                residual[:-k],
            )
            / n
        )
        weight = (
            1.0
            - k
            / (max_lag + 1.0)
        )
        long_run_variance += (
            2.0
            * weight
            * gamma_k
        )

    long_run_variance = max(
        long_run_variance,
        0.0,
    )
    se_mean = math.sqrt(
        long_run_variance
        / n
    )
    z_stat = (
        mean / se_mean
        if se_mean > 0
        else math.nan
    )
    p_value = (
        float(
            2.0
            * stats.norm.sf(
                abs(z_stat)
            )
        )
        if math.isfinite(z_stat)
        else math.nan
    )
    critical = float(
        stats.norm.ppf(0.975)
    )

    return {
        "mean": mean,
        "hac_se": se_mean,
        "hac_z": z_stat,
        "hac_p": p_value,
        "hac_ci_low": (
            mean
            - critical
            * se_mean
        ),
        "hac_ci_high": (
            mean
            + critical
            * se_mean
        ),
    }


def holm_adjust(
    p_values: dict[str, float],
) -> dict[str, float]:
    items = sorted(
        p_values.items(),
        key=lambda item: item[1],
    )
    m = len(items)
    adjusted: dict[str, float] = {}
    running_max = 0.0

    for rank, (
        name,
        p_value,
    ) in enumerate(
        items,
        start=1,
    ):
        candidate = min(
            1.0,
            (
                m - rank + 1
            )
            * float(p_value),
        )
        running_max = max(
            running_max,
            candidate,
        )
        adjusted[name] = running_max

    return adjusted


def newey_west_ols(
    y: np.ndarray,
    x: np.ndarray,
    lag: int = HAC_LAG,
) -> dict[str, float]:
    y = np.asarray(
        y,
        dtype=float,
    )
    x = np.asarray(
        x,
        dtype=float,
    )

    if len(y) != len(x):
        raise ValueError(
            "y and x lengths differ."
        )

    n = len(y)
    X = np.column_stack(
        [
            np.ones(n),
            x,
        ]
    )
    k = X.shape[1]

    xtx_inv = np.linalg.inv(
        X.T @ X
    )
    beta_hat = (
        xtx_inv
        @ X.T
        @ y
    )
    residual = (
        y
        - X
        @ beta_hat
    )

    meat = np.zeros(
        (k, k),
        dtype=float,
    )

    for t in range(n):
        xt = X[t][:, None]
        meat += (
            residual[t] ** 2
        ) * (
            xt @ xt.T
        )

    max_lag = min(
        lag,
        n - 1,
    )

    for ell in range(
        1,
        max_lag + 1,
    ):
        weight = (
            1.0
            - ell
            / (max_lag + 1.0)
        )
        gamma = np.zeros(
            (k, k),
            dtype=float,
        )

        for t in range(
            ell,
            n,
        ):
            xt = X[t][:, None]
            xlag = X[
                t - ell
            ][:, None]
            gamma += (
                residual[t]
                * residual[
                    t - ell
                ]
                * (
                    xt
                    @ xlag.T
                )
            )

        meat += (
            weight
            * (
                gamma
                + gamma.T
            )
        )

    covariance = (
        xtx_inv
        @ meat
        @ xtx_inv
    )

    covariance *= (
        n / (n - k)
    )

    se = np.sqrt(
        np.maximum(
            np.diag(covariance),
            0.0,
        )
    )

    alpha_monthly = float(
        beta_hat[0]
    )
    beta_market = float(
        beta_hat[1]
    )
    alpha_se = float(
        se[0]
    )
    beta_se = float(
        se[1]
    )

    alpha_z = (
        alpha_monthly
        / alpha_se
        if alpha_se > 0
        else math.nan
    )
    beta_z = (
        beta_market
        / beta_se
        if beta_se > 0
        else math.nan
    )

    alpha_p = (
        float(
            2.0
            * stats.norm.sf(
                abs(alpha_z)
            )
        )
        if math.isfinite(alpha_z)
        else math.nan
    )
    beta_p = (
        float(
            2.0
            * stats.norm.sf(
                abs(beta_z)
            )
        )
        if math.isfinite(beta_z)
        else math.nan
    )

    ss_res = float(
        np.sum(
            residual ** 2
        )
    )
    centered = (
        y
        - np.mean(y)
    )
    ss_tot = float(
        np.sum(
            centered ** 2
        )
    )

    r_squared = (
        1.0
        - ss_res
        / ss_tot
        if ss_tot > 0
        else math.nan
    )

    return {
        "alpha_monthly": alpha_monthly,
        "alpha_annualized_arithmetic": (
            alpha_monthly
            * 12.0
        ),
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


def compute_target_turnover(
    assignments: pd.DataFrame,
    portfolio_label: str,
) -> pd.DataFrame:
    subset = assignments[
        assignments[
            "sector_momentum_portfolio"
        ]
        == portfolio_label
    ][
        [
            "analysis_month_number",
            "security_key",
            "sector_neutral_leg_weight",
        ]
    ].copy()

    months = sorted(
        subset[
            "analysis_month_number"
        ].unique()
    )

    if months != list(
        range(1, 61)
    ):
        raise RuntimeError(
            f"{portfolio_label} target weights do not span months 1-60."
        )

    rows = []

    previous: dict[
        str,
        float,
    ] | None = None

    for month in months:
        current = {
            str(row.security_key): float(
                row.sector_neutral_leg_weight
            )
            for row in subset[
                subset[
                    "analysis_month_number"
                ]
                == month
            ].itertuples(
                index=False
            )
        }

        weight_sum = sum(
            current.values()
        )

        if not math.isclose(
            weight_sum,
            1.0,
            rel_tol=1e-10,
            abs_tol=1e-10,
        ):
            raise RuntimeError(
                f"{portfolio_label} month {month} weight sum = {weight_sum}."
            )

        if previous is None:
            turnover = math.nan
            overlap_count = math.nan
        else:
            keys = set(
                current
            ) | set(
                previous
            )
            turnover = (
                0.5
                * sum(
                    abs(
                        current.get(
                            key,
                            0.0,
                        )
                        - previous.get(
                            key,
                            0.0,
                        )
                    )
                    for key in keys
                )
            )
            overlap_count = len(
                set(current)
                & set(previous)
            )

        rows.append(
            {
                "analysis_month_number": month,
                "portfolio": portfolio_label,
                "security_count": len(current),
                "target_weight_sum": weight_sum,
                "target_weight_one_way_turnover": turnover,
                "security_overlap_count": overlap_count,
            }
        )

        previous = current

    return pd.DataFrame(rows)


def turnover_schedule_for_performance(
    turnover: pd.DataFrame,
    portfolio_label: str,
) -> np.ndarray:
    mapping = {
        int(row.analysis_month_number): float(
            row.target_weight_one_way_turnover
        )
        for row in turnover[
            turnover["portfolio"]
            == portfolio_label
        ].dropna(
            subset=[
                "target_weight_one_way_turnover"
            ]
        ).itertuples(
            index=False
        )
    }

    values = []

    for month in range(1, 60):
        if month == 1:
            values.append(1.0)
        else:
            if month not in mapping:
                raise RuntimeError(
                    f"Missing turnover for {portfolio_label}, month {month}."
                )
            values.append(
                mapping[month]
            )

    return np.asarray(
        values,
        dtype=float,
    )


def wml_cost_adjusted_returns(
    gross_wml: np.ndarray,
    winner_turnover: np.ndarray,
    loser_turnover: np.ndarray,
    trading_cost_bps: int,
    annual_borrow_fee_bps: int,
) -> np.ndarray:
    trade_rate = (
        float(trading_cost_bps)
        / 10_000.0
    )
    annual_borrow_rate = (
        float(annual_borrow_fee_bps)
        / 10_000.0
    )

    trading_cost_return = (
        trade_rate
        * (
            winner_turnover
            + loser_turnover
        )
    )

    # H2 preregistration explicitly freezes monthly borrow cost
    # as annual borrow bps divided by 12.
    borrow_cost_return = (
        annual_borrow_rate
        / 12.0
    )

    return (
        gross_wml
        - trading_cost_return
        - borrow_cost_return
    )


def main() -> None:
    print(
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}"
    )

    parser = argparse.ArgumentParser(
        description=(
            "Preregistered H2 sector-relative momentum analysis."
        )
    )
    parser.add_argument(
        "--refresh-risk-free",
        action="store_true",
        help=(
            "Redownload DGS1MO even when local cache exists."
        ),
    )
    args = parser.parse_args()

    for path in (
        REPORT_PATH,
        PRIMARY_PATH,
        SECTOR_PATH,
        QUINTILE_PATH,
        RISK_PATH,
        CAPM_PATH,
        TURNOVER_PATH,
        COST_PATH,
        LOO_PATH,
        CONTRIBUTION_PATH,
        RF_PATH,
    ):
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    connection = None

    lines = [
        rule(),
        "S&P 500 H2 — SECTOR-RELATIVE 12-1 MOMENTUM FINAL PREREGISTERED ANALYSIS",
        rule(),
        "Mode: READ-ONLY with respect to Azure SQL",
        "Analytical sample: 2021-2025",
        "Observable completed holding months: 59",
        "Primary outcome: equal-sector-weight Winner minus Loser",
        "Primary inference: two-sided HAC/Newey-West mean test, lag 3, alpha 0.05",
        f"Bootstrap replications: {BOOTSTRAP_REPLICATIONS:,}",
        "Risk-free proxy: FRED DGS1MO, latest observation on/before ranking date",
        "Risk-free conversion: annualized yield / 100 x actual holding days / 365",
        "Turnover: 0.5 * sum(abs(w_t - w_t-1)) on aggregate leg target weights",
        "Initial formation: 100% one-way turnover per leg",
        "Trading-cost grid: 5 / 10 / 20 bps per turnover unit on both legs",
        "Borrow grid: 0 / 50 / 100 / 200 bps annualized on Loser leg",
        "H2 borrow convention: annual borrow rate / 12 each month",
        "Base case: 10 bps trading + 100 bps annualized borrow",
        "Database modifications performed: 0",
    ]

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

        lines += section("1. VALIDATED SOURCE CONTROLS")

        wml = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                target_holding_end_date AS return_period_end_date,
                winner_forward_return_1m,
                loser_forward_return_1m,
                winner_minus_loser_forward_return_1m
            FROM analytics.v_h2_sector_neutral_wml_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number;
            """,
        )

        sector_extreme = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                target_holding_end_date AS return_period_end_date,
                gics_sector,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                equal_weight_forward_return_1m
            FROM analytics.v_h2_sector_extreme_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number, gics_sector, sector_momentum_quintile;
            """,
        )

        sector_quintile = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                gics_sector,
                sector_momentum_quintile,
                equal_weight_forward_return_1m
            FROM analytics.v_h2_sector_quintile_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number, gics_sector, sector_momentum_quintile;
            """,
        )

        assignments = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                security_key,
                gics_sector,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                sector_neutral_leg_weight
            FROM analytics.v_security_monthly_sector_momentum_portfolio
            WHERE sector_momentum_quintile IN (1, 5)
            ORDER BY analysis_month_number, gics_sector, sector_momentum_quintile, security_key;
            """,
        )

        benchmark = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                target_holding_end_date AS return_period_end_date,
                series_type,
                forward_return_1m
            FROM analytics.v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number, series_type;
            """,
        )

        if len(wml) != EXPECTED_WML_ROWS:
            raise RuntimeError(
                f"H2 complete W-L rows = {len(wml)}; expected 59."
            )
        if len(sector_extreme) != EXPECTED_SECTOR_EXTREME_ROWS:
            raise RuntimeError(
                "H2 complete sector extreme population mismatch."
            )
        if len(sector_quintile) != EXPECTED_SECTOR_QUINTILE_ROWS:
            raise RuntimeError(
                "H2 complete sector quintile population mismatch."
            )
        if len(benchmark) != EXPECTED_BENCHMARK_ROWS:
            raise RuntimeError(
                f"Complete benchmark rows = {len(benchmark)}; expected 118."
            )

        lines += [
            f"PASS: Aggregate H2 W-L complete rows = {len(wml):,}.",
            f"PASS: Complete Winner/Loser sector rows = {len(sector_extreme):,}.",
            f"PASS: Complete sector/quintile rows = {len(sector_quintile):,}.",
            f"PASS: Complete benchmark rows = {len(benchmark):,}.",
            "PASS: H2 forward-return integrity gate was completed before this analysis.",
        ]

        for frame in (
            wml,
            sector_extreme,
            sector_quintile,
            assignments,
            benchmark,
        ):
            if "analysis_month_number" in frame.columns:
                frame[
                    "analysis_month_number"
                ] = pd.to_numeric(
                    frame[
                        "analysis_month_number"
                    ],
                    errors="raise",
                ).astype(int)

        for frame in (
            wml,
            sector_extreme,
            benchmark,
        ):
            frame[
                "ranking_month_end_date"
            ] = pd.to_datetime(
                frame[
                    "ranking_month_end_date"
                ],
                errors="raise",
            )
            frame[
                "return_period_end_date"
            ] = pd.to_datetime(
                frame[
                    "return_period_end_date"
                ],
                errors="raise",
            )

        numeric_columns_by_frame = {
            "wml": [
                "winner_forward_return_1m",
                "loser_forward_return_1m",
                "winner_minus_loser_forward_return_1m",
            ],
            "sector_extreme": [
                "equal_weight_forward_return_1m",
            ],
            "sector_quintile": [
                "equal_weight_forward_return_1m",
            ],
            "assignments": [
                "sector_neutral_leg_weight",
            ],
            "benchmark": [
                "forward_return_1m",
            ],
        }

        for name, frame in (
            ("wml", wml),
            ("sector_extreme", sector_extreme),
            ("sector_quintile", sector_quintile),
            ("assignments", assignments),
            ("benchmark", benchmark),
        ):
            for column in numeric_columns_by_frame[name]:
                frame[column] = pd.to_numeric(
                    frame[column],
                    errors="raise",
                )

        benchmark_types = set(
            benchmark[
                "series_type"
            ].astype(str)
        )
        if benchmark_types != {
            "ETF",
            "INDEX",
        }:
            raise RuntimeError(
                f"Unexpected benchmark series types: {benchmark_types}"
            )

        benchmark["series_code"] = benchmark[
            "series_type"
        ].map(
            {
                "ETF": "SPY",
                "INDEX": "SP500",
            }
        )

        fred, fred_mode = download_fred_cache(
            args.refresh_risk_free
        )

        formation = wml[
            [
                "analysis_month_number",
                "ranking_month_end_date",
                "return_period_end_date",
            ]
        ].copy()

        rf = build_risk_free_panel(
            formation,
            fred,
        )

        lines += [
            (
                "PASS: Risk-free alignment datetime keys normalized to "
                "datetime64[ns]."
            ),
        ]

        rf.to_csv(
            RF_PATH,
            index=False,
        )

        lines += section("2. PRIMARY CONFIRMATORY H2 TEST")

        gross_wml = wml[
            "winner_minus_loser_forward_return_1m"
        ].to_numpy(
            dtype=float
        )

        classical = one_sample_t(
            gross_wml
        )
        boot_low, boot_high = bootstrap_mean_ci(
            gross_wml,
            BOOTSTRAP_SEED,
        )
        wilcoxon_stat, wilcoxon_p = wilcoxon_test(
            gross_wml
        )
        positives, negatives, sign_p = sign_test(
            gross_wml
        )
        hac = newey_west_mean_test(
            gross_wml
        )

        primary_pass = (
            classical["mean"] > 0.0
            and hac["hac_p"] < ALPHA
        )

        primary_row = {
            "observations": EXPECTED_MONTHS,
            "mean_monthly_wml": classical["mean"],
            "arithmetic_annualized_mean": classical["mean"] * 12.0,
            "monthly_sd": classical["sd"],
            "classical_t_stat": classical["t_stat"],
            "classical_t_p": classical["t_p"],
            "classical_ci_low": classical["ci_low"],
            "classical_ci_high": classical["ci_high"],
            "bootstrap_ci_low": boot_low,
            "bootstrap_ci_high": boot_high,
            "wilcoxon_stat": wilcoxon_stat,
            "wilcoxon_p": wilcoxon_p,
            "positive_months": positives,
            "negative_months": negatives,
            "sign_test_p": sign_p,
            "hac_z": hac["hac_z"],
            "hac_p": hac["hac_p"],
            "hac_ci_low": hac["hac_ci_low"],
            "hac_ci_high": hac["hac_ci_high"],
            "gross_final_wealth": final_wealth(gross_wml),
            "gross_annualized_return": annualized_geometric_return(gross_wml),
            "annualized_volatility": annualized_volatility(gross_wml),
            "maximum_drawdown": maximum_drawdown(gross_wml),
            "primary_directional_test_pass": primary_pass,
        }

        pd.DataFrame(
            [primary_row]
        ).to_csv(
            PRIMARY_PATH,
            index=False,
        )

        lines += [
            f"Mean monthly W-L: {pct(classical['mean'])}",
            f"Arithmetic annualized mean: {pct(classical['mean'] * 12.0)}",
            f"Gross compounded wealth: {primary_row['gross_final_wealth']:.4f}",
            f"Gross geometric annualized return: {pct(primary_row['gross_annualized_return'])}",
            f"Annualized volatility: {pct(primary_row['annualized_volatility'])}",
            f"Maximum drawdown: {pct(primary_row['maximum_drawdown'])}",
            (
                "Classical t-test: "
                f"t={num(classical['t_stat'])}, "
                f"p={p_text(classical['t_p'])}"
            ),
            (
                f"Bootstrap 95% CI ({BOOTSTRAP_REPLICATIONS:,}): "
                f"[{pct(boot_low)}, {pct(boot_high)}]"
            ),
            (
                "Wilcoxon signed-rank: "
                f"W={num(wilcoxon_stat, 2)}, "
                f"p={p_text(wilcoxon_p)}"
            ),
            (
                "Sign test: "
                f"positive={positives}, negative={negatives}, "
                f"p={p_text(sign_p)}"
            ),
            (
                f"PRIMARY HAC({HAC_LAG}) mean test: "
                f"z={num(hac['hac_z'])}, "
                f"p={p_text(hac['hac_p'])}"
            ),
            (
                "PRIMARY DECISION RULE: "
                + (
                    "PASS — mean W-L is positive and two-sided HAC p < 0.05."
                    if primary_pass
                    else "FAIL — mean W-L <= 0 or two-sided HAC p >= 0.05."
                )
            ),
        ]

        lines += section("3. SECTOR-LEVEL SECONDARY TESTS WITH HOLM CONTROL")

        pivot_extreme = (
            sector_extreme
            .pivot_table(
                index=[
                    "analysis_month_number",
                    "gics_sector",
                ],
                columns="sector_momentum_portfolio",
                values="equal_weight_forward_return_1m",
                aggfunc="first",
            )
            .reset_index()
        )

        if set(
            pivot_extreme.columns
        ) < {
            "WINNER",
            "LOSER",
        }:
            raise RuntimeError(
                "Sector extreme pivot is incomplete."
            )

        pivot_extreme[
            "WML"
        ] = (
            pivot_extreme["WINNER"]
            - pivot_extreme["LOSER"]
        )

        sector_rows = []
        sector_hac_raw = {}

        rf_map = rf.set_index(
            "analysis_month_number"
        )["risk_free_return"]

        for sector in CANONICAL_SECTORS:
            group = (
                pivot_extreme[
                    pivot_extreme[
                        "gics_sector"
                    ]
                    == sector
                ]
                .sort_values(
                    "analysis_month_number"
                )
            )

            if len(group) != EXPECTED_MONTHS:
                raise RuntimeError(
                    f"{sector} does not have 59 complete sector W-L observations."
                )

            winner = group[
                "WINNER"
            ].to_numpy(
                dtype=float
            )
            loser = group[
                "LOSER"
            ].to_numpy(
                dtype=float
            )
            spread = group[
                "WML"
            ].to_numpy(
                dtype=float
            )

            hac_sector = newey_west_mean_test(
                spread
            )
            sector_hac_raw[
                sector
            ] = hac_sector[
                "hac_p"
            ]

            rf_sector = np.array(
                [
                    float(
                        rf_map.loc[
                            month
                        ]
                    )
                    for month in group[
                        "analysis_month_number"
                    ]
                ],
                dtype=float,
            )

            sector_rows.append(
                {
                    "gics_sector": sector,
                    "observations": len(group),
                    "mean_winner_monthly_return": float(np.mean(winner)),
                    "mean_loser_monthly_return": float(np.mean(loser)),
                    "mean_wml_monthly_return": float(np.mean(spread)),
                    "winner_annualized_return": annualized_geometric_return(winner),
                    "loser_annualized_return": annualized_geometric_return(loser),
                    "wml_annualized_return": annualized_geometric_return(spread),
                    "wml_annualized_volatility": annualized_volatility(spread),
                    "wml_sharpe": annualized_sharpe(spread),
                    "wml_maximum_drawdown": maximum_drawdown(spread),
                    "positive_wml_months": int(np.sum(spread > 0)),
                    "positive_wml_frequency": float(np.mean(spread > 0)),
                    "hac_z": hac_sector["hac_z"],
                    "hac_p_raw": hac_sector["hac_p"],
                }
            )

        sector_holm = holm_adjust(
            sector_hac_raw
        )

        sector_summary = pd.DataFrame(
            sector_rows
        )
        sector_summary[
            "hac_p_holm"
        ] = sector_summary[
            "gics_sector"
        ].map(
            sector_holm
        )
        sector_summary[
            "holm_reject_5pct"
        ] = (
            sector_summary[
                "hac_p_holm"
            ]
            < ALPHA
        )

        sector_summary.to_csv(
            SECTOR_PATH,
            index=False,
        )

        for row in sector_summary.itertuples(
            index=False
        ):
            lines.append(
                f"{row.gics_sector:<26} | "
                f"W-L mean {pct(row.mean_wml_monthly_return)} | "
                f"Ann {pct(row.wml_annualized_return)} | "
                f"Sharpe {num(row.wml_sharpe, 3)} | "
                f"HAC p {p_text(row.hac_p_raw)} | "
                f"Holm p {p_text(row.hac_p_holm)}"
            )

        lines += section("4. QUINTILE MONOTONICITY DIAGNOSTICS")

        aggregate_quintile = (
            sector_quintile
            .groupby(
                [
                    "analysis_month_number",
                    "sector_momentum_quintile",
                ],
                as_index=False,
            )[
                "equal_weight_forward_return_1m"
            ]
            .mean()
        )

        monotonicity_rows = []

        def monotonicity_record(
            label: str,
            frame: pd.DataFrame,
        ) -> dict[str, Any]:
            means = (
                frame
                .groupby(
                    "sector_momentum_quintile"
                )[
                    "equal_weight_forward_return_1m"
                ]
                .mean()
                .reindex(
                    [1, 2, 3, 4, 5]
                )
            )

            if means.isna().any():
                raise RuntimeError(
                    f"{label} quintile means are incomplete."
                )

            values = means.to_numpy(
                dtype=float
            )
            adjacent_increases = int(
                np.sum(
                    np.diff(values)
                    > 0
                )
            )
            rho = float(
                stats.spearmanr(
                    np.arange(
                        1,
                        6,
                    ),
                    values,
                ).statistic
            )

            return {
                "scope": label,
                "q1_mean": values[0],
                "q2_mean": values[1],
                "q3_mean": values[2],
                "q4_mean": values[3],
                "q5_mean": values[4],
                "q5_minus_q1": values[4] - values[0],
                "adjacent_increases_of_4": adjacent_increases,
                "spearman_quintile_vs_mean_return": rho,
            }

        monotonicity_rows.append(
            monotonicity_record(
                "AGGREGATE_SECTOR_NEUTRAL",
                aggregate_quintile,
            )
        )

        for sector in CANONICAL_SECTORS:
            monotonicity_rows.append(
                monotonicity_record(
                    sector,
                    sector_quintile[
                        sector_quintile[
                            "gics_sector"
                        ]
                        == sector
                    ],
                )
            )

        monotonicity = pd.DataFrame(
            monotonicity_rows
        )
        monotonicity.to_csv(
            QUINTILE_PATH,
            index=False,
        )

        agg_mono = monotonicity[
            monotonicity["scope"]
            == "AGGREGATE_SECTOR_NEUTRAL"
        ].iloc[0]

        lines += [
            (
                "Aggregate sector-neutral quintile means: "
                + " | ".join(
                    f"Q{q}={pct(float(agg_mono[f'q{q}_mean']))}"
                    for q in range(1, 6)
                )
            ),
            f"Aggregate Q5-Q1 mean spread: {pct(float(agg_mono['q5_minus_q1']))}",
            (
                "Aggregate adjacent quintile increases: "
                f"{int(agg_mono['adjacent_increases_of_4'])} of 4"
            ),
            (
                "Aggregate quintile-mean Spearman rho: "
                f"{num(float(agg_mono['spearman_quintile_vs_mean_return']), 3)}"
            ),
        ]

        lines += section("5. BENCHMARK AND RISK-ADJUSTED CONTEXT")

        benchmark_pivot = (
            benchmark
            .pivot(
                index="analysis_month_number",
                columns="series_code",
                values="forward_return_1m",
            )
            .sort_index()
        )

        if list(
            benchmark_pivot.index
        ) != list(
            range(1, 60)
        ):
            raise RuntimeError(
                "Benchmark complete months are not exactly 1-59."
            )

        wml_indexed = wml.set_index(
            "analysis_month_number"
        ).sort_index()

        winner = wml_indexed[
            "winner_forward_return_1m"
        ].to_numpy(
            dtype=float
        )
        loser = wml_indexed[
            "loser_forward_return_1m"
        ].to_numpy(
            dtype=float
        )
        spread = wml_indexed[
            "winner_minus_loser_forward_return_1m"
        ].to_numpy(
            dtype=float
        )
        spy = benchmark_pivot[
            "SPY"
        ].to_numpy(
            dtype=float
        )
        sp500 = benchmark_pivot[
            "SP500"
        ].to_numpy(
            dtype=float
        )

        rf = rf.sort_values(
            "analysis_month_number"
        ).reset_index(
            drop=True
        )
        risk_free = rf[
            "risk_free_return"
        ].to_numpy(
            dtype=float
        )

        risk_rows = []

        for code, values, is_spread in (
            ("WINNER", winner, False),
            ("LOSER", loser, False),
            ("WML", spread, True),
            ("SPY", spy, False),
            ("SP500", sp500, False),
        ):
            excess = (
                values
                if is_spread
                else values
                - risk_free
            )

            risk_rows.append(
                {
                    "series_code": code,
                    "observations": len(values),
                    "gross_final_wealth": final_wealth(values),
                    "gross_annualized_return": annualized_geometric_return(values),
                    "annualized_volatility": annualized_volatility(values),
                    "annualized_arithmetic_excess_return": float(np.mean(excess) * 12.0),
                    "annualized_sharpe": annualized_sharpe(excess),
                    "maximum_drawdown": maximum_drawdown(values),
                    "positive_month_frequency": float(np.mean(values > 0)),
                    "mean_monthly_active_return_vs_spy": (
                        float(np.mean(values - spy))
                        if code not in ("SPY", "WML")
                        else (
                            float(np.mean(spread - spy))
                            if code == "WML"
                            else 0.0
                        )
                    ),
                }
            )

        risk_summary = pd.DataFrame(
            risk_rows
        )
        risk_summary.to_csv(
            RISK_PATH,
            index=False,
        )

        capm_rows = []
        market_excess = (
            spy
            - risk_free
        )

        for code, values, is_spread in (
            ("WINNER", winner, False),
            ("LOSER", loser, False),
            ("WML", spread, True),
            ("SP500", sp500, False),
        ):
            y = (
                values
                if is_spread
                else values
                - risk_free
            )
            model = newey_west_ols(
                y,
                market_excess,
            )
            model[
                "series_code"
            ] = code
            capm_rows.append(
                model
            )

        capm_summary = pd.DataFrame(
            capm_rows
        )
        capm_summary.to_csv(
            CAPM_PATH,
            index=False,
        )

        lines += [
            f"DGS1MO source mode: {fred_mode}",
            f"DGS1MO aligned rows: {len(rf)}",
            f"Maximum DGS1MO observation age: {int(rf['rf_observation_age_days'].max())} days",
        ]

        for row in risk_summary.itertuples(
            index=False
        ):
            lines.append(
                f"{row.series_code:<6} | "
                f"Ann Return {pct(row.gross_annualized_return)} | "
                f"Ann Vol {pct(row.annualized_volatility)} | "
                f"Sharpe {num(row.annualized_sharpe, 3)} | "
                f"Max DD {pct(row.maximum_drawdown)}"
            )

        lines += ["", "CAPM / SPY market-factor context:"]

        for row in capm_summary.itertuples(
            index=False
        ):
            lines.append(
                f"{row.series_code:<6} | "
                f"Alpha/mo {pct(row.alpha_monthly)} | "
                f"Alpha/yr {pct(row.alpha_annualized_arithmetic)} | "
                f"Alpha p {p_text(row.alpha_hac_p)} | "
                f"Beta {num(row.beta, 3)} | "
                f"R2 {num(row.r_squared, 3)}"
            )

        winner_minus_spy = (
            winner
            - spy
        )
        winner_minus_sp500 = (
            winner
            - sp500
        )

        lines += [
            "",
            f"Winner mean monthly active return vs SPY: {pct(float(np.mean(winner_minus_spy)))}",
            f"Winner mean monthly active return vs S&P 500 index: {pct(float(np.mean(winner_minus_sp500)))}",
        ]

        lines += section("6. TARGET-WEIGHT TURNOVER AND IMPLEMENTATION COSTS")

        assignments[
            "sector_neutral_leg_weight"
        ] = pd.to_numeric(
            assignments[
                "sector_neutral_leg_weight"
            ],
            errors="raise",
        )

        winner_turnover_df = compute_target_turnover(
            assignments,
            "WINNER",
        )
        loser_turnover_df = compute_target_turnover(
            assignments,
            "LOSER",
        )

        turnover = pd.concat(
            [
                winner_turnover_df,
                loser_turnover_df,
            ],
            ignore_index=True,
        )

        turnover.to_csv(
            TURNOVER_PATH,
            index=False,
        )

        winner_turnover = turnover_schedule_for_performance(
            turnover,
            "WINNER",
        )
        loser_turnover = turnover_schedule_for_performance(
            turnover,
            "LOSER",
        )

        cost_rows = []

        for trading_bps in TRANSACTION_COST_BPS:
            for borrow_bps in BORROW_BPS_ANNUAL:
                net = wml_cost_adjusted_returns(
                    spread,
                    winner_turnover,
                    loser_turnover,
                    trading_bps,
                    borrow_bps,
                )

                cost_rows.append(
                    {
                        "transaction_cost_bps_per_turnover": trading_bps,
                        "annual_short_borrow_fee_bps": borrow_bps,
                        "gross_final_wealth": final_wealth(spread),
                        "net_final_wealth": final_wealth(net),
                        "gross_annualized_return": annualized_geometric_return(spread),
                        "net_annualized_return": annualized_geometric_return(net),
                        "mean_winner_turnover_including_initial": float(np.mean(winner_turnover)),
                        "mean_loser_turnover_including_initial": float(np.mean(loser_turnover)),
                        "mean_total_leg_turnover_including_initial": float(np.mean(winner_turnover + loser_turnover)),
                        "monthly_borrow_cost_rate": float(borrow_bps) / 10_000.0 / 12.0,
                    }
                )

        cost_summary = pd.DataFrame(
            cost_rows
        )
        cost_summary.to_csv(
            COST_PATH,
            index=False,
        )

        base_case = cost_summary[
            (
                cost_summary[
                    "transaction_cost_bps_per_turnover"
                ]
                == BASE_CASE_TRADING_BPS
            )
            & (
                cost_summary[
                    "annual_short_borrow_fee_bps"
                ]
                == BASE_CASE_BORROW_BPS
            )
        ].iloc[0]

        base_case_positive = (
            float(
                base_case[
                    "net_annualized_return"
                ]
            )
            > 0.0
        )

        lines += [
            (
                "Winner mean one-way turnover including initial formation: "
                f"{pct(float(np.mean(winner_turnover)))}"
            ),
            (
                "Loser mean one-way turnover including initial formation: "
                f"{pct(float(np.mean(loser_turnover)))}"
            ),
        ]

        for trading_bps in TRANSACTION_COST_BPS:
            lines.append(
                f"Trading cost = {trading_bps} bps:"
            )
            subset = cost_summary[
                cost_summary[
                    "transaction_cost_bps_per_turnover"
                ]
                == trading_bps
            ]
            for row in subset.itertuples(
                index=False
            ):
                lines.append(
                    f"  Borrow {int(row.annual_short_borrow_fee_bps):>3} bps/year | "
                    f"Net wealth {row.net_final_wealth:.4f} | "
                    f"Net ann {pct(row.net_annualized_return)}"
                )

        lines += section("7. CROSS-SECTOR CONCENTRATION ROBUSTNESS")

        sector_spread_pivot = (
            pivot_extreme
            .pivot(
                index="analysis_month_number",
                columns="gics_sector",
                values="WML",
            )
            .sort_index()
        )

        if list(
            sector_spread_pivot.columns
        ) != CANONICAL_SECTORS:
            sector_spread_pivot = sector_spread_pivot[
                CANONICAL_SECTORS
            ]

        loo_rows = []

        for excluded in CANONICAL_SECTORS:
            remaining = [
                sector
                for sector in CANONICAL_SECTORS
                if sector != excluded
            ]
            loo = sector_spread_pivot[
                remaining
            ].mean(
                axis=1
            )
            loo_hac = newey_west_mean_test(
                loo.to_numpy(
                    dtype=float
                )
            )
            loo_rows.append(
                {
                    "excluded_sector": excluded,
                    "mean_monthly_wml": float(loo.mean()),
                    "annualized_arithmetic_mean": float(loo.mean() * 12.0),
                    "hac_p": loo_hac["hac_p"],
                    "positive_mean": bool(loo.mean() > 0.0),
                }
            )

        loo_summary = pd.DataFrame(
            loo_rows
        )
        loo_summary.to_csv(
            LOO_PATH,
            index=False,
        )

        positive_loo_count = int(
            loo_summary[
                "positive_mean"
            ].sum()
        )

        aggregate_arithmetic_total = float(
            gross_wml.sum()
        )

        contribution_rows = []

        for sector in CANONICAL_SECTORS:
            sector_sum = float(
                sector_spread_pivot[
                    sector
                ].sum()
            )
            additive_contribution = (
                sector_sum
                / 11.0
            )
            share = (
                additive_contribution
                / aggregate_arithmetic_total
                if aggregate_arithmetic_total != 0.0
                else math.nan
            )

            contribution_rows.append(
                {
                    "gics_sector": sector,
                    "sector_sum_monthly_wml": sector_sum,
                    "aggregate_additive_contribution": additive_contribution,
                    "share_of_aggregate_arithmetic_cumulative_wml": share,
                }
            )

        contribution = pd.DataFrame(
            contribution_rows
        )
        contribution.to_csv(
            CONTRIBUTION_PATH,
            index=False,
        )

        if aggregate_arithmetic_total > 0.0:
            max_positive_share = float(
                contribution[
                    "share_of_aggregate_arithmetic_cumulative_wml"
                ].max()
            )
            concentration_share_pass = (
                max_positive_share
                <= 0.50
            )
        else:
            max_positive_share = math.nan
            concentration_share_pass = False

        concentration_pass = (
            positive_loo_count >= 9
            and concentration_share_pass
        )

        lines += [
            (
                "Leave-one-sector-out positive mean W-L estimates: "
                f"{positive_loo_count} of 11"
            ),
            (
                "Largest additive sector share of aggregate arithmetic cumulative W-L: "
                + (
                    pct(max_positive_share)
                    if math.isfinite(max_positive_share)
                    else "N/A — aggregate arithmetic W-L is nonpositive"
                )
            ),
            (
                "Concentration criterion: "
                + (
                    "PASS"
                    if concentration_pass
                    else "FAIL"
                )
            ),
            (
                "Contribution convention: arithmetic monthly sector spreads are "
                "scaled by 1/11 so contributions add exactly to aggregate arithmetic W-L."
            ),
        ]

        lines += section("8. FINAL PREREGISTERED H2 DECISION")

        if not primary_pass:
            final_label = "NOT SUPPORTED"
            final_reason = (
                "Primary directional rule failed: mean W-L was not both positive "
                "and statistically significant at two-sided HAC(3) p < 0.05."
            )
        else:
            if (
                base_case_positive
                and concentration_pass
            ):
                final_label = (
                    "SUPPORTED — BROAD AND COST-ROBUST"
                )
                final_reason = (
                    "Primary rule passed, base-case net W-L remained positive, "
                    "and cross-sector concentration criteria passed."
                )
            else:
                final_label = (
                    "SUPPORTED — QUALIFIED"
                )
                final_reason = (
                    "Primary statistical rule passed, but either base-case cost "
                    "robustness or cross-sector concentration criterion failed."
                )

        lines += [
            f"Primary mean W-L: {pct(classical['mean'])}",
            f"Primary HAC(3) p-value: {p_text(hac['hac_p'])}",
            f"Primary statistical rule passed: {'YES' if primary_pass else 'NO'}",
            (
                "Base-case net annualized W-L "
                f"(10 bps + 100 bps borrow): "
                f"{pct(float(base_case['net_annualized_return']))}"
            ),
            f"Base-case net positive: {'YES' if base_case_positive else 'NO'}",
            f"Cross-sector concentration criterion passed: {'YES' if concentration_pass else 'NO'}",
            "",
            f"H2 FINAL LABEL: {final_label}",
            f"Reason: {final_reason}",
        ]

        lines += section("9. INTERPRETATION BOUNDARIES AND OUTPUTS")

        lines += [
            "The primary H2 test is confirmatory relative to the committed preregistration.",
            "Sector-level tests are secondary and Holm-adjusted as one 11-test family.",
            "Benchmark, Sharpe, CAPM, monotonicity, turnover, cost, and concentration results are secondary robustness evidence.",
            "DGS1MO is a constant-maturity yield proxy, not the realized return of a specific Treasury bill.",
            "CAPM controls only for SPY market exposure.",
            "Trading and borrow costs are scenarios rather than reconstructed historical execution costs.",
            "Sector contribution concentration uses an additive arithmetic decomposition because compounded W-L is not exactly decomposable by sector.",
            "No H1 parameter or conclusion is modified by H2.",
            "",
            f"Primary output: {PRIMARY_PATH.relative_to(ROOT)}",
            f"Sector inference: {SECTOR_PATH.relative_to(ROOT)}",
            f"Quintile monotonicity: {QUINTILE_PATH.relative_to(ROOT)}",
            f"Risk-adjusted summary: {RISK_PATH.relative_to(ROOT)}",
            f"CAPM summary: {CAPM_PATH.relative_to(ROOT)}",
            f"Turnover: {TURNOVER_PATH.relative_to(ROOT)}",
            f"Cost/borrow sensitivity: {COST_PATH.relative_to(ROOT)}",
            f"Leave-one-sector-out: {LOO_PATH.relative_to(ROOT)}",
            f"Sector contribution: {CONTRIBUTION_PATH.relative_to(ROOT)}",
            f"Risk-free alignment: {RF_PATH.relative_to(ROOT)}",
            "",
            "H2_SECTOR_RELATIVE_MOMENTUM_ANALYSIS_COMPLETE",
        ]

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
    print(
        report_text,
        end="",
    )
    print(
        f"Report saved: {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()
