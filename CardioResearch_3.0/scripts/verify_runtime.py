"""Read-only launcher preflight: packages, built assets, models and API inference.

Only synthetic schema-valid inputs are used. No training, installation or health
answer storage. --url additionally checks an already running loopback server.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import importlib.metadata as metadata
import json
import math
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get('src') if tag == 'script' else (
            attrs.get('href') if tag == 'link' and attrs.get('rel') == 'stylesheet' else None)
        if value:
            self.assets.append(value)


def validate_frontend(dist: Path) -> list[str]:
    """Catch incomplete builds, including stale index references to deleted assets."""
    index = dist / 'index.html'
    if not index.is_file():
        raise ValueError('Missing frontend/dist/index.html. Run setup.ps1 to build the interface.')
    parser = AssetParser()
    parser.feed(index.read_text(encoding='utf-8'))
    local = []
    for asset in parser.assets:
        parts = urlsplit(asset)
        if parts.scheme or parts.netloc:
            continue
        relative = unquote(parts.path).lstrip('/')
        target = (dist / relative).resolve()
        if not target.is_relative_to(dist.resolve()) or not target.is_file():
            raise ValueError(f'Missing or invalid frontend asset: {relative}. Rebuild the frontend.')
        local.append(relative)
    if not any(Path(asset).suffix == '.js' for asset in local):
        raise ValueError('The frontend has no local JavaScript entry point. Rebuild the frontend.')
    return local


def sample_values(fields):
    values = {}
    for field in fields:
        if field['kind'] == 'category':
            value = field['options'][0]['value']
        else:
            value = (field['min'] + field['max']) / 2
            if field.get('step') == 1:
                value = int(value)
        values[field['name']] = value
    return values


def validate_prediction(payload, dataset):
    if not isinstance(payload, dict) or payload.get('dataset') != dataset:
        raise ValueError(f'{dataset}: unexpected prediction response')
    for field in ('probability', 'threshold'):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'{dataset}: invalid {field}')
    if payload.get('positive') is not (payload['probability'] >= payload['threshold']):
        raise ValueError(f'{dataset}: decision does not match its threshold')
    if not payload.get('version') or not payload.get('model'):
        raise ValueError(f'{dataset}: model provenance missing')


def verify_server(url, schemas):
    parts = urlsplit(url)
    if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost', '::1') or parts.path not in ('', '/') or parts.query or parts.fragment or parts.username:
        raise ValueError('--url must be a loopback HTTP origin, e.g. http://127.0.0.1:8000')
    origin = url.rstrip('/')

    def request(path, payload=None):
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        req = Request(origin + path, data=body, headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=15) as response:
            return response.headers.get_content_type(), response.read()

    content_type, raw = request('/api/health')
    health = json.loads(raw)
    if content_type != 'application/json' or health.get('status') != 'ok' or not all(health.get('models', {}).get(ds) for ds in schemas):
        raise ValueError('Server health check did not confirm both models')
    content_type, raw = request('/')
    if content_type != 'text/html' or b'CardioResearch' not in raw:
        raise ValueError('Server does not serve the CardioResearch frontend')
    for dataset, fields in schemas.items():
        content_type, raw = request('/api/predict', {'dataset': dataset, 'values': sample_values(fields), 'explain': False})
        if content_type != 'application/json':
            raise ValueError('Prediction endpoint returned non-JSON content')
        validate_prediction(json.loads(raw), dataset)


def check_runtime(server_url=None):
    checks, warnings = [], []

    def check(name, action):
        try:
            detail = action()
            checks.append({'name': name, 'ok': True, 'detail': str(detail or 'passed')})
        except Exception as exc:
            checks.append({'name': name, 'ok': False, 'detail': f'{type(exc).__name__}: {exc}'})

    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'python': sys.executable,
              'python_version': sys.version.split()[0], 'checks': checks, 'warnings': warnings}
    if sys.version_info[:2] != (3, 12):
        checks.append({'name': 'Python', 'ok': False, 'detail': 'Python 3.12 is required by the saved model environment. Run setup.ps1 with Python 3.12.'})
        result['ok'] = False
        return result
    versions = {}
    core = {'numpy', 'pandas', 'scipy', 'scikit-learn', 'lightgbm'}
    for line in (ROOT / 'requirements-tested.txt').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        package, expected = line.split('==', 1)
        try:
            actual = metadata.version(package)
            versions[package] = actual
            if actual != expected:
                detail = f'{package}: installed {actual}, recorded {expected}'
                if package in core:
                    checks.append({'name': package, 'ok': False, 'detail': detail + '; saved ML model compatibility is not confirmed'})
                else:
                    warnings.append(detail + '; historical lock differs from this environment')
        except metadata.PackageNotFoundError:
            checks.append({'name': package, 'ok': False, 'detail': 'Missing dependency; run setup.ps1'})
    result['packages'] = versions
    check('Frontend assets', lambda: ', '.join(validate_frontend(ROOT / 'frontend' / 'dist')))
    if not any(not item['ok'] for item in checks):
        def models_and_api():
            import joblib
            from fastapi.testclient import TestClient
            from cardio.api import app, bundle
            from cardio.config import MODELS, SCHEMAS
            # Health only checks file existence; inference exercises deserialization
            # and the fitted preprocessing pipeline using synthetic values.
            with TestClient(app) as client:
                for dataset, fields in SCHEMAS.items():
                    model = bundle(dataset)
                    expected = [field['name'] for field in fields]
                    if model.features != expected:
                        raise ValueError(f'{dataset}: model/schema feature order mismatch')
                    background = joblib.load(MODELS / f'{dataset}_background.joblib')
                    if background.empty or not set(expected).issubset(background.columns):
                        raise ValueError(f'{dataset}: explanation background missing features or observations')
                    response = client.post('/api/predict', json={'dataset': dataset, 'values': sample_values(fields), 'explain': False})
                    response.raise_for_status()
                    validate_prediction(response.json(), dataset)
                    for route in (f'/api/schema/{dataset}', f'/api/research/{dataset}'):
                        response = client.get(route)
                        response.raise_for_status()
                        if not response.headers.get('content-type', '').startswith('application/json'):
                            raise ValueError(f'{route}: expected JSON')
                response = client.get('/')
                response.raise_for_status()
                if 'CardioResearch' not in response.text:
                    raise ValueError('Frontend route does not contain the application')
            return 'BRFSS and UCI: model loading, inference, backgrounds, schema, results and interface passed'

        check('Models and local API', models_and_api)
        if server_url:
            from cardio.config import SCHEMAS
            check('Running server', lambda: verify_server(server_url, SCHEMAS))
    result['ok'] = bool(checks) and all(item['ok'] for item in checks)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--url', help='Also check a running loopback HTTP server')
    parser.add_argument('--server-only', action='store_true', help='Check the running server after a successful local preflight')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if args.server_only:
        if not args.url:
            parser.error('--server-only requires --url')
        from cardio.config import SCHEMAS
        try:
            verify_server(args.url, SCHEMAS)
            result = {'python': sys.executable, 'python_version': sys.version.split()[0],
                      'ok': True, 'checks': [{'name': 'Running server', 'ok': True, 'detail': 'Health, frontend and BRFSS/UCI predictions passed'}], 'warnings': []}
        except Exception as exc:
            result = {'python': sys.executable, 'python_version': sys.version.split()[0],
                      'ok': False, 'checks': [{'name': 'Running server', 'ok': False, 'detail': str(exc)}], 'warnings': []}
    else:
        result = check_runtime(args.url)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"CardioResearch runtime: {result['python']} ({result['python_version']})")
        for item in result['checks']:
            print(f"{'OK' if item['ok'] else 'ERROR'} | {item['name']} | {item['detail']}")
        for warning in result['warnings']:
            print('NOTICE | ' + warning)
        print('Ready for local use.' if result['ok'] else 'Startup blocked. Fix the errors above; no packages or models were changed.')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
