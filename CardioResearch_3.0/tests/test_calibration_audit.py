import numpy as np
import pytest
from cardio.calibration_audit import calibration_diagnostics, prior_scenario


def test_exactly_calibrated_grouped_probabilities():
    p = np.repeat([.2, .5, .8], 10)
    y = np.r_[np.ones(2),np.zeros(8),np.ones(5),np.zeros(5),np.ones(8),np.zeros(2)]
    r = calibration_diagnostics(y, p)
    assert abs(r['intercept_slope_fixed_1']) < 1e-7
    assert abs(r['slope']-1) < 1e-7
    assert abs(r['mean_error_pp']) < 1e-10


def test_prior_shift_preserves_roc_and_obeys_precision_identity():
    y = np.array([1,1,1,1,0,0,0,0]); p = np.array([.9,.8,.6,.2,.7,.3,.1,.05])
    low, high = [prior_scenario(y, p, prior, .5) for prior in (.05, .3)]
    assert np.isclose(low['roc_auc'], high['roc_auc'])
    assert low['average_precision'] < high['average_precision']
    assert np.isclose(low['precision_fixed_threshold'], .75*.05/(.75*.05+.25*.95))


def test_calibration_degenerate_and_invalid_input():
    r=calibration_diagnostics([0,1,0,1], [.5]*4)
    assert r['slope'] is None
    with pytest.raises(ValueError): calibration_diagnostics([0,0], [.2,.3])
    with pytest.raises(ValueError): calibration_diagnostics([0,1], [.2,1.3])
