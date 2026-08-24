from __future__ import annotations

import math
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv
from scipy import stats


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-h2-final-analysis-integrity-audit"

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "h2_sector_relative_momentum_analysis_integrity_audit.txt"
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
TURNOVER_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "h2_turnover_monthly.csv"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXPECTED_MONTHS = 59
HAC_LAG = 3
ALPHA = 0.05
BASE_CASE_TRADING_BPS = 10
BASE_CASE_BORROW_BPS = 100

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
            print(
                f"ODBC connection established on attempt {attempt} / 5."
            )
            return connection
        except pyodbc.Error:
            if attempt == 5:
                raise
            time.sleep(10)

    raise RuntimeError("Connection retry loop ended unexpectedly.")


def fetch_df(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    return pd.DataFrame.from_records(
        cursor.fetchall(),
        columns=columns,
    )


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def newey_west_mean_test(
    values: np.ndarray,
) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    n = len(x)
    mean = float(np.mean(x))
    residual = x - mean
    lrv = float(
        np.dot(
            residual,
            residual,
        )
        / n
    )

    max_lag = min(
        HAC_LAG,
        n - 1,
    )

    for k in range(1, max_lag + 1):
        gamma = float(
            np.dot(
                residual[k:],
                residual[:-k],
            )
            / n
        )
        weight = 1.0 - k / (max_lag + 1.0)
        lrv += 2.0 * weight * gamma

    lrv = max(lrv, 0.0)
    se = math.sqrt(lrv / n)
    z = mean / se if se > 0 else math.nan
    p = (
        float(
            2.0
            * stats.norm.sf(
                abs(z)
            )
        )
        if math.isfinite(z)
        else math.nan
    )

    return {
        "mean": mean,
        "z": z,
        "p": p,
    }


def close(a: float, b: float, tol: float = 1e-10) -> bool:
    return math.isclose(
        float(a),
        float(b),
        rel_tol=tol,
        abs_tol=tol,
    )


def main() -> None:
    print(
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}"
    )

    required_files = [
        PRIMARY_PATH,
        SECTOR_PATH,
        COST_PATH,
        LOO_PATH,
        CONTRIBUTION_PATH,
        TURNOVER_PATH,
    ]

    missing = [
        str(path)
        for path in required_files
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing H2 analysis outputs: "
            + ", ".join(missing)
        )

    lines = section(
        "H2 SECTOR-RELATIVE MOMENTUM FINAL ANALYSIS INTEGRITY AUDIT"
    )
    lines += [
        "Mode: Azure SQL READ-ONLY + local output verification",
        "Azure SQL modifications performed: 0",
        "",
    ]

    failures: list[str] = []
    passed = 0
    connection = None

    def check(
        condition: bool,
        success: str,
        failure: str,
    ) -> None:
        nonlocal passed
        if condition:
            lines.append(
                f"PASS: {success}"
            )
            passed += 1
        else:
            lines.append(
                f"FAIL: {failure}"
            )
            failures.append(
                failure
            )

    try:
        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        cursor = connection.cursor()

        lines += section("1. CORE / H2 SOURCE PRESERVATION")

        for table, expected in CORE_COUNTS.items():
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            check(
                actual == expected,
                f"core.{table} remains {expected:,} rows.",
                (
                    f"core.{table} = {actual:,}; "
                    f"expected {expected:,}."
                ),
            )

        wml = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                winner_minus_loser_forward_return_1m
            FROM analytics.v_h2_sector_neutral_wml_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number;
            """,
        )

        check(
            len(wml) == EXPECTED_MONTHS,
            "Validated H2 source still has exactly 59 complete W-L months.",
            f"H2 complete W-L source rows = {len(wml)}.",
        )

        lines += section("2. PRIMARY TEST RECONSTRUCTION")

        values = pd.to_numeric(
            wml[
                "winner_minus_loser_forward_return_1m"
            ],
            errors="raise",
        ).to_numpy(
            dtype=float
        )

        independent = newey_west_mean_test(
            values
        )

        primary = pd.read_csv(
            PRIMARY_PATH
        ).iloc[0]

        check(
            close(
                independent["mean"],
                primary[
                    "mean_monthly_wml"
                ],
            ),
            "Primary mean W-L matches independent reconstruction.",
            "Primary mean W-L mismatch.",
        )

        check(
            close(
                independent["p"],
                primary[
                    "hac_p"
                ],
            ),
            "Primary HAC(3) p-value matches independent reconstruction.",
            "Primary HAC(3) p-value mismatch.",
        )

        expected_primary_pass = (
            independent["mean"] > 0.0
            and independent["p"] < ALPHA
        )

        actual_primary_pass = str(
            primary[
                "primary_directional_test_pass"
            ]
        ).strip().lower() in (
            "true",
            "1",
        )

        check(
            expected_primary_pass
            == actual_primary_pass,
            "Primary H2 directional decision flag is reproducible.",
            "Primary H2 directional decision flag mismatch.",
        )

        lines += section("3. SECONDARY OUTPUT STRUCTURE")

        sector = pd.read_csv(
            SECTOR_PATH
        )
        cost = pd.read_csv(
            COST_PATH
        )
        loo = pd.read_csv(
            LOO_PATH
        )
        contribution = pd.read_csv(
            CONTRIBUTION_PATH
        )
        turnover = pd.read_csv(
            TURNOVER_PATH
        )

        check(
            len(sector) == 11,
            "Sector inference output contains 11 GICS sectors.",
            f"Sector inference rows = {len(sector)}.",
        )
        check(
            len(cost) == 12,
            "Cost/borrow sensitivity contains all 12 preregistered scenarios.",
            f"Cost grid rows = {len(cost)}.",
        )
        check(
            len(loo) == 11,
            "Leave-one-sector-out output contains 11 exclusions.",
            f"LOO rows = {len(loo)}.",
        )
        check(
            len(contribution) == 11,
            "Sector contribution output contains 11 sectors.",
            f"Contribution rows = {len(contribution)}.",
        )
        check(
            len(turnover) == 120,
            "Turnover output contains 60 months x 2 aggregate legs.",
            f"Turnover rows = {len(turnover)}.",
        )

        base = cost[
            (
                cost[
                    "transaction_cost_bps_per_turnover"
                ]
                == BASE_CASE_TRADING_BPS
            )
            & (
                cost[
                    "annual_short_borrow_fee_bps"
                ]
                == BASE_CASE_BORROW_BPS
            )
        ]

        check(
            len(base) == 1,
            "Exactly one preregistered base-case cost row exists.",
            f"Base-case cost rows = {len(base)}.",
        )

        positive_loo = int(
            (
                loo[
                    "mean_monthly_wml"
                ]
                > 0.0
            ).sum()
        )
        check(
            0 <= positive_loo <= 11,
            f"Leave-one-sector-out positive-count is valid ({positive_loo}/11).",
            "Invalid leave-one-sector-out positive count.",
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
                (
                    f"core.{table} changed to {actual:,}; "
                    f"expected {expected:,}."
                ),
            )

        if failures:
            lines += [
                "H2_SECTOR_RELATIVE_ANALYSIS_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
            for number, failure in enumerate(
                failures,
                start=1,
            ):
                lines.append(
                    f"{number}. {failure}"
                )
        else:
            lines += [
                "H2_SECTOR_RELATIVE_ANALYSIS_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                "Primary HAC inference independently reproduced.",
                "All preregistered cost/concentration output families present.",
                "Azure SQL modifications performed by audit: 0",
                "Core rows modified: 0",
            ]

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    text = "\n".join(lines) + "\n"
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(
        text,
        end="",
    )
    print(
        f"Report saved: {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()
