"""Exports must retain fold semantics and agree with the displayed metric definitions."""
import copy
import csv
from io import StringIO
import json
from pathlib import Path

import pytest

from cardio.metrics_export import FIELDS, METRICS, export_rows, metrics_csv, metrics_from_confusion

ROOT = Path(__file__).resolve().parents[1]


def test_derived_counts_preserve_negative_mcc_and_exact_rates():
    metrics = metrics_from_confusion([[40, 10], [20, 30]])
    assert metrics == pytest.approx({'balanced_accuracy': .7, 'mcc': 1 / 6 ** .5,
                                    'npv': 2 / 3, 'fpr': .2, 'fnr': .4})
    assert metrics_from_confusion([[0, 50], [50, 0]])['mcc'] == -1


@pytest.mark.parametrize('matrix', [None, [[0, 0], [0, 0]], [[True, 1], [1, 1]],
                                   [[-1, 2], [1, 2]], [[1, 2, 3], [4, 5]]])
def test_invalid_or_empty_counts_do_not_invent_zero_metrics(matrix):
    assert all(value is None for value in metrics_from_confusion(matrix).values())


def test_cv_uses_equal_weight_fold_means_and_sample_sd_not_pooled_counts():
    report = {'benchmark': [{'name': 'Two folds', 'metrics': {'roc_auc': .83},
                            'folds': [{'confusion': [[9, 1], [1, 9]]},
                                      {'confusion': [[20, 80], [80, 20]]}]}]}
    before = copy.deepcopy(report)
    row = export_rows(report, 'uci', 'benchmark')[0]
    assert row['mcc'] == pytest.approx(.1)
    assert row['mcc_fold_sd'] == pytest.approx(.98 ** .5)
    assert row['balanced_accuracy'] == pytest.approx(.55)
    assert row['fold_count'] == 2
    assert row['derived_metrics_method'] == 'mean_of_fold_metrics'
    assert row['mcc'] != pytest.approx(metrics_from_confusion([[29, 81], [81, 29]])['mcc'])
    assert report == before


def test_undefined_fold_invalidates_mean_and_sd_without_dropping_that_fold():
    row = export_rows({'benchmark': [{'name': 'Undefined', 'folds': [
        {'confusion': [[5, 0], [0, 5]]}, {'confusion': [[0, 5], [0, 5]]}]}]}, 'uci', 'benchmark')[0]
    assert row['mcc'] is row['mcc_fold_sd'] is row['npv'] is row['npv_fold_sd'] is None
    assert row['balanced_accuracy'] == .75
    assert row['fold_count'] == 2


def test_csv_is_bom_encoded_formula_safe_and_missing_metadata_stays_blank():
    report = {'protocol': {'test': 85748}, 'benchmark': [
        {'name': ' \t=HYPERLINK("bad")', 'metrics': {'confusion': [[0, 50], [50, 0]]}},
        {'name': 'Модель, "екі"\nжол', 'metrics': {}}]}
    raw = metrics_csv(report, 'brfss', 'benchmark')
    assert raw.startswith('\ufeff')
    reader = csv.DictReader(StringIO(raw.lstrip('\ufeff')))
    rows = list(reader)
    assert reader.fieldnames == list(FIELDS)
    assert len(METRICS) == 13
    assert rows[0]['model'] == "' \t=HYPERLINK(\"bad\")"
    assert float(rows[0]['mcc']) == -1
    assert rows[0]['test_n'] == rows[0]['training_n'] == rows[0]['threshold'] == ''
    assert rows[0]['threshold_source'] == 'not_recorded_for_row'
    assert rows[1]['model'] == 'Модель, "екі"\nжол'
    assert rows[1]['mcc'] == rows[1]['mcc_fold_sd'] == ''


@pytest.mark.parametrize('dataset,experiment,n', [('brfss', 'benchmark', 8), ('brfss', 'full', 2), ('uci', 'benchmark', 8)])
def test_real_api_csv_matches_canonical_report(dataset, experiment, n):
    from fastapi.testclient import TestClient
    from cardio.api import app
    report = json.loads((ROOT / f'reports/{dataset}_results.json').read_text(encoding='utf-8'))
    with TestClient(app) as client:
        response = client.get(f'/api/research-export/{dataset}?experiment={experiment}')
    assert response.status_code == 200
    assert response.content == metrics_csv(report, dataset, experiment).encode('utf-8')
    assert response.content.startswith(b'\xef\xbb\xbf')
    assert response.headers['cache-control'] == 'no-store'
    rows = list(csv.DictReader(StringIO(response.content.decode('utf-8-sig'))))
    assert len(rows) == n
    for row in rows:
        assert all(key in row for key in METRICS)
        assert row['weighting'] == 'unweighted'
        if dataset == 'uci':
            assert row['fold_count'] == '6'
            assert row['derived_metrics_method'] == 'mean_of_fold_metrics'
        else:
            assert row['derived_metrics_method'] == 'confusion_counts'
            assert row['fold_count'] == ''
            assert all(row[key + '_fold_sd'] == '' for key in METRICS)
