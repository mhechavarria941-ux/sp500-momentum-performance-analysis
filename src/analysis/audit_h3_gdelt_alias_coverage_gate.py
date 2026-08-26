from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-gdelt-alias-coverage-missingness-audit"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

CONFIG_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_alias_coverage_missingness_gate_v1.json"
)
MANIFEST_PATH = H3_DIR / "h3_pit_attention_alias_intervals.csv"

SOURCE_FILES_PATH = H3_DIR / "h3_gdelt_stage3k_source_files.csv"
DAILY_SECURITY_PATH = H3_DIR / "h3_gdelt_stage3k_daily_security_attention.csv"
WINDOW_SECURITY_PATH = H3_DIR / "h3_gdelt_stage3k_window_security_coverage.csv"
SECURITY_SUMMARY_PATH = H3_DIR / "h3_gdelt_stage3k_security_coverage_summary.csv"
WINDOW_SUMMARY_PATH = H3_DIR / "h3_gdelt_stage3k_window_summary.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_gdelt_alias_coverage_missingness_gate_audit.txt"
)

EXPECTED_STAGE3J_POLICY_ID = "H3_PIT_ATTENTION_ALIAS_POLICY_V5"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        CONFIG_PATH,
        MANIFEST_PATH,
        SOURCE_FILES_PATH,
        DAILY_SECURITY_PATH,
        WINDOW_SECURITY_PATH,
        SECURITY_SUMMARY_PATH,
        WINDOW_SUMMARY_PATH,
    ]

    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    config_text = CONFIG_PATH.read_text(
        encoding="utf-8"
    )
    config = json.loads(config_text)
    config_sha = hashlib.sha256(
        config_text.encode("utf-8")
    ).hexdigest()

    manifest_sha = sha256_file(MANIFEST_PATH)

    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
    )
    source_files = pd.read_csv(
        SOURCE_FILES_PATH,
        dtype=str,
        keep_default_na=False,
    )
    daily = pd.read_csv(
        DAILY_SECURITY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    window_security = pd.read_csv(
        WINDOW_SECURITY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    security = pd.read_csv(
        SECURITY_SUMMARY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    window = pd.read_csv(
        WINDOW_SUMMARY_PATH,
        dtype=str,
        keep_default_na=False,
    )

    numeric_columns = {
        "source_files": [
            "parsed_rows",
            "malformed_rows",
            "malformed_row_rate",
            "total_source_document_weight",
            "active_security_count",
            "unique_active_alias_count",
        ],
        "daily": [
            "matched_source_document_weight",
            "total_source_document_weight",
            "attention_share",
            "strict_nonzero_day_flag",
        ],
        "window_security": [
            "eligible_days",
            "nonzero_days",
            "matched_source_document_weight",
            "total_source_document_weight",
            "attention_share",
            "strict_nonzero_window_flag",
        ],
        "security": [
            "eligible_anchor_windows",
            "nonzero_anchor_windows",
            "total_matched_source_document_weight",
            "total_source_document_weight",
            "any_nonzero_window_flag",
            "two_plus_nonzero_windows_flag",
            "nonzero_window_rate",
        ],
        "window": [
            "eligible_security_count",
            "strict_nonzero_security_count",
            "total_matched_source_document_weight",
            "total_source_document_weight",
            "strict_nonzero_security_rate",
        ],
    }

    frames = {
        "source_files": source_files,
        "daily": daily,
        "window_security": window_security,
        "security": security,
        "window": window,
    }

    for frame_name, columns in numeric_columns.items():
        for column in columns:
            frames[frame_name][column] = pd.to_numeric(
                frames[frame_name][column],
                errors="raise",
            )

    failures = []
    passed = 0

    lines = [
        "=" * 128,
        "H3 STAGE 3K — DIRECT GDELT ALIAS COVERAGE & MISSINGNESS GATE AUDIT",
        "=" * 128,
        "Full-history GDELT extraction authorized only if this audit passes.",
        "H3 outcome analysis authorized: NO",
        "",
    ]

    def check(
        condition: bool,
        success: str,
        failure: str,
    ) -> None:
        nonlocal passed

        if bool(condition):
            lines.append("PASS: " + success)
            passed += 1
        else:
            lines.append("FAIL: " + failure)
            failures.append(failure)

    expected_files = int(
        config["sample"]["expected_daily_files"]
    )

    check(
        len(source_files) == expected_files,
        f"Exactly {expected_files} frozen daily GDELT files are represented.",
        f"Source file rows={len(source_files)}, expected {expected_files}.",
    )

    success_statuses = {
        "DOWNLOADED_PARSED_RAW_DELETED",
        "REUSED_VALID_CACHE",
    }

    check(
        source_files["status"].isin(
            success_statuses
        ).all(),
        "Every daily source file parsed successfully or reused a valid cache.",
        "At least one daily source file lacks successful parse/cache status.",
    )

    check(
        source_files["source_file_sha256"].str.len().eq(
            64
        ).all(),
        "Every daily source file has a SHA-256 provenance hash.",
        "A daily source file is missing a valid SHA-256 hash.",
    )

    maximum_malformed = float(
        config["technical_thresholds"][
            "maximum_malformed_row_rate_per_file"
        ]
    )

    check(
        source_files["malformed_row_rate"].le(
            maximum_malformed
        ).all(),
        (
            "Every daily malformed-row rate is within the frozen "
            f"{maximum_malformed:.4%} ceiling."
        ),
        "At least one daily malformed-row rate exceeds the frozen ceiling.",
    )

    check(
        source_files[
            "total_source_document_weight"
        ].gt(0).all(),
        "Every daily GKG denominator is positive.",
        "At least one daily GKG denominator is non-positive.",
    )

    check(
        source_files["config_sha256"].eq(
            config_sha
        ).all()
        and daily["stage3k_config_sha256"].eq(
            config_sha
        ).all(),
        "All source/daily rows reproduce the frozen Stage 3K gate checksum.",
        "A Stage 3K output checksum differs from the frozen gate.",
    )

    check(
        source_files["manifest_sha256"].eq(
            manifest_sha
        ).all(),
        "Every source-file record reproduces the exact Stage 3J manifest checksum.",
        "A source-file record differs from the current Stage 3J manifest checksum.",
    )

    check(
        manifest["policy_id"].eq(
            EXPECTED_STAGE3J_POLICY_ID
        ).all(),
        "Stage 3J alias manifest remains frozen at Policy V5.",
        "Stage 3J alias manifest policy changed after the Stage 3K gate was frozen.",
    )

    check(
        daily[
            ["date", "security_key"]
        ].duplicated().sum()
        == 0,
        "Every security-date has exactly one Stage 3K attention observation.",
        "Duplicate security-date attention rows exist.",
    )

    check(
        daily["attention_share"].between(
            0.0,
            1.0,
            inclusive="both",
        ).all(),
        "Every daily attention share lies in [0, 1].",
        "At least one daily attention share lies outside [0, 1].",
    )

    check(
        (
            daily["matched_source_document_weight"]
            <= daily["total_source_document_weight"]
        ).all(),
        "Matched daily source-document weight never exceeds its denominator.",
        "A matched daily weight exceeds its denominator.",
    )

    # Reconstruct expected active security-date count from Stage 3J intervals.
    manifest["start_dt"] = pd.to_datetime(
        manifest["alias_valid_from"],
        errors="raise",
    )
    manifest["end_dt"] = pd.to_datetime(
        manifest["alias_valid_to_exclusive"],
        errors="raise",
    )

    expected_active_pairs = 0

    for date_str in source_files["date"]:
        date = pd.Timestamp(date_str)

        active = manifest[
            (manifest["start_dt"] <= date)
            & (manifest["end_dt"] > date)
        ]

        if active["security_key"].duplicated().any():
            expected_active_pairs = -1
            break

        expected_active_pairs += len(active)

    check(
        expected_active_pairs >= 0
        and len(daily) == expected_active_pairs,
        (
            "Stage 3K daily rows exactly cover the active PIT alias "
            "security-date universe."
        ),
        (
            f"Daily rows={len(daily)} versus expected active "
            f"security-date pairs={expected_active_pairs}."
        ),
    )

    eligible = security[
        security["eligible_anchor_windows"] >= 1
    ]
    eligible_2plus = security[
        security["eligible_anchor_windows"] >= 2
    ]
    high = eligible[
        eligible["structural_ambiguity_tier"].eq(
            "HIGH"
        )
    ]

    any_nonzero_rate = (
        eligible["any_nonzero_window_flag"].mean()
        if len(eligible) else 0.0
    )
    repeat_nonzero_rate = (
        eligible_2plus[
            "two_plus_nonzero_windows_flag"
        ].mean()
        if len(eligible_2plus) else 0.0
    )
    security_window_nonzero_rate = (
        window_security[
            "strict_nonzero_window_flag"
        ].mean()
        if len(window_security) else 0.0
    )
    high_any_nonzero_rate = (
        high["any_nonzero_window_flag"].mean()
        if len(high) else 0.0
    )

    t = config["coverage_thresholds"]

    check(
        any_nonzero_rate
        >= float(t["minimum_any_nonzero_security_rate"]),
        (
            "Any-nonzero security coverage meets the frozen "
            f"{float(t['minimum_any_nonzero_security_rate']):.2%} threshold "
            f"({any_nonzero_rate:.2%})."
        ),
        (
            "Any-nonzero security coverage is below threshold: "
            f"{any_nonzero_rate:.2%}."
        ),
    )

    check(
        repeat_nonzero_rate
        >= float(
            t[
                "minimum_repeat_nonzero_rate_among_securities_eligible_2plus_windows"
            ]
        ),
        (
            "Repeat nonzero coverage among securities eligible >=2 windows "
            f"meets threshold ({repeat_nonzero_rate:.2%})."
        ),
        (
            "Repeat nonzero coverage among securities eligible >=2 windows "
            f"is below threshold: {repeat_nonzero_rate:.2%}."
        ),
    )

    check(
        security_window_nonzero_rate
        >= float(
            t["minimum_nonzero_security_window_rate"]
        ),
        (
            "Strict nonzero security-window coverage meets threshold "
            f"({security_window_nonzero_rate:.2%})."
        ),
        (
            "Strict nonzero security-window coverage is below threshold: "
            f"{security_window_nonzero_rate:.2%}."
        ),
    )

    check(
        high_any_nonzero_rate
        >= float(
            t[
                "minimum_high_ambiguity_any_nonzero_rate"
            ]
        ),
        (
            "HIGH-ambiguity any-nonzero security coverage meets threshold "
            f"({high_any_nonzero_rate:.2%})."
        ),
        (
            "HIGH-ambiguity any-nonzero security coverage is below threshold: "
            f"{high_any_nonzero_rate:.2%}."
        ),
    )

    forbidden = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )

    output_columns = {
        str(column).casefold()
        for frame in (
            daily,
            window_security,
            security,
            window,
        )
        for column in frame.columns
    }

    bad = [
        column
        for column in output_columns
        if any(
            fragment in column
            for fragment in forbidden
        )
    ]

    check(
        not bad,
        "Stage 3K outputs contain no return/momentum/Winner/outcome fields.",
        (
            "Prohibited outcome-like fields found: "
            + ", ".join(sorted(bad))
        ),
    )

    gate = (
        "H3_GDELT_ALIAS_COVERAGE_MISSINGNESS_GATE_PASSED"
        if not failures
        else "H3_GDELT_ALIAS_COVERAGE_MISSINGNESS_GATE_FAILED"
    )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Daily source files: {len(source_files)}",
        f"Eligible securities: {len(eligible)}",
        f"Eligible security-window rows: {len(window_security)}",
        f"Any-nonzero security rate: {any_nonzero_rate:.6f}",
        f"Repeat nonzero rate (eligible >=2): {repeat_nonzero_rate:.6f}",
        f"Nonzero security-window rate: {security_window_nonzero_rate:.6f}",
        f"HIGH-ambiguity any-nonzero rate: {high_any_nonzero_rate:.6f}",
        "",
        gate,
        "",
        (
            "A passing Stage 3K gate authorizes design/execution of the "
            "checkpointed full 2021-2025 direct-GDELT attention extraction."
        ),
        (
            "H3 return/outcome inference remains unauthorized until the full "
            "attention panel is complete, audited, and the H3 statistical "
            "specification is separately frozen."
        ),
    ]

    AUDIT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(text, end="")


if __name__ == "__main__":
    main()
