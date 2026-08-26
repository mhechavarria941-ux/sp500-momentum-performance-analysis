from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv
from scipy import stats

try:
    import statsmodels.formula.api as smf
    from statsmodels.stats.sandwich_covariance import cov_cluster
except ImportError as exc:
    raise RuntimeError(
        "statsmodels is required for the frozen H3 panel regressions. "
        "Install it in the project environment before running this script."
    ) from exc


SCRIPT_VERSION = "2026-08-26-v2-h3-primary-confirmatory-inference-pre-model-gate-fix"

ROOT = Path(__file__).resolve().parents[2]
H3_DIR = ROOT / "reports" / "confirmatory" / "h3"

PREREG_PATH = (
    ROOT / "data" / "reference" / "h3" / "h3_statistical_preregistration_v2.json"
)
JOIN_MANIFEST_PATH = (
    H3_DIR / "h3_preregistered_predictor_outcome_join_manifest.json"
)
JOIN_AUDIT_PATH = (
    H3_DIR / "h3_preregistered_predictor_outcome_join_audit.txt"
)
JOIN_PANEL_CSV_PATH = (
    H3_DIR / "h3_preregistered_predictor_outcome_panel.csv"
)

RESULTS_CSV_PATH = H3_DIR / "h3_primary_confirmatory_results.csv"
REPORT_PATH = H3_DIR / "h3_primary_confirmatory_report.txt"
MANIFEST_PATH = H3_DIR / "h3_primary_confirmatory_manifest.json"

SQL_PANEL = "analytics.h3_preregistered_predictor_outcome_panel"
SQL_RESULTS = "analytics.h3_primary_confirmatory_results"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXPECTED_JOIN_ROWS = 29_287
EXPECTED_PREDICTOR_MONTHS = 58
EXPECTED_ISSUER_CLUSTERS = 583
EXPECTED_H3AC_ROWS = 29_114
EXPECTED_H3B_ROWS = 26_139
EXPECTED_H3B_POSITIVE_EVENTS = 807

ALPHA = 0.05
HOLM_FAMILY = ("H3A_beta_A", "H3B_beta_B", "H3C_theta")


def rule(width: int = 140) -> str:
    return "=" * width


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def load_preregistration() -> dict[str, Any]:
    if not PREREG_PATH.exists():
        raise RuntimeError(f"Missing frozen preregistration: {PREREG_PATH}")

    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))

    checks = [
        (
            prereg.get("preregistration_id")
            == "H3_STATISTICAL_PREREGISTRATION_V2",
            "Unexpected H3 preregistration ID.",
        ),
        (
            prereg["inference"]["cluster_structure"]
            == "Two-way cluster-robust covariance by issuer_id and outcome_month.",
            "Primary cluster structure changed.",
        ),
        (
            prereg["inference"]["reference_df"]
            == "min(number of issuer clusters, number of outcome-month clusters) - 1",
            "Primary reference degrees-of-freedom rule changed.",
        ),
        (
            prereg["multiple_testing"]["method"] == "Holm-Bonferroni",
            "Multiple-testing method changed.",
        ),
        (
            tuple(prereg["multiple_testing"]["family"]) == HOLM_FAMILY,
            "Frozen Holm family changed.",
        ),
        (
            float(prereg["multiple_testing"]["familywise_alpha"]) == ALPHA,
            "Frozen familywise alpha changed.",
        ),
        (
            prereg["fixed_effects_and_controls"]["security_fixed_effects"] is True,
            "Security fixed effects are no longer frozen on.",
        ),
        (
            prereg["fixed_effects_and_controls"]["outcome_month_fixed_effects"] is True,
            "Outcome-month fixed effects are no longer frozen on.",
        ),
        (
            prereg["fixed_effects_and_controls"]["current_momentum_decile_fixed_effects"] is True,
            "Current-momentum-decile fixed effects are no longer frozen on.",
        ),
        (
            prereg["fixed_effects_and_controls"]["post_hoc_controls_allowed"] is False,
            "Post-hoc controls unexpectedly became allowed.",
        ),
    ]

    failures = [message for condition, message in checks if not condition]
    if failures:
        raise RuntimeError("Frozen preregistration validation failed: " + " | ".join(failures))

    return prereg


def validate_join_gate_files() -> dict[str, Any]:
    required = (
        JOIN_MANIFEST_PATH,
        JOIN_AUDIT_PATH,
        JOIN_PANEL_CSV_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Missing required passed join artifact(s): " + ", ".join(missing)
        )

    audit_text = JOIN_AUDIT_PATH.read_text(encoding="utf-8", errors="replace")
    required_tokens = (
        "H3_PREREGISTERED_PREDICTOR_OUTCOME_JOIN_INTEGRITY_AUDIT_PASSED",
        "H3_PRIMARY_MODEL_EXECUTION_AUTHORIZED",
    )
    for token in required_tokens:
        if token not in audit_text:
            raise RuntimeError(
                f"Join audit does not contain required authorization token: {token}"
            )

    manifest = json.loads(JOIN_MANIFEST_PATH.read_text(encoding="utf-8"))

    if manifest.get("regression_inference_executed") is not False:
        raise RuntimeError(
            "Join manifest indicates inference had already been executed."
        )

    actual_csv_sha = sha256_file(JOIN_PANEL_CSV_PATH)
    if actual_csv_sha != manifest.get("panel_sha256"):
        raise RuntimeError(
            "Joined-panel CSV checksum differs from the passed join manifest."
        )

    return manifest


def query_sql_panel(connection) -> pd.DataFrame:
    query = """
    SELECT
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
    FROM analytics.h3_preregistered_predictor_outcome_panel
    ORDER BY predictor_month, security_key;
    """
    return fetch_dataframe(connection.cursor(), query)


def normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()

    string_cols = (
        "predictor_month",
        "outcome_month",
        "security_key",
        "issuer_id",
        "gics_sector",
        "structural_ambiguity_tier",
        "preregistration_sha256",
        "current_join_status",
        "next_join_status",
    )
    for col in string_cols:
        if col in panel.columns:
            panel[col] = panel[col].astype("string").str.strip()

    numeric_cols = (
        "attention_z",
        "attention_log",
        "attention_percentile_midrank",
        "analysis_month_number",
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
    )
    for col in numeric_cols:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")

    panel["security_fe"] = panel["security_key"].astype(str)
    panel["outcome_month_fe"] = panel["outcome_month"].astype(str)
    panel["current_decile_fe"] = (
        panel["current_momentum_decile"]
        .round()
        .astype("Int64")
        .astype("string")
    )

    return panel


def structural_revalidation(panel: pd.DataFrame) -> None:
    failures: list[str] = []

    def assert_check(condition: bool, passed: str, failed: str) -> None:
        if condition:
            print(f"PASS: {passed}")
        else:
            print(f"FAIL: {failed}")
            failures.append(failed)

    assert_check(
        len(panel) == EXPECTED_JOIN_ROWS,
        f"SQL analytical panel has exactly {EXPECTED_JOIN_ROWS:,} rows.",
        f"SQL analytical panel row count changed: {len(panel):,}.",
    )
    assert_check(
        panel["predictor_month"].nunique() == EXPECTED_PREDICTOR_MONTHS,
        f"SQL analytical panel has exactly {EXPECTED_PREDICTOR_MONTHS} predictor months.",
        "SQL analytical panel predictor-month count changed.",
    )
    assert_check(
        panel["issuer_id"].nunique() == EXPECTED_ISSUER_CLUSTERS,
        f"SQL analytical panel has exactly {EXPECTED_ISSUER_CLUSTERS} issuer clusters.",
        "SQL analytical panel issuer-cluster count changed.",
    )
    assert_check(
        not panel[["predictor_month", "security_key"]].duplicated().any(),
        "SQL analytical panel remains unique by predictor month and security.",
        "Duplicate predictor-month/security rows exist in SQL analytical panel.",
    )
    assert_check(
        int(panel["h3a_h3c_eligible"].fillna(0).sum()) == EXPECTED_H3AC_ROWS,
        f"H3A/H3C frozen structural sample remains {EXPECTED_H3AC_ROWS:,} rows.",
        "H3A/H3C frozen structural sample count changed.",
    )
    assert_check(
        int(panel["h3b_eligible"].fillna(0).sum()) == EXPECTED_H3B_ROWS,
        f"H3B frozen structural sample remains {EXPECTED_H3B_ROWS:,} rows.",
        "H3B frozen structural sample count changed.",
    )

    h3b = panel.loc[panel["h3b_eligible"].eq(1)].copy()
    positive_events = int(h3b["winner_entry"].fillna(0).sum())
    assert_check(
        positive_events == EXPECTED_H3B_POSITIVE_EVENTS,
        f"H3B positive Winner-entry count remains {EXPECTED_H3B_POSITIVE_EVENTS}.",
        f"H3B positive Winner-entry count changed: {positive_events}.",
    )

    h3ac = panel.loc[panel["h3a_h3c_eligible"].eq(1)].copy()
    h3b = panel.loc[panel["h3b_eligible"].eq(1)].copy()

    current_miss = panel["current_join_status"].ne("both")
    next_miss = panel["next_join_status"].ne("both")

    assert_check(
        h3ac["current_join_status"].eq("both").all(),
        "Every H3A/H3C eligible row matches the required current H1 layer.",
        "At least one H3A/H3C eligible row lacks the required current H1 join.",
    )
    assert_check(
        h3b["current_join_status"].eq("both").all(),
        "Every H3B eligible row matches the required current H1 layer.",
        "At least one H3B eligible row lacks the required current H1 join.",
    )
    assert_check(
        h3b["next_join_status"].eq("both").all(),
        "Every H3B eligible row matches the required t+1 momentum-assignment layer.",
        "At least one H3B eligible row lacks the required t+1 momentum assignment.",
    )
    assert_check(
        (
            panel.loc[current_miss, "h3a_h3c_eligible"].fillna(0).eq(0)
            & panel.loc[current_miss, "h3b_eligible"].fillna(0).eq(0)
        ).all(),
        "Predictor rows lacking the current H1 join are excluded from all primary H3 model samples.",
        "A predictor row lacking the current H1 join remains eligible for a primary H3 model.",
    )
    assert_check(
        panel.loc[next_miss, "h3b_eligible"].fillna(0).eq(0).all(),
        "Predictor rows lacking the t+1 momentum join are excluded from H3B.",
        "A predictor row lacking the t+1 momentum join remains eligible for H3B.",
    )

    print(
        "Structural join-status diagnostics: "
        f"current-H1 unmatched predictor rows={int(current_miss.sum()):,}; "
        f"t+1-momentum unmatched predictor rows={int(next_miss.sum()):,}."
    )

    if failures:
        raise RuntimeError(
            "Pre-model SQL structural revalidation failed. "
            "No confirmatory regression was executed."
        )


def two_way_cluster_covariance(
    result,
    issuer_group: pd.Series,
    month_group: pd.Series,
) -> tuple[np.ndarray, int, int, int]:
    issuer_codes = pd.factorize(issuer_group.astype(str), sort=True)[0]
    month_codes = pd.factorize(month_group.astype(str), sort=True)[0]

    intersection_labels = (
        issuer_group.astype(str)
        + "||"
        + month_group.astype(str)
    )
    intersection_codes = pd.factorize(intersection_labels, sort=True)[0]

    issuer_clusters = int(pd.Series(issuer_codes).nunique())
    month_clusters = int(pd.Series(month_codes).nunique())
    intersection_clusters = int(pd.Series(intersection_codes).nunique())

    if issuer_clusters < 2 or month_clusters < 2:
        raise RuntimeError(
            "Two-way clustered covariance requires at least two clusters "
            "in each primary cluster dimension."
        )

    cov_issuer = cov_cluster(
        result,
        issuer_codes,
        use_correction=True,
    )
    cov_month = cov_cluster(
        result,
        month_codes,
        use_correction=True,
    )
    cov_intersection = cov_cluster(
        result,
        intersection_codes,
        use_correction=True,
    )

    cov_two_way = cov_issuer + cov_month - cov_intersection
    cov_two_way = (cov_two_way + cov_two_way.T) / 2.0

    return (
        np.asarray(cov_two_way, dtype=float),
        issuer_clusters,
        month_clusters,
        intersection_clusters,
    )


def coefficient_inference(
    result,
    covariance: np.ndarray,
    term: str,
    reference_df: int,
) -> dict[str, float]:
    names = list(result.params.index)
    if term not in names:
        raise RuntimeError(
            f"Prespecified estimand term {term!r} not found in fitted model."
        )

    idx = names.index(term)
    estimate = float(result.params.iloc[idx])
    variance = float(covariance[idx, idx])

    if not np.isfinite(variance) or variance <= 0:
        raise RuntimeError(
            f"Non-positive/non-finite clustered variance for term {term}: {variance}"
        )

    se = math.sqrt(variance)
    t_stat = estimate / se
    p_value = float(
        2.0 * stats.t.sf(abs(t_stat), df=reference_df)
    )
    critical = float(stats.t.ppf(1.0 - ALPHA / 2.0, df=reference_df))
    ci_low = estimate - critical * se
    ci_high = estimate + critical * se

    return {
        "estimate": estimate,
        "cluster_se": se,
        "t_stat": t_stat,
        "reference_df": float(reference_df),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "raw_p_value": p_value,
    }


def linear_combination_inference(
    result,
    covariance: np.ndarray,
    terms: tuple[str, str],
    reference_df: int,
) -> dict[str, float]:
    names = list(result.params.index)
    if terms[0] not in names or terms[1] not in names:
        raise RuntimeError(
            f"Cannot form frozen H3C secondary linear combination: {terms}"
        )

    i = names.index(terms[0])
    j = names.index(terms[1])

    estimate = float(result.params.iloc[i] + result.params.iloc[j])
    variance = float(
        covariance[i, i]
        + covariance[j, j]
        + 2.0 * covariance[i, j]
    )

    if not np.isfinite(variance) or variance <= 0:
        raise RuntimeError(
            "Non-positive/non-finite variance for H3C Winner attention slope."
        )

    se = math.sqrt(variance)
    t_stat = estimate / se
    p_value = float(
        2.0 * stats.t.sf(abs(t_stat), df=reference_df)
    )
    critical = float(stats.t.ppf(1.0 - ALPHA / 2.0, df=reference_df))
    ci_low = estimate - critical * se
    ci_high = estimate + critical * se

    return {
        "estimate": estimate,
        "cluster_se": se,
        "t_stat": t_stat,
        "reference_df": float(reference_df),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "raw_p_value": p_value,
    }


def fit_primary_model(
    label: str,
    sample: pd.DataFrame,
    formula: str,
    estimand_term: str,
) -> tuple[dict[str, Any], Any, np.ndarray]:
    print("")
    print(rule())
    print(f"{label} PRIMARY MODEL")
    print(rule())
    print(f"Rows: {len(sample):,}")
    print(f"Issuer clusters: {sample['issuer_id'].nunique():,}")
    print(f"Outcome-month clusters: {sample['outcome_month'].nunique():,}")
    print(f"Formula: {formula}")

    model = smf.ols(
        formula=formula,
        data=sample,
        missing="raise",
    )
    result = model.fit()

    covariance, issuer_clusters, month_clusters, intersection_clusters = (
        two_way_cluster_covariance(
            result=result,
            issuer_group=sample.loc[result.model.data.row_labels, "issuer_id"],
            month_group=sample.loc[result.model.data.row_labels, "outcome_month"],
        )
    )

    reference_df = min(issuer_clusters, month_clusters) - 1

    if reference_df < 1:
        raise RuntimeError(
            f"{label} has invalid frozen reference df: {reference_df}"
        )

    inference = coefficient_inference(
        result=result,
        covariance=covariance,
        term=estimand_term,
        reference_df=reference_df,
    )

    payload: dict[str, Any] = {
        "component": label,
        "estimand_term": estimand_term,
        "model_formula": formula,
        "sample_rows": int(result.nobs),
        "security_fixed_effects": int(
            sample.loc[result.model.data.row_labels, "security_key"].nunique()
        ),
        "issuer_clusters": issuer_clusters,
        "month_clusters": month_clusters,
        "intersection_clusters": intersection_clusters,
        "reference_df": reference_df,
        **inference,
    }

    print(
        f"{estimand_term}: estimate={inference['estimate']:.12g}, "
        f"SE={inference['cluster_se']:.12g}, "
        f"t={inference['t_stat']:.6f}, "
        f"df={reference_df}, "
        f"raw p={inference['raw_p_value']:.12g}"
    )

    return payload, result, covariance


def holm_adjust(raw_p_values: dict[str, float]) -> dict[str, float]:
    if set(raw_p_values) != set(HOLM_FAMILY):
        raise RuntimeError(
            "Holm adjustment received a family different from the frozen "
            "H3A/H3B/H3C family."
        )

    m = len(raw_p_values)
    ordered = sorted(
        raw_p_values.items(),
        key=lambda item: (item[1], item[0]),
    )

    adjusted_ordered: list[tuple[str, float]] = []
    running_max = 0.0

    for rank, (name, p_value) in enumerate(ordered, start=1):
        multiplier = m - rank + 1
        candidate = min(1.0, multiplier * p_value)
        running_max = max(running_max, candidate)
        adjusted_ordered.append(
            (name, min(1.0, running_max))
        )

    return dict(adjusted_ordered)


def support_decision(
    estimate: float,
    holm_p: float,
) -> str:
    if holm_p < ALPHA and estimate > 0:
        return "SUPPORTED"
    if holm_p < ALPHA and estimate < 0:
        return "CONTRADICTED"
    return "NOT SUPPORTED"


def materialize_results_sql(
    connection,
    results_df: pd.DataFrame,
) -> None:
    cursor = connection.cursor()

    ddl = """
    IF OBJECT_ID('analytics.h3_primary_confirmatory_results', 'U') IS NOT NULL
        DROP TABLE analytics.h3_primary_confirmatory_results;

    CREATE TABLE analytics.h3_primary_confirmatory_results (
        component nvarchar(32) NOT NULL PRIMARY KEY,
        estimand_term nvarchar(128) NOT NULL,
        estimate float NOT NULL,
        cluster_se float NOT NULL,
        ci_low float NOT NULL,
        ci_high float NOT NULL,
        t_stat float NOT NULL,
        reference_df int NOT NULL,
        raw_p_value float NOT NULL,
        holm_adjusted_p_value float NOT NULL,
        economic_effect_pp float NOT NULL,
        sample_rows int NOT NULL,
        security_fixed_effects int NOT NULL,
        issuer_clusters int NOT NULL,
        month_clusters int NOT NULL,
        intersection_clusters int NOT NULL,
        decision nvarchar(32) NOT NULL,
        expected_sign nvarchar(16) NOT NULL,
        inference_method nvarchar(256) NOT NULL,
        preregistration_id nvarchar(128) NOT NULL,
        script_version nvarchar(128) NOT NULL
    );
    """
    cursor.execute(ddl)

    insert_sql = """
    INSERT INTO analytics.h3_primary_confirmatory_results (
        component,
        estimand_term,
        estimate,
        cluster_se,
        ci_low,
        ci_high,
        t_stat,
        reference_df,
        raw_p_value,
        holm_adjusted_p_value,
        economic_effect_pp,
        sample_rows,
        security_fixed_effects,
        issuer_clusters,
        month_clusters,
        intersection_clusters,
        decision,
        expected_sign,
        inference_method,
        preregistration_id,
        script_version
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
    """

    rows = [
        tuple(
            None if pd.isna(value) else value.item() if isinstance(value, np.generic) else value
            for value in row
        )
        for row in results_df[
            [
                "component",
                "estimand_term",
                "estimate",
                "cluster_se",
                "ci_low",
                "ci_high",
                "t_stat",
                "reference_df",
                "raw_p_value",
                "holm_adjusted_p_value",
                "economic_effect_pp",
                "sample_rows",
                "security_fixed_effects",
                "issuer_clusters",
                "month_clusters",
                "intersection_clusters",
                "decision",
                "expected_sign",
                "inference_method",
                "preregistration_id",
                "script_version",
            ]
        ].itertuples(index=False, name=None)
    ]

    cursor.executemany(insert_sql, rows)

    cursor.execute(
        "SELECT COUNT(*) FROM analytics.h3_primary_confirmatory_results;"
    )
    count = int(cursor.fetchone()[0])
    if count != 3:
        raise RuntimeError(
            f"SQL primary-result materialization expected 3 rows, found {count}."
        )


def write_outputs(
    results_df: pd.DataFrame,
    h3c_secondary: dict[str, float],
    prereg: dict[str, Any],
    join_manifest: dict[str, Any],
) -> None:
    H3_DIR.mkdir(parents=True, exist_ok=True)

    results_df.to_csv(RESULTS_CSV_PATH, index=False)

    report_lines = [
        rule(),
        "H3 PRIMARY CONFIRMATORY INFERENCE",
        rule(),
        f"Script version: {SCRIPT_VERSION}",
        f"Preregistration: {prereg['preregistration_id']}",
        f"Preregistration SHA-256: {sha256_file(PREREG_PATH)}",
        f"Joined-panel SHA-256: {join_manifest['panel_sha256']}",
        "",
        "PRIMARY INFERENCE",
        "Two-way cluster-robust covariance by issuer_id and outcome_month.",
        "Small-sample correction: TRUE.",
        "Reference df = min(issuer clusters, outcome-month clusters) - 1.",
        "Tests: two-sided.",
        "Holm family: H3A_beta_A, H3B_beta_B, H3C_theta.",
        "Familywise alpha: 0.05.",
        "",
    ]

    for row in results_df.itertuples(index=False):
        report_lines.extend(
            [
                f"{row.component}",
                f"  Estimand: {row.estimand_term}",
                f"  Coefficient: {row.estimate:.12g}",
                f"  Two-way clustered SE: {row.cluster_se:.12g}",
                f"  95% CI: [{row.ci_low:.12g}, {row.ci_high:.12g}]",
                f"  t statistic: {row.t_stat:.8f}",
                f"  Reference df: {int(row.reference_df)}",
                f"  Raw two-sided p-value: {row.raw_p_value:.12g}",
                f"  Holm-adjusted p-value: {row.holm_adjusted_p_value:.12g}",
                f"  Economic effect: {row.economic_effect_pp:.8f} percentage points",
                f"  Sample rows: {int(row.sample_rows):,}",
                f"  Issuer clusters: {int(row.issuer_clusters):,}",
                f"  Outcome-month clusters: {int(row.month_clusters):,}",
                f"  Decision: {row.decision}",
                "",
            ]
        )

    report_lines.extend(
        [
            "H3C PRESPECIFIED SECONDARY LINEAR COMBINATION",
            "Winner attention slope = beta_C + theta.",
            "Descriptive secondary inference only; NOT part of Holm family.",
            f"  Estimate: {h3c_secondary['estimate']:.12g}",
            f"  Two-way clustered SE: {h3c_secondary['cluster_se']:.12g}",
            f"  95% CI: [{h3c_secondary['ci_low']:.12g}, {h3c_secondary['ci_high']:.12g}]",
            f"  t statistic: {h3c_secondary['t_stat']:.8f}",
            f"  Reference df: {int(h3c_secondary['reference_df'])}",
            f"  Raw two-sided p-value: {h3c_secondary['raw_p_value']:.12g}",
            f"  Economic effect: {100.0 * h3c_secondary['estimate']:.8f} percentage points",
            "",
            "ROBUSTNESS EXECUTED IN THIS SCRIPT: NO",
            "R1/R2/ambiguity/transition/leave-one-sector-out robustness remains separate.",
            "",
            "H3_PRIMARY_CONFIRMATORY_INFERENCE_COMPLETE",
        ]
    )

    REPORT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "script_version": SCRIPT_VERSION,
        "preregistration_id": prereg["preregistration_id"],
        "preregistration_version": prereg["preregistration_version"],
        "preregistration_sha256": sha256_file(PREREG_PATH),
        "joined_panel_sha256": join_manifest["panel_sha256"],
        "sql_panel": SQL_PANEL,
        "sql_results": SQL_RESULTS,
        "results_csv": str(RESULTS_CSV_PATH.relative_to(ROOT)),
        "results_csv_sha256": sha256_file(RESULTS_CSV_PATH),
        "report": str(REPORT_PATH.relative_to(ROOT)),
        "primary_covariance": prereg["inference"]["cluster_structure"],
        "reference_df_rule": prereg["inference"]["reference_df"],
        "small_sample_correction": prereg["inference"]["small_sample_correction"],
        "holm_family": list(HOLM_FAMILY),
        "familywise_alpha": ALPHA,
        "primary_models_executed": ["H3A", "H3B", "H3C"],
        "prespecified_robustness_executed": False,
        "h3c_secondary_linear_combination": h3c_secondary,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print(rule())
    print("H3 PRIMARY CONFIRMATORY INFERENCE")
    print(rule())
    print("Outcome boundary: AUTHORIZED")
    print("Model specification changes permitted: NO")
    print("Post-hoc controls permitted: NO")
    print("Primary covariance: two-way issuer × outcome-month clustering")
    print("Multiple testing: frozen three-test Holm family")

    prereg = load_preregistration()
    join_manifest = validate_join_gate_files()

    server, database, username, password = load_environment()
    connection = connect_with_retry(
        server,
        database,
        username,
        password,
    )

    try:
        panel = normalize_panel(query_sql_panel(connection))

        print("")
        print(rule())
        print("PRE-MODEL STRUCTURAL REVALIDATION")
        print(rule())
        structural_revalidation(panel)

        h3ac = panel.loc[
            panel["h3a_h3c_eligible"].eq(1)
        ].copy()
        h3b = panel.loc[
            panel["h3b_eligible"].eq(1)
        ].copy()

        # Exact frozen formulas:
        h3a_formula = (
            "sector_relative_return_1m ~ attention_z "
            "+ C(security_fe) "
            "+ C(outcome_month_fe) "
            "+ C(current_decile_fe)"
        )
        h3b_formula = (
            "winner_entry ~ attention_z "
            "+ C(security_fe) "
            "+ C(outcome_month_fe) "
            "+ C(current_decile_fe)"
        )
        h3c_formula = (
            "sector_relative_return_1m ~ attention_z "
            "+ attention_x_current_winner "
            "+ C(security_fe) "
            "+ C(outcome_month_fe) "
            "+ C(current_decile_fe)"
        )

        h3a, _, _ = fit_primary_model(
            label="H3A",
            sample=h3ac,
            formula=h3a_formula,
            estimand_term="attention_z",
        )

        h3b_result_row, _, _ = fit_primary_model(
            label="H3B",
            sample=h3b,
            formula=h3b_formula,
            estimand_term="attention_z",
        )

        h3c, h3c_result, h3c_cov = fit_primary_model(
            label="H3C",
            sample=h3ac,
            formula=h3c_formula,
            estimand_term="attention_x_current_winner",
        )

        h3c_secondary = linear_combination_inference(
            result=h3c_result,
            covariance=h3c_cov,
            terms=("attention_z", "attention_x_current_winner"),
            reference_df=int(h3c["reference_df"]),
        )

        raw_family = {
            "H3A_beta_A": float(h3a["raw_p_value"]),
            "H3B_beta_B": float(h3b_result_row["raw_p_value"]),
            "H3C_theta": float(h3c["raw_p_value"]),
        }
        holm = holm_adjust(raw_family)

        rows = []
        specification_rows = (
            (
                h3a,
                "H3A_beta_A",
                "positive",
                prereg["hypotheses"]["H3A"]["label"],
            ),
            (
                h3b_result_row,
                "H3B_beta_B",
                "positive",
                prereg["hypotheses"]["H3B"]["label"],
            ),
            (
                h3c,
                "H3C_theta",
                "positive",
                prereg["hypotheses"]["H3C"]["label"],
            ),
        )

        for payload, family_name, expected_sign, label in specification_rows:
            estimate = float(payload["estimate"])
            holm_p = float(holm[family_name])
            rows.append(
                {
                    "component": payload["component"],
                    "family_name": family_name,
                    "label": label,
                    "estimand_term": payload["estimand_term"],
                    "estimate": estimate,
                    "cluster_se": float(payload["cluster_se"]),
                    "ci_low": float(payload["ci_low"]),
                    "ci_high": float(payload["ci_high"]),
                    "t_stat": float(payload["t_stat"]),
                    "reference_df": int(payload["reference_df"]),
                    "raw_p_value": float(payload["raw_p_value"]),
                    "holm_adjusted_p_value": holm_p,
                    "economic_effect_pp": 100.0 * estimate,
                    "sample_rows": int(payload["sample_rows"]),
                    "security_fixed_effects": int(payload["security_fixed_effects"]),
                    "issuer_clusters": int(payload["issuer_clusters"]),
                    "month_clusters": int(payload["month_clusters"]),
                    "intersection_clusters": int(payload["intersection_clusters"]),
                    "decision": support_decision(estimate, holm_p),
                    "expected_sign": expected_sign,
                    "inference_method": (
                        "OLS/LPM with security FE, outcome-month FE, current momentum-decile FE; "
                        "two-way CR1 cluster covariance by issuer_id and outcome_month"
                    ),
                    "preregistration_id": prereg["preregistration_id"],
                    "script_version": SCRIPT_VERSION,
                }
            )

        results_df = pd.DataFrame(rows)

        write_outputs(
            results_df=results_df,
            h3c_secondary=h3c_secondary,
            prereg=prereg,
            join_manifest=join_manifest,
        )
        materialize_results_sql(connection, results_df)

        print("")
        print(rule())
        print("PRIMARY H3 RESULTS")
        print(rule())

        for row in results_df.itertuples(index=False):
            print(
                f"{row.component}: "
                f"coef={row.estimate:.12g}; "
                f"SE={row.cluster_se:.12g}; "
                f"95% CI=[{row.ci_low:.12g}, {row.ci_high:.12g}]; "
                f"raw p={row.raw_p_value:.12g}; "
                f"Holm p={row.holm_adjusted_p_value:.12g}; "
                f"effect={row.economic_effect_pp:.8f} pp; "
                f"decision={row.decision}"
            )

        print("")
        print(
            "H3C Winner attention slope (beta_C + theta; secondary, not Holm): "
            f"coef={h3c_secondary['estimate']:.12g}; "
            f"SE={h3c_secondary['cluster_se']:.12g}; "
            f"95% CI=[{h3c_secondary['ci_low']:.12g}, "
            f"{h3c_secondary['ci_high']:.12g}]; "
            f"p={h3c_secondary['raw_p_value']:.12g}; "
            f"effect={100.0 * h3c_secondary['estimate']:.8f} pp"
        )

        print("")
        print(f"Results CSV: {RESULTS_CSV_PATH.relative_to(ROOT)}")
        print(f"Report: {REPORT_PATH.relative_to(ROOT)}")
        print(f"Manifest: {MANIFEST_PATH.relative_to(ROOT)}")
        print(f"SQL results table: {SQL_RESULTS}")
        print("Prespecified robustness executed: NO")
        print("H3_PRIMARY_CONFIRMATORY_INFERENCE_COMPLETE")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
