"""Scientific invariants and local job boundary, using explicit synthetic fixtures.

These fixtures do not supply the published research report, which is produced
from restored source datasets by scripts/build-experiment-lab.py.
"""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SOURCE = Path(__file__).resolve().parents[1] / 'cardio' / 'experiment_lab.py'
spec = importlib.util.spec_from_file_location('cardio.experiment_lab', SOURCE)
lab = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lab
spec.loader.exec_module(lab)


def synthetic_frame(dataset='uci', n=90):
    rng = np.random.default_rng(7)
    columns = {}
    for field in lab.SCHEMAS[dataset]:
        if field['kind'] == 'category':
            columns[field['name']] = rng.choice([o['value'] for o in field['options']], n).astype(float)
        else:
            columns[field['name']] = rng.uniform(field['min'], field['max'], n)
    result = pd.DataFrame(columns)
    result['target'] = np.arange(n) % 2
    result['row_id'] = [f'synthetic_test_{i}' for i in range(n)]
    return result


@pytest.fixture
def data_root(tmp_path):
    directory = tmp_path / 'data' / 'processed'; directory.mkdir(parents=True)
    synthetic_frame().to_pickle(directory / 'uci.pkl')
    return tmp_path


def test_configuration_bounds_are_strict():
    assert lab.validate_config({})['dataset'] == 'uci'
    for configuration in [{'seed': True}, {'seed': -1}, {'seed': 2**32}, {'c': '1'}, {'max_depth': True},
                          {'dataset': 'private'}, {'algorithm': 'shell'}, {'command': 'x'}, {'c': float('nan')}]:
        with pytest.raises((ValueError, TypeError)):
            lab.validate_config(configuration)


def test_nested_subsets_never_include_outer_validation():
    y = np.array([0] * 80 + [1] * 20)
    training, validation = next(lab.StratifiedKFold(3, shuffle=True, random_state=8).split(np.zeros(100), y))
    subsets = lab.nested_train_indices(training, y, seed=9)
    for subset in subsets:
        assert not set(subset) & set(validation)
        assert len(np.unique(y[subset])) == 2
        assert len(set(subset)) == len(subset)
    assert all(set(left).issubset(right) for left, right in zip(subsets, subsets[1:]))
    assert set(subsets[-1]) == set(training)
    assert all(np.array_equal(a, b) for a, b in zip(subsets, lab.nested_train_indices(training, y, seed=9)))


def test_preprocessing_statistics_are_fitted_on_training_only():
    train = synthetic_frame(n=90)
    validation = synthetic_frame(n=60)
    train['age'] = np.arange(90) + 18.; validation['age'] = 9000.
    estimator = lab.make_pipeline(lab.validate_config({}), 8)
    features = [f['name'] for f in lab.SCHEMAS['uci']]
    estimator.fit(train[features], train.target)
    scaler = estimator.named_steps['preprocess'].named_transformers_['numeric'].named_steps['scale']
    before = scaler.mean_.copy()
    estimator.predict_proba(validation[features])
    assert before[0] == train.age.mean()
    assert np.array_equal(before, scaler.mean_)
    assert before[0] != pd.concat([train.age, validation.age]).mean()


def test_stress_preserves_inputs_categories_and_missingness_semantics():
    train, held = synthetic_frame(n=90), synthetic_frame(n=60)
    fields = lab.SCHEMAS['uci']; names = [f['name'] for f in fields]
    train, held = train[names], held[names]
    held.loc[0, 'age'] = np.nan
    original = held.copy(deep=True)
    pd.testing.assert_frame_equal(lab.perturb(held, train, fields, 'missing', 0., 10), original)
    missing5 = lab.perturb(held, train, fields, 'missing', .05, 10)
    missing20 = lab.perturb(held, train, fields, 'missing', .2, 10)
    assert (missing5.isna().to_numpy() <= missing20.isna().to_numpy()).all()
    noisy = lab.perturb(held, train, fields, 'noise', .2, 10)
    for field in fields:
        if field['kind'] == 'category':
            pd.testing.assert_series_equal(noisy[field['name']], held[field['name']])
        else:
            assert noisy[field['name']].dropna().between(field['min'], field['max']).all()
    assert np.isnan(noisy.loc[0, 'age'])
    pd.testing.assert_frame_equal(held, original)
    dropped = lab.perturb(held, train, fields, 'drop_feature', None, 10, 'chol')
    assert dropped.chol.isna().all()
    pd.testing.assert_frame_equal(dropped.drop(columns='chol'), held.drop(columns='chol'))


def test_undefined_precision_is_not_reported_as_zero():
    result = lab.score([0, 1], [.1, .2])
    assert result['precision'] is None
    summary = lab.summarize([result])
    assert summary['precision'] == {'mean': None, 'sd': None, 'valid_evaluations': 0}
    assert summary['recall']['mean'] == 0


def test_actual_cv_runner_keeps_training_and_evaluation_disjoint(data_root):
    fits = []
    class RecordingEstimator:
        def fit(self, x, y):
            self.training = set(x.index); self.calls = 0; fits.append(self); return self
        def predict_proba(self, x):
            self.calls += 1
            if self.calls == 1:
                assert set(x.index) == self.training
            else:
                assert not set(x.index) & self.training
            p = np.full(len(x), .6)
            return np.column_stack([1-p, p])
    result = lab.run_experiment(data_root, {}, pipeline_factory=lambda c, seed: RecordingEstimator())
    assert len(fits) == 15
    assert result['learning_curve'][-1]['validation'] == result['baseline']
    assert result['n'] == 90
    assert result['protocol']['threshold'] == .5
    assert all(point['delta']['average_precision']['mean'] == 0 for point in result['stress'])
    assert len(result['stress']) == 21
    assert all(point['unique_n'] == 90 for point in result['stress'])
    assert all('row_id' not in point for point in result['stress'])
    json.dumps(result, allow_nan=False)


def test_brfss_uses_original_training_only_and_source_is_immutable(data_root):
    frame = synthetic_frame('brfss', 120)
    frame['split'] = np.where(np.arange(120) < 90, 'train', 'test')
    source = lab.dataset_path(data_root, 'brfss'); frame.to_pickle(source)
    before = source.read_bytes()
    selected, _, metadata = lab.load_frame(data_root, lab.validate_config({'dataset': 'brfss'}))
    assert len(selected) == 90 and selected['split'].eq('train').all()
    assert metadata['source_rows'] == 120
    assert source.read_bytes() == before


def test_cancellation_and_single_active_job(data_root):
    entered = threading.Event()
    def blocked_runner(root, config, progress, cancel):
        entered.set(); progress(30, 'waiting-test')
        assert cancel.wait(5)
        raise lab.Cancelled()
    manager = lab.ExperimentManager(data_root, runner=blocked_runner)
    job = manager.submit({})
    assert entered.wait(5)
    with pytest.raises(RuntimeError):
        manager.submit({})
    assert manager.cancel(job['id'])['status'] == 'cancel_requested'
    for _ in range(100):
        if manager.snapshot(job['id'])['status'] == 'cancelled':
            break
        time.sleep(.01)
    assert manager.snapshot(job['id'])['status'] == 'cancelled'
    assert not list((data_root / 'reports').rglob('*.json'))


def test_routes_require_loopback_and_same_origin_before_any_execution(data_root):
    app = FastAPI(); lab.register_experiment_lab_routes(app, data_root)
    local = TestClient(app, base_url='http://127.0.0.1:8000', client=('127.0.0.1', 1234))
    report = local.get('/api/experiment-lab')
    assert report.status_code == 200 and report.json()['runner']['available']
    assert report.headers['cache-control'] == 'no-store'
    assert local.post('/api/experiment-lab/runs', json={}).status_code == 403
    assert local.post('/api/experiment-lab/runs', json={}, headers={'origin': 'https://evil.example'}).status_code == 403
    valid = {'origin': 'http://127.0.0.1:8000'}
    assert local.post('/api/experiment-lab/runs', json={'seed': True}, headers=valid).status_code == 422
    assert local.post('/api/experiment-lab/runs', json={'x': 'a' * 3000}, headers=valid).status_code == 413
    remote = TestClient(app, base_url='http://127.0.0.1:8000', client=('192.0.2.1', 1234))
    assert not remote.get('/api/experiment-lab').json()['runner']['available']
    assert remote.post('/api/experiment-lab/runs', json={}, headers=valid).status_code == 403
    evil_host = TestClient(app, base_url='http://evil.example', client=('127.0.0.1', 1234))
    assert evil_host.post('/api/experiment-lab/runs', json={}, headers={'origin': 'http://evil.example'}).status_code == 403
    assert local.get('/api/experiment-lab/runs/unknown').status_code == 404

