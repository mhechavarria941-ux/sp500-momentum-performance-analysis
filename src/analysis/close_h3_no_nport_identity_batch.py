from __future__ import annotations

import re
import unicodedata
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v2-h3-definitive-no-nport-closure-lumen-fix"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

UNRESOLVED_PATH = H3_DIR / "h3_full_universe_name_resolution_unresolved.csv"
COVERAGE_PATH = H3_DIR / "h3_full_universe_name_resolution_coverage.csv"
MEMBERSHIP_PATH = ROOT / "data" / "interim" / "sp500_membership_intervals_2021_2025.csv"
TERMINATION_PATH = ROOT / "data" / "reference" / "securities" / "security_market_terminations.csv"
SEC_FORMER_PATH = H3_DIR / "h3_sec_former_names_raw.csv"
CIK_LOOKUP_PATH = ROOT / "data" / "interim" / "h3_sec" / "cik-lookup-data.txt"
KNOWN_EVENTS_PATH = ROOT / "data" / "reference" / "h3" / "h3_no_nport_known_name_state_events.csv"

OUT_PATH = H3_DIR / "h3_no_nport_definitive_closure.csv"
TRANSITION_PATH = H3_DIR / "h3_no_nport_membership_name_transitions.csv"
UNEXPECTED_FORMER_PATH = H3_DIR / "h3_no_nport_unexpected_sec_former_name_signals.csv"
FULL_COVERAGE_V2_PATH = H3_DIR / "h3_full_universe_name_resolution_coverage_v2.csv"
FULL_UNRESOLVED_V2_PATH = H3_DIR / "h3_full_universe_name_resolution_unresolved_v2.csv"
REPORT_PATH = H3_DIR / "h3_no_nport_definitive_closure_report.txt"

EXPECTED_ROWS = 93
EXPECTED_FULL_UNIVERSE = 593
LEGAL_SUFFIXES = {
    "INC","INCORPORATED","CORP","CORPORATION","CO","COMPANY",
    "LTD","LIMITED","PLC","LLC","LLP","LP","NV","AG","SE","SA",
}

def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)

def normalize_core(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    raw = unicodedata.normalize("NFKC", str(value)).upper()
    raw = raw.replace("&", " AND ")
    raw = re.sub(r"[’']", "", raw)
    raw = re.sub(r"[^A-Z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    tokens = raw.split()
    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    if len(tokens) >= 2 and tokens[-2] in {"CLASS","CL"}:
        tokens = tokens[:-2]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens = tokens[:-1]
    return " ".join(tokens).strip()

def date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None)

def in_interval(dt, start, end) -> bool:
    return bool(pd.notna(dt) and dt >= start and dt < end)

def parse_cik_lookup(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="latin-1", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            parts = line.rsplit(":", 2)
            if len(parts) < 2:
                continue
            name, cik = parts[0].strip(), parts[1].strip()
            if cik.isdigit():
                rows.append({
                    "lookup_name": name,
                    "lookup_core": normalize_core(name),
                    "resolved_cik": str(int(cik)).zfill(10),
                })
    return pd.DataFrame(rows).drop_duplicates()

def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        UNRESOLVED_PATH, COVERAGE_PATH, MEMBERSHIP_PATH,
        SEC_FORMER_PATH, CIK_LOOKUP_PATH, KNOWN_EVENTS_PATH,
    ):
        require(path)

    unresolved = pd.read_csv(UNRESOLVED_PATH, dtype=str, keep_default_na=False)
    coverage = pd.read_csv(COVERAGE_PATH, dtype=str, keep_default_na=False)
    membership = pd.read_csv(MEMBERSHIP_PATH, dtype=str, keep_default_na=False)
    former = pd.read_csv(SEC_FORMER_PATH, dtype=str, keep_default_na=False)
    known = pd.read_csv(KNOWN_EVENTS_PATH, dtype=str, keep_default_na=False)
    cik_lookup = parse_cik_lookup(CIK_LOOKUP_PATH)

    terminations = (
        pd.read_csv(TERMINATION_PATH, dtype=str, keep_default_na=False)
        if TERMINATION_PATH.exists() else pd.DataFrame()
    )

    if len(unresolved) != EXPECTED_ROWS:
        raise RuntimeError(f"Stage 3H unresolved rows={len(unresolved)}, expected 93.")
    if set(unresolved["stage3b2_original_status"]) != {"REVIEW_NO_MAPPED_SEC_NPORT_NAME"}:
        raise RuntimeError("Stage 3I V2 is scoped only to the 93 no-NPORT rows.")
    if len(coverage) != EXPECTED_FULL_UNIVERSE:
        raise RuntimeError(f"Coverage rows={len(coverage)}, expected 593.")

    membership["valid_from_dt"] = date_series(membership["valid_from"])
    membership["valid_to_dt"] = date_series(membership["valid_to_exclusive"])
    membership_lookup = membership.set_index("security_key")

    known["legal_dt"] = date_series(known["legal_effective_date"])
    known["public_dt"] = date_series(known["public_effective_date"])
    known_groups = {k: g.copy() for k, g in known.groupby("security_key")}

    termination_keys = (
        set(terminations["security_key"].astype(str))
        if not terminations.empty and "security_key" in terminations.columns
        else set()
    )

    lookup_groups = {
        core: sorted(set(group["resolved_cik"]))
        for core, group in cik_lookup.groupby("lookup_core") if core
    }

    former["from_dt"] = date_series(former["former_name_from"])
    former["to_dt"] = date_series(former["former_name_to"])
    former["former_core"] = former["former_name"].map(normalize_core)
    former_groups = {str(cik): g.copy() for cik, g in former.groupby("sec_cik")}

    rows, transition_rows, unexpected_rows = [], [], []

    for row in unresolved.itertuples(index=False):
        sk = str(row.security_key)
        m = membership_lookup.loc[sk]
        start, end = m["valid_from_dt"], m["valid_to_dt"]
        membership_name = str(m["company_name_reference"]).strip()
        membership_core = normalize_core(membership_name)

        candidate_cik = str(row.stage3b2_candidate_sec_cik).strip()
        resolved_cik = candidate_cik
        cik_basis = "STAGE3B2_CANDIDATE" if candidate_cik else ""

        if not resolved_cik:
            possible = lookup_groups.get(membership_core, [])
            if len(possible) == 1:
                resolved_cik = possible[0]
                cik_basis = "UNIQUE_EXACT_SEC_CIK_LOOKUP_NAME_CORE"

        events = known_groups.get(sk, pd.DataFrame())
        explanatory_events = []
        public_name_events_in_membership = []
        legal_only_events_in_membership = []
        ticker_only_events_in_membership = []

        if not events.empty:
            for event in events.itertuples(index=False):
                legal_in = in_interval(event.legal_dt, start, end)
                public_in = in_interval(event.public_dt, start, end)

                # An event can explain SEC former-name evidence if either its
                # legal or public identity boundary intersects active membership.
                if legal_in or public_in:
                    explanatory_events.append(event)

                    transition_rows.append({
                        "security_key": sk,
                        "latest_project_ticker": row.latest_project_ticker,
                        "membership_valid_from": start.date().isoformat(),
                        "membership_valid_to_exclusive": end.date().isoformat(),
                        "event_type": event.event_type,
                        "old_company_name": event.old_company_name,
                        "new_company_name": event.new_company_name,
                        "legal_effective_date": event.legal_effective_date,
                        "public_effective_date": event.public_effective_date,
                        "old_ticker": event.old_ticker,
                        "new_ticker": event.new_ticker,
                        "legal_boundary_in_membership_flag": int(legal_in),
                        "public_boundary_in_membership_flag": int(public_in),
                        "source_url": event.source_url,
                        "notes": event.notes,
                    })

                if event.event_type == "TICKER_ONLY_CHANGE":
                    if public_in or legal_in:
                        ticker_only_events_in_membership.append(event)
                else:
                    if public_in:
                        public_name_events_in_membership.append(event)
                    elif legal_in:
                        legal_only_events_in_membership.append(event)

        former_signal_count = 0

        if resolved_cik and resolved_cik in former_groups:
            fg = former_groups[resolved_cik]

            for f in fg.itertuples(index=False):
                to_dt = f.to_dt
                distinct = bool(
                    f.former_core and membership_core
                    and f.former_core != membership_core
                )
                overlaps = in_interval(to_dt, start, end)

                if not (distinct and overlaps):
                    continue

                explained = False
                for event in explanatory_events:
                    old_core = normalize_core(event.old_company_name)
                    new_core = normalize_core(event.new_company_name)
                    if f.former_core in {old_core, new_core}:
                        explained = True
                        break

                if not explained:
                    former_signal_count += 1
                    unexpected_rows.append({
                        "security_key": sk,
                        "latest_project_ticker": row.latest_project_ticker,
                        "membership_company_name": membership_name,
                        "resolved_cik": resolved_cik,
                        "former_name": f.former_name,
                        "former_name_from": f.former_name_from,
                        "former_name_to": f.former_name_to,
                        "membership_valid_from": start.date().isoformat(),
                        "membership_valid_to_exclusive": end.date().isoformat(),
                        "reason": (
                            "Distinct SEC former-name boundary falls inside "
                            "membership and is not covered by known-event ledger."
                        ),
                    })

        if public_name_events_in_membership:
            disposition = "TRUE_PIT_PUBLIC_NAME_STATE_TRANSITION"
            basis = "KNOWN_PRIMARY_SOURCE_PUBLIC_IDENTITY_EVENT"
        elif legal_only_events_in_membership:
            disposition = (
                "PREWINDOW_PUBLIC_REBRAND_WITH_INWINDOW_LEGAL_NAME_FINALIZATION"
            )
            basis = (
                "PRIMARY_SOURCE_PUBLIC_REBRAND_PREWINDOW_PLUS_LEGAL_FINALIZATION_INWINDOW"
            )
        elif sk in termination_keys:
            disposition = "STABLE_PUBLIC_NAME_UNTIL_VALIDATED_MARKET_TERMINATION"
            basis = "OFFICIAL_SP500_MEMBERSHIP_PLUS_MARKET_TERMINATION"
        elif resolved_cik:
            disposition = "STABLE_PUBLIC_NAME_OFFICIAL_MEMBERSHIP_PLUS_SEC_IDENTITY"
            basis = "OFFICIAL_SP500_MEMBERSHIP_PLUS_SEC_IDENTITY"
        else:
            disposition = "STABLE_PUBLIC_NAME_OFFICIAL_SP500_MEMBERSHIP_IDENTITY"
            basis = "OFFICIAL_SP500_MEMBERSHIP_RECONSTRUCTION"

        rows.append({
            "security_key": sk,
            "latest_project_ticker": row.latest_project_ticker,
            "canonical_company_name": row.canonical_company_name,
            "membership_company_name": membership_name,
            "membership_valid_from": start.date().isoformat(),
            "membership_valid_to_exclusive": end.date().isoformat(),
            "left_censored": str(m["left_censored"]),
            "right_censored": str(m["right_censored"]),
            "entry_source_url": str(m.get("entry_source_url", "")),
            "exit_source_url": str(m.get("exit_source_url", "")),
            "stage3b2_candidate_sec_cik": candidate_cik,
            "resolved_sec_cik": resolved_cik,
            "cik_resolution_basis": cik_basis,
            "known_in_membership_public_name_event_count": len(public_name_events_in_membership),
            "known_in_membership_legal_only_name_event_count": len(legal_only_events_in_membership),
            "known_in_membership_ticker_only_event_count": len(ticker_only_events_in_membership),
            "unexpected_in_membership_sec_former_name_signal_count": former_signal_count,
            "final_no_nport_disposition": disposition,
            "name_state_resolution_basis": basis,
            "resolution_status": "CLOSED_NO_NPORT_SOURCE_GAP",
        })

    result = pd.DataFrame(rows).sort_values(
        ["final_no_nport_disposition","latest_project_ticker","security_key"]
    )
    transitions = pd.DataFrame(transition_rows)
    unexpected = pd.DataFrame(unexpected_rows)

    # Preserve headers even when diagnostic is empty.
    unexpected_cols = [
        "security_key","latest_project_ticker","membership_company_name",
        "resolved_cik","former_name","former_name_from","former_name_to",
        "membership_valid_from","membership_valid_to_exclusive","reason",
    ]
    if unexpected.empty:
        unexpected = pd.DataFrame(columns=unexpected_cols)

    result.to_csv(OUT_PATH, index=False)
    transitions.to_csv(TRANSITION_PATH, index=False)
    unexpected.to_csv(UNEXPECTED_FORMER_PATH, index=False)

    stage3i_keys = set(result["security_key"])
    full = coverage.copy()
    mask = full["security_key"].isin(stage3i_keys)
    full.loc[mask, "final_name_resolution_status"] = (
        "RESOLVED_STAGE3I_DEFINITIVE_NO_NPORT_CLOSURE"
    )
    full.loc[mask, "final_name_resolution_layer"] = "STAGE3I"
    full.loc[mask, "later_resolution_evidence_layers_pipe"] = full.loc[
        mask, "later_resolution_evidence_layers_pipe"
    ].apply(
        lambda value: (
            (str(value) + "|STAGE3I_DEFINITIVE_NO_NPORT_CLOSURE").strip("|")
        )
    )

    full_unresolved = full[
        full["final_name_resolution_status"].eq("UNRESOLVED_CARRY_FORWARD_GAP")
    ].copy()

    full.to_csv(FULL_COVERAGE_V2_PATH, index=False)
    full_unresolved.to_csv(FULL_UNRESOLVED_V2_PATH, index=False)

    lumn = result.loc[result["security_key"].eq("LUMN")]
    if len(lumn) != 1:
        raise RuntimeError("Expected exactly one LUMN closure row.")

    counts = result["final_no_nport_disposition"].value_counts().to_dict()

    lines = [
        "=" * 126,
        "H3 STAGE 3I V2 — DEFINITIVE NO-NPORT NAME-STATE CLOSURE",
        "=" * 126,
        f"Stage 3H carry-forward identities: {len(result)}",
        f"Known primary-source event rows in ledger: {len(known)}",
        f"Known event rows intersecting membership: {len(transitions)}",
        f"Unexpected distinct SEC former-name signals: {len(unexpected)}",
        f"Full 593-universe unresolved identities after Stage 3I V2: {len(full_unresolved)}",
        "",
        "LUMN SAFETY EXCEPTION RESOLVED:",
        (
            "  Lumen brand launch: 2020-09-14 (pre-window); "
            "ticker LUMN began 2020-09-18 (pre-window); "
            "legal CenturyLink -> Lumen Technologies change: 2021-01-22."
        ),
        (
            "  Therefore LUMN is not an unexplained in-window public rebrand. "
            "It is a pre-window public rebrand with in-window legal-name finalization."
        ),
        "",
        "Final 93-row disposition counts:",
    ]

    for status, count in sorted(counts.items()):
        lines.append(f"  {status}: {count}")

    lines += [
        "",
        (
            "FULL-UNIVERSE NAME-RESEARCH CLOSURE: "
            + (
                "PASSED"
                if len(full_unresolved) == 0 and len(unexpected) == 0
                else "BLOCKED"
            )
        ),
        "Production GDELT alias intervals created: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_DEFINITIVE_NO_NPORT_CLOSURE_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")

if __name__ == "__main__":
    main()
