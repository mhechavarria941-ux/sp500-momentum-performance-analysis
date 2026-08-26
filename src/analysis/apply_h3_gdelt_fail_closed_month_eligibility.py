from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-26-v1-h3-gdelt-fail-closed-month-eligibility"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

POLICY_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_fail_closed_month_eligibility_v1.json"
)

SOURCE_GAP_POLICY_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_source_gap_handling_v1.json"
)

MONTH_COVERAGE_PATH = (
    H3_DIR / "h3_gdelt_full_calendar_month_source_coverage.csv"
)
MONTHLY_ATTENTION_PATH = (
    H3_DIR / "h3_gdelt_full_monthly_security_attention.csv"
)

MONTH_ELIGIBILITY_PATH = (
    H3_DIR / "h3_gdelt_primary_month_eligibility.csv"
)
PRIMARY_MONTHLY_PATH = (
    H3_DIR / "h3_gdelt_primary_monthly_security_attention.csv"
)
EXCLUDED_MONTHS_PATH = (
    H3_DIR / "h3_gdelt_primary_excluded_months.csv"
)
REPORT_PATH = (
    H3_DIR / "h3_gdelt_fail_closed_month_eligibility_report.txt"
)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        POLICY_PATH,
        SOURCE_GAP_POLICY_PATH,
        MONTH_COVERAGE_PATH,
        MONTHLY_ATTENTION_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    policy = json.loads(policy_text)
    policy_sha = hashlib.sha256(
        policy_text.encode("utf-8")
    ).hexdigest()

    source_gap_text = SOURCE_GAP_POLICY_PATH.read_text(
        encoding="utf-8"
    )
    source_gap_sha = hashlib.sha256(
        source_gap_text.encode("utf-8")
    ).hexdigest()

    month_cov = pd.read_csv(
        MONTH_COVERAGE_PATH,
        dtype=str,
        keep_default_na=False,
    )
    monthly = pd.read_csv(
        MONTHLY_ATTENTION_PATH,
        dtype=str,
        keep_default_na=False,
    )

    for frame, columns in (
        (
            month_cov,
            [
                "expected_calendar_days",
                "source_available_days",
                "source_missing_days",
                "source_coverage_rate",
            ],
        ),
        (
            monthly,
            [
                "source_available_days",
                "expected_active_calendar_days",
                "source_missing_days",
                "source_coverage_rate",
                "attention_share",
            ],
        ),
    ):
        for column in columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="raise",
            )

    threshold_month = float(
        policy["thresholds"][
            "minimum_calendar_month_source_coverage"
        ]
    )
    threshold_security_month = float(
        policy["thresholds"][
            "minimum_security_month_source_coverage"
        ]
    )

    # --------------------------------------------------------------
    # Global month eligibility is determined solely by GDELT source
    # coverage, before any H3 outcomes are read.
    # --------------------------------------------------------------
    month_cov["global_primary_attention_eligible_flag"] = (
        month_cov["source_coverage_rate"]
        >= threshold_month
    ).astype(int)

    month_cov["primary_attention_exclusion_reason"] = ""
    month_cov.loc[
        month_cov[
            "global_primary_attention_eligible_flag"
        ].eq(0),
        "primary_attention_exclusion_reason",
    ] = "GLOBAL_GKG1_SOURCE_COVERAGE_BELOW_FROZEN_90PCT"

    month_cov["fail_closed_policy_id"] = policy["policy_id"]
    month_cov["fail_closed_policy_sha256"] = policy_sha
    month_cov["source_gap_policy_sha256"] = source_gap_sha

    month_cov.to_csv(
        MONTH_ELIGIBILITY_PATH,
        index=False,
    )

    excluded_months = month_cov[
        month_cov[
            "global_primary_attention_eligible_flag"
        ].eq(0)
    ].copy()

    excluded_months.to_csv(
        EXCLUDED_MONTHS_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Apply global month eligibility to every security uniformly.
    # This avoids keeping only securities whose individual interval
    # happened to overlap the available portion of an undercovered
    # calendar month.
    # --------------------------------------------------------------
    monthly = monthly.merge(
        month_cov[
            [
                "month",
                "global_primary_attention_eligible_flag",
                "primary_attention_exclusion_reason",
            ]
        ],
        on="month",
        how="left",
        validate="many_to_one",
    )

    if monthly[
        "global_primary_attention_eligible_flag"
    ].isna().any():
        raise RuntimeError(
            "A security-month did not map to global month eligibility."
        )

    monthly["security_month_source_eligible_flag"] = (
        monthly["source_coverage_rate"]
        >= threshold_security_month
    ).astype(int)

    monthly["primary_attention_eligible_flag"] = (
        monthly[
            "global_primary_attention_eligible_flag"
        ].eq(1)
        & monthly[
            "security_month_source_eligible_flag"
        ].eq(1)
    ).astype(int)

    monthly["primary_attention_unavailable_flag"] = (
        1 - monthly["primary_attention_eligible_flag"]
    )

    monthly["fail_closed_policy_id"] = policy["policy_id"]
    monthly["fail_closed_policy_sha256"] = policy_sha

    # Attention is retained numerically for provenance/audit, but rows
    # with eligible_flag=0 are forbidden from the primary H3 join.
    monthly.to_csv(
        PRIMARY_MONTHLY_PATH,
        index=False,
    )

    retained = monthly[
        monthly["primary_attention_eligible_flag"].eq(1)
    ]
    excluded = monthly[
        monthly["primary_attention_eligible_flag"].eq(0)
    ]

    retained_months = sorted(
        retained["month"].unique().tolist()
    )
    excluded_global_months = sorted(
        excluded_months["month"].tolist()
    )

    min_retained_global = (
        month_cov.loc[
            month_cov[
                "global_primary_attention_eligible_flag"
            ].eq(1),
            "source_coverage_rate",
        ].min()
    )
    min_retained_security = (
        retained["source_coverage_rate"].min()
        if not retained.empty
        else float("nan")
    )

    lines = [
        "=" * 128,
        "H3 STAGE 3L — FAIL-CLOSED PRIMARY MONTH ELIGIBILITY",
        "=" * 128,
        f"Policy ID: {policy['policy_id']}",
        f"Policy SHA-256: {policy_sha}",
        f"Calendar months evaluated: {len(month_cov)}",
        f"Globally eligible primary attention months: {int(month_cov['global_primary_attention_eligible_flag'].sum())}",
        f"Globally excluded primary attention months: {len(excluded_months)}",
        f"Excluded global months: {','.join(excluded_global_months)}",
        f"Security-month rows: {len(monthly)}",
        f"Eligible primary security-month rows: {len(retained)}",
        f"Unavailable primary security-month rows: {len(excluded)}",
        "",
        "FROZEN THRESHOLDS:",
        f"  Global calendar month >= {threshold_month:.2%}",
        f"  Security-month >= {threshold_security_month:.2%}",
        "",
        "RETAINED COVERAGE:",
        f"  Minimum retained global month coverage: {min_retained_global:.6f}",
        f"  Minimum retained security-month coverage: {min_retained_security:.6f}",
        "",
        "Undercovered source months zero-filled: NO",
        "Undercovered source months partially retained cross-sectionally: NO",
        "GKG 2.x mixed into primary series: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_GDELT_PRIMARY_MONTH_ELIGIBILITY_APPLIED",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )
    print(report, end="")


if __name__ == "__main__":
    main()
