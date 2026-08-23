from __future__ import annotations

import os
import time
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_forward_return_integrity_audit.txt"
)

REQUIRED_VIEWS = {
    "v_benchmark_monthly_forward_return_1m",
    "v_momentum_decile_forward_return_1m",
    "v_momentum_long_short_forward_return_1m",
    "v_momentum_monthly_performance_1m",
    "v_security_monthly_forward_return_1m",
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
                autocommit=True,
            )
        except pyodbc.Error as error:
            retryable = any(
                term in str(error).lower()
                for term in retryable_terms
            )

            if not retryable or attempt == 5:
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


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = section(
        "AZURE SQL FORWARD-RETURN INTEGRITY AUDIT"
    )
    lines += [
        "Audit mode: READ-ONLY",
        "Credentials included in report: NO",
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
        server, database, username, password = environment()

        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )

        connection.timeout = 600
        cursor = connection.cursor()

        lines += section(
            "1. OBJECT AND CORE CONTROLS"
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

        missing = sorted(REQUIRED_VIEWS - actual_views)

        check(
            not missing,
            "All required forward-return views are present.",
            "Missing views: " + ", ".join(missing),
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table}: {expected:,} rows.",
                f"core.{table} population",
            )

        lines.append("")
        lines += section(
            "2. CONSTITUENT HOLDING-RETURN CONTROLS"
        )

        security_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m;
            """,
            23_401,
            (
                "Constituent holding output contains "
                "exactly 23,401 assignments."
            ),
            "Constituent holding rows",
        )

        complete_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            22_916,
            (
                "Exactly 22,916 constituent holding "
                "returns are complete."
            ),
            "Complete constituent holding returns",
        )

        exact_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE holding_end_is_exact_month_end = 1;
            """,
            22_850,
            (
                "Exactly 22,850 holdings end on the "
                "next SPY month-end."
            ),
            "Exact-month-end holdings",
        )

        early_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE holding_end_is_early_exit = 1;
            """,
            63,
            "Exactly 63 holdings use an early-exit boundary.",
            "Early-exit holdings",
        )

        immediate_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE holding_end_is_immediate_exit = 1;
            """,
            3,
            (
                "Exactly three holdings use an "
                "immediate-exit boundary."
            ),
            "Immediate-exit holdings",
        )

        censored_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE out_of_scope_right_censored = 1;
            """,
            485,
            (
                "Exactly 485 December 2025 holdings are "
                "right-censored outside scope."
            ),
            "Right-censored constituent holdings",
        )

        check(
            exact_rows + early_rows + immediate_rows
            == complete_rows,
            (
                "Exact and terminal holding boundaries "
                "reconcile to complete returns."
            ),
            "Complete holding-boundary counts do not reconcile.",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    analysis_month_number,
                    security_key
                FROM analytics
                    .v_security_monthly_forward_return_1m
                GROUP BY
                    analysis_month_number,
                    security_key
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            "Constituent month/security keys are unique.",
            "Duplicate constituent holding keys",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio
                AS assignment
            FULL OUTER JOIN analytics
                .v_security_monthly_forward_return_1m
                AS holding
              ON holding.analysis_month_number
               = assignment.analysis_month_number
             AND holding.security_key
               = assignment.security_key
            WHERE assignment.security_key IS NULL
               OR holding.security_key IS NULL
               OR holding.momentum_decile
                    <> assignment.momentum_decile
               OR holding.momentum_rank_desc
                    <> assignment.momentum_rank_desc
               OR holding.equal_weight
                    <> assignment.equal_weight
               OR holding.holding_start_adjusted_close
                    <> assignment.adjusted_close;
            """,
            0,
            (
                "Every holding row exactly preserves its "
                "fixed portfolio assignment."
            ),
            "Holding/assignment mismatches",
        )

        expect(
            """
            WITH expected AS (
                SELECT
                    assignment.analysis_month_number,
                    assignment.security_key,
                    next_month.month_end_date
                        AS target_end_date,
                    end_price.price_date
                        AS realized_end_date,
                    end_price.project_ticker
                        AS end_ticker,
                    end_price.provider_symbol
                        AS end_provider_symbol,
                    end_price.adjusted_close
                        AS end_adjusted_close
                FROM analytics
                    .v_security_monthly_momentum_portfolio
                    AS assignment
                LEFT JOIN analytics.v_spy_month_end_calendar
                    AS next_month
                  ON next_month.analysis_month_number
                   = assignment.analysis_month_number + 1
                OUTER APPLY (
                    SELECT TOP (1)
                        price.price_date,
                        price.project_ticker,
                        price.provider_symbol,
                        price.adjusted_close
                    FROM core.daily_security_price AS price
                    WHERE price.security_key
                        = assignment.security_key
                      AND price.price_date
                        >= assignment.month_end_date
                      AND price.price_date
                        <= next_month.month_end_date
                    ORDER BY
                        price.price_date DESC,
                        price.project_ticker ASC
                ) AS end_price
            )
            SELECT COUNT_BIG(*)
            FROM expected
            JOIN analytics
                .v_security_monthly_forward_return_1m
                AS holding
              ON holding.analysis_month_number
               = expected.analysis_month_number
             AND holding.security_key
               = expected.security_key
            WHERE ISNULL(
                    holding.target_holding_end_date,
                    CONVERT(date, '19000101', 112)
                  )
                  <> ISNULL(
                    expected.target_end_date,
                    CONVERT(date, '19000101', 112)
                  )
               OR ISNULL(
                    holding.realized_holding_end_date,
                    CONVERT(date, '19000101', 112)
                  )
                  <> ISNULL(
                    expected.realized_end_date,
                    CONVERT(date, '19000101', 112)
                  )
               OR ISNULL(
                    holding.holding_end_project_ticker,
                    ''
                  ) <> ISNULL(expected.end_ticker, '')
               OR ISNULL(
                    holding.holding_end_provider_symbol,
                    ''
                  ) <> ISNULL(expected.end_provider_symbol, '')
               OR ISNULL(
                    holding.holding_end_adjusted_close,
                    CAST(-1 AS decimal(38, 18))
                  ) <> ISNULL(
                    expected.end_adjusted_close,
                    CAST(-1 AS decimal(38, 18))
                  );
            """,
            0,
            (
                "Every realized holding boundary is the "
                "final validated price in its window."
            ),
            "Holding-boundary reconstruction mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE (
                    forward_return_1m_complete = 1
                AND ABS(
                    CAST(forward_return_1m AS float)
                    - (
                        CAST(
                            holding_end_adjusted_close
                            AS float
                        )
                        / CAST(
                            holding_start_adjusted_close
                            AS float
                        )
                        - 1.0
                    )
                ) > 0.000000000000001
                  )
               OR (
                    forward_return_1m_complete = 0
                AND forward_return_1m IS NOT NULL
                  );
            """,
            0,
            (
                "Every constituent forward return matches "
                "the adjusted-close formula."
            ),
            "Constituent forward-return formula mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_forward_return_1m
            WHERE (
                    holding_end_status = 'EXACT_MONTH_END'
                AND holding_end_is_exact_month_end <> 1
                  )
               OR (
                    holding_end_status = 'EARLY_EXIT'
                AND holding_end_is_early_exit <> 1
                  )
               OR (
                    holding_end_status = 'IMMEDIATE_EXIT'
                AND holding_end_is_immediate_exit <> 1
                  )
               OR (
                    holding_end_status = 'OUT_OF_SCOPE'
                AND out_of_scope_right_censored <> 1
                  )
               OR holding_end_status = 'UNAVAILABLE';
            """,
            0,
            (
                "Holding statuses and boundary flags are "
                "internally consistent."
            ),
            "Holding-status mismatches",
        )

        lines.append("")
        lines += section(
            "3. BENCHMARK FORWARD-RETURN CONTROLS"
        )

        benchmark_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_forward_return_1m;
            """,
            96,
            "Benchmark output contains exactly 96 rows.",
            "Benchmark holding rows",
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
                "Both benchmarks contain 47 complete "
                "forward returns."
            ),
            "Complete benchmark returns",
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
                "Only the two December 2025 benchmark "
                "rows are right-censored."
            ),
            "Right-censored benchmark rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1
              AND ABS(
                    CAST(forward_return_1m AS float)
                    - (
                        CAST(
                            holding_end_adjusted_close
                            AS float
                        )
                        / CAST(
                            holding_start_adjusted_close
                            AS float
                        )
                        - 1.0
                    )
                  ) > 0.000000000000001;
            """,
            0,
            (
                "Every benchmark forward return matches "
                "the adjusted-close formula."
            ),
            "Benchmark forward-return formula mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT analysis_month_number
                FROM analytics
                    .v_benchmark_monthly_forward_return_1m
                GROUP BY analysis_month_number
                HAVING COUNT_BIG(*) <> 2
                   OR COUNT(DISTINCT series_type) <> 2
            ) AS invalid;
            """,
            0,
            (
                "Every ranking month contains one ETF and "
                "one index benchmark."
            ),
            "Invalid monthly benchmark populations",
        )

        lines.append("")
        lines += section(
            "4. PORTFOLIO AGGREGATION CONTROLS"
        )

        decile_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_forward_return_1m;
            """,
            480,
            (
                "Decile output contains exactly 480 "
                "month/decile rows."
            ),
            "Decile return rows",
        )

        complete_deciles = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            470,
            (
                "All ten deciles are complete for 47 "
                "observable holding months."
            ),
            "Complete decile return rows",
        )

        expect(
            """
            WITH expected AS (
                SELECT
                    analysis_month_number,
                    momentum_decile,
                    COUNT_BIG(*) AS assigned_count,
                    SUM(
                        CAST(forward_return_1m_complete AS int)
                    ) AS complete_count,
                    SUM(
                        CAST(
                            holding_end_is_exact_month_end
                            AS int
                        )
                    ) AS exact_count,
                    SUM(
                        CAST(holding_end_is_early_exit AS int)
                    ) AS early_count,
                    SUM(
                        CAST(
                            holding_end_is_immediate_exit
                            AS int
                        )
                    ) AS immediate_count,
                    SUM(
                        CAST(
                            out_of_scope_right_censored
                            AS int
                        )
                    ) AS censored_count,
                    SUM(equal_weight) AS assigned_weight,
                    SUM(
                        CASE
                            WHEN forward_return_1m_complete = 1
                            THEN equal_weight
                            ELSE CAST(
                                0 AS decimal(38, 18)
                            )
                        END
                    ) AS complete_weight,
                    CAST(
                        CASE
                            WHEN SUM(
                                CAST(
                                    forward_return_1m_complete
                                    AS int
                                )
                            ) = COUNT_BIG(*)
                            THEN SUM(
                                CAST(equal_weight AS float)
                                * CAST(
                                    forward_return_1m AS float
                                )
                            )
                            ELSE NULL
                        END
                        AS decimal(38, 18)
                    ) AS expected_return
                FROM analytics
                    .v_security_monthly_forward_return_1m
                GROUP BY
                    analysis_month_number,
                    momentum_decile
            )
            SELECT COUNT_BIG(*)
            FROM expected
            JOIN analytics
                .v_momentum_decile_forward_return_1m
                AS actual
              ON actual.analysis_month_number
               = expected.analysis_month_number
             AND actual.momentum_decile
               = expected.momentum_decile
            WHERE actual.assigned_security_count
                    <> expected.assigned_count
               OR actual.complete_security_count
                    <> expected.complete_count
               OR actual.exact_month_end_count
                    <> expected.exact_count
               OR actual.early_exit_count
                    <> expected.early_count
               OR actual.immediate_exit_count
                    <> expected.immediate_count
               OR actual.right_censored_count
                    <> expected.censored_count
               OR actual.assigned_weight_sum
                    <> expected.assigned_weight
               OR actual.complete_weight_sum
                    <> expected.complete_weight
               OR ISNULL(
                    actual.equal_weight_forward_return_1m,
                    CAST(-999 AS decimal(38, 18))
                  ) <> ISNULL(
                    expected.expected_return,
                    CAST(-999 AS decimal(38, 18))
                  );
            """,
            0,
            (
                "Every decile return and boundary count "
                "matches an independent aggregation."
            ),
            "Decile aggregation mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_forward_return_1m
            WHERE ABS(
                    CAST(assigned_weight_sum AS float) - 1.0
                  ) > 0.000000000001
               OR (
                    forward_return_1m_complete = 1
                AND ABS(
                    CAST(complete_weight_sum AS float) - 1.0
                    ) > 0.000000000001
                  );
            """,
            0,
            (
                "Assigned and complete decile weights "
                "reconcile to one."
            ),
            "Invalid decile weight totals",
        )

        long_short_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_long_short_forward_return_1m;
            """,
            48,
            "Long-short output contains exactly 48 months.",
            "Long-short rows",
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
                "Winner-minus-loser returns are complete "
                "for 47 observable months."
            ),
            "Complete long-short rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_long_short_forward_return_1m
            WHERE forward_return_1m_complete = 1
              AND ABS(
                    CAST(
                        winner_minus_loser_forward_return_1m
                        AS float
                    )
                    - (
                        CAST(
                            winner_forward_return_1m AS float
                        )
                        - CAST(
                            loser_forward_return_1m AS float
                        )
                    )
                  ) > 0.000000000000001;
            """,
            0,
            (
                "Every winner-minus-loser return matches "
                "winner return minus loser return."
            ),
            "Winner-minus-loser formula mismatches",
        )

        performance_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_monthly_performance_1m;
            """,
            48,
            (
                "Combined performance output contains "
                "exactly 48 months."
            ),
            "Combined performance rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_monthly_performance_1m
            WHERE performance_1m_complete = 1;
            """,
            47,
            (
                "Momentum and benchmark comparisons are "
                "complete for 47 months."
            ),
            "Complete performance rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_monthly_performance_1m
            WHERE performance_1m_complete = 1
              AND (
                    ABS(
                        CAST(
                            winner_minus_spy_forward_return_1m
                            AS float
                        )
                        - (
                            CAST(
                                winner_forward_return_1m
                                AS float
                            )
                            - CAST(
                                spy_forward_return_1m AS float
                            )
                        )
                    ) > 0.000000000000001
                 OR ABS(
                        CAST(
                            loser_minus_spy_forward_return_1m
                            AS float
                        )
                        - (
                            CAST(
                                loser_forward_return_1m
                                AS float
                            )
                            - CAST(
                                spy_forward_return_1m AS float
                            )
                        )
                    ) > 0.000000000000001
              );
            """,
            0,
            (
                "Winner-minus-SPY and loser-minus-SPY "
                "returns match their formulas."
            ),
            "Benchmark-relative formula mismatches",
        )

        check(
            decile_rows - complete_deciles == 10,
            (
                "Only the ten December 2025 deciles are "
                "right-censored."
            ),
            "Decile right-censoring does not reconcile.",
        )

        check(
            long_short_rows - 47 == 1,
            "Only December 2025 is incomplete long-short.",
            "Long-short right-censoring does not reconcile.",
        )

        check(
            performance_rows - 47 == 1,
            "Only December 2025 is incomplete performance.",
            "Performance right-censoring does not reconcile.",
        )

        lines.append("")
        lines += section(
            "5. LOOK-AHEAD AND SOURCE-PRESERVATION CONTROLS"
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.columns
            WHERE object_id IN (
                    OBJECT_ID(
                        'analytics.v_security_monthly_'
                        + 'momentum_ranking'
                    ),
                    OBJECT_ID(
                        'analytics.v_security_monthly_'
                        + 'momentum_portfolio'
                    )
                  )
              AND (
                    name LIKE '%forward%'
                 OR name LIKE 'lead[_]%'
              );
            """,
            0,
            (
                "Signal and assignment views still contain "
                "no forward-looking columns."
            ),
            "Forward fields in signal or assignment views",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.sql_expression_dependencies AS d
            WHERE d.referencing_id IN (
                    OBJECT_ID(
                        'analytics.v_security_monthly_'
                        + 'momentum_ranking'
                    ),
                    OBJECT_ID(
                        'analytics.v_security_monthly_'
                        + 'momentum_portfolio'
                    )
                  )
              AND d.referenced_entity_name LIKE
                    '%forward_return%';
            """,
            0,
            (
                "Signal and assignment views do not depend "
                "on forward-return objects."
            ),
            "Look-ahead SQL dependencies",
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                (
                    f"core.{table} remains unchanged "
                    f"at {expected:,} rows."
                ),
                f"core.{table} final population",
            )

        lines.append("")
        lines += section("6. FINAL QUALITY GATE")

        if failures:
            lines += [
                "AZURE_SQL_FORWARD_RETURN_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]

            lines += [
                f"{number}. {failure}"
                for number, failure in enumerate(
                    failures,
                    start=1,
                )
            ]
        else:
            lines += [
                "AZURE_SQL_FORWARD_RETURN_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                f"Constituent holding rows: {security_rows:,}",
                f"Complete constituent returns: {complete_rows:,}",
                f"Exact-month-end holdings: {exact_rows:,}",
                f"Early-exit holdings: {early_rows:,}",
                f"Immediate-exit holdings: {immediate_rows:,}",
                f"Right-censored holdings: {censored_rows:,}",
                f"Benchmark holding rows: {benchmark_rows:,}",
                f"Complete decile return rows: {complete_deciles:,}",
                "Complete winner-minus-loser months: 47",
                "Complete benchmark-comparison months: 47",
                "Look-ahead dependencies: 0",
                "Core rows modified: 0",
                (
                    "Forward holding boundaries, returns, "
                    "deciles, and benchmarks are valid."
                ),
                (
                    "SQL FORWARD-RETURN QUALITY GATE "
                    "COMPLETE."
                ),
            ]

        cursor.close()

    except Exception as error:
        lines += [""] + section("AUDIT EXECUTION FAILED")
        lines += [
            type(error).__name__,
            str(error),
            "AZURE_SQL_FORWARD_RETURN_INTEGRITY_AUDIT_FAILED",
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