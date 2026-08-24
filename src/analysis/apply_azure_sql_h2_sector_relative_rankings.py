from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

SQL_PATH = (
    ROOT
    / "sql"
    / "analytics"
    / "010_create_h2_sector_relative_momentum_ranking.sql"
)

GICS_PATH = (
    ROOT
    / "data"
    / "interim"
    / "security_gics_sector_month_end_2021_2025.csv"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_h2_sector_momentum_ranking_application.txt"
)

SCRIPT_VERSION = "2026-08-24-v2-h2-sector-ranking-float-weight-fix"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

CANONICAL_SECTORS = {
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
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

EXPECTED_GICS_ROWS = 30_211
EXPECTED_MOMENTUM_ROWS = 30_121
EXPECTED_MONTHS = 60
EXPECTED_SECTORS = 11
EXPECTED_SECTOR_MONTHS = 660
EXPECTED_QUINTILE_SUMMARY_ROWS = 3_300


def section(title: str) -> list[str]:
    rule = "=" * 88
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
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=False,
            )
            print(
                f"ODBC connection established on attempt {attempt} / 5."
            )
            return connection
        except pyodbc.Error as error:
            retryable = any(
                term in str(error).lower()
                for term in retryable_terms
            )
            if not retryable or attempt == 5:
                raise
            print(
                f"ODBC connection attempt {attempt} / 5 failed. "
                "Retrying in 10 seconds."
            )
            time.sleep(10)

    raise RuntimeError("ODBC retry loop ended unexpectedly.")


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
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = section(
        "AZURE SQL H2 SECTOR-RELATIVE MOMENTUM RANKING APPLICATION"
    )
    lines += [
        "Connection status: NOT ATTEMPTED",
        "Credentials included in report: NO",
        f"Migration: {SQL_PATH.relative_to(ROOT)}",
        f"Validated GICS input: {GICS_PATH.relative_to(ROOT)}",
        (
            "Scope: sector assignment load + preregistered within-sector "
            "ranking/quintiles only"
        ),
        "Forward-return / performance inspection: NO",
        (
            "Weight implementation: explicit FLOAT 1/11 sector-neutral "
            "allocation"
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
        if not GICS_PATH.exists():
            raise FileNotFoundError(GICS_PATH)

        lines += section("1. LOCAL GICS INPUT CONTROL")

        gics = pd.read_csv(GICS_PATH)

        expected_columns = [
            "analysis_month_number",
            "month_end_date",
            "security_key",
            "project_ticker",
            "gics_sector",
        ]

        check(
            list(gics.columns) == expected_columns,
            "Local GICS input has the exact expected five-column schema.",
            f"Unexpected GICS columns: {list(gics.columns)}",
        )

        if failures:
            raise RuntimeError("Local GICS schema validation failed.")

        gics["analysis_month_number"] = pd.to_numeric(
            gics["analysis_month_number"],
            errors="raise",
        ).astype(int)
        gics["month_end_date"] = pd.to_datetime(
            gics["month_end_date"],
            errors="raise",
        )
        gics["security_key"] = (
            gics["security_key"].astype(str).str.strip()
        )
        gics["project_ticker"] = (
            gics["project_ticker"].astype(str).str.strip()
        )
        gics["gics_sector"] = (
            gics["gics_sector"].astype(str).str.strip()
        )

        check(
            len(gics) == EXPECTED_GICS_ROWS,
            "Validated monthly GICS input contains exactly 30,211 rows.",
            f"GICS input rows: {len(gics):,}.",
        )
        check(
            gics["analysis_month_number"].nunique() == EXPECTED_MONTHS
            and int(gics["analysis_month_number"].min()) == 1
            and int(gics["analysis_month_number"].max()) == 60,
            "GICS input spans analysis months 1 through 60.",
            "GICS analysis-month coverage is invalid.",
        )
        check(
            not gics.duplicated(
                ["analysis_month_number", "security_key"]
            ).any(),
            "GICS month/security keys are unique.",
            "Duplicate GICS month/security keys detected.",
        )
        check(
            set(gics["gics_sector"]) == CANONICAL_SECTORS,
            "GICS input contains exactly the 11 canonical sectors.",
            (
                "Unexpected GICS sector set: "
                + ", ".join(sorted(set(gics["gics_sector"])))
            ),
        )

        month_sector_count = (
            gics.groupby("analysis_month_number")["gics_sector"]
            .nunique()
        )
        check(
            bool((month_sector_count == EXPECTED_SECTORS).all()),
            "All 60 local ranking months contain all 11 GICS sectors.",
            "At least one local ranking month is missing a GICS sector.",
        )

        if failures:
            raise RuntimeError("Local GICS validation failed.")

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

        lines += section("2. PRE-APPLICATION DATABASE CONTROLS")

        for table, expected in CORE_COUNTS.items():
            expect(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table} remains {expected:,} rows.",
                f"core.{table} population",
            )

        expect(
            cursor,
            "SELECT COUNT_BIG(*) FROM analytics.security_month_end_snapshot;",
            EXPECTED_GICS_ROWS,
            "Ranking snapshot remains exactly 30,211 rows.",
            "Ranking snapshot rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND momentum_12_1 IS NOT NULL;
            """,
            EXPECTED_MOMENTUM_ROWS,
            (
                "Corrected H1 feature layer still contains exactly "
                "30,121 complete 12-1 signals."
            ),
            "Complete corrected momentum rows",
        )

        if failures:
            raise RuntimeError("Pre-application database control failed.")

        lines += section("3. CREATE TABLE, LOAD GICS, CREATE RANKING VIEWS")

        batches = sql_batches(
            SQL_PATH.read_text(encoding="utf-8")
        )

        check(
            len(batches) == 4,
            "H2 ranking migration contains exactly four SQL batches.",
            f"Migration batches: {len(batches)}; expected 4.",
        )

        if failures:
            raise RuntimeError("Migration batch validation failed.")

        # Batch 1 creates the table if needed.
        cursor.execute(batches[0])
        lines.append(
            "PASS: analytics.security_month_end_gics_sector is present."
        )
        passed += 1

        cursor.execute(
            "DELETE FROM analytics.security_month_end_gics_sector;"
        )

        rows = [
            (
                int(row.analysis_month_number),
                pd.Timestamp(row.month_end_date).date(),
                str(row.security_key),
                str(row.project_ticker),
                str(row.gics_sector),
            )
            for row in gics.itertuples(index=False)
        ]

        cursor.fast_executemany = True
        statement = """
        INSERT INTO analytics.security_month_end_gics_sector
        (
            analysis_month_number,
            month_end_date,
            security_key,
            project_ticker,
            gics_sector
        )
        VALUES (?, ?, ?, ?, ?);
        """

        for start in range(0, len(rows), 5000):
            cursor.executemany(
                statement,
                rows[start : start + 5000],
            )

        lines.append(
            "PASS: Loaded 30,211 validated point-in-time GICS rows."
        )
        passed += 1

        # Batches 2-4 are ranking/portfolio/summary views.
        for batch_number, batch in enumerate(
            batches[1:],
            start=2,
        ):
            cursor.execute(batch)
            lines.append(
                f"PASS: Executed SQL batch {batch_number} / 4."
            )
            passed += 1

        lines += section("4. H2 RANKING / QUINTILE QUALITY GATE")

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.security_month_end_gics_sector;
            """,
            EXPECTED_GICS_ROWS,
            "Azure GICS table contains exactly 30,211 rows.",
            "Azure GICS rows",
        )

        ranking_rows = expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_sector_momentum_ranking;
            """,
            EXPECTED_MOMENTUM_ROWS,
            (
                "H2 ranking preserves exactly the 30,121 "
                "preregistered complete momentum signals."
            ),
            "H2 ranking rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_sector_momentum_portfolio;
            """,
            EXPECTED_MOMENTUM_ROWS,
            "H2 portfolio assignment preserves every H2 ranking row.",
            "H2 portfolio rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_security_monthly_sector_momentum_ranking;
            """,
            EXPECTED_MONTHS,
            "H2 rankings span all 60 analysis months.",
            "H2 ranking months",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
            (
                SELECT
                    analysis_month_number,
                    gics_sector
                FROM analytics.v_security_monthly_sector_momentum_ranking
                GROUP BY
                    analysis_month_number,
                    gics_sector
            ) AS x;
            """,
            EXPECTED_SECTOR_MONTHS,
            "H2 rankings contain exactly 660 month/sector partitions.",
            "Month/sector partitions",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
            (
                SELECT
                    analysis_month_number,
                    gics_sector
                FROM analytics.v_security_monthly_sector_momentum_ranking
                GROUP BY
                    analysis_month_number,
                    gics_sector
                HAVING COUNT_BIG(*) < 5
            ) AS x;
            """,
            0,
            "Every H2 sector-month has at least five eligible securities.",
            "Sector-months below five eligible securities",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_sector_momentum_quintile_monthly_summary;
            """,
            EXPECTED_QUINTILE_SUMMARY_ROWS,
            (
                "H2 quintile summary contains exactly "
                "3,300 month/sector/quintile rows."
            ),
            "H2 quintile summary rows",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_security_monthly_sector_momentum_portfolio
            WHERE sector_momentum_quintile NOT BETWEEN 1 AND 5
               OR (
                    sector_momentum_quintile = 1
                AND sector_momentum_portfolio <> 'LOSER'
                  )
               OR (
                    sector_momentum_quintile = 5
                AND sector_momentum_portfolio <> 'WINNER'
                  )
               OR (
                    sector_momentum_quintile BETWEEN 2 AND 4
                AND sector_momentum_portfolio <> 'MIDDLE'
                  );
            """,
            0,
            "Q1/Q5/MIDDLE portfolio labels match the preregistration.",
            "Portfolio-label mismatches",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_sector_momentum_quintile_monthly_summary
            WHERE ABS(sector_weight_sum - 1.0) > 0.000000000001
               OR ABS(
                    sector_neutral_leg_weight_sum
                    - (
                        CAST(1.0 AS FLOAT)
                        / CAST(11.0 AS FLOAT)
                      )
                  ) > 0.000000000001;
            """,
            0,
            (
                "Every sector/quintile sleeve sums to sector weight 1 "
                "and aggregate sector-neutral weight 1/11."
            ),
            "Weight-sum mismatches",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
            (
                SELECT
                    analysis_month_number,
                    gics_sector,
                    MIN(sector_momentum_rank_asc) AS min_rank,
                    MAX(sector_momentum_rank_asc) AS max_rank,
                    COUNT_BIG(*) AS n
                FROM analytics.v_security_monthly_sector_momentum_ranking
                GROUP BY
                    analysis_month_number,
                    gics_sector
                HAVING MIN(sector_momentum_rank_asc) <> 1
                    OR MAX(sector_momentum_rank_asc) <> COUNT_BIG(*)
            ) AS x;
            """,
            0,
            "Within-sector momentum ranks are contiguous from 1 to N.",
            "Non-contiguous sector ranks",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
            (
                SELECT
                    analysis_month_number,
                    gics_sector,
                    sector_momentum_quintile,
                    COUNT_BIG(*) AS n
                FROM analytics.v_security_monthly_sector_momentum_portfolio
                GROUP BY
                    analysis_month_number,
                    gics_sector,
                    sector_momentum_quintile
            ) AS q
            JOIN
            (
                SELECT
                    analysis_month_number,
                    gics_sector,
                    MIN(n) AS min_n,
                    MAX(n) AS max_n
                FROM
                (
                    SELECT
                        analysis_month_number,
                        gics_sector,
                        sector_momentum_quintile,
                        COUNT_BIG(*) AS n
                    FROM analytics.v_security_monthly_sector_momentum_portfolio
                    GROUP BY
                        analysis_month_number,
                        gics_sector,
                        sector_momentum_quintile
                ) AS d
                GROUP BY
                    analysis_month_number,
                    gics_sector
                HAVING MAX(n) - MIN(n) > 1
            ) AS bad
              ON bad.analysis_month_number = q.analysis_month_number
             AND bad.gics_sector = q.gics_sector;
            """,
            0,
            "Within every sector-month, quintile sizes differ by at most one.",
            "Unbalanced NTILE(5) sector partitions",
        )

        lines += section("5. LOOK-AHEAD / DEPENDENCY CONTROL")

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
                  'v_security_monthly_sector_momentum_ranking',
                  'v_security_monthly_sector_momentum_portfolio',
                  'v_sector_momentum_quintile_monthly_summary'
              )
              AND LOWER(
                    COALESCE(
                        OBJECT_NAME(d.referenced_id),
                        ''
                    )
                  ) LIKE '%forward%';
            """,
            0,
            "H2 ranking views have no dependency on a forward-return object.",
            "Forward-return dependencies",
        )

        expect(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM sys.columns AS c
            JOIN sys.views AS v
              ON v.object_id = c.object_id
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name IN
              (
                  'v_security_monthly_sector_momentum_ranking',
                  'v_security_monthly_sector_momentum_portfolio',
                  'v_sector_momentum_quintile_monthly_summary'
              )
              AND (
                    LOWER(c.name) LIKE '%forward%'
                 OR LOWER(c.name) LIKE '%holding_return%'
                 OR LOWER(c.name) LIKE '%future%'
                 OR LOWER(c.name) LIKE '%alpha%'
                 OR LOWER(c.name) LIKE '%sharpe%'
                 OR LOWER(c.name) LIKE '%transaction_cost%'
              );
            """,
            0,
            (
                "H2 ranking schemas contain no forward-performance, "
                "risk, or cost fields."
            ),
            "Forbidden ranking columns",
        )

        for table, expected in CORE_COUNTS.items():
            expect(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
                expected,
                f"core.{table} remains unchanged at {expected:,} rows.",
                f"core.{table} post-application population",
            )

        if failures:
            raise RuntimeError("H2 ranking application quality gate failed.")

        connection.commit()
        lines += [
            "",
            "AZURE_SQL_H2_SECTOR_MOMENTUM_RANKING_APPLICATION_PASSED",
            f"Passed checks: {passed}",
            f"GICS rows loaded: {EXPECTED_GICS_ROWS:,}",
            f"H2 ranking rows: {ranking_rows:,}",
            f"Ranking months: {EXPECTED_MONTHS}",
            f"Month/sector partitions: {EXPECTED_SECTOR_MONTHS}",
            f"Month/sector/quintile rows: {EXPECTED_QUINTILE_SUMMARY_ROWS:,}",
            "Forward-return / H2 performance results inspected: 0",
            "Core rows modified: 0",
            (
                "H2 ranking layer is ready for independent integrity audit. "
                "Do not construct forward returns until that audit passes."
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
            "AZURE_SQL_H2_SECTOR_MOMENTUM_RANKING_APPLICATION_FAILED",
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
