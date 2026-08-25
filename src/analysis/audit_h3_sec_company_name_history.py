from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-h3-sec-name-history-resolution-audit"

IN_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

MANIFEST_PATH = IN_DIR / "h3_company_query_manifest_candidates.csv"
MAPPING_PATH = IN_DIR / "h3_sec_cik_mapping_candidates.csv"
METADATA_PATH = IN_DIR / "h3_sec_submissions_company_metadata.csv"
FORMER_NAMES_PATH = IN_DIR / "h3_sec_former_names_raw.csv"
REVIEW_QUEUE_PATH = IN_DIR / "h3_sec_identity_resolution_review_queue.csv"
DOWNLOAD_LOG_PATH = IN_DIR / "h3_sec_submissions_download_log.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_sec_name_history_resolution_integrity_audit.txt"
)

EXPECTED_SECURITY_ROWS = 593

AUTO_STATUSES = {
    "AUTO_SOURCE_AGREEMENT",
    "AUTO_EXACT_TICKER_AND_NAME",
    "AUTO_UNIQUE_EXACT_NAME",
}

VALID_STATUSES = AUTO_STATUSES | {
    "REVIEW_TICKER_ONLY",
    "REVIEW_CONFLICT",
    "UNRESOLVED",
}


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        MANIFEST_PATH,
        MAPPING_PATH,
        METADATA_PATH,
        FORMER_NAMES_PATH,
        REVIEW_QUEUE_PATH,
        DOWNLOAD_LOG_PATH,
    ]

    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Stage 3B output(s): " + ", ".join(missing)
        )

    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
    )
    mapping = pd.read_csv(
        MAPPING_PATH,
        dtype=str,
        keep_default_na=False,
    )
    metadata = pd.read_csv(
        METADATA_PATH,
        dtype=str,
        keep_default_na=False,
    )
    former = pd.read_csv(
        FORMER_NAMES_PATH,
        dtype=str,
        keep_default_na=False,
    )
    review = pd.read_csv(
        REVIEW_QUEUE_PATH,
        dtype=str,
        keep_default_na=False,
    )
    downloads = pd.read_csv(
        DOWNLOAD_LOG_PATH,
        dtype=str,
        keep_default_na=False,
    )

    failures = []
    passed = 0

    lines = [
        "=" * 112,
        "H3 STAGE 3B — SEC NAME-HISTORY RESOLUTION INTEGRITY AUDIT",
        "=" * 112,
        "Full-history GDELT extraction authorized: NO",
        "H3 return/outcome analysis authorized: NO",
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
        len(manifest) == EXPECTED_SECURITY_ROWS,
        "Stage 3A manifest contains 593 identities.",
        f"Stage 3A manifest rows={len(manifest)}, expected 593.",
    )

    check(
        len(mapping) == EXPECTED_SECURITY_ROWS,
        "SEC mapping output contains all 593 identities.",
        f"SEC mapping rows={len(mapping)}, expected 593.",
    )

    check(
        mapping["security_key"].nunique() == EXPECTED_SECURITY_ROWS,
        "Every SEC mapping security key is unique.",
        "Duplicate security keys exist in SEC mapping output.",
    )

    check(
        set(mapping["mapping_status"]).issubset(VALID_STATUSES),
        "Every SEC mapping status is from the frozen status set.",
        "Unexpected SEC mapping status found.",
    )

    check(
        mapping.loc[
            mapping["mapping_status"].isin(AUTO_STATUSES),
            "candidate_sec_cik",
        ].str.fullmatch(r"\d{10}").all(),
        "Every auto-resolved mapping has a 10-digit SEC CIK.",
        "An auto-resolved mapping lacks a valid SEC CIK.",
    )

    if not metadata.empty:
        check(
            metadata["sec_cik"].nunique() == len(metadata),
            "SEC submissions metadata has one row per CIK.",
            "Duplicate SEC submissions metadata CIK found.",
        )
    else:
        check(
            False,
            "",
            "SEC submissions metadata is empty.",
        )

    mapped_ciks = set(
        mapping.loc[
            mapping["candidate_sec_cik"].ne(""),
            "candidate_sec_cik",
        ]
    )
    downloaded_ciks = set(
        metadata["sec_cik"]
    )

    check(
        mapped_ciks.issubset(downloaded_ciks),
        "Every candidate SEC CIK has parsed submissions metadata.",
        (
            f"{len(mapped_ciks - downloaded_ciks)} candidate CIK(s) "
            "lack parsed SEC submissions metadata."
        ),
    )

    check(
        not downloads["download_status"].eq("DOWNLOAD_FAILED").any(),
        "No SEC submissions request failed.",
        "At least one SEC submissions request failed.",
    )

    former_ciks = set(former["sec_cik"]) if not former.empty else set()

    check(
        former_ciks.issubset(downloaded_ciks),
        "Every former-name record belongs to a downloaded SEC filer.",
        "Former-name evidence references an unknown SEC CIK.",
    )

    review_keys = set(review["security_key"])
    expected_review_keys = set(
        mapping.loc[
            mapping["sec_resolution_review_flag"].eq("1"),
            "security_key",
        ]
    )

    check(
        review_keys == expected_review_keys,
        "Stage 3B review queue exactly reconstructs resolution-review flags.",
        "Stage 3B review queue differs from mapping review flags.",
    )

    check(
        set(
            mapping.loc[
                ~mapping["mapping_status"].isin(AUTO_STATUSES),
                "security_key",
            ]
        ).issubset(review_keys),
        "Every non-auto SEC mapping is in the review queue.",
        "A non-auto SEC mapping is missing from review queue.",
    )

    check(
        set(
            mapping.loc[
                mapping["former_name_evidence_flag"].eq("1"),
                "security_key",
            ]
        ).issubset(review_keys),
        "Every identity with SEC former-name evidence is in the review queue.",
        "Former-name evidence exists outside the review queue.",
    )

    forbidden = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )

    all_columns = {
        str(c).casefold()
        for c in (
            list(mapping.columns)
            + list(metadata.columns)
            + list(former.columns)
            + list(review.columns)
        )
    }

    bad = [
        c
        for c in all_columns
        if any(fragment in c for fragment in forbidden)
    ]

    check(
        not bad,
        "Stage 3B outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = "H3_SEC_NAME_HISTORY_RESOLUTION_INTEGRITY_AUDIT_FAILED"
    else:
        gate = "H3_SEC_NAME_HISTORY_RESOLUTION_INTEGRITY_AUDIT_PASSED"

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"SEC resolution review queue rows: {len(review)}",
        f"Raw SEC former-name rows: {len(former)}",
        "",
        gate,
        "",
        (
            "Passing this gate authorizes construction of PIT company-name "
            "alias intervals from authoritative evidence."
        ),
        (
            "It does NOT authorize full-history GDELT extraction or H3 inference."
        ),
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
