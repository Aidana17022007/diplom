"""Recompute descriptive diagnostics from frozen predictions, without fitting.

Usage: python scripts/build-evaluation.py --archive ../../CardioResearch_project.zip
The original archive is an input only. Only aggregate diagnostics are exported.
Use --check to verify the committed payload without changing it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile


SITE_ROOT = Path(__file__).resolve().parents[1]
PREFIX = "CardioResearch/reports/"
Z_95 = 1.959963984540054
RECONCILIATION_TOLERANCE = 1e-10


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def wilson_interval(successes: int, total: int) -> list[float] | None:
    """Two-sided 95% Wilson score interval under iid Bernoulli sampling."""
    if not 0 <= successes <= total:
        raise ValueError("Invalid binomial counts")
    if not total:
        return None
    p = successes / total
    z2 = Z_95**2
    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator
    radius = Z_95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def confusion_metrics(confusion: list[list[int]]) -> dict:
    (tn, fp), (fn, tp) = confusion
    if any(not math.isfinite(x) or x < 0 for x in (tn, fp, fn, tp)):
        raise ValueError("Confusion counts must be finite and nonnegative")
    n = tn + fp + fn + tp
    recall = ratio(tp, tp + fn)
    specificity = ratio(tn, tn + fp)
    return {
        "accuracy": ratio(tp + tn, n),
        "precision": ratio(tp, tp + fp),
        "recall": recall,
        "specificity": specificity,
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "balanced_accuracy": (recall + specificity) / 2
        if recall is not None and specificity is not None else None,
        "mcc": ratio(tp * tn - fp * fn, math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))),
        "npv": ratio(tn, tn + fn),
        "fpr": ratio(fp, fp + tn),
        "fnr": ratio(fn, fn + tp),
        "positive_rate": ratio(tp + fp, n),
        "prevalence": ratio(tp + fn, n),
    }


def rank_metrics(targets: list[int], probabilities: list[float]) -> tuple[float | None, float | None]:
    """Tie-aware ROC-AUC and non-interpolated Average Precision.

    ROC-AUC counts correctly ordered positive/negative pairs, with half credit
    for ties. AP sums precision times the recall increment at each distinct
    score. It is not trapezoidal area under a sampled PR curve.
    """
    positives = sum(targets)
    negatives = len(targets) - positives
    ordered = sorted(zip(probabilities, targets), reverse=True)
    true_positives = false_positives = 0
    ap_terms, auc_terms = [], []
    index = 0
    while index < len(ordered):
        score = ordered[index][0]
        group_positive = group_negative = 0
        while index < len(ordered) and ordered[index][0] == score:
            if ordered[index][1]:
                group_positive += 1
            else:
                group_negative += 1
            index += 1
        true_positives += group_positive
        false_positives += group_negative
        if positives:
            ap_terms.append(group_positive / positives * true_positives / (true_positives + false_positives))
        auc_terms.append(group_positive * (negatives - false_positives + group_negative / 2))
    return (ratio(math.fsum(auc_terms), positives * negatives),
            math.fsum(ap_terms) if positives else None)


def probability_bins(targets: list[int], probabilities: list[float], bins: int) -> list[dict]:
    buckets = [[] for _ in range(bins)]
    for y, probability in zip(targets, probabilities):
        buckets[min(int(probability * bins), bins - 1)].append((y, probability))
    result = []
    for index, bucket in enumerate(buckets):
        n = len(bucket)
        positive = sum(y for y, _ in bucket)
        result.append({
            "lower": index / bins,
            "upper": (index + 1) / bins,
            "n": n,
            "positive": positive,
            "negative": n - positive,
            "mean_probability": math.fsum(p for _, p in bucket) / n if n else None,
            "observed_rate": positive / n if n else None,
            "ci": wilson_interval(positive, n),
        })
    return result


def evaluate(targets: list[int], probabilities: list[float], threshold: float) -> dict:
    if not targets or len(targets) != len(probabilities):
        raise ValueError("Targets and probabilities must have the same nonzero length")
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must lie in [0, 1]")
    if any(y not in (0, 1) for y in targets):
        raise ValueError("Targets must be binary")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError("Probabilities must be finite and lie in [0, 1]")
    confusion = [[0, 0], [0, 0]]
    for y, probability in zip(targets, probabilities):
        confusion[y][int(probability >= threshold)] += 1
    metrics = confusion_metrics(confusion)
    metrics["roc_auc"], metrics["average_precision"] = rank_metrics(targets, probabilities)
    n, positive = len(targets), sum(targets)
    prevalence = positive / n
    brier_baseline = prevalence * (1 - prevalence)
    metrics["brier"] = math.fsum((p - y)**2 for y, p in zip(targets, probabilities)) / n
    metrics["ap_lift"] = ratio(metrics["average_precision"], prevalence) if metrics["average_precision"] is not None else None
    metrics["brier_skill"] = 1 - metrics["brier"] / brier_baseline if brier_baseline else None
    clipped = [min(1 - 1e-15, max(1e-15, p)) for p in probabilities]
    metrics["log_loss"] = -math.fsum(math.log(p) if y else math.log1p(-p) for y, p in zip(targets, clipped)) / n
    bins = probability_bins(targets, probabilities, 10)
    metrics["ece"] = math.fsum(b["n"] * abs(b["observed_rate"] - b["mean_probability"]) for b in bins if b["n"]) / n
    (tn, fp), (fn, tp) = confusion
    return {
        "threshold": threshold,
        "n": n,
        "positive": positive,
        "negative": n - positive,
        "metrics": metrics,
        "confusion": confusion,
        "intervals": {
            "precision": wilson_interval(tp, tp + fp),
            "recall": wilson_interval(tp, tp + fn),
            "specificity": wilson_interval(tn, tn + fp),
            "npv": wilson_interval(tn, tn + fn),
        },
        "baselines": {
            "majority_accuracy": max(prevalence, 1 - prevalence),
            "prevalence": prevalence,
            "brier": brier_baseline,
            "definition": "Descriptive constant probability equal to the prevalence of this evaluation sample; not a fitted or independently validated baseline.",
        },
        "calibration": [{k: b[k] for k in ("lower", "upper", "n", "mean_probability", "observed_rate", "ci")} for b in bins],
        "distribution": [{k: b[k] for k in ("lower", "upper", "negative", "positive")} for b in probability_bins(targets, probabilities, 20)],
    }


def parse_predictions(payload: bytes, probability_column: str) -> tuple[list[int], list[float]]:
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""))
    if not {"row_id", "target", probability_column}.issubset(reader.fieldnames or []):
        raise ValueError("Prediction CSV is missing required columns")
    targets, probabilities, identifiers = [], [], set()
    for row in reader:
        identifier = row["row_id"]
        if not identifier or identifier in identifiers:
            raise ValueError("Every prediction must have a unique nonempty row_id")
        identifiers.add(identifier)
        if row["target"] not in ("0", "1"):
            raise ValueError("Prediction CSV target must be 0 or 1")
        targets.append(int(row["target"]))
        probabilities.append(float(row[probability_column]))
    return targets, probabilities


def reconcile(actual: dict, expected: dict) -> dict:
    deltas = {}
    for name in ("roc_auc", "average_precision", "brier", "accuracy", "precision", "recall", "specificity", "f1"):
        observed, reference = actual["metrics"][name], expected[name]
        if observed is None or not math.isfinite(reference):
            raise ValueError(f"Cannot reconcile {name}")
        deltas[name] = abs(observed - reference)
        if deltas[name] > RECONCILIATION_TOLERANCE:
            raise ValueError(f"Frozen predictions do not reproduce {name}: delta={deltas[name]}")
    if actual["confusion"] != expected["confusion"]:
        raise ValueError("Frozen predictions do not reproduce the saved confusion matrix")
    return {"passed": True, "absolute_tolerance": RECONCILIATION_TOLERANCE,
            "max_absolute_metric_delta": max(deltas.values()), "metric_deltas": deltas}


def build_evaluation(archive_path: Path, reports_path: Path, created: str | None = None) -> dict:
    archive_bytes, reports_bytes = archive_path.read_bytes(), reports_path.read_bytes()
    reports = json.loads(reports_bytes)
    dataset_reports = {}
    member_hashes = {}
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        saved_selection = json.loads(archive.read(PREFIX + "selection_lock.json"))
        selection = reports["research"]["brfss"]["selection"]
        if saved_selection != selection or selection.get("locked_before_test") is not True:
            raise ValueError("BRFSS frozen selection lock differs from the site report")
        for dataset, member in (("brfss", "brfss_test_predictions.csv"), ("uci", "uci_oof_predictions.csv")):
            report = reports["research"][dataset]
            selected_name = report["selection"]["deployed_model"]
            rows = report["full"] if dataset == "brfss" else report["benchmark"]
            selected = next(row for row in rows if row["name"] == selected_name)
            reference = selected["metrics"] if dataset == "brfss" else selected["oof_metrics"]
            full_member = PREFIX + member
            csv_bytes = archive.read(full_member)
            member_hashes[full_member] = sha256(csv_bytes)
            targets, probabilities = parse_predictions(csv_bytes, "probability" if dataset == "brfss" else selected_name)
            diagnostics = evaluate(targets, probabilities, report["selection"]["threshold"])
            expected_n = report["protocol"]["test"] if dataset == "brfss" else reports["data"]["uci"]["retained"]
            if diagnostics["n"] != expected_n:
                raise ValueError(f"{dataset}: sample size differs from the frozen report")
            diagnostics.update({
                "dataset": dataset,
                "model": selected_name,
                "evaluation": "locked_independent_test" if dataset == "brfss" else "averaged_patient_oof",
                "reference_metrics": reference,
                "provenance": {
                    "prediction_member": full_member,
                    "prediction_sha256": member_hashes[full_member],
                    "probability_column": "probability" if dataset == "brfss" else selected_name,
                    "weighting": "unweighted respondent-level" if dataset == "brfss" else "unweighted patient-level",
                    "threshold_source": "Frozen pre-test validation maximum F1" if dataset == "brfss" else "Fixed 0.5; averaged OOF probabilities",
                    "retrained": False,
                    "selection_changed": False,
                    "row_identifiers_exported": False,
                    "reconciliation": reconcile(diagnostics, reference),
                    "limitations": [
                        "Post-hoc descriptive diagnostics; no model, calibration, or threshold is fitted to these predictions.",
                        "Wilson intervals assume iid observations and exclude model fitting and selection uncertainty; they are not simultaneous intervals.",
                        "Calibration uses ten equal-width bins [lower, upper), with probability 1 included in the final bin. Empty bins are null. ECE depends on these bins and is exploratory.",
                        "The constant-probability Brier baseline uses this evaluation sample's prevalence and is descriptive, not a deployable fitted comparator.",
                        "BRFSS survey weights, strata and clusters are not used in these diagnostics." if dataset == "brfss" else "OOF probabilities are averaged across two repeats per patient; overlapping CV training sets induce dependence not covered by Wilson intervals. These metrics differ from mean outer-fold scores and do not independently validate the final artifact.",
                    ],
                },
            })
            if dataset == "brfss":
                validation = selected["validation"]
                validation_confusion = [[int(c) for c in row] for row in validation["confusion"]]
                diagnostics["validation"] = {
                    "n": sum(map(sum, validation_confusion)),
                    "metrics": {**{k: v for k, v in validation.items() if k != "confusion"}, **confusion_metrics(validation_confusion)},
                    "confusion": validation_confusion,
                    "source": "Saved validation aggregates at the frozen selected threshold; no row-level validation probabilities were available for additional probability diagnostics.",
                }
            dataset_reports[dataset] = diagnostics
    return {
        "schema_version": 1,
        "created": created or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "archive": archive_path.name,
            "archive_sha256": sha256(archive_bytes),
            "reports": "data/reports.json",
            "reports_sha256": sha256(reports_bytes),
            "prediction_sha256": member_hashes,
        },
        "methods": {
            "fitting": "None; only frozen saved probabilities are evaluated.",
            "classification_rule": "probability >= threshold",
            "auc": "Positive-negative pair ordering with half credit for tied scores.",
            "average_precision": "Non-interpolated precision weighted by recall increments at each distinct score.",
            "confidence_level": 0.95,
            "interval_method": "Wilson score; iid descriptive intervals conditional on fixed predictions",
            "calibration_bins": 10,
            "distribution_bins": 20,
            "binning": "Equal width [lower, upper), last bin includes 1.",
            "log_loss_probability_clip": 1e-15,
            "undefined_values": "null",
        },
        "datasets": dataset_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=SITE_ROOT.parents[1] / "CardioResearch_project.zip")
    parser.add_argument("--reports", type=Path, default=SITE_ROOT / "data" / "reports.json")
    parser.add_argument("--output", type=Path, default=SITE_ROOT / "data" / "evaluation.json")
    parser.add_argument("--check", action="store_true", help="Check the saved payload without writing it")
    args = parser.parse_args()
    existing = json.loads(args.output.read_text(encoding="utf-8")) if args.check else None
    result = build_evaluation(args.archive, args.reports, existing["created"] if existing else None)
    if args.check:
        if result != existing:
            raise SystemExit("Evaluation payload differs from recomputed frozen predictions")
        print("Evaluation payload verified against frozen predictions and source SHA-256 hashes.")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"Wrote aggregate diagnostics: {args.output}")
    for dataset, report in result["datasets"].items():
        print(f"{dataset}: n={report['n']}, AP={report['metrics']['average_precision']:.12f}, max reconciliation delta={report['provenance']['reconciliation']['max_absolute_metric_delta']:.3g}")


if __name__ == "__main__":
    main()
