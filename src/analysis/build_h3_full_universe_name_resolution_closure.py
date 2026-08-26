from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-full-universe-name-resolution-closure"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

CANDIDATE_PATH = H3_DIR / "h3_company_query_manifest_candidates.csv"
STAGE3B2_SUMMARY_PATH = H3_DIR / "h3_pit_name_evidence_security_summary.csv"
STAGE3B2_REVIEW_PATH = H3_DIR / "h3_pit_name_evidence_review_queue.csv"
STAGE3C_AUTO_PATH = H3_DIR / "h3_exact_name_transition_resolutions.csv"
STAGE3D_PATH = H3_DIR / "h3_authoritative_exact_name_transition_resolutions.csv"
STAGE3E_RESOLVED_PATH = H3_DIR / "h3_name_state_reconciliation_auto_resolved.csv"
STAGE3F_RESOLVED_PATH = H3_DIR / "h3_authoritative_name_convergence_auto_resolved.csv"
STAGE3G_CLOSED_PATH = H3_DIR / "h3_authoritative_name_state_closeout.csv"

OUT_PATH = H3_DIR / "h3_full_universe_name_resolution_coverage.csv"
UNRESOLVED_PATH = H3_DIR / "h3_full_universe_name_resolution_unresolved.csv"
REPORT_PATH = H3_DIR / "h3_full_universe_name_resolution_closure_report.txt"

EXPECTED_IDENTITIES = 593

def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)

def keyset(df: pd.DataFrame) -> set[str]:
    if df.empty:
        return set()
    return set(df["security_key"].astype(str))

def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in [
        CANDIDATE_PATH,
        STAGE3B2_SUMMARY_PATH,
        STAGE3B2_REVIEW_PATH,
        STAGE3C_AUTO_PATH,
        STAGE3D_PATH,
        STAGE3E_RESOLVED_PATH,
        STAGE3F_RESOLVED_PATH,
        STAGE3G_CLOSED_PATH,
    ]:
        require(path)

    candidate = pd.read_csv(CANDIDATE_PATH, dtype=str, keep_default_na=False)
    summary = pd.read_csv(STAGE3B2_SUMMARY_PATH, dtype=str, keep_default_na=False)
    review = pd.read_csv(STAGE3B2_REVIEW_PATH, dtype=str, keep_default_na=False)
    stage3c = pd.read_csv(STAGE3C_AUTO_PATH, dtype=str, keep_default_na=False)
    stage3d = pd.read_csv(STAGE3D_PATH, dtype=str, keep_default_na=False)
    stage3e = pd.read_csv(STAGE3E_RESOLVED_PATH, dtype=str, keep_default_na=False)
    stage3f = pd.read_csv(STAGE3F_RESOLVED_PATH, dtype=str, keep_default_na=False)
    stage3g = pd.read_csv(STAGE3G_CLOSED_PATH, dtype=str, keep_default_na=False)

    if len(candidate) != EXPECTED_IDENTITIES:
        raise RuntimeError(f"Candidate rows={len(candidate)}, expected 593.")
    if candidate["security_key"].nunique() != EXPECTED_IDENTITIES:
        raise RuntimeError("Duplicate security_key in candidate universe.")

    summary_lookup = summary.set_index("security_key")
    review_lookup = review.set_index("security_key") if not review.empty else None

    s3c = keyset(stage3c)
    s3d = keyset(stage3d)
    s3e = keyset(stage3e)
    s3f = keyset(stage3f)
    s3g = keyset(stage3g)

    rows = []

    for row in candidate.itertuples(index=False):
        sk = str(row.security_key)

        if sk not in summary_lookup.index:
            raise RuntimeError(f"Missing Stage 3B2 summary row for {sk}")

        s = summary_lookup.loc[sk]
        if isinstance(s, pd.DataFrame):
            raise RuntimeError(f"Duplicate Stage 3B2 summary rows for {sk}")

        original_status = str(s["pit_name_evidence_status"])
        original_review_flag = str(s["pit_name_review_flag"])

        layers = []
        if sk in s3c:
            layers.append("STAGE3C_AUTO_EXACT_TRANSITION")
        if sk in s3d:
            layers.append("STAGE3D_AUTHORITATIVE_TRANSITION")
        if sk in s3e:
            layers.append("STAGE3E_DETERMINISTIC_RESOLUTION")
        if sk in s3f:
            layers.append("STAGE3F_AUTHORITATIVE_CONVERGENCE")
        if sk in s3g:
            layers.append("STAGE3G_PRIMARY_SOURCE_CLOSEOUT")

        if sk in s3g:
            final_status = "RESOLVED_STAGE3G_PRIMARY_SOURCE_CLOSEOUT"
            final_layer = "STAGE3G"
        elif sk in s3f:
            final_status = "RESOLVED_STAGE3F_AUTHORITATIVE_CONVERGENCE"
            final_layer = "STAGE3F"
        elif sk in s3e:
            final_status = "RESOLVED_STAGE3E_DETERMINISTIC"
            final_layer = "STAGE3E"
        elif sk in s3d:
            final_status = "RESOLVED_STAGE3D_TRANSITION_EVIDENCE"
            final_layer = "STAGE3D"
        elif sk in s3c:
            final_status = "RESOLVED_STAGE3C_EXACT_ALIAS_EVENT"
            final_layer = "STAGE3C"
        elif original_status == "READY_STABLE_SEC_NPORT_NAME":
            final_status = "RESOLVED_STAGE3B2_STABLE_NPORT_NAME"
            final_layer = "STAGE3B2"
        else:
            final_status = "UNRESOLVED_CARRY_FORWARD_GAP"
            final_layer = "NONE"

        review_reason = ""
        review_priority = ""
        if (
            original_review_flag == "1"
            and review_lookup is not None
            and sk in review_lookup.index
        ):
            r = review_lookup.loc[sk]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            review_reason = str(r.get("pit_name_evidence_status", original_status))
            review_priority = str(r.get("review_priority", ""))

        rows.append({
            "security_key": sk,
            "latest_project_ticker": getattr(row, "latest_project_ticker", ""),
            "canonical_company_name": getattr(row, "canonical_company_name", ""),
            "structural_ambiguity_tier": getattr(row, "structural_ambiguity_tier", ""),
            "stage3b2_original_status": original_status,
            "stage3b2_original_review_flag": original_review_flag,
            "stage3b2_nport_unique_name_count": str(s.get("sec_nport_unique_name_count", "")),
            "stage3b2_nport_raw_names_pipe": str(s.get("sec_nport_raw_names_pipe", "")),
            "stage3b2_candidate_sec_cik": str(s.get("candidate_sec_cik", "")),
            "later_resolution_evidence_layers_pipe": "|".join(layers),
            "final_name_resolution_status": final_status,
            "final_name_resolution_layer": final_layer,
            "original_review_reason": review_reason,
            "original_review_priority": review_priority,
        })

    coverage = pd.DataFrame(rows).sort_values(
        ["final_name_resolution_status", "latest_project_ticker", "security_key"]
    )

    unresolved = coverage[
        coverage["final_name_resolution_status"].eq("UNRESOLVED_CARRY_FORWARD_GAP")
    ].copy()

    priority_map = {
        "REVIEW_NO_MAPPED_SEC_NPORT_NAME": 1,
        "REVIEW_MULTIPLE_SEC_NPORT_NAMES": 1,
        "REVIEW_PROJECT_PERIOD_NAME_EVENT_EVIDENCE": 2,
        "REVIEW_PROJECT_NAME_DIFFERS_FROM_SEC_NPORT": 2,
    }

    if not unresolved.empty:
        unresolved["closure_research_priority"] = (
            unresolved["stage3b2_original_status"].map(priority_map).fillna(9).astype(int)
        )
        unresolved["closure_research_question"] = (
            "This identity was flagged in Stage 3B2 but was not carried into a "
            "later resolution layer. Resolve whether the 2021-2025 public-company "
            "name state is stable, changed, unavailable from NPORT, or requires "
            "additional authoritative evidence before PIT attention aliases."
        )
        unresolved = unresolved.sort_values(
            [
                "closure_research_priority",
                "stage3b2_original_status",
                "latest_project_ticker",
                "security_key",
            ]
        )

    coverage.to_csv(OUT_PATH, index=False)
    unresolved.to_csv(UNRESOLVED_PATH, index=False)

    counts = coverage["final_name_resolution_status"].value_counts().to_dict()
    unresolved_counts = (
        unresolved["stage3b2_original_status"].value_counts().to_dict()
        if not unresolved.empty
        else {}
    )

    lines = [
        "=" * 124,
        "H3 STAGE 3H — FULL-UNIVERSE COMPANY-NAME RESOLUTION CLOSURE GATE",
        "=" * 124,
        f"Canonical security identities: {len(coverage)}",
        f"Identities classified exactly once: {coverage['security_key'].nunique()}",
        f"Resolved identities: {int((coverage['final_name_resolution_status'] != 'UNRESOLVED_CARRY_FORWARD_GAP').sum())}",
        f"Unresolved carry-forward identities: {len(unresolved)}",
        "",
        "Final resolution-layer counts:",
    ]

    for status, count in sorted(counts.items()):
        lines.append(f"  {status}: {count}")

    lines += ["", "Unresolved Stage 3B2 source-status counts:"]
    if unresolved_counts:
        for status, count in sorted(unresolved_counts.items()):
            lines.append(f"  {status}: {count}")
    else:
        lines.append("  NONE: 0")

    lines += [
        "",
        "IMPORTANT:",
        (
            "Stage 3G closed all identities that reached its primary-source "
            "research manifest. Stage 3H independently reconstructs the full "
            "593-security universe to prove that no earlier Stage 3B2 review "
            "identity was accidentally omitted from later carry-forward logic."
        ),
        "",
        (
            "FULL-UNIVERSE NAME-RESEARCH CLOSURE: "
            + ("PASSED" if len(unresolved) == 0 else "BLOCKED")
        ),
        "Production PIT attention aliases created: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_FULL_UNIVERSE_NAME_RESOLUTION_COVERAGE_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")

if __name__ == "__main__":
    main()
