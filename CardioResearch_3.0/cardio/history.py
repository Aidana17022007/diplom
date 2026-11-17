"""Append-only snapshots of research results; no submitted health answers.

Run ``python -m cardio.history`` after training or when importing an existing run.
The old ``runs`` table is deliberately left intact for backward compatibility.
Append-only behavior is enforced through this module and database triggers; it is
not protection against a database owner who can change the file or its schema.
"""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from .config import REPORTS, MODELS


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _connect(database):
    connection = sqlite3.connect(str(database), timeout=20)
    connection.execute('''CREATE TABLE IF NOT EXISTS experiment_snapshots (
        id TEXT PRIMARY KEY, dataset TEXT NOT NULL, created TEXT NOT NULL,
        training_created TEXT, source TEXT NOT NULL, model TEXT NOT NULL,
        model_version TEXT, average_precision REAL, roc_auc REAL,
        result_json TEXT NOT NULL, environment_json TEXT NOT NULL
    )''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS snapshots_no_update
        BEFORE UPDATE ON experiment_snapshots BEGIN
        SELECT RAISE(ABORT, 'Experiment snapshots are immutable'); END''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS snapshots_no_delete
        BEFORE DELETE ON experiment_snapshots BEGIN
        SELECT RAISE(ABORT, 'Experiment snapshots are immutable'); END''')
    # SQLite REPLACE can delete an existing row without firing its delete trigger
    # when recursive_triggers is off. Ignore duplicate IDs before insertion so
    # both INSERT OR REPLACE and our INSERT OR IGNORE preserve the first snapshot.
    connection.execute('''CREATE TRIGGER IF NOT EXISTS snapshots_no_replace
        BEFORE INSERT ON experiment_snapshots
        WHEN EXISTS (SELECT 1 FROM experiment_snapshots WHERE id=NEW.id)
        BEGIN SELECT RAISE(IGNORE); END''')
    return connection


def record_results(reports_dir=REPORTS, models_dir=MODELS, database=None, source='saved_results_import'):
    """Capture current artifacts exactly once for each result/environment/model hash.

    ``created`` is snapshot capture time. ``training_created`` comes from the saved
    environment and may be absent; the import time is never claimed as fit time.
    """
    reports_dir, models_dir = Path(reports_dir), Path(models_dir)
    database = Path(database) if database else reports_dir / 'experiments.sqlite'
    env_path = reports_dir / 'environment.json'
    environment = json.loads(env_path.read_text(encoding='utf-8')) if env_path.exists() else {}
    database.parent.mkdir(parents=True, exist_ok=True)
    ids = []
    with closing(_connect(database)) as connection, connection:
        for dataset in ('brfss', 'uci'):
            path = reports_dir / f'{dataset}_results.json'
            if not path.exists():
                continue
            result = json.loads(path.read_text(encoding='utf-8'))
            model_path = models_dir / f'{dataset}.joblib'
            model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest() if model_path.exists() else None
            model = result.get('selection', {}).get('deployed_model', 'Unknown')
            rows = result.get('full') or result.get('benchmark', [])
            selected = next((row for row in rows if row.get('name') == model), {})
            metrics = selected.get('metrics', {})
            material = {'dataset': dataset, 'result': result, 'model_sha256': model_hash,
                        'environment': environment}
            run_id = hashlib.sha256(_canonical(material).encode('utf-8')).hexdigest()
            connection.execute('''INSERT OR IGNORE INTO experiment_snapshots
                (id,dataset,created,training_created,source,model,model_version,
                 average_precision,roc_auc,result_json,environment_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
                run_id, dataset, datetime.now(timezone.utc).isoformat(), environment.get('started'),
                source, model, model_hash, metrics.get('average_precision'), metrics.get('roc_auc'),
                _canonical(result), _canonical(environment)))
            ids.append(run_id)
    return ids


def list_results(database=None, limit=100):
    database = Path(database) if database else REPORTS / 'experiments.sqlite'
    if not database.exists():
        return []
    with closing(sqlite3.connect(str(database))) as connection:
        connection.row_factory = sqlite3.Row
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_snapshots'").fetchone():
            return []
        rows = connection.execute('''SELECT id,dataset,created,training_created,source,model,
            model_version,average_precision,roc_auc FROM experiment_snapshots
            ORDER BY created DESC,id DESC LIMIT ?''', (min(max(int(limit), 1), 100),)).fetchall()
    return [dict(row) for row in rows]


def get_result(run_id, database=None):
    database = Path(database) if database else REPORTS / 'experiments.sqlite'
    if not database.exists():
        return None
    with closing(sqlite3.connect(str(database))) as connection:
        connection.row_factory = sqlite3.Row
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_snapshots'").fetchone():
            return None
        row = connection.execute('SELECT * FROM experiment_snapshots WHERE id=?', (run_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result['result'] = json.loads(result.pop('result_json'))
    result['environment'] = json.loads(result.pop('environment_json'))
    return result


if __name__ == '__main__':
    recorded = record_results()
    print(f'Captured {len(recorded)} current research snapshots; {len(list_results())} distinct snapshots stored.')
