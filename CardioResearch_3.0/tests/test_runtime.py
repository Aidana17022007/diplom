"""Regression checks for startup failures that previously opened a blank app."""
import pytest

from scripts.verify_runtime import validate_frontend, validate_prediction, verify_server


def test_frontend_rejects_stale_hashed_asset(tmp_path):
    (tmp_path / 'index.html').write_text('<script src="/assets/deleted.js"></script>')
    with pytest.raises(ValueError, match='Missing or invalid frontend asset'):
        validate_frontend(tmp_path)


def test_frontend_requires_javascript_and_checks_styles(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'app.js').write_text('')
    (tmp_path / 'index.html').write_text('<script src="/assets/app.js"></script><link rel="stylesheet" href="/assets/missing.css">')
    with pytest.raises(ValueError, match='missing.css'):
        validate_frontend(tmp_path)
    (assets / 'missing.css').write_text('')
    assert validate_frontend(tmp_path) == ['assets/app.js', 'assets/missing.css']


@pytest.mark.parametrize('value', [True, None, '0.2', float('nan'), float('inf'), -0.1, 1.1])
def test_prediction_preflight_rejects_invalid_probability(value):
    payload = {'dataset': 'brfss', 'probability': value, 'threshold': .5, 'positive': False, 'version': 'abc', 'model': 'LR'}
    with pytest.raises(ValueError, match='invalid probability'):
        validate_prediction(payload, 'brfss')


def test_prediction_preflight_checks_decision_semantics():
    payload = {'dataset': 'brfss', 'probability': .5, 'threshold': .5, 'positive': True, 'version': 'abc', 'model': 'LR'}
    validate_prediction(payload, 'brfss')
    payload['positive'] = False
    with pytest.raises(ValueError, match='decision'):
        validate_prediction(payload, 'brfss')


@pytest.mark.parametrize('url', ['https://example.com', 'http://localhost.evil.test', 'http://127.0.0.1/api', 'file:///etc/passwd'])
def test_server_preflight_refuses_nonlocal_origin(url):
    with pytest.raises(ValueError, match='loopback'):
        verify_server(url, {})
