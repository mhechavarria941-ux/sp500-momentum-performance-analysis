from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyodbc
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-26-v1-h3-focused-prereg-sql-binding-discovery"

ROOT = Path(__file__).resolve().parents[2]
ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

PREREG_EXTENSIONS = {".json", ".yaml", ".yml", ".md", ".txt"}

# These are specification terms only.  No outcome rows are queried.
SPEC_TERMS = (
    "h3a",
    "h3b",
    "h3c",
    "hypothesis",
    "predictor",
    "attention_z",
    "attention_percentile",
    "outcome",
    "control",
    "cluster",
    "holm",
    "alpha",
    "timing",
    "month",
    "winner",
    "residual",
    "momentum",
)

SQL_RELEVANCE_TERMS = (
    "security_key",
    "analysis_month_number",
    "ranking_month_end_date",
    "month_end_date",
    "target_holding_end_date",
    "forward_return_1m",
    "forward_return_1m_complete",
    "gics_sector",
    "sector_momentum_quintile",
    "portfolio_label",
    "winner",
    "momentum_12_1",
)


def rule(width: int = 132) -> str:
    return "=" * width


def normalize(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def rel(path: Path) -> str:
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

    retryable = (
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
                f"ODBC connection established on attempt {attempt} / 5."
            )
            return connection
        except pyodbc.Error as exc:
            if (
                attempt == 5
                or not any(x in str(exc).lower() for x in retryable)
            ):
                raise
            print(
                f"ODBC connection attempt {attempt} / 5 failed. "
                "Retrying in 10 seconds."
            )
            time.sleep(10)

    raise RuntimeError("ODBC retry loop ended unexpectedly.")


def flatten_json(
    value: Any,
    prefix: str = "",
) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            p = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(flatten_json(child, p))
        return rows

    if isinstance(value, list):
        for idx, child in enumerate(value):
            p = f"{prefix}[{idx}]"
            rows.extend(flatten_json(child, p))
        return rows

    rows.append((prefix, value))
    return rows


def prereg_score(path: Path) -> tuple[int, list[tuple[str, Any]]]:
    if path.suffix.lower() != ".json":
        return 0, []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0, []

    flat = flatten_json(payload)
    searchable = " ".join(
        f"{key} {value}"
        for key, value in flat
    ).lower()

    score = 0
    name = normalize(path.name)

    if "h3" in name:
        score += 20
    if "prereg" in name:
        score += 30
    if "statistical" in name:
        score += 15
    if "v2" in name:
        score += 10

    for token in (
        "h3a",
        "h3b",
        "h3c",
        "attention_z",
        "cluster_structure",
        "holm",
        "outcome_month",
    ):
        if token in searchable:
            score += 8

    return score, flat


def discover_preregistration() -> tuple[Path, list[tuple[str, Any]]]:
    candidates: list[tuple[int, Path, list[tuple[str, Any]]]] = []

    for path in ROOT.rglob("*.json"):
        if not path.is_file():
            continue

        normalized_path = normalize(str(path))
        if "h3" not in normalized_path:
            continue
        if "prereg" not in normalized_path:
            continue

        score, flat = prereg_score(path)
        if score > 0:
            candidates.append((score, path.resolve(), flat))

    candidates.sort(
        key=lambda x: (-x[0], len(str(x[1])), str(x[1]).lower())
    )

    print("H3 preregistration JSON candidates:")
    for score, path, _ in candidates[:10]:
        print(f"  score={score:03d}  {rel(path)}")

    if not candidates:
        raise RuntimeError(
            "No H3 preregistration JSON found."
        )

    top_score = candidates[0][0]
    tied = [row for row in candidates if row[0] == top_score]

    if len(tied) != 1:
        raise RuntimeError(
            "Top H3 preregistration JSON selection is ambiguous: "
            + ", ".join(rel(row[1]) for row in tied)
        )

    _, path, flat = candidates[0]
    return path, flat


def print_exact_spec(path: Path, flat: list[tuple[str, Any]]) -> None:
    print("")
    print(rule())
    print("1. EXACT FROZEN H3 SPECIFICATION")
    print(rule())
    print(f"Selected preregistration: {rel(path)}")
    print("")

    # Print every scalar leaf.  The preregistration JSON is the authority,
    # and this focused script should remain compact enough not to truncate.
    for key, value in flat:
        rendered = json.dumps(value, ensure_ascii=False)
        print(f"{key} = {rendered}")


def fetch_catalog(cursor) -> pd.DataFrame:
    cursor.execute(
        """
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
            AND s.name IN ('analytics', 'core', 'staging', 'raw')
        ORDER BY
            s.name,
            o.name,
            c.column_id;
        """
    )

    columns = [str(item[0]) for item in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


def object_score(group: pd.DataFrame) -> int:
    object_name = normalize(group["object_name"].iloc[0])
    columns = {
        normalize(x)
        for x in group["column_name"].astype(str).tolist()
    }

    score = 0

    if "security_key" in columns:
        score += 30

    if (
        "analysis_month_number" in columns
        or "ranking_month_end_date" in columns
        or "month_end_date" in columns
    ):
        score += 15

    for column in (
        "forward_return_1m",
        "forward_return_1m_complete",
        "gics_sector",
        "sector_momentum_quintile",
        "portfolio_label",
        "momentum_12_1",
    ):
        if column in columns:
            score += 15

    for token in (
        "forward",
        "sector",
        "momentum",
        "ranking",
        "security_month",
    ):
        if token in object_name:
            score += 5

    return score


def print_sql_binding_candidates() -> None:
    print("")
    print(rule())
    print("2. AZURE SQL H3 JOIN-SOURCE CANDIDATES")
    print(rule())
    print(
        "Metadata only: sys.objects/sys.columns. "
        "No security return rows are queried."
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

    ranked: list[
        tuple[int, str, str, str, pd.DataFrame]
    ] = []

    for (schema, obj, type_desc), group in catalog.groupby(
        ["schema_name", "object_name", "type_desc"],
        sort=True,
    ):
        score = object_score(group)
        if score <= 0:
            continue

        columns = {
            normalize(x)
            for x in group["column_name"].astype(str)
        }

        # Require identity plus either a return/status field or sector-momentum
        # assignment field. This keeps output limited to actual join candidates.
        if "security_key" not in columns:
            continue

        relevant_payload = bool(
            columns
            & {
                "forward_return_1m",
                "forward_return_1m_complete",
                "gics_sector",
                "sector_momentum_quintile",
                "portfolio_label",
                "momentum_12_1",
            }
        )
        if not relevant_payload:
            continue

        ranked.append(
            (
                score,
                str(schema),
                str(obj),
                str(type_desc),
                group.copy(),
            )
        )

    ranked.sort(
        key=lambda row: (-row[0], row[1], row[2])
    )

    if not ranked:
        raise RuntimeError(
            "No sufficiently relevant SQL join-source objects found."
        )

    print(f"Focused SQL candidates: {len(ranked)}")

    for score, schema, obj, type_desc, group in ranked[:15]:
        print("")
        print(
            f"OBJECT: [{schema}].[{obj}] "
            f"score={score} ({type_desc})"
        )
        for row in group.itertuples(index=False):
            print(
                f"  {int(row.column_id):02d}. "
                f"{row.column_name} ({row.data_type})"
            )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print(rule())
    print("H3 FOCUSED PREREGISTRATION / SQL BINDING DISCOVERY")
    print(rule())
    print("Outcome boundary: AUTHORIZED")
    print("Outcome row values queried: 0")
    print("Regression/inference executed: NO")

    path, flat = discover_preregistration()
    print_exact_spec(path, flat)
    print_sql_binding_candidates()

    print("")
    print(rule())
    print("FOCUSED DISCOVERY COMPLETE")
    print(rule())
    print("Outcome row values queried: 0")
    print("Regression/inference executed: NO")
    print("H3_FOCUSED_PREREG_SQL_BINDING_DISCOVERY_COMPLETE")
    print("NEXT_STEP_BUILD_AND_AUDIT_H3_PREDICTOR_OUTCOME_JOIN")


if __name__ == "__main__":
    main()
