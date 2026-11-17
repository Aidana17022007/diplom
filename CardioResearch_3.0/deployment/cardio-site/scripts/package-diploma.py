"""Package the original diploma plus this committed frontend and diagnostics.

Never overwrites archives, models, original research reports or draft documents.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT_PREFIX = 'CardioResearch/'
OVERLAY_MODULES = ('evaluation', 'literature', 'experiment_lab')
OVERLAY_REPORTS = ('evaluation', 'transfer', 'thesis-topic', 'literature-additions',
                   'disagreement', 'experiment-lab', 'temporal')
RESEARCH_FILES = ('uci.pkl', 'brfss.pkl', 'recovery-manifest.json')
REPRODUCE_CMD = '''@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\\Scripts\\python.exe" (
  echo First run setup.ps1 to install the recorded Python environment.
  pause
  exit /b 1
)
".venv\\Scripts\\python.exe" "deployment\\cardio-site\\scripts\\verify-research.py" --project-root . --source-dir "data\\source-cache" --download
set "verificationExitCode=%ERRORLEVEL%"
pause
exit /b %verificationExitCode%
'''.replace('\n', '\r\n')


def patch_api(original_text, version):
    """Apply reviewed overlays to the immutable original API, exactly once."""
    marker = "dist=ROOT/'frontend'/'dist'"
    if original_text.count(marker) != 1 or 'register_evaluation_routes' in original_text:
        raise ValueError('Expected the original API layout, without prior overlays')
    if original_text.count("version='2.0.0'") != 1:
        raise ValueError('Expected the original API version')
    text = original_text.replace(marker,
        'from .evaluation import register_evaluation_routes\n'
        'from .experiment_lab import register_experiment_lab_routes\n'
        'register_evaluation_routes(app, REPORTS)\n'
        'register_experiment_lab_routes(app, ROOT)\n\n' + marker)
    text = text.replace("version='2.0.0'", f"version='{version}'")
    library_start = text.index('def library():')
    library_end = text.index("@app.get('/api/research-export/{ds}')", library_start)
    block = text[library_start:library_end]
    if block.count("    return {'books':public_books") != 1:
        raise ValueError('Unexpected library route; refuse incomplete local overlay')
    block = block.replace('def library():', 'def library():\n    from .literature import with_literature_additions')
    block = block.replace("    return {'books':public_books", "    result = {'books':public_books")
    block = block.rstrip() + "\n    return with_literature_additions(result, optional_report('literature-additions.json') or {})\n\n\n"
    text = text[:library_start] + block + text[library_end:]
    compile(text, 'cardio/api.py', 'exec')
    return text


def validate_research_data(project_root, original):
    """Check provenance and hashes without deserializing trusted local pickles."""
    folder = project_root / 'data' / 'processed'
    manifest = json.loads((folder / 'recovery-manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('frozen_files_unchanged'):
        raise ValueError('Recovery did not preserve frozen research files')
    expected_rows = {'uci': 303, 'brfss': 428738}
    with zipfile.ZipFile(original) as source:
        sources = json.loads(source.read(ROOT_PREFIX + 'reports/sources.json'))
        brfss_source = next(item for item in sources if item['file'] == 'LLCP2023XPT.zip')
        uci_source = hashlib.sha256(source.read(ROOT_PREFIX + 'data/processed/uci_centers_audit.csv')).hexdigest()
    for dataset, n in expected_rows.items():
        entry = manifest['datasets'][dataset]
        with (folder / f'{dataset}.pkl').open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if entry['n'] != n or entry['processed_sha256'] != actual:
            raise ValueError(f'{dataset} prepared table does not match verified recovery manifest')
    uci, brfss = manifest['datasets']['uci'], manifest['datasets']['brfss']
    if uci['source_sha256'] != uci_source or not uci['oof_row_ids_and_targets_match']:
        raise ValueError('UCI provenance does not match the original archive')
    if (brfss['source_sha256'] != brfss_source['sha256'] or
            not all(brfss[key] for key in ('source_matches_archived_fingerprint', 'split_row_ids_match', 'test_targets_and_weights_match')) or
            brfss['train_n'] != 342990 or brfss['test_n'] != 85748 or
            brfss['max_frozen_probability_delta'] > 1e-12):
        raise ValueError('BRFSS provenance or frozen prediction parity failed')
    return folder, manifest


def prepare_local(site, original, destination, version):
    """Refresh only the explicit API overlays and aggregate reports for local QA."""
    if not (destination / 'cardio/config.py').is_file():
        raise ValueError('Local QA destination must be an extracted CardioResearch project')
    with zipfile.ZipFile(original) as source:
        api = patch_api(source.read(ROOT_PREFIX + 'cardio/api.py').decode('utf-8-sig'), version)
        frozen = {name[len(ROOT_PREFIX):]: hashlib.sha256(source.read(name)).hexdigest()
                  for name in source.namelist()
                  if name.startswith(tuple(ROOT_PREFIX + folder for folder in ('models/', 'reports/', 'output/')))}
    for name, expected in frozen.items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Original research file differs before QA overlay: {name}')
    for name in OVERLAY_MODULES:
        (destination / f'cardio/{name}.py').write_bytes((site / f'python/cardio/{name}.py').read_bytes())
    for name in OVERLAY_REPORTS:
        (destination / f'reports/{name}.json').write_bytes((site / f'data/{name}.json').read_bytes())
    (destination / 'setup.ps1').write_bytes((site / 'python/setup.ps1').read_bytes())
    (destination / 'cardio/api.py').write_text(api, encoding='utf-8')
    for name, expected in frozen.items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Original research file changed during QA overlay: {name}')
    print(json.dumps({'prepared_local': str(destination), 'version': version,
                      'modules': list(OVERLAY_MODULES), 'reports': list(OVERLAY_REPORTS),
                      'preserved_original_models_reports_drafts': len(frozen),
                      'frontend_copied': False}, ensure_ascii=False))


def main():
    site = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--destination', type=Path, help='New complete release ZIP; requires committed source')
    mode.add_argument('--prepare-local', type=Path, help='Extracted project to refresh API overlays for local QA')
    parser.add_argument('--research-data-root', type=Path, required=True,
                        help='Verified local project containing data/processed/{uci,brfss}.pkl and recovery-manifest.json')
    args = parser.parse_args()
    original = args.archive.resolve()
    version = json.loads((site / 'package.json').read_text(encoding='utf-8'))['version']
    if version != '3.0.0':
        raise ValueError('This overlay was verified for release 3.0.0')
    research_folder, recovery = validate_research_data(args.research_data_root.resolve(), original)
    if args.prepare_local:
        prepare_local(site, original, args.prepare_local.resolve(), version)
        return
    destination = args.destination.resolve()
    if destination.exists():
        raise FileExistsError(f'Preserve existing archive: {destination}')
    if subprocess.check_output(['git', '-C', str(site), 'status', '--porcelain']).strip():
        raise RuntimeError('Commit completed source before packaging')
    tracked = subprocess.check_output(['git', '-C', str(site), 'ls-files', '-z']).decode().split('\0')
    topic = json.loads((site / 'data/thesis-topic.json').read_text(encoding='utf-8'))
    release = '## Тема диплома\n\n' + '\n'.join(f'- {language.upper()}: {title}' for language,title in topic['titles'].items()) + '\n\n' + topic['scope']['ru'] + '\n\n' + '''## Обновление 3.0 — лаборатория исследований

- Добавлены разногласия моделей UCI, кривые обучения, проверки устойчивости к пропускам и шуму, а также перенос фиксированной BRFSS-модели на 2024 год с отдельным контролем отсутствующих признаков.
- Четыре новых воспроизводимых опыта LR/RF выполнены на UCI (303) и стратифицированной подвыборке BRFSS (6 000) только из исходной обучающей части. Это отдельный протокол трёхблочной CV; исходные опубликованные модели и результаты не заменяются. Разброс между блоками не является доверительным интервалом.
- В локальном приложении можно запускать ограниченные новые опыты, наблюдать прогресс и отменять запуск. Одновременно выполняется один опыт. Агрегированные результаты сохраняются в reports/experiment_lab_runs; публичная версия показывает готовые результаты и не запускает обучение.
- 3D-сравнение состояний артерии остаётся учебной визуализацией. Его геометрия не используется моделью для расчёта риска.
- В полный локальный архив включены восстановленные data/processed/uci.pkl и brfss.pkl с recovery-manifest.json. Их хеши и соответствие исходным разделениям проверены; исходные данные не входят в публичную сборку сайта.
- Для установки нужен Python 3.12. setup.ps1 выбирает существующее окружение 3.12, py -3.12 либо python версии 3.12; другой исполняемый файл можно указать через -PythonPath. Проверить выбор без установки можно с -CheckOnly. При наличии готового frontend/dist Node.js для запуска не требуется.
- После установки окружения запустите REPRODUCE.cmd либо команду ниже. Проверка восстанавливает таблицы из исходников, проверяет сохранённые прогнозы и запускает исходные Python-тесты. При отсутствии кэша она скачивает официальный архив CDC BRFSS2023 (около 93 МБ):

```powershell
python deployment/cardio-site/scripts/verify-research.py --project-root . --source-dir data/source-cache --download
```

- Методика и ограничения: deployment/cardio-site/docs/EXPERIMENT_LAB.md и DATA_REPRODUCTION.md. Новые опыты не устанавливают клиническую пригодность и не доказывают прогнозирование будущих событий. Основной текст диплома и сохранённые черновики требуют авторского обновления.

### Возможности выпуска 2.8 — исследовательский дашборд и экспорт визуализаций

- Главная страница стала исследовательским дашбордом: AP, ROC-AUC, recall, precision, ошибки по фактическим классам, калибровка, ориентир AP по доле класса и паспорт выборки.
- Контекст оценок обозначен явно: BRFSS — отложенный невзвешенный тест на 85 748 наблюдениях; UCI — усреднённые OOF-прогнозы на 303 наблюдениях, не среднее внешних CV-оценок. Сводку оценки с контекстом можно выгрузить в CSV.
- Настройки сравнения моделей сохраняются в рамках сессии. Парное сравнение экспортируется в CSV и SVG с названием набора, экспериментом, протоколом оценки и режимом взвешивания.
- Графики используют сокращённую сборку Plotly с нужными типами диаграмм; добавлено сохранение графиков в PNG.
- В 3D-атласе доступны полноэкранный режим и PNG текущего вида артерии. Учебная геометрия остаётся отдельной от оценки ML.
- Исходные модели и исследовательские отчёты сохранены. Переобучение моделей и редактирование основного текста диплома в этот выпуск не входят.

### Возможности выпуска 2.7

- Обновлены навигация, клавиатурный поиск, мобильное меню и читаемость интерфейса.
- В таблицах доступны наборы метрик, сортировка и сравнение двух моделей с разностями значений.
- Лаборатория порогов использует точный сохранённый порог BRFSS как эталон; сравнивает пропуски, ложные срабатывания и метрики на одной валидационной выборке.
- В 3D добавлены интерактивный продольный профиль, подсветка выбранного слоя и ракурс сверху. На паузе сцена перерисовывается по изменениям.
- Модели, вероятности и исследовательские результаты не переобучались. Основной текст диплома в этом выпуске не редактируется.

### Возможности более ранних выпусков

- В 3D-артерии можно перемещать сечение вдоль сосуда, сравнивать его с исходным и видеть локальные диаметр, площадь и потерю площади. Геометрия не связана с оценкой ML.
- В разделе диплома есть рабочая структура трёх глав: задачи, готовые материалы и оставшаяся работа над рукописью.
- Пользовательская статья Atherosclerosis о сосудистых факторах и деменции добавлена в библиотеку. Через PubMed проверена аннотация; полный текст не прочитан. Это теоретический контекст, а не данные для обучения.

- Новый раздел «Диагностика модели»: 19 метрик, разбор ошибок, сравнение с простыми ориентирами, калибровка с числом наблюдений и условными интервалами Wilson, распределение вероятностей и CSV/JSON.
- Дополнительный ретроспективный опыт: фиксированная UCI Random Forest проверена отдельно на Hungary (294), Switzerland (123) и VA (200). Учтены пропуски, нули и различия состава выборок. Это исследовательская оценка переноса, не клиническая валидация.
- Модели и пороги сохранены. Основные метрики сверены с исходными отчётами. UCI OOF, среднее внешней CV и результаты других центров обозначены отдельно.
- Интерфейс RU/KZ, 3D-артерия, сценарии и раздел готовности диплома сохранены. Новые агрегированные API работают и в локальном Python-приложении.
- Исходные модели и прежние исследовательские отчёты сохранены; добавлены reports/evaluation.json и reports/transfer.json. Воспроизведение описано в deployment/cardio-site/docs/EVALUATION.md.
- Прежние PDF и HTML в output сохранены как черновики. Текст диплома и описание новых опытов требуют авторской актуализации; обновление приложения не подтверждает готовность рукописи к сдаче.

'''
    root = ROOT_PREFIX
    additions = [f'cardio/{name}.py' for name in OVERLAY_MODULES]
    additions += [f'reports/{name}.json' for name in OVERLAY_REPORTS]
    additions += [f'data/processed/{name}' for name in RESEARCH_FILES]
    additions += ['REPRODUCE.cmd']
    with zipfile.ZipFile(original) as source:
        collisions = set(root + name for name in additions) & set(source.namelist())
        if collisions:
            raise ValueError(f'Original archive already contains overlay paths: {sorted(collisions)}')
    if not (site / 'client/dist/index.html').is_file():
        raise FileNotFoundError('Build the current frontend before packaging')
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for entry in source.infolist():
            if entry.filename.startswith((root+'frontend/', root+'deployment/cardio-site/')):
                continue
            payload = source.read(entry)
            if entry.filename == root+'README.md':
                lines = payload.decode('utf-8-sig').splitlines(keepends=True)
                if not lines or lines[0].strip() != '# CardioResearch':
                    raise ValueError('Unexpected README header')
                payload = ('# CardioResearch\n\n'+release+''.join(lines[1:])).encode('utf-8')
            elif entry.filename == root+'cardio/api.py':
                payload = patch_api(payload.decode('utf-8-sig'), version).encode('utf-8')
            elif entry.filename == root+'setup.ps1':
                payload = (site / 'python/setup.ps1').read_bytes()
            output.writestr(entry.filename, payload)
        for name in OVERLAY_MODULES:
            output.write(site/f'python/cardio/{name}.py', root+f'cardio/{name}.py')
        for name in OVERLAY_REPORTS:
            output.write(site/f'data/{name}.json', root+f'reports/{name}.json')
        for name in RESEARCH_FILES:
            output.write(research_folder/name, root+f'data/processed/{name}')
        output.writestr(root+'REPRODUCE.cmd', REPRODUCE_CMD.encode('ascii'))
        for name in filter(None, tracked):
            output.write(site/name, root+'deployment/cardio-site/'+name)
            if name.startswith('client/'):
                output.write(site/name, root+'frontend/'+name[len('client/'):])
        for path in (site/'client/dist').rglob('*'):
            if path.is_file():
                output.write(path, root+'frontend/dist/'+path.relative_to(site/'client/dist').as_posix())
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(destination) as result:
        assert result.testzip() is None
        assert len(result.namelist()) == len(set(result.namelist()))
        preserved = 0
        for name in source.namelist():
            if name.startswith((root+'models/', root+'reports/', root+'output/')):
                assert hashlib.sha256(source.read(name)).digest() == hashlib.sha256(result.read(name)).digest(), name
                preserved += 1
        for name in additions + ['frontend/src/EvaluationLab.tsx', 'frontend/src/ExperimentsHub.tsx',
                                  'frontend/dist/index.html', 'deployment/cardio-site/scripts/verify-research.py',
                                  'deployment/cardio-site/docs/DATA_REPRODUCTION.md']:
            assert root+name in result.namelist(), name
        assert 'register_evaluation_routes(app, REPORTS)' in result.read(root+'cardio/api.py').decode()
        assert 'register_experiment_lab_routes(app, ROOT)' in result.read(root+'cardio/api.py').decode()
        assert result.read(root+'setup.ps1') == (site / 'python/setup.ps1').read_bytes()
        assert "return with_literature_additions(result, optional_report('literature-additions.json') or {})" in result.read(root+'cardio/api.py').decode()
        for dataset in ('uci', 'brfss'):
            assert hashlib.sha256(result.read(root+f'data/processed/{dataset}.pkl')).hexdigest() == recovery['datasets'][dataset]['processed_sha256']
        assert not any(name.endswith(('.pkl', '.joblib')) for name in result.namelist()
                       if name.startswith((root+'deployment/cardio-site/', root+'frontend/')))
    print(json.dumps({'archive':str(destination), 'version':version, 'bytes':destination.stat().st_size,
                      'entries':len(result.namelist()), 'preserved_original_models_reports_drafts':preserved}, ensure_ascii=False))


if __name__ == '__main__':
    main()
