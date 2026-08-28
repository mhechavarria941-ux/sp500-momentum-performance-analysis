from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_VERSION = "2026-08-28-v1-h4-liquidity-sweep-trigger-integrity-audit"

BAR5_INPUT = Path(
    "data/interim/h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz"
)
ZONE_INPUT = Path(
    "data/interim/h4_spy_5min_location_zones_preoutcome.csv"
)
CONTACT_INPUT = Path(
    "data/interim/h4_spy_5min_first_contacts_preoutcome.csv"
)
LOCATION_AUDIT = Path(
    "reports/data_quality/h4_spy_5min_location_layer_integrity_audit.txt"
)

TRIGGER_INPUT = Path(
    "data/interim/h4_spy_liquidity_sweep_triggers_preoutcome.csv"
)
TRIGGER_MANIFEST = Path(
    "data/interim/h4_spy_liquidity_sweep_trigger_manifest.json"
)
TRIGGER_BUILD_REPORT = Path(
    "reports/data_quality/h4_spy_liquidity_sweep_trigger_build.txt"
)

AUDIT_REPORT = Path(
    "reports/data_quality/h4_spy_liquidity_sweep_trigger_integrity_audit.txt"
)
AUDIT_MANIFEST = Path(
    "data/interim/h4_spy_liquidity_sweep_trigger_audit_manifest.json"
)

SWEEP_PENETRATION_ATR = 0.02

REQUIRED_BUILD_TOKEN = "H4_LIQUIDITY_SWEEP_TRIGGER_BUILD_COMPLETE"
REQUIRED_LOCATION_TOKEN = (
    "H4_LIQUIDITY_SWEEP_TRIGGER_CONSTRUCTION_AUTHORIZED"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_constituents(value: str) -> list[tuple[str, float]]:
    out = []
    for part in str(value).split("|"):
        family, level = part.split(":", 1)
        out.append((family, float(level)))
    return out


def expected_hits(
    direction: str,
    high: float,
    low: float,
    close: float,
    atr: float,
    constituents: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    threshold = SWEEP_PENETRATION_ATR * atr
    hits = []

    if direction == "RESISTANCE":
        for family, level in constituents:
            if high >= level + threshold and close < level:
                hits.append((family, level))
    elif direction == "SUPPORT":
        for family, level in constituents:
            if low <= level - threshold and close > level:
                hits.append((family, level))
    else:
        raise RuntimeError(f"Unexpected direction: {direction}")

    return hits


def reference(
    direction: str,
    hits: list[tuple[str, float]],
) -> tuple[str, float] | tuple[None, None]:
    if not hits:
        return None, None
    if direction == "RESISTANCE":
        return max(hits, key=lambda x: (x[1], x[0]))
    return min(hits, key=lambda x: (x[1], x[0]))


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("H4 LIQUIDITY SWEEP / REJECTION TRIGGER INTEGRITY AUDIT — PRE-OUTCOME")
    print("=" * 124)
    print("Forward-return outcomes calculated: NO")
    print()

    required = [
        BAR5_INPUT,
        ZONE_INPUT,
        CONTACT_INPUT,
        LOCATION_AUDIT,
        TRIGGER_INPUT,
        TRIGGER_MANIFEST,
        TRIGGER_BUILD_REPORT,
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Missing required input: {path}")

    if REQUIRED_BUILD_TOKEN not in TRIGGER_BUILD_REPORT.read_text(
        encoding="utf-8"
    ):
        raise RuntimeError("Trigger build completion token absent.")

    if REQUIRED_LOCATION_TOKEN not in LOCATION_AUDIT.read_text(
        encoding="utf-8"
    ):
        raise RuntimeError("Location-layer trigger authorization token absent.")

    manifest = json.loads(TRIGGER_MANIFEST.read_text(encoding="utf-8"))
    if str(manifest.get("trigger_output_sha256") or "") != sha256_file(
        TRIGGER_INPUT
    ):
        raise RuntimeError("Trigger output SHA-256 mismatch.")

    bar5 = pd.read_csv(BAR5_INPUT)
    zones = pd.read_csv(ZONE_INPUT)
    contacts = pd.read_csv(CONTACT_INPUT)
    triggers = pd.read_csv(TRIGGER_INPUT)

    bar5["bar_start_et"] = pd.to_datetime(
        bar5["bar_start_et"], utc=True
    ).dt.tz_convert("America/New_York")
    bar5["bar_end_et"] = pd.to_datetime(
        bar5["bar_end_et"], utc=True
    ).dt.tz_convert("America/New_York")
    bar5["session_close_et"] = pd.to_datetime(
        bar5["session_close_et"], utc=True
    ).dt.tz_convert("America/New_York")

    contacted = contacts[contacts["contacted"] == 1].copy()

    failures: list[str] = []

    if len(triggers) != len(contacted):
        failures.append(
            f"Trigger layer must contain exactly one row per contacted zone: "
            f"contacted={len(contacted):,}, trigger_rows={len(triggers):,}"
        )

    if triggers["zone_id"].duplicated().any():
        failures.append("Trigger layer contains duplicate zone IDs.")

    if triggers["event_id"].duplicated().any():
        failures.append("Trigger layer contains duplicate event IDs.")

    contacted_ids = set(contacted["zone_id"])
    trigger_ids = set(triggers["zone_id"])
    if contacted_ids != trigger_ids:
        failures.append("Trigger zone population differs from contacted-zone population.")

    zone_map = zones.set_index("zone_id")
    bar_map = bar5.set_index(["session_date", "bar_index"])
    trigger_map = triggers.set_index("zone_id")

    trigger_count = 0
    clock_eligible_30 = 0

    for c in contacted.itertuples(index=False):
        z = zone_map.loc[c.zone_id]
        t = trigger_map.loc[c.zone_id]

        session_date = str(c.session_date)
        bar_index = int(float(c.first_contact_bar_index))
        b = bar_map.loc[(session_date, bar_index)]
        if isinstance(b, pd.DataFrame):
            failures.append(
                f"Non-unique five-minute key: {session_date}/{bar_index}"
            )
            break

        direction = str(z["direction"])
        constituents = parse_constituents(
            str(z["constituent_levels"])
        )

        hits = expected_hits(
            direction,
            float(b["high"]),
            float(b["low"]),
            float(b["close"]),
            float(z["atr14_prior"]),
            constituents,
        )
        ref_family, ref_level = reference(direction, hits)

        expected_trigger = int(bool(hits))
        observed_trigger = int(t["liquidity_sweep_trigger"])

        if observed_trigger != expected_trigger:
            failures.append(
                f"Trigger classification mismatch: {c.zone_id}"
            )
            break

        expected_families = "|".join(x[0] for x in hits) if hits else ""
        observed_families = (
            ""
            if pd.isna(t["qualifying_families"])
            else str(t["qualifying_families"])
        )
        if observed_families != expected_families:
            failures.append(
                f"Qualifying-family list mismatch: {c.zone_id}"
            )
            break

        if int(t["qualifying_constituent_count"]) != len(hits):
            failures.append(
                f"Qualifying-level count mismatch: {c.zone_id}"
            )
            break

        if hits:
            if str(t["trigger_reference_family"]) != ref_family:
                failures.append(
                    f"Reference family mismatch: {c.zone_id}"
                )
                break
            if not math.isclose(
                float(t["trigger_reference_level"]),
                float(ref_level),
                rel_tol=1e-11,
                abs_tol=1e-11,
            ):
                failures.append(
                    f"Reference level mismatch: {c.zone_id}"
                )
                break

            if direction == "RESISTANCE":
                penetration = (
                    float(b["high"]) - float(ref_level)
                ) / float(z["atr14_prior"])
                rejection = (
                    float(ref_level) - float(b["close"])
                ) / float(z["atr14_prior"])
            else:
                penetration = (
                    float(ref_level) - float(b["low"])
                ) / float(z["atr14_prior"])
                rejection = (
                    float(b["close"]) - float(ref_level)
                ) / float(z["atr14_prior"])

            if penetration + 1e-12 < SWEEP_PENETRATION_ATR:
                failures.append(
                    f"Recorded trigger below penetration threshold: {c.zone_id}"
                )
                break
            if rejection <= 0:
                failures.append(
                    f"Recorded trigger lacks same-bar rejection close: {c.zone_id}"
                )
                break

            if not math.isclose(
                float(t["penetration_atr"]),
                penetration,
                rel_tol=1e-10,
                abs_tol=1e-10,
            ):
                failures.append(
                    f"Penetration metric mismatch: {c.zone_id}"
                )
                break

            if not math.isclose(
                float(t["rejection_close_distance_atr"]),
                rejection,
                rel_tol=1e-10,
                abs_tol=1e-10,
            ):
                failures.append(
                    f"Rejection-distance metric mismatch: {c.zone_id}"
                )
                break

            trigger_count += 1

        for minutes in [15, 30, 60]:
            expected_clock = int(
                b["bar_end_et"] + timedelta(minutes=minutes)
                <= b["session_close_et"]
            )
            observed_clock = int(
                t[f"horizon_{minutes}m_clock_eligible"]
            )
            if observed_clock != expected_clock:
                failures.append(
                    f"{minutes}m clock-eligibility mismatch: {c.zone_id}"
                )
                break

        if failures:
            break

        if expected_trigger and int(t["horizon_30m_clock_eligible"]) == 1:
            clock_eligible_30 += 1

    if trigger_count != int(manifest.get("trigger_rows", -1)):
        failures.append(
            f"Trigger count differs from manifest: "
            f"audit={trigger_count:,}, manifest={manifest.get('trigger_rows')}"
        )

    if clock_eligible_30 != int(
        manifest.get("primary_30m_clock_eligible_trigger_rows", -1)
    ):
        failures.append(
            "Primary 30-minute clock-eligible trigger count differs from manifest."
        )

    forbidden_fragments = [
        "forward_return",
        "signed_forward",
        "future_return",
        "hit_rate",
        "mfe",
        "mae",
        "outcome_",
    ]
    for col in [str(x).lower() for x in triggers.columns]:
        if any(frag in col for frag in forbidden_fragments):
            failures.append(
                f"Forbidden outcome-like trigger field: {col}"
            )
            break

    passed = not failures

    resistance_count = int(
        (
            (triggers["liquidity_sweep_trigger"] == 1)
            & (triggers["direction"] == "RESISTANCE")
        ).sum()
    )
    support_count = int(
        (
            (triggers["liquidity_sweep_trigger"] == 1)
            & (triggers["direction"] == "SUPPORT")
        ).sum()
    )

    report_lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 124,
        "H4 LIQUIDITY SWEEP / REJECTION TRIGGER INTEGRITY AUDIT — PRE-OUTCOME",
        "=" * 124,
        f"Contacted zones: {len(contacted):,}",
        f"Trigger-layer rows: {len(triggers):,}",
        f"Independently recomputed qualifying triggers: {trigger_count:,}",
        f"Resistance triggers: {resistance_count:,}",
        f"Support triggers: {support_count:,}",
        f"30-minute clock-eligible triggers: {clock_eligible_30:,}",
        f"Frozen penetration threshold: "
        f"{SWEEP_PENETRATION_ATR:.2f} × prior ATR(14)",
        "Same-bar penetration/rejection recomputation: "
        f"{'PASS' if not failures else 'FAIL'}",
        "Future-return fields present: NO",
        "",
        f"FINAL H4 LIQUIDITY-SWEEP TRIGGER QUALITY GATE: "
        f"{'PASS' if passed else 'FAIL'}",
    ]

    if failures:
        report_lines.extend(["", "FAILURES:"])
        report_lines.extend(f"- {x}" for x in failures[:100])

    AUDIT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    if not passed:
        print()
        print(AUDIT_REPORT.read_text(encoding="utf-8"))
        sys.exit(2)

    audit_manifest = {
        "script_version": SCRIPT_VERSION,
        "trigger_manifest": str(TRIGGER_MANIFEST).replace("\\", "/"),
        "trigger_manifest_sha256": sha256_file(TRIGGER_MANIFEST),
        "trigger_input_sha256": sha256_file(TRIGGER_INPUT),
        "contacted_zone_rows": len(contacted),
        "trigger_rows": trigger_count,
        "primary_30m_clock_eligible_trigger_rows": clock_eligible_30,
        "resistance_trigger_rows": resistance_count,
        "support_trigger_rows": support_count,
        "forward_outcomes_calculated": False,
    }
    AUDIT_MANIFEST.write_text(
        json.dumps(audit_manifest, indent=2),
        encoding="utf-8",
    )

    report_lines.extend(
        [
            "",
            "H4_LIQUIDITY_SWEEP_TRIGGER_INTEGRITY_AUDIT_PASSED",
            "H4_PRIMARY_OUTCOME_JOIN_SPECIFICATION_AUTHORIZED",
        ]
    )
    AUDIT_REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print(AUDIT_REPORT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
