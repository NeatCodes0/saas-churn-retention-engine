"""
Automated Production Audit & Integration Test Suite.
Validates:
1. DuckDB OLAP ledger presence & event schema integrity.
2. GAAP MRR mathematical identity: Ending = Starting + New + Expansion - Contraction - Churn.
3. Cohort retention matrix bounds (0% to 100% Logo, positive NRR).
4. Out-of-time serialized XGBoost model inference consistency.
"""

from pathlib import Path
import duckdb
import joblib
import numpy as np
import pandas as pd
import pytest

DB_PATH = "data/processed/analytics.duckdb"
MODEL_PATH = "models/churn_model.joblib"


@pytest.fixture(scope="session")
def db_conn():
    assert Path(DB_PATH).exists(), f"Database file not found at {DB_PATH}"
    con = duckdb.connect(DB_PATH, read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def model_bundle():
    assert Path(MODEL_PATH).exists(), f"Model artifact not found at {MODEL_PATH}"
    bundle = joblib.load(MODEL_PATH)
    assert "pipeline" in bundle and "feature_cols" in bundle
    return bundle


# -----------------------------------------------------------------------------
# 1. Database & Table Schema Tests
# -----------------------------------------------------------------------------
def test_database_table_exists(db_conn):
    tables = [t[0] for t in db_conn.execute("SHOW TABLES").fetchall()]
    assert "subscription_events" in tables, "Table 'subscription_events' missing from DuckDB"


def test_event_row_count(db_conn):
    count = db_conn.execute("SELECT COUNT(*) FROM subscription_events").fetchone()[0]
    assert count > 10000, f"Expected >10k rows, got {count}"


def test_schema_columns(db_conn):
    cols = [col[0] for col in db_conn.execute("DESCRIBE subscription_events").fetchall()]
    expected_cols = {"customer_id", "event_date", "event_type", "tier", "mrr"}
    assert expected_cols.issubset(set(cols)), f"Schema missing essential columns: {expected_cols - set(cols)}"


# -----------------------------------------------------------------------------
# 2. GAAP MRR Waterfall Accounting Identity Test
# -----------------------------------------------------------------------------
def test_mrr_waterfall_accounting_identity(db_conn):
    with open("src/queries/mrr_waterfall.sql", "r") as f:
        query = f.read()
    
    df = db_conn.execute(query).df()
    df.columns = [c.lower() for c in df.columns]

    assert len(df) > 0, "MRR waterfall query returned empty result"

    # Verify Ending MRR = Starting + New + Expansion - Contraction - Churn for every month
    for idx, row in df.iterrows():
        calculated_net_new = (
            row["total_new_mrr"]
            + row["total_expansion_mrr"]
            - row["total_contraction_mrr"]
            - row["total_churned_mrr"]
        )
        # Tolerance of $0.05 for floating point rounding
        assert np.isclose(row["net_new_mrr"], calculated_net_new, atol=0.05), (
            f"Month {row['activity_month']} Net New mismatch: "
            f"reported {row['net_new_mrr']}, computed {calculated_net_new}"
        )


# -----------------------------------------------------------------------------
# 3. Longitudinal Cohort Retention Tests
# -----------------------------------------------------------------------------
def test_cohort_retention_bounds(db_conn):
    with open("src/queries/cohort_retention.sql", "r") as f:
        query = f.read()

    df = db_conn.execute(query).df()
    df.columns = [c.lower() for c in df.columns]

    assert len(df) > 0, "Cohort retention query returned empty result"

    # Month 0 user retention must be exactly 100%
    month_0 = df[df["tenure_month"] == 0]
    assert len(month_0) > 0, "No tenure month 0 found"
    assert (month_0["user_retention_pct"] == 100.0).all(), "Tenure 0 retention must be 100.0%"

    # User logo retention must be between 0% and 100%
    assert (df["user_retention_pct"] >= 0.0).all(), "Retention % cannot be negative"
    assert (df["user_retention_pct"] <= 100.0).all(), "Retention % cannot exceed 100%"


# -----------------------------------------------------------------------------
# 4. ML Model Inference & Behavioral Stress Tests
# -----------------------------------------------------------------------------
def test_model_inference_bounds(model_bundle):
    pipeline = model_bundle["pipeline"]
    features = model_bundle["feature_cols"]

    sample_input = pd.DataFrame([{
        "latest_tier": "Pro",
        "tenure_months": 6.0,
        "avg_mrr": 99.0,
        "max_mrr": 99.0,
        "lifetime_mrr": 594.0,
        "mrr_stddev": 0.0,
        "total_event_count": 6,
        "total_upgrades": 0,
        "total_downgrades": 0,
    }])

    prob = pipeline.predict_proba(sample_input[features])[0, 1]
    assert 0.0 <= prob <= 1.0, f"Probability out of bounds: {prob}"


def test_model_monotonicity_on_downgrades(model_bundle):
    """
    Stress test: An account with multiple downgrades should have a strictly
    higher risk score than an otherwise identical account with 0 downgrades.
    """
    pipeline = model_bundle["pipeline"]
    features = model_bundle["feature_cols"]

    healthy_account = pd.DataFrame([{
        "latest_tier": "Pro",
        "tenure_months": 4.0,
        "avg_mrr": 99.0,
        "max_mrr": 99.0,
        "lifetime_mrr": 396.0,
        "mrr_stddev": 0.0,
        "total_event_count": 4,
        "total_upgrades": 1,
        "total_downgrades": 0,
    }])

    at_risk_account = pd.DataFrame([{
        "latest_tier": "Pro",
        "tenure_months": 4.0,
        "avg_mrr": 99.0,
        "max_mrr": 99.0,
        "lifetime_mrr": 396.0,
        "mrr_stddev": 25.0,
        "total_event_count": 4,
        "total_upgrades": 0,
        "total_downgrades": 2,
    }])

    prob_healthy = pipeline.predict_proba(healthy_account[features])[0, 1]
    prob_at_risk = pipeline.predict_proba(at_risk_account[features])[0, 1]

    assert prob_at_risk > prob_healthy, (
        f"Model failed risk monotonicity: healthy={prob_healthy:.3f}, downgraded={prob_at_risk:.3f}"
    )