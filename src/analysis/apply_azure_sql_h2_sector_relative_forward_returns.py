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
    / "011_create_h2_sector_relative_forward_return_views.sql"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_h2_sector_forward_return_application.txt"
)

SCRIPT_VERSION = (
    "2026-08-24-v3-h2-sector-forward-return-batch-check-fix"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}

DEPENDENCY_VIEWS = {
    "v_security_monthly_sector_momentum_portfolio",
    "v_security_monthly_forward_return_1m",
}

NEW_VIEWS = {
    "v_h2_security_monthly_forward_return_1m",
    "v_h2_sector_quintile_forward_return_1m",
    "v_h2_sector_extreme_forward_return_1m",
    "v_h2_sector_neutral_leg_forward_return_1m",
    "v_h2_sector_neutral_wml_forward_return_1m",
}

REQUIRED_FORWARD_COLUMNS = {
    "analysis_month_number",
    "security_key",
    "target_holding_end_date",
    "holding_end_status",
    "holding_end_is_exact_month_end",
    "holding_end_is_early_exit",
    "holding_end_is_immediate_exit",
    "forward_return_1m",
    "forward_return_1m_complete",
    "out_of_scope_right_censored",
}

EXPECTED_H2_ASSIGNMENTS = 30_121
EXPECTED_COMPLETE_SECURITY_RETURNS = 29_620
EXPECTED_RIGHT_CENSORED_SECURITY = 501

EXPECTED_SECTOR_QUINTILE_ROWS = 3_300
EXPECTED_COMPLETE_SECTOR_QUINTILE_ROWS = 3_245

EXPECTED_EXTREME_ROWS = 1_320
EXPECTED_COMPLETE_EXTREME_ROWS = 1_298

EXPECTED_LEG_ROWS = 120
EXPECTED_COMPLETE_LEG_ROWS = 118

EXPECTED_WML_ROWS = 60
EXPECTED_COMPLETE_WML_ROWS = 59


def section(title: str) -> list[str]:
    rule = "=" * 92
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
                autocommit=False,
            )
            print(
                f"ODBC connection established on attempt {attempt} / 5."
            )
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


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


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


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL H2 SECTOR FORWARD-RETURN APPLICATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        (
            "Scope: fixed H2 assignments -> validated security "
            "forward returns -> sector sleeves -> sector-neutral W-L"
        ),
        "Statistical / risk / cost interpretation: NOT PERFORMED",
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
            raise FileNotFoundError(SQL_PATH)

        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        connection.timeout = 600
        cursor = connection.cursor()

        for index, value in enumerate(lines):
            if value.startswith("Connection status:"):
                lines[index] = "Connection status: SUCCESS"
                break

        lines += section("1. DEPENDENCY / SOURCE CONTROLS")

        cursor.execute(
            """
            SELECT o.name, o.type
            FROM sys.objects AS o
            JOIN sys.schemas AS s
              ON s.schema_id = o.schema_id
            WHERE s.name = 'analytics';
            """
        )
        objects = {
            str(row[0]): str(row[1]).strip()
            for row in cursor.fetchall()
        }

        missing_dependencies = sorted(
            name
            for name in DEPENDENCY_VIEWS
            if objects.get(name) != "V"
        )

        check(
            not missing_dependencies,
            "Both validated H2 ranking and security forward-return sources exist.",
            (
                "Missing dependency view(s): "
                + ", ".join(missing_dependencies)
            ),
        )

        cursor.execute(
            """
            SELECT c.name
            FROM sys.columns AS c
            JOIN sys.views AS v
              ON v.object_id = c.object_id
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name = 'v_security_monthly_forward_return_1m';
            """
        )
        actual_forward_columns = {
            str(row[0])
            for row in cursor.fetchall()
        }

        missing_forward_columns = sorted(
            REQUIRED_FORWARD_COLUMNS
            - actual_forward_columns
        )

        check(
            not missing_forward_columns,
            "Validated security forward-return view exposes all required fields.",
            (
                "Missing required forward-return field(s): "
                + ", ".join(missing_forward_columns)
            ),
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_sector_momentum_portfolio;
            """,
            EXPECTED_H2_ASSIGNMENTS,
            "H2 fixed assignment layer remains exactly 30,121 rows.",
            "H2 assignment rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_forward_return_1m;
            """,
            EXPECTED_H2_ASSIGNMENTS,
            (
                "Validated security forward-return layer remains exactly "
                "30,121 rows."
            ),
            "Validated security forward rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_SECURITY_RETURNS,
            (
                "Validated security forward-return source still contains "
                "29,620 complete returns."
            ),
            "Complete security forward returns",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_forward_return_1m
            WHERE out_of_scope_right_censored = 1;
            """,
            EXPECTED_RIGHT_CENSORED_SECURITY,
            "Exactly 501 December-2025 security rows remain right-censored.",
            "Right-censored security forward rows",
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table} remains {expected:,} rows.",
                f"core.{table} rows",
            )

        if failures:
            raise RuntimeError(
                "Pre-migration dependency/source gate failed."
            )

        lines += section("2. APPLY H2 FORWARD-RETURN VIEWS")

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )

        check(
            len(batches) == 5,
            "H2 forward-return migration contains exactly five SQL batches.",
            f"Migration batches: {len(batches)}; expected 5.",
        )

        create_view_first_statement_failures = 0
        invalid_batch_numbers: list[int] = []

        for batch_number, batch in enumerate(
            batches,
            start=1,
        ):
            # SQL Server allows leading comments before CREATE VIEW.
            # Strip only a leading block comment for this structural check.
            batch_check = re.sub(
                r"^\s*/\*.*?\*/\s*",
                "",
                batch,
                flags=re.DOTALL,
            ).lstrip()

            if not batch_check.upper().startswith(
                "CREATE OR ALTER VIEW"
            ):
                create_view_first_statement_failures += 1
                invalid_batch_numbers.append(batch_number)

        if invalid_batch_numbers:
            lines.append(
                "Invalid CREATE VIEW batch numbers: "
                + ", ".join(
                    str(number)
                    for number in invalid_batch_numbers
                )
            )

        check(
            create_view_first_statement_failures == 0,
            (
                "Every SQL batch begins with CREATE OR ALTER VIEW "
                "as required by SQL Server."
            ),
            (
                "SQL batches violating CREATE VIEW first-statement rule: "
                f"{create_view_first_statement_failures}."
            ),
        )

        if failures:
            raise RuntimeError(
                "H2 forward-return migration structure is invalid."
            )

        for batch_number, batch in enumerate(
            batches,
            start=1,
        ):
            cursor.execute(batch)
            lines.append(
                f"PASS: Executed SQL batch {batch_number} / 5."
            )
            passed += 1

        lines += section("3. SECURITY-LEVEL H2 HOLDING POPULATION")

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_security_monthly_forward_return_1m;
            """,
            EXPECTED_H2_ASSIGNMENTS,
            "H2 security holding layer preserves all 30,121 assignments.",
            "H2 security holding rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_security_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_SECURITY_RETURNS,
            (
                "H2 security holding layer contains exactly "
                "29,620 complete returns."
            ),
            "Complete H2 security returns",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_security_monthly_forward_return_1m
            WHERE out_of_scope_right_censored = 1;
            """,
            EXPECTED_RIGHT_CENSORED_SECURITY,
            "Only the 501 final-month H2 assignments are right-censored.",
            "H2 right-censored security rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
            (
                SELECT
                    analysis_month_number,
                    security_key,
                    COUNT_BIG(*) AS n
                FROM analytics.v_h2_security_monthly_forward_return_1m
                GROUP BY analysis_month_number, security_key
                HAVING COUNT_BIG(*) <> 1
            ) AS bad;
            """,
            0,
            "Every H2 month/security assignment has exactly one holding row.",
            "Duplicate/missing H2 security holding keys",
        )

        lines += section("4. SECTOR / AGGREGATE RETURN POPULATIONS")

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_quintile_forward_return_1m;
            """,
            EXPECTED_SECTOR_QUINTILE_ROWS,
            "Sector/quintile layer contains 3,300 rows.",
            "Sector/quintile rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_quintile_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_SECTOR_QUINTILE_ROWS,
            (
                "Sector/quintile layer contains 3,245 complete rows "
                "(59 months x 11 sectors x 5 quintiles)."
            ),
            "Complete sector/quintile rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_extreme_forward_return_1m;
            """,
            EXPECTED_EXTREME_ROWS,
            "Winner/Loser sector-sleeve layer contains 1,320 rows.",
            "Extreme sector rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_extreme_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_EXTREME_ROWS,
            (
                "Winner/Loser sector-sleeve layer contains "
                "1,298 complete rows."
            ),
            "Complete extreme sector rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_neutral_leg_forward_return_1m;
            """,
            EXPECTED_LEG_ROWS,
            "Sector-neutral Winner/Loser leg layer contains 120 rows.",
            "Sector-neutral leg rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_neutral_leg_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_LEG_ROWS,
            "Sector-neutral Winner/Loser layer contains 118 complete legs.",
            "Complete sector-neutral legs",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_neutral_wml_forward_return_1m;
            """,
            EXPECTED_WML_ROWS,
            "Sector-neutral W-L layer contains all 60 ranking months.",
            "H2 W-L rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_neutral_wml_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_WML_ROWS,
            "Sector-neutral W-L contains exactly 59 observable months.",
            "Complete H2 W-L rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_neutral_wml_forward_return_1m
            WHERE out_of_scope_right_censored = 1;
            """,
            1,
            "Exactly one H2 W-L row (December 2025) is right-censored.",
            "Right-censored H2 W-L rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_neutral_leg_forward_return_1m
            WHERE sector_count <> 11;
            """,
            0,
            "Every aggregate Winner/Loser leg contains all 11 sectors.",
            "Aggregate legs missing sectors",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_quintile_forward_return_1m
            WHERE ABS(sector_equal_weight_sum - 1.0)
                > 0.000000000001;
            """,
            0,
            "Every sector/quintile sleeve retains total target weight 1.",
            "Sector/quintile weight-sum errors",
        )

        lines += section("5. CENSORING / DEPENDENCY CONTROLS")

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_security_monthly_forward_return_1m
            WHERE analysis_month_number < 60
              AND forward_return_1m_complete <> 1;
            """,
            0,
            "Every H2 assignment in months 1-59 has a complete return.",
            "Incomplete H2 security returns before month 60",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_h2_sector_neutral_wml_forward_return_1m
            WHERE analysis_month_number < 60
              AND forward_return_1m_complete <> 1;
            """,
            0,
            "Every H2 aggregate W-L row in months 1-59 is complete.",
            "Incomplete H2 W-L rows before month 60",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM sys.sql_expression_dependencies AS d
            JOIN sys.views AS v
              ON v.object_id = d.referencing_id
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name IN
              (
                  'v_h2_security_monthly_forward_return_1m',
                  'v_h2_sector_quintile_forward_return_1m',
                  'v_h2_sector_extreme_forward_return_1m',
                  'v_h2_sector_neutral_leg_forward_return_1m',
                  'v_h2_sector_neutral_wml_forward_return_1m'
              )
              AND LOWER(
                    COALESCE(
                        OBJECT_NAME(d.referenced_id),
                        ''
                    )
                  ) LIKE '%h2%stat%';
            """,
            0,
            "H2 return construction has no dependency on H2 statistical output.",
            "Backward H2 statistical dependency",
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table} remains unchanged at {expected:,} rows.",
                f"core.{table} final rows",
            )

        if failures:
            raise RuntimeError(
                "H2 forward-return application quality gate failed."
            )

        connection.commit()

        lines += [
            "",
            "AZURE_SQL_H2_SECTOR_FORWARD_RETURN_APPLICATION_PASSED",
            f"Passed checks: {passed}",
            f"H2 security holding rows: {EXPECTED_H2_ASSIGNMENTS:,}",
            (
                "Complete H2 security holding returns: "
                f"{EXPECTED_COMPLETE_SECURITY_RETURNS:,}"
            ),
            (
                "Sector/quintile rows: "
                f"{EXPECTED_SECTOR_QUINTILE_ROWS:,}"
            ),
            f"Sector-neutral leg rows: {EXPECTED_LEG_ROWS}",
            f"H2 W-L rows: {EXPECTED_WML_ROWS}",
            f"Complete observable H2 W-L months: {EXPECTED_COMPLETE_WML_ROWS}",
            "Statistical / risk / cost interpretation performed: 0",
            "Core rows modified: 0",
            (
                "H2 forward-return population is ready for independent "
                "integrity audit. Do not run H2 inference yet."
            ),
        ]

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        lines += [
            "",
            "AZURE_SQL_H2_SECTOR_FORWARD_RETURN_APPLICATION_FAILED",
            type(error).__name__,
            str(error),
        ]

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

        REPORT_PATH.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
