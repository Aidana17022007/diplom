"""Descriptive diagnostics from frozen predictions, without fitting or selection.

Run with the project's scientific Python environment from the repository root.
Only aggregate outputs are written. Input hashes are checked before writing.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FRACTIONS = (0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
BUCKETS = ("0", "1", "2-3", "4+")
METRICS = ("roc_auc", "average_precision", "precision", "recall", "specificity",
           "f1", "brier", "balanced_accuracy", "mcc")


def validated_arrays(target, probability, *, allow_empty=False):
    y, p = np.asarray(target, dtype=float), np.asarray(probability, dtype=float)
    if y.ndim != 1 or p.ndim != 1 or len(y) != len(p):
        raise ValueError("Targets and probabilities must be equally sized vectors")
    if not allow_empty and not len(y):
        raise ValueError("At least one observation is required")
    if not np.isfinite(y).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Targets must be finite binary values")
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("Probabilities must be finite values in [0, 1]")
    return y.astype(int), p


def safe_ratio(numerator, denominator):
    return float(numerator / denominator) if denominator else None


def ranking_metrics(target, probability, fractions=FRACTIONS):
    """Whole-tie score thresholds, not row-order-based top-k selection.

    Cumulative gain is recall; lift is selected precision / cohort prevalence.
    The random baseline uses the actual selected fraction, including ties.
    """
    y, p = validated_arrays(target, probability)
    descending = np.sort(p)[::-1]
    total_positive, n = int(y.sum()), len(y)
    prevalence = total_positive / n
    rows = []
    for fraction in fractions:
        if not math.isfinite(fraction) or not 0 < fraction <= 1:
            raise ValueError("Requested fractions must be finite and in (0, 1]")
        requested_n = math.ceil(fraction * n)
        cutoff = float(descending[requested_n - 1])
        selected = p >= cutoff
        selected_n, positive_n = int(selected.sum()), int(y[selected].sum())
        precision = positive_n / selected_n
        rows.append({
            "requested_fraction": float(fraction),
            "actual_fraction": selected_n / n,
            "cutoff": cutoff,
            "selected_n": selected_n,
            "positive_n": positive_n,
            "precision": precision,
            "recall": safe_ratio(positive_n, total_positive),
            "lift": safe_ratio(precision, prevalence),
            "random_recall": selected_n / n if total_positive else None,
            "random_precision": prevalence,
        })
    return rows


def subgroup_metrics(target, probability, threshold):
    """Undefined ratios and single-class discrimination are null, never NaN."""
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be finite and in [0, 1]")
    y, p = validated_arrays(target, probability, allow_empty=True)
    if not len(y):
        return {key: None for key in METRICS}
    prediction = p >= threshold
    tp = int(np.sum((y == 1) & prediction))
    fp = int(np.sum((y == 0) & prediction))
    fn = int(np.sum((y == 1) & ~prediction))
    tn = int(np.sum((y == 0) & ~prediction))
    two_classes = 0 < y.sum() < len(y)
    recall, specificity = safe_ratio(tp, tp + fn), safe_ratio(tn, tn + fp)
    return {
        "roc_auc": float(roc_auc_score(y, p)) if two_classes else None,
        "average_precision": float(average_precision_score(y, p)) if two_classes else None,
        "precision": safe_ratio(tp, tp + fp),
        "recall": recall,
        "specificity": specificity,
        "f1": safe_ratio(2 * tp, 2 * tp + fp + fn),
        "brier": float(brier_score_loss(y, p)),
        "balanced_accuracy": (recall + specificity) / 2 if two_classes else None,
        "mcc": safe_ratio(tp * tn - fp * fn,
                          math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))),
    }


def matched_features(predictions, processed, features, expected_ids=None, required_split=None):
    """Validate a one-to-one prediction/source join before counting missingness."""
    if predictions.row_id.isna().any() or processed.row_id.isna().any():
        raise ValueError("Row identifiers must be present")
    prediction_ids, source_ids = predictions.row_id.astype(str), processed.row_id.astype(str)
    if prediction_ids.duplicated().any() or source_ids.duplicated().any():
        raise ValueError("Row identifiers must be unique")
    if expected_ids is not None and set(prediction_ids) != {str(v) for v in expected_ids}:
        raise ValueError("Prediction identifiers do not match the frozen cohort")
    if not set(prediction_ids).issubset(set(source_ids)):
        raise ValueError("Predictions contain unknown source identifiers")
    indexed = processed.copy()
    indexed.index = source_ids
    matched = indexed.loc[prediction_ids]
    if not np.array_equal(matched.target.to_numpy(), predictions.target.to_numpy()):
        raise ValueError("Prediction targets do not match source targets")
    if required_split and not (matched.split == required_split).all():
        raise ValueError("Predictions include observations outside the required split")
    return matched[features].reset_index(drop=True)


def missingness_metrics(target, probability, feature_frame, threshold):
    y, p = validated_arrays(target, probability)
    if len(feature_frame) != len(y):
        raise ValueError("Features and predictions must have equal length")
    counts = feature_frame.isna().sum(axis=1).to_numpy()
    masks = (counts == 0, counts == 1, (counts >= 2) & (counts <= 3), counts >= 4)
    groups = []
    for bucket, mask in zip(BUCKETS, masks):
        n, positive = int(mask.sum()), int(y[mask].sum())
        groups.append({"bucket": bucket, "n": n, "positive": positive,
                       "prevalence": safe_ratio(positive, n),
                       "metrics": subgroup_metrics(y[mask], p[mask], threshold)})
    return {
        "available": True,
        "feature_count": int(feature_frame.shape[1]),
        "counted_as_missing": "null/NaN in source-cleaned model predictors; zero is observed",
        "cohort_n": len(y),
        "groups": groups,
        "limitations": [
            "Descriptive subgroups of the same evaluation cohort; no causal interpretation.",
            "Small groups are unstable; no confidence intervals or subgroup model selection.",
            "Single-class ROC-AUC/AP and undefined ratios are null.",
        ],
    }


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_comparison(brfss, selection):
    if brfss["selection"] != selection:
        raise ValueError("Selection lock differs from the existing result report")
    rows = []
    for original in brfss["full"]:
        if original["name"] not in ("Logistic Regression", "LightGBM"):
            continue
        validation, test = original["validation"], original["metrics"]
        rows.append({
            "model": original["name"],
            "selected": original["name"] == selection["deployed_model"],
            "threshold": original["threshold"],
            "calibrated": original["calibrated"],
            "validation": {"n": int(sum(map(sum, validation["confusion"]))), "metrics": validation},
            "test": {"n": original["test_n"], "metrics": test},
        })
    if len(rows) != 2 or sum(row["selected"] for row in rows) != 1:
        raise ValueError("Expected the two frozen BRFSS candidates and one selected model")
    if max(rows, key=lambda row: row["validation"]["metrics"]["average_precision"])["model"] != selection["deployed_model"]:
        raise ValueError("The stored selection does not agree with validation average precision")
    return {
        "primary_metric": "average_precision",
        "selection_source": "validation",
        "selected_model": selection["deployed_model"],
        "selection_reason": "Highest validation average precision among the frozen full candidates.",
        "test_used_for_selection": False,
        "test_interpretation": "Post-hoc descriptive comparison; no model or threshold reselection.",
        "selection_locked_before_test": selection["locked_before_test"],
        "selection_locked_at": selection["locked_at"],
        "rows": rows,
    }


def build_payload(root=ROOT):
    from cardio.config import SCHEMAS

    relative_inputs = [
        "reports/brfss_test_predictions.csv", "reports/uci_oof_predictions.csv",
        "reports/brfss_results.json", "reports/uci_results.json",
        "reports/brfss_splits.json", "reports/selection_lock.json",
        "data/processed/brfss.pkl", "data/processed/uci.pkl", "cardio/config.py",
    ]
    hashes = {name: file_hash(root / name) for name in relative_inputs}
    brfss, uci = [read_json(root / "reports" / f"{key}_results.json") for key in ("brfss", "uci")]
    selection = read_json(root / "reports/selection_lock.json")
    splits = read_json(root / "reports/brfss_splits.json")
    datasets = {}
    for key, source, probability_column, evaluation, model, threshold in [
        ("brfss", "brfss_test_predictions.csv", "probability", "locked_independent_test",
         selection["deployed_model"], selection["threshold"]),
        ("uci", "uci_oof_predictions.csv", uci["selection"]["deployed_model"], "averaged_patient_oof",
         uci["selection"]["deployed_model"], uci["selection"]["threshold"]),
    ]:
        frame = pd.read_csv(root / "reports" / source, dtype={"row_id": str})
        processed = pd.read_pickle(root / "data/processed" / f"{key}.pkl")
        feature_names = [field["name"] for field in SCHEMAS[key]]
        matched = matched_features(frame, processed, feature_names,
                                   expected_ids=splits["test"] if key == "brfss" else processed.row_id,
                                   required_split="test" if key == "brfss" else None)
        y, p = validated_arrays(frame.target, frame[probability_column])
        if key == "brfss":
            selected_report = next(row for row in brfss["full"] if row["name"] == model)
            recomputed = subgroup_metrics(y, p, threshold)
            if len(y) != selected_report["test_n"] or any(
                not np.isclose(recomputed[metric], selected_report["metrics"][metric], rtol=1e-10, atol=1e-12)
                for metric in ("roc_auc", "average_precision", "precision", "recall", "brier")
            ):
                raise ValueError("Saved BRFSS predictions do not reproduce the frozen deployed-model metrics")
        datasets[key] = {
            "dataset": key, "model": model, "evaluation": evaluation,
            "n": len(y), "positive": int(y.sum()), "prevalence": float(y.mean()),
            "threshold": threshold, "weighting": "unweighted observations",
            "ranking": ranking_metrics(y, p),
            "missingness": missingness_metrics(y, p, matched, threshold),
            "limitations": [
                "Aggregate descriptive analysis of saved predictions; no fitting or threshold optimization.",
                "Ranking recorded disease labels is not a prospective disease forecast or treatment policy.",
            ] + (["Averaged patient OOF predictions; not independent external validation or final-model training scores."]
                 if key == "uci" else ["Survey weights and the complex survey design are not applied here."]),
        }
    comparison = frozen_comparison(brfss, selection)
    for name, original_hash in hashes.items():
        if file_hash(root / name) != original_hash:
            raise RuntimeError(f"Frozen input changed during generation: {name}")
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "frozen_prediction_analysis",
        "methods": {
            "ranking": "k=ceil(requested_fraction*n); cutoff=kth descending score; select every p>=cutoff, including ties.",
            "gain": "recall=selected positives/all positives",
            "lift": "selected precision/cohort prevalence",
            "random_baseline": "Expected recall=actual selected fraction; expected precision=cohort prevalence.",
            "missingness": "Source-cleaned predictors joined by unique row_id; targets and cohort membership verified.",
            "threshold": "Frozen deployed thresholds, unchanged for subgroup classification.",
            "uncertainty": "Point estimates only; not additional independent validation.",
        },
        "datasets": datasets,
        "brfss_comparison": comparison,
        "sources": [{"file": name, "sha256": value} for name, value in hashes.items()],
        "method_sources": [
            {"title": "IBM SPSS Modeler: reading model evaluation results",
             "url": "https://www.ibm.com/docs/en/spss-modeler/19.0.0?topic=node-reading-results-model-evaluation"},
            {"title": "scikit-learn average_precision_score",
             "url": "https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.average_precision_score.html"},
        ],
        "inputs_unchanged": True,
    }


def main():
    payload = build_payload()
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    for relative in ("reports/metrics-insights.json", "deployment/cardio-site/data/metrics-insights.json"):
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized, encoding="utf-8")
    print(json.dumps({key: {"n": row["n"], "positive": row["positive"],
                           "top_10_percent": row["ranking"][2],
                           "missing_groups": {g["bucket"]: g["n"] for g in row["missingness"]["groups"]}}
                      for key, row in payload["datasets"].items()}, indent=2))


if __name__ == "__main__":
    main()
