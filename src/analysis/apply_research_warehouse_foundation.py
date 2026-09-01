from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pyodbc
import scipy
from scipy import stats
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-28-v1-research-warehouse-foundation-stat-reference"
ROOT = Path(__file__).resolve().parents[2]

.SQL_PATH = ROOT / "sql" / "schema" / "012_research_warehouse.sql"
REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_research_warehouse_foundation.txt"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

MIN_DF = 1
MAX_DF = 600
STAT_REFERENCE_VERSION = "2026-08-28-v1-adaptive-two-sided-grid"

# Adaptive p grid:
# - exact small tail anchors;
# - fine resolution near common significance thresholds;
# - coarser resolution where p is large;
# - SQL uses linear interpolation between adjacent critical values.
P_GRID = np.unique(
    np.concatenate(
        [
            np.array([1e-8, 1e-7, 1e-6, 1e-5, 5e-5], dtype=float),
            np.arange(0.0001, 0.0100001, 0.0001, dtype=float),
            np.arange(0.0105, 0.1000001, 0.0005, dtype=float),
            np.arange(0.101, 0.5000001, 0.001, dtype=float),
            np.arange(0.502, 1.0000001, 0.002, dtype=float),
        ]
    )
)

HYPOTHESES = [
    (
        "H1",
        None,
        "Canonical 12-1 Momentum",
        "Do higher canonical 12-1 momentum ranks predict higher next-month S&P 500 constituent returns?",
        "One-month gross forward returns of fixed monthly momentum portfolios.",
        "Frozen portfolio-level mean/HAC and related preregistered H1 inference.",
        0.05,
        "CLOSED_NOT_SUPPORTED",
        "2021-01-01",
        "2025-12-31",
        None,
        None,
        "Canonical market-wide momentum research branch.",
    ),
    (
        "H2",
        None,
        "Sector-Relative 12-1 Momentum",
        "Does ranking momentum within point-in-time GICS sectors produce a robust sector-neutral winner-minus-loser return?",
        "One-month gross forward returns from within-sector momentum portfolios.",
        "Frozen H2 sector-neutral time-series inference with HAC lag 3.",
        0.05,
        "CLOSED_NOT_SUPPORTED",
        "2021-01-01",
        "2025-12-31",
        None,
        None,
        "Sector-relative confirmatory branch.",
    ),
    (
        "H3A",
        "H3",
        "Attention Predicts Sector-Relative Return",
        "Does higher issuer news attention predict higher next-month leave-one-out sector-relative return?",
        "Next-month leave-one-out sector-relative security return.",
        "Fixed-effects panel; two-way cluster by issuer and outcome month; Holm family.",
        0.05,
        "CLOSED_NOT_SUPPORTED",
        "2021-01-01",
        "2025-11-30",
        "H3_STATISTICAL_PREREGISTRATION_V2",
        "95e88d99f2b0c9beca50073844b9dadc32c11a6aa820fe04cf3ed12e94841506",
        "Primary H3 component.",
    ),
    (
        "H3B",
        "H3",
        "Attention Predicts Winner Entry",
        "Does higher issuer news attention predict entry into the next-month canonical momentum Winner decile?",
        "Binary next-month Winner-entry indicator among current non-Winners.",
        "Linear probability fixed-effects panel; two-way cluster; Holm family.",
        0.05,
        "CLOSED_NOT_SUPPORTED",
        "2021-01-01",
        "2025-11-30",
        "H3_STATISTICAL_PREREGISTRATION_V2",
        "95e88d99f2b0c9beca50073844b9dadc32c11a6aa820fe04cf3ed12e94841506",
        "Nominal positive raw p-value did not survive Holm adjustment.",
    ),
    (
        "H3C",
        "H3",
        "Attention Increment for Current Winners",
        "Does issuer news attention have an incremental positive return effect among current momentum Winners?",
        "Next-month leave-one-out sector-relative security return.",
        "Fixed-effects interaction panel; two-way cluster; Holm family.",
        0.05,
        "CLOSED_NOT_SUPPORTED",
        "2021-01-01",
        "2025-11-30",
        "H3_STATISTICAL_PREREGISTRATION_V2",
        "95e88d99f2b0c9beca50073844b9dadc32c11a6aa820fe04cf3ed12e94841506",
        "Primary H3 interaction component.",
    ),
    (
        "H3",
        None,
        "Issuer News Attention",
        "Does issuer-level news attention contain preregistered predictive information for momentum-related future outcomes?",
        "H3A/H3B/H3C component outcomes.",
        "Three-component Holm-Bonferroni family; no global binary H3 decision.",
        0.05,
        "COMPLETE_COMPONENTS_NOT_SUPPORTED",
        "2021-01-01",
        "2025-11-30",
        "H3_STATISTICAL_PREREGISTRATION_V2",
        "95e88d99f2b0c9beca50073844b9dadc32c11a6aa820fe04cf3ed12e94841506",
        "Parent metadata row for the three H3 components.",
    ),
    (
        "H4A",
        None,
        "Liquidity Sweep/Rejection Reversal",
        "Does a first-contact ATR-scaled support/resistance liquidity sweep with same-bar rejection predict reversal over the next 30 minutes?",
        "Signed 30-minute SPY gross price return; positive means preregistered rejection direction.",
        "Intercept-only OLS mean with session-clustered covariance, small-sample correction, two-sided alpha 0.05.",
        0.05,
        "CLOSED_CONTRADICTED",
        "2021-01-01",
        "2025-12-31",
        "H4_PRIMARY_LIQUIDITY_SWEEP_INFERENCE_V1",
        "60d955f3ae6e625034c7cac41c08e20c0ce19bba4324e3877fdcaa824ef4eb88",
        "Primary H4A reversal hypothesis; continuation is not retroactively substituted.",
    ),
]

VARIABLES = [
    ("momentum_12_1", "12-1 momentum", "Canonical return from the month -12 anchor through the month -1 anchor, skipping the ranking month.", "security x month", "decimal return", "adjusted_close(t-1) / adjusted_close(t-12) - 1", 1, "analytics.v_security_monthly_return_features", "momentum_12_1", "Primary H1/H2 ranking signal."),
    ("momentum_decile", "Momentum decile", "Cross-sectional canonical momentum decile, D01 through D10.", "security x ranking month", "decile", "Deterministic NTILE(10) over the frozen monthly momentum ranking.", 1, "analytics.v_security_monthly_momentum_ranking", "momentum_decile", "D10 is Winner; D01 is Loser."),
    ("forward_return_1m", "One-month forward return", "Gross holding-period return after the ranking month, with documented terminal-exit treatment.", "security x ranking month", "decimal return", "holding_end_adjusted_close / holding_start_adjusted_close - 1", 0, "analytics.v_security_monthly_forward_return_1m", "forward_return_1m", "Outcome variable; never used to construct the ranking."),
    ("gics_sector", "Point-in-time GICS sector", "Sector classification aligned to the ranking month.", "security x month", "category", "Point-in-time sector-history mapping.", 1, "analytics.security_month_end_gics_sector", "gics_sector", "Used for H2 and H3 sector-relative outcomes."),
    ("sector_momentum_quintile", "Sector momentum quintile", "Within-sector canonical momentum quintile.", "security x month x sector", "quintile", "Rank momentum within PIT GICS sector and divide into five groups.", 1, "analytics.v_security_monthly_sector_momentum_ranking", "sector_momentum_quintile", "H2 ranking variable."),
    ("sector_relative_return", "Sector-relative return", "Security forward return minus leave-one-out equal-weight mean of valid same-sector peers.", "security x month", "decimal return", "security_forward_return - mean(other valid same-sector forward returns)", 0, "analytics.h3_preregistered_predictor_outcome_panel", "sector_relative_return", "H3A/H3C outcome."),
    ("attention_z", "Issuer attention z-score", "Monthly issuer-level standardized log news-attention measure.", "issuer x predictor month, mapped to security rows", "standard deviations", "Cross-sectional monthly z-score of frozen issuer attention transformation.", 1, "analytics.h3_preregistered_predictor_outcome_panel", "attention_z", "Primary H3 predictor."),
    ("winner_entry", "Next-month Winner entry", "Indicator that a current non-D10 security enters D10 at t+1.", "security x predictor month", "0/1", "1 when next-month canonical momentum decile = D10; otherwise 0.", 0, "analytics.h3_preregistered_predictor_outcome_panel", "winner_entry", "H3B outcome."),
    ("current_winner", "Current Winner", "Indicator for canonical momentum D10 at predictor month t.", "security x predictor month", "0/1", "1 when current canonical momentum decile = D10.", 1, "analytics.h3_preregistered_predictor_outcome_panel", "current_winner", "H3C interaction variable."),
    ("atr14_prior", "Prior-session ATR(14)", "Wilder ATR(14) computed only through the prior completed trading session.", "SPY session", "price", "Wilder recursive ATR based on daily true range, lagged one session.", 1, None, "atr14_prior", "H4 volatility normalizer."),
    ("pdh", "Previous-day high", "High of the immediately previous completed trading session.", "SPY session", "price", "Lagged daily high.", 1, None, "pdh", "H4 resistance family."),
    ("pdl", "Previous-day low", "Low of the immediately previous completed trading session.", "SPY session", "price", "Lagged daily low.", 1, None, "pdl", "H4 support family."),
    ("pwh", "Previous-week high", "High of the immediately previous completed trading week.", "SPY session", "price", "Maximum daily high in prior completed calendar week.", 1, None, "pwh", "H4 resistance family."),
    ("pwl", "Previous-week low", "Low of the immediately previous completed trading week.", "SPY session", "price", "Minimum daily low in prior completed calendar week.", 1, None, "pwl", "H4 support family."),
    ("pmh", "Previous-month high", "High of the immediately previous completed calendar month.", "SPY session", "price", "Maximum daily high in prior completed calendar month.", 1, None, "pmh", "H4 resistance family."),
    ("pml", "Previous-month low", "Low of the immediately previous completed calendar month.", "SPY session", "price", "Minimum daily low in prior completed calendar month.", 1, None, "pml", "H4 support family."),
    ("rvol", "Relative volume", "Current 5-minute volume divided by the median same-time bucket volume across the prior 20 valid sessions.", "SPY x 5-minute bar", "ratio", "volume / prior20_same_bucket_median_volume", 1, None, "rvol", "H4 context, not primary trigger."),
    ("session_vwap_through_bar", "Session VWAP", "Cumulative provider-volume-weighted VWAP through the completed 5-minute bar.", "SPY x 5-minute bar", "price", "cumulative sum(minute_vwap * minute_volume) / cumulative volume", 1, None, "session_vwap_through_bar", "H4 contemporaneous context."),
    ("liquidity_sweep_trigger", "Liquidity sweep/rejection trigger", "Frozen H4 first-contact same-bar penetration and rejection indicator.", "SPY x merged S/R zone x session", "0/1", "0.02*prior ATR penetration beyond a constituent level plus same-bar close back across that level.", 1, None, "liquidity_sweep_trigger", "Primary H4A predictor/event definition."),
    ("signed_forward_return_30m", "Signed 30-minute return", "30-minute return signed so positive means movement in the preregistered rejection direction.", "H4 event", "decimal return", "direction_sign * (endpoint_close / trigger_close - 1)", 0, None, "signed_forward_return_30m", "Primary H4A outcome."),
    ("mfe_30m", "30-minute MFE", "Maximum favorable signed excursion during the six bars after the trigger.", "H4 event", "decimal return", "Maximum favorable signed high/low excursion relative to trigger close.", 0, None, "mfe_30m", "Descriptive H4 outcome."),
    ("mae_30m", "30-minute MAE", "Maximum adverse signed excursion during the six bars after the trigger.", "H4 event", "decimal return", "Maximum adverse signed high/low excursion relative to trigger close.", 0, None, "mae_30m", "Descriptive H4 outcome."),
]

HYPOTHESIS_VARIABLES = {
    "H1": [
        ("momentum_12_1", "PREDICTOR"),
        ("momentum_decile", "RANKING"),
        ("forward_return_1m", "OUTCOME"),
    ],
    "H2": [
        ("momentum_12_1", "PREDICTOR"),
        ("gics_sector", "CONTROL"),
        ("sector_momentum_quintile", "RANKING"),
        ("forward_return_1m", "OUTCOME"),
    ],
    "H3A": [
        ("attention_z", "PREDICTOR"),
        ("sector_relative_return", "OUTCOME"),
        ("momentum_decile", "CONTROL"),
        ("gics_sector", "CONTROL"),
    ],
    "H3B": [
        ("attention_z", "PREDICTOR"),
        ("winner_entry", "OUTCOME"),
        ("momentum_decile", "CONTROL"),
    ],
    "H3C": [
        ("attention_z", "PREDICTOR"),
        ("current_winner", "PREDICTOR"),
        ("sector_relative_return", "OUTCOME"),
        ("momentum_decile", "CONTROL"),
    ],
    "H4A": [
        ("atr14_prior", "CONTEXT"),
        ("pdh", "CONTEXT"),
        ("pdl", "CONTEXT"),
        ("pwh", "CONTEXT"),
        ("pwl", "CONTEXT"),
        ("pmh", "CONTEXT"),
        ("pml", "CONTEXT"),
        ("rvol", "CONTEXT"),
        ("session_vwap_through_bar", "CONTEXT"),
        ("liquidity_sweep_trigger", "PREDICTOR"),
        ("signed_forward_return_30m", "OUTCOME"),
        ("mfe_30m", "ROBUSTNESS"),
        ("mae_30m", "ROBUSTNESS"),
    ],
}

KNOWN_T_TESTS = [
    ("H3A", -0.92143255, 57, 0.360708306955),
    ("H3B", 2.05119515, 57, 0.0448539853732),
    ("H4A", -2.12253472, 155, 0.0353817887367),
]


def rule(width: int = 124) -> str:
    return "=" * width


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
            f"{ODBC_DRIVER} not installed. Available: {pyodbc.drivers()}"
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
        "08001", "08s01", "hyt00", "40613", "timeout",
        "not currently available", "unable to establish connection",
        "temporarily unavailable", "communication link failure", "10053",
    )

    for attempt in range(1, 6):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=False,
            )
            connection.timeout = 120
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
                f"ODBC attempt {attempt} / 5 failed. "
                "Retrying in 15 seconds."
            )
            time.sleep(15)

    raise RuntimeError("Connection retry loop ended unexpectedly.")


def sql_batches(sql_text: str) -> list[str]:
    return [
        x.strip()
        for x in re.split(
            r"^\s*GO\s*(?:--.*)?$",
            sql_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if x.strip()
    ]


def git_commit() -> str | None:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return value or None
    except Exception:
        return None


def chunked(rows: list[tuple], size: int) -> Iterable[list[tuple]]:
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def build_t_rows() -> list[tuple[int, float, float]]:
    rows: list[tuple[int, float, float]] = []
    for df in range(MIN_DF, MAX_DF + 1):
        critical = stats.t.ppf(1.0 - P_GRID / 2.0, df=df)
        rows.extend(
            (df, float(p), float(t))
            for p, t in zip(P_GRID, critical)
        )
    return rows


def build_normal_rows() -> list[tuple[float, float]]:
    critical = stats.norm.ppf(1.0 - P_GRID / 2.0)
    return [
        (float(p), float(z))
        for p, z in zip(P_GRID, critical)
    ]


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print(rule())
    print("AZURE SQL RESEARCH WAREHOUSE + STATISTICAL REFERENCE FOUNDATION")
    print(rule())

    if not SQL_PATH.exists():
        raise RuntimeError(f"Missing migration: {SQL_PATH}")

    server, database, username, password = environment()
    connection = connect_with_retry(server, database, username, password)
    cursor = connection.cursor()
    failures: list[str] = []

    started = datetime.now(timezone.utc).replace(microsecond=0)
    current_git = git_commit()

    try:
        # 1. Non-destructive schema migration.
        batches = sql_batches(SQL_PATH.read_text(encoding="utf-8"))
        for i, batch in enumerate(batches, start=1):
            cursor.execute(batch)
            while cursor.nextset():
                pass
            print(f"Applied SQL batch {i} / {len(batches)}.")
        connection.commit()

        # 2. Start an audit run after the audit schema exists.
        cursor.execute(
            """
            INSERT INTO audit.pipeline_run
            (
                pipeline_name,
                script_version,
                git_commit,
                started_at_utc,
                status,
                notes
            )
            OUTPUT INSERTED.run_id
            VALUES (?, ?, ?, ?, 'STARTED', ?);
            """,
            (
                "Research warehouse foundation",
                SCRIPT_VERSION,
                current_git,
                started.replace(tzinfo=None),
                "Creates non-destructive research/reporting schemas and statistical lookup references.",
            ),
        )
        run_id = int(cursor.fetchone()[0])
        connection.commit()

        # 3. Seed hypothesis metadata. Parent H3 must exist before H3A/B/C.
        ordered_hypotheses = sorted(
            HYPOTHESES,
            key=lambda x: (x[1] is not None, x[0]),
        )
        merge_h = """
        MERGE ref.hypothesis AS target
        USING
        (
            SELECT
                ? AS hypothesis_id,
                ? AS parent_hypothesis_id,
                ? AS hypothesis_name,
                ? AS research_question,
                ? AS primary_outcome,
                ? AS primary_test,
                ? AS alpha,
                ? AS status,
                CAST(? AS date) AS sample_start,
                CAST(? AS date) AS sample_end,
                ? AS preregistration_version,
                ? AS preregistration_sha256,
                ? AS notes
        ) AS source
        ON target.hypothesis_id = source.hypothesis_id
        WHEN MATCHED THEN UPDATE SET
            parent_hypothesis_id = source.parent_hypothesis_id,
            hypothesis_name = source.hypothesis_name,
            research_question = source.research_question,
            primary_outcome = source.primary_outcome,
            primary_test = source.primary_test,
            alpha = source.alpha,
            status = source.status,
            sample_start = source.sample_start,
            sample_end = source.sample_end,
            preregistration_version = source.preregistration_version,
            preregistration_sha256 = source.preregistration_sha256,
            notes = source.notes,
            updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN
            INSERT
            (
                hypothesis_id, parent_hypothesis_id, hypothesis_name,
                research_question, primary_outcome, primary_test, alpha,
                status, sample_start, sample_end, preregistration_version,
                preregistration_sha256, notes
            )
            VALUES
            (
                source.hypothesis_id, source.parent_hypothesis_id,
                source.hypothesis_name, source.research_question,
                source.primary_outcome, source.primary_test, source.alpha,
                source.status, source.sample_start, source.sample_end,
                source.preregistration_version,
                source.preregistration_sha256, source.notes
            );
        """
        for row in ordered_hypotheses:
            cursor.execute(merge_h, row)

        # 4. Seed variable catalog.
        merge_v = """
        MERGE ref.variable_catalog AS target
        USING
        (
            SELECT
                ? AS variable_name,
                ? AS display_name,
                ? AS description,
                ? AS grain,
                ? AS unit,
                ? AS formula_description,
                CAST(? AS bit) AS lookahead_safe,
                ? AS source_object,
                ? AS source_column,
                ? AS educational_notes
        ) AS source
        ON target.variable_name = source.variable_name
        WHEN MATCHED THEN UPDATE SET
            display_name = source.display_name,
            description = source.description,
            grain = source.grain,
            unit = source.unit,
            formula_description = source.formula_description,
            lookahead_safe = source.lookahead_safe,
            source_object = source.source_object,
            source_column = source.source_column,
            educational_notes = source.educational_notes
        WHEN NOT MATCHED THEN
            INSERT
            (
                variable_name, display_name, description, grain, unit,
                formula_description, lookahead_safe, source_object,
                source_column, educational_notes
            )
            VALUES
            (
                source.variable_name, source.display_name, source.description,
                source.grain, source.unit, source.formula_description,
                source.lookahead_safe, source.source_object,
                source.source_column, source.educational_notes
            );
        """
        for row in VARIABLES:
            cursor.execute(merge_v, row)

        # 5. Seed hypothesis-variable mapping.
        cursor.execute(
            "SELECT variable_id, variable_name FROM ref.variable_catalog;"
        )
        variable_ids = {
            str(name): int(variable_id)
            for variable_id, name in cursor.fetchall()
        }

        merge_map = """
        MERGE ref.hypothesis_variable_map AS target
        USING
        (
            SELECT
                ? AS hypothesis_id,
                ? AS variable_id,
                ? AS variable_role
        ) AS source
        ON target.hypothesis_id = source.hypothesis_id
       AND target.variable_id = source.variable_id
       AND target.variable_role = source.variable_role
        WHEN NOT MATCHED THEN
            INSERT (hypothesis_id, variable_id, variable_role)
            VALUES
            (source.hypothesis_id, source.variable_id, source.variable_role);
        """
        for hypothesis_id, mappings in HYPOTHESIS_VARIABLES.items():
            for variable_name, role in mappings:
                cursor.execute(
                    merge_map,
                    (
                        hypothesis_id,
                        variable_ids[variable_name],
                        role,
                    ),
                )

        connection.commit()

        # 6. Generate and populate statistical references.
        print(
            f"Generating Student-t lookup: df {MIN_DF}-{MAX_DF}, "
            f"{len(P_GRID):,} probability points per df."
        )
        t_rows = build_t_rows()
        normal_rows = build_normal_rows()

        expected_t_rows = (MAX_DF - MIN_DF + 1) * len(P_GRID)

        cursor.execute("DELETE FROM ref.student_t_two_sided_lookup;")
        cursor.execute("DELETE FROM ref.normal_two_sided_lookup;")
        connection.commit()

        insert_t = """
        INSERT INTO ref.student_t_two_sided_lookup
        (degrees_freedom, two_sided_p, critical_abs_t)
        VALUES (?, ?, ?);
        """
        cursor.fast_executemany = True
        loaded = 0
        for chunk in chunked(t_rows, 20000):
            cursor.executemany(insert_t, chunk)
            loaded += len(chunk)
            if loaded % 100000 < len(chunk):
                print(f"  Student-t rows staged: {loaded:,} / {expected_t_rows:,}")
        connection.commit()

        insert_n = """
        INSERT INTO ref.normal_two_sided_lookup
        (two_sided_p, critical_abs_z)
        VALUES (?, ?);
        """
        cursor.executemany(insert_n, normal_rows)
        connection.commit()

        now = datetime.now(timezone.utc).replace(microsecond=0).replace(tzinfo=None)

        for reference_name, min_df, max_df in [
            ("STUDENT_T_TWO_SIDED", MIN_DF, MAX_DF),
            ("STANDARD_NORMAL_TWO_SIDED", None, None),
        ]:
            cursor.execute(
                """
                MERGE ref.statistical_reference_metadata AS target
                USING
                (
                    SELECT
                        ? AS reference_name,
                        ? AS generation_version,
                        ? AS scipy_version,
                        ? AS min_df,
                        ? AS max_df,
                        ? AS probability_points,
                        ? AS interpolation_method,
                        ? AS notes,
                        ? AS generated_at_utc
                ) AS source
                ON target.reference_name = source.reference_name
                WHEN MATCHED THEN UPDATE SET
                    generation_version = source.generation_version,
                    scipy_version = source.scipy_version,
                    min_df = source.min_df,
                    max_df = source.max_df,
                    probability_points = source.probability_points,
                    interpolation_method = source.interpolation_method,
                    notes = source.notes,
                    generated_at_utc = source.generated_at_utc
                WHEN NOT MATCHED THEN
                    INSERT
                    (
                        reference_name, generation_version, scipy_version,
                        min_df, max_df, probability_points,
                        interpolation_method, notes, generated_at_utc
                    )
                    VALUES
                    (
                        source.reference_name, source.generation_version,
                        source.scipy_version, source.min_df, source.max_df,
                        source.probability_points,
                        source.interpolation_method, source.notes,
                        source.generated_at_utc
                    );
                """,
                (
                    reference_name,
                    STAT_REFERENCE_VERSION,
                    scipy.__version__,
                    min_df,
                    max_df,
                    len(P_GRID),
                    "Linear interpolation between adjacent precomputed inverse-CDF critical values.",
                    (
                        "Generated locally with SciPy and persisted in Azure SQL. "
                        "The SQL layer requires no statistical runtime library."
                    ),
                    now,
                ),
            )
        connection.commit()

        # 7. Validation.
        cursor.execute(
            "SELECT COUNT_BIG(*) FROM ref.student_t_two_sided_lookup;"
        )
        actual_t_rows = int(cursor.fetchone()[0])

        cursor.execute(
            "SELECT COUNT_BIG(*) FROM ref.normal_two_sided_lookup;"
        )
        actual_n_rows = int(cursor.fetchone()[0])

        checks: list[tuple[str, bool, str, str]] = []

        checks.append(
            (
                "Student-t lookup row count",
                actual_t_rows == expected_t_rows,
                f"{expected_t_rows}",
                f"{actual_t_rows}",
            )
        )
        checks.append(
            (
                "Normal lookup row count",
                actual_n_rows == len(P_GRID),
                f"{len(P_GRID)}",
                f"{actual_n_rows}",
            )
        )

        required_schemas = {"ref", "research", "results", "audit", "bi"}
        cursor.execute(
            """
            SELECT name
            FROM sys.schemas
            WHERE name IN ('ref','research','results','audit','bi');
            """
        )
        actual_schemas = {str(x[0]) for x in cursor.fetchall()}
        checks.append(
            (
                "Research/reporting schemas present",
                actual_schemas == required_schemas,
                ",".join(sorted(required_schemas)),
                ",".join(sorted(actual_schemas)),
            )
        )

        cursor.execute("SELECT COUNT(*) FROM ref.hypothesis;")
        hypothesis_count = int(cursor.fetchone()[0])
        checks.append(
            (
                "Hypothesis metadata seeded",
                hypothesis_count >= 7,
                ">=7",
                str(hypothesis_count),
            )
        )

        cursor.execute("SELECT COUNT(*) FROM ref.variable_catalog;")
        variable_count = int(cursor.fetchone()[0])
        checks.append(
            (
                "Variable catalog seeded",
                variable_count >= len(VARIABLES),
                f">={len(VARIABLES)}",
                str(variable_count),
            )
        )

        p_test_rows = []
        for label, t_stat, df, true_p in KNOWN_T_TESTS:
            cursor.execute(
                "SELECT ref.fn_student_t_two_sided_p(?, ?);",
                (t_stat, df),
            )
            sql_p = float(cursor.fetchone()[0])
            abs_error = abs(sql_p - true_p)
            p_test_rows.append(
                (label, t_stat, df, true_p, sql_p, abs_error)
            )
            checks.append(
                (
                    f"{label} Student-t p lookup",
                    abs_error <= 0.00001,
                    f"{true_p:.12g} ± 0.00001",
                    f"{sql_p:.12g}",
                )
            )

        # Critical value at the H4A 95% CI setting.
        cursor.execute(
            "SELECT ref.fn_student_t_critical(155, 0.05);"
        )
        sql_crit = float(cursor.fetchone()[0])
        scipy_crit = float(stats.t.ppf(0.975, df=155))
        checks.append(
            (
                "Student-t 95% critical value df=155",
                abs(sql_crit - scipy_crit) <= 1e-10,
                f"{scipy_crit:.12g}",
                f"{sql_crit:.12g}",
            )
        )

        # Existing analytical foundation should remain present.
        expected_existing = [
            ("analytics", "v_security_monthly_return_features"),
            ("analytics", "v_security_monthly_momentum_ranking"),
            ("analytics", "v_security_monthly_forward_return_1m"),
            ("analytics", "security_month_end_gics_sector"),
            ("analytics", "v_security_monthly_sector_momentum_ranking"),
            ("analytics", "h3_preregistered_predictor_outcome_panel"),
        ]
        for schema_name, object_name in expected_existing:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM sys.objects AS o
                JOIN sys.schemas AS s
                  ON s.schema_id = o.schema_id
                WHERE s.name = ? AND o.name = ?;
                """,
                (schema_name, object_name),
            )
            present = int(cursor.fetchone()[0]) == 1
            checks.append(
                (
                    f"Existing dependency {schema_name}.{object_name}",
                    present,
                    "present",
                    "present" if present else "missing",
                )
            )

        for name, passed, expected, observed in checks:
            cursor.execute(
                """
                INSERT INTO audit.quality_check
                (run_id, check_name, expected_value, observed_value, passed)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    name,
                    expected,
                    observed,
                    int(passed),
                ),
            )
            if not passed:
                failures.append(
                    f"{name}: expected {expected}; observed {observed}"
                )

        final_status = "PASSED" if not failures else "FAILED"
        cursor.execute(
            """
            UPDATE audit.pipeline_run
            SET
                completed_at_utc = SYSUTCDATETIME(),
                status = ?,
                notes = ?
            WHERE run_id = ?;
            """,
            (
                final_status,
                (
                    "Foundation and statistical reference validation complete."
                    if not failures
                    else "Foundation validation failed; see audit.quality_check."
                ),
                run_id,
            ),
        )
        connection.commit()

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

        report_lines = [
            f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
            rule(),
            "AZURE SQL RESEARCH WAREHOUSE + STATISTICAL REFERENCE FOUNDATION",
            rule(),
            f"Database: {database}",
            f"Git commit: {current_git or 'UNAVAILABLE'}",
            f"New schemas: ref, research, results, audit, bi",
            f"Probability grid points: {len(P_GRID):,}",
            f"Student-t df range: {MIN_DF}-{MAX_DF}",
            f"Expected Student-t lookup rows: {expected_t_rows:,}",
            f"Observed Student-t lookup rows: {actual_t_rows:,}",
            f"Normal lookup rows: {actual_n_rows:,}",
            f"Hypothesis metadata rows: {hypothesis_count:,}",
            f"Variable catalog rows: {variable_count:,}",
            "",
            "STATISTICAL LOOKUP VALIDATION",
        ]

        for label, t_stat, df, true_p, sql_p, abs_error in p_test_rows:
            report_lines.append(
                f"{label}: t={t_stat:.8f}, df={df}, "
                f"SciPy p={true_p:.12g}, SQL lookup p={sql_p:.12g}, "
                f"abs error={abs_error:.3g}"
            )

        report_lines.extend(
            [
                "",
                "QUALITY CHECKS",
            ]
        )
        for name, passed, expected, observed in checks:
            report_lines.append(
                f"{'PASS' if passed else 'FAIL'}: {name} "
                f"[expected={expected}; observed={observed}]"
            )

        report_lines.extend(
            [
                "",
                f"FINAL RESEARCH-WAREHOUSE FOUNDATION GATE: "
                f"{'PASS' if not failures else 'FAIL'}",
            ]
        )

        if failures:
            report_lines.extend(["", "FAILURES:"])
            report_lines.extend(f"- {x}" for x in failures)
        else:
            report_lines.extend(
                [
                    "",
                    "AZURE_SQL_RESEARCH_WAREHOUSE_FOUNDATION_PASSED",
                    "SQL_STATISTICAL_REFERENCE_LAYER_READY",
                    "SQL_H1_H4_EDUCATIONAL_BINDING_AUTHORIZED",
                ]
            )

        REPORT_PATH.write_text(
            "\n".join(report_lines) + "\n",
            encoding="utf-8",
        )
        print()
        print(REPORT_PATH.read_text(encoding="utf-8"))

        if failures:
            raise RuntimeError(
                "Research warehouse foundation quality gate failed."
            )

    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        connection.close()


if __name__ == "__main__":
    main()
