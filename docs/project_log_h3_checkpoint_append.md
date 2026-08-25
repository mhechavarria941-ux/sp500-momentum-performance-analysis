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

# Current Status

Current phase:

**H3 attention-data feasibility and point-in-time company-identity preparation**

## Closed Confirmatory Research

H1 canonical market-wide 12-1 momentum:

`CLOSED — NOT SUPPORTED IN THE CORRECTED 2021-2025 SAMPLE`

H2 sector-relative 12-1 momentum:

`CLOSED — NOT SUPPORTED IN THE PREREGISTERED 2021-2025 SAMPLE`

## Closed Exploratory Theme Branch

Post-H2 residual commonality:

`EXPLORATORY — CONSTRUCTED AND ATTRIBUTED`

Frozen evidence taxonomy:

`COMPLETED`

Phase 4A theme synchrony:

`CLOSED — NO ADJUSTED THEME-SYNCHRONY SIGNAL`

## H3 Attention Feasibility State

Direct GDELT historical pilot:

`PASSED`

Pilot company coverage:

`15 / 15 meet >=2/5 strict nonzero-window rule`

High-ambiguity pilot review:

`CLOSED — CONSERVATIVE STRICT-ALIAS POLICY RETAINED`

Cloud architecture decision:

- Google Cloud: `NO`
- BigQuery: `NO`
- direct GDELT downloads: `YES`
- Azure SQL writes during feasibility: `NO`

## Full-Universe H3 Identity State

Canonical historical security identities:

`593`

Historical ticker segments:

`594`

Candidate company-query rows:

`593`

Duplicate exact normalized aliases:

`0`

Structural ambiguity:

- HIGH: `210`
- MEDIUM: `220`
- LOW: `163`

Ticker-like exact company names:

`8`

PIT/name-history review queue:

`211`

Current company names point-in-time validated:

`NO`

Final Stage 3A V4 integrity-audit confirmation:

`PENDING`

Stage 3B SEC resolution:

`PREPARED — NOT YET EXECUTED`

## Interpretation Boundary

No H3 predictive or return inference has been performed.

No attention transformation may be selected according to return performance.

No full-history attention dataset may be joined to future returns until:

1. Stage 3A final candidate-manifest audit is confirmed;
2. SEC company-name history is resolved and audited;
3. PIT attention aliases are frozen;
4. full attention coverage/missingness is audited;
5. the usable H3 universe is frozen;
6. the attention transformation is frozen;
7. the residual-return/outcome model is frozen;
8. H3 is formally preregistered.

## Immediate Next Step

Confirm:

`H3_COMPANY_QUERY_MANIFEST_CANDIDATE_INTEGRITY_AUDIT_PASSED`

from the V4 Stage 3A audit.

Then run Stage 3B SEC company identity/name-history resolution and inspect the resulting review queue before creating point-in-time alias intervals.
