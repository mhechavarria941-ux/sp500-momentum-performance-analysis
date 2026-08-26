from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-stage3j-all-transition-name-alignment-preflight"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

CANDIDATE_PATH = H3_DIR / "h3_company_query_manifest_candidates.csv"
MEMBERSHIP_PATH = ROOT / "data" / "interim" / "sp500_membership_intervals_2021_2025.csv"
NPORT_OBS_PATH = H3_DIR / "h3_pit_name_state_observations.csv"

STAGE3C_PATH = H3_DIR / "h3_exact_name_transition_resolutions.csv"
STAGE3D_PATH = H3_DIR / "h3_authoritative_exact_name_transition_resolutions.csv"
STAGE3G_PATH = H3_DIR / "h3_authoritative_name_state_closeout.csv"
STAGE3I_PATH = H3_DIR / "h3_no_nport_definitive_closure.csv"
STAGE3I_EVENTS_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_no_nport_known_name_state_events.csv"
)

DIAGNOSTIC_PATH = H3_DIR / "h3_stage3j_transition_name_alignment_diagnostics.csv"
CHAIN_PATH = H3_DIR / "h3_stage3j_transition_chain_diagnostics.csv"
REPORT_PATH = H3_DIR / "h3_stage3j_transition_name_alignment_preflight_report.txt"

SAMPLE_START = pd.Timestamp("2021-01-01")
SAMPLE_END = pd.Timestamp("2026-01-01")

LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "ltd", "limited", "plc", "llc", "llp", "lp", "nv", "ag", "se", "sa",
}


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def parse_dt(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce", utc=True).tz_convert(None)


def normalize_full_policy_v2(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    raw = unicodedata.normalize("NFKC", str(value)).casefold()

    # Current Stage 3J Policy V2 display corrections.
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


def normalize_core_policy_v2(value: object) -> str:
    tokens = normalize_full_policy_v2(value).split()

    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens = tokens[:-1]

    return " ".join(tokens).strip()


def compact(value: object) -> str:
    """
    Diagnostic only. Never used as a production alias.

    Collapses a Policy-V2 legal core to alphanumerics so punctuation-tokenization
    artifacts such as:
        CAMPBELL S  <->  Campbell's
    can be detected in one batch.
    """
    return re.sub(r"[^a-z0-9]", "", normalize_core_policy_v2(value))


def token_multiset(value: object) -> tuple[str, ...]:
    return tuple(sorted(normalize_core_policy_v2(value).split()))


def latest_nport_name(
    observations: pd.DataFrame,
    security_key: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> str:
    subset = observations[
        observations["security_key"].astype(str).eq(security_key)
    ].copy()

    if subset.empty:
        return ""

    subset["report_dt"] = pd.to_datetime(
        subset["report_date"],
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)

    subset = subset[
        subset["report_dt"].notna()
        & (subset["report_dt"] >= start)
        & (subset["report_dt"] < end)
    ].sort_values(["report_dt", "holding_name"])

    if subset.empty:
        return ""

    return str(subset.iloc[-1]["holding_name"]).strip()


def effective_boundary(public_date: object, legal_date: object) -> pd.Timestamp:
    public_dt = parse_dt(public_date)
    if pd.notna(public_dt):
        return public_dt
    return parse_dt(legal_date)


def collect_events(
    stage3c: pd.DataFrame,
    stage3d: pd.DataFrame,
    stage3g: pd.DataFrame,
    stage3i_events: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for row in stage3c.itertuples(index=False):
        if str(row.resolution_status) != "RESOLVED_EXACT":
            continue
        d = str(row.exact_effective_date)
        rows.append({
            "security_key": str(row.security_key),
            "old_company_name": str(row.from_name_key),
            "new_company_name": str(row.to_name_key),
            "public_effective_date": d,
            "legal_effective_date": d,
            "source_layer": "STAGE3C_AUTO_EXACT",
        })

    for row in stage3d.itertuples(index=False):
        if not str(row.resolution_status).startswith(
            "RESOLVED_TRUE_LEGAL_RENAME"
        ):
            continue
        rows.append({
            "security_key": str(row.security_key),
            "old_company_name": str(row.from_name_key),
            "new_company_name": str(row.to_name_key),
            "public_effective_date": str(
                getattr(row, "public_or_trading_effective_date", "")
            ),
            "legal_effective_date": str(
                getattr(row, "exact_legal_effective_date", "")
            ),
            "source_layer": "STAGE3D_AUTHORITATIVE_RENAME",
        })

    transition_categories = {
        "TRUE_PUBLIC_LEGAL_NAME_TRANSITION_BRAND_CONTINUITY",
        "TRUE_PUBLIC_NAME_TRANSITION",
        "TRUE_PUBLIC_HOLDING_COMPANY_NAME_TRANSITION",
        "TRUE_PUBLIC_NAME_TRANSITION_DUAL_DATE",
    }

    for row in stage3g.itertuples(index=False):
        if str(row.resolution_category) not in transition_categories:
            continue

        old_name = str(
            getattr(row, "predecessor_public_company_name", "")
        ).strip()
        new_name = str(
            getattr(row, "sample_authoritative_company_name", "")
        ).strip()

        if not old_name or not new_name:
            continue

        rows.append({
            "security_key": str(row.security_key),
            "old_company_name": old_name,
            "new_company_name": new_name,
            "public_effective_date": str(
                getattr(row, "public_effective_date", "")
            ),
            "legal_effective_date": str(
                getattr(row, "legal_effective_date", "")
            ),
            "source_layer": "STAGE3G_AUTHORITATIVE_NAME_STATE",
        })

    for row in stage3i_events.itertuples(index=False):
        if str(row.event_type) == "TICKER_ONLY_CHANGE":
            continue

        rows.append({
            "security_key": str(row.security_key),
            "old_company_name": str(row.old_company_name),
            "new_company_name": str(row.new_company_name),
            "public_effective_date": str(row.public_effective_date),
            "legal_effective_date": str(row.legal_effective_date),
            "source_layer": "STAGE3I_KNOWN_PRIMARY_EVENT",
        })

    events = pd.DataFrame(rows)

    if events.empty:
        return events

    events["boundary_dt"] = events.apply(
        lambda row: effective_boundary(
            row["public_effective_date"],
            row["legal_effective_date"],
        ),
        axis=1,
    )
    events["old_core_v2"] = events["old_company_name"].map(
        normalize_core_policy_v2
    )
    events["new_core_v2"] = events["new_company_name"].map(
        normalize_core_policy_v2
    )

    # Same dedupe concept as Stage 3J.
    events = (
        events.sort_values(
            [
                "security_key",
                "boundary_dt",
                "old_core_v2",
                "new_core_v2",
                "source_layer",
            ]
        )
        .drop_duplicates(
            [
                "security_key",
                "boundary_dt",
                "old_core_v2",
                "new_core_v2",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return events


def classify_alignment(left_name: str, right_name: str) -> str:
    left_core = normalize_core_policy_v2(left_name)
    right_core = normalize_core_policy_v2(right_name)

    if left_core == right_core:
        return "MATCH_POLICY_V2"

    left_compact = compact(left_name)
    right_compact = compact(right_name)

    if left_compact and left_compact == right_compact:
        return "DISPLAY_PUNCTUATION_OR_TOKEN_SPACING_EQUIVALENT"

    left_tokens = token_multiset(left_name)
    right_tokens = token_multiset(right_name)

    if left_tokens and left_tokens == right_tokens:
        return "WORD_ORDER_ONLY_EQUIVALENT"

    if (
        left_compact
        and right_compact
        and (
            left_compact in right_compact
            or right_compact in left_compact
        )
    ):
        return "PREFIX_SUFFIX_OR_ABBREVIATION_DIFFERENCE"

    return "SEMANTIC_OR_UNEXPLAINED_MISMATCH"


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        CANDIDATE_PATH,
        MEMBERSHIP_PATH,
        NPORT_OBS_PATH,
        STAGE3C_PATH,
        STAGE3D_PATH,
        STAGE3G_PATH,
        STAGE3I_PATH,
        STAGE3I_EVENTS_PATH,
    ):
        require(path)

    candidate = pd.read_csv(
        CANDIDATE_PATH, dtype=str, keep_default_na=False
    )
    membership = pd.read_csv(
        MEMBERSHIP_PATH, dtype=str, keep_default_na=False
    )
    observations = pd.read_csv(
        NPORT_OBS_PATH, dtype=str, keep_default_na=False
    )
    stage3c = pd.read_csv(
        STAGE3C_PATH, dtype=str, keep_default_na=False
    )
    stage3d = pd.read_csv(
        STAGE3D_PATH, dtype=str, keep_default_na=False
    )
    stage3g = pd.read_csv(
        STAGE3G_PATH, dtype=str, keep_default_na=False
    )
    stage3i = pd.read_csv(
        STAGE3I_PATH, dtype=str, keep_default_na=False
    )
    stage3i_events = pd.read_csv(
        STAGE3I_EVENTS_PATH, dtype=str, keep_default_na=False
    )

    membership["start_dt"] = pd.to_datetime(
        membership["valid_from"], errors="raise", utc=True
    ).dt.tz_convert(None)
    membership["end_dt"] = pd.to_datetime(
        membership["valid_to_exclusive"], errors="raise", utc=True
    ).dt.tz_convert(None)

    membership_lookup = membership.set_index("security_key")
    candidate_lookup = candidate.set_index("security_key")
    stage3g_lookup = stage3g.set_index("security_key")
    stage3i_lookup = stage3i.set_index("security_key")

    events = collect_events(stage3c, stage3d, stage3g, stage3i_events)

    diagnostics = []
    chain_diagnostics = []

    for sk, group in events.groupby("security_key"):
        if sk not in membership_lookup.index:
            chain_diagnostics.append({
                "security_key": sk,
                "diagnostic_type": "EVENT_SECURITY_NOT_IN_MEMBERSHIP_LEDGER",
                "left_name": "",
                "right_name": "",
                "alignment_class": "ERROR",
                "notes": "Transition event security_key not present in membership interval ledger.",
            })
            continue

        m = membership_lookup.loc[sk]
        start = max(m["start_dt"], SAMPLE_START)
        end = min(m["end_dt"], SAMPLE_END)

        if start >= end:
            continue

        in_sample = group[
            group["boundary_dt"].notna()
            & (group["boundary_dt"] > start)
            & (group["boundary_dt"] < end)
        ].sort_values(
            [
                "boundary_dt",
                "old_core_v2",
                "new_core_v2",
            ]
        )

        if in_sample.empty:
            continue

        # ----------------------------------------------------------
        # 1. Chain continuity across every transition event.
        # ----------------------------------------------------------
        rows = list(in_sample.itertuples(index=False))

        for i in range(len(rows) - 1):
            left = rows[i]
            right = rows[i + 1]
            alignment = classify_alignment(
                left.new_company_name,
                right.old_company_name,
            )

            chain_diagnostics.append({
                "security_key": sk,
                "diagnostic_type": "TRANSITION_CHAIN_NEW_TO_NEXT_OLD",
                "left_name": left.new_company_name,
                "right_name": right.old_company_name,
                "left_boundary": left.boundary_dt.date().isoformat(),
                "right_boundary": right.boundary_dt.date().isoformat(),
                "alignment_class": alignment,
                "notes": (
                    "Sequential transition chain must converge before interval "
                    "construction."
                ),
            })

        # ----------------------------------------------------------
        # 2. Independently resolved source name using Stage 3J
        #    source precedence.
        # ----------------------------------------------------------
        source_name = ""
        source_layer = ""

        if sk in stage3g_lookup.index:
            g = stage3g_lookup.loc[sk]
            if isinstance(g, pd.DataFrame):
                g = g.iloc[0]
            source_name = str(
                g.get("sample_authoritative_company_name", "")
            ).strip()
            source_layer = "STAGE3G_AUTHORITATIVE_SAMPLE_NAME"

        if not source_name and sk in stage3i_lookup.index:
            irow = stage3i_lookup.loc[sk]
            if isinstance(irow, pd.DataFrame):
                irow = irow.iloc[0]
            source_name = str(
                irow.get("membership_company_name", "")
            ).strip()
            source_layer = "STAGE3I_MEMBERSHIP_NAME"

        if not source_name:
            source_name = latest_nport_name(
                observations, sk, start, end
            )
            if source_name:
                source_layer = "LATEST_IN_MEMBERSHIP_SEC_NPORT_NAME"

        if not source_name and sk in candidate_lookup.index:
            c = candidate_lookup.loc[sk]
            if isinstance(c, pd.DataFrame):
                c = c.iloc[0]
            source_name = str(
                c.get("canonical_company_name", "")
            ).strip()
            source_layer = "CANONICAL_PROJECT_FALLBACK"

        final_event = in_sample.iloc[-1]
        final_name = str(final_event["new_company_name"]).strip()

        alignment = classify_alignment(
            final_name,
            source_name,
        )

        diagnostics.append({
            "security_key": sk,
            "latest_project_ticker": (
                str(candidate_lookup.loc[sk].get("latest_project_ticker", ""))
                if sk in candidate_lookup.index
                else ""
            ),
            "transition_count_in_sample": len(in_sample),
            "final_transition_name": final_name,
            "independent_source_name": source_name,
            "independent_source_layer": source_layer,
            "final_core_policy_v2": normalize_core_policy_v2(final_name),
            "source_core_policy_v2": normalize_core_policy_v2(source_name),
            "final_compact_diagnostic": compact(final_name),
            "source_compact_diagnostic": compact(source_name),
            "alignment_class": alignment,
            "builder_would_block_under_policy_v2": int(
                alignment != "MATCH_POLICY_V2"
            ),
            "candidate_display_only_fix": int(
                alignment in {
                    "DISPLAY_PUNCTUATION_OR_TOKEN_SPACING_EQUIVALENT",
                    "WORD_ORDER_ONLY_EQUIVALENT",
                }
            ),
        })

    diag = pd.DataFrame(diagnostics)
    chain = pd.DataFrame(chain_diagnostics)

    if diag.empty:
        diag = pd.DataFrame(
            columns=[
                "security_key",
                "latest_project_ticker",
                "transition_count_in_sample",
                "final_transition_name",
                "independent_source_name",
                "independent_source_layer",
                "final_core_policy_v2",
                "source_core_policy_v2",
                "final_compact_diagnostic",
                "source_compact_diagnostic",
                "alignment_class",
                "builder_would_block_under_policy_v2",
                "candidate_display_only_fix",
            ]
        )

    if chain.empty:
        chain = pd.DataFrame(
            columns=[
                "security_key",
                "diagnostic_type",
                "left_name",
                "right_name",
                "left_boundary",
                "right_boundary",
                "alignment_class",
                "notes",
            ]
        )

    diag = diag.sort_values(
        [
            "builder_would_block_under_policy_v2",
            "alignment_class",
            "latest_project_ticker",
            "security_key",
        ],
        ascending=[False, True, True, True],
    )

    chain = chain.sort_values(
        [
            "alignment_class",
            "security_key",
            "left_boundary",
        ]
    )

    diag.to_csv(DIAGNOSTIC_PATH, index=False)
    chain.to_csv(CHAIN_PATH, index=False)

    mismatches = diag[
        diag["builder_would_block_under_policy_v2"].eq(1)
    ]

    chain_mismatches = chain[
        ~chain["alignment_class"].isin(
            ["MATCH_POLICY_V2"]
        )
    ] if not chain.empty else chain

    class_counts = (
        diag["alignment_class"].value_counts().to_dict()
        if not diag.empty else {}
    )

    lines = [
        "=" * 128,
        "H3 STAGE 3J — ALL-TRANSITION NAME ALIGNMENT PREFLIGHT AUDIT",
        "=" * 128,
        f"Collected authoritative transition evidence rows: {len(events)}",
        f"Securities with in-sample name transitions audited: {len(diag)}",
        f"Final-state/source mismatches under current Policy V2: {len(mismatches)}",
        f"Sequential transition-chain nonmatches: {len(chain_mismatches)}",
        f"Display-only candidate mismatches: {int(mismatches['candidate_display_only_fix'].sum()) if not mismatches.empty else 0}",
        "",
        "Alignment class counts:",
    ]

    for status, count in sorted(class_counts.items()):
        lines.append(f"  {status}: {count}")

    lines += [
        "",
        "INTERPRETATION:",
        (
            "MATCH_POLICY_V2 rows already pass the current Stage 3J "
            "normalization."
        ),
        (
            "DISPLAY_PUNCTUATION_OR_TOKEN_SPACING_EQUIVALENT rows are cases "
            "such as CAMPBELL S vs Campbell's where the compact alphanumeric "
            "diagnostic agrees. This is diagnostic evidence only; the audit "
            "does not modify policy."
        ),
        (
            "WORD_ORDER_ONLY_EQUIVALENT indicates exact token equivalence "
            "after ordering only."
        ),
        (
            "PREFIX_SUFFIX_OR_ABBREVIATION_DIFFERENCE and "
            "SEMANTIC_OR_UNEXPLAINED_MISMATCH must not be auto-fixed from this "
            "audit alone."
        ),
        "",
        "Files:",
        f"  {DIAGNOSTIC_PATH.name}",
        f"  {CHAIN_PATH.name}",
        "",
        "Manifest builder executed: NO",
        "Alias policy modified: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        (
            "H3_STAGE3J_NAME_ALIGNMENT_PREFLIGHT_COMPLETE"
        ),
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
