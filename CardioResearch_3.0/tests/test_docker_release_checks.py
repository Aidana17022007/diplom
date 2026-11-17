import copy
import hashlib
import json

import pytest

from cardio.release_checks import build_release_checks, docker_quality_limit


def evidence():
    return {'schema_version': 1, 'application_version': '3.3.0', 'status': 'passed',
            'docker': {'build_exit_code': 0},
            'runtime': {'health': {'status': 'ok', 'version': '3.3.0',
                                   'models': {'brfss': True, 'uci': True}}}}


def write(tmp_path, value=None):
    report = {'release': '3.3.0', 'checked_date': '2026-11-17',
              'docker': {'checked': True, 'status': 'passed', 'report': 'docker-audit.json'}}
    (tmp_path / 'release_3_3_validation.json').write_text(json.dumps(report), encoding='utf-8')
    if value is not None:
        (tmp_path / 'docker-audit.json').write_text(json.dumps(value), encoding='utf-8')
    return build_release_checks(tmp_path, '3.3.0')


def test_docker_requires_matching_saved_build_and_runtime_evidence(tmp_path):
    result = write(tmp_path, evidence())
    check = result['checks']['docker']
    assert check['status'] == 'passed'
    assert check['report_file'] == 'docker-audit.json'
    assert check['report_sha256'] == hashlib.sha256((tmp_path / 'docker-audit.json').read_bytes()).hexdigest()
    assert docker_quality_limit(result)['status'] == 'passed'
    assert 'полный набор тестов внутри контейнера не запускался' in docker_quality_limit(result)['detail']


@pytest.mark.parametrize('change', [
    lambda value: value.update(application_version='3.2.0'),
    lambda value: value['runtime']['health'].update(version='3.2.0'),
    lambda value: value['docker'].update(build_exit_code=None),
    lambda value: value['docker'].update(build_exit_code=False),
    lambda value: value['runtime']['health'].update(status='error'),
    lambda value: value['runtime']['health']['models'].update(uci=False),
    lambda value: value.pop('runtime'),
])
def test_incomplete_or_mismatched_evidence_never_becomes_passed(tmp_path, change):
    value = copy.deepcopy(evidence());change(value)
    result = write(tmp_path, value)
    assert result['checks']['docker']['status'] == 'unknown'
    assert docker_quality_limit(result)['status'] == 'not_verified'


def test_absent_or_bad_evidence_does_not_borrow_legacy_verification(tmp_path):
    (tmp_path / 'verification.json').write_text('{"docker":"passed"}')
    assert write(tmp_path)['checks']['docker']['status'] == 'unknown'
    (tmp_path / 'docker-audit.json').write_text('{broken')
    assert build_release_checks(tmp_path, '3.3.0')['checks']['docker']['status'] == 'unknown'


def test_failed_build_and_stale_passport_are_not_current_docker_success(tmp_path):
    value = evidence();value['docker']['build_exit_code'] = 1
    result = write(tmp_path, value)
    assert result['checks']['docker']['status'] == 'failed'
    assert docker_quality_limit(result)['status'] == 'failed'
    write(tmp_path, evidence())
    stale = build_release_checks(tmp_path, '3.4.0')
    assert stale['checks']['docker']['status'] == 'passed'
    assert docker_quality_limit(stale)['status'] == 'not_verified'


def test_local_quality_replaces_legacy_docker_state(monkeypatch, tmp_path):
    from cardio import api
    report = write(tmp_path, evidence())
    monkeypatch.setattr(api, 'release_checks', lambda: report)
    docker = [row for row in api.quality()['limits'] if row['id'] == 'docker']
    assert docker == [docker_quality_limit(report)]
    assert docker[0]['status'] == 'passed'
