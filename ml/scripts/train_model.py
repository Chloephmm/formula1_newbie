"""Train + calibrate + evaluate the podium model, and write metrics.json.

Run from ml/:
    python scripts/train_model.py

Outputs:
    ml/models/podium_model.pkl
    <repo>/web/public/data/metrics.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # add ml/ to sys.path

from src.model.data import ML_DIR, load_features, split_by_season  # noqa: E402
from src.model.evaluate import evaluate  # noqa: E402
from src.model.train import train  # noqa: E402

WEB_DATA = ML_DIR.parent / "web" / "public" / "data"


def main() -> None:
    print("Training (LightGBM + logistic baseline) and calibrating on 2023 ...")
    artifact = train()

    df = load_features()
    _tr, _ca, test = split_by_season(df)
    metrics = evaluate(artifact, test)

    p = metrics["podium"]
    b = p["baseline"]
    x = p.get("xgboost") or {}
    print("\n================  PODIUM MODEL — REPORT CARD (test: 2024-2026)  ================")
    print(f"  test rows: {p['testRows']}   podium positives: {p['testPositives']}")
    print(f"  {'metric':16s} {'LightGBM':>10s} {'XGBoost':>10s} {'baseline':>10s}")
    print(f"  {'ROC-AUC':16s} {p['rocAuc']:>10.3f} {x.get('rocAuc', float('nan')):>10.3f} {b['rocAuc']:>10.3f}")
    print(f"  {'top-1 accuracy':16s} {p['top1Accuracy']:>10.3f} {x.get('top1Accuracy', float('nan')):>10.3f} {b['top1Accuracy']:>10.3f}")
    print(f"  {'top-3 accuracy':16s} {p['top3Accuracy']:>10.3f} {x.get('top3Accuracy', float('nan')):>10.3f} {b['top3Accuracy']:>10.3f}")
    print(f"  {'log-loss':16s} {p['logLoss']:>10.3f} {x.get('logLoss', float('nan')):>10.3f} {'n/a':>10s}")
    print("\n  feature importances:")
    for fi in metrics["featureImportances"]:
        bar = "#" * int(fi["importance"] * 40)
        print(f"    {fi['feature']:24s} {fi['importance']:.3f} {bar}")
    print("\n  calibration curve (predicted -> actual):")
    for c in metrics["calibration"]:
        print(f"    pred {c['predicted']:.2f}  ->  actual {c['actual']:.2f}")
    print("================================================================================")

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nwrote {WEB_DATA / 'metrics.json'}")
    print(f"saved {ML_DIR / 'models' / 'podium_model.pkl'}")


if __name__ == "__main__":
    main()
