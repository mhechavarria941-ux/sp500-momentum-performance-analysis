from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v6-h3-pit-attention-alias-manifest-audit-precision-alignment"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

POLICY_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_pit_attention_alias_policy_v5.json"
)

MEMBERSHIP_PATH = (
    ROOT / "data" / "interim"
    / "sp500_membership_intervals_2021_2025.csv"
)

MANIFEST_PATH = H3_DIR / "h3_pit_attention_alias_intervals.csv"
COLLISIONS_PATH = H3_DIR / "h3_pit_attention_alias_collision_diagnostics.csv"
SHARED_ISSUER_COLLISIONS_PATH = H3_DIR / "h3_pit_attention_alias_shared_issuer_collisions.csv"
ALIAS_SAFETY_PATH = H3_DIR / "h3_pit_attention_alias_safety_diagnostics.csv"
TRANSITION_ALIGNMENT_PATH = H3_DIR / "h3_pit_attention_alias_transition_alignment_diagnostics.csv"
PRECISION_CONTROL_PATH = H3_DIR / "h3_pit_attention_alias_precision_control_diagnostics.csv"
SUMMARY_PATH = H3_DIR / "h3_pit_attention_alias_security_summary.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_pit_attention_alias_manifest_integrity_audit.txt"
)

SAMPLE_START = pd.Timestamp("2021-01-01")
SAMPLE_END = pd.Timestamp("2026-01-01")


LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "ltd", "limited", "plc", "llc", "llp", "lp", "nv", "ag", "se", "sa",
}


def normalize_full(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    raw = unicodedata.normalize("NFKC", str(value)).casefold()

    # Frozen provider/display corrections from Stage 3J policy.
    raw = re.sub(r"/\s*the\s*$", " ", raw)
    raw = re.sub(
        r"/\s*(?:de|md|mo|mn|ny|oh|nj|pa|va|ca|tx)\s*/",
        " ",
        raw,
    )

    raw = raw.replace("&", " and ")
    raw = re.sub(r"[’']", "", raw)
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    if raw.startswith("the "):
        raw = raw[4:].strip()

    tokens = raw.split()

    if len(tokens) >= 2 and tokens[-2] in {"class", "cl"}:
        tokens = tokens[:-2]

    return " ".join(tokens).strip()


def normalize_core(value: object) -> str:
    tokens = normalize_full(value).split()

    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens = tokens[:-1]

    return " ".join(tokens).strip()


def precision_control_valid(row: pd.Series) -> bool:
    """
    Policy V5 audit invariant.

    A HIGH-ambiguity or ticker-like row may legitimately differ from the raw
    state `full_normalized_alias` when V6 qualified a ticker-like state with a
    fuller authoritative issuer name, or when a true cross-issuer collision
    required qualified full-name escalation.

    The replacement is precision-preserving only when:
      1) production alias is nonblank;
      2) its conservative legal core is exactly the frozen state legal core;
      3) it is either the original full normalized state name OR its recorded
         selection reason is one of the qualified-full-name controls.

    This explicitly rejects broad legal-core aliases and semantic substitutions.
    """
    production = str(row.get("production_alias", "")).strip()
    full_alias = str(row.get("full_normalized_alias", "")).strip()
    state_core = str(row.get("legal_core_alias", "")).strip()
    reason = str(row.get("alias_selection_reason", "")).strip()

    if not production or not state_core:
        return False

    if normalize_core(production) != state_core:
        return False

    if production == full_alias:
        return True

    allowed_qualified_reasons = {
        "QUALIFIED_FULL_AUTHORITATIVE_NAME_BARE_TICKER_CONTROL",
        "QUALIFIED_FULL_AUTHORITATIVE_NAME_CROSS_ISSUER_COLLISION_ESCALATION",
    }

    return reason in allowed_qualified_reasons


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        POLICY_PATH,
        MEMBERSHIP_PATH,
        MANIFEST_PATH,
        COLLISIONS_PATH,
        SHARED_ISSUER_COLLISIONS_PATH,
        ALIAS_SAFETY_PATH,
        TRANSITION_ALIGNMENT_PATH,
        SUMMARY_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    policy_text = POLICY_PATH.read_text(
        encoding="utf-8"
    )
    policy_sha = hashlib.sha256(
        policy_text.encode("utf-8")
    ).hexdigest()

    membership = pd.read_csv(
        MEMBERSHIP_PATH,
        dtype=str,
        keep_default_na=False,
    )
    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
    )
    collisions = pd.read_csv(
        COLLISIONS_PATH,
        dtype=str,
        keep_default_na=False,
    )
    shared_issuer_collisions = pd.read_csv(
        SHARED_ISSUER_COLLISIONS_PATH,
        dtype=str,
        keep_default_na=False,
    )
    alias_safety = pd.read_csv(
        ALIAS_SAFETY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    transition_alignment = pd.read_csv(
        TRANSITION_ALIGNMENT_PATH,
        dtype=str,
        keep_default_na=False,
    )
    summary = pd.read_csv(
        SUMMARY_PATH,
        dtype=str,
        keep_default_na=False,
    )

    membership["start_dt"] = pd.to_datetime(
        membership["valid_from"],
        errors="raise",
        utc=True,
    ).dt.tz_convert(None)

    membership["end_dt"] = pd.to_datetime(
        membership["valid_to_exclusive"],
        errors="raise",
        utc=True,
    ).dt.tz_convert(None)

    manifest["start_dt"] = pd.to_datetime(
        manifest["alias_valid_from"],
        errors="raise",
    )
    manifest["end_dt"] = pd.to_datetime(
        manifest["alias_valid_to_exclusive"],
        errors="raise",
    )

    failures = []
    passed = 0

    lines = [
        "=" * 126,
        "H3 STAGE 3J — PIT ATTENTION ALIAS MANIFEST INTEGRITY AUDIT",
        "=" * 126,
        "Full-history GDELT extraction authorized: NO until this gate passes.",
        "H3 outcome analysis authorized: NO",
        "",
    ]

    def check(condition: bool, success: str, failure: str):
        nonlocal passed
        if bool(condition):
            lines.append("PASS: " + success)
            passed += 1
        else:
            lines.append("FAIL: " + failure)
            failures.append(failure)

    expected_keys = set(
        membership.loc[
            (membership["start_dt"] < SAMPLE_END)
            & (membership["end_dt"] > SAMPLE_START),
            "security_key",
        ]
    )

    manifest_keys = set(
        manifest["security_key"]
    )

    check(
        manifest_keys == expected_keys,
        (
            "Alias manifest security universe exactly equals the set of "
            "membership identities overlapping 2021-2025."
        ),
        (
            f"Alias security universe mismatch: expected {len(expected_keys)}, "
            f"found {len(manifest_keys)}."
        ),
    )

    check(
        manifest["production_alias"].ne("").all(),
        "Every alias interval has a nonblank production alias.",
        "A production alias is blank.",
    )

    check(
        manifest["matching_mode"].eq(
            "EXACT_NORMALIZED_GKG_ORGANIZATION"
        ).all(),
        "Every row uses the frozen exact normalized GKG organization mode.",
        "Unexpected matching mode found.",
    )

    check(
        manifest["policy_sha256"].eq(
            policy_sha
        ).all(),
        "Every manifest row reproduces the frozen policy checksum.",
        "Manifest policy checksum differs from frozen policy file.",
    )

    check(
        (manifest["start_dt"] < manifest["end_dt"]).all(),
        "Every alias interval has positive duration.",
        "A zero/negative alias interval exists.",
    )

    # No overlap and no gap inside each clipped membership interval.
    membership_lookup = membership.set_index(
        "security_key"
    )

    interval_failures = []

    for sk, group in manifest.groupby("security_key"):
        group = group.sort_values("start_dt")

        m = membership_lookup.loc[sk]
        expected_start = max(
            m["start_dt"],
            SAMPLE_START,
        )
        expected_end = min(
            m["end_dt"],
            SAMPLE_END,
        )

        if group.iloc[0]["start_dt"] != expected_start:
            interval_failures.append(
                f"{sk}: first alias interval does not start at clipped membership start"
            )

        if group.iloc[-1]["end_dt"] != expected_end:
            interval_failures.append(
                f"{sk}: final alias interval does not end at clipped membership end"
            )

        prev_end = None
        for row in group.itertuples(index=False):
            if prev_end is not None and row.start_dt != prev_end:
                interval_failures.append(
                    f"{sk}: alias interval gap/overlap at {row.start_dt}"
                )
            prev_end = row.end_dt

    check(
        not interval_failures,
        (
            "Alias intervals exactly partition every security's clipped "
            "membership interval with no gaps or overlaps."
        ),
        (
            f"{len(interval_failures)} membership-partition issue(s) found. "
            + ("; ".join(interval_failures[:5]) if interval_failures else "")
        ),
    )

    check(
        len(collisions) == 0,
        (
            "No blocking overlapping cross-issuer or unresolved-issuer "
            "production alias collision remains."
        ),
        (
            f"{len(collisions)} blocking cross/unresolved-issuer alias "
            "collision(s) remain."
        ),
    )

    if not shared_issuer_collisions.empty:
        check(
            shared_issuer_collisions["left_issuer_cik"].ne("").all()
            and shared_issuer_collisions["right_issuer_cik"].ne("").all()
            and (
                shared_issuer_collisions["left_issuer_cik"]
                == shared_issuer_collisions["right_issuer_cik"]
            ).all()
            and shared_issuer_collisions["collision_class"].eq(
                "SHARED_ISSUER_MULTI_SECURITY_ALIAS"
            ).all(),
            (
                "Every allowed shared alias overlap is explicitly tied to "
                "the same nonblank authoritative issuer CIK."
            ),
            (
                "An allowed shared-issuer alias overlap lacks same-CIK "
                "authoritative support."
            ),
        )
    else:
        check(
            True,
            "No same-issuer multi-security shared alias overlaps require allowance.",
            "",
        )

    check(
        len(alias_safety) == 0,
        "Alias-safety preflight contains zero unresolved qualification issues.",
        f"{len(alias_safety)} unresolved alias-safety issue(s) remain.",
    )

    check(
        len(transition_alignment) == 0,
        (
            "All authoritative transition chains and static-source-to-chain "
            "alignments passed the batch preflight."
        ),
        (
            f"{len(transition_alignment)} transition alignment issue(s) "
            "remain."
        ),
    )

    check(
        manifest["bare_ticker_alias_flag"].eq("0").all(),
        "No production alias is an explicitly detected bare stock ticker.",
        (
            f"{int(manifest['bare_ticker_alias_flag'].eq('1').sum())} "
            "bare-ticker alias row(s) remain."
        ),
    )

    high = manifest[
        manifest["structural_ambiguity_tier"].eq(
            "HIGH"
        )
    ].copy()

    ticker_like = manifest[
        manifest["ticker_like_exact_name_flag"].eq(
            "1"
        )
    ].copy()

    high["precision_control_valid"] = high.apply(
        precision_control_valid,
        axis=1,
    )
    ticker_like["precision_control_valid"] = ticker_like.apply(
        precision_control_valid,
        axis=1,
    )

    precision_bad = pd.concat(
        [
            high.loc[
                ~high["precision_control_valid"],
                [
                    "security_key",
                    "latest_project_ticker",
                    "structural_ambiguity_tier",
                    "ticker_like_exact_name_flag",
                    "authoritative_state_name",
                    "full_normalized_alias",
                    "legal_core_alias",
                    "production_alias",
                    "alias_selection_reason",
                    "bare_ticker_qualification_source",
                ],
            ],
            ticker_like.loc[
                ~ticker_like["precision_control_valid"],
                [
                    "security_key",
                    "latest_project_ticker",
                    "structural_ambiguity_tier",
                    "ticker_like_exact_name_flag",
                    "authoritative_state_name",
                    "full_normalized_alias",
                    "legal_core_alias",
                    "production_alias",
                    "alias_selection_reason",
                    "bare_ticker_qualification_source",
                ],
            ],
        ],
        ignore_index=True,
    ).drop_duplicates()

    precision_bad.to_csv(
        PRECISION_CONTROL_PATH,
        index=False,
    )

    check(
        high["precision_control_valid"].all(),
        (
            "Every HIGH-ambiguity row uses either its full normalized state "
            "name or a qualified full authoritative alias with the exact same "
            "legal core."
        ),
        (
            f"{int((~high['precision_control_valid']).sum())} HIGH-ambiguity "
            "row(s) fail the precision-preserving alias invariant."
        ),
    )

    check(
        ticker_like["precision_control_valid"].all(),
        (
            "Every ticker-like issuer-name row uses either its full normalized "
            "state name or a qualified full authoritative alias with the exact "
            "same legal core."
        ),
        (
            f"{int((~ticker_like['precision_control_valid']).sum())} "
            "ticker-like issuer-name row(s) fail the precision-preserving "
            "alias invariant."
        ),
    )

    forbidden = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )

    columns = {
        str(c).casefold()
        for c in manifest.columns
    }

    bad = [
        c for c in columns
        if any(fragment in c for fragment in forbidden)
    ]

    check(
        not bad,
        "Alias manifest contains no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like columns found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = (
            "H3_PIT_ATTENTION_ALIAS_MANIFEST_INTEGRITY_AUDIT_FAILED"
        )
    else:
        gate = (
            "H3_PIT_ATTENTION_ALIAS_MANIFEST_INTEGRITY_AUDIT_PASSED"
        )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Alias security identities: {manifest['security_key'].nunique()}",
        f"Alias intervals: {len(manifest)}",
        f"Identities with >1 interval: {int(pd.to_numeric(summary['alias_interval_count']).gt(1).sum())}",
        f"Precision-control diagnostic rows: {len(precision_bad)}",
        "",
        gate,
        "",
        (
            "Passing Stage 3J freezes the primary PIT attention-alias "
            "construction policy."
        ),
        (
            "The next authorized step is a no-outcome GDELT coverage/missingness "
            "gate. Full-history H3 inference is still not authorized."
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
