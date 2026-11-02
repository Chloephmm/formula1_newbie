"""Write a reviewable before/after forecast and DNF-feature comparison."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))

from src.model.forecast import _historical_driver_table  # noqa: E402


def comparison(before, after):
    old, new = before.get("forecast", before), after["forecast"]
    if (old["race"]["season"], old["race"]["round"]) != (new["race"]["season"], new["race"]["round"]):
        raise ValueError("comparison events differ")
    old_p = {row["code"]: row for row in old["preQualifyingPodium"]}
    old_q = {row["code"]: row for row in old["predictedQualifying"]}
    new_q = {row["code"]: row for row in new["predictedQualifying"]}
    history = _historical_driver_table(new["race"]["date"])
    history["old_dnf"] = (~((history.status == "Finished") | history.status.astype(str).str.startswith("+"))).astype(int)
    recent = history.groupby("driver_id", sort=False).tail(5)
    dnf = recent.groupby("code")[["old_dnf", "is_dnf"]].mean()
    rows = []
    for row in new["preQualifyingPodium"]:
        code = row["code"]
        rows.append({
            "code": code, "driver": row["driverName"],
            "saved_podium_probability": old_p.get(code, {}).get("podiumProbability"),
            "corrected_podium_probability": row["podiumProbability"],
            "saved_qualifying_position": old_q.get(code, {}).get("position"),
            "corrected_qualifying_position": new_q[code]["position"],
            "saved_qualifying_gap": old_q.get(code, {}).get("gap"),
            "corrected_qualifying_gap": new_q[code]["gap"],
            "old_rule_recent_dnf_rate": float(dnf.loc[code, "old_dnf"]) if code in dnf.index else None,
            "corrected_recent_dnf_rate": float(dnf.loc[code, "is_dnf"]) if code in dnf.index else None,
        })
    return {
        "race_id": after["race_id"],
        "saved_prediction_updated_at": before.get("prediction_updated_at"),
        "candidate_prediction_updated_at": after["prediction_updated_at"],
        "interpretation": "Before/after is not a causal attribution: status correction, race-local grid defaults and reproducibility controls changed together. The original saved-versus-local discrepancy remains unexplained. DNF comparisons reconstruct the old rule on current cached history, not recovered old model provenance.",
        "drivers": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = comparison(json.loads(args.before.read_text(encoding="utf-8")),
                        json.loads(args.candidate.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for row in report["drivers"][:5]:
        print(f"{row['code']}: {row['saved_podium_probability']:.2%} -> {row['corrected_podium_probability']:.2%}")
