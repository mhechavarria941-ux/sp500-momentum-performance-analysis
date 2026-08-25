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

SCRIPT_VERSION = "2026-08-24-v1-post-h2-commonality-driver-audit"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXP_DIR = ROOT / "reports" / "exploratory"

PHASE1_RESIDUAL_PANEL_PATH = EXP_DIR / "post_h2_winner_residual_panel.csv"
PHASE1_COMMONALITY_PATH = EXP_DIR / "post_h2_winner_commonality_factor.csv"

SECURITY_MONTH_PATH = EXP_DIR / "post_h2_commonality_security_month_contributions.csv"
SECURITY_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_security_contributions.csv"
MONTH_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_month_drivers.csv"
SECTOR_VARIANCE_PATH = EXP_DIR / "post_h2_commonality_sector_variance_contributions.csv"
PAIRWISE_PATH = EXP_DIR / "post_h2_commonality_residual_pairwise_correlations.csv"
PC1_SCORE_PATH = EXP_DIR / "post_h2_commonality_pc1_scores.csv"
CONCENTRATION_PATH = EXP_DIR / "post_h2_commonality_concentration_summary.csv"

AUDIT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "post_h2_commonality_driver_phase2_integrity_audit.txt"
)

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
    rule = "=" * 108
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


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        PHASE1_RESIDUAL_PANEL_PATH,
        PHASE1_COMMONALITY_PATH,
        SECURITY_MONTH_PATH,
        SECURITY_SUMMARY_PATH,
        MONTH_SUMMARY_PATH,
        SECTOR_VARIANCE_PATH,
        PAIRWISE_PATH,
        PC1_SCORE_PATH,
        CONCENTRATION_PATH,
    ]
    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Missing Phase 2 output(s): " + ", ".join(missing)
        )

    lines = section(
        "POST-H2 COMMONALITY DRIVER PHASE 2 INTEGRITY AUDIT"
    )
    lines += [
        "Mode: Azure SQL READ-ONLY + local exact-decomposition verification",
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
                f"core.{table}={actual:,}; expected {expected:,}.",
            )

        lines += section("2. EXACT CONTRIBUTION RECONSTRUCTION")

        detail = pd.read_csv(SECURITY_MONTH_PATH)
        residual_panel = pd.read_csv(
            PHASE1_RESIDUAL_PANEL_PATH,
            index_col=0,
        )
        phase1_factor = pd.read_csv(
            PHASE1_COMMONALITY_PATH
        )

        detail["analysis_month_number"] = pd.to_numeric(
            detail["analysis_month_number"],
            errors="raise",
        ).astype(int)
        residual_panel.index = residual_panel.index.astype(int)
        phase1_factor["analysis_month_number"] = pd.to_numeric(
            phase1_factor["analysis_month_number"],
            errors="raise",
        ).astype(int)

        reconstructed_sector = (
            detail.groupby(
                [
                    "analysis_month_number",
                    "gics_sector",
                ]
            )["sector_residual_contribution"]
            .sum()
            .unstack("gics_sector")
            .reindex(columns=CANONICAL_SECTORS)
            .sort_index()
        )

        phase1_residual = (
            residual_panel[
                CANONICAL_SECTORS
            ]
            .sort_index()
            .astype(float)
        )

        check(
            reconstructed_sector.shape == (59, 11),
            "Security contributions reconstruct a 59 x 11 sector residual panel.",
            f"Reconstructed sector panel shape={reconstructed_sector.shape}.",
        )

        sector_max_error = float(
            np.max(
                np.abs(
                    reconstructed_sector.to_numpy(dtype=float)
                    - phase1_residual.to_numpy(dtype=float)
                )
            )
        )

        check(
            sector_max_error <= 1e-10,
            (
                "Security contributions reconstruct every Phase 1 sector "
                f"residual (max error {sector_max_error:.3e})."
            ),
            f"Sector residual reconstruction max error={sector_max_error:.3e}.",
        )

        reconstructed_factor = (
            detail.groupby(
                "analysis_month_number"
            )["aggregate_commonality_contribution"]
            .sum()
            .sort_index()
        )

        stored_factor = (
            phase1_factor
            .set_index(
                "analysis_month_number"
            )[
                "commonality_factor_equal_weight_residual"
            ]
            .sort_index()
            .astype(float)
        )

        factor_max_error = float(
            np.max(
                np.abs(
                    reconstructed_factor.to_numpy(dtype=float)
                    - stored_factor.to_numpy(dtype=float)
                )
            )
        )

        check(
            factor_max_error <= 1e-10,
            (
                "Security contributions reconstruct every Phase 1 aggregate "
                f"commonality observation (max error {factor_max_error:.3e})."
            ),
            f"Aggregate factor reconstruction max error={factor_max_error:.3e}.",
        )

        lines += section("3. SECURITY / MONTH / SECTOR SUMMARY CONTROLS")

        security = pd.read_csv(SECURITY_SUMMARY_PATH)
        months = pd.read_csv(MONTH_SUMMARY_PATH)
        sector_variance = pd.read_csv(SECTOR_VARIANCE_PATH)
        pairwise = pd.read_csv(PAIRWISE_PATH)
        pc1 = pd.read_csv(PC1_SCORE_PATH)
        concentration = pd.read_csv(CONCENTRATION_PATH)

        check(
            not security.duplicated(
                [
                    "security_key",
                    "project_ticker",
                ]
            ).any(),
            "Security summary contains one row per security/ticker.",
            "Security summary contains duplicate security/ticker rows.",
        )

        absolute_share_sum = float(
            security[
                "share_of_total_absolute_commonality_contribution"
            ].sum()
        )
        check(
            math.isclose(
                absolute_share_sum,
                1.0,
                rel_tol=1e-10,
                abs_tol=1e-10,
            ),
            "Security absolute-contribution shares sum to 1.",
            f"Security absolute-contribution shares sum to {absolute_share_sum}.",
        )

        check(
            len(months) == 59
            and months["analysis_month_number"].nunique() == 59,
            "Month-driver output contains exactly 59 observable months.",
            f"Month-driver rows={len(months)}.",
        )

        check(
            set(months["positive_residual_sector_count"].astype(int)).issubset(
                set(range(0, 12))
            ),
            "Positive residual-sector counts are all in [0, 11].",
            "Invalid positive residual-sector count detected.",
        )

        variance_share_sum = float(
            sector_variance[
                "share_of_commonality_factor_variance"
            ].sum()
        )
        check(
            len(sector_variance) == 11
            and math.isclose(
                variance_share_sum,
                1.0,
                rel_tol=1e-10,
                abs_tol=1e-10,
            ),
            "Sector variance contribution output has 11 rows and sums to 1.",
            (
                f"Sector variance rows={len(sector_variance)}, "
                f"share sum={variance_share_sum}."
            ),
        )

        check(
            len(pairwise) == 55,
            "Residual pairwise network contains 11 choose 2 = 55 sector pairs.",
            f"Residual pair rows={len(pairwise)}, expected 55.",
        )

        check(
            len(pc1) == 59
            and pc1["analysis_month_number"].nunique() == 59,
            "Residual PC1 score output contains exactly 59 months.",
            f"Residual PC1 rows={len(pc1)}.",
        )

        expected_metrics = {
            "top_10_security_absolute_contribution_share",
            "top_25_security_absolute_contribution_share",
            "security_absolute_contribution_hhi",
            "top_10_month_absolute_factor_share",
            "top_3_sector_absolute_variance_share",
            "residual_factor_pc1_correlation",
        }

        check(
            set(concentration["metric"]) == expected_metrics,
            "Concentration output contains the six defined exploratory metrics.",
            "Concentration metric set is incomplete.",
        )

        lines += section("4. FINAL GATE")

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
                "POST_H2_COMMONALITY_DRIVER_PHASE2_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
            for number, failure in enumerate(failures, start=1):
                lines.append(f"{number}. {failure}")
        else:
            lines += [
                "POST_H2_COMMONALITY_DRIVER_PHASE2_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                "Exact security -> sector -> aggregate commonality decomposition verified.",
                "Azure SQL modifications performed: 0",
                "Core rows modified: 0",
                "H1/H2 conclusions modified: 0",
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
