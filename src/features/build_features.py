"""
Feature Engineering Engine for SaaS Customer Churn Prediction.
Extracts behavioral, tenure, and monetary features from DuckDB ledger events
while strictly preventing temporal lookahead leakage.
"""

from pathlib import Path
import duckdb
import pandas as pd


def extract_churn_features(
    db_path: str = "data/processed/analytics.duckdb",
    cutoff_date: str = "2025-01-01"
) -> pd.DataFrame:
    """
    Extracts customer feature vectors evaluated strictly at or before cutoff_date,
    and constructs the target variable 'is_churned' observed after cutoff_date.
    """
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database not found at {db_file.resolve()}")

    con = duckdb.connect(str(db_file))

    query = f"""
    WITH pre_cutoff_events AS (
        -- Step 1: Historical events strictly before cutoff date (Features ONLY)
        SELECT 
            customer_id,
            event_date,
            cohort_month,
            tier,
            mrr,
            event_type
        FROM subscription_events
        WHERE event_date < '{cutoff_date}'
    ),

    customer_aggregates AS (
        -- Step 2: Compute RFM and behavioral features per account
        SELECT 
            customer_id,
            MIN(cohort_month) AS initial_cohort_month,
            MAX(tier) AS latest_tier,
            -- Tenure in months prior to cutoff
            ROUND((EPOCH(CAST('{cutoff_date}' AS DATE)) - EPOCH(MIN(event_date))) / (86400 * 30.4375), 1) AS tenure_months,
            -- Monetary features
            ROUND(AVG(mrr), 2) AS avg_mrr,
            ROUND(MAX(mrr), 2) AS max_mrr,
            ROUND(SUM(mrr), 2) AS lifetime_mrr,
            -- MRR volatility
            COALESCE(ROUND(STDDEV(mrr), 2), 0.0) AS mrr_stddev,
            -- Total events and behavioral movements
            COUNT(*) AS total_event_count,
            COUNT(CASE WHEN event_type = 'upgrade' THEN 1 END) AS total_upgrades,
            COUNT(CASE WHEN event_type = 'downgrade' THEN 1 END) AS total_downgrades
        FROM pre_cutoff_events
        GROUP BY customer_id
    ),

    post_cutoff_churn AS (
        -- Step 3: Observe target variable (churn after cutoff date)
        SELECT 
            customer_id,
            MAX(CASE WHEN event_type = 'churn' THEN 1 ELSE 0 END) AS is_churned
        FROM subscription_events
        WHERE event_date >= '{cutoff_date}'
        GROUP BY customer_id
    )

    -- Step 4: Join features with the future ground-truth target
    SELECT 
        c.customer_id,
        c.initial_cohort_month,
        c.latest_tier,
        c.tenure_months,
        c.avg_mrr,
        c.max_mrr,
        c.lifetime_mrr,
        c.mrr_stddev,
        c.total_event_count,
        c.total_upgrades,
        c.total_downgrades,
        COALESCE(p.is_churned, 0) AS is_churned
    FROM customer_aggregates c
    LEFT JOIN post_cutoff_churn p 
        ON c.customer_id = p.customer_id
    WHERE c.tenure_months > 0;
    """

    df_features = con.execute(query).df()
    con.close()
    return df_features


if __name__ == "__main__":
    df = extract_churn_features()
    print("=" * 60)
    print("FEATURE EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Dataset Shape: {df.shape}")
    print("\nFeature Columns:")
    print(df.columns.tolist())
    print("\nTarget Variable Distribution:")
    print(df["is_churned"].value_counts(dropna=False))
    print(f"\nChurn Rate: {df['is_churned'].mean() * 100:.2f}%")