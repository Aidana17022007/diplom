"""Saved release provenance must never invent a current passing verification."""
import hashlib
import json
from pathlib import Path

import pytest

from cardio.release_checks import build_release_checks
from scripts.export_release_checks import export


def saved(release='3.2.0'):
    return {
        'release': release, 'checked_date': '2026-11-17',
        'python_tests': {'passed': 117, 'failed': 0, 'errors': 0},
        'worker_tests': {'passed': 85, 'failed': 0},
        'builds': {'local_frontend': 'TypeScript and Vite passed', 'hosted_frontend': 'TypeScript and Vite passed'},
        'browser': {'checked': False},
        'startup': {'preflight': 'run.ps1 -CheckOnly passed; ready', 'http_smoke': 'smoke.json'},
        'frozen_artifacts_sha256': {'models/brfss.joblib': 'a' * 64},
    }


def write_report(folder, release='3.2.0', payload=None):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('release_' + release.replace('.', '_') + '_validation.json')
    path.write_text(json.dumps(payload if payload is not None else saved(release)), encoding='utf-8')
    return path


def test_current_report_has_exact_provenance_and_separate_browser_limit(tmp_path):
    path = write_report(tmp_path)
    (tmp_path / 'smoke.json').write_text(json.dumps({'release': '3.2.0', 'checked': True, 'health': True,
                                                   'html': True, 'frontend_assets': ['/assets/app.js']}))
    result = build_release_checks(tmp_path, '3.2.0')
    assert result['status'] == 'current' and result['version_match'] is True
    assert result['checked_release'] == '3.2.0'
    assert result['report_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['checks']['python']['passed'] == 117
    assert result['checks']['worker']['passed'] == 85
    assert result['checks']['worker']['errors'] is None
    assert result['checks']['browser']['status'] == 'not_verified'
    assert result['checks']['startup']['status'] == result['checks']['builds']['status'] == 'passed'
    assert result['frozen_artifact_count'] == 1
    assert result['measured_now'] is False


def test_stale_report_preserves_historical_counts_without_current_claim(tmp_path):
    write_report(tmp_path)
    result = build_release_checks(tmp_path, '3.3.0')
    assert result['status'] == 'stale' and result['version_match'] is False
    assert result['checks']['python']['passed'] == 117
    assert 'checked_release_is_older_than_application' in result['issues']


def test_semantic_order_beats_filename_order_and_ignores_future_release(tmp_path):
    for version in ('3.9.0', '3.10.0', '4.0.0'):
        write_report(tmp_path, version)
    result = build_release_checks(tmp_path, '3.12.0')
    assert result['checked_release'] == '3.10.0'
    assert result['status'] == 'stale'


@pytest.mark.parametrize('content', ['{bad', '[]', '{"release":"3.1.0"}', '{"release":"3.3.0","checked_date":"no date"}'])
def test_bad_newest_report_does_not_fall_back_to_older_success(tmp_path, content):
    write_report(tmp_path, '3.2.0')
    (tmp_path / 'release_3_3_validation.json').write_text(content)
    result = build_release_checks(tmp_path, '3.3.0')
    assert result['status'] == 'unknown'
    assert result['checked_release'] is None
    assert result['checks']['python']['status'] == 'unknown'
    assert result['checks']['python']['passed'] is None


def test_missing_empty_and_ambiguous_reports_fail_closed(tmp_path):
    result = build_release_checks(tmp_path, '3.2.0')
    assert result['status'] == 'unknown'
    assert result['report_file'] is None
    assert all(row['status'] == 'unknown' for row in result['checks'].values())
    write_report(tmp_path)
    (tmp_path / 'release_3_2_validation.json').write_text(json.dumps(saved()))
    assert build_release_checks(tmp_path, '3.2.0')['issues'] == ['ambiguous_release_reports']


@pytest.mark.parametrize('counts,status', [
    ({}, 'unknown'), ({'passed': 0, 'failed': 0, 'errors': 0}, 'unknown'),
    ({'passed': 1, 'failed': 0}, 'unknown'),
    ({'passed': 1, 'failed': 2, 'errors': 0}, 'failed'),
    ({'passed': 0, 'failed': 0, 'errors': 1}, 'failed'),
    ({'passed': True, 'failed': 0, 'errors': 0}, 'unknown'),
    ({'passed': 1, 'failed': -1, 'errors': 0}, 'unknown'),
])
def test_python_status_requires_valid_explicit_nonempty_counts(tmp_path, counts, status):
    report = saved();report['python_tests'] = counts
    write_report(tmp_path, payload=report)
    assert build_release_checks(tmp_path, '3.2.0')['checks']['python']['status'] == status


def test_ambiguous_build_browser_and_startup_text_is_not_evidence(tmp_path):
    report = saved()
    report['builds']['local_frontend'] = 'not passed'
    report['browser'] = {'desktop': 'passed on another release'}
    report['startup'] = {'preflight': 'passed', 'http_smoke': '../private.json'}
    write_report(tmp_path, payload=report)
    result = build_release_checks(tmp_path, '3.2.0')
    for key in ('builds', 'browser', 'startup'):
        assert result['checks'][key]['status'] == 'unknown'


def test_explicit_browser_failure_is_not_hidden_by_conflicting_checked_flag(tmp_path):
    report = saved()
    report['browser'] = {'checked': False, 'status': 'failed'}
    write_report(tmp_path, payload=report)
    browser = build_release_checks(tmp_path, '3.2.0')['checks']['browser']
    assert browser['status'] == 'failed'
    assert browser['detail'] == 'Browser verification was recorded as failed.'


def test_smoke_from_another_release_cannot_validate_current_startup(tmp_path):
    write_report(tmp_path)
    (tmp_path / 'smoke.json').write_text(json.dumps({'release': '3.1.0', 'checked': True,
                                                   'health': True, 'html': True, 'frontend_assets': ['/assets/app.js']}))
    assert build_release_checks(tmp_path, '3.2.0')['checks']['startup']['status'] == 'unknown'


def test_private_paths_are_not_exposed_from_arbitrary_report_fields(tmp_path):
    report = saved();report['private_path'] = 'C:\\Users\\example\\secret'
    report['frozen_artifacts_sha256'].update({'C:/Users/example/secret': 'b' * 64,
                                            '../outside': 'b' * 64, 'reports/../../private': 'b' * 64,
                                            'reports/bad': 'invalid', 'data/private': 'c' * 64})
    write_report(tmp_path, payload=report)
    result = build_release_checks(tmp_path, '3.2.0')
    assert 'Users' not in json.dumps(result)
    assert result['frozen_artifact_count'] == 2
    assert set(result['frozen_artifacts_sha256']) == {'models/brfss.joblib', 'data/private'}


def test_generator_uses_package_version_and_writes_identical_public_copies(tmp_path):
    write_report(tmp_path / 'reports')
    package = tmp_path / 'deployment/cardio-site/package.json'
    package.parent.mkdir(parents=True)
    package.write_text('{"version":"3.3.0"}')
    payload = export(tmp_path)
    assert payload['status'] == 'stale'
    assert (tmp_path / 'reports/release-checks.json').read_bytes() == (tmp_path / 'deployment/cardio-site/data/release-checks.json').read_bytes()


@pytest.mark.parametrize('version', [None, '3.2', '3.02.0', 'latest', 'C:\\Users\\private'])
def test_invalid_application_version_fails_closed_without_echoing_it(tmp_path, version):
    result = build_release_checks(tmp_path, version)
    assert result['status'] == 'unknown' and result['application_version'] is None
