"""Restore exact research tables and run the original Python suite in one command.

Only the generated sample_prediction.pdf output is redirected to a verification
directory. Test code, source data, expected values and assertions are unmodified.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    root = args.project_root.resolve()
    spec = importlib.util.spec_from_file_location('research_prepare', Path(__file__).with_name('prepare-research-data.py'))
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    recovery = prepare.recover(root, args.source_dir.resolve(), ['uci', 'brfss'], args.download)
    folder = root / 'data' / 'processed' / 'verification'
    folder.mkdir(parents=True, exist_ok=True)
    temp = (folder / ('pytest-tmp-' + uuid.uuid4().hex)).resolve()
    if temp.parent != folder.resolve() or temp.exists():
        raise RuntimeError('Expected a new test temporary directory inside verification output')
    before = prepare.frozen_files(root)

    class ReportOutput:
        def __truediv__(self, name):
            return (folder if name == 'sample_prediction.pdf' else root / 'reports') / name

    class PreserveReports:
        def pytest_collection_modifyitems(self, items):
            for item in items:
                if item.module.__name__.endswith('test_project'):
                    item.module.REPORTS = ReportOutput()

    sys.path.insert(0, str(root))
    import pytest
    previous = Path.cwd()
    try:
        os.chdir(root)
        print('Running the complete original Python test suite...', flush=True)
        code = pytest.main(['tests', '-q', '-o', f'cache_dir={folder / "pytest-cache"}',
                            f'--basetemp={temp}', f'--junitxml={folder / "pytest.xml"}'],
                           plugins=[PreserveReports()])
    finally:
        os.chdir(previous)
    unchanged = before == prepare.frozen_files(root)
    result = {'pytest_exit_code': int(code), 'frozen_files_unchanged': unchanged,
              'frozen_files_checked': len(before), 'recovery': recovery,
              'pdf_output_redirected': 'data/processed/verification/sample_prediction.pdf'}
    (folder / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'pytest_exit_code': int(code), 'frozen_files_unchanged': unchanged,
                      'result': str(folder / 'verification.json')}))
    if not unchanged:
        raise RuntimeError('Original models/reports changed during verification')
    raise SystemExit(int(code))


if __name__ == '__main__':
    main()
