from __future__ import annotations

import os
import time
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

REPORT = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_monthly_return_feature_integrity_audit.txt"
)

HORIZONS = (1, 3, 6, 12)

BENCHMARK_COMPLETE = {
    1: 118,
    3: 114,
    6: 108,
    12: 96,
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
        "ConnectRetryCount=5;"
        "ConnectRetryInterval=10;"
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

    for attempt in range(
        1,
        maximum_attempts + 1,
    ):
        try:
            return pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )

        except pyodbc.Error as error:
            error_text = str(error).lower()

            retryable = any(
                term in error_text
                for term in retryable_terms
            )

            if (
                not retryable
                or attempt == maximum_attempts
            ):
                raise

            print(
                "ODBC connection attempt "
                f"{attempt} / {maximum_attempts} failed. "
                f"Retrying in "
                f"{retry_wait_seconds} seconds."
            )

            time.sleep(retry_wait_seconds)

    raise RuntimeError(
        "ODBC connection retry loop ended unexpectedly."
    )


def main() -> None:
    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL MONTHLY RETURN-FEATURE INTEGRITY AUDIT"
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
        server, database, username, password = (
            environment()
        )

        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        cursor = connection.cursor()

        lines += section(
            "1. OBJECT AND SOURCE CONTROLS"
        )

        required = {
            "v_security_month_end_price",
            "v_benchmark_month_end_price",
            "v_security_monthly_return_features",
            "v_benchmark_monthly_return_features",
        }

        cursor.execute(
            """
            SELECT v.name
            FROM sys.views AS v
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics';
            """
        )
        actual = {
            str(row[0])
            for row in cursor.fetchall()
        }
        missing = sorted(required - actual)

        check(
            not missing,
            (
                "All monthly source and feature "
                "views are present."
            ),
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
            "2. CONSTITUENT FEATURE POPULATION"
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features;
            """,
            30_211,
            (
                "Constituent feature view contains "
                "exactly 30,211 rows."
            ),
            "Constituent feature rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    month_end_date,
                    security_key
                FROM analytics
                    .v_security_monthly_return_features
                GROUP BY
                    month_end_date,
                    security_key
                HAVING COUNT_BIG(*) <> 1
            ) AS duplicates;
            """,
            0,
            (
                "Constituent feature month/security "
                "keys are unique."
            ),
            "Duplicate constituent feature keys",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
                AS feature
            FULL OUTER JOIN analytics
                .security_month_end_snapshot
                AS source
              ON source.month_end_date
               = feature.month_end_date
             AND source.security_key
               = feature.security_key
            WHERE feature.security_key IS NULL
               OR source.security_key IS NULL
               OR feature.analysis_month_number
                  <> source.analysis_month_number
               OR feature.project_ticker
                  <> source.project_ticker
               OR feature.adjusted_close
                  <> source.adjusted_close;
            """,
            0,
            (
                "Every constituent feature row "
                "reconciles to its month-end source."
            ),
            "Feature/source mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM sys.columns
            WHERE object_id = OBJECT_ID(
                'analytics.v_security_monthly_return_features'
            )
              AND (
                    name LIKE '%forward%'
                 OR name LIKE 'lead[_]%'
              );
            """,
            0,
            (
                "The constituent signal view contains "
                "no forward-looking fields."
            ),
            "Forward-looking feature columns",
        )

        lines.append("")

        lines += section(
            "3. CONSTITUENT TRAILING RETURNS"
        )

        complete_counts: dict[int, int] = {}

        for horizon in HORIZONS:
            expect(
                f"""
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_security_monthly_return_features
                    AS feature
                LEFT JOIN analytics
                    .security_month_end_snapshot
                    AS lag_price
                  ON lag_price.security_key
                   = feature.security_key
                 AND lag_price.analysis_month_number
                   = feature.analysis_month_number
                     - {horizon}
                WHERE
                    feature.trailing_return_{horizon}m_complete
                    <> CASE
                        WHEN lag_price.security_key IS NULL
                        THEN 0
                        ELSE 1
                    END
                   OR (
                        feature
                            .trailing_return_{horizon}m_complete
                            = 1
                        AND (
                            feature
                                .trailing_return_{horizon}m
                                IS NULL
                            OR feature
                                .lag_{horizon}_month_end_date
                                <> lag_price.month_end_date
                        )
                   )
                   OR (
                        feature
                            .trailing_return_{horizon}m_complete
                            = 0
                        AND (
                            feature
                                .trailing_return_{horizon}m
                                IS NOT NULL
                            OR feature
                                .lag_{horizon}_month_end_date
                                IS NOT NULL
                        )
                   );
                """,
                0,
                (
                    f"{horizon}-month completeness "
                    "exactly matches its lag observation."
                ),
                (
                    f"{horizon}-month completeness "
                    "mismatches"
                ),
            )

            expect(
                f"""
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_security_monthly_return_features
                    AS feature
                JOIN analytics
                    .security_month_end_snapshot
                    AS lag_price
                  ON lag_price.security_key
                   = feature.security_key
                 AND lag_price.analysis_month_number
                   = feature.analysis_month_number
                     - {horizon}
                WHERE ABS(
                    CAST(
                        feature.trailing_return_{horizon}m
                        AS float
                    )
                    - (
                        CAST(
                            feature.adjusted_close
                            AS float
                        )
                        / CAST(
                            lag_price.adjusted_close
                            AS float
                        )
                        - 1.0
                    )
                ) > 0.000000000000001;
                """,
                0,
                (
                    f"Every {horizon}-month return "
                    "matches the adjusted-close formula."
                ),
                (
                    f"{horizon}-month formula "
                    "mismatches"
                ),
            )

            complete_counts[horizon] = scalar(
                cursor,
                f"""
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_security_monthly_return_features
                WHERE trailing_return_{horizon}m_complete
                    = 1;
                """,
            )

            check(
                (
                    0
                    < complete_counts[horizon]
                    < 30_211
                ),
                (
                    f"{horizon}-month completeness "
                    "population: "
                    f"{complete_counts[horizon]:,} rows."
                ),
                (
                    f"Invalid {horizon}-month "
                    "completeness population: "
                    f"{complete_counts[horizon]:,}."
                ),
            )

        lines.append("")

        lines += section(
            "4. CANONICAL 12-1 MOMENTUM"
        )

        momentum_rows = expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1;
            """,
            23_401,
            (
                "Canonical 12-1 momentum is complete "
                "for 23,401 rows."
            ),
            "Complete momentum rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
                AS feature
            LEFT JOIN analytics
                .security_month_end_snapshot
                AS lag_1
              ON lag_1.security_key
               = feature.security_key
             AND lag_1.analysis_month_number
               = feature.analysis_month_number - 1
            LEFT JOIN analytics
                .security_month_end_snapshot
                AS lag_12
              ON lag_12.security_key
               = feature.security_key
             AND lag_12.analysis_month_number
               = feature.analysis_month_number - 12
            WHERE
                feature.momentum_12_1_complete
                <> CASE
                    WHEN lag_1.security_key IS NOT NULL
                     AND lag_12.security_key IS NOT NULL
                    THEN 1
                    ELSE 0
                END
               OR (
                    feature.momentum_12_1_complete = 1
                    AND feature.momentum_12_1 IS NULL
               )
               OR (
                    feature.momentum_12_1_complete = 0
                    AND feature.momentum_12_1 IS NOT NULL
               )
               OR (
                    lag_1.security_key IS NULL
                    AND feature.momentum_12_1_end_date
                        IS NOT NULL
               )
               OR (
                    lag_1.security_key IS NOT NULL
                    AND feature.momentum_12_1_end_date
                        <> lag_1.month_end_date
               )
               OR (
                    lag_12.security_key IS NULL
                    AND feature.momentum_12_1_start_date
                        IS NOT NULL
               )
               OR (
                    lag_12.security_key IS NOT NULL
                    AND feature.momentum_12_1_start_date
                        <> lag_12.month_end_date
               );
            """,
            0,
            (
                "Momentum completeness and anchor "
                "dates match months -1 and -12."
            ),
            "Momentum completeness mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
                AS feature
            JOIN analytics
                .security_month_end_snapshot
                AS lag_1
              ON lag_1.security_key
               = feature.security_key
             AND lag_1.analysis_month_number
               = feature.analysis_month_number - 1
            JOIN analytics
                .security_month_end_snapshot
                AS lag_12
              ON lag_12.security_key
               = feature.security_key
             AND lag_12.analysis_month_number
               = feature.analysis_month_number - 12
            WHERE ABS(
                CAST(
                    feature.momentum_12_1
                    AS float
                )
                - (
                    CAST(
                        lag_1.adjusted_close
                        AS float
                    )
                    / CAST(
                        lag_12.adjusted_close
                        AS float
                    )
                    - 1.0
                )
            ) > 0.000000000000001;
            """,
            0,
            (
                "Every momentum signal matches the "
                "month -1 / month -12 formula."
            ),
            "Momentum formula mismatches",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND (
                    DATEDIFF(
                        MONTH,
                        momentum_12_1_start_date,
                        momentum_12_1_end_date
                    ) <> 11
                 OR DATEDIFF(
                        MONTH,
                        momentum_12_1_end_date,
                        month_end_date
                    ) <> 1
              );
            """,
            0,
            (
                "Every momentum window spans months "
                "-12 through -1 and skips the "
                "ranking month."
            ),
            "Invalid momentum date windows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_security_monthly_return_features
                AS feature
            JOIN analytics
                .security_month_end_snapshot
                AS prior_month
              ON prior_month.security_key
               = feature.security_key
             AND prior_month.analysis_month_number
               = feature.analysis_month_number - 1
            WHERE feature.security_key = 'DAY'
              AND feature.project_ticker = 'DAY'
              AND prior_month.project_ticker = 'CDAY'
              AND feature.trailing_return_1m_complete
                  = 1;
            """,
            1,
            (
                "The CDAY-to-DAY identity transition "
                "remains continuous at month-end."
            ),
            (
                "Complete CDAY-to-DAY monthly "
                "transitions"
            ),
        )

        lines.append("")

        lines += section(
            "5. BENCHMARK FEATURES"
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_return_features;
            """,
            120,
            (
                "Benchmark feature view contains "
                "exactly 120 rows."
            ),
            "Benchmark feature rows",
        )

        for horizon in HORIZONS:
            expected = BENCHMARK_COMPLETE[horizon]

            expect(
                f"""
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_benchmark_monthly_return_features
                WHERE trailing_return_{horizon}m_complete
                    = 1
                  AND trailing_return_{horizon}m
                    IS NOT NULL;
                """,
                expected,
                (
                    f"Benchmark {horizon}-month "
                    "completeness is exact: "
                    f"{expected} rows."
                ),
                (
                    f"Complete benchmark "
                    f"{horizon}-month rows"
                ),
            )

            expect(
                f"""
                SELECT COUNT_BIG(*)
                FROM analytics
                    .v_benchmark_monthly_return_features
                    AS feature
                JOIN analytics
                    .benchmark_month_end_snapshot
                    AS lag_price
                  ON lag_price.security_key
                   = feature.security_key
                 AND lag_price.project_ticker
                   = feature.project_ticker
                 AND lag_price.analysis_month_number
                   = feature.analysis_month_number
                     - {horizon}
                WHERE ABS(
                    CAST(
                        feature.trailing_return_{horizon}m
                        AS float
                    )
                    - (
                        CAST(
                            feature.adjusted_close
                            AS float
                        )
                        / CAST(
                            lag_price.adjusted_close
                            AS float
                        )
                        - 1.0
                    )
                ) > 0.000000000000001;
                """,
                0,
                (
                    "Every benchmark "
                    f"{horizon}-month return "
                    "matches its formula."
                ),
                (
                    "Benchmark "
                    f"{horizon}-month formula mismatches"
                ),
            )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND momentum_12_1 IS NOT NULL;
            """,
            96,
            (
                "Both benchmarks contain 48 complete "
                "momentum observations."
            ),
            "Complete benchmark momentum rows",
        )

        expect(
            """
            SELECT COUNT_BIG(*)
            FROM analytics
                .v_benchmark_monthly_return_features
                AS feature
            JOIN analytics
                .benchmark_month_end_snapshot
                AS lag_1
              ON lag_1.security_key
               = feature.security_key
             AND lag_1.project_ticker
               = feature.project_ticker
             AND lag_1.analysis_month_number
               = feature.analysis_month_number - 1
            JOIN analytics
                .benchmark_month_end_snapshot
                AS lag_12
              ON lag_12.security_key
               = feature.security_key
             AND lag_12.project_ticker
               = feature.project_ticker
             AND lag_12.analysis_month_number
               = feature.analysis_month_number - 12
            WHERE ABS(
                CAST(
                    feature.momentum_12_1
                    AS float
                )
                - (
                    CAST(
                        lag_1.adjusted_close
                        AS float
                    )
                    / CAST(
                        lag_12.adjusted_close
                        AS float
                    )
                    - 1.0
                )
            ) > 0.000000000000001;
            """,
            0,
            (
                "Every benchmark momentum signal "
                "matches its formula."
            ),
            "Benchmark momentum formula mismatches",
        )

        lines.append("")

        lines += section(
            "6. FINAL QUALITY GATE"
        )

        if failures:
            lines += [
                (
                    "AZURE_SQL_MONTHLY_RETURN_FEATURE_"
                    "INTEGRITY_AUDIT_FAILED"
                ),
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]

            lines += [
                f"{number}. {failure}"
                for number, failure in enumerate(
                    failures,
                    1,
                )
            ]
        else:
            lines += [
                (
                    "AZURE_SQL_MONTHLY_RETURN_FEATURE_"
                    "INTEGRITY_AUDIT_PASSED"
                ),
                f"Passed checks: {passed}",
                "Constituent feature rows: 30,211",
                (
                    "Complete 1-month returns: "
                    f"{complete_counts[1]:,}"
                ),
                (
                    "Complete 3-month returns: "
                    f"{complete_counts[3]:,}"
                ),
                (
                    "Complete 6-month returns: "
                    f"{complete_counts[6]:,}"
                ),
                (
                    "Complete 12-month returns: "
                    f"{complete_counts[12]:,}"
                ),
                (
                    "Complete canonical 12-1 "
                    "momentum signals: "
                    f"{momentum_rows:,}"
                ),
                "Benchmark feature rows: 120",
                "Forward-looking feature columns: 0",
                "Core rows modified: 0",
                (
                    "Exact-calendar monthly return and "
                    "momentum features are analysis-ready."
                ),
                (
                    "SQL MONTHLY FEATURE-ENGINEERING "
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
                "AZURE_SQL_MONTHLY_RETURN_FEATURE_"
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
        REPORT.write_text(
            report,
            encoding="utf-8",
        )
        print(report, end="")
        print(f"Report saved: {REPORT}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()