from pathlib import Path
import sys

import pandas as pd


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "price_download_manifest.csv"
)

YAHOO_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "price_availability_audit.csv"
)

TIINGO_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "tiingo_fallback_audit.csv"
)

TIINGO_CANDIDATE_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "tiingo_symbol_candidate_audit.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "price_source_resolutions.csv"
)


# --------------------------------------------------
# Helper
# --------------------------------------------------

def print_section(title):

    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


# --------------------------------------------------
# Start
# --------------------------------------------------

print_section("PRICE SOURCE RESOLUTION BUILD")


# --------------------------------------------------
# 1. Verify required files
# --------------------------------------------------

required_files = [
    MANIFEST_FILE,
    YAHOO_AUDIT_FILE,
    TIINGO_AUDIT_FILE,
    TIINGO_CANDIDATE_AUDIT_FILE,
]


for path in required_files:

    if not path.exists():

        print(
            f"\nERROR: Required file missing:\n"
            f"{path}"
        )

        sys.exit(1)


# --------------------------------------------------
# 2. Load datasets
# --------------------------------------------------

manifest = pd.read_csv(
    MANIFEST_FILE
)

yahoo_audit = pd.read_csv(
    YAHOO_AUDIT_FILE
)

tiingo_audit = pd.read_csv(
    TIINGO_AUDIT_FILE
)

candidate_audit = pd.read_csv(
    TIINGO_CANDIDATE_AUDIT_FILE
)


# --------------------------------------------------
# 3. Input validation
# --------------------------------------------------

print_section("1. INPUT VALIDATION")


manifest_duplicates = manifest.duplicated(
    subset=[
        "security_key",
        "project_ticker",
    ],
    keep=False,
)


if manifest_duplicates.any():

    print(
        "\nERROR: Duplicate manifest identities "
        "were detected."
    )

    print(
        manifest.loc[
            manifest_duplicates,
            [
                "security_key",
                "project_ticker",
            ],
        ].to_string(
            index=False
        )
    )

    sys.exit(1)


print(
    f"Manifest requests: "
    f"{len(manifest)}"
)

print(
    f"Yahoo audit rows: "
    f"{len(yahoo_audit)}"
)

print(
    f"Tiingo direct audit rows: "
    f"{len(tiingo_audit)}"
)

print(
    f"Tiingo candidate audit rows: "
    f"{len(candidate_audit)}"
)


# --------------------------------------------------
# 4. Merge Yahoo availability results
# --------------------------------------------------

print_section("2. BUILD PRIMARY SOURCE STATUS")


resolution = manifest.merge(
    yahoo_audit[
        [
            "security_key",
            "project_ticker",
            "yahoo_ticker",
            "status",
            "error_message",
        ]
    ],
    on=[
        "security_key",
        "project_ticker",
        "yahoo_ticker",
    ],
    how="left",
    validate="one_to_one",
)


# --------------------------------------------------
# Validate Yahoo results
# --------------------------------------------------

missing_yahoo = (
    resolution["status"]
    .isna()
)


if missing_yahoo.any():

    print(
        "\nERROR: Some manifest requests do not "
        "have a Yahoo availability result."
    )

    print(
        resolution.loc[
            missing_yahoo,
            [
                "security_key",
                "project_ticker",
            ],
        ].to_string(
            index=False
        )
    )

    sys.exit(1)


# --------------------------------------------------
# Initialize source-resolution fields
# --------------------------------------------------

resolution["primary_source"] = (
    "Yahoo Finance"
)

resolution["primary_symbol"] = (
    resolution["yahoo_ticker"]
)

resolution["primary_status"] = (
    resolution["status"]
)

resolution["fallback_source"] = ""

resolution["fallback_symbol"] = ""

resolution["source_url"] = ""

resolution["resolution_status"] = (
    resolution["primary_status"]
    .apply(
        lambda value:
            "PRIMARY_AVAILABLE"
            if value == "AVAILABLE"
            else "FALLBACK_REQUIRED"
    )
)

resolution["notes"] = (
    resolution["error_message"]
    .fillna("")
)


# --------------------------------------------------
# 5. Normalize direct Tiingo audit
# --------------------------------------------------

print_section("3. APPLY DIRECT TIINGO FALLBACKS")


tiingo_audit = (
    tiingo_audit
    .drop_duplicates(
        subset=[
            "security_key",
            "project_ticker",
        ],
        keep="last",
    )
    .reset_index(
        drop=True
    )
)


validated_tiingo = tiingo_audit[
    tiingo_audit["tiingo_status"]
    == "VALIDATED"
].copy()


print(
    f"Validated direct Tiingo fallbacks: "
    f"{len(validated_tiingo)}"
)


# --------------------------------------------------
# Apply direct-symbol Tiingo fallbacks
# --------------------------------------------------

for _, tiingo_row in (
    validated_tiingo.iterrows()
):

    security_key = str(
        tiingo_row["security_key"]
    )

    project_ticker = str(
        tiingo_row["project_ticker"]
    )

    tiingo_symbol = str(
        tiingo_row["tiingo_symbol"]
    )


    mask = (
        (
            resolution["security_key"]
            == security_key
        )
        &
        (
            resolution["project_ticker"]
            == project_ticker
        )
    )


    match_count = int(
        mask.sum()
    )


    if match_count != 1:

        print(
            "\nERROR: Expected exactly one "
            "resolution row for:"
        )

        print(
            f"{security_key} / "
            f"{project_ticker}"
        )

        print(
            f"Matches found: "
            f"{match_count}"
        )

        sys.exit(1)


    resolution.loc[
        mask,
        "fallback_source",
    ] = "Tiingo"


    resolution.loc[
        mask,
        "fallback_symbol",
    ] = tiingo_symbol


    resolution.loc[
        mask,
        "resolution_status",
    ] = "FALLBACK_VALIDATED"


    resolution.loc[
        mask,
        "source_url",
    ] = (
        "https://api.tiingo.com/"
        f"tiingo/daily/{tiingo_symbol}"
    )


    original_note = (
        resolution.loc[
            mask,
            "notes",
        ]
        .iloc[0]
    )


    rows_returned = int(
        tiingo_row[
            "rows_returned"
        ]
    )

    null_count = int(
        tiingo_row[
            "required_null_count"
        ]
    )

    duplicate_dates = int(
        tiingo_row[
            "duplicate_dates"
        ]
    )


    fallback_note = (
        f"Tiingo direct-symbol fallback validated. "
        f"Rows returned: {rows_returned}. "
        f"Returned range: "
        f"{tiingo_row['first_returned_date']} "
        f"through "
        f"{tiingo_row['last_returned_date']}. "
        f"Required-field null count: "
        f"{null_count}. "
        f"Duplicate dates: "
        f"{duplicate_dates}."
    )


    if original_note:

        combined_note = (
            f"Yahoo Finance: "
            f"{original_note} "
            f"{fallback_note}"
        )

    else:

        combined_note = (
            fallback_note
        )


    resolution.loc[
        mask,
        "notes",
    ] = combined_note


# --------------------------------------------------
# 6. Record failed direct Tiingo attempts
# --------------------------------------------------

unresolved_tiingo = tiingo_audit[
    tiingo_audit["tiingo_status"]
    != "VALIDATED"
].copy()


for _, tiingo_row in (
    unresolved_tiingo.iterrows()
):

    security_key = str(
        tiingo_row["security_key"]
    )

    project_ticker = str(
        tiingo_row["project_ticker"]
    )


    mask = (
        (
            resolution["security_key"]
            == security_key
        )
        &
        (
            resolution["project_ticker"]
            == project_ticker
        )
    )


    if int(mask.sum()) != 1:

        continue


    # Do not overwrite anything already resolved.
    if (
        resolution.loc[
            mask,
            "resolution_status",
        ].iloc[0]
        == "FALLBACK_VALIDATED"
    ):

        continue


    original_note = (
        resolution.loc[
            mask,
            "notes",
        ]
        .iloc[0]
    )


    tiingo_error = (
        tiingo_row.get(
            "error_message",
            "",
        )
    )


    if pd.isna(
        tiingo_error
    ):

        tiingo_error = ""


    attempt_note = (
        f" Tiingo direct-symbol attempt "
        f"returned "
        f"{tiingo_row['tiingo_status']}."
    )


    if tiingo_error:

        attempt_note += (
            f" {tiingo_error}"
        )


    resolution.loc[
        mask,
        "notes",
    ] = (
        original_note
        + attempt_note
    )


# --------------------------------------------------
# 7. Apply validated provider-symbol candidates
# --------------------------------------------------

print_section(
    "4. APPLY TIINGO SYMBOL MAPPINGS"
)


candidate_audit = (
    candidate_audit
    .drop_duplicates(
        subset=[
            "security_key",
            "original_ticker",
            "candidate_ticker",
        ],
        keep="last",
    )
    .reset_index(
        drop=True
    )
)


validated_candidates = candidate_audit[
    candidate_audit["status"]
    == "CANDIDATE_FULL_COVERAGE"
].copy()


print(
    f"Validated provider-symbol mappings: "
    f"{len(validated_candidates)}"
)


for _, candidate_row in (
    validated_candidates.iterrows()
):

    security_key = str(
        candidate_row["security_key"]
    )

    original_ticker = str(
        candidate_row[
            "original_ticker"
        ]
    )

    candidate_ticker = str(
        candidate_row[
            "candidate_ticker"
        ]
    )


    mask = (
        (
            resolution["security_key"]
            == security_key
        )
        &
        (
            resolution["project_ticker"]
            == original_ticker
        )
    )


    match_count = int(
        mask.sum()
    )


    if match_count != 1:

        print(
            "\nERROR: Expected exactly one "
            "resolution row for provider-symbol "
            "mapping:"
        )

        print(
            f"{security_key} / "
            f"{original_ticker} "
            f"-> {candidate_ticker}"
        )

        print(
            f"Matches found: "
            f"{match_count}"
        )

        sys.exit(1)


    # ----------------------------------------------
    # Candidate source
    # ----------------------------------------------

    resolution.loc[
        mask,
        "fallback_source",
    ] = "Tiingo"


    resolution.loc[
        mask,
        "fallback_symbol",
    ] = candidate_ticker


    resolution.loc[
        mask,
        "resolution_status",
    ] = "FALLBACK_VALIDATED"


    resolution.loc[
        mask,
        "source_url",
    ] = (
        "https://api.tiingo.com/"
        f"tiingo/daily/{candidate_ticker}"
    )


    # ----------------------------------------------
    # Candidate audit note
    # ----------------------------------------------

    original_note = (
        resolution.loc[
            mask,
            "notes",
        ]
        .iloc[0]
    )


    rows_returned = int(
        candidate_row[
            "rows_returned"
        ]
    )

    start_gap = int(
        candidate_row[
            "start_gap_days"
        ]
    )

    end_gap = int(
        candidate_row[
            "end_gap_days"
        ]
    )

    null_count = int(
        candidate_row[
            "required_null_count"
        ]
    )

    duplicate_dates = int(
        candidate_row[
            "duplicate_dates"
        ]
    )


    mapping_note = (
        f" Tiingo direct symbol "
        f"{original_ticker} was unavailable. "
        f"Provider symbol "
        f"{candidate_ticker} returned full "
        f"historical coverage for the original "
        f"manifest interval. "
        f"Rows returned: "
        f"{rows_returned}. "
        f"Returned range: "
        f"{candidate_row['first_returned_date']} "
        f"through "
        f"{candidate_row['last_returned_date']}. "
        f"Start gap: "
        f"{start_gap} calendar day(s). "
        f"End gap: "
        f"{end_gap} calendar day(s). "
        f"Required-field null count: "
        f"{null_count}. "
        f"Duplicate dates: "
        f"{duplicate_dates}."
    )


    resolution.loc[
        mask,
        "notes",
    ] = (
        original_note
        + mapping_note
    )

# --------------------------------------------------
# Apply validated manual INFO fallback
# --------------------------------------------------

print_section(
    "5. APPLY MANUAL INFO FALLBACK"
)


info_mask = (
    (resolution["security_key"] == "INFO")
    &
    (resolution["project_ticker"] == "INFO")
)


if int(info_mask.sum()) != 1:

    print(
        "\nERROR: Expected exactly one "
        "INFO resolution row."
    )

    print(
        f"Matches found: "
        f"{int(info_mask.sum())}"
    )

    sys.exit(1)


resolution.loc[
    info_mask,
    "fallback_source",
] = "Investing.com"


resolution.loc[
    info_mask,
    "fallback_symbol",
] = "INFO_OLD"


resolution.loc[
    info_mask,
    "resolution_status",
] = "FALLBACK_VALIDATED"


resolution.loc[
    info_mask,
    "source_url",
] = (
    "https://www.investing.com/"
    "equities/markit-ltd-historical-data"
)


original_note = (
    resolution.loc[
        info_mask,
        "notes",
    ]
    .iloc[0]
)


info_note = (
    " Manual archived-security fallback validated. "
    "Investing.com instrument INFO_OLD returned "
    "543 daily OHLCV observations from 2020-01-02 "
    "through 2022-02-25. Raw schema passed validation, "
    "dates were unique, OHLC relationships were valid, "
    "there were zero missing OHLC or volume values, "
    "and the final 2022-02-25 close of 108.61 matched "
    "the independently expected IHS Markit endpoint. "
    "Adjusted-price reconstruction remains pending."
)


resolution.loc[
    info_mask,
    "notes",
] = (
    original_note
    + info_note
)


print(
    "INFO -> Investing.com / INFO_OLD "
    "FALLBACK_VALIDATED"
)

# --------------------------------------------------
# 8. Select final output columns
# --------------------------------------------------

output_columns = [
    "security_key",
    "project_ticker",
    "primary_source",
    "primary_symbol",
    "primary_status",
    "fallback_source",
    "fallback_symbol",
    "resolution_status",
    "source_url",
    "notes",
]


resolution = (
    resolution[
        output_columns
    ]
    .sort_values(
        [
            "resolution_status",
            "security_key",
            "project_ticker",
        ]
    )
    .reset_index(
        drop=True
    )
)


# --------------------------------------------------
# 9. Final validation
# --------------------------------------------------

print_section(
    "5. RESOLUTION SUMMARY"
)


status_counts = (
    resolution[
        "resolution_status"
    ]
    .value_counts()
)


print(
    status_counts.to_string()
)


primary_count = int(
    (
        resolution[
            "resolution_status"
        ]
        == "PRIMARY_AVAILABLE"
    ).sum()
)


fallback_count = int(
    (
        resolution[
            "resolution_status"
        ]
        == "FALLBACK_VALIDATED"
    ).sum()
)


unresolved_count = int(
    (
        resolution[
            "resolution_status"
        ]
        == "FALLBACK_REQUIRED"
    ).sum()
)


resolved_count = (
    primary_count
    + fallback_count
)


print(
    f"\nTotal requests: "
    f"{len(resolution)}"
)

print(
    f"Primary Yahoo requests: "
    f"{primary_count}"
)

print(
    f"Validated fallback requests: "
    f"{fallback_count}"
)

print(
    f"Resolved requests: "
    f"{resolved_count}"
)

print(
    f"Still unresolved: "
    f"{unresolved_count}"
)


# --------------------------------------------------
# Validate total request count
# --------------------------------------------------

if len(resolution) != len(manifest):

    print(
        "\nERROR: Resolution table row count "
        "does not match manifest."
    )

    print(
        f"Manifest: "
        f"{len(manifest)}"
    )

    print(
        f"Resolution table: "
        f"{len(resolution)}"
    )

    sys.exit(1)


print(
    "\nPASS: Resolution row count "
    "matches manifest."
)


# --------------------------------------------------
# 10. Show unresolved requests
# --------------------------------------------------

print_section(
    "6. UNRESOLVED SYMBOLS"
)


unresolved = resolution[
    resolution[
        "resolution_status"
    ]
    == "FALLBACK_REQUIRED"
]


if unresolved.empty:

    print(
        "None."
    )

else:

    print(
        unresolved[
            [
                "security_key",
                "project_ticker",
                "primary_status",
                "notes",
            ]
        ].to_string(
            index=False
        )
    )


# --------------------------------------------------
# 11. Save reference table
# --------------------------------------------------

print_section(
    "7. SAVE REFERENCE TABLE"
)


OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


resolution.to_csv(
    OUTPUT_FILE,
    index=False,
)


print(
    f"Reference table saved:\n"
    f"{OUTPUT_FILE}"
)


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section(
    "BUILD RESULT"
)


if unresolved_count == 0:

    print(
        "ALL PRICE SOURCES RESOLVED."
    )


else:

    print(
        f"{resolved_count} OF "
        f"{len(resolution)} PRICE REQUESTS "
        "HAVE A VALIDATED SOURCE."
    )

    print(
        f"{unresolved_count} REQUEST(S) "
        "STILL REQUIRE RESOLUTION."
    )