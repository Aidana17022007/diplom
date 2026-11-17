"""Bounded, local-only research experiments. Never replaces deployed artifacts.

Each outer fold owns its preprocessing and estimator. Learning-curve subsets
come only from that fold's training rows; perturbations affect its held-out rows.
Only aggregate results/configuration are persisted, never submitted health data.
"""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import math
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits
from starlette.requests import Request

from .config import SCHEMAS

FRACTIONS = (.2, .4, .6, .8, 1.)
MISSING_LEVELS = (0., .05, .1, .2)
NOISE_LEVELS = (0., .05, .1, .2)
FOLDS = 3
REPEATS = 3
BRFSS_LIMIT = 6000
METRICS = ('roc_auc', 'average_precision', 'accuracy', 'precision', 'recall', 'specificity', 'f1', 'brier')
ALGORITHMS = ('logistic_regression', 'random_forest')
TERMINAL = ('succeeded', 'failed', 'cancelled')


def now():
    return datetime.now(timezone.utc).isoformat()


class Cancelled(Exception):
    pass


def validate_config(value):
    if not isinstance(value, dict) or set(value) - {'dataset', 'algorithm', 'seed', 'c', 'max_depth'}:
        raise ValueError('Unknown experiment configuration fields')
    dataset, algorithm = value.get('dataset', 'uci'), value.get('algorithm', 'logistic_regression')
    seed = value.get('seed', 20261109)
    if dataset not in SCHEMAS or algorithm not in ALGORITHMS:
        raise ValueError('Choose a supported dataset and algorithm')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('Seed must be an integer between 0 and 4294967295')
    c, depth = value.get('c', 1.), value.get('max_depth', 5)
    if type(c) not in (int, float) or c not in (.1, 1., 10.):
        raise ValueError('C must be 0.1, 1 or 10')
    if type(depth) is not int or depth not in (3, 5, 8):
        raise ValueError('Tree depth must be 3, 5 or 8')
    return {'dataset': dataset, 'algorithm': algorithm, 'seed': seed, 'c': float(c), 'max_depth': depth}


def dataset_path(root, dataset):
    return Path(root) / 'data' / 'processed' / f'{dataset}.pkl'


def load_frame(root, config):
    path = dataset_path(root, config['dataset'])
    if not path.is_file():
        raise FileNotFoundError('Prepared research data are unavailable')
    frame = pd.read_pickle(path)
    features = [field['name'] for field in SCHEMAS[config['dataset']]]
    if not set(features + ['target', 'row_id']).issubset(frame.columns):
        raise ValueError('Prepared dataset has an incompatible schema')
    if frame.row_id.duplicated().any() or not frame.target.isin([0, 1]).all():
        raise ValueError('Prepared dataset has invalid labels or duplicate row IDs')
    source_rows = len(frame)
    if config['dataset'] == 'brfss':
        if 'split' not in frame or not frame['split'].isin(['train', 'test']).all():
            raise ValueError('Original BRFSS split is required')
        frame = frame.loc[frame['split'] == 'train'].copy()
        if len(frame) > BRFSS_LIMIT:
            indices, _ = train_test_split(np.arange(len(frame)), train_size=BRFSS_LIMIT,
                                          stratify=frame.target, random_state=config['seed'])
            frame = frame.iloc[np.sort(indices)].copy()
    if len(frame) < 60 or frame.target.nunique() != 2 or frame.target.value_counts().min() < 15:
        raise ValueError('Insufficient observations for the fixed experiment protocol')
    if not all(pd.api.types.is_numeric_dtype(frame[name]) for name in features):
        raise ValueError('Prepared features must be numeric')
    if np.isinf(frame[features].to_numpy(dtype=float)).any():
        raise ValueError('Infinite values are not supported')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    selected_digest = hashlib.sha256('\n'.join(frame.row_id.astype(str)).encode()).hexdigest()
    return frame.reset_index(drop=True), features, {'prepared_dataset_sha256': digest,
        'selected_row_ids_sha256': selected_digest, 'source_rows': source_rows,
        'source_scope': 'original BRFSS training pool only' if config['dataset'] == 'brfss' else 'UCI Cleveland',
        'rows': len(frame), 'positive': int(frame.target.sum()), 'features': len(features)}


def make_pipeline(config, seed):
    fields = SCHEMAS[config['dataset']]
    numeric = [field['name'] for field in fields if field['kind'] == 'number']
    categories = [field for field in fields if field['kind'] == 'category']
    pre = ColumnTransformer([
        ('numeric', Pipeline([('impute', SimpleImputer(strategy='median', keep_empty_features=True)),
                              ('scale', StandardScaler())]), numeric),
        ('category', Pipeline([('impute', SimpleImputer(strategy='constant', fill_value=-1)),
                               ('encode', OneHotEncoder(categories=[[-1] + [o['value'] for o in f['options']]
                                   for f in categories], handle_unknown='ignore', sparse_output=False))]),
         [field['name'] for field in categories])])
    if config['algorithm'] == 'logistic_regression':
        estimator = LogisticRegression(C=config['c'], class_weight='balanced', max_iter=1500, random_state=seed)
    else:
        estimator = RandomForestClassifier(n_estimators=100, max_depth=config['max_depth'],
            min_samples_leaf=3, class_weight='balanced', random_state=seed, n_jobs=2)
    return Pipeline([('preprocess', pre), ('model', estimator)])


def score(y, probability):
    y, probability = np.asarray(y), np.asarray(probability)
    if not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise ValueError('Invalid model probabilities')
    tn, fp, fn, tp = (int(n) for n in confusion_matrix(y, probability >= .5, labels=[0, 1]).ravel())
    ratio = lambda numerator, denominator: float(numerator / denominator) if denominator else None
    two_classes = len(np.unique(y)) == 2
    return {'roc_auc': float(roc_auc_score(y, probability)) if two_classes else None,
        'average_precision': float(average_precision_score(y, probability)) if np.any(y == 1) else None,
        'accuracy': ratio(tp + tn, len(y)), 'precision': ratio(tp, tp + fp),
        'recall': ratio(tp, tp + fn), 'specificity': ratio(tn, tn + fp),
        'f1': ratio(2 * tp, 2 * tp + fp + fn), 'brier': float(brier_score_loss(y, probability))}


def summarize(records):
    result = {}
    for key in METRICS:
        values = np.array([row[key] for row in records if row[key] is not None], dtype=float)
        result[key] = {'mean': float(values.mean()) if len(values) else None,
                       'sd': float(values.std(ddof=1)) if len(values) > 1 else None,
                       'valid_evaluations': len(values)}
    return result


def metric_delta(actual, reference):
    return {key: actual[key] - reference[key] if actual[key] is not None and reference[key] is not None else None
            for key in METRICS}


def nested_train_indices(indices, y, fractions=FRACTIONS, seed=0):
    """Deterministic nested class-stratified subsets of outer training rows."""
    rng = np.random.default_rng(seed)
    classes = {label: rng.permutation(indices[np.asarray(y)[indices] == label]) for label in (0, 1)}
    result = []
    for fraction in fractions:
        parts = [rows[:max(1, int(math.floor(len(rows) * fraction)))] for rows in classes.values()]
        result.append(np.sort(np.concatenate(parts)))
    return result


def perturb(frame, training, fields, kind, level, seed, feature=None):
    changed = frame.copy(deep=True)
    rng = np.random.default_rng(seed)
    if kind == 'missing':
        mask = rng.random(changed.shape) < level
        changed = changed.mask(mask)
    elif kind == 'drop_feature':
        if feature not in changed:
            raise ValueError('Unknown feature')
        changed[feature] = np.nan
    elif kind == 'noise':
        for field in fields:
            if field['kind'] != 'number':
                continue
            name = field['name']
            scale = float(training[name].std(ddof=0))
            if not math.isfinite(scale) or scale == 0 or level == 0:
                continue
            values = changed[name] + rng.normal(0, level * scale, len(changed))
            values = values.clip(field['min'], field['max'])
            if field.get('step') == 1:
                values = values.round()
            changed[name] = values
    else:
        raise ValueError('Unknown perturbation')
    return changed


def run_experiment(root, configuration, progress=None, cancel=None, pipeline_factory=None):
    config = validate_config(configuration)
    frame, features, provenance = load_frame(root, config)
    x, y = frame[features], frame.target.to_numpy()
    fields = SCHEMAS[config['dataset']]
    factory = pipeline_factory or make_pipeline
    started, created = time.perf_counter(), now()
    folds = list(StratifiedKFold(FOLDS, shuffle=True, random_state=config['seed']).split(x, y))
    plan = [('missing', level, None, REPEATS) for level in MISSING_LEVELS]
    plan += [('noise', level, None, REPEATS) for level in NOISE_LEVELS]
    plan += [('drop_feature', None, feature, 1) for feature in features]
    total = FOLDS * (len(FRACTIONS) + sum(item[3] for item in plan))
    completed = 0
    learning = {fraction: {'train': [], 'validation': [], 'train_n': [], 'validation_n': [], 'fit_seconds': []}
                for fraction in FRACTIONS}
    stress = {(kind, level, feature): {'metrics': [], 'delta': [], 'missing': []} for kind, level, feature, _ in plan}
    baseline = []
    split_digest = hashlib.sha256()

    def checkpoint(stage):
        if cancel and cancel.is_set():
            raise Cancelled('Cancellation requested')
        if progress:
            progress(min(99, round(completed / total * 100)), stage)

    # The service admits one active job. BLAS and forest parallelism are bounded.
    with threadpool_limits(limits=2):
        for fold_index, (training, validation) in enumerate(folds):
            split_digest.update(np.asarray(training, dtype='<i8').tobytes())
            split_digest.update(np.asarray(validation, dtype='<i8').tobytes())
            subsets = nested_train_indices(training, y, seed=(config['seed'] + fold_index) % 2**32)
            full_model, reference = None, None
            for fraction, subset in zip(FRACTIONS, subsets):
                checkpoint(f'learning:{fold_index + 1}/{FOLDS}:{fraction:g}')
                estimator = factory(config, (config['seed'] + fold_index) % 2**32)
                began = time.perf_counter()
                estimator.fit(x.iloc[subset], y[subset])
                fit_seconds = time.perf_counter() - began
                checkpoint(f'scoring:{fold_index + 1}/{FOLDS}:{fraction:g}')
                train_score = score(y[subset], estimator.predict_proba(x.iloc[subset])[:, 1])
                validation_score = score(y[validation], estimator.predict_proba(x.iloc[validation])[:, 1])
                point = learning[fraction]
                point['train'].append(train_score); point['validation'].append(validation_score)
                point['train_n'].append(len(subset)); point['validation_n'].append(len(validation))
                point['fit_seconds'].append(fit_seconds)
                if fraction == 1:
                    full_model, reference = estimator, validation_score
                    baseline.append(reference)
                completed += 1
            for kind, level, feature, repeats in plan:
                destination = stress[(kind, level, feature)]
                for repeat in range(repeats):
                    checkpoint(f'stress:{fold_index + 1}/{FOLDS}:{kind}:{feature or level}:{repeat + 1}')
                    # Same uniform draws at all missingness levels give nested masks.
                    perturb_seed = (config['seed'] + 10000 + 100 * fold_index + repeat) % 2**32
                    modified = perturb(x.iloc[validation], x.iloc[training], fields, kind, level, perturb_seed, feature)
                    actual = score(y[validation], full_model.predict_proba(modified)[:, 1])
                    destination['metrics'].append(actual); destination['delta'].append(metric_delta(actual, reference))
                    destination['missing'].append(float(modified.isna().to_numpy().mean()))
                    completed += 1
    checkpoint('finalizing')
    learning_curve = [{'fraction': fraction, 'train_n_mean': float(np.mean(point['train_n'])),
        'train_n_min': min(point['train_n']), 'train_n_max': max(point['train_n']),
        'validation_n_mean': float(np.mean(point['validation_n'])), 'train': summarize(point['train']),
        'validation': summarize(point['validation']), 'fit_seconds_mean': float(np.mean(point['fit_seconds']))}
        for fraction, point in learning.items()]
    stress_report = [{'kind': kind, 'level': level, **({'feature': feature} if feature else {}),
        'metrics': summarize(point['metrics']), 'delta': summarize(point['delta']),
        'unique_n': len(x), 'evaluations': len(point['metrics']),
        'actual_missing_fraction_mean': float(np.mean(point['missing']))}
        for (kind, level, feature), point in stress.items()]
    import sklearn
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
    return {'id': f"{config['dataset']}-{config['algorithm']}-{config_hash}", 'created_at': created,
        'config': config, 'n': len(x), 'positive': int(y.sum()), 'features': features,
        'baseline': summarize(baseline), 'learning_curve': learning_curve, 'stress': stress_report,
        'duration_seconds': time.perf_counter() - started,
        'protocol': {'evaluation': 'new_stratified_3_fold_cv', 'folds': FOLDS, 'threshold': .5,
            'weighting': 'unweighted', 'class_weight': 'balanced', 'fractions': list(FRACTIONS),
            'perturbation_repeats': REPEATS, 'brfss_training_cap': BRFSS_LIMIT,
            'preprocessing': 'fit separately within every training subset; fixed documented categorical vocabulary',
            'noise': 'Gaussian SD = level × outer-training numeric SD; bounded by feature schema; categorical values unchanged',
            'missing': 'additional MCAR cell masking; existing missing values retained; same draws across levels',
            'standard_deviation': 'Descriptive sample SD across fold or fold/perturbation evaluations; not a confidence interval',
            'selection': 'Fixed research configuration, no hyperparameter search and no deployment/model selection',
            'artifact_relation': 'New fold-specific estimators; does not evaluate or replace the previously deployed full UCI artifact',
            'model_parameters': {'C': config['c'], 'max_iter': 1500} if config['algorithm'] == 'logistic_regression'
                else {'n_estimators': 100, 'max_depth': config['max_depth'], 'min_samples_leaf': 3, 'n_jobs': 2}},
        'provenance': {**provenance, 'fold_indices_sha256': split_digest.hexdigest(),
            'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'sklearn': sklearn.__version__, 'numpy': np.__version__, 'pandas': pd.__version__},
        'limitations': ['Research configurations are distinct from the original nested-CV benchmark and frozen production models.',
            'Repeated use of these CV results for model selection requires a new independent evaluation.',
            'MCAR masking and bounded Gaussian noise are controlled perturbations, not a claim about real missingness mechanisms.',
            'Fold samples overlap in training. Descriptive SD does not quantify uncertainty of the full learning procedure.',
            'No clinical validation or future-event prediction is established.']}


class ExperimentManager:
    """One worker, bounded in-memory queue/history, aggregate-only files."""
    def __init__(self, root, runner=run_experiment):
        self.root, self.runner = Path(root), runner
        self.lock = threading.RLock()
        self.jobs = OrderedDict()
        self.cancels = {}
        self.limit = 12

    def snapshot(self, identifier):
        with self.lock:
            if identifier not in self.jobs:
                return None
            return copy.deepcopy(self.jobs[identifier])

    def summaries(self):
        with self.lock:
            return [{key: copy.deepcopy(value) for key, value in job.items() if key != 'result'}
                    for job in reversed(self.jobs.values())]

    def submit(self, configuration):
        config = validate_config(configuration)
        if not dataset_path(self.root, config['dataset']).is_file():
            raise FileNotFoundError('Prepared research data are unavailable')
        with self.lock:
            if any(job['status'] not in TERMINAL for job in self.jobs.values()):
                raise RuntimeError('An experiment is already running')
            while len(self.jobs) >= self.limit:
                old, _ = self.jobs.popitem(last=False); self.cancels.pop(old, None)
            identifier = uuid.uuid4().hex
            self.jobs[identifier] = {'id': identifier, 'status': 'queued', 'progress': 0,
                'stage': 'queued', 'created_at': now(), 'config': config}
            self.cancels[identifier] = threading.Event()
            threading.Thread(target=self._execute, args=(identifier,), daemon=True, name='cardio-experiment').start()
            return self.snapshot(identifier)

    def cancel(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None:
                return None
            if job['status'] not in TERMINAL:
                self.cancels[identifier].set(); job['status'] = 'cancel_requested'
            return copy.deepcopy(job)

    def _execute(self, identifier):
        def progress(percent, stage):
            with self.lock:
                self.jobs[identifier].update(progress=percent, stage=stage)
        with self.lock:
            job = self.jobs[identifier]
            if not self.cancels[identifier].is_set():
                job['status'] = 'running'
            configuration = dict(job['config'])
        try:
            result = self.runner(self.root, configuration, progress=progress, cancel=self.cancels[identifier])
            if self.cancels[identifier].is_set():
                raise Cancelled()
            directory = self.root / 'reports' / 'experiment_lab_runs'
            directory.mkdir(parents=True, exist_ok=True)
            result['id'] = identifier
            destination = directory / f'{identifier}.json'
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
            owned = sorted((p for p in directory.glob('*.json') if len(p.stem) == 32 and
                all(c in '0123456789abcdef' for c in p.stem)), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in owned[24:]:
                old.unlink()
            with self.lock:
                self.jobs[identifier].update(status='succeeded', progress=100, stage='completed', result=result, finished_at=now())
        except Cancelled:
            with self.lock:
                self.jobs[identifier].update(status='cancelled', stage='cancelled', finished_at=now())
        except Exception:
            # Do not reflect local paths or data values in API errors.
            with self.lock:
                self.jobs[identifier].update(status='failed', stage='failed',
                    error='Experiment could not complete. Check prepared data and local dependencies.', finished_at=now())


def local_request(request):
    try:
        peer = ipaddress.ip_address(request.client.host)
        hostname = request.url.hostname
        host_local = hostname == 'localhost' or ipaddress.ip_address(hostname).is_loopback
        return peer.is_loopback and host_local
    except (ValueError, AttributeError):
        return False


def register_experiment_lab_routes(app, root):
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse
    manager = ExperimentManager(root)
    app.state.experiment_lab = manager

    def require_local(request):
        if not local_request(request):
            raise HTTPException(403, 'Experiment execution is available only on loopback')

    async def require_write(request):
        require_local(request)
        origin = request.headers.get('origin')
        expected = f'{request.url.scheme}://{request.url.netloc}'
        if origin != expected or request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, 'Use the local application to start or cancel an experiment')

    @app.get('/api/experiment-lab')
    def report(request: Request):
        path = Path(root) / 'reports' / 'experiment-lab.json'
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema_version': 1, 'created_at': None, 'runs': []}
        local = local_request(request)
        if local:
            directory = Path(root) / 'reports' / 'experiment_lab_runs'
            saved = sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:24]
            for completed in saved:
                try:
                    record = json.loads(completed.read_text(encoding='utf-8'))
                    if isinstance(record, dict) and record.get('baseline') and record.get('learning_curve'):
                        data['runs'].append(record)
                except (ValueError, OSError):
                    continue
        available = [dataset for dataset in SCHEMAS if dataset_path(root, dataset).is_file()]
        jobs = manager.summaries() if local else []
        data['runner'] = {'available': local and bool(available), 'local': local,
            'available_datasets': available if local else [], 'algorithms': list(ALGORITHMS),
            'limits': {'active_jobs': 1, 'history_jobs': manager.limit, 'folds': FOLDS, 'brfss_rows': BRFSS_LIMIT,
                       'c': [.1, 1., 10.], 'max_depth': [3, 5, 8], 'cancel': 'cooperative between fitting/scoring steps'},
            'reason': None if local and available else 'Prepared datasets and a loopback Python application are required',
            'active_job': next((job for job in jobs if job['status'] not in TERMINAL), None), 'recent_jobs': jobs}
        return JSONResponse(data, headers={'Cache-Control': 'no-store'})

    @app.post('/api/experiment-lab/runs')
    async def submit(request: Request):
        await require_write(request)
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, 'Use application/json')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2048:
                raise HTTPException(413, 'Experiment configuration is too large')
        try:
            configuration = json.loads(raw)
            result = manager.submit(configuration)
        except (ValueError, TypeError, UnicodeError):
            raise HTTPException(422, 'Invalid experiment configuration') from None
        except FileNotFoundError:
            raise HTTPException(503, 'Restore the prepared dataset before starting') from None
        except RuntimeError:
            raise HTTPException(409, 'An experiment is already running') from None
        return JSONResponse(result, status_code=202, headers={'Cache-Control': 'no-store'})

    @app.get('/api/experiment-lab/runs/{identifier}')
    def status(identifier: str, request: Request):
        require_local(request)
        result = manager.snapshot(identifier)
        if result is None:
            raise HTTPException(404, 'Experiment not found in this server session')
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    @app.post('/api/experiment-lab/runs/{identifier}/cancel')
    async def cancel(identifier: str, request: Request):
        await require_write(request)
        result = manager.cancel(identifier)
        if result is None:
            raise HTTPException(404, 'Experiment not found in this server session')
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

