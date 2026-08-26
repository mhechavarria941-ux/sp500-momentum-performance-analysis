from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v2-h3-pit-name-evidence-timezone-normalization-fix"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

CANDIDATE_MANIFEST_PATH = H3_DIR / "h3_company_query_manifest_candidates.csv"
SEC_MAPPING_PATH = H3_DIR / "h3_sec_cik_mapping_candidates.csv"
SEC_FORMER_NAMES_PATH = H3_DIR / "h3_sec_former_names_raw.csv"

SEC_HOLDINGS_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "sec_select_sector_canonical_holdings_clean.csv"
)
SEC_BRIDGE_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "sec_gics_identifier_security_key_bridge.csv"
)
MEMBERSHIP_PATH = (
    ROOT / "data" / "interim"
    / "sp500_membership_intervals_2021_2025.csv"
)
TICKER_HISTORY_PATH = H3_DIR / "h3_core_security_ticker_history_snapshot.csv"
SECURITY_ALIASES_PATH = (
    ROOT / "data" / "reference" / "securities"
    / "security_aliases.csv"
)

SUMMARY_PATH = H3_DIR / "h3_pit_name_evidence_security_summary.csv"
OBSERVATIONS_PATH = H3_DIR / "h3_pit_name_state_observations.csv"
TRANSITIONS_PATH = H3_DIR / "h3_pit_name_transition_candidates.csv"
REVIEW_PATH = H3_DIR / "h3_pit_name_evidence_review_queue.csv"
ALIAS_EVENTS_PATH = H3_DIR / "h3_pit_name_alias_events_mapped.csv"
UNMAPPED_ALIAS_EVENTS_PATH = H3_DIR / "h3_pit_name_alias_events_unmapped.csv"
REPORT_PATH = H3_DIR / "h3_pit_name_evidence_consolidation_report.txt"

PROJECT_START = pd.Timestamp("2021-01-01")
PROJECT_END_EXCLUSIVE = pd.Timestamp("2026-01-01")
SUPPORT_START = pd.Timestamp("2020-12-01")

EXPECTED_IDENTITIES = 593


def normalize_company_name(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    text = unicodedata.normalize("NFKC", str(value)).upper()
    text = text.replace("&", " AND ")

    text = re.sub(r"\bTHE\b", " ", text)
    text = re.sub(r"\bCLASS\s+[A-Z0-9]+\b", " ", text)
    text = re.sub(r"\bCL\s+[A-Z0-9]+\b", " ", text)
    text = re.sub(r"\bORDINARY\s+SHARES?\b", " ", text)
    text = re.sub(r"\bCOMMON\s+STOCK\b", " ", text)

    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    suffixes = (
        " HOLDINGS CORPORATION",
        " HOLDINGS CORP",
        " HOLDING CORPORATION",
        " HOLDING CORP",
        " HOLDINGS PLC",
        " HOLDING PLC",
        " INCORPORATED",
        " CORPORATION",
        " COMPANY",
        " LIMITED",
        " HOLDINGS",
        " HOLDING",
        " CORP",
        " INC",
        " PLC",
        " LTD",
        " CO",
    )

    changed = True
    while changed and text:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[:-len(suffix)].strip()
                changed = True
                break

    return text


def ticker_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().upper()
    if text in {"", "NAN", "NONE", "NULL", "-"}:
        return ""
    return re.sub(r"[^A-Z0-9]", "", text)


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def date_or_nat(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce")


def overlap_project_period(start: pd.Timestamp, end: pd.Timestamp) -> bool:
    # SEC formerNames dates can be incomplete. Missing dates remain review evidence.
    if pd.isna(start) or pd.isna(end):
        return True
    return bool(start < PROJECT_END_EXCLUSIVE and end >= PROJECT_START)


def build_ticker_map(ticker_history: pd.DataFrame) -> tuple[dict[str, str], set[str]]:
    work = ticker_history[["security_key", "ticker"]].copy()
    work["ticker_key"] = work["ticker"].map(ticker_key)
    work = work[work["ticker_key"].ne("")].drop_duplicates()

    counts = work.groupby("ticker_key")["security_key"].nunique()
    ambiguous = set(counts[counts > 1].index)

    unique = (
        work[~work["ticker_key"].isin(ambiguous)]
        .drop_duplicates("ticker_key")
        .set_index("ticker_key")["security_key"]
        .astype(str)
        .to_dict()
    )
    return unique, ambiguous


def map_alias_events(
    aliases: pd.DataFrame,
    ticker_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapped = []
    unmapped = []

    for row in aliases.itertuples(index=False):
        old_key = ticker_key(getattr(row, "old_ticker", ""))
        new_key = ticker_key(getattr(row, "new_ticker", ""))

        old_security = ticker_map.get(old_key) if old_key else None
        new_security = ticker_map.get(new_key) if new_key else None

        security_key = None
        reason = ""

        if old_security and new_security and old_security == new_security:
            security_key = old_security
        elif old_security and not new_security:
            security_key = old_security
        elif new_security and not old_security:
            security_key = new_security
        elif old_security and new_security and old_security != new_security:
            reason = f"OLD_NEW_SECURITY_CONFLICT:{old_security}|{new_security}"
        else:
            reason = "NO_UNIQUE_TICKER_HISTORY_MAPPING"

        payload = {
            "effective_date": getattr(row, "effective_date", ""),
            "old_ticker": getattr(row, "old_ticker", ""),
            "new_ticker": getattr(row, "new_ticker", ""),
            "old_company_name": getattr(row, "old_company_name", ""),
            "new_company_name": getattr(row, "new_company_name", ""),
            "event_type": getattr(row, "event_type", ""),
            "source_type": getattr(row, "source_type", ""),
            "source_url": getattr(row, "source_url", ""),
            "notes": getattr(row, "notes", ""),
            "old_name_key": normalize_company_name(
                getattr(row, "old_company_name", "")
            ),
            "new_name_key": normalize_company_name(
                getattr(row, "new_company_name", "")
            ),
        }

        if security_key:
            payload["security_key"] = str(security_key)
            payload["mapping_status"] = "MAPPED_UNIQUE_TICKER_HISTORY"
            mapped.append(payload)
        else:
            payload["mapping_status"] = reason
            unmapped.append(payload)

    return pd.DataFrame(mapped), pd.DataFrame(unmapped)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        CANDIDATE_MANIFEST_PATH,
        SEC_MAPPING_PATH,
        SEC_FORMER_NAMES_PATH,
        SEC_HOLDINGS_PATH,
        SEC_BRIDGE_PATH,
        MEMBERSHIP_PATH,
        TICKER_HISTORY_PATH,
        SECURITY_ALIASES_PATH,
    ):
        require(path)

    H3_DIR.mkdir(parents=True, exist_ok=True)

    candidate = pd.read_csv(
        CANDIDATE_MANIFEST_PATH, dtype=str, keep_default_na=False
    )
    sec_mapping = pd.read_csv(
        SEC_MAPPING_PATH, dtype=str, keep_default_na=False
    )
    former = pd.read_csv(
        SEC_FORMER_NAMES_PATH, dtype=str, keep_default_na=False
    )
    holdings = pd.read_csv(
        SEC_HOLDINGS_PATH,
        dtype={
            "holding_identifier": str,
            "holding_ticker": str,
            "holding_name": str,
        },
    )
    bridge = pd.read_csv(
        SEC_BRIDGE_PATH,
        dtype={"holding_identifier": str, "security_key": str},
    )
    membership = pd.read_csv(
        MEMBERSHIP_PATH, dtype=str, keep_default_na=False
    )
    ticker_history = pd.read_csv(
        TICKER_HISTORY_PATH, dtype=str, keep_default_na=False
    )
    aliases = pd.read_csv(
        SECURITY_ALIASES_PATH, dtype=str, keep_default_na=False
    )

    if len(candidate) != EXPECTED_IDENTITIES:
        raise RuntimeError(
            f"Candidate manifest rows={len(candidate)}, expected {EXPECTED_IDENTITIES}."
        )

    # ------------------------------------------------------------------
    # Membership boundaries.
    # ------------------------------------------------------------------
    membership["valid_from"] = pd.to_datetime(
        membership["valid_from"], errors="raise"
    )
    membership["valid_to_exclusive"] = pd.to_datetime(
        membership["valid_to_exclusive"], errors="raise"
    )
    membership["security_key"] = membership["security_key"].astype(str)

    if membership["security_key"].duplicated().any():
        raise RuntimeError(
            "Expected one canonical membership interval per security identity."
        )

    membership_bounds = membership[
        ["security_key", "valid_from", "valid_to_exclusive"]
    ].copy()

    # ------------------------------------------------------------------
    # Authoritative historical names from already validated SEC NPORT holdings.
    # ------------------------------------------------------------------
    bridge["holding_identifier"] = (
        bridge["holding_identifier"].astype(str).str.strip().str.upper()
    )
    bridge["security_key"] = bridge["security_key"].astype(str).str.strip()

    if bridge["holding_identifier"].duplicated().any():
        raise RuntimeError(
            "SEC GICS identifier bridge is not unique by holding_identifier."
        )

    holdings["holding_identifier"] = (
        holdings["holding_identifier"].astype(str).str.strip().str.upper()
    )
    holdings["report_date"] = pd.to_datetime(
        holdings["report_date"], errors="raise"
    )

    mapped_holdings = holdings.merge(
        bridge,
        on="holding_identifier",
        how="left",
        validate="many_to_one",
    )

    mapped_holdings = mapped_holdings[
        mapped_holdings["security_key"].notna()
    ].copy()

    mapped_holdings["security_key"] = (
        mapped_holdings["security_key"].astype(str).str.strip()
    )

    mapped_holdings = mapped_holdings.merge(
        membership_bounds,
        on="security_key",
        how="left",
        validate="many_to_one",
    )

    if mapped_holdings["valid_from"].isna().any():
        raise RuntimeError(
            "Mapped SEC holdings contain security_keys outside membership table."
        )

    # Retain a short pre-window support state for names of constituents already
    # present on 2021-01-01; in-window observations are primary evidence.
    mapped_holdings["evidence_scope"] = "OUTSIDE_MEMBERSHIP"

    in_membership = (
        (mapped_holdings["report_date"] >= mapped_holdings["valid_from"])
        & (
            mapped_holdings["report_date"]
            < mapped_holdings["valid_to_exclusive"]
        )
        & (mapped_holdings["report_date"] < PROJECT_END_EXCLUSIVE)
    )
    mapped_holdings.loc[in_membership, "evidence_scope"] = "IN_MEMBERSHIP"

    pre_support = (
        (mapped_holdings["valid_from"] == PROJECT_START)
        & (mapped_holdings["report_date"] >= SUPPORT_START)
        & (mapped_holdings["report_date"] < PROJECT_START)
    )
    mapped_holdings.loc[pre_support, "evidence_scope"] = "PRE_WINDOW_SUPPORT"

    name_evidence = mapped_holdings[
        mapped_holdings["evidence_scope"].isin(
            ["IN_MEMBERSHIP", "PRE_WINDOW_SUPPORT"]
        )
    ].copy()

    name_evidence["name_key"] = name_evidence["holding_name"].map(
        normalize_company_name
    )

    name_evidence = name_evidence[name_evidence["name_key"].ne("")].copy()

    observations = (
        name_evidence[
            [
                "security_key",
                "report_date",
                "holding_name",
                "name_key",
                "holding_identifier",
                "holding_ticker",
                "evidence_scope",
            ]
        ]
        .drop_duplicates()
        .sort_values(["security_key", "report_date", "name_key"])
        .reset_index(drop=True)
    )
    observations.to_csv(OBSERVATIONS_PATH, index=False)

    # ------------------------------------------------------------------
    # Existing explicit alias-event evidence.
    # ------------------------------------------------------------------
    ticker_map, ambiguous_tickers = build_ticker_map(ticker_history)
    mapped_aliases, unmapped_aliases = map_alias_events(aliases, ticker_map)

    if not mapped_aliases.empty:
        mapped_aliases["effective_date"] = pd.to_datetime(
            mapped_aliases["effective_date"], errors="coerce"
        )
        mapped_aliases["project_period_event_flag"] = (
            (mapped_aliases["effective_date"] >= PROJECT_START)
            & (mapped_aliases["effective_date"] < PROJECT_END_EXCLUSIVE)
        ).astype(int)

    mapped_aliases.to_csv(ALIAS_EVENTS_PATH, index=False)
    unmapped_aliases.to_csv(UNMAPPED_ALIAS_EVENTS_PATH, index=False)

    # ------------------------------------------------------------------
    # SEC submissions former-name evidence, restricted for decision making
    # to records overlapping the project period. Older names remain provenance.
    # ------------------------------------------------------------------
    if not former.empty:
        # SEC formerNames dates can arrive as a mixture of date-only strings
        # and timezone-bearing timestamps. Normalize all parseable values to
        # UTC first, then remove timezone information so comparisons against
        # the project's date-only boundaries are deterministic and safe.
        former["former_name_from_dt"] = (
            pd.to_datetime(
                former["former_name_from"],
                errors="coerce",
                utc=True,
            )
            .dt.tz_convert(None)
        )
        former["former_name_to_dt"] = (
            pd.to_datetime(
                former["former_name_to"],
                errors="coerce",
                utc=True,
            )
            .dt.tz_convert(None)
        )
        former["project_period_overlap_flag"] = former.apply(
            lambda row: int(
                overlap_project_period(
                    row["former_name_from_dt"],
                    row["former_name_to_dt"],
                )
            ),
            axis=1,
        )
    else:
        former["project_period_overlap_flag"] = pd.Series(dtype=int)

    # ------------------------------------------------------------------
    # Build security-level evidence summary.
    # ------------------------------------------------------------------
    rows = []

    candidate_lookup = candidate.set_index("security_key")
    sec_mapping_lookup = sec_mapping.set_index("security_key")

    alias_groups = (
        {k: g.copy() for k, g in mapped_aliases.groupby("security_key")}
        if not mapped_aliases.empty else {}
    )
    obs_groups = (
        {k: g.copy() for k, g in observations.groupby("security_key")}
        if not observations.empty else {}
    )

    former_by_cik = (
        {k: g.copy() for k, g in former.groupby("sec_cik")}
        if not former.empty else {}
    )

    transition_rows = []

    for security_key in candidate["security_key"].astype(str):
        c = candidate_lookup.loc[security_key]
        m = sec_mapping_lookup.loc[security_key]

        obs = obs_groups.get(security_key, pd.DataFrame())
        if obs.empty:
            unique_name_keys = []
            raw_names = []
            first_obs = ""
            last_obs = ""
            in_membership_obs = 0
            pre_support_obs = 0
        else:
            unique_name_keys = sorted(set(obs["name_key"].astype(str)))
            raw_names = sorted(set(obs["holding_name"].astype(str)))
            first_obs = str(pd.to_datetime(obs["report_date"]).min().date())
            last_obs = str(pd.to_datetime(obs["report_date"]).max().date())
            in_membership_obs = int(
                obs["evidence_scope"].eq("IN_MEMBERSHIP").sum()
            )
            pre_support_obs = int(
                obs["evidence_scope"].eq("PRE_WINDOW_SUPPORT").sum()
            )

            # Observation-bounded transition candidates only; no exact date is
            # inferred from quarterly holdings.
            ordered = (
                obs.sort_values(["report_date", "name_key"])
                .drop_duplicates(["report_date", "name_key"])
            )
            prior_key = None
            prior_date = None
            for item in ordered.itertuples(index=False):
                if prior_key is not None and item.name_key != prior_key:
                    transition_rows.append(
                        {
                            "security_key": security_key,
                            "from_name_key": prior_key,
                            "to_name_key": item.name_key,
                            "last_observed_old_state_date": prior_date,
                            "first_observed_new_state_date": item.report_date,
                            "transition_date_status": "BOUNDED_NOT_EXACT",
                        }
                    )
                prior_key = item.name_key
                prior_date = item.report_date

        alias_group = alias_groups.get(security_key, pd.DataFrame())
        alias_event_count = len(alias_group)
        project_alias_event_count = (
            int(alias_group["project_period_event_flag"].sum())
            if not alias_group.empty
            else 0
        )

        cik = str(m.get("candidate_sec_cik", "")).strip()
        former_group = former_by_cik.get(cik, pd.DataFrame()) if cik else pd.DataFrame()
        former_total = len(former_group)
        former_project = (
            int(former_group["project_period_overlap_flag"].sum())
            if not former_group.empty
            else 0
        )

        project_name_key = normalize_company_name(
            c["canonical_company_name"]
        )
        project_name_seen_flag = int(
            project_name_key in unique_name_keys
        )

        nport_unique_count = len(unique_name_keys)

        # Classification intentionally prioritizes the historical SEC NPORT
        # name observations already validated and mapped in the GICS pipeline.
        if nport_unique_count == 0:
            status = "REVIEW_NO_MAPPED_SEC_NPORT_NAME"
        elif nport_unique_count > 1:
            status = "REVIEW_MULTIPLE_SEC_NPORT_NAMES"
        elif project_name_seen_flag == 0:
            status = "REVIEW_PROJECT_NAME_DIFFERS_FROM_SEC_NPORT"
        elif project_alias_event_count > 0 or former_project > 0:
            status = "REVIEW_PROJECT_PERIOD_NAME_EVENT_EVIDENCE"
        else:
            status = "READY_STABLE_SEC_NPORT_NAME"

        review_flag = int(not status.startswith("READY_"))

        rows.append(
            {
                "security_key": security_key,
                "latest_project_ticker": c.get("latest_project_ticker", ""),
                "canonical_company_name": c["canonical_company_name"],
                "project_name_key": project_name_key,
                "structural_ambiguity_tier": c["structural_ambiguity_tier"],
                "stage3b_mapping_status": m["mapping_status"],
                "candidate_sec_cik": cik,
                "sec_nport_observation_rows": len(obs),
                "sec_nport_in_membership_rows": in_membership_obs,
                "sec_nport_pre_window_support_rows": pre_support_obs,
                "sec_nport_unique_name_count": nport_unique_count,
                "sec_nport_name_keys_pipe": "|".join(unique_name_keys),
                "sec_nport_raw_names_pipe": "|".join(raw_names),
                "sec_nport_first_observed_date": first_obs,
                "sec_nport_last_observed_date": last_obs,
                "project_current_name_seen_in_sec_nport_flag": project_name_seen_flag,
                "mapped_alias_event_count": alias_event_count,
                "project_period_alias_event_count": project_alias_event_count,
                "sec_former_name_count_for_cik": former_total,
                "project_period_sec_former_name_count": former_project,
                "pit_name_evidence_status": status,
                "pit_name_review_flag": review_flag,
            }
        )

    summary = pd.DataFrame(rows).sort_values(
        [
            "pit_name_review_flag",
            "pit_name_evidence_status",
            "latest_project_ticker",
            "security_key",
        ],
        ascending=[False, True, True, True],
    )

    summary.to_csv(SUMMARY_PATH, index=False)

    transitions = pd.DataFrame(
        transition_rows,
        columns=[
            "security_key",
            "from_name_key",
            "to_name_key",
            "last_observed_old_state_date",
            "first_observed_new_state_date",
            "transition_date_status",
        ],
    )
    transitions.to_csv(TRANSITIONS_PATH, index=False)

    review = summary[summary["pit_name_review_flag"].eq(1)].copy()

    priority = {
        "REVIEW_NO_MAPPED_SEC_NPORT_NAME": 1,
        "REVIEW_MULTIPLE_SEC_NPORT_NAMES": 1,
        "REVIEW_PROJECT_PERIOD_NAME_EVENT_EVIDENCE": 2,
        "REVIEW_PROJECT_NAME_DIFFERS_FROM_SEC_NPORT": 2,
    }
    review["review_priority"] = (
        review["pit_name_evidence_status"].map(priority).fillna(9).astype(int)
    )

    review = review.sort_values(
        ["review_priority", "latest_project_ticker", "security_key"]
    )
    review.to_csv(REVIEW_PATH, index=False)

    status_counts = summary["pit_name_evidence_status"].value_counts().to_dict()

    lines = [
        "=" * 120,
        "H3 STAGE 3B2 — POINT-IN-TIME COMPANY-NAME EVIDENCE CONSOLIDATION",
        "=" * 120,
        f"Security identities: {len(summary)}",
        f"Mapped SEC NPORT name-observation rows: {len(observations)}",
        (
            "Identities with at least one mapped SEC NPORT name state: "
            f"{int(summary['sec_nport_unique_name_count'].gt(0).sum())}"
        ),
        (
            "Identities with exactly one SEC NPORT normalized name state: "
            f"{int(summary['sec_nport_unique_name_count'].eq(1).sum())}"
        ),
        (
            "Identities with multiple SEC NPORT normalized name states: "
            f"{int(summary['sec_nport_unique_name_count'].gt(1).sum())}"
        ),
        (
            "Identities with no mapped SEC NPORT name state: "
            f"{int(summary['sec_nport_unique_name_count'].eq(0).sum())}"
        ),
        f"Mapped security_aliases events: {len(mapped_aliases)}",
        f"Unmapped security_aliases events: {len(unmapped_aliases)}",
        f"Observation-bounded name transition candidates: {len(transitions)}",
        (
            "READY stable-name identities: "
            f"{int(summary['pit_name_evidence_status'].eq('READY_STABLE_SEC_NPORT_NAME').sum())}"
        ),
        f"Remaining focused PIT-name review queue: {len(review)}",
        "",
        "Status counts:",
    ]

    for status, count in sorted(status_counts.items()):
        lines.append(f"  {status}: {count}")

    lines += [
        "",
        "SOURCE HIERARCHY FOR THIS STAGE:",
        (
            "1. already validated SEC Select Sector NPORT holding-name states "
            "mapped to security_key by the audited GICS identifier bridge;"
        ),
        "2. explicit project security_aliases events;",
        "3. SEC submissions/formerNames as secondary identity/name-history evidence;",
        "4. current project company_name_reference as comparison evidence only.",
        "",
        "IMPORTANT:",
        (
            "Quarterly SEC NPORT observations bound a possible name transition "
            "but do NOT provide an exact effective date by themselves."
        ),
        (
            "No production point-in-time alias interval is created in this stage."
        ),
        "Return/outcome fields read: 0",
        "Full-history GDELT extraction performed: NO",
        "",
        "H3_PIT_NAME_EVIDENCE_CONSOLIDATION_COMPLETE",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
