from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from mssql_python import connect


ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = (
    ROOT
    / "sql"
    / "analytics"
    / "003_create_return_foundation_views.sql"
)
REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_return_foundation_application.txt"
)

EXPECTED_VIEWS = {
    "v_benchmark_daily_return",
    "v_benchmark_month_end_price",
    "v_security_daily_return",
    "v_security_month_end_price",
    "v_spy_month_end_calendar",
    "v_spy_trading_calendar",
}

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
        "AZURE SQL RETURN-FOUNDATION APPLICATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        "Migration type: CREATE OR ALTER analytical views",
        "",
    ]

    failures: list[str] = []
    passed_checks = 0
    connection = None

    def check(
        condition: bool,
        success: str,
        failure: str,
    ) -> None:
        nonlocal passed_checks

        if condition:
            lines.append(f"PASS: {success}")
            passed_checks += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    try:
        if not SQL_PATH.exists():
            raise FileNotFoundError(
                f"SQL migration not found: {SQL_PATH}"
            )

        server, database, username, password = environment()

        connection = connect(
            server=server,
            database=database,
            uid=username,
            pwd=password,
            encrypt="yes",
            trust_server_certificate="no",
            timeout=300,
        )
        cursor = connection.cursor()

        lines[3] = "Connection status: SUCCESS"

        lines += section(
            "1. PRE-MIGRATION CORE CONTROL"
        )

        for table, expected in EXPECTED_CORE_COUNTS.items():
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
                "Pre-migration core population control failed."
            )

        lines.append("")

        lines += section(
            "2. APPLY ANALYTICAL VIEWS"
        )

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )

        check(
            len(batches) == 8,
            (
                "Migration contains the expected "
                "eight SQL batches."
            ),
            (
                f"Migration contains {len(batches)} "
                "batches; expected 8."
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
            passed_checks += 1

        connection.commit()

        lines.append(
            "PASS: Analytical-view migration committed."
        )
        passed_checks += 1
        lines.append("")

        lines += section(
            "3. VERIFY ANALYTICAL OBJECTS"
        )

        cursor.execute(
            """
            SELECT v.name
            FROM sys.views AS v
            INNER JOIN sys.schemas AS s
                ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics';
            """
        )
        actual_views = {
            str(row[0])
            for row in cursor.fetchall()
        }

        missing_views = sorted(
            EXPECTED_VIEWS - actual_views
        )

        check(
            not missing_views,
            (
                f"All {len(EXPECTED_VIEWS)} "
                "return-foundation views are present."
            ),
            "Missing views: " + ", ".join(missing_views),
        )

        populations = {
            "SPY trading sessions": scalar(
                cursor,
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_spy_trading_calendar;
                """,
            ),
            "SPY month-end sessions": scalar(
                cursor,
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_spy_month_end_calendar;
                """,
            ),
            "Constituent daily-return rows": scalar(
                cursor,
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_security_daily_return;
                """,
            ),
            "Benchmark daily-return rows": scalar(
                cursor,
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_benchmark_daily_return;
                """,
            ),
            "Constituent month-end rows": scalar(
                cursor,
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_security_month_end_price;
                """,
            ),
            "Benchmark month-end rows": scalar(
                cursor,
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_benchmark_month_end_price;
                """,
            ),
        }

        check(
            populations["SPY trading sessions"] == 1_255,
            (
                "SPY calendar contains "
                "1,255 trading sessions."
            ),
            (
                "SPY calendar does not contain "
                "1,255 sessions."
            ),
        )
        check(
            populations["SPY month-end sessions"] == 60,
            (
                "SPY calendar contains "
                "60 exact month-end sessions."
            ),
            (
                "SPY month-end calendar does not "
                "contain 60 sessions."
            ),
        )
        check(
            (
                populations[
                    "Constituent daily-return rows"
                ]
                == 631_942
            ),
            (
                "Constituent daily-return view preserves "
                "all 631,942 observations."
            ),
            (
                "Constituent daily-return population "
                "is incorrect."
            ),
        )
        check(
            populations["Benchmark daily-return rows"]
            == 2_510,
            (
                "Benchmark daily-return view preserves "
                "all 2,510 observations."
            ),
            (
                "Benchmark daily-return population "
                "is incorrect."
            ),
        )
        check(
            populations["Benchmark month-end rows"] == 120,
            (
                "Benchmark month-end view contains "
                "120 observations."
            ),
            (
                "Benchmark month-end view does not "
                "contain 120 observations."
            ),
        )
        check(
            populations["Constituent month-end rows"] > 0,
            (
                "Constituent month-end view "
                "is populated."
            ),
            (
                "Constituent month-end view is empty."
            ),
        )

        lines.append("")

        lines += section(
            "4. POST-MIGRATION CORE CONTROL"
        )

        for table, expected in EXPECTED_CORE_COUNTS.items():
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

        lines.append("")

        lines += section(
            "5. FINAL QUALITY GATE"
        )

        if failures:
            lines += [
                (
                    "AZURE_SQL_RETURN_FOUNDATION_"
                    "APPLICATION_FAILED"
                ),
                f"Passed checks: {passed_checks}",
                f"Failed checks: {len(failures)}",
            ]

            for number, failure in enumerate(
                failures,
                start=1,
            ):
                lines.append(f"{number}. {failure}")
        else:
            month_end_rows = populations[
                "Constituent month-end rows"
            ]

            lines += [
                (
                    "AZURE_SQL_RETURN_FOUNDATION_"
                    "APPLICATION_PASSED"
                ),
                f"Passed checks: {passed_checks}",
                "Analytical views created or updated: 6",
                (
                    "Constituent month-end observations: "
                    f"{month_end_rows:,}"
                ),
                "Core rows modified: 0",
                (
                    "SQL return foundation is ready for "
                    "independent integrity auditing."
                ),
            ]

        cursor.close()

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        lines += [""] + section(
            "APPLICATION FAILED"
        )
        lines += [
            type(error).__name__,
            str(error),
            (
                "AZURE_SQL_RETURN_FOUNDATION_"
                "APPLICATION_FAILED"
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