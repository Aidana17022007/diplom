"""Packaging refuses unverified inputs and applies API registration only once."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


SITE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('package_diploma', SITE / 'scripts/package-diploma.py')
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def test_api_overlay_is_guarded_and_compiles():
    original = """version='2.0.0'
def library():
    return {'books':public_books}
@app.get('/api/research-export/{ds}')
def export(ds): pass
dist=ROOT/'frontend'/'dist'
"""
    output = package.patch_api(original, '3.0.0')
    compile(output, 'api.py', 'exec')
    assert output.count('register_experiment_lab_routes(app, ROOT)') == 1
    assert output.count('register_evaluation_routes(app, REPORTS)') == 1
    assert "version='3.0.0'" in output
    with pytest.raises(ValueError, match='original API'):
        package.patch_api(output, '3.0.0')
    with pytest.raises(ValueError, match='original API version'):
        package.patch_api(original.replace('2.0.0', '2.1.0'), '3.0.0')


def test_research_provenance_rejects_changed_table_or_failed_parity(tmp_path):
    digest = lambda value: hashlib.sha256(value).hexdigest()
    folder = tmp_path / 'project/data/processed'
    folder.mkdir(parents=True)
    archive = tmp_path / 'original.zip'
    source_hash = digest(b'original-source')
    with zipfile.ZipFile(archive, 'x') as zipped:
        zipped.writestr('CardioResearch/reports/sources.json', json.dumps([
            {'file': 'LLCP2023XPT.zip', 'sha256': source_hash}]))
        zipped.writestr('CardioResearch/data/processed/uci_centers_audit.csv', b'audit')
    manifest = {'frozen_files_unchanged': True, 'datasets': {
        'uci': {'n': 303, 'processed_sha256': digest(b'uci-fixture'),
                'source_sha256': digest(b'audit'), 'oof_row_ids_and_targets_match': True},
        'brfss': {'n': 428738, 'processed_sha256': digest(b'brfss-fixture'),
                  'source_sha256': source_hash, 'source_matches_archived_fingerprint': True,
                  'split_row_ids_match': True, 'test_targets_and_weights_match': True,
                  'train_n': 342990, 'test_n': 85748, 'max_frozen_probability_delta': 1e-16}}}
    for dataset in ('uci', 'brfss'):
        (folder / f'{dataset}.pkl').write_bytes(f'{dataset}-fixture'.encode())
    path = folder / 'recovery-manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    assert package.validate_research_data(tmp_path / 'project', archive)[0] == folder
    (folder / 'uci.pkl').write_bytes(b'changed')
    with pytest.raises(ValueError, match='table does not match'):
        package.validate_research_data(tmp_path / 'project', archive)
    (folder / 'uci.pkl').write_bytes(b'uci-fixture')
    manifest['datasets']['brfss']['max_frozen_probability_delta'] = .01
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='prediction parity failed'):
        package.validate_research_data(tmp_path / 'project', archive)
