from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v2-h3-full-gdelt-attention-extraction-audit-resilient-source"
H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
PROTOCOL_PATH = ROOT / "data" / "reference" / "h3" / "h3_full_gdelt_attention_extraction_v1.json"
MANIFEST_PATH = H3_DIR / "h3_pit_attention_alias_intervals.csv"
SOURCE_LEDGER_PATH = H3_DIR / "h3_gdelt_full_source_files.csv"
DOWNLOAD_FAILURES_PATH = H3_DIR / "h3_gdelt_full_download_failures.csv"
MONTHLY_PATH = H3_DIR / "h3_gdelt_full_monthly_security_attention.csv"
YEARLY_TEMPLATE = "h3_gdelt_full_daily_security_{year}.csv.gz"
AUDIT_PATH = ROOT / "reports" / "data_quality" / "h3_full_gdelt_attention_extraction_integrity_audit.txt"
FORBIDDEN = ("return", "momentum", "winner", "commonality_factor", "outcome")


def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    for p in (PROTOCOL_PATH,MANIFEST_PATH,SOURCE_LEDGER_PATH,DOWNLOAD_FAILURES_PATH,MONTHLY_PATH):
        if not p.exists(): raise FileNotFoundError(p)
    yearly_paths=[H3_DIR/YEARLY_TEMPLATE.format(year=y) for y in range(2021,2026)]
    for p in yearly_paths:
        if not p.exists(): raise FileNotFoundError(p)

    protocol_text=PROTOCOL_PATH.read_text(encoding="utf-8"); protocol=json.loads(protocol_text)
    protocol_sha=hashlib.sha256(protocol_text.encode()).hexdigest(); manifest_sha=sha256_file(MANIFEST_PATH)
    manifest=pd.read_csv(MANIFEST_PATH,dtype=str,keep_default_na=False)
    source=pd.read_csv(SOURCE_LEDGER_PATH,dtype=str,keep_default_na=False)
    source_failures=pd.read_csv(DOWNLOAD_FAILURES_PATH,dtype=str,keep_default_na=False)
    monthly=pd.read_csv(MONTHLY_PATH,dtype=str,keep_default_na=False)

    for c in ("source_file_bytes","parsed_rows","malformed_rows","malformed_row_rate","total_source_document_weight","active_security_count","unique_active_alias_count"):
        source[c]=pd.to_numeric(source[c],errors="raise")
    for c in ("eligible_days","nonzero_days","matched_source_document_weight","total_source_document_weight","unique_aliases_in_month","attention_share","strict_nonzero_month_flag","partial_calendar_month_flag"):
        monthly[c]=pd.to_numeric(monthly[c],errors="raise")

    failures=[]; passed=0
    lines=["="*128,"H3 STAGE 3L — FULL DIRECT-GDELT ATTENTION EXTRACTION INTEGRITY AUDIT","="*128,"H3 statistical inference authorized: NO",""]
    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if bool(condition): lines.append("PASS: "+success); passed+=1
        else: lines.append("FAIL: "+failure); failures.append(failure)

    expected_days=int(protocol["source"]["expected_daily_files"])
    expected_dates=pd.date_range(start=protocol["source"]["date_start"],end=pd.Timestamp(protocol["source"]["date_end_exclusive"])-pd.Timedelta(days=1),freq="D")
    observed_dates=pd.to_datetime(source["date"],errors="raise")
    check(len(source)==expected_days and observed_dates.nunique()==expected_days and set(observed_dates)==set(expected_dates),f"Source ledger contains the complete {expected_days}-date calendar.",f"Source ledger rows={len(source)}, unique dates={observed_dates.nunique()}, expected {expected_days}.")
    success_statuses={"DOWNLOADED_PARSED_RAW_DELETED","REUSED_VALID_CACHE"}
    check(source["status"].isin(success_statuses).all(),"Every daily source file has successful parse/cache status.","At least one daily source status is not successful.")
    check(len(source_failures)==0,"The resilient source-acquisition failure manifest is empty.",f"{len(source_failures)} unresolved source-download failure(s) remain.")
    if "catalog_listed_flag" in source.columns:
        listed=pd.to_numeric(source["catalog_listed_flag"],errors="coerce").fillna(0)
        check(listed.eq(1).all(),"Every expected GKG source file is present in the loaded official GDELT catalog.","At least one expected source file was not present in the loaded GDELT catalog.")
    if "catalog_size_match_flag" in source.columns and source["catalog_size_match_flag"].ne("").any():
        size_flags=pd.to_numeric(source.loc[source["catalog_size_match_flag"].ne(""),"catalog_size_match_flag"],errors="raise")
        check(size_flags.eq(1).all(),"Every source/cache with catalog size evidence matches the official GDELT file size.","At least one source/cache size differs from the official GDELT catalog.")
    check(source["source_file_sha256"].str.len().eq(64).all(),"Every daily source file has SHA-256 provenance.","A daily source file lacks a 64-character SHA-256 hash.")
    malformed_ceiling=float(protocol["technical_gate"]["maximum_malformed_row_rate_per_file"])
    check(source["malformed_row_rate"].le(malformed_ceiling).all(),f"Every daily malformed-row rate is within the frozen {malformed_ceiling:.4%} ceiling.","At least one daily malformed-row rate exceeds the ceiling.")
    check(source["total_source_document_weight"].gt(0).all(),"Every daily GDELT source-document denominator is positive.","At least one daily GDELT denominator is non-positive.")
    check(source["stage3j_manifest_sha256"].eq(manifest_sha).all(),"Every source record reproduces the exact Stage 3J manifest checksum.","A source record differs from the current Stage 3J manifest checksum.")
    check(source["protocol_sha256"].eq(protocol_sha).all() and monthly["stage3l_protocol_sha256"].eq(protocol_sha).all(),"Source and monthly outputs reproduce the frozen Stage 3L protocol checksum.","A Stage 3L output checksum differs from the frozen protocol.")

    manifest["start_dt"]=pd.to_datetime(manifest["alias_valid_from"],errors="raise")
    manifest["end_dt"]=pd.to_datetime(manifest["alias_valid_to_exclusive"],errors="raise")
    expected_pairs=0; daily_rows=0; duplicate_pairs=0; share_range_ok=True; weight_order_ok=True; daily_for_monthly=[]
    for year,path in zip(range(2021,2026),yearly_paths):
        daily=pd.read_csv(path,dtype=str,keep_default_na=False,compression="gzip")
        for c in ("matched_source_document_weight","total_source_document_weight","attention_share","strict_nonzero_day_flag"):
            daily[c]=pd.to_numeric(daily[c],errors="raise")
        daily_rows += len(daily)
        duplicate_pairs += int(daily[["date","security_key"]].duplicated().sum())
        share_range_ok = bool(share_range_ok and daily["attention_share"].between(0.0,1.0,inclusive="both").all())
        weight_order_ok = bool(weight_order_ok and (daily["matched_source_document_weight"]<=daily["total_source_document_weight"]).all())
        for date in pd.date_range(start=f"{year}-01-01",end=f"{year}-12-31",freq="D"):
            active=manifest[(manifest["start_dt"]<=date)&(manifest["end_dt"]>date)]
            if active["security_key"].duplicated().any(): expected_pairs=-1; break
            expected_pairs += len(active)
        daily_for_monthly.append(daily)

    check(duplicate_pairs==0,"Yearly daily shards contain no duplicate security-date observations.",f"Duplicate security-date rows={duplicate_pairs}.")
    check(expected_pairs>=0 and daily_rows==expected_pairs,"Daily attention shards exactly cover the full active PIT security-date universe.",f"Daily rows={daily_rows}; expected active security-date pairs={expected_pairs}.")
    check(share_range_ok,"Every daily attention share lies in [0, 1].","At least one daily attention share lies outside [0, 1].")
    check(weight_order_ok,"Daily matched source-document weight never exceeds its denominator.","At least one daily matched weight exceeds its denominator.")
    check(not monthly[["month","security_key"]].duplicated().any(),"Monthly panel has one row per security-month.","Duplicate security-month rows exist.")
    check(monthly["attention_share"].between(0.0,1.0,inclusive="both").all(),"Every monthly attention share lies in [0, 1].","At least one monthly attention share lies outside [0, 1].")

    recomputed_frames=[]
    for daily in daily_for_monthly:
        recomputed=(daily.groupby(["month","security_key"],as_index=False)
                    .agg(eligible_days_recomputed=("date","nunique"),matched_recomputed=("matched_source_document_weight","sum"),total_recomputed=("total_source_document_weight","sum")))
        recomputed_frames.append(recomputed)
    recomputed=pd.concat(recomputed_frames,ignore_index=True)
    compare=monthly.merge(recomputed,on=["month","security_key"],how="outer",indicator=True)
    aggregation_ok=bool(compare["_merge"].eq("both").all() and (compare["eligible_days"]==compare["eligible_days_recomputed"]).all() and (compare["matched_source_document_weight"]==compare["matched_recomputed"]).all() and (compare["total_source_document_weight"]==compare["total_recomputed"]).all())
    check(aggregation_ok,"Monthly panel exactly reaggregates from the frozen daily security shards.","Monthly panel does not exactly reproduce daily-shard aggregation.")

    all_output_columns={str(c).casefold() for frame in [source,monthly]+daily_for_monthly for c in frame.columns}
    bad=[c for c in all_output_columns if any(fragment in c for fragment in FORBIDDEN)]
    check(not bad,"Stage 3L outputs contain no return/momentum/Winner/outcome fields.","Prohibited outcome-like fields found: "+", ".join(sorted(bad)))

    gate="H3_FULL_GDELT_ATTENTION_EXTRACTION_INTEGRITY_AUDIT_PASSED" if not failures else "H3_FULL_GDELT_ATTENTION_EXTRACTION_INTEGRITY_AUDIT_FAILED"
    lines += ["",f"Passed checks: {passed}",f"Failed checks: {len(failures)}",f"Daily GDELT source files: {len(source)}",f"Daily security-attention rows: {daily_rows}",f"Monthly security-attention rows: {len(monthly)}",f"Monthly unique securities: {monthly['security_key'].nunique()}","",gate,"","A passing Stage 3L audit closes the no-outcome attention acquisition layer. The next step is to freeze the H3 statistical specification and attention transformation before any outcome join or hypothesis test."]
    AUDIT_PATH.parent.mkdir(parents=True,exist_ok=True)
    text="\n".join(lines)+"\n"; AUDIT_PATH.write_text(text,encoding="utf-8"); print(text,end="")


if __name__ == "__main__":
    main()
