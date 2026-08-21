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
    / "azure_sql_momentum_ranking_integrity_audit.txt"
)

REQUIRED_VIEWS = {
    "v_momentum_decile_monthly_summary",
    "v_security_monthly_momentum_portfolio",
    "v_security_monthly_momentum_ranking",
    "v_security_monthly_return_features",
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
                autocommit=True,
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
        "AZURE SQL MOMENTUM-RANKING INTEGRITY AUDIT"
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
        connection.timeout = 300
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
        missing_views = sorted(REQUIRED_VIEWS - actual_views)

        check(
            not missing_views,
            (
                "The monthly feature, ranking, portfolio, "
                "and summary views are present."
            ),
            "Missing views: " + ", ".join(missing_views),
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table}: {expected:,} rows.",
                f"core.{table} population",
            )

        source_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND momentum_12_1 IS NOT NULL;
            """,
            23_401,
            (
                "The validated source contains exactly "
                "23,401 complete momentum signals."
            ),
            "Complete source momentum rows",
        )

        lines.append("")
        lines += section(
            "2. RANKING POPULATION AND SOURCE RECONCILIATION"
        )

        ranking_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_ranking;
            """,
            source_rows,
            (
                "Ranking output contains exactly "
                "23,401 eligible observations."
            ),
            "Ranking rows",
        )

        ranking_months = expect(
            """
            SELECT COUNT_BIG(DISTINCT month_end_date)
            FROM analytics
                .v_security_monthly_momentum_ranking;
            """,
            48,
            "Ranking output contains exactly 48 months.",
            "Ranking months",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    MIN(month_end_date) AS first_month,
                    MAX(month_end_date) AS last_month
                FROM analytics
                    .v_security_monthly_momentum_ranking
            ) AS boundaries
            WHERE first_month <> '2022-01-31'
               OR last_month <> '2025-12-31';
            """,
            0,
            (
                "Ranking dates span 2022-01-31 "
                "through 2025-12-31."
            ),
            "Invalid ranking-date boundaries",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    MIN(eligible_security_count)
                        AS minimum_population,
                    MAX(eligible_security_count)
                        AS maximum_population
                FROM analytics
                    .v_security_monthly_momentum_ranking
            ) AS populations
            WHERE minimum_population <> 485
               OR maximum_population <> 491;
            """,
            0,
            (
                "Monthly eligible populations have the "
                "validated range of 485-491."
            ),
            "Invalid eligible-population range",
        )

        expect(
            """
            WITH source_population AS (
                SELECT
                    analysis_month_number,
                    COUNT_BIG(*) AS source_count
                FROM analytics
                    .v_security_monthly_return_features
                WHERE momentum_12_1_complete = 1
                  AND momentum_12_1 IS NOT NULL
                GROUP BY analysis_month_number
            ),
            ranking_population AS (
                SELECT
                    analysis_month_number,
                    COUNT_BIG(*) AS ranking_count,
                    MAX(eligible_security_count)
                        AS declared_count
                FROM analytics
                    .v_security_monthly_momentum_ranking
                GROUP BY analysis_month_number
            )
            SELECT COUNT_BIG(*)
            FROM source_population AS source
            FULL OUTER JOIN ranking_population AS ranking
              ON ranking.analysis_month_number
               = source.analysis_month_number
            WHERE source.analysis_month_number IS NULL
               OR ranking.analysis_month_number IS NULL
               OR source.source_count <> ranking.ranking_count
               OR source.source_count <> ranking.declared_count;
            """,
            0,
            (
                "Every monthly eligible population "
                "exactly matches the validated source."
            ),
            "Monthly source/ranking population mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT month_end_date, security_key
                FROM analytics
                    .v_security_monthly_momentum_ranking
                GROUP BY month_end_date, security_key
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            "Ranking month/security keys are unique.",
            "Duplicate ranking keys",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
                AS source
            FULL OUTER JOIN analytics
                .v_security_monthly_momentum_ranking
                AS ranking
              ON ranking.analysis_month_number
               = source.analysis_month_number
             AND ranking.security_key = source.security_key
            WHERE (
                    source.momentum_12_1_complete = 1
                AND source.momentum_12_1 IS NOT NULL
                  )
              AND (
                    ranking.security_key IS NULL
                 OR ranking.month_end_date
                    <> source.month_end_date
                 OR ranking.project_ticker
                    <> source.project_ticker
                 OR ranking.momentum_12_1_start_date
                    <> source.momentum_12_1_start_date
                 OR ranking.momentum_12_1_end_date
                    <> source.momentum_12_1_end_date
                 OR ranking.momentum_12_1
                    <> source.momentum_12_1
              )
               OR (
                    ranking.security_key IS NOT NULL
                AND (
                        source.security_key IS NULL
                     OR source.momentum_12_1_complete <> 1
                     OR source.momentum_12_1 IS NULL
                )
              );
            """,
            0,
            (
                "Ranking rows contain all and only the "
                "validated source signals."
            ),
            "Ranking/source row mismatches",
        )

        lines.append("")
        lines += section(
            "3. INDEPENDENT RANK AND TIE RECONSTRUCTION"
        )

        expect(
            """
            WITH expected AS (
                SELECT
                    feature.analysis_month_number,
                    feature.security_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            feature.analysis_month_number
                        ORDER BY
                            feature.momentum_12_1 DESC,
                            feature.security_key ASC
                    ) AS expected_rank_desc,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            feature.analysis_month_number
                        ORDER BY
                            feature.momentum_12_1 ASC,
                            feature.security_key DESC
                    ) AS expected_rank_asc,
                    COUNT_BIG(*) OVER (
                        PARTITION BY
                            feature.analysis_month_number,
                            feature.momentum_12_1
                    ) AS expected_tie_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            feature.analysis_month_number,
                            feature.momentum_12_1
                        ORDER BY feature.security_key ASC
                    ) AS expected_tie_order
                FROM analytics
                    .v_security_monthly_return_features
                    AS feature
                WHERE feature.momentum_12_1_complete = 1
                  AND feature.momentum_12_1 IS NOT NULL
            )
            SELECT COUNT_BIG(*)
            FROM expected
            JOIN analytics
                .v_security_monthly_momentum_ranking
                AS ranking
              ON ranking.analysis_month_number
               = expected.analysis_month_number
             AND ranking.security_key = expected.security_key
            WHERE ranking.momentum_rank_desc
                    <> expected.expected_rank_desc
               OR ranking.momentum_rank_asc
                    <> expected.expected_rank_asc
               OR ranking.momentum_tie_count
                    <> expected.expected_tie_count
               OR ranking.momentum_tie_break_order
                    <> expected.expected_tie_order;
            """,
            0,
            (
                "Every rank and tie field matches an "
                "independent source reconstruction."
            ),
            "Rank or tie reconstruction mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_ranking
            WHERE momentum_rank_desc + momentum_rank_asc
                <> eligible_security_count + 1;
            """,
            0,
            (
                "Ascending and descending ranks are "
                "exact complements."
            ),
            "Noncomplementary ranking rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_ranking
            WHERE momentum_rank_desc NOT BETWEEN
                    1 AND eligible_security_count
               OR momentum_rank_asc NOT BETWEEN
                    1 AND eligible_security_count
               OR momentum_tie_break_order NOT BETWEEN
                    1 AND momentum_tie_count;
            """,
            0,
            "All rank and tie positions are in range.",
            "Out-of-range rank or tie positions",
        )

        tied_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_ranking
            WHERE momentum_tie_count > 1;
            """,
        )

        lines.append("")
        lines += section(
            "4. DECILE AND PORTFOLIO ASSIGNMENT"
        )

        portfolio_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio;
            """,
            ranking_rows,
            (
                "Portfolio output preserves all "
                "23,401 ranking observations."
            ),
            "Portfolio rows",
        )

        expect(
            """
            WITH expected AS (
                SELECT
                    feature.analysis_month_number,
                    feature.security_key,
                    NTILE(10) OVER (
                        PARTITION BY
                            feature.analysis_month_number
                        ORDER BY
                            feature.momentum_12_1 ASC,
                            feature.security_key DESC
                    ) AS expected_decile
                FROM analytics
                    .v_security_monthly_return_features
                    AS feature
                WHERE feature.momentum_12_1_complete = 1
                  AND feature.momentum_12_1 IS NOT NULL
            )
            SELECT COUNT_BIG(*)
            FROM expected
            JOIN analytics
                .v_security_monthly_momentum_portfolio
                AS portfolio
              ON portfolio.analysis_month_number
               = expected.analysis_month_number
             AND portfolio.security_key
               = expected.security_key
            WHERE portfolio.momentum_decile
                <> expected.expected_decile;
            """,
            0,
            (
                "Every decile matches an independent "
                "NTILE reconstruction."
            ),
            "Decile reconstruction mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_ranking
                AS ranking
            FULL OUTER JOIN analytics
                .v_security_monthly_momentum_portfolio
                AS portfolio
              ON portfolio.analysis_month_number
               = ranking.analysis_month_number
             AND portfolio.security_key
               = ranking.security_key
            WHERE ranking.security_key IS NULL
               OR portfolio.security_key IS NULL
               OR portfolio.momentum_rank_desc
                    <> ranking.momentum_rank_desc
               OR portfolio.momentum_rank_asc
                    <> ranking.momentum_rank_asc
               OR portfolio.momentum_12_1
                    <> ranking.momentum_12_1;
            """,
            0,
            (
                "Portfolio rows exactly preserve their "
                "ranking inputs."
            ),
            "Portfolio/ranking mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT analysis_month_number
                FROM analytics
                    .v_security_monthly_momentum_portfolio
                GROUP BY analysis_month_number
                HAVING COUNT(DISTINCT momentum_decile) <> 10
            ) AS invalid;
            """,
            0,
            "Every ranking month contains all ten deciles.",
            "Months without all ten deciles",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    MIN(decile_security_count)
                        AS minimum_decile_count,
                    MAX(decile_security_count)
                        AS maximum_decile_count
                FROM analytics
                    .v_security_monthly_momentum_portfolio
            ) AS counts
            WHERE minimum_decile_count <> 48
               OR maximum_decile_count <> 50;
            """,
            0,
            (
                "Monthly decile populations have the "
                "validated range of 48-50."
            ),
            "Invalid decile-population range",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT analysis_month_number
                FROM analytics
                    .v_security_monthly_momentum_portfolio
                GROUP BY analysis_month_number
                HAVING MAX(decile_security_count)
                    - MIN(decile_security_count) > 1
            ) AS invalid;
            """,
            0,
            (
                "Decile sizes differ by no more than "
                "one security within every month."
            ),
            "Months with unbalanced deciles",
        )

        expect(
            """
            WITH counts AS (
                SELECT
                    analysis_month_number,
                    momentum_decile,
                    COUNT_BIG(*) AS expected_count
                FROM analytics
                    .v_security_monthly_momentum_portfolio
                GROUP BY
                    analysis_month_number,
                    momentum_decile
            )
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio
                AS portfolio
            JOIN counts
              ON counts.analysis_month_number
               = portfolio.analysis_month_number
             AND counts.momentum_decile
               = portfolio.momentum_decile
            WHERE portfolio.decile_security_count
                    <> counts.expected_count
               OR ABS(
                    CAST(portfolio.equal_weight AS float)
                    - 1.0
                      / CAST(counts.expected_count AS float)
               ) > 0.000000000000001;
            """,
            0,
            (
                "Every decile count and equal weight "
                "matches its independently derived value."
            ),
            "Decile count or weight mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio
            WHERE momentum_portfolio <>
                CASE momentum_decile
                    WHEN 1 THEN 'LOSER'
                    WHEN 10 THEN 'WINNER'
                    ELSE 'MIDDLE'
                END;
            """,
            0,
            (
                "Winner, middle, and loser labels "
                "exactly match their deciles."
            ),
            "Portfolio-label mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_monthly_summary
                AS lower_decile
            JOIN analytics
                .v_momentum_decile_monthly_summary
                AS upper_decile
              ON upper_decile.analysis_month_number
               = lower_decile.analysis_month_number
             AND upper_decile.momentum_decile
               = lower_decile.momentum_decile + 1
            WHERE lower_decile.maximum_momentum_12_1
                > upper_decile.minimum_momentum_12_1;
            """,
            0,
            (
                "Momentum is monotonic across adjacent "
                "deciles in every month."
            ),
            "Adjacent-decile momentum inversions",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT momentum_portfolio
                FROM analytics
                    .v_security_monthly_momentum_portfolio
                WHERE momentum_portfolio IN (
                    'WINNER', 'LOSER'
                )
                GROUP BY momentum_portfolio
                HAVING COUNT(
                    DISTINCT analysis_month_number
                ) <> 48
            ) AS invalid;
            """,
            0,
            (
                "Winner and loser portfolios both cover "
                "all 48 ranking months."
            ),
            "Incomplete winner/loser portfolios",
        )

        winner_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio
            WHERE momentum_portfolio = 'WINNER';
            """,
        )

        loser_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio
            WHERE momentum_portfolio = 'LOSER';
            """,
        )

        lines.append("")
        lines += section(
            "5. MONTHLY SUMMARY AND LOOK-AHEAD CONTROLS"
        )

        summary_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_monthly_summary;
            """,
            480,
            (
                "Monthly summary contains exactly "
                "480 month/decile rows."
            ),
            "Monthly summary rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    analysis_month_number,
                    momentum_decile
                FROM analytics
                    .v_momentum_decile_monthly_summary
                GROUP BY
                    analysis_month_number,
                    momentum_decile
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            "Monthly summary keys are unique.",
            "Duplicate monthly summary keys",
        )

        expect(
            """
            WITH expected AS (
                SELECT
                    analysis_month_number,
                    month_start_date,
                    month_end_date,
                    momentum_decile,
                    momentum_portfolio,
                    MAX(eligible_security_count)
                        AS eligible_security_count,
                    COUNT_BIG(*) AS decile_security_count,
                    MIN(momentum_12_1)
                        AS minimum_momentum_12_1,
                    MAX(momentum_12_1)
                        AS maximum_momentum_12_1,
                    AVG(momentum_12_1)
                        AS average_momentum_12_1,
                    SUM(equal_weight) AS equal_weight_sum
                FROM analytics
                    .v_security_monthly_momentum_portfolio
                GROUP BY
                    analysis_month_number,
                    month_start_date,
                    month_end_date,
                    momentum_decile,
                    momentum_portfolio
            )
            SELECT COUNT_BIG(*)
            FROM expected
            FULL OUTER JOIN analytics
                .v_momentum_decile_monthly_summary
                AS summary
              ON summary.analysis_month_number
               = expected.analysis_month_number
             AND summary.momentum_decile
               = expected.momentum_decile
            WHERE expected.analysis_month_number IS NULL
               OR summary.analysis_month_number IS NULL
               OR summary.month_end_date
                    <> expected.month_end_date
               OR summary.momentum_portfolio
                    <> expected.momentum_portfolio
               OR summary.eligible_security_count
                    <> expected.eligible_security_count
               OR summary.decile_security_count
                    <> expected.decile_security_count
               OR summary.minimum_momentum_12_1
                    <> expected.minimum_momentum_12_1
               OR summary.maximum_momentum_12_1
                    <> expected.maximum_momentum_12_1
               OR summary.average_momentum_12_1
                    <> expected.average_momentum_12_1
               OR summary.equal_weight_sum
                    <> expected.equal_weight_sum;
            """,
            0,
            (
                "Every summary row exactly reconciles "
                "to the detailed portfolio assignments."
            ),
            "Monthly summary reconciliation mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_momentum_decile_monthly_summary
            WHERE ABS(
                CAST(equal_weight_sum AS float) - 1.0
            ) > 0.000000000001;
            """,
            0,
            "Every monthly decile has unit total weight.",
            "Invalid monthly decile weight totals",
        )

        forward_columns = expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.columns AS c
            JOIN sys.views AS v
              ON v.object_id = c.object_id
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name IN (
                    'v_security_monthly_momentum_ranking',
                    'v_security_monthly_momentum_portfolio',
                    'v_momentum_decile_monthly_summary'
              )
              AND (
                    c.name LIKE '%forward%'
                 OR c.name LIKE 'lead[_]%'
              );
            """,
            0,
            (
                "Ranking and portfolio views contain no "
                "forward-looking fields."
            ),
            "Forward-looking columns",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.sql_modules AS module
            JOIN sys.views AS view_object
              ON view_object.object_id = module.object_id
            JOIN sys.schemas AS schema_object
              ON schema_object.schema_id
               = view_object.schema_id
            WHERE schema_object.name = 'analytics'
              AND view_object.name IN (
                    'v_security_monthly_momentum_ranking',
                    'v_security_monthly_momentum_portfolio',
                    'v_momentum_decile_monthly_summary'
              )
              AND (
                    module.definition LIKE '%LEAD(%'
                 OR module.definition LIKE '%FOLLOWING%'
              );
            """,
            0,
            (
                "Ranking definitions contain no future-row "
                "window functions."
            ),
            "Forward-window SQL definitions",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_ranking
            WHERE DATEDIFF(
                    MONTH,
                    momentum_12_1_start_date,
                    momentum_12_1_end_date
                  ) <> 11
               OR DATEDIFF(
                    MONTH,
                    momentum_12_1_end_date,
                    month_end_date
                  ) <> 1;
            """,
            0,
            (
                "Every ranking uses months -12 through "
                "-1 and skips its ranking month."
            ),
            "Invalid ranking signal windows",
        )

        lines.append("")
        lines += section("6. FINAL QUALITY GATE")

        if failures:
            lines += [
                (
                    "AZURE_SQL_MOMENTUM_RANKING_"
                    "INTEGRITY_AUDIT_FAILED"
                ),
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
                (
                    "AZURE_SQL_MOMENTUM_RANKING_"
                    "INTEGRITY_AUDIT_PASSED"
                ),
                f"Passed checks: {passed}",
                f"Ranking months: {ranking_months}",
                f"Eligible momentum rows: {ranking_rows:,}",
                "Monthly eligible population range: 485-491",
                "Monthly decile population range: 48-50",
                f"Portfolio assignment rows: {portfolio_rows:,}",
                f"Winner portfolio rows: {winner_rows:,}",
                f"Loser portfolio rows: {loser_rows:,}",
                (
                    "Rows participating in exact ties: "
                    f"{tied_rows:,}"
                ),
                (
                    "Monthly decile summary rows: "
                    f"{summary_rows:,}"
                ),
                (
                    "Forward-looking columns: "
                    f"{forward_columns}"
                ),
                "Core rows modified: 0",
                (
                    "Point-in-time rankings, ties, deciles, "
                    "labels, and equal weights are valid."
                ),
                (
                    "SQL MOMENTUM-RANKING QUALITY GATE "
                    "COMPLETE."
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
                "AZURE_SQL_MOMENTUM_RANKING_"
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
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(report, end="")
        print(f"Report saved: {REPORT_PATH}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()