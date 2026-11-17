"""Complete metric exports with explicit evaluation and aggregation provenance."""
from __future__ import annotations

import csv
import math
import re
from io import StringIO

BASE_METRICS = ('roc_auc', 'average_precision', 'accuracy', 'precision', 'recall',
                'specificity', 'f1', 'brier')
DERIVED_METRICS = ('balanced_accuracy', 'mcc', 'npv', 'fpr', 'fnr')
METRICS = BASE_METRICS + DERIVED_METRICS
FIELDS = ('dataset', 'experiment', 'model', 'evaluation', 'training_n', 'test_n',
          'threshold', 'threshold_source', 'weighting', 'fold_count', 'base_metrics_method',
          'derived_metrics_method', 'fold_sd_method') + METRICS + tuple(
              name + '_fold_sd' for name in METRICS) + (
                  'procedure_seconds', 'procedure_definition', 'predict_seconds')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def metrics_from_confusion(matrix):
    unavailable = dict.fromkeys(DERIVED_METRICS)
    if not isinstance(matrix, list) or len(matrix) != 2 or not all(
            isinstance(row, list) and len(row) == 2 for row in matrix):
        return unavailable
    counts = [value for row in matrix for value in row]
    if not all(finite(value) and value >= 0 for value in counts):
        return unavailable
    tn, fp, fn, tp = counts
    n = sum(counts)
    if not finite(n) or n <= 0:
        return unavailable
    ratio = lambda numerator, denominator: numerator / denominator if denominator > 0 else None
    recall, specificity = ratio(tp, tp + fn), ratio(tn, tn + fp)
    a, b, c, d = [value / n for value in counts]
    denominator = math.sqrt((d + b) * (d + c) * (a + b) * (a + c))
    return {'balanced_accuracy': None if recall is None or specificity is None else (recall + specificity) / 2,
            'mcc': max(-1., min(1., (a * d - b * c) / denominator)) if denominator > 0 else None,
            'npv': ratio(tn, tn + fn), 'fpr': ratio(fp, tn + fp), 'fnr': ratio(fn, tp + fn)}


def export_rows(report, dataset, experiment):
    if dataset not in ('brfss', 'uci') or experiment not in ('benchmark', 'full'):
        raise ValueError('Unsupported dataset or experiment')
    result = []
    for row in report.get(experiment, []):
        is_cv = dataset == 'uci'
        folds = row.get('folds') if isinstance(row.get('folds'), list) else []
        saved = row.get('metrics') or {}
        scores = {key: saved.get(key) if finite(saved.get(key)) else None for key in BASE_METRICS}
        std = {key: None for key in METRICS}
        method = 'unavailable'
        if is_cv:
            for key in BASE_METRICS:
                value = (row.get('std') or {}).get(key)
                std[key] = value if finite(value) and value >= 0 else None
            derived = [metrics_from_confusion(fold.get('confusion') if isinstance(fold, dict) else None)
                       for fold in folds]
            if folds:
                method = 'mean_of_fold_metrics'
            for key in DERIVED_METRICS:
                values = [fold[key] for fold in derived]
                if values and all(finite(value) for value in values):
                    mean = sum(values) / len(values)
                    scores[key] = mean
                    std[key] = math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1)) if len(values) > 1 else None
                else:
                    scores[key] = None
        else:
            derived = metrics_from_confusion(saved.get('confusion'))
            scores.update(derived)
            if any(finite(value) for value in derived.values()):
                method = 'confusion_counts'
        evaluation = (f'Mean of {len(folds)} outer CV folds; fold SD is not a confidence interval' if folds
                      else 'Outer CV; fold details unavailable') if is_cv else (
                          'Locked independent test' if experiment == 'full' else 'Fixed common benchmark test subset')
        procedure = ('Total outer CV procedure including search, prediction and scoring' if is_cv else
                     'Full fit plus calibration and validation procedure' if experiment == 'full' else
                     'Base CV plus randomized search and refit')
        threshold = row.get('threshold') if finite(row.get('threshold')) else None
        duration = row.get('search_seconds') if row.get('search_seconds') is not None else row.get('fit_seconds')
        record = {'dataset': dataset, 'experiment': experiment, 'model': row.get('name'),
                  'evaluation': evaluation, 'training_n': row.get('training_n'), 'test_n': row.get('test_n'),
                  'threshold': threshold, 'threshold_source': 'saved_row' if threshold is not None else 'not_recorded_for_row',
                  'weighting': 'unweighted', 'fold_count': len(folds) if is_cv and folds else None,
                  'base_metrics_method': 'saved_mean_of_outer_fold_metrics' if is_cv else 'saved_single_evaluation',
                  'derived_metrics_method': method,
                  'fold_sd_method': 'sample_ddof_1; descriptive, not confidence interval' if is_cv and len(folds) > 1 else None,
                  'procedure_seconds': duration if finite(duration) else None,
                  'procedure_definition': procedure,
                  'predict_seconds': row.get('predict_seconds') if finite(row.get('predict_seconds')) else None,
                  **scores, **{name + '_fold_sd': std[name] for name in METRICS}}
        result.append(record)
    return result


def safe_cell(value):
    if value is None or type(value) in (int, float) and not finite(value):
        return ''
    # Quoting CSV alone does not neutralize spreadsheet formulas. Numeric negatives
    # remain numeric; only potentially executable text cells receive an apostrophe.
    if isinstance(value, str) and re.match(r'^(?:[\t\r\n]|\s*[=+\-@])', value):
        return "'" + value
    return value


def metrics_csv(report, dataset, experiment):
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\r\n')
    writer.writeheader()
    for record in export_rows(report, dataset, experiment):
        writer.writerow({key: safe_cell(value) for key, value in record.items()})
    return '\ufeff' + stream.getvalue()
