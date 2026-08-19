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
    / "002_expand_market_data_decimal_scale.sql"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_decimal_scale_migration.txt"
)


TABLES = (
    (
        "core",
        "daily_security_price",
    ),
    (
        "core",
        "daily_benchmark_price",
    ),
    (
        "staging",
        "daily_security_price",
    ),
    (
        "staging",
        "daily_benchmark_price",
    ),
)


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


def main() -> None:

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL DECIMAL-SCALE MIGRATION"
    )

    lines += [
        "Credentials included in report: NO",
        "Migration: "
        f"{SQL_PATH.relative_to(ROOT)}",
        "Target decimal definition: "
        "DECIMAL(38, 18)",
        "",
    ]

    connection = None
    passed = False

    try:

        if not SQL_PATH.exists():

            raise FileNotFoundError(
                f"Migration not found: {SQL_PATH}"
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
            "1. EMPTY-TABLE CONTROL"
        )

        for (
            schema,
            table,
        ) in TABLES:

            cursor.execute(
                "SELECT COUNT_BIG(*) "
                f"FROM {schema}.{table};"
            )

            count = int(
                cursor.fetchone()[0]
            )

            lines.append(
                f"{schema}.{table}: "
                f"{count:,} rows"
            )

            if count != 0:

                raise RuntimeError(
                    f"{schema}.{table} must "
                    "be empty before this "
                    "migration."
                )

        connection.commit()

        lines += [
            "PASS: All four price tables "
            "are empty.",
            "",
        ]

        lines += section(
            "2. APPLY MIGRATION"
        )

        sql_text = SQL_PATH.read_text(
            encoding="utf-8"
        )

        cursor.execute(sql_text)

        connection.commit()

        lines += [
            "PASS: Decimal-scale migration "
            "executed and committed.",
            "",
        ]

        lines += section(
            "3. VERIFY DECIMAL DEFINITIONS"
        )

        cursor.execute(
            """
            SELECT
                s.name,
                t.name,
                c.name,
                ty.name,
                c.precision,
                c.scale
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
            ORDER BY
                s.name,
                t.name,
                c.column_id;
            """
        )

        definitions = (
            cursor.fetchall()
        )

        if len(definitions) != 28:

            raise RuntimeError(
                f"Found {len(definitions)} "
                "decimal definitions; "
                "expected 28."
            )

        invalid = [
            row
            for row in definitions
            if (
                str(row[3]).lower()
                != "decimal"
                or int(row[4]) != 38
                or int(row[5]) != 18
            )
        ]

        if invalid:

            raise RuntimeError(
                "One or more price columns "
                "remain at the wrong scale."
            )

        lines.append(
            "PASS: All 28 price/action "
            "columns are DECIMAL(38, 18)."
        )

        cursor.execute(
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
                AND t.name IN (
                    'daily_security_price',
                    'daily_benchmark_price'
                )
                AND cc.name IN (
                    'CK_daily_security_price_positive',
                    'CK_daily_security_price_high',
                    'CK_daily_security_price_low',
                    'CK_daily_security_price_actions',
                    'CK_daily_benchmark_price_positive',
                    'CK_daily_benchmark_price_high',
                    'CK_daily_benchmark_price_low',
                    'CK_daily_benchmark_price_actions'
                );
            """
        )

        check_count = int(
            cursor.fetchone()[0]
        )

        if check_count != 8:

            raise RuntimeError(
                f"Found {check_count} price "
                "checks; expected 8."
            )

        lines.append(
            "PASS: All eight price "
            "integrity checks are present."
        )

        cursor.execute(
            """
            SELECT COUNT_BIG(*)
            FROM sys.indexes
            WHERE
                object_id = OBJECT_ID(
                    'core.daily_security_price'
                )
                AND name =
                    'IX_daily_security_price_security_date';
            """
        )

        index_count = int(
            cursor.fetchone()[0]
        )

        if index_count != 1:

            raise RuntimeError(
                "The daily-security "
                "supporting index is missing."
            )

        lines.append(
            "PASS: The daily-security "
            "supporting index is present."
        )

        lines.append("")

        lines += section(
            "4. FINAL QUALITY GATE"
        )

        lines += [
            "AZURE_SQL_DECIMAL_SCALE_"
            "MIGRATION_PASSED",
            "Tables migrated: 4",
            "Decimal columns verified: 28",
            "Decimal precision: 38",
            "Decimal scale: 18",
            "Data rows modified: 0",
            "Azure SQL is ready for a clean "
            "controlled-load retry.",
        ]

        passed = True

        cursor.close()

    except Exception as error:

        if connection is not None:

            try:

                connection.rollback()

            except Exception:

                pass

        lines += [""]

        lines += section(
            "MIGRATION FAILED"
        )

        lines += [
            type(error).__name__,
            str(error),
            "AZURE_SQL_DECIMAL_SCALE_"
            "MIGRATION_FAILED",
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

    if not passed:

        raise SystemExit(1)


if __name__ == "__main__":

    main()