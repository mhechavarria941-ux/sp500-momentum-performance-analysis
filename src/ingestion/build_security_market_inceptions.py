from pathlib import Path
import sys

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_market_inceptions.csv"
)

INTEGRITY_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_integrity_audit.csv"
)

DOWNLOAD_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_download_audit.csv"
)

VALIDATION_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "security_market_inception_validation.csv"
)


# ============================================================
# EXPECTED INCEPTION-BOUNDARY SECURITIES
# ============================================================

EXPECTED_SECURITIES = {
    "AMTM",
    "CARR",
    "CEG",
    "FTRE",
    "GEHC",
    "GEV",
    "KVUE",
    "MBC",
    "OGN",
    "OTIS",
    "PHIN",
    "Q",
    "SNDK",
    "SOLS",
    "SOLV",
    "VLTO",
    "VNT",
}


# ============================================================
# DISPLAY
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    260,
)

pd.set_option(
    "display.max_colwidth",
    120,
)


def print_section(title):

    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


# ============================================================
# REFERENCE POPULATION
# ============================================================

records = [

    # --------------------------------------------------------
    # 2020
    # --------------------------------------------------------

    {
        "security_key":
            "CARR",

        "project_ticker":
            "CARR",

        "company_name":
            "Carrier Global Corporation",

        "market_inception_date":
            "2020-03-18",

        "regular_way_start_date":
            "2020-04-03",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "United Technologies Corporation",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXPECTED",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "SEC / Company Press Release",

        "source_url_primary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/101829/"
                "000114036120005675/"
                "nc10009877x1_ex99-1.htm"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "UTC stated that when-issued trading "
                "for Carrier was expected to begin on "
                "or around 2020-03-18 under CARR-WI. "
                "Regular-way trading began following "
                "the separation on 2020-04-03. "
                "Yahoo history currently begins "
                "2020-03-19, so the approximate "
                "when-issued boundary must remain "
                "visible during validation."
            ),
    },

    {
        "security_key":
            "OTIS",

        "project_ticker":
            "OTIS",

        "company_name":
            "Otis Worldwide Corporation",

        "market_inception_date":
            "2020-03-18",

        "regular_way_start_date":
            "2020-04-03",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "United Technologies Corporation",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXPECTED",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "SEC / Company Press Release",

        "source_url_primary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/101829/"
                "000114036120005675/"
                "nc10009877x1_ex99-1.htm"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "UTC stated that when-issued trading "
                "for Otis was expected to begin on "
                "or around 2020-03-18 under OTIS-WI. "
                "Regular-way trading began following "
                "the separation on 2020-04-03. "
                "Yahoo history currently begins "
                "2020-03-19."
            ),
    },

    {
        "security_key":
            "VNT",

        "project_ticker":
            "VNT",

        "company_name":
            "Vontier Corporation",

        "market_inception_date":
            "2020-09-24",

        "regular_way_start_date":
            "2020-10-09",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Fortive Corporation",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company Investor Relations",

        "source_url_primary":
            (
                "https://investors.fortive.com/"
                "news-events/press-releases/"
                "detail/109/"
                "fortive-announces-expected-"
                "completion-date-of-october-9-"
                "2020-for-spin-off-of-vontier"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Fortive announced that Vontier "
                "when-issued trading was expected "
                "to begin 2020-09-24 under VNT WI. "
                "Regular-way trading was expected "
                "to begin 2020-10-09."
            ),
    },

    # --------------------------------------------------------
    # 2021
    # --------------------------------------------------------

    {
        "security_key":
            "OGN",

        "project_ticker":
            "OGN",

        "company_name":
            "Organon & Co.",

        "market_inception_date":
            "2021-05-14",

        "regular_way_start_date":
            "2021-06-03",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Merck & Co., Inc.",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_WINDOW_PLUS_PROVIDER_OBSERVATION",

        "evidence_status":
            "CORROBORATED",

        "source_type":
            "SEC Information Statement",

        "source_url_primary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/1821825/"
                "000119312521140380/"
                "d56612dex991.htm"
            ),

        "source_url_secondary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/1821825/"
                "000182182522000002/"
                "ogn-20211231.htm"
            ),

        "notes":
            (
                "Organon's information statement "
                "said a when-issued market was "
                "expected on or shortly before the "
                "2021-05-17 record date. The first "
                "validated provider observation is "
                "2021-05-14, consistent with that "
                "official window. Regular-way "
                "trading commenced 2021-06-03."
            ),
    },

    # --------------------------------------------------------
    # 2022
    # --------------------------------------------------------

    {
        "security_key":
            "CEG",

        "project_ticker":
            "CEG",

        "company_name":
            "Constellation Energy Corporation",

        "market_inception_date":
            "2022-01-19",

        "regular_way_start_date":
            "2022-02-02",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Exelon Corporation",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "EXCHANGE_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Nasdaq Corporate Actions",

        "source_url_primary":
            (
                "https://www.nasdaqtrader.com/"
                "TraderNews.aspx?id=eca2022-5"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Nasdaq established the CEGVV "
                "when-issued market with first trade "
                "date 2022-01-19. The symbol changed "
                "to CEG when regular-way trading "
                "began 2022-02-02."
            ),
    },

    {
        "security_key":
            "GEHC",

        "project_ticker":
            "GEHC",

        "company_name":
            "GE HealthCare Technologies Inc.",

        "market_inception_date":
            "2022-12-16",

        "regular_way_start_date":
            "2023-01-04",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "General Electric Company",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "COMPANY_10K_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "SEC Form 10-K",

        "source_url_primary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/1932393/"
                "000193239323000025/"
                "gehc-20221231.htm"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "GE HealthCare's Form 10-K states "
                "that a when-issued trading market "
                "began 2022-12-16 and regular-way "
                "trading began 2023-01-04. Yahoo "
                "contains a 2022-12-15 observation, "
                "which will remain a separate "
                "one-session review rather than "
                "changing the official inception."
            ),
    },

    {
        "security_key":
            "MBC",

        "project_ticker":
            "MBC",

        "company_name":
            "MasterBrand, Inc.",

        "market_inception_date":
            "2022-12-09",

        "regular_way_start_date":
            "2022-12-15",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Fortune Brands Home & Security, Inc.",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company Investor Relations",

        "source_url_primary":
            (
                "https://ir.fbin.com/"
                "news-releases/news-release-details/"
                "fortune-brands-board-directors-"
                "approves-separation-masterbrand"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Fortune Brands stated that "
                "MasterBrand when-issued trading "
                "would commence on or about "
                "2022-12-09 under MBC WI, with "
                "regular-way MBC trading beginning "
                "2022-12-15."
            ),
    },

    # --------------------------------------------------------
    # 2023
    # --------------------------------------------------------

    {
        "security_key":
            "FTRE",

        "project_ticker":
            "FTRE",

        "company_name":
            "Fortrea Holdings Inc.",

        "market_inception_date":
            "2023-06-16",

        "regular_way_start_date":
            "2023-07-03",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Laboratory Corporation of America Holdings",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company Investor Relations",

        "source_url_primary":
            (
                "https://ir.fortrea.com/"
                "news-releases/news-release-details/"
                "labcorp-announces-additional-"
                "information-connection-its-spin"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Labcorp expected Fortrea's "
                "when-issued market to begin on or "
                "around 2023-06-16 under FTREV. "
                "Regular-way trading was expected "
                "to begin 2023-07-03."
            ),
    },

    {
        "security_key":
            "KVUE",

        "project_ticker":
            "KVUE",

        "company_name":
            "Kenvue Inc.",

        "market_inception_date":
            "2023-05-04",

        "regular_way_start_date":
            "2023-05-04",

        "event_type":
            "IPO",

        "parent_company":
            "Johnson & Johnson",

        "inception_market_type":
            "REGULAR_WAY_IPO",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company Investor Relations",

        "source_url_primary":
            (
                "https://investors.kenvue.com/"
                "financial-news/news-details/2023/"
                "Kenvue-to-Begin-Trading-on-the-"
                "New-York-Stock-Exchange/"
                "default.aspx"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Kenvue began NYSE trading under "
                "KVUE on 2023-05-04 in connection "
                "with its IPO. No independent "
                "public Kenvue price history exists "
                "before the IPO."
            ),
    },

    {
        "security_key":
            "PHIN",

        "project_ticker":
            "PHIN",

        "company_name":
            "PHINIA Inc.",

        "market_inception_date":
            "2023-06-28",

        "regular_way_start_date":
            "2023-07-05",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "BorgWarner Inc.",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_RULE_DERIVED",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "SEC Information Statement",

        "source_url_primary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/1968915/"
                "000162828023018828/"
                "exhibit991-form10.htm"
            ),

        "source_url_secondary":
            (
                "https://www.borgwarner.com/"
                "newsroom/press-releases/2023/"
                "06/14/"
                "borgwarner-announces-anticipated-"
                "completion-date-of-phinia-spin-off"
            ),

        "notes":
            (
                "PHINIA stated that a when-issued "
                "market would develop on the third "
                "trading day before the 2023-07-03 "
                "distribution date. That produces "
                "2023-06-28. Regular-way trading "
                "began 2023-07-05 after the July 4 "
                "market holiday."
            ),
    },

    {
        "security_key":
            "VLTO",

        "project_ticker":
            "VLTO",

        "company_name":
            "Veralto Corporation",

        "market_inception_date":
            "2023-09-27",

        "regular_way_start_date":
            "2023-10-02",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Danaher Corporation",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company Investor Relations / SEC Form 10-K",

        "source_url_primary":
        (
            "https://investors.danaher.com/"
            "2023-08-25-Danaher-Declares-pro-Rata-"
            "Dividend-of-Veralto-Common-Stock-and-"
            "Announces-Expected-When-issued-Trading-"
            "of-Veralto-Common-Stock"
        ),

        "source_url_secondary":
        (
            "https://www.sec.gov/Archives/"
            "edgar/data/1967680/"
            "000196768024000033/"
            "vlto-20231231.htm"
        ),

        "notes":
        (
            "Danaher explicitly announced that "
            "Veralto when-issued trading was expected "
            "to begin 2023-09-27 under VLTO WI. "
            "Regular-way VLTO trading began "
            "2023-10-02. Yahoo history begins "
            "2023-10-04. Tiingo subsequently "
            "identified the when-issued instrument "
            "as VLTO-W and returned all three "
            "2023-09-27 through 2023-09-29 sessions."
        ),
    },

    # --------------------------------------------------------
    # 2024
    # --------------------------------------------------------

    {
        "security_key":
            "AMTM",

        "project_ticker":
            "AMTM",

        "company_name":
            "Amentum Holdings, Inc.",

        "market_inception_date":
            "2024-09-24",

        "regular_way_start_date":
            "2024-09-30",

        "event_type":
            "SPIN_OFF_AND_COMBINATION",

        "parent_company":
            "Jacobs Solutions Inc.",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "SEC Filing",

        "source_url_primary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/52988/"
                "000119312524219294/"
                "d876828dex991.htm"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Jacobs expected Amentum "
                "when-issued trading to commence "
                "on or about 2024-09-24 under "
                "AMTM WI. Regular-way trading "
                "began 2024-09-30."
            ),
    },

    {
        "security_key":
            "GEV",

        "project_ticker":
            "GEV",

        "company_name":
            "GE Vernova Inc.",

        "market_inception_date":
            "2024-03-27",

        "regular_way_start_date":
            "2024-04-02",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "General Electric Company",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company Press Release",

        "source_url_primary":
            (
                "https://www.ge.com/news/"
                "press-releases/"
                "ge-board-of-directors-approves-"
                "spin-off-of-ge-vernova-"
                "ge-vernova-and-ge-aerospace-to"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "GE anticipated when-issued "
                "GE Vernova trading beginning on "
                "or about 2024-03-27 under GEV WI. "
                "Regular-way GEV trading began "
                "2024-04-02."
            ),
    },

    {
        "security_key":
            "SOLV",

        "project_ticker":
            "SOLV",

        "company_name":
            "Solventum Corporation",

        "market_inception_date":
            "2024-03-26",

        "regular_way_start_date":
            "2024-04-01",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "3M Company",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company SEC Filing",

        "source_url_primary":
            (
                "https://investors.solventum.com/"
                "financials/sec-filings/content/"
                "0001628280-24-010988/"
                "solventum-effectiveness8xk.htm"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Solventum expected when-issued "
                "trading to begin on or about "
                "2024-03-26 under SOLV WI. "
                "Regular-way trading began "
                "2024-04-01."
            ),
    },

    # --------------------------------------------------------
    # 2025
    # --------------------------------------------------------

    {
        "security_key":
            "SNDK",

        "project_ticker":
            "SNDK",

        "company_name":
            "Sandisk Corporation",

        "market_inception_date":
            "2025-02-13",

        "regular_way_start_date":
            "2025-02-24",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Western Digital Corporation",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "EXCHANGE_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Nasdaq Corporate Actions / SEC",

        "source_url_primary":
            (
                "https://www.nasdaqtrader.com/"
                "TraderNews.aspx?id=ECA2025-38"
            ),

        "source_url_secondary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/2023554/"
                "000119312525027285/"
                "d229754d8k.htm"
            ),

        "notes":
            (
                "Nasdaq records Sandisk's "
                "when-issued market beginning "
                "2025-02-13 under SNDKV. "
                "Regular-way trading under SNDK "
                "began 2025-02-24."
            ),
    },

    {
        "security_key":
            "SOLS",

        "project_ticker":
            "SOLS",

        "company_name":
            "Solstice Advanced Materials Inc.",

        "market_inception_date":
            "2025-10-20",

        "regular_way_start_date":
            "2025-10-30",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "Honeywell International Inc.",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "Company Investor Relations",

        "source_url_primary":
            (
                "https://investor.honeywell.com/"
                "news-releases/news-release-details/"
                "honeywell-board-directors-"
                "sets-record-date-and-announces"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "Honeywell anticipated Solstice "
                "when-issued trading beginning "
                "on or about 2025-10-20. "
                "Regular-way SOLS trading began "
                "2025-10-30."
            ),
    },

    {
        "security_key":
            "Q",

        "project_ticker":
            "Q",

        "company_name":
            "Qnity Electronics, Inc.",

        "market_inception_date":
            "2025-10-27",

        "regular_way_start_date":
            "2025-11-03",

        "event_type":
            "SPIN_OFF",

        "parent_company":
            "DuPont de Nemours, Inc.",

        "inception_market_type":
            "WHEN_ISSUED",

        "date_basis":
            "OFFICIAL_EXACT",

        "evidence_status":
            "VERIFIED",

        "source_type":
            "SEC Information Statement",

        "source_url_primary":
            (
                "https://www.sec.gov/Archives/"
                "edgar/data/2058873/"
                "000119312525240313/"
                "d21160dex991.htm"
            ),

        "source_url_secondary":
            "",

        "notes":
            (
                "NYSE advised that Qnity "
                "when-issued trading would begin "
                "2025-10-27 under Q WI. "
                "Regular-way trading under Q "
                "began 2025-11-03."
            ),
    },
]


# ============================================================
# BUILD REFERENCE DATAFRAME
# ============================================================

print_section(
    "BUILD SECURITY MARKET INCEPTION REFERENCE"
)


reference = pd.DataFrame(
    records
)


# ============================================================
# 1. BASIC REFERENCE VALIDATION
# ============================================================

print_section(
    "1. REFERENCE STRUCTURE VALIDATION"
)


print(
    f"Rows defined: "
    f"{len(reference)}"
)


if len(reference) != 17:

    print(
        "\nERROR: Expected exactly "
        "17 legitimate inception cases."
    )

    sys.exit(1)


duplicate_keys = (
    reference[
        [
            "security_key",
            "project_ticker",
        ]
    ]
    .duplicated()
)


if duplicate_keys.any():

    print(
        "\nERROR: Duplicate security/ticker "
        "reference rows detected."
    )

    print(
        reference[
            duplicate_keys
        ].to_string(
            index=False
        )
    )

    sys.exit(1)


actual_securities = set(
    reference[
        "security_key"
    ]
)


if actual_securities != EXPECTED_SECURITIES:

    print(
        "\nERROR: Reference security set "
        "does not match expected cases."
    )

    print(
        "\nMissing:"
    )

    print(
        sorted(
            EXPECTED_SECURITIES
            - actual_securities
        )
    )

    print(
        "\nUnexpected:"
    )

    print(
        sorted(
            actual_securities
            - EXPECTED_SECURITIES
        )
    )

    sys.exit(1)


reference[
    "market_inception_date"
] = pd.to_datetime(
    reference[
        "market_inception_date"
    ],
    errors="raise",
)


reference[
    "regular_way_start_date"
] = pd.to_datetime(
    reference[
        "regular_way_start_date"
    ],
    errors="raise",
)


invalid_order = reference[
    reference[
        "regular_way_start_date"
    ]
    <
    reference[
        "market_inception_date"
    ]
]


if not invalid_order.empty:

    print(
        "\nERROR: Regular-way trading "
        "precedes market inception."
    )

    print(
        invalid_order.to_string(
            index=False
        )
    )

    sys.exit(1)


print(
    "PASS: 17 unique inception "
    "records are structurally valid."
)


# ============================================================
# 2. LOAD CURRENT INTEGRITY AUDIT
# ============================================================

print_section(
    "2. RECONCILE WITH CURRENT BLOCKING CASES"
)


if not INTEGRITY_FILE.exists():

    print(
        "\nERROR: Integrity audit file "
        "does not exist:"
    )

    print(
        INTEGRITY_FILE
    )

    sys.exit(1)


integrity = pd.read_csv(
    INTEGRITY_FILE
)


blocking = integrity[
    integrity[
        "status"
    ]
    == "REVIEW_BLOCKING"
].copy()


blocking_securities = set(
    blocking[
        "security_key"
    ]
)


print(
    f"Current blocking cases: "
    f"{len(blocking_securities)}"
)


print(
    f"Expected legitimate inception cases: "
    f"{len(EXPECTED_SECURITIES)}"
)


# DISCA is deliberately NOT an inception exemption.
# Its incomplete historical source was resolved
# separately through the validated source composite.

non_disca_blocking = (
    blocking_securities
    - {
        "DISCA"
    }
)


if (
    non_disca_blocking
    != EXPECTED_SECURITIES
):

    print(
        "\nERROR:"
    )

    print(
        "The current blocking set does not "
        "match the 17 expected legitimate "
        "security-inception cases."
    )

    print(
        "\nBlocking but not referenced:"
    )

    print(
        sorted(
            non_disca_blocking
            - EXPECTED_SECURITIES
        )
    )

    print(
        "\nReferenced but not currently blocking:"
    )

    print(
        sorted(
            EXPECTED_SECURITIES
            - non_disca_blocking
        )
    )

    sys.exit(1)


print(
    "PASS:"
)

print(
    "All 17 legitimate start-boundary "
    "cases are represented."
)

print(
    "DISCA remains correctly excluded "
    "from inception exemptions."
)


# ============================================================
# 3. LOAD SPY TRADING CALENDAR
# ============================================================

print_section(
    "3. BUILD SPY SESSION REFERENCE"
)


if not DOWNLOAD_AUDIT_FILE.exists():

    print(
        "\nERROR: Download audit not found."
    )

    sys.exit(1)


download_audit = pd.read_csv(
    DOWNLOAD_AUDIT_FILE
)


download_audit = (
    download_audit
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


spy_rows = download_audit[
    download_audit[
        "security_key"
    ]
    == "SPY_ETF"
]


if len(spy_rows) != 1:

    print(
        "\nERROR: Expected exactly "
        "one SPY_ETF row."
    )

    sys.exit(1)


spy_file = (
    PROJECT_ROOT
    / str(
        spy_rows.iloc[0][
            "output_file"
        ]
    )
)


if not spy_file.exists():

    print(
        "\nERROR: SPY raw file missing:"
    )

    print(
        spy_file
    )

    sys.exit(1)


spy = pd.read_csv(
    spy_file
)


spy_dates = pd.to_datetime(
    spy[
        "Date"
    ],
    errors="raise",
    utc=True,
)


spy_dates = (
    spy_dates
    .dt
    .tz_convert(None)
    .dt
    .normalize()
    .drop_duplicates()
    .sort_values()
    .reset_index(
        drop=True
    )
)


print(
    f"SPY sessions available: "
    f"{len(spy_dates)}"
)

print(
    f"First SPY session: "
    f"{spy_dates.min().date()}"
)

print(
    f"Last SPY session: "
    f"{spy_dates.max().date()}"
)


# ============================================================
# 4. VALIDATE EACH INCEPTION AGAINST OBSERVED HISTORY
# ============================================================

print_section(
    "4. INCEPTION-TO-PROVIDER VALIDATION"
)


validation_records = []


for _, inception_row in (
    reference.iterrows()
):

    security_key = (
        inception_row[
            "security_key"
        ]
    )

    project_ticker = (
        inception_row[
            "project_ticker"
        ]
    )


    current = integrity[
        (
            integrity[
                "security_key"
            ]
            == security_key
        )
        &
        (
            integrity[
                "project_ticker"
            ]
            == project_ticker
        )
    ]


    if len(current) != 1:

        print(
            "\nERROR: Expected exactly "
            f"one integrity row for "
            f"{security_key}."
        )

        sys.exit(1)


    current = current.iloc[0]


    requested_start = pd.Timestamp(
        current[
            "requested_start"
        ]
    ).normalize()


    provider_first_date = pd.Timestamp(
        current[
            "first_date"
        ]
    ).normalize()


    market_inception = (
        inception_row[
            "market_inception_date"
        ]
        .normalize()
    )


    regular_way_start = (
        inception_row[
            "regular_way_start_date"
        ]
        .normalize()
    )


    effective_expected_start = max(
        requested_start,
        market_inception,
    )


    # --------------------------------------------------------
    # Sessions requested before the security existed.
    #
    # These are not missing-price failures.
    # --------------------------------------------------------

    pre_inception_sessions = spy_dates[
        (
            spy_dates
            >= requested_start
        )
        &
        (
            spy_dates
            < effective_expected_start
        )
    ]


    pre_inception_count = len(
        pre_inception_sessions
    )


    # --------------------------------------------------------
    # Sessions after independent-market inception but
    # before our provider begins.
    #
    # These ARE real provider-boundary differences
    # and must remain visible.
    # --------------------------------------------------------

    post_inception_gap = spy_dates[
        (
            spy_dates
            >= effective_expected_start
        )
        &
        (
            spy_dates
            < provider_first_date
        )
    ]


    post_inception_gap_count = len(
        post_inception_gap
    )


    # --------------------------------------------------------
    # Provider observation occurring before the official
    # reference inception.
    # --------------------------------------------------------

    provider_pre_inception = (
        provider_first_date
        < market_inception
    )


    provider_pre_inception_days = (
        (
            market_inception
            - provider_first_date
        ).days
        if provider_pre_inception
        else 0
    )


    # --------------------------------------------------------
    # Classification
    # --------------------------------------------------------

    if provider_pre_inception:

        validation_status = (
            "PROVIDER_PRE_INCEPTION_REVIEW"
        )


    elif post_inception_gap_count == 0:

        validation_status = (
            "VALIDATED_INCEPTION_BOUNDARY"
        )


    elif post_inception_gap_count <= 2:

        validation_status = (
            "SMALL_POST_INCEPTION_GAP_REVIEW"
        )


    else:

        validation_status = (
            "POST_INCEPTION_GAP_REVIEW"
        )


    first_missing_after_inception = (
        post_inception_gap.iloc[0].date()
        if post_inception_gap_count > 0
        else None
    )


    last_missing_after_inception = (
        post_inception_gap.iloc[-1].date()
        if post_inception_gap_count > 0
        else None
    )


    validation_records.append(
        {
            "security_key":
                security_key,

            "project_ticker":
                project_ticker,

            "company_name":
                inception_row[
                    "company_name"
                ],

            "requested_start":
                requested_start.date(),

            "market_inception_date":
                market_inception.date(),

            "regular_way_start_date":
                regular_way_start.date(),

            "provider_first_date":
                provider_first_date.date(),

            "pre_inception_requested_sessions":
                pre_inception_count,

            "post_inception_missing_sessions":
                post_inception_gap_count,

            "first_missing_after_inception":
                first_missing_after_inception,

            "last_missing_after_inception":
                last_missing_after_inception,

            "provider_pre_inception":
                provider_pre_inception,

            "provider_pre_inception_days":
                provider_pre_inception_days,

            "date_basis":
                inception_row[
                    "date_basis"
                ],

            "evidence_status":
                inception_row[
                    "evidence_status"
                ],

            "validation_status":
                validation_status,
        }
    )


validation = pd.DataFrame(
    validation_records
)


# ============================================================
# 5. DISPLAY VALIDATION
# ============================================================

print(
    validation[
        [
            "security_key",
            "requested_start",
            "market_inception_date",
            "provider_first_date",
            "pre_inception_requested_sessions",
            "post_inception_missing_sessions",
            "provider_pre_inception",
            "validation_status",
        ]
    ]
    .sort_values(
        [
            "validation_status",
            "security_key",
        ]
    )
    .to_string(
        index=False
    )
)


# ============================================================
# 6. SAVE REFERENCE
# ============================================================

print_section(
    "5. SAVE AUTHORITATIVE INCEPTION REFERENCE"
)


REFERENCE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


reference_to_save = (
    reference.copy()
)


reference_to_save[
    "market_inception_date"
] = (
    reference_to_save[
        "market_inception_date"
    ]
    .dt
    .strftime(
        "%Y-%m-%d"
    )
)


reference_to_save[
    "regular_way_start_date"
] = (
    reference_to_save[
        "regular_way_start_date"
    ]
    .dt
    .strftime(
        "%Y-%m-%d"
    )
)


reference_to_save = (
    reference_to_save
    .sort_values(
        [
            "market_inception_date",
            "security_key",
        ]
    )
    .reset_index(
        drop=True
    )
)


reference_to_save.to_csv(
    REFERENCE_FILE,
    index=False,
)


print(
    f"Saved:\n"
    f"{REFERENCE_FILE}"
)


# ============================================================
# 7. SAVE VALIDATION
# ============================================================

print_section(
    "6. SAVE INCEPTION VALIDATION"
)


VALIDATION_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


validation = (
    validation
    .sort_values(
        [
            "validation_status",
            "security_key",
        ]
    )
    .reset_index(
        drop=True
    )
)


validation.to_csv(
    VALIDATION_FILE,
    index=False,
)


print(
    f"Saved:\n"
    f"{VALIDATION_FILE}"
)


# ============================================================
# 8. SUMMARY
# ============================================================

print_section(
    "7. VALIDATION SUMMARY"
)


print(
    f"Reference rows: "
    f"{len(reference_to_save)}"
)


print(
    "\nEvidence status:"
)

print(
    reference_to_save[
        "evidence_status"
    ]
    .value_counts()
    .to_string()
)


print(
    "\nProvider-boundary validation:"
)

print(
    validation[
        "validation_status"
    ]
    .value_counts()
    .to_string()
)


print(
    "\nTotal requested SPY sessions "
    "correctly removed as pre-inception:"
)

print(
    int(
        validation[
            "pre_inception_requested_sessions"
        ]
        .sum()
    )
)


# ============================================================
# 9. FOLLOW-UP CASES
# ============================================================

print_section(
    "8. CASES REQUIRING FOLLOW-UP"
)


follow_up = validation[
    validation[
        "validation_status"
    ]
    != "VALIDATED_INCEPTION_BOUNDARY"
]


if follow_up.empty:

    print(
        "None."
    )


else:

    print(
        follow_up[
            [
                "security_key",
                "market_inception_date",
                "regular_way_start_date",
                "provider_first_date",
                "post_inception_missing_sessions",
                "provider_pre_inception",
                "provider_pre_inception_days",
                "date_basis",
                "validation_status",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ============================================================
# FINAL RESULT
# ============================================================

print_section(
    "INCEPTION REFERENCE RESULT"
)


if len(reference_to_save) != 17:

    print(
        "FAILED:"
    )

    print(
        "The inception reference does "
        "not contain exactly 17 records."
    )

    sys.exit(1)


if (
    set(
        reference_to_save[
            "security_key"
        ]
    )
    != EXPECTED_SECURITIES
):

    print(
        "FAILED:"
    )

    print(
        "The inception security population "
        "is incorrect."
    )

    sys.exit(1)


print(
    "SECURITY MARKET INCEPTION "
    "REFERENCE BUILT SUCCESSFULLY."
)

print(
    "\n17 legitimate independent-security "
    "start boundaries are now documented."
)

print(
    "\nPre-inception requested price history "
    "can now be excluded from missing-data "
    "coverage expectations without inventing "
    "parent-company price history."
)

print(
    "\nAny post-inception provider gaps remain "
    "explicit review items."
)