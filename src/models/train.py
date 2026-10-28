"""
Model Training & Evaluation Pipeline for SaaS Churn Prediction.
Enforces chronological train/test splitting and cost-sensitive re-weighting.
"""

from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from src.features.build_features import extract_churn_features


def train_and_evaluate_models():
    # 1. Extract feature matrix
    print("[1/5] Extracting feature matrix from DuckDB...")
    df = extract_churn_features()

    # 2. Chronological Train / Test Split
    # Training cohorts: early 2024 cohorts; Test cohorts: late 2024 cohorts
    split_cohort = "2024-09"
    print(f"[2/5] Performing chronological split at cohort: {split_cohort}...")

    train_df = df[df["initial_cohort_month"] < split_cohort].copy()
    test_df = df[df["initial_cohort_month"] >= split_cohort].copy()

    feature_cols = [
        "latest_tier",
        "tenure_months",
        "avg_mrr",
        "max_mrr",
        "lifetime_mrr",
        "mrr_stddev",
        "total_event_count",
        "total_upgrades",
        "total_downgrades",
    ]
    target_col = "is_churned"

    X_train = train_df[feature_cols]
    y_train = train_df[target_col]
    X_test = test_df[feature_cols]
    y_test = test_df[target_col]

    print(f"  Train set: {len(X_train)} accounts ({y_train.sum()} churned, {y_train.mean()*100:.1f}%)")
    print(f"  Test set:  {len(X_test)} accounts ({y_test.sum()} churned, {y_test.mean()*100:.1f}%)")

    # 3. Calculate class imbalance ratio for cost-sensitive loss
    pos_weight = (len(y_train) - y_train.sum()) / max(y_train.sum(), 1)

    # 4. Define Preprocessing Pipelines
    cat_features = ["latest_tier"]
    num_features = [col for col in feature_cols if col != "latest_tier"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), num_features),
            ("cat", OneHotEncoder(drop="first", handle_unknown="ignore"), cat_features),
        ]
    )

    models = {
        "Logistic Regression": Pipeline([
            ("prep", preprocessor),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
        ]),
        "Random Forest": Pipeline([
            ("prep", preprocessor),
            ("clf", RandomForestClassifier(
                n_estimators=150,
                max_depth=6,
                class_weight="balanced",
                random_state=42
            )),
        ]),
        "XGBoost": Pipeline([
            ("prep", preprocessor),
            ("clf", XGBClassifier(
                n_estimators=120,
                max_depth=4,
                learning_rate=0.05,
                scale_pos_weight=pos_weight,
                random_state=42,
                eval_metric="logloss"
            )),
        ]),
    }

    print("\n[3/5] Training and benchmarking candidate architectures...")
    results = []
    best_pr_auc = -1.0
    best_model_name = None
    best_pipeline = None

    for name, pipeline in models.items():
        pipeline.fit(X_train, y_train)

        # Probabilities for class 1
        y_pred_proba = pipeline.predict_proba(X_test)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        roc_auc = roc_auc_score(y_test, y_pred_proba)
        pr_auc = average_precision_score(y_test, y_pred_proba)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)

        results.append({
            "Model": name,
            "ROC-AUC": round(roc_auc, 4),
            "PR-AUC": round(pr_auc, 4),
            "F1-Score": round(f1, 4),
            "Precision": round(precision, 4),
            "Recall": round(recall, 4),
        })

        if pr_auc > best_pr_auc:
            best_pr_auc = pr_auc
            best_model_name = name
            best_pipeline = pipeline

    # 5. Display Leaderboard
    leaderboard = pd.DataFrame(results).sort_values(by="PR-AUC", ascending=False)
    print("\n[4/5] Model Benchmark Leaderboard:")
    print("=" * 70)
    print(leaderboard.to_string(index=False))
    print("=" * 70)

    # 6. Save Production Artifact
    model_dir = Path("models")
    model_dir.mkdir(parents=True, exist_ok=True)
    save_path = model_dir / "churn_model.joblib"

    joblib.dump({
        "pipeline": best_pipeline,
        "feature_cols": feature_cols,
        "model_name": best_model_name,
        "best_pr_auc": best_pr_auc,
    }, save_path)

    print(f"\n[5/5] Best model ({best_model_name}) serialized to {save_path.resolve()}")


if __name__ == "__main__":
    train_and_evaluate_models()