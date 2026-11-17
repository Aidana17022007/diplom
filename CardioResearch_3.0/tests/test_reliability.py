import numpy as np
import pytest
from cardio.reliability import exact_recall_interval, fixed_prediction_bootstrap

def test_zero_success_does_not_imply_zero_uncertainty():
    lo,hi=exact_recall_interval(0,41)
    assert lo==0 and .08<hi<.09
    assert exact_recall_interval(0,0) is None
    assert exact_recall_interval(41,41)[1]==1
    with pytest.raises(ValueError):exact_recall_interval(4,3)

def test_bootstrap_preserves_model_pairing_and_reproducibility():
    y=np.tile([0,1],20);p=np.linspace(.01,.99,len(y))
    ci,draws=fixed_prediction_bootstrap(y,{'a':p,'same':p},repeats=40,seed=7)
    ci2,draws2=fixed_prediction_bootstrap(y,{'a':p},repeats=40,seed=7)
    assert np.array_equal(draws['a'],draws['same'])
    assert np.array_equal(draws['a'],draws2['a'])
    assert ci['a']==ci2['a']
    for bounds in ci['a'].values():assert 0<=bounds[0]<=bounds[1]<=1
    with pytest.raises(ValueError):fixed_prediction_bootstrap(y,{'bad':p[:-1]},40)
