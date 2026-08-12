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

# Current Status

Completed:

`Development environment → GitHub → Azure SQL → Python/Azure connection → raw SPY acquisition → workbook audit → constituent filtering → 503-security anchor`

Current phase:

**Historical S&P 500 membership reconstruction**

Next objective:

Identify and document S&P 500 constituent additions and removals from the anchor date backward through the analytical period so that membership can be reconstructed for January 2021 through December 2025.

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
