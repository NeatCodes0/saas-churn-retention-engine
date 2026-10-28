# ⬡ SaaS Churn & Cohort Retention Intelligence Engine

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-OLAP-FFF000?style=flat&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-Cost--Sensitive-EB6434?style=flat)](https://xgboost.readthedocs.io/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Command--Center-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io/)

A production-grade analytical and predictive SaaS intelligence engine. Transforms raw, granular subscription event streams into GAAP-aligned MRR waterfall ledgers, triangular logo/NRR retention matrices, and real-time out-of-time churn inference prioritized by **Expected Dollar Loss ($)**.

---

## Architecture Overview

```text
┌─────────────────────────────────┐
│  Synthetic Ledger Generator     │  (34,660 events across multi-state account lifecycles)
│  src/data/generate_events.py    │
└────────────────┬────────────────┘
                 │ (Parquet Columnar Storage)
                 ▼
┌─────────────────────────────────┐
│     In-Memory DuckDB OLAP       │  (Zero-network, vectorized columnar execution)
│  data/processed/analytics.duckdb│
└────────┬────────────────────────┘
         │
         ├──────────────────────────────────────────┐
         ▼                                          ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────────────┐
│ Analytical Window SQL Pipelines │   │ Predictive Feature Engineering Pipeline │
│ • mrr_waterfall.sql             │   │ • src/features/build_features.py        │
│ • cohort_retention.sql          │   │ • Strict Chronological Cutoff (T_obs)   │
└────────────────┬────────────────┘   └────────────────────┬────────────────────┘
                 │                                         │
                 │                    ┌────────────────────┴────────────────────┐
                 │                    ▼                                         ▼
                 │       ┌────────────────────────┐                ┌────────────────────────┐
                 │       │ Train/Test Evaluation  │                │ Production Serialization│
                 │       │ (OOT PR-AUC & F1)      │                │ models/churn_model.pkl │
                 │       └────────────────────────┘                └───────────┬────────────┘
                 │                                                             │
                 └───────────────────────┬─────────────────────────────────────┘
                                         ▼
                 ┌──────────────────────────────────────────────────────────────┐
                 │          Full-Stack Executive Command Center                 │
                 │                       (app.py)                               │
                 │  • GAAP MRR Waterfall Decomposition                          │
                 │  • Dual-Dimension Triangular Cohort Heatmaps                 │
                 │  • Tactical CS Priority Queue (Expected Loss Ranking)        │
                 │  • Real-Time Parametric Risk Simulator                       │
                 └──────────────────────────────────────────────────────────────┘
```

---

## Core System Capabilities

### 1. Embedded OLAP & GAAP Financial Decompositions
- **Zero-Network In-Process Analytics**: Replaces slow cloud warehouse latency with an embedded DuckDB instance executing vectorized window operations across tens of thousands of subscription states in milliseconds.
- **GAAP MRR Movements**: Categorizes ledger transactions into distinct accounting dimensions:
  - **New MRR**: First-time subscriptions.
  - **Expansion MRR**: Upgrades from Starter ($29) to Pro ($99) or Enterprise ($299).
  - **Contraction MRR**: Plan tier downgrades prior to cancellation.
  - **Gross Churn MRR**: Permanent account cancellations.
  - **Ending MRR**: $\text{Starting MRR} + \text{New} + \text{Expansion} - \text{Contraction} - \text{Churn}$.

### 2. Longitudinal Cohort Matrices & Net Revenue Retention (NRR)
- **Dual-Lens Evaluation**: Calculates both **User Logo Retention (%)** and **Dollar-Weighted Net Revenue Retention (NRR %)** across acquisition cohorts.
- **Expansion Dynamics**: Visualizes expansion inflection points where accounts expand spend faster than churn erosion (NRR > 100%).

### 3. Leakage-Free Predictive Churn Modeling
- **Temporal Integrity**: Strictly avoids random cross-validation leakage by implementing chronological cutoff splitting ($T_{\text{obs}}$). Features are evaluated only on historical transactions; target labels are observed strictly in the future horizon.
- **Handling Class Imbalance**: Addresses the natural 10.5% SaaS churn skew using cost-sensitive gradient boosting (`scale_pos_weight = count(neg) / count(pos)`).
- **Ranking Metric**: Optimized on **PR-AUC (Precision-Recall AUC)** to prevent misleading accuracy inflation on imbalanced classes.

### 4. Economic Loss Prioritization Desk
- Replaces naive probability thresholding with **Expected Monthly Loss Allocation**:
  $$\text{Expected MRR Loss} = P(\text{churn}) \times \text{Current MRR}$$
- Automatically routes accounts into automated Customer Success playbooks:
  - `EXECUTIVE SPONSOR RESCUE`: Churn risk $\ge 55\%$ & $\text{MRR} \ge \$200$.
  - `VALUE RE-ALIGNMENT CADENCE`: Accounts with recorded downgrades.
  - `ONBOARDING ACTIVATION AUDIT`: At-risk accounts with tenure $\le 3\text{ months}$.
  - `DISCOUNTED CONTRACT LOCK`: At-risk accounts on legacy single licenses.

---

## Repository Structure

```text
saas-churn-retention-engine/
├── app.py                           # Command Center Executive Streamlit Application
├── requirements.txt                 # Pinned production dependencies
├── README.md                        # Master architectural documentation
├── data/
│   ├── raw/                         # Raw synthetic subscription event Parquet files
│   └── processed/
│       └── analytics.duckdb         # Vectorized embedded database store
├── docs/                            # In-depth architectural & study guides (Steps 1–6)
│   ├── step_01_synthetic_events_guide.md
│   ├── ...
│   ├── step_05_feature_engineering_and_churn_ml.md
│   └── step_06_dashboard_and_deployment.md
├── models/
│   └── churn_model.joblib           # Serialized production XGBoost pipeline
└── src/
    ├── data/
    │   └── generate_events.py       # Multi-state synthetic subscription generator
    ├── features/
    │   └── build_features.py        # Temporal leakage-free feature store
    ├── models/
    │   └── train.py                 # Out-of-time benchmarking & artifact serialization
    └── queries/
        ├── mrr_waterfall.sql        # Window-function GAAP MRR decomposition
        └── cohort_retention.sql     # Triangular survival & NRR SQL queries
```

---

## Quickstart & Local Setup

### 1. Environment Initialization
```bash
git clone https://github.com/<your-username>/saas-churn-retention-engine.git
cd saas-churn-retention-engine

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# Unix/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Data Pipeline & Feature Extraction
```bash
# Generate synthetic subscription events and seed DuckDB
python src/data/generate_events.py

# Extract leakage-free feature vectors
python src/features/build_features.py
```

### 3. Model Training & Out-of-Time Benchmark
```bash
# Benchmark architectures and serialize production XGBoost pipeline
python -m src.models.train
```

### 4. Launch Command Center
```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser to view the interactive dashboard.