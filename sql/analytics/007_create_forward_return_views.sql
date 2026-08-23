SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

CREATE OR ALTER VIEW
    analytics.v_security_monthly_forward_return_1m
AS
SELECT
    portfolio.analysis_month_number,
    portfolio.month_start_date AS ranking_month_start_date,
    portfolio.month_end_date AS ranking_month_end_date,
    portfolio.security_key,
    portfolio.company_name_reference,
    portfolio.project_ticker AS ranking_project_ticker,
    portfolio.provider_symbol AS ranking_provider_symbol,
    portfolio.momentum_12_1_start_date,
    portfolio.momentum_12_1_end_date,
    portfolio.momentum_12_1,
    portfolio.eligible_security_count,
    portfolio.momentum_rank_desc,
    portfolio.momentum_rank_asc,
    portfolio.momentum_decile,
    portfolio.momentum_portfolio,
    portfolio.decile_security_count,
    portfolio.equal_weight,
    portfolio.month_end_date AS holding_start_date,
    next_month.month_end_date
        AS target_holding_end_date,
    end_price.price_date AS realized_holding_end_date,
    portfolio.adjusted_close
        AS holding_start_adjusted_close,
    end_price.adjusted_close
        AS holding_end_adjusted_close,
    end_price.project_ticker AS holding_end_project_ticker,
    end_price.provider_symbol AS holding_end_provider_symbol,
    CAST(
        CASE
            WHEN next_month.month_end_date IS NULL
            THEN 'OUT_OF_SCOPE'
            WHEN end_price.price_date
                = next_month.month_end_date
            THEN 'EXACT_MONTH_END'
            WHEN end_price.price_date
                = portfolio.month_end_date
            THEN 'IMMEDIATE_EXIT'
            WHEN end_price.price_date
                < next_month.month_end_date
            THEN 'EARLY_EXIT'
            ELSE 'UNAVAILABLE'
        END
        AS varchar(32)
    ) AS holding_end_status,
    CAST(
        CASE
            WHEN next_month.month_end_date IS NOT NULL
             AND end_price.price_date IS NOT NULL
             AND portfolio.adjusted_close > 0
            THEN
                CAST(end_price.adjusted_close AS float)
                / CAST(portfolio.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS forward_return_1m,
    CAST(
        CASE
            WHEN next_month.month_end_date IS NOT NULL
             AND end_price.price_date IS NOT NULL
             AND portfolio.adjusted_close > 0
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS forward_return_1m_complete,
    CAST(
        CASE
            WHEN end_price.price_date
                = next_month.month_end_date
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS holding_end_is_exact_month_end,
    CAST(
        CASE
            WHEN next_month.month_end_date IS NOT NULL
             AND end_price.price_date
                > portfolio.month_end_date
             AND end_price.price_date
                < next_month.month_end_date
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS holding_end_is_early_exit,
    CAST(
        CASE
            WHEN next_month.month_end_date IS NOT NULL
             AND end_price.price_date
                = portfolio.month_end_date
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS holding_end_is_immediate_exit,
    CAST(
        CASE
            WHEN next_month.month_end_date IS NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS out_of_scope_right_censored
FROM analytics.v_security_monthly_momentum_portfolio
    AS portfolio
LEFT JOIN analytics.v_spy_month_end_calendar
    AS next_month
  ON next_month.analysis_month_number
   = portfolio.analysis_month_number + 1
OUTER APPLY (
    SELECT TOP (1)
        price.price_date,
        price.project_ticker,
        price.provider_symbol,
        price.adjusted_close
    FROM core.daily_security_price AS price
    WHERE price.security_key = portfolio.security_key
      AND price.price_date >= portfolio.month_end_date
      AND price.price_date <= next_month.month_end_date
    ORDER BY
        price.price_date DESC,
        price.project_ticker ASC
) AS end_price;
GO

CREATE OR ALTER VIEW
    analytics.v_benchmark_monthly_forward_return_1m
AS
WITH ranking_months AS (
    SELECT DISTINCT
        portfolio.analysis_month_number,
        portfolio.month_start_date,
        portfolio.month_end_date
    FROM analytics.v_security_monthly_momentum_portfolio
        AS portfolio
)
SELECT
    ranking_month.analysis_month_number,
    ranking_month.month_start_date
        AS ranking_month_start_date,
    ranking_month.month_end_date
        AS ranking_month_end_date,
    current_price.security_key,
    current_price.project_ticker,
    current_price.provider_symbol,
    current_price.benchmark_name,
    current_price.series_type,
    ranking_month.month_end_date AS holding_start_date,
    next_calendar.month_end_date
        AS target_holding_end_date,
    next_price.month_end_date AS realized_holding_end_date,
    current_price.adjusted_close
        AS holding_start_adjusted_close,
    next_price.adjusted_close
        AS holding_end_adjusted_close,
    CAST(
        CASE
            WHEN next_calendar.month_end_date IS NULL
            THEN 'OUT_OF_SCOPE'
            WHEN next_price.month_end_date
                = next_calendar.month_end_date
            THEN 'EXACT_MONTH_END'
            ELSE 'UNAVAILABLE'
        END
        AS varchar(32)
    ) AS holding_end_status,
    CAST(
        CASE
            WHEN next_price.month_end_date
                = next_calendar.month_end_date
             AND current_price.adjusted_close > 0
            THEN
                CAST(next_price.adjusted_close AS float)
                / CAST(current_price.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS forward_return_1m,
    CAST(
        CASE
            WHEN next_price.month_end_date
                = next_calendar.month_end_date
             AND current_price.adjusted_close > 0
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS forward_return_1m_complete,
    CAST(
        CASE
            WHEN next_calendar.month_end_date IS NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS out_of_scope_right_censored
FROM ranking_months AS ranking_month
INNER JOIN analytics.benchmark_month_end_snapshot
    AS current_price
  ON current_price.analysis_month_number
   = ranking_month.analysis_month_number
LEFT JOIN analytics.v_spy_month_end_calendar
    AS next_calendar
  ON next_calendar.analysis_month_number
   = ranking_month.analysis_month_number + 1
LEFT JOIN analytics.benchmark_month_end_snapshot
    AS next_price
  ON next_price.analysis_month_number
   = ranking_month.analysis_month_number + 1
 AND next_price.security_key = current_price.security_key
 AND next_price.project_ticker
   = current_price.project_ticker;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_decile_forward_return_1m
AS
SELECT
    holding.analysis_month_number,
    holding.ranking_month_start_date,
    holding.ranking_month_end_date,
    holding.target_holding_end_date,
    holding.momentum_decile,
    holding.momentum_portfolio,
    COUNT_BIG(*) AS assigned_security_count,
    SUM(
        CAST(holding.forward_return_1m_complete AS int)
    ) AS complete_security_count,
    SUM(
        CAST(holding.holding_end_is_exact_month_end AS int)
    ) AS exact_month_end_count,
    SUM(
        CAST(holding.holding_end_is_early_exit AS int)
    ) AS early_exit_count,
    SUM(
        CAST(holding.holding_end_is_immediate_exit AS int)
    ) AS immediate_exit_count,
    SUM(
        CAST(holding.out_of_scope_right_censored AS int)
    ) AS right_censored_count,
    SUM(holding.equal_weight) AS assigned_weight_sum,
    SUM(
        CASE
            WHEN holding.forward_return_1m_complete = 1
            THEN holding.equal_weight
            ELSE CAST(0 AS decimal(38, 18))
        END
    ) AS complete_weight_sum,
    CAST(
        CASE
            WHEN SUM(
                CAST(
                    holding.forward_return_1m_complete
                    AS int
                )
            ) = COUNT_BIG(*)
            THEN SUM(
                CAST(holding.equal_weight AS float)
                * CAST(holding.forward_return_1m AS float)
            )
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS equal_weight_forward_return_1m,
    CAST(
        CASE
            WHEN SUM(
                CAST(
                    holding.forward_return_1m_complete
                    AS int
                )
            ) = COUNT_BIG(*)
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS forward_return_1m_complete
FROM analytics.v_security_monthly_forward_return_1m
    AS holding
GROUP BY
    holding.analysis_month_number,
    holding.ranking_month_start_date,
    holding.ranking_month_end_date,
    holding.target_holding_end_date,
    holding.momentum_decile,
    holding.momentum_portfolio;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_long_short_forward_return_1m
AS
SELECT
    decile.analysis_month_number,
    MAX(decile.ranking_month_start_date)
        AS ranking_month_start_date,
    MAX(decile.ranking_month_end_date)
        AS ranking_month_end_date,
    MAX(decile.target_holding_end_date)
        AS target_holding_end_date,
    MAX(
        CASE
            WHEN decile.momentum_decile = 10
            THEN decile.assigned_security_count
        END
    ) AS winner_security_count,
    MAX(
        CASE
            WHEN decile.momentum_decile = 1
            THEN decile.assigned_security_count
        END
    ) AS loser_security_count,
    MAX(
        CASE
            WHEN decile.momentum_decile = 10
            THEN decile.equal_weight_forward_return_1m
        END
    ) AS winner_forward_return_1m,
    MAX(
        CASE
            WHEN decile.momentum_decile = 1
            THEN decile.equal_weight_forward_return_1m
        END
    ) AS loser_forward_return_1m,
    CAST(
        CASE
            WHEN MIN(
                CASE
                    WHEN decile.momentum_decile IN (1, 10)
                    THEN CAST(
                        decile.forward_return_1m_complete
                        AS int
                    )
                    ELSE 1
                END
            ) = 1
            THEN
                CAST(
                    MAX(
                        CASE
                            WHEN decile.momentum_decile = 10
                            THEN decile
                                .equal_weight_forward_return_1m
                        END
                    )
                    AS float
                )
                - CAST(
                    MAX(
                        CASE
                            WHEN decile.momentum_decile = 1
                            THEN decile
                                .equal_weight_forward_return_1m
                        END
                    )
                    AS float
                )
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS winner_minus_loser_forward_return_1m,
    CAST(
        CASE
            WHEN MIN(
                CASE
                    WHEN decile.momentum_decile IN (1, 10)
                    THEN CAST(
                        decile.forward_return_1m_complete
                        AS int
                    )
                    ELSE 1
                END
            ) = 1
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS forward_return_1m_complete
FROM analytics.v_momentum_decile_forward_return_1m
    AS decile
GROUP BY decile.analysis_month_number;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_monthly_performance_1m
AS
WITH benchmark AS (
    SELECT
        benchmark_return.analysis_month_number,
        MAX(
            CASE
                WHEN benchmark_return.series_type = 'ETF'
                THEN benchmark_return.forward_return_1m
            END
        ) AS spy_forward_return_1m,
        MAX(
            CASE
                WHEN benchmark_return.series_type = 'INDEX'
                THEN benchmark_return.forward_return_1m
            END
        ) AS sp500_index_forward_return_1m,
        MIN(
            CAST(
                benchmark_return.forward_return_1m_complete
                AS int
            )
        ) AS benchmark_return_complete
    FROM analytics.v_benchmark_monthly_forward_return_1m
        AS benchmark_return
    GROUP BY benchmark_return.analysis_month_number
)
SELECT
    long_short.analysis_month_number,
    long_short.ranking_month_start_date,
    long_short.ranking_month_end_date,
    long_short.target_holding_end_date,
    long_short.winner_security_count,
    long_short.loser_security_count,
    long_short.winner_forward_return_1m,
    long_short.loser_forward_return_1m,
    long_short.winner_minus_loser_forward_return_1m,
    benchmark.spy_forward_return_1m,
    benchmark.sp500_index_forward_return_1m,
    CAST(
        CASE
            WHEN long_short.forward_return_1m_complete = 1
             AND benchmark.benchmark_return_complete = 1
            THEN
                CAST(
                    long_short.winner_forward_return_1m
                    AS float
                )
                - CAST(
                    benchmark.spy_forward_return_1m
                    AS float
                )
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS winner_minus_spy_forward_return_1m,
    CAST(
        CASE
            WHEN long_short.forward_return_1m_complete = 1
             AND benchmark.benchmark_return_complete = 1
            THEN
                CAST(
                    long_short.loser_forward_return_1m
                    AS float
                )
                - CAST(
                    benchmark.spy_forward_return_1m
                    AS float
                )
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS loser_minus_spy_forward_return_1m,
    CAST(
        CASE
            WHEN long_short.forward_return_1m_complete = 1
             AND benchmark.benchmark_return_complete = 1
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS performance_1m_complete
FROM analytics.v_momentum_long_short_forward_return_1m
    AS long_short
INNER JOIN benchmark
  ON benchmark.analysis_month_number
   = long_short.analysis_month_number;
GO