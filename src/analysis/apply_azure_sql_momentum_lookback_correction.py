from __future__ import annotations

import os
import re
import time
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

SQL_PATH = (
    ROOT
    / "sql"
    / "analytics"
    / "009_correct_momentum_feature_lookback_scope.sql"
)

STANDARDIZED_PATH = (
    ROOT
    / "data"
    / "interim"
    / "standardized_price_history.csv.gz"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_momentum_lookback_correction_application.txt"
)

EXPECTED_STANDARDIZED_ROWS = 783_086
EXPECTED_SECURITY_FEATURE_ROWS = 30_211
EXPECTED_SECURITY_COMPLETE = {
    1: 30_209,
    3: 30_192,
    6: 30_169,
    12: 30_121,
}
EXPECTED_SECURITY_MOMENTUM = 30_121
EXPECTED_BENCHMARK_FEATURE_ROWS = 120
EXPECTED_BENCHMARK_COMPLETE = {
    1: 120,
    3: 120,
    6: 120,
    12: 120,
}
EXPECTED_BENCHMARK_MOMENTUM = 120
EXPECTED_RANKING_MONTHS = 60
EXPECTED_DECILE_ROWS = 600
EXPECTED_COMPLETE_DECILE_ROWS = 590
EXPECTED_LONG_SHORT_ROWS = 60
EXPECTED_COMPLETE_LONG_SHORT_ROWS = 59
EXPECTED_BENCHMARK_FORWARD_ROWS = 120
EXPECTED_COMPLETE_BENCHMARK_FORWARD_ROWS = 118
EXPECTED_PERFORMANCE_MONTHS = 59
EXPECTED_PANEL_ROWS = 767
EXPECTED_TURNOVER_ROWS = 590
EXPECTED_TURNOVER_MONTHS = 59
EXPECTED_SERIES = 13

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
SCRIPT_VERSION = "2026-08-24-v2-catalog-object-check"


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


def sql_batches(sql_text: str) -> list[str]:
    return [
        batch.strip()
        for batch in re.split(
            r"^\s*GO\s*(?:--.*)?$",
            sql_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if batch.strip()
    ]


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
            return pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=False,
            )
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


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def fetch_one(cursor, query: str) -> tuple:
    cursor.execute(query)
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Expected one SQL row; query returned none.")
    return tuple(row)


def feature_month_number(date_series: pd.Series) -> pd.Series:
    return (
        (date_series.dt.year - 2021) * 12
        + date_series.dt.month
    ).astype(int)


def prepare_support() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not STANDARDIZED_PATH.exists():
        raise FileNotFoundError(
            f"Standardized price history not found: "
            f"{STANDARDIZED_PATH}"
        )

    print("Loading standardized price history...")
    prices = pd.read_csv(
        STANDARDIZED_PATH,
        usecols=[
            "security_key",
            "project_ticker",
            "date",
            "adjusted_close",
        ],
        low_memory=False,
    )

    if len(prices) != EXPECTED_STANDARDIZED_ROWS:
        raise RuntimeError(
            f"Standardized rows: {len(prices):,}; "
            f"expected {EXPECTED_STANDARDIZED_ROWS:,}."
        )

    prices["security_key"] = (
        prices["security_key"].astype(str).str.strip()
    )
    prices["project_ticker"] = (
        prices["project_ticker"].astype(str).str.strip()
    )
    prices["date"] = pd.to_datetime(
        prices["date"],
        errors="raise",
    )
    prices["adjusted_close"] = pd.to_numeric(
        prices["adjusted_close"],
        errors="raise",
    )

    if (
        prices["adjusted_close"].isna().any()
        or (prices["adjusted_close"] <= 0).any()
    ):
        raise RuntimeError(
            "Standardized adjusted close contains null or "
            "nonpositive values."
        )

    support_window = prices[
        (prices["date"] >= pd.Timestamp("2020-01-01"))
        & (prices["date"] <= pd.Timestamp("2025-12-31"))
    ].copy()

    spy = support_window[
        support_window["project_ticker"] == "SPY"
    ][["date"]].copy()

    spy["period"] = spy["date"].dt.to_period("M")
    month_ends = (
        spy.groupby("period", sort=True)["date"]
        .max()
        .reset_index()
    )

    expected_periods = pd.period_range(
        "2020-01",
        "2025-12",
        freq="M",
    )
    actual_periods = list(month_ends["period"])

    if actual_periods != list(expected_periods):
        raise RuntimeError(
            "SPY support calendar is not exactly "
            "2020-01 through 2025-12."
        )

    exact_month_end_dates = set(month_ends["date"])

    monthly = support_window[
        support_window["date"].isin(exact_month_end_dates)
    ].copy()

    duplicate_security_date = monthly[
        ~monthly["project_ticker"].isin({"SPY", "^GSPC"})
    ].duplicated(
        ["security_key", "date"],
        keep=False,
    )

    if duplicate_security_date.any():
        duplicate_rows = monthly[
            ~monthly["project_ticker"].isin({"SPY", "^GSPC"})
        ][duplicate_security_date]
        raise RuntimeError(
            "Permanent security identity has duplicate exact "
            "month-end support rows. First examples: "
            + duplicate_rows[
                ["security_key", "project_ticker", "date"]
            ]
            .head(10)
            .to_string(index=False)
        )

    monthly["feature_month_number"] = (
        feature_month_number(monthly["date"])
    )

    security_support = monthly[
        ~monthly["project_ticker"].isin({"SPY", "^GSPC"})
    ][
        [
            "feature_month_number",
            "date",
            "security_key",
            "project_ticker",
            "adjusted_close",
        ]
    ].copy()

    benchmark_support = monthly[
        monthly["project_ticker"].isin({"SPY", "^GSPC"})
    ][
        [
            "feature_month_number",
            "date",
            "security_key",
            "project_ticker",
            "adjusted_close",
        ]
    ].copy()

    security_support = security_support.sort_values(
        ["security_key", "feature_month_number"]
    ).reset_index(drop=True)

    benchmark_support = benchmark_support.sort_values(
        ["security_key", "project_ticker", "feature_month_number"]
    ).reset_index(drop=True)

    if security_support.duplicated(
        ["security_key", "feature_month_number"]
    ).any():
        raise RuntimeError(
            "Duplicate security feature-support key detected."
        )

    if benchmark_support.duplicated(
        [
            "security_key",
            "project_ticker",
            "feature_month_number",
        ]
    ).any():
        raise RuntimeError(
            "Duplicate benchmark feature-support key detected."
        )

    # Both validated benchmark series have exact SPY month-end observations
    # for all 72 support months in the inspection.
    if len(benchmark_support) != 144:
        raise RuntimeError(
            f"Benchmark support rows: {len(benchmark_support):,}; "
            "expected 144 (2 series x 72 months)."
        )

    return security_support, benchmark_support


def sql_rows(frame: pd.DataFrame) -> list[tuple]:
    rows: list[tuple] = []
    for row in frame.itertuples(index=False):
        rows.append(
            (
                int(row.feature_month_number),
                pd.Timestamp(row.date).date(),
                str(row.security_key),
                str(row.project_ticker),
                Decimal(str(row.adjusted_close)),
            )
        )
    return rows


def insert_chunks(
    cursor,
    statement: str,
    rows: list[tuple],
    chunk_size: int = 5000,
) -> None:
    cursor.fast_executemany = True
    for start in range(0, len(rows), chunk_size):
        cursor.executemany(
            statement,
            rows[start : start + chunk_size],
        )


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    lines = section(
        "AZURE SQL MOMENTUM LOOKBACK-SCOPE CORRECTION APPLICATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        (
            "Correction: preserve point-in-time ranking membership while "
            "restoring validated pre-membership lag-price support."
        ),
        (
            "Revision: catalog-based dependency detection replaces the "
            "false-negative parameterized OBJECT_ID pre-check."
        ),
        "Core-table modifications intended: 0",
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
            lines.append(f"PASS: {success}")
            passed += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    def expect(
        cursor,
        query: str,
        expected: int,
        success: str,
        label: str,
    ) -> int:
        actual = scalar(cursor, query)
        check(
            actual == expected,
            success,
            f"{label}: found {actual:,}; expected {expected:,}.",
        )
        return actual

    try:
        if not SQL_PATH.exists():
            raise FileNotFoundError(
                f"SQL migration not found: {SQL_PATH}"
            )

        security_support, benchmark_support = prepare_support()

        lines += section("1. LOCAL SUPPORT PREPARATION")
        check(
            len(security_support) > EXPECTED_SECURITY_FEATURE_ROWS,
            (
                "Constituent feature-support population prepared: "
                f"{len(security_support):,} exact month-end rows."
            ),
            (
                "Constituent feature-support population is unexpectedly "
                f"small: {len(security_support):,}."
            ),
        )
        check(
            len(benchmark_support) == 144,
            "Benchmark feature-support population is exactly 144 rows.",
            f"Benchmark support rows: {len(benchmark_support):,}.",
        )
        check(
            int(security_support["feature_month_number"].min()) == -11
            and int(security_support["feature_month_number"].max()) == 60,
            (
                "Constituent support month numbering spans "
                "2020-01 (-11) through 2025-12 (60)."
            ),
            "Constituent feature-month numbering is incorrect.",
        )
        check(
            int(benchmark_support["feature_month_number"].min()) == -11
            and int(benchmark_support["feature_month_number"].max()) == 60,
            (
                "Benchmark support month numbering spans "
                "2020-01 (-11) through 2025-12 (60)."
            ),
            "Benchmark feature-month numbering is incorrect.",
        )

        if failures:
            raise RuntimeError(
                "Local support preparation failed."
            )

        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        connection.timeout = 600
        cursor = connection.cursor()
        lines[3] = "Connection status: SUCCESS"

        lines.append("")
        lines += section("2. PRE-CORRECTION DATABASE CONTROLS")

        required_objects = {
            "security_month_end_snapshot": "U",
            "benchmark_month_end_snapshot": "U",
            "v_security_monthly_return_features": "V",
            "v_benchmark_monthly_return_features": "V",
            "v_security_monthly_momentum_portfolio": "V",
            "v_security_monthly_forward_return_1m": "V",
            "v_momentum_monthly_return_panel": "V",
        }

        # Use the SQL Server system catalog directly.  The previous
        # parameterized OBJECT_ID(?, NULL) probe produced false negatives
        # through this Azure SQL / ODBC path even though direct SELECTs
        # against the same objects succeeded.
        cursor.execute(
            """
            SELECT
                o.name,
                o.type
            FROM sys.objects AS o
            JOIN sys.schemas AS s
              ON s.schema_id = o.schema_id
            WHERE s.name = 'analytics';
            """
        )

        catalog_objects = {
            str(row[0]): str(row[1]).strip()
            for row in cursor.fetchall()
        }

        missing_objects = [
            f"analytics.{name}"
            for name, expected_type in required_objects.items()
            if catalog_objects.get(name) != expected_type
        ]

        check(
            not missing_objects,
            (
                "All required upstream and downstream analytical objects "
                "exist with the expected SQL object types."
            ),
            (
                "Missing or wrong-type objects: "
                + ", ".join(missing_objects)
            ),
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table}: {expected:,} rows.",
                f"core.{table} pre-correction population",
            )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.security_month_end_snapshot;
            """,
            EXPECTED_SECURITY_FEATURE_ROWS,
            "Current ranking-date snapshot remains 30,211 rows.",
            "Security month-end snapshot rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1;
            """,
            23_401,
            (
                "Pre-correction feature layer is the expected "
                "23,401-signal snapshot-only state."
            ),
            "Pre-correction complete momentum rows",
        )

        if failures:
            raise RuntimeError(
                "Pre-correction dependency/core control failed."
            )

        lines.append("")
        lines += section("3. APPLY SUPPORT TABLES AND CORRECTED FEATURE VIEWS")

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )

        check(
            len(batches) == 4,
            "Correction migration contains the expected four SQL batches.",
            (
                f"Correction migration contains {len(batches)} batches; "
                "expected 4."
            ),
        )
        if failures:
            raise RuntimeError(
                "Correction migration batch structure is invalid."
            )

        # Batch 1 creates support tables if they do not already exist.
        cursor.execute(batches[0])
        lines.append("PASS: Feature-support tables are present.")
        passed += 1

        cursor.execute(
            "DELETE FROM analytics.security_month_end_feature_support;"
        )
        cursor.execute(
            "DELETE FROM analytics.benchmark_month_end_feature_support;"
        )

        security_rows = sql_rows(security_support)
        benchmark_rows = sql_rows(benchmark_support)

        print(
            "Loading exact month-end feature support into Azure SQL..."
        )

        insert_chunks(
            cursor,
            """
            INSERT INTO analytics.security_month_end_feature_support
            (
                feature_month_number,
                month_end_date,
                security_key,
                project_ticker,
                adjusted_close
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            security_rows,
        )

        insert_chunks(
            cursor,
            """
            INSERT INTO analytics.benchmark_month_end_feature_support
            (
                feature_month_number,
                month_end_date,
                security_key,
                project_ticker,
                adjusted_close
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            benchmark_rows,
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.security_month_end_feature_support;
            """,
            len(security_rows),
            (
                "Azure SQL constituent feature-support row count "
                "matches the local exact-month-end source."
            ),
            "Constituent feature-support rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.benchmark_month_end_feature_support;
            """,
            len(benchmark_rows),
            (
                "Azure SQL benchmark feature-support row count "
                "matches the local exact-month-end source."
            ),
            "Benchmark feature-support rows",
        )

        # Apply corrected constituent and benchmark feature views, then
        # refresh the existing downstream view dependency chain.
        for batch_number, batch in enumerate(
            batches[1:],
            start=2,
        ):
            cursor.execute(batch)
            lines.append(
                f"PASS: Executed correction SQL batch "
                f"{batch_number} / {len(batches)}."
            )
            passed += 1

        lines.append("")
        lines += section("4. CORRECTED FEATURE POPULATIONS")

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_return_features;
            """,
            EXPECTED_SECURITY_FEATURE_ROWS,
            (
                "Corrected constituent feature view still preserves "
                "all 30,211 ranking-date observations."
            ),
            "Constituent feature rows",
        )

        for horizon, expected in EXPECTED_SECURITY_COMPLETE.items():
            expect(
                cursor,
                f"""
                SELECT COUNT_BIG(*)
                FROM analytics.v_security_monthly_return_features
                WHERE trailing_return_{horizon}m_complete = 1
                  AND trailing_return_{horizon}m IS NOT NULL;
                """,
                expected,
                (
                    f"Corrected constituent {horizon}-month completeness "
                    f"is exact: {expected:,}."
                ),
                f"Complete constituent {horizon}-month rows",
            )

        momentum_rows = expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND momentum_12_1 IS NOT NULL;
            """,
            EXPECTED_SECURITY_MOMENTUM,
            (
                "Corrected canonical 12-1 momentum population is "
                "exactly 30,121 rows."
            ),
            "Complete constituent momentum rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_return_features AS f
            LEFT JOIN analytics.security_month_end_feature_support AS lag_1
              ON lag_1.security_key = f.security_key
             AND lag_1.feature_month_number
               = f.analysis_month_number - 1
            LEFT JOIN analytics.security_month_end_feature_support AS lag_12
              ON lag_12.security_key = f.security_key
             AND lag_12.feature_month_number
               = f.analysis_month_number - 12
            WHERE
                f.momentum_12_1_complete
                <> CASE
                    WHEN lag_1.security_key IS NOT NULL
                     AND lag_12.security_key IS NOT NULL
                    THEN 1 ELSE 0
                   END
               OR (
                    f.momentum_12_1_complete = 1
                    AND ABS(
                        CAST(f.momentum_12_1 AS FLOAT)
                        - (
                            CAST(lag_1.adjusted_close AS FLOAT)
                            / CAST(lag_12.adjusted_close AS FLOAT)
                            - 1.0
                        )
                    ) > 0.000000000000001
               );
            """,
            0,
            (
                "Every corrected momentum-completeness flag and value "
                "reconciles to support months -1 and -12."
            ),
            "Corrected constituent momentum mismatches",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND (
                    DATEDIFF(
                        MONTH,
                        momentum_12_1_start_date,
                        momentum_12_1_end_date
                    ) <> 11
                 OR DATEDIFF(
                        MONTH,
                        momentum_12_1_end_date,
                        month_end_date
                    ) <> 1
              );
            """,
            0,
            (
                "Every corrected momentum window remains months "
                "-12 through -1 and skips the ranking month."
            ),
            "Invalid corrected momentum date windows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_monthly_return_features;
            """,
            EXPECTED_BENCHMARK_FEATURE_ROWS,
            "Benchmark feature view still contains 120 ranking rows.",
            "Benchmark feature rows",
        )

        for horizon, expected in EXPECTED_BENCHMARK_COMPLETE.items():
            expect(
                cursor,
                f"""
                SELECT COUNT_BIG(*)
                FROM analytics.v_benchmark_monthly_return_features
                WHERE trailing_return_{horizon}m_complete = 1
                  AND trailing_return_{horizon}m IS NOT NULL;
                """,
                expected,
                (
                    f"Corrected benchmark {horizon}-month completeness "
                    f"is exact: {expected}."
                ),
                f"Complete benchmark {horizon}-month rows",
            )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND momentum_12_1 IS NOT NULL;
            """,
            EXPECTED_BENCHMARK_MOMENTUM,
            (
                "Both benchmarks now contain complete 12-1 momentum "
                "for all 60 ranking months."
            ),
            "Complete benchmark momentum rows",
        )

        if failures:
            raise RuntimeError(
                "Corrected feature validation failed."
            )

        lines.append("")
        lines += section("5. DOWNSTREAM PROPAGATION")

        ranking_rows = expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_momentum_portfolio;
            """,
            EXPECTED_SECURITY_MOMENTUM,
            (
                "Portfolio assignments propagate all 30,121 "
                "corrected momentum signals."
            ),
            "Portfolio assignment rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_security_monthly_momentum_portfolio;
            """,
            EXPECTED_RANKING_MONTHS,
            "Momentum portfolios now span all 60 ranking months.",
            "Ranking months",
        )

        min_rank_month, max_rank_month = fetch_one(
            cursor,
            """
            SELECT
                MIN(analysis_month_number),
                MAX(analysis_month_number)
            FROM analytics.v_security_monthly_momentum_portfolio;
            """,
        )
        check(
            int(min_rank_month) == 1 and int(max_rank_month) == 60,
            "Ranking assignments span analysis months 1 through 60.",
            (
                "Ranking assignment month bounds are "
                f"{min_rank_month} through {max_rank_month}."
            ),
        )

        decile_rows = expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_decile_forward_return_1m;
            """,
            EXPECTED_DECILE_ROWS,
            "Decile forward-return layer contains all 600 month/decile rows.",
            "Decile forward-return rows",
        )

        complete_decile_rows = expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_decile_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_DECILE_ROWS,
            (
                "All ten deciles contain complete returns for "
                "59 observable holding months."
            ),
            "Complete decile forward-return rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_long_short_forward_return_1m;
            """,
            EXPECTED_LONG_SHORT_ROWS,
            "Winner-minus-loser layer contains all 60 ranking months.",
            "Winner-minus-loser rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_long_short_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_LONG_SHORT_ROWS,
            (
                "Winner-minus-loser returns are complete for "
                "59 observable months."
            ),
            "Complete winner-minus-loser rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_monthly_forward_return_1m;
            """,
            EXPECTED_BENCHMARK_FORWARD_ROWS,
            (
                "Benchmark forward-return layer contains two series "
                "across all 60 ranking months."
            ),
            "Benchmark forward-return rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_BENCHMARK_FORWARD_ROWS,
            (
                "Both benchmarks contain 59 complete forward returns "
                "(118 rows total)."
            ),
            "Complete benchmark forward-return rows",
        )

        panel_rows = expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
            EXPECTED_PANEL_ROWS,
            (
                "Gross monthly return panel contains 767 observations "
                "(13 series x 59 months)."
            ),
            "Monthly return-panel rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT series_code)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
            EXPECTED_SERIES,
            "Gross return panel still contains all 13 analytical series.",
            "Analytical series",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
            EXPECTED_PERFORMANCE_MONTHS,
            "Gross return panel now contains 59 observable months.",
            "Observable performance months",
        )

        min_perf_month, max_perf_month = fetch_one(
            cursor,
            """
            SELECT
                MIN(analysis_month_number),
                MAX(analysis_month_number)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
        )
        check(
            int(min_perf_month) == 1 and int(max_perf_month) == 59,
            (
                "Completed performance now spans analysis months "
                "1 through 59; December 2025 remains right-censored."
            ),
            (
                "Performance month bounds are "
                f"{min_perf_month} through {max_perf_month}."
            ),
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_cumulative_wealth;
            """,
            panel_rows,
            "Cumulative wealth preserves all 767 panel rows.",
            "Cumulative-wealth rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_wealth_drawdown;
            """,
            panel_rows,
            "Drawdown layer preserves all 767 panel rows.",
            "Drawdown rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_performance_summary;
            """,
            EXPECTED_SERIES,
            "Performance summary still contains 13 series.",
            "Performance-summary rows",
        )

        turnover_rows = expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_decile_turnover;
            """,
            EXPECTED_TURNOVER_ROWS,
            (
                "Turnover layer contains 590 month/decile rebalances "
                "(59 consecutive transitions x 10 deciles)."
            ),
            "Turnover rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_momentum_decile_turnover;
            """,
            EXPECTED_TURNOVER_MONTHS,
            "Turnover spans 59 consecutive rebalances.",
            "Turnover months",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_turnover_summary;
            """,
            10,
            "Turnover summary still contains one row per decile.",
            "Turnover-summary rows",
        )

        # Security-level forward counts are intentionally reported rather than
        # fully hard-coded because the corrected ranking population changes
        # which securities enter the portfolios.  Only the final ranking month
        # should remain right-censored.
        security_forward_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_forward_return_1m;
            """,
        )
        complete_security_forward = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
        )
        right_censored_security = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_forward_return_1m
            WHERE out_of_scope_right_censored = 1;
            """,
        )
        last_month_assignments = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_momentum_portfolio
            WHERE analysis_month_number = 60;
            """,
        )

        check(
            security_forward_rows == ranking_rows,
            (
                "Security forward-return layer preserves every corrected "
                f"assignment: {security_forward_rows:,} rows."
            ),
            (
                f"Security forward rows {security_forward_rows:,} do not "
                f"match assignments {ranking_rows:,}."
            ),
        )
        check(
            right_censored_security == last_month_assignments,
            (
                "Only December 2025 security assignments are "
                f"right-censored: {right_censored_security:,} rows."
            ),
            (
                f"Right-censored security rows {right_censored_security:,} "
                f"do not match December assignments "
                f"{last_month_assignments:,}."
            ),
        )
        check(
            complete_security_forward
            == security_forward_rows - right_censored_security,
            (
                "Every in-scope corrected security assignment has a "
                f"complete holding return: {complete_security_forward:,}."
            ),
            (
                "Complete security forward-return population does not "
                "reconcile to total minus right-censored rows."
            ),
        )

        if failures:
            raise RuntimeError(
                "Downstream corrected-population validation failed."
            )

        lines.append("")
        lines += section("6. FINAL CORE PRESERVATION")

        for table, expected in CORE_COUNTS.items():
            expect(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table} remains unchanged at {expected:,} rows.",
                f"core.{table} post-correction population",
            )

        if failures:
            raise RuntimeError(
                "Core preservation check failed."
            )

        connection.commit()
        lines.append(
            "PASS: Lookback-scope correction transaction committed."
        )
        passed += 1

        lines.append("")
        lines += section("7. FINAL QUALITY GATE")
        lines += [
            "AZURE_SQL_MOMENTUM_LOOKBACK_SCOPE_CORRECTION_PASSED",
            f"Passed checks: {passed}",
            f"Constituent feature-support rows: {len(security_support):,}",
            "Benchmark feature-support rows: 144",
            "Ranking-date constituent feature rows: 30,211",
            "Corrected 1-month complete rows: 30,209",
            "Corrected 3-month complete rows: 30,192",
            "Corrected 6-month complete rows: 30,169",
            "Corrected 12-month complete rows: 30,121",
            "Corrected 12-1 momentum rows: 30,121",
            "Signals restored versus snapshot-only design: 6,720",
            "Ranking months: 60",
            "Complete observable performance months: 59",
            "Decile forward-return rows: 600",
            "Complete decile forward-return rows: 590",
            "Complete WML months: 59",
            "Complete benchmark forward-return rows: 118",
            "Monthly return-panel rows: 767",
            "Turnover rows: 590",
            f"Security forward-return rows: {security_forward_rows:,}",
            f"Complete security forward returns: {complete_security_forward:,}",
            f"Right-censored December 2025 assignments: {right_censored_security:,}",
            "Core rows modified: 0",
            (
                "The intended 2021-2025 momentum experiment is now "
                "propagated through the existing ranking, forward-return, "
                "and portfolio-performance view chain."
            ),
            (
                "Next action: independently audit the corrected layer, "
                "update hard-coded validation scripts/reports, document the "
                "correction in the project log, then commit the correction."
            ),
        ]

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        if len(lines) > 3 and lines[3] == "Connection status: NOT ATTEMPTED":
            lines[3] = "Connection status: FAILED"

        failures.append(str(error))
        lines += [
            "",
            *section("CORRECTION APPLICATION FAILED"),
            type(error).__name__,
            str(error),
            "TRANSACTION STATUS: ROLLED BACK",
            "AZURE_SQL_MOMENTUM_LOOKBACK_SCOPE_CORRECTION_FAILED",
        ]

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

        report = "\n".join(lines) + "\n"
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(report, end="")
        print(f"Report saved: {REPORT_PATH}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
