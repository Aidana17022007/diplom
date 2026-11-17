"""Refresh the same compact saved-release passport for Python and Worker."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from cardio.release_checks import build_release_checks


def export(root=ROOT):
    root = Path(root)
    package = json.loads((root / 'deployment/cardio-site/package.json').read_text(encoding='utf-8'))
    payload = build_release_checks(root / 'reports', package.get('version'))
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    for name in ('reports/release-checks.json', 'deployment/cardio-site/data/release-checks.json'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return payload


if __name__ == '__main__':
    result = export()
    print(json.dumps({key: result[key] for key in ('application_version', 'checked_release', 'status', 'report_file')}, ensure_ascii=False))
