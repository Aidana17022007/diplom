import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('development_study', ROOT / 'scripts/development_study.py')
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_training_sample_cannot_include_original_holdouts():
    frame = pd.DataFrame({'row_id': np.arange(30), 'target': [0, 1] * 15})
    splits = {'fit': list(range(24)), 'calibration': [24, 25], 'validation': [26, 27], 'test': [28, 29]}
    sample = study.select_training_sample(frame, splits, n=12, seed=21)
    assert len(sample) == 12 and sample.target.sum() == 6
    assert set(sample.row_id).issubset(set(splits['fit']))
    assert sample.row_id.tolist() == study.select_training_sample(frame, splits, n=12, seed=21).row_id.tolist()
    with pytest.raises(ValueError, match='overlaps'):
        study.select_training_sample(frame, {**splits, 'test': [0, 29]}, n=12)
    with pytest.raises(ValueError, match='Duplicate source'):
        study.select_training_sample(pd.concat([frame, frame.iloc[[0]]]), splits, n=12)


def test_diagnostic_metrics_use_fixed_half_threshold_and_keep_undefined_precision():
    result = study.scores([0, 1, 0, 1], [.1, .8, .6, .4])
    assert result['recall'] == result['precision'] == result['f1'] == result['balanced_accuracy'] == .5
    assert result['brier'] == pytest.approx((.01 + .04 + .36 + .36) / 4)
    assert result['roc_auc'] == .75
    assert result['average_precision'] == pytest.approx((1 + 2 / 3) / 2)
    absent = study.scores([0, 1], [.1, .2])
    assert absent['precision'] is None and absent['recall'] == 0
    with pytest.raises(ValueError):
        study.scores([0, 1], [float('nan'), .2])


def test_summary_does_not_drop_undefined_folds_or_mislabel_sd_as_ci():
    folds = [{'metrics': {key: value for key in study.METRICS}} for value in [0., .5, 1.]]
    means, deviations = study.summarize(folds)
    assert means['average_precision'] == .5
    assert deviations['average_precision'] == .5
    folds[1]['metrics']['precision'] = None
    means, deviations = study.summarize(folds)
    assert means['precision'] is None and deviations['precision'] is None
