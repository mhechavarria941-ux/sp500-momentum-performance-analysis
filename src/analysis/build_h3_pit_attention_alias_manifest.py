from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v6-h3-pit-attention-alias-manifest-systematic-safety-fix"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

POLICY_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_pit_attention_alias_policy_v5.json"
)

CANDIDATE_PATH = H3_DIR / "h3_company_query_manifest_candidates.csv"
FULL_CLOSURE_PATH = H3_DIR / "h3_full_universe_name_resolution_coverage_v2.csv"
MEMBERSHIP_PATH = (
    ROOT / "data" / "interim"
    / "sp500_membership_intervals_2021_2025.csv"
)
NPORT_OBS_PATH = H3_DIR / "h3_pit_name_state_observations.csv"
TICKER_HISTORY_PATH = H3_DIR / "h3_core_security_ticker_history_snapshot.csv"
STAGE3B2_SUMMARY_PATH = H3_DIR / "h3_pit_name_evidence_security_summary.csv"
SEC_METADATA_PATH = H3_DIR / "h3_sec_submissions_company_metadata.csv"

STAGE3G_PATH = H3_DIR / "h3_authoritative_name_state_closeout.csv"
STAGE3I_PATH = H3_DIR / "h3_no_nport_definitive_closure.csv"

STAGE3C_TRANSITIONS_PATH = H3_DIR / "h3_exact_name_transition_resolutions.csv"
STAGE3D_TRANSITIONS_PATH = (
    H3_DIR / "h3_authoritative_exact_name_transition_resolutions.csv"
)
STAGE3G_TRANSITIONS_PATH = H3_DIR / "h3_authoritative_name_state_closeout.csv"
STAGE3I_EVENTS_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_no_nport_known_name_state_events.csv"
)

OUT_PATH = H3_DIR / "h3_pit_attention_alias_intervals.csv"
EVENTS_PATH = H3_DIR / "h3_pit_attention_alias_transition_events.csv"
COLLISIONS_PATH = H3_DIR / "h3_pit_attention_alias_collision_diagnostics.csv"
SHARED_ISSUER_COLLISIONS_PATH = H3_DIR / "h3_pit_attention_alias_shared_issuer_collisions.csv"
ALIAS_SAFETY_PATH = H3_DIR / "h3_pit_attention_alias_safety_diagnostics.csv"
TRANSITION_ALIGNMENT_PATH = H3_DIR / "h3_pit_attention_alias_transition_alignment_diagnostics.csv"
SECURITY_SUMMARY_PATH = H3_DIR / "h3_pit_attention_alias_security_summary.csv"
REPORT_PATH = H3_DIR / "h3_pit_attention_alias_manifest_report.txt"

SAMPLE_START = pd.Timestamp("2021-01-01")
SAMPLE_END = pd.Timestamp("2026-01-01")
EXPECTED_IDENTITIES = 593

LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "ltd", "limited", "plc", "llc", "llp", "lp", "nv", "ag", "se", "sa",
}


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def dt(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce", utc=True).tz_convert(None)


def normalize_full(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    raw = unicodedata.normalize("NFKC", str(value)).casefold()

    # Provider/display sources sometimes move a leading article to the end:
    #   "Cigna Group/The" -> "The Cigna Group"
    #   "Charles Schwab Corp/The" -> "The Charles Schwab Corp"
    #
    # Treat trailing /THE as presentation metadata before punctuation collapse.
    # This does not remove a semantic word from the company name.
    raw = re.sub(r"/\s*the\s*$", " ", raw)

    # Remove slash-jurisdiction labels before general punctuation collapse.
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

    # Remove only explicit security-class presentation at the tail.
    if len(tokens) >= 2 and tokens[-2] in {"class", "cl"}:
        tokens = tokens[:-2]

    return " ".join(tokens).strip()


def normalize_core(value: object) -> str:
    full = normalize_full(value)
    tokens = full.split()

    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens = tokens[:-1]

    return " ".join(tokens).strip()


def compact_core(value: object) -> str:
    """
    Deterministic presentation-equivalence diagnostic.

    This is never used as the production alias itself. It only identifies
    punctuation/token-spacing differences such as:
        CAMPBELL S  <->  Campbell's

    Semantic differences remain different because all alphanumeric characters
    are preserved.
    """
    return re.sub(r"[^a-z0-9]", "", normalize_core(value))


def names_align_exact_or_display(left: object, right: object) -> bool:
    left_core = normalize_core(left)
    right_core = normalize_core(right)

    if not left_core or not right_core:
        return False

    if left_core == right_core:
        return True

    return compact_core(left) == compact_core(right)


def interval_overlap(a_start, a_end, b_start, b_end) -> bool:
    return bool(a_start < b_end and b_start < a_end)


def pick_latest_nport_name(
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
        subset["report_date"], errors="coerce", utc=True
    ).dt.tz_convert(None)

    subset = subset[
        subset["report_dt"].notna()
        & (subset["report_dt"] >= start)
        & (subset["report_dt"] < end)
    ]

    if subset.empty:
        return ""

    subset = subset.sort_values(["report_dt", "holding_name"])
    return str(subset.iloc[-1]["holding_name"]).strip()


def event_boundary(public_date: object, legal_date: object) -> pd.Timestamp:
    public_dt = dt(public_date)
    if pd.notna(public_dt):
        return public_dt
    return dt(legal_date)


def collect_transition_events(
    stage3c: pd.DataFrame,
    stage3d: pd.DataFrame,
    stage3g: pd.DataFrame,
    stage3i_events: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    # Stage 3C: the one automatically exact-resolved event.
    for row in stage3c.itertuples(index=False):
        if str(row.resolution_status) != "RESOLVED_EXACT":
            continue

        boundary = dt(row.exact_effective_date)

        rows.append({
            "security_key": str(row.security_key),
            "old_company_name": str(row.from_name_key),
            "new_company_name": str(row.to_name_key),
            "public_effective_date": (
                "" if pd.isna(boundary) else boundary.date().isoformat()
            ),
            "legal_effective_date": (
                "" if pd.isna(boundary) else boundary.date().isoformat()
            ),
            "effective_boundary_source": "STAGE3C_EXACT_EVENT",
            "source_url": str(getattr(row, "source_url_pipe", "")),
        })

    # Stage 3D: only true legal/company renames.
    for row in stage3d.itertuples(index=False):
        status = str(row.resolution_status)
        if not status.startswith("RESOLVED_TRUE_LEGAL_RENAME"):
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
            "effective_boundary_source": "STAGE3D_AUTHORITATIVE_RENAME",
            "source_url": str(getattr(row, "source_url", "")),
        })

    # Stage 3G: only categories that represent a public-name state transition
    # during the sample. Internal/public-brand-continuity reorganizations do not
    # create a production attention-name transition here.
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
            "effective_boundary_source": "STAGE3G_AUTHORITATIVE_NAME_STATE",
            "source_url": str(getattr(row, "source_url", "")),
        })

    # Stage 3I known events. Ticker-only changes do not split company-name aliases.
    # LUMN's public boundary is pre-window, so it will be naturally ignored by
    # the interval builder even though its legal finalization is in-window.
    for row in stage3i_events.itertuples(index=False):
        if str(row.event_type) == "TICKER_ONLY_CHANGE":
            continue

        rows.append({
            "security_key": str(row.security_key),
            "old_company_name": str(row.old_company_name),
            "new_company_name": str(row.new_company_name),
            "public_effective_date": str(row.public_effective_date),
            "legal_effective_date": str(row.legal_effective_date),
            "effective_boundary_source": "STAGE3I_KNOWN_PRIMARY_EVENT",
            "source_url": str(row.source_url),
        })

    events = pd.DataFrame(
        rows,
        columns=[
            "security_key",
            "old_company_name",
            "new_company_name",
            "public_effective_date",
            "legal_effective_date",
            "effective_boundary_source",
            "source_url",
        ],
    )

    if events.empty:
        return events

    events["boundary_dt"] = events.apply(
        lambda row: event_boundary(
            row["public_effective_date"],
            row["legal_effective_date"],
        ),
        axis=1,
    )

    events["old_core"] = events["old_company_name"].map(normalize_core)
    events["new_core"] = events["new_company_name"].map(normalize_core)

    # Deduplicate equivalent evidence rows after core/date normalization.
    events = (
        events.sort_values(
            [
                "security_key",
                "boundary_dt",
                "old_core",
                "new_core",
                "effective_boundary_source",
            ]
        )
        .drop_duplicates(
            [
                "security_key",
                "boundary_dt",
                "old_core",
                "new_core",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return events


def is_bare_ticker_alias(
    alias: object,
    historical_tickers: set[str],
) -> bool:
    value = str(alias).strip()

    if not value:
        return False

    tokens = value.split()
    token_key = re.sub(r"[^A-Z0-9]", "", value.upper())

    return bool(
        len(tokens) == 1
        and token_key in historical_tickers
    )


def authoritative_name_candidates(
    *,
    security_key: str,
    state_name: str,
    source_name: str,
    canonical_name: str,
    membership_name: str,
    issuer_cik: str,
    stage3g_lookup,
    stage3i_lookup,
    sec_metadata_lookup,
) -> list[tuple[str, str]]:
    """
    Return fuller authoritative name candidates.

    A candidate is not automatically accepted. The caller must require its
    conservative legal core to equal the current state core exactly.
    """
    candidates: list[tuple[str, str]] = []

    def add(value: object, layer: str) -> None:
        name = str(value).strip()
        if not name:
            return
        key = normalize_full(name)
        if not key:
            return
        if any(normalize_full(existing) == key for existing, _ in candidates):
            return
        candidates.append((name, layer))

    add(state_name, "STATE_NAME")
    add(source_name, "INDEPENDENT_SOURCE_NAME")

    if stage3g_lookup is not None and security_key in stage3g_lookup.index:
        row = stage3g_lookup.loc[security_key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        add(
            row.get("sample_authoritative_company_name", ""),
            "STAGE3G_AUTHORITATIVE_SAMPLE_NAME",
        )

    if stage3i_lookup is not None and security_key in stage3i_lookup.index:
        row = stage3i_lookup.loc[security_key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        add(
            row.get("membership_company_name", ""),
            "STAGE3I_MEMBERSHIP_NAME",
        )

    if (
        issuer_cik
        and sec_metadata_lookup is not None
        and issuer_cik in sec_metadata_lookup.index
    ):
        row = sec_metadata_lookup.loc[issuer_cik]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        add(
            row.get("sec_current_name", ""),
            "SEC_CURRENT_FILER_NAME",
        )

    add(membership_name, "CANONICAL_MEMBERSHIP_NAME")
    add(canonical_name, "CANONICAL_PROJECT_NAME")

    return candidates


def qualified_full_alias_for_core(
    *,
    target_core: str,
    candidates: list[tuple[str, str]],
    historical_tickers: set[str],
) -> tuple[str, str]:
    """
    Find a non-bare full normalized alias whose legal core exactly equals
    target_core.

    This is deterministic qualification, not fuzzy broadening.
    """
    for candidate_name, layer in candidates:
        if normalize_core(candidate_name) != target_core:
            continue

        full = normalize_full(candidate_name)
        if not full:
            continue

        if is_bare_ticker_alias(full, historical_tickers):
            continue

        return full, layer

    return "", ""


def classify_overlapping_aliases(
    df: pd.DataFrame,
) -> tuple[list[dict], list[dict]]:
    """
    Return:
      blocking collisions, allowed same-issuer shared aliases.

    Same-issuer sharing requires the same nonblank SEC CIK.
    """
    blocking = []
    shared_issuer = []

    for alias, group in df.groupby("production_alias"):
        if not alias:
            continue

        records = list(group.to_dict("records"))

        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                left = records[i]
                right = records[j]

                if left["security_key"] == right["security_key"]:
                    continue

                if not interval_overlap(
                    left["alias_valid_from_dt"],
                    left["alias_valid_to_dt"],
                    right["alias_valid_from_dt"],
                    right["alias_valid_to_dt"],
                ):
                    continue

                left_cik = str(left.get("issuer_cik", "")).strip()
                right_cik = str(right.get("issuer_cik", "")).strip()

                record = {
                    "production_alias": alias,
                    "left_security_key": left["security_key"],
                    "right_security_key": right["security_key"],
                    "left_issuer_cik": left_cik,
                    "right_issuer_cik": right_cik,
                    "left_valid_from": left["alias_valid_from"],
                    "left_valid_to_exclusive": left["alias_valid_to_exclusive"],
                    "right_valid_from": right["alias_valid_from"],
                    "right_valid_to_exclusive": right["alias_valid_to_exclusive"],
                }

                if (
                    left_cik
                    and right_cik
                    and left_cik == right_cik
                ):
                    record["collision_class"] = (
                        "SHARED_ISSUER_MULTI_SECURITY_ALIAS"
                    )
                    shared_issuer.append(record)
                else:
                    record["collision_class"] = (
                        "BLOCKING_CROSS_OR_UNRESOLVED_ISSUER_ALIAS"
                    )
                    blocking.append(record)

    return blocking, shared_issuer


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    # Frozen normalization regression checks.
    regression_cases = {
        "Cigna Group/The": "cigna group",
        "The Cigna Group": "cigna group",
        "Charles Schwab Corp/The": "charles schwab",
    }
    for raw_name, expected_core in regression_cases.items():
        observed_core = normalize_core(raw_name)
        if observed_core != expected_core:
            raise RuntimeError(
                f"Alias-normalization regression failed for {raw_name!r}: "
                f"{observed_core!r} != {expected_core!r}"
            )

    if not names_align_exact_or_display(
        "CAMPBELL S",
        "Campbell's Company/The",
    ):
        raise RuntimeError(
            "Display-equivalence regression failed for CPB."
        )

    if not names_align_exact_or_display(
        "Fortune Brands Home & Security",
        "Fortune Brands Home & Security, Inc.",
    ):
        raise RuntimeError(
            "Pre-transition membership-name regression failed for FBHS."
        )

    if not names_align_exact_or_display(
        "Penn National Gaming",
        "Penn National Gaming, Inc.",
    ):
        raise RuntimeError(
            "Pre-transition membership-name regression failed for PENN."
        )

    if not names_align_exact_or_display(
        "Kellanova",
        "Kellanova",
    ):
        raise RuntimeError(
            "Post-transition membership-name regression failed for K."
        )

    required = [
        POLICY_PATH,
        CANDIDATE_PATH,
        FULL_CLOSURE_PATH,
        MEMBERSHIP_PATH,
        NPORT_OBS_PATH,
        TICKER_HISTORY_PATH,
        STAGE3B2_SUMMARY_PATH,
        SEC_METADATA_PATH,
        STAGE3G_PATH,
        STAGE3I_PATH,
        STAGE3C_TRANSITIONS_PATH,
        STAGE3D_TRANSITIONS_PATH,
        STAGE3G_TRANSITIONS_PATH,
        STAGE3I_EVENTS_PATH,
    ]
    for path in required:
        require(path)

    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    policy = json.loads(policy_text)
    policy_sha = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()

    candidate = pd.read_csv(
        CANDIDATE_PATH, dtype=str, keep_default_na=False
    )
    closure = pd.read_csv(
        FULL_CLOSURE_PATH, dtype=str, keep_default_na=False
    )
    membership = pd.read_csv(
        MEMBERSHIP_PATH, dtype=str, keep_default_na=False
    )
    observations = pd.read_csv(
        NPORT_OBS_PATH, dtype=str, keep_default_na=False
    )
    ticker_history = pd.read_csv(
        TICKER_HISTORY_PATH, dtype=str, keep_default_na=False
    )
    stage3b2_summary = pd.read_csv(
        STAGE3B2_SUMMARY_PATH, dtype=str, keep_default_na=False
    )
    sec_metadata = pd.read_csv(
        SEC_METADATA_PATH, dtype=str, keep_default_na=False
    )
    stage3g = pd.read_csv(
        STAGE3G_PATH, dtype=str, keep_default_na=False
    )
    stage3i = pd.read_csv(
        STAGE3I_PATH, dtype=str, keep_default_na=False
    )
    stage3c = pd.read_csv(
        STAGE3C_TRANSITIONS_PATH, dtype=str, keep_default_na=False
    )
    stage3d = pd.read_csv(
        STAGE3D_TRANSITIONS_PATH, dtype=str, keep_default_na=False
    )
    stage3i_events = pd.read_csv(
        STAGE3I_EVENTS_PATH, dtype=str, keep_default_na=False
    )

    if len(candidate) != EXPECTED_IDENTITIES:
        raise RuntimeError(
            f"Candidate rows={len(candidate)}, expected 593."
        )
    if len(closure) != EXPECTED_IDENTITIES:
        raise RuntimeError(
            f"Closure rows={len(closure)}, expected 593."
        )
    if closure["final_name_resolution_status"].eq(
        "UNRESOLVED_CARRY_FORWARD_GAP"
    ).any():
        raise RuntimeError(
            "Full-universe company-name closure is not complete."
        )

    membership["valid_from_dt"] = pd.to_datetime(
        membership["valid_from"], errors="raise", utc=True
    ).dt.tz_convert(None)
    membership["valid_to_dt"] = pd.to_datetime(
        membership["valid_to_exclusive"], errors="raise", utc=True
    ).dt.tz_convert(None)

    if membership["security_key"].duplicated().any():
        raise RuntimeError(
            "Expected one canonical membership interval per security_key."
        )

    candidate_lookup = candidate.set_index("security_key")
    closure_lookup = closure.set_index("security_key")
    membership_lookup = membership.set_index("security_key")

    stage3g_lookup = (
        stage3g.set_index("security_key")
        if not stage3g.empty else None
    )
    stage3i_lookup = (
        stage3i.set_index("security_key")
        if not stage3i.empty else None
    )
    stage3b2_lookup = (
        stage3b2_summary.set_index("security_key")
        if not stage3b2_summary.empty else None
    )
    sec_metadata_lookup = (
        sec_metadata.set_index("sec_cik")
        if not sec_metadata.empty else None
    )

    historical_tickers = {
        re.sub(r"[^A-Z0-9]", "", str(ticker).upper())
        for ticker in ticker_history["ticker"]
        if str(ticker).strip()
    }

    events = collect_transition_events(
        stage3c,
        stage3d,
        stage3g,
        stage3i_events,
    )
    events.to_csv(EVENTS_PATH, index=False)

    event_groups = {
        key: group.copy()
        for key, group in events.groupby("security_key")
    } if not events.empty else {}

    interval_rows = []
    transition_alignment_issues = []
    alias_safety_issues = []

    for sk in candidate["security_key"].astype(str):
        if sk not in membership_lookup.index:
            raise RuntimeError(
                f"Missing membership interval for security_key={sk}"
            )

        c = candidate_lookup.loc[sk]
        cl = closure_lookup.loc[sk]
        m = membership_lookup.loc[sk]

        start = max(m["valid_from_dt"], SAMPLE_START)
        end = min(m["valid_to_dt"], SAMPLE_END)

        if start >= end:
            # Identity exists in the historical ledger but never overlaps
            # the H3 2021-2025 attention sample.
            continue

        # --------------------------------------------------------------
        # Authoritative issuer CIK for collision classification.
        # Precedence follows the most authoritative resolved local layer.
        # --------------------------------------------------------------
        issuer_cik = ""
        issuer_cik_source = ""

        if (
            stage3g_lookup is not None
            and sk in stage3g_lookup.index
        ):
            row3g = stage3g_lookup.loc[sk]
            if isinstance(row3g, pd.DataFrame):
                row3g = row3g.iloc[0]
            value = str(
                row3g.get("sample_authoritative_cik", "")
            ).strip()
            if value:
                issuer_cik = value
                issuer_cik_source = "STAGE3G_SAMPLE_CIK"

        if (
            not issuer_cik
            and stage3i_lookup is not None
            and sk in stage3i_lookup.index
        ):
            row3i = stage3i_lookup.loc[sk]
            if isinstance(row3i, pd.DataFrame):
                row3i = row3i.iloc[0]
            value = str(
                row3i.get("resolved_sec_cik", "")
            ).strip()
            if value:
                issuer_cik = value
                issuer_cik_source = "STAGE3I_RESOLVED_CIK"

        if (
            not issuer_cik
            and stage3b2_lookup is not None
            and sk in stage3b2_lookup.index
        ):
            row3b2 = stage3b2_lookup.loc[sk]
            if isinstance(row3b2, pd.DataFrame):
                row3b2 = row3b2.iloc[0]
            value = str(
                row3b2.get("candidate_sec_cik", "")
            ).strip()
            if value:
                issuer_cik = value
                issuer_cik_source = "STAGE3B2_CANDIDATE_CIK"

        source_name = ""
        source_layer = ""

        if (
            stage3g_lookup is not None
            and sk in stage3g_lookup.index
        ):
            g = stage3g_lookup.loc[sk]
            if isinstance(g, pd.DataFrame):
                g = g.iloc[0]
            source_name = str(
                g.get("sample_authoritative_company_name", "")
            ).strip()
            source_layer = "STAGE3G_AUTHORITATIVE_SAMPLE_NAME"

        if (
            not source_name
            and stage3i_lookup is not None
            and sk in stage3i_lookup.index
        ):
            i = stage3i_lookup.loc[sk]
            if isinstance(i, pd.DataFrame):
                i = i.iloc[0]
            source_name = str(
                i.get("membership_company_name", "")
            ).strip()
            source_layer = "STAGE3I_MEMBERSHIP_NAME"

        if not source_name:
            nport_name = pick_latest_nport_name(
                observations, sk, start, end
            )
            if nport_name:
                source_name = nport_name
                source_layer = "LATEST_IN_MEMBERSHIP_SEC_NPORT_NAME"

        if not source_name:
            source_name = str(
                c.get("canonical_company_name", "")
            ).strip()
            source_layer = "CANONICAL_PROJECT_FALLBACK"

        if not source_name:
            raise RuntimeError(
                f"No source company name available for {sk}"
            )

        security_events = event_groups.get(
            sk,
            pd.DataFrame(),
        )

        if not security_events.empty:
            security_events = security_events[
                security_events["boundary_dt"].notna()
            ].copy()

            # Primary media boundary uses public date first.
            security_events = security_events[
                (security_events["boundary_dt"] > start)
                & (security_events["boundary_dt"] < end)
            ].sort_values(
                [
                    "boundary_dt",
                    "old_core",
                    "new_core",
                ]
            )

            # Detect conflicting same-date transitions before interval build.
            #
            # V2 implementation note:
            # Avoid GroupBy.apply here. Depending on the pandas version,
            # DataFrameGroupBy.apply can return a DataFrame rather than a
            # one-dimensional Series. In that case `(date_conflicts > 1).any()`
            # also returns a Series, and using it in `if` raises:
            # "The truth value of a Series is ambiguous."
            #
            # We only need the number of unique (old_core, new_core) pairs
            # per boundary date, so drop_duplicates + groupby.size is both
            # simpler and version-stable.
            date_conflicts = (
                security_events[
                    ["boundary_dt", "old_core", "new_core"]
                ]
                .drop_duplicates()
                .groupby("boundary_dt", dropna=False)
                .size()
            )

            if date_conflicts.gt(1).any():
                conflict_dates = [
                    value.date().isoformat()
                    for value in date_conflicts[
                        date_conflicts.gt(1)
                    ].index.tolist()
                ]
                transition_alignment_issues.append({
                    "security_key": sk,
                    "latest_project_ticker": c.get(
                        "latest_project_ticker", ""
                    ),
                    "issue_type": "CONFLICTING_SAME_DATE_TRANSITION_EVIDENCE",
                    "source_name": source_name,
                    "source_layer": source_layer,
                    "chain_states_pipe": "",
                    "chain_boundaries_pipe": "|".join(conflict_dates),
                    "notes": (
                        "More than one distinct old->new transition exists "
                        "on the same effective boundary."
                    ),
                })
                continue

            # Audit every transition-to-next-transition name handoff.
            chain_continuity_failed = False
            event_records = list(
                security_events.itertuples(index=False)
            )

            for idx in range(len(event_records) - 1):
                left = event_records[idx]
                right = event_records[idx + 1]

                if not names_align_exact_or_display(
                    left.new_company_name,
                    right.old_company_name,
                ):
                    transition_alignment_issues.append({
                        "security_key": sk,
                        "latest_project_ticker": c.get(
                            "latest_project_ticker", ""
                        ),
                        "issue_type": "SEQUENTIAL_EVENT_CHAIN_NAME_MISMATCH",
                        "source_name": source_name,
                        "source_layer": source_layer,
                        "chain_states_pipe": (
                            str(left.new_company_name)
                            + "|"
                            + str(right.old_company_name)
                        ),
                        "chain_boundaries_pipe": (
                            str(left.boundary_dt.date().isoformat())
                            + "|"
                            + str(right.boundary_dt.date().isoformat())
                        ),
                        "notes": (
                            "New name from one event does not match old name "
                            "of the next event."
                        ),
                    })
                    chain_continuity_failed = True

            if chain_continuity_failed:
                continue

        if security_events.empty:
            state_names = [(start, end, source_name, "STABLE")]
        else:
            state_names = []
            first = security_events.iloc[0]
            current_name = str(first["old_company_name"]).strip()
            cursor = start

            for _, event in security_events.iterrows():
                boundary = event["boundary_dt"]

                if boundary <= cursor:
                    current_name = str(
                        event["new_company_name"]
                    ).strip()
                    continue

                state_names.append(
                    (
                        cursor,
                        boundary,
                        current_name,
                        str(event["effective_boundary_source"]),
                    )
                )

                current_name = str(
                    event["new_company_name"]
                ).strip()
                cursor = boundary

            if cursor < end:
                state_names.append(
                    (cursor, end, current_name, "POST_TRANSITION")
                )

            # --------------------------------------------------------------
            # V5: authoritative event-chain temporal state validation.
            #
            # Static source names are point-in-time identity corroboration.
            # Depending on source timing they may represent:
            #   - the first pre-transition state,
            #   - an intermediate state, or
            #   - the terminal post-transition state.
            #
            # Therefore never assume a static Stage 3I/NPORT/Stage 3G name is
            # specifically the first or final state. It must match ANY state
            # in the authoritative event chain.
            # --------------------------------------------------------------
            chain_state_names = [
                str(security_events.iloc[0]["old_company_name"]).strip()
            ] + [
                str(value).strip()
                for value in security_events["new_company_name"].tolist()
            ]

            matching_state_indexes = [
                index
                for index, chain_name in enumerate(chain_state_names)
                if names_align_exact_or_display(
                    source_name,
                    chain_name,
                )
            ]

            if not matching_state_indexes:
                transition_alignment_issues.append({
                    "security_key": sk,
                    "latest_project_ticker": c.get(
                        "latest_project_ticker", ""
                    ),
                    "issue_type": "STATIC_SOURCE_MATCHES_NO_EVENT_CHAIN_STATE",
                    "source_name": source_name,
                    "source_layer": source_layer,
                    "chain_states_pipe": "|".join(chain_state_names),
                    "chain_boundaries_pipe": "|".join(
                        [
                            value.date().isoformat()
                            for value in security_events["boundary_dt"].tolist()
                        ]
                    ),
                    "notes": (
                        "Static source name must match at least one authoritative "
                        "event-chain state under exact or deterministic display "
                        "equivalence."
                    ),
                })
                # Do not create potentially invalid production intervals for
                # this security. Continue auditing the remaining universe so
                # all problems are reported in one run.
                continue

            # If the independent static source matches the TERMINAL state only
            # by display equivalence, use its authoritative spelling for the
            # final interval. If it matches an earlier state, the event chain
            # remains solely responsible for the terminal spelling.
            terminal_index = len(chain_state_names) - 1
            if terminal_index in matching_state_indexes:
                terminal_name = chain_state_names[-1]

                if (
                    normalize_core(terminal_name)
                    != normalize_core(source_name)
                    and compact_core(terminal_name)
                    == compact_core(source_name)
                ):
                    if state_names:
                        (
                            last_start,
                            last_end,
                            _,
                            last_basis,
                        ) = state_names[-1]

                        state_names[-1] = (
                            last_start,
                            last_end,
                            source_name,
                            last_basis
                            + "|DISPLAY_EQUIVALENCE_CANONICALIZED",
                        )

        ambiguity = str(
            c.get("structural_ambiguity_tier", "")
        ).upper()
        ticker_like_flag = str(
            c.get("ticker_like_exact_name_flag", "0")
        ) == "1"

        for alias_start, alias_end, state_name, state_basis in state_names:
            full_alias = normalize_full(state_name)
            core_alias = normalize_core(state_name)

            ticker_key = re.sub(
                r"[^A-Z0-9]", "", core_alias.upper()
            )

            force_full = (
                ambiguity == "HIGH"
                or ticker_like_flag
                or len(core_alias.replace(" ", "")) < 4
                or ticker_key in historical_tickers
            )

            selected = full_alias if force_full else core_alias
            selection_reason = (
                "FULL_AUTHORITATIVE_NAME_PRECISION_CONTROL"
                if force_full
                else "CONSERVATIVE_LEGAL_CORE"
            )

            candidate_names = authoritative_name_candidates(
                security_key=sk,
                state_name=state_name,
                source_name=source_name,
                canonical_name=str(
                    c.get("canonical_company_name", "")
                ),
                membership_name=str(
                    m.get("company_name_reference", "")
                ),
                issuer_cik=issuer_cik,
                stage3g_lookup=stage3g_lookup,
                stage3i_lookup=stage3i_lookup,
                sec_metadata_lookup=sec_metadata_lookup,
            )

            qualified_alias, qualified_layer = (
                qualified_full_alias_for_core(
                    target_core=core_alias,
                    candidates=candidate_names,
                    historical_tickers=historical_tickers,
                )
            )

            # Bare stock tickers are never production organization aliases.
            if is_bare_ticker_alias(
                selected,
                historical_tickers,
            ):
                if qualified_alias:
                    selected = qualified_alias
                    selection_reason = (
                        "QUALIFIED_FULL_AUTHORITATIVE_NAME_"
                        "BARE_TICKER_CONTROL"
                    )
                else:
                    alias_safety_issues.append({
                        "security_key": sk,
                        "latest_project_ticker": c.get(
                            "latest_project_ticker", ""
                        ),
                        "issue_type": (
                            "NO_NONBARE_AUTHORITATIVE_NAME_FOR_TICKER_CORE"
                        ),
                        "authoritative_state_name": state_name,
                        "state_core": core_alias,
                        "attempted_alias": selected,
                        "issuer_cik": issuer_cik,
                        "candidate_names_pipe": "|".join(
                            [name for name, _ in candidate_names]
                        ),
                        "notes": (
                            "A bare-ticker state could not be deterministically "
                            "qualified with a fuller authoritative name sharing "
                            "the exact legal core."
                        ),
                    })
                    continue

            if not selected:
                alias_safety_issues.append({
                    "security_key": sk,
                    "latest_project_ticker": c.get(
                        "latest_project_ticker", ""
                    ),
                    "issue_type": "BLANK_SELECTED_ALIAS",
                    "authoritative_state_name": state_name,
                    "state_core": core_alias,
                    "attempted_alias": selected,
                    "issuer_cik": issuer_cik,
                    "candidate_names_pipe": "|".join(
                        [name for name, _ in candidate_names]
                    ),
                    "notes": "Selected production alias is blank.",
                })
                continue

            # Collision escalation should never revert a successfully-qualified
            # ticker core back to a bare token.
            collision_safe_full_alias = (
                qualified_alias
                if qualified_alias
                else full_alias
            )

            interval_rows.append({
                "security_key": sk,
                "issuer_cik": issuer_cik,
                "issuer_cik_source": issuer_cik_source,
                "latest_project_ticker": c.get(
                    "latest_project_ticker", ""
                ),
                "structural_ambiguity_tier": ambiguity,
                "ticker_like_exact_name_flag": int(
                    ticker_like_flag
                ),
                "membership_valid_from": start.date().isoformat(),
                "membership_valid_to_exclusive": end.date().isoformat(),
                "alias_valid_from": alias_start.date().isoformat(),
                "alias_valid_to_exclusive": alias_end.date().isoformat(),
                "authoritative_state_name": state_name,
                "authoritative_name_source_layer": source_layer,
                "state_basis": state_basis,
                "full_normalized_alias": full_alias,
                "legal_core_alias": core_alias,
                "collision_safe_full_alias": collision_safe_full_alias,
                "production_alias": selected,
                "alias_selection_reason": selection_reason,
                "bare_ticker_qualification_source": qualified_layer,
                "matching_mode": "EXACT_NORMALIZED_GKG_ORGANIZATION",
                "policy_id": policy["policy_id"],
                "policy_sha256": policy_sha,
            })

    transition_issue_columns = [
        "security_key",
        "latest_project_ticker",
        "issue_type",
        "source_name",
        "source_layer",
        "chain_states_pipe",
        "chain_boundaries_pipe",
        "notes",
    ]

    transition_issue_df = pd.DataFrame(
        transition_alignment_issues,
        columns=transition_issue_columns,
    )
    transition_issue_df.to_csv(
        TRANSITION_ALIGNMENT_PATH,
        index=False,
    )

    if transition_alignment_issues:
        issue_counts = (
            transition_issue_df["issue_type"]
            .value_counts()
            .to_dict()
        )
        raise RuntimeError(
            "Stage 3J transition preflight found "
            f"{len(transition_alignment_issues)} issue(s) across "
            f"{transition_issue_df['security_key'].nunique()} security(s). "
            f"Counts={issue_counts}. Inspect "
            f"{TRANSITION_ALIGNMENT_PATH.name}; all issues were collected "
            "in this single run."
        )

    alias_safety_columns = [
        "security_key",
        "latest_project_ticker",
        "issue_type",
        "authoritative_state_name",
        "state_core",
        "attempted_alias",
        "issuer_cik",
        "candidate_names_pipe",
        "notes",
    ]
    alias_safety_df = pd.DataFrame(
        alias_safety_issues,
        columns=alias_safety_columns,
    )
    alias_safety_df.to_csv(
        ALIAS_SAFETY_PATH,
        index=False,
    )

    if alias_safety_issues:
        issue_counts = (
            alias_safety_df["issue_type"]
            .value_counts()
            .to_dict()
        )
        raise RuntimeError(
            "Stage 3J alias-safety preflight found "
            f"{len(alias_safety_issues)} issue(s) across "
            f"{alias_safety_df['security_key'].nunique()} security(s). "
            f"Counts={issue_counts}. Inspect {ALIAS_SAFETY_PATH.name}; "
            "all issues were collected in this single run."
        )

    manifest = pd.DataFrame(interval_rows)

    manifest["alias_valid_from_dt"] = pd.to_datetime(
        manifest["alias_valid_from"], errors="raise"
    )
    manifest["alias_valid_to_dt"] = pd.to_datetime(
        manifest["alias_valid_to_exclusive"], errors="raise"
    )

    # --------------------------------------------------------------
    # Issuer-aware collision control.
    # --------------------------------------------------------------
    initial_blocking, initial_shared_issuer = (
        classify_overlapping_aliases(manifest)
    )

    collision_security_keys = set()

    for collision in initial_blocking:
        collision_security_keys.add(
            collision["left_security_key"]
        )
        collision_security_keys.add(
            collision["right_security_key"]
        )

    if collision_security_keys:
        mask = manifest["security_key"].isin(
            collision_security_keys
        )
        manifest.loc[mask, "production_alias"] = manifest.loc[
            mask, "collision_safe_full_alias"
        ]
        manifest.loc[mask, "alias_selection_reason"] = (
            "QUALIFIED_FULL_AUTHORITATIVE_NAME_"
            "CROSS_ISSUER_COLLISION_ESCALATION"
        )

    final_blocking, final_shared_issuer = (
        classify_overlapping_aliases(manifest)
    )

    blocking_df = pd.DataFrame(
        final_blocking,
        columns=[
            "production_alias",
            "left_security_key",
            "right_security_key",
            "left_issuer_cik",
            "right_issuer_cik",
            "left_valid_from",
            "left_valid_to_exclusive",
            "right_valid_from",
            "right_valid_to_exclusive",
            "collision_class",
        ],
    )
    blocking_df.to_csv(
        COLLISIONS_PATH,
        index=False,
    )

    shared_issuer_df = pd.DataFrame(
        final_shared_issuer,
        columns=[
            "production_alias",
            "left_security_key",
            "right_security_key",
            "left_issuer_cik",
            "right_issuer_cik",
            "left_valid_from",
            "left_valid_to_exclusive",
            "right_valid_from",
            "right_valid_to_exclusive",
            "collision_class",
        ],
    )
    shared_issuer_df.to_csv(
        SHARED_ISSUER_COLLISIONS_PATH,
        index=False,
    )

    # Final bare-ticker audit after collision escalation.
    manifest["bare_ticker_alias_flag"] = manifest[
        "production_alias"
    ].apply(
        lambda value: int(
            is_bare_ticker_alias(
                value,
                historical_tickers,
            )
        )
    )

    manifest = manifest.drop(
        columns=[
            "alias_valid_from_dt",
            "alias_valid_to_dt",
            "collision_safe_full_alias",
        ]
    ).sort_values(
        [
            "security_key",
            "alias_valid_from",
            "alias_valid_to_exclusive",
        ]
    )

    manifest.to_csv(OUT_PATH, index=False)

    # Security-level summary.
    security_summary = (
        manifest.groupby("security_key", as_index=False)
        .agg(
            alias_interval_count=(
                "production_alias", "size"
            ),
            unique_production_alias_count=(
                "production_alias", "nunique"
            ),
            first_alias_date=(
                "alias_valid_from", "min"
            ),
            last_alias_end_exclusive=(
                "alias_valid_to_exclusive", "max"
            ),
            ambiguity_tier=(
                "structural_ambiguity_tier", "first"
            ),
            bare_ticker_alias_rows=(
                "bare_ticker_alias_flag", "sum"
            ),
        )
    )
    security_summary.to_csv(
        SECURITY_SUMMARY_PATH,
        index=False,
    )

    sample_security_count = manifest[
        "security_key"
    ].nunique()

    transition_security_count = int(
        security_summary[
            "alias_interval_count"
        ].gt(1).sum()
    )

    lines = [
        "=" * 128,
        "H3 STAGE 3J — PIT ATTENTION ALIAS MANIFEST",
        "=" * 128,
        f"Policy ID: {policy['policy_id']}",
        f"Policy SHA-256: {policy_sha}",
        f"Canonical identities in closure ledger: {len(closure)}",
        f"Identities overlapping 2021-2025 sample: {sample_security_count}",
        f"Production alias intervals: {len(manifest)}",
        f"Identities with >1 alias interval: {transition_security_count}",
        f"Collected authoritative transition evidence rows: {len(events)}",
        f"Initial blocking cross/unresolved-issuer collisions: {len(initial_blocking)}",
        f"Final blocking cross/unresolved-issuer collisions: {len(final_blocking)}",
        f"Allowed same-issuer shared-alias overlaps: {len(final_shared_issuer)}",
        f"Bare-ticker production alias rows: {int(manifest['bare_ticker_alias_flag'].sum())}",
        "",
        "PRIMARY MATCHING MODE:",
        "  EXACT_NORMALIZED_GKG_ORGANIZATION",
        "",
        "TRANSITION RULE:",
        (
            "  Public/trading effective date has priority over legal date. "
            "Old alias ends immediately before the public boundary; new alias "
            "starts on the boundary."
        ),
        "",
        "Production alias manifest created: YES",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_PIT_ATTENTION_ALIAS_MANIFEST_COMPLETE",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )
    print(report, end="")


if __name__ == "__main__":
    main()
