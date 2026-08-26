from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-26-v1-h3-preregistered-predictor-outcome-join"

ROOT = Path(__file__).resolve().parents[2]
H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
OUT_DIR = ROOT / "reports" / "confirmatory" / "h3"

PREDICTOR_PATH = H3_DIR / "h3_preregistered_attention_predictor_panel.csv"
PREREG_PATH = ROOT / "data" / "reference" / "h3" / "h3_statistical_preregistration_v2.json"

PANEL_PATH = OUT_DIR / "h3_preregistered_predictor_outcome_panel.csv"
AUDIT_PATH = OUT_DIR / "h3_preregistered_predictor_outcome_join_audit.txt"
MANIFEST_PATH = OUT_DIR / "h3_preregistered_predictor_outcome_join_manifest.json"

SQL_TABLE = "analytics.h3_preregistered_predictor_outcome_panel"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXPECTED_PREDICTOR_ROWS = 29_287
EXPECTED_PREDICTOR_MONTHS = 58
EXPECTED_ISSUER_CLUSTERS = 583
EXPECTED_EXCLUDED_PREDICTOR_MONTH = pd.Period("2025-06", freq="M")

FROZEN_START = pd.Period("2021-01", freq="M")
FROZEN_END = pd.Period("2025-11", freq="M")

MIN_SECTOR_PEERS = 5
MIN_MODEL_ROWS = 1000
MIN_ISSUER_CLUSTERS = 100
MIN_OUTCOME_MONTH_CLUSTERS = 30
MIN_H3B_POSITIVE_EVENTS = 100


def rule(width: int = 136) -> str:
    return "=" * width


def normalize_name(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(condition: bool, passed: str, failed: str, failures: list[str]) -> None:
    if condition:
        print(f"PASS: {passed}")
    else:
        print(f"FAIL: {failed}")
        failures.append(failed)


def load_environment() -> tuple[str, str, str, str]:
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
            "Missing Azure SQL environment variables: " + ", ".join(missing)
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
            f"{ODBC_DRIVER} is not installed. Available drivers: {pyodbc.drivers()}"
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
            print(f"ODBC connection established on attempt {attempt} / 5.")
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

    raise RuntimeError("ODBC retry loop ended unexpectedly.")


def fetch_dataframe(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


def parse_predictor_month(series: pd.Series) -> pd.Series:
    periods = pd.PeriodIndex(
        series.astype("string").str.strip(),
        freq="M",
    )
    return pd.Series(periods, index=series.index, dtype="period[M]")


def choose_optional_column(
    columns: list[str],
    candidates: tuple[str, ...],
) -> str | None:
    normalized = {normalize_name(c): c for c in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def load_predictor() -> tuple[pd.DataFrame, dict[str, str | None]]:
    if not PREDICTOR_PATH.exists():
        raise RuntimeError(f"Missing frozen predictor: {PREDICTOR_PATH}")
    if not PREREG_PATH.exists():
        raise RuntimeError(f"Missing frozen preregistration: {PREREG_PATH}")

    header = list(pd.read_csv(PREDICTOR_PATH, nrows=0).columns)

    required = {
        "month",
        "security_key",
        "issuer_id",
        "attention_z",
        "attention_log",
        "attention_percentile_midrank",
    }
    missing = sorted(required - set(header))
    if missing:
        raise RuntimeError(
            "Frozen predictor is missing required columns: " + ", ".join(missing)
        )

    dtype_map = {
        "month": "string",
        "security_key": "string",
        "issuer_id": "string",
    }
    predictor = pd.read_csv(PREDICTOR_PATH, dtype=dtype_map)

    predictor["security_key"] = predictor["security_key"].astype("string").str.strip()
    predictor["issuer_id"] = predictor["issuer_id"].astype("string").str.strip()
    predictor["predictor_month"] = parse_predictor_month(predictor["month"])

    structural_col = choose_optional_column(
        header,
        (
            "structural_ambiguity_tier",
            "alias_structural_ambiguity_tier",
        ),
    )
    transition_col = choose_optional_column(
        header,
        (
            "pit_alias_transition_month_flag",
            "alias_transition_month_flag",
            "transition_month_flag",
        ),
    )
    prereg_sha_col = choose_optional_column(
        header,
        ("preregistration_sha256",),
    )

    optional_map = {
        "structural_ambiguity_tier": structural_col,
        "pit_alias_transition_month_flag": transition_col,
        "preregistration_sha256": prereg_sha_col,
    }

    return predictor, optional_map


def load_preregistration() -> dict:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))

    if payload.get("preregistration_id") != "H3_STATISTICAL_PREREGISTRATION_V2":
        raise RuntimeError("Unexpected H3 preregistration ID.")

    if (
        payload["return_outcome"]["source"]
        != "Corrected H1 one-month gross security forward-return layer; no recomputation from a different price source."
    ):
        raise RuntimeError("Frozen H3 return source changed.")

    if payload["return_outcome"]["minimum_valid_sector_peers"] != MIN_SECTOR_PEERS:
        raise RuntimeError("Frozen minimum sector-peer requirement changed.")

    return payload


def query_sql_sources(connection) -> tuple[pd.DataFrame, pd.DataFrame]:
    cursor = connection.cursor()

    current_query = """
    SELECT
        f.analysis_month_number,
        f.ranking_month_end_date,
        f.security_key,
        f.momentum_decile AS current_momentum_decile,
        CAST(f.forward_return_1m AS float) AS forward_return_1m,
        CAST(f.forward_return_1m_complete AS int) AS forward_return_1m_complete,
        CAST(f.out_of_scope_right_censored AS int) AS out_of_scope_right_censored,
        g.month_end_date AS gics_month_end_date,
        g.gics_sector
    FROM analytics.v_security_monthly_forward_return_1m AS f
    LEFT JOIN analytics.security_month_end_gics_sector AS g
        ON g.analysis_month_number = f.analysis_month_number
       AND g.security_key = f.security_key
    WHERE
        f.ranking_month_end_date >= '2021-01-01'
        AND f.ranking_month_end_date < '2025-12-01'
    ORDER BY
        f.ranking_month_end_date,
        f.security_key;
    """

    next_ranking_query = """
    SELECT
        analysis_month_number,
        month_end_date,
        security_key,
        momentum_decile AS next_momentum_decile,
        CAST(momentum_12_1_complete AS int) AS next_momentum_12_1_complete
    FROM analytics.v_security_monthly_momentum_ranking
    WHERE
        month_end_date >= '2021-02-01'
        AND month_end_date < '2026-01-01'
    ORDER BY
        month_end_date,
        security_key;
    """

    current = fetch_dataframe(cursor, current_query)
    next_rank = fetch_dataframe(cursor, next_ranking_query)

    return current, next_rank


def prepare_current_universe(current: pd.DataFrame) -> pd.DataFrame:
    current = current.copy()

    current["security_key"] = current["security_key"].astype("string").str.strip()
    current["ranking_month_end_date"] = pd.to_datetime(
        current["ranking_month_end_date"]
    )
    current["gics_month_end_date"] = pd.to_datetime(
        current["gics_month_end_date"]
    )

    current["predictor_month"] = (
        current["ranking_month_end_date"].dt.to_period("M")
    )

    current["current_momentum_decile"] = pd.to_numeric(
        current["current_momentum_decile"],
        errors="coerce",
    ).astype("Int64")

    current["forward_return_1m"] = pd.to_numeric(
        current["forward_return_1m"],
        errors="coerce",
    )
    current["forward_return_1m_complete"] = pd.to_numeric(
        current["forward_return_1m_complete"],
        errors="coerce",
    ).fillna(0).astype(int)

    valid_return = (
        current["forward_return_1m_complete"].eq(1)
        & current["forward_return_1m"].notna()
        & current["gics_sector"].notna()
    )
    current["__valid_sector_return"] = valid_return.astype(int)
    current["__return_for_sector"] = current["forward_return_1m"].where(
        valid_return,
        np.nan,
    )

    sector_stats = (
        current.groupby(
            ["predictor_month", "gics_sector"],
            dropna=False,
            as_index=False,
        )
        .agg(
            sector_valid_security_count=(
                "__valid_sector_return",
                "sum",
            ),
            sector_valid_return_sum=(
                "__return_for_sector",
                "sum",
            ),
        )
    )

    current = current.merge(
        sector_stats,
        on=["predictor_month", "gics_sector"],
        how="left",
        validate="many_to_one",
    )

    current["leave_one_out_sector_peers"] = np.where(
        valid_return,
        current["sector_valid_security_count"] - 1,
        np.nan,
    )

    current["sector_peer_mean_excl"] = np.where(
        valid_return
        & current["leave_one_out_sector_peers"].gt(0),
        (
            current["sector_valid_return_sum"]
            - current["forward_return_1m"]
        )
        / current["leave_one_out_sector_peers"],
        np.nan,
    )

    current["sector_relative_return_1m"] = np.where(
        valid_return
        & current["leave_one_out_sector_peers"].ge(MIN_SECTOR_PEERS),
        current["forward_return_1m"]
        - current["sector_peer_mean_excl"],
        np.nan,
    )

    return current


def prepare_next_rank(next_rank: pd.DataFrame) -> pd.DataFrame:
    next_rank = next_rank.copy()
    next_rank["security_key"] = (
        next_rank["security_key"].astype("string").str.strip()
    )
    next_rank["month_end_date"] = pd.to_datetime(
        next_rank["month_end_date"]
    )
    next_rank["outcome_month"] = next_rank["month_end_date"].dt.to_period("M")
    next_rank["next_momentum_decile"] = pd.to_numeric(
        next_rank["next_momentum_decile"],
        errors="coerce",
    ).astype("Int64")
    next_rank["next_momentum_12_1_complete"] = pd.to_numeric(
        next_rank["next_momentum_12_1_complete"],
        errors="coerce",
    ).fillna(0).astype(int)
    return next_rank


def build_panel(
    predictor: pd.DataFrame,
    current: pd.DataFrame,
    next_rank: pd.DataFrame,
    optional_map: dict[str, str | None],
) -> pd.DataFrame:
    current_keep = current[
        [
            "analysis_month_number",
            "predictor_month",
            "security_key",
            "ranking_month_end_date",
            "gics_month_end_date",
            "gics_sector",
            "current_momentum_decile",
            "forward_return_1m",
            "forward_return_1m_complete",
            "out_of_scope_right_censored",
            "sector_valid_security_count",
            "leave_one_out_sector_peers",
            "sector_peer_mean_excl",
            "sector_relative_return_1m",
        ]
    ].copy()

    panel = predictor.merge(
        current_keep,
        on=["predictor_month", "security_key"],
        how="left",
        validate="one_to_one",
        indicator="__current_join",
    )

    panel["outcome_month"] = panel["predictor_month"] + 1

    next_keep = next_rank[
        [
            "outcome_month",
            "security_key",
            "next_momentum_decile",
            "next_momentum_12_1_complete",
        ]
    ].copy()

    panel = panel.merge(
        next_keep,
        on=["outcome_month", "security_key"],
        how="left",
        validate="one_to_one",
        indicator="__next_join",
    )

    panel["current_winner"] = (
        panel["current_momentum_decile"].eq(10)
        .fillna(False)
        .astype(int)
    )

    panel["attention_x_current_winner"] = np.where(
        panel["current_momentum_decile"].notna(),
        panel["attention_z"] * panel["current_winner"].astype(float),
        np.nan,
    )

    valid_current_decile = panel["current_momentum_decile"].between(1, 10)

    panel["h3a_h3c_eligible"] = (
        panel["forward_return_1m_complete"].eq(1)
        & panel["forward_return_1m"].notna()
        & panel["gics_sector"].notna()
        & panel["leave_one_out_sector_peers"].ge(MIN_SECTOR_PEERS)
        & panel["sector_relative_return_1m"].notna()
        & valid_current_decile.fillna(False)
    ).fillna(False).astype(int)

    current_nonwinner = (
        panel["current_momentum_decile"].between(1, 9).fillna(False)
    )
    valid_next_assignment = (
        panel["next_momentum_12_1_complete"].eq(1)
        & panel["next_momentum_decile"].between(1, 10).fillna(False)
    ).fillna(False)

    panel["h3b_eligible"] = (
        current_nonwinner
        & valid_next_assignment
    ).fillna(False).astype(int)

    panel["winner_entry"] = pd.Series(
        pd.NA,
        index=panel.index,
        dtype="Int64",
    )
    h3b_mask = panel["h3b_eligible"].eq(1)
    panel.loc[h3b_mask, "winner_entry"] = (
        panel.loc[h3b_mask, "next_momentum_decile"]
        .eq(10)
        .astype(int)
    )

    panel["predictor_month_end"] = (
        panel["predictor_month"].dt.to_timestamp(how="end").dt.normalize()
    )
    panel["outcome_month_end"] = (
        panel["outcome_month"].dt.to_timestamp(how="end").dt.normalize()
    )

    structural_source = optional_map["structural_ambiguity_tier"]
    transition_source = optional_map["pit_alias_transition_month_flag"]
    prereg_sha_source = optional_map["preregistration_sha256"]

    if structural_source is None:
        panel["structural_ambiguity_tier"] = pd.NA
    elif structural_source != "structural_ambiguity_tier":
        panel["structural_ambiguity_tier"] = panel[structural_source]

    if transition_source is None:
        panel["pit_alias_transition_month_flag"] = pd.NA
    elif transition_source != "pit_alias_transition_month_flag":
        panel["pit_alias_transition_month_flag"] = panel[transition_source]

    if prereg_sha_source is None:
        panel["preregistration_sha256"] = pd.NA
    elif prereg_sha_source != "preregistration_sha256":
        panel["preregistration_sha256"] = panel[prereg_sha_source]

    output_columns = [
        "predictor_month",
        "predictor_month_end",
        "outcome_month",
        "outcome_month_end",
        "security_key",
        "issuer_id",
        "attention_z",
        "attention_log",
        "attention_percentile_midrank",
        "structural_ambiguity_tier",
        "pit_alias_transition_month_flag",
        "preregistration_sha256",
        "analysis_month_number",
        "gics_sector",
        "current_momentum_decile",
        "current_winner",
        "forward_return_1m",
        "forward_return_1m_complete",
        "out_of_scope_right_censored",
        "sector_valid_security_count",
        "leave_one_out_sector_peers",
        "sector_peer_mean_excl",
        "sector_relative_return_1m",
        "attention_x_current_winner",
        "h3a_h3c_eligible",
        "next_momentum_decile",
        "next_momentum_12_1_complete",
        "winner_entry",
        "h3b_eligible",
        "__current_join",
        "__next_join",
    ]

    return panel[output_columns].copy()


def audit_panel(
    predictor: pd.DataFrame,
    current: pd.DataFrame,
    next_rank: pd.DataFrame,
    panel: pd.DataFrame,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    lines: list[str] = []

    def record(condition: bool, passed: str, failed: str) -> None:
        check(condition, passed, failed, failures)
        lines.append(("PASS: " + passed) if condition else ("FAIL: " + failed))

    record(
        len(predictor) == EXPECTED_PREDICTOR_ROWS,
        f"Frozen predictor has exactly {EXPECTED_PREDICTOR_ROWS:,} rows.",
        f"Frozen predictor row count changed: {len(predictor):,}.",
    )
    record(
        predictor["predictor_month"].nunique() == EXPECTED_PREDICTOR_MONTHS,
        f"Frozen predictor has exactly {EXPECTED_PREDICTOR_MONTHS} eligible months.",
        "Frozen predictor month count changed.",
    )
    record(
        predictor["issuer_id"].nunique() == EXPECTED_ISSUER_CLUSTERS,
        f"Frozen predictor has exactly {EXPECTED_ISSUER_CLUSTERS} issuer clusters.",
        "Frozen predictor issuer-cluster count changed.",
    )
    record(
        not predictor[["predictor_month", "security_key"]].duplicated().any(),
        "Frozen predictor has exactly one row per security-month.",
        "Duplicate predictor security-month rows exist.",
    )
    record(
        EXPECTED_EXCLUDED_PREDICTOR_MONTH
        not in set(predictor["predictor_month"].unique()),
        "Frozen excluded month 2025-06 is absent from the predictor panel.",
        "Frozen excluded month 2025-06 reappeared in the predictor panel.",
    )
    record(
        not current[["predictor_month", "security_key"]].duplicated().any(),
        "Canonical H1 forward-return source is unique by predictor month and security.",
        "Canonical H1 forward-return source has duplicate month-security rows.",
    )
    record(
        not next_rank[["outcome_month", "security_key"]].duplicated().any(),
        "Canonical next-month momentum source is unique by outcome month and security.",
        "Canonical next-month momentum source has duplicate month-security rows.",
    )
    record(
        len(panel) == len(predictor),
        "Outcome join preserves every frozen predictor row exactly once.",
        "Outcome join changed the number of frozen predictor rows.",
    )
    record(
        not panel[["predictor_month", "security_key"]].duplicated().any(),
        "Joined panel remains unique by predictor month and security.",
        "Joined panel contains duplicate predictor security-month rows.",
    )
    record(
        (
            panel["outcome_month"]
            == panel["predictor_month"] + 1
        ).all(),
        "Every outcome month is exactly predictor month t + 1.",
        "At least one outcome month is not exactly predictor month t + 1.",
    )

    gics_dates = current["gics_month_end_date"].dropna()
    ranking_dates = current.loc[
        current["gics_month_end_date"].notna(),
        "ranking_month_end_date",
    ]
    record(
        (
            gics_dates.dt.to_period("M").reset_index(drop=True)
            == ranking_dates.dt.to_period("M").reset_index(drop=True)
        ).all(),
        "PIT GICS sector rows align to the same predictor month as H1 ranking rows.",
        "At least one PIT GICS row is misaligned to the predictor month.",
    )

    h3ac = panel[panel["h3a_h3c_eligible"].eq(1)].copy()
    h3b = panel[panel["h3b_eligible"].eq(1)].copy()

    record(
        len(h3ac) >= MIN_MODEL_ROWS,
        f"H3A/H3C structural sample has at least {MIN_MODEL_ROWS:,} rows.",
        f"H3A/H3C structural sample has only {len(h3ac):,} rows.",
    )
    record(
        h3ac["issuer_id"].nunique() >= MIN_ISSUER_CLUSTERS,
        f"H3A/H3C has at least {MIN_ISSUER_CLUSTERS} issuer clusters.",
        "H3A/H3C has too few issuer clusters.",
    )
    record(
        h3ac["outcome_month"].nunique() >= MIN_OUTCOME_MONTH_CLUSTERS,
        f"H3A/H3C has at least {MIN_OUTCOME_MONTH_CLUSTERS} outcome-month clusters.",
        "H3A/H3C has too few outcome-month clusters.",
    )
    record(
        h3ac["leave_one_out_sector_peers"].ge(MIN_SECTOR_PEERS).all(),
        "Every H3A/H3C row has at least 5 valid OTHER same-sector return peers.",
        "An H3A/H3C row violates the frozen leave-one-out sector-peer minimum.",
    )
    record(
        h3ac["sector_relative_return_1m"].notna().all(),
        "Every H3A/H3C row has a valid leave-one-out sector-relative return.",
        "An H3A/H3C row lacks the frozen sector-relative outcome.",
    )
    record(
        h3ac["current_momentum_decile"].between(1, 10).all(),
        "Every H3A/H3C row has a valid current corrected H1 momentum decile.",
        "An H3A/H3C row lacks a valid current corrected H1 momentum decile.",
    )

    record(
        len(h3b) >= MIN_MODEL_ROWS,
        f"H3B structural sample has at least {MIN_MODEL_ROWS:,} rows.",
        f"H3B structural sample has only {len(h3b):,} rows.",
    )
    record(
        h3b["issuer_id"].nunique() >= MIN_ISSUER_CLUSTERS,
        f"H3B has at least {MIN_ISSUER_CLUSTERS} issuer clusters.",
        "H3B has too few issuer clusters.",
    )
    record(
        h3b["outcome_month"].nunique() >= MIN_OUTCOME_MONTH_CLUSTERS,
        f"H3B has at least {MIN_OUTCOME_MONTH_CLUSTERS} outcome-month clusters.",
        "H3B has too few outcome-month clusters.",
    )
    record(
        h3b["current_momentum_decile"].between(1, 9).all(),
        "Every H3B row is a current non-Winner (D01-D09).",
        "An H3B row is not in the frozen D01-D09 risk set.",
    )
    record(
        h3b["next_momentum_decile"].between(1, 10).all(),
        "Every H3B row has a valid t+1 corrected H1 momentum assignment.",
        "An H3B row lacks a valid t+1 corrected H1 momentum assignment.",
    )
    record(
        set(h3b["winner_entry"].dropna().astype(int).unique()).issubset({0, 1}),
        "H3B Winner-entry outcome is binary.",
        "H3B Winner-entry outcome contains values outside {0,1}.",
    )

    positive_events = int(h3b["winner_entry"].fillna(0).sum())
    record(
        positive_events >= MIN_H3B_POSITIVE_EVENTS,
        f"H3B has at least {MIN_H3B_POSITIVE_EVENTS} positive Winner-entry events.",
        f"H3B has only {positive_events} positive Winner-entry events.",
    )

    record(
        (
            panel["current_winner"]
            == panel["current_momentum_decile"].eq(10).fillna(False).astype(int)
        ).all(),
        "Current-Winner indicator reproduces corrected H1 D10 exactly.",
        "Current-Winner indicator does not reproduce corrected H1 D10.",
    )

    record(
        pd.Period("2025-07", freq="M")
        not in set(panel["outcome_month"].unique()),
        "No July-2025 H3 outcome observation exists because June-2025 attention was frozen ineligible.",
        "A July-2025 H3 outcome observation exists despite frozen June-2025 exclusion.",
    )

    lines.extend(
        [
            "",
            f"Joined predictor rows: {len(panel):,}",
            f"Current H1 join matches: {(panel['__current_join'] == 'both').sum():,}",
            f"Current H1 join misses: {(panel['__current_join'] != 'both').sum():,}",
            f"Next-month ranking join matches: {(panel['__next_join'] == 'both').sum():,}",
            f"Next-month ranking join misses: {(panel['__next_join'] != 'both').sum():,}",
            f"H3A/H3C eligible rows: {len(h3ac):,}",
            f"H3A/H3C issuer clusters: {h3ac['issuer_id'].nunique():,}",
            f"H3A/H3C outcome-month clusters: {h3ac['outcome_month'].nunique():,}",
            f"H3B eligible rows: {len(h3b):,}",
            f"H3B issuer clusters: {h3b['issuer_id'].nunique():,}",
            f"H3B outcome-month clusters: {h3b['outcome_month'].nunique():,}",
            f"H3B positive Winner-entry events: {positive_events:,}",
        ]
    )

    return failures, lines


def to_sql_scalar(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def materialize_sql(connection, panel: pd.DataFrame) -> None:
    cursor = connection.cursor()

    ddl = """
    IF OBJECT_ID('analytics.h3_preregistered_predictor_outcome_panel', 'U') IS NOT NULL
        DROP TABLE analytics.h3_preregistered_predictor_outcome_panel;

    CREATE TABLE analytics.h3_preregistered_predictor_outcome_panel (
        predictor_month char(7) NOT NULL,
        predictor_month_end date NOT NULL,
        outcome_month char(7) NOT NULL,
        outcome_month_end date NOT NULL,
        security_key nvarchar(64) NOT NULL,
        issuer_id nvarchar(64) NOT NULL,
        attention_z float NOT NULL,
        attention_log float NOT NULL,
        attention_percentile_midrank float NOT NULL,
        structural_ambiguity_tier nvarchar(64) NULL,
        pit_alias_transition_month_flag bit NULL,
        preregistration_sha256 nvarchar(128) NULL,
        analysis_month_number int NULL,
        gics_sector nvarchar(128) NULL,
        current_momentum_decile tinyint NULL,
        current_winner bit NULL,
        forward_return_1m float NULL,
        forward_return_1m_complete bit NULL,
        out_of_scope_right_censored bit NULL,
        sector_valid_security_count int NULL,
        leave_one_out_sector_peers int NULL,
        sector_peer_mean_excl float NULL,
        sector_relative_return_1m float NULL,
        attention_x_current_winner float NULL,
        h3a_h3c_eligible bit NOT NULL,
        next_momentum_decile tinyint NULL,
        next_momentum_12_1_complete bit NULL,
        winner_entry bit NULL,
        h3b_eligible bit NOT NULL,
        current_join_status nvarchar(16) NOT NULL,
        next_join_status nvarchar(16) NOT NULL,
        CONSTRAINT PK_h3_preregistered_predictor_outcome_panel
            PRIMARY KEY (predictor_month, security_key)
    );
    """
    cursor.execute(ddl)

    insert_sql = """
    INSERT INTO analytics.h3_preregistered_predictor_outcome_panel (
        predictor_month,
        predictor_month_end,
        outcome_month,
        outcome_month_end,
        security_key,
        issuer_id,
        attention_z,
        attention_log,
        attention_percentile_midrank,
        structural_ambiguity_tier,
        pit_alias_transition_month_flag,
        preregistration_sha256,
        analysis_month_number,
        gics_sector,
        current_momentum_decile,
        current_winner,
        forward_return_1m,
        forward_return_1m_complete,
        out_of_scope_right_censored,
        sector_valid_security_count,
        leave_one_out_sector_peers,
        sector_peer_mean_excl,
        sector_relative_return_1m,
        attention_x_current_winner,
        h3a_h3c_eligible,
        next_momentum_decile,
        next_momentum_12_1_complete,
        winner_entry,
        h3b_eligible,
        current_join_status,
        next_join_status
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
    """

    insert_frame = panel.copy()
    insert_frame["predictor_month"] = insert_frame["predictor_month"].astype(str)
    insert_frame["outcome_month"] = insert_frame["outcome_month"].astype(str)
    insert_frame["__current_join"] = insert_frame["__current_join"].astype(str)
    insert_frame["__next_join"] = insert_frame["__next_join"].astype(str)

    columns = [
        "predictor_month",
        "predictor_month_end",
        "outcome_month",
        "outcome_month_end",
        "security_key",
        "issuer_id",
        "attention_z",
        "attention_log",
        "attention_percentile_midrank",
        "structural_ambiguity_tier",
        "pit_alias_transition_month_flag",
        "preregistration_sha256",
        "analysis_month_number",
        "gics_sector",
        "current_momentum_decile",
        "current_winner",
        "forward_return_1m",
        "forward_return_1m_complete",
        "out_of_scope_right_censored",
        "sector_valid_security_count",
        "leave_one_out_sector_peers",
        "sector_peer_mean_excl",
        "sector_relative_return_1m",
        "attention_x_current_winner",
        "h3a_h3c_eligible",
        "next_momentum_decile",
        "next_momentum_12_1_complete",
        "winner_entry",
        "h3b_eligible",
        "__current_join",
        "__next_join",
    ]

    rows = [
        tuple(to_sql_scalar(value) for value in row)
        for row in insert_frame[columns].itertuples(index=False, name=None)
    ]

    cursor.fast_executemany = True
    cursor.executemany(insert_sql, rows)

    cursor.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT predictor_month) AS predictor_months,
            COUNT(DISTINCT issuer_id) AS issuer_clusters
        FROM analytics.h3_preregistered_predictor_outcome_panel;
        """
    )
    result = cursor.fetchone()

    if int(result[0]) != len(panel):
        raise RuntimeError(
            f"SQL materialization row count mismatch: {result[0]} vs {len(panel)}."
        )
    if int(result[1]) != EXPECTED_PREDICTOR_MONTHS:
        raise RuntimeError(
            f"SQL materialization predictor-month count mismatch: {result[1]}."
        )
    if int(result[2]) != EXPECTED_ISSUER_CLUSTERS:
        raise RuntimeError(
            f"SQL materialization issuer-cluster count mismatch: {result[2]}."
        )


def write_outputs(
    panel: pd.DataFrame,
    audit_lines: list[str],
    prereg: dict,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    export = panel.copy()
    export["predictor_month"] = export["predictor_month"].astype(str)
    export["outcome_month"] = export["outcome_month"].astype(str)
    export["__current_join"] = export["__current_join"].astype(str)
    export["__next_join"] = export["__next_join"].astype(str)
    export.to_csv(PANEL_PATH, index=False)

    panel_sha = sha256_file(PANEL_PATH)
    predictor_sha = sha256_file(PREDICTOR_PATH)
    prereg_sha = sha256_file(PREREG_PATH)

    report = [
        rule(),
        "H3 PREREGISTERED PREDICTOR → OUTCOME JOIN — INTEGRITY AUDIT",
        rule(),
        f"Script version: {SCRIPT_VERSION}",
        f"Preregistration ID: {prereg['preregistration_id']}",
        f"Frozen predictor SHA-256: {predictor_sha}",
        f"Frozen preregistration SHA-256: {prereg_sha}",
        f"Joined panel SHA-256: {panel_sha}",
        "",
        *audit_lines,
        "",
        "Regression/inference executed: NO",
        "Coefficient inspection performed by this script: NO",
        "Primary H3 models remain blocked unless every structural join check passes.",
        "",
        "H3_PREREGISTERED_PREDICTOR_OUTCOME_JOIN_INTEGRITY_AUDIT_PASSED",
        "H3_PRIMARY_MODEL_EXECUTION_AUTHORIZED",
    ]
    AUDIT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")

    manifest = {
        "script_version": SCRIPT_VERSION,
        "preregistration_id": prereg["preregistration_id"],
        "preregistration_version": prereg["preregistration_version"],
        "predictor_path": str(PREDICTOR_PATH.relative_to(ROOT)),
        "predictor_sha256": predictor_sha,
        "preregistration_path": str(PREREG_PATH.relative_to(ROOT)),
        "preregistration_sha256": prereg_sha,
        "panel_path": str(PANEL_PATH.relative_to(ROOT)),
        "panel_sha256": panel_sha,
        "sql_table": SQL_TABLE,
        "primary_return_source": "analytics.v_security_monthly_forward_return_1m",
        "pit_sector_source": "analytics.security_month_end_gics_sector",
        "next_month_momentum_source": "analytics.v_security_monthly_momentum_ranking",
        "sector_residual_rule": prereg["return_outcome"]["sector_residual_definition"],
        "h3b_entry_definition": prereg["hypotheses"]["H3B"]["entry_definition"],
        "regression_inference_executed": False,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print(rule())
    print("H3 PREREGISTERED PREDICTOR → OUTCOME JOIN")
    print(rule())
    print("Outcome boundary: AUTHORIZED")
    print("Primary regression/inference permitted in this script: NO")
    print("Purpose: construct and audit the exact frozen H3 analytical panel.")

    prereg = load_preregistration()
    predictor, optional_map = load_predictor()

    server, database, username, password = load_environment()
    connection = connect_with_retry(
        server,
        database,
        username,
        password,
    )

    try:
        current_raw, next_raw = query_sql_sources(connection)

        current = prepare_current_universe(current_raw)
        next_rank = prepare_next_rank(next_raw)

        panel = build_panel(
            predictor=predictor,
            current=current,
            next_rank=next_rank,
            optional_map=optional_map,
        )

        print("")
        print(rule())
        print("STRUCTURAL JOIN AUDIT")
        print(rule())

        failures, audit_lines = audit_panel(
            predictor=predictor,
            current=current,
            next_rank=next_rank,
            panel=panel,
        )

        if failures:
            print("")
            print(rule())
            print("FINAL GATE")
            print(rule())
            print(f"Failed checks: {len(failures)}")
            print("H3_PRIMARY_MODEL_EXECUTION_REMAINS_BLOCKED")
            raise RuntimeError(
                "H3 predictor→outcome join failed structural audit. "
                "No analytical panel was materialized."
            )

        write_outputs(
            panel=panel,
            audit_lines=audit_lines,
            prereg=prereg,
        )

        materialize_sql(connection, panel)

        print("")
        print(rule())
        print("FINAL GATE")
        print(rule())
        print(f"Passed checks: {len([x for x in audit_lines if x.startswith('PASS:')])}")
        print("Failed checks: 0")
        print(f"Joined predictor rows: {len(panel):,}")
        print(
            f"H3A/H3C eligible rows: "
            f"{panel['h3a_h3c_eligible'].sum():,}"
        )
        print(
            f"H3B eligible rows: "
            f"{panel['h3b_eligible'].sum():,}"
        )
        print(
            f"H3B positive Winner-entry events: "
            f"{panel.loc[panel['h3b_eligible'].eq(1), 'winner_entry'].fillna(0).sum():,.0f}"
        )
        print(f"CSV panel: {PANEL_PATH.relative_to(ROOT)}")
        print(f"SQL table: {SQL_TABLE}")
        print(f"Audit report: {AUDIT_PATH.relative_to(ROOT)}")
        print(f"Manifest: {MANIFEST_PATH.relative_to(ROOT)}")
        print("Regression/inference executed: NO")
        print("H3_PREREGISTERED_PREDICTOR_OUTCOME_JOIN_INTEGRITY_AUDIT_PASSED")
        print("H3_PRIMARY_MODEL_EXECUTION_AUTHORIZED")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
