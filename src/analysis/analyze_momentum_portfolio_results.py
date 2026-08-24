from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

REPORT_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "momentum_portfolio_results.txt"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXPECTED_SERIES = {
    "D01",
    "D02",
    "D03",
    "D04",
    "D05",
    "D06",
    "D07",
    "D08",
    "D09",
    "D10",
    "WML",
    "SPY",
    "SP500",
}


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


def fetch_dicts(cursor, query: str) -> list[dict[str, Any]]:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


def scalar(cursor, query: str) -> Any:
    cursor.execute(query)
    return cursor.fetchone()[0]


def pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.{digits}f}%"


def num(value: Any, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}"


def money_index(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.4f}"


def date_text(value: Any) -> str:
    if value is None:
        return "N/A"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def rule() -> str:
    return "=" * 110


def section(title: str) -> list[str]:
    return ["", rule(), title, rule()]


def performance_row_line(row: dict[str, Any]) -> str:
    return (
        f"{row['series_code']:<6}"
        f"{row['series_name'][:28]:<30}"
        f"{money_index(row['final_wealth']):>10}"
        f"{pct(row['cumulative_return']):>12}"
        f"{pct(row['annualized_return']):>12}"
        f"{pct(row['annualized_volatility']):>12}"
        f"{pct(row['maximum_drawdown']):>12}"
        f"{pct(row['positive_month_frequency']):>12}"
        f"{pct(row['annualized_active_return_vs_spy']):>12}"
        f"{num(row['information_ratio_vs_spy']):>10}"
    )


def turnover_row_line(row: dict[str, Any]) -> str:
    return (
        f"{int(row['momentum_decile']):<8}"
        f"{str(row['momentum_portfolio']):<10}"
        f"{pct(row['average_monthly_target_weight_turnover']):>14}"
        f"{pct(row['annualized_target_weight_turnover']):>14}"
        f"{pct(row['average_security_overlap_rate']):>14}"
        f"{int(row['total_security_entries']):>12}"
        f"{int(row['total_security_exits']):>12}"
    )


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = None
    lines: list[str] = [
        rule(),
        "S&P 500 MOMENTUM — VALIDATED GROSS PORTFOLIO RESULTS",
        rule(),
        "Mode: READ-ONLY",
        "Source: validated Azure SQL portfolio-performance views",
        "Risk-free rate applied: NO",
        "Transaction costs applied: NO",
        "Sharpe ratio calculated: NO",
        "Regression alpha calculated: NO",
    ]

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

        print("Reading validated portfolio-performance results...")

        summary_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_performance_summary
            ORDER BY series_sort_order;
            """,
        )

        summary = {
            str(row["series_code"]): row
            for row in summary_rows
        }

        if set(summary) != EXPECTED_SERIES:
            raise RuntimeError(
                "Unexpected analytical-series population. "
                f"Found: {sorted(summary)}"
            )

        if any(int(row["observed_months"]) != 47 for row in summary_rows):
            raise RuntimeError(
                "At least one analytical series does not contain 47 observed months."
            )

        turnover_rows = fetch_dicts(
            cursor,
            """
            SELECT *
            FROM analytics.v_momentum_turnover_summary
            ORDER BY momentum_decile;
            """,
        )

        if len(turnover_rows) != 10:
            raise RuntimeError(
                f"Expected 10 turnover-summary rows; found {len(turnover_rows)}."
            )

        key_months = fetch_dicts(
            cursor,
            """
            WITH selected AS (
                SELECT
                    analysis_month_number,
                    ranking_month_end_date,
                    return_period_end_date,
                    series_code,
                    monthly_return,
                    ROW_NUMBER() OVER (
                        PARTITION BY series_code
                        ORDER BY monthly_return DESC, analysis_month_number
                    ) AS best_rank,
                    ROW_NUMBER() OVER (
                        PARTITION BY series_code
                        ORDER BY monthly_return ASC, analysis_month_number
                    ) AS worst_rank
                FROM analytics.v_momentum_monthly_return_panel
                WHERE series_code IN ('D01', 'D10', 'WML', 'SPY', 'SP500')
            )
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                return_period_end_date,
                series_code,
                monthly_return,
                CASE
                    WHEN best_rank = 1 THEN 'BEST'
                    WHEN worst_rank = 1 THEN 'WORST'
                END AS observation_type
            FROM selected
            WHERE best_rank = 1 OR worst_rank = 1
            ORDER BY series_code, observation_type;
            """,
        )

        max_drawdown_rows = fetch_dicts(
            cursor,
            """
            WITH ranked AS (
                SELECT
                    series_code,
                    analysis_month_number,
                    ranking_month_end_date,
                    return_period_end_date,
                    ending_wealth,
                    running_peak_wealth,
                    drawdown,
                    ROW_NUMBER() OVER (
                        PARTITION BY series_code
                        ORDER BY drawdown ASC, analysis_month_number
                    ) AS drawdown_rank
                FROM analytics.v_momentum_wealth_drawdown
                WHERE series_code IN ('D01', 'D10', 'WML', 'SPY', 'SP500')
            )
            SELECT
                series_code,
                analysis_month_number,
                ranking_month_end_date,
                return_period_end_date,
                ending_wealth,
                running_peak_wealth,
                drawdown
            FROM ranked
            WHERE drawdown_rank = 1
            ORDER BY
                CASE series_code
                    WHEN 'D01' THEN 1
                    WHEN 'D10' THEN 2
                    WHEN 'WML' THEN 3
                    WHEN 'SPY' THEN 4
                    WHEN 'SP500' THEN 5
                    ELSE 99
                END;
            """,
        )

        comparison = fetch_dicts(
            cursor,
            """
            WITH monthly AS (
                SELECT
                    analysis_month_number,
                    MAX(CASE WHEN series_code = 'D10' THEN monthly_return END) AS winner_return,
                    MAX(CASE WHEN series_code = 'D01' THEN monthly_return END) AS loser_return,
                    MAX(CASE WHEN series_code = 'WML' THEN monthly_return END) AS wml_return,
                    MAX(CASE WHEN series_code = 'SPY' THEN monthly_return END) AS spy_return,
                    MAX(CASE WHEN series_code = 'SP500' THEN monthly_return END) AS sp500_return
                FROM analytics.v_momentum_monthly_return_panel
                GROUP BY analysis_month_number
            )
            SELECT
                COUNT_BIG(*) AS observed_months,
                SUM(CASE WHEN winner_return > loser_return THEN 1 ELSE 0 END) AS winner_beats_loser_months,
                SUM(CASE WHEN winner_return > spy_return THEN 1 ELSE 0 END) AS winner_beats_spy_months,
                SUM(CASE WHEN loser_return > spy_return THEN 1 ELSE 0 END) AS loser_beats_spy_months,
                SUM(CASE WHEN wml_return > 0 THEN 1 ELSE 0 END) AS positive_wml_months,
                SUM(CASE WHEN spy_return > sp500_return THEN 1 ELSE 0 END) AS spy_beats_index_months
            FROM monthly;
            """,
        )[0]

        deciles = [
            summary[f"D{decile:02d}"]
            for decile in range(1, 11)
        ]
        annualized_returns = [
            float(row["annualized_return"])
            for row in deciles
        ]
        monotonic_increases = sum(
            current > previous
            for previous, current in zip(
                annualized_returns[:-1],
                annualized_returns[1:],
            )
        )

        winner = summary["D10"]
        loser = summary["D01"]
        wml = summary["WML"]
        spy = summary["SPY"]
        sp500 = summary["SP500"]

        best_series = max(
            summary_rows,
            key=lambda row: float(row["annualized_return"]),
        )
        worst_series = min(
            summary_rows,
            key=lambda row: float(row["annualized_return"]),
        )

        decile_best = max(
            deciles,
            key=lambda row: float(row["annualized_return"]),
        )
        decile_worst = min(
            deciles,
            key=lambda row: float(row["annualized_return"]),
        )

        turnover_by_decile = {
            int(row["momentum_decile"]): row
            for row in turnover_rows
        }
        winner_turnover = turnover_by_decile[10]
        loser_turnover = turnover_by_decile[1]
        highest_turnover = max(
            turnover_rows,
            key=lambda row: float(row["average_monthly_target_weight_turnover"]),
        )
        lowest_turnover = min(
            turnover_rows,
            key=lambda row: float(row["average_monthly_target_weight_turnover"]),
        )
        mean_decile_turnover = sum(
            float(row["average_monthly_target_weight_turnover"])
            for row in turnover_rows
        ) / 10.0

        lines += section("1. COMPLETE PERFORMANCE SUMMARY")
        lines += [
            (
                f"{'Code':<6}{'Series':<30}{'Wealth':>10}{'Cum Ret':>12}"
                f"{'Ann Ret':>12}{'Ann Vol':>12}{'Max DD':>12}"
                f"{'Pos Mths':>12}{'Act vs SPY':>12}{'Info Rat':>10}"
            ),
            "-" * 110,
        ]
        lines.extend(performance_row_line(row) for row in summary_rows)

        lines += section("2. MOMENTUM STRATEGY HEADLINES")
        lines += [
            f"Winner decile (D10) annualized return: {pct(winner['annualized_return'])}",
            f"Loser decile (D01) annualized return: {pct(loser['annualized_return'])}",
            (
                "Winner minus loser annualized-return difference "
                f"(D10 - D01): "
                f"{pct(float(winner['annualized_return']) - float(loser['annualized_return']))}"
            ),
            f"WML annualized return: {pct(wml['annualized_return'])}",
            f"WML cumulative return: {pct(wml['cumulative_return'])}",
            f"WML final wealth from $1: {money_index(wml['final_wealth'])}",
            f"SPY annualized return: {pct(spy['annualized_return'])}",
            f"S&P 500 index annualized return: {pct(sp500['annualized_return'])}",
            (
                "Winner decile annualized-return difference versus SPY: "
                f"{pct(float(winner['annualized_return']) - float(spy['annualized_return']))}"
            ),
            (
                "Winner decile annualized active return vs SPY "
                "(arithmetic convention): "
                f"{pct(winner['annualized_active_return_vs_spy'])}"
            ),
            (
                "Winner decile information ratio vs SPY: "
                f"{num(winner['information_ratio_vs_spy'])}"
            ),
            (
                "Winner decile maximum drawdown: "
                f"{pct(winner['maximum_drawdown'])}"
            ),
            (
                "Loser decile maximum drawdown: "
                f"{pct(loser['maximum_drawdown'])}"
            ),
            f"WML maximum drawdown: {pct(wml['maximum_drawdown'])}",
            f"SPY maximum drawdown: {pct(spy['maximum_drawdown'])}",
            (
                "Best annualized-return series overall: "
                f"{best_series['series_code']} ({best_series['series_name']}) "
                f"at {pct(best_series['annualized_return'])}"
            ),
            (
                "Worst annualized-return series overall: "
                f"{worst_series['series_code']} ({worst_series['series_name']}) "
                f"at {pct(worst_series['annualized_return'])}"
            ),
            (
                "Best momentum decile by annualized return: "
                f"{decile_best['series_code']} at {pct(decile_best['annualized_return'])}"
            ),
            (
                "Worst momentum decile by annualized return: "
                f"{decile_worst['series_code']} at {pct(decile_worst['annualized_return'])}"
            ),
            (
                "Adjacent decile annualized-return increases from D01 to D10: "
                f"{monotonic_increases} of 9"
            ),
        ]

        lines += section("3. MONTH-BY-MONTH COMPARISON COUNTS")
        lines += [
            f"Observable months: {int(comparison['observed_months'])}",
            (
                "Winner decile beat loser decile: "
                f"{int(comparison['winner_beats_loser_months'])} of "
                f"{int(comparison['observed_months'])} months"
            ),
            (
                "Winner decile beat SPY: "
                f"{int(comparison['winner_beats_spy_months'])} of "
                f"{int(comparison['observed_months'])} months"
            ),
            (
                "Loser decile beat SPY: "
                f"{int(comparison['loser_beats_spy_months'])} of "
                f"{int(comparison['observed_months'])} months"
            ),
            (
                "WML was positive: "
                f"{int(comparison['positive_wml_months'])} of "
                f"{int(comparison['observed_months'])} months"
            ),
            (
                "SPY beat the S&P 500 index: "
                f"{int(comparison['spy_beats_index_months'])} of "
                f"{int(comparison['observed_months'])} months"
            ),
        ]

        lines += section("4. BEST AND WORST MONTHS")
        for row in key_months:
            lines.append(
                f"{row['series_code']:<5} "
                f"{row['observation_type']:<5} | "
                f"ranking month-end {date_text(row['ranking_month_end_date'])} | "
                f"holding end {date_text(row['return_period_end_date'])} | "
                f"return {pct(row['monthly_return'])}"
            )

        lines += section("5. MAXIMUM-DRAWDOWN OBSERVATIONS")
        for row in max_drawdown_rows:
            lines.append(
                f"{row['series_code']:<5} | "
                f"ranking month-end {date_text(row['ranking_month_end_date'])} | "
                f"holding end {date_text(row['return_period_end_date'])} | "
                f"wealth {money_index(row['ending_wealth'])} | "
                f"running peak {money_index(row['running_peak_wealth'])} | "
                f"drawdown {pct(row['drawdown'])}"
            )

        lines += section("6. DECILE TURNOVER SUMMARY")
        lines += [
            (
                f"{'Decile':<8}{'Label':<10}{'Avg Monthly':>14}"
                f"{'Annualized':>14}{'Avg Overlap':>14}"
                f"{'Entries':>12}{'Exits':>12}"
            ),
            "-" * 84,
        ]
        lines.extend(turnover_row_line(row) for row in turnover_rows)

        lines += [
            "",
            (
                "Average monthly turnover across all ten deciles: "
                f"{pct(mean_decile_turnover)}"
            ),
            (
                "Winner decile average monthly turnover: "
                f"{pct(winner_turnover['average_monthly_target_weight_turnover'])}"
            ),
            (
                "Loser decile average monthly turnover: "
                f"{pct(loser_turnover['average_monthly_target_weight_turnover'])}"
            ),
            (
                "Highest-turnover decile: "
                f"D{int(highest_turnover['momentum_decile']):02d} at "
                f"{pct(highest_turnover['average_monthly_target_weight_turnover'])}"
            ),
            (
                "Lowest-turnover decile: "
                f"D{int(lowest_turnover['momentum_decile']):02d} at "
                f"{pct(lowest_turnover['average_monthly_target_weight_turnover'])}"
            ),
        ]

        lines += section("7. INTERPRETATION BOUNDARIES")
        lines += [
            "All figures are validated gross performance.",
            "No transaction costs have been deducted.",
            "No risk-free rate has been applied.",
            "No Sharpe ratio has been calculated.",
            "No regression alpha has been calculated.",
            "No statistical significance test is performed by this script.",
            (
                "The report describes the observed 47-month sample and should not "
                "be interpreted as evidence of future performance."
            ),
        ]

        lines += [
            "",
            "RESULT_EXTRACTION_COMPLETE",
            f"Report saved: {REPORT_PATH}",
        ]

        cursor.close()

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    report_text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(report_text)


if __name__ == "__main__":
    main()
