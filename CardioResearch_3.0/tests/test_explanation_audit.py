import numpy as np
import pytest
from cardio.explain import permutation_shap
from cardio.explanation_audit import coalition_values, exact_from_values, sampled_from_values


def test_exact_cubic_interaction_and_unused_feature():
    # The unanimity game allocates a three-way interaction equally.
    bg = np.zeros((2, 4)); x = np.ones(4)
    values = coalition_values(lambda a: a[:, 0]*a[:, 1]*a[:, 2], bg, x, 3)
    actual = exact_from_values(values)
    assert np.allclose(actual, [1/3, 1/3, 1/3, 0])
    assert np.isclose(actual.sum(), values[-1]-values[0])


def test_cached_sampling_matches_production_with_missing_values():
    bg = np.array([[0., 1., np.nan], [2., 0., 3.]])
    x = np.array([1., np.nan, 2.])
    def predict(a):
        b = np.nan_to_num(a, nan=-1)
        return 1/(1+np.exp(-(b[:, 0]*b[:, 1]*b[:, 2] + b[:, 2])))
    values = coalition_values(predict, bg, x, 2)
    for budget in (12, 48, 192):
        direct, baseline = permutation_shap(predict, bg, x, budget, 19)
        assert np.allclose(sampled_from_values(values, budget, 19), direct, atol=1e-12)
        assert np.isclose(values[0], baseline)


def test_boundary_and_nonfinite_scores_are_rejected():
    with pytest.raises(ValueError):
        coalition_values(lambda a: np.zeros(len(a)), np.zeros((2, 16)), np.zeros(16))
    with pytest.raises(ValueError):
        coalition_values(lambda a: np.full(len(a), np.nan), np.zeros((2, 3)), np.zeros(3))
    with pytest.raises(ValueError):
        sampled_from_values(np.zeros(8), 3)
