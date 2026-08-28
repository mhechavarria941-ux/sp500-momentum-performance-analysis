from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

SCRIPT_VERSION = "2026-08-28-v1-h4-alpaca-sip-full-acquisition"
SYMBOL = "SPY"
FEED = "sip"
TIMEFRAME = "1Min"
ADJUSTMENT = "raw"
START_DATE = date(2021, 1, 1)
END_DATE = date(2025, 12, 31)
DATA_BASE_URL = "https://data.alpaca.markets"
CALENDAR_URL = "https://paper-api.alpaca.markets/v2/calendar"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
RAW_DIR = Path("data/raw/source/intraday/alpaca/spy_1min_sip")
CALENDAR_PATH = RAW_DIR / "alpaca_market_calendar_2021_2025.json"
MANIFEST_PATH = Path("data/interim/h4_spy_alpaca_1min_acquisition_manifest.json")
REPORT_PATH = Path("reports/data_quality/h4_spy_alpaca_1min_acquisition.txt")
SOURCE_GATE_JSON = Path("reports/data_quality/h4_alpaca_sip_source_feasibility.json")
REQUEST_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 6
PAGE_LIMIT = 10000


def credentials() -> tuple[str, str]:
    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in the local environment. "
            "Do not commit either value."
        )
    return key.strip(), secret.strip()


def auth_headers(key: str, secret: str) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def request_json(url: str, hdrs: dict[str, str], params: dict[str, Any]):
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After") or min(60, 2 ** attempt))
                print(f"  HTTP 429; retrying after {wait:.1f}s")
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                wait = min(60, 2 ** attempt)
                print(f"  HTTP {r.status_code}; retrying after {wait:.1f}s")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} for {r.url}: {r.text[:1000]}")
            return r.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(60, 2 ** attempt))
    raise RuntimeError(f"Request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_source_gate() -> None:
    if not SOURCE_GATE_JSON.exists():
        raise RuntimeError(f"Missing source-gate artifact: {SOURCE_GATE_JSON}")
    payload = json.loads(SOURCE_GATE_JSON.read_text(encoding="utf-8"))
    audits = payload.get("audits") or []
    expected = {"2021-01-04", "2022-06-15", "2023-10-02", "2024-03-15", "2025-12-31"}
    observed = {str(x.get("date")) for x in audits}
    if observed != expected or not all(bool(x.get("full_rth_coverage")) for x in audits):
        raise RuntimeError("Alpaca SIP source gate is not fully passed; acquisition is unauthorized.")
    print("PASS: Alpaca SIP source-gate artifact verified.")


def acquire_calendar(hdrs: dict[str, str]):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if CALENDAR_PATH.exists():
        rows = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        if isinstance(rows, list) and rows:
            print(f"Reusing existing calendar: {CALENDAR_PATH}")
            return rows
        raise RuntimeError("Existing calendar file is invalid.")
    rows = request_json(
        CALENDAR_URL,
        hdrs,
        {"start": START_DATE.isoformat(), "end": END_DATE.isoformat()},
    )
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Alpaca calendar returned no sessions.")
    CALENDAR_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Saved calendar: {CALENDAR_PATH}")
    return rows


def month_windows():
    out = []
    y, m = START_DATE.year, START_DATE.month
    while (y, m) <= (END_DATE.year, END_DATE.month):
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        out.append((max(start, START_DATE), min(end, END_DATE)))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return out


def query_bounds(start_day: date, end_day: date):
    start_et = datetime.combine(start_day, datetime.min.time(), tzinfo=ET)
    next_et = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=ET)
    start_utc = start_et.astimezone(UTC)
    end_utc = (next_et - timedelta(microseconds=1)).astimezone(UTC)
    return start_utc.isoformat().replace("+00:00", "Z"), end_utc.isoformat().replace("+00:00", "Z")


def monthly_path(start_day: date) -> Path:
    return RAW_DIR / f"spy_1min_sip_{start_day:%Y_%m}.json.gz"


def read_month(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def acquire_month(hdrs, start_day: date, end_day: date):
    path = monthly_path(start_day)
    if path.exists():
        payload = read_month(path)
        req = payload.get("request") or {}
        if (
            req.get("symbol") == SYMBOL
            and req.get("feed") == FEED
            and req.get("timeframe") == TIMEFRAME
            and req.get("adjustment") == ADJUSTMENT
            and req.get("start_date") == start_day.isoformat()
            and req.get("end_date") == end_day.isoformat()
        ):
            print(f"Reusing {path.name}: {len(payload.get('bars') or []):,} bars")
            return path, payload, False
        raise RuntimeError(f"Existing monthly file metadata mismatch: {path}")

    qstart, qend = query_bounds(start_day, end_day)
    url = f"{DATA_BASE_URL}/v2/stocks/{SYMBOL}/bars"
    bars = []
    page_token = None
    page_count = 0

    while True:
        params = {
            "timeframe": TIMEFRAME,
            "start": qstart,
            "end": qend,
            "limit": PAGE_LIMIT,
            "adjustment": ADJUSTMENT,
            "feed": FEED,
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token
        payload = request_json(url, hdrs, params)
        page = payload.get("bars") or []
        if not isinstance(page, list):
            raise RuntimeError("Alpaca 'bars' field is not a list.")
        bars.extend(page)
        page_count += 1
        page_token = payload.get("next_page_token")
        if not page_token:
            break

    out = {
        "script_version": SCRIPT_VERSION,
        "downloaded_utc": datetime.now(tz=UTC).isoformat(),
        "request": {
            "symbol": SYMBOL,
            "feed": FEED,
            "timeframe": TIMEFRAME,
            "adjustment": ADJUSTMENT,
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "query_start_utc": qstart,
            "query_end_utc": qend,
            "sort": "asc",
            "page_limit": PAGE_LIMIT,
        },
        "provider_page_count": page_count,
        "bar_count": len(bars),
        "bars": bars,
    }
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Downloaded {path.name}: {len(bars):,} bars across {page_count} page(s)")
    return path, out, True


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 110)
    print("H4 SPY ALPACA SIP FULL 1-MINUTE ACQUISITION — PRE-OUTCOME")
    print("=" * 110)
    print("H4 event triggers calculated: NO")
    print("H4 forward outcomes calculated: NO")
    print()

    verify_source_gate()
    key, secret = credentials()
    hdrs = auth_headers(key, secret)
    calendar = acquire_calendar(hdrs)
    windows = month_windows()
    manifest_rows = []
    new_files = 0

    for i, (start_day, end_day) in enumerate(windows, start=1):
        print(f"[{i:02d}/{len(windows):02d}] {start_day:%Y-%m}")
        path, payload, was_new = acquire_month(hdrs, start_day, end_day)
        new_files += int(was_new)
        manifest_rows.append({
            "month": start_day.strftime("%Y-%m"),
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "file": str(path).replace("\\", "/"),
            "sha256": sha256_file(path),
            "bar_count": int(payload.get("bar_count", len(payload.get("bars") or []))),
            "provider_page_count": int(payload.get("provider_page_count", 0)),
        })

    manifest = {
        "script_version": SCRIPT_VERSION,
        "symbol": SYMBOL,
        "feed": FEED,
        "timeframe": TIMEFRAME,
        "adjustment": ADJUSTMENT,
        "study_start": START_DATE.isoformat(),
        "study_end": END_DATE.isoformat(),
        "calendar_file": str(CALENDAR_PATH).replace("\\", "/"),
        "calendar_sha256": sha256_file(CALENDAR_PATH),
        "calendar_sessions": len(calendar),
        "monthly_files": len(manifest_rows),
        "new_monthly_files_this_run": new_files,
        "total_raw_bars": sum(x["bar_count"] for x in manifest_rows),
        "months": manifest_rows,
        "h4_event_triggers_calculated": False,
        "h4_forward_outcomes_calculated": False,
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = "\n".join([
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 110,
        "H4 SPY ALPACA SIP FULL 1-MINUTE ACQUISITION",
        "=" * 110,
        f"Study interval: {START_DATE} through {END_DATE}",
        f"Calendar sessions: {len(calendar):,}",
        f"Monthly raw files: {len(manifest_rows):,}",
        f"New monthly files this run: {new_files:,}",
        f"Total raw bars: {manifest['total_raw_bars']:,}",
        f"Feed: {FEED}",
        f"Adjustment: {ADJUSTMENT}",
        "H4 event triggers calculated: NO",
        "H4 forward outcomes calculated: NO",
        "",
        "No analytical-use authorization is granted until the independent minute-history audit passes.",
        "",
        "H4_ALPACA_SIP_FULL_ACQUISITION_COMPLETE",
    ]) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
