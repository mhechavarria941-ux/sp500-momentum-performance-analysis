# Power BI Desktop Build — S&P 500 Momentum Analysis

## 1. Connect

Power BI Desktop:

**Home → Get data → SQL Server**

Use the existing Azure SQL database:

`sp500_analytics`

Recommended connectivity mode:

`Import`

The curated BI layer is compact enough for a responsive research dashboard, while the large raw H4 minute/5-minute tables remain outside the default Power BI model.

## 2. Load These BI Objects

### Dimensions
- `bi.dim_date`
- `bi.dim_hypothesis`
- `bi.dim_variable`
- `bi.dim_h4_session`

### Bridge
- `bi.bridge_hypothesis_variable`

### Facts
- `bi.fact_results`
- `bi.fact_result_breakdown`
- `bi.fact_h1_monthly`
- `bi.fact_h1_summary`
- `bi.fact_h1_primary_monthly`
- `bi.fact_h2_monthly`
- `bi.fact_h3_panel`
- `bi.fact_h4_events`
- `bi.fact_h4_yearly`
- `bi.fact_data_quality`
- `bi.fact_exclusions`
- `bi.fact_artifacts`

## 3. Relationships

Create one-to-many, single-direction relationships.

### Hypothesis
`dim_hypothesis[hypothesis_id]` → `fact_results[hypothesis_id]`

`dim_hypothesis[hypothesis_id]` → `fact_result_breakdown[hypothesis_id]`

`dim_hypothesis[hypothesis_id]` → `fact_exclusions[hypothesis_id]`

`dim_hypothesis[hypothesis_id]` → `fact_artifacts[hypothesis_id]`

`dim_hypothesis[hypothesis_id]` → `bridge_hypothesis_variable[hypothesis_id]`

### Variable
`dim_variable[variable_id]` → `bridge_hypothesis_variable[variable_id]`

### Date
Mark:

`dim_date[date]`

as the model Date Table.

Active:
- `dim_date[date]` → `fact_h1_monthly[ranking_month_end_date]`
- `dim_date[date]` → `fact_h1_primary_monthly[ranking_month_end_date]`
- `dim_date[date]` → `fact_h2_monthly[ranking_month_end_date]`
- `dim_date[date]` → `fact_h3_panel[predictor_month_end]`
- `dim_date[date]` → `fact_h4_events[session_date]`
- `dim_date[date]` → `dim_h4_session[session_date]`

Optional inactive:
- `dim_date[date]` → `fact_h3_panel[outcome_month_end]`

Do not enable bidirectional filtering.

## 4. Measure Table

Create an Enter Data table named:

`_Measures`

Keep one placeholder column, then hide it.

Add the measures from:

`docs/power_bi_dax_measures.md`

Start with:

- Selected Estimate
- Selected Raw P Value
- Selected Adjusted P Value
- Selected Decision
- H1 Monthly Return
- H2 Mean WML
- H3 Winner Entry Rate
- H4 Events
- H4 Sessions
- H4 Mean Signed Return 30m
- H4 Directional Success Rate 30m
- H4 Mean MFE 30m
- H4 Mean MAE 30m
- Quality Pass Rate

## 5. Validation Before Visual Design

Create temporary cards/tables and confirm:

### H2
`H2 Months = 59`

### H3
Eligible H3A/H3C rows:
`29,114`

Eligible H3B rows:
`26,139`

### H4
Events:
`164`

Sessions:
`156`

Mean signed 30-minute return:
approximately `-0.061314%`

The official H4A p-value and decision must come from `fact_results`, not from DAX:

- p-value ≈ `0.03538`
- decision = `CONTRADICTED`

## 6. Page Order

1. Executive Research Summary
2. H1 — Canonical Momentum
3. H2 — Sector-Relative Momentum
4. H3 — News Attention
5. H4 — Intraday Market Structure
6. Cross-Hypothesis Comparison
7. Data Quality / Provenance
8. Variable Explorer

## 7. First Visuals

### Executive Summary
- Matrix: hypothesis/component, estimate, p-value, decision
- Cards: H1 status, H2 status, H3 status, H4A status
- Timeline/sample window

### H1
- Column chart: annualized return by D01–D10
- Line chart: monthly WML
- Comparison: D10 vs SPY
- Cards: annualized return, volatility, max drawdown

### H2
- Line chart: monthly sector-neutral WML
- Column chart: quintile mean returns
- Card: frozen H2 p-value / decision

### H3
- Histogram or binned chart: attention_z
- Winner-entry rate by attention bin
- Sector-relative return by attention bin
- Result matrix: H3A/H3B/H3C coefficient, raw p, Holm p, decision

### H4
- Cards: events, sessions, mean signed 30m return, p-value, decision
- Column chart: yearly mean signed 30m return
- Support vs resistance comparison
- Confluence comparison
- RVOL comparison
- MFE vs MAE

## 8. Research Rule

Do not use Power BI to redefine the frozen hypothesis tests.

The dashboard explains and explores the completed study.

Official inference is read from:

`bi.fact_results`
