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
    / "008_create_portfolio_performance_views.sql"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_portfolio_performance_application.txt"
)

NEW_VIEWS = {
    "v_momentum_monthly_return_panel",
    "v_momentum_cumulative_wealth",
    "v_momentum_wealth_drawdown",
    "v_momentum_performance_summary",
    "v_momentum_decile_turnover",
    "v_momentum_turnover_summary",
}

DEPENDENCY_VIEWS = {
    "v_security_monthly_momentum_portfolio",
    "v_momentum_decile_forward_return_1m",
    "v_momentum_long_short_forward_return_1m",
    "v_benchmark_monthly_forward_return_1m",
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

EXPECTED_PANEL_ROWS = 611
EXPECTED_SERIES = 13
EXPECTED_OBSERVABLE_MONTHS = 47
EXPECTED_PERFORMANCE_ROWS = 13
EXPECTED_TURNOVER_ROWS = 470
EXPECTED_TURNOVER_SUMMARY_ROWS = 10
EXPECTED_REBALANCES = 47

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
        "AZURE SQL PORTFOLIO-PERFORMANCE APPLICATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        (
            "Strategy: gross portfolio performance, "
            "cumulative wealth, drawdown, and turnover"
        ),
        (
            "Excluded by design: risk-free rates, Sharpe "
            "ratios, regression alpha, and transaction costs"
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
                "All four ranking and forward-return "
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
            FROM analytics
                .v_security_monthly_momentum_portfolio;
            """,
            23_401,
            (
                "The ranking source still contains "
                "23,401 fixed portfolio assignments."
            ),
            "Portfolio assignment rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            470,
            (
                "The source contains 470 complete "
                "month/decile forward returns."
            ),
            "Complete decile forward-return rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_long_short_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            47,
            (
                "The source contains 47 complete "
                "winner-minus-loser returns."
            ),
            "Complete winner-minus-loser rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            94,
            (
                "The benchmark source contains 94 "
                "complete returns across two series."
            ),
            "Complete benchmark forward-return rows",
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
            "2. APPLY PORTFOLIO-PERFORMANCE VIEWS"
        )

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )

        check(
            len(batches) == 7,
            (
                "Migration contains the expected "
                "seven SQL batches."
            ),
            (
                f"Migration contains {len(batches)} "
                "batches; expected 7."
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
            "3. MONTHLY RETURN PANEL"
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
            (
                "All six portfolio-performance views "
                "are present."
            ),
            "Missing views: " + ", ".join(missing_views),
        )

        panel_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
            EXPECTED_PANEL_ROWS,
            (
                "The monthly return panel contains "
                "611 complete series/month observations."
            ),
            "Monthly return-panel rows",
        )

        expect(
            """
            SELECT COUNT_BIG(DISTINCT series_code)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
            EXPECTED_SERIES,
            (
                "The panel contains all 13 analytical "
                "series."
            ),
            "Return-panel series",
        )

        expect(
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
            EXPECTED_OBSERVABLE_MONTHS,
            (
                "The panel contains exactly 47 observable "
                "holding months."
            ),
            "Observable return-panel months",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    analysis_month_number,
                    series_code,
                    COUNT_BIG(*) AS row_count
                FROM analytics.v_momentum_monthly_return_panel
                GROUP BY
                    analysis_month_number,
                    series_code
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            (
                "Every month/series key in the return "
                "panel is unique."
            ),
            "Duplicate month/series return-panel keys",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_monthly_return_panel
            WHERE monthly_return IS NULL
               OR return_complete <> 1;
            """,
            0,
            (
                "Every panel observation is a complete, "
                "non-null monthly return."
            ),
            "Incomplete return-panel rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    series_code,
                    COUNT_BIG(*) AS observed_months
                FROM analytics.v_momentum_monthly_return_panel
                GROUP BY series_code
                HAVING COUNT_BIG(*) <> 47
            ) AS bad_series;
            """,
            0,
            (
                "Each analytical series contains exactly "
                "47 monthly returns."
            ),
            "Series with incorrect monthly populations",
        )

        lines.append("")
        lines += section(
            "4. CUMULATIVE WEALTH AND DRAWDOWN"
        )

        wealth_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_cumulative_wealth;
            """,
            panel_rows,
            (
                "Cumulative wealth preserves every "
                "monthly return-panel row."
            ),
            "Cumulative-wealth rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_cumulative_wealth
            WHERE return_sequence = 1
              AND ABS(
                    CAST(beginning_wealth AS float) - 1.0
                  ) > 0.000000000001;
            """,
            0,
            (
                "Every series begins with wealth indexed "
                "to 1.00."
            ),
            "Invalid initial wealth rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_cumulative_wealth
            WHERE beginning_wealth <= 0
               OR ending_wealth <= 0
               OR return_period_count <> 47;
            """,
            0,
            (
                "All wealth observations are positive and "
                "use 47 return periods."
            ),
            "Invalid cumulative-wealth rows",
        )

        expect(
            """
            WITH chained AS (
                SELECT
                    series_code,
                    analysis_month_number,
                    beginning_wealth,
                    LAG(ending_wealth) OVER (
                        PARTITION BY series_code
                        ORDER BY analysis_month_number
                    ) AS previous_ending_wealth
                FROM analytics.v_momentum_cumulative_wealth
            )
            SELECT COUNT_BIG(*)
            FROM chained
            WHERE previous_ending_wealth IS NOT NULL
              AND ABS(
                    CAST(beginning_wealth AS float)
                    - CAST(previous_ending_wealth AS float)
                  ) > 0.000000000001;
            """,
            0,
            (
                "Every month's beginning wealth equals "
                "the previous month's ending wealth."
            ),
            "Broken cumulative-wealth chains",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_cumulative_wealth
            WHERE ABS(
                    CAST(ending_wealth AS float)
                    - CAST(beginning_wealth AS float)
                      * (1.0 + CAST(monthly_return AS float))
                  ) > 0.000000000001;
            """,
            0,
            (
                "Every ending wealth value matches the "
                "monthly compounding formula."
            ),
            "Cumulative-wealth formula mismatches",
        )

        drawdown_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_wealth_drawdown;
            """,
            wealth_rows,
            (
                "The drawdown view preserves every "
                "cumulative-wealth observation."
            ),
            "Drawdown rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_wealth_drawdown
            WHERE running_peak_wealth < 1
               OR drawdown > 0.000000000001
               OR drawdown < -1.000000000001;
            """,
            0,
            (
                "Running peaks and drawdowns remain "
                "within valid wealth bounds."
            ),
            "Invalid running-peak or drawdown rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_wealth_drawdown
            WHERE ABS(
                    CAST(drawdown AS float)
                    - (
                        CAST(ending_wealth AS float)
                        / CAST(running_peak_wealth AS float)
                        - 1.0
                    )
                  ) > 0.000000000001;
            """,
            0,
            (
                "Every drawdown matches ending wealth "
                "relative to its running peak."
            ),
            "Drawdown formula mismatches",
        )

        lines.append("")
        lines += section(
            "5. PERFORMANCE SUMMARY"
        )

        performance_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_performance_summary;
            """,
            EXPECTED_PERFORMANCE_ROWS,
            (
                "The performance summary contains one "
                "row for each of 13 analytical series."
            ),
            "Performance-summary rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_performance_summary
            WHERE observed_months <> 47
               OR final_wealth <= 0
               OR positive_month_frequency < 0
               OR positive_month_frequency > 1
               OR maximum_drawdown > 0.000000000001
               OR maximum_drawdown < -1.000000000001
               OR monthly_volatility < 0
               OR annualized_volatility < 0;
            """,
            0,
            (
                "All summary statistics have valid "
                "populations and numeric bounds."
            ),
            "Invalid performance-summary statistics",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_performance_summary
            WHERE ABS(
                    CAST(cumulative_return AS float)
                    - (CAST(final_wealth AS float) - 1.0)
                  ) > 0.000000000001;
            """,
            0,
            (
                "Every cumulative return reconciles to "
                "final wealth minus one."
            ),
            "Cumulative-return summary mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_performance_summary
            WHERE ABS(
                    CAST(annualized_volatility AS float)
                    - CAST(monthly_volatility AS float)
                      * SQRT(12.0)
                  ) > 0.000000000001;
            """,
            0,
            (
                "Every annualized volatility matches "
                "monthly volatility times sqrt(12)."
            ),
            "Annualized-volatility formula mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_performance_summary
            WHERE series_code = 'SPY'
              AND (
                    ABS(
                        CAST(mean_monthly_active_return_vs_spy AS float)
                    ) > 0.000000000001
                 OR ABS(
                        CAST(annualized_active_return_vs_spy AS float)
                    ) > 0.000000000001
                 OR ABS(
                        CAST(annualized_tracking_error_vs_spy AS float)
                    ) > 0.000000000001
                 OR information_ratio_vs_spy IS NOT NULL
              );
            """,
            0,
            (
                "SPY correctly has zero active return and "
                "tracking error versus itself."
            ),
            "Invalid SPY self-relative statistics",
        )

        lines.append("")
        lines += section(
            "6. PORTFOLIO TURNOVER"
        )

        turnover_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_decile_turnover;
            """,
            EXPECTED_TURNOVER_ROWS,
            (
                "The turnover layer contains all 470 "
                "month/decile rebalances."
            ),
            "Decile-turnover rows",
        )

        expect(
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_momentum_decile_turnover;
            """,
            EXPECTED_REBALANCES,
            (
                "Turnover spans exactly 47 consecutive "
                "monthly rebalances."
            ),
            "Turnover rebalance months",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_decile_turnover
            WHERE current_security_count <> (
                    retained_security_count
                    + entered_security_count
                  )
               OR previous_security_count <> (
                    retained_security_count
                    + exited_security_count
                  )
               OR current_security_count < 48
               OR current_security_count > 50
               OR previous_security_count < 48
               OR previous_security_count > 50
               OR security_overlap_rate < 0
               OR security_overlap_rate > 1
               OR target_weight_one_way_turnover < 0
               OR target_weight_one_way_turnover > 1;
            """,
            0,
            (
                "Every turnover row reconciles security "
                "counts, overlap, and one-way turnover."
            ),
            "Invalid decile-turnover rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    analysis_month_number,
                    momentum_decile,
                    COUNT_BIG(*) AS row_count
                FROM analytics.v_momentum_decile_turnover
                GROUP BY
                    analysis_month_number,
                    momentum_decile
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            (
                "Every month/decile turnover key is "
                "unique."
            ),
            "Duplicate month/decile turnover keys",
        )

        turnover_summary_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_turnover_summary;
            """,
            EXPECTED_TURNOVER_SUMMARY_ROWS,
            (
                "The turnover summary contains one row "
                "for each momentum decile."
            ),
            "Turnover-summary rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_turnover_summary
            WHERE observed_rebalances <> 47
               OR average_monthly_target_weight_turnover < 0
               OR average_monthly_target_weight_turnover > 1
               OR annualized_target_weight_turnover < 0
               OR average_security_overlap_rate < 0
               OR average_security_overlap_rate > 1;
            """,
            0,
            (
                "Every turnover summary row has 47 "
                "rebalances and valid metric bounds."
            ),
            "Invalid turnover-summary rows",
        )

        lines.append("")
        lines += section(
            "7. METHODOLOGY AND LOOK-AHEAD CONTROLS"
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.columns AS c
            JOIN sys.views AS v
              ON v.object_id = c.object_id
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name IN (
                    'v_momentum_monthly_return_panel',
                    'v_momentum_cumulative_wealth',
                    'v_momentum_wealth_drawdown',
                    'v_momentum_performance_summary',
                    'v_momentum_decile_turnover',
                    'v_momentum_turnover_summary'
              )
              AND (
                    LOWER(c.name) LIKE '%sharpe%'
                 OR LOWER(c.name) LIKE '%alpha%'
                 OR LOWER(c.name) LIKE '%risk_free%'
                 OR LOWER(c.name) LIKE '%transaction_cost%'
                 OR LOWER(c.name) LIKE '%net_of_cost%'
              );
            """,
            0,
            (
                "No deferred Sharpe, alpha, risk-free, "
                "or transaction-cost fields are present."
            ),
            "Deferred methodology columns present",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_monthly_return_panel
            WHERE analysis_month_number = 60;
            """,
            0,
            (
                "The right-censored December 2025 ranking "
                "month is excluded from gross performance."
            ),
            "Right-censored rows in performance panel",
        )

        lines.append("")
        lines += section(
            "8. POST-MIGRATION CORE CONTROL"
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
            "PASS: Portfolio-performance migration committed."
        )
        passed += 1

        lines.append("")
        lines += section("9. FINAL QUALITY GATE")
        lines += [
            "AZURE_SQL_PORTFOLIO_PERFORMANCE_APPLICATION_PASSED",
            f"Passed checks: {passed}",
            "Analytical views created or updated: 6",
            f"Monthly return-panel rows: {panel_rows:,}",
            f"Analytical series: {EXPECTED_SERIES}",
            (
                "Observable gross-performance months: "
                f"{EXPECTED_OBSERVABLE_MONTHS}"
            ),
            f"Cumulative-wealth rows: {wealth_rows:,}",
            f"Drawdown rows: {drawdown_rows:,}",
            f"Performance-summary rows: {performance_rows:,}",
            f"Decile-turnover rows: {turnover_rows:,}",
            (
                "Turnover-summary rows: "
                f"{turnover_summary_rows:,}"
            ),
            "Gross performance convention: YES",
            "Risk-free-rate dependency: NO",
            "Sharpe ratio calculated: NO",
            "Regression alpha calculated: NO",
            "Transaction costs applied: NO",
            "Core rows modified: 0",
            (
                "Gross portfolio performance, cumulative "
                "wealth, drawdown, and turnover are ready "
                "for independent auditing."
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
            "AZURE_SQL_PORTFOLIO_PERFORMANCE_APPLICATION_FAILED",
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
