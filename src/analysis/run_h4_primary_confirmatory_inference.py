from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

SCRIPT_VERSION = "2026-08-28-v1-h4-primary-confirmatory-inference"

PREREG_PATH = Path(
    "data/reference/h4/h4_primary_liquidity_sweep_inference_v1.json"
)
JOIN_INPUT = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join.csv"
)
JOIN_MANIFEST = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join_manifest.json"
)
JOIN_AUDIT = Path(
    "reports/data_quality/h4_spy_primary_liquidity_sweep_outcome_join_audit.txt"
)
JOIN_AUDIT_MANIFEST = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join_audit_manifest.json"
)

RESULTS_CSV = Path(
    "reports/confirmatory/h4/h4_primary_confirmatory_results.csv"
)
REPORT_TXT = Path(
    "reports/confirmatory/h4/h4_primary_confirmatory_report.txt"
)
MANIFEST_JSON = Path(
    "reports/confirmatory/h4/h4_primary_confirmatory_manifest.json"
)

REQUIRED_JOIN_TOKENS = [
    "H4_PRIMARY_OUTCOME_JOIN_INTEGRITY_AUDIT_PASSED",
    "H4_PRIMARY_CONFIRMATORY_INFERENCE_AUTHORIZED",
]

ALPHA = 0.05
MIN_EVENTS = 100
MIN_CLUSTERS = 100
PRIMARY_COL = "signed_forward_return_30m"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_authorization() -> dict:
    for path in [
        PREREG_PATH,
        JOIN_INPUT,
        JOIN_MANIFEST,
        JOIN_AUDIT,
        JOIN_AUDIT_MANIFEST,
    ]:
        if not path.exists():
            raise RuntimeError(f"Missing required input: {path}")

    audit_text = JOIN_AUDIT.read_text(encoding="utf-8")
    for token in REQUIRED_JOIN_TOKENS:
        if token not in audit_text:
            raise RuntimeError(
                f"Required outcome-join authorization token absent: {token}"
            )

    manifest = json.loads(JOIN_MANIFEST.read_text(encoding="utf-8"))
    if str(manifest.get("outcome_join_output_sha256") or "") != sha256_file(
        JOIN_INPUT
    ):
        raise RuntimeError("Outcome-join SHA-256 mismatch.")

    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if prereg.get("preregistration_name") != "H4_PRIMARY_LIQUIDITY_SWEEP_INFERENCE_V1":
        raise RuntimeError("Unexpected H4 primary preregistration.")

    return prereg


def cluster_mean_test(
    df: pd.DataFrame,
    value_col: str,
) -> dict:
    y = df[value_col].astype(float).to_numpy()
    x = np.ones((len(df), 1), dtype=float)

    model = sm.OLS(y, x).fit()

    groups = pd.Categorical(df["session_date"]).codes
    robust = model.get_robustcov_results(
        cov_type="cluster",
        groups=groups,
        use_correction=True,
        df_correction=True,
    )

    estimate = float(model.params[0])
    se = float(robust.bse[0])

    clusters = int(df["session_date"].nunique())
    df_ref = clusters - 1
    if df_ref <= 0:
        raise RuntimeError("Insufficient session clusters.")

    t_stat = estimate / se
    p_two = 2.0 * stats.t.sf(abs(t_stat), df=df_ref)
    crit = stats.t.ppf(1.0 - ALPHA / 2.0, df=df_ref)
    ci_low = estimate - crit * se
    ci_high = estimate + crit * se

    return {
        "estimate": estimate,
        "se": se,
        "t_stat": t_stat,
        "df_ref": df_ref,
        "p_two_sided": float(p_two),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "events": len(df),
        "session_clusters": clusters,
    }


def session_collapsed_hac(
    df: pd.DataFrame,
    value_col: str,
    maxlags: int = 5,
) -> dict:
    daily = (
        df.groupby("session_date", as_index=False)[value_col]
        .mean()
        .sort_values("session_date")
    )

    y = daily[value_col].astype(float).to_numpy()
    x = np.ones((len(daily), 1), dtype=float)

    model = sm.OLS(y, x).fit(
        cov_type="HAC",
        cov_kwds={
            "maxlags": maxlags,
            "use_correction": True,
        },
    )

    estimate = float(model.params[0])
    se = float(model.bse[0])
    t_stat = estimate / se
    df_ref = len(daily) - 1
    p_two = 2.0 * stats.t.sf(abs(t_stat), df=df_ref)
    crit = stats.t.ppf(1.0 - ALPHA / 2.0, df=df_ref)

    return {
        "estimate": estimate,
        "se": se,
        "t_stat": t_stat,
        "df_ref": df_ref,
        "p_two_sided": float(p_two),
        "ci_low": float(estimate - crit * se),
        "ci_high": float(estimate + crit * se),
        "sessions": len(daily),
        "hac_lag": maxlags,
    }


def decision(estimate: float, p_value: float) -> str:
    if p_value < ALPHA and estimate > 0:
        return "SUPPORTED"
    if p_value < ALPHA and estimate < 0:
        return "CONTRADICTED"
    return "NOT SUPPORTED"


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    prereg = verify_authorization()

    df = pd.read_csv(JOIN_INPUT)

    if df[PRIMARY_COL].isna().any():
        raise RuntimeError("Primary H4 outcome contains missing values.")

    if len(df) < MIN_EVENTS:
        raise RuntimeError(
            f"Primary H4 sample below frozen minimum: "
            f"{len(df)} < {MIN_EVENTS}"
        )

    clusters = int(df["session_date"].nunique())
    if clusters < MIN_CLUSTERS:
        raise RuntimeError(
            f"Primary H4 session clusters below frozen minimum: "
            f"{clusters} < {MIN_CLUSTERS}"
        )

    primary = cluster_mean_test(df, PRIMARY_COL)
    primary_decision = decision(
        primary["estimate"],
        primary["p_two_sided"],
    )

    secondary = {}
    for minutes in [15, 60]:
        col = f"signed_forward_return_{minutes}m"
        sub = df[df[col].notna()].copy()
        if len(sub) >= MIN_EVENTS and sub["session_date"].nunique() >= MIN_CLUSTERS:
            secondary[str(minutes)] = cluster_mean_test(sub, col)

    hac = session_collapsed_hac(df, PRIMARY_COL, maxlags=5)

    yearly = (
        df.assign(year=df["session_date"].str.slice(0, 4))
        .groupby("year")
        .agg(
            events=("event_id", "size"),
            sessions=("session_date", "nunique"),
            mean_signed_return_30m=(PRIMARY_COL, "mean"),
        )
        .reset_index()
    )

    results_rows = [
        {
            "component": "H4A_PRIMARY",
            "estimand": "mean_signed_forward_return_30m",
            "estimate": primary["estimate"],
            "cluster_se": primary["se"],
            "ci_95_low": primary["ci_low"],
            "ci_95_high": primary["ci_high"],
            "t_stat": primary["t_stat"],
            "reference_df": primary["df_ref"],
            "p_two_sided": primary["p_two_sided"],
            "economic_effect_percentage_points": 100.0 * primary["estimate"],
            "events": primary["events"],
            "session_clusters": primary["session_clusters"],
            "decision": primary_decision,
            "primary_or_secondary": "PRIMARY",
        }
    ]

    for minutes, res in secondary.items():
        results_rows.append(
            {
                "component": f"H4_SECONDARY_{minutes}M",
                "estimand": f"mean_signed_forward_return_{minutes}m",
                "estimate": res["estimate"],
                "cluster_se": res["se"],
                "ci_95_low": res["ci_low"],
                "ci_95_high": res["ci_high"],
                "t_stat": res["t_stat"],
                "reference_df": res["df_ref"],
                "p_two_sided": res["p_two_sided"],
                "economic_effect_percentage_points": 100.0 * res["estimate"],
                "events": res["events"],
                "session_clusters": res["session_clusters"],
                "decision": "DESCRIPTIVE ONLY",
                "primary_or_secondary": "SECONDARY",
            }
        )

    results = pd.DataFrame(results_rows)

    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_CSV, index=False)

    lines = [
        "H4 PRIMARY CONFIRMATORY INFERENCE",
        "=" * 124,
        f"Script version: {SCRIPT_VERSION}",
        f"Preregistration: {prereg['preregistration_name']}",
        f"Preregistration SHA-256: {sha256_file(PREREG_PATH)}",
        f"Outcome-join SHA-256: {sha256_file(JOIN_INPUT)}",
        "",
        "PRIMARY H4A",
        "Event-level signed 30-minute return.",
        "Positive signed return = movement in preregistered sweep/rejection direction.",
        "Intercept-only OLS with session-clustered covariance.",
        "Small-sample correction: TRUE.",
        "Reference df = eligible session clusters - 1.",
        "Test: two-sided.",
        "Alpha: 0.05.",
        "",
        f"Coefficient / mean signed return: {primary['estimate']:.12g}",
        f"Session-clustered SE: {primary['se']:.12g}",
        f"95% CI: [{primary['ci_low']:.12g}, {primary['ci_high']:.12g}]",
        f"t statistic: {primary['t_stat']:.8f}",
        f"Reference df: {primary['df_ref']}",
        f"Two-sided p-value: {primary['p_two_sided']:.12g}",
        f"Economic effect: {100.0 * primary['estimate']:.8f} percentage points",
        f"Eligible events: {primary['events']:,}",
        f"Eligible session clusters: {primary['session_clusters']:,}",
        f"Decision: {primary_decision}",
        "",
        "PRESPECIFIED SESSION-COLLAPSED ROBUSTNESS",
        "Mean event return within each eligible session; HAC(5) on session means.",
        f"Estimate: {hac['estimate']:.12g}",
        f"HAC SE: {hac['se']:.12g}",
        f"95% CI: [{hac['ci_low']:.12g}, {hac['ci_high']:.12g}]",
        f"Two-sided p-value: {hac['p_two_sided']:.12g}",
        f"Sessions: {hac['sessions']:,}",
        "Robustness cannot upgrade the primary decision.",
        "",
        "SECONDARY HORIZONS",
    ]

    for minutes in [15, 60]:
        res = secondary.get(str(minutes))
        if res is None:
            lines.append(
                f"{minutes}m: insufficient frozen minimum sample for "
                "clustered secondary inference."
            )
        else:
            lines.extend(
                [
                    f"{minutes}m mean signed return: {res['estimate']:.12g}",
                    f"{minutes}m clustered SE: {res['se']:.12g}",
                    f"{minutes}m 95% CI: "
                    f"[{res['ci_low']:.12g}, {res['ci_high']:.12g}]",
                    f"{minutes}m two-sided p-value: "
                    f"{res['p_two_sided']:.12g}",
                    f"{minutes}m events: {res['events']:,}",
                    "Decision: DESCRIPTIVE ONLY",
                ]
            )

    lines.extend(
        [
            "",
            "YEAR-BY-YEAR DESCRIPTIVE STABILITY",
        ]
    )
    for r in yearly.itertuples(index=False):
        lines.append(
            f"{r.year}: events={int(r.events):,}, "
            f"sessions={int(r.sessions):,}, "
            f"mean signed 30m return={float(r.mean_signed_return_30m):.12g}"
        )

    lines.extend(
        [
            "",
            "IMPORTANT",
            "This is a gross price-return signal test.",
            "No deployable strategy claim is authorized without separate "
            "spread/slippage/cost analysis.",
            "",
            "H4_PRIMARY_CONFIRMATORY_INFERENCE_COMPLETE",
        ]
    )

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "script_version": SCRIPT_VERSION,
        "preregistration": str(PREREG_PATH).replace("\\", "/"),
        "preregistration_sha256": sha256_file(PREREG_PATH),
        "outcome_join": str(JOIN_INPUT).replace("\\", "/"),
        "outcome_join_sha256": sha256_file(JOIN_INPUT),
        "results_csv": str(RESULTS_CSV).replace("\\", "/"),
        "results_csv_sha256": sha256_file(RESULTS_CSV),
        "report_txt": str(REPORT_TXT).replace("\\", "/"),
        "report_txt_sha256": sha256_file(REPORT_TXT),
        "primary_decision": primary_decision,
        "primary_estimate": primary["estimate"],
        "primary_p_two_sided": primary["p_two_sided"],
        "primary_events": primary["events"],
        "primary_session_clusters": primary["session_clusters"],
    }
    MANIFEST_JSON.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(REPORT_TXT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
