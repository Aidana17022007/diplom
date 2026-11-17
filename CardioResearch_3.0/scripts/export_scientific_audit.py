"""Publish aggregate, reproducible diagnostics from the saved November experiments.

No training, record-level profiles, individual attributions or model parameters
are exported. The local API and Worker serve the same generated payload.
"""
from pathlib import Path
import hashlib
import json
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]


def build_payload(root=ROOT):
    reports = root / 'reports'
    literature = json.loads((reports / 'literature_experiments.json').read_text(encoding='utf-8'))
    explanation = json.loads((reports / 'explanation_audit.json').read_text(encoding='utf-8'))
    if explanation['pilot'] or not explanation['inputs_unchanged'] or not literature['inputs_unchanged']:
        raise ValueError('Expected completed audits with unchanged frozen inputs')
    sources = []
    for name in ['literature_experiments.json', 'explanation_audit.json']:
        sources.append({'file': name, 'sha256': hashlib.sha256((reports / name).read_bytes()).hexdigest()})
    datasets = []
    for dataset in explanation['datasets']:
        detail = dataset['profiles_detail']
        datasets.append({
            **{key: dataset[key] for key in ['dataset', 'model', 'features', 'coalitions_per_profile', 'profiles', 'summary']},
            'background_change_mean_mae_pp': mean(row['background_change']['mae_pp'] for row in detail),
            'background_change_max_error_pp': max(row['background_change']['max_error_pp'] for row in detail),
            'exact_max_additivity_error': max(row['exact_additivity_error'] for row in detail),
        })
    return {
        'schema_version': 1,
        'created_utc': max(literature['created_utc'], explanation['created_utc']),
        'scope': 'saved_exploratory_diagnostics',
        'production_model_replaced': False,
        'sources': sources,
        'threshold': literature['threshold'],
        'missingness': literature['missingness'],
        'calibration': literature['calibration'],
        'prevalence_scenarios': literature['prevalence_scenarios'],
        'literature_protocol': literature['protocol'],
        'explanation': {'protocol': explanation['protocol'], 'datasets': datasets},
    }


if __name__ == '__main__':
    encoded = json.dumps(build_payload(), ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    for destination in [ROOT / 'reports/scientific-audit.json', ROOT / 'deployment/cardio-site/data/scientific-audit.json']:
        destination.write_text(encoded, encoding='utf-8')
    print('Exported aggregate scientific audit; frozen inputs unchanged.')
