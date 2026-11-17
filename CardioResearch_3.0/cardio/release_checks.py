"""Public provenance of saved release checks; never run tests from an API request."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


VERSION = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
REPORT_NAME = re.compile(r'^release_(\d+)_(\d+)(?:_(\d+))?_validation\.json$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
SCOPE = 'Saved software release verification; not a new measurement or clinical validation.'


def semantic_version(value):
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    return tuple(map(int, match.groups())) if match else None


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _counts(value, *, require_errors):
    """Missing or malformed counts cannot become a passing zero-test result."""
    result = {'status': 'unknown', **dict.fromkeys(('passed', 'failed', 'errors', 'skipped'))}
    if not isinstance(value, dict):
        return result
    invalid = False
    for key in ('passed', 'failed', 'errors', 'skipped'):
        count = value.get(key)
        if type(count) is int and count >= 0:
            result[key] = count
        elif key in value:
            invalid = True
    if invalid:
        return result
    if result['passed'] is None or result['failed'] is None:
        return result
    if require_errors and result['errors'] is None:
        return result
    if result['failed'] > 0 or (result['errors'] or 0) > 0:
        result['status'] = 'failed'
    elif result['passed'] > 0:
        result['status'] = 'passed'
    return result


def _builds(value):
    if not isinstance(value, dict):
        return {'status': 'unknown'}
    states = []
    for key in ('local_frontend', 'hosted_frontend'):
        text = value.get(key)
        if text in ('passed', 'TypeScript and Vite passed'):
            states.append('passed')
        elif text in ('failed', 'TypeScript failed', 'Vite failed'):
            states.append('failed')
        else:
            states.append('unknown')
    return {'status': 'failed' if 'failed' in states else 'passed' if states == ['passed', 'passed'] else 'unknown'}


def _browser(value):
    status = 'unknown'
    if isinstance(value, dict):
        if value.get('status') == 'failed':
            status = 'failed'
        elif value.get('checked') is False:
            status = 'not_verified'
        elif value.get('checked') is True and (value.get('status') == 'passed' or value.get('passed') is True):
            status = 'passed'
    detail = {
        'passed': 'Browser verification was explicitly recorded as passed.',
        'failed': 'Browser verification was recorded as failed.',
        'not_verified': 'Browser verification was not performed in this release.',
        'unknown': 'No unambiguous browser verification status is recorded.',
    }[status]
    return {'status': status, 'detail': detail}


def _startup(value, reports, release):
    result = {'status': 'unknown', 'detail': 'Saved startup evidence is missing or incomplete.',
              'report_file': None, 'report_sha256': None}
    if not isinstance(value, dict):
        return result
    if value.get('status') == 'failed':
        return {**result, 'status': 'failed', 'detail': 'Startup verification was recorded as failed.'}
    preflight = value.get('preflight')
    preflight_ok = isinstance(preflight, str) and (
        preflight == 'passed' or preflight.startswith('run.ps1 -CheckOnly passed;'))
    name = value.get('http_smoke')
    # Only a plain basename is allowed; no paths from a report are followed.
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.json', name):
        return result
    path = reports / name
    if path.is_symlink():
        return result
    try:
        raw = path.read_bytes()
        smoke = json.loads(raw)
    except (OSError, ValueError):
        return result
    if not isinstance(smoke, dict):
        return result
    result.update({'report_file': name, 'report_sha256': _hash(raw)})
    if smoke.get('release') != release:
        return result
    assets = smoke.get('frontend_assets')
    if (preflight_ok and smoke.get('checked') is True and smoke.get('health') is True
            and smoke.get('html') is True and isinstance(assets, list) and assets
            and all(isinstance(item, str) and item.startswith('/assets/') for item in assets)):
        result.update({'status': 'passed', 'detail': 'Saved preflight and HTTP smoke checks passed.'})
    elif smoke.get('checked') is False:
        result.update({'status': 'not_verified', 'detail': 'HTTP smoke verification was not completed.'})
    return result


def _public_hashes(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
            continue
        path = PurePosixPath(name)
        if (path.is_absolute() or '\\' in name or ':' in name or '..' in path.parts
                or not path.parts or path.parts[0] not in ('models', 'reports', 'data')):
            continue
        result[name] = digest
    return result


def build_release_checks(reports: Path, application_version: str):
    """Select the greatest eligible semantic version; fail closed on its bad report.

    Release filenames declare the version being checked. Their content must agree.
    An invalid newest candidate is not silently replaced by a historical success.
    All check statuses describe saved evidence only, even for a matching release.
    """
    reports = Path(reports)
    current = semantic_version(application_version)
    result = {
        'schema_version': 1, 'application_version': application_version,
        'checked_release': None, 'checked_date': None, 'report_file': None,
        'report_sha256': None, 'version_match': False, 'status': 'unknown',
        'scope': SCOPE, 'measured_now': False,
        'checks': {'python': _counts(None, require_errors=True),
                   'worker': _counts(None, require_errors=False),
                   'builds': _builds(None), 'browser': _browser(None),
                   'startup': _startup(None, reports, None)},
        'frozen_artifact_count': 0, 'frozen_artifacts_sha256': {},
        'issues': [],
    }
    if current is None:
        result['application_version'] = None
        result['issues'].append('invalid_application_version')
        return result
    candidates = []
    for path in reports.glob('release_*_validation.json'):
        match = REPORT_NAME.fullmatch(path.name)
        if match:
            version = tuple(int(part or 0) for part in match.groups())
            if version <= current:
                candidates.append((version, path))
    if not candidates:
        result['issues'].append('no_eligible_release_report')
        return result
    newest = max(version for version, _ in candidates)
    matches = [path for version, path in candidates if version == newest]
    if len(matches) != 1:
        result['issues'].append('ambiguous_release_reports')
        return result
    path = matches[0]
    result['report_file'] = path.name
    if path.is_symlink():
        result['issues'].append('invalid_release_report')
        return result
    try:
        raw = path.read_bytes()
        result['report_sha256'] = _hash(raw)
        report = json.loads(raw)
    except (OSError, ValueError):
        result['issues'].append('invalid_release_report')
        return result
    if not isinstance(report, dict) or semantic_version(report.get('release')) != newest:
        result['issues'].append('release_identity_mismatch')
        return result
    checked_date = report.get('checked_date')
    try:
        if not isinstance(checked_date, str) or date.fromisoformat(checked_date).isoformat() != checked_date:
            raise ValueError('date')
    except ValueError:
        result['issues'].append('invalid_checked_date')
        return result
    result.update({'checked_release': report['release'], 'checked_date': checked_date,
                   'version_match': newest == current, 'status': 'current' if newest == current else 'stale'})
    result['checks'] = {
        'python': _counts(report.get('python_tests'), require_errors=True),
        'worker': _counts(report.get('worker_tests'), require_errors=False),
        'builds': _builds(report.get('builds')),
        'browser': _browser(report.get('browser')),
        'startup': _startup(report.get('startup'), reports, report['release']),
    }
    hashes = _public_hashes(report.get('frozen_artifacts_sha256'))
    result.update({'frozen_artifact_count': len(hashes), 'frozen_artifacts_sha256': hashes})
    if newest != current:
        result['issues'].append('checked_release_is_older_than_application')
    if any(check['status'] == 'unknown' for check in result['checks'].values()):
        result['issues'].append('some_checks_have_no_unambiguous_evidence')
    return result
