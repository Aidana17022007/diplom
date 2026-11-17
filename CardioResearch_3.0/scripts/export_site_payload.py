"""Export only audited aggregate API responses into the hosted Worker source."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cardio import api

dest = ROOT / 'deployment/cardio-site/data'
dest.mkdir(parents=True, exist_ok=True)
payload = {
    'environment': api.environment(),
    'reliability': api.reliability(),
    'experiments': api.experiments(),
    'quality': api.quality(),
    'library': api.library(),
    'schema': {ds: api.schema(ds) for ds in ('brfss', 'uci')},
    'research': {ds: api.research(ds) for ds in ('brfss', 'uci')},
    'data': {ds: api.data(ds) for ds in ('brfss', 'uci')},
}
payload['experiment_details'] = {run['id']: api.experiment(run['id']) for run in payload['experiments']['runs']}
payload['quality']['hosting'] = {
    'runtime': 'JavaScript Cloudflare Worker',
    'training_runtime': 'Python; saved environment describes original offline training',
    'history': 'Read-only snapshots exported from the local experiment registry; updated on redeployment',
    'answers_persisted': False,
}
serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
for forbidden in ('C:\\\\Users', 'C:/Users', 'OneDrive', 'student_profile', 'train_ids', 'test_ids', 'row_id'):
    if forbidden in serialized:
        raise ValueError('Aggregate export unexpectedly contains a private path or row identifier: '+forbidden)
(dest / 'reports.json').write_text(serialized, encoding='utf-8')
print('Exported aggregate responses:', len(serialized.encode('utf-8')), 'bytes; SHA256', hashlib.sha256(serialized.encode('utf-8')).hexdigest())
