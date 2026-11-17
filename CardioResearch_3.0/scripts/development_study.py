"""Bounded exploratory model development using only the original BRFSS fit pool.

The protocol is written before fitting. All candidate pipelines, including the
baseline, are freshly fitted inside shared folds. The deployed artifacts and
the original calibration/validation/test partitions are never evaluated here.
"""
from __future__ import annotations

import os
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
os.environ.setdefault('MKL_NUM_THREADS', '2')

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss, confusion_matrix
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from lightgbm import LGBMClassifier
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from cardio.config import SCHEMAS
from cardio.learning import preprocessing

SEED = 20261118
SAMPLE_N = 36000
METRICS = ('average_precision', 'roc_auc', 'brier', 'recall', 'precision', 'f1', 'balanced_accuracy')
CONFIGS = [
    {'id': 'lr_baseline', 'name': 'Logistic Regression · original configuration', 'algorithm': 'logistic_regression',
     'params': {'C': 10, 'class_weight': None, 'max_iter': 1500, 'random_state': SEED}},
    {'id': 'lgbm_leaf7', 'name': 'LightGBM · 7 leaves', 'algorithm': 'lightgbm',
     'params': {'n_estimators': 150, 'num_leaves': 7, 'min_child_samples': 200, 'reg_lambda': 10,
                'learning_rate': .05, 'max_depth': -1, 'verbosity': -1, 'n_jobs': 2,
                'random_state': SEED, 'deterministic': True, 'force_col_wise': True}},
    {'id': 'lgbm_leaf15', 'name': 'LightGBM · 15 leaves', 'algorithm': 'lightgbm',
     'params': {'n_estimators': 150, 'num_leaves': 15, 'min_child_samples': 300, 'reg_lambda': 20,
                'learning_rate': .05, 'max_depth': -1, 'verbosity': -1, 'n_jobs': 2,
                'random_state': SEED, 'deterministic': True, 'force_col_wise': True}},
    {'id': 'hgb_leaf15', 'name': 'HistGradientBoosting · 15 leaves', 'algorithm': 'hist_gradient_boosting',
     'params': {'max_iter': 150, 'max_leaf_nodes': 15, 'min_samples_leaf': 200, 'l2_regularization': 10,
                'learning_rate': .05, 'early_stopping': False, 'random_state': SEED}},
]


def fingerprint(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def frozen_hashes(root):
    names = ['data/processed/brfss.pkl', 'reports/brfss_splits.json', 'reports/brfss_results.json',
             'reports/brfss_search.json', 'reports/brfss_test_predictions.csv', 'reports/selection_lock.json',
             'reports/uci_results.json', 'reports/uci_folds.json', 'reports/uci_oof_predictions.csv']
    names += [p.relative_to(root).as_posix() for p in (root / 'models').glob('*.joblib')]
    return {name: fingerprint(root / name) for name in sorted(names)}


def select_training_sample(frame, split_ids, n=SAMPLE_N, seed=SEED):
    """Validate partition separation before looking up the training-only sample."""
    if frame.row_id.duplicated().any():
        raise ValueError('Duplicate source row IDs')
    fit = list(split_ids['fit'])
    if len(fit) != len(set(fit)):
        raise ValueError('Duplicate fit row IDs')
    forbidden = set().union(*(set(split_ids[name]) for name in ('calibration', 'validation', 'test')))
    if set(fit) & forbidden:
        raise ValueError('Fit pool overlaps an original holdout partition')
    indexed = frame.set_index('row_id', drop=False)
    if not set(fit).issubset(indexed.index):
        raise ValueError('Fit IDs are missing from the processed data')
    pool = indexed.loc[fit]
    if n < 6 or n > len(pool) or set(pool.target.unique()) != {0, 1}:
        raise ValueError('Expected a two-class fit pool and a valid sample size')
    if n == len(pool):
        selected = pool.copy()
    else:
        positions, _ = train_test_split(np.arange(len(pool)), train_size=n, stratify=pool.target,
                                       random_state=seed)
        selected = pool.iloc[positions].copy()
    if set(selected.row_id) & forbidden:
        raise ValueError('Sample includes an original holdout row')
    return selected


def scores(y, probability):
    y = np.asarray(y)
    p = np.asarray(probability, dtype=float)
    if y.ndim != 1 or y.shape != p.shape or set(np.unique(y)) != {0, 1}:
        raise ValueError('Expected matching two-class target and probability vectors')
    if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError('Probabilities must be finite in [0, 1]')
    tn, fp, fn, tp = confusion_matrix(y, p >= .5, labels=[0, 1]).ravel()
    recall, specificity = tp / (tp + fn), tn / (tn + fp)
    return {'average_precision': float(average_precision_score(y, p)),
            'roc_auc': float(roc_auc_score(y, p)), 'brier': float(brier_score_loss(y, p)),
            'recall': float(recall), 'precision': float(tp / (tp + fp)) if tp + fp else None,
            'f1': float(2 * tp / (2 * tp + fp + fn)),
            'balanced_accuracy': float((recall + specificity) / 2)}


def summarize(folds):
    means, stds = {}, {}
    for key in METRICS:
        values = [row['metrics'][key] for row in folds]
        # Do not silently change the number of evaluated folds when a ratio is undefined.
        means[key] = float(np.mean(values)) if all(value is not None for value in values) else None
        stds[key] = float(np.std(values, ddof=1)) if len(values) > 1 and all(value is not None for value in values) else None
    return means, stds


def make_pipeline(config):
    constructors = {'logistic_regression': LogisticRegression, 'lightgbm': LGBMClassifier,
                    'hist_gradient_boosting': HistGradientBoostingClassifier}
    return Pipeline([('pre', preprocessing('brfss')), ('model', constructors[config['algorithm']](**config['params']))])


def run(root=ROOT):
    started = time.perf_counter()
    before = frozen_hashes(root)
    baseline = next(row for row in json.loads((root / 'reports/brfss_search.json').read_text(encoding='utf-8'))
                    if row['name'] == 'Logistic Regression')
    if baseline['best_params'] != {'model__class_weight': None, 'model__C': 10}:
        raise ValueError('Original LR baseline parameters changed; review the fixed study protocol')
    splits = json.loads((root / 'reports/brfss_splits.json').read_text(encoding='utf-8'))
    sample = select_training_sample(pd.read_pickle(root / 'data/processed/brfss.pkl'), splits)
    features = [field['name'] for field in SCHEMAS['brfss']]
    X, y = sample[features], sample.target.to_numpy()
    folds = list(StratifiedKFold(3, shuffle=True, random_state=SEED).split(X, y))
    coverage = np.zeros(len(sample), dtype=int)
    for fit, validation in folds:
        assert not set(fit) & set(validation)
        coverage[validation] += 1
    assert np.all(coverage == 1)
    # Fingerprints bind the shared folds without publishing record-level IDs.
    # Canonical text is stable for string IDs; object-array bytes contain pointers.
    sample_digest = hashlib.sha256(json.dumps(sample.row_id.tolist(), separators=(',', ':')).encode('utf-8')).hexdigest()
    fold_digest = hashlib.sha256(b''.join(np.asarray(v, dtype='<i8').tobytes() for _, v in folds)).hexdigest()
    protocol = {
        'schema_version': 1, 'recorded_before_fit_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Bounded exploratory development-only comparison; not a new clinical validation',
        'seed': SEED, 'dataset': 'BRFSS 2023', 'fit_pool_n': len(splits['fit']), 'sample_n': len(sample),
        'sample': 'Stratified sample from original fit IDs only', 'sample_ids_sha256': sample_digest,
        'fold_validation_positions_sha256': fold_digest, 'cv': '3 shared stratified folds; 24000 fit / 12000 validation per fold',
        'preprocessing': 'Fresh original median imputation, scaling and fixed-category encoding inside each fold',
        'primary_metric': 'average_precision', 'diagnostic_threshold': .5,
        'calibration': 'None; raw model probabilities compared consistently',
        'models': CONFIGS, 'native_threads': 2, 'inputs_sha256': before,
        'original_holdouts_used': False, 'production_model_replaced': False,
        'sources': ['https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html',
                    'https://lightgbm.readthedocs.io/en/stable/Parameters.html'],
        'limitations': ['Exploratory comparison after earlier research; not an original preregistration',
                       'Three dependent CV folds; their sample SD is not a confidence interval',
                       'Selecting the largest mean AP introduces selection optimism',
                       'Performance on this subset does not establish improvement on the original test or in a clinic',
                       'No class weights or survey-design inference; no future-event horizon'],
    }
    encoded = (json.dumps(protocol, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    protocol_path = root / 'reports/development-study-protocol.json'
    protocol_path.write_bytes(encoded)
    print('Fixed protocol written before fitting:', protocol_path.name, flush=True)
    results = []
    with threadpool_limits(limits=2):
        for config in CONFIGS:
            result = {'id': config['id'], 'name': config['name'], 'config': config, 'folds': []}
            for fold, (fit, validation) in enumerate(folds, 1):
                print(config['id'], 'fold', fold, flush=True)
                tick = time.perf_counter()
                model = make_pipeline(config)
                with warnings.catch_warnings():
                    warnings.simplefilter('error', ConvergenceWarning)
                    model.fit(X.iloc[fit], y[fit])
                fit_seconds = time.perf_counter() - tick
                probability = model.predict_proba(X.iloc[validation])[:, 1]
                result['folds'].append({'fold': fold, 'n_fit': len(fit), 'n_validation': len(validation),
                                        'positive_validation': int(y[validation].sum()),
                                        'metrics': scores(y[validation], probability),
                                        'fit_seconds': fit_seconds})
            result['mean'], result['std'] = summarize(result['folds'])
            results.append(result)
    baseline_folds = results[0]['folds']
    for result in results:
        result['paired_ap_deltas'] = [row['metrics']['average_precision'] - base['metrics']['average_precision']
                                      for row, base in zip(result['folds'], baseline_folds)]
        result['delta_ap_vs_baseline'] = result['mean']['average_precision'] - results[0]['mean']['average_precision']
    best = max(results, key=lambda row: row['mean']['average_precision'])
    after = frozen_hashes(root)
    if before != after:
        raise RuntimeError('Frozen inputs changed during development study')
    import sklearn, lightgbm
    report = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'dataset': 'brfss', 'scope': 'exploratory_train_only', 'n': len(sample),
              'positive': int(y.sum()), 'protocol': protocol,
              'protocol_sha256': hashlib.sha256(encoded).hexdigest(), 'models': results,
              'conclusion': {'best_by_mean_ap_id': best['id'],
                             'delta_ap_vs_baseline': best['delta_ap_vs_baseline'],
                             'all_folds_positive': all(delta > 0 for delta in best['paired_ap_deltas']),
                             'no_production_replacement': True},
              'environment': {'python': sys.version.split()[0], 'sklearn': sklearn.__version__,
                              'lightgbm': lightgbm.__version__, 'numpy': np.__version__},
              'elapsed_seconds': time.perf_counter() - started,
              'inputs_sha256': before, 'inputs_unchanged': True}
    output = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    for path in [root / 'reports/development-study.json', root / 'deployment/cardio-site/data/development-study.json']:
        path.write_bytes(output)
    print(json.dumps({'models': [{ 'id': r['id'], 'ap': r['mean']['average_precision'],
                                  'delta': r['delta_ap_vs_baseline']} for r in results],
                      'elapsed_seconds': report['elapsed_seconds'], 'inputs_unchanged': True}), flush=True)
    return report


if __name__ == '__main__':
    run()
