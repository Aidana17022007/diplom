"""Restore archived research tables without refitting or modifying frozen reports.

Run using the original project's Python environment. BRFSS must match the exact
source hash recorded in reports/sources.json; current or substituted datasets are
never silently accepted. Only data/processed outputs are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import zipfile


BRFSS_URL = 'https://www.cdc.gov/brfss/annual_data/2023/files/LLCP2023XPT.zip'


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def frozen_files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): digest(p) for folder in ['models', 'reports']
            for p in sorted((root / folder).rglob('*'))
            if p.is_file() and 'experiment_lab_runs' not in p.relative_to(root).parts}


def download(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'CardioResearch-reproduction/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as output:
        while data := response.read(1024 * 1024):
            output.write(data)
    partial.replace(path)


def save_or_verify(frame, path: Path) -> None:
    import pandas as pd
    if path.exists():
        pd.testing.assert_frame_equal(pd.read_pickle(path), frame)
        return
    partial = path.with_suffix('.pkl.part')
    frame.to_pickle(partial)
    partial.replace(path)


def recover(root: Path, source_dir: Path, datasets: list[str], allow_download: bool) -> dict:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import train_test_split

    sys.path.insert(0, str(root))
    from cardio.config import SCHEMAS, SEED
    from cardio.prepare import clean_brfss

    before = frozen_files(root)
    output = {'schema_version': 1, 'seed': SEED, 'datasets': {}, 'frozen_files_unchanged': False}
    processed = root / 'data' / 'processed'
    processed.mkdir(parents=True, exist_ok=True)

    if 'uci' in datasets:
        audit_path = processed / 'uci_centers_audit.csv'
        audit = pd.read_csv(audit_path)
        frame = audit.loc[audit.center == 'Cleveland'].copy().reset_index(drop=True)
        frame['target'] = (frame.severity > 0).astype(int)
        frame['row_id'] = ['cleveland_' + str(i) for i in range(len(frame))]
        oof = pd.read_csv(root / 'reports' / 'uci_oof_predictions.csv')
        assert len(frame) == 303
        assert list(frame.row_id) == list(oof.row_id)
        np.testing.assert_array_equal(frame.target.to_numpy(), oof.target.to_numpy())
        save_or_verify(frame, processed / 'uci.pkl')
        output['datasets']['uci'] = {
            'n': len(frame), 'positive': int(frame.target.sum()),
            'source': 'Original archived uci_centers_audit.csv; Cleveland rows only',
            'source_sha256': digest(audit_path), 'oof_row_ids_and_targets_match': True,
            'processed_sha256': digest(processed / 'uci.pkl'),
        }

    if 'brfss' in datasets:
        manifest = json.loads((root / 'reports' / 'sources.json').read_text(encoding='utf-8'))
        expected = next(entry for entry in manifest if entry['file'] == 'LLCP2023XPT.zip')
        source = source_dir / expected['file']
        if not source.exists() and allow_download:
            download(source, BRFSS_URL)
        if not source.exists():
            raise FileNotFoundError(f'Missing {source}; provide the exact source or use --download')
        if source.stat().st_size != expected['bytes'] or digest(source) != expected['sha256']:
            raise ValueError('BRFSS source differs from the archived fingerprint; refusing substitution')
        chunks = []
        raw_n = mismatches = 0
        with zipfile.ZipFile(source) as archive:
            names = [name for name in archive.namelist() if name.strip().lower().endswith('.xpt')]
            if len(names) != 1:
                raise ValueError('Expected exactly one XPT member')
            with archive.open(names[0]) as stream:
                for chunk in pd.read_sas(stream, format='xport', chunksize=20000, encoding='utf-8'):
                    chunk.index = np.arange(raw_n, raw_n + len(chunk))
                    raw_n += len(chunk)
                    cleaned = clean_brfss(chunk)
                    reference = chunk['_MICHD'].map({1: 1, 2: 0})
                    mismatches += int((cleaned.target.fillna(-1) != reference.fillna(-1)).sum())
                    chunks.append(cleaned)
                    print(f'BRFSS source rows: {raw_n}', flush=True)
        frame = pd.concat(chunks, ignore_index=True).dropna(subset=['target']).reset_index(drop=True)
        frame['target'] = frame.target.astype(int)
        if frame.duplicated(['state', 'psu']).any():
            raise ValueError('Repeated state/PSU; original individual split is not applicable')
        train, test = train_test_split(np.arange(len(frame)), test_size=.2, stratify=frame.target,
                                      random_state=SEED)
        frame['split'] = 'train'
        frame.loc[test, 'split'] = 'test'
        audit = json.loads((root / 'reports' / 'brfss_data.json').read_text(encoding='utf-8'))
        splits = json.loads((root / 'reports' / 'brfss_splits.json').read_text(encoding='utf-8'))
        assert raw_n == audit['raw_rows'] and len(frame) == audit['retained'] and mismatches == 0
        assert len(train) == audit['train_n'] and len(test) == audit['test_n']
        tested = frame.loc[frame.split == 'test']
        assert list(tested.row_id) == list(splits['test'])
        frozen = pd.read_csv(root / 'reports' / 'brfss_test_predictions.csv', dtype={'row_id': str})
        assert list(tested.row_id) == list(frozen.row_id)
        np.testing.assert_array_equal(tested.target.to_numpy(), frozen.target.to_numpy())
        np.testing.assert_allclose(tested.weight.to_numpy(), frozen.weight.to_numpy(), rtol=1e-12)
        print('BRFSS split, targets and weights verified; checking frozen predictions...', flush=True)
        model = joblib.load(root / 'models' / 'brfss.joblib')
        probabilities = model.predict_proba(tested[model.features])[:, 1]
        delta = float(np.max(np.abs(probabilities - frozen.probability.to_numpy())))
        assert delta < 1e-12, f'Restored data do not reproduce frozen predictions: {delta}'
        print(f'BRFSS full-test probability parity: {delta:.3g}; checking processed table...', flush=True)
        save_or_verify(frame, processed / 'brfss.pkl')
        output['datasets']['brfss'] = {
            'n': len(frame), 'positive': int(frame.target.sum()), 'train_n': len(train),
            'test_n': len(test), 'source_url': BRFSS_URL, 'source_sha256': digest(source),
            'source_matches_archived_fingerprint': True, 'split_row_ids_match': True,
            'test_targets_and_weights_match': True, 'max_frozen_probability_delta': delta,
            'processed_sha256': digest(processed / 'brfss.pkl'),
        }

    if before != frozen_files(root):
        raise RuntimeError('Frozen models or reports changed during restoration')
    output['frozen_files_unchanged'] = True
    output['frozen_file_count'] = len(before)
    (processed / 'recovery-manifest.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(f'Recovery verified; {len(before)} frozen model/report files unchanged.', flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--datasets', nargs='+', choices=['uci', 'brfss'], default=['uci', 'brfss'])
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    print(json.dumps(recover(args.project_root.resolve(), args.source_dir.resolve(), args.datasets,
                             args.download), indent=2))
