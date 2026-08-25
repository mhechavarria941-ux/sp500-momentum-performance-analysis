from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-h3-direct-gdelt-daily-pilot-audit"

MANIFEST_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_daily_pilot_query_manifest.csv"
)
ANCHORS_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_daily_pilot_anchor_windows.csv"
)

OUT_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

DOWNLOAD_MANIFEST_PATH = OUT_DIR / "h3_gdelt_daily_pilot_download_manifest.csv"
DAILY_COVERAGE_PATH = OUT_DIR / "h3_gdelt_daily_pilot_daily_coverage.csv"
ANCHOR_COVERAGE_PATH = OUT_DIR / "h3_gdelt_daily_pilot_anchor_coverage.csv"
VARIANT_PATH = OUT_DIR / "h3_gdelt_daily_pilot_org_variants.csv"
ESTIMATE_PATH = OUT_DIR / "h3_gdelt_daily_pilot_download_estimate.json"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_direct_gdelt_daily_pilot_feasibility_audit.txt"
)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        MANIFEST_PATH,
        ANCHORS_PATH,
        DOWNLOAD_MANIFEST_PATH,
        DAILY_COVERAGE_PATH,
        ANCHOR_COVERAGE_PATH,
        VARIANT_PATH,
        ESTIMATE_PATH,
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Executed pilot output(s) missing: "
            + ", ".join(missing)
        )

    manifest = pd.read_csv(
        MANIFEST_PATH
    )
    anchors = pd.read_csv(
        ANCHORS_PATH
    )
    downloads = pd.read_csv(
        DOWNLOAD_MANIFEST_PATH
    )
    daily = pd.read_csv(
        DAILY_COVERAGE_PATH
    )
    anchor = pd.read_csv(
        ANCHOR_COVERAGE_PATH
    )
    variants = pd.read_csv(
        VARIANT_PATH
    )
    estimate = json.loads(
        ESTIMATE_PATH.read_text(
            encoding="utf-8"
        )
    )

    failures = []
    passed = 0

    lines = [
        "=" * 110,
        "H3 ATTENTION FEASIBILITY — DIRECT GDELT DAILY PILOT AUDIT",
        "=" * 110,
        "Google Cloud / BigQuery permitted: NO",
        "Azure SQL used by pilot: NO",
        "Return/outcome analysis permitted: NO",
        "",
    ]

    def check(
        condition: bool,
        success: str,
        failure: str,
    ) -> None:
        nonlocal passed

        if bool(condition):
            lines.append(
                "PASS: " + success
            )
            passed += 1
        else:
            lines.append(
                "FAIL: " + failure
            )
            failures.append(
                failure
            )

    check(
        len(downloads) == 35
        and downloads["date"].nunique() == 35,
        "Exactly 35 frozen daily GKG files were processed.",
        (
            f"Download-manifest rows={len(downloads)}, "
            f"unique dates={downloads['date'].nunique()}."
        ),
    )

    expected_daily_rows = (
        len(manifest) * 35
    )
    check(
        len(daily) == expected_daily_rows,
        (
            "Daily coverage contains every "
            f"company-date pair ({expected_daily_rows})."
        ),
        (
            f"Daily coverage rows={len(daily)}, "
            f"expected {expected_daily_rows}."
        ),
    )

    expected_anchor_rows = (
        len(manifest) * len(anchors)
    )
    check(
        len(anchor) == expected_anchor_rows,
        (
            "Anchor coverage contains every "
            f"company-window pair ({expected_anchor_rows})."
        ),
        (
            f"Anchor coverage rows={len(anchor)}, "
            f"expected {expected_anchor_rows}."
        ),
    )

    check(
        set(anchor["anchor_id"])
        == set(anchors["anchor_id"]),
        "All five frozen historical anchor windows are present.",
        "Historical anchor-window set is incomplete.",
    )

    check(
        set(anchor["ticker"])
        == set(manifest["ticker"]),
        "All 15 frozen pilot companies are present.",
        "Pilot company set is incomplete.",
    )

    check(
        anchor[
            "total_source_documents"
        ].gt(0).all(),
        "Every company-anchor denominator is positive.",
        "At least one company-anchor denominator is zero.",
    )

    check(
        anchor[
            "news_attention_share"
        ].between(0.0, 1.0).all(),
        "Every attention share is bounded in [0, 1].",
        "At least one attention share is invalid.",
    )

    check(
        "configured_csv_field_limit" in daily.columns
        and pd.to_numeric(
            daily["configured_csv_field_limit"],
            errors="coerce",
        ).gt(131072).all(),
        (
            "CSV parser field limit was raised above Python's default "
            "131,072 bytes for all processed GKG rows."
        ),
        "CSV parser field-limit safeguard is missing or too small.",
    )

    check(
        downloads[
            "sha256"
        ].astype(str).str.len().eq(64).all(),
        "Every downloaded archive has a recorded SHA-256.",
        "At least one archive lacks a valid SHA-256.",
    )

    check(
        not bool(
            estimate.get(
                "google_cloud_used",
                True,
            )
        )
        and not bool(
            estimate.get(
                "azure_sql_used",
                True,
            )
        ),
        "Pilot records zero Google Cloud and zero Azure SQL use.",
        "Pilot estimate unexpectedly records cloud-query use.",
    )

    forbidden_fragments = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )

    pilot_columns = {
        str(column).casefold()
        for column in (
            list(daily.columns)
            + list(anchor.columns)
            + list(variants.columns)
        )
    }

    bad_columns = [
        column
        for column in pilot_columns
        if any(
            fragment in column
            for fragment in forbidden_fragments
        )
    ]

    check(
        not bad_columns,
        "Pilot outputs contain no return/momentum/Winner/outcome columns.",
        "Prohibited outcome-like columns: "
        + ", ".join(
            sorted(bad_columns)
        ),
    )

    nonzero = (
        anchor.assign(
            nonzero=(
                anchor[
                    "matched_source_documents"
                ] > 0
            ).astype(int)
        )
        .groupby(
            "ticker",
            as_index=False,
        )["nonzero"]
        .sum()
    )

    usable_count = int(
        (
            nonzero["nonzero"] >= 2
        ).sum()
    )

    check(
        usable_count >= 10,
        (
            "At least 10/15 pilot companies have strict nonzero "
            "organization coverage in >=2/5 anchor windows."
        ),
        (
            f"Only {usable_count}/15 companies meet the "
            ">=2/5 nonzero-anchor feasibility rule."
        ),
    )

    high_ambiguity = set(
        manifest.loc[
            manifest[
                "ambiguity_tier"
            ].eq("HIGH"),
            "ticker",
        ]
    )

    variant_tickers = set(
        variants["ticker"].astype(str)
    )

    check(
        high_ambiguity.issubset(
            variant_tickers
        ),
        (
            "Every HIGH-ambiguity company has broad organization "
            "variants available for manual review."
        ),
        (
            "A HIGH-ambiguity company is missing from "
            "variant diagnostics."
        ),
    )

    if failures:
        gate = (
            "H3_DIRECT_GDELT_DAILY_PILOT_FEASIBILITY_GATE_FAILED"
        )
    else:
        gate = (
            "H3_DIRECT_GDELT_DAILY_PILOT_FEASIBILITY_GATE_"
            "PASSED_WITH_AMBIGUITY_REVIEW_REQUIRED"
        )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        (
            "Companies meeting >=2/5 strict nonzero-anchor rule: "
            f"{usable_count}/15"
        ),
        "",
        gate,
    ]

    AUDIT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    text = "\n".join(
        lines
    ) + "\n"

    AUDIT_PATH.write_text(
        text,
        encoding="utf-8",
    )

    print(
        text,
        end="",
    )


if __name__ == "__main__":
    main()
