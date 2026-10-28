# Step 1 Study Guide: SaaS Economics, Retention Analytics & System Architecture

## 1. Executive Summary & Problem Framing
In subscription platforms, aggregate recurring revenue metrics often mask underlying customer attrition—a dynamic termed the "leaky bucket problem." When new customer acquisition velocity hides deteriorating cohort retention, long-term enterprise value collapses. 

This engine models recurring subscription logs, computes customer and revenue cohort retention matrices, isolates Monthly Recurring Revenue (MRR) movements, and fits survival curves to detect churn cliffs.

---

## 2. Core SaaS Business Metrics & Mathematical Foundations

### 2.1 Monthly Recurring Revenue (MRR) Waterfall
Monthly Recurring Revenue measures normalized, predictable subscription revenue generated in a given month. The MRR waterfall isolates the mechanics driving monthly revenue variation:

$$\text{MRR}_{t} = \text{MRR}_{t-1} + \text{New MRR}_t + \text{Expansion MRR}_t - \text{Contraction MRR}_t - \text{Churned MRR}_t$$

* **New MRR**: Invoiced recurring revenue from first-time paying subscribers acquired during month $t$.
* **Expansion MRR**: Invoiced recurring revenue added from existing customers upgrading tiers or adding seats in month $t$.
* **Contraction MRR**: Recurring revenue reduced when existing customers downgrade plans without fully canceling in month $t$.
* **Churned MRR**: Recurring revenue lost when existing customers cancel entirely in month $t$.
* **Net New MRR**: $\text{New MRR}_t + \text{Expansion MRR}_t - \text{Contraction MRR}_t - \text{Churned MRR}_t$.

### 2.2 Customer Retention vs. Net Revenue Retention (NRR)
* **Logo (User) Retention Rate**:
  $$\text{Logo Retention}_t = \frac{\text{Active Accounts in Month } t \text{ from Cohort } C}{\text{Initial Accounts in Cohort } C \text{ at Month } 0} \times 100$$
  Tracks user attrition irrespective of account size.

* **Net Revenue Retention (NRR)**:
  $$\text{NRR}_t = \frac{\text{MRR from Cohort } C \text{ in Month } t}{\text{Original MRR from Cohort } C \text{ in Month } 0} \times 100$$
  Accounts for contraction, churn, and expansion. An NRR $> 100\%$ indicates "Net Negative Churn," where expansion from retained accounts outpaces total revenue lost from cancellations and downgrades.

### 2.3 Customer Lifetime Value (LTV) & CAC Payback
* **Average Revenue Per User (ARPU)**:
  $$\text{ARPU} = \frac{\text{Total MRR}}{\text{Active Subscriptions}}$$

* **Customer Lifetime Value (LTV)**:
  $$\text{LTV} = \frac{\text{ARPU} \times \text{Gross Margin \%}}{\text{Customer Churn Rate}}$$

* **Customer Acquisition Cost (CAC) Payback Period**:
  $$\text{CAC Payback (Months)} = \frac{\text{CAC}}{\text{ARPU} \times \text{Gross Margin \%}}$$

* **Venture & Enterprise SaaS Benchmarks**:
  * **LTV:CAC $< 1.0$**: Unsustainable unit economics (loss per customer acquired).
  * **LTV:CAC $3.0 - 5.0$**: Industry target for venture-scale SaaS.
  * **CAC Payback $< 12 \text{ months}$**: Strong capital efficiency for self-serve/SMB tiers.

---

## 3. Analytical Architecture & Technology Stack

* **DuckDB**: Vectorized analytical query engine (OLAP). Processes columnar vectors (typically 2,048 values per chunk) in-CPU cache, avoiding the overhead of row-oriented database engines.
* **SQL Window Functions**: In-database analytical queries executing rolling partitions, lag-based state transitions, and triangular cohort aggregations directly over Parquet files.
* **Lifelines / SciPy**: Non-parametric survival estimation using Kaplan-Meier curves, accounting for right-censored data (subscribers active at observation cut-off).
* **Streamlit & Plotly**: Interactive UI rendering triangular cohort heatmaps, survival hazard curves, and dynamic churn sensitivity sliders.

---

## 4. Key Real-World Interview Questions & Answers

### Q1: What is the difference between Logo Churn and Revenue Churn?
> **Answer**: Logo churn measures the percentage of subscriber accounts lost over a period, whereas Revenue Churn measures the percentage of recurring revenue lost. In enterprise B2B SaaS, a team can have low logo churn (e.g., losing three small customers) but high revenue churn (if one of those was an enterprise account driving 20% of MRR). Conversely, high logo churn on self-serve tiers can be masked by strong expansion on enterprise tiers.

### Q2: Why is Kaplan-Meier preferred over Logistic Regression for churn analysis?
> **Answer**: Logistic regression requires a fixed observation window and cannot natively handle **right-censoring** (customers whose subscription lifecycle is ongoing at the time of analysis). If you treat active customers as "not churned," you introduce survival bias; if you exclude them, you skew churn higher. Kaplan-Meier explicitly models tenure as a time-to-event variable, utilizing censored durations up to the latest observation.

### Q3: Why use DuckDB instead of SQLite or Pandas for cohort aggregation?
> **Answer**: SQLite is row-oriented (OLTP), meaning queries reading specific columns scan entire row tuples, wasting disk and memory bandwidth. Pandas executes in-memory with single-threaded bottlenecks on large datasets. DuckDB uses columnar storage, vectorized SIMD execution, parallel query planning, and can query Parquet files directly with out-of-core streaming without loading the entire dataset into memory.