from __future__ import annotations

import math
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-post-h2-winner-commonality-audit"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

REPORT_DIR = ROOT / "reports" / "exploratory"

WINNER_HISTORY_PATH = REPORT_DIR / "post_h2_winner_membership_history.csv"
WINNER_PERSISTENCE_PATH = REPORT_DIR / "post_h2_winner_persistence_by_security.csv"
TRANSITION_PATH = REPORT_DIR / "post_h2_winner_transition_by_sector_month.csv"
SECTOR_PANEL_PATH = REPORT_DIR / "post_h2_sector_winner_return_panel.csv"
SYNC_PATH = REPORT_DIR / "post_h2_winner_synchrony_monthly.csv"
REGRESSION_PATH = REPORT_DIR / "post_h2_winner_market_sector_regressions.csv"
RESIDUAL_PANEL_PATH = REPORT_DIR / "post_h2_winner_residual_panel.csv"
RAW_CORR_PATH = REPORT_DIR / "post_h2_winner_raw_correlation_matrix.csv"
ACTIVE_CORR_PATH = REPORT_DIR / "post_h2_winner_sector_active_correlation_matrix.csv"
RESIDUAL_CORR_PATH = REPORT_DIR / "post_h2_winner_residual_correlation_matrix.csv"
PCA_PATH = REPORT_DIR / "post_h2_winner_pca_summary.csv"
COMMONALITY_PATH = REPORT_DIR / "post_h2_winner_commonality_factor.csv"
AUDIT_PATH = ROOT / "reports" / "data_quality" / "post_h2_winner_commonality_integrity_audit.txt"

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

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}


def section(title: str) -> list[str]:
    rule = "=" * 104
    return [rule, title, rule]


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


def connect_with_retry(server, database, username, password):
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
            time.sleep(10)

    raise RuntimeError("Connection retry loop ended unexpectedly.")


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def average_pairwise_correlation(corr: pd.DataFrame) -> float:
    matrix = corr.to_numpy(dtype=float)
    upper = matrix[np.triu_indices(matrix.shape[0], k=1)]
    return float(np.mean(upper))


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        WINNER_HISTORY_PATH,
        WINNER_PERSISTENCE_PATH,
        TRANSITION_PATH,
        SECTOR_PANEL_PATH,
        SYNC_PATH,
        REGRESSION_PATH,
        RESIDUAL_PANEL_PATH,
        RAW_CORR_PATH,
        ACTIVE_CORR_PATH,
        RESIDUAL_CORR_PATH,
        PCA_PATH,
        COMMONALITY_PATH,
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing exploratory output(s): " + ", ".join(missing)
        )

    lines = section(
        "POST-H2 WINNER COMMONALITY PHASE 1 INTEGRITY AUDIT"
    )
    lines += [
        "Mode: Azure SQL READ-ONLY + local output verification",
        "H1/H2 conclusion changes permitted: NO",
        "Azure SQL modifications performed: 0",
        "",
    ]

    failures: list[str] = []
    passed = 0
    connection = None

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if condition:
            lines.append(f"PASS: {success}")
            passed += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    try:
        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        cursor = connection.cursor()

        lines += section("1. CORE PRESERVATION")

        for table, expected in CORE_COUNTS.items():
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            check(
                actual == expected,
                f"core.{table} remains {expected:,} rows.",
                f"core.{table}={actual:,}, expected {expected:,}.",
            )

        lines += section("2. WINNER MEMBERSHIP / TRANSITION OUTPUTS")

        history = pd.read_csv(WINNER_HISTORY_PATH)
        persistence = pd.read_csv(WINNER_PERSISTENCE_PATH)
        transitions = pd.read_csv(TRANSITION_PATH)

        check(
            history["analysis_month_number"].nunique() == 60,
            "Winner membership history spans all 60 ranking months.",
            "Winner membership history does not span 60 months.",
        )
        check(
            set(history["gics_sector"]) == set(CANONICAL_SECTORS),
            "Winner membership history contains all 11 canonical sectors.",
            "Winner membership history sector set is incomplete.",
        )
        check(
            len(transitions) == 649,
            "Winner transition output contains 59 x 11 = 649 rows.",
            f"Winner transition rows={len(transitions)}, expected 649.",
        )
        check(
            transitions[
                [
                    "current_winner_retention",
                    "previous_winner_survival",
                    "jaccard_similarity",
                ]
            ].apply(
                lambda column: column.between(0.0, 1.0).all()
            ).all(),
            "All Winner persistence rates are bounded in [0, 1].",
            "At least one Winner persistence rate is outside [0, 1].",
        )
        check(
            not persistence.duplicated(
                [
                    "security_key",
                    "project_ticker",
                ]
            ).any(),
            (
                "Winner persistence output contains exactly one row per "
                "security/ticker across its full point-in-time sector history."
            ),
            "Winner persistence output contains duplicate security/ticker rows.",
        )

        check(
            (
                persistence["winner_months"]
                <= persistence["eligible_months"]
            ).all(),
            "No security has more Winner months than eligible months.",
            "At least one security has Winner months > eligible months.",
        )

        check(
            {
                "gics_sectors_seen",
                "winner_sector_count",
                "latest_winner_sector",
            }.issubset(
                persistence.columns
            ),
            (
                "Winner persistence preserves sector-history metadata without "
                "splitting a security's persistence record."
            ),
            "Winner persistence sector-history metadata is incomplete.",
        )
        check(
            (
                persistence["winner_share_of_eligible_months"]
                .between(0.0, 1.0)
            ).all(),
            "All security Winner-share values are bounded in [0, 1].",
            "At least one security Winner-share value is outside [0, 1].",
        )

        lines += section("3. RETURN PANELS / RESIDUALIZATION")

        panel = pd.read_csv(SECTOR_PANEL_PATH)
        sync = pd.read_csv(SYNC_PATH)
        regressions = pd.read_csv(REGRESSION_PATH)
        residual_panel = pd.read_csv(
            RESIDUAL_PANEL_PATH,
            index_col=0,
        )

        check(
            len(panel) == 649,
            "Winner sector return panel contains 59 x 11 = 649 rows.",
            f"Winner sector return panel rows={len(panel)}, expected 649.",
        )
        check(
            len(sync) == 59,
            "Winner synchrony output contains 59 observable months.",
            f"Winner synchrony rows={len(sync)}, expected 59.",
        )
        check(
            len(regressions) == 11,
            "Residualization output contains one regression per GICS sector.",
            f"Residualization rows={len(regressions)}, expected 11.",
        )
        check(
            residual_panel.shape == (59, 11),
            "Residual Winner panel has shape 59 x 11.",
            f"Residual panel shape={residual_panel.shape}, expected (59, 11).",
        )
        check(
            not residual_panel.isna().any().any(),
            "Residual Winner panel has no missing values.",
            "Residual Winner panel contains missing values.",
        )
        check(
            (
                regressions["residual_mean"].abs()
                < 1e-10
            ).all(),
            "Every in-sample sector residual series has mean approximately zero.",
            "At least one sector residual mean is not approximately zero.",
        )

        lines += section("4. CORRELATION / PCA / COMMONALITY CONTROLS")

        raw_corr = pd.read_csv(
            RAW_CORR_PATH,
            index_col=0,
        )
        active_corr = pd.read_csv(
            ACTIVE_CORR_PATH,
            index_col=0,
        )
        residual_corr = pd.read_csv(
            RESIDUAL_CORR_PATH,
            index_col=0,
        )
        pca = pd.read_csv(PCA_PATH)
        commonality = pd.read_csv(COMMONALITY_PATH)

        for name, corr in (
            ("raw", raw_corr),
            ("active", active_corr),
            ("residual", residual_corr),
        ):
            check(
                corr.shape == (11, 11),
                f"{name} correlation matrix is 11 x 11.",
                f"{name} correlation matrix shape={corr.shape}.",
            )
            check(
                np.allclose(
                    corr.to_numpy(dtype=float),
                    corr.to_numpy(dtype=float).T,
                    atol=1e-12,
                    rtol=1e-12,
                ),
                f"{name} correlation matrix is symmetric.",
                f"{name} correlation matrix is not symmetric.",
            )
            check(
                np.allclose(
                    np.diag(corr.to_numpy(dtype=float)),
                    1.0,
                    atol=1e-12,
                    rtol=1e-12,
                ),
                f"{name} correlation matrix diagonal equals 1.",
                f"{name} correlation matrix diagonal differs from 1.",
            )

        check(
            set(pca["stage"]) == {
                "RAW_WINNER",
                "ACTIVE_VS_SECTOR",
                "RESIDUAL_SPY_PLUS_SECTOR",
            },
            "PCA output contains raw, sector-active, and residual stages.",
            "PCA stage set is incomplete.",
        )

        pca_ok = True
        for stage, group in pca.groupby("stage"):
            total = float(group["explained_variance_ratio"].sum())
            if not math.isclose(
                total,
                1.0,
                rel_tol=1e-10,
                abs_tol=1e-10,
            ):
                pca_ok = False

        check(
            pca_ok,
            "PCA explained-variance ratios sum to 1 for every stage.",
            "At least one PCA stage does not sum to 1.",
        )

        reconstructed_commonality = (
            residual_panel
            .mean(axis=1)
            .to_numpy(dtype=float)
        )
        stored_commonality = pd.to_numeric(
            commonality[
                "commonality_factor_equal_weight_residual"
            ],
            errors="raise",
        ).to_numpy(dtype=float)

        check(
            np.allclose(
                reconstructed_commonality,
                stored_commonality,
                atol=1e-12,
                rtol=1e-12,
            ),
            "Stored residual commonality factor equals the mean of 11 sector residuals.",
            "Residual commonality factor does not reconstruct exactly.",
        )

        lines += [
            f"Raw average pairwise correlation: {average_pairwise_correlation(raw_corr):.4f}",
            f"Sector-active average pairwise correlation: {average_pairwise_correlation(active_corr):.4f}",
            f"Residual average pairwise correlation: {average_pairwise_correlation(residual_corr):.4f}",
        ]

        lines += section("5. FINAL GATE")

        for table, expected in CORE_COUNTS.items():
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            check(
                actual == expected,
                f"core.{table} final population remains {expected:,}.",
                f"core.{table} final population changed to {actual:,}.",
            )

        if failures:
            lines += [
                "POST_H2_WINNER_COMMONALITY_PHASE1_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
            for number, failure in enumerate(failures, start=1):
                lines.append(f"{number}. {failure}")
        else:
            lines += [
                "POST_H2_WINNER_COMMONALITY_PHASE1_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                "Azure SQL modifications performed: 0",
                "Core rows modified: 0",
                "H1/H2 conclusions modified: 0",
                (
                    "Exploratory Winner persistence, synchrony, residualization, "
                    "correlation, PCA, and commonality outputs are internally consistent."
                ),
            ]

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"Report saved: {AUDIT_PATH}")


if __name__ == "__main__":
    main()
