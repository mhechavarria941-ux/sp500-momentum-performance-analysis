# S&P 500 Momentum & Performance Analytics — Project Log

## Purpose

This document is the continuously maintained technical record for the **S&P 500 Momentum & Performance Analytics** project.

It records the complete workflow, including data sources, development environment, ingestion, auditing, transformations, database design, analytical decisions, validation results, generated files, and major Git commits.

The purpose is to make the project reproducible 

---

# Project Index

## Phase 0 — Development Environment

* Configure VS Code
* Configure Python virtual environment
* Configure project dependencies
* Configure Git
* Connect local repository to GitHub
* Establish `.gitignore`
* Establish `requirements.txt`

## Phase 1 — Data Platform

* Create Azure SQL database
* Create database schemas
* Connect Python to Azure SQL
* Verify database connectivity

## Phase 2 — S&P 500 Membership Construction

* Obtain current constituent reference
* Audit source workbook
* Remove non-index/fund-specific positions
* Establish constituent anchor
* Obtain historical additions and removals
* Reconstruct historical membership
* Validate point-in-time constituent counts

## Phase 3 — Historical Market Data

* Determine historical security universe
* Download 2021–2025 market data
* Preserve raw market data
* Validate trading histories
* Resolve ticker changes and corporate actions
* Load raw data into Azure

## Phase 4 — Data Cleaning and Normalization

* Populate staging layer
* Standardize securities
* Normalize companies
* Normalize sectors and industries
* Normalize index membership
* Normalize daily market prices
* Validate relationships and constraints

## Phase 5 — Feature Engineering

* Daily returns
* Monthly returns
* Annual returns
* Cumulative returns
* 1-month momentum
* 3-month momentum
* 6-month momentum
* 12-month momentum
* Moving averages
* Volatility
* Maximum drawdown
* Beta
* Sharpe ratio
* Forward returns

## Phase 6 — Exploratory Analysis

* S&P 500 benchmark performance
* Company-level performance
* Sector performance
* Momentum distributions
* Risk-return relationships
* Drawdowns
* Market leadership

## Phase 7 — Momentum Research

* Momentum rankings
* Momentum deciles
* Momentum persistence
* Forward-return testing
* Sector-relative momentum
* Risk-adjusted momentum

## Phase 8 — SQL Analytics

* Analytical views
* Ranking queries
* Sector queries
* Momentum queries
* Risk queries
* Performance queries

## Phase 9 — Power BI

* Azure SQL connection
* Semantic model
* Market overview
* Sector performance
* Momentum explorer
* Risk-return analysis

## Phase 10 — Publication

* Final analytical notebook
* Kaggle publication
* GitHub documentation
* Data-source documentation
* Reproducibility testing
* Final project release

---

# Chronological Development Log

## 2026-08 — Project Reconstruction

### 0.1 Legacy Project Review

An older S&P 500 momentum project was identified containing:

* `momentum_trends.csv`
* `dynamic_financial_analytical_model.ipynb`

The cleaned dataset was approximately 466 MB.

### Decision

The legacy dataset and notebook will **not** be used as authoritative inputs for the rebuilt project.

They were moved outside the active repository into:

`sp500_legacy/`

The old project's findings may later be used only to formulate hypotheses that must be independently reproduced and validated using the new pipeline.

---

## 0.2 Project Repository

Repository:

`sp500-momentum-performance-analysis`

Primary development workflow:

`VS Code → Python → Git → GitHub`

GitHub username:

`mhechavarria941-ux`

The repository was initialized and connected to GitHub.

An MIT license was selected for original project code.

---

## 0.3 Python Environment

An isolated Python virtual environment named:

`MYVENV`

was created outside the project directory.

VS Code was configured to use:

`MYVENV\Scripts\python.exe`

Project dependencies are recorded in:

`requirements.txt`

Sensitive environment variables are excluded from Git using:

`.gitignore`

---

# Phase 1 — Azure Data Platform

## 1.1 Azure SQL Database

Database created:

`sp500_analytics`

An existing Azure SQL logical server was reused.

Four database schemas were created:

`raw`

Source data with minimal transformation.

`staging`

Temporary cleaning, standardization, and transformation layer.

`core`

Normalized relational data model.

`analytics`

Derived metrics, analytical tables, and views.

---

## 1.2 Python-to-Azure Connection

A local environment file was created:

`.env`

It contains Azure SQL connection information and is excluded from Git.

Connection test script:

`src/ingestion/test_azure_connection.py`

Python successfully connected to:

`sp500_analytics`

using the project's `MYVENV` environment.

---

# Phase 2 — S&P 500 Membership Construction

## 2.1 Source Strategy

The project will not use the current Wikipedia constituent table as its primary membership source.

Current constituent information is anchored using the holdings of the:

**State Street SPDR S&P 500 ETF Trust (SPY)**

Historical S&P 500 additions and removals will subsequently be reconstructed using documented index-change information.

The final objective is a **point-in-time S&P 500 membership dataset**, rather than applying today's constituents retroactively to previous years.

This is intended to reduce survivorship bias.

---

## 2.2 Raw SPY Holdings Source

Raw source workbook:

`data/raw/source/constituents/holdings-daily-us-en-spy.xlsx`

Source:

State Street SPDR S&P 500 ETF Trust

Holdings date:

`2026-08-10`

The original workbook is preserved unchanged.

---

## 2.3 Workbook Inspection

Inspection script created:

`src/ingestion/inspect_spy_holdings.py`

Workbook sheet:

`holdings`

Workbook structure identified:

Rows 0–2 contain fund metadata.

Row 4 contains the actual table headings.

Holding records begin after row 4.

Relevant source columns:

`Name`

`Ticker`

`Identifier`

`SEDOL`

`Weight`

`Sector`

`Shares Held`

`Local Currency`

---

## 2.4 Initial Dataset Audit

Membership construction script:

`src/ingestion/build_sp500_membership.py`

Raw parsed dataset:

`593 rows × 8 columns`

Rows containing ticker values:

`505`

Rows without ticker values:

`88`

All 505 candidate holding rows use:

`USD`

Duplicate tickers:

`0`

Rows with missing/non-numeric portfolio weight:

`0`

---

## 2.5 Fund-Specific Position Audit

Two non-standard ticker positions were identified.

### US Dollar Position

Name:

`US DOLLAR`

Ticker:

`-`

This represents a fund cash position and is not an S&P 500 security.

### Hologic Corporate-Action Position

Name:

`CONTRA HOLOGIC INCORPO`

Ticker:

`2602335D`

This represents a residual corporate-action position rather than a normal listed S&P 500 equity security.

Both positions are excluded from the constituent anchor.

Dollar General (`DG`) and Dollar Tree (`DLTR`) were also identified by the keyword audit because their company names contain "Dollar", but both are valid equities and remain in the universe.

---

## 2.6 Constituent Filtering Rule

Rather than manually excluding individual suspicious records, candidate securities are filtered using a valid listed-equity ticker pattern.

Accepted examples include:

`AAPL`

`NVDA`

`GOOG`

`GOOGL`

`BRK.B`

`BF.B`

Fund-specific/non-standard identifiers such as:

`-`

and:

`2602335D`

are rejected by this rule.

---

## 2.7 Current Constituent Anchor

After filtering:

**503 constituent securities**

remain.

This represents the project's current constituent anchor as of:

`2026-08-10`

Generated interim file:

`data/interim/sp500_constituent_anchor_2026-08-10.csv`

This file is derived from the untouched State Street source workbook and can therefore be reproduced by the ingestion pipeline.

---

## 2.8 Derived Data and Version-Control Policy

### Decision

Generated intermediate datasets will not be committed to GitHub when they can be fully reproduced from documented source data and committed project code.

The directory:

`data/interim/`

will therefore remain excluded from Git version control through `.gitignore`.

For example, the generated constituent anchor:

`data/interim/sp500_constituent_anchor_2026-08-10.csv`

is not stored in GitHub because it can be recreated by running:

`src/ingestion/build_sp500_membership.py`

against the preserved State Street SPY source workbook.

### Rationale

This approach keeps the repository focused on reproducibility rather than storing unnecessary generated copies of data. GitHub will primarily preserve the code, documentation, configuration, SQL, analytical logic, and appropriate source-reference files required to reconstruct the project's outputs.

Large datasets, temporary transformation outputs, and reproducible intermediate datasets will remain outside Git unless there is a specific analytical or documentation reason to version them.

### Reproducibility Requirement

Any dataset excluded from Git must have:

* A documented original source.
* A documented acquisition or generation method.
* Committed code capable of reproducing it.
* Relevant transformation and filtering decisions recorded in this project log.
* Validation checks sufficient to confirm that the reproduced dataset matches the expected result.

For the current constituent anchor, the expected validation result is:

**503 S&P 500 constituent securities as of 2026-08-10.**

## 2.9 Historical S&P 500 Constituent Change Reference

### Objective

Construct a documented historical record of S&P 500 constituent additions and deletions covering the entire period necessary to reconstruct point-in-time membership for the project's 2021–2025 analytical window.

Because the constituent anchor is dated:

`2026-08-10`

the historical change record extends beyond the primary analysis period and includes all identified membership changes from January 2021 through the anchor date in August 2026.

The reconstruction process will therefore be able to begin with the verified 2026 anchor and roll membership backward through every recorded index action.

### Reference Dataset

Historical constituent actions are stored in:

`data/reference/membership/sp500_official_changes.csv`

Unlike generated files under `data/interim/`, this reference dataset is maintained in Git because it contains manually curated source records and source provenance required to reproduce the historical membership model.

### Source Strategy

The primary source for constituent changes is:

**S&P Dow Jones Indices / S&P Global official index announcements and press releases.**

Each reference record preserves its associated S&P Global source URL.

A secondary historical change source was used selectively as a completeness check when reviewing yearly sequences, but the reference table is based primarily on documented S&P Global index actions.

### Data Model

Each membership action is stored as an independent row rather than storing an addition and deletion together in a single record.

Fields include:

`announcement_date`

`effective_date`

`index_name`

`action`

`company_name`

`ticker`

`gics_sector`

`source_type`

`source_url`

`notes`

This action-level structure was selected because additions and deletions do not always occur on the same effective date.

Examples identified during source construction include spin-offs and corporate actions in which a new security entered the index on one trading date and the corresponding deletion occurred on a later trading date.

### Historical Coverage

Membership-change records were collected for:

`2021`

`2022`

`2023`

`2024`

`2025`

and:

`2026 through 2026-08-10`

Events announced before January 1, 2021 were included when their **effective date** occurred within the reconstruction period.

For example, the Enphase Energy / Tiffany & Co. change was announced in December 2020 but became effective in January 2021 and is therefore included.

### Important Security-Level Events

The historical audit identified several cases demonstrating why the project must model securities rather than assume a simple 500-company replacement structure.

Examples include:

* Multiple share classes.
* Share-class consolidation.
* Corporate spin-offs.
* Temporary S&P 500 membership.
* Additions and deletions occurring on different effective dates.
* Securities entering the index briefly before subsequently moving to another S&P index.
* Corporate acquisitions causing immediate or off-cycle deletions.

Examples observed during the historical review include Warner Bros. Discovery, Under Armour share classes, MasterBrand, Fortrea, PHINIA, Solventum, GE Vernova, Amentum, and other spin-off-related securities.

### Validation

Validation script:

`src/ingestion/validate_membership_changes.py`

The validator checks:

* Required column structure.
* Missing required values.
* Date formatting.
* Announcement/effective-date ordering.
* Index-name consistency.
* Valid action values.
* Ticker formatting.
* Duplicate membership actions.
* Approved S&P Global source domains.
* GICS sector terminology.
* Addition and deletion counts.
* Effective-date distributions.
* Chronological ordering.

Final historical reference validation:

`202 total membership actions`

`100 additions`

`102 deletions`

`Net security-count change: -2`

`Critical validation errors: 0`

`VALIDATION PASSED`

The difference between additions and deletions is not treated as a data-quality error because the S&P 500 constituent-security count can change as a result of multiple share classes, security consolidation, spin-offs, and related index-maintenance events.

### Known Data Standardization Issue

At least one official source uses:

`Information Technologies`

rather than the canonical GICS sector name:

`Information Technology`

The reference dataset currently preserves the source wording rather than silently modifying it.

Sector terminology will be standardized later in the staging layer while preserving the original source value for provenance.

### Result

The project now contains:

1. A verified **503-security S&P 500 constituent anchor as of 2026-08-10**.
2. A documented historical membership-action dataset extending backward through January 2021.
3. Source provenance for individual historical membership actions.
4. Automated structural and logical validation of the historical reference dataset.

Together, these components provide the inputs required to reconstruct point-in-time S&P 500 membership throughout the 2021–2025 analysis period.

### Next Step

Perform a full-history integrity audit and then construct the Python membership-reconstruction engine.

The reconstruction engine will begin with the 2026-08-10 constituent anchor and reverse historical membership actions according to their effective dates to generate membership states and security membership intervals for the 2021–2025 analytical period.

## 2.10 Full-History Membership Integrity Audit

### Objective

Validate that the historical S&P 500 membership-action ledger can be reconciled with the verified 2026-08-10 constituent anchor before generating point-in-time membership intervals.

Structural validation alone is not sufficient because ticker changes, corporate identity changes, missing membership events, or inconsistent security identifiers can produce logically incorrect historical membership even when the source CSV is correctly formatted.

### Audit Script

Integrity audit:

`src/ingestion/audit_membership_history.py`

The audit begins with the verified:

`2026-08-10`

constituent anchor containing:

`503 securities`

and processes the historical membership actions in reverse chronological order.

### Security Identity Reference

During the initial integrity audit, two ticker-continuity issues were identified.

#### Ceridian / Dayforce

Historical ticker:

`CDAY`

Current ticker:

`DAY`

Ceridian HCM changed its corporate identity and ticker to Dayforce while remaining an S&P 500 constituent.

#### EchoStar

Historical ticker:

`SATS`

Current ticker:

`ECHO`

EchoStar changed its ticker while remaining the same constituent security.

These events are not S&P 500 additions or deletions and therefore are maintained separately in:

`data/reference/securities/security_aliases.csv`

This separation preserves the distinction between:

- index membership events;
- security identity/ticker events;
- future market-price observations.

### Reverse-Reconstruction Logic

The integrity audit processes three event types on a shared chronological timeline:

1. Reverse historical additions by removing the added security.
2. Reverse historical deletions by restoring the deleted security.
3. Reverse ticker aliases by replacing the newer ticker with its historical ticker.

Ticker changes do not alter the number of constituent securities.

### Validation Result

Verified anchor:

`503 securities as of 2026-08-10`

Historical membership actions:

`202`

Historical additions:

`100`

Historical deletions:

`102`

Expected constituent-security count at:

`2021-01-01 = 505`

Reverse reconstruction result:

`505 securities`

Security-identity conflicts:

`0`

Final result:

`FULL-HISTORY INTEGRITY AUDIT PASSED`

### Checkpoint Counts

The action ledger implies the following constituent-security counts:

`2021-01-01: 505`

`2021-12-31: 505`

`2022-12-31: 503`

`2023-12-31: 503`

`2024-12-31: 503`

`2025-12-31: 503`

`2026-08-10: 503`

The difference between 500 companies and the number of constituent securities is retained rather than artificially forcing the historical universe to exactly 500 rows.

### Generated Audit Outputs

The audit generates reproducible interim outputs:

`data/interim/membership_count_checkpoints.csv`

and, only when problems are detected:

`data/interim/membership_integrity_issues.csv`

These outputs remain excluded from Git because they can be regenerated from committed reference data and project code.

### Result

The verified anchor, historical membership-action ledger, and security-alias reference are now logically compatible.

The project can therefore proceed to generate point-in-time S&P 500 membership intervals for the 2021–2025 analytical period.

### Next Step

Build the historical membership reconstruction pipeline and generate security-level membership intervals containing each constituent's valid-from and valid-to dates.

# Current Status

Completed:

`Development environment → GitHub → Azure SQL → Python/Azure connection → raw SPY acquisition → workbook audit → constituent filtering → 503-security anchor → historical S&P 500 change-source construction → historical change validation`

Historical membership reference:

`202 membership actions`

`100 additions`

`102 deletions`

Coverage:

`2021-01 through 2026-08-10`

Critical validation errors:

`0`
## 2.11 Point-in-Time Membership Interval Construction

### Objective

Generate the final security-level S&P 500 membership universe for the analytical period:

`2021-01-01 through 2025-12-31`

using the verified 2026 constituent anchor, historical S&P membership actions, and documented security ticker aliases.

### Reconstruction Script

Point-in-time membership construction is performed by:

`src/ingestion/build_membership_intervals.py`

The script first reconstructs the S&P 500 membership state at:

`2021-01-01`

by reversing all membership and ticker-identity events from the 2026-08-10 anchor.

It then processes events forward through December 31, 2025 to create security-level membership intervals.

### Interval Convention

Membership intervals use:

`valid_from`

as an inclusive boundary and:

`valid_to_exclusive`

as an exclusive boundary.

For example, if a security is removed effective July 9, 2025, its membership interval ends at:

`valid_to_exclusive = 2025-07-09`

meaning the security is no longer considered an index member on that date.

Open memberships at the end of the analytical period are clipped to:

`2026-01-01`

which represents the exclusive boundary immediately following December 31, 2025.

### Censoring Flags

Securities already present at the start of the analytical window are marked:

`left_censored = True`

because their actual index-entry date occurred before January 1, 2021.

Securities still present after December 31, 2025 are marked:

`right_censored = True`

because their actual index-exit date occurs outside the analytical window.

### Security Identity and Ticker History

Index membership and ticker identity are stored separately.

This allows a constituent to remain continuously in the S&P 500 even when its ticker changes.

Example:

`CDAY → DAY`

The security remains one constituent identity while its ticker history contains two separate ticker-validity intervals.

### Generated Outputs

Membership intervals:

`data/interim/sp500_membership_intervals_2021_2025.csv`

Ticker history:

`data/interim/sp500_ticker_history_2021_2025.csv`

Both outputs remain excluded from Git because they are reproducible from committed reference data and committed Python code.

### Point-in-Time Validation

The reconstructed membership table successfully reproduced every expected checkpoint:

`2021-01-01: 505 securities`

`2021-12-31: 505 securities`

`2022-12-31: 503 securities`

`2023-12-31: 503 securities`

`2024-12-31: 503 securities`

`2025-12-31: 503 securities`

All checkpoint validations passed.

### Final Universe Summary

Membership interval rows:

`593`

Unique security identities:

`593`

Ticker-history rows:

`594`

Unique historical tickers:

`594`

Securities active at the analysis start:

`505`

Securities active at the analysis end:

`503`

Final result:

`POINT-IN-TIME MEMBERSHIP CONSTRUCTION PASSED`

### Result

The project now has a survivorship-bias-aware, security-level S&P 500 universe covering the complete 2021–2025 analytical period.

Historical membership, security identity, and ticker history are represented independently and can now be used to determine which securities should contribute to market analysis on any given date.

## 3.1 Historical Market Data Source Strategy

### Objective

Acquire reproducible daily historical market prices for every security appearing in the point-in-time S&P 500 universe while preserving historical securities that are no longer actively traded.

The acquisition period includes the 2021-2025 analytical window plus sufficient pre-membership price history to support trailing momentum calculations.

### Price Download Manifest

The acquisition plan is generated by:

`src/ingestion/build_price_download_manifest.py`

Generated manifest:

`data/interim/price_download_manifest.csv`

The manifest contains:

- 594 historical equity ticker segments
- 2 benchmark series
- 596 total price requests
- 595 unique security keys
- 596 unique project tickers
- 596 unique provider ticker requests

The two benchmark series are:

- `^GSPC`
- `SPY`

Historical price lookback is generally extended approximately 400 calendar days before the beginning of a ticker's analytical interval to support trailing 12-month momentum calculations.

Price history and S&P 500 membership remain conceptually separate. Pre-membership prices may be used for feature construction but do not imply earlier index membership.

### Yahoo Finance Symbol Mapping

Yahoo Finance is the primary historical price source.

Ticker-format transformations identified:

- `BF.B -> BF-B`
- `BRK.B -> BRK-B`

The acquisition process explicitly requests unadjusted OHLC prices while retaining adjusted prices and corporate actions where available.

---

## 3.2 Yahoo Finance Availability Audit

Yahoo Finance availability was tested before performing the full historical acquisition.

Audit script:

`src/ingestion/audit_price_availability.py`

Generated audit:

`data/interim/price_availability_audit.csv`

Initial result:

- Total requests tested: 596
- Yahoo Finance available: 553
- Yahoo Finance failures: 43

All 553 successful Yahoo requests returned the expected daily price structure.

The 43 failures primarily represented historical, acquired, renamed, delisted, or otherwise inactive securities.

Yahoo Finance failures were not interpreted as membership failures. Historical S&P 500 membership remained authoritative from the separately constructed membership dataset.

---

## 3.3 Historical Security Price Fallback Strategy

### Objective

Resolve the 43 Yahoo Finance failures without dropping historical S&P 500 constituents and introducing survivorship bias.

A paid-only historical-data dependency was avoided where possible so that the project remains reasonably reproducible.

### Tiingo

Tiingo was selected as the primary fallback source because its free API provides historical end-of-day equity data including:

- Open
- High
- Low
- Close
- Volume
- Adjusted Open
- Adjusted High
- Adjusted Low
- Adjusted Close
- Adjusted Volume
- Dividend cash payments
- Split factors

The Tiingo API token is stored only in `.env` and is never committed to Git.

### Initial ATVI Validation

Activision Blizzard (`ATVI`) was used as the initial fallback proof of concept.

Tiingo returned:

- 953 daily observations
- First observation: 2020-01-02
- Last observation: 2023-10-13
- Complete expected schema
- Zero required price-field nulls
- Zero duplicate dates

Result:

`TIINGO FALLBACK VALIDATION PASSED`

This established Tiingo as a viable source for historical securities unavailable from Yahoo Finance.

---

## 3.4 Tiingo Fallback Availability Audit

Batch fallback testing was performed using:

`src/ingestion/audit_tiingo_fallbacks.py`

Generated audit:

`data/interim/tiingo_fallback_audit.csv`

Results for the 43 Yahoo failures:

- 37 direct Tiingo symbols validated
- 4 direct symbols returned no data
- 2 direct symbols returned HTTP failures
- 6 symbols required additional investigation

The six unresolved ticker segments were:

- `CDAY`
- `FBHS`
- `FRC`
- `GPS`
- `HFC`
- `INFO`

All other Yahoo failures had complete Tiingo fallback coverage.

---

## 3.5 Historical Provider-Symbol Resolution

Some historical securities were available through Tiingo under successor or alternate provider symbols.

Candidate-symbol testing was performed using:

`src/ingestion/test_tiingo_symbol_candidates.py`

Generated audit:

`data/interim/tiingo_symbol_candidate_audit.csv`

Validated mappings:

- `CDAY -> DAY`
- `FBHS -> FBIN`
- `GPS -> GAP`
- `HFC -> DINO`
- `FRC -> FRCB`

For each mapping, the candidate provider symbol was required to return the complete original ticker's requested historical interval rather than merely exist as a currently recognized symbol.

All five mappings returned:

`CANDIDATE_FULL_COVERAGE`

The candidate series also passed schema, null-value, duplicate-date, and date-range checks.

After these mappings:

- Yahoo Finance primary requests: 553
- Tiingo fallback requests: 42
- Remaining unresolved requests: 1

The only remaining unresolved ticker was historical IHS Markit:

`INFO`

---

## 3.6 Historical INFO / IHS Markit Resolution

The ticker `INFO` required special handling because the symbol has subsequently been reused by another financial instrument.

Several automated fallback approaches were tested and rejected.

### Tiingo Direct Symbol

`INFO`

Result:

`NO_DATA`

### Tiingo Predecessor Candidate

`MRKT`

Result:

`NO_DATA`

### Tiingo Search / Permanent Identifier

Searches for:

- `INFO`
- `IHS Markit`
- `Markit`

did not identify the historical IHS Markit security.

### Financial Modeling Prep

FMP returned a currently active ETF using ticker `INFO`, not historical IHS Markit.

The result was rejected because the security identity was incorrect.

### Twelve Data

Twelve Data also returned an ETF-associated `INFO` series.

Metadata identified:

- Type: ETF
- Exchange/MIC inconsistent with historical IHS Markit

The returned data also contained duplicate dates and failed the historical IHS Markit final-price identity check.

The result was rejected.

### Investing.com Archived Security

Historical IHS Markit data was manually exported from the archived Investing.com instrument:

`INFO_OLD`

Raw source file:

`data/raw/source/prices/info_old_investing_2020_2022.csv`

The original file is preserved unchanged and excluded from Git.

Validation script:

`src/ingestion/validate_info_investing.py`

Validation results:

- Rows: 543
- First observation: 2020-01-02
- Last observation: 2022-02-25
- Duplicate dates: 0
- Missing OHLC values: 0
- Missing volume values: 0
- Invalid OHLC relationships: 0
- Expected final close: 108.61
- Returned final close: 108.61

Result:

`INFO INVESTING.COM RAW PRICE VALIDATION PASSED`

The archived series therefore matches the expected historical IHS Markit security.

Adjusted-price reconstruction for INFO remains a future transformation because the Investing.com source provides unadjusted OHLCV rather than the same adjusted-price structure available from Yahoo Finance and Tiingo.

---

## 3.7 Price Source Resolution Reference

The authoritative acquisition-routing table is:

`data/reference/market_data/price_source_resolutions.csv`

It is generated using:

`src/ingestion/build_price_source_resolutions.py`

Final resolution:

- Yahoo Finance primary source: 553 requests
- Tiingo validated fallback: 42 requests
- Investing.com validated fallback: 1 request
- Total resolved requests: 596
- Unresolved requests: 0

Result:

`ALL PRICE SOURCES RESOLVED`

The reference table is committed to Git because it contains acquisition metadata and provenance rather than downloaded market-price observations.

---

## 3.8 Historical Market Price Acquisition

Full historical acquisition is performed using:

`src/ingestion/download_market_prices.py`

The downloader reads the price manifest and validated source-resolution table and automatically routes each request to its approved provider.

### Yahoo Finance

Raw files are stored locally under:

`data/raw/source/prices/yahoo/`

### Tiingo

Raw files are stored locally under:

`data/raw/source/prices/tiingo/`

### Investing.com

The validated IHS Markit source remains:

`data/raw/source/prices/info_old_investing_2020_2022.csv`

### Restartability

Each acquisition is written independently.

Download status is maintained in:

`data/interim/market_price_download_audit.csv`

Existing valid files are reused when the downloader is restarted.

This design prevents completed downloads from being lost if a provider temporarily fails or an API quota is reached.

### Final Acquisition Result

Full acquisition completed successfully:

- Total requests: 596
- Yahoo Finance: 553
- Tiingo: 42
- Investing.com: 1
- Newly downloaded programmatically: 595
- Manual validated source files: 1
- Failures: 0
- Incomplete requests: 0

Final result:

`ALL 596 HISTORICAL PRICE REQUESTS ARE PRESENT`

and:

`MARKET PRICE ACQUISITION PASSED`

Raw market-price datasets are intentionally excluded from Git.

The repository preserves:

- acquisition code
- source-resolution metadata
- historical membership methodology
- ticker-resolution logic
- validation code
- reproducibility documentation

without redistributing provider market-price datasets.

## 3.9 Raw Market-Price Integrity Audit

### Objective

Validate every acquired historical price file before standardization, return calculation, momentum feature engineering, or database loading.

The audit intentionally treated successful acquisition and analytical readiness as separate concepts.

Audit script:

`src/ingestion/audit_market_price_integrity.py`

Generated outputs:

- `data/interim/market_price_integrity_audit.csv`
- `data/interim/market_price_integrity_issues.csv`
- `data/interim/market_price_calendar_gaps.csv`

The audit evaluated:

- provider schema integrity
- row-count reconciliation
- first/last-date consistency
- duplicate dates
- invalid dates
- required OHLCV nulls
- adjusted-close availability
- nonpositive prices
- negative volume
- impossible OHLC relationships
- corporate-action fields
- requested-range violations
- U.S. trading-calendar continuity using SPY
- beginning-of-history coverage
- internal trading-session coverage
- end-of-history coverage

Initial result:

- Total requests audited: 596
- Critical integrity PASS: 595
- Critical integrity FAIL: 1
- Blocking coverage review: 18
- Non-blocking review: 2
- Completely clean: 575

The critical failure was:

`UA — INVALID_LOW`

The blocking coverage cases were primarily newly created securities whose requested momentum lookback extended into periods before the independent security existed.

One major exception was:

`DISCA`

Tiingo direct coverage contained only three observations:

- 2022-04-06
- 2022-04-07
- 2022-04-08

This left 570 requested SPY sessions before the first returned observation and was correctly classified as a genuine provider-history problem rather than an inception exception.

Non-blocking review items were:

- `INFO` — adjusted-price reconstruction pending
- `FISV` — one internal missing trading session on 2025-11-12

The audit therefore successfully prevented structurally present but analytically incomplete data from entering the standardized analytical layer.

---

## 3.10 Market-Price Exception Investigation

### UA Invalid Low

Diagnostic script:

`src/ingestion/diagnose_market_integrity_exceptions.py`

Yahoo Finance contained the following UA observation on 2021-05-05:

- Open: approximately 20.87
- High: approximately 21.825
- Low: 21.00
- Close: approximately 21.13

Because the reported Low exceeded the Open by approximately $0.13, the observation violated the OHLC relationship:

`Low <= min(Open, High, Close)`

The difference was approximately 62.29 basis points and was therefore too large to classify as floating-point noise.

No dividend or split occurred around the affected observation.

Independent Tiingo verification returned:

- Open: 20.87
- High: 21.825
- Low: 20.57
- Close: 21.13
- Volume: 9,649,700

The independently verified Tiingo observation preserved Yahoo's Open, High, and Close while providing a logically valid Low of 20.57.

Resolution:

- Preserve the original Yahoo raw file unchanged.
- During standardization, override only the defective Yahoo `Low` field for 2021-05-05 using the independently verified Tiingo value.
- Do not replace Yahoo volume or the entire Yahoo row because provider volume differed materially.

Resolution type:

`FIELD_OVERRIDE`

---

## 3.11 FISV Internal Trading-Session Resolution

The original integrity audit identified one missing internal U.S. trading session for FISV:

`2025-11-12`

Independent Tiingo verification was performed using both provider symbols:

- `FISV`
- `FI`

Both symbols returned the same 2025-11-12 observation:

- Open: 64.20
- High: 64.87
- Low: 63.11
- Close: 64.38
- Adjusted Close: 64.38
- Volume: 6,244,651

This independently confirmed that the missing date was a legitimate trading session omitted from the Yahoo history.

Resolution:

- Preserve the original Yahoo file unchanged.
- Insert the validated Tiingo observation during construction of the analysis-ready series.

Resolution type:

`ROW_INSERT`

The Fiserv ticker history also requires explicit identity documentation because the security transitioned:

`FISV -> FI -> FISV`

Provider symbol continuity must not be treated as a substitute for the project's corporate-security identity model.

---

## 3.12 DISCA Historical Source Resolution

Direct Tiingo metadata for `DISCA` began only on:

`2022-04-06`

This explained why the direct fallback returned only three observations.

A Tiingo permanent-identity search identified historical Discovery Class A continuity under permanent identifier:

`US000000000527`

This permanent identity returned historical observations beginning:

`2020-01-02`

and extending through:

`2022-04-08`

The permanent-identity series was validated against the direct `DISCA` observations in their overlapping period.

A source-preserving historical composite was then constructed:

- permanent-identity Tiingo history for the earlier period
- direct Tiingo `DISCA` observations where available
- direct DISCA observations receive precedence on overlapping dates

Resolution script:

`src/ingestion/resolve_market_price_exceptions.py`

Derived composite:

`data/interim/disca_tiingo_identity_composite.csv`

The composite was required to pass:

- duplicate-date validation
- required-value validation
- OHLC validation
- price positivity
- split-factor validation
- complete requested SPY-session coverage

The original direct Tiingo raw source remained unchanged.

Resolution type:

`SOURCE_COMPOSITE`

---

## 3.13 Price Exception Resolution Reference

Validated exceptional price transformations are documented in:

`data/reference/market_data/price_exception_resolutions.csv`

Current validated price exceptions:

### UA

Resolution:

`FIELD_OVERRIDE`

Action:

Replace only the 2021-05-05 Low during standardization with independently verified Tiingo Low = 20.57.

### FISV

Resolution:

`ROW_INSERT`

Action:

Insert independently verified Tiingo observation for 2025-11-12.

### DISCA

Resolution:

`SOURCE_COMPOSITE`

Action:

Use validated Tiingo historical permanent-identity history plus direct DISCA observations.

All raw provider files remain immutable.

The reference table records methodology and provenance and is version-controlled.

---

## 3.14 Independent-Security Market Inception Model

### Problem

The price manifest intentionally requested approximately 400 calendar days of historical lookback for momentum construction.

For securities created through IPOs or corporate spin-offs, part of the requested lookback can occur before the independent security existed.

Those dates must not be interpreted as missing market data.

Importantly:

- historical parent-company prices are not substituted
- pre-inception prices are not fabricated
- business-operating history is not treated as independent-security trading history

### Reference

Builder:

`src/ingestion/build_security_market_inceptions.py`

Authoritative reference:

`data/reference/securities/security_market_inceptions.csv`

Validation:

`data/interim/security_market_inception_validation.csv`

The reference contains 17 independent-security inception cases:

- AMTM
- CARR
- CEG
- FTRE
- GEHC
- GEV
- KVUE
- MBC
- OGN
- OTIS
- PHIN
- Q
- SNDK
- SOLS
- SOLV
- VLTO
- VNT

Each reference record preserves information such as:

- security identity
- company name
- market inception date
- regular-way trading date
- event type
- parent company
- when-issued versus regular-way market
- date basis
- evidence status
- source type
- primary source
- secondary source
- methodological notes

The effective price-coverage start is defined conceptually as:

`max(requested_lookback_start, independent_security_market_inception)`

This prevents the audit from demanding prices for dates on which the independent security could not yet have traded.

### Validation Result

Reference rows: 17

Evidence status:

- VERIFIED: 16
- CORROBORATED: 1

Thirteen securities aligned directly with their documented independent-market inception.

A total of:

`3,779 SPY trading sessions`

were correctly reclassified from apparent missing-history requirements to legitimate pre-inception periods.

Four cases required additional investigation:

- CARR
- OTIS
- GEHC
- VLTO

---

## 3.15 Market-Inception Boundary Resolution

Boundary verification script:

`src/ingestion/verify_market_inception_boundaries.py`

Authoritative resolution reference:

`data/reference/market_data/market_inception_boundary_resolutions.csv`

### CARR

Official expected when-issued boundary:

`2020-03-18`

Yahoo first observation:

`2020-03-19`

Tiingo first observation:

`2020-03-19`

Because the official announcement used an approximate expected boundary and two independent providers begin on 2020-03-19, the project accepts 2020-03-19 as the first independently observed trading session.

No synthetic 2020-03-18 price is created.

Resolution:

`CROSS_PROVIDER_OBSERVED_BOUNDARY`

### OTIS

Official expected when-issued boundary:

`2020-03-18`

Yahoo first observation:

`2020-03-19`

Tiingo first observation:

`2020-03-19`

Treatment matches CARR.

Resolution:

`CROSS_PROVIDER_OBSERVED_BOUNDARY`

### GEHC

Official independent-market inception:

`2022-12-16`

Yahoo contained one observation dated:

`2022-12-15`

Independent Tiingo verification contained no pre-inception observation.

The Yahoo 2022-12-15 observation is therefore treated as a provider artifact.

Resolution:

`EXCLUDE_PRE_INCEPTION_PROVIDER_ROW`

The raw Yahoo file remains unchanged.

The analysis-ready GEHC series begins on 2022-12-16.

### VLTO

Official when-issued inception:

`2023-09-27`

Regular-way trading start:

`2023-10-02`

Yahoo history began:

`2023-10-04`

Tiingo regular `VLTO` recovered:

- 2023-10-02
- 2023-10-03

A Tiingo asset search identified:

`VLTO-W — Veralto Corp WhenIssued`

The `VLTO-W` historical series recovered all three missing when-issued sessions:

- 2023-09-27
- 2023-09-28
- 2023-09-29

The final VLTO boundary history therefore uses:

- Tiingo `VLTO-W`: 2023-09-27 through 2023-09-29
- Tiingo `VLTO`: 2023-10-02 through 2023-10-03
- Yahoo Finance `VLTO`: beginning 2023-10-04

Derived composite:

`data/interim/vlto_market_boundary_composite.csv`

Validation:

- Composite rows: 568
- Expected sessions from market inception: 568
- Actual sessions: 568
- Missing sessions: 0
- Extra sessions: 0
- Duplicate dates: 0
- Required null values: 0
- Invalid HIGH rows: 0
- Invalid LOW rows: 0
- Nonpositive prices: 0
- Negative volume: 0
- Invalid split factors: 0

Result:

`VLTO COMPLETE MARKET-BOUNDARY COVERAGE PASSED`

Resolution:

`SOURCE_COMPOSITE`

All four previously unresolved inception-boundary cases are now explicitly documented and resolved.

---

## 3.16 Transformation-Aware Analysis-Ready Integrity Audit

### Objective

Re-audit all 596 historical price requests after applying only documented and independently validated transformations.

Audit script:

`src/ingestion/audit_analysis_ready_price_integrity.py`

The audit creates a temporary analysis-ready representation rather than modifying source-native raw data.

Validated transformations applied:

- UA — verified Low override
- FISV — verified missing-row insert
- DISCA — validated historical source composite
- GEHC — documented pre-inception-row exclusion
- VLTO — validated when-issued + regular-way + Yahoo composite
- CARR — validated observed market boundary
- OTIS — validated observed market boundary
- 17 market-inception cases — pre-inception periods removed from coverage expectations

### Result

Total requests audited:

`596`

Status:

- PASS: 586
- FAIL: 10

Source-level result:

- Yahoo Finance: 553 PASS / 0 FAIL
- Tiingo: 33 PASS / 9 FAIL
- Investing.com: 0 PASS / 1 FAIL

All remaining failures were caused exclusively by:

`UNEXPLAINED_MISSING_SESSIONS`

No remaining failures involved:

- duplicate dates
- invalid dates
- invalid HIGH values
- invalid LOW values
- required OHLCV nulls
- extra trading sessions

Global remaining discrepancy:

`18 missing SPY sessions`

The ten affected historical securities were:

- INFO
- ATVI
- CTLT
- CXO
- HES
- JNPR
- MRO
- PXD
- TWTR
- VAR

The pattern suggested that the analysis-ready audit was still requiring prices after certain securities had ceased independent public trading.

This identified the need for a security-market-termination model analogous to the previously implemented security-market-inception model.

---

## 3.17 Terminal Market-Boundary Diagnostic

Diagnostic script:

`src/ingestion/diagnose_analysis_ready_terminal_boundaries.py`

Generated output:

`data/interim/analysis_ready_terminal_boundary_diagnostic.csv`

The diagnostic tested whether each of the 18 unexplained missing sessions occurred:

- before the first observation
- internally within an active trading history
- or strictly after the final observed security price

### Result

All 10 failed securities were classified:

`TERMINAL_ONLY`

Breakdown:

| Security | Last Observed Date | Missing Terminal Sessions |
|---|---:|---:|
| CXO | 2021-01-15 | 2 |
| VAR | 2021-04-16 | 1 |
| INFO | 2022-02-25 | 2 |
| TWTR | 2022-10-28 | 1 |
| ATVI | 2023-10-13 | 2 |
| PXD | 2024-05-03 | 2 |
| MRO | 2024-11-22 | 1 |
| CTLT | 2024-12-18 | 2 |
| JNPR | 2025-07-02 | 3 |
| HES | 2025-07-18 | 2 |

Totals:

- Terminal missing sessions: 18
- Start missing sessions: 0
- Internal/other missing sessions: 0

Result:

`ALL 10 FAILURES ARE PURE TERMINAL-BOUNDARY CASES`

This establishes that the remaining coverage discrepancy is not an internal price-history failure.

The next required methodological layer is an independent-security market-termination reference.

The future expected price interval will therefore be bounded by both independent-security inception and independent-security termination.

Conceptually:

`effective_expected_start = max(requested_start, security_market_inception)`

and:

`effective_expected_end_exclusive = min(requested_end_exclusive, security_market_termination)`

No post-merger, post-delisting, or post-privatization prices will be fabricated.

Index-membership timing and independent-security tradability remain separate concepts.

---

## 3.18 Independent-Security Market-Termination Reference

### Objective

Define the legitimate end of independent public trading for the ten historical securities identified by the terminal-boundary diagnostic.

The termination model is maintained separately from S&P 500 membership because a security can leave the index before it stops trading, or it can remain in the index until a merger, acquisition, privatization, or other corporate event terminates independent trading.

### Builder and Reference

Builder:

`src/ingestion/build_security_market_terminations.py`

Authoritative reference:

`data/reference/securities/security_market_terminations.csv`

The reference contains one record for each diagnosed terminal case and preserves:

- `security_key`
- `project_ticker`
- company name
- corporate-event date
- last valid trading date
- accepted end-exclusive date
- event type
- acquirer
- trading-suspension date
- termination basis
- evidence status
- provider terminal date
- provider terminal action
- source URL
- methodological notes

### End-Exclusive Convention

The accepted market-termination boundary is stored as:

`accepted_effective_end_exclusive`

A price observation is eligible only when:

`date < accepted_effective_end_exclusive`

The expected analytical interval is therefore bounded by:

`effective_expected_end_exclusive = min(requested_end_exclusive, accepted_effective_end_exclusive)`

### Validated Terminal Cases

| Security | Last Valid Trading Date | Accepted End Exclusive | Provider Terminal Action |
|---|---:|---:|---|
| CXO | 2021-01-15 | 2021-01-19 | KEEP |
| VAR | 2021-04-15 | 2021-04-16 | EXCLUDE_PROVIDER_ARTIFACT |
| INFO | 2022-02-25 | 2022-02-28 | KEEP |
| TWTR | 2022-10-27 | 2022-10-28 | EXCLUDE_PROVIDER_ARTIFACT |
| ATVI | 2023-10-12 | 2023-10-13 | EXCLUDE_PROVIDER_ARTIFACT |
| PXD | 2024-05-02 | 2024-05-03 | EXCLUDE_PROVIDER_ARTIFACT |
| MRO | 2024-11-21 | 2024-11-22 | EXCLUDE_PROVIDER_ARTIFACT |
| CTLT | 2024-12-17 | 2024-12-18 | EXCLUDE_PROVIDER_ARTIFACT |
| JNPR | 2025-07-01 | 2025-07-02 | EXCLUDE_PROVIDER_ARTIFACT |
| HES | 2025-07-17 | 2025-07-18 | EXCLUDE_PROVIDER_ARTIFACT |

### Provider Terminal-Row Determination

The earlier terminal diagnostic proved that the remaining expected-session gaps occurred after each provider's final returned observation.

It did not, by itself, prove that every provider terminal observation represented a legitimate independent trading session.

Independent corporate-event and trading-suspension evidence established the following treatment:

- 8 provider terminal rows are excluded as provider artifacts.
- 2 provider terminal rows are retained.
- CXO and INFO are the only retained provider tails.
- VAR's provider row dated 2021-04-16 is excluded; its last valid trading date is 2021-04-15.

Raw provider files remain unchanged. Exclusions occur only in the temporary analysis-ready representation.

### Validation Result

Reference rows:

`10`

Evidence statuses:

- `VERIFIED`
- `CORROBORATED`

Provider terminal actions:

- `EXCLUDE_PROVIDER_ARTIFACT: 8`
- `KEEP: 2`

Result:

`SECURITY MARKET-TERMINATION REFERENCE PASSED`

---

## 3.19 INFO Corporate Actions and Adjusted-Price Reconstruction

### Objective

Construct a validated adjusted-close history for historical IHS Markit (`INFO`) without modifying the archived Investing.com OHLCV source file.

### Corporate-Action Reference

Builder:

`src/ingestion/build_info_corporate_actions.py`

Reference:

`data/reference/market_data/info_corporate_actions.csv`

The reference documents nine historical cash dividends with:

- declaration date
- ex-dividend date
- record date
- payment date
- cash amount
- split factor
- published close anchor
- published adjusted-close anchor
- evidence status
- resolution status
- source provenance

### Dividend Validation

Validated dividend events:

`9`

Total cash dividends:

`$1.68 per share`

Split events:

`0`

Every action is classified:

`CASH_DIVIDEND`

with:

`resolution_status = VALIDATED`

and:

`evidence_status = CORROBORATED`

### Reconstruction Method

Reconstruction script:

`src/ingestion/resolve_info_adjusted_prices.py`

For each ex-dividend event, the backward adjustment factor is calculated from the prior trading-session close:

`event_factor = (prior_close - cash_dividend) / prior_close`

The factor is applied only to observations before the corresponding ex-dividend date.

Multiple event factors accumulate backward through time.

The final adjusted close is calculated as:

`adjusted_close = close × cumulative_adjustment_factor`

The terminal adjustment factor equals 1.0, so the final adjusted close equals the final unadjusted close.

### Generated Outputs

Reconstructed series:

`data/interim/info_adjusted_price_reconstruction.csv`

Validation table:

`data/interim/info_adjusted_price_validation.csv`

Both are reproducible interim outputs and remain outside Git.

### Validation Result

Rows reconstructed:

`543`

Coverage:

`2020-01-02 through 2022-02-25`

Dividend events applied:

`9`

Total dividends applied:

`$1.68`

Published adjusted-price anchors:

`9 / 9 PASS`

Additional validation confirmed:

- no duplicate dates
- no missing required OHLCV values
- no missing adjusted closes
- no nonpositive reconstructed prices
- cumulative adjustment factors remain within `(0, 1]`
- adjustment factors do not decrease moving forward
- final adjustment factor equals 1.0
- final adjusted close equals final close
- no stock splits occurred during the reconstruction period

Result:

`INFO ADJUSTED-PRICE RECONSTRUCTION PASSED`

The raw Investing.com file remains unchanged.

---

## 3.20 Final Analysis-Ready Price Integrity Audit

### Objective

Perform the final 596-request integrity audit after applying every documented and validated market-data resolution.

The audit continues to preserve raw provider files and constructs transformations only in the temporary analysis-ready representation.

### Reference Control Gate

The final control gate requires:

- 596 download requests
- 17 security-market-inception records
- 10 security-market-termination records
- 8 excluded provider terminal artifacts
- 2 retained terminal provider rows
- 3 validated price exceptions: UA, FISV, and DISCA
- 4 validated market-boundary resolutions: CARR, OTIS, GEHC, and VLTO
- 9 validated INFO cash dividends totaling $1.68

The audit refuses to continue when any required reference file, expected population, evidence status, resolution status, or date boundary changes unexpectedly.

### Applied Transformations

The final analysis-ready representation includes only documented transformations:

- UA verified Low override
- FISV verified row insertion
- DISCA permanent-identity/direct-symbol composite
- CARR observed inception boundary
- OTIS observed inception boundary
- GEHC pre-inception provider-row exclusion
- VLTO when-issued/regular-way/Yahoo composite
- 17 independent-security inception boundaries
- 10 independent-security termination boundaries
- 8 provider terminal-row exclusions
- INFO dividend-adjusted price reconstruction

### Final Result

Total requests audited:

`596`

Status counts:

- `PASS: 596`
- `REVIEW_KNOWN: 0`
- `FAIL: 0`

Source-level result by original acquisition source:

- Yahoo Finance: 553 PASS
- Tiingo: 42 PASS
- Investing.com: 1 PASS

Global validation totals:

- unexplained missing sessions: 0
- unexplained extra sessions: 0
- duplicate dates: 0
- invalid dates: 0
- required OHLCV nulls: 0
- adjusted-close nulls: 0
- nonpositive prices: 0
- negative volume: 0
- invalid HIGH rows: 0
- invalid LOW rows: 0
- known review items: 0
- critical failures: 0

Final result:

`ANALYSIS-READY PRICE INTEGRITY AUDIT PASSED`

and:

`RAW / ACQUISITION QUALITY GATE COMPLETE`

The market-price layer is now approved for standardized analytical output.

---

## 3.21 Standardized Price-History Layer

### Objective

Export one canonical long-format daily price history from the exact transformation path validated by the final integrity audit.

The export is attached to the successful final audit path so that a failed or incomplete audit cannot overwrite the last valid standardized dataset.

### Canonical Schema

The standardized history contains:

`security_key`

`project_ticker`

`provider_symbol`

`date`

`open`

`high`

`low`

`close`

`adjusted_close`

`volume`

`dividend`

`split_factor`

`source`

### Identity Model

The canonical observation key is:

`security_key + project_ticker + date`

`security_key` preserves corporate-security identity independently from the displayed or provider ticker.

`project_ticker` preserves the historical ticker segment requested by the project.

`provider_symbol` preserves the acquisition symbol used by the approved provider route.

### Generated Outputs

Standardized history:

`data/interim/standardized_price_history.csv.gz`

Request-level manifest:

`data/interim/standardized_price_history_manifest.csv`

Both outputs remain excluded from Git because they are reproducible from committed code, reference controls, and preserved raw inputs.

### Validation Result

Standardized requests:

`596`

Standardized observations:

`783,086`

Canonical-key duplicates:

`0`

Additional validation confirmed:

- exact reconciliation with all 596 audit row counts
- exact reconciliation with audited first and last dates
- canonical column order preserved
- no canonical numeric nulls
- positive price values
- nonnegative volume
- positive split factors
- complete row-level source labels

Result:

`STANDARDIZED_PRICE_HISTORY_PASSED`

---

## 3.22 Membership-to-Price Integration Input Inspection

### Objective

Inspect the existing membership and standardized-price inputs before joining point-in-time S&P 500 membership to daily prices.

The inspection is read-only and does not modify membership references, generated membership intervals, standardized prices, or manifests.

### Inspection Script

`src/ingestion/inspect_membership_join_inputs.py`

### Inspection Report

`reports/data_quality/membership_inspection.txt`

Unlike generated analytical datasets under `data/interim/`, this report is retained as version-controlled data-quality documentation for the membership-integration checkpoint.

### Membership Inputs Identified

Current constituent anchor:

`data/interim/sp500_constituent_anchor_2026-08-10.csv`

Official membership actions:

`data/reference/membership/sp500_official_changes.csv`

Point-in-time membership intervals:

`data/interim/sp500_membership_intervals_2021_2025.csv`

Membership-count checkpoints:

`data/interim/membership_count_checkpoints.csv`

### Inspection Results

Current SPY anchor:

- 503 rows
- 503 unique tickers
- anchor date: 2026-08-10

Official membership-change reference:

- 202 action rows
- 188 unique tickers
- 100 additions
- 102 deletions
- earliest effective date: 2021-01-07
- latest effective date: 2026-08-05

Standardized price manifest:

- 596 request rows
- 596 unique project tickers
- 595 unique security keys
- 595 unique provider symbols

Standardized price history:

- 13 canonical columns
- 783,086 validated observations

### Remaining Membership Validation Requirement

The existing interval and checkpoint files were identified by the inventory but were not yet examined by the initial inspection script.

Before any membership-to-price join, the project must explicitly validate:

- interval column structure
- inclusive `valid_from` semantics
- exclusive `valid_to_exclusive` semantics
- unique security identity mapping
- ticker-history mapping to `security_key`
- absence of overlapping intervals for the same security
- checkpoint constituent counts
- price availability during valid membership intervals
- absence of membership rows outside the 2021–2025 analytical window

No return, momentum, or forward-performance calculation should begin until this membership-integration gate passes.
## 3.23 Membership Interval Integrity Audit

### Objective

Perform the dedicated quality gate required before joining point-in-time S&P 500 membership to standardized daily prices.

The audit validates the membership interval table, ticker-history table, reconstruction checkpoints, security aliases, documented market terminations, and standardized price-request manifest as one internally consistent system.

### Audit Script

`src/ingestion/audit_membership_interval_integrity.py`

### Audit Report

`reports/data_quality/membership_interval_integrity_audit.txt`

The audit report is retained as version-controlled data-quality documentation.

### Validated Inputs

Membership intervals:

`data/interim/sp500_membership_intervals_2021_2025.csv`

Ticker history:

`data/interim/sp500_ticker_history_2021_2025.csv`

Membership checkpoints:

`data/interim/membership_count_checkpoints.csv`

Security aliases:

`data/reference/securities/security_aliases.csv`

Security market terminations:

`data/reference/securities/security_market_terminations.csv`

Standardized price manifest:

`data/interim/standardized_price_history_manifest.csv`

### Interval and Identity Validation

The audit confirmed:

- exact expected schemas and row populations
- no exact duplicate rows
- no required-field nulls
- valid inclusive-start and exclusive-end dates
- positive-duration membership and ticker intervals
- censoring flags consistent with the analysis boundaries
- entry and exit provenance consistent with censoring status
- canonical security-key continuity
- no ticker-history gaps or overlaps
- exact partitioning of every membership interval by ticker history
- `DAY` as the only multi-segment security identity, represented by `CDAY -> DAY`

The documented:

`SATS -> ECHO`

alias became effective on:

`2026-06-24`

This date is outside the 2021–2025 analytical scope. Neither ticker appears in the in-scope ticker-history output, so the alias correctly creates no 2021–2025 ticker segment.

### Checkpoint Validation

All six in-scope point-in-time membership counts were reproduced directly from the interval table:

`2021-01-01: 505 securities`

`2021-12-31: 505 securities`

`2022-12-31: 503 securities`

`2023-12-31: 503 securities`

`2024-12-31: 503 securities`

`2025-12-31: 503 securities`

The:

`2026-08-10: 503 securities`

record remains an anchor/reconstruction control and is not evaluated against interval rows clipped at `2026-01-01`.

### Membership-to-Price Request Reconciliation

Every one of the:

`594 ticker-history segments`

maps to exactly one standardized constituent-price request.

The remaining two of the 596 standardized price requests are the non-constituent benchmark series.

Ten price-request windows end before their associated S&P membership interval because independent public trading terminated before the official index deletion date:

- ATVI
- CTLT
- CXO
- HES
- INFO
- JNPR
- MRO
- PXD
- TWTR
- VAR

All ten early boundaries reconcile exactly to the validated:

`security_market_terminations.csv`

reference. No undocumented early price-window ending remains.

### Methodological Decision

Index membership and independent-security tradability remain separate concepts.

A constituent-price observation is usable only while both conditions are satisfied:

`membership valid_from <= date < membership valid_to_exclusive`

and:

`date < accepted market-termination end-exclusive boundary`, when a documented termination exists.

The project will not fabricate post-termination prices merely because the official membership deletion became effective later.

### Final Result

Passed checks:

`95`

Membership intervals:

`593`

Security identities:

`593`

Ticker-history segments:

`594`

Historical tickers:

`594`

In-scope checkpoints validated:

`6`

Standardized constituent requests mapped:

`594`

Documented market-termination truncations:

`10`

Non-constituent benchmark requests:

`2`

Final result:

`MEMBERSHIP_INTERVAL_INTEGRITY_AUDIT_PASSED`

and:

`POINT-IN-TIME MEMBERSHIP QUALITY GATE COMPLETE`

### Next Step

Construct the point-in-time membership-to-price bridge using canonical security identity, historical ticker validity, membership validity, and documented tradability boundaries.

Return calculation, momentum feature engineering, and forward-performance testing remain blocked until the bridge itself passes its integrity audit.


---

# Current Status

Current phase:

**Point-in-time membership-to-price bridge construction**

Completed:

- Project architecture and reproducibility framework
- Azure SQL analytical database foundation
- Current 503-security S&P 500 constituent anchor
- Historical S&P 500 membership-action reference
- Full-history membership integrity audit
- Point-in-time membership interval construction
- Historical security identity reconciliation
- 596-request price-download manifest
- Yahoo Finance primary-source acquisition
- Tiingo fallback acquisition and validation
- Investing.com historical INFO raw-price validation
- Complete 596-request historical acquisition
- Raw provider-file integrity audit
- UA defective-price resolution
- FISV missing-session resolution
- DISCA historical source reconstruction
- 17 independent-security market-inception references
- CARR and OTIS observed-boundary resolutions
- GEHC pre-inception provider-artifact resolution
- VLTO when-issued and regular-way source composite
- 10 independent-security market-termination references
- 8 provider terminal-artifact exclusions
- INFO nine-dividend corporate-action reference
- INFO 543-row adjusted-price reconstruction
- Final 596-request analysis-ready integrity audit
- Canonical 783,086-row standardized price history
- Initial membership-to-price input inspection
- Dedicated membership interval and ticker-history inspection
- 95-check membership interval integrity audit
- Exact mapping of 594 historical ticker segments to standardized price requests
- Reconciliation of 10 early price boundaries to documented market terminations
- Point-in-time membership quality gate

Current market-data quality state:

- Total requests: 596
- PASS: 596
- Known review items: 0
- Critical failures: 0
- Standardized rows: 783,086
- Canonical-key duplicates: 0
- Unexplained missing sessions: 0
- Unexplained extra sessions: 0
- Invalid OHLC relationships: 0
- Required OHLCV nulls: 0

Current membership state:

- Anchor securities as of 2026-08-10: 503
- Official membership actions: 202
- Point-in-time membership intervals: 593
- Unique security identities: 593
- Ticker-history segments: 594
- Unique historical tickers: 594
- 2021-01-01 checkpoint: 505 securities
- 2025-12-31 checkpoint: 503 securities
- Dedicated integrity checks passed: 95
- Membership/ticker interval gaps or overlaps: 0
- Unexplained identity mappings: 0
- Standardized constituent requests mapped: 594
- Documented market-termination truncations: 10
- Non-constituent benchmark requests: 2
- Membership quality-gate result: PASSED

Next objective:

Construct the point-in-time membership-to-price bridge from:

`data/interim/sp500_membership_intervals_2021_2025.csv`

and:

`data/interim/sp500_ticker_history_2021_2025.csv`

and:

`data/interim/standardized_price_history.csv.gz`

The bridge must retain only constituent observations satisfying both the security membership interval and historical ticker-validity interval.

The two benchmark series must remain outside the constituent bridge and be retained separately for benchmark analysis.

Return calculation, momentum feature engineering, and forward-performance testing remain blocked until the membership-to-price integration gate passes.

Git checkpoint objective:

Commit the membership interval builder, interval inspection script, integrity-audit script, both membership data-quality reports, and this updated project log while continuing to exclude reproducible interim datasets, timestamped backup scripts, and one-time integration helpers.

---

# Logging Standard Going Forward

Every meaningful project step should record:

**Step ID**

A sequential project identifier.

**Date**

When the step was performed.

**Objective**

What the step was intended to accomplish.

**Source**

Where the data or information originated.

**Files Created or Modified**

Exact project paths.

**Method**

Python, SQL, Power BI, manual acquisition, API, etc.

**Transformation**

Exactly what was changed.

**Validation**

Counts, duplicate checks, missing-value checks, reconciliation totals, or other tests.

**Decision**

Why a particular analytical or technical choice was made.

**Output**

Dataset, table, view, notebook, script, or analytical result produced.

**Issues / Limitations**

Anything that could affect interpretation or reproducibility.

**Next Step**

The immediate continuation point.

**Git Commit**

The commit hash or commit message corresponding to the completed milestone.
