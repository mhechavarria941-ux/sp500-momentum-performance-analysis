from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-31-v1-apply-bi-date"
ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = ROOT / "sql" / "analytics" / "015_bi_date.sql"
ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


def env():
    load_dotenv(ROOT / ".env")
    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )
    values = tuple(os.getenv(n) for n in names)
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))
    return values


def esc(v: str) -> str:
    return "{" + v.replace("}", "}}") + "}"


def connect(server, database, username, password):
    cs = (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={esc(database)};"
        f"UID={esc(username)};"
        f"PWD={esc(password)};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    for attempt in range(1, 6):
        try:
            c = pyodbc.connect(cs, timeout=30, autocommit=False)
            c.timeout = 120
            print(f"ODBC connection established on attempt {attempt} / 5.")
            return c
        except pyodbc.Error:
            if attempt == 5:
                raise
            time.sleep(15)
    raise RuntimeError("Connection retry loop ended unexpectedly.")


def batches(text: str):
    return [
        x.strip()
        for x in re.split(
            r"^\s*GO\s*(?:--.*)?$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if x.strip()
    ]


def scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main():
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    if not SQL_PATH.exists():
        raise RuntimeError(f"Missing SQL file: {SQL_PATH}")

    server, database, username, password = env()
    conn = connect(server, database, username, password)
    cur = conn.cursor()

    try:
        for batch in batches(SQL_PATH.read_text(encoding="utf-8")):
            cur.execute(batch)
            while cur.nextset():
                pass
        conn.commit()

        row_count = int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.dim_date;"))
        distinct_count = int(
            scalar(cur, "SELECT COUNT_BIG(DISTINCT [date]) FROM bi.dim_date;")
        )
        min_date = scalar(cur, "SELECT MIN([date]) FROM bi.dim_date;")
        max_date = scalar(cur, "SELECT MAX([date]) FROM bi.dim_date;")
        expected = int(
            scalar(
                cur,
                "SELECT DATEDIFF(DAY, MIN([date]), MAX([date])) + 1 FROM bi.dim_date;"
            )
        )

        print(f"Rows: {row_count:,}")
        print(f"Distinct dates: {distinct_count:,}")
        print(f"Minimum date: {min_date}")
        print(f"Maximum date: {max_date}")
        print(f"Expected continuous rows: {expected:,}")

        if row_count != distinct_count:
            raise RuntimeError("bi.dim_date contains duplicate dates.")

        if row_count != expected:
            raise RuntimeError("bi.dim_date still contains gaps.")

        print()
        print("FINAL BI DATE DIMENSION GATE: PASS")
        print("BI_DATE_DIMENSION_CONTINUOUS")
        print("POWER_BI_DATE_TABLE_MARKING_AUTHORIZED")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
