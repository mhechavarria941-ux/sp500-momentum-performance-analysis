from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from mssql_python import connect


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "interim"

BRIDGE = (
    DATA
    / "sp500_membership_price_bridge_2021_2025.csv.gz"
)

BENCHMARKS = (
    DATA
    / "sp500_benchmark_price_history_2021_2025.csv.gz"
)

REPORT = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_market_data_integrity_audit.txt"
)


EXPECTED_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}


CHECKPOINTS = {
    "2021-01-01": 505,
    "2021-12-31": 505,
    "2022-12-31": 503,
    "2023-12-31": 503,
    "2024-12-31": 503,
    "2025-12-31": 503,
}


AGGREGATE_COLUMNS = [
    "adjusted_close",
    "volume",
    "dividend",
    "split_factor",
]


def section(
    title: str,
) -> list[str]:

    rule = "=" * 79

    return [
        rule,
        title,
        rule,
    ]


def environment() -> tuple[
    str,
    str,
    str,
    str,
]:

    load_dotenv(
        ROOT / ".env"
    )

    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )

    values = tuple(
        os.getenv(name)
        for name in names
    )

    missing = [
        name
        for name, value in zip(
            names,
            values,
        )
        if not value
    ]

    if missing:

        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )

    return values  # type: ignore[return-value]


def scalar(
    cursor,
    query: str,
) -> int:

    cursor.execute(query)

    return int(
        cursor.fetchone()[0]
    )


def source_aggregates(
    path: Path,
) -> tuple[
    Decimal,
    int,
    Decimal,
    Decimal,
]:

    adjusted_close = Decimal(0)
    volume = 0
    dividend = Decimal(0)
    split_factor = Decimal(0)

    for chunk in pd.read_csv(
        path,
        usecols=AGGREGATE_COLUMNS,
        dtype=str,
        keep_default_na=False,
        chunksize=50_000,
    ):

        adjusted_close += sum(
            Decimal(value)
            for value in chunk[
                "adjusted_close"
            ]
        )

        volume += sum(
            int(value)
            for value in chunk[
                "volume"
            ]
        )

        dividend += sum(
            Decimal(value)
            for value in chunk[
                "dividend"
            ]
        )

        split_factor += sum(
            Decimal(value)
            for value in chunk[
                "split_factor"
            ]
        )

    return (
        adjusted_close,
        volume,
        dividend,
        split_factor,
    )


def database_aggregates(
    cursor,
    table: str,
) -> tuple[
    Decimal,
    int,
    Decimal,
    Decimal,
]:

    cursor.execute(
        f"""
        SELECT
            SUM(adjusted_close),
            SUM(volume),
            SUM(dividend),
            SUM(split_factor)
        FROM core.{table};
        """
    )

    row = cursor.fetchone()

    return (
        Decimal(row[0]),
        int(row[1]),
        Decimal(row[2]),
        Decimal(row[3]),
    )


def main() -> None:

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL MARKET-DATA "
        "INTEGRITY AUDIT"
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

            lines.append(
                f"PASS: {success}"
            )

            passed_checks += 1

        else:

            lines.append(
                f"FAIL: {failure}"
            )

            failures.append(failure)

    try:

        if (
            not BRIDGE.exists()
            or not BENCHMARKS.exists()
        ):

            raise FileNotFoundError(
                "One or both price source "
                "files are missing."
            )

        (
            server,
            database,
            username,
            password,
        ) = environment()

        connection = connect(
            server=server,
            database=database,
            uid=username,
            pwd=password,
            encrypt="yes",
            trust_server_certificate="no",
            timeout=90,
        )

        cursor = connection.cursor()

        lines += section(
            "1. CORE AND STAGING POPULATIONS"
        )

        for (
            table,
            expected,
        ) in EXPECTED_COUNTS.items():

            actual = scalar(
                cursor,
                "SELECT COUNT_BIG(*) "
                f"FROM core.{table};",
            )

            check(
                actual == expected,
                f"core.{table}: "
                f"{actual:,} / "
                f"{expected:,} rows.",
                f"core.{table}: "
                f"found {actual:,}; "
                f"expected {expected:,}.",
            )

        for table in EXPECTED_COUNTS:

            actual = scalar(
                cursor,
                "SELECT COUNT_BIG(*) "
                f"FROM staging.{table};",
            )

            check(
                actual == 0,
                f"staging.{table} is empty.",
                f"staging.{table} contains "
                f"{actual:,} rows.",
            )

        lines.append("")

        lines += section(
            "2. CONSTRAINT TRUST AND "
            "DECIMAL DEFINITIONS"
        )

        untrusted_foreign_keys = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM sys.foreign_keys AS fk
            JOIN sys.tables AS t
                ON t.object_id =
                    fk.parent_object_id
            JOIN sys.schemas AS s
                ON s.schema_id =
                    t.schema_id
            WHERE
                s.name = 'core'
                AND (
                    fk.is_disabled = 1
                    OR fk.is_not_trusted = 1
                );
            """,
        )

        check(
            untrusted_foreign_keys == 0,
            "All core foreign keys are "
            "enabled and trusted.",
            f"Found {untrusted_foreign_keys} "
            "disabled or untrusted "
            "foreign keys.",
        )

        untrusted_checks = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM sys.check_constraints AS cc
            JOIN sys.tables AS t
                ON t.object_id =
                    cc.parent_object_id
            JOIN sys.schemas AS s
                ON s.schema_id =
                    t.schema_id
            WHERE
                s.name = 'core'
                AND (
                    cc.is_disabled = 1
                    OR cc.is_not_trusted = 1
                );
            """,
        )

        check(
            untrusted_checks == 0,
            "All core check constraints are "
            "enabled and trusted.",
            f"Found {untrusted_checks} "
            "disabled or untrusted "
            "check constraints.",
        )

        valid_decimal_columns = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM sys.columns AS c
            JOIN sys.tables AS t
                ON t.object_id =
                    c.object_id
            JOIN sys.schemas AS s
                ON s.schema_id =
                    t.schema_id
            JOIN sys.types AS ty
                ON ty.user_type_id =
                    c.user_type_id
            WHERE
                s.name IN (
                    'core',
                    'staging'
                )
                AND t.name IN (
                    'daily_security_price',
                    'daily_benchmark_price'
                )
                AND c.name IN (
                    'open',
                    'high',
                    'low',
                    'close',
                    'adjusted_close',
                    'dividend',
                    'split_factor'
                )
                AND ty.name = 'decimal'
                AND c.precision = 38
                AND c.scale = 18;
            """,
        )

        check(
            valid_decimal_columns == 28,
            "All 28 market-value columns "
            "remain DECIMAL(38, 18).",
            f"Only {valid_decimal_columns} "
            "of 28 market-value columns "
            "have the required definition.",
        )

        lines.append("")

        lines += section(
            "3. MEMBERSHIP AND IDENTITY "
            "RECONCILIATION"
        )

        for (
            day,
            expected,
        ) in CHECKPOINTS.items():

            actual = scalar(
                cursor,
                f"""
                SELECT
                    COUNT_BIG(
                        DISTINCT security_key
                    )
                FROM core.index_membership
                WHERE
                    valid_from <= '{day}'
                    AND valid_to_exclusive >
                        '{day}';
                """,
            )

            check(
                actual == expected,
                f"{day} membership count: "
                f"{actual}.",
                f"{day} membership count is "
                f"{actual}; expected "
                f"{expected}.",
            )

        cursor.execute(
            """
            SELECT
                security_key
            FROM core.security_ticker_history
            GROUP BY
                security_key
            HAVING COUNT_BIG(*) > 1;
            """
        )

        multi_segment_keys = sorted(
            str(row[0])
            for row in cursor.fetchall()
        )

        check(
            multi_segment_keys == ["DAY"],
            "DAY is the only multi-segment "
            "security identity.",
            "Unexpected multi-segment "
            f"identities: {multi_segment_keys}.",
        )

        lines.append("")

        lines += section(
            "4. CONSTITUENT PRICE "
            "RECONCILIATION"
        )

        manifest_mismatches = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
                core.security_price_eligibility
                    AS e
            LEFT JOIN (
                SELECT
                    security_key,
                    project_ticker,
                    COUNT_BIG(*) AS
                        actual_rows,
                    MIN(price_date) AS
                        first_date,
                    MAX(price_date) AS
                        last_date
                FROM
                    core.daily_security_price
                GROUP BY
                    security_key,
                    project_ticker
            ) AS p
                ON p.security_key =
                    e.security_key
                AND p.project_ticker =
                    e.project_ticker
            WHERE
                p.security_key IS NULL
                OR p.actual_rows <>
                    e.bridge_rows
                OR p.first_date <>
                    e.first_bridge_date
                OR p.last_date <>
                    e.last_bridge_date;
            """,
        )

        check(
            manifest_mismatches == 0,
            "All constituent price segments "
            "reconcile to their manifests.",
            f"Found {manifest_mismatches} "
            "manifest reconciliation failures.",
        )

        outside_usable = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
                core.daily_security_price
                    AS p
            JOIN
                core.security_price_eligibility
                    AS e
                ON e.security_key =
                    p.security_key
                AND e.project_ticker =
                    p.project_ticker
            WHERE
                p.price_date <
                    e.usable_start
                OR p.price_date >=
                    e.usable_end_exclusive;
            """,
        )

        check(
            outside_usable == 0,
            "No constituent observations "
            "fall outside usable intervals.",
            f"Found {outside_usable:,} "
            "observations outside usable "
            "intervals.",
        )

        constituent_requests = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    security_key,
                    project_ticker
                FROM
                    core.daily_security_price
                GROUP BY
                    security_key,
                    project_ticker
            ) AS requests;
            """,
        )

        check(
            constituent_requests == 594,
            "Constituent history contains "
            "exactly 594 requests.",
            "Constituent history contains "
            f"{constituent_requests} requests.",
        )

        lines.append("")

        lines += section(
            "5. BENCHMARK RECONCILIATION"
        )

        complete_benchmarks = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM (
                SELECT
                    security_key,
                    project_ticker
                FROM
                    core.daily_benchmark_price
                GROUP BY
                    security_key,
                    project_ticker
                HAVING COUNT_BIG(*) = 1255
            ) AS complete_series;
            """,
        )

        check(
            complete_benchmarks == 2,
            "Both benchmark requests contain "
            "exactly 1,255 sessions.",
            f"Only {complete_benchmarks} "
            "benchmark requests contain "
            "1,255 sessions.",
        )

        cursor.execute(
            """
            SELECT
                series_type,
                COUNT_BIG(*)
            FROM core.benchmark_series
            GROUP BY series_type;
            """
        )

        benchmark_types = {
            str(row[0]): int(row[1])
            for row in cursor.fetchall()
        }

        check(
            benchmark_types == {
                "ETF": 1,
                "INDEX": 1,
            },
            "Benchmark definitions contain "
            "one ETF and one index.",
            "Unexpected benchmark "
            f"classifications: "
            f"{benchmark_types}.",
        )

        lines.append("")

        lines += section(
            "6. SOURCE-TO-SQL NUMERIC "
            "RECONCILIATION"
        )

        source_constituent = (
            source_aggregates(BRIDGE)
        )

        sql_constituent = (
            database_aggregates(
                cursor,
                "daily_security_price",
            )
        )

        check(
            source_constituent
            == sql_constituent,
            "Constituent adjusted-close, "
            "volume, dividend, and split "
            "aggregates exactly match "
            "the source.",
            "One or more constituent numeric "
            "aggregates differ from the source.",
        )

        source_benchmarks = (
            source_aggregates(BENCHMARKS)
        )

        sql_benchmarks = (
            database_aggregates(
                cursor,
                "daily_benchmark_price",
            )
        )

        check(
            source_benchmarks
            == sql_benchmarks,
            "Benchmark adjusted-close, "
            "volume, dividend, and split "
            "aggregates exactly match "
            "the source.",
            "One or more benchmark numeric "
            "aggregates differ from the source.",
        )

        lines.append("")

        lines += section(
            "7. FINAL QUALITY GATE"
        )

        if failures:

            lines.append(
                "AZURE_SQL_MARKET_DATA_"
                "INTEGRITY_AUDIT_FAILED"
            )

            lines.append(
                f"Passed checks: "
                f"{passed_checks}"
            )

            lines.append(
                f"Failed checks: "
                f"{len(failures)}"
            )

            for (
                number,
                failure,
            ) in enumerate(
                failures,
                start=1,
            ):

                lines.append(
                    f"{number}. {failure}"
                )

        else:

            lines += [
                "AZURE_SQL_MARKET_DATA_"
                "INTEGRITY_AUDIT_PASSED",
                f"Passed checks: "
                f"{passed_checks}",
                "Core security identities: 593",
                "Core ticker-history "
                "segments: 594",
                "Core membership intervals: 593",
                "Core constituent "
                "observations: 631,942",
                "Core benchmark "
                "observations: 2,510",
                "Total core daily "
                "observations: 634,452",
                "Staging rows remaining: 0",
                "Source-to-SQL numeric "
                "aggregate differences: 0",
                "NORMALIZED AZURE SQL "
                "MARKET-DATA QUALITY "
                "GATE COMPLETE.",
            ]

        cursor.close()

    except Exception as error:

        lines += [""]

        lines += section(
            "AUDIT EXECUTION FAILED"
        )

        lines += [
            type(error).__name__,
            str(error),
            "AZURE_SQL_MARKET_DATA_"
            "INTEGRITY_AUDIT_FAILED",
        ]

        failures.append(
            str(error)
        )

    finally:

        if connection is not None:

            try:

                connection.close()

            except Exception:

                pass

        report = (
            "\n".join(lines)
            + "\n"
        )

        REPORT.write_text(
            report,
            encoding="utf-8",
        )

        print(
            report,
            end="",
        )

        print(
            f"Report saved: {REPORT}"
        )

    if failures:

        raise SystemExit(1)


if __name__ == "__main__":

    main()