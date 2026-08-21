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
    / "006_create_momentum_ranking_views.sql"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_momentum_ranking_application.txt"
)

NEW_VIEWS = {
    "v_momentum_decile_monthly_summary",
    "v_security_monthly_momentum_portfolio",
    "v_security_monthly_momentum_ranking",
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
        "AZURE SQL MOMENTUM-RANKING APPLICATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        (
            "Strategy: point-in-time ranking, "
            "deterministic ties, and decile assignment"
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
        connection.timeout = 300
        cursor = connection.cursor()
        lines[3] = "Connection status: SUCCESS"

        lines += section(
            "1. DEPENDENCY AND CORE CONTROLS"
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.views AS v
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name =
                'v_security_monthly_return_features';
            """,
            1,
            (
                "The validated monthly momentum "
                "feature dependency is present."
            ),
            "Monthly feature dependencies",
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
                "The source contains exactly 23,401 "
                "complete momentum signals."
            ),
            "Complete source momentum rows",
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
            "2. APPLY MOMENTUM-RANKING VIEWS"
        )

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )
        check(
            len(batches) == 4,
            (
                "Migration contains the expected "
                "four SQL batches."
            ),
            (
                f"Migration contains {len(batches)} "
                "batches; expected 4."
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
            "3. VERIFY RANKING AND PORTFOLIO OUTPUTS"
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
            "All three momentum-ranking views are present.",
            "Missing views: " + ", ".join(missing_views),
        )

        ranking_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_ranking;
            """,
            source_rows,
            (
                "Ranking view contains all and only "
                "23,401 complete momentum signals."
            ),
            "Ranking rows",
        )

        portfolio_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_momentum_portfolio;
            """,
            ranking_rows,
            (
                "Portfolio assignment preserves all "
                "23,401 ranking rows."
            ),
            "Portfolio rows",
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
            "Monthly decile summary rows",
        )

        validation_queries = [
            (
                """
                SELECT COUNT_BIG(*)
                FROM (
                    SELECT month_end_date, security_key
                    FROM analytics
                        .v_security_monthly_momentum_ranking
                    GROUP BY month_end_date, security_key
                    HAVING COUNT_BIG(*) <> 1
                ) AS invalid;
                """,
                "Ranking month/security keys are unique.",
                "Duplicate ranking keys",
            ),
            (
                """
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_security_monthly_momentum_ranking
                WHERE momentum_12_1_complete <> 1
                   OR momentum_12_1 IS NULL;
                """,
                (
                    "Every ranking row contains a "
                    "complete momentum signal."
                ),
                "Ineligible ranking rows",
            ),
            (
                """
                SELECT COUNT_BIG(*)
                FROM (
                    SELECT analysis_month_number
                    FROM analytics
                        .v_security_monthly_momentum_ranking
                    GROUP BY analysis_month_number
                    HAVING COUNT_BIG(*)
                            <> COUNT_BIG(
                                DISTINCT momentum_rank_desc
                            )
                        OR MIN(momentum_rank_desc) <> 1
                        OR MAX(momentum_rank_desc)
                            <> MAX(eligible_security_count)
                        OR COUNT_BIG(*)
                            <> MAX(eligible_security_count)
                ) AS invalid;
                """,
                (
                    "Every monthly descending rank is "
                    "unique, contiguous, and complete."
                ),
                "Months with invalid ranks",
            ),
            (
                """
                SELECT COUNT_BIG(*)
                FROM (
                    SELECT analysis_month_number
                    FROM analytics
                        .v_security_monthly_momentum_portfolio
                    GROUP BY analysis_month_number
                    HAVING COUNT(DISTINCT momentum_decile)
                        <> 10
                ) AS invalid;
                """,
                "Every ranking month contains ten deciles.",
                "Months without ten deciles",
            ),
            (
                """
                SELECT COUNT_BIG(*)
                FROM (
                    SELECT analysis_month_number
                    FROM analytics
                        .v_momentum_decile_monthly_summary
                    GROUP BY analysis_month_number
                    HAVING MAX(decile_security_count)
                        - MIN(decile_security_count) > 1
                ) AS invalid;
                """,
                (
                    "Monthly decile sizes differ by no "
                    "more than one security."
                ),
                "Months with unbalanced deciles",
            ),
            (
                """
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_security_monthly_momentum_portfolio
                WHERE momentum_decile NOT BETWEEN 1 AND 10
                   OR momentum_portfolio <>
                        CASE momentum_decile
                            WHEN 1 THEN 'LOSER'
                            WHEN 10 THEN 'WINNER'
                            ELSE 'MIDDLE'
                        END;
                """,
                (
                    "Winner, middle, and loser labels "
                    "match their deciles."
                ),
                "Invalid portfolio labels",
            ),
            (
                """
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_momentum_decile_monthly_summary
                WHERE ABS(
                    CAST(equal_weight_sum AS float) - 1.0
                ) > 0.000000000001;
                """,
                "Every monthly decile has unit total weight.",
                "Invalid decile weight totals",
            ),
            (
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
                (
                    "Momentum-ranking objects contain "
                    "no forward-looking fields."
                ),
                "Forward-looking ranking columns",
            ),
        ]

        for query, success, label in validation_queries:
            expect(query, 0, success, label)

        cursor.execute(
            """
            SELECT
                MIN(eligible_security_count),
                MAX(eligible_security_count)
            FROM analytics
                .v_security_monthly_momentum_ranking;
            """
        )
        population_row = cursor.fetchone()
        minimum_population = int(population_row[0])
        maximum_population = int(population_row[1])

        check(
            minimum_population >= 10,
            (
                "Every ranking month has at least ten "
                "eligible securities."
            ),
            (
                "Minimum eligible population is only "
                f"{minimum_population}."
            ),
        )

        lines.append("")
        lines += section(
            "4. POST-MIGRATION CORE CONTROL"
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
            "PASS: Momentum-ranking migration committed."
        )
        passed += 1

        lines.append("")
        lines += section("5. FINAL QUALITY GATE")
        lines += [
            "AZURE_SQL_MOMENTUM_RANKING_APPLICATION_PASSED",
            f"Passed checks: {passed}",
            "Analytical views created or updated: 3",
            f"Ranking months: {ranking_months}",
            f"Eligible momentum rows: {ranking_rows:,}",
            (
                "Monthly eligible population range: "
                f"{minimum_population:,}-"
                f"{maximum_population:,}"
            ),
            f"Monthly decile summary rows: {summary_rows:,}",
            "Forward-looking ranking columns: 0",
            "Core rows modified: 0",
            (
                "Point-in-time momentum rankings and "
                "portfolio assignments are ready for "
                "independent auditing."
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
            "AZURE_SQL_MOMENTUM_RANKING_APPLICATION_FAILED",
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