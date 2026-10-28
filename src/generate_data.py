"""
Synthetic SaaS Subscription Event Generator.
Simulates multi-month customer lifecycles with realistic churn cliffs,
tier upgrades/downgrades, and exports directly to Parquet and DuckDB.
"""

from datetime import datetime, timedelta
import random
import duckdb
import numpy as np
import pandas as pd

# Set deterministic seed for reproducibility
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

TIER_PRICING = {
    "Starter": 29.0,
    "Pro": 99.0,
    "Enterprise": 299.0
}

TIER_WEIGHTS = [0.60, 0.30, 0.10]  # 60% Starter, 30% Pro, 10% Enterprise
TIERS = list(TIER_PRICING.keys())


def generate_cohort_customers(
    start_date: datetime,
    end_date: datetime,
    customers_per_month: int = 250
) -> pd.DataFrame:
    """Generates initial customer signups distributed across monthly cohorts."""
    records = []
    current_cohort = start_date
    cust_counter = 1000

    while current_cohort <= end_date:
        for _ in range(customers_per_month):
            cust_counter += 1
            # Random signup day within the month
            day_offset = random.randint(0, 27)
            signup_date = current_cohort + timedelta(days=day_offset)
            initial_tier = np.random.choice(TIERS, p=TIER_WEIGHTS)
            
            records.append({
                "customer_id": f"CUST-{cust_counter}",
                "signup_date": signup_date.date(),
                "cohort_month": current_cohort.strftime("%Y-%m"),
                "current_tier": initial_tier,
                "current_mrr": TIER_PRICING[initial_tier],
                "is_active": True
            })
        
        # Advance by 1 month
        if current_cohort.month == 12:
            current_cohort = current_cohort.replace(year=current_cohort.year + 1, month=1)
        else:
            current_cohort = current_cohort.replace(month=current_cohort.month + 1)

    return pd.DataFrame(records)


def simulate_monthly_events(
    customers_df: pd.DataFrame,
    simulation_end: datetime
) -> pd.DataFrame:
    """
    Simulates monthly recurring renewal cycles, realistic month-2 churn cliff,
    upgrades, downgrades, and churn events.
    """
    events = []

    for _, row in customers_df.iterrows():
        cust_id = row["customer_id"]
        signup_date = row["signup_date"]
        current_tier = row["current_tier"]
        current_mrr = row["current_mrr"]
        
        # Emit initial 'new' event
        events.append({
            "event_id": f"EVT-{len(events) + 1:07d}",
            "customer_id": cust_id,
            "cohort_month": row["cohort_month"],
            "event_date": signup_date,
            "tier": current_tier,
            "mrr": current_mrr,
            "event_type": "new"
        })

        # Progress month by month
        curr_billing_date = signup_date + timedelta(days=30)
        tenure_month = 1
        active = True

        while curr_billing_date <= simulation_end.date() and active:
            rand_val = random.random()

            # Churn cliff logic: High churn in early months (trial/onboarding drop-off)
            if tenure_month == 1:
                churn_prob = 0.18  # 18% churn in Month 1 -> 2
            elif tenure_month <= 3:
                churn_prob = 0.08  # 8% churn in Months 2-3
            else:
                churn_prob = 0.025 # Stabilized long-term churn: 2.5%

            if rand_val < churn_prob:
                # Customer churns
                events.append({
                    "event_id": f"EVT-{len(events) + 1:07d}",
                    "customer_id": cust_id,
                    "cohort_month": row["cohort_month"],
                    "event_date": curr_billing_date,
                    "tier": current_tier,
                    "mrr": 0.0,
                    "event_type": "churn"
                })
                active = False
            else:
                # Upgrades and Downgrades
                change_roll = random.random()
                event_type = "renew"

                if change_roll < 0.04 and current_tier != "Enterprise":
                    # Upgrade tier
                    current_tier = "Pro" if current_tier == "Starter" else "Enterprise"
                    current_mrr = TIER_PRICING[current_tier]
                    event_type = "upgrade"
                elif change_roll > 0.98 and current_tier != "Starter":
                    # Downgrade tier
                    current_tier = "Starter" if current_tier == "Pro" else "Pro"
                    current_mrr = TIER_PRICING[current_tier]
                    event_type = "downgrade"

                events.append({
                    "event_id": f"EVT-{len(events) + 1:07d}",
                    "customer_id": cust_id,
                    "cohort_month": row["cohort_month"],
                    "event_date": curr_billing_date,
                    "tier": current_tier,
                    "mrr": current_mrr,
                    "event_type": event_type
                })

            curr_billing_date += timedelta(days=30)
            tenure_month += 1

    return pd.DataFrame(events)


def build_duckdb_storage(events_df: pd.DataFrame, parquet_path: str, duckdb_path: str):
    """Saves raw event logs to columnar Parquet and exposes it through DuckDB views."""
    # Write optimized Parquet file
    events_df.to_parquet(parquet_path, engine="pyarrow", index=False)
    print(f"[✓] Saved {len(events_df):,} events to Parquet: {parquet_path}")

    # Initialize DuckDB relational file and register Parquet view
    con = duckdb.connect(duckdb_path)
    con.execute(f"""
        CREATE OR REPLACE TABLE subscription_events AS 
        SELECT 
            event_id,
            customer_id,
            cohort_month,
            CAST(event_date AS DATE) AS event_date,
            tier,
            CAST(mrr AS DOUBLE) AS mrr,
            event_type
        FROM read_parquet('{parquet_path}');
    """)
    
    count_res = con.execute("SELECT COUNT(*) FROM subscription_events;").fetchone()[0]
    print(f"[✓] Initialized DuckDB table 'subscription_events' at {duckdb_path} with {count_res:,} rows.")
    con.close()


def main():
    print("Starting SaaS subscription event generation...")
    sim_start = datetime(2024, 1, 1)
    sim_end = datetime(2025, 6, 1)

    print(f"Generating cohorts from {sim_start.strftime('%Y-%m')} to {sim_end.strftime('%Y-%m')}...")
    cohorts_df = generate_cohort_customers(sim_start, sim_end, customers_per_month=300)
    print(f"Generated {len(cohorts_df):,} distinct customer accounts.")

    print("Simulating event trajectories (renewals, cliffs, upgrades, downgrades)...")
    events_df = simulate_monthly_events(cohorts_df, sim_end)

    parquet_file = "data/raw/subscription_events.parquet"
    db_file = "data/processed/analytics.duckdb"
    
    build_duckdb_storage(events_df, parquet_file, db_file)
    print("[✓] Step 2 data pipeline generation completed successfully.")


if __name__ == "__main__":
    main()
    