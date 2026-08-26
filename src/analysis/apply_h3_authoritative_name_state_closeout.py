from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-authoritative-name-state-closeout"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

INPUT_PATH = H3_DIR / "h3_authoritative_name_convergence_research_manifest.csv"
REFERENCE_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_authoritative_name_state_resolutions_stage3g.csv"
)

OUT_PATH = H3_DIR / "h3_authoritative_name_state_closeout.csv"
REMAINING_PATH = H3_DIR / "h3_authoritative_name_state_research_remaining.csv"
REPORT_PATH = H3_DIR / "h3_authoritative_name_state_closeout_report.txt"

EXPECTED_ROWS = 34
EXPECTED_XOM_SAMPLE_CIK = "0000034088"
EXPECTED_TJX_SAMPLE_CIK = "0000109198"

ALLOWED_CATEGORIES = {
    "PUBLIC_BRAND_CONTINUITY_HOLDING_COMPANY_REORG",
    "PUBLIC_BRAND_CONTINUITY_INTERNAL_REORG",
    "TRUE_PUBLIC_LEGAL_NAME_TRANSITION_BRAND_CONTINUITY",
    "PREPUBLIC_TRANSACTION_NAME_NOT_ATTENTION_ALIAS",
    "TRUE_PUBLIC_NAME_TRANSITION",
    "JURISDICTION_OR_SOURCE_LABEL_VARIANT",
    "SEC_FORMER_NAME_METADATA_NOT_PUBLIC_PARENT",
    "TRUE_PUBLIC_HOLDING_COMPANY_NAME_TRANSITION",
    "PREWINDOW_FORMER_NAME",
    "PREWINDOW_FORMER_NAME_AND_SOURCE_LABEL_VARIANT",
    "TRUE_PUBLIC_NAME_TRANSITION_DUAL_DATE",
    "SEC_CONFORMED_OR_DISPLAY_NAME_VARIANT",
    "SEC_CONFORMED_WORD_ORDER_VARIANT",
    "LEGAL_FORM_PUNCTUATION_VARIANT",
    "POST_SAMPLE_BRAND_TICKER_CHANGE_NOT_PIT",
    "JURISDICTION_LABEL_VARIANT_PUBLIC_SPIN",
    "MISSING_CIK_MAPPING_RESOLVED",
    "POST_SAMPLE_HOLDING_COMPANY_REORG_CURRENT_REFERENCE_NOT_PIT",
}


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (INPUT_PATH, REFERENCE_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    source = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False)
    ref = pd.read_csv(REFERENCE_PATH, dtype=str, keep_default_na=False)

    if len(source) != EXPECTED_ROWS:
        raise RuntimeError(
            f"Stage 3F research rows={len(source)}, expected {EXPECTED_ROWS}."
        )
    if len(ref) != EXPECTED_ROWS:
        raise RuntimeError(
            f"Stage 3G reference rows={len(ref)}, expected {EXPECTED_ROWS}."
        )
    if source["security_key"].duplicated().any():
        raise RuntimeError("Duplicate security_key in Stage 3F research manifest.")
    if ref["security_key"].duplicated().any():
        raise RuntimeError("Duplicate security_key in Stage 3G reference ledger.")

    if set(source["security_key"]) != set(ref["security_key"]):
        missing = sorted(set(source["security_key"]) - set(ref["security_key"]))
        extra = sorted(set(ref["security_key"]) - set(source["security_key"]))
        raise RuntimeError(
            f"Stage 3G key mismatch. Missing={missing}; extra={extra}"
        )

    if not set(ref["resolution_category"]).issubset(ALLOWED_CATEGORIES):
        bad = sorted(set(ref["resolution_category"]) - ALLOWED_CATEGORIES)
        raise RuntimeError(f"Unexpected resolution category: {bad}")

    # Preserve the locally generated Stage 3F row as the controlling universe,
    # then attach only the authoritative closeout fields from the reference ledger.
    reference_only_cols = [
        "security_key",
        "resolution_category",
        "sample_authoritative_company_name",
        "sample_authoritative_cik",
        "predecessor_public_company_name",
        "predecessor_public_cik",
        "legal_effective_date",
        "public_effective_date",
        "post_sample_effective_date",
        "excluded_name",
        "excluded_name_reason",
        "source_type",
        "source_url",
        "evidence_note",
        "production_implication",
        "stage3g_resolution_status",
        "resolution_confidence",
    ]

    merged = source.merge(
        ref[reference_only_cols],
        on="security_key",
        how="left",
        validate="one_to_one",
    )

    if merged["stage3g_resolution_status"].ne("CLOSED_AUTHORITATIVE").any():
        raise RuntimeError("At least one Stage 3G identity is not closed.")

    # Critical point-in-time corrections.
    xom = merged.loc[merged["security_key"].eq("XOM")].iloc[0]
    if xom["sample_authoritative_cik"] != EXPECTED_XOM_SAMPLE_CIK:
        raise RuntimeError("XOM sample CIK correction is missing.")

    tjx = merged.loc[merged["security_key"].eq("TJX")].iloc[0]
    if tjx["sample_authoritative_cik"] != EXPECTED_TJX_SAMPLE_CIK:
        raise RuntimeError("TJX CIK resolution is missing.")

    merged = merged.sort_values(["security_key"]).reset_index(drop=True)
    merged.to_csv(OUT_PATH, index=False)

    # Stage 3G is intended to close all 34 primary-source cases.
    remaining = merged.iloc[0:0].copy()
    remaining.to_csv(REMAINING_PATH, index=False)

    category_counts = merged["resolution_category"].value_counts().to_dict()

    lines = [
        "=" * 124,
        "H3 STAGE 3G — AUTHORITATIVE NAME-STATE CLOSEOUT",
        "=" * 124,
        f"Input Stage 3F primary-source research identities: {len(source)}",
        f"Authoritatively closed identities: {len(merged)}",
        f"Remaining external name-state research identities: {len(remaining)}",
        "",
        "Category counts:",
    ]

    for category, count in sorted(category_counts.items()):
        lines.append(f"  {category}: {count}")

    lines += [
        "",
        "CRITICAL PIT CORRECTIONS:",
        (
            "  XOM: 2021-2025 public issuer is Exxon Mobil Corporation, "
            "CIK 0000034088. ExxonMobil Holdings Corporation / CIK "
            "0002115436 is a post-sample 2026 successor parent."
        ),
        (
            "  TJX: Stage 3F missing CIK is resolved to official SEC "
            "CIK 0000109198."
        ),
        (
            "  MRSH: the Marsh brand / MRSH ticker change is effective "
            "2026-01-14 and must not be backcast into the 2021-2025 sample."
        ),
        "",
        "NAME-STATE CONTROLS:",
        (
            "  Pre-public transaction shell names are retained as provenance "
            "but explicitly excluded from production attention aliases."
        ),
        (
            "  Internal holding-company reorganizations with continuous "
            "public branding are distinguished from genuine public-name changes."
        ),
        (
            "  Legal dates and public/trading dates are stored separately "
            "when authoritative sources distinguish them."
        ),
        "",
        "Production PIT GDELT alias intervals created: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_AUTHORITATIVE_NAME_STATE_CLOSEOUT_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
