from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-26-v2-h3-statistical-preregistration-audit-issuer-day"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

PREREG_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_statistical_preregistration_v2.json"
)
PREDICTOR_PATH = (
    H3_DIR / "h3_preregistered_attention_predictor_panel.csv"
)
ISSUER_DAY_PATH = (
    H3_DIR / "h3_preregistered_attention_issuer_day_panel.csv.gz"
)
ISSUER_MONTH_PATH = (
    H3_DIR / "h3_preregistered_attention_issuer_month_panel.csv"
)
SAME_ISSUER_DAY_DIAGNOSTICS_PATH = (
    H3_DIR / "h3_preregistered_attention_same_issuer_day_diagnostics.csv"
)
MONTH_SUMMARY_PATH = (
    H3_DIR / "h3_preregistered_attention_month_summary.csv"
)

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_statistical_preregistration_integrity_audit.txt"
)

FORBIDDEN = (
    "return",
    "momentum",
    "winner",
    "outcome",
    "commonality",
)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        PREREG_PATH,
        PREDICTOR_PATH,
        ISSUER_DAY_PATH,
        ISSUER_MONTH_PATH,
        SAME_ISSUER_DAY_DIAGNOSTICS_PATH,
        MONTH_SUMMARY_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    prereg_text = PREREG_PATH.read_text(encoding="utf-8")
    prereg = json.loads(prereg_text)
    prereg_sha = hashlib.sha256(
        prereg_text.encode("utf-8")
    ).hexdigest()

    predictor = pd.read_csv(
        PREDICTOR_PATH,
        dtype=str,
        keep_default_na=False,
    )
    issuer_day = pd.read_csv(
        ISSUER_DAY_PATH,
        dtype=str,
        keep_default_na=False,
        compression="gzip",
    )
    issuer = pd.read_csv(
        ISSUER_MONTH_PATH,
        dtype=str,
        keep_default_na=False,
    )
    diagnostics = pd.read_csv(
        SAME_ISSUER_DAY_DIAGNOSTICS_PATH,
        dtype=str,
        keep_default_na=False,
    )
    month_summary = pd.read_csv(
        MONTH_SUMMARY_PATH,
        dtype=str,
        keep_default_na=False,
    )

    numeric_specs = (
        (
            predictor,
            [
                "issuer_attention_share",
                "attention_share",
                "security_month_attention_share_provenance",
                "attention_log",
                "attention_z",
                "attention_percentile_midrank",
                "attention_log_mean",
                "attention_log_sd",
                "primary_attention_eligible_flag",
            ],
        ),
        (
            issuer_day,
            [
                "matched_source_document_weight",
                "total_source_document_weight",
                "issuer_day_attention_share",
            ],
        ),
        (
            issuer,
            [
                "matched_source_document_weight",
                "total_source_document_weight",
                "issuer_attention_share",
                "attention_log",
                "attention_z",
                "attention_percentile_midrank",
                "attention_log_mean",
                "attention_log_sd",
            ],
        ),
    )

    for frame, columns in numeric_specs:
        for column in columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="raise",
            )

    failures = []
    passed = 0

    lines = [
        "=" * 128,
        "H3 STATISTICAL PREREGISTRATION V2 — INTEGRITY AUDIT",
        "=" * 128,
        "H3 outcome join authorized only if this gate passes.",
        "",
    ]

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if bool(condition):
            lines.append("PASS: " + success)
            passed += 1
        else:
            lines.append("FAIL: " + failure)
            failures.append(failure)

    check(
        len(diagnostics) == 0,
        "Same-issuer DAILY attention has zero unresolved simultaneous-security disagreements.",
        f"{len(diagnostics)} same-issuer/day disagreement row(s) remain.",
    )

    check(
        predictor[
            "preregistration_sha256"
        ].eq(prereg_sha).all()
        and issuer[
            "preregistration_sha256"
        ].eq(prereg_sha).all(),
        "Predictor outputs reproduce the frozen V2 preregistration checksum.",
        "A predictor output checksum differs from the frozen V2 preregistration.",
    )

    check(
        not issuer_day[
            ["date", "issuer_id"]
        ].duplicated().any(),
        "Issuer-day panel has exactly one row per issuer-date.",
        "Duplicate issuer-date rows remain after deduplication.",
    )

    check(
        not issuer[
            ["month", "issuer_id"]
        ].duplicated().any(),
        "Issuer attention panel has exactly one row per issuer-month.",
        "Duplicate issuer-month rows exist.",
    )

    check(
        not predictor[
            ["month", "security_key"]
        ].duplicated().any(),
        "Predictor panel has exactly one row per eligible security-month.",
        "Duplicate security-month rows exist.",
    )

    # Exact issuer-month reaggregation from issuer-days.
    recomputed = (
        issuer_day.groupby(
            ["month", "issuer_id"],
            as_index=False,
        )
        .agg(
            matched_recomputed=(
                "matched_source_document_weight", "sum"
            ),
            denominator_recomputed=(
                "total_source_document_weight", "sum"
            ),
        )
    )
    recomputed["share_recomputed"] = (
        recomputed["matched_recomputed"]
        / recomputed["denominator_recomputed"]
    )

    compare = issuer.merge(
        recomputed,
        on=["month", "issuer_id"],
        how="left",
        validate="one_to_one",
    )

    check(
        compare["matched_recomputed"].notna().all()
        and (
            compare["matched_source_document_weight"]
            == compare["matched_recomputed"]
        ).all()
        and (
            compare["total_source_document_weight"]
            == compare["denominator_recomputed"]
        ).all()
        and np.allclose(
            compare["issuer_attention_share"],
            compare["share_recomputed"],
            atol=1e-15,
            rtol=1e-12,
        ),
        "Issuer-month attention exactly reaggregates from unique issuer-days.",
        "Issuer-month attention differs from issuer-day reaggregation.",
    )

    # Frozen transform.
    scale = float(
        prereg["attention_primary"]["scale_constant"]
    )
    expected_log = np.log1p(
        scale * issuer["issuer_attention_share"]
    )

    check(
        np.allclose(
            issuer["attention_log"],
            expected_log,
            atol=1e-15,
            rtol=1e-12,
        ),
        "Issuer attention_log exactly reproduces the frozen V2 log1p transform.",
        "Issuer attention_log differs from the frozen V2 transform.",
    )

    zstats = (
        issuer.groupby("month")
        .agg(
            z_mean=("attention_z", "mean"),
            z_sd=("attention_z", lambda s: s.std(ddof=1)),
            issuer_count=("issuer_id", "nunique"),
        )
        .reset_index()
    )

    check(
        np.allclose(
            zstats["z_mean"],
            0.0,
            atol=1e-10,
            rtol=0.0,
        ),
        "Issuer-level attention_z has zero mean in every predictor month.",
        "A predictor month has non-zero issuer-level attention_z mean.",
    )

    check(
        np.allclose(
            zstats["z_sd"],
            1.0,
            atol=1e-10,
            rtol=0.0,
        ),
        "Issuer-level attention_z has sample SD 1 in every predictor month.",
        "A predictor month has issuer-level attention_z SD different from 1.",
    )

    min_cross = int(
        prereg[
            "sample_and_missingness"
        ]["minimum_cross_section_for_attention_z"]
    )

    check(
        zstats["issuer_count"].ge(min_cross).all(),
        f"Every predictor month contains at least {min_cross} eligible issuers.",
        "A predictor month has too few issuers for frozen standardization.",
    )

    # Every mapped security of the issuer gets the same issuer predictor.
    mapped = (
        predictor.groupby(
            ["month", "issuer_id"]
        )
        .agg(
            attention_share_nunique=(
                "issuer_attention_share", "nunique"
            ),
            attention_z_nunique=(
                "attention_z", "nunique"
            ),
            attention_log_nunique=(
                "attention_log", "nunique"
            ),
        )
        .reset_index()
    )

    check(
        mapped[
            [
                "attention_share_nunique",
                "attention_z_nunique",
                "attention_log_nunique",
            ]
        ].le(1).all().all(),
        "All eligible securities of an issuer-month receive identical frozen issuer attention values.",
        "At least one issuer-month maps different predictor values to its securities.",
    )

    check(
        predictor[
            "primary_attention_eligible_flag"
        ].eq(1).all(),
        "Every predictor security-month passed the fail-closed attention eligibility gate.",
        "An ineligible attention security-month remains in the predictor panel.",
    )

    start = prereg[
        "analysis_timing"
    ]["predictor_month_start"]
    end = prereg[
        "analysis_timing"
    ]["predictor_month_end"]

    check(
        predictor["month"].between(
            start,
            end,
            inclusive="both",
        ).all(),
        f"Every predictor month lies in the frozen {start} through {end} interval.",
        "A predictor row lies outside the frozen timing interval.",
    )

    check(
        issuer[
            "attention_percentile_midrank"
        ].between(
            0.0,
            1.0,
            inclusive="both",
        ).all(),
        "Prespecified issuer percentile robustness transform lies in [0, 1].",
        "A percentile robustness value lies outside [0, 1].",
    )

    # Trigger-case regression: same issuer should now be allowed to map
    # to multiple eligible securities without demanding equal pre-aggregated
    # security-month provenance ratios.
    trigger = predictor[
        (predictor["month"] == "2022-04")
        & (predictor["issuer_id"] == "0001437107")
    ]

    if len(trigger) >= 2:
        check(
            trigger["issuer_attention_share"].nunique() == 1
            and trigger["attention_z"].nunique() == 1,
            "2022-04 CIK 0001437107 maps one issuer-month predictor across its eligible security identities.",
            "The 2022-04 CIK 0001437107 regression control still disagrees after issuer-day aggregation.",
        )
    else:
        check(
            True,
            "2022-04 CIK 0001437107 has fewer than two eligible predictor securities; no mapping conflict remains.",
            "",
        )

    # Outcome firewall.
    all_columns = {
        str(column).casefold()
        for frame in (
            predictor,
            issuer_day,
            issuer,
            month_summary,
        )
        for column in frame.columns
    }
    forbidden_columns = [
        column
        for column in all_columns
        if any(
            fragment in column
            for fragment in FORBIDDEN
        )
    ]

    check(
        not forbidden_columns,
        "V2 preregistration outputs contain no return/momentum/Winner/outcome fields.",
        "Outcome-firewall violation: " + ", ".join(sorted(forbidden_columns)),
    )

    check(
        prereg[
            "inference"
        ]["cluster_structure"]
        == "Two-way cluster-robust covariance by issuer_id and outcome_month.",
        "Primary inference remains frozen to two-way issuer × outcome-month clustering.",
        "Primary clustering changed in V2.",
    )

    check(
        prereg[
            "multiple_testing"
        ]["method"]
        == "Holm-Bonferroni"
        and float(
            prereg[
                "multiple_testing"
            ]["familywise_alpha"]
        )
        == 0.05
        and len(
            prereg[
                "multiple_testing"
            ]["family"]
        )
        == 3,
        "H3A/H3B/H3C remain the frozen three-test Holm family at alpha 0.05.",
        "Multiple-testing family or alpha changed in V2.",
    )

    check(
        prereg[
            "preregistration_amendment"
        ]["outcomes_read_before_amendment"]
        is False,
        "V2 records that no outcomes were read before the issuer-day amendment.",
        "V2 amendment metadata does not preserve the outcome firewall.",
    )

    gate = (
        "H3_STATISTICAL_PREREGISTRATION_V2_INTEGRITY_AUDIT_PASSED"
        if not failures
        else
        "H3_STATISTICAL_PREREGISTRATION_V2_INTEGRITY_AUDIT_FAILED"
    )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Predictor months: {predictor['month'].nunique()}",
        f"Predictor security-month rows: {len(predictor)}",
        f"Issuer-day rows: {len(issuer_day)}",
        f"Issuer-month rows: {len(issuer)}",
        f"Unique issuer clusters: {predictor['issuer_id'].nunique()}",
        "",
        gate,
        "",
        (
            "A passing V2 gate freezes the corrected issuer-level attention construction "
            "and authorizes the deterministic H3 attention/outcome join."
        ),
    ]

    AUDIT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
