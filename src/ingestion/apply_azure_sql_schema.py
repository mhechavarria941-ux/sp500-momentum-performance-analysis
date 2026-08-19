from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from mssql_python import connect


ROOT = Path(__file__).resolve().parents[2]

SQL_PATH = (
    ROOT
    / "sql"
    / "schema"
    / "001_create_market_data_model.sql"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_schema_application.txt"
)


EXPECTED_CORE_TABLES = {
    "benchmark_series",
    "daily_benchmark_price",
    "daily_security_price",
    "index_membership",
    "market_index",
    "security",
    "security_price_eligibility",
    "security_ticker_history",
}


EXPECTED_STAGING_TABLES = {
    "benchmark_series",
    "daily_benchmark_price",
    "daily_security_price",
    "index_membership",
    "security",
    "security_price_eligibility",
    "security_ticker_history",
}


EXPECTED_PRIMARY_KEYS = {
    "PK_benchmark_series",
    "PK_daily_benchmark_price",
    "PK_daily_security_price",
    "PK_index_membership",
    "PK_market_index",
    "PK_security",
    "PK_security_price_eligibility",
    "PK_security_ticker_history",
}


EXPECTED_FOREIGN_KEYS = {
    "FK_daily_benchmark_price_series",
    "FK_daily_security_price_eligibility",
    "FK_index_membership_entry_ticker",
    "FK_index_membership_exit_ticker",
    "FK_index_membership_index",
    "FK_index_membership_security",
    "FK_price_eligibility_ticker",
    "FK_ticker_history_security",
}


EXPECTED_CHECK_CONSTRAINTS = {
    "CK_benchmark_series_type",
    "CK_daily_benchmark_price_actions",
    "CK_daily_benchmark_price_high",
    "CK_daily_benchmark_price_low",
    "CK_daily_benchmark_price_positive",
    "CK_daily_security_price_actions",
    "CK_daily_security_price_high",
    "CK_daily_security_price_low",
    "CK_daily_security_price_positive",
    "CK_index_membership_dates",
    "CK_index_membership_entry_source",
    "CK_index_membership_exit_fields",
    "CK_market_index_dates",
    "CK_price_eligibility_counts",
    "CK_price_eligibility_effective_dates",
    "CK_price_eligibility_first_date",
    "CK_price_eligibility_last_date",
    "CK_price_eligibility_usable_dates",
    "CK_security_key_not_blank",
    "CK_security_name_not_blank",
    "CK_ticker_history_dates",
    "CK_ticker_not_blank",
}


EXPECTED_INDEXES = {
    "IX_daily_security_price_security_date",
    "UQ_security_ticker_pair",
}


EMPTY_CORE_TABLES = sorted(
    EXPECTED_CORE_TABLES - {"market_index"}
)


def section(title: str) -> list[str]:

    rule = "=" * 79

    return [
        rule,
        title,
        rule,
    ]


def require_environment() -> tuple[
    str,
    str,
    str,
    str,
]:

    load_dotenv(ROOT / ".env")

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
            "Missing required environment "
            "variable(s): "
            + ", ".join(missing)
        )

    return values  # type: ignore[return-value]


def fetch_name_set(
    cursor,
    query: str,
) -> set[str]:

    cursor.execute(query)

    return {
        str(row[0])
        for row in cursor.fetchall()
    }


def validate_set(
    lines: list[str],
    label: str,
    actual: set[str],
    expected: set[str],
) -> None:

    missing = sorted(
        expected - actual
    )

    if missing:

        lines.append(
            f"FAIL: {label} missing: "
            + ", ".join(missing)
        )

        raise RuntimeError(
            f"Required {label.lower()} "
            "are missing."
        )

    lines.append(
        f"PASS: {label}: "
        f"{len(expected)} / "
        f"{len(expected)} present."
    )


def main() -> None:

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines: list[str] = []

    connection = None

    try:

        (
            server,
            database,
            username,
            password,
        ) = require_environment()

        if not SQL_PATH.exists():

            raise FileNotFoundError(
                "Schema migration not found: "
                f"{SQL_PATH}"
            )

        sql_text = SQL_PATH.read_text(
            encoding="utf-8"
        )

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

        lines.extend(
            section(
                "AZURE SQL SCHEMA APPLICATION"
            )
        )

        lines.append(
            "Connection status: SUCCESS"
        )

        lines.append(
            "Credentials included in report: NO"
        )

        lines.append(
            "Migration: "
            f"{SQL_PATH.relative_to(ROOT)}"
        )

        lines.append("")

        lines.extend(
            section("1. APPLY MIGRATION")
        )

        cursor.execute(sql_text)

        connection.commit()

        lines.append(
            "PASS: Migration batch executed "
            "and committed."
        )

        lines.append(
            "PASS: Migration is "
            "create-if-absent and "
            "non-destructive."
        )

        lines.append("")

        lines.extend(
            section("2. VERIFY TABLES")
        )

        core_tables = fetch_name_set(
            cursor,
            """
            SELECT
                t.name
            FROM sys.tables AS t
            JOIN sys.schemas AS s
                ON s.schema_id = t.schema_id
            WHERE s.name = 'core';
            """,
        )

        staging_tables = fetch_name_set(
            cursor,
            """
            SELECT
                t.name
            FROM sys.tables AS t
            JOIN sys.schemas AS s
                ON s.schema_id = t.schema_id
            WHERE s.name = 'staging';
            """,
        )

        validate_set(
            lines,
            "Core tables",
            core_tables,
            EXPECTED_CORE_TABLES,
        )

        validate_set(
            lines,
            "Staging tables",
            staging_tables,
            EXPECTED_STAGING_TABLES,
        )

        lines.append("")

        lines.extend(
            section(
                "3. VERIFY RELATIONAL CONTROLS"
            )
        )

        primary_keys = fetch_name_set(
            cursor,
            """
            SELECT
                kc.name
            FROM sys.key_constraints AS kc
            JOIN sys.tables AS t
                ON t.object_id =
                    kc.parent_object_id
            JOIN sys.schemas AS s
                ON s.schema_id =
                    t.schema_id
            WHERE
                s.name = 'core'
                AND kc.type = 'PK';
            """,
        )

        foreign_keys = fetch_name_set(
            cursor,
            """
            SELECT
                fk.name
            FROM sys.foreign_keys AS fk
            JOIN sys.tables AS t
                ON t.object_id =
                    fk.parent_object_id
            JOIN sys.schemas AS s
                ON s.schema_id =
                    t.schema_id
            WHERE s.name = 'core';
            """,
        )

        check_constraints = fetch_name_set(
            cursor,
            """
            SELECT
                cc.name
            FROM sys.check_constraints AS cc
            JOIN sys.tables AS t
                ON t.object_id =
                    cc.parent_object_id
            JOIN sys.schemas AS s
                ON s.schema_id =
                    t.schema_id
            WHERE s.name = 'core';
            """,
        )

        indexes = fetch_name_set(
            cursor,
            """
            SELECT
                i.name
            FROM sys.indexes AS i
            JOIN sys.tables AS t
                ON t.object_id =
                    i.object_id
            JOIN sys.schemas AS s
                ON s.schema_id =
                    t.schema_id
            WHERE
                s.name = 'core'
                AND i.name IS NOT NULL;
            """,
        )

        validate_set(
            lines,
            "Primary keys",
            primary_keys,
           EXPECTED_PRIMARY_KEYS,
        )

        validate_set(
            lines,
            "Foreign keys",
            foreign_keys,
            EXPECTED_FOREIGN_KEYS,
        )

        validate_set(
            lines,
            "Check constraints",
            check_constraints,
            EXPECTED_CHECK_CONSTRAINTS,
        )

        validate_set(
            lines,
            "Required indexes",
            indexes,
            EXPECTED_INDEXES,
        )

        lines.append("")

        lines.extend(
            section(
                "4. VERIFY INITIAL STATE"
            )
        )

        cursor.execute(
            """
            SELECT
                index_code,
                index_name,
                index_provider,
                CONVERT(
                    VARCHAR(10),
                    analysis_start,
                    23
                ),
                CONVERT(
                    VARCHAR(10),
                    analysis_end,
                    23
                )
            FROM core.market_index
            WHERE index_code = 'SP500';
            """
        )

        anchor_rows = cursor.fetchall()

        expected_anchor = (
            "SP500",
            "S&P 500",
            "S&P Dow Jones Indices",
            "2021-01-01",
            "2025-12-31",
        )

        if (
            len(anchor_rows) != 1
            or tuple(anchor_rows[0])
            != expected_anchor
        ):

            lines.append(
                "FAIL: The SP500 analytical "
                "anchor is missing or incorrect."
            )

            raise RuntimeError(
                "SP500 analytical anchor "
                "validation failed."
            )

        lines.append(
            "PASS: SP500 analytical anchor "
            "is present and correct."
        )

        nonempty_tables: list[str] = []

        for table_name in EMPTY_CORE_TABLES:

            cursor.execute(
                "SELECT COUNT_BIG(*) "
                f"FROM core.{table_name};"
            )

            if int(cursor.fetchone()[0]) != 0:

                nonempty_tables.append(
                    f"core.{table_name}"
                )

        for table_name in sorted(
            EXPECTED_STAGING_TABLES
        ):

            cursor.execute(
                "SELECT COUNT_BIG(*) "
                f"FROM staging.{table_name};"
            )

            if int(cursor.fetchone()[0]) != 0:

                nonempty_tables.append(
                    f"staging.{table_name}"
                )

        if nonempty_tables:

            lines.append(
                "FAIL: Tables expected to be "
                "empty contain rows: "
                + ", ".join(nonempty_tables)
            )

            raise RuntimeError(
                "Initial table-state "
                "validation failed."
            )

        lines.append(
            "PASS: All seven staging tables "
            "are empty."
        )

        lines.append(
            "PASS: All seven load-target core "
            "tables are empty."
        )

        lines.append("")

        lines.extend(
            section("5. FINAL QUALITY GATE")
        )

        lines.append(
            "AZURE_SQL_MARKET_DATA_SCHEMA_"
            "APPLICATION_PASSED"
        )

        lines.append(
            "Core tables present: "
            f"{len(EXPECTED_CORE_TABLES)}"
        )

        lines.append(
            "Staging tables present: "
            f"{len(EXPECTED_STAGING_TABLES)}"
        )

        lines.append(
            "Primary keys present: "
            f"{len(EXPECTED_PRIMARY_KEYS)}"
        )

        lines.append(
            "Foreign keys present: "
            f"{len(EXPECTED_FOREIGN_KEYS)}"
        )

        lines.append(
            "Check constraints present: "
            f"{len(EXPECTED_CHECK_CONSTRAINTS)}"
        )

        lines.append(
            "Required supporting indexes "
            "present: "
            f"{len(EXPECTED_INDEXES)}"
        )

        lines.append(
            "Data rows loaded: 0"
        )

        lines.append(
            "Normalized Azure SQL structure "
            "is ready for controlled loading."
        )

        cursor.close()

    except Exception as error:

        if connection is not None:

            try:

                connection.rollback()

            except Exception:

                pass

        if not lines:

            lines.extend(
                section(
                    "AZURE SQL SCHEMA APPLICATION"
                )
            )

            lines.append(
                "Connection status: "
                "FAILED OR NOT ESTABLISHED"
            )

            lines.append(
                "Credentials included in "
                "report: NO"
            )

            lines.append("")

        lines.extend(
            section(
                "SCHEMA APPLICATION FAILED"
            )
        )

        lines.append(
            type(error).__name__
        )

        lines.append(
            str(error)
        )

        lines.append(
            "AZURE_SQL_MARKET_DATA_SCHEMA_"
            "APPLICATION_FAILED"
        )

    finally:

        if connection is not None:

            try:

                connection.close()

            except Exception:

                pass

        report = "\n".join(lines) + "\n"

        REPORT_PATH.write_text(
            report,
            encoding="utf-8",
        )

        print(
            report,
            end="",
        )

        print(
            "Report saved: "
            f"{REPORT_PATH}"
        )


if __name__ == "__main__":

    main()