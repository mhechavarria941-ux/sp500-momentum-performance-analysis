from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path

import pandas as pd

try:
    from google.cloud import bigquery
except ImportError as exc:
    raise SystemExit(
        "google-cloud-bigquery is required. Install with:\n"
        "  pip install google-cloud-bigquery\n"
        "Then authenticate, for example:\n"
        "  gcloud auth application-default login"
    ) from exc


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-h3-gdelt-gkg-feasibility-pilot"

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
RUN_REPORT_PATH = OUT_DIR / "h3_gdelt_gkg_pilot_run_report.txt"

GKG_TABLE = "`gdelt-bq.gdeltv2.gkg_partitioned`"


def quote_sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def anchor_case(anchors: pd.DataFrame) -> str:
    pieces = []
    for row in anchors.itertuples(index=False):
        pieces.append(
            "WHEN DATE(_PARTITIONTIME) >= DATE("
            + quote_sql_string(str(row.start_date))
            + ") AND DATE(_PARTITIONTIME) < DATE("
            + quote_sql_string(str(row.end_date_exclusive))
            + ") THEN "
            + quote_sql_string(str(row.anchor_id))
        )
    return "CASE\n" + "\n".join(pieces) + "\nEND"


def partition_filter(anchors: pd.DataFrame) -> str:
    pieces = []
    for row in anchors.itertuples(index=False):
        pieces.append(
            "(_PARTITIONTIME >= TIMESTAMP("
            + quote_sql_string(str(row.start_date))
            + ") AND _PARTITIONTIME < TIMESTAMP("
            + quote_sql_string(str(row.end_date_exclusive))
            + "))"
        )
    return " OR ".join(pieces)


def coverage_sql(manifest: pd.DataFrame, anchors: pd.DataFrame) -> str:
    anchor_expr = anchor_case(anchors)
    filter_expr = partition_filter(anchors)

    count_exprs = []
    for row in manifest.itertuples(index=False):
        ticker = re.sub(r"[^A-Z0-9]", "_", str(row.ticker).upper())
        pattern = str(row.exact_v2organization_regex)
        count_exprs.append(
            "COUNTIF(REGEXP_CONTAINS(LOWER(IFNULL(V2Organizations, '')), "
            + quote_sql_string(pattern)
            + ")) AS match_"
            + ticker
        )

    return f"""
WITH base AS (
  SELECT
    {anchor_expr} AS anchor_id,
    V2Organizations
  FROM {GKG_TABLE}
  WHERE {filter_expr}
)
SELECT
  anchor_id,
  COUNT(*) AS total_gkg_records,
  {", ".join(count_exprs)}
FROM base
WHERE anchor_id IS NOT NULL
GROUP BY anchor_id
ORDER BY anchor_id
""".strip()


def variants_sql(manifest: pd.DataFrame, anchors: pd.DataFrame) -> str:
    filter_expr = partition_filter(anchors)

    structs = []
    for row in manifest.itertuples(index=False):
        structs.append(
            "STRUCT("
            + quote_sql_string(str(row.ticker))
            + " AS ticker, "
            + quote_sql_string(str(row.broad_variant_regex))
            + " AS broad_regex)"
        )

    company_array = ",\n    ".join(structs)

    return f"""
WITH companies AS (
  SELECT *
  FROM UNNEST([
    {company_array}
  ])
),
org_mentions AS (
  SELECT
    LOWER(TRIM(SPLIT(org_entry, ',')[SAFE_OFFSET(0)])) AS org_name
  FROM {GKG_TABLE},
  UNNEST(SPLIT(IFNULL(V2Organizations, ''), ';')) AS org_entry
  WHERE {filter_expr}
),
matched AS (
  SELECT
    c.ticker,
    o.org_name,
    COUNT(*) AS mention_occurrences
  FROM org_mentions o
  JOIN companies c
    ON REGEXP_CONTAINS(o.org_name, c.broad_regex)
  WHERE o.org_name IS NOT NULL
    AND o.org_name != ''
  GROUP BY c.ticker, o.org_name
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY ticker
      ORDER BY mention_occurrences DESC, org_name
    ) AS variant_rank
  FROM matched
)
SELECT
  ticker,
  org_name,
  mention_occurrences,
  variant_rank
FROM ranked
WHERE variant_rank <= 15
ORDER BY ticker, variant_rank
""".strip()


def dry_run_bytes(client: bigquery.Client, sql: str) -> int:
    config = bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
    )
    job = client.query(sql, job_config=config)
    return int(job.total_bytes_processed or 0)


def bytes_to_gb(value: int) -> float:
    return value / (1024 ** 3)


def reshape_coverage(
    raw: pd.DataFrame,
    manifest: pd.DataFrame,
    anchors: pd.DataFrame,
) -> pd.DataFrame:
    anchor_meta = anchors.set_index("anchor_id").to_dict("index")
    rows = []

    for source_row in raw.itertuples(index=False):
        anchor_id = str(source_row.anchor_id)
        total = int(source_row.total_gkg_records)
        meta = anchor_meta[anchor_id]

        for company in manifest.itertuples(index=False):
            ticker = str(company.ticker).upper()
            column = "match_" + re.sub(r"[^A-Z0-9]", "_", ticker)
            matches = int(getattr(source_row, column))
            rows.append(
                {
                    "anchor_id": anchor_id,
                    "start_date": meta["start_date"],
                    "end_date_exclusive": meta["end_date_exclusive"],
                    "ticker": ticker,
                    "canonical_company_name": company.canonical_company_name,
                    "ambiguity_tier": company.ambiguity_tier,
                    "matched_gkg_records": matches,
                    "total_gkg_records": total,
                    "normalized_share": (
                        matches / total
                        if total > 0
                        else math.nan
                    ),
                    "mentions_per_100k_gkg_records": (
                        100000.0 * matches / total
                        if total > 0
                        else math.nan
                    ),
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--billing-project",
        default=os.getenv("GOOGLE_CLOUD_PROJECT"),
        help=(
            "Google Cloud project billed for the public BigQuery query. "
            "May also be set through GOOGLE_CLOUD_PROJECT."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the pilot after dry-run cost checks.",
    )
    parser.add_argument(
        "--max-gb",
        type=float,
        default=50.0,
        help=(
            "Maximum combined dry-run bytes in GiB allowed for execution. "
            "Default: 50."
        ),
    )
    args = parser.parse_args()

    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    if not args.billing_project:
        raise SystemExit(
            "A billing/quota project is required. Supply --billing-project "
            "or set GOOGLE_CLOUD_PROJECT."
        )

    manifest = pd.read_csv(MANIFEST_PATH)
    anchors = pd.read_csv(ANCHORS_PATH)

    if manifest["ticker"].duplicated().any():
        raise RuntimeError("Duplicate tickers in pilot manifest.")
    if anchors["anchor_id"].duplicated().any():
        raise RuntimeError("Duplicate anchor IDs.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = bigquery.Client(project=args.billing_project)

    coverage_query = coverage_sql(manifest, anchors)
    variant_query = variants_sql(manifest, anchors)

    coverage_bytes = dry_run_bytes(client, coverage_query)
    variant_bytes = dry_run_bytes(client, variant_query)
    total_bytes = coverage_bytes + variant_bytes

    cost = {
        "script_version": SCRIPT_VERSION,
        "billing_project": args.billing_project,
        "coverage_query_bytes": coverage_bytes,
        "coverage_query_gib": bytes_to_gb(coverage_bytes),
        "variant_query_bytes": variant_bytes,
        "variant_query_gib": bytes_to_gb(variant_bytes),
        "combined_bytes": total_bytes,
        "combined_gib": bytes_to_gb(total_bytes),
        "max_gib_allowed": args.max_gb,
        "execute_requested": bool(args.execute),
    }
    COST_PATH.write_text(
        json.dumps(cost, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "Coverage-query dry-run estimate: "
        f"{bytes_to_gb(coverage_bytes):.3f} GiB"
    )
    print(
        "Variant-query dry-run estimate: "
        f"{bytes_to_gb(variant_bytes):.3f} GiB"
    )
    print(
        "Combined dry-run estimate: "
        f"{bytes_to_gb(total_bytes):.3f} GiB"
    )

    if not args.execute:
        report = [
            "H3 GDELT GKG FEASIBILITY PILOT — DRY RUN ONLY",
            f"Combined estimated scan: {bytes_to_gb(total_bytes):.3f} GiB",
            f"Configured execution cap: {args.max_gb:.3f} GiB",
            "No attention values were retrieved.",
            "No returns/outcomes were queried.",
            "",
            "To execute after reviewing the estimate:",
            "python src\\analysis\\probe_h3_gdelt_gkg_bigquery.py "
            f"--billing-project {args.billing_project} "
            f"--max-gb {args.max_gb} --execute",
            "",
            "H3_GDELT_GKG_PILOT_DRY_RUN_COMPLETE",
        ]
        RUN_REPORT_PATH.write_text(
            "\n".join(report) + "\n",
            encoding="utf-8",
        )
        print("\n".join(report))
        return

    combined_gib = bytes_to_gb(total_bytes)
    if combined_gib > args.max_gb:
        raise RuntimeError(
            f"Execution refused: dry-run estimate {combined_gib:.3f} GiB "
            f"exceeds --max-gb {args.max_gb:.3f}."
        )

    raw_coverage = client.query(coverage_query).result().to_dataframe()
    coverage = reshape_coverage(
        raw_coverage,
        manifest,
        anchors,
    )
    coverage.to_csv(
        COVERAGE_PATH,
        index=False,
    )

    variants = client.query(variant_query).result().to_dataframe()
    variants = variants.merge(
        manifest[
            [
                "ticker",
                "canonical_company_name",
                "ambiguity_tier",
                "exact_v2organization_regex",
                "review_note",
            ]
        ],
        on="ticker",
        how="left",
        validate="many_to_one",
    )
    variants.to_csv(
        VARIANT_PATH,
        index=False,
    )

    expected_rows = len(manifest) * len(anchors)
    if len(coverage) != expected_rows:
        raise RuntimeError(
            f"Coverage rows={len(coverage)}, expected {expected_rows}."
        )

    nonzero = (
        coverage.assign(
            is_nonzero=coverage["matched_gkg_records"] > 0
        )
        .groupby("ticker", as_index=False)
        .agg(
            nonzero_anchor_windows=("is_nonzero", "sum"),
            total_matches=("matched_gkg_records", "sum"),
        )
    )

    merged = manifest[
        [
            "ticker",
            "canonical_company_name",
            "ambiguity_tier",
        ]
    ].merge(
        nonzero,
        on="ticker",
        how="left",
        validate="one_to_one",
    )

    usable = int(
        (
            merged["nonzero_anchor_windows"]
            >= 3
        ).sum()
    )

    high_ambiguity = merged[
        merged["ambiguity_tier"].eq("HIGH")
    ]["ticker"].tolist()

    report = [
        "H3 GDELT GKG FEASIBILITY PILOT — EXECUTED",
        f"Pilot securities: {len(manifest)}",
        f"Anchor windows: {len(anchors)}",
        f"Coverage rows: {len(coverage)}",
        (
            "Companies with nonzero GKG organization matches in >=3/5 "
            f"anchor windows: {usable}/{len(manifest)}"
        ),
        "High-ambiguity queries requiring explicit review: "
        + (
            ", ".join(high_ambiguity)
            if high_ambiguity
            else "None"
        ),
        f"Combined BigQuery scan estimate: {combined_gib:.3f} GiB",
        "Returns/outcomes joined: 0",
        "",
        "H3_GDELT_GKG_PILOT_EXECUTION_COMPLETE",
    ]

    RUN_REPORT_PATH.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )
    print("\n".join(report))


if __name__ == "__main__":
    main()
