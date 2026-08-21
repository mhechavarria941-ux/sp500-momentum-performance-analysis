from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from mssql_python import connect


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_return_foundation_integrity_audit.txt"
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


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def main() -> None:
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL RETURN-FOUNDATION INTEGRITY AUDIT"
    )
    lines += [
        "Audit mode: READ-ONLY",
        "Credentials included in report: NO",
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

    def check_scalar(
        cursor,
        query: str,
        expected: int,
        success: str,
        failure_label: str,
    ) -> int:
        actual = scalar(cursor, query)

        check(
            actual == expected,
            success,
            (
                f"{failure_label}: found {actual:,}; "
                f"expected {expected:,}."
            ),
        )
        return actual

    try:
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

        lines += section(
            "1. OBJECT AND SOURCE CONTROLS"
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
        missing_views = sorted(
            EXPECTED_VIEWS - actual_views
        )

        check(
            not missing_views,
            (
                "All six return-foundation views "
                "are present."
            ),
            "Missing views: " + ", ".join(missing_views),
        )

        for table, expected in EXPECTED_CORE_COUNTS.items():
            check_scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table}: {expected:,} rows.",
                f"core.{table} population",
            )

        lines.append("")

        lines += section(
            "2. SPY TRADING CALENDAR"
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_spy_trading_calendar;
            """,
            1_255,
            (
                "SPY calendar contains exactly "
                "1,255 sessions."
            ),
            "SPY session count",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT price_date
                FROM analytics.v_spy_trading_calendar
                GROUP BY price_date
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            "SPY calendar dates are unique.",
            "Duplicate SPY dates",
        )

        cursor.execute(
            """
            SELECT
                MIN(price_date),
                MAX(price_date)
            FROM analytics.v_spy_trading_calendar;
            """
        )
        first_spy_date, last_spy_date = (
            cursor.fetchone()
        )

        check(
            str(first_spy_date) == "2021-01-04",
            (
                "First SPY trading session "
                "is 2021-01-04."
            ),
            (
                "First SPY trading session is "
                f"{first_spy_date}."
            ),
        )

        check(
            str(last_spy_date) == "2025-12-31",
            (
                "Last SPY trading session "
                "is 2025-12-31."
            ),
            (
                "Last SPY trading session is "
                f"{last_spy_date}."
            ),
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_spy_trading_calendar
                AS current_session
            LEFT JOIN analytics.v_spy_trading_calendar
                AS prior_session
              ON prior_session.trading_session_number
               = current_session.trading_session_number - 1
            WHERE current_session.trading_session_number > 1
              AND (
                    prior_session.price_date IS NULL
                 OR current_session.previous_spy_session
                    <> prior_session.price_date
              );
            """,
            0,
            (
                "Every SPY session points to its "
                "immediately preceding session."
            ),
            "Invalid SPY predecessor mappings",
        )

        lines.append("")

        lines += section(
            "3. EXACT SPY MONTH-END CALENDAR"
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_spy_month_end_calendar;
            """,
            60,
            (
                "Month-end calendar contains "
                "exactly 60 months."
            ),
            "Month-end count",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    calendar_year,
                    calendar_month
                FROM analytics.v_spy_month_end_calendar
                GROUP BY
                    calendar_year,
                    calendar_month
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            (
                "Every calendar month has exactly "
                "one SPY month-end."
            ),
            "Duplicate month-end calendar months",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_spy_month_end_calendar
                AS month_end
            WHERE month_end.month_end_date <> (
                SELECT MAX(calendar.price_date)
                FROM analytics.v_spy_trading_calendar
                    AS calendar
                WHERE YEAR(calendar.price_date)
                    = month_end.calendar_year
                  AND MONTH(calendar.price_date)
                    = month_end.calendar_month
            );
            """,
            0,
            (
                "Every month-end is the final SPY "
                "session of its calendar month."
            ),
            "Incorrect SPY month-end dates",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_spy_month_end_calendar
            WHERE analysis_month_number < 1
               OR analysis_month_number > 60;
            """,
            0,
            (
                "Analysis-month numbering is "
                "limited to 1 through 60."
            ),
            "Invalid analysis-month numbers",
        )

        lines.append("")

        lines += section(
            "4. CONSTITUENT DAILY RETURNS"
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_daily_return;
            """,
            631_942,
            (
                "Daily-return view preserves all "
                "631,942 constituent rows."
            ),
            "Constituent daily-return rows",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    security_key,
                    price_date
                FROM analytics.v_security_daily_return
                GROUP BY
                    security_key,
                    price_date
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            (
                "Constituent security/date return "
                "keys are unique."
            ),
            "Duplicate constituent return keys",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_daily_return
            WHERE daily_return_complete = 1
              AND (
                    daily_return IS NULL
                 OR previous_price_date
                    <> expected_previous_price_date
              );
            """,
            0,
            (
                "Every complete constituent return "
                "uses the prior SPY session."
            ),
            "Invalid complete constituent returns",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_daily_return
            WHERE daily_return_complete = 0
              AND daily_return IS NOT NULL;
            """,
            0,
            (
                "Incomplete constituent returns "
                "remain null."
            ),
            (
                "Populated incomplete "
                "constituent returns"
            ),
        )

        incomplete_security_returns = check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_daily_return
            WHERE daily_return_complete = 0;
            """,
            593,
            (
                "Exactly one initial return is "
                "incomplete per security identity."
            ),
            "Incomplete constituent returns",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_daily_return
            WHERE daily_return_complete = 1
              AND ABS(
                    CAST(daily_return AS float)
                    - (
                        CAST(adjusted_close AS float)
                        / CAST(
                            previous_adjusted_close
                            AS float
                        )
                        - 1.0
                    )
                  ) > 0.000000000000001;
            """,
            0,
            (
                "Every constituent return matches "
                "the adjusted-close formula."
            ),
            (
                "Constituent return formula "
                "mismatches"
            ),
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_daily_return
            WHERE security_key = 'DAY'
              AND project_ticker = 'DAY'
              AND previous_project_ticker = 'CDAY'
              AND daily_return_complete = 1;
            """,
            1,
            (
                "The CDAY-to-DAY transition preserves "
                "security-return continuity."
            ),
            "Complete CDAY-to-DAY transition rows",
        )

        lines.append("")

        lines += section(
            "5. BENCHMARK DAILY RETURNS"
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_daily_return;
            """,
            2_510,
            (
                "Benchmark daily-return view contains "
                "exactly 2,510 rows."
            ),
            "Benchmark daily-return rows",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_daily_return
            WHERE daily_return_complete = 1
              AND daily_return IS NOT NULL
              AND previous_price_date
                  = expected_previous_price_date;
            """,
            2_508,
            (
                "Both benchmarks contain "
                "1,254 complete daily returns."
            ),
            "Complete benchmark returns",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_daily_return
            WHERE daily_return_complete = 0
              AND daily_return IS NULL;
            """,
            2,
            (
                "Each benchmark has one initial "
                "incomplete return."
            ),
            "Incomplete benchmark returns",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_daily_return
            WHERE daily_return_complete = 1
              AND ABS(
                    CAST(daily_return AS float)
                    - (
                        CAST(adjusted_close AS float)
                        / CAST(
                            previous_adjusted_close
                            AS float
                        )
                        - 1.0
                    )
                  ) > 0.000000000000001;
            """,
            0,
            (
                "Every benchmark return matches "
                "the adjusted-close formula."
            ),
            "Benchmark return formula mismatches",
        )

        lines.append("")

        lines += section(
            "6. EXACT MONTH-END PRICE OUTPUTS"
        )

        constituent_month_end_rows = check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_month_end_price;
            """,
            30_211,
            (
                "Constituent month-end output contains "
                "30,211 observations."
            ),
            "Constituent month-end rows",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT month_end_date)
            FROM analytics.v_security_month_end_price;
            """,
            60,
            (
                "Constituent output covers all "
                "60 SPY month-ends."
            ),
            "Constituent month-end coverage",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    month_end_date,
                    security_key
                FROM analytics.v_security_month_end_price
                GROUP BY
                    month_end_date,
                    security_key
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            (
                "Constituent month-end security/date "
                "keys are unique."
            ),
            (
                "Duplicate constituent "
                "month-end keys"
            ),
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_month_end_price
                AS price
            LEFT JOIN analytics.v_spy_month_end_calendar
                AS calendar
              ON calendar.month_end_date
               = price.month_end_date
            WHERE calendar.month_end_date IS NULL;
            """,
            0,
            (
                "Every constituent observation uses "
                "an exact SPY month-end."
            ),
            (
                "Non-SPY constituent "
                "month-end rows"
            ),
        )

        cursor.execute(
            """
            SELECT
                MIN(month_population),
                MAX(month_population)
            FROM (
                SELECT
                    month_end_date,
                    COUNT_BIG(*) AS month_population
                FROM analytics.v_security_month_end_price
                GROUP BY month_end_date
            ) AS populations;
            """
        )
        min_population, max_population = (
            int(value)
            for value in cursor.fetchone()
        )

        check(
            (
                min_population >= 502
                and max_population <= 506
            ),
            (
                "Monthly constituent populations remain "
                "within the validated daily bounds: "
                f"{min_population}-{max_population}."
            ),
            (
                "Monthly population range falls outside "
                "the validated daily bounds: "
                f"{min_population}-{max_population}."
            ),
        )

        check_scalar(
            cursor,
            """
            WITH expected_populations AS (
                SELECT
                    calendar.month_end_date,
                    COUNT_BIG(*) AS expected_population
                FROM analytics.v_spy_month_end_calendar
                    AS calendar
                INNER JOIN core.daily_security_price
                    AS price
                  ON price.price_date
                   = calendar.month_end_date
                GROUP BY calendar.month_end_date
            ),
            actual_populations AS (
                SELECT
                    month_end_date,
                    COUNT_BIG(*) AS actual_population
                FROM analytics.v_security_month_end_price
                GROUP BY month_end_date
            )
            SELECT COUNT_BIG(*)
            FROM expected_populations AS expected
            FULL OUTER JOIN actual_populations AS actual
              ON actual.month_end_date
               = expected.month_end_date
            WHERE expected.month_end_date IS NULL
               OR actual.month_end_date IS NULL
               OR expected.expected_population
                  <> actual.actual_population;
            """,
            0,
            (
                "Every monthly population exactly matches "
                "the underlying core month-end prices."
            ),
            "Month-end population reconciliation failures",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_month_end_price;
            """,
            120,
            (
                "Benchmark output contains two series "
                "across 60 month-ends."
            ),
            "Benchmark month-end rows",
        )

        check_scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    security_key,
                    project_ticker
                FROM analytics.v_benchmark_month_end_price
                GROUP BY
                    security_key,
                    project_ticker
                HAVING COUNT_BIG(*) = 60
            ) AS complete_series;
            """,
            2,
            (
                "Both benchmarks contain all "
                "60 month-end observations."
            ),
            (
                "Complete benchmark "
                "month-end series"
            ),
        )

        lines.append("")

        lines += section(
            "7. FINAL QUALITY GATE"
        )

        if failures:
            lines += [
                (
                    "AZURE_SQL_RETURN_FOUNDATION_"
                    "INTEGRITY_AUDIT_FAILED"
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
            complete_constituent_returns = (
                631_942 - incomplete_security_returns
            )

            lines += [
                (
                    "AZURE_SQL_RETURN_FOUNDATION_"
                    "INTEGRITY_AUDIT_PASSED"
                ),
                f"Passed checks: {passed_checks}",
                "SPY trading sessions: 1,255",
                "SPY month-end sessions: 60",
                (
                    "Constituent daily observations: "
                    "631,942"
                ),
                (
                    "Constituent complete daily returns: "
                    f"{complete_constituent_returns:,}"
                ),
                (
                    "Constituent month-end observations: "
                    f"{constituent_month_end_rows:,}"
                ),
                "Benchmark daily observations: 2,510",
                "Benchmark month-end observations: 120",
                "Core rows modified: 0",
                (
                    "Daily-return and exact-month-end "
                    "foundations are analysis-ready."
                ),
                (
                    "SQL RETURN-FOUNDATION "
                    "QUALITY GATE COMPLETE."
                ),
            ]

        cursor.close()

    except Exception as error:
        lines += [""] + section(
            "AUDIT EXECUTION FAILED"
        )
        lines += [
            type(error).__name__,
            str(error),
            (
                "AZURE_SQL_RETURN_FOUNDATION_"
                "INTEGRITY_AUDIT_FAILED"
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