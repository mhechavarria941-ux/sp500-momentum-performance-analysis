from __future__ import annotations

import csv
import gzip
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, Iterator, TextIO

import pandas as pd
from dotenv import load_dotenv
from mssql_python import connect


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "interim"

REPORT = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_market_data_load.txt"
)

MEMBERSHIP = (
    DATA
    / "sp500_membership_intervals_2021_2025.csv"
)

TICKERS = (
    DATA
    / "sp500_ticker_history_2021_2025.csv"
)

BRIDGE = (
    DATA
    / "sp500_membership_price_bridge_2021_2025.csv.gz"
)

MANIFEST = (
    DATA
    / "sp500_membership_price_bridge_manifest.csv"
)

BENCHMARKS = (
    DATA
    / "sp500_benchmark_price_history_2021_2025.csv.gz"
)

BATCH_SIZE = 25_000
BULK_TIMEOUT = 900


HEADERS = {
    MEMBERSHIP: [
        "security_key",
        "company_name_reference",
        "valid_from",
        "left_censored",
        "entry_ticker",
        "entry_source_url",
        "valid_to_exclusive",
        "right_censored",
        "exit_ticker",
        "exit_source_url",
    ],
    TICKERS: [
        "security_key",
        "ticker",
        "ticker_valid_from",
        "left_censored",
        "ticker_valid_to_exclusive",
        "right_censored",
    ],
    BRIDGE: [
        "security_key",
        "project_ticker",
        "provider_symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend",
        "split_factor",
        "source",
        "membership_valid_from",
        "membership_valid_to_exclusive",
        "ticker_valid_from",
        "ticker_valid_to_exclusive",
        "effective_price_start",
        "effective_price_end_exclusive",
        "usable_start",
        "usable_end_exclusive",
    ],
    MANIFEST: [
        "security_key",
        "project_ticker",
        "membership_valid_from",
        "membership_valid_to_exclusive",
        "ticker_valid_from",
        "ticker_valid_to_exclusive",
        "effective_price_start",
        "effective_price_end_exclusive",
        "usable_start",
        "usable_end_exclusive",
        "standardized_rows",
        "bridge_rows",
        "rows_before_usable_window",
        "rows_after_usable_window",
        "first_bridge_date",
        "last_bridge_date",
    ],
    BENCHMARKS: [
        "security_key",
        "project_ticker",
        "provider_symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend",
        "split_factor",
        "source",
    ],
}


TABLE_COLUMNS = {
    "security": [
        "security_key",
        "company_name_reference",
    ],
    "security_ticker_history": [
        "security_key",
        "ticker",
        "ticker_valid_from",
        "ticker_valid_to_exclusive",
        "left_censored",
        "right_censored",
    ],
    "index_membership": [
        "index_code",
        "security_key",
        "valid_from",
        "valid_to_exclusive",
        "left_censored",
        "right_censored",
        "entry_ticker",
        "entry_source_url",
        "exit_ticker",
        "exit_source_url",
    ],
    "security_price_eligibility": [
        "security_key",
        "project_ticker",
        "effective_price_start",
        "effective_price_end_exclusive",
        "usable_start",
        "usable_end_exclusive",
        "standardized_rows",
        "bridge_rows",
        "rows_before_usable_window",
        "rows_after_usable_window",
        "first_bridge_date",
        "last_bridge_date",
    ],
    "daily_security_price": [
        "security_key",
        "project_ticker",
        "provider_symbol",
        "price_date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend",
        "split_factor",
        "source",
    ],
    "benchmark_series": [
        "security_key",
        "project_ticker",
        "provider_symbol",
        "benchmark_name",
        "series_type",
        "source",
    ],
    "daily_benchmark_price": [
        "security_key",
        "project_ticker",
        "provider_symbol",
        "price_date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend",
        "split_factor",
        "source",
    ],
}


EXPECTED = {
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

    return [
        rule,
        title,
        rule,
    ]


def open_text(
    path: Path,
) -> TextIO:

    if path.suffix.lower() == ".gz":

        return gzip.open(
            path,
            "rt",
            encoding="utf-8-sig",
            newline="",
        )

    return path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    )


def dictionaries(
    path: Path,
) -> Iterator[dict[str, str]]:

    with open_text(path) as handle:

        yield from csv.DictReader(handle)


def parsed_date(
    value: str,
) -> date:

    return date.fromisoformat(
        value.strip()
    )


def parsed_bool(
    value: str,
) -> int:

    value = value.strip().lower()

    if value == "true":

        return 1

    if value == "false":

        return 0

    raise ValueError(
        f"Invalid Boolean value: {value!r}"
    )


def nullable(
    value: str | None,
) -> str | None:

    if (
        value is None
        or not value.strip()
    ):

        return None

    return value.strip()


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


def validate_headers(
    lines: list[str],
) -> None:

    for path, expected in HEADERS.items():

        if not path.exists():

            raise FileNotFoundError(
                "Required source not found: "
                f"{path}"
            )

        with open_text(path) as handle:

            actual = next(
                csv.reader(handle),
                None,
            )

        if actual != expected:

            raise RuntimeError(
                f"Unexpected columns in "
                f"{path.name}.\n"
                f"Expected: {expected}\n"
                f"Actual: {actual}"
            )

        lines.append(
            f"PASS: {path.name} has "
            "the expected columns."
        )


def security_rows() -> list[tuple]:

    values = {
        (
            row["security_key"].strip(),
            row[
                "company_name_reference"
            ].strip(),
        )
        for row in dictionaries(
            MEMBERSHIP
        )
    }

    security_keys = {
        row[0]
        for row in values
    }

    if (
        len(values) != 593
        or len(security_keys) != 593
    ):

        raise RuntimeError(
            "Security identity derivation "
            "did not produce 593 keys."
        )

    return sorted(values)


def ticker_rows() -> Iterator[tuple]:

    for row in dictionaries(TICKERS):

        yield (
            row["security_key"].strip(),
            row["ticker"].strip(),
            parsed_date(
                row["ticker_valid_from"]
            ),
            parsed_date(
                row[
                    "ticker_valid_to_exclusive"
                ]
            ),
            parsed_bool(
                row["left_censored"]
            ),
            parsed_bool(
                row["right_censored"]
            ),
        )


def membership_rows() -> Iterator[tuple]:

    for row in dictionaries(
        MEMBERSHIP
    ):

        yield (
            "SP500",
            row["security_key"].strip(),
            parsed_date(
                row["valid_from"]
            ),
            parsed_date(
                row["valid_to_exclusive"]
            ),
            parsed_bool(
                row["left_censored"]
            ),
            parsed_bool(
                row["right_censored"]
            ),
            row["entry_ticker"].strip(),
            nullable(
                row["entry_source_url"]
            ),
            nullable(
                row["exit_ticker"]
            ),
            nullable(
                row["exit_source_url"]
            ),
        )


def eligibility_rows() -> Iterator[tuple]:

    for row in dictionaries(
        MANIFEST
    ):

        yield (
            row["security_key"].strip(),
            row["project_ticker"].strip(),
            parsed_date(
                row[
                    "effective_price_start"
                ]
            ),
            parsed_date(
                row[
                    "effective_price_end_exclusive"
                ]
            ),
            parsed_date(
                row["usable_start"]
            ),
            parsed_date(
                row["usable_end_exclusive"]
            ),
            int(
                row["standardized_rows"]
            ),
            int(
                row["bridge_rows"]
            ),
            int(
                row[
                    "rows_before_usable_window"
                ]
            ),
            int(
                row[
                    "rows_after_usable_window"
                ]
            ),
            parsed_date(
                row["first_bridge_date"]
            ),
            parsed_date(
                row["last_bridge_date"]
            ),
        )


PRICE_SOURCE_COLUMNS = [
    "security_key",
    "project_ticker",
    "provider_symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend",
    "split_factor",
    "source",
]


def price_rows(
    path: Path,
) -> Iterator[tuple]:

    for chunk in pd.read_csv(
        path,
        usecols=PRICE_SOURCE_COLUMNS,
        dtype=str,
        keep_default_na=False,
        chunksize=50_000,
    ):

        selected = chunk[
            PRICE_SOURCE_COLUMNS
        ]

        for row in selected.itertuples(
            index=False,
            name=None,
        ):

            yield (
                row[0].strip(),
                row[1].strip(),
                row[2].strip(),
                parsed_date(row[3]),
                Decimal(row[4]),
                Decimal(row[5]),
                Decimal(row[6]),
                Decimal(row[7]),
                Decimal(row[8]),
                int(row[9]),
                Decimal(row[10]),
                Decimal(row[11]),
                row[12].strip(),
            )


def benchmark_series_rows() -> list[tuple]:

    metadata = pd.read_csv(
        BENCHMARKS,
        usecols=[
            "security_key",
            "project_ticker",
            "provider_symbol",
            "source",
        ],
        dtype=str,
    ).drop_duplicates()

    if len(metadata) != 2:

        raise RuntimeError(
            "Expected exactly two "
            "benchmark metadata rows."
        )

    output = []

    spy_count = 0
    index_count = 0

    for row in metadata.itertuples(
        index=False,
    ):

        is_spy = (
            row.project_ticker.upper()
            == "SPY"
            or row.provider_symbol.upper()
            == "SPY"
        )

        if is_spy:

            name = (
                "SPDR S&P 500 ETF Trust"
            )

            kind = "ETF"

            spy_count += 1

        else:

            name = "S&P 500 Index"

            kind = "INDEX"

            index_count += 1

        output.append(
            (
                row.security_key,
                row.project_ticker,
                row.provider_symbol,
                name,
                kind,
                row.source,
            )
        )

    if (
        spy_count != 1
        or index_count != 1
    ):

        raise RuntimeError(
            "Expected one SPY ETF and one "
            "S&P 500 index request."
        )

    return sorted(output)


def scalar(
    cursor,
    query: str,
) -> int:

    cursor.execute(query)

    return int(
        cursor.fetchone()[0]
    )


def row_count(
    cursor,
    schema: str,
    table: str,
) -> int:

    return scalar(
        cursor,
        "SELECT COUNT_BIG(*) "
        f"FROM {schema}.{table};",
    )


def require_empty(
    cursor,
) -> None:

    nonempty = []

    for schema in (
        "staging",
        "core",
    ):

        for table in EXPECTED:

            if row_count(
                cursor,
                schema,
                table,
            ):

                nonempty.append(
                    f"{schema}.{table}"
                )

    if nonempty:

        raise RuntimeError(
            "Load targets are not empty: "
            + ", ".join(nonempty)
        )


def bulk_load(
    cursor,
    table: str,
    rows: Iterable[tuple],
    lines: list[str],
) -> None:

    result = cursor.bulkcopy(
        f"staging.{table}",
        rows,
        batch_size=BATCH_SIZE,
        timeout=BULK_TIMEOUT,
        column_mappings=(
            TABLE_COLUMNS[table]
        ),
        table_lock=True,
        keep_nulls=True,
        use_internal_transaction=True,
    )

    lines.append(
        f"Loaded staging.{table}; "
        "driver-reported rows: "
        f"{result['rows_copied']:,}."
    )


def validate_counts(
    cursor,
    schema: str,
    lines: list[str],
) -> None:

    for table, expected in (
        EXPECTED.items()
    ):

        actual = row_count(
            cursor,
            schema,
            table,
        )

        if actual != expected:

            raise RuntimeError(
                f"{schema}.{table}: "
                f"found {actual:,}; "
                f"expected {expected:,}."
            )

        lines.append(
            f"PASS: {schema}.{table}: "
            f"{actual:,} / "
            f"{expected:,} rows."
        )


def quoted(
    column: str,
) -> str:

    if column in {
        "open",
        "close",
    }:

        return f"[{column}]"

    return column


def promote(
    cursor,
) -> None:

    for table, columns in (
        TABLE_COLUMNS.items()
    ):

        names = ", ".join(
            quoted(column)
            for column in columns
        )

        cursor.execute(
            f"INSERT INTO core.{table} "
            f"({names}) "
            f"SELECT {names} "
            f"FROM staging.{table};"
        )


def validate_relationships(
    cursor,
    lines: list[str],
) -> None:

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
                COUNT_BIG(*) AS rows_found,
                MIN(price_date) AS first_date,
                MAX(price_date) AS last_date
            FROM core.daily_security_price
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
            OR p.rows_found <>
                e.bridge_rows
            OR p.first_date <>
                e.first_bridge_date
            OR p.last_date <>
                e.last_bridge_date;
        """,
    )

    if manifest_mismatches:

        raise RuntimeError(
            "Manifest reconciliation failed "
            f"for {manifest_mismatches} "
            "segments."
        )

    lines.append(
        "PASS: All 594 constituent price "
        "segments reconcile to their "
        "manifests."
    )

    outside = scalar(
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

    if outside:

        raise RuntimeError(
            f"Found {outside:,} prices "
            "outside usable intervals."
        )

    lines.append(
        "PASS: No constituent prices fall "
        "outside usable intervals."
    )

    requests = scalar(
        cursor,
        """
        SELECT COUNT_BIG(*)
        FROM (
            SELECT
                security_key,
                project_ticker
            FROM core.daily_security_price
            GROUP BY
                security_key,
                project_ticker
        ) AS requests;
        """,
    )

    if requests != 594:

        raise RuntimeError(
            f"Found {requests} constituent "
            "requests; expected 594."
        )

    lines.append(
        "PASS: Constituent prices contain "
        "exactly 594 requests."
    )

    complete_benchmarks = scalar(
        cursor,
        """
        SELECT COUNT_BIG(*)
        FROM (
            SELECT
                security_key,
                project_ticker
            FROM core.daily_benchmark_price
            GROUP BY
                security_key,
                project_ticker
            HAVING COUNT_BIG(*) = 1255
        ) AS complete_benchmarks;
        """,
    )

    if complete_benchmarks != 2:

        raise RuntimeError(
            "Both benchmark requests must "
            "contain 1,255 rows."
        )

    lines.append(
        "PASS: Both benchmark requests "
        "contain exactly 1,255 sessions."
    )

    checkpoint = """
        SELECT
            COUNT_BIG(
                DISTINCT security_key
            )
        FROM core.index_membership
        WHERE
            valid_from <= '{day}'
            AND valid_to_exclusive >
                '{day}';
    """

    start_count = scalar(
        cursor,
        checkpoint.format(
            day="2021-01-01"
        ),
    )

    end_count = scalar(
        cursor,
        checkpoint.format(
            day="2025-12-31"
        ),
    )

    if (
        start_count,
        end_count,
    ) != (
        505,
        503,
    ):

        raise RuntimeError(
            "Membership checkpoints failed: "
            f"{start_count} and {end_count}."
        )

    lines.append(
        "PASS: SQL membership checkpoints "
        "reproduce 505 and 503 securities."
    )


def clear_staging(
    connection,
) -> None:

    cursor = connection.cursor()

    tables = reversed(
        list(EXPECTED)
    )

    for table in tables:

        cursor.execute(
            "TRUNCATE TABLE "
            f"staging.{table};"
        )

    connection.commit()

    cursor.close()


def main() -> None:

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL CONTROLLED "
        "MARKET-DATA LOAD"
    )

    lines += [
        "Credentials included in report: NO",
        "Load strategy: staging, "
        "reconciliation, transactional "
        "promotion",
        "",
    ]

    connection = None

    staging_started = False
    core_committed = False
    passed = False

    try:

        lines += section(
            "1. SOURCE PREFLIGHT"
        )

        validate_headers(lines)

        securities = security_rows()

        benchmark_series = (
            benchmark_series_rows()
        )

        lines += [
            "PASS: Derived reference rows "
            "are valid.",
            "",
        ]

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
            "2. EMPTY-TARGET CONTROL"
        )

        require_empty(cursor)

        connection.commit()

        lines += [
            "PASS: All staging and core "
            "load targets are empty.",
            "",
        ]

        lines += section(
            "3. BULK LOAD STAGING"
        )

        staging_started = True

        loads: list[
            tuple[
                str,
                Callable[
                    [],
                    Iterable[tuple],
                ],
            ]
        ] = [
            (
                "security",
                lambda: securities,
            ),
            (
                "security_ticker_history",
                ticker_rows,
            ),
            (
                "index_membership",
                membership_rows,
            ),
            (
                "security_price_eligibility",
                eligibility_rows,
            ),
            (
                "daily_security_price",
                lambda: price_rows(
                    BRIDGE
                ),
            ),
            (
                "benchmark_series",
                lambda: benchmark_series,
            ),
            (
                "daily_benchmark_price",
                lambda: price_rows(
                    BENCHMARKS
                ),
            ),
        ]

        for (
            table,
            rows_factory,
        ) in loads:

            bulk_load(
                cursor,
                table,
                rows_factory(),
                lines,
            )

        connection.commit()

        lines.append("")

        lines += section(
            "4. STAGING RECONCILIATION"
        )

        validate_counts(
            cursor,
            "staging",
            lines,
        )

        connection.commit()

        lines.append("")

        lines += section(
            "5. TRANSACTIONAL "
            "CORE PROMOTION"
        )

        cursor.execute(
            "SET XACT_ABORT ON;"
        )

        promote(cursor)

        validate_counts(
            cursor,
            "core",
            lines,
        )

        validate_relationships(
            cursor,
            lines,
        )

        connection.commit()

        core_committed = True

        lines += [
            "PASS: All seven core inserts "
            "committed as one transaction.",
            "",
        ]

        lines += section(
            "6. STAGING CLEANUP"
        )

        clear_staging(connection)

        staging_started = False

        for table in EXPECTED:

            remaining = row_count(
                cursor,
                "staging",
                table,
            )

            if remaining:

                raise RuntimeError(
                    f"staging.{table} "
                    "was not cleared."
                )

        connection.commit()

        lines += [
            "PASS: All staging tables were "
            "cleared after promotion.",
            "",
        ]

        lines += section(
            "7. FINAL QUALITY GATE"
        )

        lines += [
            "AZURE_SQL_CONTROLLED_"
            "MARKET_DATA_LOAD_PASSED",
            "Security identities loaded: 593",
            "Ticker-history segments "
            "loaded: 594",
            "Membership intervals loaded: 593",
            "Price-eligibility manifests "
            "loaded: 594",
            "Constituent price observations "
            "loaded: 631,942",
            "Benchmark series loaded: 2",
            "Benchmark price observations "
            "loaded: 2,510",
            "Total daily price observations "
            "loaded: 634,452",
            "Staging rows remaining: 0",
            "Normalized Azure SQL market-data "
            "load is complete.",
        ]

        passed = True

        cursor.close()

    except Exception as error:

        if connection is not None:

            try:

                connection.rollback()

            except Exception:

                pass

        cleanup_status = (
            "Not required."
        )

        if (
            connection is not None
            and staging_started
        ):

            try:

                clear_staging(
                    connection
                )

                cleanup_status = (
                    "Completed; staging tables "
                    "were cleared."
                )

            except Exception as cleanup_error:

                cleanup_status = (
                    f"FAILED: {cleanup_error}"
                )

        lines += [""]

        lines += section(
            "CONTROLLED LOAD FAILED"
        )

        lines += [
            type(error).__name__,
            str(error),
            "Core promotion committed: "
            f"{core_committed}",
            "Failure cleanup: "
            f"{cleanup_status}",
            "AZURE_SQL_CONTROLLED_"
            "MARKET_DATA_LOAD_FAILED",
        ]

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

    if not passed:

        raise SystemExit(1)


if __name__ == "__main__":

    main()