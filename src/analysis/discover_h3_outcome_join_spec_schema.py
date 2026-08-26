from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyodbc
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-26-v1-h3-outcome-join-spec-schema-discovery"

ROOT = Path(__file__).resolve().parents[2]

PREDICTOR_PATH = (
    ROOT
    / "reports"
    / "exploratory"
    / "h3_attention_feasibility"
    / "h3_preregistered_attention_predictor_panel.csv"
)

EXPECTED_PREDICTOR_ROWS = 29_287
EXPECTED_PREDICTOR_MONTHS = 58
EXPECTED_ISSUER_CLUSTERS = 583

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

PREREG_NAME_HINTS = (
    "h3",
    "prereg",
)

PREREG_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
}

SQL_OBJECT_NAME_HINTS = (
    "momentum",
    "forward",
    "winner",
    "loser",
    "sector",
    "security_month",
    "ranking",
    "portfolio",
)

DISPLAY_VALUE_KEYS = {
    "h3a",
    "h3b",
    "h3c",
    "hypothesis",
    "hypotheses",
    "analysis_timing",
    "predictor",
    "predictors",
    "outcome",
    "outcomes",
    "primary_inference",
    "inference",
    "clustering",
    "cluster",
    "holm",
    "multiple_testing",
    "controls",
    "control_variables",
    "robustness",
    "attention_z",
    "attention_percentile_midrank",
    "predictor_month_start",
    "predictor_month_end",
    "outcome_month",
}


def rule(width: int = 136) -> str:
    return "=" * width


def normalize(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


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
            "Missing Azure SQL environment variables: "
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
                autocommit=True,
            )
            print(
                f"ODBC connection established on attempt "
                f"{attempt} / 5."
            )
            return connection
        except pyodbc.Error as exc:
            retryable = any(
                term in str(exc).lower()
                for term in retryable_terms
            )
            if not retryable or attempt == 5:
                raise

            print(
                f"ODBC connection attempt {attempt} / 5 failed. "
                "Retrying in 10 seconds."
            )
            time.sleep(10)

    raise RuntimeError("Connection retry loop ended unexpectedly.")


def discover_preregistration_files() -> list[Path]:
    candidates: list[Path] = []

    excluded_dirs = {
        ".git",
        ".venv",
        "venv",
        "myvenv",
        "__pycache__",
        "node_modules",
    }

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in PREREG_EXTENSIONS:
            continue

        try:
            parts = {normalize(p) for p in path.relative_to(ROOT).parts[:-1]}
        except ValueError:
            parts = set()

        if parts & excluded_dirs:
            continue

        name = normalize(path.name)
        if not all(hint in name for hint in PREREG_NAME_HINTS):
            continue

        candidates.append(path.resolve())

    return sorted(
        set(candidates),
        key=lambda p: (
            0 if p.suffix.lower() == ".json" else 1,
            len(str(p)),
            str(p).lower(),
        ),
    )


def flatten_json(
    value: Any,
    prefix: str = "",
) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(flatten_json(child, next_prefix))
        return out

    if isinstance(value, list):
        for index, child in enumerate(value):
            next_prefix = f"{prefix}[{index}]"
            out.extend(flatten_json(child, next_prefix))
        return out

    out.append((prefix, value))
    return out


def print_json_relevant(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  JSON parse failed: {exc}")
        return

    flattened = flatten_json(payload)
    relevant: list[tuple[str, Any]] = []

    for key, value in flattened:
        n = normalize(key)
        if any(token in n for token in DISPLAY_VALUE_KEYS):
            relevant.append((key, value))

    if not relevant:
        print("  No targeted preregistration keys identified.")
        return

    for key, value in relevant:
        rendered = repr(value)
        if len(rendered) > 500:
            rendered = rendered[:497] + "..."
        print(f"  {key} = {rendered}")


def print_text_relevant(path: Path) -> None:
    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    patterns = (
        "H3A",
        "H3B",
        "H3C",
        "hypothesis",
        "outcome",
        "predictor",
        "attention_z",
        "percentile",
        "cluster",
        "Holm",
        "control",
        "month",
        "inference",
    )

    matches: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        low = line.lower()
        if any(pattern.lower() in low for pattern in patterns):
            matches.append((i, line.rstrip()))

    if not matches:
        print("  No targeted specification lines identified.")
        return

    for i, line in matches[:160]:
        print(f"  L{i}: {line}")

    if len(matches) > 160:
        print(
            f"  ... {len(matches) - 160} additional relevant lines omitted."
        )


def predictor_structure() -> None:
    print("")
    print(rule())
    print("1. FROZEN PREDICTOR STRUCTURE")
    print(rule())

    if not PREDICTOR_PATH.exists():
        raise RuntimeError(
            "Frozen predictor panel not found: "
            f"{relative(PREDICTOR_PATH)}"
        )

    frame = pd.read_csv(PREDICTOR_PATH)

    print(f"Path: {relative(PREDICTOR_PATH)}")
    print(f"Rows: {len(frame):,}")
    print(f"Columns: {len(frame.columns)}")
    print("Column names:")
    for col in frame.columns:
        print(f"  {col}")

    month_col = "month" if "month" in frame.columns else None
    issuer_col = next(
        (
            c for c in (
                "issuer_id",
                "issuer_cik",
                "cik",
            )
            if c in frame.columns
        ),
        None,
    )
    security_col = next(
        (
            c for c in (
                "security_key",
                "security_id",
            )
            if c in frame.columns
        ),
        None,
    )

    if month_col is not None:
        print(
            f"Unique predictor months: "
            f"{frame[month_col].nunique(dropna=True)}"
        )
    if issuer_col is not None:
        print(
            f"Unique issuer clusters: "
            f"{frame[issuer_col].nunique(dropna=True)}"
        )
    if security_col is not None:
        print(
            f"Unique security identities: "
            f"{frame[security_col].nunique(dropna=True)}"
        )

    if len(frame) != EXPECTED_PREDICTOR_ROWS:
        raise RuntimeError(
            f"Frozen predictor rows changed: {len(frame):,}; "
            f"expected {EXPECTED_PREDICTOR_ROWS:,}."
        )

    if month_col is not None:
        actual_months = frame[month_col].nunique(dropna=True)
        if actual_months != EXPECTED_PREDICTOR_MONTHS:
            raise RuntimeError(
                f"Frozen predictor month count changed: {actual_months}; "
                f"expected {EXPECTED_PREDICTOR_MONTHS}."
            )

    if issuer_col is not None:
        actual_issuers = frame[issuer_col].nunique(dropna=True)
        if actual_issuers != EXPECTED_ISSUER_CLUSTERS:
            raise RuntimeError(
                f"Frozen issuer cluster count changed: {actual_issuers}; "
                f"expected {EXPECTED_ISSUER_CLUSTERS}."
            )

    print("PASS: Frozen predictor population matches the authorized V2 gate.")


def preregistration_structure() -> None:
    print("")
    print(rule())
    print("2. FROZEN H3 PREREGISTRATION DISCOVERY")
    print(rule())

    files = discover_preregistration_files()

    if not files:
        raise RuntimeError(
            "No H3 preregistration file was discovered in the repository."
        )

    print(f"Candidate H3 preregistration files: {len(files)}")

    for path in files:
        print("")
        print(f"FILE: {relative(path)}")
        print(f"TYPE: {path.suffix.lower()}")
        if path.suffix.lower() == ".json":
            print_json_relevant(path)
        else:
            print_text_relevant(path)


def fetch_catalog(cursor) -> pd.DataFrame:
    query = """
    SELECT
        s.name AS schema_name,
        o.name AS object_name,
        o.type_desc,
        c.column_id,
        c.name AS column_name,
        TYPE_NAME(c.user_type_id) AS data_type
    FROM sys.objects AS o
    INNER JOIN sys.schemas AS s
        ON s.schema_id = o.schema_id
    INNER JOIN sys.columns AS c
        ON c.object_id = o.object_id
    WHERE
        o.type IN ('V', 'U')
        AND o.is_ms_shipped = 0
    ORDER BY
        s.name,
        o.name,
        c.column_id;
    """
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


def sql_schema_structure() -> None:
    print("")
    print(rule())
    print("3. AZURE SQL OUTCOME-SOURCE CATALOG DISCOVERY")
    print(rule())
    print(
        "Catalog metadata only: sys.objects/sys.columns. "
        "No outcome rows or return values are queried."
    )

    server, database, username, password = environment()
    connection = connect_with_retry(
        server,
        database,
        username,
        password,
    )

    try:
        cursor = connection.cursor()
        catalog = fetch_catalog(cursor)
    finally:
        connection.close()

    mask = pd.Series(False, index=catalog.index)
    for token in SQL_OBJECT_NAME_HINTS:
        mask |= (
            catalog["object_name"]
            .astype(str)
            .str.lower()
            .str.contains(token, regex=False)
        )

    selected = catalog.loc[mask].copy()

    if selected.empty:
        raise RuntimeError(
            "No likely H3 outcome-source objects were discovered "
            "from Azure SQL catalog metadata."
        )

    grouped = selected.groupby(
        ["schema_name", "object_name", "type_desc"],
        sort=True,
    )

    print(
        f"Candidate SQL objects: "
        f"{selected[['schema_name','object_name']].drop_duplicates().shape[0]}"
    )

    for (schema, obj, type_desc), group in grouped:
        print("")
        print(f"OBJECT: [{schema}].[{obj}]  ({type_desc})")
        for _, row in group.iterrows():
            print(
                f"  {int(row['column_id']):02d}. "
                f"{row['column_name']}  ({row['data_type']})"
            )


def source_code_join_hints() -> None:
    print("")
    print(rule())
    print("4. EXISTING H3 SOURCE-CODE JOIN HINTS")
    print(rule())

    source_files = sorted(
        (
            ROOT / "src" / "analysis"
        ).glob("*h3*.py")
    )

    patterns = (
        "outcome",
        "forward_return",
        "winner",
        "loser",
        "security_key",
        "issuer",
        "outcome_month",
        "predictor_month",
        "cluster",
        "H3A",
        "H3B",
        "H3C",
    )

    found_any = False

    for path in source_files:
        lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

        matches = []
        for i, line in enumerate(lines, start=1):
            low = line.lower()
            if any(pattern.lower() in low for pattern in patterns):
                matches.append((i, line.rstrip()))

        if not matches:
            continue

        found_any = True
        print("")
        print(f"FILE: {relative(path)}")
        for i, line in matches[:120]:
            print(f"  L{i}: {line}")

        if len(matches) > 120:
            print(
                f"  ... {len(matches) - 120} additional matches omitted."
            )

    if not found_any:
        print("No existing H3 outcome/join implementation hints found.")


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print(rule())
    print("H3 OUTCOME-JOIN SPECIFICATION / SCHEMA DISCOVERY")
    print(rule())
    print("H3 outcome boundary status: AUTHORIZED")
    print("Outcome values queried: NO")
    print("SQL activity: catalog metadata only")
    print(
        "Purpose: bind the next join implementation to the exact "
        "frozen H3 specification and existing validated SQL objects."
    )

    predictor_structure()
    preregistration_structure()
    sql_schema_structure()
    source_code_join_hints()

    print("")
    print(rule())
    print("DISCOVERY COMPLETE")
    print(rule())
    print("Predictor values inspected: structural population/schema only")
    print("Outcome/return row values queried: 0")
    print("Regression/inference executed: NO")
    print("H3_OUTCOME_JOIN_SPEC_SCHEMA_DISCOVERY_COMPLETE")
    print("NEXT_STEP_BUILD_EXACT_PREREGISTERED_H3_OUTCOME_JOIN")


if __name__ == "__main__":
    main()
