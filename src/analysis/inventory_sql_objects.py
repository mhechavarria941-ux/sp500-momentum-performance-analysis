from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-28-v1-research-sql-object-inventory"
ROOT = Path(__file__).resolve().parents[2]

CSV_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_research_object_inventory.csv"
)
TXT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_research_object_inventory.txt"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
SCHEMAS = (
    "raw",
    "staging",
    "core",
    "analytics",
    "ref",
    "research",
    "results",
    "audit",
    "bi",
)

KEYWORDS = (
    "momentum",
    "forward",
    "portfolio",
    "sector",
    "gics",
    "attention",
    "h3",
    "intraday",
    "spy",
    "sweep",
    "liquidity",
    "result",
    "hypothesis",
    "variable",
    "stat",
)


def environment() -> tuple[str, str, str, str]:
    load_dotenv(ROOT / ".env")
    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )
    values = tuple(os.getenv(name) for name in names)
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        raise RuntimeError(
            "Missing Azure SQL environment variables: "
            + ", ".join(missing)
        )
    return values  # type: ignore[return-value]


def odbc_escape(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def connect_with_retry(server, database, username, password):
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
    for attempt in range(1, 6):
        try:
            c = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            c.timeout = 120
            print(f"ODBC connection established on attempt {attempt} / 5.")
            return c
        except pyodbc.Error:
            if attempt == 5:
                raise
            time.sleep(15)
    raise RuntimeError("Connection retry loop ended unexpectedly.")


def fetch_df(cursor, sql, params=()):
    cursor.execute(sql, params)
    cols = [x[0] for x in cursor.description]
    return pd.DataFrame.from_records(cursor.fetchall(), columns=cols)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    server, database, username, password = environment()
    connection = connect_with_retry(server, database, username, password)

    try:
        cursor = connection.cursor()

        placeholders = ",".join("?" for _ in SCHEMAS)
        catalog = fetch_df(
            cursor,
            f"""
            SELECT
                s.name AS schema_name,
                o.name AS object_name,
                o.type_desc AS object_type,
                c.column_id,
                c.name AS column_name,
                ty.name AS data_type,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable
            FROM sys.objects AS o
            JOIN sys.schemas AS s
              ON s.schema_id = o.schema_id
            JOIN sys.columns AS c
              ON c.object_id = o.object_id
            JOIN sys.types AS ty
              ON ty.user_type_id = c.user_type_id
            WHERE
                o.type IN ('U','V')
                AND s.name IN ({placeholders})
            ORDER BY
                s.name,
                o.name,
                c.column_id;
            """,
            SCHEMAS,
        )

        object_rows = fetch_df(
            cursor,
            f"""
            SELECT
                s.name AS schema_name,
                o.name AS object_name,
                o.type_desc AS object_type,
                CASE
                    WHEN o.type = 'U' THEN
                        COALESCE(
                            (
                                SELECT SUM(ps.row_count)
                                FROM sys.dm_db_partition_stats AS ps
                                WHERE ps.object_id = o.object_id
                                  AND ps.index_id IN (0,1)
                            ),
                            0
                        )
                    ELSE NULL
                END AS approximate_rows
            FROM sys.objects AS o
            JOIN sys.schemas AS s
              ON s.schema_id = o.schema_id
            WHERE
                o.type IN ('U','V')
                AND s.name IN ({placeholders})
            ORDER BY s.name, o.name;
            """,
            SCHEMAS,
        )

        lower_names = (
            object_rows["object_name"]
            .astype(str)
            .str.lower()
        )
        relevant_mask = pd.Series(False, index=object_rows.index)
        for keyword in KEYWORDS:
            relevant_mask |= lower_names.str.contains(
                keyword,
                regex=False,
            )
        relevant = object_rows[relevant_mask].copy()

        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        catalog.to_csv(CSV_PATH, index=False)

        lines = [
            f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
            "=" * 124,
            "AZURE SQL RESEARCH OBJECT INVENTORY",
            "=" * 124,
            f"Database: {database}",
            f"Catalog column rows: {len(catalog):,}",
            f"Tables/views: {len(object_rows):,}",
            f"Research-keyword objects: {len(relevant):,}",
            "",
            "RELEVANT OBJECTS",
        ]

        for row in relevant.itertuples(index=False):
            rows_text = (
                "view"
                if pd.isna(row.approximate_rows)
                else f"{int(row.approximate_rows):,} rows"
            )
            lines.append(
                f"- {row.schema_name}.{row.object_name} "
                f"[{row.object_type}; {rows_text}]"
            )

        lines.extend(
            [
                "",
                "SCHEMA COUNTS",
            ]
        )
        schema_counts = (
            object_rows.groupby("schema_name")
            .size()
            .sort_index()
        )
        for schema, count in schema_counts.items():
            lines.append(f"- {schema}: {int(count):,} objects")

        lines.extend(
            [
                "",
                "No database modifications performed.",
                "",
                "AZURE_SQL_RESEARCH_OBJECT_INVENTORY_COMPLETE",
            ]
        )

        TXT_PATH.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print(TXT_PATH.read_text(encoding="utf-8"))

    finally:
        connection.close()


if __name__ == "__main__":
    main()
