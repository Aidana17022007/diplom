import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('export_scientific_audit', ROOT / 'scripts/export_scientific_audit.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_generated_audit_matches_frozen_sources_and_hosted_copy():
    payload = module.build_payload()
    assert payload == json.loads((ROOT / 'reports/scientific-audit.json').read_text(encoding='utf-8'))
    assert payload == json.loads((ROOT / 'deployment/cardio-site/data/scientific-audit.json').read_text(encoding='utf-8'))
    for source in payload['sources']:
        assert source['sha256'] == hashlib.sha256((ROOT / 'reports' / source['file']).read_bytes()).hexdigest()
    assert payload['production_model_replaced'] is False
    assert [row['n'] for row in payload['calibration']] == [85748, 85748]
    assert all(row['profiles'] == 6 for row in payload['explanation']['datasets'])
    assert all(len(row['summary']) == 3 for row in payload['explanation']['datasets'])


def test_audit_excludes_record_level_data_and_preserves_units():
    payload = module.build_payload()
    forbidden = {'profiles_detail', 'row_ids', 'row_id', 'input_values', 'contributions', 'y_true', 'y_pred', 'probabilities', 'coef_', 'estimators_'}
    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(payload)
    for dataset in payload['explanation']['datasets']:
        assert dataset['background_change_mean_mae_pp'] > dataset['summary'][1]['mean_mae_pp']
        assert all(row['profile_seed_pairs'] == 120 for row in dataset['summary'])
    assert max(r['roc_auc'] for r in payload['prevalence_scenarios']) - min(r['roc_auc'] for r in payload['prevalence_scenarios']) < 1e-10


def test_local_scientific_audit_route():
    from fastapi.testclient import TestClient
    from cardio.api import app
    with TestClient(app) as client:
        response = client.get('/api/scientific-audit')
    assert response.status_code == 200
    assert response.json() == module.build_payload()
