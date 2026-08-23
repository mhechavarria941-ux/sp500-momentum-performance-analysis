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
    / "007_create_forward_return_views.sql"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_forward_return_application.txt"
)

NEW_VIEWS = {
    "v_benchmark_monthly_forward_return_1m",
    "v_momentum_decile_forward_return_1m",
    "v_momentum_long_short_forward_return_1m",
    "v_momentum_monthly_performance_1m",
    "v_security_monthly_forward_return_1m",
}

DEPENDENCY_VIEWS = {
    "v_security_monthly_momentum_portfolio",
    "v_spy_month_end_calendar",
}

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
    retry_wait_seconds = 15
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
                "ODBC connection attempt "
                f"{attempt} / {maximum_attempts} failed. "
                f"Retrying in {retry_wait_seconds} seconds."
            )
            time.sleep(retry_wait_seconds)

    raise RuntimeError(
        "ODBC connection retry loop ended unexpectedly."
    )


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = section(
        "AZURE SQL FORWARD-RETURN APPLICATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        (
            "Strategy: fixed assignments, next-month "
            "holding returns, and terminal exits"
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

    def expect(
        query: str,
        expected: int,
        success: str,
        label: str,
    ) -> int:
        actual = scalar(cursor, query)
        check(
            actual == expected,
            success,
            (
                f"{label}: found {actual:,}; "
                f"expected {expected:,}."
            ),
        )
        return actual

    try:
        if not SQL_PATH.exists():
            raise FileNotFoundError(
                f"SQL migration not found: {SQL_PATH}"
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

        lines += section(
            "1. DEPENDENCY AND CORE CONTROLS"
        )

        cursor.execute(
            """
            SELECT v.name
            FROM sys.views AS v
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics';
            """
        )
        actual_views = {
            str(row[0])
            for row in cursor.fetchall()
        }
        missing_dependencies = sorted(
            DEPENDENCY_VIEWS - actual_views
        )

        check(
            not missing_dependencies,
            (
                "The momentum portfolio and SPY calendar "
                "dependencies are present."
            ),
            (
                "Missing dependency views: "
                + ", ".join(missing_dependencies)
            ),
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.tables AS t
            JOIN sys.schemas AS s
              ON s.schema_id = t.schema_id
            WHERE s.name = 'analytics'
              AND t.name = 'benchmark_month_end_snapshot';
            """,
            1,
            "The indexed benchmark snapshot is present.",
            "Benchmark snapshot tables",
        )

        assignment_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio;
            """,
            23_401,
            (
                "The source contains exactly 23,401 "
                "fixed portfolio assignments."
            ),
            "Portfolio assignment rows",
        )

        expect(
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics
                .v_security_monthly_momentum_portfolio;
            """,
            48,
            "The source contains exactly 48 ranking months.",
            "Ranking months",
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table}: {expected:,} rows.",
                f"core.{table} population",
            )

        if failures:
            raise RuntimeError(
                "Dependency or core control failed."
            )

        lines.append("")
        lines += section(
            "2. APPLY FORWARD-RETURN VIEWS"
        )

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )

        check(
            len(batches) == 6,
            (
                "Migration contains the expected "
                "six SQL batches."
            ),
            (
                f"Migration contains {len(batches)} "
                "batches; expected 6."
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
            "3. CONSTITUENT HOLDING-RETURN OUTPUT"
        )

        cursor.execute(
            """
            SELECT v.name
            FROM sys.views AS v
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics';
            """
        )
        actual_views = {
            str(row[0])
            for row in cursor.fetchall()
        }
        missing_views = sorted(NEW_VIEWS - actual_views)

        check(
            not missing_views,
            "All five forward-return views are present.",
            "Missing views: " + ", ".join(missing_views),
        )

        security_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m;
            """,
            assignment_rows,
            (
                "Constituent holding output preserves all "
                "23,401 assignments."
            ),
            "Constituent holding rows",
        )

        last_month_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio
            WHERE analysis_month_number = 60;
            """,
        )

        complete_security_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            security_rows - last_month_rows,
            (
                "Every in-scope constituent assignment "
                "has a complete holding return."
            ),
            "Complete constituent forward returns",
        )

        right_censored_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE out_of_scope_right_censored = 1;
            """,
            last_month_rows,
            (
                "Only the December 2025 assignments are "
                "right-censored outside the project scope."
            ),
            "Right-censored constituent rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE target_holding_end_date IS NOT NULL
              AND holding_end_status = 'UNAVAILABLE';
            """,
            0,
            (
                "No in-scope constituent holding return "
                "is unavailable."
            ),
            "Unavailable in-scope constituent returns",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE (
                    forward_return_1m_complete = 1
                AND forward_return_1m IS NULL
                  )
               OR (
                    forward_return_1m_complete = 0
                AND forward_return_1m IS NOT NULL
                  )
               OR (
                    out_of_scope_right_censored = 1
                AND holding_end_status <> 'OUT_OF_SCOPE'
                  );
            """,
            0,
            (
                "Constituent completeness, return, and "
                "censoring fields are internally consistent."
            ),
            "Inconsistent constituent holding fields",
        )

        exact_month_end_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE holding_end_is_exact_month_end = 1;
            """,
        )

        early_exit_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE holding_end_is_early_exit = 1;
            """,
        )

        immediate_exit_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE holding_end_is_immediate_exit = 1;
            """,
        )

        check(
            (
                exact_month_end_rows
                + early_exit_rows
                + immediate_exit_rows
                == complete_security_rows
            ),
            (
                "Every complete constituent return has "
                "one exact or terminal holding boundary."
            ),
            (
                "Complete-return boundary counts do not "
                "reconcile."
            ),
        )

        lines.append("")
        lines += section(
            "4. PORTFOLIO AND BENCHMARK OUTPUTS"
        )

        benchmark_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_forward_return_1m;
            """,
            96,
            (
                "Benchmark holding output contains two "
                "series across all 48 ranking months."
            ),
            "Benchmark holding rows",
        )

        benchmark_complete_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            94,
            (
                "Both benchmarks contain 47 complete "
                "forward returns."
            ),
            "Complete benchmark forward returns",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_forward_return_1m
            WHERE out_of_scope_right_censored = 1;
            """,
            2,
            (
                "Exactly two December 2025 benchmark "
                "rows are right-censored."
            ),
            "Right-censored benchmark rows",
        )

        decile_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_forward_return_1m;
            """,
            480,
            (
                "Decile output contains all 480 "
                "month/decile assignments."
            ),
            "Decile forward-return rows",
        )

        complete_decile_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            470,
            (
                "All ten deciles contain complete returns "
                "for 47 observable months."
            ),
            "Complete decile forward-return rows",
        )

        long_short_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_long_short_forward_return_1m;
            """,
            48,
            (
                "Winner-minus-loser output contains all "
                "48 ranking months."
            ),
            "Winner-minus-loser rows",
        )

        complete_long_short_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_long_short_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            47,
            (
                "Winner-minus-loser returns are complete "
                "for 47 observable months."
            ),
            "Complete winner-minus-loser rows",
        )

        performance_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_monthly_performance_1m;
            """,
            48,
            (
                "Combined momentum-performance output "
                "contains all 48 ranking months."
            ),
            "Combined performance rows",
        )

        complete_performance_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_monthly_performance_1m
            WHERE performance_1m_complete = 1;
            """,
            47,
            (
                "Combined momentum and benchmark returns "
                "are complete for 47 observable months."
            ),
            "Complete combined performance rows",
        )

        check(
            benchmark_rows - benchmark_complete_rows == 2,
            "Benchmark completeness reconciles.",
            "Benchmark completeness does not reconcile.",
        )

        check(
            decile_rows - complete_decile_rows == 10,
            "Decile right-censoring reconciles.",
            "Decile right-censoring does not reconcile.",
        )

        check(
            long_short_rows - complete_long_short_rows == 1,
            "Long-short right-censoring reconciles.",
            "Long-short right-censoring does not reconcile.",
        )

        check(
            performance_rows - complete_performance_rows == 1,
            "Combined performance right-censoring reconciles.",
            (
                "Combined performance right-censoring "
                "does not reconcile."
            ),
        )

        lines.append("")
        lines += section(
            "5. POST-MIGRATION CORE CONTROL"
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                (
                    f"core.{table} remains unchanged "
                    f"at {expected:,} rows."
                ),
                f"core.{table} post-migration population",
            )

        if failures:
            raise RuntimeError(
                "Post-migration validation failed."
            )

        connection.commit()
        lines.append(
            "PASS: Forward-return migration committed."
        )
        passed += 1

        lines.append("")
        lines += section("6. FINAL QUALITY GATE")
        lines += [
            "AZURE_SQL_FORWARD_RETURN_APPLICATION_PASSED",
            f"Passed checks: {passed}",
            "Analytical views created or updated: 5",
            f"Constituent holding rows: {security_rows:,}",
            (
                "Complete constituent holding returns: "
                f"{complete_security_rows:,}"
            ),
            (
                "Exact-month-end constituent holdings: "
                f"{exact_month_end_rows:,}"
            ),
            (
                "Early-exit constituent holdings: "
                f"{early_exit_rows:,}"
            ),
            (
                "Immediate-exit constituent holdings: "
                f"{immediate_exit_rows:,}"
            ),
            (
                "Out-of-scope constituent holdings: "
                f"{right_censored_rows:,}"
            ),
            f"Benchmark holding rows: {benchmark_rows:,}",
            (
                "Complete decile return rows: "
                f"{complete_decile_rows:,}"
            ),
            (
                "Complete winner-minus-loser months: "
                f"{complete_long_short_rows}"
            ),
            (
                "Complete benchmark-comparison months: "
                f"{complete_performance_rows}"
            ),
            "Core rows modified: 0",
            (
                "One-month forward holding returns are "
                "ready for independent auditing."
            ),
        ]

        cursor.close()

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        if lines[3] == "Connection status: NOT ATTEMPTED":
            lines[3] = "Connection status: FAILED"

        lines += [""] + section("APPLICATION FAILED")
        lines += [
            type(error).__name__,
            str(error),
            "AZURE_SQL_FORWARD_RETURN_APPLICATION_FAILED",
        ]
        failures.append(str(error))

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