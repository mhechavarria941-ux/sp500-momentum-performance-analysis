from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v2-h3-full-gdelt-attention-extraction-resilient-download"
H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
PROTOCOL_PATH = ROOT / "data" / "reference" / "h3" / "h3_full_gdelt_attention_extraction_v1.json"
MANIFEST_PATH = H3_DIR / "h3_pit_attention_alias_intervals.csv"
STAGE3J_AUDIT_PATH = ROOT / "reports" / "data_quality" / "h3_pit_attention_alias_manifest_integrity_audit.txt"
STAGE3K_AUDIT_PATH = ROOT / "reports" / "data_quality" / "h3_gdelt_alias_coverage_missingness_gate_audit.txt"
STAGE3K_SOURCE_PATH = H3_DIR / "h3_gdelt_stage3k_source_files.csv"
CACHE_ROOT = ROOT / "data" / "interim" / "h3_gdelt_full"
RAW_DIR = CACHE_ROOT / "raw"
DAILY_CACHE_DIR = CACHE_ROOT / "daily_security"
META_DIR = CACHE_ROOT / "metadata"
SOURCE_LEDGER_PATH = H3_DIR / "h3_gdelt_full_source_files.csv"
MONTHLY_PATH = H3_DIR / "h3_gdelt_full_monthly_security_attention.csv"
COVERAGE_BY_CLASS_PATH = H3_DIR / "h3_gdelt_full_coverage_by_alias_class.csv"
REPORT_PATH = H3_DIR / "h3_gdelt_full_extraction_report.txt"
DOWNLOAD_FAILURES_PATH = H3_DIR / "h3_gdelt_full_download_failures.csv"
CATALOG_SNAPSHOT_PATH = H3_DIR / "h3_gdelt_gkg_catalog_snapshot.csv"
GDELT_MD5_URL = "https://data.gdeltproject.org/gkg/md5sums"
GDELT_FILESIZES_URL = "https://data.gdeltproject.org/gkg/filesizes"
YEARLY_TEMPLATE = "h3_gdelt_full_daily_security_{year}.csv.gz"
STAGE3J_PASS = "H3_PIT_ATTENTION_ALIAS_MANIFEST_INTEGRITY_AUDIT_PASSED"
STAGE3K_PASS = "H3_GDELT_ALIAS_COVERAGE_MISSINGNESS_GATE_PASSED"
LEGAL_SUFFIXES = {"inc","incorporated","corp","corporation","co","company","ltd","limited","plc","llc","llp","lp","nv","ag","se","sa"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--force-redownload", action="store_true")
    p.add_argument("--sleep-seconds", type=float, default=0.25)
    p.add_argument("--download-attempts", type=int, default=6)
    p.add_argument("--estimate-only", action="store_true")
    return p.parse_args()


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as h:
        for block in iter(lambda: h.read(1024 * 1024), b""):
            d.update(block)
    return d.hexdigest()

def md5_file(path: Path) -> str:
    d = hashlib.md5()
    with path.open("rb") as h:
        for block in iter(lambda: h.read(1024 * 1024), b""):
            d.update(block)
    return d.hexdigest()


def fetch_text(url: str, attempts: int = 4) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 H3-SP500-Attention-Research/1.0 "
            "(academic reproducibility extraction)"
        )
    }
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(
        f"Unable to retrieve GDELT catalog after {attempts} attempts: "
        f"{url} | {last_error}"
    )


def load_gdelt_catalog() -> dict[str, dict[str, object]]:
    try:
        md5_text = fetch_text(GDELT_MD5_URL)
        size_text = fetch_text(GDELT_FILESIZES_URL)
    except Exception as exc:
        print(f"WARNING: GDELT catalog unavailable: {exc}")
        return {}

    md5_map = {}
    for line in md5_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and len(parts[0]) == 32:
            md5_map[parts[-1]] = parts[0].lower()

    size_map = {}
    for line in size_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            try:
                size_map[parts[-1]] = int(parts[0])
            except Exception:
                pass

    names = sorted(set(md5_map) | set(size_map))
    catalog = {
        name: {
            "catalog_md5": md5_map.get(name, ""),
            "catalog_size_bytes": size_map.get(name, ""),
        }
        for name in names
    }

    snapshot = pd.DataFrame(
        [
            {
                "filename": name,
                "catalog_md5": values["catalog_md5"],
                "catalog_size_bytes": values["catalog_size_bytes"],
            }
            for name, values in catalog.items()
            if name.endswith(".gkg.csv.zip")
        ]
    )
    CATALOG_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_csv(CATALOG_SNAPSHOT_PATH, index=False)
    print(f"Official GDELT GKG catalog loaded: {len(snapshot):,} daily files.")
    return catalog



def normalize_full(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    raw = unicodedata.normalize("NFKC", str(value)).casefold()
    raw = re.sub(r"/\s*the\s*$", " ", raw)
    raw = re.sub(r"/\s*(?:de|md|mo|mn|ny|oh|nj|pa|va|ca|tx)\s*/", " ", raw)
    raw = raw.replace("&", " and ")
    raw = re.sub(r"[’']", "", raw)
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw.startswith("the "):
        raw = raw[4:].strip()
    tokens = raw.split()
    if len(tokens) >= 2 and tokens[-2] in {"class", "cl"}:
        tokens = tokens[:-2]
    return " ".join(tokens).strip()


def normalize_core(value: object) -> str:
    tokens = normalize_full(value).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens = tokens[:-1]
    return " ".join(tokens).strip()


def self_test() -> None:
    cases = {
        "Cigna Group/The": ("cigna group", "cigna group"),
        "The Cigna Group": ("cigna group", "cigna group"),
        "RTX Corporation": ("rtx corporation", "rtx"),
        "Campbell's Company/The": ("campbells company", "campbells"),
    }
    for raw, expected in cases.items():
        observed = (normalize_full(raw), normalize_core(raw))
        if observed != expected:
            raise RuntimeError(f"Normalization self-test failed for {raw!r}: {observed!r} != {expected!r}")


def date_range(start: str, end_exclusive: str) -> list[pd.Timestamp]:
    return list(pd.date_range(start=pd.Timestamp(start), end=pd.Timestamp(end_exclusive)-pd.Timedelta(days=1), freq="D"))


def active_alias_rows(manifest: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    return manifest[(manifest["alias_valid_from_dt"] <= date) & (manifest["alias_valid_to_dt"] > date)].copy()


def download_file(
    url: str,
    destination: Path,
    *,
    attempts: int = 6,
    expected_md5: str = "",
    expected_size: object = "",
) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    if temp.exists():
        temp.unlink()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 H3-SP500-Attention-Research/1.0 "
            "(academic reproducibility extraction)"
        ),
        "Cache-Control": "no-cache",
    }

    candidates = [url]
    if url.startswith("https://"):
        candidates.append("http://" + url[len("https://"):])

    expected_size_int = None
    try:
        if expected_size not in ("", None):
            expected_size_int = int(expected_size)
    except Exception:
        expected_size_int = None

    last_error = None
    history = []
    waits = [5, 15, 30, 60, 120]

    for candidate in candidates:
        for attempt in range(1, attempts + 1):
            try:
                req = urllib.request.Request(candidate, headers=headers)
                with urllib.request.urlopen(req, timeout=180) as response, temp.open("wb") as h:
                    shutil.copyfileobj(response, h)

                if temp.stat().st_size <= 0:
                    raise RuntimeError("Downloaded source file is empty.")

                observed_size = temp.stat().st_size
                if (
                    expected_size_int is not None
                    and observed_size != expected_size_int
                ):
                    raise RuntimeError(
                        f"Catalog size mismatch: observed={observed_size}, "
                        f"expected={expected_size_int}"
                    )

                observed_md5 = md5_file(temp)
                if expected_md5 and observed_md5.lower() != expected_md5.lower():
                    raise RuntimeError(
                        f"Catalog MD5 mismatch: observed={observed_md5}, "
                        f"expected={expected_md5}"
                    )

                temp.replace(destination)
                return {
                    "resolved_url": candidate,
                    "source_file_md5": observed_md5,
                    "catalog_md5_verified": int(
                        bool(expected_md5)
                        and observed_md5.lower() == expected_md5.lower()
                    ),
                    "catalog_size_verified": int(
                        expected_size_int is not None
                        and observed_size == expected_size_int
                    ),
                }

            except Exception as exc:
                last_error = exc
                if temp.exists():
                    temp.unlink()
                code = exc.code if isinstance(exc, urllib.error.HTTPError) else ""
                history.append(
                    f"url={candidate} attempt={attempt} http={code} error={exc}"
                )
                if attempt < attempts:
                    time.sleep(waits[min(attempt - 1, len(waits) - 1)])

    raise RuntimeError(
        f"Download failed after {attempts} attempts per endpoint: {url} | "
        f"{last_error} | history={' || '.join(history[-6:])}"
    )


def parse_gkg_daily(zip_path: Path, active_aliases: set[str]) -> tuple[int,int,int,dict[str,int]]:
    parsed_rows = malformed_rows = total_weight = 0
    alias_weight: dict[str,int] = defaultdict(int)
    csv.field_size_limit(256 * 1024 * 1024)
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = [n for n in archive.namelist() if not n.endswith("/")]
        if len(members) != 1:
            raise RuntimeError(f"Expected one member in {zip_path.name}; found {len(members)}.")
        with archive.open(members[0], "r") as binary, io.TextIOWrapper(binary, encoding="utf-8", errors="replace", newline="") as text:
            reader = csv.reader(text, delimiter="\t")
            for fields in reader:
                if len(fields) <= 6:
                    malformed_rows += 1; continue
                try:
                    weight = int(fields[1])
                except Exception:
                    malformed_rows += 1; continue
                if weight < 0:
                    malformed_rows += 1; continue
                parsed_rows += 1
                total_weight += weight
                organizations = fields[6]
                if not organizations or not active_aliases:
                    continue
                matched_aliases: set[str] = set()
                for raw_org in organizations.split(";"):
                    raw_org = raw_org.strip()
                    if not raw_org: continue
                    full, core = normalize_full(raw_org), normalize_core(raw_org)
                    if full in active_aliases: matched_aliases.add(full)
                    if core in active_aliases: matched_aliases.add(core)
                for alias in matched_aliases:
                    alias_weight[alias] += weight
    return parsed_rows, malformed_rows, total_weight, dict(alias_weight)


def cache_valid(meta_path: Path, daily_path: Path, *, date: pd.Timestamp, manifest_sha: str, protocol_sha: str, cache_schema_version: str, parser_contract_version: str) -> bool:
    if not meta_path.exists() or not daily_path.exists(): return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(meta.get("date") == date.date().isoformat() and meta.get("stage3j_manifest_sha256") == manifest_sha and meta.get("protocol_sha256") == protocol_sha and meta.get("cache_schema_version") == cache_schema_version and meta.get("parser_contract_version") == parser_contract_version)


def estimate_transfer(expected_days: int) -> None:
    if not STAGE3K_SOURCE_PATH.exists():
        print("Stage 3K source ledger not found; transfer estimate unavailable."); return
    pilot = pd.read_csv(STAGE3K_SOURCE_PATH, dtype=str, keep_default_na=False)
    if "source_file_bytes" not in pilot.columns:
        print("Stage 3K source byte sizes unavailable."); return
    sizes = pd.to_numeric(pilot["source_file_bytes"], errors="coerce").dropna()
    if sizes.empty:
        print("Stage 3K source byte sizes unavailable."); return
    average, median = sizes.mean(), sizes.median()
    projected = average * expected_days
    print(f"Estimated full raw transfer from Stage 3K sample: {projected/(1024**3):,.2f} GiB (mean daily zip {average/(1024**2):,.2f} MiB; median {median/(1024**2):,.2f} MiB).")
    print("Raw zips are deleted after successful parse; compressed parsed caches remain.")


def build_daily_output(*, date: pd.Timestamp, active: pd.DataFrame, alias_weight: dict[str,int], total_weight: int, stage3j_manifest_sha: str, protocol_sha: str) -> pd.DataFrame:
    rows=[]
    for row in active.itertuples(index=False):
        matched=int(alias_weight.get(str(row.production_alias),0))
        rows.append({
            "date":date.date().isoformat(),"year":date.year,"month":date.strftime("%Y-%m"),
            "security_key":row.security_key,"issuer_cik":row.issuer_cik,"latest_project_ticker":row.latest_project_ticker,
            "structural_ambiguity_tier":row.structural_ambiguity_tier,"alias_selection_reason":row.alias_selection_reason,
            "authoritative_name_source_layer":row.authoritative_name_source_layer,"production_alias":row.production_alias,
            "alias_valid_from":row.alias_valid_from,"alias_valid_to_exclusive":row.alias_valid_to_exclusive,
            "matched_source_document_weight":matched,"total_source_document_weight":total_weight,
            "attention_share":matched/total_weight,"strict_nonzero_day_flag":int(matched>0),
            "stage3j_policy_id":row.policy_id,"stage3j_policy_sha256":row.policy_sha256,
            "stage3j_manifest_sha256":stage3j_manifest_sha,"stage3l_protocol_sha256":protocol_sha,
        })
    return pd.DataFrame(rows)


def consolidate_year(year: int, dates: list[pd.Timestamp]) -> Path:
    output_path = H3_DIR / YEARLY_TEMPLATE.format(year=year)
    frames=[]
    for date in dates:
        p=DAILY_CACHE_DIR/f"{date.strftime('%Y%m%d')}_security_attention.csv.gz"
        require(p)
        frames.append(pd.read_csv(p,dtype=str,keep_default_na=False,compression="gzip"))
    df=pd.concat(frames,ignore_index=True)
    if df[["date","security_key"]].duplicated().any():
        raise RuntimeError(f"{year}: duplicate security-date rows during consolidation.")
    df.to_csv(output_path,index=False,compression="gzip")
    return output_path


def aggregate_monthly(yearly_paths: list[Path]) -> pd.DataFrame:
    monthly_frames=[]
    for path in yearly_paths:
        daily=pd.read_csv(path,dtype=str,keep_default_na=False,compression="gzip")
        for c in ("matched_source_document_weight","total_source_document_weight","strict_nonzero_day_flag"):
            daily[c]=pd.to_numeric(daily[c],errors="raise")
        grouped=(daily.groupby(["month","security_key","issuer_cik","latest_project_ticker","structural_ambiguity_tier","alias_selection_reason","authoritative_name_source_layer"],as_index=False)
                 .agg(eligible_days=("date","nunique"),nonzero_days=("strict_nonzero_day_flag","sum"),matched_source_document_weight=("matched_source_document_weight","sum"),total_source_document_weight=("total_source_document_weight","sum"),unique_aliases_in_month=("production_alias","nunique")))
        grouped["attention_share"]=grouped["matched_source_document_weight"]/grouped["total_source_document_weight"]
        grouped["strict_nonzero_month_flag"]=(grouped["matched_source_document_weight"]>0).astype(int)
        grouped["partial_calendar_month_flag"]=(grouped["eligible_days"]<pd.to_datetime(grouped["month"]+"-01").dt.days_in_month).astype(int)
        monthly_frames.append(grouped)
    monthly=pd.concat(monthly_frames,ignore_index=True).sort_values(["month","security_key"])
    if monthly[["month","security_key"]].duplicated().any():
        raise RuntimeError("Duplicate security-month rows after aggregation.")
    return monthly


def main() -> None:
    args=parse_args(); print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}"); self_test()
    for p in (PROTOCOL_PATH,MANIFEST_PATH,STAGE3J_AUDIT_PATH,STAGE3K_AUDIT_PATH): require(p)
    if STAGE3J_PASS not in STAGE3J_AUDIT_PATH.read_text(encoding="utf-8",errors="replace"):
        raise RuntimeError("Stage 3J prerequisite has not passed.")
    if STAGE3K_PASS not in STAGE3K_AUDIT_PATH.read_text(encoding="utf-8",errors="replace"):
        raise RuntimeError("Stage 3K prerequisite has not passed.")
    protocol_text=PROTOCOL_PATH.read_text(encoding="utf-8"); config=json.loads(protocol_text)
    protocol_sha=hashlib.sha256(protocol_text.encode()).hexdigest()
    manifest=pd.read_csv(MANIFEST_PATH,dtype=str,keep_default_na=False)
    expected_policy=config["prerequisites"]["stage3j_policy_id"]
    if not manifest["policy_id"].eq(expected_policy).all():
        raise RuntimeError(f"Stage 3J manifest is not frozen at {expected_policy}.")
    manifest["alias_valid_from_dt"]=pd.to_datetime(manifest["alias_valid_from"],errors="raise")
    manifest["alias_valid_to_dt"]=pd.to_datetime(manifest["alias_valid_to_exclusive"],errors="raise")
    manifest_sha=sha256_file(MANIFEST_PATH)
    dates=date_range(config["source"]["date_start"],config["source"]["date_end_exclusive"])
    expected_days=int(config["source"]["expected_daily_files"])
    if len(dates)!=expected_days: raise RuntimeError(f"Calendar generated {len(dates)} dates; expected {expected_days}.")
    estimate_transfer(expected_days)
    if args.estimate_only: return
    for d in (CACHE_ROOT,RAW_DIR,DAILY_CACHE_DIR,META_DIR,H3_DIR): d.mkdir(parents=True,exist_ok=True)
    catalog=load_gdelt_catalog()
    cache_schema=config["cache"]["schema_version"]; parser_contract=config["cache"]["parser_contract_version"]
    source_rows=[]; downloaded_count=0; reused_count=0
    def process_one_date(ordinal: int, date: pd.Timestamp, deferred_retry: bool):
        nonlocal downloaded_count, reused_count
        ymd=date.strftime("%Y%m%d")
        filename=f"{ymd}.gkg.csv.zip"
        url=config["source"]["url_template"].replace("{YYYYMMDD}",ymd)
        raw_path=RAW_DIR/filename
        daily_path=DAILY_CACHE_DIR/f"{ymd}_security_attention.csv.gz"
        meta_path=META_DIR/f"{ymd}.json"

        active=active_alias_rows(manifest,date)
        if active["security_key"].duplicated().any():
            raise RuntimeError(f"{ymd}: multiple active alias rows for a security.")

        entry=catalog.get(filename,{})
        expected_md5=str(entry.get("catalog_md5","")).strip()
        expected_size=entry.get("catalog_size_bytes","")
        catalog_listed=int(bool(entry))

        valid=(
            not args.force_redownload
            and cache_valid(
                meta_path,daily_path,date=date,manifest_sha=manifest_sha,
                protocol_sha=protocol_sha,cache_schema_version=cache_schema,
                parser_contract_version=parser_contract
            )
        )

        if valid:
            meta=json.loads(meta_path.read_text(encoding="utf-8"))
            reused_count+=1
            observed_bytes=int(meta.get("source_file_bytes",0))
            size_match=(
                int(observed_bytes==int(expected_size))
                if expected_size not in ("",None) else ""
            )
            return True,{
                "date":meta["date"],"year":date.year,
                "source_url":meta["source_url"],
                "resolved_source_url":meta.get("resolved_source_url",meta["source_url"]),
                "source_file_sha256":meta["source_file_sha256"],
                "source_file_md5":meta.get("source_file_md5",""),
                "source_file_bytes":meta["source_file_bytes"],
                "parsed_rows":meta["parsed_rows"],
                "malformed_rows":meta["malformed_rows"],
                "malformed_row_rate":meta["malformed_row_rate"],
                "total_source_document_weight":meta["total_source_document_weight"],
                "active_security_count":meta["active_security_count"],
                "unique_active_alias_count":meta["unique_active_alias_count"],
                "status":"REUSED_VALID_CACHE",
                "download_pass":meta.get("download_pass","LEGACY_OR_PRIOR_CACHE"),
                "catalog_listed_flag":catalog_listed,
                "catalog_md5":expected_md5,
                "catalog_size_bytes":expected_size,
                "catalog_size_match_flag":size_match,
                "catalog_md5_verified_flag":meta.get("catalog_md5_verified_flag",""),
                "stage3j_manifest_sha256":manifest_sha,
                "protocol_sha256":protocol_sha,
                "cache_schema_version":cache_schema,
                "parser_contract_version":parser_contract,
                "download_error":"",
            }

        pass_name="DEFERRED_RETRY" if deferred_retry else "PRIMARY_PASS"
        print(
            f"[{ordinal:04d}/{len(dates)}] {date.date()} | "
            f"active securities={len(active)} | {pass_name}"
        )

        try:
            info=download_file(
                url,raw_path,attempts=args.download_attempts,
                expected_md5=expected_md5,expected_size=expected_size
            )
            raw_sha=sha256_file(raw_path)
            raw_bytes=raw_path.stat().st_size
            parsed_rows,malformed_rows,total_weight,alias_weight=parse_gkg_daily(
                raw_path,set(active["production_alias"].astype(str))
            )
            if total_weight<=0:
                raise RuntimeError(f"{ymd}: non-positive source denominator.")

            malformed_rate=(
                malformed_rows/(parsed_rows+malformed_rows)
                if (parsed_rows+malformed_rows)>0 else 1.0
            )
            daily=build_daily_output(
                date=date,active=active,alias_weight=alias_weight,
                total_weight=total_weight,stage3j_manifest_sha=manifest_sha,
                protocol_sha=protocol_sha
            )
            daily.to_csv(daily_path,index=False,compression="gzip")

            meta={
                "date":date.date().isoformat(),
                "source_url":url,
                "resolved_source_url":info["resolved_url"],
                "source_file_sha256":raw_sha,
                "source_file_md5":info["source_file_md5"],
                "source_file_bytes":raw_bytes,
                "parsed_rows":parsed_rows,
                "malformed_rows":malformed_rows,
                "malformed_row_rate":malformed_rate,
                "total_source_document_weight":total_weight,
                "active_security_count":len(active),
                "unique_active_alias_count":active["production_alias"].nunique(),
                "stage3j_manifest_sha256":manifest_sha,
                "protocol_sha256":protocol_sha,
                "cache_schema_version":cache_schema,
                "parser_contract_version":parser_contract,
                "runner_script_version":SCRIPT_VERSION,
                "download_pass":pass_name,
                "catalog_listed_flag":catalog_listed,
                "catalog_md5":expected_md5,
                "catalog_size_bytes":expected_size,
                "catalog_size_match_flag":info["catalog_size_verified"],
                "catalog_md5_verified_flag":info["catalog_md5_verified"],
            }
            meta_path.write_text(
                json.dumps(meta,indent=2,sort_keys=True)+"\n",encoding="utf-8"
            )
            if raw_path.exists():
                raw_path.unlink()
            downloaded_count+=1
            if args.sleep_seconds>0:
                time.sleep(args.sleep_seconds)

            return True,{
                **meta,
                "year":date.year,
                "status":"DOWNLOADED_PARSED_RAW_DELETED",
                "download_error":"",
            }

        except Exception as exc:
            if raw_path.exists():
                raw_path.unlink()
            print(
                f"DEFERRED DOWNLOAD FAILURE: {date.date()} | "
                f"catalog_listed={catalog_listed} | {exc}"
            )
            return False,{
                "date":date.date().isoformat(),"year":date.year,
                "source_url":url,"resolved_source_url":"",
                "source_file_sha256":"","source_file_md5":"","source_file_bytes":"",
                "parsed_rows":"","malformed_rows":"","malformed_row_rate":"",
                "total_source_document_weight":"",
                "active_security_count":len(active),
                "unique_active_alias_count":active["production_alias"].nunique(),
                "status":(
                    "DOWNLOAD_FAILED_CATALOG_LISTED"
                    if catalog_listed else "DOWNLOAD_FAILED_NOT_IN_LOADED_CATALOG"
                ),
                "download_pass":pass_name,
                "catalog_listed_flag":catalog_listed,
                "catalog_md5":expected_md5,
                "catalog_size_bytes":expected_size,
                "catalog_size_match_flag":"",
                "catalog_md5_verified_flag":"",
                "stage3j_manifest_sha256":manifest_sha,
                "protocol_sha256":protocol_sha,
                "cache_schema_version":cache_schema,
                "parser_contract_version":parser_contract,
                "download_error":str(exc),
            }

    source_by_date={}
    failed_dates=[]

    for ordinal,date in enumerate(dates,start=1):
        ok,row=process_one_date(ordinal,date,False)
        source_by_date[date.date().isoformat()]=row
        if not ok:
            failed_dates.append((ordinal,date))

    if failed_dates:
        print(f"\\nDeferred retry pass for {len(failed_dates)} failed date(s)...")
        time.sleep(10)
        remaining=[]
        for ordinal,date in failed_dates:
            ok,row=process_one_date(ordinal,date,True)
            source_by_date[date.date().isoformat()]=row
            if not ok:
                remaining.append((ordinal,date))
        failed_dates=remaining

    source_ledger=pd.DataFrame(
        [source_by_date[d.date().isoformat()] for d in dates]
    )
    source_ledger.to_csv(SOURCE_LEDGER_PATH,index=False)

    failures=source_ledger[
        ~source_ledger["status"].isin(
            {"DOWNLOADED_PARSED_RAW_DELETED","REUSED_VALID_CACHE"}
        )
    ].copy()
    failures.to_csv(DOWNLOAD_FAILURES_PATH,index=False)

    if len(failures):
        listed=int(pd.to_numeric(
            failures["catalog_listed_flag"],errors="coerce"
        ).fillna(0).sum())
        print("\\n"+"="*128)
        print("H3 STAGE 3L — SOURCE ACQUISITION INCOMPLETE")
        print("="*128)
        print(f"Remaining failed dates: {len(failures)}")
        print(f"Catalog-listed failed dates: {listed}")
        print(f"Failure manifest: {DOWNLOAD_FAILURES_PATH}")
        print(
            "All successful daily caches are preserved. Rerun the same command "
            "later; only missing dates will be retried."
        )
        print("H3_FULL_GDELT_ATTENTION_EXTRACTION_INCOMPLETE_RETRY_REQUIRED")
        return

    yearly_paths=[]
    for year in range(2021,2026):
        year_dates=[d for d in dates if d.year==year]; print(f"Consolidating {year} ({len(year_dates)} daily caches)...")
        yearly_paths.append(consolidate_year(year,year_dates))
    print("Aggregating monthly security attention...")
    monthly=aggregate_monthly(yearly_paths); monthly["stage3j_manifest_sha256"]=manifest_sha; monthly["stage3l_protocol_sha256"]=protocol_sha; monthly.to_csv(MONTHLY_PATH,index=False)
    coverage=(monthly.groupby(["structural_ambiguity_tier","alias_selection_reason","authoritative_name_source_layer"],as_index=False)
              .agg(security_month_rows=("security_key","size"),unique_securities=("security_key","nunique"),nonzero_security_months=("strict_nonzero_month_flag","sum"),mean_attention_share=("attention_share","mean"),median_attention_share=("attention_share","median")))
    coverage["nonzero_security_month_rate"]=coverage["nonzero_security_months"]/coverage["security_month_rows"]; coverage.to_csv(COVERAGE_BY_CLASS_PATH,index=False)
    total_daily_rows=nonzero_daily_rows=0
    for path in yearly_paths:
        frame=pd.read_csv(path,usecols=["strict_nonzero_day_flag"],dtype=str,keep_default_na=False,compression="gzip"); flags=pd.to_numeric(frame["strict_nonzero_day_flag"],errors="raise")
        total_daily_rows+=len(frame); nonzero_daily_rows+=int(flags.sum())
    daily_nonzero_rate=nonzero_daily_rows/total_daily_rows if total_daily_rows else 0.0
    monthly_nonzero_rate=monthly["strict_nonzero_month_flag"].mean() if len(monthly) else 0.0
    lines=["="*128,"H3 STAGE 3L — FULL 2021-2025 DIRECT-GDELT ATTENTION EXTRACTION","="*128,f"Protocol ID: {config['protocol_id']}",f"Protocol SHA-256: {protocol_sha}",f"Stage 3J manifest SHA-256: {manifest_sha}",f"Calendar dates processed: {len(source_ledger)}",f"New source downloads this run: {downloaded_count}",f"Valid daily caches reused: {reused_count}",f"Unresolved source-download failures: 0",f"Daily security-attention rows: {total_daily_rows}",f"Monthly security-attention rows: {len(monthly)}",f"Monthly unique securities: {monthly['security_key'].nunique()}",f"Daily strict-nonzero rate: {daily_nonzero_rate:.6f}",f"Monthly strict-nonzero rate: {monthly_nonzero_rate:.6f}","","YEARLY DAILY SHARDS:"]
    lines += [f"  {p.name}" for p in yearly_paths]
    lines += ["","Raw daily GDELT zips retained: 0 after successful parse","Return/outcome fields read: 0","H3 inference performed: NO","","H3_FULL_GDELT_ATTENTION_EXTRACTION_COMPLETE"]
    report="\n".join(lines)+"\n"; REPORT_PATH.write_text(report,encoding="utf-8"); print(report,end="")


if __name__ == "__main__":
    main()
