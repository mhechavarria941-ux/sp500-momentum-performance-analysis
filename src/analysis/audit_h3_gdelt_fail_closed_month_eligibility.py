from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-26-v1-h3-gdelt-fail-closed-month-eligibility-audit"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

POLICY_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_fail_closed_month_eligibility_v1.json"
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

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_gdelt_fail_closed_month_eligibility_audit.txt"
)

FORBIDDEN = (
    "return",
    "momentum",
    "winner",
    "commonality_factor",
    "outcome",
)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        POLICY_PATH,
        MONTH_ELIGIBILITY_PATH,
        PRIMARY_MONTHLY_PATH,
        EXCLUDED_MONTHS_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    policy = json.loads(policy_text)
    policy_sha = hashlib.sha256(
        policy_text.encode("utf-8")
    ).hexdigest()

    months = pd.read_csv(
        MONTH_ELIGIBILITY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    monthly = pd.read_csv(
        PRIMARY_MONTHLY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    excluded_months = pd.read_csv(
        EXCLUDED_MONTHS_PATH,
        dtype=str,
        keep_default_na=False,
    )

    for frame, columns in (
        (
            months,
            [
                "source_coverage_rate",
                "global_primary_attention_eligible_flag",
            ],
        ),
        (
            monthly,
            [
                "source_coverage_rate",
                "global_primary_attention_eligible_flag",
                "security_month_source_eligible_flag",
                "primary_attention_eligible_flag",
                "primary_attention_unavailable_flag",
            ],
        ),
    ):
        for column in columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="raise",
            )

    month_threshold = float(
        policy["thresholds"][
            "minimum_calendar_month_source_coverage"
        ]
    )
    security_threshold = float(
        policy["thresholds"][
            "minimum_security_month_source_coverage"
        ]
    )

    failures = []
    passed = 0

    lines = [
        "=" * 128,
        "H3 STAGE 3L — FAIL-CLOSED PRIMARY MONTH ELIGIBILITY AUDIT",
        "=" * 128,
        "H3 statistical inference authorized: NO",
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
        months["fail_closed_policy_sha256"].eq(
            policy_sha
        ).all()
        and monthly["fail_closed_policy_sha256"].eq(
            policy_sha
        ).all(),
        "All outputs reproduce the frozen fail-closed policy checksum.",
        "An output checksum differs from the frozen fail-closed policy.",
    )

    expected_global = (
        months["source_coverage_rate"]
        >= month_threshold
    ).astype(int)

    check(
        months[
            "global_primary_attention_eligible_flag"
        ].equals(expected_global),
        (
            "Global month eligibility is exactly the frozen "
            "90% source-coverage rule."
        ),
        "Global month eligibility differs from the frozen threshold rule.",
    )

    expected_excluded = set(
        months.loc[
            months[
                "global_primary_attention_eligible_flag"
            ].eq(0),
            "month",
        ]
    )

    check(
        set(excluded_months["month"])
        == expected_excluded,
        "Excluded-month ledger exactly matches globally undercovered months.",
        "Excluded-month ledger differs from globally undercovered months.",
    )

    check(
        monthly[
            ["month", "security_key"]
        ].duplicated().sum()
        == 0,
        "Primary monthly attention panel has exactly one row per security-month.",
        "Duplicate security-month rows exist.",
    )

    month_flag_lookup = months.set_index(
        "month"
    )["global_primary_attention_eligible_flag"]

    mapped_global = monthly[
        "month"
    ].map(month_flag_lookup)

    check(
        mapped_global.notna().all()
        and (
            mapped_global.astype(int)
            == monthly[
                "global_primary_attention_eligible_flag"
            ]
        ).all(),
        "Every security in a calendar month receives the same global month eligibility.",
        "Global month eligibility is not uniform across the cross-section.",
    )

    expected_security = (
        monthly["source_coverage_rate"]
        >= security_threshold
    ).astype(int)

    check(
        (
            monthly[
                "security_month_source_eligible_flag"
            ]
            == expected_security
        ).all(),
        "Security-month coverage flag exactly follows the frozen 90% threshold.",
        "Security-month coverage flag differs from the frozen threshold.",
    )

    expected_primary = (
        monthly[
            "global_primary_attention_eligible_flag"
        ].eq(1)
        & monthly[
            "security_month_source_eligible_flag"
        ].eq(1)
    ).astype(int)

    check(
        (
            monthly["primary_attention_eligible_flag"]
            == expected_primary
        ).all(),
        "Primary attention eligibility equals global-month AND security-month coverage eligibility.",
        "Primary attention eligibility does not reproduce the frozen fail-closed rule.",
    )

    retained = monthly[
        monthly["primary_attention_eligible_flag"].eq(1)
    ]

    check(
        retained["source_coverage_rate"].ge(
            security_threshold
        ).all(),
        "Every retained security-month meets the frozen source-coverage threshold.",
        "A retained security-month falls below the frozen threshold.",
    )

    retained_months = set(retained["month"])
    bad_global_retained = months[
        months["month"].isin(retained_months)
        & (
            months["source_coverage_rate"]
            < month_threshold
        )
    ]

    check(
        bad_global_retained.empty,
        "No globally undercovered calendar month is retained in the primary H3 attention series.",
        "A globally undercovered calendar month remains in the primary series.",
    )

    # Undercovered rows remain explicitly unavailable; no attempt is made
    # to reinterpret missing source coverage as zero attention.
    unavailable = monthly[
        monthly[
            "primary_attention_eligible_flag"
        ].eq(0)
    ]

    check(
        (
            unavailable[
                "primary_attention_unavailable_flag"
            ]
            == 1
        ).all(),
        "Every excluded security-month is explicitly marked unavailable.",
        "An excluded security-month is not marked unavailable.",
    )

    all_columns = {
        str(c).casefold()
        for frame in (months, monthly, excluded_months)
        for c in frame.columns
    }
    bad_fields = [
        c
        for c in all_columns
        if any(fragment in c for fragment in FORBIDDEN)
    ]

    check(
        not bad_fields,
        "Fail-closed eligibility outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad_fields)),
    )

    gate = (
        "H3_FULL_GDELT_ATTENTION_ACQUISITION_CLOSED_FAIL_CLOSED_MONTH_ELIGIBILITY"
        if not failures
        else
        "H3_GDELT_FAIL_CLOSED_MONTH_ELIGIBILITY_AUDIT_FAILED"
    )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Calendar months: {len(months)}",
        f"Globally excluded months: {len(expected_excluded)}",
        (
            "Excluded months: "
            + ",".join(sorted(expected_excluded))
        ),
        f"Monthly security rows: {len(monthly)}",
        f"Primary eligible security-month rows: {len(retained)}",
        "",
        gate,
        "",
        (
            "A passing gate closes the primary GKG 1.0 attention acquisition "
            "layer without relaxing the frozen 90% coverage threshold."
        ),
        (
            "The next authorized task is H3 statistical preregistration before "
            "any attention/outcome join."
        ),
    ]

    AUDIT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(text, end="")


if __name__ == "__main__":
    main()
