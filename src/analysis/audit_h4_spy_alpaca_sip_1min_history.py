from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPT_VERSION = "2026-08-28-v1-h4-alpaca-sip-minute-integrity-audit"
RAW_DIR = Path("data/raw/source/intraday/alpaca/spy_1min_sip")
CALENDAR_PATH = RAW_DIR / "alpaca_market_calendar_2021_2025.json"
MANIFEST_PATH = Path("data/interim/h4_spy_alpaca_1min_acquisition_manifest.json")
OUTPUT_DATA_PATH = Path("data/interim/h4_spy_1min_sip_2021_2025.csv.gz")
OUTPUT_AUDIT_PATH = Path("reports/data_quality/h4_spy_1min_sip_integrity_audit.txt")
OUTPUT_MANIFEST_PATH = Path("data/interim/h4_spy_1min_sip_standardized_manifest.json")
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
EXPECTED_MONTHS = 60
EXPECTED_START = "2021-01"
EXPECTED_END = "2025-12"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_calendar_time(session_date: str, hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":")[:2])
    d = datetime.fromisoformat(session_date)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=ET)


def minute_range(start: datetime, end_exclusive: datetime):
    t = start
    while t < end_exclusive:
        yield t
        t += timedelta(minutes=1)


def load_calendar() -> dict[str, dict[str, Any]]:
    if not CALENDAR_PATH.exists():
        raise RuntimeError(f"Missing calendar: {CALENDAR_PATH}")
    rows = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Calendar JSON is invalid.")
    sessions = {}
    for row in rows:
        d = str(row.get("date") or "")
        o = str(row.get("open") or "")
        c = str(row.get("close") or "")
        if not d or not o or not c:
            raise RuntimeError(f"Calendar row missing date/open/close: {row}")
        if d in sessions:
            raise RuntimeError(f"Duplicate calendar date: {d}")
        sessions[d] = row
    return sessions


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise RuntimeError(f"Missing acquisition manifest: {MANIFEST_PATH}")
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rows = m.get("months") or []
    months = [str(x.get("month")) for x in rows]
    if len(rows) != EXPECTED_MONTHS:
        raise RuntimeError("Acquisition manifest does not contain exactly 60 monthly files.")
    if not months or months[0] != EXPECTED_START or months[-1] != EXPECTED_END:
        raise RuntimeError("Acquisition manifest does not span 2021-01 through 2025-12.")
    return m


def num(x: Any, name: str, context: str) -> float:
    if x is None:
        raise RuntimeError(f"Missing {name} at {context}")
    v = float(x)
    if not math.isfinite(v):
        raise RuntimeError(f"Non-finite {name} at {context}: {x}")
    return v


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 120)
    print("H4 SPY ALPACA SIP 1-MINUTE INTEGRITY AUDIT — PRE-OUTCOME")
    print("=" * 120)
    print("H4 event triggers calculated: NO")
    print("H4 forward outcomes calculated: NO")
    print()

    calendar = load_calendar()
    manifest = load_manifest()
    if str(manifest.get("calendar_sha256")) != sha256_file(CALENDAR_PATH):
        raise RuntimeError("Calendar SHA-256 no longer matches acquisition manifest.")

    failures: list[str] = []
    observed: dict[datetime, dict[str, Any]] = {}
    raw_bar_count = 0
    rth_bar_count = 0
    duplicate_timestamps = 0
    invalid_ohlc = 0
    invalid_volume = 0
    missing_vwap = 0
    invalid_transactions = 0

    month_rows = manifest.get("months") or []
    for i, rec in enumerate(month_rows, start=1):
        path = Path(str(rec["file"]))
        print(f"[{i:02d}/{EXPECTED_MONTHS:02d}] Auditing {path.name}")
        if not path.exists():
            failures.append(f"Missing monthly raw file: {path}")
            continue
        if sha256_file(path) != str(rec.get("sha256")):
            failures.append(f"SHA-256 mismatch: {path}")
            continue
        with gzip.open(path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
        bars = payload.get("bars") or []
        raw_bar_count += len(bars)
        if len(bars) != int(rec.get("bar_count", -1)):
            failures.append(f"Bar-count mismatch: {path}")

        for bar in bars:
            ts_raw = bar.get("t")
            if ts_raw is None:
                failures.append(f"Missing timestamp in {path}")
                continue
            ts_utc = parse_rfc3339(str(ts_raw)).astimezone(UTC)
            ts_et = ts_utc.astimezone(ET)
            session_date = ts_et.date().isoformat()
            session = calendar.get(session_date)
            if session is None:
                continue
            open_et = parse_calendar_time(session_date, str(session["open"]))
            close_et = parse_calendar_time(session_date, str(session["close"]))
            if not (open_et <= ts_et < close_et):
                continue
            rth_bar_count += 1

            if ts_et in observed:
                duplicate_timestamps += 1
                failures.append(f"Duplicate RTH timestamp: {ts_et.isoformat()}")
                continue

            context = ts_et.isoformat()
            try:
                o = num(bar.get("o"), "open", context)
                h = num(bar.get("h"), "high", context)
                l = num(bar.get("l"), "low", context)
                c = num(bar.get("c"), "close", context)
                v = num(bar.get("v"), "volume", context)
            except RuntimeError as exc:
                failures.append(str(exc))
                continue

            if min(o, h, l, c) <= 0 or h < max(o, l, c) or l > min(o, h, c):
                invalid_ohlc += 1
                failures.append(f"Invalid OHLC at {context}")
            if v <= 0:
                invalid_volume += 1
                failures.append(f"Nonpositive volume at {context}")

            vw = bar.get("vw")
            n = bar.get("n")
            if vw is None:
                missing_vwap += 1
            elif not math.isfinite(float(vw)) or float(vw) <= 0:
                failures.append(f"Invalid VWAP at {context}")
            if n is None or int(n) <= 0:
                invalid_transactions += 1
                failures.append(f"Missing/nonpositive transaction count at {context}")

            observed[ts_et] = {
                "timestamp_utc": ts_utc,
                "timestamp_et": ts_et,
                "session_date": session_date,
                "session_open_et": open_et,
                "session_close_et": close_et,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
                "vwap": None if vw is None else float(vw),
                "transactions": None if n is None else int(n),
            }

    expected: set[datetime] = set()
    early_close_sessions = 0
    for session_date, session in sorted(calendar.items()):
        open_et = parse_calendar_time(session_date, str(session["open"]))
        close_et = parse_calendar_time(session_date, str(session["close"]))
        mins = list(minute_range(open_et, close_et))
        expected.update(mins)
        if len(mins) < 390:
            early_close_sessions += 1

    observed_set = set(observed)
    missing_expected = sorted(expected - observed_set)
    extra_observed = sorted(observed_set - expected)
    for ts in missing_expected[:50]:
        failures.append(f"Missing expected RTH minute: {ts.isoformat()}")
    for ts in extra_observed[:50]:
        failures.append(f"Unexpected RTH minute: {ts.isoformat()}")

    passed = (
        not failures
        and duplicate_timestamps == 0
        and invalid_ohlc == 0
        and invalid_volume == 0
        and len(missing_expected) == 0
        and len(extra_observed) == 0
        and len(observed) == len(expected)
    )

    OUTPUT_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    report_lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 120,
        "H4 SPY ALPACA SIP 1-MINUTE INTEGRITY AUDIT",
        "=" * 120,
        f"Calendar sessions: {len(calendar):,}",
        f"Early-close sessions: {early_close_sessions:,}",
        f"Expected RTH minutes: {len(expected):,}",
        f"Observed unique RTH minutes: {len(observed):,}",
        f"Raw provider bars: {raw_bar_count:,}",
        f"RTH provider bars examined: {rth_bar_count:,}",
        f"Missing expected RTH minutes: {len(missing_expected):,}",
        f"Unexpected RTH minutes: {len(extra_observed):,}",
        f"Duplicate RTH timestamps: {duplicate_timestamps:,}",
        f"Invalid OHLC rows: {invalid_ohlc:,}",
        f"Invalid/nonpositive volume rows: {invalid_volume:,}",
        f"Missing provider VWAP rows: {missing_vwap:,}",
        f"Missing/invalid transaction-count rows: {invalid_transactions:,}",
        "H4 event triggers calculated: NO",
        "H4 forward outcomes calculated: NO",
        "",
        f"FINAL INTRADAY MINUTE-HISTORY QUALITY GATE: {'PASS' if passed else 'FAIL'}",
    ]

    if failures:
        report_lines += ["", "FAILURE SAMPLE:"] + [f"- {x}" for x in failures[:100]]
        OUTPUT_AUDIT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        print("\n" + OUTPUT_AUDIT_PATH.read_text(encoding="utf-8"))
        sys.exit(2)

    fields = [
        "timestamp_utc", "timestamp_et", "session_date", "session_open_et", "session_close_et",
        "open", "high", "low", "close", "volume", "vwap", "transactions",
    ]
    with gzip.open(OUTPUT_DATA_PATH, "wt", encoding="utf-8", newline="") as gz:
        w = csv.DictWriter(gz, fieldnames=fields)
        w.writeheader()
        for ts in sorted(observed):
            r = observed[ts]
            w.writerow({
                "timestamp_utc": r["timestamp_utc"].isoformat(),
                "timestamp_et": r["timestamp_et"].isoformat(),
                "session_date": r["session_date"],
                "session_open_et": r["session_open_et"].isoformat(),
                "session_close_et": r["session_close_et"].isoformat(),
                "open": f"{r['open']:.12g}",
                "high": f"{r['high']:.12g}",
                "low": f"{r['low']:.12g}",
                "close": f"{r['close']:.12g}",
                "volume": f"{r['volume']:.12g}",
                "vwap": "" if r["vwap"] is None else f"{r['vwap']:.12g}",
                "transactions": "" if r["transactions"] is None else str(r["transactions"]),
            })

    standardized_manifest = {
        "script_version": SCRIPT_VERSION,
        "source_acquisition_manifest": str(MANIFEST_PATH).replace("\\", "/"),
        "source_acquisition_manifest_sha256": sha256_file(MANIFEST_PATH),
        "calendar_file": str(CALENDAR_PATH).replace("\\", "/"),
        "calendar_sha256": sha256_file(CALENDAR_PATH),
        "canonical_output": str(OUTPUT_DATA_PATH).replace("\\", "/"),
        "canonical_output_sha256": sha256_file(OUTPUT_DATA_PATH),
        "calendar_sessions": len(calendar),
        "early_close_sessions": early_close_sessions,
        "expected_rth_minutes": len(expected),
        "canonical_rows": len(observed),
        "provider_vwap_missing_rows": missing_vwap,
        "provider_transaction_count_missing_or_invalid_rows": invalid_transactions,
        "h4_event_triggers_calculated": False,
        "h4_forward_outcomes_calculated": False,
    }
    OUTPUT_MANIFEST_PATH.write_text(json.dumps(standardized_manifest, indent=2), encoding="utf-8")

    report_lines += [
        "",
        f"Canonical RTH output: {OUTPUT_DATA_PATH}",
        f"Canonical RTH rows: {len(observed):,}",
        f"Canonical output SHA-256: {standardized_manifest['canonical_output_sha256']}",
        "",
        "H4_SPY_ALPACA_SIP_MINUTE_HISTORY_INTEGRITY_AUDIT_PASSED",
        "H4_5MIN_LOCATION_LAYER_CONSTRUCTION_AUTHORIZED",
    ]
    OUTPUT_AUDIT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n" + OUTPUT_AUDIT_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
