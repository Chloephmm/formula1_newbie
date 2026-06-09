"""Evaluate the podium model on the held-out test seasons (>=2024).

Produces the metrics dict used by metrics.json: log-loss, ROC-AUC, top-1 / top-3
accuracy, a baseline comparison, a calibration (reliability) curve, and feature
importances.
"""
from __future__ import annotations

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import log_loss, roc_auc_score

from src.model.data import FEATURES


def _per_race_accuracy(df, proba):
    """top-1 = did the highest-prob driver win; top-3 = predicted∩actual podium / 3."""
    d = df[["season", "round", "position"]].copy().reset_index(drop=True)
    d["p"] = proba
    top1_hits, top3_overlap, n_races = 0, 0.0, 0
    for _, g in d.groupby(["season", "round"]):
        n_races += 1
        g = g.sort_values("p", ascending=False)
        if int(g.iloc[0]["position"]) == 1:
            top1_hits += 1
        pred3 = set(g.head(3).index)
        actual3 = set(g[g["position"] <= 3].index)
        top3_overlap += len(pred3 & actual3) / 3.0
    return top1_hits / n_races, top3_overlap / n_races


def evaluate(artifact, test):
    model, baseline = artifact["model"], artifact["baseline"]
    xgb_model = artifact.get("xgboost")
    Xte, yte = test[FEATURES], test["podium"]

    p_model = model.predict_proba(Xte)[:, 1]
    p_base = baseline.predict_proba(Xte)[:, 1]

    m_top1, m_top3 = _per_race_accuracy(test, p_model)
    b_top1, b_top3 = _per_race_accuracy(test, p_base)

    xgb_block = None
    if xgb_model is not None:
        p_xgb = xgb_model.predict_proba(Xte)[:, 1]
        x_top1, x_top3 = _per_race_accuracy(test, p_xgb)
        xgb_block = {
            "logLoss": round(float(log_loss(yte, p_xgb)), 4),
            "rocAuc": round(float(roc_auc_score(yte, p_xgb)), 4),
            "top1Accuracy": round(float(x_top1), 4),
            "top3Accuracy": round(float(x_top3), 4),
        }

    prob_true, prob_pred = calibration_curve(yte, p_model, n_bins=10, strategy="quantile")

    imp = artifact["feature_importances"]
    imp_total = sum(imp.values()) or 1.0

    return {
        "podium": {
            "logLoss": round(float(log_loss(yte, p_model)), 4),
            "rocAuc": round(float(roc_auc_score(yte, p_model)), 4),
            "top1Accuracy": round(float(m_top1), 4),
            "top3Accuracy": round(float(m_top3), 4),
            "baseline": {
                "rocAuc": round(float(roc_auc_score(yte, p_base)), 4),
                "top1Accuracy": round(float(b_top1), 4),
                "top3Accuracy": round(float(b_top3), 4),
            },
            "xgboost": xgb_block,
            "testRows": int(len(test)),
            "testPositives": int(yte.sum()),
        },
        "calibration": [
            {"predicted": round(float(pp), 4), "actual": round(float(pt), 4)}
            for pp, pt in zip(prob_pred, prob_true)
        ],
        "featureImportances": [
            {"feature": f, "importance": round(imp[f] / imp_total, 4)}
            for f in sorted(FEATURES, key=lambda k: imp[k], reverse=True)
        ],
    }
