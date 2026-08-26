from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-deterministic-name-state-reconciliation"

H3_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

REMAINING_PATH = H3_DIR / "h3_name_state_reconciliation_remaining.csv"
SUMMARY_PATH = H3_DIR / "h3_pit_name_evidence_security_summary.csv"
OBSERVATIONS_PATH = H3_DIR / "h3_pit_name_state_observations.csv"
SEC_MAPPING_PATH = H3_DIR / "h3_sec_cik_mapping_candidates.csv"
SEC_METADATA_PATH = H3_DIR / "h3_sec_submissions_company_metadata.csv"
SEC_FORMER_PATH = H3_DIR / "h3_sec_former_names_raw.csv"

AUTO_TRANSITIONS_PATH = H3_DIR / "h3_exact_name_transition_resolutions.csv"
AUTHORITATIVE_TRANSITIONS_PATH = (
    H3_DIR / "h3_authoritative_exact_name_transition_resolutions.csv"
)

OUT_PATH = H3_DIR / "h3_name_state_reconciliation_classification.csv"
RESOLVED_PATH = H3_DIR / "h3_name_state_reconciliation_auto_resolved.csv"
RESEARCH_PATH = H3_DIR / "h3_name_state_reconciliation_research_manifest.csv"
TRANSITION_SUPPORT_PATH = H3_DIR / "h3_combined_resolved_name_transitions.csv"
REPORT_PATH = H3_DIR / "h3_name_state_reconciliation_report.txt"

EXPECTED_REMAINING_ROWS = 119
PROJECT_START = pd.Timestamp("2021-01-01")
PROJECT_END_EXCLUSIVE = pd.Timestamp("2026-01-01")

RESOLVED_PREFIX = "RESOLVED_"
RESEARCH_PREFIX = "RESEARCH_"


LEGAL_SUFFIX_PATTERNS = [
    r"\bINCORPORATED\b",
    r"\bCORPORATION\b",
    r"\bCOMPANY\b",
    r"\bLIMITED\b",
    r"\bLTD\b",
    r"\bINC\b",
    r"\bCORP\b",
    r"\bCO\b",
    r"\bPLC\b",
    r"\bLLC\b",
    r"\bLLP\b",
    r"\bLP\b",
    r"\bN\s*V\b",
    r"\bNV\b",
    r"\bS\s*A\b",
    r"\bSA\b",
    r"\bA\s*G\b",
    r"\bAG\b",
    r"\bS\s*E\b",
    r"\bSE\b",
]

TRAILING_JURISDICTION_PATTERNS = [
    r"\bDELAWARE\b",
    r"\bDEL\b",
]


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def normalize_exact(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    text = unicodedata.normalize("NFKC", str(value)).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[’']", "", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text.startswith("THE "):
        text = text[4:].strip()

    return text


def normalize_legal_core(value: object) -> str:
    """
    Conservative deterministic legal-style normalization only.

    This intentionally does NOT remove semantic words such as:
      GROUP, HOLDINGS, INTERNATIONAL, TECHNOLOGIES, ENERGY, FINANCIAL,
      SYSTEMS, PROPERTIES, HEALTH, DIGITAL, etc.

    The goal is to reconcile punctuation/legal-form presentation, not to
    maximize name similarity.
    """
    text = normalize_exact(value)

    # Remove common security-class descriptions.
    text = re.sub(r"\bCLASS\s+[A-Z0-9]+\b", " ", text)
    text = re.sub(r"\bCL\s+[A-Z0-9]+\b", " ", text)
    text = re.sub(r"\bORDINARY\s+SHARES?\b", " ", text)
    text = re.sub(r"\bCOMMON\s+STOCK\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    changed = True
    while changed and text:
        changed = False

        for pattern in LEGAL_SUFFIX_PATTERNS:
            updated = re.sub(
                rf"(?:\s+|^){pattern}$",
                "",
                text,
            ).strip()
            if updated != text:
                text = updated
                changed = True
                break

        if changed:
            continue

        for pattern in TRAILING_JURISDICTION_PATTERNS:
            updated = re.sub(
                rf"(?:\s+|^){pattern}$",
                "",
                text,
            ).strip()
            if updated != text:
                text = updated
                changed = True
                break

    return re.sub(r"\s+", " ", text).strip()


def split_pipe(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [
        part.strip()
        for part in str(value).split("|")
        if part.strip()
    ]


def date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)


def project_period_former_names(
    former: pd.DataFrame,
) -> pd.DataFrame:
    if former.empty:
        return former.copy()

    work = former.copy()
    work["from_dt"] = date_series(work["former_name_from"])
    work["to_dt"] = date_series(work["former_name_to"])

    work["project_overlap"] = (
        (
            work["from_dt"].isna()
            | (work["from_dt"] < PROJECT_END_EXCLUSIVE)
        )
        & (
            work["to_dt"].isna()
            | (work["to_dt"] >= PROJECT_START)
        )
    )

    return work[work["project_overlap"]].copy()


def build_transition_support(
    auto: pd.DataFrame,
    authoritative: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    if not auto.empty:
        for row in auto.itertuples(index=False):
            rows.append(
                {
                    "security_key": str(row.security_key),
                    "from_name_key": str(row.from_name_key),
                    "to_name_key": str(row.to_name_key),
                    "resolution_class": "TRUE_RENAME",
                    "resolution_status": str(row.resolution_status),
                    "exact_legal_effective_date": str(
                        getattr(row, "exact_effective_date", "")
                    ),
                    "source_layer": "STAGE3C_AUTO_EXACT",
                }
            )

    if not authoritative.empty:
        for row in authoritative.itertuples(index=False):
            status = str(row.resolution_status)

            if status.startswith("RESOLVED_TRUE_LEGAL_RENAME"):
                resolution_class = "TRUE_RENAME"
            elif status.startswith("REJECT_FALSE_TRANSITION"):
                resolution_class = "FALSE_TRANSITION"
            else:
                resolution_class = "UNKNOWN"

            rows.append(
                {
                    "security_key": str(row.security_key),
                    "from_name_key": str(row.from_name_key),
                    "to_name_key": str(row.to_name_key),
                    "resolution_class": resolution_class,
                    "resolution_status": status,
                    "exact_legal_effective_date": str(
                        getattr(row, "exact_legal_effective_date", "")
                    ),
                    "source_layer": "STAGE3D_AUTHORITATIVE",
                }
            )

    result = pd.DataFrame(
        rows,
        columns=[
            "security_key",
            "from_name_key",
            "to_name_key",
            "resolution_class",
            "resolution_status",
            "exact_legal_effective_date",
            "source_layer",
        ],
    )

    if not result.empty:
        result = result.drop_duplicates().sort_values(
            [
                "security_key",
                "exact_legal_effective_date",
                "from_name_key",
                "to_name_key",
            ]
        )

    return result


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        REMAINING_PATH,
        SUMMARY_PATH,
        OBSERVATIONS_PATH,
        SEC_MAPPING_PATH,
        SEC_METADATA_PATH,
        SEC_FORMER_PATH,
        AUTO_TRANSITIONS_PATH,
        AUTHORITATIVE_TRANSITIONS_PATH,
    ]
    for path in required:
        require(path)

    remaining = pd.read_csv(
        REMAINING_PATH,
        dtype=str,
        keep_default_na=False,
    )
    summary = pd.read_csv(
        SUMMARY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    observations = pd.read_csv(
        OBSERVATIONS_PATH,
        dtype=str,
        keep_default_na=False,
    )
    sec_mapping = pd.read_csv(
        SEC_MAPPING_PATH,
        dtype=str,
        keep_default_na=False,
    )
    sec_metadata = pd.read_csv(
        SEC_METADATA_PATH,
        dtype=str,
        keep_default_na=False,
    )
    former = pd.read_csv(
        SEC_FORMER_PATH,
        dtype=str,
        keep_default_na=False,
    )
    auto_transitions = pd.read_csv(
        AUTO_TRANSITIONS_PATH,
        dtype=str,
        keep_default_na=False,
    )
    authoritative_transitions = pd.read_csv(
        AUTHORITATIVE_TRANSITIONS_PATH,
        dtype=str,
        keep_default_na=False,
    )

    if len(remaining) != EXPECTED_REMAINING_ROWS:
        raise RuntimeError(
            f"Remaining Stage 3D rows={len(remaining)}, "
            f"expected {EXPECTED_REMAINING_ROWS}."
        )

    if remaining["security_key"].duplicated().any():
        raise RuntimeError(
            "Expected one NAME_STATE_RECONCILIATION row per security_key."
        )

    transition_support = build_transition_support(
        auto_transitions,
        authoritative_transitions,
    )
    transition_support.to_csv(
        TRANSITION_SUPPORT_PATH,
        index=False,
    )

    summary_lookup = summary.set_index("security_key")
    mapping_lookup = sec_mapping.set_index("security_key")

    metadata_lookup = (
        sec_metadata.set_index("sec_cik")
        if not sec_metadata.empty
        else pd.DataFrame()
    )

    obs_groups = {
        str(key): group.copy()
        for key, group in observations.groupby("security_key")
    }

    former_project = project_period_former_names(former)
    former_groups = {
        str(key): group.copy()
        for key, group in former_project.groupby("sec_cik")
    }

    transition_groups = {
        str(key): group.copy()
        for key, group in transition_support.groupby("security_key")
    }

    classification_rows = []

    for row in remaining.itertuples(index=False):
        security_key = str(row.security_key)
        s = summary_lookup.loc[security_key]
        m = mapping_lookup.loc[security_key]

        project_name = str(row.canonical_company_name)
        project_exact = normalize_exact(project_name)
        project_core = normalize_legal_core(project_name)

        cik = str(row.candidate_sec_cik).strip()
        sec_current_name = ""

        if (
            cik
            and not sec_metadata.empty
            and cik in metadata_lookup.index
        ):
            metadata_row = metadata_lookup.loc[cik]
            if isinstance(metadata_row, pd.DataFrame):
                metadata_row = metadata_row.iloc[0]
            sec_current_name = str(
                metadata_row.get("sec_current_name", "")
            )

        sec_current_exact = normalize_exact(sec_current_name)
        sec_current_core = normalize_legal_core(sec_current_name)

        obs = obs_groups.get(
            security_key,
            pd.DataFrame(),
        )

        raw_nport_names = (
            sorted(set(obs["holding_name"].astype(str)))
            if not obs.empty
            else []
        )

        nport_exact = sorted(
            {
                normalize_exact(name)
                for name in raw_nport_names
                if normalize_exact(name)
            }
        )
        nport_cores = sorted(
            {
                normalize_legal_core(name)
                for name in raw_nport_names
                if normalize_legal_core(name)
            }
        )

        transitions = transition_groups.get(
            security_key,
            pd.DataFrame(),
        )

        true_transition_count = (
            int(
                transitions[
                    "resolution_class"
                ].eq("TRUE_RENAME").sum()
            )
            if not transitions.empty
            else 0
        )

        false_transition_count = (
            int(
                transitions[
                    "resolution_class"
                ].eq("FALSE_TRANSITION").sum()
            )
            if not transitions.empty
            else 0
        )

        project_former = former_groups.get(
            cik,
            pd.DataFrame(),
        ) if cik else pd.DataFrame()

        project_former_count = len(project_former)

        # Build the set of transition name cores that have already been
        # authoritatively explained.
        explained_transition_cores = set()
        if not transitions.empty:
            for transition in transitions.itertuples(index=False):
                explained_transition_cores.add(
                    normalize_legal_core(
                        transition.from_name_key
                    )
                )
                explained_transition_cores.add(
                    normalize_legal_core(
                        transition.to_name_key
                    )
                )

        nport_core_set = set(nport_cores)

        all_nport_states_explained = bool(
            nport_core_set
            and nport_core_set.issubset(
                explained_transition_cores
            )
        )

        # ----------------------------------------------------------
        # Frozen deterministic classification.
        # ----------------------------------------------------------
        if (
            true_transition_count > 0
            and all_nport_states_explained
        ):
            status = "RESOLVED_BY_AUTHORITATIVE_TRANSITION_HISTORY"
            rationale = (
                "All observed NPORT name states are covered by already "
                "resolved true rename transition evidence."
            )

        elif (
            false_transition_count > 0
            and true_transition_count == 0
            and all_nport_states_explained
        ):
            status = "RESOLVED_FALSE_NPORT_TRANSITION_STABLE_ISSUER"
            rationale = (
                "All apparent NPORT name-state changes are already "
                "authoritatively rejected as source-label variants or "
                "multi-registrant contamination."
            )

        elif (
            len(nport_cores) == 1
            and project_core
            and nport_cores[0] == project_core
            and (
                not sec_current_core
                or sec_current_core == project_core
            )
            and project_former_count == 0
        ):
            status = "RESOLVED_STABLE_LEGAL_STYLE_EQUIVALENT"
            rationale = (
                "Project name, NPORT historical state, and available SEC "
                "current name agree after conservative legal-style "
                "normalization; no project-period SEC former-name evidence."
            )

        elif len(nport_cores) == 0:
            status = "RESEARCH_NO_NPORT_NAME_EVIDENCE"
            rationale = (
                "No mapped NPORT company-name state is available for "
                "deterministic reconciliation."
            )

        elif len(nport_cores) > 1:
            status = "RESEARCH_MULTIPLE_UNEXPLAINED_NPORT_STATES"
            rationale = (
                "Multiple historical NPORT name states remain after applying "
                "all already resolved transition evidence."
            )

        elif project_former_count > 0:
            status = "RESEARCH_PROJECT_PERIOD_SEC_FORMER_NAME_EVIDENCE"
            rationale = (
                "SEC former-name metadata overlaps the project window and "
                "has not yet been tied to an exact authoritative transition "
                "or rejected as irrelevant."
            )

        elif (
            len(nport_cores) == 1
            and project_core
            and nport_cores[0] != project_core
        ):
            status = "RESEARCH_PROJECT_VS_NPORT_NAME_CORE_CONFLICT"
            rationale = (
                "Project reference company name and historical NPORT name "
                "remain different under conservative legal-style normalization."
            )

        elif (
            sec_current_core
            and project_core
            and sec_current_core != project_core
        ):
            status = "RESEARCH_PROJECT_VS_SEC_CURRENT_NAME_CORE_CONFLICT"
            rationale = (
                "Project reference company name and SEC current filer name "
                "remain different under conservative legal-style normalization."
            )

        else:
            status = "RESEARCH_UNRESOLVED_NAME_STATE"
            rationale = (
                "Available deterministic evidence does not meet a frozen "
                "automatic-resolution rule."
            )

        classification_rows.append(
            {
                "security_key": security_key,
                "latest_project_ticker": row.latest_project_ticker,
                "canonical_company_name": project_name,
                "candidate_sec_cik": cik,
                "project_name_exact": project_exact,
                "project_name_legal_core": project_core,
                "sec_current_name": sec_current_name,
                "sec_current_name_exact": sec_current_exact,
                "sec_current_name_legal_core": sec_current_core,
                "nport_raw_names_pipe": "|".join(raw_nport_names),
                "nport_exact_names_pipe": "|".join(nport_exact),
                "nport_legal_cores_pipe": "|".join(nport_cores),
                "nport_legal_core_count": len(nport_cores),
                "true_transition_count": true_transition_count,
                "false_transition_count": false_transition_count,
                "all_nport_states_explained_by_transition_flag": int(
                    all_nport_states_explained
                ),
                "project_period_sec_former_name_count": project_former_count,
                "reconciliation_status": status,
                "reconciliation_rationale": rationale,
            }
        )

    result = pd.DataFrame(classification_rows)

    if len(result) != EXPECTED_REMAINING_ROWS:
        raise RuntimeError(
            f"Classification rows={len(result)}, expected 119."
        )

    resolved = result[
        result["reconciliation_status"].str.startswith(
            RESOLVED_PREFIX
        )
    ].copy()

    research = result[
        result["reconciliation_status"].str.startswith(
            RESEARCH_PREFIX
        )
    ].copy()

    if len(resolved) + len(research) != len(result):
        unexpected = result.loc[
            ~result["reconciliation_status"].str.startswith(
                (RESOLVED_PREFIX, RESEARCH_PREFIX)
            ),
            ["security_key", "reconciliation_status"],
        ]
        raise RuntimeError(
            "Unexpected reconciliation status:\n"
            + unexpected.to_string(index=False)
        )

    priority = {
        "RESEARCH_MULTIPLE_UNEXPLAINED_NPORT_STATES": 1,
        "RESEARCH_PROJECT_PERIOD_SEC_FORMER_NAME_EVIDENCE": 1,
        "RESEARCH_PROJECT_VS_NPORT_NAME_CORE_CONFLICT": 2,
        "RESEARCH_PROJECT_VS_SEC_CURRENT_NAME_CORE_CONFLICT": 2,
        "RESEARCH_NO_NPORT_NAME_EVIDENCE": 3,
        "RESEARCH_UNRESOLVED_NAME_STATE": 4,
    }

    research["research_priority"] = (
        research["reconciliation_status"]
        .map(priority)
        .fillna(9)
        .astype(int)
    )

    research["required_source_standard"] = (
        "SEC filing, SEC exhibit, official company investor-relations "
        "announcement, or equivalent primary corporate source"
    )

    research["research_question"] = research.apply(
        lambda x: (
            "Resolve the issuer's valid public/company name state(s) and any "
            "project-period effective date(s) needed for a high-precision "
            "GDELT company-attention alias."
        ),
        axis=1,
    )

    result = result.sort_values(
        [
            "reconciliation_status",
            "latest_project_ticker",
            "security_key",
        ]
    )
    resolved = resolved.sort_values(
        [
            "reconciliation_status",
            "latest_project_ticker",
            "security_key",
        ]
    )
    research = research.sort_values(
        [
            "research_priority",
            "reconciliation_status",
            "latest_project_ticker",
            "security_key",
        ]
    )

    result.to_csv(OUT_PATH, index=False)
    resolved.to_csv(RESOLVED_PATH, index=False)
    research.to_csv(RESEARCH_PATH, index=False)

    status_counts = (
        result["reconciliation_status"]
        .value_counts()
        .to_dict()
    )

    lines = [
        "=" * 122,
        "H3 STAGE 3E — DETERMINISTIC NAME-STATE RECONCILIATION",
        "=" * 122,
        f"Input NAME_STATE_RECONCILIATION identities: {len(result)}",
        f"Automatically reconciled identities: {len(resolved)}",
        f"Remaining targeted research identities: {len(research)}",
        (
            "Combined already-resolved name-transition rows used as evidence: "
            f"{len(transition_support)}"
        ),
        "",
        "Status counts:",
    ]

    for status, count in sorted(status_counts.items()):
        lines.append(f"  {status}: {count}")

    lines += [
        "",
        "AUTOMATIC RESOLUTION RULES:",
        (
            "- already-authoritative true transition history explains all "
            "observed NPORT states;"
        ),
        (
            "- already-rejected false transitions explain all observed "
            "NPORT state variation; or"
        ),
        (
            "- one stable NPORT name state equals the project/SEC name after "
            "conservative legal-form normalization and there is no "
            "project-period SEC former-name evidence."
        ),
        "",
        "NO fuzzy matching is used.",
        (
            "Semantic words such as GROUP, HOLDINGS, INTERNATIONAL, "
            "TECHNOLOGIES, ENERGY, FINANCIAL, SYSTEMS, HEALTH, etc. "
            "are NOT stripped merely to force agreement."
        ),
        "",
        "Production PIT alias intervals created: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_DETERMINISTIC_NAME_STATE_RECONCILIATION_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
