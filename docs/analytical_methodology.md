# Analytical Methodology

## 1. Purpose

This document defines the analytical rules used to transform the validated
point-in-time S&P 500 market-data model into return, momentum, benchmark,
and risk-analysis datasets.

The methodology is fixed before analytical calculations are implemented so
that SQL views, Python audits, and Power BI measures use consistent definitions.

The primary analysis period is:

- Start date: 2021-01-01
- End date: 2025-12-31

The normalized Azure SQL market-data layer is the authoritative analytical
source.

---

## 2. Computing Responsibilities

### 2.1 Azure SQL

Azure SQL and T-SQL are the primary analytical engine.

SQL is responsible for:

- SPY trading-session calendars
- Calendar month-end identification
- Daily security returns
- Daily benchmark returns
- Monthly security observations
- Monthly benchmark observations
- Trailing returns
- Momentum signals
- Cross-sectional momentum rankings
- Forward returns
- Benchmark-relative returns
- Volatility
- Beta
- Drawdown foundations
- Analytical completeness indicators
- Look-ahead and censoring controls

### 2.2 Python

Python provides an independent validation and reproducibility layer.

Python is responsible for:

- Auditing SQL row counts
- Independently recalculating sampled returns
- Verifying month-end selection
- Verifying momentum lookback windows
- Verifying forward-return horizons
- Detecting missing or extra observations
- Validating SQL aggregate results
- Producing controlled reports and exports
- Performing statistical analysis that is unnecessarily complex in T-SQL

Python must not silently replace the authoritative SQL calculation layer.

### 2.3 Power BI

Power BI consumes validated SQL analytical views.

Power BI is responsible for:

- Interactive filtering
- Portfolio and benchmark visualization
- Momentum-decile comparisons
- Return and risk dashboards
- Summary measures based on validated SQL outputs

Power BI must not redefine core return or momentum methodology.

---

## 3. Authoritative Source Tables

The analytical layer is built from the following normalized Azure SQL tables:

- `core.security`
- `core.security_ticker_history`
- `core.index_membership`
- `core.security_price_eligibility`
- `core.daily_security_price`
- `core.benchmark_series`
- `core.daily_benchmark_price`

Validated core populations are:

- Security identities: 593
- Ticker-history segments: 594
- Membership intervals: 593
- Price-eligibility intervals: 594
- Constituent daily observations: 631,942
- Benchmark definitions: 2
- Benchmark daily observations: 2,510
- Total daily observations: 634,452

All staging tables were empty following controlled promotion.

---

## 4. Security Identity

The persistent `security_key` is the analytical security identity.

Ticker symbols are historical attributes and must not be treated as permanent
security identities.

All calculations spanning ticker changes must partition by `security_key`.

The CDAY-to-DAY ticker change therefore remains one continuous security
identity represented by two ticker-history segments.

Ticker symbols remain available for:

- Historical display
- Source reconciliation
- Segment-level eligibility checks
- Provider-symbol traceability

---

## 5. Point-in-Time Membership

A security is considered an index constituent on date `d` when:

```text
membership_valid_from <= d
and
d < membership_valid_to_exclusive