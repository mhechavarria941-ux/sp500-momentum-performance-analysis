from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_VERSION = "2026-08-28-v1-h4-5min-location-layer-integrity-audit"

MINUTE_INPUT = Path(
    "data/interim/h4_spy_1min_sip_2021_2025_primary_eligible.csv.gz"
)
MINUTE_MANIFEST = Path(
    "data/interim/h4_spy_1min_sip_primary_eligible_manifest.json"
)
MINUTE_AUDIT = Path(
    "reports/data_quality/h4_spy_1min_sip_integrity_audit_v2.txt"
)

DAILY_OUTPUT = Path(
    "data/interim/h4_spy_daily_sip_support_levels_2020_2025.csv"
)
BAR5_OUTPUT = Path(
    "data/interim/h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz"
)
ZONE_OUTPUT = Path(
    "data/interim/h4_spy_5min_location_zones_preoutcome.csv"
)
CONTACT_OUTPUT = Path(
    "data/interim/h4_spy_5min_first_contacts_preoutcome.csv"
)
BUILD_MANIFEST = Path(
    "data/interim/h4_spy_5min_location_layer_manifest.json"
)
BUILD_REPORT = Path(
    "reports/data_quality/h4_spy_5min_location_layer_build.txt"
)

AUDIT_OUTPUT = Path(
    "reports/data_quality/h4_spy_5min_location_layer_integrity_audit.txt"
)
AUDIT_MANIFEST = Path(
    "data/interim/h4_spy_5min_location_layer_audit_manifest.json"
)

ATR_PERIOD = 14
ZONE_HALF_WIDTH_ATR = 0.10

REQUIRED_BUILD_TOKEN = "H4_5MIN_LOCATION_LAYER_BUILD_COMPLETE"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str, failures: list[str]) -> None:
    failures.append(msg)


def recompute_wilder_atr(daily: pd.DataFrame) -> pd.Series:
    prev_close = daily["close"].shift(1)
    tr = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = pd.Series(np.nan, index=daily.index, dtype=float)
    atr.iloc[ATR_PERIOD - 1] = tr.iloc[:ATR_PERIOD].mean()

    for i in range(ATR_PERIOD, len(daily)):
        atr.iloc[i] = (
            atr.iloc[i - 1] * (ATR_PERIOD - 1) + tr.iloc[i]
        ) / ATR_PERIOD

    return atr


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("H4 SPY 5-MINUTE LOCATION LAYER INTEGRITY AUDIT — PRE-OUTCOME")
    print("=" * 124)
    print("Liquidity-sweep trigger calculated: NO")
    print("H4 forward-return outcomes calculated: NO")
    print()

    required = [
        MINUTE_INPUT,
        MINUTE_MANIFEST,
        MINUTE_AUDIT,
        DAILY_OUTPUT,
        BAR5_OUTPUT,
        ZONE_OUTPUT,
        CONTACT_OUTPUT,
        BUILD_MANIFEST,
        BUILD_REPORT,
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Missing required input: {path}")

    if REQUIRED_BUILD_TOKEN not in BUILD_REPORT.read_text(encoding="utf-8"):
        raise RuntimeError("Location-layer build completion token absent.")

    manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))

    for key, path in [
        ("daily_support_output_sha256", DAILY_OUTPUT),
        ("bar5_output_sha256", BAR5_OUTPUT),
        ("zone_output_sha256", ZONE_OUTPUT),
        ("contact_output_sha256", CONTACT_OUTPUT),
    ]:
        if str(manifest.get(key) or "") != sha256_file(path):
            raise RuntimeError(
                f"Build-manifest SHA-256 mismatch for {path}"
            )

    failures: list[str] = []

    minute = pd.read_csv(MINUTE_INPUT)
    minute["timestamp_et"] = pd.to_datetime(
        minute["timestamp_et"],
        utc=True,
    ).dt.tz_convert("America/New_York")
    minute["session_open_et"] = pd.to_datetime(
        minute["session_open_et"],
        utc=True,
    ).dt.tz_convert("America/New_York")

    minute["minute_offset"] = (
        (minute["timestamp_et"] - minute["session_open_et"])
        .dt.total_seconds()
        .div(60)
        .astype(int)
    )
    minute["bar_index"] = minute["minute_offset"] // 5
    minute["vwap_num"] = minute["vwap"] * minute["volume"]

    source_counts = (
        minute.groupby(["session_date", "bar_index"])
        .size()
    )
    bad_counts = source_counts[source_counts != 5]
    if not bad_counts.empty:
        fail(
            f"Source minute data contains {len(bad_counts)} non-5-minute buckets.",
            failures,
        )

    recomputed = (
        minute.groupby(
            ["session_date", "bar_index"],
            sort=True,
        )
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            vwap_num=("vwap_num", "sum"),
            transactions=("transactions", "sum"),
            minute_count=("timestamp_et", "size"),
        )
        .reset_index()
    )
    recomputed["vwap"] = (
        recomputed["vwap_num"] / recomputed["volume"]
    )

    bar5 = pd.read_csv(BAR5_OUTPUT)

    expected_bar_rows = len(minute) // 5
    if len(bar5) != expected_bar_rows:
        fail(
            f"5-minute row count mismatch: expected={expected_bar_rows:,}, "
            f"observed={len(bar5):,}",
            failures,
        )

    if int(bar5["session_date"].nunique()) != int(
        manifest["primary_sessions"]
    ):
        fail("5-minute session count differs from build manifest.", failures)

    compare = bar5.merge(
        recomputed,
        on=["session_date", "bar_index"],
        how="outer",
        suffixes=("_built", "_recomputed"),
        indicator=True,
    )

    if not (compare["_merge"] == "both").all():
        fail("5-minute key population differs from source recomputation.", failures)

    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "transactions",
    ]:
        a = compare[f"{col}_built"].astype(float)
        b = compare[f"{col}_recomputed"].astype(float)
        if not np.allclose(a, b, rtol=1e-10, atol=1e-10, equal_nan=True):
            fail(f"5-minute {col} differs from full source recomputation.", failures)

    if not (bar5["minute_count"] == 5).all():
        fail("At least one built 5-minute bar does not contain exactly 5 minutes.", failures)

    # Daily level validation.
    daily = pd.read_csv(DAILY_OUTPUT).sort_values("session_date").reset_index(drop=True)
    required_daily = [
        "open", "high", "low", "close", "atr14", "atr14_prior",
        "pdh", "pdl", "pwh", "pwl", "pmh", "pml",
        "prior_all_time_high",
    ]
    if daily[required_daily].iloc[40:].isna().any().any():
        fail("Unexpected missing values in mature daily support layer.", failures)

    recomputed_atr = recompute_wilder_atr(daily)
    if not np.allclose(
        daily["atr14"].to_numpy(dtype=float),
        recomputed_atr.to_numpy(dtype=float),
        rtol=1e-11,
        atol=1e-11,
        equal_nan=True,
    ):
        fail("Daily Wilder ATR(14) fails independent recomputation.", failures)

    if not np.allclose(
        daily["atr14_prior"].to_numpy(dtype=float),
        recomputed_atr.shift(1).to_numpy(dtype=float),
        rtol=1e-11,
        atol=1e-11,
        equal_nan=True,
    ):
        fail("Prior-day ATR field is not a one-session lag of Wilder ATR.", failures)

    if not np.allclose(
        daily["pdh"].to_numpy(dtype=float),
        daily["high"].shift(1).to_numpy(dtype=float),
        equal_nan=True,
    ):
        fail("PDH is not the previous completed session high.", failures)

    if not np.allclose(
        daily["pdl"].to_numpy(dtype=float),
        daily["low"].shift(1).to_numpy(dtype=float),
        equal_nan=True,
    ):
        fail("PDL is not the previous completed session low.", failures)

    recomputed_ath = daily["high"].expanding().max().shift(1)
    if not np.allclose(
        daily["prior_all_time_high"].to_numpy(dtype=float),
        recomputed_ath.to_numpy(dtype=float),
        equal_nan=True,
    ):
        fail("Prior all-time high field fails independent recomputation.", failures)

    # Recompute previous completed week/month levels.
    dts = pd.to_datetime(daily["session_date"])
    wk = (
        dts - pd.to_timedelta(dts.dt.weekday, unit="D")
    ).dt.date.astype(str)
    mo = dts.dt.to_period("M").astype(str)

    weekly = pd.DataFrame(
        {
            "week_start": wk,
            "high": daily["high"],
            "low": daily["low"],
        }
    ).groupby("week_start", as_index=False).agg(
        hi=("high", "max"),
        lo=("low", "min"),
    ).sort_values("week_start")
    weekly["pwh_check"] = weekly["hi"].shift(1)
    weekly["pwl_check"] = weekly["lo"].shift(1)

    week_check = pd.DataFrame(
        {"week_start": wk}
    ).merge(
        weekly[["week_start", "pwh_check", "pwl_check"]],
        on="week_start",
        how="left",
    )

    if not np.allclose(
        daily["pwh"].to_numpy(dtype=float),
        week_check["pwh_check"].to_numpy(dtype=float),
        equal_nan=True,
    ):
        fail("PWH fails previous-completed-week recomputation.", failures)

    if not np.allclose(
        daily["pwl"].to_numpy(dtype=float),
        week_check["pwl_check"].to_numpy(dtype=float),
        equal_nan=True,
    ):
        fail("PWL fails previous-completed-week recomputation.", failures)

    monthly = pd.DataFrame(
        {
            "month_key": mo,
            "high": daily["high"],
            "low": daily["low"],
        }
    ).groupby("month_key", as_index=False).agg(
        hi=("high", "max"),
        lo=("low", "min"),
    ).sort_values("month_key")
    monthly["pmh_check"] = monthly["hi"].shift(1)
    monthly["pml_check"] = monthly["lo"].shift(1)

    month_check = pd.DataFrame(
        {"month_key": mo}
    ).merge(
        monthly[["month_key", "pmh_check", "pml_check"]],
        on="month_key",
        how="left",
    )

    if not np.allclose(
        daily["pmh"].to_numpy(dtype=float),
        month_check["pmh_check"].to_numpy(dtype=float),
        equal_nan=True,
    ):
        fail("PMH fails previous-completed-month recomputation.", failures)

    if not np.allclose(
        daily["pml"].to_numpy(dtype=float),
        month_check["pml_check"].to_numpy(dtype=float),
        equal_nan=True,
    ):
        fail("PML fails previous-completed-month recomputation.", failures)

    # Zone structural audit.
    zones = pd.read_csv(ZONE_OUTPUT)
    contacts = pd.read_csv(CONTACT_OUTPUT)

    if zones["zone_id"].duplicated().any():
        fail("Zone IDs are not unique.", failures)

    if len(contacts) != len(zones):
        fail("Contact layer does not contain exactly one row per zone.", failures)

    if contacts["zone_id"].duplicated().any():
        fail("Contact layer contains duplicate zone IDs.", failures)

    zone_contact = zones.merge(
        contacts,
        on=["zone_id", "session_date", "direction"],
        how="outer",
        indicator=True,
        suffixes=("_zone", "_contact"),
    )
    if not (zone_contact["_merge"] == "both").all():
        fail("Zone/contact key populations differ.", failures)

    # Each zone must be a union of 0.10*ATR intervals around its constituent levels.
    for z in zones.itertuples(index=False):
        parts = str(z.constituent_levels).split("|")
        parsed = []
        for part in parts:
            family, level = part.split(":", 1)
            parsed.append((family, float(level)))

        half = ZONE_HALF_WIDTH_ATR * float(z.atr14_prior)
        lower = min(level - half for _, level in parsed)
        upper = max(level + half for _, level in parsed)

        if not math.isclose(float(z.zone_lower), lower, rel_tol=1e-11, abs_tol=1e-11):
            fail(f"Zone lower boundary mismatch: {z.zone_id}", failures)
            break
        if not math.isclose(float(z.zone_upper), upper, rel_tol=1e-11, abs_tol=1e-11):
            fail(f"Zone upper boundary mismatch: {z.zone_id}", failures)
            break
        if int(z.confluence_count) != len(parsed):
            fail(f"Zone confluence count mismatch: {z.zone_id}", failures)
            break

    # Same-direction zones within a session must no longer overlap after merging.
    for (_, _), g in zones.sort_values(
        ["session_date", "direction", "zone_lower"]
    ).groupby(["session_date", "direction"]):
        previous_upper = None
        for r in g.itertuples(index=False):
            if previous_upper is not None and float(r.zone_lower) <= previous_upper:
                fail(
                    f"Post-merge zones still overlap in {r.session_date} {r.direction}.",
                    failures,
                )
                break
            previous_upper = float(r.zone_upper)

    # Verify every recorded first contact is truly the earliest intersecting bar.
    bars_by_session = {
        s: g.sort_values("bar_index")
        for s, g in bar5.groupby("session_date")
    }
    zones_by_id = zones.set_index("zone_id")

    for c in contacts.itertuples(index=False):
        z = zones_by_id.loc[c.zone_id]
        bars = bars_by_session[c.session_date]
        hits = bars[
            (bars["high"] >= float(z["zone_lower"]))
            & (bars["low"] <= float(z["zone_upper"]))
        ]

        if hits.empty:
            if int(c.contacted) != 0:
                fail(f"False recorded contact: {c.zone_id}", failures)
                break
        else:
            expected_index = int(hits.iloc[0]["bar_index"])
            if int(c.contacted) != 1:
                fail(f"Missing recorded contact: {c.zone_id}", failures)
                break
            if int(float(c.first_contact_bar_index)) != expected_index:
                fail(f"First-contact index is not earliest: {c.zone_id}", failures)
                break

    # Explicit firewall: no outcome fields are allowed.
    forbidden_fragments = [
        "forward_return",
        "signed_forward",
        "hit_rate",
        "mfe",
        "mae",
        "future_return",
        "outcome_15",
        "outcome_30",
        "outcome_60",
    ]
    all_columns = (
        [str(x).lower() for x in bar5.columns]
        + [str(x).lower() for x in zones.columns]
        + [str(x).lower() for x in contacts.columns]
    )
    for frag in forbidden_fragments:
        if any(frag in col for col in all_columns):
            fail(f"Forbidden outcome-like field detected: {frag}", failures)

    passed = len(failures) == 0

    report_lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 124,
        "H4 SPY 5-MINUTE LOCATION LAYER INTEGRITY AUDIT — PRE-OUTCOME",
        "=" * 124,
        f"Primary-eligible sessions: {bar5['session_date'].nunique():,}",
        f"Canonical source minutes: {len(minute):,}",
        f"Expected 5-minute bars: {expected_bar_rows:,}",
        f"Observed 5-minute bars: {len(bar5):,}",
        f"Merged location zones: {len(zones):,}",
        f"Contact rows: {len(contacts):,}",
        f"Contacted zones: {int(contacts['contacted'].sum()):,}",
        f"Confluence zones: "
        f"{int((zones['confluence_status'] == 'CONFLUENCE').sum()):,}",
        "Full 1m→5m OHLCV/VWAP/transaction recomputation: "
        f"{'PASS' if not any('5-minute' in x for x in failures) else 'FAIL'}",
        "Wilder ATR and higher-timeframe level recomputation: "
        f"{'PASS' if not any(x.startswith(('Daily', 'PDH', 'PDL', 'PWH', 'PWL', 'PMH', 'PML', 'Prior')) for x in failures) else 'FAIL'}",
        "Zone merge / first-contact audit: "
        f"{'PASS' if not any(('Zone' in x or 'contact' in x or 'overlap' in x) for x in failures) else 'FAIL'}",
        "H4 liquidity-sweep trigger calculated: NO",
        "H4 forward-return outcomes calculated: NO",
        "",
        f"FINAL H4 5-MINUTE LOCATION-LAYER QUALITY GATE: "
        f"{'PASS' if passed else 'FAIL'}",
    ]

    if failures:
        report_lines.extend(["", "FAILURES:"])
        report_lines.extend(f"- {x}" for x in failures[:100])

    AUDIT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUTPUT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    if not passed:
        print()
        print(AUDIT_OUTPUT.read_text(encoding="utf-8"))
        sys.exit(2)

    audit_manifest = {
        "script_version": SCRIPT_VERSION,
        "build_manifest": str(BUILD_MANIFEST).replace("\\", "/"),
        "build_manifest_sha256": sha256_file(BUILD_MANIFEST),
        "bar5_sha256": sha256_file(BAR5_OUTPUT),
        "zones_sha256": sha256_file(ZONE_OUTPUT),
        "contacts_sha256": sha256_file(CONTACT_OUTPUT),
        "primary_sessions": int(bar5["session_date"].nunique()),
        "minute_rows": len(minute),
        "bar5_rows": len(bar5),
        "zone_rows": len(zones),
        "contact_rows": len(contacts),
        "contacted_zone_rows": int(contacts["contacted"].sum()),
        "liquidity_sweep_trigger_calculated": False,
        "h4_forward_outcomes_calculated": False,
    }

    AUDIT_MANIFEST.write_text(
        json.dumps(audit_manifest, indent=2),
        encoding="utf-8",
    )

    report_lines.extend(
        [
            "",
            "H4_5MIN_LOCATION_LAYER_INTEGRITY_AUDIT_PASSED",
            "H4_LIQUIDITY_SWEEP_TRIGGER_CONSTRUCTION_AUTHORIZED",
        ]
    )
    AUDIT_OUTPUT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print(AUDIT_OUTPUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
