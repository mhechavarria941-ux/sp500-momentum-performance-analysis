from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-h3-company-query-manifest-tickerlike-name-audit"

OUT_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

SECURITY_PATH = OUT_DIR / "h3_core_security_snapshot.csv"
TICKER_HISTORY_PATH = OUT_DIR / "h3_core_security_ticker_history_snapshot.csv"
MANIFEST_PATH = OUT_DIR / "h3_company_query_manifest_candidates.csv"
REVIEW_QUEUE_PATH = OUT_DIR / "h3_company_name_history_review_queue.csv"
ALIAS_COLLISION_PATH = OUT_DIR / "h3_company_exact_alias_collision_audit.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_company_query_manifest_candidate_integrity_audit.txt"
)

EXPECTED_SECURITY_ROWS = 593
EXPECTED_TICKER_HISTORY_ROWS = 594


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        SECURITY_PATH,
        TICKER_HISTORY_PATH,
        MANIFEST_PATH,
        REVIEW_QUEUE_PATH,
        ALIAS_COLLISION_PATH,
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Missing H3 identity-manifest output(s): "
            + ", ".join(missing)
        )

    security = pd.read_csv(
        SECURITY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    ticker_history = pd.read_csv(
        TICKER_HISTORY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
    )
    review = pd.read_csv(
        REVIEW_QUEUE_PATH,
        dtype=str,
        keep_default_na=False,
    )
    collisions = pd.read_csv(
        ALIAS_COLLISION_PATH,
        dtype=str,
        keep_default_na=False,
    )

    failures = []
    passed = 0

    lines = [
        "=" * 112,
        "H3 FULL-UNIVERSE COMPANY QUERY MANIFEST — CANDIDATE INTEGRITY AUDIT",
        "=" * 112,
        "Return/outcome analysis permitted: NO",
        "Production GDELT extraction authorized by this audit: NO",
        "",
    ]

    def check(
        condition: bool,
        success: str,
        failure: str,
    ) -> None:
        nonlocal passed

        if bool(condition):
            lines.append(
                "PASS: " + success
            )
            passed += 1
        else:
            lines.append(
                "FAIL: " + failure
            )
            failures.append(
                failure
            )

    check(
        len(security) == EXPECTED_SECURITY_ROWS,
        "Core security snapshot contains 593 identities.",
        (
            f"Core security snapshot rows={len(security)}, "
            "expected 593."
        ),
    )

    check(
        len(ticker_history)
        == EXPECTED_TICKER_HISTORY_ROWS,
        "Core ticker-history snapshot contains 594 segments.",
        (
            f"Ticker-history rows={len(ticker_history)}, "
            "expected 594."
        ),
    )

    check(
        len(manifest) == EXPECTED_SECURITY_ROWS,
        "Candidate manifest contains one row for all 593 identities.",
        (
            f"Candidate manifest rows={len(manifest)}, "
            "expected 593."
        ),
    )

    check(
        manifest["security_key"].nunique()
        == EXPECTED_SECURITY_ROWS,
        "Every candidate-manifest security key is unique.",
        "Candidate manifest contains duplicate security keys.",
    )

    ticker_segments = pd.to_numeric(
        manifest[
            "ticker_segment_count"
        ],
        errors="raise",
    )

    check(
        int(ticker_segments.sum())
        == EXPECTED_TICKER_HISTORY_ROWS,
        "Candidate manifest reconstructs all 594 ticker-history segments.",
        (
            f"Reconstructed ticker segments={int(ticker_segments.sum())}, "
            "expected 594."
        ),
    )

    check(
        manifest[
            "canonical_company_name"
        ].str.strip().ne("").all(),
        "Every security has a nonblank canonical company/security name.",
        "At least one canonical company/security name is blank.",
    )

    check(
        manifest[
            "exact_legal_name_alias"
        ].str.strip().ne("").all(),
        "Every security has a nonblank exact normalized name alias.",
        "At least one exact normalized alias is blank.",
    )

    check(
        manifest[
            "production_aliases_pipe"
        ].eq(
            manifest[
                "exact_legal_name_alias"
            ]
        ).all(),
        (
            "Production-candidate aliases contain only the exact "
            "normalized legal/current name."
        ),
        (
            "At least one candidate production alias was broadened "
            "before PIT name-history review."
        ),
    )

    check(
        manifest[
            "current_name_point_in_time_validated"
        ].eq("0").all(),
        (
            "No current company name is incorrectly marked "
            "point-in-time validated."
        ),
        (
            "A current company name was marked PIT-validated "
            "before authoritative review."
        ),
    )

    check(
        manifest[
            "production_alias_status"
        ].eq(
            "CANDIDATE_EXACT_NAME_ONLY_"
            "PENDING_PIT_NAME_HISTORY_REVIEW"
        ).all(),
        "Every row remains explicitly non-production pending PIT review.",
        "At least one row has an unauthorized production status.",
    )

    # Legitimate issuer names can themselves be ticker-like acronyms/brands.
    # This is not a failure when the alias came from the canonical company-name
    # field. The required control is that every such case is explicitly flagged
    # HIGH ambiguity and placed in the authoritative-name review queue.
    if "ticker_like_exact_name_flag" not in manifest.columns:
        raise RuntimeError(
            "V2 audit requires ticker_like_exact_name_flag. "
            "Re-run the V3/V4 candidate builder first."
        )

    ticker_like = manifest[
        manifest["ticker_like_exact_name_flag"].eq("1")
    ].copy()

    check(
        ticker_like["structural_ambiguity_tier"].eq("HIGH").all(),
        (
            "Every ticker-like exact legal/current company name is "
            "classified HIGH ambiguity."
        ),
        (
            "At least one ticker-like exact company name is not "
            "classified HIGH ambiguity."
        ),
    )

    check(
        set(ticker_like["security_key"]).issubset(
            set(review["security_key"])
        ),
        (
            "Every ticker-like exact legal/current company name is "
            "present in the authoritative-name review queue."
        ),
        (
            "At least one ticker-like exact company name is missing "
            "from the authoritative-name review queue."
        ),
    )

    collision_keys = set(
        collisions["security_key"]
    )
    manifest_collision_keys = set(
        manifest.loc[
            manifest[
                "duplicate_exact_alias_flag"
            ].eq("1"),
            "security_key",
        ]
    )

    check(
        collision_keys
        == manifest_collision_keys,
        "Exact-alias collision report reconstructs manifest collision flags.",
        "Alias collision report differs from manifest flags.",
    )

    review_keys = set(
        review["security_key"]
    )
    manifest_review_keys = set(
        manifest.loc[
            manifest[
                "historical_name_review_flag"
            ].eq("1"),
            "security_key",
        ]
    )

    check(
        review_keys
        == manifest_review_keys,
        "Name-history review queue reconstructs manifest review flags.",
        "Name-history review queue differs from manifest flags.",
    )

    forbidden = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )

    columns = {
        str(column).casefold()
        for column in (
            list(manifest.columns)
            + list(review.columns)
        )
    }

    bad_columns = [
        column
        for column in columns
        if any(
            fragment in column
            for fragment in forbidden
        )
    ]

    check(
        not bad_columns,
        "Manifest/review outputs contain no return or outcome fields.",
        (
            "Prohibited outcome-like columns found: "
            + ", ".join(
                sorted(bad_columns)
            )
        ),
    )

    if failures:
        gate = (
            "H3_COMPANY_QUERY_MANIFEST_CANDIDATE_"
            "INTEGRITY_AUDIT_FAILED"
        )
    else:
        gate = (
            "H3_COMPANY_QUERY_MANIFEST_CANDIDATE_"
            "INTEGRITY_AUDIT_PASSED"
        )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"PIT/name-history review queue rows: {len(review)}",
        f"Exact-alias collision rows: {len(collisions)}",
        (
            "Ticker-like exact legal/current-name rows: "
            f"{int(manifest['ticker_like_exact_name_flag'].eq('1').sum())}"
        ),
        "",
        gate,
        "",
        (
            "Passing this audit authorizes authoritative "
            "company-name-history resolution only."
        ),
        (
            "It does NOT authorize full-history attention extraction "
            "or H3 inference."
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
