/*
S&P 500 Momentum Analysis
Research warehouse + statistical reference foundation

Version: 2026-08-28-v1

This migration is intentionally non-destructive.
It extends the existing raw/staging/core/analytics architecture with:
  ref      - research definitions and statistical lookup references
  research - hypothesis-specific analytical panels
  results  - frozen hypothesis results and breakdowns
  audit    - provenance, quality checks, exclusions, artifacts
  bi       - student/Power BI semantic views

The existing core and analytics objects are not modified.
*/

SET XACT_ABORT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ref')
    EXEC(N'CREATE SCHEMA ref AUTHORIZATION dbo;');

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'research')
    EXEC(N'CREATE SCHEMA research AUTHORIZATION dbo;');

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'results')
    EXEC(N'CREATE SCHEMA results AUTHORIZATION dbo;');

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'audit')
    EXEC(N'CREATE SCHEMA audit AUTHORIZATION dbo;');

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'bi')
    EXEC(N'CREATE SCHEMA bi AUTHORIZATION dbo;');
GO

IF OBJECT_ID(N'ref.hypothesis', N'U') IS NULL
BEGIN
    CREATE TABLE ref.hypothesis
    (
        hypothesis_id               varchar(16)     NOT NULL,
        parent_hypothesis_id        varchar(16)     NULL,
        hypothesis_name             nvarchar(200)   NOT NULL,
        research_question           nvarchar(1200)  NOT NULL,
        primary_outcome             nvarchar(600)   NULL,
        primary_test                nvarchar(800)   NULL,
        alpha                       decimal(12,10)   NULL,
        status                      varchar(64)      NOT NULL,
        sample_start                date             NULL,
        sample_end                  date             NULL,
        preregistration_version     nvarchar(200)   NULL,
        preregistration_sha256      char(64)         NULL,
        notes                       nvarchar(3000)   NULL,
        created_at_utc              datetime2(0)     NOT NULL
            CONSTRAINT DF_ref_hypothesis_created
            DEFAULT SYSUTCDATETIME(),
        updated_at_utc              datetime2(0)     NOT NULL
            CONSTRAINT DF_ref_hypothesis_updated
            DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_ref_hypothesis
            PRIMARY KEY (hypothesis_id),

        CONSTRAINT FK_ref_hypothesis_parent
            FOREIGN KEY (parent_hypothesis_id)
            REFERENCES ref.hypothesis(hypothesis_id),

        CONSTRAINT CK_ref_hypothesis_alpha
            CHECK (alpha IS NULL OR (alpha > 0 AND alpha < 1))
    );
END;
GO

IF OBJECT_ID(N'ref.variable_catalog', N'U') IS NULL
BEGIN
    CREATE TABLE ref.variable_catalog
    (
        variable_id             int IDENTITY(1,1) NOT NULL,
        variable_name           sysname           NOT NULL,
        display_name            nvarchar(200)     NOT NULL,
        description             nvarchar(2000)    NOT NULL,
        grain                   nvarchar(250)     NOT NULL,
        unit                    nvarchar(100)     NULL,
        formula_description     nvarchar(2000)    NULL,
        lookahead_safe          bit               NOT NULL,
        source_object           nvarchar(300)     NULL,
        source_column           sysname           NULL,
        educational_notes       nvarchar(2500)    NULL,
        created_at_utc          datetime2(0)      NOT NULL
            CONSTRAINT DF_ref_variable_catalog_created
            DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_ref_variable_catalog
            PRIMARY KEY (variable_id),

        CONSTRAINT UQ_ref_variable_catalog_name
            UNIQUE (variable_name)
    );
END;
GO

IF OBJECT_ID(N'ref.hypothesis_variable_map', N'U') IS NULL
BEGIN
    CREATE TABLE ref.hypothesis_variable_map
    (
        hypothesis_id       varchar(16)    NOT NULL,
        variable_id         int            NOT NULL,
        variable_role       varchar(40)    NOT NULL,
        notes               nvarchar(1500) NULL,

        CONSTRAINT PK_ref_hypothesis_variable_map
            PRIMARY KEY (hypothesis_id, variable_id, variable_role),

        CONSTRAINT FK_ref_hvm_hypothesis
            FOREIGN KEY (hypothesis_id)
            REFERENCES ref.hypothesis(hypothesis_id),

        CONSTRAINT FK_ref_hvm_variable
            FOREIGN KEY (variable_id)
            REFERENCES ref.variable_catalog(variable_id),

        CONSTRAINT CK_ref_hvm_role
            CHECK (
                variable_role IN
                (
                    'PREDICTOR',
                    'OUTCOME',
                    'CONTROL',
                    'RANKING',
                    'CONTEXT',
                    'ROBUSTNESS',
                    'IDENTIFIER',
                    'WEIGHT'
                )
            )
    );
END;
GO

IF OBJECT_ID(N'ref.statistical_reference_metadata', N'U') IS NULL
BEGIN
    CREATE TABLE ref.statistical_reference_metadata
    (
        reference_name          varchar(80)     NOT NULL,
        generation_version      varchar(120)    NOT NULL,
        scipy_version           varchar(40)     NOT NULL,
        min_df                  int             NULL,
        max_df                  int             NULL,
        probability_points      int             NOT NULL,
        interpolation_method    nvarchar(500)   NOT NULL,
        notes                   nvarchar(2000)  NULL,
        generated_at_utc        datetime2(0)    NOT NULL,

        CONSTRAINT PK_ref_statistical_reference_metadata
            PRIMARY KEY (reference_name)
    );
END;
GO

IF OBJECT_ID(N'ref.student_t_two_sided_lookup', N'U') IS NULL
BEGIN
    CREATE TABLE ref.student_t_two_sided_lookup
    (
        degrees_freedom     smallint NOT NULL,
        two_sided_p         float    NOT NULL,
        critical_abs_t      float    NOT NULL,

        CONSTRAINT PK_ref_student_t_two_sided_lookup
            PRIMARY KEY CLUSTERED
            (degrees_freedom, two_sided_p),

        CONSTRAINT CK_ref_student_t_df
            CHECK (degrees_freedom BETWEEN 1 AND 600),

        CONSTRAINT CK_ref_student_t_p
            CHECK (two_sided_p > 0 AND two_sided_p <= 1),

        CONSTRAINT CK_ref_student_t_critical
            CHECK (critical_abs_t >= 0)
    );

    CREATE INDEX IX_ref_student_t_df_critical
        ON ref.student_t_two_sided_lookup
        (degrees_freedom, critical_abs_t)
        INCLUDE (two_sided_p);
END;
GO

IF OBJECT_ID(N'ref.normal_two_sided_lookup', N'U') IS NULL
BEGIN
    CREATE TABLE ref.normal_two_sided_lookup
    (
        two_sided_p         float NOT NULL,
        critical_abs_z      float NOT NULL,

        CONSTRAINT PK_ref_normal_two_sided_lookup
            PRIMARY KEY CLUSTERED (two_sided_p),

        CONSTRAINT CK_ref_normal_p
            CHECK (two_sided_p > 0 AND two_sided_p <= 1),

        CONSTRAINT CK_ref_normal_critical
            CHECK (critical_abs_z >= 0)
    );

    CREATE INDEX IX_ref_normal_critical
        ON ref.normal_two_sided_lookup
        (critical_abs_z)
        INCLUDE (two_sided_p);
END;
GO

IF OBJECT_ID(N'audit.pipeline_run', N'U') IS NULL
BEGIN
    CREATE TABLE audit.pipeline_run
    (
        run_id                  bigint IDENTITY(1,1) NOT NULL,
        pipeline_name           nvarchar(200) NOT NULL,
        script_version          nvarchar(200) NULL,
        git_commit              varchar(64) NULL,
        started_at_utc          datetime2(0) NOT NULL,
        completed_at_utc        datetime2(0) NULL,
        status                  varchar(32) NOT NULL,
        source_artifact_sha256  char(64) NULL,
        notes                   nvarchar(3000) NULL,

        CONSTRAINT PK_audit_pipeline_run
            PRIMARY KEY (run_id),

        CONSTRAINT CK_audit_pipeline_run_status
            CHECK (
                status IN
                ('STARTED','PASSED','FAILED','REVIEW','SKIPPED')
            )
    );
END;
GO

IF OBJECT_ID(N'audit.quality_check', N'U') IS NULL
BEGIN
    CREATE TABLE audit.quality_check
    (
        quality_check_id    bigint IDENTITY(1,1) NOT NULL,
        run_id              bigint NOT NULL,
        check_name          nvarchar(300) NOT NULL,
        expected_value      nvarchar(1000) NULL,
        observed_value      nvarchar(1000) NULL,
        passed              bit NOT NULL,
        details             nvarchar(3000) NULL,

        CONSTRAINT PK_audit_quality_check
            PRIMARY KEY (quality_check_id),

        CONSTRAINT FK_audit_quality_check_run
            FOREIGN KEY (run_id)
            REFERENCES audit.pipeline_run(run_id)
    );

    CREATE INDEX IX_audit_quality_check_run
        ON audit.quality_check(run_id, passed);
END;
GO

IF OBJECT_ID(N'audit.exclusion', N'U') IS NULL
BEGIN
    CREATE TABLE audit.exclusion
    (
        exclusion_id        bigint IDENTITY(1,1) NOT NULL,
        hypothesis_id       varchar(16) NULL,
        exclusion_scope     varchar(80) NOT NULL,
        entity_key          nvarchar(300) NOT NULL,
        start_date          date NULL,
        end_date            date NULL,
        reason_code         varchar(120) NOT NULL,
        reason_description  nvarchar(2500) NOT NULL,
        source_reference    nvarchar(1000) NULL,
        frozen              bit NOT NULL
            CONSTRAINT DF_audit_exclusion_frozen DEFAULT 1,

        CONSTRAINT PK_audit_exclusion
            PRIMARY KEY (exclusion_id),

        CONSTRAINT FK_audit_exclusion_hypothesis
            FOREIGN KEY (hypothesis_id)
            REFERENCES ref.hypothesis(hypothesis_id)
    );

    CREATE INDEX IX_audit_exclusion_hypothesis
        ON audit.exclusion(hypothesis_id, start_date, end_date);
END;
GO

IF OBJECT_ID(N'audit.artifact', N'U') IS NULL
BEGIN
    CREATE TABLE audit.artifact
    (
        artifact_id         bigint IDENTITY(1,1) NOT NULL,
        run_id              bigint NULL,
        hypothesis_id       varchar(16) NULL,
        artifact_name       nvarchar(300) NOT NULL,
        artifact_type       varchar(80) NOT NULL,
        repository_path     nvarchar(1000) NULL,
        sha256              char(64) NULL,
        description         nvarchar(2000) NULL,
        created_at_utc      datetime2(0) NOT NULL
            CONSTRAINT DF_audit_artifact_created
            DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_audit_artifact
            PRIMARY KEY (artifact_id),

        CONSTRAINT FK_audit_artifact_run
            FOREIGN KEY (run_id)
            REFERENCES audit.pipeline_run(run_id),

        CONSTRAINT FK_audit_artifact_hypothesis
            FOREIGN KEY (hypothesis_id)
            REFERENCES ref.hypothesis(hypothesis_id)
    );
END;
GO

IF OBJECT_ID(N'results.hypothesis_result', N'U') IS NULL
BEGIN
    CREATE TABLE results.hypothesis_result
    (
        result_id                   bigint IDENTITY(1,1) NOT NULL,
        hypothesis_id               varchar(16) NOT NULL,
        component                   nvarchar(120) NOT NULL,
        result_version              nvarchar(120) NOT NULL,
        sample_start                date NULL,
        sample_end                  date NULL,
        estimand                    nvarchar(500) NOT NULL,
        estimate                    float NULL,
        standard_error              float NULL,
        ci_low                      float NULL,
        ci_high                     float NULL,
        test_statistic              float NULL,
        reference_df                int NULL,
        raw_p_value                 float NULL,
        adjusted_p_value            float NULL,
        multiple_testing_method     nvarchar(100) NULL,
        n_observations              bigint NULL,
        n_clusters_primary          bigint NULL,
        n_clusters_secondary        bigint NULL,
        economic_effect             float NULL,
        economic_effect_unit        nvarchar(120) NULL,
        decision                    varchar(64) NOT NULL,
        primary_secondary           varchar(32) NOT NULL,
        covariance_method           nvarchar(300) NULL,
        source_report_path          nvarchar(1000) NULL,
        source_report_sha256        char(64) NULL,
        preregistration_sha256      char(64) NULL,
        frozen                      bit NOT NULL
            CONSTRAINT DF_results_hypothesis_result_frozen DEFAULT 1,
        recorded_at_utc             datetime2(0) NOT NULL
            CONSTRAINT DF_results_hypothesis_result_recorded
            DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_results_hypothesis_result
            PRIMARY KEY (result_id),

        CONSTRAINT FK_results_hypothesis_result_hypothesis
            FOREIGN KEY (hypothesis_id)
            REFERENCES ref.hypothesis(hypothesis_id),

        CONSTRAINT UQ_results_hypothesis_result
            UNIQUE (hypothesis_id, component, result_version),

        CONSTRAINT CK_results_hypothesis_result_p
            CHECK (
                (raw_p_value IS NULL OR (raw_p_value BETWEEN 0 AND 1))
                AND
                (adjusted_p_value IS NULL OR
                    (adjusted_p_value BETWEEN 0 AND 1))
            ),

        CONSTRAINT CK_results_hypothesis_result_type
            CHECK (
                primary_secondary IN
                ('PRIMARY','SECONDARY','ROBUSTNESS','DESCRIPTIVE')
            )
    );

    CREATE INDEX IX_results_hypothesis_result_hypothesis
        ON results.hypothesis_result
        (hypothesis_id, primary_secondary, recorded_at_utc);
END;
GO

IF OBJECT_ID(N'results.result_breakdown', N'U') IS NULL
BEGIN
    CREATE TABLE results.result_breakdown
    (
        breakdown_id        bigint IDENTITY(1,1) NOT NULL,
        hypothesis_id       varchar(16) NOT NULL,
        result_version      nvarchar(120) NOT NULL,
        breakdown_type      varchar(80) NOT NULL,
        breakdown_value     nvarchar(200) NOT NULL,
        metric_name         nvarchar(200) NOT NULL,
        metric_value        float NULL,
        n_observations      bigint NULL,
        notes               nvarchar(1500) NULL,

        CONSTRAINT PK_results_result_breakdown
            PRIMARY KEY (breakdown_id),

        CONSTRAINT FK_results_result_breakdown_hypothesis
            FOREIGN KEY (hypothesis_id)
            REFERENCES ref.hypothesis(hypothesis_id),

        CONSTRAINT UQ_results_result_breakdown
            UNIQUE
            (
                hypothesis_id,
                result_version,
                breakdown_type,
                breakdown_value,
                metric_name
            )
    );

    CREATE INDEX IX_results_result_breakdown_hypothesis
        ON results.result_breakdown
        (hypothesis_id, breakdown_type, breakdown_value);
END;
GO

CREATE OR ALTER FUNCTION ref.fn_student_t_two_sided_p
(
    @t_stat float,
    @degrees_freedom int
)
RETURNS float
AS
BEGIN
    DECLARE @abs_t float;
    DECLARE @t_lower float;
    DECLARE @p_upper float;
    DECLARE @t_upper float;
    DECLARE @p_lower float;
    DECLARE @result float;

    IF @t_stat IS NULL OR @degrees_freedom IS NULL
        RETURN NULL;

    IF @degrees_freedom < 1 OR @degrees_freedom > 600
        RETURN NULL;

    SET @abs_t = ABS(@t_stat);

    IF @abs_t = 0
        RETURN 1.0;

    SELECT TOP (1)
        @t_lower = critical_abs_t,
        @p_upper = two_sided_p
    FROM ref.student_t_two_sided_lookup
    WHERE degrees_freedom = @degrees_freedom
      AND critical_abs_t <= @abs_t
    ORDER BY critical_abs_t DESC;

    SELECT TOP (1)
        @t_upper = critical_abs_t,
        @p_lower = two_sided_p
    FROM ref.student_t_two_sided_lookup
    WHERE degrees_freedom = @degrees_freedom
      AND critical_abs_t >= @abs_t
    ORDER BY critical_abs_t ASC;

    IF @t_lower IS NULL
        RETURN 1.0;

    IF @t_upper IS NULL
    BEGIN
        SELECT @result = MIN(two_sided_p)
        FROM ref.student_t_two_sided_lookup
        WHERE degrees_freedom = @degrees_freedom;
        RETURN @result;
    END;

    IF @t_upper = @t_lower
        RETURN @p_lower;

    SET @result =
        @p_upper
        + (
            (@abs_t - @t_lower)
            * (@p_lower - @p_upper)
            / (@t_upper - @t_lower)
        );

    IF @result < 0 SET @result = 0;
    IF @result > 1 SET @result = 1;

    RETURN @result;
END;
GO

CREATE OR ALTER FUNCTION ref.fn_normal_two_sided_p
(
    @z_stat float
)
RETURNS float
AS
BEGIN
    DECLARE @abs_z float;
    DECLARE @z_lower float;
    DECLARE @p_upper float;
    DECLARE @z_upper float;
    DECLARE @p_lower float;
    DECLARE @result float;

    IF @z_stat IS NULL
        RETURN NULL;

    SET @abs_z = ABS(@z_stat);

    IF @abs_z = 0
        RETURN 1.0;

    SELECT TOP (1)
        @z_lower = critical_abs_z,
        @p_upper = two_sided_p
    FROM ref.normal_two_sided_lookup
    WHERE critical_abs_z <= @abs_z
    ORDER BY critical_abs_z DESC;

    SELECT TOP (1)
        @z_upper = critical_abs_z,
        @p_lower = two_sided_p
    FROM ref.normal_two_sided_lookup
    WHERE critical_abs_z >= @abs_z
    ORDER BY critical_abs_z ASC;

    IF @z_lower IS NULL
        RETURN 1.0;

    IF @z_upper IS NULL
    BEGIN
        SELECT @result = MIN(two_sided_p)
        FROM ref.normal_two_sided_lookup;
        RETURN @result;
    END;

    IF @z_upper = @z_lower
        RETURN @p_lower;

    SET @result =
        @p_upper
        + (
            (@abs_z - @z_lower)
            * (@p_lower - @p_upper)
            / (@z_upper - @z_lower)
        );

    IF @result < 0 SET @result = 0;
    IF @result > 1 SET @result = 1;

    RETURN @result;
END;
GO

CREATE OR ALTER FUNCTION ref.fn_student_t_critical
(
    @degrees_freedom int,
    @two_sided_alpha float
)
RETURNS float
AS
BEGIN
    DECLARE @exact float;
    DECLARE @p_lower float;
    DECLARE @t_upper float;
    DECLARE @p_upper float;
    DECLARE @t_lower float;
    DECLARE @result float;

    IF @degrees_freedom IS NULL
       OR @degrees_freedom < 1
       OR @degrees_freedom > 600
       OR @two_sided_alpha IS NULL
       OR @two_sided_alpha <= 0
       OR @two_sided_alpha > 1
        RETURN NULL;

    SELECT @exact = critical_abs_t
    FROM ref.student_t_two_sided_lookup
    WHERE degrees_freedom = @degrees_freedom
      AND ABS(two_sided_p - @two_sided_alpha) < 1e-15;

    IF @exact IS NOT NULL
        RETURN @exact;

    SELECT TOP (1)
        @p_lower = two_sided_p,
        @t_upper = critical_abs_t
    FROM ref.student_t_two_sided_lookup
    WHERE degrees_freedom = @degrees_freedom
      AND two_sided_p < @two_sided_alpha
    ORDER BY two_sided_p DESC;

    SELECT TOP (1)
        @p_upper = two_sided_p,
        @t_lower = critical_abs_t
    FROM ref.student_t_two_sided_lookup
    WHERE degrees_freedom = @degrees_freedom
      AND two_sided_p > @two_sided_alpha
    ORDER BY two_sided_p ASC;

    IF @p_lower IS NULL OR @p_upper IS NULL
        RETURN NULL;

    SET @result =
        @t_upper
        + (
            (@two_sided_alpha - @p_lower)
            * (@t_lower - @t_upper)
            / (@p_upper - @p_lower)
        );

    RETURN @result;
END;
GO

CREATE OR ALTER VIEW bi.vw_variable_catalog
AS
SELECT
    h.hypothesis_id,
    h.hypothesis_name,
    m.variable_role,
    v.variable_name,
    v.display_name,
    v.description,
    v.grain,
    v.unit,
    v.formula_description,
    v.lookahead_safe,
    v.source_object,
    v.source_column,
    v.educational_notes
FROM ref.hypothesis_variable_map AS m
JOIN ref.hypothesis AS h
  ON h.hypothesis_id = m.hypothesis_id
JOIN ref.variable_catalog AS v
  ON v.variable_id = m.variable_id;
GO

CREATE OR ALTER VIEW bi.vw_research_summary
AS
WITH ranked AS
(
    SELECT
        r.*,
        ROW_NUMBER() OVER
        (
            PARTITION BY r.hypothesis_id, r.component
            ORDER BY r.recorded_at_utc DESC, r.result_id DESC
        ) AS rn
    FROM results.hypothesis_result AS r
)
SELECT
    h.hypothesis_id,
    h.parent_hypothesis_id,
    h.hypothesis_name,
    h.research_question,
    h.primary_outcome,
    h.primary_test,
    h.alpha,
    h.status AS hypothesis_status,
    h.sample_start,
    h.sample_end,
    r.component,
    r.estimand,
    r.estimate,
    r.standard_error,
    r.ci_low,
    r.ci_high,
    r.test_statistic,
    r.reference_df,
    r.raw_p_value,
    r.adjusted_p_value,
    r.n_observations,
    r.n_clusters_primary,
    r.n_clusters_secondary,
    r.economic_effect,
    r.economic_effect_unit,
    r.decision,
    r.primary_secondary,
    r.covariance_method,
    r.result_version
FROM ref.hypothesis AS h
LEFT JOIN ranked AS r
  ON r.hypothesis_id = h.hypothesis_id
 AND r.rn = 1;
GO
