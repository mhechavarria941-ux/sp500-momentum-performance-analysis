# SQL Research Warehouse Design

## Objective

Complete the S&P 500 Momentum Analysis as an end-to-end analytical system in which:

1. Python remains the authoritative construction/audit and confirmatory-computation layer.
2. Azure SQL contains the reproducible analytical representation of H1 through H4.
3. SQL queries can reproduce the economic quantities and inferential decisions used by the research.
4. Power BI connects to curated `bi` views rather than Python-generated result CSVs.
5. Students can trace each displayed result to an understandable SQL query and variable definition.

## Existing Architecture Preserved

Existing schemas remain unchanged:

- `raw`
- `staging`
- `core`
- `analytics`

The database is extended with:

- `ref` — hypothesis definitions, variable dictionary, statistical reference distributions.
- `research` — hypothesis-specific educational/reproduction panels.
- `results` — frozen primary, secondary, robustness, and breakdown results.
- `audit` — pipeline runs, quality checks, exclusions, checksums, provenance.
- `bi` — curated Power BI/student-facing semantic views.

## Statistical Reference Layer

Azure SQL does not depend on SciPy at query time.

The project precomputes and persists:

### `ref.student_t_two_sided_lookup`

- degrees of freedom: `1` through `600`
- adaptive two-sided p-value grid
- corresponding absolute Student-t critical value
- generated from SciPy
- persisted in Azure SQL

SQL function:

`ref.fn_student_t_two_sided_p(t_stat, degrees_freedom)`

The function linearly interpolates between adjacent precomputed inverse-CDF points.

This is designed to reproduce the project's Student-t p-values closely enough to preserve the frozen numerical interpretation and exact support/not-supported/contradicted decisions.

### `ref.normal_two_sided_lookup`

Normal-distribution counterpart for asymptotic z/HAC reporting where required.

SQL function:

`ref.fn_normal_two_sided_p(z_stat)`

### `ref.fn_student_t_critical(df, alpha)`

Returns/interpolates the two-sided Student-t critical value required for confidence intervals.

Exact common alpha values such as `0.05` are included directly in the grid.

## Educational Metadata

### `ref.hypothesis`

One row per hypothesis/component.

### `ref.variable_catalog`

Defines:

- variable name;
- display name;
- description;
- grain;
- unit;
- formula;
- look-ahead status;
- source object;
- educational notes.

### `ref.hypothesis_variable_map`

Maps variables to H1-H4 as:

- predictor;
- outcome;
- control;
- ranking variable;
- context;
- robustness variable;
- identifier;
- weight.

## Results Layer

### `results.hypothesis_result`

Normalized statistical-result storage for H1-H4.

### `results.result_breakdown`

Supports:

- year;
- sector;
- decile;
- horizon;
- confluence;
- other descriptive breakdowns.

## Audit Layer

### `audit.pipeline_run`

Every major database-generation run.

### `audit.quality_check`

Expected versus observed validation checks.

### `audit.exclusion`

Research exclusions such as H4 infrastructure sessions.

### `audit.artifact`

Checksum/provenance links between SQL and repository artifacts.

## Power BI Contract

Power BI will use only curated `bi` views for normal reporting.

Initial foundation views:

- `bi.vw_research_summary`
- `bi.vw_variable_catalog`

Later H1-H4 binding will add:

- `bi.vw_h1_decile_performance`
- `bi.vw_h1_wml_vs_spy`
- `bi.vw_h2_sector_results`
- `bi.vw_h3_attention_panel`
- `bi.vw_h3_results`
- `bi.vw_h4_events`
- `bi.vw_h4_yearly_results`
- `bi.vw_data_quality`

## Reproduction Rule

Every final Power BI chart must have:

1. a documented `bi` or `research` SQL source;
2. a student-readable reproduction query;
3. a variable-catalog entry for every nontrivial analytical variable;
4. reconciliation against the frozen Python result when the chart represents a confirmatory result.

DAX is reserved for presentation/filter-context calculations.

The official inferential result is stored in SQL and reconciled to the frozen Python result rather than independently redefined in DAX.
