from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-h3-gdelt-gkg-pilot-audit"

MANIFEST_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_gkg_pilot_query_manifest.csv"
)
ANCHORS_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_gkg_pilot_anchor_windows.csv"
)

OUT_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
COVERAGE_PATH = OUT_DIR / "h3_gdelt_gkg_pilot_coverage.csv"
VARIANT_PATH = OUT_DIR / "h3_gdelt_gkg_pilot_org_variants.csv"
COST_PATH = OUT_DIR / "h3_gdelt_gkg_pilot_cost_estimate.json"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_gdelt_gkg_pilot_feasibility_audit.txt"
)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        MANIFEST_PATH,
        ANCHORS_PATH,
        COVERAGE_PATH,
        VARIANT_PATH,
        COST_PATH,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Pilot execution outputs are missing: "
            + ", ".join(missing)
        )

    manifest = pd.read_csv(MANIFEST_PATH)
    anchors = pd.read_csv(ANCHORS_PATH)
    coverage = pd.read_csv(COVERAGE_PATH)
    variants = pd.read_csv(VARIANT_PATH)
    cost = json.loads(COST_PATH.read_text(encoding="utf-8"))

    failures = []
    passes = 0

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passes
        if condition:
            lines.append("PASS: " + success)
            passes += 1
        else:
            lines.append("FAIL: " + failure)
            failures.append(failure)

    lines = [
        "=" * 106,
        "H3 ATTENTION FEASIBILITY — GDELT GKG PILOT AUDIT",
        "=" * 106,
        "Scope: source coverage / query ambiguity only",
        "Return or H3 outcome analysis permitted: NO",
        "",
    ]

    expected_rows = len(manifest) * len(anchors)

    check(
        len(coverage) == expected_rows,
        f"Coverage output contains {expected_rows} ticker-anchor rows.",
        f"Coverage rows={len(coverage)}, expected {expected_rows}.",
    )

    check(
        set(coverage["anchor_id"]) == set(anchors["anchor_id"]),
        "All five frozen historical anchor windows are present.",
        "Historical anchor coverage is incomplete.",
    )

    check(
        set(coverage["ticker"]) == set(manifest["ticker"]),
        "All frozen pilot companies are present.",
        "Pilot company coverage is incomplete.",
    )

    check(
        coverage["total_gkg_records"].gt(0).all(),
        "Every historical anchor window contains GKG records.",
        "At least one anchor window contains zero GKG records.",
    )

    check(
        coverage["normalized_share"].between(0.0, 1.0).all(),
        "Every normalized news share lies in [0, 1].",
        "At least one normalized news share is invalid.",
    )

    forbidden = {
        "forward_return_1m",
        "commonality_factor",
        "momentum_12_1",
        "sector_momentum_quintile",
        "winner",
        "outcome",
    }

    lower_columns = {str(c).lower() for c in coverage.columns}
    check(
        not any(term in lower_columns for term in forbidden),
        "Pilot coverage output contains no H3 return/outcome fields.",
        "Pilot coverage output contains a prohibited outcome field.",
    )

    nonzero = (
        coverage.assign(
            nonzero=coverage["matched_gkg_records"] > 0
        )
        .groupby("ticker", as_index=False)["nonzero"]
        .sum()
    )

    usable_count = int((nonzero["nonzero"] >= 3).sum())
    check(
        usable_count >= 12,
        (
            "At least 12/15 pilot companies have nonzero organization "
            "coverage in >=3/5 anchor windows."
        ),
        (
            f"Only {usable_count}/15 pilot companies have nonzero coverage "
            "in >=3/5 anchors."
        ),
    )

    high_ambiguity = set(
        manifest.loc[
            manifest["ambiguity_tier"].eq("HIGH"),
            "ticker",
        ]
    )
    variant_tickers = set(variants["ticker"].astype(str))
    check(
        high_ambiguity.issubset(variant_tickers),
        "Every HIGH-ambiguity company has extracted organization variants for review.",
        "A HIGH-ambiguity company is missing from variant diagnostics.",
    )

    check(
        bool(cost.get("execute_requested")),
        "Cost manifest records an executed pilot run.",
        "Cost manifest does not record an executed pilot.",
    )

    if failures:
        gate = "H3_GDELT_GKG_PILOT_FEASIBILITY_GATE_FAILED"
    else:
        gate = (
            "H3_GDELT_GKG_PILOT_FEASIBILITY_GATE_PASSED_WITH_"
            "HIGH_AMBIGUITY_REVIEW_REQUIRED"
        )

    lines += [
        "",
        f"Passed checks: {passes}",
        f"Failed checks: {len(failures)}",
        f"Companies meeting >=3/5 nonzero-anchor rule: {usable_count}/15",
        "",
        gate,
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
