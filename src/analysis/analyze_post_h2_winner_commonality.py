from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-security-level-persistence-fix"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

REPORT_DIR = ROOT / "reports" / "exploratory"
REPORT_PATH = REPORT_DIR / "post_h2_winner_commonality_analysis.txt"

WINNER_HISTORY_PATH = REPORT_DIR / "post_h2_winner_membership_history.csv"
WINNER_PERSISTENCE_PATH = REPORT_DIR / "post_h2_winner_persistence_by_security.csv"
TRANSITION_PATH = REPORT_DIR / "post_h2_winner_transition_by_sector_month.csv"
SECTOR_PERSISTENCE_PATH = REPORT_DIR / "post_h2_winner_persistence_by_sector.csv"
SECTOR_PANEL_PATH = REPORT_DIR / "post_h2_sector_winner_return_panel.csv"
SYNC_PATH = REPORT_DIR / "post_h2_winner_synchrony_monthly.csv"
REGRESSION_PATH = REPORT_DIR / "post_h2_winner_market_sector_regressions.csv"
RESIDUAL_PANEL_PATH = REPORT_DIR / "post_h2_winner_residual_panel.csv"
RAW_CORR_PATH = REPORT_DIR / "post_h2_winner_raw_correlation_matrix.csv"
ACTIVE_CORR_PATH = REPORT_DIR / "post_h2_winner_sector_active_correlation_matrix.csv"
RESIDUAL_CORR_PATH = REPORT_DIR / "post_h2_winner_residual_correlation_matrix.csv"
PCA_PATH = REPORT_DIR / "post_h2_winner_pca_summary.csv"
PCA_LOADINGS_PATH = REPORT_DIR / "post_h2_winner_pca_loadings.csv"
COMMONALITY_PATH = REPORT_DIR / "post_h2_winner_commonality_factor.csv"

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

EXPECTED_RANKING_MONTHS = 60
EXPECTED_RETURN_MONTHS = 59
EXPECTED_SECTOR_MONTHS = 649  # 59 transitions x 11 sectors
EXPECTED_COMPLETE_SECURITY_RETURNS = 29_620
EXPECTED_COMPLETE_WINNER_SECTOR_ROWS = 649
EXPECTED_BENCHMARK_ROWS = 118

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}


def line() -> str:
    return "=" * 118


def section(title: str) -> list[str]:
    return ["", line(), title, line()]


def pct(value: float, digits: int = 2) -> str:
    return f"{100.0 * float(value):.{digits}f}%"


def num(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


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
            "Missing environment variables: " + ", ".join(missing)
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
            f"{ODBC_DRIVER} is not installed. Available drivers: {pyodbc.drivers()}"
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

    for attempt in range(1, 6):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(f"ODBC connection established on attempt {attempt} / 5.")
            return connection
        except pyodbc.Error:
            if attempt == 5:
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
    return pd.DataFrame.from_records(cursor.fetchall(), columns=columns)


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def max_consecutive_streak(months: Iterable[int]) -> int:
    values = sorted(set(int(x) for x in months))
    if not values:
        return 0

    best = 1
    current = 1

    for previous, current_month in zip(values, values[1:]):
        if current_month == previous + 1:
            current += 1
            best = max(best, current)
        else:
            current = 1

    return best


def average_pairwise_correlation(corr: pd.DataFrame) -> float:
    matrix = corr.to_numpy(dtype=float)
    n = matrix.shape[0]
    if n < 2:
        return math.nan
    upper = matrix[np.triu_indices(n, k=1)]
    return float(np.mean(upper))


def correlation_pca(
    panel: pd.DataFrame,
    stage: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    PCA on the correlation matrix so no high-volatility sector dominates
    simply because of scale.
    """
    ordered = panel[CANONICAL_SECTORS].copy()
    if ordered.isna().any().any():
        raise RuntimeError(f"{stage} panel contains missing values.")

    standardized = (
        ordered - ordered.mean(axis=0)
    ) / ordered.std(axis=0, ddof=1)

    corr = standardized.corr().to_numpy(dtype=float)
    eigenvalues, eigenvectors = np.linalg.eigh(corr)

    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    explained = eigenvalues / eigenvalues.sum()

    summary = pd.DataFrame(
        {
            "stage": stage,
            "component": np.arange(1, len(eigenvalues) + 1),
            "eigenvalue": eigenvalues,
            "explained_variance_ratio": explained,
            "cumulative_explained_variance_ratio": np.cumsum(explained),
        }
    )

    loadings = pd.DataFrame(
        {
            "stage": stage,
            "gics_sector": CANONICAL_SECTORS,
            "pc1_loading": eigenvectors[:, 0],
            "pc2_loading": eigenvectors[:, 1],
        }
    )

    # Eigenvectors have arbitrary sign. Normalize PC1 so the average loading
    # is positive; this makes repeated runs easier to interpret.
    if float(loadings["pc1_loading"].mean()) < 0:
        loadings["pc1_loading"] *= -1.0

    return summary, loadings


def fit_market_sector_regression(
    y: np.ndarray,
    spy: np.ndarray,
    sector_baseline: np.ndarray,
) -> tuple[dict[str, float], np.ndarray]:
    """
    Exploratory in-sample OLS:
        Winner_sector_return = alpha + beta_m * SPY + beta_s * sector_EW + residual

    This is descriptive residualization, not a confirmatory factor model.
    """
    y = np.asarray(y, dtype=float)
    spy = np.asarray(spy, dtype=float)
    sector_baseline = np.asarray(sector_baseline, dtype=float)

    X = np.column_stack(
        [
            np.ones(len(y)),
            spy,
            sector_baseline,
        ]
    )

    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    residual = y - fitted

    ss_res = float(np.sum(residual ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = (
        1.0 - ss_res / ss_tot
        if ss_tot > 0
        else math.nan
    )

    return (
        {
            "alpha_monthly": float(beta[0]),
            "beta_spy": float(beta[1]),
            "beta_sector_equal_weight": float(beta[2]),
            "r_squared": r_squared,
            "winner_return_mean": float(np.mean(y)),
            "residual_mean": float(np.mean(residual)),
            "residual_std": float(np.std(residual, ddof=1)),
        },
        residual,
    )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        line(),
        "POST-H2 EXPLORATORY CROSS-SECTOR WINNER COMMONALITY — PHASE 1",
        line(),
        "Status: EXPLORATORY / NON-CONFIRMATORY",
        "H1 conclusion modified: NO",
        "H2 conclusion modified: NO",
        "Azure SQL mode: READ-ONLY",
        "",
        "Purpose:",
        "1. quantify repeated Winner membership and persistence;",
        "2. measure synchronous Winner-sector behavior;",
        "3. remove broad SPY and own-sector equal-weight return exposure;",
        "4. measure remaining cross-sector residual commonality;",
        "5. create a descriptive commonality factor for later exploratory work.",
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

        lines += section("1. SOURCE / PRESERVATION CONTROLS")

        for table, expected in CORE_COUNTS.items():
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            if actual != expected:
                raise RuntimeError(
                    f"core.{table} changed: {actual:,} vs expected {expected:,}."
                )
            lines.append(f"PASS: core.{table} remains {expected:,} rows.")

        ranking = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_end_date AS ranking_month_end_date,
                security_key,
                project_ticker,
                gics_sector,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                sector_neutral_leg_weight
            FROM analytics.v_security_monthly_sector_momentum_portfolio
            ORDER BY analysis_month_number, gics_sector, security_key;
            """,
        )

        security_forward = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                target_holding_end_date AS return_period_end_date,
                security_key,
                project_ticker,
                gics_sector,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                sector_equal_weight,
                sector_neutral_leg_weight,
                forward_return_1m
            FROM analytics.v_h2_security_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number, gics_sector, security_key;
            """,
        )

        winner_sector = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                target_holding_end_date AS return_period_end_date,
                gics_sector,
                equal_weight_forward_return_1m AS winner_sector_return
            FROM analytics.v_h2_sector_extreme_forward_return_1m
            WHERE forward_return_1m_complete = 1
              AND sector_momentum_portfolio = 'WINNER'
            ORDER BY analysis_month_number, gics_sector;
            """,
        )

        benchmark = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                series_type,
                forward_return_1m
            FROM analytics.v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number, series_type;
            """,
        )

        ranking["analysis_month_number"] = pd.to_numeric(
            ranking["analysis_month_number"], errors="raise"
        ).astype(int)
        security_forward["analysis_month_number"] = pd.to_numeric(
            security_forward["analysis_month_number"], errors="raise"
        ).astype(int)
        winner_sector["analysis_month_number"] = pd.to_numeric(
            winner_sector["analysis_month_number"], errors="raise"
        ).astype(int)
        benchmark["analysis_month_number"] = pd.to_numeric(
            benchmark["analysis_month_number"], errors="raise"
        ).astype(int)

        ranking["ranking_month_end_date"] = pd.to_datetime(
            ranking["ranking_month_end_date"], errors="raise"
        )
        security_forward["ranking_month_end_date"] = pd.to_datetime(
            security_forward["ranking_month_end_date"], errors="raise"
        )
        security_forward["return_period_end_date"] = pd.to_datetime(
            security_forward["return_period_end_date"], errors="raise"
        )
        winner_sector["ranking_month_end_date"] = pd.to_datetime(
            winner_sector["ranking_month_end_date"], errors="raise"
        )
        winner_sector["return_period_end_date"] = pd.to_datetime(
            winner_sector["return_period_end_date"], errors="raise"
        )

        for frame in (ranking, security_forward, winner_sector, benchmark):
            for column in (
                "security_key",
                "project_ticker",
                "gics_sector",
                "sector_momentum_portfolio",
                "series_type",
            ):
                if column in frame.columns:
                    frame[column] = frame[column].astype(str).str.strip()

        for column in (
            "sector_equal_weight",
            "sector_neutral_leg_weight",
            "forward_return_1m",
        ):
            if column in security_forward.columns:
                security_forward[column] = pd.to_numeric(
                    security_forward[column], errors="raise"
                )

        winner_sector["winner_sector_return"] = pd.to_numeric(
            winner_sector["winner_sector_return"], errors="raise"
        )
        benchmark["forward_return_1m"] = pd.to_numeric(
            benchmark["forward_return_1m"], errors="raise"
        )

        if ranking["analysis_month_number"].nunique() != EXPECTED_RANKING_MONTHS:
            raise RuntimeError("Ranking source does not span 60 months.")
        if len(security_forward) != EXPECTED_COMPLETE_SECURITY_RETURNS:
            raise RuntimeError(
                f"Complete security forward rows={len(security_forward):,}, "
                f"expected {EXPECTED_COMPLETE_SECURITY_RETURNS:,}."
            )
        if len(winner_sector) != EXPECTED_COMPLETE_WINNER_SECTOR_ROWS:
            raise RuntimeError(
                f"Complete Winner-sector rows={len(winner_sector):,}, "
                f"expected {EXPECTED_COMPLETE_WINNER_SECTOR_ROWS:,}."
            )
        if len(benchmark) != EXPECTED_BENCHMARK_ROWS:
            raise RuntimeError(
                f"Complete benchmark rows={len(benchmark):,}, "
                f"expected {EXPECTED_BENCHMARK_ROWS:,}."
            )

        lines += [
            f"PASS: H2 ranking source spans {EXPECTED_RANKING_MONTHS} months.",
            f"PASS: complete security forward source = {len(security_forward):,} rows.",
            f"PASS: complete Winner-sector source = {len(winner_sector):,} rows.",
            f"PASS: complete benchmark source = {len(benchmark):,} rows.",
        ]

        lines += section("2. WINNER MEMBERSHIP HISTORY AND PERSISTENCE")

        eligible = ranking[
            [
                "analysis_month_number",
                "ranking_month_end_date",
                "security_key",
                "project_ticker",
                "gics_sector",
            ]
        ].copy()

        winners = ranking[
            ranking["sector_momentum_portfolio"] == "WINNER"
        ][
            [
                "analysis_month_number",
                "ranking_month_end_date",
                "security_key",
                "project_ticker",
                "gics_sector",
                "sector_momentum_quintile",
                "sector_neutral_leg_weight",
            ]
        ].copy()

        winners.to_csv(
            WINNER_HISTORY_PATH,
            index=False,
        )

        eligible_months = (
            eligible.groupby(
                [
                    "security_key",
                    "project_ticker",
                ],
                as_index=False,
            )["analysis_month_number"]
            .nunique()
            .rename(
                columns={
                    "analysis_month_number": "eligible_months"
                }
            )
        )

        # Security-level persistence must be measured across the security's
        # full point-in-time history, not split by GICS sector. A small number
        # of securities legitimately change GICS sectors during 2021-2025
        # (for example, official reclassifications). Grouping persistence by
        # security + sector creates multiple rows for one security and would
        # artificially split its Winner history.
        winner_counts = (
            winners.groupby(
                [
                    "security_key",
                    "project_ticker",
                ],
                as_index=False,
            )["analysis_month_number"]
            .agg(
                winner_months="nunique",
                first_winner_month="min",
                last_winner_month="max",
            )
        )

        sector_history = (
            winners.groupby(
                [
                    "security_key",
                    "project_ticker",
                ],
                as_index=False,
            )
            .agg(
                gics_sectors_seen=(
                    "gics_sector",
                    lambda values: " | ".join(
                        sorted(
                            set(
                                str(value)
                                for value in values
                            )
                        )
                    ),
                ),
                winner_sector_count=(
                    "gics_sector",
                    "nunique",
                ),
                latest_winner_sector=(
                    "gics_sector",
                    "last",
                ),
            )
        )

        streak_rows = []
        for keys, group in winners.groupby(
            [
                "security_key",
                "project_ticker",
            ],
            sort=False,
        ):
            security_key, ticker = keys
            streak_rows.append(
                {
                    "security_key": security_key,
                    "project_ticker": ticker,
                    "max_consecutive_winner_streak": max_consecutive_streak(
                        group["analysis_month_number"]
                    ),
                }
            )

        streaks = pd.DataFrame(streak_rows)

        persistence = (
            winner_counts
            .merge(
                eligible_months,
                on=[
                    "security_key",
                    "project_ticker",
                ],
                how="left",
                validate="one_to_one",
            )
            .merge(
                sector_history,
                on=[
                    "security_key",
                    "project_ticker",
                ],
                how="left",
                validate="one_to_one",
            )
            .merge(
                streaks,
                on=[
                    "security_key",
                    "project_ticker",
                ],
                how="left",
                validate="one_to_one",
            )
        )

        persistence["winner_share_of_eligible_months"] = (
            persistence["winner_months"]
            / persistence["eligible_months"]
        )

        if persistence.duplicated(
            [
                "security_key",
                "project_ticker",
            ]
        ).any():
            raise RuntimeError(
                "Security-level Winner persistence still contains duplicate "
                "security/ticker rows."
            )

        if (
            persistence["winner_months"]
            > persistence["eligible_months"]
        ).any():
            raise RuntimeError(
                "A security has more Winner months than eligible months."
            )

        persistence = persistence.sort_values(
            [
                "winner_months",
                "max_consecutive_winner_streak",
                "winner_share_of_eligible_months",
                "project_ticker",
            ],
            ascending=[
                False,
                False,
                False,
                True,
            ],
        ).reset_index(drop=True)

        persistence.to_csv(
            WINNER_PERSISTENCE_PATH,
            index=False,
        )

        transition_rows = []

        winner_sets = {
            (
                int(month),
                str(sector),
            ): set(group["security_key"].astype(str))
            for (month, sector), group in winners.groupby(
                [
                    "analysis_month_number",
                    "gics_sector",
                ]
            )
        }

        for month in range(2, 61):
            for sector in CANONICAL_SECTORS:
                previous = winner_sets.get(
                    (month - 1, sector),
                    set(),
                )
                current = winner_sets.get(
                    (month, sector),
                    set(),
                )

                if not previous or not current:
                    raise RuntimeError(
                        f"Missing Winner set for month={month}, sector={sector}."
                    )

                overlap = previous & current
                union = previous | current

                transition_rows.append(
                    {
                        "analysis_month_number": month,
                        "gics_sector": sector,
                        "previous_winner_count": len(previous),
                        "current_winner_count": len(current),
                        "overlap_count": len(overlap),
                        "entrant_count": len(current - previous),
                        "exit_count": len(previous - current),
                        "current_winner_retention": len(overlap) / len(current),
                        "previous_winner_survival": len(overlap) / len(previous),
                        "jaccard_similarity": len(overlap) / len(union),
                    }
                )

        transitions = pd.DataFrame(transition_rows)

        if len(transitions) != EXPECTED_SECTOR_MONTHS:
            raise RuntimeError(
                f"Winner transition rows={len(transitions)}, "
                f"expected {EXPECTED_SECTOR_MONTHS}."
            )

        transitions.to_csv(
            TRANSITION_PATH,
            index=False,
        )

        sector_persistence = (
            transitions.groupby(
                "gics_sector",
                as_index=False,
            )
            .agg(
                mean_current_winner_retention=(
                    "current_winner_retention",
                    "mean",
                ),
                median_current_winner_retention=(
                    "current_winner_retention",
                    "median",
                ),
                mean_previous_winner_survival=(
                    "previous_winner_survival",
                    "mean",
                ),
                mean_jaccard_similarity=(
                    "jaccard_similarity",
                    "mean",
                ),
                mean_entrant_count=(
                    "entrant_count",
                    "mean",
                ),
                mean_exit_count=(
                    "exit_count",
                    "mean",
                ),
            )
        )

        sector_persistence.to_csv(
            SECTOR_PERSISTENCE_PATH,
            index=False,
        )

        overall_retention = float(
            transitions["current_winner_retention"].mean()
        )
        overall_jaccard = float(
            transitions["jaccard_similarity"].mean()
        )

        multi_sector_winner_security_count = int(
            (
                persistence["winner_sector_count"]
                > 1
            ).sum()
        )

        lines += [
            f"Winner membership rows across 60 ranking months: {len(winners):,}",
            f"Unique securities appearing as Winner at least once: {persistence['security_key'].nunique():,}",
            (
                "Winner securities observed across more than one GICS sector "
                f"during the sample: {multi_sector_winner_security_count}"
            ),
            f"Mean sector-month current-Winner retention: {pct(overall_retention)}",
            f"Mean sector-month Winner-set Jaccard similarity: {pct(overall_jaccard)}",
            "",
            "Most frequently recurring Winners:",
        ]

        for row in persistence.head(15).itertuples(index=False):
            sector_display = str(row.gics_sectors_seen)
            lines.append(
                f"{row.project_ticker:<8} | "
                f"{sector_display:<45} | "
                f"Winner months {int(row.winner_months):>2}/{int(row.eligible_months):>2} | "
                f"Share {pct(row.winner_share_of_eligible_months)} | "
                f"Max streak {int(row.max_consecutive_winner_streak)}"
            )

        lines += section("3. WINNER SECTOR RETURN PANEL AND SYNCHRONY")

        sector_baseline = (
            security_forward
            .groupby(
                [
                    "analysis_month_number",
                    "gics_sector",
                ],
                as_index=False,
            )["forward_return_1m"]
            .mean()
            .rename(
                columns={
                    "forward_return_1m": "sector_equal_weight_return"
                }
            )
        )

        spy = benchmark[
            benchmark["series_type"] == "ETF"
        ][
            [
                "analysis_month_number",
                "forward_return_1m",
            ]
        ].rename(
            columns={
                "forward_return_1m": "spy_return"
            }
        )

        if len(spy) != EXPECTED_RETURN_MONTHS:
            raise RuntimeError(
                f"SPY complete rows={len(spy)}, expected 59."
            )

        panel_long = (
            winner_sector
            .merge(
                sector_baseline,
                on=[
                    "analysis_month_number",
                    "gics_sector",
                ],
                how="left",
                validate="one_to_one",
            )
            .merge(
                spy,
                on="analysis_month_number",
                how="left",
                validate="many_to_one",
            )
        )

        if panel_long[
            [
                "sector_equal_weight_return",
                "spy_return",
            ]
        ].isna().any().any():
            raise RuntimeError(
                "Winner return panel has missing sector baseline or SPY return."
            )

        panel_long[
            "winner_active_vs_sector"
        ] = (
            panel_long["winner_sector_return"]
            - panel_long["sector_equal_weight_return"]
        )

        panel_long.to_csv(
            SECTOR_PANEL_PATH,
            index=False,
        )

        raw_wide = (
            panel_long
            .pivot(
                index="analysis_month_number",
                columns="gics_sector",
                values="winner_sector_return",
            )
            .reindex(
                columns=CANONICAL_SECTORS
            )
            .sort_index()
        )

        active_wide = (
            panel_long
            .pivot(
                index="analysis_month_number",
                columns="gics_sector",
                values="winner_active_vs_sector",
            )
            .reindex(
                columns=CANONICAL_SECTORS
            )
            .sort_index()
        )

        if (
            len(raw_wide) != EXPECTED_RETURN_MONTHS
            or raw_wide.isna().any().any()
            or active_wide.isna().any().any()
        ):
            raise RuntimeError(
                "Winner sector return matrices are incomplete."
            )

        raw_corr = raw_wide.corr()
        active_corr = active_wide.corr()

        raw_corr.to_csv(
            RAW_CORR_PATH,
            index=True,
        )
        active_corr.to_csv(
            ACTIVE_CORR_PATH,
            index=True,
        )

        raw_avg_corr = average_pairwise_correlation(
            raw_corr
        )
        active_avg_corr = average_pairwise_correlation(
            active_corr
        )

        sync = pd.DataFrame(
            {
                "analysis_month_number": raw_wide.index.astype(int),
                "positive_winner_sectors": (
                    raw_wide > 0
                ).sum(axis=1).to_numpy(),
                "winner_beats_sector_baseline_count": (
                    active_wide > 0
                ).sum(axis=1).to_numpy(),
                "mean_winner_sector_return": raw_wide.mean(axis=1).to_numpy(),
                "cross_sector_winner_return_std": raw_wide.std(
                    axis=1,
                    ddof=1,
                ).to_numpy(),
                "mean_winner_active_vs_sector": active_wide.mean(axis=1).to_numpy(),
                "cross_sector_active_return_std": active_wide.std(
                    axis=1,
                    ddof=1,
                ).to_numpy(),
            }
        )

        lines += [
            f"Average pairwise raw Winner-sector return correlation: {num(raw_avg_corr)}",
            f"Average pairwise Winner active-vs-sector correlation: {num(active_avg_corr)}",
            f"Mean sectors with positive Winner return per month: {num(sync['positive_winner_sectors'].mean(), 2)} / 11",
            f"Mean sectors where Winner beat own sector baseline: {num(sync['winner_beats_sector_baseline_count'].mean(), 2)} / 11",
            f"Months with >=8 positive Winner sectors: {int((sync['positive_winner_sectors'] >= 8).sum())} / 59",
        ]

        lines += section("4. SPY + OWN-SECTOR RESIDUALIZATION")

        regression_rows = []
        residual_long_rows = []

        spy_map = spy.set_index(
            "analysis_month_number"
        )["spy_return"]

        for sector in CANONICAL_SECTORS:
            group = (
                panel_long[
                    panel_long["gics_sector"] == sector
                ]
                .sort_values(
                    "analysis_month_number"
                )
                .reset_index(drop=True)
            )

            if len(group) != EXPECTED_RETURN_MONTHS:
                raise RuntimeError(
                    f"{sector} Winner panel rows={len(group)}, expected 59."
                )

            y = group[
                "winner_sector_return"
            ].to_numpy(
                dtype=float
            )
            spy_values = group[
                "spy_return"
            ].to_numpy(
                dtype=float
            )
            sector_values = group[
                "sector_equal_weight_return"
            ].to_numpy(
                dtype=float
            )

            coefficients, residual = fit_market_sector_regression(
                y,
                spy_values,
                sector_values,
            )

            regression_rows.append(
                {
                    "gics_sector": sector,
                    "observations": len(group),
                    **coefficients,
                }
            )

            for month, value in zip(
                group["analysis_month_number"].astype(int),
                residual,
            ):
                residual_long_rows.append(
                    {
                        "analysis_month_number": int(month),
                        "gics_sector": sector,
                        "winner_residual_return": float(value),
                    }
                )

        regressions = pd.DataFrame(regression_rows)
        regressions.to_csv(
            REGRESSION_PATH,
            index=False,
        )

        residual_long = pd.DataFrame(
            residual_long_rows
        )

        residual_wide = (
            residual_long
            .pivot(
                index="analysis_month_number",
                columns="gics_sector",
                values="winner_residual_return",
            )
            .reindex(
                columns=CANONICAL_SECTORS
            )
            .sort_index()
        )

        if (
            len(residual_wide) != EXPECTED_RETURN_MONTHS
            or residual_wide.isna().any().any()
        ):
            raise RuntimeError(
                "Residual Winner return matrix is incomplete."
            )

        residual_wide.to_csv(
            RESIDUAL_PANEL_PATH,
            index=True,
        )

        residual_corr = residual_wide.corr()
        residual_corr.to_csv(
            RESIDUAL_CORR_PATH,
            index=True,
        )

        residual_avg_corr = average_pairwise_correlation(
            residual_corr
        )

        commonality = pd.DataFrame(
            {
                "analysis_month_number": residual_wide.index.astype(int),
                "commonality_factor_equal_weight_residual": residual_wide.mean(
                    axis=1
                ).to_numpy(),
                "positive_residual_sector_count": (
                    residual_wide > 0
                ).sum(axis=1).to_numpy(),
                "cross_sector_residual_std": residual_wide.std(
                    axis=1,
                    ddof=1,
                ).to_numpy(),
            }
        )

        sync = sync.merge(
            commonality,
            on="analysis_month_number",
            how="left",
            validate="one_to_one",
        )
        sync.to_csv(
            SYNC_PATH,
            index=False,
        )
        commonality.to_csv(
            COMMONALITY_PATH,
            index=False,
        )

        lines += [
            (
                "Residualization model per sector: "
                "Winner return ~ intercept + SPY return + equal-weight own-sector return"
            ),
            f"Average pairwise residual Winner correlation: {num(residual_avg_corr)}",
            f"Mean sectors with positive residual per month: {num(commonality['positive_residual_sector_count'].mean(), 2)} / 11",
            f"Residual commonality-factor monthly volatility: {pct(commonality['commonality_factor_equal_weight_residual'].std(ddof=1))}",
            (
                "Residual commonality-factor mean: "
                f"{pct(commonality['commonality_factor_equal_weight_residual'].mean(), 4)} "
                "(mechanically near zero because sector regressions include intercepts)"
            ),
        ]

        lines += section("5. RAW / ACTIVE / RESIDUAL PCA COMMONALITY")

        pca_frames = []
        loading_frames = []

        for stage, frame in (
            ("RAW_WINNER", raw_wide),
            ("ACTIVE_VS_SECTOR", active_wide),
            ("RESIDUAL_SPY_PLUS_SECTOR", residual_wide),
        ):
            summary, loadings = correlation_pca(
                frame,
                stage,
            )
            pca_frames.append(
                summary
            )
            loading_frames.append(
                loadings
            )

        pca = pd.concat(
            pca_frames,
            ignore_index=True,
        )
        loadings = pd.concat(
            loading_frames,
            ignore_index=True,
        )

        pca.to_csv(
            PCA_PATH,
            index=False,
        )
        loadings.to_csv(
            PCA_LOADINGS_PATH,
            index=False,
        )

        for stage in (
            "RAW_WINNER",
            "ACTIVE_VS_SECTOR",
            "RESIDUAL_SPY_PLUS_SECTOR",
        ):
            pc1 = pca[
                (pca["stage"] == stage)
                & (pca["component"] == 1)
            ].iloc[0]
            pc2 = pca[
                (pca["stage"] == stage)
                & (pca["component"] == 2)
            ].iloc[0]
            lines.append(
                f"{stage:<25} | "
                f"PC1 explained {pct(pc1['explained_variance_ratio'])} | "
                f"PC1+PC2 explained {pct(pc2['cumulative_explained_variance_ratio'])}"
            )

        lines += section("6. EXPLORATORY INTERPRETATION BOUNDARY")

        lines += [
            "These outputs are descriptive and exploratory.",
            "They do not alter the closed H2 label.",
            "The own-sector control is an equal-weight return of all H2-eligible stocks in that GICS sector.",
            "Because the Winner sleeve is part of its own sector baseline, the sector control is not an independent tradable benchmark.",
            "The SPY + sector residualization is in-sample OLS and should not be interpreted as an investable alpha estimate.",
            "PCA is performed on correlation matrices to study common movement rather than raw-volatility dominance.",
            "The equal-weight residual commonality factor has approximately zero full-sample mean by construction because each sector regression includes an intercept.",
            "If residual correlations and PCA still show meaningful common movement, the next phase should investigate which securities/months drive it.",
            "Narrative, news, search-attention, or social/cultural variables should not be introduced until this return-commonality layer is understood.",
        ]

        lines += section("7. OUTPUTS")

        for path in (
            WINNER_HISTORY_PATH,
            WINNER_PERSISTENCE_PATH,
            TRANSITION_PATH,
            SECTOR_PERSISTENCE_PATH,
            SECTOR_PANEL_PATH,
            SYNC_PATH,
            REGRESSION_PATH,
            RESIDUAL_PANEL_PATH,
            RAW_CORR_PATH,
            ACTIVE_CORR_PATH,
            RESIDUAL_CORR_PATH,
            PCA_PATH,
            PCA_LOADINGS_PATH,
            COMMONALITY_PATH,
        ):
            lines.append(
                str(path.relative_to(ROOT))
            )

        lines += [
            "",
            "POST_H2_WINNER_COMMONALITY_PHASE1_COMPLETE",
        ]

        cursor.close()

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )
    print(
        report,
        end="",
    )
    print(
        f"Report saved: {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()
