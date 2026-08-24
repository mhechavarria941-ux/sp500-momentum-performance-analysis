from __future__ import annotations

import math
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_portfolio_performance_integrity_audit.txt"
)

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}

SOURCE_VIEWS = {
    "v_security_monthly_momentum_portfolio",
    "v_momentum_decile_forward_return_1m",
    "v_momentum_long_short_forward_return_1m",
    "v_benchmark_monthly_forward_return_1m",
}

PERFORMANCE_VIEWS = {
    "v_momentum_monthly_return_panel",
    "v_momentum_cumulative_wealth",
    "v_momentum_wealth_drawdown",
    "v_momentum_performance_summary",
    "v_momentum_decile_turnover",
    "v_momentum_turnover_summary",
}

EXPECTED_COLUMNS = {
    "v_momentum_monthly_return_panel": [
        "analysis_month_number",
        "ranking_month_start_date",
        "ranking_month_end_date",
        "return_period_end_date",
        "series_code",
        "series_name",
        "series_type",
        "momentum_decile",
        "series_sort_order",
        "monthly_return",
        "return_complete",
    ],
    "v_momentum_cumulative_wealth": [
        "analysis_month_number",
        "ranking_month_start_date",
        "ranking_month_end_date",
        "return_period_end_date",
        "series_code",
        "series_name",
        "series_type",
        "momentum_decile",
        "series_sort_order",
        "return_sequence",
        "return_period_count",
        "monthly_return",
        "beginning_wealth",
        "ending_wealth",
    ],
    "v_momentum_wealth_drawdown": [
        "analysis_month_number",
        "ranking_month_start_date",
        "ranking_month_end_date",
        "return_period_end_date",
        "series_code",
        "series_name",
        "series_type",
        "momentum_decile",
        "series_sort_order",
        "return_sequence",
        "return_period_count",
        "monthly_return",
        "beginning_wealth",
        "ending_wealth",
        "running_peak_wealth",
        "drawdown",
    ],
    "v_momentum_performance_summary": [
        "series_code",
        "series_name",
        "series_type",
        "momentum_decile",
        "series_sort_order",
        "observed_months",
        "first_analysis_month_number",
        "last_analysis_month_number",
        "final_wealth",
        "cumulative_return",
        "arithmetic_mean_monthly_return",
        "geometric_mean_monthly_return",
        "annualized_return",
        "monthly_volatility",
        "annualized_volatility",
        "worst_monthly_return",
        "best_monthly_return",
        "positive_months",
        "positive_month_frequency",
        "maximum_drawdown",
        "mean_monthly_active_return_vs_spy",
        "annualized_active_return_vs_spy",
        "annualized_tracking_error_vs_spy",
        "information_ratio_vs_spy",
    ],
    "v_momentum_decile_turnover": [
        "analysis_month_number",
        "month_start_date",
        "month_end_date",
        "previous_analysis_month_number",
        "previous_month_end_date",
        "momentum_decile",
        "momentum_portfolio",
        "current_security_count",
        "previous_security_count",
        "retained_security_count",
        "entered_security_count",
        "exited_security_count",
        "security_overlap_rate",
        "target_weight_one_way_turnover",
    ],
    "v_momentum_turnover_summary": [
        "momentum_decile",
        "momentum_portfolio",
        "observed_rebalances",
        "average_monthly_target_weight_turnover",
        "annualized_target_weight_turnover",
        "minimum_monthly_target_weight_turnover",
        "maximum_monthly_target_weight_turnover",
        "average_security_overlap_rate",
        "total_security_entries",
        "total_security_exits",
    ],
}

EXPECTED_PANEL_ROWS = 611
EXPECTED_SERIES_COUNT = 13
EXPECTED_RETURN_MONTHS = 47
EXPECTED_TURNOVER_ROWS = 470
EXPECTED_TURNOVER_SUMMARY_ROWS = 10
EXPECTED_RANKING_ROWS = 23_401
EXPECTED_COMPLETE_DECILE_ROWS = 470
EXPECTED_COMPLETE_LONG_SHORT_ROWS = 47
EXPECTED_COMPLETE_BENCHMARK_ROWS = 94

RETURN_MONTHS = tuple(range(13, 60))
TURNOVER_MONTHS = tuple(range(14, 61))

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
TOLERANCE = 1e-10


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
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(
                "ODBC connection established on attempt "
                f"{attempt} / {maximum_attempts}."
            )
            return connection
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


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def fetch_dicts(cursor, query: str) -> list[dict[str, Any]]:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


def close_number(
    actual: Any,
    expected: Any,
    tolerance: float = TOLERANCE,
) -> bool:
    if actual is None or expected is None:
        return actual is None and expected is None

    actual_float = float(actual)
    expected_float = float(expected)

    return math.isclose(
        actual_float,
        expected_float,
        rel_tol=tolerance,
        abs_tol=tolerance,
    )


def row_value_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, float):
        return close_number(actual, expected)
    return actual == expected


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def series_metadata(
    series_code: str,
) -> tuple[str, str, int | None, int]:
    if series_code.startswith("D"):
        decile = int(series_code[1:])
        name = (
            "Loser Decile"
            if decile == 1
            else "Winner Decile"
            if decile == 10
            else f"Momentum Decile {decile}"
        )
        return name, "DECILE", decile, decile

    if series_code == "WML":
        return "Winner Minus Loser", "LONG_SHORT", None, 11

    if series_code == "SPY":
        return "SPDR S&P 500 ETF Trust", "BENCHMARK", None, 12

    if series_code == "SP500":
        return "S&P 500 Index", "BENCHMARK", None, 13

    raise ValueError(f"Unexpected series code: {series_code}")


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = section(
        "AZURE SQL PORTFOLIO-PERFORMANCE INTEGRITY AUDIT"
    )
    lines += [
        "Audit mode: READ-ONLY",
        "Credentials included in report: NO",
        (
            "Independent method: reconstruct portfolio panel, wealth, "
            "drawdown, summary statistics, and turnover in Python"
        ),
        (
            "Deferred by design: risk-free rates, Sharpe ratios, "
            "regression alpha, and transaction costs"
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
            f"{label}: found {actual:,}; expected {expected:,}.",
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

        print("Running portfolio-performance integrity audit...")

        lines += section("1. OBJECT, SCHEMA, AND SOURCE CONTROLS")
        print("Audit section 1 / 8: object and source controls")

        actual_views = {
            str(row["name"])
            for row in fetch_dicts(
                cursor,
                """
                SELECT v.name
                FROM sys.views AS v
                JOIN sys.schemas AS s
                  ON s.schema_id = v.schema_id
                WHERE s.name = 'analytics';
                """,
            )
        }

        required_views = SOURCE_VIEWS | PERFORMANCE_VIEWS
        missing_views = sorted(required_views - actual_views)
        check(
            not missing_views,
            "All required source and portfolio-performance views are present.",
            "Missing analytics views: " + ", ".join(missing_views),
        )

        schema_mismatches: list[str] = []
        for view_name, expected_columns in EXPECTED_COLUMNS.items():
            rows = fetch_dicts(
                cursor,
                f"""
                SELECT c.name
                FROM sys.columns AS c
                JOIN sys.views AS v
                  ON v.object_id = c.object_id
                JOIN sys.schemas AS s
                  ON s.schema_id = v.schema_id
                WHERE s.name = 'analytics'
                  AND v.name = '{view_name}'
                ORDER BY c.column_id;
                """,
            )
            actual_columns = [str(row["name"]) for row in rows]
            if actual_columns != expected_columns:
                schema_mismatches.append(
                    f"{view_name}: {actual_columns}"
                )

        check(
            not schema_mismatches,
            "All six portfolio-performance views match the expected schemas.",
            "Unexpected view schema(s): " + " | ".join(schema_mismatches),
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table}: {expected:,} rows.",
                f"core.{table} population",
            )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_momentum_portfolio;
            """,
            EXPECTED_RANKING_ROWS,
            "The ranking source still contains 23,401 fixed assignments.",
            "Ranking source rows",
        )
        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_decile_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_DECILE_ROWS,
            "The decile source still contains 470 complete returns.",
            "Complete decile source rows",
        )
        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_long_short_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_LONG_SHORT_ROWS,
            "The long-short source still contains 47 complete returns.",
            "Complete long-short source rows",
        )
        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1;
            """,
            EXPECTED_COMPLETE_BENCHMARK_ROWS,
            "The benchmark source still contains 94 complete returns.",
            "Complete benchmark source rows",
        )

        lines.append("")
        lines += section("2. INDEPENDENT MONTHLY RETURN-PANEL RECONSTRUCTION")
        print("Audit section 2 / 8: reconstructing monthly return panel")

        decile_source = fetch_dicts(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_start_date,
                ranking_month_end_date,
                target_holding_end_date,
                momentum_decile,
                equal_weight_forward_return_1m,
                forward_return_1m_complete
            FROM analytics.v_momentum_decile_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number, momentum_decile;
            """,
        )
        long_short_source = fetch_dicts(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_start_date,
                ranking_month_end_date,
                target_holding_end_date,
                winner_minus_loser_forward_return_1m,
                forward_return_1m_complete
            FROM analytics.v_momentum_long_short_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number;
            """,
        )
        benchmark_source = fetch_dicts(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_start_date,
                ranking_month_end_date,
                target_holding_end_date,
                series_type,
                forward_return_1m,
                forward_return_1m_complete
            FROM analytics.v_benchmark_monthly_forward_return_1m
            WHERE forward_return_1m_complete = 1
            ORDER BY analysis_month_number, series_type;
            """,
        )

        expected_panel: dict[tuple[int, str], dict[str, Any]] = {}

        for row in decile_source:
            decile = int(row["momentum_decile"])
            code = f"D{decile:02d}"
            name, series_type, momentum_decile, sort_order = series_metadata(code)
            expected_panel[(int(row["analysis_month_number"]), code)] = {
                "analysis_month_number": int(row["analysis_month_number"]),
                "ranking_month_start_date": row["ranking_month_start_date"],
                "ranking_month_end_date": row["ranking_month_end_date"],
                "return_period_end_date": row["target_holding_end_date"],
                "series_code": code,
                "series_name": name,
                "series_type": series_type,
                "momentum_decile": momentum_decile,
                "series_sort_order": sort_order,
                "monthly_return": float(row["equal_weight_forward_return_1m"]),
                "return_complete": 1,
            }

        for row in long_short_source:
            code = "WML"
            name, series_type, momentum_decile, sort_order = series_metadata(code)
            expected_panel[(int(row["analysis_month_number"]), code)] = {
                "analysis_month_number": int(row["analysis_month_number"]),
                "ranking_month_start_date": row["ranking_month_start_date"],
                "ranking_month_end_date": row["ranking_month_end_date"],
                "return_period_end_date": row["target_holding_end_date"],
                "series_code": code,
                "series_name": name,
                "series_type": series_type,
                "momentum_decile": momentum_decile,
                "series_sort_order": sort_order,
                "monthly_return": float(
                    row["winner_minus_loser_forward_return_1m"]
                ),
                "return_complete": 1,
            }

        benchmark_types = {str(row["series_type"]) for row in benchmark_source}
        check(
            benchmark_types == {"ETF", "INDEX"},
            "Benchmark source contains exactly one ETF and one index type.",
            f"Unexpected benchmark source types: {sorted(benchmark_types)}",
        )

        for row in benchmark_source:
            code = "SPY" if row["series_type"] == "ETF" else "SP500"
            name, series_type, momentum_decile, sort_order = series_metadata(code)
            expected_panel[(int(row["analysis_month_number"]), code)] = {
                "analysis_month_number": int(row["analysis_month_number"]),
                "ranking_month_start_date": row["ranking_month_start_date"],
                "ranking_month_end_date": row["ranking_month_end_date"],
                "return_period_end_date": row["target_holding_end_date"],
                "series_code": code,
                "series_name": name,
                "series_type": series_type,
                "momentum_decile": momentum_decile,
                "series_sort_order": sort_order,
                "monthly_return": float(row["forward_return_1m"]),
                "return_complete": 1,
            }

        actual_panel_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_monthly_return_panel
            ORDER BY analysis_month_number, series_sort_order;
            """,
        )
        actual_panel = {
            (int(row["analysis_month_number"]), str(row["series_code"])): row
            for row in actual_panel_rows
        }

        check(
            len(expected_panel) == EXPECTED_PANEL_ROWS,
            "Independent source reconstruction produced 611 panel rows.",
            (
                "Independent panel reconstruction produced "
                f"{len(expected_panel):,} rows; expected 611."
            ),
        )
        check(
            len(actual_panel_rows) == EXPECTED_PANEL_ROWS,
            "SQL monthly return panel contains 611 rows.",
            f"SQL return panel contains {len(actual_panel_rows):,} rows.",
        )
        check(
            set(actual_panel) == set(expected_panel),
            "Every SQL month/series key matches the independent source reconstruction.",
            "SQL and independent return-panel keys differ.",
        )

        panel_mismatches = 0
        fields_to_compare = EXPECTED_COLUMNS["v_momentum_monthly_return_panel"]
        for key, expected_row in expected_panel.items():
            actual_row = actual_panel.get(key)
            if actual_row is None:
                panel_mismatches += 1
                continue
            for field in fields_to_compare:
                expected_value = expected_row[field]
                actual_value = actual_row[field]
                if field == "monthly_return":
                    equal = close_number(actual_value, expected_value)
                else:
                    equal = row_value_equal(actual_value, expected_value)
                if not equal:
                    panel_mismatches += 1
                    break

        check(
            panel_mismatches == 0,
            "Every return-panel row exactly reconciles to its independent source mapping.",
            f"Return-panel row mismatches: {panel_mismatches:,}.",
        )

        actual_return_months = tuple(sorted({key[0] for key in actual_panel}))
        actual_series = {key[1] for key in actual_panel}
        check(
            actual_return_months == RETURN_MONTHS,
            "Gross-performance months are exactly analysis months 13 through 59.",
            f"Unexpected gross-performance months: {actual_return_months}",
        )
        check(
            len(actual_series) == EXPECTED_SERIES_COUNT,
            "The return panel contains exactly 13 analytical series.",
            f"Return-panel series count: {len(actual_series)}.",
        )
        check(
            all(float(row["monthly_return"]) > -1.0 for row in actual_panel_rows),
            "Every monthly return is greater than -100%, preserving the wealth domain.",
            "At least one monthly return is less than or equal to -100%.",
        )

        lines.append("")
        lines += section("3. INDEPENDENT WEALTH AND DRAWDOWN RECONSTRUCTION")
        print("Audit section 3 / 8: reconstructing wealth and drawdown")

        expected_wealth: dict[tuple[int, str], dict[str, Any]] = {}
        expected_drawdown: dict[tuple[int, str], dict[str, Any]] = {}

        rows_by_series: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in expected_panel.values():
            rows_by_series[str(row["series_code"])].append(row)

        for series_code, rows in rows_by_series.items():
            rows.sort(key=lambda row: int(row["analysis_month_number"]))
            wealth = 1.0
            running_peak = 1.0
            count = len(rows)

            for sequence, row in enumerate(rows, start=1):
                beginning = wealth
                ending = beginning * (1.0 + float(row["monthly_return"]))
                running_peak = max(running_peak, ending, 1.0)
                drawdown = ending / running_peak - 1.0
                key = (int(row["analysis_month_number"]), series_code)

                expected_wealth[key] = {
                    **row,
                    "return_sequence": sequence,
                    "return_period_count": count,
                    "beginning_wealth": beginning,
                    "ending_wealth": ending,
                }
                expected_drawdown[key] = {
                    **expected_wealth[key],
                    "running_peak_wealth": running_peak,
                    "drawdown": drawdown,
                }
                wealth = ending

        actual_wealth_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_cumulative_wealth
            ORDER BY series_code, analysis_month_number;
            """,
        )
        actual_wealth = {
            (int(row["analysis_month_number"]), str(row["series_code"])): row
            for row in actual_wealth_rows
        }

        check(
            len(actual_wealth_rows) == EXPECTED_PANEL_ROWS,
            "Cumulative wealth preserves all 611 panel observations.",
            f"Cumulative-wealth rows: {len(actual_wealth_rows):,}.",
        )
        check(
            set(actual_wealth) == set(expected_wealth),
            "Cumulative-wealth keys match the independent reconstruction.",
            "Cumulative-wealth keys differ from independent reconstruction.",
        )

        wealth_mismatches = 0
        for key, expected_row in expected_wealth.items():
            actual_row = actual_wealth.get(key)
            if actual_row is None:
                wealth_mismatches += 1
                continue
            exact_fields = (
                "return_sequence",
                "return_period_count",
                "series_code",
                "analysis_month_number",
            )
            numeric_fields = (
                "monthly_return",
                "beginning_wealth",
                "ending_wealth",
            )
            if any(
                actual_row[field] != expected_row[field]
                for field in exact_fields
            ) or any(
                not close_number(actual_row[field], expected_row[field])
                for field in numeric_fields
            ):
                wealth_mismatches += 1

        check(
            wealth_mismatches == 0,
            "All SQL wealth chains match direct Python compounding.",
            f"Independent wealth mismatches: {wealth_mismatches:,}.",
        )

        actual_drawdown_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_wealth_drawdown
            ORDER BY series_code, analysis_month_number;
            """,
        )
        actual_drawdown = {
            (int(row["analysis_month_number"]), str(row["series_code"])): row
            for row in actual_drawdown_rows
        }

        check(
            len(actual_drawdown_rows) == EXPECTED_PANEL_ROWS,
            "Drawdown history preserves all 611 wealth observations.",
            f"Drawdown rows: {len(actual_drawdown_rows):,}.",
        )

        drawdown_mismatches = 0
        for key, expected_row in expected_drawdown.items():
            actual_row = actual_drawdown.get(key)
            if actual_row is None:
                drawdown_mismatches += 1
                continue
            for field in (
                "beginning_wealth",
                "ending_wealth",
                "running_peak_wealth",
                "drawdown",
            ):
                if not close_number(actual_row[field], expected_row[field]):
                    drawdown_mismatches += 1
                    break

        check(
            drawdown_mismatches == 0,
            "All SQL running peaks and drawdowns match the Python reconstruction.",
            f"Independent drawdown mismatches: {drawdown_mismatches:,}.",
        )

        lines.append("")
        lines += section("4. INDEPENDENT PERFORMANCE-SUMMARY RECONSTRUCTION")
        print("Audit section 4 / 8: reconstructing performance summary")

        spy_returns = {
            int(row["analysis_month_number"]): float(row["monthly_return"])
            for row in expected_panel.values()
            if row["series_code"] == "SPY"
        }

        expected_summary: dict[str, dict[str, Any]] = {}
        for series_code, rows in rows_by_series.items():
            rows.sort(key=lambda row: int(row["analysis_month_number"]))
            returns = [float(row["monthly_return"]) for row in rows]
            active_returns = [
                float(row["monthly_return"])
                - spy_returns[int(row["analysis_month_number"])]
                for row in rows
            ]
            n = len(returns)
            final_key = (int(rows[-1]["analysis_month_number"]), series_code)
            final_wealth = float(expected_wealth[final_key]["ending_wealth"])
            monthly_volatility = statistics.stdev(returns)
            tracking_error = statistics.stdev(active_returns)
            arithmetic_mean = mean(returns)
            mean_active = mean(active_returns)
            positive_months = sum(value > 0 for value in returns)
            maximum_drawdown = min(
                float(expected_drawdown[
                    (int(row["analysis_month_number"]), series_code)
                ]["drawdown"])
                for row in rows
            )
            information_ratio = (
                None
                if math.isclose(tracking_error, 0.0, abs_tol=TOLERANCE)
                else mean_active / tracking_error * math.sqrt(12.0)
            )
            name, series_type, momentum_decile, sort_order = series_metadata(
                series_code
            )

            expected_summary[series_code] = {
                "series_code": series_code,
                "series_name": name,
                "series_type": series_type,
                "momentum_decile": momentum_decile,
                "series_sort_order": sort_order,
                "observed_months": n,
                "first_analysis_month_number": int(rows[0]["analysis_month_number"]),
                "last_analysis_month_number": int(rows[-1]["analysis_month_number"]),
                "final_wealth": final_wealth,
                "cumulative_return": final_wealth - 1.0,
                "arithmetic_mean_monthly_return": arithmetic_mean,
                "geometric_mean_monthly_return": final_wealth ** (1.0 / n) - 1.0,
                "annualized_return": final_wealth ** (12.0 / n) - 1.0,
                "monthly_volatility": monthly_volatility,
                "annualized_volatility": monthly_volatility * math.sqrt(12.0),
                "worst_monthly_return": min(returns),
                "best_monthly_return": max(returns),
                "positive_months": positive_months,
                "positive_month_frequency": positive_months / n,
                "maximum_drawdown": maximum_drawdown,
                "mean_monthly_active_return_vs_spy": mean_active,
                "annualized_active_return_vs_spy": mean_active * 12.0,
                "annualized_tracking_error_vs_spy": tracking_error * math.sqrt(12.0),
                "information_ratio_vs_spy": information_ratio,
            }

        actual_summary_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_performance_summary
            ORDER BY series_sort_order;
            """,
        )
        actual_summary = {
            str(row["series_code"]): row
            for row in actual_summary_rows
        }

        check(
            len(actual_summary_rows) == EXPECTED_SERIES_COUNT,
            "Performance summary contains exactly 13 series rows.",
            f"Performance-summary rows: {len(actual_summary_rows)}.",
        )
        check(
            set(actual_summary) == set(expected_summary),
            "Performance-summary series exactly match the independent reconstruction.",
            "Performance-summary series differ from independent reconstruction.",
        )

        summary_mismatches = 0
        numeric_summary_fields = (
            "final_wealth",
            "cumulative_return",
            "arithmetic_mean_monthly_return",
            "geometric_mean_monthly_return",
            "annualized_return",
            "monthly_volatility",
            "annualized_volatility",
            "worst_monthly_return",
            "best_monthly_return",
            "positive_month_frequency",
            "maximum_drawdown",
            "mean_monthly_active_return_vs_spy",
            "annualized_active_return_vs_spy",
            "annualized_tracking_error_vs_spy",
            "information_ratio_vs_spy",
        )
        exact_summary_fields = (
            "series_code",
            "series_name",
            "series_type",
            "momentum_decile",
            "series_sort_order",
            "observed_months",
            "first_analysis_month_number",
            "last_analysis_month_number",
            "positive_months",
        )

        for series_code, expected_row in expected_summary.items():
            actual_row = actual_summary.get(series_code)
            if actual_row is None:
                summary_mismatches += 1
                continue
            exact_ok = all(
                actual_row[field] == expected_row[field]
                for field in exact_summary_fields
            )
            numeric_ok = all(
                close_number(actual_row[field], expected_row[field])
                for field in numeric_summary_fields
            )
            if not exact_ok or not numeric_ok:
                summary_mismatches += 1

        check(
            summary_mismatches == 0,
            (
                "All SQL performance statistics match independent Python "
                "recalculation from monthly returns."
            ),
            f"Independent performance-summary mismatches: {summary_mismatches}.",
        )
        check(
            actual_summary["SPY"]["information_ratio_vs_spy"] is None
            and close_number(
                actual_summary["SPY"]["mean_monthly_active_return_vs_spy"],
                0.0,
            )
            and close_number(
                actual_summary["SPY"]["annualized_tracking_error_vs_spy"],
                0.0,
            ),
            "SPY correctly has zero active return/tracking error versus itself.",
            "SPY self-relative statistics are not zero/null as required.",
        )

        lines.append("")
        lines += section("5. INDEPENDENT TARGET-WEIGHT TURNOVER RECONSTRUCTION")
        print("Audit section 5 / 8: reconstructing decile turnover")

        portfolio_rows = fetch_dicts(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_start_date,
                month_end_date,
                momentum_decile,
                security_key,
                equal_weight
            FROM analytics.v_security_monthly_momentum_portfolio
            ORDER BY analysis_month_number, momentum_decile, security_key;
            """,
        )

        month_dates: dict[int, tuple[Any, Any]] = {}
        weights: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)

        for row in portfolio_rows:
            month_number = int(row["analysis_month_number"])
            decile = int(row["momentum_decile"])
            month_dates[month_number] = (
                row["month_start_date"],
                row["month_end_date"],
            )
            weights[(month_number, decile)][str(row["security_key"])] = float(
                row["equal_weight"]
            )

        ranking_months = tuple(sorted(month_dates))
        check(
            ranking_months == tuple(range(13, 61)),
            "Ranking assignments span exactly analysis months 13 through 60.",
            f"Unexpected ranking months: {ranking_months}",
        )

        expected_turnover: dict[tuple[int, int], dict[str, Any]] = {}
        for month_number in TURNOVER_MONTHS:
            previous_month = month_number - 1
            for decile in range(1, 11):
                current = weights[(month_number, decile)]
                previous = weights[(previous_month, decile)]
                securities = set(current) | set(previous)
                retained = set(current) & set(previous)
                entered = set(current) - set(previous)
                exited = set(previous) - set(current)
                overlap = len(retained) / len(previous)
                one_way_turnover = 0.5 * sum(
                    abs(current.get(security, 0.0) - previous.get(security, 0.0))
                    for security in securities
                )
                portfolio_label = (
                    "LOSER"
                    if decile == 1
                    else "WINNER"
                    if decile == 10
                    else "MIDDLE"
                )
                expected_turnover[(month_number, decile)] = {
                    "analysis_month_number": month_number,
                    "month_start_date": month_dates[month_number][0],
                    "month_end_date": month_dates[month_number][1],
                    "previous_analysis_month_number": previous_month,
                    "previous_month_end_date": month_dates[previous_month][1],
                    "momentum_decile": decile,
                    "momentum_portfolio": portfolio_label,
                    "current_security_count": len(current),
                    "previous_security_count": len(previous),
                    "retained_security_count": len(retained),
                    "entered_security_count": len(entered),
                    "exited_security_count": len(exited),
                    "security_overlap_rate": overlap,
                    "target_weight_one_way_turnover": one_way_turnover,
                }

        actual_turnover_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_decile_turnover
            ORDER BY analysis_month_number, momentum_decile;
            """,
        )
        actual_turnover = {
            (int(row["analysis_month_number"]), int(row["momentum_decile"])): row
            for row in actual_turnover_rows
        }

        check(
            len(expected_turnover) == EXPECTED_TURNOVER_ROWS,
            "Independent turnover reconstruction produced 470 rebalances.",
            f"Independent turnover rows: {len(expected_turnover):,}.",
        )
        check(
            len(actual_turnover_rows) == EXPECTED_TURNOVER_ROWS,
            "SQL turnover layer contains 470 month/decile rebalances.",
            f"SQL turnover rows: {len(actual_turnover_rows):,}.",
        )
        check(
            set(actual_turnover) == set(expected_turnover),
            "Every SQL turnover key matches the independent reconstruction.",
            "SQL and independent turnover keys differ.",
        )

        turnover_mismatches = 0
        exact_turnover_fields = (
            "analysis_month_number",
            "month_start_date",
            "month_end_date",
            "previous_analysis_month_number",
            "previous_month_end_date",
            "momentum_decile",
            "momentum_portfolio",
            "current_security_count",
            "previous_security_count",
            "retained_security_count",
            "entered_security_count",
            "exited_security_count",
        )
        numeric_turnover_fields = (
            "security_overlap_rate",
            "target_weight_one_way_turnover",
        )

        for key, expected_row in expected_turnover.items():
            actual_row = actual_turnover.get(key)
            if actual_row is None:
                turnover_mismatches += 1
                continue
            exact_ok = all(
                actual_row[field] == expected_row[field]
                for field in exact_turnover_fields
            )
            numeric_ok = all(
                close_number(actual_row[field], expected_row[field])
                for field in numeric_turnover_fields
            )
            if not exact_ok or not numeric_ok:
                turnover_mismatches += 1

        check(
            turnover_mismatches == 0,
            (
                "All SQL security counts, overlap rates, and target-weight "
                "turnover values match independent Python reconstruction."
            ),
            f"Independent turnover mismatches: {turnover_mismatches:,}.",
        )
        check(
            tuple(sorted({key[0] for key in actual_turnover})) == TURNOVER_MONTHS,
            "Turnover covers exactly 47 consecutive rebalances, months 14 through 60.",
            "Turnover rebalance months are not exactly 14 through 60.",
        )

        lines.append("")
        lines += section("6. INDEPENDENT TURNOVER-SUMMARY RECONSTRUCTION")
        print("Audit section 6 / 8: reconstructing turnover summary")

        expected_turnover_summary: dict[int, dict[str, Any]] = {}
        for decile in range(1, 11):
            rows = [
                row
                for (month_number, row_decile), row in expected_turnover.items()
                if row_decile == decile
            ]
            turnover_values = [
                float(row["target_weight_one_way_turnover"])
                for row in rows
            ]
            overlap_values = [
                float(row["security_overlap_rate"])
                for row in rows
            ]
            label = (
                "LOSER"
                if decile == 1
                else "WINNER"
                if decile == 10
                else "MIDDLE"
            )
            expected_turnover_summary[decile] = {
                "momentum_decile": decile,
                "momentum_portfolio": label,
                "observed_rebalances": len(rows),
                "average_monthly_target_weight_turnover": mean(turnover_values),
                "annualized_target_weight_turnover": mean(turnover_values) * 12.0,
                "minimum_monthly_target_weight_turnover": min(turnover_values),
                "maximum_monthly_target_weight_turnover": max(turnover_values),
                "average_security_overlap_rate": mean(overlap_values),
                "total_security_entries": sum(
                    int(row["entered_security_count"]) for row in rows
                ),
                "total_security_exits": sum(
                    int(row["exited_security_count"]) for row in rows
                ),
            }

        actual_turnover_summary_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_turnover_summary
            ORDER BY momentum_decile;
            """,
        )
        actual_turnover_summary = {
            int(row["momentum_decile"]): row
            for row in actual_turnover_summary_rows
        }

        check(
            len(actual_turnover_summary_rows) == EXPECTED_TURNOVER_SUMMARY_ROWS,
            "Turnover summary contains exactly one row for each decile.",
            f"Turnover-summary rows: {len(actual_turnover_summary_rows)}.",
        )

        turnover_summary_mismatches = 0
        exact_turnover_summary_fields = (
            "momentum_decile",
            "momentum_portfolio",
            "observed_rebalances",
            "total_security_entries",
            "total_security_exits",
        )
        numeric_turnover_summary_fields = (
            "average_monthly_target_weight_turnover",
            "annualized_target_weight_turnover",
            "minimum_monthly_target_weight_turnover",
            "maximum_monthly_target_weight_turnover",
            "average_security_overlap_rate",
        )

        for decile, expected_row in expected_turnover_summary.items():
            actual_row = actual_turnover_summary.get(decile)
            if actual_row is None:
                turnover_summary_mismatches += 1
                continue
            exact_ok = all(
                actual_row[field] == expected_row[field]
                for field in exact_turnover_summary_fields
            )
            numeric_ok = all(
                close_number(actual_row[field], expected_row[field])
                for field in numeric_turnover_summary_fields
            )
            if not exact_ok or not numeric_ok:
                turnover_summary_mismatches += 1

        check(
            turnover_summary_mismatches == 0,
            "All ten turnover-summary rows match independent Python aggregation.",
            (
                "Independent turnover-summary mismatches: "
                f"{turnover_summary_mismatches}."
            ),
        )

        lines.append("")
        lines += section("7. METHODOLOGY, DEPENDENCY, AND LOOK-AHEAD CONTROLS")
        print("Audit section 7 / 8: methodology and dependency controls")

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
            "No deferred risk-free, Sharpe, alpha, or transaction-cost fields are present.",
            "Deferred methodology columns",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_monthly_return_panel
            WHERE analysis_month_number = 60;
            """,
            0,
            "Right-censored December 2025 returns are excluded from gross performance.",
            "Right-censored performance rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_decile_turnover
            WHERE analysis_month_number = 60;
            """,
            10,
            (
                "December 2025 remains in turnover as ten valid target-weight "
                "rebalances even though its forward return is censored."
            ),
            "December 2025 turnover rows",
        )

        dependency_rows = fetch_dicts(
            cursor,
            """
            SELECT
                OBJECT_NAME(d.referencing_id) AS referencing_object,
                OBJECT_NAME(d.referenced_id) AS referenced_object
            FROM sys.sql_expression_dependencies AS d
            JOIN sys.views AS v
              ON v.object_id = d.referencing_id
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name IN (
                    'v_security_monthly_momentum_portfolio',
                    'v_momentum_decile_forward_return_1m',
                    'v_momentum_long_short_forward_return_1m',
                    'v_benchmark_monthly_forward_return_1m'
              );
            """,
        )
        backward_dependencies = [
            row
            for row in dependency_rows
            if row["referenced_object"] in PERFORMANCE_VIEWS
        ]
        check(
            not backward_dependencies,
            (
                "Ranking and forward-return source views do not depend on the "
                "new portfolio-performance layer."
            ),
            "Backward dependency from source layer into performance views detected.",
        )

        view_definitions = fetch_dicts(
            cursor,
            """
            SELECT
                v.name,
                m.definition
            FROM sys.views AS v
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            JOIN sys.sql_modules AS m
              ON m.object_id = v.object_id
            WHERE s.name = 'analytics'
              AND v.name IN (
                    'v_momentum_monthly_return_panel',
                    'v_momentum_cumulative_wealth',
                    'v_momentum_wealth_drawdown',
                    'v_momentum_performance_summary',
                    'v_momentum_decile_turnover',
                    'v_momentum_turnover_summary'
              );
            """,
        )
        forbidden_terms = (
            "risk_free",
            "sharpe",
            "regression_alpha",
            "transaction_cost",
            "net_of_cost",
        )
        forbidden_definition_hits = [
            str(row["name"])
            for row in view_definitions
            if any(
                term in str(row["definition"]).lower()
                for term in forbidden_terms
            )
        ]
        check(
            not forbidden_definition_hits,
            "SQL definitions contain no deferred risk/cost methodology.",
            (
                "Deferred methodology terms found in SQL definitions: "
                + ", ".join(forbidden_definition_hits)
            ),
        )

        lines.append("")
        lines += section("8. FINAL CORE PRESERVATION AND QUALITY GATE")
        print("Audit section 8 / 8: final core preservation")

        for table, expected in CORE_COUNTS.items():
            expect(
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table} remains unchanged at {expected:,} rows.",
                f"core.{table} final population",
            )

        if failures:
            lines += [
                "",
                "AZURE_SQL_PORTFOLIO_PERFORMANCE_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
            lines += [
                f"{number}. {failure}"
                for number, failure in enumerate(failures, start=1)
            ]
        else:
            lines += [
                "",
                "AZURE_SQL_PORTFOLIO_PERFORMANCE_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                "Monthly return-panel rows: 611",
                "Analytical series: 13",
                "Observable gross-performance months: 47",
                "Cumulative-wealth rows: 611",
                "Drawdown rows: 611",
                "Performance-summary rows: 13",
                "Decile-turnover rows: 470",
                "Turnover-summary rows: 10",
                "Independent Python return-panel mismatches: 0",
                "Independent Python wealth mismatches: 0",
                "Independent Python drawdown mismatches: 0",
                "Independent Python performance-summary mismatches: 0",
                "Independent Python turnover mismatches: 0",
                "Independent Python turnover-summary mismatches: 0",
                "Gross performance convention: YES",
                "Risk-free-rate dependency: NO",
                "Sharpe ratio calculated: NO",
                "Regression alpha calculated: NO",
                "Transaction costs applied: NO",
                "Core rows modified: 0",
                "SQL PORTFOLIO-PERFORMANCE QUALITY GATE COMPLETE",
            ]

        cursor.close()

    except Exception as error:
        lines += [""] + section("AUDIT EXECUTION FAILED")
        lines += [
            type(error).__name__,
            str(error),
            "AZURE_SQL_PORTFOLIO_PERFORMANCE_INTEGRITY_AUDIT_FAILED",
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
