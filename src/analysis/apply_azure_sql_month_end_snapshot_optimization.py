from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

SQL_PATH = (
    ROOT
    / "sql"
    / "analytics"
    / "005_create_indexed_month_end_snapshots.sql"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_month_end_snapshot_optimization.txt"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXPECTED_CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}


def section(title: str) -> list[str]:
    rule = "=" * 79
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
            return pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=False,
            )

        except pyodbc.Error as error:
            error_text = str(error).lower()
            retryable = any(
                term in error_text
                for term in retryable_terms
            )

            if (
                not retryable
                or attempt == 5
            ):
                raise

            print(
                "ODBC connection attempt "
                f"{attempt} / 5 failed. "
                "Retrying in 15 seconds."
            )
            time.sleep(15)

    raise RuntimeError(
        "ODBC connection retry loop ended unexpectedly."
    )


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


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def main() -> None:
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL MONTH-END SNAPSHOT OPTIMIZATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        (
            "Strategy: indexed analytical snapshots "
            "with transactional refresh"
        ),
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

    try:
        if not SQL_PATH.exists():
            raise FileNotFoundError(
                f"SQL migration not found: {SQL_PATH}"
            )

        server, database, username, password = (
            environment()
        )

        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )

        lines[3] = "Connection status: SUCCESS"

        connection.timeout = 600
        cursor = connection.cursor()

        lines += section(
            "1. PRE-OPTIMIZATION CORE CONTROL"
        )

        for table, expected in (
            EXPECTED_CORE_COUNTS.items()
        ):
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )

            check(
                actual == expected,
                (
                    f"core.{table}: "
                    f"{actual:,} / {expected:,} rows."
                ),
                (
                    f"core.{table}: found {actual:,}; "
                    f"expected {expected:,}."
                ),
            )

        if failures:
            raise RuntimeError(
                "Pre-optimization core control failed."
            )

        lines.append("")

        lines += section(
            "2. APPLY SNAPSHOT STRUCTURE AND FEATURE VIEWS"
        )

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )

        check(
            len(batches) == 5,
            (
                "Migration contains the expected "
                "five SQL batches."
            ),
            (
                f"Migration contains {len(batches)} "
                "batches; expected 5."
            ),
        )

        if failures:
            raise RuntimeError(
                "SQL migration batch structure is invalid."
            )

        for batch_number, batch in enumerate(
            batches,
            start=1,
        ):
            cursor.execute(batch)
            lines.append(
                "PASS: Executed SQL batch "
                f"{batch_number} / {len(batches)}."
            )
            passed += 1

        lines.append("")

        lines += section(
            "3. TRANSACTIONAL SNAPSHOT REFRESH"
        )

        cursor.execute(
            """
            DELETE FROM
                analytics.security_month_end_snapshot;
            """
        )
        cursor.execute(
            """
            DELETE FROM
                analytics.benchmark_month_end_snapshot;
            """
        )

        refresh_started = time.perf_counter()

        cursor.execute(
            """
            INSERT INTO
                analytics.security_month_end_snapshot (
                    analysis_month_number,
                    month_start_date,
                    month_end_date,
                    security_key,
                    company_name_reference,
                    project_ticker,
                    provider_symbol,
                    adjusted_close,
                    membership_valid_from,
                    membership_valid_to_exclusive,
                    usable_start,
                    usable_end_exclusive
                )
            SELECT
                analysis_month_number,
                month_start_date,
                month_end_date,
                security_key,
                company_name_reference,
                project_ticker,
                provider_symbol,
                adjusted_close,
                membership_valid_from,
                membership_valid_to_exclusive,
                usable_start,
                usable_end_exclusive
            FROM analytics.v_security_month_end_price;
            """
        )
        security_inserted = cursor.rowcount

        cursor.execute(
            """
            INSERT INTO
                analytics.benchmark_month_end_snapshot (
                    analysis_month_number,
                    month_start_date,
                    month_end_date,
                    security_key,
                    project_ticker,
                    provider_symbol,
                    benchmark_name,
                    series_type,
                    adjusted_close
                )
            SELECT
                analysis_month_number,
                month_start_date,
                month_end_date,
                security_key,
                project_ticker,
                provider_symbol,
                benchmark_name,
                series_type,
                adjusted_close
            FROM analytics.v_benchmark_month_end_price;
            """
        )
        benchmark_inserted = cursor.rowcount

        refresh_seconds = (
            time.perf_counter()
            - refresh_started
        )

        check(
            security_inserted in (-1, 30_211),
            "Constituent snapshot insert completed.",
            (
                "Driver reported "
                f"{security_inserted:,} "
                "constituent inserts."
            ),
        )

        check(
            benchmark_inserted in (-1, 120),
            "Benchmark snapshot insert completed.",
            (
                "Driver reported "
                f"{benchmark_inserted:,} "
                "benchmark inserts."
            ),
        )

        lines.append(
            "Snapshot refresh elapsed seconds: "
            f"{refresh_seconds:.3f}"
        )
        lines.append("")

        lines += section(
            "4. SNAPSHOT RECONCILIATION"
        )

        security_snapshot_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.security_month_end_snapshot;
            """,
        )

        benchmark_snapshot_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.benchmark_month_end_snapshot;
            """,
        )

        check(
            security_snapshot_rows == 30_211,
            (
                "Constituent snapshot contains "
                "exactly 30,211 rows."
            ),
            (
                "Constituent snapshot contains "
                f"{security_snapshot_rows:,} rows."
            ),
        )

        check(
            benchmark_snapshot_rows == 120,
            (
                "Benchmark snapshot contains "
                "exactly 120 rows."
            ),
            (
                "Benchmark snapshot contains "
                f"{benchmark_snapshot_rows:,} rows."
            ),
        )

        security_mismatches = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_month_end_price
                AS source
            FULL OUTER JOIN
                analytics.security_month_end_snapshot
                AS snapshot
              ON snapshot.analysis_month_number
               = source.analysis_month_number
             AND snapshot.security_key
               = source.security_key
            WHERE source.security_key IS NULL
               OR snapshot.security_key IS NULL
               OR snapshot.month_start_date
                  <> source.month_start_date
               OR snapshot.month_end_date
                  <> source.month_end_date
               OR snapshot.company_name_reference
                  <> source.company_name_reference
               OR snapshot.project_ticker
                  <> source.project_ticker
               OR snapshot.provider_symbol
                  <> source.provider_symbol
               OR snapshot.adjusted_close
                  <> source.adjusted_close
               OR snapshot.membership_valid_from
                  <> source.membership_valid_from
               OR snapshot.membership_valid_to_exclusive
                  <> source.membership_valid_to_exclusive
               OR snapshot.usable_start
                  <> source.usable_start
               OR snapshot.usable_end_exclusive
                  <> source.usable_end_exclusive;
            """,
        )

        check(
            security_mismatches == 0,
            (
                "Constituent snapshot exactly "
                "reconciles to its source view."
            ),
            (
                f"Found {security_mismatches:,} "
                "constituent snapshot mismatches."
            ),
        )

        benchmark_mismatches = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_month_end_price
                AS source
            FULL OUTER JOIN
                analytics.benchmark_month_end_snapshot
                AS snapshot
              ON snapshot.analysis_month_number
               = source.analysis_month_number
             AND snapshot.security_key
               = source.security_key
             AND snapshot.project_ticker
               = source.project_ticker
            WHERE source.security_key IS NULL
               OR snapshot.security_key IS NULL
               OR snapshot.month_start_date
                  <> source.month_start_date
               OR snapshot.month_end_date
                  <> source.month_end_date
               OR snapshot.provider_symbol
                  <> source.provider_symbol
               OR snapshot.benchmark_name
                  <> source.benchmark_name
               OR snapshot.series_type
                  <> source.series_type
               OR snapshot.adjusted_close
                  <> source.adjusted_close;
            """,
        )

        check(
            benchmark_mismatches == 0,
            (
                "Benchmark snapshot exactly "
                "reconciles to its source view."
            ),
            (
                f"Found {benchmark_mismatches:,} "
                "benchmark snapshot mismatches."
            ),
        )

        lines.append("")

        lines += section(
            "5. OPTIMIZED FEATURE PERFORMANCE"
        )

        count_started = time.perf_counter()

        feature_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features;
            """,
        )

        feature_count_seconds = (
            time.perf_counter()
            - count_started
        )

        check(
            feature_rows == 30_211,
            (
                "Optimized feature view contains "
                "exactly 30,211 rows."
            ),
            (
                "Optimized feature view contains "
                f"{feature_rows:,} rows."
            ),
        )

        check(
            feature_count_seconds < 30,
            (
                "Feature row count completed in "
                f"{feature_count_seconds:.3f} seconds."
            ),
            (
                "Feature row count required "
                f"{feature_count_seconds:.3f} seconds."
            ),
        )

        momentum_started = time.perf_counter()

        momentum_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1;
            """,
        )

        momentum_count_seconds = (
            time.perf_counter()
            - momentum_started
        )

        check(
            momentum_rows == 23_401,
            (
                "Optimized feature view preserves "
                "23,401 complete momentum rows."
            ),
            (
                "Optimized feature view contains "
                f"{momentum_rows:,} momentum rows."
            ),
        )

        check(
            momentum_count_seconds < 30,
            (
                "Momentum row count completed in "
                f"{momentum_count_seconds:.3f} seconds."
            ),
            (
                "Momentum row count required "
                f"{momentum_count_seconds:.3f} seconds."
            ),
        )

        lines.append("")

        lines += section(
            "6. POST-OPTIMIZATION CORE CONTROL"
        )

        for table, expected in (
            EXPECTED_CORE_COUNTS.items()
        ):
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )

            check(
                actual == expected,
                (
                    f"core.{table} remains unchanged "
                    f"at {actual:,} rows."
                ),
                (
                    f"core.{table} changed to "
                    f"{actual:,} rows."
                ),
            )

        if failures:
            raise RuntimeError(
                "One or more optimization controls failed."
            )

        connection.commit()
        lines.append(
            "PASS: Snapshot refresh and view "
            "optimization committed."
        )
        passed += 1
        lines.append("")

        lines += section(
            "7. FINAL QUALITY GATE"
        )

        lines += [
            (
                "AZURE_SQL_MONTH_END_SNAPSHOT_"
                "OPTIMIZATION_PASSED"
            ),
            f"Passed checks: {passed}",
            "Indexed analytical snapshot tables: 2",
            (
                "Constituent snapshot rows: "
                f"{security_snapshot_rows:,}"
            ),
            (
                "Benchmark snapshot rows: "
                f"{benchmark_snapshot_rows:,}"
            ),
            (
                "Feature count elapsed seconds: "
                f"{feature_count_seconds:.3f}"
            ),
            (
                "Momentum count elapsed seconds: "
                f"{momentum_count_seconds:.3f}"
            ),
            "Constituent feature rows: 30,211",
            (
                "Complete canonical 12-1 "
                "momentum rows: 23,401"
            ),
            "Core rows modified: 0",
            (
                "Monthly feature views are ready for "
                "a reliable integrity-audit retry."
            ),
        ]

        cursor.close()

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        if lines[3] == (
            "Connection status: NOT ATTEMPTED"
        ):
            lines[3] = "Connection status: FAILED"

        lines += [""] + section(
            "OPTIMIZATION FAILED"
        )
        lines += [
            type(error).__name__,
            str(error),
            (
                "AZURE_SQL_MONTH_END_SNAPSHOT_"
                "OPTIMIZATION_FAILED"
            ),
        ]
        failures.append(str(error))

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
        print(report, end="")
        print(f"Report saved: {REPORT_PATH}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()