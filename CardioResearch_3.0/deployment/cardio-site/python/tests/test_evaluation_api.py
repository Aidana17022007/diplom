"""HTTP parity for the new aggregate endpoints without loading ML dependencies."""
import csv
import importlib.util
import io
import json
from pathlib import Path
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('evaluation_api', ROOT / 'python/cardio/evaluation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = FastAPI()
module.register_evaluation_routes(app, ROOT / 'data')
client = TestClient(app)


class AggregateAPITests(unittest.TestCase):
    def test_payloads_and_csv_match_saved_aggregates(self):
        report = json.loads((ROOT / 'data/evaluation.json').read_text(encoding='utf-8'))
        for ds in ['brfss', 'uci']:
            payload = client.get('/api/evaluation/' + ds)
            self.assertEqual(payload.status_code, 200)
            self.assertEqual(payload.json(), module.evaluation_payload(report, ds))
            file = client.get('/api/evaluation-export/' + ds)
            self.assertEqual(file.json(), payload.json())
            self.assertIn('attachment;', file.headers['content-disposition'])
            file = client.get('/api/evaluation-export/' + ds + '?format=csv')
            rows = list(csv.DictReader(io.StringIO(file.content.decode('utf-8-sig'))))
            self.assertEqual(float(next(r for r in rows if r['metric'] == 'recall')['value']), payload.json()['metrics']['recall'])
            self.assertEqual(next(r for r in rows if r['metric'] == 'recall')['interval_method'], 'Wilson 95%; fixed predictions; sampling/design limitations apply')

    def test_invalid_inputs_and_missing_artifact(self):
        self.assertEqual(client.get('/api/evaluation/unknown').status_code, 400)
        self.assertEqual(client.get('/api/evaluation-export/brfss?format=html').status_code, 422)
        missing_app = FastAPI()
        module.register_evaluation_routes(missing_app, ROOT / 'missing-report-directory')
        self.assertEqual(TestClient(missing_app).get('/api/evaluation/brfss').status_code, 503)

    def test_transfer_and_download_are_identical(self):
        payload = client.get('/api/transfer/uci')
        self.assertEqual(payload.status_code, 200)
        self.assertEqual(sum(row['n'] for row in payload.json()['cohorts']), 617)
        self.assertEqual(client.get('/api/transfer-export/uci').json(), payload.json())


if __name__ == '__main__':
    unittest.main()
