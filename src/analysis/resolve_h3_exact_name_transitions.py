from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-exact-name-transition-resolution"

H3_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

SUMMARY_PATH = H3_DIR / "h3_pit_name_evidence_security_summary.csv"
REVIEW_PATH = H3_DIR / "h3_pit_name_evidence_review_queue.csv"
TRANSITIONS_PATH = H3_DIR / "h3_pit_name_transition_candidates.csv"
ALIAS_EVENTS_PATH = H3_DIR / "h3_pit_name_alias_events_mapped.csv"
SEC_FORMER_NAMES_PATH = H3_DIR / "h3_sec_former_names_raw.csv"

RESOLUTIONS_PATH = H3_DIR / "h3_exact_name_transition_resolutions.csv"
UNRESOLVED_PATH = H3_DIR / "h3_exact_name_transition_unresolved.csv"
RESEARCH_MANIFEST_PATH = H3_DIR / "h3_exact_name_transition_research_manifest.csv"
SEC_FORMER_RELEVANT_PATH = H3_DIR / "h3_sec_former_names_project_period_relevant.csv"
REPORT_PATH = H3_DIR / "h3_exact_name_transition_resolution_report.txt"

PROJECT_START = pd.Timestamp("2021-01-01")
PROJECT_END_EXCLUSIVE = pd.Timestamp("2026-01-01")

EXACT_SOURCE = "PROJECT_SECURITY_ALIASES_EXACT_EVENT"


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def parse_date(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce", utc=True).tz_convert(None)


def normalize_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        SUMMARY_PATH,
        REVIEW_PATH,
        TRANSITIONS_PATH,
        ALIAS_EVENTS_PATH,
        SEC_FORMER_NAMES_PATH,
    ):
        require(path)

    summary = pd.read_csv(
        SUMMARY_PATH, dtype=str, keep_default_na=False
    )
    review = pd.read_csv(
        REVIEW_PATH, dtype=str, keep_default_na=False
    )
    transitions = pd.read_csv(
        TRANSITIONS_PATH, dtype=str, keep_default_na=False
    )
    alias_events = pd.read_csv(
        ALIAS_EVENTS_PATH, dtype=str, keep_default_na=False
    )
    former = pd.read_csv(
        SEC_FORMER_NAMES_PATH, dtype=str, keep_default_na=False
    )

    # --------------------------------------------------------------
    # Normalize dates.
    # --------------------------------------------------------------
    if not transitions.empty:
        transitions["last_old_dt"] = normalize_date_series(
            transitions["last_observed_old_state_date"]
        )
        transitions["first_new_dt"] = normalize_date_series(
            transitions["first_observed_new_state_date"]
        )

    if not alias_events.empty:
        alias_events["effective_dt"] = normalize_date_series(
            alias_events["effective_date"]
        )

    if not former.empty:
        former["former_from_dt"] = normalize_date_series(
            former["former_name_from"]
        )
        former["former_to_dt"] = normalize_date_series(
            former["former_name_to"]
        )
        former["project_period_relevant_flag"] = (
            (
                former["former_from_dt"].isna()
                | (former["former_from_dt"] < PROJECT_END_EXCLUSIVE)
            )
            & (
                former["former_to_dt"].isna()
                | (former["former_to_dt"] >= PROJECT_START)
            )
        ).astype(int)
    else:
        former["project_period_relevant_flag"] = pd.Series(dtype=int)

    former_relevant = former[
        former["project_period_relevant_flag"].eq(1)
    ].copy()

    former_relevant.to_csv(
        SEC_FORMER_RELEVANT_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Exact transition resolution:
    #
    # The only automatic exact-date source in this stage is an explicit
    # dated project security_aliases event whose old/new normalized names
    # exactly match a bounded NPORT transition and whose effective date
    # falls inside that NPORT observation interval.
    # --------------------------------------------------------------
    resolution_rows = []
    unresolved_rows = []

    if not transitions.empty:
        for row in transitions.itertuples(index=False):
            security_key = str(row.security_key)
            old_key = str(row.from_name_key)
            new_key = str(row.to_name_key)
            last_old = row.last_old_dt
            first_new = row.first_new_dt

            candidates = alias_events[
                alias_events["security_key"].astype(str).eq(security_key)
                & alias_events["old_name_key"].astype(str).eq(old_key)
                & alias_events["new_name_key"].astype(str).eq(new_key)
            ].copy()

            if pd.notna(last_old):
                candidates = candidates[
                    candidates["effective_dt"] > last_old
                ]
            if pd.notna(first_new):
                candidates = candidates[
                    candidates["effective_dt"] <= first_new
                ]

            candidates = candidates[
                candidates["effective_dt"].notna()
            ].copy()

            unique_dates = sorted(
                set(candidates["effective_dt"].tolist())
            )

            base = {
                "security_key": security_key,
                "from_name_key": old_key,
                "to_name_key": new_key,
                "last_observed_old_state_date": (
                    "" if pd.isna(last_old) else last_old.date().isoformat()
                ),
                "first_observed_new_state_date": (
                    "" if pd.isna(first_new) else first_new.date().isoformat()
                ),
            }

            if len(unique_dates) == 1:
                exact_date = unique_dates[0]
                source_rows = candidates[
                    candidates["effective_dt"].eq(exact_date)
                ]

                resolution_rows.append(
                    {
                        **base,
                        "resolution_status": "RESOLVED_EXACT",
                        "exact_effective_date": exact_date.date().isoformat(),
                        "resolution_source": EXACT_SOURCE,
                        "source_type_pipe": "|".join(
                            sorted(
                                set(
                                    source_rows["source_type"]
                                    .astype(str)
                                    .tolist()
                                )
                            )
                        ),
                        "source_url_pipe": "|".join(
                            sorted(
                                {
                                    x
                                    for x in source_rows["source_url"]
                                    .astype(str)
                                    .tolist()
                                    if x
                                }
                            )
                        ),
                        "source_event_type_pipe": "|".join(
                            sorted(
                                set(
                                    source_rows["event_type"]
                                    .astype(str)
                                    .tolist()
                                )
                            )
                        ),
                        "candidate_event_count": len(candidates),
                    }
                )
            else:
                reason = (
                    "NO_EXACT_MATCHING_ALIAS_EVENT_IN_BOUND"
                    if len(unique_dates) == 0
                    else "MULTIPLE_EXACT_ALIAS_EVENT_DATES_IN_BOUND"
                )

                unresolved_rows.append(
                    {
                        **base,
                        "resolution_status": "UNRESOLVED_EXACT_DATE",
                        "unresolved_reason": reason,
                        "matching_alias_event_rows": len(candidates),
                        "matching_alias_event_dates_pipe": "|".join(
                            d.date().isoformat()
                            for d in unique_dates
                        ),
                    }
                )

    resolutions = pd.DataFrame(
        resolution_rows,
        columns=[
            "security_key",
            "from_name_key",
            "to_name_key",
            "last_observed_old_state_date",
            "first_observed_new_state_date",
            "resolution_status",
            "exact_effective_date",
            "resolution_source",
            "source_type_pipe",
            "source_url_pipe",
            "source_event_type_pipe",
            "candidate_event_count",
        ],
    )

    unresolved = pd.DataFrame(
        unresolved_rows,
        columns=[
            "security_key",
            "from_name_key",
            "to_name_key",
            "last_observed_old_state_date",
            "first_observed_new_state_date",
            "resolution_status",
            "unresolved_reason",
            "matching_alias_event_rows",
            "matching_alias_event_dates_pipe",
        ],
    )

    resolutions.to_csv(RESOLUTIONS_PATH, index=False)
    unresolved.to_csv(UNRESOLVED_PATH, index=False)

    # --------------------------------------------------------------
    # Build targeted research manifest.
    #
    # Include:
    # - unresolved bounded NPORT transitions;
    # - review identities with no bounded transition but still requiring
    #   project-period name-event resolution.
    # --------------------------------------------------------------
    research_rows = []

    summary_lookup = summary.set_index("security_key")

    unresolved_keys = set(
        unresolved["security_key"].astype(str)
    ) if not unresolved.empty else set()

    for row in unresolved.itertuples(index=False):
        s = summary_lookup.loc[str(row.security_key)]

        research_rows.append(
            {
                "security_key": row.security_key,
                "latest_project_ticker": s["latest_project_ticker"],
                "canonical_company_name": s["canonical_company_name"],
                "research_type": "EXACT_RENAME_DATE",
                "from_name_key": row.from_name_key,
                "to_name_key": row.to_name_key,
                "search_start_date": row.last_observed_old_state_date,
                "search_end_date": row.first_observed_new_state_date,
                "candidate_sec_cik": s["candidate_sec_cik"],
                "research_priority": 1,
                "required_source_standard": (
                    "SEC filing/current report/company investor-relations "
                    "announcement or other primary authoritative corporate source"
                ),
                "research_question": (
                    "What exact effective date changed the issuer/company "
                    "name from the old observed name to the new observed name?"
                ),
            }
        )

    # Cases flagged for project-period name-event evidence but which did not
    # produce a bounded historical-name transition also deserve targeted review.
    extra_review = review[
        review["pit_name_evidence_status"].isin(
            [
                "REVIEW_PROJECT_PERIOD_NAME_EVENT_EVIDENCE",
                "REVIEW_PROJECT_NAME_DIFFERS_FROM_SEC_NPORT",
            ]
        )
        & ~review["security_key"].astype(str).isin(unresolved_keys)
    ].copy()

    for row in extra_review.itertuples(index=False):
        research_rows.append(
            {
                "security_key": row.security_key,
                "latest_project_ticker": row.latest_project_ticker,
                "canonical_company_name": row.canonical_company_name,
                "research_type": "NAME_STATE_RECONCILIATION",
                "from_name_key": "",
                "to_name_key": "",
                "search_start_date": "2021-01-01",
                "search_end_date": "2025-12-31",
                "candidate_sec_cik": row.candidate_sec_cik,
                "research_priority": 2,
                "required_source_standard": (
                    "SEC/company primary authoritative source"
                ),
                "research_question": (
                    "Did this issuer have a project-period company-name "
                    "change relevant to attention-query aliases, and if so "
                    "what were the exact names and effective dates?"
                ),
            }
        )

    research = pd.DataFrame(
        research_rows,
        columns=[
            "security_key",
            "latest_project_ticker",
            "canonical_company_name",
            "research_type",
            "from_name_key",
            "to_name_key",
            "search_start_date",
            "search_end_date",
            "candidate_sec_cik",
            "research_priority",
            "required_source_standard",
            "research_question",
        ],
    )

    if not research.empty:
        research = research.drop_duplicates().sort_values(
            [
                "research_priority",
                "latest_project_ticker",
                "security_key",
            ]
        )

    research.to_csv(RESEARCH_MANIFEST_PATH, index=False)

    # --------------------------------------------------------------
    # Report.
    # --------------------------------------------------------------
    lines = [
        "=" * 120,
        "H3 STAGE 3C — EXACT COMPANY-NAME TRANSITION RESOLUTION",
        "=" * 120,
        f"Stage 3B2 focused review identities: {len(review)}",
        f"Bounded SEC NPORT name-transition candidates: {len(transitions)}",
        f"Automatically exact-resolved transitions: {len(resolutions)}",
        f"Unresolved bounded transitions: {len(unresolved)}",
        (
            "Additional project-period name-state reconciliation cases: "
            f"{len(extra_review)}"
        ),
        f"Targeted authoritative research manifest rows: {len(research)}",
        f"Project-period relevant SEC former-name evidence rows: {len(former_relevant)}",
        "",
        "AUTOMATIC EXACT-DATE RULE:",
        (
            "Only an explicit dated project security_aliases event with "
            "exact old/new normalized-name agreement AND a date inside "
            "the quarterly NPORT transition bound may auto-resolve an "
            "exact rename date."
        ),
        "",
        "SEC formerNames remain corroborating evidence only in this stage;",
        "they are not treated as an exact rename date automatically.",
        "",
        "Production PIT alias intervals created: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_EXACT_NAME_TRANSITION_RESOLUTION_COMPLETE",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
