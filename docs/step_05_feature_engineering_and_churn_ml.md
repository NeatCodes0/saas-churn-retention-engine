# Step 5 Master Study Guide: Feature Engineering, Temporal Leakage & Churn Prediction Pipeline

---

## 1. Executive Summary & SaaS Churn Problem Formulation

Churn prediction transforms historical subscription event streams into proactive retention interventions. A model that predicts churn with high precision enables Customer Success teams to trigger targeted re-engagement campaigns (e.g., proactive onboarding check-ins, discount incentives, executive sponsorship) *before* the customer reaches a cancellation decision.

### Problem Formulation
- **Unit of Analysis**: Individual subscription account (`customer_id`).
- **Target Label ($y$)**: Binary indicator:
  $$y = \begin{cases} 1 & \text{if account churns within prediction horizon } [T_{\text{obs}}, T_{\text{obs}} + H] \\ 0 & \text{if account remains active throughout horizon} \end{cases}$$
- **Observation Cutoff ($T_{\text{obs}}$)**: The point in time up to which features may be computed.
- **Prediction Horizon ($H$)**: The forward-looking window (typically 30, 60, or 90 days).

---

## 2. Temporal Data Leakage: The #1 Trap in Subscription ML

In standard tabular datasets, practitioners often run random cross-validation or `train_test_split(test_size=0.2)`. **In subscription and time-series data, random splitting introduces severe data leakage.**

```text
Time Line:  ───────────────[ Observation Cutoff T_obs ]───────────────[ Horizon H ]───>
Features Allowed:          [Past Events: t <= T_obs  ]   <-- ONLY THIS
Target Label:                                            [Churn Event: T_obs < t <= T_obs + H]
LEAKAGE TRAP:              [DO NOT use any events where t > T_obs to build features!]
```

### Forms of Leakage:
1. **Target Leakage via Future Spend**: Including `lifetime_value` calculated through the end of the entire dataset rather than evaluated strictly at $T_{\text{obs}}$.
2. **Temporal Lookahead via Random Splitting**: A customer's Month 2 event ends up in the test set while their Month 6 event ends up in the train set. The tree splits on patterns it has already memorized from the future.
3. **Target Encoding Leakage**: Calculating mean target values on the entire dataset before fold splitting.

---

## 3. High-Signal Feature Taxonomy for SaaS Churn

| Feature Category        | Engineered Metric   | Formula / Logic                                           | Business Signal                                         |
| :---------------------- | :------------------ | :-------------------------------------------------------- | :------------------------------------------------------ |
| **Tenure**              | `tenure_months`     | Months active prior to $T_{\text{obs}}$                   | Baseline stickiness; early-tenure accounts churn faster |
| **Monetary / Scale**    | `avg_mrr`           | Mean MRR across active events                             | Average account sizing                                  |
| **Monetary / Scale**    | `max_mrr`           | Peak MRR achieved prior to $T_{\text{obs}}$               | Account ceiling capacity                                |
| **Monetary / Scale**    | `lifetime_mrr`      | $\sum \text{mrr}$ from signup to $T_{\text{obs}}$         | Total capital invested in the platform                  |
| **Behavioral Velocity** | `total_event_count` | Total billing transactions                                | Engagement longevity                                    |
| **Behavioral Velocity** | `total_upgrades`    | Count of upgrade events                                   | Positive sentiment & product adoption                   |
| **Behavioral Velocity** | `total_downgrades`  | Count of downgrade events                                 | Early distress signal prior to outright cancellation    |
| **Stability**           | `mrr_stddev`        | $\text{StdDev}(\text{mrr})$ over account history          | Unstable license usage or intermittent seat billing     |
| **Categorical Tier**    | `latest_tier`       | Tier at $T_{\text{obs}}$ (`Starter`, `Pro`, `Enterprise`) | Discretionary vs. mission-critical business usage       |

---

## 4. Class Imbalance Strategies: Metric Selection & Loss Re-weighting

In healthy SaaS businesses, monthly churn typically ranges between 2% and 8%. This introduces substantial **class imbalance** ($y=1$ is rare).

### 4.1 Why Accuracy is Unusable
If churn is 4%, a naive model that predicts every single customer will stay active achieves **96% accuracy** while catching 0% of churners.

### 4.2 Production Evaluation Metrics
* **PR-AUC (Area Under Precision-Recall Curve)**: The primary metric for highly imbalanced classification. Focuses on the trade-off between false alarms (precision) and missed churners (recall).
* **ROC-AUC**: Measures ranking separation between active and churned customers across all decision thresholds.
* **Cost-Weighted Utility Matrix**: 
  $$\text{Expected Value} = (\text{TP} \times V_{\text{saved}}) - (\text{FP} \times C_{\text{incentive}}) - (\text{FN} \times V_{\text{lost}})$$

### 4.3 Handling the Imbalance in Algorithms
1. **Cost-Sensitive Loss (`scale_pos_weight` in XGBoost/LightGBM)**: Penalizes false negatives proportionally:
   $$\text{scale\_pos\_weight} = \frac{\text{Count of Negative Class (Active)}}{\text{Count of Positive Class (Churn)}}$$
2. **Threshold Tuning**: Rather than using a default threshold of $0.5$, sweep thresholds from $0.1$ to $0.9$ to maximize F1-score or business utility.

---

## 5. Algorithmic Comparison: Linear vs. Tree-Based Models

| Model                   | Pros                                                                                                                    | Cons                                                                                                | Best Use Case                                                      |
| :---------------------- | :---------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------- |
| **Logistic Regression** | Fully interpretable log-odds coefficients, fast inference, robust baseline                                              | Cannot capture non-linear cliffs (e.g., tenure 3-month trial drop) without manual interaction terms | Regulatory/executive reporting, strict baseline verification       |
| **Random Forest**       | Handles collinearity, non-linear boundaries, resistant to overfitting                                                   | Slower inference on large batches, large memory footprint for deep ensembles                        | Mid-sized tabular datasets with complex multi-feature interactions |
| **XGBoost / LightGBM**  | Native handling of class imbalance (`scale_pos_weight`), fast histogram-based splits, state-of-the-art tabular accuracy | Requires careful hyperparameter tuning (learning rate, max depth, subsample) to avoid overfitting   | Production deployment standard for tabular enterprise ML           |

---

## 6. Interpretability & Feature Importance: SHAP Mechanics

In production SaaS, customer success reps need to know *why* an account is flagged. 

**SHAP (SHapley Additive exPlanations)** decomposes the final model score into additive contributions from each feature based on cooperative game theory:

$$\hat{y}_i = \phi_0 + \sum_{j=1}^{M} \phi_{i,j}$$

- $\phi_0$: The base expected value (dataset average churn rate).
- $\phi_{i,j}$: The exact push (positive or negative) that feature $j$ exerts on customer $i$'s risk score.

This allows the engine to output an actionable explanation card for each account:
- `"Account CUST-1049 is at 82% churn risk because total_downgrades >= 2 (+0.31) and tenure_months <= 3 (+0.24)."`

---

## 7. Real-World Staff & Senior Interview Questions & Answers

### Q1: Why is chronological train/test splitting mandatory for churn prediction over standard k-fold cross validation?
> **Answer**: 
> Standard k-fold randomly samples records across the entire timeline. If a customer signs up in January and churns in November, random splits can put their October downgrade in the training set and their March renewal in the test set. The model ends up learning future event signatures to predict past behavior (temporal data leakage). Chronological splitting establishes an immutable time boundary: all training data occurs prior to $T_{\text{split}}$, and all test data occurs after $T_{\text{split}}$, simulating true production deployment.

### Q2: Why should you avoid SMOTE (Synthetic Minority Over-sampling) on tabular business metrics?
> **Answer**: 
> SMOTE synthesizes new samples by taking linear combinations of nearest neighbors in feature space. In business event data with discrete tiers (`Starter`, `Pro`, `Enterprise`) and exact pricing rules, linear interpolation generates mathematically nonsensical combinations (e.g., an Enterprise tier account paying $32.40 with 0.4 upgrades). Modern production pipelines favor cost-sensitive loss weighting (`scale_pos_weight` in GBDTs) or threshold moving, which preserve the true data distribution without synthesizing false records.

### Q3: How do you balance Precision vs. Recall when setting the decision threshold for CS retention outreach?
> **Answer**: 
> It is an economic optimization problem determined by Customer Success capacity and retention incentives:
> - If Customer Success has limited headcount and each high-touch outreach is expensive ($C_{\text{outreach}}$ is high), optimize for **High Precision** (e.g., threshold $0.7$) so team bandwidth is spent only on near-certain churners.
> - If retention outreach is automated (e.g., an automated marketing email offering a discount where marginal cost is low), optimize for **High Recall** (e.g., threshold $0.3$) to capture as many at-risk accounts as possible, accepting a higher false-alarm rate.