from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

SCRIPT_VERSION = "2026-08-26-v2-h4-alpaca-sip-source-feasibility"
SYMBOL = "SPY"
BASE_URL = "https://data.alpaca.markets"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

SAMPLE_DATES = [
    "2021-01-04",
    "2022-06-15",
    "2023-10-02",
    "2024-03-15",
    "2025-12-31",
]

OUTPUT_PATH = Path("reports/data_quality/h4_alpaca_sip_source_feasibility.txt")
JSON_OUTPUT_PATH = Path("reports/data_quality/h4_alpaca_sip_source_feasibility.json")

EXPECTED_FULL_RTH_MINUTES = 390
REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 4


@dataclass
class DayAudit:
    date: str
    http_status: int | None
    result_count: int
    rth_count: int
    duplicate_timestamps: int
    invalid_ohlc: int
    nonpositive_volume: int
    missing_volume: int
    missing_vwap: int
    missing_transactions: int
    first_rth_et: str | None
    last_rth_et: str | None
    access_ok: bool
    full_rth_coverage: bool
    message: str


def get_credentials() -> tuple[str, str]:
    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")

    if not key or not secret:
        raise RuntimeError(
            "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in the project "
            "environment before running this probe. Do not commit either value."
        )

    return key.strip(), secret.strip()


def request_day(
    api_key: str,
    api_secret: str,
    date_str: str,
) -> tuple[int, dict[str, Any]]:
    url = f"{BASE_URL}/v2/stocks/{SYMBOL}/bars"
    params = {
        "timeframe": "1Min",
        "start": f"{date_str}T00:00:00-05:00",
        "end": f"{date_str}T23:59:59-05:00",
        "limit": 10000,
        "adjustment": "raw",
        "feed": "sip",
        "sort": "asc",
    }
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }

    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            status = response.status_code
            try:
                payload = response.json()
            except Exception:
                payload = {
                    "message": "NON_JSON_RESPONSE",
                    "raw_prefix": response.text[:500],
                }
            return status, payload
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Request failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def parse_alpaca_timestamp(value: str) -> datetime:
    # Alpaca returns RFC3339 timestamps, often ending in Z.
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ET)


def is_regular_session_minute(ts_et: datetime) -> bool:
    # Probe dates are ordinary full sessions.
    # Production acquisition must use an official exchange calendar so
    # early-close sessions are not incorrectly forced to 390 minutes.
    tod = ts_et.timetz().replace(tzinfo=None)
    return dt_time(9, 30) <= tod < dt_time(16, 0)


def audit_day(
    date_str: str,
    status: int,
    payload: dict[str, Any],
) -> DayAudit:
    if status != 200:
        msg = str(
            payload.get("message")
            or payload.get("error")
            or payload
        )
        return DayAudit(
            date=date_str,
            http_status=status,
            result_count=0,
            rth_count=0,
            duplicate_timestamps=0,
            invalid_ohlc=0,
            nonpositive_volume=0,
            missing_volume=0,
            missing_vwap=0,
            missing_transactions=0,
            first_rth_et=None,
            last_rth_et=None,
            access_ok=False,
            full_rth_coverage=False,
            message=msg[:500],
        )

    rows = payload.get("bars") or []
    rth_rows = []
    timestamps: list[str] = []

    invalid_ohlc = 0
    nonpositive_volume = 0
    missing_volume = 0
    missing_vwap = 0
    missing_transactions = 0

    for row in rows:
        ts_raw = row.get("t")
        if ts_raw is None:
            continue

        ts_et = parse_alpaca_timestamp(str(ts_raw))
        if not is_regular_session_minute(ts_et):
            continue

        rth_rows.append(row)
        timestamps.append(str(ts_raw))

        o = row.get("o")
        h = row.get("h")
        l = row.get("l")
        c = row.get("c")
        v = row.get("v")

        if None in (o, h, l, c):
            invalid_ohlc += 1
        else:
            o = float(o)
            h = float(h)
            l = float(l)
            c = float(c)
            if (
                h < max(o, l, c)
                or l > min(o, h, c)
                or min(o, h, l, c) <= 0
            ):
                invalid_ohlc += 1

        if v is None:
            missing_volume += 1
        elif float(v) <= 0:
            nonpositive_volume += 1

        if row.get("vw") is None:
            missing_vwap += 1

        if row.get("n") is None:
            missing_transactions += 1

    duplicate_timestamps = len(timestamps) - len(set(timestamps))
    unique_times = sorted(
        {parse_alpaca_timestamp(ts) for ts in timestamps}
    )

    full_rth_coverage = (
        len(unique_times) == EXPECTED_FULL_RTH_MINUTES
        and duplicate_timestamps == 0
        and invalid_ohlc == 0
        and missing_volume == 0
        and nonpositive_volume == 0
        and bool(unique_times)
        and unique_times[0].strftime("%H:%M") == "09:30"
        and unique_times[-1].strftime("%H:%M") == "15:59"
    )

    return DayAudit(
        date=date_str,
        http_status=status,
        result_count=len(rows),
        rth_count=len(rth_rows),
        duplicate_timestamps=duplicate_timestamps,
        invalid_ohlc=invalid_ohlc,
        nonpositive_volume=nonpositive_volume,
        missing_volume=missing_volume,
        missing_vwap=missing_vwap,
        missing_transactions=missing_transactions,
        first_rth_et=unique_times[0].isoformat() if unique_times else None,
        last_rth_et=unique_times[-1].isoformat() if unique_times else None,
        access_ok=True,
        full_rth_coverage=full_rth_coverage,
        message="OK",
    )


def render_report(audits: list[DayAudit]) -> str:
    all_access = all(a.access_ok for a in audits)
    all_full = all(a.full_rth_coverage for a in audits)
    volume_ok = all(
        a.missing_volume == 0 and a.nonpositive_volume == 0
        for a in audits
    )
    ohlc_ok = all(a.invalid_ohlc == 0 for a in audits)
    unique_ok = all(a.duplicate_timestamps == 0 for a in audits)

    vwap_available_everywhere = all(
        a.missing_vwap == 0 for a in audits
    )
    txn_available_everywhere = all(
        a.missing_transactions == 0 for a in audits
    )

    gate_pass = (
        all_access
        and all_full
        and volume_ok
        and ohlc_ok
        and unique_ok
    )

    lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 110,
        "H4 ALPACA SIP HISTORICAL-MINUTE SOURCE FEASIBILITY",
        "=" * 110,
        f"Symbol: {SYMBOL}",
        f"Candidate source API: {BASE_URL}",
        "Requested feed: sip",
        "Requested bar: 1 minute",
        "Adjustment: raw",
        "Primary analytical target after approval: 5-minute bars derived from 1-minute data",
        "Primary session: regular U.S. equity session",
        "",
        "IMPORTANT:",
        "This probe inspects source structure and historical coverage only.",
        "It does NOT calculate post-trigger H4 forward returns or test any H4 hypothesis.",
        "",
    ]

    for a in audits:
        lines.extend([
            "-" * 110,
            f"Date: {a.date}",
            f"HTTP status: {a.http_status}",
            f"Total API bars: {a.result_count:,}",
            f"RTH bars: {a.rth_count:,} / expected {EXPECTED_FULL_RTH_MINUTES}",
            f"First RTH timestamp ET: {a.first_rth_et}",
            f"Last RTH timestamp ET: {a.last_rth_et}",
            f"Duplicate RTH timestamps: {a.duplicate_timestamps}",
            f"Invalid OHLC rows: {a.invalid_ohlc}",
            f"Missing volume rows: {a.missing_volume}",
            f"Nonpositive volume rows: {a.nonpositive_volume}",
            f"Missing provider VWAP rows: {a.missing_vwap}",
            f"Missing transaction-count rows: {a.missing_transactions}",
            f"Historical SIP access: {'PASS' if a.access_ok else 'FAIL'}",
            f"Full ordinary-session coverage: {'PASS' if a.full_rth_coverage else 'FAIL'}",
            f"Source message: {a.message}",
        ])

    lines.extend([
        "",
        "=" * 110,
        "SOURCE GATE SUMMARY",
        "=" * 110,
        f"Historical SIP access across all sample years: {'PASS' if all_access else 'FAIL'}",
        f"Full 390-minute RTH coverage on all probe dates: {'PASS' if all_full else 'FAIL'}",
        f"OHLC integrity: {'PASS' if ohlc_ok else 'FAIL'}",
        f"Volume integrity: {'PASS' if volume_ok else 'FAIL'}",
        f"Timestamp uniqueness: {'PASS' if unique_ok else 'FAIL'}",
        f"Provider minute VWAP present on all probe RTH rows: {'YES' if vwap_available_everywhere else 'NO / REVIEW'}",
        f"Transaction count present on all probe RTH rows: {'YES' if txn_available_everywhere else 'NO / REVIEW'}",
        "",
        f"FINAL SOURCE FEASIBILITY: {'PASS' if gate_pass else 'FAIL / REVIEW REQUIRED'}",
    ])

    if gate_pass:
        lines.extend([
            "",
            "H4_ALPACA_SIP_MINUTE_SOURCE_FEASIBILITY_GATE_PASSED",
            "",
            "Next authorized action:",
            "Build and audit the full SPY 2021-01-01 through 2025-12-31",
            "1-minute regular-session acquisition layer before deriving H4 events.",
        ])
    else:
        lines.extend([
            "",
            "NO FULL H4 INTRADAY ACQUISITION IS AUTHORIZED BY THIS RUN.",
            "Resolve feed access/history/session completeness first.",
        ])

    return "\n".join(lines) + "\n"


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    api_key, api_secret = get_credentials()

    audits: list[DayAudit] = []

    for date_str in SAMPLE_DATES:
        print(f"Probing {SYMBOL} SIP 1-minute history for {date_str} ...")
        status, payload = request_day(
            api_key,
            api_secret,
            date_str,
        )
        audit = audit_day(date_str, status, payload)
        audits.append(audit)

        print(
            f"  status={audit.http_status}, RTH={audit.rth_count}, "
            f"coverage={'PASS' if audit.full_rth_coverage else 'FAIL'}"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        render_report(audits),
        encoding="utf-8",
    )
    JSON_OUTPUT_PATH.write_text(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "symbol": SYMBOL,
                "candidate_source": BASE_URL,
                "feed": "sip",
                "sample_dates": SAMPLE_DATES,
                "audits": [a.__dict__ for a in audits],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(OUTPUT_PATH.read_text(encoding="utf-8"))

    if not all(a.full_rth_coverage for a in audits):
        sys.exit(2)


if __name__ == "__main__":
    main()
