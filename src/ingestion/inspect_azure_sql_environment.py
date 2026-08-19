from contextlib import redirect_stdout
from pathlib import Path
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from mssql_python import connect


ROOT = Path(__file__).resolve().parents[2]

REPORT = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_environment_inspection.txt"
)

REQUIRED_SCHEMAS = {
    "raw",
    "staging",
    "core",
    "analytics",
}


def section(title):
    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def query(cursor, sql):
    cursor.execute(sql)

    rows = cursor.fetchall()

    columns = [
        item[0]
        for item in cursor.description
    ]

    return pd.DataFrame.from_records(
        rows,
        columns=columns,
    )


def display(
    frame,
    empty_message,
):
    if frame.empty:
        print(empty_message)

    else:
        print(
            frame.to_string(
                index=False
            )
        )


def inspect():
    load_dotenv(
        ROOT / ".env"
    )

    settings = {
        "server": os.getenv(
            "AZURE_SQL_SERVER"
        ),
        "database": os.getenv(
            "AZURE_SQL_DATABASE"
        ),
        "uid": os.getenv(
            "AZURE_SQL_USERNAME"
        ),
        "pwd": os.getenv(
            "AZURE_SQL_PASSWORD"
        ),
    }

    missing = [
        name
        for name, value in settings.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing Azure SQL settings: "
            f"{missing}"
        )

    connection = connect(
        server=settings["server"],
        database=settings["database"],
        uid=settings["uid"],
        pwd=settings["pwd"],
        encrypt="yes",
        trust_server_certificate="no",
        timeout=90,
    )

    cursor = connection.cursor()

    try:
        section(
            "AZURE SQL READ-ONLY "
            "ENVIRONMENT INSPECTION"
        )

        print(
            "Connection status: SUCCESS"
        )

        print(
            "Credentials included in report: NO"
        )

        database = query(
            cursor,
            """
            SELECT
                DB_NAME() AS database_name,
                compatibility_level,
                collation_name,
                is_read_committed_snapshot_on
            FROM sys.databases
            WHERE name = DB_NAME();
            """,
        )

        section(
            "1. DATABASE CONFIGURATION"
        )

        display(
            database,
            (
                "Database metadata was "
                "not returned."
            ),
        )

        schemas = query(
            cursor,
            """
            SELECT
                name AS schema_name
            FROM sys.schemas
            WHERE name NOT IN (
                'db_accessadmin',
                'db_backupoperator',
                'db_datareader',
                'db_datawriter',
                'db_ddladmin',
                'db_denydatareader',
                'db_denydatawriter',
                'db_owner',
                'db_securityadmin',
                'guest',
                'INFORMATION_SCHEMA',
                'sys'
            )
            ORDER BY name;
            """,
        )

        section(
            "2. USER SCHEMAS"
        )

        display(
            schemas,
            "No user schemas found.",
        )

        schema_set = set(
            schemas["schema_name"]
        )

        for name in sorted(
            REQUIRED_SCHEMAS
        ):
            status = (
                "PRESENT"
                if name in schema_set
                else "MISSING"
            )

            print(
                f"Required schema {name}: "
                f"{status}"
            )

        tables = query(
            cursor,
            """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                COALESCE(
                    SUM(
                        CASE
                            WHEN p.index_id IN (0, 1)
                            THEN p.rows
                            ELSE 0
                        END
                    ),
                    0
                ) AS approximate_rows
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s
                ON s.schema_id = t.schema_id
            LEFT JOIN sys.partitions AS p
                ON p.object_id = t.object_id
            GROUP BY
                s.name,
                t.name
            ORDER BY
                s.name,
                t.name;
            """,
        )

        section(
            "3. EXISTING TABLES"
        )

        display(
            tables,
            "No user tables found.",
        )

        views = query(
            cursor,
            """
            SELECT
                s.name AS schema_name,
                v.name AS view_name
            FROM sys.views AS v
            INNER JOIN sys.schemas AS s
                ON s.schema_id = v.schema_id
            ORDER BY
                s.name,
                v.name;
            """,
        )

        section(
            "4. EXISTING VIEWS"
        )

        display(
            views,
            "No user views found.",
        )

        columns = query(
            cursor,
            """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                c.column_id,
                c.name AS column_name,
                ty.name AS data_type,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable,
                c.is_identity,
                dc.definition AS default_definition
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s
                ON s.schema_id = t.schema_id
            INNER JOIN sys.columns AS c
                ON c.object_id = t.object_id
            INNER JOIN sys.types AS ty
                ON ty.user_type_id = c.user_type_id
            LEFT JOIN sys.default_constraints AS dc
                ON dc.parent_object_id = c.object_id
                AND dc.parent_column_id = c.column_id
            ORDER BY
                s.name,
                t.name,
                c.column_id;
            """,
        )

        section(
            "5. TABLE COLUMNS"
        )

        display(
            columns,
            "No table columns found.",
        )

        primary_keys = query(
            cursor,
            """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                kc.name AS constraint_name,
                ic.key_ordinal,
                c.name AS column_name
            FROM sys.key_constraints AS kc
            INNER JOIN sys.tables AS t
                ON t.object_id = kc.parent_object_id
            INNER JOIN sys.schemas AS s
                ON s.schema_id = t.schema_id
            INNER JOIN sys.index_columns AS ic
                ON ic.object_id = kc.parent_object_id
                AND ic.index_id = kc.unique_index_id
            INNER JOIN sys.columns AS c
                ON c.object_id = ic.object_id
                AND c.column_id = ic.column_id
            WHERE kc.type = 'PK'
            ORDER BY
                s.name,
                t.name,
                ic.key_ordinal;
            """,
        )

        section(
            "6. PRIMARY KEYS"
        )

        display(
            primary_keys,
            "No primary keys found.",
        )

        foreign_keys = query(
            cursor,
            """
            SELECT
                fk.name AS constraint_name,
                ps.name AS parent_schema,
                pt.name AS parent_table,
                pc.name AS parent_column,
                rs.name AS referenced_schema,
                rt.name AS referenced_table,
                rc.name AS referenced_column,
                fkc.constraint_column_id
            FROM sys.foreign_keys AS fk
            INNER JOIN sys.foreign_key_columns AS fkc
                ON fkc.constraint_object_id =
                    fk.object_id
            INNER JOIN sys.tables AS pt
                ON pt.object_id =
                    fk.parent_object_id
            INNER JOIN sys.schemas AS ps
                ON ps.schema_id =
                    pt.schema_id
            INNER JOIN sys.columns AS pc
                ON pc.object_id =
                    pt.object_id
                AND pc.column_id =
                    fkc.parent_column_id
            INNER JOIN sys.tables AS rt
                ON rt.object_id =
                    fk.referenced_object_id
            INNER JOIN sys.schemas AS rs
                ON rs.schema_id =
                    rt.schema_id
            INNER JOIN sys.columns AS rc
                ON rc.object_id =
                    rt.object_id
                AND rc.column_id =
                    fkc.referenced_column_id
            ORDER BY
                fk.name,
                fkc.constraint_column_id;
            """,
        )

        section(
            "7. FOREIGN KEYS"
        )

        display(
            foreign_keys,
            "No foreign keys found.",
        )

        indexes = query(
            cursor,
            """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                i.name AS index_name,
                i.type_desc,
                i.is_unique,
                i.is_primary_key,
                i.is_disabled
            FROM sys.indexes AS i
            INNER JOIN sys.tables AS t
                ON t.object_id = i.object_id
            INNER JOIN sys.schemas AS s
                ON s.schema_id = t.schema_id
            WHERE i.index_id > 0
            ORDER BY
                s.name,
                t.name,
                i.name;
            """,
        )

        section(
            "8. INDEXES"
        )

        display(
            indexes,
            "No indexes found.",
        )

        section(
            "9. INSPECTION SUMMARY"
        )

        print(
            f"User schemas: {len(schemas):,}"
        )

        print(
            f"User tables: {len(tables):,}"
        )

        print(
            f"User views: {len(views):,}"
        )

        present_required = (
            REQUIRED_SCHEMAS
            & schema_set
        )

        print(
            "Required analytical schemas "
            f"present: {len(present_required)} "
            f"/ {len(REQUIRED_SCHEMAS)}"
        )

        print(
            "Database modifications performed: 0"
        )

        print(
            "AZURE_SQL_ENVIRONMENT_"
            "INSPECTION_PASSED"
        )

    finally:
        cursor.close()
        connection.close()


def main():
    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    error = None

    with REPORT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as report:
        with redirect_stdout(report):
            try:
                inspect()

            except Exception as caught:
                error = caught

                section(
                    "INSPECTION FAILED"
                )

                print(
                    type(caught).__name__
                )

                print(caught)

    if error is not None:
        print(
            "AZURE SQL ENVIRONMENT "
            "INSPECTION FAILED"
        )

        print(
            "Saved diagnostic report: "
            f"{REPORT}"
        )

        print(error)
        sys.exit(1)

    print(
        "AZURE SQL ENVIRONMENT "
        "INSPECTION PASSED"
    )

    print(
        "Saved inspection report: "
        f"{REPORT}"
    )


if __name__ == "__main__":
    main()