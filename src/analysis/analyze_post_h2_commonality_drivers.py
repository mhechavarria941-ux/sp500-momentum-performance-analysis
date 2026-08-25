from __future__ import annotations

import math
import os
import time
from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-post-h2-commonality-driver-attribution"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXP_DIR = ROOT / "reports" / "exploratory"

PHASE1_PANEL_PATH = EXP_DIR / "post_h2_sector_winner_return_panel.csv"
PHASE1_REGRESSION_PATH = EXP_DIR / "post_h2_winner_market_sector_regressions.csv"
PHASE1_RESIDUAL_PANEL_PATH = EXP_DIR / "post_h2_winner_residual_panel.csv"
PHASE1_COMMONALITY_PATH = EXP_DIR / "post_h2_winner_commonality_factor.csv"

REPORT_PATH = EXP_DIR / "post_h2_commonality_driver_analysis.txt"
SECURITY_MONTH_PATH = EXP_DIR / "post_h2_commonality_security_month_contributions.csv"
SECURITY_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_security_contributions.csv"
MONTH_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_month_drivers.csv"
TOP_MONTH_SECURITY_PATH = EXP_DIR / "post_h2_commonality_top_month_security_contributors.csv"
SECTOR_VARIANCE_PATH = EXP_DIR / "post_h2_commonality_sector_variance_contributions.csv"
PAIRWISE_PATH = EXP_DIR / "post_h2_commonality_residual_pairwise_correlations.csv"
PC1_SCORE_PATH = EXP_DIR / "post_h2_commonality_pc1_scores.csv"
CONCENTRATION_PATH = EXP_DIR / "post_h2_commonality_concentration_summary.csv"

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

EXPECTED_RETURN_MONTHS = 59
EXPECTED_SECTOR_MONTHS = 649
N_SECTORS = 11

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}


def rule() -> str:
    return "=" * 122


def section(title: str) -> list[str]:
    return ["", rule(), title, rule()]


def pct(value: float, digits: int = 3) -> str:
    return f"{100.0 * float(value):.{digits}f}%"


def num(value: float, digits: int = 4) -> str:
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


def residual_pc1_scores(
    residual_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = residual_panel[CANONICAL_SECTORS].copy()

    standardized = (
        ordered - ordered.mean(axis=0)
    ) / ordered.std(axis=0, ddof=1)

    corr = standardized.corr().to_numpy(dtype=float)
    eigenvalues, eigenvectors = np.linalg.eigh(corr)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    pc1 = eigenvectors[:, 0].copy()

    if float(np.mean(pc1)) < 0:
        pc1 *= -1.0

    raw_score = standardized.to_numpy(dtype=float) @ pc1
    score_z = (
        raw_score - raw_score.mean()
    ) / raw_score.std(ddof=1)

    score_frame = pd.DataFrame(
        {
            "analysis_month_number": ordered.index.astype(int),
            "pc1_score": raw_score,
            "pc1_score_z": score_z,
        }
    )

    loading_frame = pd.DataFrame(
        {
            "gics_sector": CANONICAL_SECTORS,
            "pc1_loading": pc1,
            "pc1_explained_variance_ratio": (
                float(eigenvalues[0] / eigenvalues.sum())
            ),
        }
    )

    return score_frame, loading_frame


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required_phase1 = [
        PHASE1_PANEL_PATH,
        PHASE1_REGRESSION_PATH,
        PHASE1_RESIDUAL_PANEL_PATH,
        PHASE1_COMMONALITY_PATH,
    ]
    missing = [
        str(path)
        for path in required_phase1
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Missing Phase 1 exploratory output(s): " + ", ".join(missing)
        )

    EXP_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        rule(),
        "POST-H2 EXPLORATORY WINNER COMMONALITY — PHASE 2 DRIVER ATTRIBUTION",
        rule(),
        "Status: EXPLORATORY / NON-CONFIRMATORY",
        "H1 conclusion modified: NO",
        "H2 conclusion modified: NO",
        "Azure SQL mode: READ-ONLY",
        "",
        "Goal: identify the months, sectors, and Winner securities that drive the residual cross-sector commonality observed in Phase 1.",
        "",
        "Exact additive decomposition:",
        "sector residual_t = sum_i [sector Winner weight_i,t * (security return_i,t - fitted sector Winner return_t)]",
        "aggregate commonality_t = (1/11) * sum_sector(sector residual_t)",
        "security aggregate contribution_i,t = (1/11) * sector Winner weight_i,t * (security return_i,t - fitted sector Winner return_t)",
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

        winner_security = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                target_holding_end_date AS return_period_end_date,
                security_key,
                project_ticker,
                gics_sector,
                sector_equal_weight,
                forward_return_1m
            FROM analytics.v_h2_security_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1
              AND sector_momentum_portfolio = 'WINNER'
            ORDER BY analysis_month_number, gics_sector, security_key;
            """,
        )

        winner_security["analysis_month_number"] = pd.to_numeric(
            winner_security["analysis_month_number"],
            errors="raise",
        ).astype(int)
        winner_security["ranking_month_end_date"] = pd.to_datetime(
            winner_security["ranking_month_end_date"],
            errors="raise",
        )
        winner_security["return_period_end_date"] = pd.to_datetime(
            winner_security["return_period_end_date"],
            errors="raise",
        )
        winner_security["sector_equal_weight"] = pd.to_numeric(
            winner_security["sector_equal_weight"],
            errors="raise",
        )
        winner_security["forward_return_1m"] = pd.to_numeric(
            winner_security["forward_return_1m"],
            errors="raise",
        )

        for column in (
            "security_key",
            "project_ticker",
            "gics_sector",
        ):
            winner_security[column] = (
                winner_security[column].astype(str).str.strip()
            )

        if winner_security["analysis_month_number"].nunique() != EXPECTED_RETURN_MONTHS:
            raise RuntimeError("Complete Winner security rows do not span 59 months.")

        sector_group_count = (
            winner_security[
                [
                    "analysis_month_number",
                    "gics_sector",
                ]
            ]
            .drop_duplicates()
            .shape[0]
        )
        if sector_group_count != EXPECTED_SECTOR_MONTHS:
            raise RuntimeError(
                f"Winner security sector-month groups={sector_group_count}, "
                f"expected {EXPECTED_SECTOR_MONTHS}."
            )

        panel = pd.read_csv(PHASE1_PANEL_PATH)
        regressions = pd.read_csv(PHASE1_REGRESSION_PATH)
        phase1_commonality = pd.read_csv(PHASE1_COMMONALITY_PATH)
        residual_panel = pd.read_csv(
            PHASE1_RESIDUAL_PANEL_PATH,
            index_col=0,
        )

        panel["analysis_month_number"] = pd.to_numeric(
            panel["analysis_month_number"],
            errors="raise",
        ).astype(int)
        phase1_commonality["analysis_month_number"] = pd.to_numeric(
            phase1_commonality["analysis_month_number"],
            errors="raise",
        ).astype(int)
        residual_panel.index = residual_panel.index.astype(int)

        if len(panel) != EXPECTED_SECTOR_MONTHS:
            raise RuntimeError(
                f"Phase 1 sector panel rows={len(panel)}, expected {EXPECTED_SECTOR_MONTHS}."
            )
        if len(regressions) != N_SECTORS:
            raise RuntimeError(
                f"Phase 1 regression rows={len(regressions)}, expected 11."
            )
        if residual_panel.shape != (EXPECTED_RETURN_MONTHS, N_SECTORS):
            raise RuntimeError(
                f"Phase 1 residual panel shape={residual_panel.shape}, expected (59, 11)."
            )

        lines += [
            f"PASS: complete Winner security returns span {EXPECTED_RETURN_MONTHS} months.",
            f"PASS: Winner security source contains {sector_group_count} sector-month groups.",
            f"PASS: Phase 1 residual panel shape = {residual_panel.shape}.",
        ]

        lines += section("2. EXACT SECURITY-LEVEL CONTRIBUTION DECOMPOSITION")

        needed_panel = panel[
            [
                "analysis_month_number",
                "gics_sector",
                "spy_return",
                "sector_equal_weight_return",
                "winner_sector_return",
            ]
        ].copy()

        needed_reg = regressions[
            [
                "gics_sector",
                "alpha_monthly",
                "beta_spy",
                "beta_sector_equal_weight",
            ]
        ].copy()

        detail = (
            winner_security
            .merge(
                needed_panel,
                on=[
                    "analysis_month_number",
                    "gics_sector",
                ],
                how="left",
                validate="many_to_one",
            )
            .merge(
                needed_reg,
                on="gics_sector",
                how="left",
                validate="many_to_one",
            )
        )

        required_numeric = [
            "spy_return",
            "sector_equal_weight_return",
            "winner_sector_return",
            "alpha_monthly",
            "beta_spy",
            "beta_sector_equal_weight",
        ]
        if detail[required_numeric].isna().any().any():
            raise RuntimeError("Security contribution panel has missing Phase 1 controls.")

        detail["fitted_sector_winner_return"] = (
            detail["alpha_monthly"]
            + detail["beta_spy"] * detail["spy_return"]
            + detail["beta_sector_equal_weight"]
            * detail["sector_equal_weight_return"]
        )

        detail["security_return_minus_sector_fitted"] = (
            detail["forward_return_1m"]
            - detail["fitted_sector_winner_return"]
        )

        detail["sector_residual_contribution"] = (
            detail["sector_equal_weight"]
            * detail["security_return_minus_sector_fitted"]
        )

        detail["aggregate_commonality_contribution"] = (
            detail["sector_residual_contribution"]
            / float(N_SECTORS)
        )

        detail["absolute_commonality_contribution"] = (
            detail["aggregate_commonality_contribution"].abs()
        )

        # Sector-level exact reconstruction.
        reconstructed_sector = (
            detail.groupby(
                [
                    "analysis_month_number",
                    "gics_sector",
                ],
                as_index=False,
            )["sector_residual_contribution"]
            .sum()
        )

        phase1_sector_long = (
            residual_panel
            .reset_index()
            .melt(
                id_vars=[
                    residual_panel.index.name
                    if residual_panel.index.name is not None
                    else "index"
                ],
                var_name="gics_sector",
                value_name="phase1_sector_residual",
            )
        )

        index_column = phase1_sector_long.columns[0]
        phase1_sector_long = phase1_sector_long.rename(
            columns={
                index_column: "analysis_month_number"
            }
        )
        phase1_sector_long["analysis_month_number"] = pd.to_numeric(
            phase1_sector_long["analysis_month_number"],
            errors="raise",
        ).astype(int)

        sector_check = reconstructed_sector.merge(
            phase1_sector_long,
            on=[
                "analysis_month_number",
                "gics_sector",
            ],
            how="inner",
            validate="one_to_one",
        )

        sector_max_error = float(
            (
                sector_check["sector_residual_contribution"]
                - sector_check["phase1_sector_residual"]
            )
            .abs()
            .max()
        )

        if sector_max_error > 1e-10:
            raise RuntimeError(
                f"Security decomposition does not reconstruct sector residuals; "
                f"max error={sector_max_error:.3e}."
            )

        reconstructed_month = (
            detail.groupby(
                "analysis_month_number",
                as_index=False,
            )["aggregate_commonality_contribution"]
            .sum()
            .rename(
                columns={
                    "aggregate_commonality_contribution":
                    "reconstructed_commonality_factor"
                }
            )
        )

        phase1_factor = phase1_commonality[
            [
                "analysis_month_number",
                "commonality_factor_equal_weight_residual",
            ]
        ].copy()

        factor_check = reconstructed_month.merge(
            phase1_factor,
            on="analysis_month_number",
            how="inner",
            validate="one_to_one",
        )

        factor_max_error = float(
            (
                factor_check["reconstructed_commonality_factor"]
                - factor_check[
                    "commonality_factor_equal_weight_residual"
                ]
            )
            .abs()
            .max()
        )

        if factor_max_error > 1e-10:
            raise RuntimeError(
                f"Security decomposition does not reconstruct commonality factor; "
                f"max error={factor_max_error:.3e}."
            )

        detail.to_csv(
            SECURITY_MONTH_PATH,
            index=False,
        )

        lines += [
            f"PASS: sector residual reconstruction max absolute error = {sector_max_error:.3e}.",
            f"PASS: aggregate commonality reconstruction max absolute error = {factor_max_error:.3e}.",
            f"Security-month Winner contribution rows: {len(detail):,}.",
        ]

        lines += section("3. SECURITY-LEVEL DRIVERS")

        security_summary = (
            detail.groupby(
                [
                    "security_key",
                    "project_ticker",
                ],
                as_index=False,
            )
            .agg(
                gics_sectors_seen=(
                    "gics_sector",
                    lambda values: " | ".join(sorted(set(map(str, values)))),
                ),
                winner_return_months=(
                    "analysis_month_number",
                    "nunique",
                ),
                cumulative_signed_commonality_contribution=(
                    "aggregate_commonality_contribution",
                    "sum",
                ),
                cumulative_absolute_commonality_contribution=(
                    "absolute_commonality_contribution",
                    "sum",
                ),
                mean_signed_commonality_contribution=(
                    "aggregate_commonality_contribution",
                    "mean",
                ),
                max_positive_month_contribution=(
                    "aggregate_commonality_contribution",
                    "max",
                ),
                max_negative_month_contribution=(
                    "aggregate_commonality_contribution",
                    "min",
                ),
            )
        )

        total_absolute = float(
            security_summary[
                "cumulative_absolute_commonality_contribution"
            ].sum()
        )

        security_summary["share_of_total_absolute_commonality_contribution"] = (
            security_summary[
                "cumulative_absolute_commonality_contribution"
            ]
            / total_absolute
        )

        security_summary["absolute_signed_contribution"] = (
            security_summary[
                "cumulative_signed_commonality_contribution"
            ].abs()
        )

        security_summary = security_summary.sort_values(
            [
                "cumulative_absolute_commonality_contribution",
                "absolute_signed_contribution",
                "project_ticker",
            ],
            ascending=[
                False,
                False,
                True,
            ],
        ).reset_index(drop=True)

        security_summary[
            "cumulative_share_of_total_absolute_commonality_contribution"
        ] = (
            security_summary[
                "share_of_total_absolute_commonality_contribution"
            ].cumsum()
        )

        security_summary.to_csv(
            SECURITY_SUMMARY_PATH,
            index=False,
        )

        top10_abs_share = float(
            security_summary.head(10)[
                "share_of_total_absolute_commonality_contribution"
            ].sum()
        )
        top25_abs_share = float(
            security_summary.head(25)[
                "share_of_total_absolute_commonality_contribution"
            ].sum()
        )

        security_hhi = float(
            np.sum(
                np.square(
                    security_summary[
                        "share_of_total_absolute_commonality_contribution"
                    ].to_numpy(dtype=float)
                )
            )
        )

        lines += [
            f"Unique Winner securities in complete return months: {len(security_summary):,}",
            f"Top 10 securities' share of absolute commonality contribution: {pct(top10_abs_share)}",
            f"Top 25 securities' share of absolute commonality contribution: {pct(top25_abs_share)}",
            f"Security absolute-contribution HHI: {num(security_hhi, 5)}",
            "",
            "Top 15 securities by cumulative absolute commonality contribution:",
        ]

        for row in security_summary.head(15).itertuples(index=False):
            lines.append(
                f"{row.project_ticker:<8} | "
                f"Months {int(row.winner_return_months):>2} | "
                f"Abs share {pct(row.share_of_total_absolute_commonality_contribution)} | "
                f"Signed cumulative {pct(row.cumulative_signed_commonality_contribution, 4)} | "
                f"{row.gics_sectors_seen}"
            )

        lines += section("4. MONTH-LEVEL DRIVERS AND SYNCHRONY")

        month_sector = reconstructed_sector.merge(
            phase1_sector_long,
            on=[
                "analysis_month_number",
                "gics_sector",
            ],
            how="inner",
            validate="one_to_one",
        )

        month_sector["absolute_sector_residual"] = (
            month_sector["phase1_sector_residual"].abs()
        )

        month_sector_abs_total = (
            month_sector.groupby(
                "analysis_month_number"
            )["absolute_sector_residual"]
            .sum()
        )

        month_sector_max_abs = (
            month_sector.groupby(
                "analysis_month_number"
            )["absolute_sector_residual"]
            .max()
        )

        month_sector_dominance = (
            month_sector_max_abs
            / month_sector_abs_total
        )

        month_dates = (
            detail.groupby(
                "analysis_month_number",
                as_index=False,
            )
            .agg(
                ranking_month_end_date=(
                    "ranking_month_end_date",
                    "first",
                ),
                return_period_end_date=(
                    "return_period_end_date",
                    "first",
                ),
            )
        )

        month_summary = (
            phase1_commonality
            .merge(
                month_dates,
                on="analysis_month_number",
                how="left",
                validate="one_to_one",
            )
        )

        month_summary[
            "absolute_commonality_factor"
        ] = month_summary[
            "commonality_factor_equal_weight_residual"
        ].abs()

        month_summary[
            "largest_absolute_sector_share_of_monthly_residual_activity"
        ] = month_summary[
            "analysis_month_number"
        ].map(
            month_sector_dominance.to_dict()
        )

        month_summary = month_summary.sort_values(
            [
                "absolute_commonality_factor",
                "analysis_month_number",
            ],
            ascending=[
                False,
                True,
            ],
        ).reset_index(drop=True)

        month_summary[
            "absolute_commonality_rank"
        ] = np.arange(
            1,
            len(month_summary) + 1,
        )

        month_summary.to_csv(
            MONTH_SUMMARY_PATH,
            index=False,
        )

        top_months = set(
            month_summary.head(10)[
                "analysis_month_number"
            ].astype(int)
        )

        top_month_security = detail[
            detail[
                "analysis_month_number"
            ].isin(top_months)
        ].copy()

        top_month_security[
            "within_month_absolute_rank"
        ] = (
            top_month_security.groupby(
                "analysis_month_number"
            )["absolute_commonality_contribution"]
            .rank(
                method="first",
                ascending=False,
            )
            .astype(int)
        )

        top_month_security = top_month_security[
            top_month_security[
                "within_month_absolute_rank"
            ] <= 15
        ].sort_values(
            [
                "analysis_month_number",
                "within_month_absolute_rank",
            ]
        )

        top_month_security.to_csv(
            TOP_MONTH_SECURITY_PATH,
            index=False,
        )

        lines += [
            "Top 10 months by absolute residual commonality factor:",
        ]

        for row in month_summary.head(10).itertuples(index=False):
            lines.append(
                f"Month {int(row.analysis_month_number):>2} | "
                f"Ranking {pd.Timestamp(row.ranking_month_end_date).date()} | "
                f"Factor {pct(row.commonality_factor_equal_weight_residual, 4)} | "
                f"Positive residual sectors {int(row.positive_residual_sector_count):>2}/11 | "
                f"Largest sector activity share {pct(row.largest_absolute_sector_share_of_monthly_residual_activity)}"
            )

        lines += section("5. SECTOR VARIANCE CONTRIBUTION TO COMMONALITY")

        factor = (
            phase1_commonality
            .set_index(
                "analysis_month_number"
            )[
                "commonality_factor_equal_weight_residual"
            ]
            .sort_index()
            .astype(float)
        )

        residual_ordered = residual_panel[
            CANONICAL_SECTORS
        ].sort_index().astype(float)

        factor_variance = float(
            np.var(
                factor.to_numpy(),
                ddof=1,
            )
        )

        if factor_variance <= 0:
            raise RuntimeError("Commonality factor variance is nonpositive.")

        sector_variance_rows = []

        for sector in CANONICAL_SECTORS:
            covariance = float(
                np.cov(
                    residual_ordered[sector].to_numpy(),
                    factor.to_numpy(),
                    ddof=1,
                )[0, 1]
            )

            additive_variance_contribution = (
                covariance / float(N_SECTORS)
            )
            variance_share = (
                additive_variance_contribution
                / factor_variance
            )

            sector_variance_rows.append(
                {
                    "gics_sector": sector,
                    "covariance_with_commonality_factor": covariance,
                    "additive_variance_contribution": additive_variance_contribution,
                    "share_of_commonality_factor_variance": variance_share,
                }
            )

        sector_variance = pd.DataFrame(
            sector_variance_rows
        ).sort_values(
            "share_of_commonality_factor_variance",
            ascending=False,
        )

        variance_share_sum = float(
            sector_variance[
                "share_of_commonality_factor_variance"
            ].sum()
        )

        if not math.isclose(
            variance_share_sum,
            1.0,
            rel_tol=1e-10,
            abs_tol=1e-10,
        ):
            raise RuntimeError(
                f"Sector variance shares do not sum to 1: {variance_share_sum}."
            )

        sector_variance.to_csv(
            SECTOR_VARIANCE_PATH,
            index=False,
        )

        lines += [
            "Sector shares of commonality-factor variance (additive covariance decomposition):",
        ]

        for row in sector_variance.itertuples(index=False):
            lines.append(
                f"{row.gics_sector:<26} | "
                f"Variance share {pct(row.share_of_commonality_factor_variance)}"
            )

        lines += section("6. RESIDUAL PAIRWISE NETWORK")

        pair_rows = []

        for sector_a, sector_b in combinations(
            CANONICAL_SECTORS,
            2,
        ):
            correlation = float(
                residual_ordered[
                    sector_a
                ].corr(
                    residual_ordered[
                        sector_b
                    ]
                )
            )

            pair_rows.append(
                {
                    "sector_a": sector_a,
                    "sector_b": sector_b,
                    "residual_correlation": correlation,
                    "absolute_residual_correlation": abs(correlation),
                }
            )

        pairwise = pd.DataFrame(
            pair_rows
        ).sort_values(
            [
                "absolute_residual_correlation",
                "residual_correlation",
            ],
            ascending=[
                False,
                False,
            ],
        )

        pairwise.to_csv(
            PAIRWISE_PATH,
            index=False,
        )

        lines += [
            "Top 10 residual sector-pair correlations by absolute magnitude:",
        ]

        for row in pairwise.head(10).itertuples(index=False):
            lines.append(
                f"{row.sector_a:<26} <-> {row.sector_b:<26} | "
                f"corr {num(row.residual_correlation)}"
            )

        lines += section("7. RESIDUAL PC1 MONTH SCORES")

        pc1_scores, pc1_loadings = residual_pc1_scores(
            residual_ordered
        )

        pc1_scores = pc1_scores.merge(
            month_dates,
            on="analysis_month_number",
            how="left",
            validate="one_to_one",
        )

        pc1_scores.to_csv(
            PC1_SCORE_PATH,
            index=False,
        )

        factor_pc1_corr = float(
            np.corrcoef(
                pc1_scores["pc1_score"].to_numpy(dtype=float),
                factor.loc[
                    pc1_scores[
                        "analysis_month_number"
                    ].astype(int)
                ].to_numpy(dtype=float),
            )[0, 1]
        )

        strongest_positive = pc1_scores.nlargest(
            5,
            "pc1_score_z",
        )
        strongest_negative = pc1_scores.nsmallest(
            5,
            "pc1_score_z",
        )

        lines += [
            f"Residual PC1 explained variance: {pct(float(pc1_loadings['pc1_explained_variance_ratio'].iloc[0]))}",
            f"Correlation of residual PC1 score with equal-weight residual commonality factor: {num(factor_pc1_corr)}",
            "",
            "Strongest positive residual-PC1 months:",
        ]

        for row in strongest_positive.itertuples(index=False):
            lines.append(
                f"Month {int(row.analysis_month_number):>2} | "
                f"Ranking {pd.Timestamp(row.ranking_month_end_date).date()} | "
                f"PC1 z {num(row.pc1_score_z)}"
            )

        lines.append("")
        lines.append("Strongest negative residual-PC1 months:")

        for row in strongest_negative.itertuples(index=False):
            lines.append(
                f"Month {int(row.analysis_month_number):>2} | "
                f"Ranking {pd.Timestamp(row.ranking_month_end_date).date()} | "
                f"PC1 z {num(row.pc1_score_z)}"
            )

        lines += section("8. CONCENTRATION SUMMARY")

        sector_variance_abs_share = (
            sector_variance[
                "share_of_commonality_factor_variance"
            ].abs()
        )
        top3_sector_variance_share = float(
            sector_variance_abs_share.nlargest(3).sum()
            / sector_variance_abs_share.sum()
        )

        month_abs_factor = month_summary[
            "absolute_commonality_factor"
        ]
        top10_month_abs_share = float(
            month_abs_factor.head(10).sum()
            / month_abs_factor.sum()
        )

        concentration = pd.DataFrame(
            [
                {
                    "metric": "top_10_security_absolute_contribution_share",
                    "value": top10_abs_share,
                },
                {
                    "metric": "top_25_security_absolute_contribution_share",
                    "value": top25_abs_share,
                },
                {
                    "metric": "security_absolute_contribution_hhi",
                    "value": security_hhi,
                },
                {
                    "metric": "top_10_month_absolute_factor_share",
                    "value": top10_month_abs_share,
                },
                {
                    "metric": "top_3_sector_absolute_variance_share",
                    "value": top3_sector_variance_share,
                },
                {
                    "metric": "residual_factor_pc1_correlation",
                    "value": factor_pc1_corr,
                },
            ]
        )

        concentration.to_csv(
            CONCENTRATION_PATH,
            index=False,
        )

        lines += [
            f"Top 10 securities / total absolute contribution: {pct(top10_abs_share)}",
            f"Top 25 securities / total absolute contribution: {pct(top25_abs_share)}",
            f"Top 10 months / total absolute factor magnitude: {pct(top10_month_abs_share)}",
            f"Top 3 sectors / total absolute variance-share magnitude: {pct(top3_sector_variance_share)}",
            f"Residual factor vs residual PC1 correlation: {num(factor_pc1_corr)}",
        ]

        lines += section("9. EXPLORATORY INTERPRETATION BOUNDARY")

        lines += [
            "This phase attributes the already-defined Phase 1 residual commonality; it does not create a new confirmatory effect.",
            "Security contributions are exact algebraic decompositions of sector Winner residuals using the Phase 1 in-sample regression coefficients.",
            "A security's contribution is not a causal attribution and is not an estimate of standalone alpha.",
            "Large cumulative absolute contribution can arise from repeated Winner membership, large idiosyncratic moves, or both.",
            "Sector variance shares may be negative because covariance contributions to a portfolio variance can be negative.",
            "PC1 scores measure the strongest residual co-movement direction and are not returns of a tradable portfolio.",
            "The next phase should use these ranked months/securities to characterize firm-level common traits and event/theme clustering.",
            "Narrative/attention variables should still be treated as a separate exploratory or preregistered hypothesis rather than retrofitted onto H2.",
        ]

        lines += section("10. OUTPUTS")

        for path in (
            SECURITY_MONTH_PATH,
            SECURITY_SUMMARY_PATH,
            MONTH_SUMMARY_PATH,
            TOP_MONTH_SECURITY_PATH,
            SECTOR_VARIANCE_PATH,
            PAIRWISE_PATH,
            PC1_SCORE_PATH,
            CONCENTRATION_PATH,
        ):
            lines.append(str(path.relative_to(ROOT)))

        lines += [
            "",
            "POST_H2_COMMONALITY_DRIVER_PHASE2_COMPLETE",
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
    print(report_text, end="")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
