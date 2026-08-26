from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-authoritative-name-convergence"

H3_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

INPUT_PATH = H3_DIR / "h3_name_state_reconciliation_research_manifest.csv"
SEC_FORMER_PATH = H3_DIR / "h3_sec_former_names_raw.csv"

OUT_PATH = H3_DIR / "h3_authoritative_name_convergence_classification.csv"
RESOLVED_PATH = H3_DIR / "h3_authoritative_name_convergence_auto_resolved.csv"
RESEARCH_PATH = H3_DIR / "h3_authoritative_name_convergence_research_manifest.csv"
FORMER_DETAIL_PATH = H3_DIR / "h3_authoritative_name_convergence_former_name_detail.csv"
REPORT_PATH = H3_DIR / "h3_authoritative_name_convergence_report.txt"

EXPECTED_INPUT_ROWS = 118

PROJECT_START = pd.Timestamp("2021-01-01")
PROJECT_END_EXCLUSIVE = pd.Timestamp("2026-01-01")

LEGAL_SUFFIXES = {
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "LTD",
    "LIMITED",
    "PLC",
    "LLC",
    "LLP",
    "LP",
    "NV",
    "AG",
    "SE",
    "SA",
}

SLASH_JURISDICTIONS = {
    "DE",
    "MD",
    "MO",
    "MN",
    "NY",
    "OH",
    "NJ",
    "PA",
    "VA",
    "CA",
    "TX",
    "NEW",
}


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def normalize_registry_core(value: object) -> str:
    """
    Conservative normalization for comparing authoritative SEC/NPORT issuer names.

    Allowed changes:
    - case/punctuation;
    - ampersand -> AND;
    - leading/trailing THE;
    - explicit security-class labels;
    - EDGAR slash-state qualifiers such as /DE/ or /MD/;
    - trailing legal forms (Inc., Corp., Co., PLC, Ltd., N.V., etc.).

    Not allowed:
    - fuzzy matching;
    - word-order changes;
    - abbreviation expansion such as INTL -> INTERNATIONAL;
    - semantic word removal such as GROUP/HOLDINGS/ENERGY/TECHNOLOGIES.
    """
    if value is None or pd.isna(value):
        return ""

    raw = unicodedata.normalize("NFKC", str(value)).upper()

    # Remove explicit EDGAR slash jurisdiction annotations before punctuation
    # is stripped, so state codes are not mistaken for semantic company words.
    raw = re.sub(
        r"/\s*(?:DE|MD|MO|MN|NY|OH|NJ|PA|VA|CA|TX|NEW)\s*/",
        " ",
        raw,
    )

    raw = raw.replace("&", " AND ")
    raw = re.sub(r"[’']", "", raw)
    raw = re.sub(r"[^A-Z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    tokens = raw.split()

    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    if tokens and tokens[-1] == "THE":
        tokens = tokens[:-1]

    # Remove trailing security-class presentation.
    if len(tokens) >= 2 and tokens[-2] in {"CLASS", "CL"}:
        tokens = tokens[:-2]

    # Remove trailing legal forms repeatedly.
    changed = True
    while tokens and changed:
        changed = False

        if tokens[-1] in LEGAL_SUFFIXES:
            tokens = tokens[:-1]
            changed = True
            continue

        # Some source strings can retain an unmarked jurisdiction after a legal
        # form has already been normalized away. Only remove it when the
        # original raw string visibly used slash-state notation.
        if (
            tokens
            and tokens[-1] in SLASH_JURISDICTIONS
            and re.search(
                r"/\s*" + re.escape(tokens[-1]) + r"\s*/",
                str(value).upper(),
            )
        ):
            tokens = tokens[:-1]
            changed = True

    return " ".join(tokens).strip()


def normalize_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)


def project_period_former_names(former: pd.DataFrame) -> pd.DataFrame:
    if former.empty:
        return former.copy()

    work = former.copy()
    work["former_from_dt"] = normalize_date_series(
        work["former_name_from"]
    )
    work["former_to_dt"] = normalize_date_series(
        work["former_name_to"]
    )

    # Missing boundaries remain uncertain and therefore cannot be used to
    # auto-resolve a former-name case.
    work["date_complete_flag"] = (
        work["former_from_dt"].notna()
        & work["former_to_dt"].notna()
    ).astype(int)

    work["project_overlap_flag"] = (
        (
            work["former_from_dt"].isna()
            | (work["former_from_dt"] < PROJECT_END_EXCLUSIVE)
        )
        & (
            work["former_to_dt"].isna()
            | (work["former_to_dt"] >= PROJECT_START)
        )
    ).astype(int)

    work["former_name_registry_core"] = (
        work["former_name"].map(normalize_registry_core)
    )

    return work[
        work["project_overlap_flag"].eq(1)
    ].copy()


def pipe_parts(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [
        part.strip()
        for part in str(value).split("|")
        if part.strip()
    ]


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (INPUT_PATH, SEC_FORMER_PATH):
        require(path)

    input_df = pd.read_csv(
        INPUT_PATH,
        dtype=str,
        keep_default_na=False,
    )
    former = pd.read_csv(
        SEC_FORMER_PATH,
        dtype=str,
        keep_default_na=False,
    )

    if len(input_df) != EXPECTED_INPUT_ROWS:
        raise RuntimeError(
            f"Stage 3E research rows={len(input_df)}, expected 118."
        )

    if input_df["security_key"].duplicated().any():
        raise RuntimeError(
            "Expected one Stage 3E research row per security_key."
        )

    former_project = project_period_former_names(former)

    former_groups = {
        str(cik): group.copy()
        for cik, group in former_project.groupby("sec_cik")
    }

    detail_rows = []
    classification_rows = []

    for row in input_df.itertuples(index=False):
        security_key = str(row.security_key)
        cik = str(row.candidate_sec_cik).strip()

        sec_core = normalize_registry_core(
            row.sec_current_name
        )

        nport_raw_names = pipe_parts(
            row.nport_raw_names_pipe
        )
        nport_cores = sorted(
            {
                normalize_registry_core(name)
                for name in nport_raw_names
                if normalize_registry_core(name)
            }
        )

        single_nport_core = (
            nport_cores[0]
            if len(nport_cores) == 1
            else ""
        )

        sec_nport_agreement = int(
            bool(
                sec_core
                and single_nport_core
                and sec_core == single_nport_core
            )
        )

        former_group = (
            former_groups.get(cik, pd.DataFrame())
            if cik
            else pd.DataFrame()
        )

        former_count = len(former_group)
        former_date_complete = int(
            bool(
                not former_group.empty
                and former_group[
                    "date_complete_flag"
                ].eq(1).all()
            )
        ) if former_count else 1

        former_cores = sorted(
            {
                str(value)
                for value in (
                    former_group[
                        "former_name_registry_core"
                    ].tolist()
                    if former_count
                    else []
                )
                if str(value)
            }
        )

        all_former_same_as_authoritative = int(
            bool(
                former_count
                and sec_nport_agreement
                and former_date_complete
                and former_cores
                and set(former_cores) == {single_nport_core}
            )
        )

        if former_count:
            for former_row in former_group.itertuples(index=False):
                detail_rows.append(
                    {
                        "security_key": security_key,
                        "latest_project_ticker": row.latest_project_ticker,
                        "candidate_sec_cik": cik,
                        "sec_current_name": row.sec_current_name,
                        "authoritative_registry_core": (
                            single_nport_core
                            if sec_nport_agreement
                            else ""
                        ),
                        "former_name": former_row.former_name,
                        "former_name_registry_core": (
                            former_row.former_name_registry_core
                        ),
                        "former_name_from": former_row.former_name_from,
                        "former_name_to": former_row.former_name_to,
                        "date_complete_flag": former_row.date_complete_flag,
                        "same_core_as_authoritative_flag": int(
                            bool(
                                sec_nport_agreement
                                and former_row.former_name_registry_core
                                == single_nport_core
                            )
                        ),
                    }
                )

        original_status = str(
            row.reconciliation_status
        )

        if (
            original_status
            == "RESEARCH_PROJECT_VS_NPORT_NAME_CORE_CONFLICT"
            and sec_nport_agreement
        ):
            status = (
                "RESOLVED_AUTHORITATIVE_SEC_NPORT_AGREEMENT_"
                "PROJECT_REFERENCE_PRESENTATION_DIFFERENCE"
            )
            rationale = (
                "SEC current filer name and the single historical NPORT issuer "
                "name agree under conservative registry normalization. The "
                "project company_name_reference is therefore treated as a "
                "provider/presentation label rather than the authoritative "
                "GDELT issuer-name source."
            )

        elif (
            original_status
            == "RESEARCH_PROJECT_PERIOD_SEC_FORMER_NAME_EVIDENCE"
            and all_former_same_as_authoritative
        ):
            status = (
                "RESOLVED_SEC_FORMER_NAMES_REGISTRY_STYLE_EQUIVALENT"
            )
            rationale = (
                "SEC current filer name and the single historical NPORT issuer "
                "name agree, and every project-overlapping SEC former-name "
                "record has the same conservative registry core with complete "
                "date metadata. Former-name evidence is therefore a registry/"
                "legal-style presentation difference rather than a substantive "
                "issuer-name state change."
            )

        elif (
            original_status
            == "RESEARCH_PROJECT_PERIOD_SEC_FORMER_NAME_EVIDENCE"
            and former_count
            and not former_date_complete
        ):
            status = (
                "RESEARCH_SEC_FORMER_NAME_DATE_BOUNDARY_INCOMPLETE"
            )
            rationale = (
                "At least one project-overlapping SEC former-name record has "
                "an incomplete date boundary; no automatic resolution allowed."
            )

        elif (
            original_status
            == "RESEARCH_PROJECT_PERIOD_SEC_FORMER_NAME_EVIDENCE"
            and former_count
            and not all_former_same_as_authoritative
        ):
            status = (
                "RESEARCH_SUBSTANTIVE_OR_DISTINCT_SEC_FORMER_NAME"
            )
            rationale = (
                "At least one project-overlapping SEC former-name registry "
                "core differs from the authoritative SEC/NPORT current core "
                "or SEC/NPORT current names do not agree. Primary-source "
                "historical-name review is still required."
            )

        elif (
            original_status
            == "RESEARCH_MULTIPLE_UNEXPLAINED_NPORT_STATES"
        ):
            status = (
                "RESEARCH_MULTIPLE_UNEXPLAINED_NPORT_STATES"
            )
            rationale = (
                "Multiple authoritative historical NPORT issuer-name states "
                "remain and must be resolved from primary evidence."
            )

        else:
            status = (
                "RESEARCH_AUTHORITATIVE_NAME_CONVERGENCE_NOT_ESTABLISHED"
            )
            rationale = (
                "Frozen automatic authoritative-convergence rules were not met."
            )

        classification_rows.append(
            {
                "security_key": security_key,
                "latest_project_ticker": row.latest_project_ticker,
                "canonical_company_name": row.canonical_company_name,
                "candidate_sec_cik": cik,
                "original_reconciliation_status": original_status,
                "sec_current_name": row.sec_current_name,
                "sec_current_registry_core": sec_core,
                "nport_raw_names_pipe": row.nport_raw_names_pipe,
                "nport_registry_cores_pipe": "|".join(nport_cores),
                "nport_registry_core_count": len(nport_cores),
                "sec_nport_authoritative_agreement_flag": sec_nport_agreement,
                "project_period_sec_former_name_rows": former_count,
                "former_name_date_complete_flag": former_date_complete,
                "former_name_registry_cores_pipe": "|".join(former_cores),
                "all_former_names_same_authoritative_core_flag": (
                    all_former_same_as_authoritative
                ),
                "stage3f_status": status,
                "stage3f_rationale": rationale,
            }
        )

    result = pd.DataFrame(classification_rows)

    resolved = result[
        result["stage3f_status"].str.startswith(
            "RESOLVED_"
        )
    ].copy()

    research = result[
        result["stage3f_status"].str.startswith(
            "RESEARCH_"
        )
    ].copy()

    if len(resolved) + len(research) != EXPECTED_INPUT_ROWS:
        raise RuntimeError(
            "Stage 3F result does not partition all 118 identities."
        )

    detail = pd.DataFrame(
        detail_rows,
        columns=[
            "security_key",
            "latest_project_ticker",
            "candidate_sec_cik",
            "sec_current_name",
            "authoritative_registry_core",
            "former_name",
            "former_name_registry_core",
            "former_name_from",
            "former_name_to",
            "date_complete_flag",
            "same_core_as_authoritative_flag",
        ],
    )

    priority = {
        "RESEARCH_MULTIPLE_UNEXPLAINED_NPORT_STATES": 1,
        "RESEARCH_SUBSTANTIVE_OR_DISTINCT_SEC_FORMER_NAME": 1,
        "RESEARCH_SEC_FORMER_NAME_DATE_BOUNDARY_INCOMPLETE": 1,
        "RESEARCH_AUTHORITATIVE_NAME_CONVERGENCE_NOT_ESTABLISHED": 2,
    }

    research["research_priority"] = (
        research["stage3f_status"]
        .map(priority)
        .fillna(9)
        .astype(int)
    )
    research["required_source_standard"] = (
        "SEC filing/SEC exhibit/official company investor-relations "
        "announcement or equivalent primary authoritative source"
    )
    research["research_question"] = (
        "Resolve the issuer's valid public/company name state(s) and any "
        "project-period effective date(s) required for a high-precision "
        "GDELT attention alias."
    )

    result = result.sort_values(
        [
            "stage3f_status",
            "latest_project_ticker",
            "security_key",
        ]
    )
    resolved = resolved.sort_values(
        [
            "stage3f_status",
            "latest_project_ticker",
            "security_key",
        ]
    )
    research = research.sort_values(
        [
            "research_priority",
            "stage3f_status",
            "latest_project_ticker",
            "security_key",
        ]
    )

    result.to_csv(OUT_PATH, index=False)
    resolved.to_csv(RESOLVED_PATH, index=False)
    research.to_csv(RESEARCH_PATH, index=False)
    detail.to_csv(FORMER_DETAIL_PATH, index=False)

    counts = (
        result["stage3f_status"]
        .value_counts()
        .to_dict()
    )

    lines = [
        "=" * 124,
        "H3 STAGE 3F — AUTHORITATIVE NAME CONVERGENCE",
        "=" * 124,
        f"Input Stage 3E research identities: {len(result)}",
        f"Automatically reconciled in Stage 3F: {len(resolved)}",
        f"Remaining primary-source research identities: {len(research)}",
        f"Project-overlapping SEC former-name detail rows inspected: {len(detail)}",
        "",
        "Status counts:",
    ]

    for status, count in sorted(counts.items()):
        lines.append(f"  {status}: {count}")

    lines += [
        "",
        "KEY METHODOLOGICAL CORRECTION:",
        (
            "A provider-style project company_name_reference does not have "
            "to equal the historical attention alias when authoritative SEC "
            "current identity and SEC-filed NPORT historical issuer name agree."
        ),
        (
            "Likewise, SEC former-name metadata does not force manual review "
            "when every project-overlapping former-name record collapses to "
            "the same conservative registry core as the authoritative issuer "
            "and has complete date boundaries."
        ),
        "",
        "NO fuzzy matching is used.",
        "NO semantic company words are stripped to force agreement.",
        "Production PIT alias intervals created: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_AUTHORITATIVE_NAME_CONVERGENCE_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(text, end="")


if __name__ == "__main__":
    main()
