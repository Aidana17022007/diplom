"""The public diagnostics must expose saved aggregates consistently."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from cardio.api import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name,scope', [
    ('metrics-insights', 'frozen_prediction_analysis'),
    ('development-study', 'exploratory_train_only'),
])
def test_saved_metrics_routes_match_reports_and_hosted_payloads(name, scope):
    expected = json.loads((ROOT / f'reports/{name}.json').read_text(encoding='utf-8'))
    hosted = json.loads((ROOT / f'deployment/cardio-site/data/{name}.json').read_text(encoding='utf-8'))
    with TestClient(app) as client:
        response = client.get(f'/api/{name}')
    assert response.status_code == 200
    assert response.json() == expected == hosted
    assert expected['scope'] == scope
    assert expected['inputs_unchanged'] is True
    forbidden = {'row_id', 'row_ids', 'sample_ids', 'target', 'targets', 'y_true',
                 'probabilities', 'input_values', 'coef_', 'estimators_'}

    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(expected)


def test_development_protocol_and_frozen_input_hashes_are_still_exact():
    report = json.loads((ROOT / 'reports/development-study.json').read_text(encoding='utf-8'))
    protocol = ROOT / 'reports/development-study-protocol.json'
    assert report['protocol_sha256'] == hashlib.sha256(protocol.read_bytes()).hexdigest()
    assert report['protocol'] == json.loads(protocol.read_text(encoding='utf-8'))
    assert report['conclusion']['no_production_replacement'] is True
    for name, expected in report['inputs_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
