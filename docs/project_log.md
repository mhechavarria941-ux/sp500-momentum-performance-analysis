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

Current phase:

**Point-in-time S&P 500 membership interval construction**

Next objective:

Generate a reproducible security-level membership table containing the valid membership periods for every S&P 500 security appearing between January 1, 2021 and December 31, 2025.


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
