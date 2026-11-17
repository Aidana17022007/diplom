"""Run: python -m scripts.audit_explanations [--pilot]. No model fitting."""
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits
from cardio.explain import permutation_shap
from cardio.explanation_audit import coalition_values, exact_from_values, sampled_from_values, comparison

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_inputs(dataset, protocol):
    model = joblib.load(ROOT / 'models' / f'{dataset}.joblib')
    pool = joblib.load(ROOT / 'models' / f'{dataset}_background.joblib')[model.features].reset_index(drop=True)
    rng = np.random.default_rng(protocol['seed'])
    candidates = np.arange(30, len(pool))
    if len(candidates) < protocol['profiles_per_dataset'] + 30:
        raise ValueError('Insufficient disjoint saved training-background rows')
    chosen = rng.choice(candidates, protocol['profiles_per_dataset'], replace=False)
    alternate = rng.choice(np.setdiff1d(candidates, chosen), 30, replace=False)
    return model, pool, chosen, alternate


def run(pilot=False):
    protocol_path = ROOT / 'reports/explanation_audit_protocol.json'
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    watched = [ROOT/'models'/f'{d}{suffix}.joblib' for d in protocol['datasets'] for suffix in ('','_background')]
    watched += [ROOT/'reports'/n for n in ('brfss_results.json','uci_results.json','selection_lock.json') if (ROOT/'reports'/n).exists()]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in watched}
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'pilot': pilot,
              'protocol_sha256': digest(protocol_path), 'protocol': protocol,
              'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__},
              'inputs_sha256': hashes, 'datasets': []}
    for dataset in protocol['datasets']:
        model, pool, chosen, alternate = selected_inputs(dataset, protocol)
        background = pool.iloc[:30].to_numpy(dtype=float)
        alternative = pool.iloc[alternate].to_numpy(dtype=float)
        def predict(a):
            return model.raw_probability(pd.DataFrame(a, columns=model.features))
        records, timings = [], []
        ids = chosen[:1] if pilot else chosen
        for number, row in enumerate(ids, 1):
            x = pool.iloc[row].to_numpy(dtype=float)
            start = time.perf_counter()
            values = coalition_values(predict, background, x)
            exact = exact_from_values(values)
            enumeration_seconds = time.perf_counter() - start
            start = time.perf_counter()
            live, baseline = permutation_shap(predict, background, x)
            production_seconds = time.perf_counter() - start
            cached = sampled_from_values(values, 48, protocol['production_seed'])
            parity_error = float(np.max(np.abs(cached - live)))
            if parity_error > 1e-10 or abs(baseline-values[0]) > 1e-10:
                raise AssertionError('Cached sampling differs from deployed estimator')
            rec = {'profile_number': number,
                   'production_seed_48': comparison(exact, live),
                   'production_cached_max_delta': parity_error,
                   'exact_additivity_error': float(abs(values[0]+exact.sum()-values[-1])),
                   'production_additivity_error': float(abs(baseline+live.sum()-values[-1])),
                   'budget_runs': {}}
            for budget in protocol['permutation_budgets']:
                estimates = [sampled_from_values(values, budget, protocol['seed']+i) for i in range(protocol['seeds_per_budget'])]
                rec['budget_runs'][str(budget)] = [comparison(exact, estimate) for estimate in estimates]
            if not pilot:
                other_values = coalition_values(predict, alternative, x)
                other_exact = exact_from_values(other_values)
                rec['background_change'] = comparison(exact, other_exact)
                rec['background_change']['baseline_delta_pp'] = float((other_values[0]-values[0])*100)
            records.append(rec)
            timings.append({'exact_seconds': enumeration_seconds, 'production_48_seconds': production_seconds})
            print(f'{dataset} {number}/{len(ids)}: exact {enumeration_seconds:.2f}s, live {production_seconds:.2f}s, parity {parity_error:.2g}', flush=True)
        summary = []
        for budget in protocol['permutation_budgets']:
            runs = [v for rec in records for v in rec['budget_runs'][str(budget)]]
            summary.append({'permutations': budget, 'profile_seed_pairs': len(runs),
                            'mean_mae_pp': float(np.mean([r['mae_pp'] for r in runs])),
                            'p95_max_error_pp': float(np.quantile([r['max_error_pp'] for r in runs], .95)),
                            'worst_error_pp': max(r['max_error_pp'] for r in runs),
                            'mean_top3_overlap': float(np.mean([r['top3_overlap'] for r in runs])),
                            'mean_sign_agreement': float(np.mean([r['sign_agreement'] for r in runs if r['sign_agreement'] is not None]))})
        report['datasets'].append({'dataset': dataset, 'model': model.name, 'features': len(model.features),
                                   'coalitions_per_profile': 1 << len(model.features), 'profiles': len(records),
                                   'summary': summary, 'profiles_detail': records, 'timings': timings})
    report['inputs_unchanged'] = all(digest(ROOT/name) == value for name, value in hashes.items())
    assert report['inputs_unchanged']
    destination = ROOT/'reports'/('explanation_audit_pilot.json' if pilot else 'explanation_audit.json')
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Saved', destination.name, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        run(args.pilot)
