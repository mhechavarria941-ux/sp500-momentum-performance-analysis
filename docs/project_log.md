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

* Canonical 12-1 momentum rankings and deciles
* Corrected 2021–2025 forward-return testing
* Statistical, risk-adjusted, and implementation-cost analysis
* H1 canonical 12-1 momentum closeout — not supported
* Point-in-time GICS sector-history construction
* H2 sector-relative 12-1 momentum preregistration
* Within-sector quintile and sector-neutral portfolio testing
* Post-H2 commonality and residual-winner exploration
* H3 external-attention source feasibility and company-identity resolution
* Point-in-time attention-alias construction and GDELT historical extraction
* Fail-closed attention coverage policy and statistical preregistration
* Frozen issuer-level attention predictor
* H3 predictor-to-outcome analytical-panel construction
* H3 primary confirmatory inference freeze
* H4 intraday price-location and market-structure preregistration

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

---
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

## 3.24 Point-in-Time Membership-to-Price Bridge

### Objective

Construct a daily constituent-price dataset that includes a security only while all applicable conditions are valid:

- the security is an S&P 500 constituent
- the historical ticker is valid
- the standardized price request is inside its validated usable period
- independent public trading has not terminated

This bridge prevents current constituents from being applied retroactively and prevents historical ticker changes, market terminations, and momentum-lookback observations from creating invalid constituent rows.

### Builder

`src/ingestion/build_membership_price_bridge.py`

### Source Inputs

Standardized price history:

`data/interim/standardized_price_history.csv.gz`

Standardized price manifest:

`data/interim/standardized_price_history_manifest.csv`

Membership intervals:

`data/interim/sp500_membership_intervals_2021_2025.csv`

Ticker history:

`data/interim/sp500_ticker_history_2021_2025.csv`

### Eligibility Rule

For each security, ticker, and date, the builder requires:

`membership_valid_from <= date < membership_valid_to_exclusive`

and:

`ticker_valid_from <= date < ticker_valid_to_exclusive`

and:

`usable_start <= date < usable_end_exclusive`

The usable interval is calculated as:

`usable_start = max(membership start, ticker start, effective price start)`

and:

`usable_end_exclusive = min(membership end, ticker end, effective price end)`

This combines index membership, historical ticker identity, validated market inception, and validated market termination without treating them as the same concept.

### Constituent and Benchmark Separation

The 594 historical constituent ticker requests are written to the point-in-time bridge.

The two non-constituent benchmark requests are stored separately.

This prevents benchmark observations from entering company-level or constituent-level calculations while preserving them for market comparison, beta, and excess-return analysis.

### Generated Outputs

Point-in-time constituent bridge:

`data/interim/sp500_membership_price_bridge_2021_2025.csv.gz`

Ticker-segment reconciliation manifest:

`data/interim/sp500_membership_price_bridge_manifest.csv`

Benchmark history:

`data/interim/sp500_benchmark_price_history_2021_2025.csv.gz`

These files remain excluded from Git because they are reproducible from committed code, validated reference controls, and preserved source data.

### Build Result

Constituent bridge rows:

`631,942`

Constituent security identities:

`593`

Historical constituent ticker segments:

`594`

Benchmark rows:

`2,510`

Benchmark requests:

`2`

Standardized constituent lookback and out-of-window rows removed:

`148,128`

Result:

`MEMBERSHIP_PRICE_BRIDGE_BUILD_PASSED`

### Independent Integrity Audit

Audit script:

`src/ingestion/audit_membership_price_bridge.py`

Audit report:

`reports/data_quality/membership_price_bridge_integrity_audit.txt`

The audit independently reloads the source datasets and reconstructs the expected bridge rather than relying only on the builder’s internal validation.

The audit validates:

- exact input and output schemas
- expected row populations
- canonical observation-key uniqueness
- security and ticker populations
- reconstruction of all membership, ticker, and effective-price controls
- exact source-to-bridge row reconciliation
- exact numeric reconciliation with standardized price history
- membership interval eligibility
- ticker-validity eligibility
- usable-price interval eligibility
- absence of benchmark observations from the constituent bridge
- exact benchmark separation
- daily constituent population reconciliation
- complete SPY-session coverage for every ticker segment
- absence of missing or extra constituent trading sessions

### SPY Trading-Calendar Validation

SPY trading sessions during 2021–2025:

`1,255`

Every historical ticker segment was compared independently against the eligible SPY sessions inside its usable interval.

Results:

- missing expected constituent sessions: 0
- extra constituent sessions: 0
- membership/ticker/date duplicates: 0

Daily constituent observations ranged from:

`502`

to:

`506`

The project preserves the observed security-level index structure and documented tradability boundaries rather than artificially forcing every day to contain exactly 500 rows.

### Market-Termination Reconciliation

Exactly ten ticker intervals end at a validated effective-price boundary before their S&P membership interval ends:

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

These are the same ten independently validated security-market-termination cases.

No undocumented early price boundary remains.

### Final Audit Result

Passed checks:

`77`

Constituent bridge rows:

`631,942`

Security identities:

`593`

Historical ticker segments:

`594`

SPY trading sessions:

`1,255`

Benchmark rows:

`2,510`

Documented early price boundaries:

`10`

Final result:

`MEMBERSHIP_PRICE_BRIDGE_INTEGRITY_AUDIT_PASSED`

and:

`POINT-IN-TIME MEMBERSHIP-PRICE INTEGRATION QUALITY GATE COMPLETE`

### Result

The project now has a fully validated, survivorship-bias-aware daily constituent-price dataset for the complete 2021–2025 analytical period.

The membership-to-price integration gate is complete.

Return calculation and momentum feature engineering are no longer blocked by membership or market-data integrity.

### Next Step

Design and populate the normalized Azure SQL analytical layer using the validated security identities, ticker history, membership intervals, constituent price bridge, and benchmark history.

## 3.25 Azure SQL Environment Inspection

### Objective

Inspect the target Azure SQL database before creating or loading analytical objects.

The inspection was explicitly read-only and was designed to establish the database configuration, available schemas, existing object inventory, and compatibility with the planned normalized market-data model.

### Inspection Script

`src/ingestion/inspect_azure_sql_environment.py`

### Inspection Report

`reports/data_quality/azure_sql_environment_inspection.txt`

The report excludes all database credentials and records that no database modifications were performed.

### Connection Resolution

The initial connection attempt timed out because the connection configuration required an explicit extended timeout for the Azure SQL endpoint.

The connection was validated after applying:

`timeout=90`

to the `mssql_python.connect()` call.

TCP connectivity to the Azure SQL endpoint on port 1433 was also confirmed.

### Environment Result

Database:

`sp500_analytics`

Compatibility level:

`170`

Collation:

`SQL_Latin1_General_CP1_CI_AS`

Read-committed snapshot isolation:

`ON`

Required schemas present:

- `raw`
- `staging`
- `core`
- `analytics`

User tables present before deployment:

`0`

Database modifications performed:

`0`

Final result:

`AZURE_SQL_ENVIRONMENT_INSPECTION_PASSED`

The database was empty, correctly configured, and free of legacy-table conflicts.

## 3.26 Normalized Azure SQL Market-Data Schema

### Objective

Create the normalized relational structure required to preserve canonical security identity, historical ticker validity, point-in-time S&P 500 membership, validated constituent prices, price-eligibility controls, and separate benchmark history.

### Baseline Migration

`sql/schema/001_create_market_data_model.sql`

### Application Script

`src/ingestion/apply_azure_sql_schema.py`

### Application Report

`reports/data_quality/azure_sql_schema_application.txt`

### Core Data Model

The migration created eight core tables:

- `core.market_index`
- `core.security`
- `core.security_ticker_history`
- `core.index_membership`
- `core.security_price_eligibility`
- `core.daily_security_price`
- `core.benchmark_series`
- `core.daily_benchmark_price`

The `core.market_index` table contains the single analytical anchor:

`SP500 | S&P 500 | S&P Dow Jones Indices | 2021-01-01 | 2025-12-31`

### Staging Model

Seven constraint-free staging tables mirror the load-target columns required for:

- securities
- ticker history
- membership intervals
- price eligibility
- constituent prices
- benchmark definitions
- benchmark prices

The staging layer permits fast bulk loading and independent reconciliation before constrained core promotion.

### Relational Controls

Primary keys:

`8`

Foreign keys:

`8`

Check constraints:

`22`

Required supporting indexes:

`2`

All objects were created inside a transactional, create-if-absent migration.

No membership or price data was loaded during schema deployment.

### Result

Final result:

`AZURE_SQL_MARKET_DATA_SCHEMA_APPLICATION_PASSED`

The normalized Azure SQL structure was ready for controlled loading.

## 3.27 Azure SQL Load-Input Inspection

### Objective

Inspect the exact source schemas, row populations, driver capability, and database target state before defining bulk-copy mappings.

### Inspection Script

`src/ingestion/inspect_azure_sql_load_inputs.py`

### Inspection Report

`reports/data_quality/azure_sql_load_input_inspection.txt`

### Source Inputs

Membership intervals:

`data/interim/sp500_membership_intervals_2021_2025.csv`

Ticker history:

`data/interim/sp500_ticker_history_2021_2025.csv`

Constituent bridge:

`data/interim/sp500_membership_price_bridge_2021_2025.csv.gz`

Bridge manifest:

`data/interim/sp500_membership_price_bridge_manifest.csv`

Benchmark history:

`data/interim/sp500_benchmark_price_history_2021_2025.csv.gz`

### Validated Populations

Membership intervals:

`593`

Ticker-history segments:

`594`

Constituent observations:

`631,942`

Bridge-manifest rows:

`594`

Benchmark observations:

`2,510`

All five source datasets matched their previously validated row anchors and exact expected column structures.

### Driver Capability

Installed `mssql-python` version:

`1.13.0`

`cursor.bulkcopy` availability:

`True`

All seven core load targets and all seven staging tables were empty at the time of inspection.

Database modifications performed:

`0`

Final result:

`AZURE_SQL_LOAD_INPUT_INSPECTION_PASSED`

## 3.28 Decimal-Precision Migration and Controlled Market-Data Load

### Objective

Load the five validated analytical sources into Azure SQL through a controlled staging, reconciliation, and transactional-promotion workflow.

### Loader

`src/ingestion/load_azure_sql_market_data.py`

The loader:

- validates every source header before connecting
- rejects nonempty staging or core targets
- streams large compressed price files in bounded chunks
- bulk-loads only the constraint-free staging layer
- reconciles all staging row counts to documented anchors
- promotes all seven datasets to core in one transaction
- validates manifest, usable-window, membership, and benchmark relationships
- clears staging only after successful core promotion
- clears partial staging rows automatically if bulk loading fails
- never deletes or replaces committed core data

### Initial Decimal-Scale Failure

The first bulk-load attempt stopped while loading constituent prices because a validated source value had eleven decimal places while the original schema allowed ten:

`Input decimal scale 11 exceeds target scale 10`

The loader reported:

`Core promotion committed: False`

and:

`Failure cleanup: Completed; staging tables were cleared.`

No core rows were committed by the failed attempt, and no source data was changed or rounded.

### Precision Decision

The project preserves the validated source precision instead of silently quantizing values to ten decimal places.

All market-value columns were expanded from:

`DECIMAL(28, 10)`

to:

`DECIMAL(38, 18)`

The affected columns are:

- `open`
- `high`
- `low`
- `close`
- `adjusted_close`
- `dividend`
- `split_factor`

across both constituent and benchmark price tables in the core and staging schemas.

### Corrective Migration

Migration:

`sql/schema/002_expand_market_data_decimal_scale.sql`

Migration runner:

`src/ingestion/apply_azure_sql_decimal_scale_migration.py`

Migration report:

`reports/data_quality/azure_sql_decimal_scale_migration.txt`

The baseline migration was also updated so future database creation uses `DECIMAL(38, 18)` directly.

### Migration Validation

Tables migrated:

`4`

Decimal columns verified:

`28`

Price-integrity checks restored and verified:

`8`

Supporting daily-security index restored and verified:

`1`

Data rows modified by the precision migration:

`0`

Final migration result:

`AZURE_SQL_DECIMAL_SCALE_MIGRATION_PASSED`

### Final Core Populations

Security identities:

`593`

Ticker-history segments:

`594`

Membership intervals:

`593`

Price-eligibility manifests:

`594`

Constituent price observations:

`631,942`

Benchmark definitions:

`2`

Benchmark price observations:

`2,510`

Total daily price observations:

`634,452`

After the successful promotion, a later loader invocation was correctly rejected because all seven core load targets were already populated.

The rejected duplicate attempt made no database changes and required no cleanup.

Because that later attempt overwrote the loader's operational text report, the independent post-load integrity audit is retained as the authoritative completion record.

## 3.29 Azure SQL Market-Data Integrity Audit

### Objective

Independently determine whether the existing Azure SQL core population is complete, relationally valid, numerically identical to the validated source outputs, and safe to use for feature engineering.

The audit is read-only and performs no database modifications.

### Audit Script

`src/ingestion/audit_azure_sql_market_data_load.py`

### Audit Report

`reports/data_quality/azure_sql_market_data_integrity_audit.txt`

### Population Validation

All seven core load targets exactly matched their documented source anchors.

All seven staging tables contained zero rows.

### Relational and Precision Validation

The audit confirmed:

- all core foreign keys are enabled and trusted
- all core check constraints are enabled and trusted
- all 28 market-value columns remain `DECIMAL(38, 18)`
- all six point-in-time membership checkpoints reconcile
- `DAY` is the only multi-segment security identity
- all 594 constituent price segments reconcile to their manifests
- no constituent observation falls outside its usable interval
- both benchmark requests contain exactly 1,255 sessions
- benchmark definitions contain exactly one ETF and one index

### Source-to-SQL Numeric Reconciliation

The source files and Azure SQL core tables were independently aggregated for:

- adjusted close
- volume
- dividend
- split factor

Constituent aggregate differences:

`0`

Benchmark aggregate differences:

`0`

### Final Result

Passed checks:

`31`

Core security identities:

`593`

Core ticker-history segments:

`594`

Core membership intervals:

`593`

Core constituent observations:

`631,942`

Core benchmark observations:

`2,510`

Total core daily observations:

`634,452`

Staging rows remaining:

`0`

Final result:

`AZURE_SQL_MARKET_DATA_INTEGRITY_AUDIT_PASSED`

and:

`NORMALIZED AZURE SQL MARKET-DATA QUALITY GATE COMPLETE`

### Result

The normalized Azure SQL market-data layer is complete, source-reconciled, relationally constrained, and ready for analytical feature engineering.

Daily returns, momentum features, risk measures, and forward-performance testing are no longer blocked by source, membership, bridge, or database integrity.

### Next Step

Define the analytical price and return methodology before creating the first feature-engineering tables or views.

The next stage must specify adjusted-price usage, dividend treatment, daily-return convention, monthly observation convention, lookback completeness requirements, and look-ahead protections before momentum variables are calculated.
## 3.30 Analytical Price and Return Methodology

### Objective

Define the analytical conventions required to calculate reproducible daily returns, monthly returns, and momentum signals without introducing look-ahead bias, ticker discontinuities, or inconsistent calendar assumptions.

### Documentation

`docs/analytical_methodology.md`

### Analytical Engine

Azure SQL is the primary feature-engineering and analytical engine.

Python is used for independent integrity auditing, reproducibility controls, and report generation.

Power BI will consume validated analytical outputs during the reporting stage.

### Price Convention

Returns use `adjusted_close`.

The adjusted price series incorporates the economic effects of validated dividends and stock splits.

Raw close is retained for reference but is not used as the canonical total-return input.

### Daily Return Convention

Daily simple return:

`adjusted_close_t / adjusted_close_previous_session - 1`

A daily return is complete only when the previous observation is the immediately preceding SPY trading session.

Missing sessions are not bridged or imputed.

### Monthly Observation Convention

Each analytical month uses the final SPY trading session of the calendar month.

Constituent and benchmark month-end observations must fall on that exact SPY session.

### Monthly Return Features

Trailing returns are calculated over exact:

- 1-month
- 3-month
- 6-month
- 12-month

A feature is complete only when its required calendar-month anchor exists.

### Canonical Momentum Convention

Canonical 12-1 momentum is defined as:

`adjusted_close_month_minus_1 / adjusted_close_month_minus_12 - 1`

The formation window spans months `-12` through `-1`.

The ranking month is skipped.

### Identity Convention

`security_key` is the permanent analytical identity.

Ticker changes do not break return continuity when the underlying security identity remains unchanged.

This convention preserves the validated `CDAY` to `DAY` transition.

### Look-Ahead Controls

Signal views contain no forward-return, lead, or future-performance columns.

Forward returns will be constructed in a separate analytical layer after signals and rankings are finalized.

Point-in-time membership, ticker-validity intervals, and usable-price boundaries remain enforced.

### Decisions Deferred

Risk-free-rate treatment and risk-adjusted performance measures remain deferred until the required external rate source and conventions are documented.

### Result

The analytical methodology is defined and ready for SQL implementation.

### Next Step

Create the SPY trading calendar, exact month-end calendar, daily-return views, and month-end price views in Azure SQL.

---

## 3.31 Azure SQL Return Foundation

### Objective

Create the SQL calendar and return foundation required for monthly feature engineering while preserving the validated normalized core data.

### SQL Migration

`sql/analytics/003_create_return_foundation_views.sql`

### Application Script

`src/analysis/apply_azure_sql_return_foundation.py`

### Application Report

`reports/data_quality/azure_sql_return_foundation_application.txt`

### Objects Created

The migration created or updated six analytical views:

- `analytics.v_spy_trading_calendar`
- `analytics.v_spy_month_end_calendar`
- `analytics.v_security_daily_return`
- `analytics.v_benchmark_daily_return`
- `analytics.v_security_month_end_price`
- `analytics.v_benchmark_month_end_price`

### Calendar Results

SPY trading sessions:

`1,255`

Exact SPY month-end sessions:

`60`

First SPY session:

`2021-01-04`

Last SPY session:

`2025-12-31`

### Return Results

Constituent daily observations:

`631,942`

Benchmark daily observations:

`2,510`

Constituent month-end observations:

`30,211`

Benchmark month-end observations:

`120`

### Validation

The application passed `31` checks.

All seven core-table populations remained unchanged.

Core rows modified:

`0`

Final result:

`AZURE_SQL_RETURN_FOUNDATION_APPLICATION_PASSED`

### Result

The exact-session daily-return and exact-month-end SQL foundation was created successfully.

### Next Step

Independently audit calendar continuity, return formulas, month-end selection, identity continuity, and source preservation.

---

## 3.32 Azure SQL Return-Foundation Integrity Audit

### Objective

Independently validate the return-foundation views without modifying the database.

### Audit Script

`src/analysis/audit_azure_sql_return_foundation.py`

### Audit Report

`reports/data_quality/azure_sql_return_foundation_integrity_audit.txt`

### Calendar Validation

The audit confirmed:

- exactly 1,255 unique SPY sessions
- exact coverage from `2021-01-04` through `2025-12-31`
- every SPY session points to its immediately preceding session
- exactly 60 calendar months
- one exact final SPY session per calendar month
- analysis-month numbering from 1 through 60

### Constituent Return Validation

The audit confirmed:

- all 631,942 constituent observations are preserved
- constituent security/date keys are unique
- complete daily returns use the immediately preceding SPY session
- incomplete returns remain null
- each security identity has exactly one initial incomplete return
- all calculated returns match the adjusted-close formula
- the `CDAY` to `DAY` identity transition remains continuous

Complete constituent daily returns:

`631,349`

### Month-End Validation

Constituent month-end observations:

`30,211`

Monthly constituent population range:

`502-505`

Every monthly population exactly matched the underlying core month-end prices.

Benchmark month-end observations:

`120`

### Final Result

Passed checks:

`36`

Core rows modified:

`0`

Final result:

`AZURE_SQL_RETURN_FOUNDATION_INTEGRITY_AUDIT_PASSED`

and:

`SQL RETURN-FOUNDATION QUALITY GATE COMPLETE`

### Result

The daily-return and exact-month-end foundations are analysis-ready.

### Next Step

Create exact-calendar monthly return and canonical 12-1 momentum feature views.

---

## 3.33 Azure SQL Monthly Return Features

### Objective

Create monthly constituent and benchmark feature views using exact calendar-month anchors and the documented adjusted-close methodology.

### SQL Migration

`sql/analytics/004_create_monthly_return_feature_views.sql`

### Application Script

`src/analysis/apply_azure_sql_monthly_return_features.py`

### Application Report

`reports/data_quality/azure_sql_monthly_return_feature_application.txt`

### Objects Created

The migration created or updated:

- `analytics.v_security_monthly_return_features`
- `analytics.v_benchmark_monthly_return_features`

### Features Created

The views calculate:

- 1-month trailing return
- 3-month trailing return
- 6-month trailing return
- 12-month trailing return
- canonical 12-1 momentum
- exact completeness indicators
- required historical anchor dates

No forward-looking performance fields were added.

### Application Results

Constituent feature rows:

`30,211`

Complete canonical 12-1 momentum rows:

`23,401`

Benchmark feature rows:

`120`

Passed checks:

`24`

Core rows modified:

`0`

Final result:

`AZURE_SQL_MONTHLY_RETURN_FEATURE_APPLICATION_PASSED`

### Performance Issue

Although the feature calculations were logically correct, querying the original nested constituent feature view was too expensive for the two-vCore serverless database.

A simple feature-row count required approximately:

`271 seconds`

Long-running audit queries produced intermittent Azure SQL timeouts and communication-link failures.

### Decision

Preserve the validated formulas while materializing the exact month-end source observations into indexed analytical snapshot tables.

### Next Step

Create transactionally refreshed, indexed month-end snapshots and rebuild the feature views on those snapshots.

---

## 3.34 Indexed Month-End Snapshot Optimization

### Objective

Eliminate repeated evaluation of the expensive nested month-end views while preserving exact reconciliation to the validated source calculations.

### SQL Migration

`sql/analytics/005_create_indexed_month_end_snapshots.sql`

### Application Script

`src/analysis/apply_azure_sql_month_end_snapshot_optimization.py`

### Application Report

`reports/data_quality/azure_sql_month_end_snapshot_optimization.txt`

### Objects Created

The migration created indexed analytical snapshot tables:

- `analytics.security_month_end_snapshot`
- `analytics.benchmark_month_end_snapshot`

The monthly feature views were recreated against these snapshot tables without changing their formulas or output structure.

### Refresh Strategy

The snapshot refresh:

- executes transactionally
- clears and reloads both snapshot tables
- reconciles the snapshot populations to their original source views
- commits only after all validation checks pass
- leaves the normalized core tables unchanged

### Snapshot Results

Constituent snapshot rows:

`30,211`

Benchmark snapshot rows:

`120`

Snapshot refresh elapsed time:

`0.796 seconds`

### Performance Results

Constituent feature count:

`30,211`

Feature-count elapsed time:

`0.051 seconds`

Complete momentum count:

`23,401`

Momentum-count elapsed time:

`0.109 seconds`

The feature-count runtime decreased from approximately `271` seconds to `0.051` seconds.

### Validation

The optimization passed `31` checks.

Both snapshots exactly reconciled to their original source views.

Core rows modified:

`0`

Final result:

`AZURE_SQL_MONTH_END_SNAPSHOT_OPTIMIZATION_PASSED`

### Connection Correction

The Python optimization runner initially attempted to assign a timeout to a `pyodbc.Cursor`, which does not support that attribute.

The timeout was correctly assigned to the connection before cursor creation.

### Result

The monthly feature layer retains its validated calculations while providing reliable query performance for independent auditing and subsequent analysis.

### Next Step

Run the complete monthly return-feature integrity audit against the optimized snapshot-backed feature layer.

---

## 3.35 Azure SQL Monthly Return-Feature Integrity Audit

### Objective

Independently validate every monthly return and momentum feature after the indexed snapshot optimization.

The audit is read-only and performs no database modifications.

### Audit Script

`src/analysis/audit_azure_sql_monthly_return_features.py`

### Audit Report

`reports/data_quality/azure_sql_monthly_return_feature_integrity_audit.txt`

### Python and Driver Configuration

Python package:

`pyodbc==5.3.0`

Required system driver:

`ODBC Driver 18 for SQL Server`

`mssql-python` remains installed for the existing bulk-copy ingestion workflow.

### Constituent Feature Validation

Constituent feature rows:

`30,211`

Complete 1-month returns:

`29,623`

Complete 3-month returns:

`28,464`

Complete 6-month returns:

`26,752`

Complete 12-month returns:

`23,401`

Complete canonical 12-1 momentum signals:

`23,401`

The audit confirmed:

- unique month/security feature keys
- exact reconciliation to the indexed month-end snapshots
- exact lag-observation completeness
- exact adjusted-close return formulas
- exact month `-1` and month `-12` momentum anchors
- an 11-month momentum window ending one month before ranking
- continuous `CDAY` to `DAY` security identity
- zero forward-looking feature columns

### Benchmark Feature Validation

Benchmark feature rows:

`120`

Complete benchmark 1-month returns:

`118`

Complete benchmark 3-month returns:

`114`

Complete benchmark 6-month returns:

`108`

Complete benchmark 12-month returns:

`96`

Complete benchmark momentum observations:

`96`

Each benchmark contains `48` complete momentum observations.

### Final Result

Passed checks:

`40`

Forward-looking feature columns:

`0`

Core rows modified:

`0`

Final result:

`AZURE_SQL_MONTHLY_RETURN_FEATURE_INTEGRITY_AUDIT_PASSED`

and:

`SQL MONTHLY FEATURE-ENGINEERING QUALITY GATE COMPLETE`

### Result

The exact-calendar monthly return and canonical 12-1 momentum features are correct, source-reconciled, free of forward-looking fields, and analysis-ready.

### Next Step

Create the point-in-time monthly momentum-ranking and portfolio-assignment layer.

The next layer must define eligibility, ranking order, tie handling, portfolio counts, and decile assignment before forward returns are joined.
---
## 3.36 Azure SQL Point-in-Time Momentum Rankings

### Objective

Convert the validated canonical 12-1 momentum signals into deterministic monthly cross-sectional rankings and equal-weighted decile assignments without introducing forward-return information.

### SQL Migration

`sql/analytics/006_create_momentum_ranking_views.sql`

### Application Script

`src/analysis/apply_azure_sql_momentum_rankings.py`

### Application Report

`reports/data_quality/azure_sql_momentum_ranking_application.txt`

### Analytical Objects Created

The migration created or updated:

- `analytics.v_security_monthly_momentum_ranking`
- `analytics.v_security_monthly_momentum_portfolio`
- `analytics.v_momentum_decile_monthly_summary`

### Eligibility Convention

A security is eligible for ranking only when:

- `momentum_12_1_complete = 1`
- `momentum_12_1` is not null
- its validated point-in-time feature row exists for the ranking month

### Ranking Convention

Momentum is ranked independently within each month.

Descending rank:

- rank 1 represents the highest momentum
- exact ties are resolved by `security_key` ascending

Ascending rank:

- rank 1 represents the lowest momentum
- exact ties are resolved by `security_key` descending

The ascending and descending ranks are exact complements.

### Portfolio Convention

`NTILE(10)` assigns approximately equal momentum deciles.

Portfolio definitions:

- decile 1: `LOSER`
- deciles 2 through 9: `MIDDLE`
- decile 10: `WINNER`

Each security receives an equal weight within its monthly decile.

### Application Results

Ranking months:

`48`

Eligible momentum rows:

`23,401`

Monthly eligible population range:

`485-491`

Monthly decile summary rows:

`480`

Forward-looking ranking columns:

`0`

Core rows modified:

`0`

Passed checks:

`36`

Final result:

`AZURE_SQL_MOMENTUM_RANKING_APPLICATION_PASSED`

### Result

The point-in-time momentum rankings and portfolio assignments were created successfully.

### Next Step

Independently reconstruct and audit ranking populations, ranks, ties, deciles, labels, weights, and look-ahead controls.

---

## 3.37 Azure SQL Momentum-Ranking Integrity Audit

### Objective

Independently validate the complete momentum-ranking and portfolio-assignment layer without modifying the database.

### Audit Script

`src/analysis/audit_azure_sql_momentum_rankings.py`

### Audit Report

`reports/data_quality/azure_sql_momentum_ranking_integrity_audit.txt`

### Source Reconciliation

The audit confirmed:

- exactly 23,401 eligible momentum observations
- exactly 48 ranking months
- ranking dates from `2022-01-31` through `2025-12-31`
- monthly eligible populations of 485 through 491
- exact reconciliation to the validated monthly feature source
- unique month/security ranking keys

### Rank and Tie Validation

The audit independently reconstructed:

- descending momentum rank
- ascending momentum rank
- exact-tie population
- deterministic tie-break order

All reconstructed values matched the ranking view.

Rows participating in exact momentum ties:

`0`

### Portfolio Validation

The audit independently reconstructed all decile assignments using `NTILE(10)`.

Monthly decile population range:

`48-50`

Portfolio assignment rows:

`23,401`

Winner portfolio rows:

`2,307`

Loser portfolio rows:

`2,353`

Both winner and loser portfolios cover all 48 ranking months.

Momentum is monotonic across adjacent deciles in every month.

### Weight and Summary Validation

Every security’s equal weight matched:

`1 / monthly decile population`

Every monthly decile’s weights sum to one.

Monthly decile summary rows:

`480`

Every summary row exactly reconciled to the detailed assignments.

### Look-Ahead Controls

The audit confirmed:

- forward-looking columns: 0
- future-row SQL window functions: 0
- signal windows span months `-12` through `-1`
- every signal skips its ranking month
- forward performance remains outside the ranking layer

### Final Result

Passed checks:

`36`

Core rows modified:

`0`

Final result:

`AZURE_SQL_MOMENTUM_RANKING_INTEGRITY_AUDIT_PASSED`

and:

`SQL MOMENTUM-RANKING QUALITY GATE COMPLETE`

### Result

Point-in-time rankings, deterministic ordering, decile assignments, portfolio labels, and equal weights are valid and analysis-ready.

### Next Step

Define and implement the forward-return and portfolio-performance layer.

Forward returns must be joined only after portfolio assignments are fixed. The next layer must explicitly address exact holding periods, constituent exits, terminal observations, right-censoring, benchmark alignment, and the unavailable post-scope return for the final December 2025 ranking.

## 3.38 Azure SQL One-Month Forward-Return Layer

### Date

2026-08-22

### Objective

Create a reproducible Azure SQL layer that connects each fixed point-in-time momentum portfolio assignment to its subsequent one-month holding-period return.

The assignment population must remain fixed before any future price information is joined.

### SQL Migration

`sql/analytics/007_create_forward_return_views.sql`

### Application Script

`src/analysis/apply_azure_sql_forward_returns.py`

### Application Report

`reports/data_quality/azure_sql_forward_return_application.txt`

### Source Objects

The forward-return layer uses:

- `analytics.v_security_monthly_momentum_portfolio`
- `analytics.v_spy_month_end_calendar`
- the indexed benchmark month-end snapshot
- `core.daily_security_price`
- the validated benchmark price history

### Holding-Period Convention

Each security is assigned to its momentum portfolio using only information available at the ranking month-end.

The intended holding period is:

- start: the ranking month-end
- target end: the following SPY month-end
- return horizon: one month

The fixed portfolio assignment is established before the subsequent holding return is joined.

### Terminal-Exit Treatment

When a security has no validated price on the target month-end because its usable market history ends during the holding month, the last validated observation within the holding window is used.

Holding boundaries are classified as:

- `EXACT_MONTH_END`
- `EARLY_EXIT`
- `IMMEDIATE_EXIT`
- `OUT_OF_SCOPE`

An early or immediate exit is treated as a documented terminal holding boundary rather than an unexplained missing return.

December 2025 assignments are right-censored because their January 2026 holding-period endpoints fall outside the validated 2021-2025 project scope.

### Analytical Views

The migration created or updated five views:

- `analytics.v_security_monthly_forward_return_1m`
- `analytics.v_benchmark_monthly_forward_return_1m`
- `analytics.v_momentum_decile_forward_return_1m`
- `analytics.v_momentum_long_short_forward_return_1m`
- `analytics.v_momentum_monthly_performance_1m`

### Portfolio Aggregation

Security-level forward returns are aggregated using the equal weights fixed during portfolio assignment.

The output provides:

- all ten momentum-decile returns
- winner-portfolio returns
- loser-portfolio returns
- winner-minus-loser returns
- SPY forward returns
- S&P 500 index forward returns
- winner-minus-SPY returns
- loser-minus-SPY returns

### Application Validation

Passed checks:

`46`

Analytical views created or updated:

`5`

Constituent holding rows:

`23,401`

Complete constituent holding returns:

`22,916`

Exact-month-end constituent holdings:

`22,850`

Early-exit constituent holdings:

`63`

Immediate-exit constituent holdings:

`3`

Out-of-scope constituent holdings:

`485`

Benchmark holding rows:

`96`

Complete decile return rows:

`470`

Complete winner-minus-loser months:

`47`

Complete benchmark-comparison months:

`47`

Core rows modified:

`0`

Final result:

`AZURE_SQL_FORWARD_RETURN_APPLICATION_PASSED`

### Decision

The project uses a fixed-assignment, next-month holding-return convention.

Terminal observations are preserved when they represent the final validated price of a security that exits during the holding month. This avoids silently discarding delisted or acquired securities and reduces survivorship bias.

December 2025 is retained as a documented right-censored ranking month but is excluded from completed forward-performance calculations.

### Result

The point-in-time momentum portfolios now have validated one-month forward returns for every observable holding month.

The layer is ready for independent integrity auditing.

---

## 3.39 Azure SQL Forward-Return Integrity Audit

### Date

2026-08-23

### Objective

Independently verify that the Azure SQL forward-return layer preserves fixed point-in-time assignments, uses valid holding boundaries, calculates returns correctly, aggregates portfolios accurately, and introduces no look-ahead dependency.

The audit is read-only and performs no database modifications.

### Audit Script

`src/analysis/audit_azure_sql_forward_returns.py`

### Audit Report

`reports/data_quality/azure_sql_forward_return_integrity_audit.txt`

### Independent Validation

The audit independently confirmed:

- all required forward-return objects are present
- all 23,401 fixed portfolio assignments are preserved
- constituent month/security keys are unique
- every holding row preserves its original rank, decile, weight, and starting price
- every realized endpoint is the final validated security price within its holding window
- all complete constituent returns match the adjusted-close formula
- terminal-boundary classifications reconcile exactly
- all benchmark returns match the adjusted-close formula
- every decile return matches an independent security-level aggregation
- assigned and complete decile weights reconcile to one
- winner-minus-loser returns equal winner returns minus loser returns
- winner-minus-SPY and loser-minus-SPY returns match their formulas
- only December 2025 is right-censored
- signal and assignment objects contain no forward-looking columns
- signal and assignment objects do not depend on forward-return objects
- all core-table populations remain unchanged

### Final Result

Passed checks:

`47`

Constituent holding rows:

`23,401`

Complete constituent returns:

`22,916`

Exact-month-end holdings:

`22,850`

Early-exit holdings:

`63`

Immediate-exit holdings:

`3`

Right-censored holdings:

`485`

Benchmark holding rows:

`96`

Complete decile return rows:

`470`

Complete winner-minus-loser months:

`47`

Complete benchmark-comparison months:

`47`

Look-ahead dependencies:

`0`

Core rows modified:

`0`

Final result:

`AZURE_SQL_FORWARD_RETURN_INTEGRITY_AUDIT_PASSED`

and:

`SQL FORWARD-RETURN QUALITY GATE COMPLETE`

### Result

The one-month forward-return layer is point-in-time valid, terminal-exit aware, independently reconciled, and ready for portfolio-performance analysis.

No unexplained in-scope holding returns are missing.

No portfolio assignments were changed after observing future returns.

No forward-return dependency enters the momentum signal or portfolio-assignment layers.

### Issues / Limitations

December 2025 contains 485 valid momentum assignments but no completed one-month forward return because January 2026 is outside the validated project scope.

Transaction costs, turnover costs, risk-free returns, and risk-adjusted performance statistics have not yet been applied.

### Next Step

Create the Azure SQL portfolio-performance layer using the 47 complete observable holding months.

The next layer should calculate:

- cumulative wealth
- arithmetic and geometric average returns
- annualized return
- annualized volatility
- maximum drawdown
- positive-month frequency
- benchmark-relative performance
- winner-minus-loser performance
- portfolio turnover

Risk-free-rate and transaction-cost conventions must be established before producing Sharpe ratios, net-of-cost results, or regression-based alpha estimates.

---

## 3.40 Azure SQL Portfolio-Performance and Cumulative-Wealth Layer

### Date

2026-08-23

### Objective

Convert the validated one-month forward-return series into a portfolio-level performance layer capable of measuring compounded wealth, return characteristics, drawdowns, benchmark-relative performance, and momentum-portfolio turnover.

The layer uses only the 47 complete observable holding months established by the validated forward-return methodology.

### SQL Migration

`sql/analytics/008_create_portfolio_performance_views.sql`

### Application Script

`src/analysis/apply_azure_sql_portfolio_performance.py`

### Application Report

`reports/data_quality/azure_sql_portfolio_performance_application.txt`

### Source Objects

The portfolio-performance layer builds on the previously validated ranking and forward-return objects:

- `analytics.v_security_monthly_momentum_portfolio`
- `analytics.v_momentum_decile_forward_return_1m`
- `analytics.v_momentum_long_short_forward_return_1m`
- `analytics.v_benchmark_monthly_forward_return_1m`

Portfolio assignments remain fixed before future returns enter the analytical process.

### Analytical Objects Created

The migration created or updated six analytical views:

- `analytics.v_momentum_monthly_return_panel`
- `analytics.v_momentum_cumulative_wealth`
- `analytics.v_momentum_wealth_drawdown`
- `analytics.v_momentum_performance_summary`
- `analytics.v_momentum_decile_turnover`
- `analytics.v_momentum_turnover_summary`

### Monthly Return Panel

The monthly panel contains 13 analytical series:

- momentum deciles 1 through 10
- winner-minus-loser (`WML`)
- SPY
- S&P 500 index

Each series contains exactly:

`47`

complete observable monthly returns.

Monthly return-panel rows:

`611`

The right-censored December 2025 forward-return period remains excluded because January 2026 falls outside the validated analytical scope.

### Cumulative-Wealth Convention

Each analytical series begins with wealth indexed to:

`1.00`

Monthly wealth is compounded sequentially using:

`ending_wealth = beginning_wealth × (1 + monthly_return)`

Each month's beginning wealth equals the preceding month's ending wealth.

Cumulative-wealth rows:

`611`

### Drawdown Convention

For each series, the layer tracks the historical running wealth peak.

Drawdown is calculated as:

`ending_wealth / running_peak_wealth - 1`

This measures the percentage decline from the highest wealth value previously achieved by the strategy.

Drawdown rows:

`611`

### Performance Summary

The performance-summary layer contains one row for each of the 13 analytical series.

The summary includes portfolio-level measures derived from the 47 complete monthly returns, including:

- arithmetic average monthly return
- geometric average monthly return
- cumulative return
- annualized return
- monthly volatility
- annualized volatility
- best monthly return
- worst monthly return
- positive-month frequency
- maximum drawdown
- SPY-relative active return statistics
- tracking error
- information ratio where defined

Performance-summary rows:

`13`

### Benchmark Treatment

SPY and the S&P 500 index are retained as separate benchmark series.

SPY represents the investable ETF benchmark.

The S&P 500 index represents the underlying index benchmark.

SPY is used as the reference series for active-return and tracking-error calculations in the current performance layer.

### Portfolio-Turnover Convention

Turnover is measured from the target portfolio weights established by consecutive monthly momentum rankings.

For each decile and rebalance month, the layer compares:

- prior securities
- current securities
- retained securities
- portfolio entries
- portfolio exits
- security overlap
- target-weight changes

One-way turnover measures the proportion of portfolio capital that would need to be reallocated to move from the previous target portfolio to the new target portfolio.

Decile turnover rows:

`470`

Turnover-summary rows:

`10`

Rebalances per decile:

`47`

December 2025 remains included in turnover because the December target portfolio is a valid point-in-time rebalance even though its January 2026 forward return is right-censored.

### Gross-Performance Convention

The current portfolio-performance layer represents:

`GROSS PERFORMANCE`

No transaction costs are deducted.

The following methodologies remain intentionally deferred:

- risk-free-rate adjustment
- Sharpe ratio
- regression alpha
- transaction-cost-adjusted performance
- net-of-cost performance

These measures require additional methodological decisions and, where applicable, external data before they are calculated.

### Application Validation

Passed checks:

`56`

Analytical views created or updated:

`6`

Monthly return-panel rows:

`611`

Analytical series:

`13`

Observable gross-performance months:

`47`

Cumulative-wealth rows:

`611`

Drawdown rows:

`611`

Performance-summary rows:

`13`

Decile-turnover rows:

`470`

Turnover-summary rows:

`10`

Core rows modified:

`0`

Final result:

`AZURE_SQL_PORTFOLIO_PERFORMANCE_APPLICATION_PASSED`

### Result

The validated forward-return layer has been converted into a complete gross portfolio-performance framework.

The project can now evaluate how the momentum portfolios compounded through time, how volatile they were, how deeply they declined from prior peaks, how they performed relative to SPY, and how much portfolio rebalancing the momentum strategy required.

### Next Step

Independently reconstruct the portfolio-performance calculations in Python and reconcile them against the Azure SQL analytical views before accepting the results as authoritative.

---

## 3.41 Azure SQL Portfolio-Performance Integrity Audit

### Date

2026-08-23

### Objective

Independently validate the complete portfolio-performance layer without modifying the database.

The audit reconstructs the monthly performance panel, cumulative wealth, drawdowns, summary statistics, and momentum-decile turnover directly in Python using the previously validated ranking and forward-return sources.

### Audit Script

`src/analysis/audit_azure_sql_portfolio_performance.py`

### Audit Report

`reports/data_quality/azure_sql_portfolio_performance_integrity_audit.txt`

### Audit Mode

The audit is:

`READ-ONLY`

No analytical or core database rows are modified.

### Independent Monthly Return Reconstruction

Python independently reconstructed all portfolio and benchmark return observations from the previously validated forward-return sources.

Validated:

- monthly return-panel rows: `611`
- analytical series: `13`
- observable performance months: `47`
- month/series key mismatches: `0`
- return-value mismatches: `0`

The observable performance period corresponds exactly to analysis months:

`13 through 59`

The right-censored December 2025 return remains excluded.

### Independent Cumulative-Wealth Reconstruction

Python independently compounded every monthly return sequence beginning at:

`1.00`

Validated:

- cumulative-wealth rows: `611`
- broken wealth chains: `0`
- compounding mismatches: `0`
- nonpositive wealth observations: `0`

Every SQL wealth observation matched the independent Python calculation.

### Independent Drawdown Reconstruction

Python independently reconstructed:

- running wealth peaks
- monthly drawdowns
- maximum drawdowns

Validated drawdown rows:

`611`

Independent Python drawdown mismatches:

`0`

### Independent Performance-Summary Reconstruction

Python independently recalculated the statistics for all 13 analytical series directly from monthly returns.

The audit independently verified:

- arithmetic return
- geometric return
- cumulative return
- annualized return
- monthly volatility
- annualized volatility
- best month
- worst month
- positive-month frequency
- maximum drawdown
- SPY-relative active-return statistics
- tracking error
- information ratio where defined

Performance-summary rows:

`13`

Independent Python performance-summary mismatches:

`0`

SPY correctly produced zero active return and zero tracking error relative to itself.

### Independent Turnover Reconstruction

The audit reloaded all:

`23,401`

fixed momentum assignments and independently reconstructed portfolio changes between consecutive ranking months.

For every month and decile, Python independently calculated:

- prior security count
- current security count
- retained securities
- entries
- exits
- overlap
- one-way target-weight turnover

Independent turnover rows:

`470`

SQL turnover rows:

`470`

Independent Python turnover mismatches:

`0`

Turnover covers exactly:

`47`

consecutive monthly rebalances corresponding to analysis months:

`14 through 60`

### Independent Turnover-Summary Reconstruction

Python independently aggregated the monthly turnover results for all ten momentum deciles.

Turnover-summary rows:

`10`

Independent Python turnover-summary mismatches:

`0`

### Methodology and Look-Ahead Controls

The audit confirmed:

- risk-free-rate fields are absent
- Sharpe-ratio fields are absent
- regression-alpha fields are absent
- transaction-cost fields are absent
- net-of-cost fields are absent
- December 2025 realized returns remain excluded
- December 2025 remains correctly included as a valid turnover rebalance
- ranking and forward-return source objects do not depend on the new performance layer
- the performance layer introduces no backward dependency into signal construction or portfolio assignment

### Core Preservation

All validated core populations remained unchanged.

Core rows modified:

`0`

### Final Result

Passed checks:

`50`

Monthly return-panel rows:

`611`

Analytical series:

`13`

Observable gross-performance months:

`47`

Cumulative-wealth rows:

`611`

Drawdown rows:

`611`

Performance-summary rows:

`13`

Decile-turnover rows:

`470`

Turnover-summary rows:

`10`

Independent Python return-panel mismatches:

`0`

Independent Python wealth mismatches:

`0`

Independent Python drawdown mismatches:

`0`

Independent Python performance-summary mismatches:

`0`

Independent Python turnover mismatches:

`0`

Independent Python turnover-summary mismatches:

`0`

Gross performance convention:

`YES`

Risk-free-rate dependency:

`NO`

Sharpe ratio calculated:

`NO`

Regression alpha calculated:

`NO`

Transaction costs applied:

`NO`

Core rows modified:

`0`

Final result:

`AZURE_SQL_PORTFOLIO_PERFORMANCE_INTEGRITY_AUDIT_PASSED`

and:

`SQL PORTFOLIO-PERFORMANCE QUALITY GATE COMPLETE`

### Result

The gross portfolio-performance layer is independently validated and analysis-ready.

Every SQL return, wealth, drawdown, performance-summary, and turnover result reconciles to an independent Python reconstruction.

The project can now begin interpreting the actual momentum-strategy results without relying on unverified analytical calculations.

### Issues / Limitations

The performance history contains 47 observable forward-return months.

December 2025 remains right-censored for realized performance because January 2026 is outside the validated project scope.

Current results are gross of transaction costs.

Risk-free-rate-adjusted performance, Sharpe ratios, regression alpha, and net-of-cost results remain outside the current validated methodology.

### Next Step

Inspect and document the validated portfolio-performance results, including:

- winner performance
- loser performance
- winner-minus-loser performance
- cumulative wealth
- annualized returns
- annualized volatility
- maximum drawdown
- positive-month frequency
- SPY and S&P 500 benchmark comparisons
- momentum-decile behavior
- portfolio turnover

After the gross results are understood, define the risk-free-rate and transaction-cost methodologies before implementing Sharpe ratios, regression alpha, or net-of-cost performance.

---

## 3.42 Validated Gross Momentum-Strategy Results and Interpretation Checkpoint

> **SUPERSEDED ANALYTICAL CHECKPOINT — retained for audit history.**
>
> The 47-month results documented in this section were calculated correctly for the then-current SQL feature population, but that feature population was later found to omit validated pre-membership lookback prices that had been intentionally acquired for momentum construction. Section 3.43 documents the correction. All 47-month performance and statistical findings must be treated as historical diagnostics only and must not be used as the current project result.


### Date

2026-08-23

### Objective

Extract, document, and interpret the first validated portfolio-level momentum results produced by the completed SQL performance layer.

This checkpoint is intentionally analytical rather than methodological. It records what the validated 47-month gross-performance sample currently shows, while explicitly separating observed findings from conclusions that still require statistical, risk-adjusted, and net-of-cost testing.

### Analysis Script

`src/analysis/analyze_momentum_portfolio_results.py`

### Analysis Report

`reports/analysis/momentum_portfolio_results.txt`

### Source Objects

The analysis reads only from the previously validated portfolio-performance views:

- `analytics.v_momentum_performance_summary`
- `analytics.v_momentum_monthly_return_panel`
- `analytics.v_momentum_wealth_drawdown`
- `analytics.v_momentum_turnover_summary`

No database modifications are performed.

### Analysis Scope

The validated gross-performance sample contains:

- 47 observable forward-return months
- 13 analytical series
- 10 momentum deciles
- 1 winner-minus-loser (`WML`) series
- SPY
- S&P 500 index
- 611 monthly return-panel observations
- 470 month/decile turnover observations

The analysis remains gross of transaction costs and does not yet include:

- risk-free-rate adjustment
- Sharpe ratios
- regression alpha
- transaction-cost-adjusted performance
- statistical significance tests

### Primary Performance Findings

Winner decile (`D10`):

- final wealth from $1.00: `1.6913`
- cumulative return: `69.13%`
- annualized return: `14.36%`
- annualized volatility: `19.19%`
- maximum drawdown: `-14.23%`
- positive-month frequency: `63.83%`
- annualized active return versus SPY: `1.94%`
- information ratio versus SPY: `0.197`

Loser decile (`D01`):

- final wealth from $1.00: `1.1546`
- cumulative return: `15.46%`
- annualized return: `3.74%`
- annualized volatility: `24.23%`
- maximum drawdown: `-26.95%`
- positive-month frequency: `46.81%`

Winner-minus-loser (`WML`):

- final wealth from $1.00: `1.3187`
- cumulative return: `31.87%`
- annualized return: `7.32%`
- annualized volatility: `18.35%`
- maximum drawdown: `-22.82%`
- positive-month frequency: `65.96%`

SPY:

- final wealth from $1.00: `1.6023`
- cumulative return: `60.23%`
- annualized return: `12.79%`
- annualized volatility: `15.82%`
- maximum drawdown: `-20.25%`
- positive-month frequency: `65.96%`

S&P 500 index:

- final wealth from $1.00: `1.5160`
- cumulative return: `51.60%`
- annualized return: `11.21%`
- annualized volatility: `15.79%`
- maximum drawdown: `-20.85%`
- positive-month frequency: `63.83%`

### Cross-Portfolio Findings

Winner-decile annualized return minus loser-decile annualized return:

`10.62 percentage points`

Winner-decile annualized return minus SPY annualized return:

`1.57 percentage points`

Observed monthly comparisons:

- D10 beat D01 in `31 of 47` months
- D10 beat SPY in `25 of 47` months
- D01 beat SPY in `17 of 47` months
- WML was positive in `31 of 47` months
- SPY beat the S&P 500 index in `45 of 47` months

### Decile Pattern

Annualized returns by momentum decile:

- D01: `3.74%`
- D02: `0.62%`
- D03: `8.73%`
- D04: `5.24%`
- D05: `8.09%`
- D06: `8.48%`
- D07: `9.16%`
- D08: `8.77%`
- D09: `8.08%`
- D10: `14.36%`

Adjacent annualized returns increase in only:

`5 of 9`

decile transitions.

### Interpretation

The observed sample shows a strong separation between the highest- and lowest-momentum portfolios.

The winner decile produced the highest annualized return of all 13 analytical series and materially outperformed the loser decile.

The winner decile also exceeded SPY on a gross annualized basis over the observed sample while experiencing a smaller maximum drawdown than SPY.

However, the momentum effect is not perfectly monotonic across all ten deciles.

The middle deciles do not produce a smooth increase in return from D01 through D10. The strongest observed effect is concentrated primarily in the highest-momentum portfolio rather than appearing as a perfectly ordered decile gradient.

This distinction is important and should be preserved in future interpretation.

The WML series provides additional evidence of a meaningful observed spread between the strongest- and weakest-momentum securities:

- annualized return: `7.32%`
- cumulative return: `31.87%`
- positive in `31 of 47` months

The `10.62` percentage-point difference between independently annualized D10 and D01 returns is not expected to equal the `7.32%` annualized WML result.

WML is formed by subtracting D01 from D10 at the monthly-return level and then compounding that return series through time.

### Drawdown Interpretation

The winner portfolio's observed maximum drawdown:

`-14.23%`

was smaller than:

- SPY: `-20.25%`
- S&P 500 index: `-20.85%`
- loser decile: `-26.95%`

Within this sample, the winner portfolio therefore did not achieve its higher gross return simply by accepting a larger maximum peak-to-trough decline.

This is an economically interesting result, but it requires further risk-adjusted and statistical analysis before being interpreted as a persistent risk advantage.

### Turnover Findings

Average monthly target-weight turnover:

- D01: `27.07%`
- D10: `28.64%`
- all deciles average: `59.84%`
- highest observed decile turnover: D07 at `72.82%`

Average security overlap:

- D01: `72.96%`
- D10: `71.45%`

The extreme momentum portfolios are substantially more persistent than the middle deciles.

This suggests that securities near the strongest and weakest momentum extremes tend to remain in those extreme portfolios more often than securities remain in the middle momentum buckets.

The annualized turnover values are simple annualizations of monthly target-weight turnover and do not represent trading losses.

Transaction costs remain unmodeled.

### Benchmark Interpretation

SPY outperformed the S&P 500 index in:

`45 of 47`

observed months.

Under the current methodology, SPY adjusted-close returns represent an investable total-return-style benchmark, while the S&P 500 index series is retained separately as the underlying index benchmark.

For current active-return comparisons, SPY remains the primary reference series.

The benchmark difference should continue to be documented so that SPY-versus-index return differences are not misinterpreted as tracking skill.

### Important Interpretation Boundary

The current evidence is economically interesting but not yet sufficient to claim that the momentum effect is statistically reliable, structurally persistent, or implementable after costs.

The observed sample contains only:

`47 months`

of completed forward performance.

The winner portfolio's gross annualized advantage over SPY is modest relative to its much larger advantage over the loser portfolio.

The current winner information ratio versus SPY is:

`0.197`

Therefore, the current evidence supports a documented sample finding, not a final claim of persistent abnormal performance.

### Current Working Interpretation

The current project evidence supports the following provisional interpretation:

The 2022-2025 validated sample exhibits a substantial cross-sectional separation between the highest- and lowest-momentum S&P 500 securities. The winner decile produced the strongest gross annualized performance in the analysis and modestly outperformed SPY while experiencing a smaller observed maximum drawdown. The effect is concentrated at the highest-momentum extreme rather than displaying a perfectly monotonic decile-return gradient.

This interpretation remains provisional and requires formal statistical testing, risk-adjusted analysis, transaction-cost modeling, and additional robustness analysis before stronger conclusions are made.

### Questions Requiring Further Study

Before progressing to presentation or final conclusions, the project should determine:

- whether mean WML return is statistically different from zero
- whether the D10 minus D01 return spread is statistically significant
- whether D10 excess return over SPY is statistically significant
- whether observed performance is concentrated in a small number of unusually strong months
- whether the decile relationship has a statistically meaningful cross-sectional trend
- whether results remain economically meaningful after realistic transaction costs
- whether risk-adjusted performance remains favorable after introducing a documented risk-free rate
- whether regression-based alpha remains positive after controlling for market exposure
- whether the result persists across subperiods or market regimes
- whether sector concentration helps explain the winner-decile result

### Result

The first validated gross momentum-strategy results have been extracted and documented.

The project now has an explicit analytical interpretation checkpoint separating:

- validated observed results
- provisional interpretation
- unresolved statistical questions
- deferred risk-adjusted methodology
- deferred transaction-cost methodology

No final momentum-performance claim is made at this stage.

### Next Step

Perform formal statistical testing of the validated 47-month momentum results before introducing additional performance methodology.

The next analytical layer should test:

- WML mean return versus zero
- D10 minus D01 performance
- D10 excess return versus SPY
- sensitivity to extreme months
- cross-decile trend strength

After statistical testing, define the risk-free-rate and transaction-cost methodologies before calculating Sharpe ratios, regression alpha, or net-of-cost performance.

---

## 3.43 Momentum Lookback-Scope Correction and Independent Quality Gate

### Date

2026-08-24

### Objective

Correct a methodological boundary discovered after the first gross-results and statistical-analysis checkpoints.

The original project design intentionally acquired approximately one year of pre-window market history so that trailing 12-month and canonical 12-1 momentum could be calculated beginning in the 2021 analytical window.

The SQL feature layer, however, used the membership-clipped 2021-2025 month-end snapshot as both:

- the ranking-date population, and
- the historical lag-price population.

That implementation correctly prevented non-members from entering portfolios, but it also removed valid pre-membership historical prices that were intended only for feature construction.

### Design Error

The prior SQL feature source conflated two distinct concepts:

1. **Ranking eligibility**
   - must be a valid point-in-time S&P 500 constituent
   - must have the active project ticker for the ranking date
   - must have a valid ranking-date market observation

2. **Historical feature support**
   - may use validated price observations before S&P 500 membership
   - must belong to the same permanent `security_key`
   - does not grant index membership
   - exists only to calculate trailing features

Because the historical lag source was clipped to membership, the prior implementation did not use the acquired 2020 support prices for January-December 2021 momentum rankings.

The same issue could also suppress valid signals for securities newly added to the S&P 500 later in the 2021-2025 period when their pre-membership trading history was already available and validated.

### Read-Only Scope Inspection

Inspection script:

`src/analysis/inspect_2021_momentum_lookback_coverage.py`

Inspection report:

`reports/data_quality/momentum_lookback_scope_correction_inspection.txt`

The inspection first reproduced the existing validated snapshot-only feature population before evaluating any correction.

Old-state reconciliation:

- constituent month-end snapshot rows: `30,211`
- complete 1-month rows: `29,623`
- complete 3-month rows: `28,464`
- complete 6-month rows: `26,752`
- complete 12-month rows: `23,401`
- complete canonical 12-1 momentum signals: `23,401`
- ranking months: `48`
- ranking span: analysis months `13-60`

This exact reconstruction confirmed that the problem was a methodological scope boundary rather than a random data or SQL inconsistency.

### Corrected Feature-Support Result

Using validated standardized price history by permanent security identity while keeping ranking-date membership constrained produced:

- exact constituent feature-support rows: `37,245`
- exact benchmark feature-support rows: `144`
- support months: `72`
- support span: `2020-01` through `2025-12`
- corrected 1-month complete constituent rows: `30,209`
- corrected 3-month complete constituent rows: `30,192`
- corrected 6-month complete constituent rows: `30,169`
- corrected 12-month complete constituent rows: `30,121`
- corrected canonical 12-1 momentum signals: `30,121`
- restored momentum signals: `6,720`
- incomplete 12-1 ranking rows: `90`
- corrected ranking months: `60`

2021 complete momentum signals:

- 2021-01: `502`
- 2021-02: `502`
- 2021-03: `505`
- 2021-04: `505`
- 2021-05: `505`
- 2021-06: `504`
- 2021-07: `504`
- 2021-08: `504`
- 2021-09: `504`
- 2021-10: `504`
- 2021-11: `504`
- 2021-12: `504`

### SQL Correction

Migration:

`sql/analytics/009_correct_momentum_feature_lookback_scope.sql`

Application script:

`src/analysis/apply_azure_sql_momentum_lookback_correction.py`

Application report:

`reports/data_quality/azure_sql_momentum_lookback_correction_application.txt`

The correction created analytical feature-support tables:

- `analytics.security_month_end_feature_support`
- `analytics.benchmark_month_end_feature_support`

The support tables contain exact SPY-month-end historical observations used only as trailing feature anchors.

The ranking-date population remains:

`analytics.security_month_end_snapshot`

Therefore, the existence of a historical price observation before membership cannot cause a security to enter a momentum portfolio before it is actually an S&P 500 constituent.

### Corrected Feature Methodology

For each valid ranking-date constituent observation:

1. preserve point-in-time membership and ranking-date eligibility
2. locate historical price anchors by permanent `security_key`
3. allow those anchors to precede S&P 500 membership
4. compute trailing returns from corrected historical support
5. calculate canonical 12-1 momentum from:
   - month `-12`
   - through month `-1`
6. continue to exclude the ranking month from the signal
7. rank only valid S&P 500 members at the ranking date

The corrected design therefore preserves survivorship-bias controls while using the historical prices intentionally collected for signal construction.

### Application Quality Gate

The correction application passed:

`65 checks`

Key corrected downstream populations:

- corrected momentum assignments: `30,121`
- ranking months: `60`
- decile forward-return rows: `600`
- complete decile forward-return rows: `590`
- winner-minus-loser rows: `60`
- complete winner-minus-loser months: `59`
- benchmark forward-return rows: `120`
- complete benchmark forward-return rows: `118`
- security forward-return rows: `30,121`
- complete security forward returns: `29,620`
- right-censored December 2025 assignments: `501`
- gross monthly return-panel rows: `767`
- analytical series: `13`
- observable completed performance months: `59`
- turnover rows: `590`
- turnover months: `59`

Core rows modified:

`0`

Final application result:

`AZURE_SQL_MOMENTUM_LOOKBACK_SCOPE_CORRECTION_PASSED`

### Independent Integrity Audit

Audit script:

`src/analysis/audit_azure_sql_momentum_lookback_correction.py`

Audit report:

`reports/data_quality/azure_sql_momentum_lookback_correction_integrity_audit.txt`

The audit is read-only and independently reconstructs the correction from the validated standardized price history.

It verifies:

- all `37,245` constituent support observations
- all `144` benchmark support observations
- security identity
- project ticker
- exact SPY month-end anchor date
- adjusted close
- 1-month lag dates and returns
- 3-month lag dates and returns
- 6-month lag dates and returns
- 12-month lag dates and returns
- all `30,121` canonical 12-1 momentum values
- all momentum start and end anchors
- all 60 monthly ranking populations
- downstream ranking and forward-return propagation
- December 2025 right-censoring
- performance-panel structure
- wealth and drawdown structural validity
- unchanged core populations

Independent audit checks passed:

`65`

Failed checks:

`0`

Final audit result:

`AZURE_SQL_MOMENTUM_LOOKBACK_SCOPE_CORRECTION_INTEGRITY_AUDIT_PASSED`

and:

`CORRECTION QUALITY GATE COMPLETE`

### Core Preservation

The following validated core populations remained unchanged:

- securities: `593`
- ticker-history rows: `594`
- membership intervals: `593`
- price-eligibility rows: `594`
- constituent daily observations: `631,942`
- benchmark definitions: `2`
- benchmark daily observations: `2,510`

Core-table modifications detected:

`0`

### Analytical Consequence

The original intended study is now restored:

- feature-support history: `2020-01` through `2025-12`
- analytical ranking window: `2021-01` through `2025-12`
- ranking months: `60`
- completed one-month forward-performance months: `59`
- December 2025 ranking: right-censored because January 2026 is outside project scope

The previously reported 47-month gross-performance results and the statistical tests calculated from that 47-month panel are now **superseded**.

Those calculations were valid for the narrower snapshot-only feature population, but they are not the final intended 2021-2025 experiment.

They must not be used as current evidence for:

- winner performance
- loser performance
- winner-minus-loser performance
- SPY-relative performance
- drawdowns
- turnover
- statistical significance
- decile monotonicity

The corrected 59-month analytical panel must be re-extracted and re-tested before any economic or statistical interpretation is carried forward.

### Decision

Do not extend to risk-free-rate methodology, Sharpe ratios, regression alpha, or transaction-cost-adjusted performance until the corrected gross-results and statistical analyses have been rerun and documented.

### Result

The lookback-scope correction is complete and independently validated.

The project is again aligned with its original methodology:

**2020 historical prices support feature construction; 2021-2025 point-in-time membership defines portfolio eligibility.**

### Next Step

Commit the methodological correction and its quality-gate evidence.

After the correction commit:

1. rerun corrected gross portfolio-results extraction across all 59 completed months
2. document the new economic findings
3. rerun formal statistical testing across the corrected 59-month panel
4. compare the corrected findings with the superseded 47-month checkpoint only as an audit/history exercise
5. then proceed to risk-free-rate, Sharpe, regression-alpha, and transaction-cost methodology

---

## 3.44 Corrected 2021-2025 Momentum Hypothesis Final Risk/Cost Closeout

### Date

2026-08-24

### Objective

Finalize the corrected 2021-2025 momentum-performance hypothesis by combining:

- corrected gross portfolio performance
- formal statistical testing
- ex-ante risk-free-rate adjustment
- Sharpe ratios
- CAPM-style alpha and beta
- transaction-cost sensitivity
- winner-minus-loser short-leg implementation sensitivity

This checkpoint closes the current momentum hypothesis before the project opens a new research hypothesis.

### Corrected Analytical Sample

The final corrected experiment uses:

- feature-support history: `2020-01` through `2025-12`
- point-in-time ranking window: `2021-01` through `2025-12`
- ranking months: `60`
- completed forward-performance months: `59`
- analytical series: `13`
- monthly return-panel rows: `767`
- corrected canonical 12-1 momentum signals: `30,121`
- right-censored final ranking month: December 2025

The previous 47-month result remains superseded.

### Final Gross Performance Findings

Winner decile (`D10`):

- cumulative return: `84.21%`
- annualized return: `13.23%`
- annualized volatility: `18.49%`
- maximum drawdown: `-17.30%`
- positive-month frequency: `61.02%`

Loser decile (`D01`):

- cumulative return: `63.67%`
- annualized return: `10.54%`
- annualized volatility: `23.57%`
- maximum drawdown: `-25.95%`
- positive-month frequency: `54.24%`

Winner-minus-loser (`WML`):

- cumulative return: `-1.63%`
- annualized return: `-0.33%`
- annualized volatility: `18.65%`
- maximum drawdown: `-23.82%`
- positive months: `34 of 59`

SPY:

- cumulative return: `97.40%`
- annualized return: `14.83%`
- annualized volatility: `15.23%`
- maximum drawdown: `-23.93%`
- positive-month frequency: `67.80%`

S&P 500 index:

- cumulative return: `84.30%`
- annualized return: `13.24%`
- annualized volatility: `15.18%`
- maximum drawdown: `-24.77%`

### Gross Economic Interpretation

The winner decile outperformed the loser decile by:

`2.69 percentage points`

on the independently annualized gross-return basis.

However:

- D10 underperformed SPY by `1.60 percentage points` annually
- D03, not D10, was the best momentum decile
- D03 annualized return: `13.40%`
- D10 annualized return: `13.23%`
- adjacent decile annualized-return increases: `5 of 9`
- WML compounded to a slightly negative return

The corrected 2021-2025 sample therefore does not show a dominant or monotonic momentum payoff.

### Formal Statistical Testing

Primary WML / D10-minus-D01 mean-spread test:

- mean monthly WML: `0.118%`
- classical t-test p-value: `0.8666`
- bootstrap 95% mean interval: `[-1.256%, 1.442%]`
- Wilcoxon p-value: `0.5868`
- sign-test p-value: `0.2976`
- Newey-West/HAC p-value: `0.8351`

D10 excess return versus SPY:

- mean monthly excess return: `-0.076%`
- classical t-test p-value: `0.8408`
- bootstrap 95% mean interval: `[-0.789%, 0.670%]`
- Wilcoxon p-value: `0.4969`
- sign-test p-value: `0.7948`
- Newey-West/HAC p-value: `0.8223`

Cross-decile trend:

- mean monthly slope: `0.010%` per decile step
- classical slope p-value: `0.8827`
- Newey-West/HAC slope p-value: `0.8515`
- mean monthly Spearman correlation: `0.0817`
- mean-Spearman p-value: `0.3201`

Holm-adjusted primary hypothesis results:

- WML mean vs zero: do not reject
- D10 excess vs SPY: do not reject
- cross-decile mean slope vs zero: do not reject

All Holm-adjusted p-values:

`1.0000`

### Statistical Interpretation

The corrected 59-month sample does not provide statistically significant evidence that:

- mean WML return differs from zero
- D10 reliably outperforms SPY
- returns increase systematically with momentum decile

The observed effect estimates are also economically small relative to their month-to-month variability.

This is stronger than merely saying that the sample may lack power. The point estimates themselves do not indicate a large, stable momentum premium in the corrected experiment.

### Risk-Free-Rate Methodology

Risk-free proxy:

`FRED DGS1MO`

Series name:

`Market Yield on U.S. Treasury Securities at 1-Month Constant Maturity, Quoted on an Investment Basis`

Timing rule:

Use the latest available DGS1MO observation on or before each ranking date.

Holding-period conversion:

`annualized yield / 100 x actual holding days / 365`

Controls:

- aligned months: `59`
- earliest ranking date: `2021-01-29`
- latest ranking date: `2025-11-28`
- annual-yield range used: `0.010%` to `5.600%`
- holding-period risk-free return range: `0.001%` to `0.506%`
- maximum observation age at formation: `0 days`
- future risk-free observations used: `0`

DGS1MO is treated as a reproducible market-yield proxy, not as the realized return from purchasing a specific Treasury bill.

### Sharpe-Ratio Findings

D01:

- annualized return: `10.54%`
- annualized volatility: `23.57%`
- annualized arithmetic excess return: `9.42%`
- Sharpe: `0.399`

D03:

- annualized return: `13.40%`
- annualized volatility: `17.26%`
- annualized arithmetic excess return: `10.79%`
- Sharpe: `0.625`

D10:

- annualized return: `13.23%`
- annualized volatility: `18.49%`
- annualized arithmetic excess return: `10.84%`
- Sharpe: `0.587`

SPY:

- annualized return: `14.83%`
- annualized volatility: `15.23%`
- annualized arithmetic excess return: `11.75%`
- Sharpe: `0.774`

S&P 500 index:

- annualized return: `13.24%`
- annualized volatility: `15.18%`
- annualized arithmetic excess return: `10.33%`
- Sharpe: `0.683`

D10 Sharpe minus SPY Sharpe:

`-0.187`

### Risk-Adjusted Interpretation

The winner decile's smaller maximum drawdown did not translate into a superior overall sample Sharpe ratio.

SPY had:

- higher annualized return
- lower annualized volatility
- higher annualized Sharpe

Therefore, the corrected sample does not support the hypothesis that D10 provided a better overall return-per-unit-of-volatility profile than SPY.

### CAPM / Market-Regression Findings

Regression for long-only portfolios:

`(R_portfolio - R_f) = alpha + beta * (R_SPY - R_f) + error`

Regression for WML:

`R_WML = alpha + beta * (R_SPY - R_f) + error`

Inference:

Newey-West/HAC, lag `3`

D10:

- monthly alpha: `-0.096%`
- annualized arithmetic alpha: `-1.152%`
- alpha HAC p-value: `0.7764`
- beta: `1.020`
- beta p-value: `<0.0001`
- R-squared: `0.704`

WML:

- monthly alpha: `0.288%`
- annualized arithmetic alpha: `3.454%`
- alpha HAC p-value: `0.5821`
- beta: `-0.173`
- beta p-value: `0.2432`
- R-squared: `0.020`

D01:

- annualized arithmetic alpha: `-4.606%`
- alpha p-value: `0.3855`
- beta: `1.193`

D03:

- annualized arithmetic alpha: `-0.657%`
- alpha p-value: `0.8592`
- beta: `0.974`

### CAPM Interpretation

D10's beta of approximately `1.02` indicates market exposure close to SPY, but its estimated alpha is negative and statistically indistinguishable from zero.

WML has low market explanatory power in this sample, but its positive estimated alpha is also statistically indistinguishable from zero.

The corrected experiment therefore does not provide evidence of statistically significant market-adjusted abnormal return for D10 or WML.

CAPM is only a one-factor control and does not account for other systematic factor exposures.

### Long-Only Transaction-Cost Sensitivity

Transaction-cost assumptions:

- `5 bps`
- `10 bps`
- `20 bps`

per unit of one-way turnover.

Initial January 2021 portfolio formation:

`100% one-way turnover`

Subsequent months use validated portfolio turnover.

D10:

- gross annualized return: `13.23%`
- 5 bps net annualized return: `13.023%`
- 10 bps net annualized return: `12.817%`
- 20 bps net annualized return: `12.406%`

Annualized D10 return drag:

- 5 bps: `0.206%`
- 10 bps: `0.412%`
- 20 bps: `0.824%`

D01:

- 5 bps net annualized return: `10.346%`
- 10 bps net annualized return: `10.154%`
- 20 bps net annualized return: `9.769%`

Because D10 already underperformed SPY gross, realistic positive trading costs only widen the observed performance disadvantage.

### WML Trading and Borrow-Cost Sensitivity

WML is treated separately as a zero-cost:

`long D10 / short D01`

spread.

Trading-cost scenarios apply to both legs.

Illustrative annual short-borrow fee scenarios:

- `0 bps`
- `50 bps`
- `100 bps`
- `200 bps`

At `5 bps` trading cost:

- 0 bps borrow: `-0.693%` annualized
- 50 bps borrow: `-1.190%`
- 100 bps borrow: `-1.684%`
- 200 bps borrow: `-2.667%`

At `10 bps` trading cost:

- 0 bps borrow: `-1.049%`
- 50 bps borrow: `-1.545%`
- 100 bps borrow: `-2.038%`
- 200 bps borrow: `-3.017%`

At `20 bps` trading cost:

- 0 bps borrow: `-1.759%`
- 50 bps borrow: `-2.251%`
- 100 bps borrow: `-2.741%`
- 200 bps borrow: `-3.714%`

The gross WML result was already slightly negative, so modeled implementation frictions make the long-short strategy progressively less attractive.

These are implementation sensitivity scenarios, not reconstructed realized historical shorting costs.

### Final Momentum-Hypothesis Decision

The corrected 2021-2025 experiment does **not support** the working hypothesis that canonical 12-1 momentum, implemented as monthly S&P 500 momentum deciles, produced a reliable superior return in this sample.

Evidence:

1. D10 did not outperform SPY on gross annualized return.
2. D10 did not outperform SPY on sample Sharpe ratio.
3. D10 CAPM alpha was negative and statistically insignificant.
4. WML gross compounded return was slightly negative.
5. WML mean return was statistically indistinguishable from zero.
6. WML CAPM alpha was statistically insignificant.
7. The decile-return relationship was not monotonic.
8. The cross-decile slope was statistically insignificant.
9. Positive transaction costs reduced D10 returns further.
10. Trading and borrow-cost scenarios reduced WML returns further.

### Important Research Interpretation

This result does not establish that momentum never works.

It establishes that the specific tested implementation:

- S&P 500 point-in-time constituents
- canonical 12-1 adjusted-close momentum
- monthly ranking
- equal-weight momentum deciles
- one-month holding periods
- corrected 2021-2025 analytical window

did not produce statistically reliable or implementation-robust superior performance in this sample.

The project should preserve this as a completed negative/unsupported hypothesis rather than alter the methodology after seeing the result.

That makes the result useful as a research finding and provides a controlled base from which to open new hypotheses.

### Final Status

Gross-performance analysis:

`COMPLETE`

Statistical significance analysis:

`COMPLETE`

Risk-free-rate methodology:

`COMPLETE`

Sharpe-ratio analysis:

`COMPLETE`

CAPM alpha/beta analysis:

`COMPLETE`

Transaction-cost sensitivity:

`COMPLETE`

WML borrow-cost sensitivity:

`COMPLETE`

Current 12-1 momentum hypothesis:

`CLOSED — NOT SUPPORTED IN THE CORRECTED 2021-2025 SAMPLE`

### Next Step

Commit the final risk/cost analysis and this hypothesis-closeout documentation.

After the commit, open a new research hypothesis without rewriting or tuning the completed canonical 12-1 result.

Potential next hypotheses should be treated as new experiments with their own documented rationale, methodology, and validation checkpoint.

---


## 3.45 Point-in-Time GICS Sector Layer and H2 Sector-Relative Momentum Preregistration

### Date

`2026-08-24`

### Objective

Build and validate a point-in-time GICS sector-classification layer for every security-month in the corrected 2021–2025 S&P 500 ranking universe, then preregister the second research hypothesis before inspecting any H2 performance results.

The new experiment is:

**H2 — Sector-relative 12-1 momentum**

Stocks with stronger corrected 12-1 momentum relative to other stocks in their own point-in-time GICS sector are hypothesized to earn higher subsequent one-month returns than weaker sector-relative stocks.

This is a new experiment. The completed H1 canonical market-wide momentum methodology and its unsupported result remain frozen.

### Source Strategy

The GICS layer was constructed from authoritative and regulator-filed sources rather than using a current classification table retroactively.

Primary evidence hierarchy:

1. **Official S&P DJI / MSCI GICS effective-date evidence** for known sector reclassifications.
2. **SEC Form N-PORT filings** for the Select Sector SPDR ETF family as historical quarter-end sector-state evidence.
3. **Official S&P 500 membership-event GICS evidence** where applicable.
4. Audited security-identity reconciliation layers used only to map source identifiers to the project's permanent `security_key`.

Current State Street SPY holdings were used only for identity reconciliation where needed. The current SPY `Sector` field was not used to backfill historical classifications.

Wikipedia was not used as a project data source.

### SEC Select Sector Source Validation

The initial iShares IVV historical-holdings route was tested and rejected because the historical response was not reliably exposed in a usable machine-readable form.

The project then validated the SEC Form N-PORT route for the canonical Select Sector SPDR funds.

Canonical sector series:

- XLC — Communication Services
- XLY — Consumer Discretionary
- XLP — Consumer Staples
- XLE — Energy
- XLF — Financials
- XLV — Health Care
- XLI — Industrials
- XLK — Information Technology
- XLB — Materials
- XLRE — Real Estate
- XLU — Utilities

The SEC complete-submission-text route was used to recover the raw N-PORT XML because direct `primary_doc.xml` requests were rendered as SEC viewer HTML in the local retrieval environment.

### Canonical SEC Snapshot Rebuild

Canonical Select Sector SPDR series IDs were pinned explicitly to prevent newly introduced Premium Income products from being selected as the historical sector funds.

The canonical rebuild produced:

- 21 historical report dates
- 21 / 21 complete 11-sector partitions
- 10,582 raw equity rows
- 10,577 clean canonical equity rows
- 5 tiny residual cross-holdings excluded as ETF implementation artifacts
- 0 unresolved material cross-sector duplicates
- 503–505 unique security identifiers per complete historical snapshot
- exact 503-security partition at 2025-12-31

The five excluded residual cross-holdings were:

- S&P Global in XLI while materially held in XLF during three 2022 quarter-ends
- GE HealthCare in XLI while materially held in XLV during two 2023 quarter-ends

The residual positions were many orders of magnitude smaller than the dominant sector holdings and were retained in the audit record rather than interpreted as genuine dual-sector classifications.

Canonical rebuild result:

`SEC_SELECT_SECTOR_CANONICAL_SOURCE_GATE_PASSED`

### Authoritative GICS Transition Ledger

Twenty sector-transition candidates detected from the canonical SEC sequence were reconciled to authoritative effective-date evidence.

The transition ledger covers:

- Leidos Holdings
- Teledyne Technologies
- Roper Technologies
- Automatic Data Processing
- Broadridge Financial Solutions
- Ceridian / Dayforce
- Dollar General
- Dollar Tree
- Fidelity National Information Services
- Fiserv
- FleetCor / Corpay
- Global Payments
- Jack Henry & Associates
- Mastercard
- Paychex
- Paycom
- PayPal
- Target
- Visa
- CoStar Group

Sixteen transitions use the 2023 GICS structural revision effective after the close of:

`2023-03-17`

with analytical validity beginning:

`2023-03-20`

Company-specific effective dates were preserved separately.

CoStar Group remained:

`Industrials`

through the close of:

`2023-06-30`

and became:

`Real Estate`

from:

`2023-07-03`

The close-date-aware transition validator reconciled all 20 detected transitions exactly.

Result:

`GICS_TRANSITION_EFFECTIVE_DATE_GATE_PASSED`

### Identity-Reconciliation Investigation

The first point-in-time sector builder exposed a systematic identity-bridge defect:

- membership security identities: 593
- identities with sector intervals: 503
- unresolved identities: 90
- missing ranking-date assignments: 5,400
- exact deficit per ranking month: 90

A dedicated diagnostic confirmed that the **same 90 `security_key` values were missing in all 60 months**, proving that the problem was an identity bridge defect rather than missing historical sector coverage.

The identity bridge was then strengthened conservatively without fuzzy auto-matching.

Final identity hierarchy:

1. historical project ticker
2. current State Street SPY CUSIP identity
3. unique exact normalized current / documented-alias company name
4. explicit audited residual identifier override
5. unique identifier propagation from already resolved rows

Ambiguous company-name keys such as Alphabet, Fox, and News were excluded from name-based resolution.

### Audited Residual Identity Overrides

Thirteen exact identifier overrides were required after the deterministic identity tiers.

The override ledger is:

`data/reference/gics/gics_security_key_identity_overrides.csv`

It includes audited mappings for:

- JCI
- LYB
- NCLH
- XOM
- CPAY / historical FleetCor
- PAYC
- CAG
- CPB
- CTRA
- EA
- HOLX
- LW
- POOL

Examples of why explicit overrides were necessary:

- Johnson Controls, LyondellBasell, and Norwegian Cruise Line were represented in SEC N-PORT primarily through non-U.S. ISIN identity.
- FleetCor and Corpay have different CUSIPs but preserve the same SEC LEI, providing deterministic issuer continuity.
- Campbell Soup / The Campbell's Company and Cabot Oil & Gas / Coterra preserved stable SEC CUSIPs across naming changes.
- Pool Corp was explicitly matched to CUSIP `73278L105`; a diagnostic substring match to Whirlpool was identified as a search-only false positive and was not used in the production bridge.

No fuzzy identity rule was introduced.

### CoStar Official Membership-Event Evidence Correction

One official membership-event GICS evidence row was inconsistent with the authoritative historical state.

The local event record for CoStar Group's S&P 500 addition on:

`2022-09-19`

contained:

`Real Estate`

but authoritative evidence establishes that CoStar belonged to:

`Industrials`

at that time.

CoStar's later move to Real Estate is separately represented by the authoritative transition effective after the close of 2023-06-30.

The membership action and effective date were not modified.

A one-row audited sector-evidence correction layer was created:

`data/reference/gics/gics_official_event_sector_overrides.csv`

The correction is applied in memory by the builder and preserves the original source ledger for provenance.

### Evidence-Scope Correction

The evidence audit initially reported 413 mismatches.

A targeted diagnostic showed:

- 412 mismatches were SEC observations dated `2020-12-31`
- 1 mismatch was the CoStar membership-event sector issue described above

The 2020-12-31 observations are pre-window support evidence. They occur before the 2021-01-01 analytical membership intervals and therefore should not be evaluated as contradictions to a 2021–2025 membership classification.

The final builder retains those SEC observations for provenance and support, but sector contradiction checks are applied only when the SEC evidence date overlaps the applicable project membership interval.

This changes the audit scope, not the historical sector source.

### Files Created or Modified

Primary construction and validation:

- `src/analysis/audit_point_in_time_gics_sector_coverage.py`
- `src/analysis/probe_ishares_ivv_historical_holdings.py`
- `src/analysis/probe_sec_select_sector_nport.py`
- `src/analysis/extract_sec_select_sector_historical_holdings.py`
- `src/analysis/rebuild_sec_select_sector_canonical_snapshots.py`
- `src/analysis/diagnose_sec_select_sector_snapshot_anomalies.py`
- `src/analysis/validate_gics_transition_effective_dates.py`
- `src/analysis/build_point_in_time_gics_security_intervals.py`

Targeted identity diagnostics were used during development to isolate mapping failures before the production bridge was changed.

Reference / audit-control files:

- `data/reference/gics/gics_transition_effective_dates.csv`
- `data/reference/gics/gics_security_key_identity_overrides.csv`
- `data/reference/gics/gics_official_event_sector_overrides.csv`

Canonical outputs:

- `data/reference/gics/security_gics_sector_intervals_2021_2025.csv`
- `data/interim/security_gics_sector_month_end_2021_2025.csv`
- `data/reference/gics/sec_gics_identifier_security_key_bridge.csv`
- `reports/data_quality/gics_monthly_sector_coverage.csv`
- `reports/data_quality/point_in_time_gics_security_key_monthly_audit.txt`

H2 specification:

- `docs/h2_sector_relative_momentum_preregistration.md`
- `docs/project_log.md`

### Final Point-in-Time GICS Validation

Final production builder version:

`2026-08-24-v4-final-identity-and-evidence-scope`

Final identity state:

- SEC canonical holding rows: 10,577
- SEC rows mapped to `security_key`: 9,584
- SEC rows retained unmatched for source audit: 993
- unique SEC holding identifiers bridged: 512
- current State Street CUSIP identifiers bridged: 491
- ambiguous current State Street identifiers: 0
- unique normalized current / alias company names bridged: 487
- ambiguous normalized company names excluded: 3
- audited residual identity overrides: 13
- official membership-event rows mapped: 178
- official membership-event rows unmatched: 0
- authoritative GICS transitions mapped: 20
- audited official membership-event GICS corrections applied: 1

Final permanent interval state:

- membership security identities: 593
- security identities with GICS intervals: 593
- GICS interval rows: 613
- authoritative transitions represented: 20
- interval overlaps: 0
- interval gaps: 0
- unresolved initial-sector identities: 0
- unexplained in-membership evidence mismatches: 0

Final monthly state:

- Azure ranking snapshot rows: 30,211
- monthly GICS assignment rows: 30,211
- ranking months: 60
- security identities appearing on at least one ranking date: 588
- missing ranking-date sector assignments: 0
- duplicate security-month assignments: 0
- sector count range: 11 to 11
- monthly security-count range: 502 to 505
- every month reconciles exactly to the ranking snapshot

The difference between 593 membership identities and 588 identities appearing in month-end assignments is expected because some historical constituents can enter and leave between ranking dates without appearing on one of the 60 exact month-end snapshots.

The remaining 993 unmapped SEC ETF rows are retained as source-audit information. They are not a hard H2 failure because the project ranking universe itself is fully classified and contradiction-free.

Final result:

`POINT_IN_TIME_GICS_MONTHLY_QUALITY_GATE_PASSED`

and:

`H2 SECTOR-RELATIVE MOMENTUM DATA PREREQUISITE: READY`

Azure SQL modifications performed by the sector builder:

`0`

Validated price/membership core rows modified:

`0`

### H2 Preregistration

H2 was specified **after the GICS prerequisite passed and before H2 performance results were inspected**.

Full preregistration:

`docs/h2_sector_relative_momentum_preregistration.md`

The preregistration freezes the following rules.

#### Signal

Use the corrected H1 canonical 12-1 signal:

`price(t-1) / price(t-12) - 1`

The ranking month itself remains skipped.

2020 remains lookback support only.

#### Within-Sector Ranking

Within every:

`(ranking_month, gics_sector)`

partition, securities are ordered by:

1. `momentum_12_1 ASC`
2. `security_key ASC`

and assigned deterministic quintiles using the equivalent of:

`NTILE(5)`

Q1 is the loser sleeve.

Q5 is the winner sleeve.

#### Portfolio Weighting

Within each sector sleeve:

`equal weight by security`

Across sectors:

`equal weight across all 11 GICS sectors`

This prevents large sectors from dominating the aggregate strategy.

Primary aggregate return:

`sector-neutral Winner - sector-neutral Loser`

#### Forward Period

One-month forward return using the same terminal-exit and censoring rules as corrected H1.

December 2025 remains a ranking month but is excluded from realized-return inference if January 2026 forward performance is unavailable.

#### Primary Statistical Test

Primary null:

`H0: mean monthly aggregate sector-neutral W-L = 0`

Inference:

`two-sided HAC / Newey-West lag 3`

Significance threshold:

`alpha = 0.05`

Directional support requires:

- aggregate mean W-L > 0
- two-sided HAC(3) p-value < 0.05

A statistically insignificant positive point estimate is not classified as support.

#### Robustness Tests

The preregistration also requires:

- ordinary one-sample t-test
- bootstrap 95% confidence interval
- Wilcoxon signed-rank test
- sign test
- HAC(3) intercept test
- 11 sector-level W-L tests with Holm adjustment
- quintile monotonicity diagnostics
- benchmark comparisons
- DGS1MO-based Sharpe ratios
- CAPM alpha/beta against SPY
- target-weight turnover
- implementation-cost sensitivity
- short-borrow sensitivity

#### Cost Grid

One-way transaction costs:

- 5 bps
- 10 bps
- 20 bps

Annualized borrow costs on the loser leg:

- 0 bps
- 50 bps
- 100 bps
- 200 bps

Base-case implementation scenario:

`10 bps transaction cost + 100 bps annualized loser-leg borrow`

#### Cross-Sector Concentration Test

Broad cross-sector support additionally requires:

- at least 9 of 11 leave-one-sector-out mean W-L estimates remain positive
- no single sector contributes more than 50% of cumulative gross aggregate W-L

A statistically significant result that fails either implementation-cost or cross-sector-concentration robustness is reported as qualified rather than broad support.

### H2 Decision Labels Frozen Before Results

The H2 experiment must use exactly these interpretation classes:

- `SUPPORTED — BROAD AND COST-ROBUST`
- `SUPPORTED — QUALIFIED`
- `NOT SUPPORTED`
- `INVALID / REVIEW REQUIRED`

Any post-result alternative signal, cutoff, weighting scheme, sector exclusion, inference rule, or sample window must be labeled exploratory and cannot alter the preregistered H2 conclusion.

### Issues / Limitations

- Select Sector SPDR N-PORT filings provide historical quarter-end sector-state evidence rather than a native daily GICS history.
- Exact reclassification dates therefore come from authoritative S&P DJI / MSCI transition evidence, not inferred solely from ETF quarter-end states.
- Current State Street SPY holdings are used only for identity reconciliation in documented bridge tiers, not for historical sector backfilling.
- Unmapped SEC ETF rows remain in audit outputs; they do not affect the fully classified point-in-time ranking universe.
- No H2 return, significance, or performance result has been inspected at this checkpoint.

### Decision

The point-in-time GICS prerequisite is closed.

H2 is formally preregistered as a separate experiment.

The H1 canonical 12-1 momentum conclusion remains:

`CLOSED — NOT SUPPORTED IN THE CORRECTED 2021-2025 SAMPLE`

No H1 parameter will be retuned in response to that result.

### Output

Analysis-ready H2 sector layer:

`data/interim/security_gics_sector_month_end_2021_2025.csv`

Permanent sector-history layer:

`data/reference/gics/security_gics_sector_intervals_2021_2025.csv`

Formal H2 specification:

`docs/h2_sector_relative_momentum_preregistration.md`

### Next Step

Commit the validated GICS source / identity / interval layer and the H2 preregistration **before** implementing or running H2 performance analysis.

After that commit:

1. implement the within-sector quintile assignment layer;
2. independently audit the ranking and weighting rules;
3. construct the one-month sector-sleeve and sector-neutral forward-return layer;
4. audit the complete H2 performance population;
5. only then expose H2 return results.

### Git Commit

`PENDING — commit the GICS quality-gate closure and H2 preregistration before viewing H2 performance results.`

---

---

## 3.46 H2 Sector-Relative Momentum Implementation, Validation, and Final Closeout

### Date

2026-08-24

### Objective

Implement the preregistered H2 sector-relative 12-1 momentum experiment, independently validate its ranking and forward-return layers, apply the frozen statistical/risk/cost rules, and close the hypothesis without post-result retuning.

### Source

H2 used only previously validated project inputs:

- corrected canonical 12-1 momentum features;
- point-in-time S&P 500 ranking snapshots;
- validated point-in-time GICS sector assignments;
- validated one-month security forward returns;
- SPY and S&P 500 benchmark returns;
- FRED DGS1MO as the ex-ante risk-free proxy.

### Files Created or Modified

Primary implementation:

- `sql/analytics/010_create_h2_sector_relative_momentum_ranking.sql`
- `sql/analytics/011_create_h2_sector_relative_forward_return_views.sql`
- `src/analysis/apply_azure_sql_h2_sector_relative_rankings.py`
- `src/analysis/audit_azure_sql_h2_sector_relative_rankings.py`
- `src/analysis/apply_azure_sql_h2_sector_relative_forward_returns.py`
- `src/analysis/audit_azure_sql_h2_sector_relative_forward_returns.py`
- `src/analysis/analyze_h2_sector_relative_momentum.py`
- `src/analysis/audit_h2_sector_relative_momentum_analysis.py`

Canonical H2 outputs include:

- `reports/analysis/h2_sector_relative_momentum_analysis.txt`
- `reports/analysis/h2_primary_inference.csv`
- `reports/analysis/h2_sector_inference.csv`
- `reports/analysis/h2_quintile_monotonicity.csv`
- `reports/analysis/h2_risk_adjusted_summary.csv`
- `reports/analysis/h2_capm_summary.csv`
- `reports/analysis/h2_turnover_monthly.csv`
- `reports/analysis/h2_cost_borrow_sensitivity.csv`
- `reports/analysis/h2_leave_one_sector_out.csv`
- `reports/analysis/h2_sector_contribution.csv`
- `reports/analysis/h2_risk_free_monthly.csv`

### Method / Transformation

Within each `(ranking_month, gics_sector)`, securities were ordered by corrected `momentum_12_1 ASC, security_key ASC` and assigned deterministic quintiles.

- Q1 = Loser
- Q5 = Winner
- securities equal weighted within each sector sleeve
- all 11 sector sleeves equal weighted in the aggregate
- primary spread = sector-neutral Winner minus Loser
- one-month forward holding period
- December 2025 retained as a ranking month but right-censored for realized performance

Primary inference remained the preregistered two-sided HAC/Newey-West lag-3 mean test at `alpha = 0.05`.

### Validation

Final H2 ranking state:

- ranking assignments: `30,121`
- ranking months: `60`
- month/sector partitions: `660`
- month/sector/quintile rows: `3,300`
- ranking/weighting integrity gate: `PASSED`

Final H2 performance state:

- security holding rows: `30,121`
- complete security forward returns: `29,620`
- right-censored December-2025 rows: `501`
- complete sector/quintile returns: `3,245`
- complete Winner/Loser sector returns: `1,298`
- complete aggregate Winner/Loser legs: `118`
- complete aggregate W-L months: `59`
- forward-return integrity audit: `PASSED`

### Result

Aggregate sector-neutral W-L:

- mean monthly return: `+0.186%`
- arithmetic annualized mean: `+2.237%`
- geometric annualized return: `+1.605%`
- annualized volatility: `11.399%`
- maximum drawdown: `-13.234%`
- primary HAC(3) p-value: `0.6043`

Robustness:

- t-test p-value: `0.6650`
- bootstrap 95% monthly mean interval: `[-0.654%, +0.997%]`
- Wilcoxon p-value: `0.4504`
- sign-test p-value: `0.4350`
- no individual sector survived Holm adjustment
- quintile adjacent increases: `3 of 4`

Risk / implementation:

- Winner annualized return: `12.575%`
- Loser annualized return: `9.482%`
- W-L Sharpe ratio: `0.196`
- SPY annualized return: `14.834%`
- SPY Sharpe ratio: `0.774`
- W-L CAPM annualized arithmetic alpha: `+3.221%`
- W-L alpha p-value: `0.4601`
- Winner mean one-way turnover: `27.240%`
- Loser mean one-way turnover: `26.000%`
- base-case `10 bps + 100 bps borrow` net annualized W-L: `-0.049%`

Cross-sector robustness:

- positive leave-one-sector-out estimates: `11 / 11`
- largest additive sector contribution: `50.719%`
- preregistered concentration criterion: `FAIL`

### Decision

**H2 FINAL LABEL: `NOT SUPPORTED`**

The primary directional rule failed because the positive W-L estimate was not statistically significant under the frozen HAC(3) test. The base-case implementation result was slightly negative and the frozen cross-sector concentration threshold also failed.

No H1 or H2 parameter was retuned after results.

### Issues / Limitations

- The 59-month sample is limited.
- Cost and borrow values are scenarios rather than reconstructed execution costs.
- DGS1MO is a constant-maturity yield proxy.
- CAPM controls only for SPY market exposure.
- The 50% concentration threshold was narrowly missed but was not relaxed after the result.

### Next Step

Open a separately labeled post-H2 exploratory branch to determine whether cross-sector Winner behavior contains residual commonality worth characterizing.

### Git Commit

Checkpoint message: `research: close H2 and preserve preregistered sector-relative momentum result`

---

## 3.47 Post-H2 Winner Commonality — Phase 1 and Phase 2

### Date

2026-08-24

### Objective

Determine whether the sector-relative Winner sleeves exhibited common behavior after stripping broad market and own-sector return exposure, without altering H2.

### Method

Phase 1 constructed:

- Winner membership and persistence histories;
- cross-sector Winner correlations;
- own-sector equal-weight return baselines;
- per-sector regressions of Winner-sector return on SPY and own-sector return;
- residual Winner return series;
- an exploratory commonality factor equal to the cross-sector mean residual;
- PCA and correlation diagnostics.

Phase 2 decomposed the resulting commonality factor additively by security, month, and sector to identify the observations contributing most strongly to exploratory residual commonality.

### Validation

Phase 1:

`POST_H2_WINNER_COMMONALITY_PHASE1_INTEGRITY_AUDIT_PASSED`

Expected source populations included:

- complete constituent forward-return rows: `29,620`
- Winner-sector rows: `649`
- benchmark rows: `118`

Phase 2:

`POST_H2_COMMONALITY_DRIVER_PHASE2_COMPLETE`

and:

`POST_H2_COMMONALITY_DRIVER_PHASE2_INTEGRITY_AUDIT_PASSED`

### Decision

The residual commonality factor is exploratory only. Its average is not itself treated as a new return anomaly, and no causal interpretation is attached to common residual behavior.

### Next Step

Freeze a deterministic research-target sample before collecting external narrative evidence.

### Git Commit

Checkpoint message: `research: add post-H2 residual winner commonality diagnostics`

---

## 3.48 Post-H2 Research Targets and External Evidence — Phase 3A / 3B

### Date

2026-08-24

### Objective

Select research targets deterministically from the completed commonality attribution before reviewing external narrative evidence, then collect authoritative evidence without coding themes during collection.

### Method

Phase 3A froze:

- `30` security targets;
- `15` extreme/commonality-relevant months;
- a deterministic target priority queue;
- target details, similarity, co-occurrence, and external-research manifest.

Phase 3B then collected two evidence records per target across three batches using primary/official sources.

### Validation

Evidence collection produced:

- `60` security evidence rows;
- `30` month evidence rows;
- `90` total merged evidence rows;
- unique evidence IDs;
- primary/official sources only;
- no Wikipedia;
- theme codes intentionally blank during collection;
- support flags initially `UNCLEAR`.

### Decision

Evidence was collected before the thematic taxonomy was frozen to reduce the risk of coding evidence only into a preselected favored narrative.

### Next Step

Freeze a taxonomy independent of return-significance results, then code the already collected evidence.

### Git Commit

Checkpoint message: `research: freeze post-H2 research targets and authoritative evidence ledger`

---

## 3.49 Frozen Theme Taxonomy and Target Coding — Phase 3C / 3D

### Date

2026-08-24

### Objective

Freeze a descriptive taxonomy before full target coding, then code the 45 frozen targets under that unchanged taxonomy.

### Taxonomy Freeze

The frozen taxonomy contains 17 codes:

Security structural themes:

- `S01` AI / Compute / Digital Infrastructure
- `S02` Power / Energy Infrastructure
- `S03` Electrification / Energy Transition
- `S04` Commodity / Resource Scarcity & Pricing
- `S05` Capacity Expansion / Supply-Demand Imbalance
- `S06` Digital Platform / Monetization Shift
- `S07` Experiential / Consumer Demand
- `S08` Real-Asset Occupancy / Demographic Demand
- `S09` Strategic Consolidation / Portfolio Scale
- `S10` Recurring Membership / Customer-Loyalty Economics

Macro month themes:

- `M01` Accommodative Monetary / Fiscal Support
- `M02` Restrictive / Tightening Monetary Policy
- `M03` Easing / Policy-Pivot Transition
- `M04` Disinflation / Inflation Deceleration
- `M05` Persistent / Sticky Inflation
- `M06` Labor / Growth Resilience
- `M07` Macro Uncertainty / Dual-Mandate Rebalancing

Frozen taxonomy SHA-256:

`1c7698cbe2facd069c7a12fda41cbf7399a9f657ed4f7a9f956d135f8f9d2576`

Freeze gate:

`PHASE3C_THEME_TAXONOMY_FREEZE_PASSED`

### Phase 3D Validation

- target matrix rows: `45`
- evidence-to-theme bridge rows: `140`
- unique target-code assignments: `98`
- all evidence remained same-target
- taxonomy checksum preserved

Final gate:

`POST_H2_PHASE3D_THEME_CODING_INTEGRITY_AUDIT_PASSED`

### Descriptive Findings

Most prevalent security themes among the selected top 30 security drivers included:

- S05: `15 / 30`
- S01: `9 / 30`
- S03: `8 / 30`
- S04: `8 / 30`
- S09: `7 / 30`

Because coding is multi-label, prevalence shares are overlapping and cannot be summed.

### Decision

Theme coding is descriptive evidence only. It does not establish synchronized behavior, predictive power, or causality.

### Next Step

Test whether securities sharing a frozen structural theme exhibit unusually synchronized contribution behavior relative to randomized same-size groups.

### Git Commit

Checkpoint message: `research: freeze post-H2 taxonomy and complete evidence coding`

---

## 3.50 Theme-Synchrony Test and Closeout — Phase 4A

### Date

2026-08-24

### Objective

Test whether the frozen structural themes explain residual Winner commonality through unusually synchronized monthly contribution behavior.

### Frozen Test Design

Universe:

the same frozen top-30 security-driver sample.

Monthly security contribution series:

- exact Phase 2 contribution when the security is a Winner;
- zero otherwise;
- `59` months.

Structural-theme metrics:

1. average pairwise Pearson correlation of signed monthly contribution series;
2. correlation between monthly active tagged-Winner count and absolute aggregate commonality factor.

Randomization:

- `20,000` same-sized random groups per eligible theme;
- seed `20260824`;
- one-sided greater-than-null Monte Carlo test;
- Holm adjustment separately for metric A and metric B;
- themes with fewer than three securities descriptive only.

### Validation

- themes analyzed: `10`
- randomized themes: `8`
- descriptive-only themes: `2`
- monthly panel rows: `590`
- taxonomy checksum preserved
- audit checks passed: `13 / 13`

Final gate:

`POST_H2_PHASE4A_THEME_SYNCHRONY_INTEGRITY_AUDIT_PASSED`

### Result

No structural theme survived Holm adjustment.

Notable nominal result:

- S06 synchronization correlation: `+0.1879`
- nominal Monte Carlo p-value: `0.0495`
- Holm-adjusted p-value: `0.3960`

Therefore S06 is **not** statistically significant after the preregistered multiple-testing adjustment.

All presence-versus-absolute-commonality Holm-adjusted p-values were `1.0`.

Macro codes were evaluated descriptively only on the selected extreme months; no macro inference was permitted.

### Decision

**Phase 4A final label: `CLOSED — NO ADJUSTED THEME-SYNCHRONY SIGNAL`**

The taxonomy was not retuned after the null result.

### Next Step

Close the thematic-synchrony explanation branch and evaluate whether an independently measured external attention variable is feasible for a separately preregistered H3.

### Git Commit

Checkpoint message: `research: close Phase 4A with no adjusted theme-synchrony signal`

---

## 3.51 Candidate H3 Attention Research — Source Feasibility Protocol

### Date

2026-08-24

### Objective

Determine whether a historical external-attention dataset can be built cleanly before choosing an H3 transformation or testing any relationship with returns.

### Candidate H3 Concept

Potential future H3 outcomes include:

1. next-month residual security return;
2. next-month probability of entering the sector-relative Winner sleeve;
3. Winner-status × attention interaction for next-month residual return.

No primary outcome or attention transformation is selected based on observed predictive performance.

Timing convention:

`attention through month t → outcome at t+1`

### Source Decision

Google Trends was investigated as a search-attention source, but the official API is alpha and its rolling five-year window does not independently cover the entire January 2021–December 2025 project sample from the current 2026 research date.

A Google Cloud / BigQuery implementation was explicitly rejected for practical infrastructure reasons because the project already uses Azure and there is no methodological need to introduce a second cloud platform solely for the attention layer.

The historical pilot therefore uses direct GDELT downloads over HTTPS.

### Decision

Infrastructure boundary:

- Google Cloud: `NO`
- BigQuery: `NO`
- unofficial Google Trends packages as primary source: `NO`
- direct GDELT historical archive: `YES`
- Azure SQL modification during feasibility: `NO`

### Next Step

Run a no-outcome-leakage direct-GDELT source/coverage/ambiguity pilot before building full history.

### Git Commit

Checkpoint message: `research: define H3 attention feasibility source and infrastructure boundary`

---

## 3.52 Direct GDELT Historical Feasibility Pilot

### Date

2026-08-24

### Objective

Test whether directly downloadable GDELT Global Knowledge Graph files can supply a reproducible historical company-news attention proxy across 2021–2025 without adding Google Cloud infrastructure.

### Source / Metric

Direct daily GDELT GKG archive:

`https://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip`

Pilot company count:

`15`

Frozen historical anchor windows:

`5`

Seven days per anchor:

`35 daily GKG archives`

Company matching uses strict company aliases rather than bare stock tickers.

Attention quantity:

`matched_source_documents / total_source_documents`

The older GKG daily stream's `NUMARTS` value is used as the source-document weight rather than counting every GKG nameset equally.

### Implementation Note

The first execution exposed Python's default CSV field-size limit:

`131,072 bytes`

A valid GDELT row exceeded that limit.

The parser was corrected by raising `csv.field_size_limit()` to the largest platform-supported value before parsing. No attention methodology was changed.

### Validation

Final direct-GDELT pilot audit:

- daily GKG files processed: `35 / 35`
- company-date rows: `525 / 525`
- company-anchor rows: `75 / 75`
- historical anchor windows: `5 / 5`
- pilot companies: `15 / 15`
- all denominators positive
- all attention shares in `[0, 1]`
- parser field limit raised successfully
- SHA-256 recorded for every downloaded archive
- Google Cloud used: `NO`
- Azure SQL used: `NO`
- return/momentum/Winner/outcome columns: `0`
- companies with strict nonzero coverage in at least `2 / 5` anchor windows: `15 / 15`
- all HIGH-ambiguity companies had broad variants available for review

Final gate:

`H3_DIRECT_GDELT_DAILY_PILOT_FEASIBILITY_GATE_PASSED_WITH_AMBIGUITY_REVIEW_REQUIRED`

### Decision

Direct GDELT is historically accessible and operationally feasible enough to continue to an entity-name ambiguity gate.

### Next Step

Review high-ambiguity company-name variants before any larger extraction.

### Git Commit

Checkpoint message: `research: validate direct GDELT historical attention feasibility`

---

## 3.53 GDELT Company-Name Ambiguity Review and Closeout

### Date

2026-08-24

### Objective

Determine whether high-ambiguity company names can be queried with acceptable precision without expanding the strict alias set solely to maximize article counts.

### Pilot Coverage

Company coverage was strong:

- 13 of 15 pilot companies had nonzero strict coverage in `4–5 / 5` windows;
- NRG remained usable at `2 / 5`;
- both HIGH-ambiguity companies had strict coverage in `5 / 5`.

HIGH-ambiguity companies:

- IRM — Iron Mountain Incorporated
- MOS — The Mosaic Company

### IRM Decision

Retain strict aliases:

- `iron mountain incorporated`
- `iron mountain inc`

Reject unrelated school, medical, library, academic, and geographic variants.

Issuer-adjacent variants such as `iron mountain data centers` remain diagnostic-only rather than being promoted automatically.

### MOS Decision

Retain the strict company-name alias.

Do not promote:

- bare `mosaic`;
- `mosaic co`.

The broad variant list contained multiple unrelated community, health, cultural, religious, museum, finance, and other entities.

### Decision

**AMBIGUITY REVIEW CLOSED — CONSERVATIVE STRICT-ALIAS POLICY RETAINED**

Precision is preferred over recall because both high-ambiguity companies already achieved full pilot-window coverage with strict aliases.

No return or outcome data were used in this decision.

### Next Step

Scale identity/query preparation to all 593 historical security identities before downloading full 2021–2025 attention history.

### Git Commit

Checkpoint message: `research: close GDELT pilot ambiguity gate with conservative aliases`

---

## 3.54 Full-Universe H3 Company-Query Candidate Manifest — Stage 3A

### Date

2026-08-24

### Objective

Expand the successful pilot from 15 securities to the full canonical historical security identity universe while preserving a strict separation between current company names and point-in-time historical company-name validity.

### Source

Read-only Azure SQL identity tables:

- `core.security`
- `core.security_ticker_history`

Actual canonical company-name source column:

`company_name_reference`

### Connectivity / Schema Corrections

The first identity-export script encountered an Azure SQL ODBC timeout/connection-string issue. Connection handling was corrected without changing the requested data.

The first candidate builder expected a generic company-name field and stopped when the actual schema showed:

`company_name_reference`

The builder was updated to recognize the real schema explicitly.

The first audit also treated every short canonical issuer name that looked like a ticker as an automatic bare-ticker failure. This was too strict because some legitimate issuer names are themselves acronym/brand names.

The final control therefore adds:

`ticker_like_exact_name_flag`

and requires such cases to remain HIGH ambiguity and enter authoritative review rather than automatically rejecting the source identity.

Examples surfaced:

- CRH
- EQT
- ETSY
- FMC
- LKQ
- NOV
- PTC
- PVH

### Candidate Manifest Result

- security identities: `593`
- ticker-history segments represented: `594`
- identities with multiple ticker segments: `1`
- duplicate exact normalized aliases: `0`
- HIGH structural ambiguity: `210`
- MEDIUM structural ambiguity: `220`
- LOW structural ambiguity: `163`
- ticker-like exact legal/current names: `8`
- PIT/name-history review queue: `211`

### Production Boundary

This remains a **candidate** manifest.

- current names are not assumed valid throughout 2021–2025;
- suffix-stripped names are diagnostic only;
- the normalized exact legal/current name is the only candidate alias;
- no bare ticker is intentionally promoted as an attention query;
- no row is marked point-in-time validated yet.

### Validation State

Candidate build:

`H3_COMPANY_QUERY_MANIFEST_CANDIDATE_BUILD_COMPLETE`

The final V4 audit logic was prepared to treat ticker-like legal issuer names as controlled review cases rather than automatic failures.

At this checkpoint, the final post-V4 integrity-audit output has not been recorded in this log and must be confirmed before Stage 3A is considered closed.

### Decision

The 593-security identity universe is successfully represented, but authoritative company-name history remains required for 211 review identities and any issuer with historical-name evidence.

### Next Step

Use authoritative SEC identity/name-history sources to resolve CIKs, current filer names, and former-name evidence without fuzzy matching.

### Git Commit

Checkpoint message: `research: build full H3 company-query candidate manifest`

---

## 3.55 SEC Company Identity / Historical-Name Resolution Preparation — Stage 3B

### Date

2026-08-24

### Objective

Prepare the authoritative company-identity resolution layer needed before constructing point-in-time GDELT query aliases.

### Planned Authoritative Sources

SEC-only identity sources:

1. `company_tickers.json`
   - current ticker / CIK / conformed company-name associations;

2. `cik-lookup-data.txt`
   - cumulative SEC CIK/entity-name lookup evidence;

3. SEC Submissions API:
   - `https://data.sec.gov/submissions/CIK##########.json`
   - current filer name, tickers, exchanges, and `formerNames`.

### Frozen Mapping Policy

No fuzzy name matching.

Auto-resolution is allowed only when deterministic official-source conditions hold, such as:

- project ticker and exact normalized company name agreeing on one CIK;
- exact current ticker record plus exact normalized company name;
- one unique exact normalized company-name CIK mapping.

Ticker-only matches, conflicts, and non-unique mappings remain review cases.

SEC `formerNames` records are retained as raw authoritative evidence and are not automatically converted into PIT alias intervals.

### Files Prepared

- `src/analysis/resolve_h3_sec_company_name_history.py`
- `src/analysis/audit_h3_sec_company_name_history.py`
- `docs/h3_stage3b_sec_name_history_resolution_protocol.md`

Programmatic SEC access requires a user-supplied `SEC_USER_AGENT` containing a real contact email. This value is environment configuration and must not be committed.

### Validation State

Stage 3B implementation is prepared but has not yet been executed at this checkpoint.

Therefore:

- SEC mapping result: `PENDING`
- SEC former-name extraction: `PENDING`
- Stage 3B integrity audit: `PENDING`
- PIT alias-interval construction: `NOT AUTHORIZED YET`
- full 2021–2025 GDELT extraction: `NOT AUTHORIZED YET`
- H3 inference: `NOT AUTHORIZED`

### Next Step

First confirm the final Stage 3A V4 integrity audit.

Then execute Stage 3B against official SEC sources, audit deterministic CIK mapping and former-name evidence, and only after that construct point-in-time company-name alias intervals.

### Git Commit

Checkpoint message: `research: prepare SEC point-in-time company-name resolution for H3`

---

---

## 3.56 H3 SEC Identity Resolution Execution and PIT Name-Evidence Consolidation — Stages 3B / 3B2

### Date

2026-08-25

### Objective

Execute the previously prepared SEC identity/name-history resolution and consolidate point-in-time historical issuer-name evidence before authorizing any production GDELT alias interval.

The H3 outcome firewall remained active throughout these stages.

### Stage 3B — SEC Company Identity / Name-History Resolution

Primary implementation:

- `src/analysis/resolve_h3_sec_company_name_history.py`
- `src/analysis/audit_h3_sec_company_name_history.py`

Authoritative sources:

- SEC `company_tickers.json`
- SEC cumulative CIK/entity-name lookup data
- SEC Submissions JSON and `formerNames`

Stage 3B result:

- Stage 3A identities: `593`
- identities with candidate SEC CIK: `538`
- auto-resolved SEC mappings: `286`
- identities with SEC former-name evidence: `321`
- unique SEC submission files requested/reused: `534`
- SEC submission download failures: `0`
- Stage 3B review queue: `525`

Mapping status counts:

- `AUTO_SOURCE_AGREEMENT: 280`
- `AUTO_UNIQUE_EXACT_NAME: 6`
- `REVIEW_CONFLICT: 18`
- `REVIEW_TICKER_ONLY: 252`
- `UNRESOLVED: 37`

No fuzzy matching was introduced.

An auto-resolved CIK was treated only as deterministic issuer-identity evidence. It did not automatically authorize a historical company name as a production attention alias.

Return/outcome fields read:

`0`

Full-history GDELT extraction performed:

`NO`

### Stage 3B2 — Point-in-Time Name-Evidence Consolidation

The next layer combined SEC/N-PORT historical issuer-name observations, the project membership identity model, deterministic CIK mappings, and known alias/name events.

Primary implementation:

- `src/analysis/build_h3_pit_name_evidence_consolidation.py`
- `src/analysis/audit_h3_pit_name_evidence_consolidation.py`

Primary outputs included:

- `reports/exploratory/h3_attention_feasibility/h3_pit_name_evidence_security_summary.csv`
- `reports/exploratory/h3_attention_feasibility/h3_pit_name_evidence_review_queue.csv`
- `reports/exploratory/h3_attention_feasibility/h3_pit_name_state_observations.csv`
- `reports/exploratory/h3_attention_feasibility/h3_pit_name_transition_candidates.csv`

Focused Stage 3B2 review identities:

`233`

Historical point-in-time name observations retained in the later audited evidence layer:

`9,584`

The audit required all observations to map back to known project security identities and prohibited return, momentum, Winner, or other H3 outcome fields.

### Decision

Historical issuer-name evidence was now structured sufficiently to begin exact transition-date resolution.

No production GDELT alias interval was yet authorized from unresolved quarterly name-state changes.

### Next Step

Resolve bounded company-name transitions conservatively and isolate every remaining project-period name-state conflict for authoritative closeout.

---

## 3.57 Exact Transition Resolution and Deterministic Name-State Reconciliation — Stages 3C through 3F

### Date

2026-08-25

### Objective

Convert historical issuer-name evidence into defensible point-in-time name states without inferring exact dates from quarterly observations or forcing company-name agreement through fuzzy normalization.

### Stage 3C — Exact Company-Name Transition Resolution

Primary implementation:

- `src/analysis/resolve_h3_exact_name_transitions.py`
- `src/analysis/audit_h3_exact_name_transitions.py`

Result:

- Stage 3B2 focused review identities: `233`
- bounded SEC N-PORT name-transition candidates: `23`
- automatically exact-resolved transitions: `1`
- unresolved bounded transitions: `22`
- additional project-period name-state reconciliation cases: `119`
- targeted authoritative research-manifest rows: `141`
- project-period relevant SEC former-name evidence rows: `100`

Automatic exact-date resolution was intentionally narrow.

An exact date could be assigned automatically only when a dated project security-alias event exactly matched the normalized old/new names and fell inside the SEC N-PORT transition bound.

SEC `formerNames` remained corroborating evidence and was not automatically treated as an exact rename date.

Result token:

`H3_EXACT_NAME_TRANSITION_RESOLUTION_COMPLETE`

### Stage 3D — Authoritative Exact-Transition Closeout

The unresolved bounded transitions were researched against authoritative sources and recorded separately from automatic resolutions.

Key files:

- `src/analysis/apply_h3_authoritative_exact_transition_resolutions.py`
- `src/analysis/audit_h3_authoritative_exact_transition_resolutions.py`
- `data/reference/h3/h3_authoritative_exact_name_transition_resolutions.csv`
- `reports/data_quality/h3_authoritative_exact_transition_closeout_integrity_audit.txt`

The authoritative closeout remained outcome-blind.

### Stage 3E — Deterministic Name-State Reconciliation

Primary implementation:

- `src/analysis/reconcile_h3_remaining_name_states.py`
- `src/analysis/audit_h3_remaining_name_state_reconciliation.py`

Input reconciliation identities:

`119`

Automatically reconciled:

`1`

Remaining targeted research identities:

`118`

Already resolved transition rows used as evidence:

`23`

Status counts:

- `RESEARCH_MULTIPLE_UNEXPLAINED_NPORT_STATES: 1`
- `RESEARCH_PROJECT_PERIOD_SEC_FORMER_NAME_EVIDENCE: 63`
- `RESEARCH_PROJECT_VS_NPORT_NAME_CORE_CONFLICT: 54`
- `RESOLVED_STABLE_LEGAL_STYLE_EQUIVALENT: 1`

No fuzzy matching was used.

Semantic words such as `GROUP`, `HOLDINGS`, `INTERNATIONAL`, `TECHNOLOGIES`, `ENERGY`, `FINANCIAL`, `SYSTEMS`, or `HEALTH` were not stripped merely to manufacture agreement.

Result token:

`H3_DETERMINISTIC_NAME_STATE_RECONCILIATION_COMPLETE`

### Stage 3F — Authoritative Name Convergence

Primary implementation:

- `src/analysis/reconcile_h3_authoritative_name_convergence.py`
- `src/analysis/audit_h3_authoritative_name_convergence.py`

Input Stage 3E research identities:

`118`

Automatically reconciled:

`84`

Remaining primary-source research identities:

`34`

Project-overlapping SEC former-name detail rows inspected:

`71`

Status counts:

- `RESEARCH_AUTHORITATIVE_NAME_CONVERGENCE_NOT_ESTABLISHED: 13`
- `RESEARCH_MULTIPLE_UNEXPLAINED_NPORT_STATES: 1`
- `RESEARCH_SUBSTANTIVE_OR_DISTINCT_SEC_FORMER_NAME: 20`
- `RESOLVED_AUTHORITATIVE_SEC_NPORT_AGREEMENT_PROJECT_REFERENCE_PRESENTATION_DIFFERENCE: 41`
- `RESOLVED_SEC_FORMER_NAMES_REGISTRY_STYLE_EQUIVALENT: 43`

### Methodological Correction

A provider-style `company_name_reference` was not required to equal the historical attention alias when authoritative SEC current identity and SEC-filed N-PORT historical issuer names converged on the same issuer.

Likewise, an SEC former-name record did not automatically force review when all project-overlapping former-name records reduced to the same conservative registry core and had complete date boundaries.

Result token:

`H3_AUTHORITATIVE_NAME_CONVERGENCE_COMPLETE`

### Outcome Firewall

Across Stages 3C through 3F:

- production PIT attention alias intervals were not created prematurely;
- full-history GDELT extraction was not performed;
- return/outcome fields read: `0`.

### Next Step

Close the remaining authoritative research cases, prove full-universe name-resolution coverage, and separately resolve identities lacking N-PORT support.

---

## 3.58 Full-Universe Authoritative Name-State Closure — Stages 3G through 3I

### Date

2026-08-25

### Objective

Close the remaining issuer-name research cases and prove that the complete 593-security historical universe could be represented under deterministic, point-in-time attention-name rules before constructing the production alias manifest.

### Stage 3G — Authoritative Name-State Closeout

Primary files:

- `src/analysis/apply_h3_authoritative_name_state_closeout.py`
- `src/analysis/audit_h3_authoritative_name_state_closeout.py`
- `data/reference/h3/h3_authoritative_name_state_resolutions_stage3g.csv`
- `reports/exploratory/h3_attention_feasibility/h3_authoritative_name_state_closeout.csv`
- `reports/data_quality/h3_authoritative_name_state_closeout_integrity_audit.txt`

The Stage 3F primary-source research population was closed using explicit source-backed dispositions rather than widening automated matching rules.

Representative controls included issuer-history treatment for cases such as Exxon Mobil (`XOM`) and TJX (`TJX`).

### Stage 3H — Full-Universe Name-Resolution Closure

Primary files:

- `src/analysis/build_h3_full_universe_name_resolution_closure.py`
- `src/analysis/audit_h3_full_universe_name_resolution_closure.py`
- `docs/h3_stage3h_full_universe_name_resolution_closure_protocol.md`
- `reports/exploratory/h3_attention_feasibility/h3_full_universe_name_resolution_coverage_v2.csv`
- `reports/data_quality/h3_full_universe_name_resolution_closure_integrity_audit.txt`

The closure reconciled the full Stage 3A candidate universe against all later authoritative evidence layers and ensured that each security identity had exactly one final resolution disposition.

Canonical H3 historical security universe:

`593`

### Stage 3I — Definitive No-NPORT Closure

Some security identities could not rely on the same N-PORT evidence path.

They were handled through a separately documented definitive closure using project membership events, SEC identity/former-name evidence, and known public name/ticker transitions.

Primary files:

- `src/analysis/close_h3_no_nport_identity_batch.py`
- `src/analysis/audit_h3_no_nport_identity_batch.py`
- `docs/h3_stage3i_definitive_no_nport_closure_protocol.md`
- `docs/h3_stage3i_v2_lumen_resolution.md`
- `data/reference/h3/h3_no_nport_known_name_state_events.csv`
- `reports/data_quality/h3_definitive_no_nport_closure_integrity_audit.txt`

Lumen (`LUMN`) received a documented Stage 3I V2 resolution rather than being silently forced through the N-PORT mapping path.

### Decision

The company-identity and historical-name prerequisite was closed across the complete H3 universe.

The next stage was authorized to convert the closed evidence into production point-in-time attention aliases.

Return/momentum/Winner/outcome fields remained prohibited throughout the closure process.

---

## 3.59 Point-in-Time Attention Alias Policy and Transition Safety — Stage 3J

### Date

2026-08-25

### Objective

Translate the closed issuer-name evidence into date-bounded production GDELT aliases while preventing ambiguous entity names, overlapping cross-issuer aliases, and unsupported transition timing from contaminating the attention measure.

### Policy Evolution

The Stage 3J alias policy was refined through explicitly versioned controls:

- `h3_pit_attention_alias_policy_v1.json`
- `h3_pit_attention_alias_policy_v2.json`
- `h3_pit_attention_alias_policy_v3.json`
- `h3_pit_attention_alias_policy_v4.json`
- `h3_pit_attention_alias_policy_v5.json`

The final H3 preregistration later froze:

`H3_PIT_ATTENTION_ALIAS_POLICY_V5`

### Production Builder and Audit

Primary implementation:

- `src/analysis/build_h3_pit_attention_alias_manifest.py`
- `src/analysis/audit_h3_pit_attention_alias_manifest.py`

Primary outputs included:

- `h3_pit_attention_alias_intervals.csv`
- `h3_pit_attention_alias_security_summary.csv`
- `h3_pit_attention_alias_collision_diagnostics.csv`
- `h3_pit_attention_alias_shared_issuer_collisions.csv`
- `h3_pit_attention_alias_precision_control_diagnostics.csv`
- `h3_pit_attention_alias_safety_diagnostics.csv`
- `h3_pit_attention_alias_transition_events.csv`

### Alias Safety Rules

The final design:

- preserves `security_key` as the security identity;
- carries authoritative issuer CIK where available;
- uses full authoritative names when shorter aliases would be ambiguous;
- does not automatically promote bare tickers;
- distinguishes same-issuer multi-security alias overlap from cross-issuer collision;
- permits shared aliases only when both rows map to the same nonblank authoritative issuer CIK;
- blocks unresolved or cross-issuer collisions;
- preserves point-in-time alias validity intervals.

### Transition Alignment Preflight

A dedicated all-transition preflight audited:

- collected authoritative transition evidence rows: `33`
- securities with in-sample name transitions: `26`
- final-state/source mismatches under Policy V2: `3`
- sequential transition-chain nonmatches: `0`
- display-only candidate mismatches: `1`

Initial alignment classes:

- `MATCH_POLICY_V2: 23`
- `DISPLAY_PUNCTUATION_OR_TOKEN_SPACING_EQUIVALENT: 1`
- `SEMANTIC_OR_UNEXPLAINED_MISMATCH: 2`

The diagnostic did not auto-fix semantic mismatches.

Subsequent authoritative re-research and policy-control memos closed the remaining alias-safety issues before Policy V5 was frozen.

### Outcome Firewall

Manifest builder and audit remained pre-outcome.

Full-history GDELT extraction was not authorized until the final alias gate passed.

Return/outcome fields read:

`0`

### Next Step

Test the final alias policy against direct GDELT coverage and missingness before committing to the full 2021–2025 extraction.

---

## 3.60 Full-Universe GDELT Alias Coverage / Missingness Gate — Stage 3K

### Date

2026-08-25

### Objective

Validate that the production point-in-time alias manifest produces usable direct-GDELT historical attention coverage without modifying the alias policy based on any H3 return relationship.

### Protocol

Documentation:

`docs/h3_stage3k_gdelt_alias_coverage_missingness_protocol.md`

Primary implementation:

- `src/analysis/run_h3_gdelt_alias_coverage_gate.py`
- `src/analysis/audit_h3_gdelt_alias_coverage_gate.py`

### Coverage Outputs

Primary diagnostic outputs included:

- `h3_gdelt_stage3k_source_files.csv`
- `h3_gdelt_stage3k_daily_security_attention.csv`
- `h3_gdelt_stage3k_window_security_coverage.csv`
- `h3_gdelt_stage3k_window_summary.csv`
- `h3_gdelt_stage3k_security_coverage_summary.csv`

The gate reused frozen historical anchor windows rather than immediately downloading the full study interval.

Stage 3K source files:

`35`

Stage 3K daily security-attention rows:

`17,626`

The coverage layer retained point-in-time active aliases and issuer metadata and checked for duplicate security-date records and invalid attention denominators.

### Decision

The final alias policy was considered operationally usable for full direct-GDELT historical extraction.

No alias was widened because of a future return result.

H3 return/outcome inference remained unauthorized.

### Next Step

Run the complete 2021–2025 direct GDELT extraction under a frozen extraction protocol and audit the resulting daily/monthly attention layer before preregistration.

---

## 3.61 Full 2021–2025 GDELT Attention Extraction and Source-Gap Reconciliation — Stage 3L

### Date

2026-08-25 to 2026-08-26

### Objective

Construct the full historical H3 news-attention layer from direct GDELT GKG 1.0 archives while preserving source provenance, point-in-time aliases, and explicit missing-source treatment.

### Frozen Extraction Protocol

Primary protocol:

`data/reference/h3/h3_full_gdelt_attention_extraction_v1.json`

Documentation:

- `docs/h3_stage3l_full_gdelt_attention_protocol.md`
- `docs/h3_stage3l_v2_resilient_source_acquisition.md`
- `docs/h3_stage3l_v3_source_gap_reconciliation.md`
- `docs/h3_stage3l_v4_transition_month_aggregation_fix.md`
- `docs/h3_stage3l_v5_fail_closed_month_eligibility.md`

Primary extraction:

- `src/analysis/run_h3_full_gdelt_attention_extraction.py`
- `src/analysis/audit_h3_full_gdelt_attention_extraction.py`

### Attention Definition

For each point-in-time active security/name state and GDELT source day:

`attention_share = matched_source_document_weight / total_source_document_weight`

GDELT GKG `NUMARTS` is used as document weight.

True source-observed zero matches remain zero.

Missing source days are not treated as zero-attention days.

### Full Extraction Outputs

The extraction produced yearly daily shards for:

- 2021
- 2022
- 2023
- 2024
- 2025

Full calendar source-file ledger:

`1,826` calendar dates

Full monthly security-attention rows:

`30,301`

Monthly range:

`2021-01 through 2025-12`

The full source-gap ledger identified:

`21` documented source-gap days

rather than silently converting failed/unavailable archives into zero attention.

### Source-Gap Reconciliation

Primary implementation:

- `src/analysis/reconcile_h3_gdelt_source_gaps.py`
- `src/analysis/finalize_h3_gdelt_source_gap_reconciliation.py`
- `src/analysis/audit_h3_gdelt_source_gap_reconciliation.py`

Frozen policy:

`H3_GDELT_SOURCE_GAP_HANDLING_V1`

The source-gap reconciliation preserved the observed data and attached explicit eligibility controls rather than backfilling missing GKG1 days from future information.

### Transition-Month Aggregation Correction

A transition-month diagnostic exposed the need to aggregate point-in-time name/security states without treating legitimate within-month security/name transitions as duplicate issuer exposure.

The extraction/reconciliation logic was corrected before H3 statistical outcomes were read.

This later became important again in the V1→V2 preregistration amendment at issuer level.

### Outcome Firewall

Stage 3L outputs contain no return, momentum, Winner, commonality-factor, or outcome fields.

The no-outcome attention acquisition layer was closed before statistical H3 specification was finalized.

### Next Step

Freeze a fail-closed month-eligibility rule based only on source coverage, then preregister the H3 predictor, outcomes, models, inference, and robustness rules.

---

## 3.62 Fail-Closed GDELT Month Eligibility and June 2025 Exclusion

### Date

2026-08-26

### Objective

Prevent materially incomplete GDELT months from entering primary H3 inference while keeping source-coverage decisions independent of H3 outcomes.

### Frozen Policy

Reference:

`data/reference/h3/h3_gdelt_fail_closed_month_eligibility_v1.json`

Implementation:

- `src/analysis/apply_h3_gdelt_fail_closed_month_eligibility.py`
- `src/analysis/audit_h3_gdelt_fail_closed_month_eligibility.py`

Primary monthly controls:

- `h3_gdelt_primary_month_eligibility.csv`
- `h3_gdelt_primary_excluded_months.csv`
- `h3_gdelt_primary_monthly_security_attention.csv`

### Coverage Rule

Primary GKG1 month eligibility requires the frozen source-coverage threshold to be satisfied before any attention/outcome join.

Frozen minimum source coverage:

`90%`

Any month with:

`primary_attention_eligible_flag = 0`

is excluded from every primary H3 specification.

Attention is not imputed for an excluded month.

### June 2025

June 2025 contained:

- calendar days: `30`
- valid source days: `13`
- documented GKG1 source-gap days: `17`
- source coverage: approximately `43.3%`

The month was therefore marked:

`global_primary_attention_eligible_flag = 0`

with exclusion reason:

`GLOBAL_GKG1_SOURCE_COVERAGE_BELOW_FROZEN_90PCT`

June 2025 is the only excluded primary attention month in the 2021-01 through 2025-12 eligibility table.

The monthly security-attention values for June still exist as provenance; they are simply not authorized for primary H3 inference.

### Important Timing Distinction

The H3 predictor interval is:

`2021-01 through 2025-11`

December 2025 is not a predictor month because attention measured in December 2025 would require a January 2026 outcome outside the frozen project outcome sample.

Therefore:

- calendar months in predictor interval: `59`
- source-coverage exclusions inside predictor interval: `1`
- excluded predictor month: `2025-06`
- authorized predictor months: `58`

### Diagnostic Correction

A later outcome-blind diagnostic initially assumed that every calendar month from 2021-01 through 2025-11 had to appear in the frozen predictor panel.

That diagnostic correctly identified June 2025 as absent but incorrectly treated the absence as a construction failure.

A dedicated source-only trace then proved that June's absence was the intended consequence of the already frozen 90% coverage gate.

The diagnostic itself was corrected to compare the predictor month set against the **frozen eligible-month set**, not against the unconditional calendar set.

This did not change the H3 preregistration, predictor, source-gap policy, or month eligibility.

### Final Gate

The corrected eligible-month audit confirmed:

- 59 calendar months in the frozen predictor interval
- exactly one preregistered fail-closed exclusion
- June 2025 exclusion reason reproduced exactly
- 58 authorized predictor months
- no outcome/return data read

Result:

`H3_FROZEN_ELIGIBLE_MONTH_SET_GATE_PASSED`

and:

`H3_OUTCOME_JOIN_AUTHORIZED_BY_MONTH_SET_GATE`

---

## 3.63 H3 Statistical Preregistration, V1→V2 Issuer-Day Amendment, and Frozen Predictor

### Date

2026-08-26

### Objective

Freeze the H3 statistical design and attention transformation before allowing attention to touch return, momentum, Winner, or other outcome data.

### Preregistration Files

- `data/reference/h3/h3_statistical_preregistration_v1.json`
- `data/reference/h3/h3_statistical_preregistration_v2.json`
- `docs/h3_statistical_preregistration_v1.md`
- `docs/h3_statistical_preregistration_v2.md`
- `docs/h3_preregistration_v1_to_v2_amendment_memo.md`

Current authoritative preregistration:

`H3_STATISTICAL_PREREGISTRATION_V2`

Version:

`2026-08-26-v2`

### Frozen Timing

Predictor:

`attention measured over calendar month t`

Outcome:

`one-month-ahead outcome over t to t+1 / ranking month t+1 as applicable`

Lookahead:

`false`

Predictor month interval:

`2021-01 through 2025-11`

Undercovered attention months are excluded before any H3 outcome data are read.

### Primary Attention Predictor

Issuer identity:

- SEC CIK when nonblank
- deterministic `SECURITY::<security_key>` fallback otherwise

Unit before security mapping:

`issuer-month constructed from deduplicated issuer-days`

Raw issuer-month attention:

`sum(unique issuer-day matched NUMARTS) / sum(unique issuer-day total NUMARTS)`

Log transform:

`ln(1 + 1,000,000 × issuer_attention_share)`

Primary standardization:

Within each eligible predictor month, calculate the mean and sample standard deviation across unique eligible issuers and set:

`attention_z = (attention_log - monthly issuer mean) / monthly issuer sample SD`

Winsorization:

`NO`

True zero attention:

`retained exactly`

Missing attention imputation:

`NO`

The frozen issuer-month value is then mapped back to each eligible security row for that issuer.

### Prespecified Robustness Predictor Transforms

R1:

issuer-month empirical midrank percentile of raw issuer attention.

R2:

unstandardized issuer `attention_log` with the same fixed effects.

Robustness cannot upgrade a failed primary hypothesis to supported.

### H3A

Label:

`Attention predicts next-month sector-relative return`

Model:

`sector_relative_return_i,t+1 = security_FE_i + outcome_month_FE_t+1 + current_momentum_decile_FE_t + beta_A * attention_z_i,t + error`

Primary estimand:

`beta_A`

Expected sign:

`positive`

Sector-relative outcome:

security one-month forward return minus the equal-weight mean forward return of all **other** valid securities in the same PIT GICS sector at predictor month `t`.

Minimum other same-sector peers:

`5`

### H3B

Label:

`Attention predicts next-month Winner entry`

Risk set:

securities that are not D10 at month `t` and have a valid corrected H1 momentum assignment at `t+1`.

Winner-entry outcome:

`1` if corrected H1 momentum decile is D10 at `t+1`, otherwise `0`.

Model type:

`Linear probability model`

Model:

`winner_entry_i,t+1 = security_FE_i + outcome_month_FE_t+1 + current_momentum_decile_FE_t (D01-D09) + beta_B * attention_z_i,t + error`

Primary estimand:

`beta_B`

Expected sign:

`positive`

### H3C

Label:

`Attention has an incremental effect for current Winners`

Current Winner:

corrected H1 D10 at predictor month `t`.

Model:

`sector_relative_return_i,t+1 = security_FE_i + outcome_month_FE_t+1 + current_momentum_decile_FE_t + beta_C * attention_z_i,t + theta * (attention_z_i,t * current_winner_i,t) + error`

Primary estimand:

`theta`

Expected sign:

`positive`

Prespecified secondary linear combination:

`beta_C + theta`

This Winner attention slope is descriptive secondary inference and is not part of the Holm family.

### Fixed Effects and Primary Inference

Frozen fixed effects:

- security FE: `YES`
- outcome-month FE: `YES`
- current momentum-decile FE: `YES`
- sector FE: `NO`
- post-hoc controls: `NOT ALLOWED`

Primary covariance:

`Two-way cluster-robust covariance by issuer_id and outcome_month`

Small-sample correction:

`YES`

Reference degrees of freedom:

`min(number of issuer clusters, number of outcome-month clusters) - 1`

Tests:

`two-sided`

HAC lag-3 is not the primary H3 covariance estimator because H3 is a security-month panel rather than a portfolio time series.

### Multiple Testing

Frozen Holm family:

1. `H3A_beta_A`
2. `H3B_beta_B`
3. `H3C_theta`

Method:

`Holm-Bonferroni`

Familywise alpha:

`0.05`

Component support requires both:

- Holm-adjusted two-sided p-value `< 0.05`
- preregistered positive coefficient sign

A significant negative coefficient is labeled:

`CONTRADICTED`

Otherwise:

`NOT SUPPORTED`

There is no post-hoc global H3 binary decision.

### V1→V2 Issuer-Day Amendment

The V1 predictor preparation incorrectly required security-month attention rows sharing one issuer CIK to be identical.

That rule fails for a valid issuer whose security/name/ticker state changes inside a month because the separate security rows can cover different active-day subsets.

Trigger case:

- month: `2022-04`
- issuer CIK: `0001437107`
- security identities: `DISCA`, `DISCK`, `WBD`

Observed V1 security-month attention range:

- minimum: `0.0001412389797165`
- maximum: `0.0001660893085939`

The V2 amendment implemented the already intended issuer-level unit:

1. verify same-issuer attention consistency on each calendar day;
2. deduplicate to exactly one issuer-date;
3. aggregate unique issuer-days to one issuer-month;
4. standardize across unique issuers;
5. map the issuer-month predictor back to eligible security rows.

The amendment changed:

- predictor aggregation implementation: `YES`

The amendment did **not** change:

- H3 models
- inference
- multiple-testing family
- source-gap policy
- timing
- outcomes

Outcomes read before amendment:

`NO`

### V2 Integrity Audit

Script:

`src/analysis/audit_h3_statistical_preregistration.py`

Final result:

- checks passed: `19`
- checks failed: `0`
- predictor months: `58`
- predictor security-month rows: `29,287`
- issuer-day rows: `887,018`
- issuer-month rows: `29,078`
- unique issuer clusters: `583`

Key validations included:

- zero unresolved same-issuer daily attention disagreements;
- exact issuer-day uniqueness;
- exact issuer-month uniqueness;
- issuer-month reaggregation from unique issuer-days;
- exact frozen `log1p` transform;
- monthly `attention_z` mean zero;
- monthly `attention_z` sample SD one;
- at least 100 eligible issuers in every predictor month;
- identical mapped issuer values across an issuer's eligible security identities;
- no return/momentum/Winner/outcome fields in predictor outputs;
- unchanged issuer × outcome-month primary clustering;
- unchanged H3A/H3B/H3C Holm family;
- outcome firewall preserved through the V2 amendment.

Final token:

`H3_STATISTICAL_PREREGISTRATION_V2_INTEGRITY_AUDIT_PASSED`

### Decision

The corrected issuer-level H3 attention predictor was frozen before outcome exposure.

The deterministic attention/outcome join was authorized only after the V2 preregistration audit and the frozen eligible-month gate both passed.

---

## 3.64 H3 Predictor-to-Outcome Join and Structural Integrity Gate

### Date

2026-08-26

### Objective

Construct the exact preregistered H3 analytical panel using the already frozen attention predictor and the validated Azure SQL H1/GICS layers, then independently block model execution unless every structural alignment check passes.

### SQL Binding Discovery

Before reading outcome rows, schema-only discovery confirmed the existing Azure SQL objects required by the frozen H3 specification.

Primary SQL sources selected:

- `analytics.v_security_monthly_forward_return_1m`
- `analytics.security_month_end_gics_sector`
- `analytics.v_security_monthly_momentum_ranking`

The discovery stage queried SQL catalog metadata only and executed no regression/inference.

### Join Implementation

Script:

`src/analysis/build_and_audit_h3_preregistered_predictor_outcome_join.py`

Frozen attention input:

`reports/exploratory/h3_attention_feasibility/h3_preregistered_attention_predictor_panel.csv`

Frozen predictor population:

- rows: `29,287`
- eligible months: `58`
- issuer clusters: `583`

### H3A / H3C Outcome Construction

The corrected H1 one-month gross security forward-return layer is reused directly.

No alternative price source is introduced.

For each predictor security-month, PIT GICS sector is attached for month `t`.

The leave-one-out sector benchmark is calculated from **all other valid securities in that same PIT sector**, not merely securities that possess an H3 attention observation.

A row is H3A/H3C eligible only when:

- one-month forward return is complete;
- PIT sector exists;
- current corrected H1 momentum decile is valid;
- at least `5` other same-sector valid forward returns exist;
- the leave-one-out sector-relative return is valid.

### H3B Outcome Construction

Current D10 rows are removed from the H3B risk set.

Among current D01-D09 securities with a valid `t+1` corrected H1 momentum assignment:

`winner_entry = 1`

when the next-month decile is D10, otherwise:

`winner_entry = 0`

### Timing Control

Every joined row must satisfy:

`outcome_month = predictor_month + 1`

Because June 2025 attention is frozen ineligible, no July 2025 H3 outcome observation is permitted.

### Join Audit Result

Passed checks:

`26`

Failed checks:

`0`

Final population:

- joined predictor rows: `29,287`
- H3A/H3C eligible rows: `29,114`
- H3B eligible rows: `26,139`
- H3B positive Winner-entry events: `807`

The audit also confirmed:

- predictor row count preserved exactly;
- unique predictor-month/security keys;
- unique canonical current-return source keys;
- unique next-month momentum source keys;
- exact `t+1` timing;
- exact PIT GICS month alignment;
- minimum model-row thresholds satisfied;
- minimum issuer-cluster thresholds satisfied;
- minimum outcome-month-cluster thresholds satisfied;
- H3A/H3C peer minimum satisfied;
- H3B risk set limited to D01-D09;
- H3B next-month assignment valid;
- Winner entry binary;
- current-Winner indicator exactly reproduces corrected H1 D10.

### Materialized Outputs

CSV analytical panel:

`reports/confirmatory/h3/h3_preregistered_predictor_outcome_panel.csv`

Audit:

`reports/confirmatory/h3/h3_preregistered_predictor_outcome_join_audit.txt`

Manifest/checksum record:

`reports/confirmatory/h3/h3_preregistered_predictor_outcome_join_manifest.json`

Azure SQL analytical table:

`analytics.h3_preregistered_predictor_outcome_panel`

Final tokens:

`H3_PREREGISTERED_PREDICTOR_OUTCOME_JOIN_INTEGRITY_AUDIT_PASSED`

and:

`H3_PRIMARY_MODEL_EXECUTION_AUTHORIZED`

Regression/inference executed by the join script:

`NO`

### Decision

The structural H3 analytical population is frozen and valid.

The project has crossed the outcome-join boundary, but the actual H3 coefficients and p-values have still not been observed.

---

## 3.65 H3 Primary Confirmatory Inference Code Freeze — Pre-Execution Checkpoint

### Date

2026-08-26

### Objective

Freeze the exact code that will execute H3A, H3B, and H3C before the first confirmatory H3 coefficients or p-values are observed.

### Script

`src/analysis/run_h3_primary_confirmatory_inference.py`

Script version:

`2026-08-26-v1-h3-primary-confirmatory-inference`

### Frozen Input Expectations

The inference code refuses to run unless the preceding join artifacts and authorization tokens are present and unchanged.

Expected analytical panel:

- rows: `29,287`
- predictor months: `58`
- issuer clusters: `583`
- H3A/H3C rows: `29,114`
- H3B rows: `26,139`
- H3B positive Winner-entry events: `807`

The script validates the joined-panel checksum against the passed join manifest before model execution.

### Frozen Models

Only the three prespecified primary models are executed:

- H3A `beta_A`
- H3B `beta_B`
- H3C interaction `theta`

No post-hoc controls are permitted.

Primary fixed effects and covariance remain exactly those in `H3_STATISTICAL_PREREGISTRATION_V2`.

Holm adjustment is applied across exactly:

`H3A_beta_A`, `H3B_beta_B`, `H3C_theta`

The prespecified H3C Winner attention slope:

`beta_C + theta`

is reported only as secondary inference and is not added to the Holm family.

### Intended Result Artifacts

After execution, the script is designed to create:

- `reports/confirmatory/h3/h3_primary_confirmatory_results.csv`
- `reports/confirmatory/h3/h3_primary_confirmatory_report.txt`
- `reports/confirmatory/h3/h3_primary_confirmatory_manifest.json`

and SQL table:

`analytics.h3_primary_confirmatory_results`

### Current State

At this checkpoint:

`PRIMARY H3 CONFIRMATORY INFERENCE HAS NOT BEEN RUN`

No H3 coefficient, confidence interval, p-value, Holm-adjusted p-value, or support decision has been observed.

This is the final provenance boundary before confirmatory inference.

### Required Git Boundary

Commit the completed H3 source/identity/attention/preregistration/join work and this updated project log.

Then commit the frozen primary inference script before executing it.

The first H3 confirmatory result must be observed only after those code/specification checkpoints exist in Git history.

---

---

## 3.66 H3 Primary Confirmatory Inference — Frozen Preregistered Results

### Date

2026-08-26

### Objective

Execute the first confirmatory H3 inference exactly as frozen in:

`H3_STATISTICAL_PREREGISTRATION_V2`

after the prerequisite attention-predictor, eligible-month, predictor-to-outcome join, and pre-model structural gates had passed.

No H3 coefficient, confidence interval, p-value, or support decision had been observed before this run.

### Primary Inference Script

`src/analysis/run_h3_primary_confirmatory_inference.py`

Initial frozen version:

`2026-08-26-v1-h3-primary-confirmatory-inference`

Executed version:

`2026-08-26-v2-h3-primary-confirmatory-inference-pre-model-gate-fix`

### Pre-Model Gate Correction Before First Result Exposure

The first execution attempt failed before model estimation because the Python environment did not yet contain:

`statsmodels`

The dependency was added to the project environment and requirements without changing the inference specification.

A subsequent V1 execution reached the structural revalidation gate and stopped before regression because the script required every one of the 29,287 frozen predictor rows to match the current H1 layer.

That assertion was stricter than the frozen preregistration.

The preregistered missingness rules require only that rows entering a given primary model possess the inputs required by that model.

Therefore the pre-model gate was corrected so that:

- every H3A/H3C eligible row must match the required current H1 layer;
- every H3B eligible row must match the required current H1 layer;
- every H3B eligible row must match the required `t+1` momentum-assignment layer;
- predictor rows lacking the current H1 join must be excluded from all primary H3 model samples;
- predictor rows lacking the `t+1` momentum join must be excluded from H3B.

The correction changed only the software validation gate.

It did **not** change:

- H3A, H3B, or H3C model formulas;
- the frozen attention predictor;
- the outcome definitions;
- sample/missingness rules;
- fixed effects;
- cluster structure;
- reference degrees-of-freedom rule;
- Holm family;
- familywise alpha;
- expected coefficient signs.

Both failed attempts stopped before any H3 regression coefficient or p-value was produced.

The V2 gate correction was committed before the first successful confirmatory run.

### Frozen Input Checksums

Preregistration SHA-256:

`95e88d99f2b0c9beca50073844b9dadc32c11a6aa820fe04cf3ed12e94841506`

Joined analytical-panel SHA-256:

`8ad29c02180efb9b2cc46ef640699a4c7e339cbd45ac7d1a9ab869d1c979729c`

### Primary Inference Convention

Primary covariance:

`two-way cluster-robust covariance by issuer_id and outcome_month`

Small-sample correction:

`TRUE`

Reference degrees of freedom:

`min(issuer clusters, outcome-month clusters) - 1`

Tests:

`two-sided`

Frozen Holm family:

1. `H3A_beta_A`
2. `H3B_beta_B`
3. `H3C_theta`

Familywise alpha:

`0.05`

A component is supported only when:

- its Holm-adjusted two-sided p-value is below `0.05`; and
- its coefficient has the preregistered positive sign.

A statistically significant negative coefficient would be classified:

`CONTRADICTED`

Otherwise the component is:

`NOT SUPPORTED`

### H3A — Attention Predicts Next-Month Sector-Relative Return

Primary estimand:

`beta_A on attention_z`

Sample:

- rows: `29,114`
- issuer clusters: `573`
- outcome-month clusters: `58`
- reference df: `57`

Result:

- coefficient: `-0.00195918387663`
- economic effect: `-0.19591839 percentage points` per +1 SD issuer attention
- two-way clustered SE: `0.00212623687722`
- 95% CI: `[-0.00621689978153, 0.00229853202827]`
- t statistic: `-0.92143255`
- raw two-sided p-value: `0.360708306955`
- Holm-adjusted p-value: `0.360708306955`

Decision:

`NOT SUPPORTED`

### H3A Interpretation

The point estimate is opposite the preregistered positive sign and statistically indistinguishable from zero.

The primary H3A result therefore provides no confirmatory evidence that higher issuer attention predicts higher next-month leave-one-out sector-relative return.

---

### H3B — Attention Predicts Next-Month Winner Entry

Primary estimand:

`beta_B on attention_z`

Sample:

- rows: `26,139`
- issuer clusters: `567`
- outcome-month clusters: `58`
- reference df: `57`

Positive Winner-entry events:

`807`

Result:

- coefficient: `0.00713020049062`
- economic effect: `+0.71302005 percentage points` in next-month D10-entry probability per +1 SD issuer attention
- two-way clustered SE: `0.00347612000556`
- 95% CI: `[0.000169390247139, 0.0140910107341]`
- t statistic: `2.05119515`
- raw two-sided p-value: `0.0448539853732`
- Holm-adjusted p-value: `0.13456195612`

Decision:

`NOT SUPPORTED`

### H3B Interpretation

H3B is the only primary component with:

- the preregistered positive sign; and
- an unadjusted two-sided p-value below `0.05`.

However, H3B belongs to the frozen three-test Holm family.

After the required Holm-Bonferroni adjustment:

`Holm p = 0.13456195612`

which exceeds the familywise alpha of `0.05`.

Therefore the positive H3B estimate is a:

`NOMINAL / UNADJUSTED POSITIVE SIGNAL`

but it is **not confirmatory support**.

The raw p-value must not replace the preregistered Holm-adjusted decision rule.

---

### H3C — Incremental Attention Effect for Current Winners

Primary estimand:

`theta on attention_z × current_winner`

Sample:

- rows: `29,114`
- issuer clusters: `573`
- outcome-month clusters: `58`
- reference df: `57`

Result:

- interaction coefficient: `-0.00287813829612`
- economic effect: `-0.28781383 percentage points` incremental next-month sector-relative return per +1 SD attention for current Winners
- two-way clustered SE: `0.00192537935189`
- 95% CI: `[-0.00673364394433, 0.000977367352076]`
- t statistic: `-1.49484219`
- raw two-sided p-value: `0.140471654115`
- Holm-adjusted p-value: `0.280943308231`

Decision:

`NOT SUPPORTED`

### H3C Interpretation

The interaction estimate is negative, opposite the preregistered positive sign, and statistically indistinguishable from zero.

The primary H3C result therefore provides no confirmatory evidence that current Winners receive an additional positive return effect from higher issuer attention.

---

### H3C Prespecified Secondary Winner-Attention Slope

Secondary linear combination:

`beta_C + theta`

This quantity was preregistered as descriptive secondary inference and is not part of the Holm family.

Result:

- estimate: `-0.00456932295679`
- economic effect: `-0.45693230 percentage points`
- two-way clustered SE: `0.00303325163356`
- 95% CI: `[-0.0106433045823, 0.00150465866875]`
- t statistic: `-1.50641078`
- reference df: `57`
- raw two-sided p-value: `0.137484018992`

Interpretation:

The estimated total attention slope among current Winners is negative and statistically indistinguishable from zero.

Because this is secondary inference, it cannot alter the H3C primary decision.

### Primary Confirmatory Decision

Frozen component decisions:

- H3A: `NOT SUPPORTED`
- H3B: `NOT SUPPORTED`
- H3C: `NOT SUPPORTED`

The preregistration explicitly does not define a post-hoc global H3 binary decision.

Accordingly, the correct primary conclusion is:

**None of the three preregistered H3 confirmatory components is supported in the primary analysis.**

H3B exhibits a positive nominal association with next-month Winner entry before multiple-testing correction, but the association does not survive the frozen Holm adjustment and therefore cannot be reported as confirmatory support.

H3A and H3C both have point estimates opposite their preregistered positive directions.

### Result Artifacts

Primary results:

`reports/confirmatory/h3/h3_primary_confirmatory_results.csv`

Primary report:

`reports/confirmatory/h3/h3_primary_confirmatory_report.txt`

Primary manifest:

`reports/confirmatory/h3/h3_primary_confirmatory_manifest.json`

Azure SQL result table:

`analytics.h3_primary_confirmatory_results`

Final execution token:

`H3_PRIMARY_CONFIRMATORY_INFERENCE_COMPLETE`

### Interpretation Boundary

The primary H3 confirmatory analysis is now historically frozen.

The following are prohibited:

- dropping H3A or H3C from the Holm family because their results were unfavorable;
- treating H3B's raw p-value as the confirmatory decision;
- replacing `attention_z` with a robustness transform because the primary result was not supported;
- changing the June 2025 exclusion;
- changing fixed effects or cluster structure based on these results;
- adding post-hoc controls and relabeling them as primary;
- redefining Winner entry or sector-relative return;
- changing the sample window after observing the primary results.

### Prespecified Robustness Still Pending

The primary inference script did not execute robustness analyses.

The remaining preregistered robustness work includes:

1. R1 issuer-month empirical midrank percentile attention;
2. R2 unstandardized issuer `attention_log`;
3. exclusion of HIGH structural-ambiguity alias rows;
4. exclusion of PIT alias-transition months;
5. leave-one-sector-out coefficient stability for H3A and H3C;
6. permitted covariance robustness such as issuer-only and month-only clustering, clearly labeled as robustness.

These tests may characterize sensitivity and stability.

They cannot upgrade a failed primary H3 component to `SUPPORTED`.

### Result

H3 primary confirmatory inference is complete.

Current primary evidence:

- H3A: not supported;
- H3B: positive nominal association, but not supported after Holm adjustment;
- H3C: not supported;
- secondary Winner attention slope: negative and statistically indistinguishable from zero.

### Next Step

Commit the H3 primary result artifacts and this project-log checkpoint.

After that commit, execute the already prespecified H3 robustness suite without changing the frozen primary interpretation.

---

---

## 3.67 H4 Intraday Price-Location and Market-Structure Research Design — Pre-Outcome Freeze

### Date

2026-08-26

### Objective

Open a new research branch after the H1, H2, and H3 primary analyses without retuning any completed hypothesis.

H4 shifts the project from monthly cross-sectional return prediction toward short-horizon intraday market structure.

The central design principle is:

**location first, trigger second, outcome last.**

Support/resistance, liquidity, volume, and volatility are used to define where analysis should occur.

ICT-style structures are then treated as objectively coded event triggers inside those pre-existing states rather than as discretionary chart labels.

### Primary Instrument

Initial H4 instrument:

`SPY`

The first intraday experiment is intentionally restricted to one highly liquid investable S&P 500 proxy.

This reduces:

- cross-sectional identity complexity;
- data volume;
- multiple-testing burden;
- event-definition ambiguity.

The full S&P 500 security universe is not included in the first H4 experiment.

### Primary Data Frequency

Required raw data:

`1-minute consolidated U.S. equity bars`

Primary analytical frequency:

`5-minute bars`

Primary session:

`regular U.S. equity trading hours only`

Premarket and after-hours observations are excluded from the initial primary test.

### Consolidated-Market Source Requirement

A single-exchange feed is not acceptable for the primary H4 volume/liquidity analysis.

The source must provide consolidated U.S. market coverage.

Candidate primary route:

`Massive / Polygon U.S. Stocks aggregate bars`

The source must pass a historical coverage and structural feasibility gate before full acquisition.

Free IEX-only historical data is not authorized as the primary H4 source because its volume is not consolidated U.S. market volume.

### Primary Location Engine

The first confirmatory H4 location layer uses only price levels known before the current session:

Resistance:

- previous-day high (`PDH`);
- previous-week high (`PWH`);
- previous-month high (`PMH`).

Support:

- previous-day low (`PDL`);
- previous-week low (`PWL`);
- previous-month low (`PML`).

No hand-drawn or outcome-informed support/resistance level is permitted.

### Volatility-Normalized Zones

Daily volatility normalizer:

`prior-day ATR(14)`

Zone half-width:

`0.10 × prior-day ATR(14)`

Each historical level is therefore treated as a zone rather than an infinitely precise price line.

Same-direction overlapping zones are merged.

Merged zones retain their contributing level families so confluence can be measured without double-counting one price interaction.

### Primary H4 Trigger

The first ICT-style trigger is limited to:

`same-bar liquidity sweep / rejection`

Bearish resistance sweep:

- 5-minute high exceeds resistance level by at least `0.02 × ATR(14)`;
- same 5-minute bar closes back below the resistance level.

Bullish support sweep:

- 5-minute low exceeds support level downward by at least `0.02 × ATR(14)`;
- same 5-minute bar closes back above the support level.

Only the first interaction with a merged zone on a session is eligible for the primary H4A event.

Later revisits of the same zone cannot become additional primary events.

### Primary H4 Outcome

Primary forward horizon:

`30 minutes`

Signed-return convention:

- bullish support sweep: ordinary forward return;
- bearish resistance sweep: negative of ordinary forward return.

Therefore:

`positive signed return = subsequent movement in the preregistered rejection direction`

The primary test will evaluate whether mean signed 30-minute return after qualifying first-interaction sweep/rejection events is positive.

The exact inference estimator will be frozen after source/event-count feasibility is known and before any H4 forward-return result is inspected.

Same-day event dependence must be accounted for.

### Secondary Horizons

Prespecified descriptive/robustness horizons:

- 15 minutes;
- 60 minutes.

Additional descriptive outcomes may include:

- maximum favorable excursion;
- maximum adverse excursion;
- directional success rate;
- results by support versus resistance;
- results by day/week/month level family;
- confluence versus single-source zones.

These cannot replace the 30-minute primary outcome.

### Price-Discovery / No-Prior-Resistance Branch

Historical resistance is never fabricated above price.

When SPY is above every historical completed-session high available before the observation, the state is classified:

`PRICE DISCOVERY / NO PRIOR OVERHEAD RESISTANCE`

The separate price-discovery context will use deterministic variables such as:

- ATR-normalized extension above prior all-time high;
- ATR-normalized distance from session VWAP;
- time-of-day-adjusted relative volume;
- opening-range extension;
- rolling intraday realized volatility;
- recent displacement.

These variables are context features only at this checkpoint.

The price-discovery branch requires a separate frozen inference specification before predictive testing.

### Relative Volume

Primary relative-volume context:

`current 5-minute volume / median same-time-bucket volume across prior 20 valid sessions`

Elevated-volume diagnostic:

`RVOL >= 1.50`

Raw volume is not treated as order flow.

True order-flow or order-book imbalance would require trade/quote or depth data and a separate methodology.

### VWAP

If reliable trade-based minute VWAP is available from the approved source, session VWAP is accumulated using only observations available through the current time.

No future bar may enter VWAP.

If trade-based VWAP is unavailable, the project will not silently substitute a typical-price approximation in the primary specification.

### Deferred ICT Structures

The following are deliberately excluded from the first H4 primary test:

- fair value gaps;
- market structure shifts;
- breaks of structure;
- displacement filters;
- order blocks;
- volume-profile nodes;
- anchored VWAP;
- true trade/quote order imbalance;
- Level II/order-book imbalance.

They may be opened later only under separate frozen rules.

This restriction is intended to prevent combinatorial pattern mining.

### H4 Outcome Firewall

Before the H4 event methodology is fully frozen and audited, development scripts may inspect:

- OHLCV structure;
- timestamps;
- session completeness;
- historical levels;
- ATR distributions;
- volume distributions;
- VWAP availability;
- counts of candidate zones;
- counts of qualifying sweep events.

They may not inspect:

- post-trigger returns;
- directional hit rates;
- MFE/MAE;
- performance by alternative thresholds.

No threshold may be selected because it produced superior future returns.

### Files Created

Formal H4 design:

`docs/h4_intraday_market_structure_preregistration_v1.md`

Initial source probe:

`src/analysis/probe_h4_intraday_data_source.py`

Expected reports:

- `reports/data_quality/h4_intraday_source_feasibility.txt`
- `reports/data_quality/h4_intraday_source_feasibility.json`

### Current H4 State

Location hierarchy:

`FROZEN V1`

Primary instrument:

`SPY`

Primary analytical interval:

`5 MINUTES`

Primary location families:

`PDH / PDL / PWH / PWL / PMH / PML`

Primary trigger:

`SAME-BAR LIQUIDITY SWEEP / REJECTION`

Primary forward horizon:

`30 MINUTES`

Price-discovery fallback:

`DEFINED — INFERENCE NOT YET AUTHORIZED`

H4 forward-return results observed:

`NO`

Full intraday acquisition:

`NOT AUTHORIZED`

### Next Step

Run the consolidated-minute source feasibility probe against representative dates from every study year.

The source gate must establish:

- access to 2021–2025 history;
- complete regular-session minute coverage;
- valid OHLC;
- valid consolidated volume;
- unique timestamps;
- deterministic Eastern-time conversion;
- availability status for trade-based VWAP and transaction count.

Only after this gate passes should the full SPY 2021–2025 intraday history be acquired.

---

---

## 3.68 H4 Massive/Polygon Source-Gate Failure and Alpaca SIP Fallback Authorization

### Date

2026-08-26

### Objective

Evaluate the first candidate consolidated intraday source without exposing any H4 forward-return result, then select the next source-feasibility route based only on historical coverage and source structure.

### Massive / Polygon Probe

Script:

`src/analysis/probe_h4_intraday_data_source.py`

Script version:

`2026-08-26-v1-h4-intraday-source-feasibility`

Probe dates:

- `2021-01-04`
- `2022-06-15`
- `2023-10-02`
- `2024-03-15`
- `2025-12-31`

Result:

- 2021: `403 — plan timeframe unavailable`
- 2022: `403 — plan timeframe unavailable`
- 2023: `403 — plan timeframe unavailable`
- 2024-03: `403 — plan timeframe unavailable`
- 2025-12-31: `200`

The accessible 2025 session returned:

- 390 / 390 regular-session minute bars;
- first bar: `09:30 ET`;
- last bar: `15:59 ET`;
- duplicate timestamps: `0`;
- invalid OHLC rows: `0`;
- missing volume rows: `0`;
- nonpositive volume rows: `0`;
- missing provider VWAP rows: `0`;
- missing transaction-count rows: `0`.

Therefore the candidate source structure is suitable for H4, but the current subscription does not expose the complete frozen 2021-2025 study period.

Final gate:

`FAIL / REVIEW REQUIRED`

Full H4 acquisition remained unauthorized.

### Current Massive Plan Constraint

The failure is classified:

`SUBSCRIPTION HISTORY DEPTH — NOT DATA QUALITY`

No H4 threshold, trigger, location rule, or outcome definition changed because of this failure.

### Authorized Fallback Test

Before purchasing a deeper Massive history plan, the project will test:

`Alpaca historical SIP minute bars`

The fallback remains methodologically compatible because the required source properties are:

- consolidated U.S. equity market coverage;
- historical 1-minute OHLCV;
- deterministic timestamps;
- adequate 2021-2025 history.

The fallback is a source-access change only.

H4 forward outcomes remain unread.

Fallback probe:

`src/analysis/probe_h4_alpaca_sip_source.py`

Expected reports:

- `reports/data_quality/h4_alpaca_sip_source_feasibility.txt`
- `reports/data_quality/h4_alpaca_sip_source_feasibility.json`

### Outcome Firewall

H4 post-trigger returns observed:

`NO`

H4 event success rates observed:

`NO`

MFE / MAE observed:

`NO`

Primary H4 thresholds changed:

`NO`

### Next Step

Run the Alpaca SIP historical-minute source gate over representative dates in every study year.

Only if the source passes will full 2021-2025 SPY minute acquisition be authorized.

---

## 3.69 Alpaca SIP Source Gate Passed and Full H4 Minute-History Acquisition Authorization

### Date

2026-08-28

### Objective

Close the intraday source-feasibility stage after the Massive / Polygon plan-depth failure and authorize full SPY 2021–2025 minute-history acquisition using the independently tested Alpaca SIP route.

### Source-Gate Result

Fallback source:

`Alpaca historical SIP stock bars`

Probe:

`src/analysis/probe_h4_alpaca_sip_source.py`

Probe script version:

`2026-08-26-v2-h4-alpaca-sip-source-feasibility`

The five-date source gate covering representative dates in:

- 2021
- 2022
- 2023
- 2024
- 2025

passed.

Because the probe exits successfully only when every sample date has complete ordinary-session coverage, the pass establishes:

- historical SIP access across all five study years;
- complete regular-session 1-minute coverage on the frozen probe dates;
- valid OHLC structure;
- positive/nonmissing volume;
- unique minute timestamps.

The detailed source-gate report and JSON artifact remain the authoritative record for provider VWAP and transaction-count availability.

H4 forward outcomes observed during the source gate:

`NO`

### Source Decision

Primary H4 intraday source:

`ALPACA SIP`

Massive / Polygon remains structurally suitable but is not the selected primary route under the current subscription because its available historical depth did not cover the frozen 2021–2025 study interval.

No H4 location threshold, sweep threshold, forward horizon, or outcome definition changed in response to the source substitution.

### Full Acquisition Design

Full SPY acquisition is now authorized for:

`2021-01-01 through 2025-12-31`

Raw frequency:

`1 minute`

Feed:

`SIP`

Adjustment:

`raw`

Acquisition script:

`src/analysis/download_h4_spy_alpaca_sip_1min_history.py`

The downloader:

- verifies the passed source-gate JSON before continuing;
- downloads Alpaca's official market calendar for the complete study interval;
- downloads SPY bars in restartable monthly blocks;
- follows `next_page_token` pagination;
- retries rate-limit and transient server responses;
- preserves monthly raw provider payloads under the local raw-data tree;
- records SHA-256 checksums and request metadata;
- calculates no ICT trigger or forward-return outcome.

Expected raw directory:

`data/raw/source/intraday/alpaca/spy_1min_sip/`

Acquisition manifest:

`data/interim/h4_spy_alpaca_1min_acquisition_manifest.json`

Acquisition report:

`reports/data_quality/h4_spy_alpaca_1min_acquisition.txt`

### Independent Minute-History Audit

Audit script:

`src/analysis/audit_h4_spy_alpaca_sip_1min_history.py`

The audit reconstructs the exact expected minute grid from the Alpaca market calendar.

This explicitly handles early-close sessions rather than requiring 390 minutes on every trading date.

The audit blocks downstream use unless it confirms:

- all 60 monthly raw files and checksums;
- exact market-calendar reconciliation;
- no missing expected RTH minutes;
- no unexpected RTH minutes;
- no duplicate RTH timestamps;
- valid OHLC relationships;
- positive volume;
- provider VWAP availability state;
- transaction-count availability state.

Only after the audit passes is the canonical RTH-only minute layer materialized:

`data/interim/h4_spy_1min_sip_2021_2025.csv.gz`

Canonical manifest:

`data/interim/h4_spy_1min_sip_standardized_manifest.json`

Audit:

`reports/data_quality/h4_spy_1min_sip_integrity_audit.txt`

Required success tokens:

`H4_SPY_ALPACA_SIP_MINUTE_HISTORY_INTEGRITY_AUDIT_PASSED`

and:

`H4_5MIN_LOCATION_LAYER_CONSTRUCTION_AUTHORIZED`

### Outcome Firewall

During acquisition and the independent raw-history audit:

- support/resistance events calculated: `NO`
- liquidity sweeps calculated: `NO`
- 15/30/60-minute forward returns calculated: `NO`
- directional hit rates calculated: `NO`
- MFE / MAE calculated: `NO`

Therefore the H4 outcome firewall remains intact.

### Decision

Full raw intraday acquisition is authorized.

H4 market-structure event construction remains blocked until the complete 2021–2025 SIP minute-history integrity audit passes.

### Next Step

Run the full acquisition script.

Then run the independent minute-history audit.

Only after both complete successfully should the project derive audited 5-minute bars and deterministic support/resistance location states.

---

---

## 3.69 H4 Full SIP Minute-History Integrity Gate — Nine Isolated Missing Bars

### Date

2026-08-28

### Objective

Independently validate the complete 2021–2025 SPY Alpaca SIP one-minute history before constructing any H4 market-structure event or forward outcome.

### Audit

Script:

`src/analysis/audit_h4_spy_alpaca_sip_1min_history.py`

Script version:

`2026-08-28-v1-h4-alpaca-sip-minute-integrity-audit`

### Population

Official Alpaca market-calendar sessions:

`1,255`

Early-close sessions:

`10`

Expected regular-session minutes:

`487,650`

Observed unique regular-session minutes:

`487,641`

Raw provider bars:

`1,025,947`

Regular-session provider bars examined:

`487,641`

### Structural Validation

Unexpected RTH minutes:

`0`

Duplicate RTH timestamps:

`0`

Invalid OHLC rows:

`0`

Invalid/nonpositive volume rows:

`0`

Missing provider VWAP rows:

`0`

Missing/invalid transaction-count rows:

`0`

### Missing-Minute Result

Exactly:

`9`

expected regular-session minute bars were absent.

Missing intervals:

`2021-05-05 11:27 through 11:31 ET`

and:

`2023-06-05 09:52 through 09:55 ET`

No H4 event trigger or forward outcome was calculated.

Final minute-history quality gate:

`FAIL`

### Interpretation

The missing population represents approximately:

`9 / 487,650 ≈ 0.00185%`

of expected regular-session minutes.

Because SPY is an extremely liquid security and the gaps occur in two short contiguous clusters, the project does not assume that these are genuine no-trade intervals.

The audit remains fail-closed.

No synthetic carry-forward, interpolation, zero-volume bar, or silent deletion is permitted.

### Same-Provider Resolution Path

Alpaca documents that stock minute bars are aggregated from underlying SIP trades and that trade conditions determine whether individual trades update bar price fields and/or volume.

Therefore the next authorized diagnostic queries the underlying Alpaca historical SIP trades for each missing minute.

Diagnostic:

`src/analysis/diagnose_h4_alpaca_missing_minutes_with_sip_trades.py`

Expected outputs:

- `reports/data_quality/h4_spy_alpaca_missing_minute_trade_diagnostic.txt`
- `reports/data_quality/h4_spy_alpaca_missing_minute_trade_diagnostic.json`

If all nine intervals contain underlying SIP trades, the gaps may be treated as provider minute-aggregate omissions and a same-provider reconstruction may be designed using Alpaca's published aggregation-condition rules.

If any interval lacks underlying SIP trades, no reconstruction is authorized from this diagnostic.

### Outcome Firewall

Support/resistance events calculated:

`NO`

Liquidity sweeps calculated:

`NO`

Forward returns calculated:

`NO`

Hit rates calculated:

`NO`

MFE / MAE calculated:

`NO`

H4 thresholds changed:

`NO`

### Next Step

Run the underlying SIP-trade diagnostic for the nine missing minute intervals.

Do not alter or bypass the failed raw minute-history gate before the diagnostic is reviewed.

---

## 3.70 H4 Intraday Data-Exception Policy — Two Infrastructure Sessions Excluded

### Date

2026-08-28

### Decision

Freeze two whole-session exclusions before constructing any H4 event or forward outcome.

Excluded sessions:

- `2021-05-05`
- `2023-06-05`

Classification:

`DOCUMENTED MARKET-DATA INFRASTRUCTURE EXCEPTIONS`

### Evidence

The first H4 full-history integrity audit found exactly nine missing regular-session SPY minute bars:

- `2021-05-05 11:27–11:31 ET`
- `2023-06-05 09:52–09:55 ET`

The subsequent same-provider Alpaca SIP trade diagnostic returned:

- missing intervals with at least one underlying SIP trade: `0 / 9`
- total underlying SIP trades returned: `0`
- total reported share size returned: `0`

Therefore same-provider minute-bar reconstruction is not authorized.

Contemporaneous infrastructure evidence indicates that the two missing clusters align with documented market-data/venue technology incidents rather than an ordinary no-trade state in SPY.

### Frozen Policy

The project will:

- preserve all raw Alpaca files unchanged;
- not synthesize the nine missing bars;
- not interpolate;
- not carry prices forward;
- not insert zero-volume observations;
- not mix an alternate provider into those nine minutes;
- exclude the entire affected sessions from H4 primary and robustness intraday event/outcome analysis.

The whole-session exclusion is deliberately more conservative than excluding only the missing intervals.

### Frozen Exception File

`data/reference/h4/h4_intraday_data_exceptions_v1.json`

The file contains the exact two excluded dates and explicitly prohibits reconstruction.

### Revised Integrity Gate

Script:

`src/analysis/audit_h4_spy_alpaca_sip_1min_history_v2.py`

The revised gate is allowed to pass only if:

1. the current raw-data missing population remains exactly the same frozen nine minutes;
2. every missing minute belongs to one of the two frozen exception sessions;
3. there are zero missing minutes in every other session;
4. there are zero unexpected RTH minutes;
5. there are zero duplicate RTH timestamps;
6. OHLC integrity passes;
7. volume integrity passes;
8. the frozen exception policy has not changed.

The revised canonical H4 minute layer excludes both complete sessions.

### Expected Primary Population

Complete calendar sessions:

`1,255`

Excluded infrastructure-exception sessions:

`2`

Expected primary-eligible sessions:

`1,253`

Expected full-calendar RTH minutes:

`487,650`

The two excluded sessions are ordinary 390-minute sessions, so expected primary-eligible RTH minutes are:

`486,870`

### Outcome Firewall

Support/resistance events calculated:

`NO`

Liquidity sweeps calculated:

`NO`

Forward returns calculated:

`NO`

Directional hit rates calculated:

`NO`

MFE / MAE calculated:

`NO`

H4 thresholds changed:

`NO`

### Next Step

Run the V2 exception-aware minute-history integrity audit.

Only after the token:

`H4_5MIN_LOCATION_LAYER_CONSTRUCTION_AUTHORIZED`

may the project derive five-minute bars and construct the H4 pre-outcome location layer.

---

## 3.71 H4 Five-Minute Location Layer — Pre-Outcome Construction Authorization

### Date

2026-08-28

### Status

This stage remains fully behind the H4 outcome firewall.

The construction script refuses to execute unless the revised exception-aware one-minute audit contains both authorization tokens:

`H4_SPY_ALPACA_SIP_PRIMARY_ELIGIBLE_MINUTE_HISTORY_AUDIT_PASSED`

and:

`H4_5MIN_LOCATION_LAYER_CONSTRUCTION_AUTHORIZED`

No H4 forward-return outcome is calculated in either the builder or the independent audit.

### Source Architecture

Primary intraday source:

`Alpaca SIP raw one-minute SPY bars`

Primary-eligible intraday sessions:

`1,253`, conditional on the passed V2 audit.

Frozen excluded infrastructure sessions:

- `2021-05-05`
- `2023-06-05`

Raw intraday files remain unchanged.

### Higher-Timeframe Support Data

Higher-timeframe location levels are sourced separately from:

`Alpaca SIP raw daily SPY bars`

using:

`adjustment = raw`

Support-history interval:

`2020-11-01 through 2025-12-31`

The additional 2020 support history provides pre-2021 ATR, prior-week, and prior-month state without using future H4 observations.

The two excluded intraday infrastructure sessions remain eligible to contribute to later PDH/PWH/PMH or PDL/PWL/PML calculations only if their complete daily SIP bars exist and pass daily OHLC validation.

No missing one-minute bar is reconstructed.

### Five-Minute Aggregation

The primary analytical bar is deterministically aggregated from the audited one-minute layer.

Each five-minute bar must contain exactly:

`5`

consecutive primary-eligible one-minute observations.

Aggregation:

- open = first one-minute open;
- high = maximum one-minute high;
- low = minimum one-minute low;
- close = last one-minute close;
- volume = sum of one-minute volume;
- transactions = sum of one-minute transaction count;
- five-minute VWAP = volume-weighted combination of provider one-minute VWAP.

The independent audit fully recomputes these fields from the one-minute source.

### Daily Volatility and Major Levels

ATR:

`Wilder ATR(14)`

The intraday session may use only:

`ATR(14) calculated through the prior completed trading session`

Primary resistance families:

- `PDH`
- `PWH`
- `PMH`

Primary support families:

- `PDL`
- `PWL`
- `PML`

Previous week means the immediately previous completed Monday–Sunday calendar week containing trading sessions.

Previous month means the immediately previous completed calendar month.

### Location Zones

Every source level receives half-width:

`0.10 × prior-session ATR(14)`

Same-direction intervals that overlap are deterministically merged.

Merged zones preserve:

- contributing level families;
- constituent price levels;
- lower and upper boundaries;
- confluence count;
- `SINGLE_SOURCE` versus `CONFLUENCE`.

### First Contact

For each merged zone and session:

`first contact = earliest five-minute bar whose high-low range intersects the merged zone`

Only the first interaction is retained for the primary H4 architecture.

No liquidity-sweep success condition is calculated at this stage.

### Pre-Outcome Price-Discovery Context

The five-minute layer also records deterministic state variables requested for sessions with little or no historical overhead resistance:

- prior completed-session all-time high;
- close above prior all-time high;
- intrabar break above prior all-time high;
- ATR-normalized extension above prior all-time high;
- session VWAP through the current completed bar;
- ATR-normalized distance from VWAP;
- same-time-bucket relative volume versus the median of the prior 20 valid sessions;
- elevated RVOL diagnostic at `RVOL >= 1.50`;
- rolling 30-minute realized volatility from six completed five-minute returns;
- time-of-day realized-volatility ratio versus the prior-20-session median;
- 30-minute opening-range extension normalized by ATR;
- three-bar displacement normalized by ATR.

These are context variables only.

They do not alter H4A's frozen primary S/R sweep definition.

### New Scripts

Builder:

`src/analysis/build_h4_5min_location_layer.py`

Independent audit:

`src/analysis/audit_h4_5min_location_layer.py`

### Expected Outputs

Daily support layer:

`data/interim/h4_spy_daily_sip_support_levels_2020_2025.csv`

Five-minute pre-outcome layer:

`data/interim/h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz`

Merged zones:

`data/interim/h4_spy_5min_location_zones_preoutcome.csv`

First contacts:

`data/interim/h4_spy_5min_first_contacts_preoutcome.csv`

Build manifest:

`data/interim/h4_spy_5min_location_layer_manifest.json`

Build report:

`reports/data_quality/h4_spy_5min_location_layer_build.txt`

Independent audit:

`reports/data_quality/h4_spy_5min_location_layer_integrity_audit.txt`

### Outcome Firewall

Liquidity-sweep trigger:

`NOT CALCULATED`

15-minute forward return:

`NOT CALCULATED`

30-minute primary forward return:

`NOT CALCULATED`

60-minute forward return:

`NOT CALCULATED`

Directional success:

`NOT CALCULATED`

MFE / MAE:

`NOT CALCULATED`

Threshold selection from outcomes:

`PROHIBITED`

### Next Authorization

Only a passed independent five-minute location-layer audit may issue:

`H4_5MIN_LOCATION_LAYER_INTEGRITY_AUDIT_PASSED`

and:

`H4_LIQUIDITY_SWEEP_TRIGGER_CONSTRUCTION_AUTHORIZED`

Only then may the project construct the frozen liquidity-sweep/rejection trigger, still before opening the forward-return outcomes.

---

## 3.72 H4 Five-Minute Location Builder V1 Failure — Timestamp Serialization Order Corrected Before Outcomes

### Date

2026-08-28

### Failed Execution

Script:

`src/analysis/build_h4_5min_location_layer.py`

Version:

`2026-08-28-v1-h4-5min-location-layer-pre-outcome`

The script passed the V2 one-minute authorization gate and successfully completed:

- daily PIT support/resistance construction;
- canonical primary-eligible one-minute loading;
- deterministic five-minute aggregation;
- pre-outcome context attachment;
- merged S/R zone construction.

It then failed during first-contact construction with:

`AttributeError: 'str' object has no attribute 'isoformat'`

The fault occurred because the builder converted:

- `bar_start_et`
- `bar_end_et`
- `session_open_et`
- `session_close_et`

from timezone-aware datetime objects into ISO strings before calling `build_first_contacts()`.

`build_first_contacts()` then attempted to serialize `bar_start_et` and `bar_end_et` using `.isoformat()`, which is a datetime method and is not available on an already serialized string.

### Outcome Firewall

At the time of failure:

Liquidity-sweep trigger calculated:

`NO`

15-minute forward return calculated:

`NO`

30-minute forward return calculated:

`NO`

60-minute forward return calculated:

`NO`

Directional hit rate calculated:

`NO`

MFE / MAE calculated:

`NO`

No H4 predictive result was exposed.

### Corrective Action

Replacement version:

`2026-08-28-v2-h4-5min-location-layer-serialization-order-fix`

The correction is implementation-only.

V2 now performs the operations in this order:

1. maintain timezone-aware datetime values in memory;
2. construct deterministic S/R zones;
3. identify first contacts while datetime semantics remain intact;
4. serialize datetime columns to ISO strings only after first-contact construction;
5. write the pre-outcome artifacts.

### Frozen Research Decisions Unchanged

The correction changes none of the following:

- SPY as primary instrument;
- Alpaca SIP as primary intraday source;
- the two frozen infrastructure-session exclusions;
- five-minute bar definition;
- Wilder ATR(14);
- prior-day ATR usage;
- PDH/PDL/PWH/PWL/PMH/PML definitions;
- `0.10 × ATR` zone half-width;
- deterministic same-direction zone merging;
- first-contact definition;
- RVOL definition;
- price-discovery definition;
- opening-range context;
- realized-volatility context;
- displacement context;
- any future liquidity-sweep threshold;
- any forward-return horizon;
- any inference rule.

No post-outcome tuning occurred.

### Canonical Script

The V2 file should replace:

`src/analysis/build_h4_5min_location_layer.py`

The independent audit remains:

`src/analysis/audit_h4_5min_location_layer.py`

because the audit methodology is unaffected by the serialization-order bug.

### Next Step

Commit the V2 implementation correction before successful location-layer results are observed.

Then rerun:

`python src/analysis/build_h4_5min_location_layer.py`

and, only after a successful build token, run:

`python src/analysis/audit_h4_5min_location_layer.py`

---

## 3.73 H4 Liquidity-Sweep Trigger Layer — Pre-Outcome Freeze

### Date

2026-08-28

### Authorization

The independently audited five-minute location layer passed and issued:

`H4_LIQUIDITY_SWEEP_TRIGGER_CONSTRUCTION_AUTHORIZED`

The project is therefore authorized to construct the frozen H4 liquidity-sweep/rejection trigger.

Forward-return outcomes remain unopened.

### Eligible Trigger Population

Only:

`first-contact bars from the independently audited merged S/R zone layer`

are eligible.

Later revisits of a merged zone on the same session are not eligible for the H4A primary trigger.

### Frozen Penetration Threshold

The first-contact five-minute bar must penetrate an eligible constituent level by at least:

`0.02 × prior-session Wilder ATR(14)`

### Resistance Trigger

For constituent resistance level `L`:

`first_contact_high >= L + 0.02 × prior_ATR14`

and:

`first_contact_close < L`

Expected rejection direction:

`DOWN`

### Support Trigger

For constituent support level `L`:

`first_contact_low <= L - 0.02 × prior_ATR14`

and:

`first_contact_close > L`

Expected rejection direction:

`UP`

### Merged-Zone Rule

A merged zone contains one or more constituent PDH/PWH/PMH or PDL/PWL/PML levels.

The merged zone triggers if:

`AT LEAST ONE CONSTITUENT LEVEL`

satisfies the corresponding same-bar sweep/rejection rule.

This rule is frozen before opening any H4 forward outcome.

### Multiple Qualifying Constituent Levels

If multiple constituent levels inside one merged zone qualify on the same first-contact bar, the zone remains:

`ONE EVENT`

The deterministic reference level is:

- resistance: highest qualifying constituent level;
- support: lowest qualifying constituent level.

This selects the most extreme qualifying swept/rejected level without creating duplicate events.

### Trigger Time

Trigger time:

`close of the qualifying first-contact five-minute bar`

No information after that bar may enter trigger construction.

### Horizon Clock Eligibility

Before outcome access, the trigger layer records whether sufficient official regular-session clock time remains for:

- 15 minutes;
- 30 minutes;
- 60 minutes.

A horizon is clock-eligible only when:

`trigger_bar_end + horizon <= official session close`

Primary horizon remains:

`30 minutes`

Secondary horizons remain:

- `15 minutes`
- `60 minutes`

Clock eligibility is not an outcome and is frozen before the future-return join.

### Context Preserved on Trigger Rows

Contemporaneous pre-outcome context may be carried forward from the audited location layer, including:

- confluence status;
- contributing level families;
- first-contact OHLCV;
- provider VWAP;
- session VWAP;
- RVOL;
- realized-volatility state;
- opening-range extension;
- three-bar displacement;
- price-discovery indicators.

These fields do not alter the H4A primary trigger definition.

### New Scripts

Trigger builder:

`src/analysis/build_h4_liquidity_sweep_trigger_layer.py`

Independent trigger audit:

`src/analysis/audit_h4_liquidity_sweep_trigger_layer.py`

### Expected Outputs

Trigger layer:

`data/interim/h4_spy_liquidity_sweep_triggers_preoutcome.csv`

Manifest:

`data/interim/h4_spy_liquidity_sweep_trigger_manifest.json`

Build report:

`reports/data_quality/h4_spy_liquidity_sweep_trigger_build.txt`

Independent audit:

`reports/data_quality/h4_spy_liquidity_sweep_trigger_integrity_audit.txt`

Audit manifest:

`data/interim/h4_spy_liquidity_sweep_trigger_audit_manifest.json`

### Outcome Firewall

15-minute forward return:

`NOT CALCULATED`

30-minute forward return:

`NOT CALCULATED`

60-minute forward return:

`NOT CALCULATED`

Signed forward return:

`NOT CALCULATED`

Directional success:

`NOT CALCULATED`

MFE / MAE:

`NOT CALCULATED`

No trigger threshold may be changed after future returns are opened.

### Next Authorization

Only a successful independent trigger audit may issue:

`H4_LIQUIDITY_SWEEP_TRIGGER_INTEGRITY_AUDIT_PASSED`

and:

`H4_PRIMARY_OUTCOME_JOIN_SPECIFICATION_AUTHORIZED`

At that point the project may freeze the exact forward-outcome join and inference specification before calculating the first H4 result.

---

## 3.74 H4 Primary Outcome and Confirmatory Inference — Pre-Outcome Freeze

### Date

2026-08-28

### Authorization

The H4 liquidity-sweep trigger layer passed its independent integrity audit and issued:

`H4_PRIMARY_OUTCOME_JOIN_SPECIFICATION_AUTHORIZED`

No H4 forward-return result had been observed before this specification was frozen.

### Primary H4A Question

Does an objectively defined first-contact support/resistance liquidity sweep and same-bar rejection predict price movement in the preregistered rejection direction over the next 30 minutes?

### Primary Eligible Event

An event enters H4A only when:

- `liquidity_sweep_trigger == 1`
- `horizon_30m_clock_eligible == 1`

No overnight extension and no next-session carry are allowed.

### Exact 30-Minute Endpoint

The trigger occurs at the close of the qualifying first-contact five-minute bar.

The 30-minute endpoint is:

`trigger_bar_index + 6`

using the close of that five-minute bar.

Secondary endpoints:

- 15 minutes = `trigger_bar_index + 3`
- 60 minutes = `trigger_bar_index + 12`

Every endpoint must remain in the same official regular session.

### Signed Return

Raw return:

`endpoint_close / trigger_close - 1`

Direction sign:

- support sweep = `+1`
- resistance sweep = `-1`

Primary signed return:

`direction_sign × raw_forward_return_30m`

Thus a positive value always means movement in the preregistered rejection direction.

### Primary Estimand

`mean signed_forward_return_30m`

across all frozen eligible H4A events.

### Primary Inference

Model:

`intercept-only OLS on event-level signed_forward_return_30m`

Covariance:

`cluster-robust by session_date`

Small-sample correction:

`TRUE`

Reference degrees of freedom:

`number of unique eligible session clusters - 1`

Primary test:

`two-sided`

Alpha:

`0.05`

Frozen minimum sample:

- events >= `100`
- unique session clusters >= `100`

### Support Rule

`SUPPORTED`

only if:

- two-sided p-value < `0.05`
- estimated mean signed return > `0`

`CONTRADICTED`

only if:

- two-sided p-value < `0.05`
- estimated mean signed return < `0`

Otherwise:

`NOT SUPPORTED`

### Why Session Clustering

Multiple merged-zone triggers can occur within one trading session.

They are not treated as independent for inference.

Session clustering allows event-level estimation while accounting for arbitrary within-session dependence.

### Secondary Outcomes

Prespecified descriptive/robustness horizons:

- 15 minutes
- 60 minutes

They cannot replace or upgrade the 30-minute primary decision.

### MFE / MAE

For the six five-minute bars immediately following the trigger bar:

- MFE = maximum favorable signed price excursion relative to trigger close
- MAE = maximum adverse signed price excursion relative to trigger close

These are descriptive and not part of the H4A primary significance test.

### Session-Collapsed Robustness

Prespecified robustness:

1. average signed 30-minute return across all eligible events within each session;
2. test the mean session return using Newey-West HAC with lag `5`.

This robustness cannot upgrade a failed primary result.

### Additional Descriptive Stability

The confirmatory report may show:

- year-by-year event count and mean signed 30-minute return;
- support versus resistance stability;
- confluence versus single-source stability;
- elevated versus non-elevated RVOL stability.

These are not separate confirmatory H4A tests unless separately preregistered later.

### Gross Return Boundary

H4A is a gross price-return signal test.

It does not include:

- spread;
- slippage;
- commissions;
- market impact.

No deployable trading-strategy claim is permitted until execution costs are analyzed separately.

### Frozen Preregistration

`data/reference/h4/h4_primary_liquidity_sweep_inference_v1.json`

### New Scripts

Outcome join:

`src/analysis/build_h4_primary_outcome_join.py`

Independent outcome audit:

`src/analysis/audit_h4_primary_outcome_join.py`

Confirmatory inference:

`src/analysis/run_h4_primary_confirmatory_inference.py`

### Required Execution Order

1. commit this preregistration and all three scripts before outcome access;
2. run the outcome join;
3. run the independent outcome audit;
4. only after `H4_PRIMARY_CONFIRMATORY_INFERENCE_AUTHORIZED`, run confirmatory inference.

### Outcome Firewall at Freeze

Forward-return outcomes observed:

`NO`

Mean signed return observed:

`NO`

Hit rate observed:

`NO`

MFE / MAE observed:

`NO`

P-value observed:

`NO`

Threshold retuning after outcomes:

`PROHIBITED`

# Current Status

Current phase:

**H4 PRIMARY OUTCOME + INFERENCE SPECIFICATION — FROZEN BEFORE OUTCOME ACCESS**

## H4 Research State

Primary instrument:

`SPY`

Primary intraday source:

`ALPACA SIP`

Five-minute location layer:

`PASSED`

Liquidity-sweep trigger layer:

`PASSED`

Primary H4A outcome:

`SIGNED 30-MINUTE RETURN`

Primary inference:

`EVENT-LEVEL INTERCEPT-ONLY OLS WITH SESSION-CLUSTERED COVARIANCE`

Primary test:

`TWO-SIDED α=0.05 + POSITIVE SIGN REQUIREMENT`

Secondary horizons:

`15 MINUTES / 60 MINUTES — DESCRIPTIVE ONLY`

H4 forward-return results observed:

`NO AT SPECIFICATION FREEZE`

## Immediate Next Step

Commit the frozen preregistration and all outcome/inference scripts.

Then run:

`python src/analysis/build_h4_primary_outcome_join.py`

followed by:

`python src/analysis/audit_h4_primary_outcome_join.py`

Only after the audit issues:

`H4_PRIMARY_CONFIRMATORY_INFERENCE_AUTHORIZED`

may the first H4 confirmatory result be calculated.
