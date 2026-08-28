from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_VERSION = "2026-08-28-v1-h4-primary-outcome-join-audit"

PREREG_PATH = Path(
    "data/reference/h4/h4_primary_liquidity_sweep_inference_v1.json"
)
BAR5_INPUT = Path(
    "data/interim/h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz"
)
TRIGGER_INPUT = Path(
    "data/interim/h4_spy_liquidity_sweep_triggers_preoutcome.csv"
)
JOIN_INPUT = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join.csv"
)
JOIN_MANIFEST = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join_manifest.json"
)
JOIN_REPORT = Path(
    "reports/data_quality/h4_spy_primary_liquidity_sweep_outcome_join.txt"
)

AUDIT_REPORT = Path(
    "reports/data_quality/h4_spy_primary_liquidity_sweep_outcome_join_audit.txt"
)
AUDIT_MANIFEST = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join_audit_manifest.json"
)

REQUIRED_JOIN_TOKEN = "H4_PRIMARY_OUTCOME_JOIN_COMPLETE"
HORIZON_TO_OFFSET = {15: 3, 30: 6, 60: 12}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def direction_sign(direction: str) -> int:
    if direction == "SUPPORT":
        return 1
    if direction == "RESISTANCE":
        return -1
    raise RuntimeError(f"Unexpected direction: {direction}")


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("H4 PRIMARY OUTCOME-JOIN INTEGRITY AUDIT")
    print("=" * 124)
    print("Inferential statistics calculated: NO")
    print()

    for path in [
        PREREG_PATH,
        BAR5_INPUT,
        TRIGGER_INPUT,
        JOIN_INPUT,
        JOIN_MANIFEST,
        JOIN_REPORT,
    ]:
        if not path.exists():
            raise RuntimeError(f"Missing required input: {path}")

    if REQUIRED_JOIN_TOKEN not in JOIN_REPORT.read_text(encoding="utf-8"):
        raise RuntimeError("Outcome-join completion token absent.")

    manifest = json.loads(JOIN_MANIFEST.read_text(encoding="utf-8"))
    if str(manifest.get("outcome_join_output_sha256") or "") != sha256_file(
        JOIN_INPUT
    ):
        raise RuntimeError("Outcome-join SHA-256 mismatch.")

    bars = pd.read_csv(BAR5_INPUT)
    triggers = pd.read_csv(TRIGGER_INPUT)
    joined = pd.read_csv(JOIN_INPUT)

    bar_map = bars.set_index(["session_date", "bar_index"])

    expected_events = triggers[
        (triggers["liquidity_sweep_trigger"] == 1)
        & (triggers["horizon_30m_clock_eligible"] == 1)
    ].copy()

    failures: list[str] = []

    if len(joined) != len(expected_events):
        failures.append(
            f"Primary row count mismatch: expected={len(expected_events)}, "
            f"joined={len(joined)}"
        )

    if set(joined["event_id"]) != set(expected_events["event_id"]):
        failures.append("Primary event-ID population mismatch.")

    if joined["event_id"].duplicated().any():
        failures.append("Duplicate event IDs in outcome join.")

    join_map = joined.set_index("event_id")

    for t in expected_events.itertuples(index=False):
        j = join_map.loc[t.event_id]
        if isinstance(j, pd.DataFrame):
            failures.append(f"Non-unique joined event: {t.event_id}")
            break

        session_date = str(t.session_date)
        trigger_index = int(t.first_contact_bar_index)
        trigger_close = float(t.first_contact_close)
        sign = direction_sign(str(t.direction))

        if int(j["direction_sign"]) != sign:
            failures.append(f"Direction sign mismatch: {t.event_id}")
            break

        for minutes, offset in HORIZON_TO_OFFSET.items():
            clock_flag = int(
                getattr(t, f"horizon_{minutes}m_clock_eligible")
            )

            raw_col = f"raw_forward_return_{minutes}m"
            signed_col = f"signed_forward_return_{minutes}m"
            endpoint_col = f"endpoint_{minutes}m_close"

            if clock_flag == 0:
                if not (
                    pd.isna(j[raw_col])
                    and pd.isna(j[signed_col])
                    and pd.isna(j[endpoint_col])
                ):
                    failures.append(
                        f"Ineligible horizon unexpectedly populated: "
                        f"{t.event_id}/{minutes}m"
                    )
                    break
                continue

            target_index = trigger_index + offset
            try:
                endpoint = bar_map.loc[(session_date, target_index)]
            except KeyError:
                failures.append(
                    f"Expected endpoint missing: {t.event_id}/{minutes}m"
                )
                break

            if isinstance(endpoint, pd.DataFrame):
                failures.append(
                    f"Non-unique endpoint: {t.event_id}/{minutes}m"
                )
                break

            expected_close = float(endpoint["close"])
            expected_raw = expected_close / trigger_close - 1.0
            expected_signed = sign * expected_raw

            if not math.isclose(
                float(j[endpoint_col]),
                expected_close,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                failures.append(
                    f"Endpoint close mismatch: {t.event_id}/{minutes}m"
                )
                break

            if not math.isclose(
                float(j[raw_col]),
                expected_raw,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                failures.append(
                    f"Raw return mismatch: {t.event_id}/{minutes}m"
                )
                break

            if not math.isclose(
                float(j[signed_col]),
                expected_signed,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                failures.append(
                    f"Signed return mismatch: {t.event_id}/{minutes}m"
                )
                break

            expected_success = int(expected_signed > 0)
            if int(j[f"directional_success_{minutes}m"]) != expected_success:
                failures.append(
                    f"Directional-success mismatch: "
                    f"{t.event_id}/{minutes}m"
                )
                break

        if failures:
            break

        future = []
        for idx in range(trigger_index + 1, trigger_index + 7):
            b = bar_map.loc[(session_date, idx)]
            if isinstance(b, pd.DataFrame):
                failures.append(
                    f"Non-unique MFE/MAE path bar: {t.event_id}/{idx}"
                )
                break
            future.append(b)

        if failures:
            break

        if sign == 1:
            expected_mfe = max(
                float(b["high"]) / trigger_close - 1.0
                for b in future
            )
            expected_mae = min(
                float(b["low"]) / trigger_close - 1.0
                for b in future
            )
        else:
            expected_mfe = max(
                -(float(b["low"]) / trigger_close - 1.0)
                for b in future
            )
            expected_mae = min(
                -(float(b["high"]) / trigger_close - 1.0)
                for b in future
            )

        if not math.isclose(
            float(j["mfe_30m"]),
            expected_mfe,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            failures.append(f"MFE mismatch: {t.event_id}")
            break

        if not math.isclose(
            float(j["mae_30m"]),
            expected_mae,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            failures.append(f"MAE mismatch: {t.event_id}")
            break

    if joined["signed_forward_return_30m"].isna().any():
        failures.append("Primary signed 30-minute return contains missing values.")

    if int(joined["session_date"].nunique()) != int(
        manifest.get("primary_session_clusters", -1)
    ):
        failures.append("Primary session-cluster count mismatch.")

    passed = not failures

    report_lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 124,
        "H4 PRIMARY OUTCOME-JOIN INTEGRITY AUDIT",
        "=" * 124,
        f"Primary event rows: {len(joined):,}",
        f"Primary session clusters: {joined['session_date'].nunique():,}",
        "15/30/60-minute endpoint offsets independently recomputed: "
        f"{'PASS' if passed else 'FAIL'}",
        "Signed-direction convention independently recomputed: "
        f"{'PASS' if passed else 'FAIL'}",
        "30-minute MFE/MAE independently recomputed: "
        f"{'PASS' if passed else 'FAIL'}",
        "Inferential statistics calculated: NO",
        "Mean returns printed: NO",
        "P-values printed: NO",
        "",
        f"FINAL H4 PRIMARY OUTCOME-JOIN QUALITY GATE: "
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
        "join_manifest": str(JOIN_MANIFEST).replace("\\", "/"),
        "join_manifest_sha256": sha256_file(JOIN_MANIFEST),
        "join_input_sha256": sha256_file(JOIN_INPUT),
        "primary_rows": len(joined),
        "primary_session_clusters": int(
            joined["session_date"].nunique()
        ),
        "inferential_statistics_calculated": False,
    }
    AUDIT_MANIFEST.write_text(
        json.dumps(audit_manifest, indent=2),
        encoding="utf-8",
    )

    report_lines.extend(
        [
            "",
            "H4_PRIMARY_OUTCOME_JOIN_INTEGRITY_AUDIT_PASSED",
            "H4_PRIMARY_CONFIRMATORY_INFERENCE_AUTHORIZED",
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
