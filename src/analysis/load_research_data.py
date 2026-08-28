from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-28-v1-load-research-data"
ROOT = Path(__file__).resolve().parents[2]

SQL_PATH = ROOT / "sql" / "analytics" / "013_research_bindings.sql"
REPORT_PATH = ROOT / "reports" / "data_quality" / "research_data_load.txt"

H4_MINUTE = ROOT / "data" / "interim" / "h4_spy_1min_sip_2021_2025_primary_eligible.csv.gz"
H4_DAILY = ROOT / "data" / "interim" / "h4_spy_daily_sip_support_levels_2020_2025.csv"
H4_BAR5 = ROOT / "data" / "interim" / "h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz"
H4_ZONE = ROOT / "data" / "interim" / "h4_spy_5min_location_zones_preoutcome.csv"
H4_TRIGGER = ROOT / "data" / "interim" / "h4_spy_liquidity_sweep_triggers_preoutcome.csv"
H4_OUTCOME = ROOT / "data" / "interim" / "h4_spy_primary_liquidity_sweep_outcome_join.csv"
H4_RESULTS = ROOT / "reports" / "confirmatory" / "h4" / "h4_primary_confirmatory_results.csv"
H4_REPORT = ROOT / "reports" / "confirmatory" / "h4" / "h4_primary_confirmatory_report.txt"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def environment() -> tuple[str, str, str, str]:
    load_dotenv(ROOT / ".env")
    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )
    vals = tuple(os.getenv(n) for n in names)
    missing = [n for n, v in zip(names, vals) if not v]
    if missing:
        raise RuntimeError("Missing Azure SQL environment variables: " + ", ".join(missing))
    return vals  # type: ignore[return-value]


def odbc_escape(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def connect_with_retry(server: str, database: str, username: str, password: str):
    cs = (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={odbc_escape(database)};"
        f"UID={odbc_escape(username)};"
        f"PWD={odbc_escape(password)};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    for attempt in range(1, 6):
        try:
            c = pyodbc.connect(cs, timeout=30, autocommit=False)
            c.timeout = 600
            print(f"ODBC connection established on attempt {attempt} / 5.")
            return c
        except pyodbc.Error:
            if attempt == 5:
                raise
            time.sleep(15)
    raise RuntimeError("Connection retry loop ended unexpectedly.")


def sql_batches(text: str) -> list[str]:
    return [
        x.strip()
        for x in re.split(
            r"^\s*GO\s*(?:--.*)?$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if x.strip()
    ]


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def to_naive_et(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, utc=True)
    return dt.dt.tz_convert("America/New_York").dt.tz_localize(None)


def to_naive_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.tz_localize(None)


def scalar(cursor, sql: str, params=()) -> Any:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return None if row is None else row[0]


def columns(cursor, schema: str, obj: str) -> list[str]:
    cursor.execute(
        """
        SELECT c.name
        FROM sys.columns AS c
        JOIN sys.objects AS o ON o.object_id = c.object_id
        JOIN sys.schemas AS s ON s.schema_id = o.schema_id
        WHERE s.name = ? AND o.name = ?
        ORDER BY c.column_id;
        """,
        (schema, obj),
    )
    return [str(r[0]) for r in cursor.fetchall()]


def choose(cols: list[str], candidates: list[str], label: str) -> str:
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    raise RuntimeError(f"Could not identify {label}. Columns={cols}")


def dataframe_rows(df: pd.DataFrame, cols: list[str]):
    for row in df[cols].itertuples(index=False, name=None):
        out = []
        for v in row:
            if pd.isna(v):
                out.append(None)
            elif isinstance(v, np.generic):
                out.append(v.item())
            else:
                out.append(v)
        yield tuple(out)


def replace_table(cursor, table: str, insert_sql: str, rows, chunk_size: int = 25000):
    cursor.execute(f"DELETE FROM {table};")
    cursor.fast_executemany = True
    chunk = []
    count = 0
    for row in rows:
        chunk.append(row)
        if len(chunk) >= chunk_size:
            cursor.executemany(insert_sql, chunk)
            count += len(chunk)
            print(f"  {table}: {count:,} rows staged")
            chunk.clear()
    if chunk:
        cursor.executemany(insert_sql, chunk)
        count += len(chunk)
    print(f"  {table}: {count:,} total rows staged")
    return count


def load_h4(cursor) -> dict[str, int]:
    for p in [H4_MINUTE, H4_DAILY, H4_BAR5, H4_ZONE, H4_TRIGGER, H4_OUTCOME, H4_RESULTS, H4_REPORT]:
        if not p.exists():
            raise RuntimeError(f"Missing required H4 artifact: {p}")

    counts: dict[str, int] = {}

    minute = pd.read_csv(H4_MINUTE)
    minute["timestamp_utc"] = to_naive_utc(minute["timestamp_utc"])
    minute["timestamp_et"] = to_naive_et(minute["timestamp_et"])
    minute["session_open_et"] = to_naive_et(minute["session_open_et"])
    minute["session_close_et"] = to_naive_et(minute["session_close_et"])
    minute["session_date"] = pd.to_datetime(minute["session_date"]).dt.date
    minute["minute_index"] = (
        (minute["timestamp_et"] - minute["session_open_et"])
        .dt.total_seconds()
        .div(60)
        .astype(int)
    )

    mcols = [
        "session_date","minute_index","timestamp_utc","timestamp_et",
        "session_open_et","session_close_et","open","high","low","close",
        "volume","vwap","transactions",
    ]
    counts["h4_minute"] = replace_table(
        cursor,
        "research.h4_minute",
        """
        INSERT INTO research.h4_minute
        (session_date,minute_index,timestamp_utc,timestamp_et,session_open_et,
         session_close_et,[open],high,low,[close],volume,vwap,transactions)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        dataframe_rows(minute, mcols),
    )

    daily = pd.read_csv(H4_DAILY)
    daily["session_date"] = pd.to_datetime(daily["session_date"]).dt.date
    daily["week_start"] = pd.to_datetime(daily["week_start"]).dt.date
    dcols = [
        "session_date","open","high","low","close","volume","true_range",
        "atr14","atr14_prior","pdh","pdl","pwh","pwl","pmh","pml",
        "prior_all_time_high","prior_all_time_low","week_start","month_key",
    ]
    counts["h4_daily_level"] = replace_table(
        cursor,
        "research.h4_daily_level",
        """
        INSERT INTO research.h4_daily_level
        (session_date,[open],high,low,[close],volume,true_range,atr14,atr14_prior,
         pdh,pdl,pwh,pwl,pmh,pml,prior_all_time_high,prior_all_time_low,
         week_start,month_key)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        dataframe_rows(daily, dcols),
    )

    bar = pd.read_csv(H4_BAR5)
    bar["session_date"] = pd.to_datetime(bar["session_date"]).dt.date
    bar["bar_start_et"] = to_naive_et(bar["bar_start_et"])
    bar["bar_end_et"] = to_naive_et(bar["bar_end_et"])
    bcols = [
        "session_date","bar_index","bar_start_et","bar_end_et","open","high",
        "low","close","volume","vwap","transactions","session_vwap_through_bar",
        "atr14_prior","pdh","pdl","pwh","pwl","pmh","pml","prior_all_time_high",
        "rvol_prior20_median","rvol","rvol_elevated",
        "distance_from_session_vwap_atr","extension_above_prior_ath_atr",
        "price_discovery_close","ath_break_intrabar","log_return_5m",
        "realized_vol_30m","realized_vol_30m_prior20_median",
        "realized_vol_30m_ratio","displacement_3bar_atr",
        "opening_range_30m_high","opening_range_30m_low",
        "opening_range_extension_atr",
    ]
    counts["h4_bar_5m"] = replace_table(
        cursor,
        "research.h4_bar_5m",
        """
        INSERT INTO research.h4_bar_5m
        (session_date,bar_index,bar_start_et,bar_end_et,[open],high,low,[close],
         volume,vwap,transactions,session_vwap_through_bar,atr14_prior,pdh,pdl,
         pwh,pwl,pmh,pml,prior_all_time_high,rvol_prior20_median,rvol,
         rvol_elevated,distance_from_session_vwap_atr,
         extension_above_prior_ath_atr,price_discovery_close,ath_break_intrabar,
         log_return_5m,realized_vol_30m,realized_vol_30m_prior20_median,
         realized_vol_30m_ratio,displacement_3bar_atr,opening_range_30m_high,
         opening_range_30m_low,opening_range_extension_atr)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        dataframe_rows(bar, bcols),
    )

    zone = pd.read_csv(H4_ZONE)
    zone["session_date"] = pd.to_datetime(zone["session_date"]).dt.date
    zcols = [
        "zone_id","session_date","direction","zone_sequence","zone_lower",
        "zone_upper","atr14_prior","zone_half_width_atr","confluence_count",
        "confluence_status","families","constituent_levels",
        "min_constituent_level","max_constituent_level",
    ]
    counts["h4_zone"] = replace_table(
        cursor,
        "research.h4_zone",
        """
        INSERT INTO research.h4_zone
        (zone_id,session_date,direction,zone_sequence,zone_lower,zone_upper,
         atr14_prior,zone_half_width_atr,confluence_count,confluence_status,
         families,constituent_levels,min_constituent_level,max_constituent_level)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        dataframe_rows(zone, zcols),
    )

    trig = pd.read_csv(H4_TRIGGER)
    trig = trig[trig["liquidity_sweep_trigger"] == 1].copy()
    trig["session_date"] = pd.to_datetime(trig["session_date"]).dt.date
    trig["first_contact_bar_start_et"] = to_naive_et(trig["first_contact_bar_start_et"])
    trig["first_contact_bar_end_et"] = to_naive_et(trig["first_contact_bar_end_et"])
    tcols = [
        "event_id","zone_id","session_date","direction",
        "expected_rejection_direction","confluence_status","confluence_count",
        "families","atr14_prior","sweep_penetration_threshold_atr",
        "first_contact_bar_index","first_contact_bar_start_et",
        "first_contact_bar_end_et","first_contact_open","first_contact_high",
        "first_contact_low","first_contact_close","first_contact_volume",
        "session_vwap_through_bar","rvol","rvol_elevated",
        "distance_from_session_vwap_atr","realized_vol_30m",
        "realized_vol_30m_ratio","opening_range_extension_atr",
        "displacement_3bar_atr","price_discovery_close",
        "liquidity_sweep_trigger","qualifying_constituent_count",
        "qualifying_families","trigger_reference_family",
        "trigger_reference_level","penetration_atr",
        "rejection_close_distance_atr","horizon_15m_clock_eligible",
        "horizon_30m_clock_eligible","horizon_60m_clock_eligible",
    ]
    counts["h4_trigger"] = replace_table(
        cursor,
        "research.h4_trigger",
        """
        INSERT INTO research.h4_trigger
        (event_id,zone_id,session_date,direction,expected_rejection_direction,
         confluence_status,confluence_count,families,atr14_prior,
         sweep_penetration_threshold_atr,first_contact_bar_index,
         first_contact_bar_start_et,first_contact_bar_end_et,first_contact_open,
         first_contact_high,first_contact_low,first_contact_close,
         first_contact_volume,session_vwap_through_bar,rvol,rvol_elevated,
         distance_from_session_vwap_atr,realized_vol_30m,realized_vol_30m_ratio,
         opening_range_extension_atr,displacement_3bar_atr,
         price_discovery_close,liquidity_sweep_trigger,
         qualifying_constituent_count,qualifying_families,
         trigger_reference_family,trigger_reference_level,penetration_atr,
         rejection_close_distance_atr,horizon_15m_clock_eligible,
         horizon_30m_clock_eligible,horizon_60m_clock_eligible)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        dataframe_rows(trig, tcols),
    )

    outcome = pd.read_csv(H4_OUTCOME)
    ocols = [
        "event_id","raw_forward_return_15m","signed_forward_return_15m",
        "directional_success_15m","raw_forward_return_30m",
        "signed_forward_return_30m","directional_success_30m",
        "raw_forward_return_60m","signed_forward_return_60m",
        "directional_success_60m","mfe_30m","mae_30m",
    ]
    counts["h4_outcome"] = replace_table(
        cursor,
        "research.h4_outcome",
        """
        INSERT INTO research.h4_outcome
        (event_id,raw_forward_return_15m,signed_forward_return_15m,
         directional_success_15m,raw_forward_return_30m,
         signed_forward_return_30m,directional_success_30m,
         raw_forward_return_60m,signed_forward_return_60m,
         directional_success_60m,mfe_30m,mae_30m)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        dataframe_rows(outcome, ocols),
    )

    return counts


def create_h2_views(cursor) -> tuple[str, str]:
    source = "v_h2_sector_neutral_wml_forward_return_1m"
    cols = columns(cursor, "analytics", source)
    month_col = choose(
        cols,
        ["analysis_month_number", "ranking_month_number", "month_number"],
        "H2 analysis month",
    )
    date_col = choose(
        cols,
        ["ranking_month_end_date", "month_end_date", "ranking_date"],
        "H2 ranking month-end date",
    )
    value_col = choose(
        cols,
        [
            "winner_minus_loser_return_1m",
            "sector_neutral_wml_return_1m",
            "wml_forward_return_1m",
            "wml_return_1m",
            "forward_return_1m",
        ],
        "H2 WML return",
    )
    complete_col = choose(
        cols,
        [
            "forward_return_1m_complete",
            "wml_forward_return_1m_complete",
            "return_complete",
        ],
        "H2 completeness flag",
    )

    cursor.execute(
        f"""
        CREATE OR ALTER VIEW research.v_h2_primary_monthly
        AS
        SELECT
            CAST([{month_col}] AS int) AS analysis_month_number,
            CAST([{date_col}] AS date) AS ranking_month_end_date,
            CAST([{value_col}] AS float) AS value
        FROM analytics.{source}
        WHERE [{complete_col}] = 1;
        """
    )

    cursor.execute(
        """
        CREATE OR ALTER VIEW bi.vw_h2_wml
        AS
        SELECT *
        FROM research.v_h2_primary_monthly;
        """
    )

    cursor.execute(
        """
        CREATE OR ALTER VIEW bi.vw_h2_quintile
        AS
        SELECT *
        FROM analytics.v_h2_sector_quintile_forward_return_1m;
        """
    )
    return value_col, complete_col


def seed_results(cursor) -> None:
    # Replace only project result versions owned by this binding loader.
    cursor.execute(
        """
        DELETE FROM results.hypothesis_result
        WHERE result_version IN
        (
            'H1_CLOSEOUT_2026_08_24',
            'H2_CLOSEOUT_2026_08_24',
            'H3_PRIMARY_SQL_COPY_2026_08_28',
            'H4_PRIMARY_CONFIRMATORY_2026_08_28'
        );
        """
    )

    # H1: three frozen primary family components from the corrected closeout.
    h1_rows = [
        (
            "H1","WML_MEAN","H1_CLOSEOUT_2026_08_24",
            "2021-01-01","2025-12-31","Mean monthly WML return",
            0.00118,None,None,None,None,None,0.8351,1.0,
            "Holm",59,None,None,0.118,"percentage points per month",
            "NOT SUPPORTED","PRIMARY","Newey-West/HAC lag 3",
        ),
        (
            "H1","D10_EXCESS_SPY","H1_CLOSEOUT_2026_08_24",
            "2021-01-01","2025-12-31","Mean monthly D10 excess return versus SPY",
            -0.00076,None,None,None,None,None,0.8223,1.0,
            "Holm",59,None,None,-0.076,"percentage points per month",
            "NOT SUPPORTED","PRIMARY","Newey-West/HAC lag 3",
        ),
        (
            "H1","DECILE_SLOPE","H1_CLOSEOUT_2026_08_24",
            "2021-01-01","2025-12-31","Mean monthly cross-decile return slope",
            0.00010,None,None,None,None,None,0.8515,1.0,
            "Holm",59,None,None,0.010,"percentage points per decile per month",
            "NOT SUPPORTED","PRIMARY","Newey-West/HAC lag 3",
        ),
    ]

    insert = """
    INSERT INTO results.hypothesis_result
    (hypothesis_id,component,result_version,sample_start,sample_end,estimand,
     estimate,standard_error,ci_low,ci_high,test_statistic,reference_df,
     raw_p_value,adjusted_p_value,multiple_testing_method,n_observations,
     n_clusters_primary,n_clusters_secondary,economic_effect,economic_effect_unit,
     decision,primary_secondary,covariance_method)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
    """
    cursor.executemany(insert, h1_rows)

    # H2 frozen primary.
    cursor.execute(
        insert,
        (
            "H2","SECTOR_NEUTRAL_WML","H2_CLOSEOUT_2026_08_24",
            "2021-01-01","2025-12-31",
            "Mean monthly aggregate sector-neutral Winner-minus-Loser return",
            0.00186,None,-0.00654,0.00997,0.5182,None,0.6043,None,
            None,59,None,None,0.186,"percentage points per month",
            "NOT SUPPORTED","PRIMARY","Newey-West/HAC lag 3",
        ),
    )

    # H3 exact copy from the already materialized SQL result table.
    cursor.execute(
        """
        INSERT INTO results.hypothesis_result
        (hypothesis_id,component,result_version,sample_start,sample_end,estimand,
         estimate,standard_error,ci_low,ci_high,test_statistic,reference_df,
         raw_p_value,adjusted_p_value,multiple_testing_method,n_observations,
         n_clusters_primary,n_clusters_secondary,economic_effect,economic_effect_unit,
         decision,primary_secondary,covariance_method,preregistration_sha256)
        SELECT
            CASE component
                WHEN 'H3A_beta_A' THEN 'H3A'
                WHEN 'H3B_beta_B' THEN 'H3B'
                WHEN 'H3C_theta' THEN 'H3C'
            END,
            component,
            'H3_PRIMARY_SQL_COPY_2026_08_28',
            CAST('2021-01-01' AS date),
            CAST('2025-11-30' AS date),
            estimand_term,
            estimate,
            cluster_se,
            ci_low,
            ci_high,
            t_stat,
            reference_df,
            raw_p_value,
            holm_adjusted_p_value,
            'Holm',
            sample_rows,
            issuer_clusters,
            month_clusters,
            economic_effect_pp,
            'percentage points per +1 SD attention',
            decision,
            'PRIMARY',
            inference_method,
            '95e88d99f2b0c9beca50073844b9dadc32c11a6aa820fe04cf3ed12e94841506'
        FROM analytics.h3_primary_confirmatory_results;
        """
    )

    # H4 exact result CSV.
    h4 = pd.read_csv(H4_RESULTS)
    report_sha = sha256_file(H4_REPORT)
    for r in h4.itertuples(index=False):
        component = str(r.component)
        primary = str(r.primary_or_secondary)
        cursor.execute(
            """
            INSERT INTO results.hypothesis_result
            (hypothesis_id,component,result_version,sample_start,sample_end,estimand,
             estimate,standard_error,ci_low,ci_high,test_statistic,reference_df,
             raw_p_value,adjusted_p_value,multiple_testing_method,n_observations,
             n_clusters_primary,economic_effect,economic_effect_unit,decision,
             primary_secondary,covariance_method,source_report_path,
             source_report_sha256,preregistration_sha256)
            VALUES
            ('H4A',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                component,
                "H4_PRIMARY_CONFIRMATORY_2026_08_28",
                "2021-01-01",
                "2025-12-31",
                str(r.estimand),
                float(r.estimate),
                float(r.cluster_se),
                float(r.ci_95_low),
                float(r.ci_95_high),
                float(r.t_stat),
                int(r.reference_df),
                float(r.p_two_sided),
                None,
                None,
                int(r.events),
                int(r.session_clusters),
                float(r.economic_effect_percentage_points),
                "percentage points",
                str(r.decision),
                primary,
                "Session-clustered OLS mean",
                "reports/confirmatory/h4/h4_primary_confirmatory_report.txt",
                report_sha,
                "60d955f3ae6e625034c7cac41c08e20c0ce19bba4324e3877fdcaa824ef4eb88",
            ),
        )


def seed_breakdowns(cursor) -> None:
    cursor.execute(
        """
        DELETE FROM results.result_breakdown
        WHERE result_version IN
        (
            'H1_CLOSEOUT_2026_08_24',
            'H2_CLOSEOUT_2026_08_24',
            'H4_PRIMARY_CONFIRMATORY_2026_08_28'
        );
        """
    )

    # H1 series performance comes directly from validated SQL.
    cursor.execute(
        """
        INSERT INTO results.result_breakdown
        (hypothesis_id,result_version,breakdown_type,breakdown_value,
         metric_name,metric_value,n_observations)
        SELECT
            'H1',
            'H1_CLOSEOUT_2026_08_24',
            'SERIES',
            series_code,
            'annualized_return',
            annualized_return,
            observed_months
        FROM analytics.v_momentum_performance_summary;
        """
    )
    cursor.execute(
        """
        INSERT INTO results.result_breakdown
        (hypothesis_id,result_version,breakdown_type,breakdown_value,
         metric_name,metric_value,n_observations)
        SELECT
            'H1',
            'H1_CLOSEOUT_2026_08_24',
            'SERIES',
            series_code,
            'maximum_drawdown',
            maximum_drawdown,
            observed_months
        FROM analytics.v_momentum_performance_summary;
        """
    )

    # H2 documented quintile means.
    h2_q = {
        "Q1": 0.00905,
        "Q2": 0.00952,
        "Q3": 0.00902,
        "Q4": 0.01020,
        "Q5": 0.01091,
    }
    for q, value in h2_q.items():
        cursor.execute(
            """
            INSERT INTO results.result_breakdown
            (hypothesis_id,result_version,breakdown_type,breakdown_value,
             metric_name,metric_value,n_observations,notes)
            VALUES
            ('H2','H2_CLOSEOUT_2026_08_24','QUINTILE',?,
             'mean_monthly_return',?,59,
             'Frozen closeout summary; aggregate sector-neutral quintile.');
            """,
            (q, value),
        )

    # H4 yearly breakdown is computed directly from loaded event outcomes.
    cursor.execute(
        """
        INSERT INTO results.result_breakdown
        (hypothesis_id,result_version,breakdown_type,breakdown_value,
         metric_name,metric_value,n_observations)
        SELECT
            'H4A',
            'H4_PRIMARY_CONFIRMATORY_2026_08_28',
            'YEAR',
            CONVERT(varchar(4), YEAR(t.session_date)),
            'mean_signed_return_30m',
            AVG(o.signed_forward_return_30m),
            COUNT_BIG(*)
        FROM research.h4_trigger AS t
        JOIN research.h4_outcome AS o
          ON o.event_id = t.event_id
        WHERE
            t.liquidity_sweep_trigger = 1
            AND t.horizon_30m_clock_eligible = 1
        GROUP BY YEAR(t.session_date);
        """
    )


def seed_audit(cursor, run_id: int) -> None:
    # H4 infrastructure exclusions.
    for session_date in ("2021-05-05", "2023-06-05"):
        cursor.execute(
            """
            IF NOT EXISTS
            (
                SELECT 1
                FROM audit.exclusion
                WHERE hypothesis_id = 'H4A'
                  AND exclusion_scope = 'INTRADAY_SESSION'
                  AND entity_key = ?
            )
            INSERT INTO audit.exclusion
            (hypothesis_id,exclusion_scope,entity_key,start_date,end_date,
             reason_code,reason_description,source_reference,frozen)
            VALUES
            ('H4A','INTRADAY_SESSION',?,CAST(? AS date),CAST(? AS date),
             'MARKET_DATA_INFRASTRUCTURE_EXCEPTION',
             'Whole RTH session excluded under the frozen H4 infrastructure exception policy; no missing minute reconstruction.',
             'data/reference/h4/h4_intraday_data_exceptions_v1.json',1);
            """,
            (session_date, session_date, session_date, session_date),
        )

    artifacts = [
        ("H4 minute layer", H4_MINUTE, "DATASET"),
        ("H4 daily levels", H4_DAILY, "DATASET"),
        ("H4 5-minute layer", H4_BAR5, "DATASET"),
        ("H4 zones", H4_ZONE, "DATASET"),
        ("H4 triggers", H4_TRIGGER, "DATASET"),
        ("H4 outcome join", H4_OUTCOME, "DATASET"),
        ("H4 confirmatory result", H4_RESULTS, "RESULT"),
        ("H4 confirmatory report", H4_REPORT, "REPORT"),
    ]
    for name, path, typ in artifacts:
        cursor.execute(
            """
            INSERT INTO audit.artifact
            (run_id,hypothesis_id,artifact_name,artifact_type,repository_path,
             sha256,description)
            VALUES (?,?,?,?,?,?,?);
            """,
            (
                run_id,
                "H4A",
                name,
                typ,
                str(path.relative_to(ROOT)).replace("\\", "/"),
                sha256_file(path),
                "Loaded/reconciled by the SQL research-data binding pipeline.",
            ),
        )


def validate(cursor, counts: dict[str, int]) -> list[str]:
    failures: list[str] = []

    expected = {
        "research.h4_minute": 486870,
        "research.h4_bar_5m": 97374,
        "research.h4_outcome": 164,
    }

    for table, exp in expected.items():
        actual = int(scalar(cursor, f"SELECT COUNT_BIG(*) FROM {table};"))
        if actual != exp:
            failures.append(f"{table}: {actual:,} rows; expected {exp:,}")

    trigger_count = int(
        scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM research.h4_trigger
            WHERE liquidity_sweep_trigger = 1
              AND horizon_30m_clock_eligible = 1;
            """,
        )
    )
    if trigger_count != 164:
        failures.append(f"H4 primary trigger rows={trigger_count}; expected 164")

    h4_mean = float(
        scalar(
            cursor,
            """
            SELECT AVG(o.signed_forward_return_30m)
            FROM research.h4_trigger AS t
            JOIN research.h4_outcome AS o
              ON o.event_id = t.event_id
            WHERE
                t.liquidity_sweep_trigger = 1
                AND t.horizon_30m_clock_eligible = 1;
            """,
        )
    )
    if not np.isclose(h4_mean, -0.000613142249862, atol=1e-14, rtol=1e-12):
        failures.append(
            f"H4 SQL mean={h4_mean:.15g}; expected -0.000613142249862"
        )

    h4_sessions = int(
        scalar(
            cursor,
            """
            SELECT COUNT(DISTINCT session_date)
            FROM research.h4_trigger
            WHERE liquidity_sweep_trigger = 1
              AND horizon_30m_clock_eligible = 1;
            """,
        )
    )
    if h4_sessions != 156:
        failures.append(f"H4 sessions={h4_sessions}; expected 156")

    h3_rows = int(scalar(cursor, "SELECT COUNT_BIG(*) FROM research.v_h3_panel;"))
    if h3_rows != 29287:
        failures.append(f"H3 panel rows={h3_rows}; expected 29,287")

    result_rows = int(scalar(cursor, "SELECT COUNT_BIG(*) FROM results.hypothesis_result;"))
    if result_rows < 8:
        failures.append(f"Unified result rows={result_rows}; expected at least 8")

    return failures


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("SQL RESEARCH DATA BINDING + H4 MATERIALIZATION")
    print("=" * 124)

    if not SQL_PATH.exists():
        raise RuntimeError(f"Missing migration: {SQL_PATH}")

    server, database, username, password = environment()
    conn = connect_with_retry(server, database, username, password)
    cur = conn.cursor()
    run_id = None

    try:
        foundation = scalar(
            cur,
            """
            SELECT COUNT_BIG(*)
            FROM audit.pipeline_run
            WHERE pipeline_name = 'Research warehouse foundation'
              AND status = 'PASSED';
            """,
        )
        if int(foundation or 0) < 1:
            raise RuntimeError("Passed research-warehouse foundation run not found.")

        for i, batch in enumerate(sql_batches(SQL_PATH.read_text(encoding="utf-8")), start=1):
            cur.execute(batch)
            while cur.nextset():
                pass
            print(f"Applied SQL batch {i}.")
        conn.commit()

        cur.execute(
            """
            INSERT INTO audit.pipeline_run
            (pipeline_name,script_version,git_commit,started_at_utc,status,notes)
            OUTPUT INSERTED.run_id
            VALUES
            ('Research data binding',?,?,SYSUTCDATETIME(),'STARTED',
             'Materializes H4 and binds H1-H4 to unified research/results/bi layers.');
            """,
            (SCRIPT_VERSION, git_commit()),
        )
        run_id = int(cur.fetchone()[0])
        conn.commit()

        value_col, complete_col = create_h2_views(cur)
        print(
            "H2 binding discovered: "
            f"value={value_col}; complete={complete_col}"
        )

        counts = load_h4(cur)
        seed_results(cur)
        seed_breakdowns(cur)
        seed_audit(cur, run_id)

        failures = validate(cur, counts)

        checks = [
            ("H4 primary minute rows", 486870, int(scalar(cur, "SELECT COUNT_BIG(*) FROM research.h4_minute;"))),
            ("H4 5-minute rows", 97374, int(scalar(cur, "SELECT COUNT_BIG(*) FROM research.h4_bar_5m;"))),
            ("H4 primary outcomes", 164, int(scalar(cur, "SELECT COUNT_BIG(*) FROM research.h4_outcome;"))),
            ("H3 panel rows", 29287, int(scalar(cur, "SELECT COUNT_BIG(*) FROM research.v_h3_panel;"))),
        ]
        for name, exp, obs in checks:
            cur.execute(
                """
                INSERT INTO audit.quality_check
                (run_id,check_name,expected_value,observed_value,passed)
                VALUES (?,?,?,?,?);
                """,
                (run_id, name, str(exp), str(obs), int(exp == obs)),
            )

        cur.execute(
            """
            UPDATE audit.pipeline_run
            SET completed_at_utc = SYSUTCDATETIME(),
                status = ?,
                notes = ?
            WHERE run_id = ?;
            """,
            (
                "PASSED" if not failures else "FAILED",
                "H1-H4 research data binding complete."
                if not failures
                else "Binding validation failed; inspect report.",
                run_id,
            ),
        )

        if failures:
            conn.rollback()
        else:
            conn.commit()

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

        h4_mean = scalar(
            cur,
            """
            SELECT AVG(o.signed_forward_return_30m)
            FROM research.h4_trigger AS t
            JOIN research.h4_outcome AS o ON o.event_id = t.event_id
            WHERE t.liquidity_sweep_trigger = 1
              AND t.horizon_30m_clock_eligible = 1;
            """,
        ) if not failures else None

        lines = [
            f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
            "=" * 124,
            "SQL RESEARCH DATA BINDING + H4 MATERIALIZATION",
            "=" * 124,
            f"Database: {database}",
            f"H2 WML source value column: {value_col}",
            f"H2 WML completeness column: {complete_col}",
            f"H4 minute rows: {counts.get('h4_minute', 0):,}",
            f"H4 daily-level rows: {counts.get('h4_daily_level', 0):,}",
            f"H4 5-minute rows: {counts.get('h4_bar_5m', 0):,}",
            f"H4 zone rows: {counts.get('h4_zone', 0):,}",
            f"H4 trigger rows: {counts.get('h4_trigger', 0):,}",
            f"H4 outcome rows: {counts.get('h4_outcome', 0):,}",
            f"H4 SQL mean signed 30m return: "
            f"{'N/A' if h4_mean is None else f'{float(h4_mean):.12g}'}",
            f"Unified result rows: "
            f"{int(scalar(cur, 'SELECT COUNT_BIG(*) FROM results.hypothesis_result;')) if not failures else 'N/A'}",
            f"Result-breakdown rows: "
            f"{int(scalar(cur, 'SELECT COUNT_BIG(*) FROM results.result_breakdown;')) if not failures else 'N/A'}",
            "",
            f"FINAL SQL RESEARCH-DATA BINDING GATE: {'PASS' if not failures else 'FAIL'}",
        ]
        if failures:
            lines.extend(["", "FAILURES:"])
            lines.extend(f"- {x}" for x in failures)
        else:
            lines.extend(
                [
                    "",
                    "SQL_H1_H4_RESEARCH_DATA_BINDING_PASSED",
                    "SQL_H4_FROZEN_RESULT_REPRODUCED",
                    "POWER_BI_SEMANTIC_MODEL_BUILD_AUTHORIZED",
                ]
            )

        REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print()
        print(REPORT_PATH.read_text(encoding="utf-8"))

        if failures:
            raise RuntimeError("SQL research-data binding quality gate failed.")

    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        if run_id is not None:
            try:
                cur.execute(
                    """
                    UPDATE audit.pipeline_run
                    SET completed_at_utc = SYSUTCDATETIME(),
                        status = 'FAILED',
                        notes = ?
                    WHERE run_id = ?;
                    """,
                    (f"{type(exc).__name__}: {str(exc)[:1500]}", run_id),
                )
                conn.commit()
            except Exception:
                pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    main()
