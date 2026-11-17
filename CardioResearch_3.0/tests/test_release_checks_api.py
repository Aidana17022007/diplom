import json
from pathlib import Path

from fastapi.testclient import TestClient
from cardio.api import app

ROOT = Path(__file__).resolve().parents[1]


def test_release_passport_and_quality_use_the_same_versioned_evidence():
    with TestClient(app) as client:
        passport = client.get('/api/release-checks')
        quality = client.get('/api/quality').json()
        health = client.get('/api/health').json()
    assert passport.status_code == 200
    report = passport.json()
    assert report['application_version'] == health['version']
    assert report == quality['release']
    assert quality['tests']['source'] == report['report_file']
    assert quality['tests']['source'] != 'verification.json'
    assert quality['tests']['passed'] == report['checks']['python']['passed']
    assert quality['tests']['measured_now'] is False
    assert report['measured_now'] is False
    assert report == json.loads((ROOT / 'reports/release-checks.json').read_text(encoding='utf-8'))
    assert report == json.loads((ROOT / 'deployment/cardio-site/data/release-checks.json').read_text(encoding='utf-8'))
    assert quality['privacy']['answers_saved'] is False
