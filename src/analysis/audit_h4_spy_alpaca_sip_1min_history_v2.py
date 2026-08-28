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

SCRIPT_VERSION = "2026-08-28-v2-h4-alpaca-sip-minute-integrity-audit-exception-policy"

RAW_DIR = Path("data/raw/source/intraday/alpaca/spy_1min_sip")
CALENDAR_PATH = RAW_DIR / "alpaca_market_calendar_2021_2025.json"
ACQUISITION_MANIFEST_PATH = Path(
    "data/interim/h4_spy_alpaca_1min_acquisition_manifest.json"
)
EXCEPTION_POLICY_PATH = Path(
    "data/reference/h4/h4_intraday_data_exceptions_v1.json"
)

OUTPUT_DATA_PATH = Path(
    "data/interim/h4_spy_1min_sip_2021_2025_primary_eligible.csv.gz"
)
OUTPUT_AUDIT_PATH = Path(
    "reports/data_quality/h4_spy_1min_sip_integrity_audit_v2.txt"
)
OUTPUT_MANIFEST_PATH = Path(
    "data/interim/h4_spy_1min_sip_primary_eligible_manifest.json"
)

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

EXPECTED_MONTHS = 60
EXPECTED_EXCEPTION_DATES = {"2021-05-05", "2023-06-05"}


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


def iter_expected_minutes(start: datetime, end_exclusive: datetime):
    t = start
    while t < end_exclusive:
        yield t
        t += timedelta(minutes=1)


def validate_number(x: Any, name: str, context: str) -> float:
    if x is None:
        raise RuntimeError(f"Missing {name} at {context}")
    v = float(x)
    if not math.isfinite(v):
        raise RuntimeError(f"Non-finite {name} at {context}: {x}")
    return v


def load_json(path: Path) -> Any:
    if not path.exists():
        raise RuntimeError(f"Missing required input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("H4 SPY ALPACA SIP 1-MINUTE INTEGRITY AUDIT V2 — FROZEN EXCEPTION POLICY")
    print("=" * 124)
    print("H4 event triggers calculated: NO")
    print("H4 forward-return outcomes calculated: NO")
    print()

    calendar_rows = load_json(CALENDAR_PATH)
    acquisition_manifest = load_json(ACQUISITION_MANIFEST_PATH)
    exception_policy = load_json(EXCEPTION_POLICY_PATH)

    if not isinstance(calendar_rows, list) or not calendar_rows:
        raise RuntimeError("Invalid Alpaca market calendar.")

    if int(acquisition_manifest.get("monthly_files", -1)) != EXPECTED_MONTHS:
        raise RuntimeError("Acquisition manifest must contain exactly 60 monthly files.")

    if str(exception_policy.get("version")) != "H4_INTRADAY_DATA_EXCEPTIONS_V1":
        raise RuntimeError("Unexpected H4 exception-policy version.")

    policy_exceptions = exception_policy.get("exceptions") or []
    exception_dates = {
        str(x.get("session_date"))
        for x in policy_exceptions
        if bool(x.get("exclude_entire_session"))
    }

    if exception_dates != EXPECTED_EXCEPTION_DATES:
        raise RuntimeError(
            f"Frozen exception dates changed. Expected {sorted(EXPECTED_EXCEPTION_DATES)}, "
            f"found {sorted(exception_dates)}."
        )

    if any(bool(x.get("reconstruction_authorized")) for x in policy_exceptions):
        raise RuntimeError("Frozen exception policy unexpectedly authorizes reconstruction.")

    calendar = {}
    for row in calendar_rows:
        d = str(row.get("date") or "")
        if not d:
            raise RuntimeError("Calendar row missing date.")
        if d in calendar:
            raise RuntimeError(f"Duplicate calendar date: {d}")
        calendar[d] = row

    month_rows = acquisition_manifest.get("months") or []
    if len(month_rows) != EXPECTED_MONTHS:
        raise RuntimeError("Unexpected monthly acquisition-manifest population.")

    observed: dict[datetime, dict[str, Any]] = {}
    duplicate_timestamps = 0
    invalid_ohlc = 0
    invalid_volume = 0
    missing_vwap = 0
    invalid_transactions = 0
    raw_bar_count = 0
    rth_bar_count = 0
    failures: list[str] = []

    for i, rec in enumerate(month_rows, start=1):
        path = Path(str(rec["file"]))
        print(f"[{i:02d}/{EXPECTED_MONTHS:02d}] Auditing {path.name}")

        if not path.exists():
            failures.append(f"Missing monthly raw file: {path}")
            continue

        expected_sha = str(rec.get("sha256") or "")
        actual_sha = sha256_file(path)
        if expected_sha != actual_sha:
            failures.append(f"SHA-256 mismatch: {path}")
            continue

        with gzip.open(path, "rt", encoding="utf-8") as f:
            payload = json.load(f)

        bars = payload.get("bars") or []
        raw_bar_count += len(bars)

        if len(bars) != int(rec.get("bar_count", -1)):
            failures.append(
                f"Bar-count mismatch for {path}: "
                f"manifest={rec.get('bar_count')} actual={len(bars)}"
            )

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
                o = validate_number(bar.get("o"), "open", context)
                h = validate_number(bar.get("h"), "high", context)
                l = validate_number(bar.get("l"), "low", context)
                c = validate_number(bar.get("c"), "close", context)
                v = validate_number(bar.get("v"), "volume", context)
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
            else:
                vw_v = float(vw)
                if not math.isfinite(vw_v) or vw_v <= 0:
                    failures.append(f"Invalid VWAP at {context}")

            if n is None:
                invalid_transactions += 1
            else:
                n_v = int(n)
                if n_v <= 0:
                    invalid_transactions += 1
                    failures.append(f"Nonpositive transaction count at {context}")

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

    expected_all: set[datetime] = set()
    expected_exception: set[datetime] = set()
    expected_primary: set[datetime] = set()

    early_close_sessions = 0
    primary_sessions = 0

    for session_date, session in sorted(calendar.items()):
        open_et = parse_calendar_time(session_date, str(session["open"]))
        close_et = parse_calendar_time(session_date, str(session["close"]))
        session_minutes = set(iter_expected_minutes(open_et, close_et))

        expected_all.update(session_minutes)

        if len(session_minutes) < 390:
            early_close_sessions += 1

        if session_date in exception_dates:
            expected_exception.update(session_minutes)
        else:
            expected_primary.update(session_minutes)
            primary_sessions += 1

    observed_set = set(observed)

    missing_all = sorted(expected_all - observed_set)
    missing_primary = sorted(expected_primary - observed_set)
    unexpected_all = sorted(observed_set - expected_all)

    missing_exception = sorted(set(missing_all) & expected_exception)
    unexplained_missing = sorted(set(missing_all) - expected_exception)

    # Freeze the exact original missing population.
    expected_original_missing = {
        datetime(2021, 5, 5, 11, 27, tzinfo=ET),
        datetime(2021, 5, 5, 11, 28, tzinfo=ET),
        datetime(2021, 5, 5, 11, 29, tzinfo=ET),
        datetime(2021, 5, 5, 11, 30, tzinfo=ET),
        datetime(2021, 5, 5, 11, 31, tzinfo=ET),
        datetime(2023, 6, 5, 9, 52, tzinfo=ET),
        datetime(2023, 6, 5, 9, 53, tzinfo=ET),
        datetime(2023, 6, 5, 9, 54, tzinfo=ET),
        datetime(2023, 6, 5, 9, 55, tzinfo=ET),
    }

    if set(missing_all) != expected_original_missing:
        failures.append(
            "Current raw-data missing-minute population no longer equals the frozen "
            "nine-minute exception population."
        )

    if unexplained_missing:
        for ts in unexplained_missing[:50]:
            failures.append(
                f"Unexplained missing minute outside frozen exception sessions: "
                f"{ts.isoformat()}"
            )

    if missing_primary:
        for ts in missing_primary[:50]:
            failures.append(
                f"Missing minute in primary-eligible session: {ts.isoformat()}"
            )

    if unexpected_all:
        for ts in unexpected_all[:50]:
            failures.append(f"Unexpected RTH minute: {ts.isoformat()}")

    primary_observed = {
        ts: row
        for ts, row in observed.items()
        if row["session_date"] not in exception_dates
    }

    passed = (
        not failures
        and duplicate_timestamps == 0
        and invalid_ohlc == 0
        and invalid_volume == 0
        and len(missing_primary) == 0
        and len(unexplained_missing) == 0
        and len(unexpected_all) == 0
        and set(primary_observed) == expected_primary
    )

    report_lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 124,
        "H4 SPY ALPACA SIP 1-MINUTE INTEGRITY AUDIT V2 — FROZEN EXCEPTION POLICY",
        "=" * 124,
        f"Calendar sessions: {len(calendar):,}",
        f"Frozen excluded infrastructure-exception sessions: {len(exception_dates):,}",
        f"Primary-eligible sessions: {primary_sessions:,}",
        f"Early-close sessions in complete calendar: {early_close_sessions:,}",
        f"Expected RTH minutes, all sessions: {len(expected_all):,}",
        f"Observed unique RTH minutes, all sessions: {len(observed):,}",
        f"Frozen missing minutes, all sessions: {len(missing_all):,}",
        f"Missing minutes inside frozen exception sessions: {len(missing_exception):,}",
        f"Unexplained missing minutes outside exception sessions: {len(unexplained_missing):,}",
        f"Expected primary-eligible RTH minutes: {len(expected_primary):,}",
        f"Observed primary-eligible RTH minutes: {len(primary_observed):,}",
        f"Missing primary-eligible minutes: {len(missing_primary):,}",
        f"Unexpected RTH minutes: {len(unexpected_all):,}",
        f"Duplicate RTH timestamps: {duplicate_timestamps:,}",
        f"Invalid OHLC rows: {invalid_ohlc:,}",
        f"Invalid/nonpositive volume rows: {invalid_volume:,}",
        f"Missing provider VWAP rows: {missing_vwap:,}",
        f"Missing/invalid transaction-count rows: {invalid_transactions:,}",
        "H4 event triggers calculated: NO",
        "H4 forward-return outcomes calculated: NO",
        "",
        "Frozen exception sessions:",
    ]

    for d in sorted(exception_dates):
        report_lines.append(f"- {d}")

    report_lines.extend(
        [
            "",
            f"FINAL PRIMARY-ELIGIBLE MINUTE-HISTORY QUALITY GATE: "
            f"{'PASS' if passed else 'FAIL'}",
        ]
    )

    if failures:
        report_lines.extend(["", "FAILURE SAMPLE:"])
        report_lines.extend(f"- {x}" for x in failures[:100])

    OUTPUT_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not passed:
        OUTPUT_AUDIT_PATH.write_text(
            "\n".join(report_lines) + "\n",
            encoding="utf-8",
        )
        print()
        print(OUTPUT_AUDIT_PATH.read_text(encoding="utf-8"))
        sys.exit(2)

    fieldnames = [
        "timestamp_utc",
        "timestamp_et",
        "session_date",
        "session_open_et",
        "session_close_et",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "transactions",
    ]

    with gzip.open(OUTPUT_DATA_PATH, "wt", encoding="utf-8", newline="") as gz:
        writer = csv.DictWriter(gz, fieldnames=fieldnames)
        writer.writeheader()

        for ts in sorted(primary_observed):
            row = primary_observed[ts]
            writer.writerow(
                {
                    "timestamp_utc": row["timestamp_utc"].isoformat(),
                    "timestamp_et": row["timestamp_et"].isoformat(),
                    "session_date": row["session_date"],
                    "session_open_et": row["session_open_et"].isoformat(),
                    "session_close_et": row["session_close_et"].isoformat(),
                    "open": f"{row['open']:.12g}",
                    "high": f"{row['high']:.12g}",
                    "low": f"{row['low']:.12g}",
                    "close": f"{row['close']:.12g}",
                    "volume": f"{row['volume']:.12g}",
                    "vwap": "" if row["vwap"] is None else f"{row['vwap']:.12g}",
                    "transactions": "" if row["transactions"] is None else str(row["transactions"]),
                }
            )

    output_manifest = {
        "script_version": SCRIPT_VERSION,
        "exception_policy": str(EXCEPTION_POLICY_PATH).replace("\\", "/"),
        "exception_policy_sha256": sha256_file(EXCEPTION_POLICY_PATH),
        "source_acquisition_manifest": str(ACQUISITION_MANIFEST_PATH).replace("\\", "/"),
        "source_acquisition_manifest_sha256": sha256_file(ACQUISITION_MANIFEST_PATH),
        "calendar_file": str(CALENDAR_PATH).replace("\\", "/"),
        "calendar_sha256": sha256_file(CALENDAR_PATH),
        "canonical_primary_eligible_output": str(OUTPUT_DATA_PATH).replace("\\", "/"),
        "canonical_primary_eligible_output_sha256": sha256_file(OUTPUT_DATA_PATH),
        "calendar_sessions": len(calendar),
        "excluded_exception_sessions": sorted(exception_dates),
        "primary_eligible_sessions": primary_sessions,
        "expected_all_rth_minutes": len(expected_all),
        "observed_all_rth_minutes": len(observed),
        "frozen_missing_minutes": len(missing_all),
        "expected_primary_eligible_rth_minutes": len(expected_primary),
        "canonical_primary_eligible_rows": len(primary_observed),
        "provider_vwap_missing_rows": missing_vwap,
        "provider_transaction_count_missing_or_invalid_rows": invalid_transactions,
        "h4_event_triggers_calculated": False,
        "h4_forward_outcomes_calculated": False,
    }

    OUTPUT_MANIFEST_PATH.write_text(
        json.dumps(output_manifest, indent=2),
        encoding="utf-8",
    )

    report_lines.extend(
        [
            "",
            f"Primary-eligible canonical output: {OUTPUT_DATA_PATH}",
            f"Primary-eligible canonical rows: {len(primary_observed):,}",
            f"Canonical output SHA-256: "
            f"{output_manifest['canonical_primary_eligible_output_sha256']}",
            "",
            "H4_SPY_ALPACA_SIP_PRIMARY_ELIGIBLE_MINUTE_HISTORY_AUDIT_PASSED",
            "H4_5MIN_LOCATION_LAYER_CONSTRUCTION_AUTHORIZED",
        ]
    )

    OUTPUT_AUDIT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print(OUTPUT_AUDIT_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
