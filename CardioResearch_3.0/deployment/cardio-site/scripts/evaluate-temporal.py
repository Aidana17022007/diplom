"""Audit BRFSS2024 schema and evaluate a frozen BRFSS2023 artifact.

This is exploratory cross-year transfer with two entirely unavailable predictors,
not an isolated estimate of temporal drift or clinical validation. No fitting,
threshold selection, calibration or model selection is performed here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


SOURCE_URL = 'https://www.cdc.gov/brfss/annual_data/2024/files/LLCP2024XPT.zip'
CODEBOOK_URL = 'https://www.cdc.gov/brfss/annual_data/2024/zip/codebook24_llcp-v2-508.zip'
LAYOUT_URL = 'https://www.cdc.gov/brfss/annual_data/2024/llcp_varlayout_24_onecolumn.html'
SOURCE_HASH = 'd33de91a584e866f657d29b1d5b51b5672467286ed22d021e36ee3c7b4d712a4'
CODEBOOK_HASH = '06c1c0e9c384d70c5b204e7869b1b1ad3f402a37a730c1d9a1f5aeee94fd1918'
ABSENT = {'BPHIGH6': 'hypertension', 'TOLDHI3': 'cholesterol'}


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(root: Path, source: Path, codebook: Path, destination: Path) -> dict:
    import joblib
    import numpy as np
    import pandas as pd
    from bs4 import BeautifulSoup
    sys.path.insert(0, str(root))
    from cardio.config import SCHEMAS
    from cardio.learning import metrics
    from cardio.prepare import clean_brfss

    if sha(source) != SOURCE_HASH or sha(codebook) != CODEBOOK_HASH:
        raise ValueError('The source/codebook version differs; review its schema before replacing fingerprints')
    frozen_paths = [p for folder in ['models', 'reports'] for p in (root / folder).rglob('*')
                    if p.is_file() and 'experiment_lab_runs' not in p.relative_to(root).parts]
    frozen = {str(p): sha(p) for p in frozen_paths}
    model_path = root / 'models' / 'brfss.joblib'
    model = joblib.load(model_path)
    fields = SCHEMAS['brfss']
    features = [f['name'] for f in fields]
    required = [f['source'].split(' / ')[0] for f in fields]
    targets = ['CVDINFR4', 'CVDCRHD4', '_MICHD']

    with zipfile.ZipFile(codebook) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(('.htm', '.html'))]
        if len(names) != 1:
            raise ValueError('Expected one official HTML codebook')
        text = re.sub(r'\s+', ' ', BeautifulSoup(archive.read(names[0]), 'html.parser').get_text(' ', strip=True))
    variables = set(re.findall(r'SAS Variable Name: (\w+)', text))
    absent = [name for name in required if name not in variables]
    if set(absent) != set(ABSENT) or not set(targets).issubset(variables):
        raise ValueError('The reviewed nine-predictor/two-missing schema no longer applies')

    chunks = []
    raw_n = mismatches = 0
    raw_columns = []
    with zipfile.ZipFile(source) as archive:
        names = [name for name in archive.namelist() if name.strip().lower().endswith('.xpt')]
        if len(names) != 1:
            raise ValueError('Expected exactly one XPT member')
        with archive.open(names[0]) as stream:
            for chunk in pd.read_sas(stream, format='xport', chunksize=20000, encoding='utf-8'):
                if not raw_columns:
                    raw_columns = list(chunk.columns)
                    if set(required) - set(raw_columns) != set(ABSENT):
                        raise ValueError('XPT schema differs from codebook feature audit')
                chunk.index = np.arange(raw_n, raw_n + len(chunk))
                raw_n += len(chunk)
                for name in absent:
                    chunk[name] = np.nan
                cleaned = clean_brfss(chunk)
                reference = chunk['_MICHD'].map({1: 1, 2: 0})
                mismatches += int((cleaned.target.fillna(-1) != reference.fillna(-1)).sum())
                chunks.append(cleaned)
                print(f'BRFSS2024 source rows: {raw_n}', flush=True)
    transfer = pd.concat(chunks, ignore_index=True)
    unknown = int(transfer.target.isna().sum())
    transfer = transfer.dropna(subset=['target']).reset_index(drop=True)
    transfer['target'] = transfer.target.astype(int)
    if raw_n != 457670 or mismatches or transfer.duplicated(['state', 'psu']).any():
        raise ValueError('Source count, target mapping or respondent uniqueness check failed')

    original = pd.read_pickle(root / 'data' / 'processed' / 'brfss.pkl')
    original = original.loc[original.split == 'test'].copy()
    masked = original.copy()
    masked[list(ABSENT.values())] = np.nan

    def cohort(frame, identity, year, label):
        probabilities = model.predict_proba(frame[features])[:, 1]
        scores = metrics(frame.target, probabilities, model.threshold)
        confusion = [[int(value) for value in row] for row in scores.pop('confusion')]
        w = frame.weight.to_numpy()
        weighted = metrics(frame.target, probabilities, model.threshold, weight=w)
        weighted.pop('confusion')
        calibration = []
        for index in range(10):
            lower, upper = index / 10, (index + 1) / 10
            selected = (probabilities >= lower) & ((probabilities < upper) if index < 9 else (probabilities <= upper))
            calibration.append({'lower': lower, 'upper': upper, 'n': int(selected.sum()),
                                'mean_probability': float(probabilities[selected].mean()) if selected.any() else None,
                                'observed_rate': float(frame.target.to_numpy()[selected].mean()) if selected.any() else None})
        return {'id': identity, 'year': year, 'label': label, 'n': len(frame),
                'positive': int(frame.target.sum()), 'negative': int(len(frame) - frame.target.sum()),
                'prevalence': float(frame.target.mean()), 'threshold': float(model.threshold),
                'weighting': 'unweighted', 'metrics': scores, 'confusion': confusion,
                'survey_weighted_metrics': weighted,
                'feature_missingness': {name: int(frame[name].isna().sum()) for name in features},
                'calibration': calibration}

    cohorts = [cohort(original, 'test_2023', 2023, {'ru': 'Тест 2023 · исходные признаки', 'kk': '2023 тесті · бастапқы белгілер'}),
               cohort(masked, 'masked_2023', 2023, {'ru': 'Тест 2023 · два признака скрыты', 'kk': '2023 тесті · екі белгі жасырылған'}),
               cohort(transfer, 'transfer_2024', 2024, {'ru': 'Перенос 2024 · два признака отсутствуют', 'kk': '2024-ке тасымалдау · екі белгі жоқ'})]
    # The baseline must still reproduce the old report before any new result is accepted.
    saved = pd.read_csv(root / 'reports' / 'brfss_test_predictions.csv')
    np.testing.assert_allclose(model.predict_proba(original[features])[:, 1], saved.probability.to_numpy(), rtol=0, atol=1e-12)
    if frozen != {str(p): sha(p) for p in frozen_paths}:
        raise RuntimeError('Frozen model/report hashes changed')

    schema_rows = []
    for field in fields:
        variable = field['source'].split(' / ')[0]
        schema_rows.append({'feature': field['name'], 'source': variable, 'present_2024': variable in variables,
                            'kind': field['kind'], 'label': field['label'],
                            'allowed_values': [o['value'] for o in field.get('options', [])],
                            'transformation': 'BMI / 100' if field['name'] == 'bmi' else '88 days -> 0; 77/99 -> missing' if field['name'] in ['physical_days', 'mental_days'] else 'Documented categories; other values -> missing'})
    output = {
        'schema_version': 1, 'status': 'complete', 'dataset': 'brfss', 'model': model.name,
        'threshold': float(model.threshold),
        'scope': {'ru': 'Исследовательский перенос между годами при изменившейся доступности признаков',
                  'kk': 'Белгілердің қолжетімділігі өзгерген кездегі жылдар арасындағы зерттеу тасымалы'},
        'missing_features': [{'feature': feature, 'source': source} for source, feature in ABSENT.items()],
        'cohorts': cohorts,
        'schema': {'required': required, 'present': [name for name in required if name in variables], 'absent': absent,
                   'features': schema_rows, 'source_raw_rows': raw_n, 'source_columns': len(raw_columns),
                   'unknown_target_removed': unknown, 'target_mismatches': mismatches,
                   'target': 'CVDINFR4=1 OR CVDCRHD4=1 => 1; both=2 => 0; otherwise exclude; checked against _MICHD',
                   'missing_policy': 'Absent predictors become NaN; the frozen training pipeline encodes unknown categorical values as -1. No fitting or replacement with a healthy category.'},
        'provenance': {'sources': [SOURCE_URL, CODEBOOK_URL, LAYOUT_URL], 'source_sha256': SOURCE_HASH,
                       'codebook_sha256': CODEBOOK_HASH, 'model_sha256': sha(model_path),
                       'created': datetime.now(timezone.utc).isoformat(),
                       'threshold_source': 'Original validation maximum F1; fixed before original held-out test; unchanged',
                       'frozen_files_unchanged': True, 'frozen_file_count': len(frozen),
                       'refit': False, 'recalibration': False, 'threshold_retuning': False},
        'limitations': {
            'ru': ['В 2024 нет BPHIGH6 и TOLDHI3. Результат одновременно отражает другой год, состав выборки и отсутствие двух признаков.',
                   'Контроль 2023 с двумя скрытыми признаками показывает чувствительность той же модели на тех же тестовых наблюдениях; это не новый независимый тест.',
                   'Основные метрики невзвешенные. Дополнительные оценки с весами не заменяют анализ сложного дизайна опроса.',
                   'Таблицы описывают зарегистрированное заболевание, а не будущие события. Новый год не является повторным наблюдением тех же людей.',
                   'Не проводились клиническая валидация, проверка в Казахстане, переобучение или выбор лучшей модели по данным 2024.',
                   'Average Precision зависит от доли положительного класса; изменение AP между годами само по себе не доказывает улучшение модели.'],
            'kk': ['2024 жылы BPHIGH6 және TOLDHI3 жоқ. Нәтиже басқа жылды, іріктеме құрамын және екі белгінің болмауын бірге көрсетеді.',
                   'Екі белгісі жасырылған 2023 бақылауы сол модельдің сол тест жазбаларындағы сезімталдығын көрсетеді; бұл жаңа тәуелсіз тест емес.',
                   'Негізгі метрикалар салмақсыз. Салмақпен қосымша бағалау сауалнаманың күрделі дизайнын талдауды алмастырмайды.',
                   'Кестелер болашақ оқиғаларды емес, тіркелген ауруды сипаттайды. Жаңа жыл сол адамдарды қайта бақылау емес.',
                   'Клиникалық валидация, Қазақстанда тексеру, қайта оқыту немесе 2024 деректері бойынша үздік модельді таңдау жүргізілген жоқ.',
                   'Average Precision оң кластың үлесіне тәуелді; жылдар арасындағы AP өзгерісі өздігінен модельдің жақсарғанын дәлелдемейді.']},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--codebook', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.project_root.resolve(), args.source.resolve(), args.codebook.resolve(), args.output.resolve())
    print(json.dumps({'status': report['status'], 'cohorts': [{k: c[k] for k in ['id', 'n', 'positive', 'metrics']} for c in report['cohorts']]}))
