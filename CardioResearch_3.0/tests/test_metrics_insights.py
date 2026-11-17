"""Tests for aggregate diagnostics, tie handling, and frozen cohort validation."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import average_precision_score, balanced_accuracy_score, matthews_corrcoef

from scripts.build_metrics_insights import (
    frozen_comparison, matched_features, missingness_metrics, ranking_metrics, subgroup_metrics,
)


def test_gain_and_lift_use_whole_ties_and_actual_random_coverage():
    # The requested top 25% intersects a two-observation tie: both must enter.
    result = ranking_metrics([1, 0, 1, 0], [.8, .8, .3, .1], [.25, 1])
    top, full = result
    assert top == {"requested_fraction": .25, "actual_fraction": .5, "cutoff": .8,
                   "selected_n": 2, "positive_n": 1, "precision": .5, "recall": .5,
                   "lift": 1., "random_recall": .5, "random_precision": .5}
    assert full["selected_n"] == 4
    assert full["recall"] == full["lift"] == full["random_recall"] == 1


def test_ranking_is_invariant_to_permutation_and_all_equal_scores():
    y, p = np.array([0, 1, 1, 0, 1]), np.array([.2, .8, .8, .8, .1])
    permutation = [3, 1, 0, 4, 2]
    assert ranking_metrics(y, p) == ranking_metrics(y[permutation], p[permutation])
    equal = ranking_metrics(y, np.repeat(.5, 5))
    assert all(row["selected_n"] == 5 and row["lift"] == 1 for row in equal)


def test_ranking_zero_positives_and_rounding_do_not_invent_metrics():
    zero = ranking_metrics([0, 0, 0], [.7, .5, .1], [.5])[0]
    assert zero["selected_n"] == 2
    assert zero["actual_fraction"] == 2 / 3
    assert zero["precision"] == zero["random_precision"] == 0
    assert zero["recall"] is zero["lift"] is zero["random_recall"] is None


@pytest.mark.parametrize("target,probability,fractions", [
    ([], [], [.1]), ([0, 1], [.5], [.1]), ([0, 2], [.1, .9], [.1]),
    ([0, 1], [np.nan, .2], [.1]), ([0, 1], [.2, 1.1], [.1]),
    ([0, 1], [.2, .7], [0]), ([0, 1], [.2, .7], [1.01]),
    ([0, 1], [.2, .7], [np.nan]), ([[0, 1]], [[.2, .7]], [.1]),
])
def test_invalid_ranking_inputs_fail(target, probability, fractions):
    with pytest.raises(ValueError):
        ranking_metrics(target, probability, fractions)


def test_subgroup_metrics_match_reference_sklearn_without_trapezoidal_ap():
    y = np.array([1, 0, 1, 0, 0, 1])
    p = np.array([.8, .7, .6, .4, .1, .2])
    result = subgroup_metrics(y, p, .6)
    assert result["average_precision"] == pytest.approx(average_precision_score(y, p))
    assert result["balanced_accuracy"] == pytest.approx(balanced_accuracy_score(y, p >= .6))
    assert result["mcc"] == pytest.approx(matthews_corrcoef(y, p >= .6))
    assert result["precision"] == result["recall"] == 2 / 3
    assert result["specificity"] == 2 / 3


def test_empty_and_single_class_groups_have_explicit_nulls():
    empty = subgroup_metrics([], [], .5)
    assert all(value is None for value in empty.values())
    negative = subgroup_metrics([0, 0], [.1, .2], .5)
    assert negative["roc_auc"] is negative["average_precision"] is None
    assert negative["recall"] is negative["precision"] is negative["mcc"] is None
    assert negative["specificity"] == 1
    assert negative["brier"] == pytest.approx(.025)
    positive = subgroup_metrics([1, 1], [.1, .2], .5)
    assert positive["specificity"] is positive["balanced_accuracy"] is None
    assert positive["recall"] == positive["f1"] == 0
    json.dumps({"empty": empty, "negative": negative, "positive": positive}, allow_nan=False)


def test_missingness_partition_counts_nan_but_preserves_zero():
    features = pd.DataFrame([[0, 0, 1, 2], [np.nan, 1, 2, 3],
                             [np.nan, np.nan, 1, 2], [np.nan] * 4])
    result = missingness_metrics([0, 1, 0, 1], [.1, .8, .3, .6], features, .5)
    assert result["feature_count"] == 4
    assert [group["n"] for group in result["groups"]] == [1, 1, 1, 1]
    assert [group["positive"] for group in result["groups"]] == [0, 1, 0, 1]
    assert sum(group["n"] for group in result["groups"]) == result["cohort_n"]


def test_source_join_preserves_prediction_order_and_checks_targets_and_split():
    predictions = pd.DataFrame({"row_id": ["2", "1"], "target": [1, 0]})
    source = pd.DataFrame({"row_id": [1, 2], "target": [0, 1],
                           "split": ["test", "test"], "x": [0, np.nan]})
    matched = matched_features(predictions, source, ["x"], [1, 2], "test")
    assert pd.isna(matched.iloc[0].x) and matched.iloc[1].x == 0
    wrong_target = predictions.copy()
    wrong_target.loc[0, "target"] = 0
    with pytest.raises(ValueError, match="targets"):
        matched_features(wrong_target, source, ["x"])
    source.loc[0, "split"] = "fit"
    with pytest.raises(ValueError, match="required split"):
        matched_features(predictions, source, ["x"], required_split="test")


@pytest.mark.parametrize("failure", ["duplicate_prediction", "duplicate_source", "unknown", "missing_cohort", "null_id"])
def test_source_join_rejects_ambiguous_or_incomplete_cohorts(failure):
    predictions = pd.DataFrame({"row_id": ["1", "2"], "target": [0, 1]})
    source = pd.DataFrame({"row_id": [1, 2], "target": [0, 1], "x": [1, 2]})
    expected = [1, 2]
    if failure == "duplicate_prediction":
        predictions.loc[1, "row_id"] = "1"
    elif failure == "duplicate_source":
        source.loc[1, "row_id"] = 1
    elif failure == "unknown":
        predictions.loc[1, "row_id"] = "3"
        expected = None
    elif failure == "missing_cohort":
        expected = [1, 2, 3]
    else:
        predictions.loc[0, "row_id"] = None
    with pytest.raises(ValueError):
        matched_features(predictions, source, ["x"], expected)


def test_comparison_preserves_validation_selection_even_when_test_ranking_reverses():
    def candidate(name, validation_ap, test_ap):
        return {"name": name, "threshold": .2, "calibrated": False, "test_n": 4,
                "validation": {"average_precision": validation_ap, "confusion": [[1, 1], [1, 1]]},
                "metrics": {"average_precision": test_ap, "confusion": [[1, 1], [1, 1]]}}
    selection = {"deployed_model": "Logistic Regression", "locked_before_test": True, "locked_at": "frozen"}
    brfss = {"selection": selection, "full": [candidate("Logistic Regression", .4, .3),
                                               candidate("LightGBM", .39, .5)]}
    original = copy.deepcopy(brfss)
    result = frozen_comparison(brfss, selection)
    assert result["selected_model"] == "Logistic Regression"
    assert result["test_used_for_selection"] is False
    assert result["rows"][1]["test"]["metrics"]["average_precision"] == .5
    assert brfss == original


def test_published_aggregate_reconciles_cohorts_and_contains_no_individual_predictions():
    root = Path(__file__).resolve().parents[1]
    report_bytes = (root / "reports/metrics-insights.json").read_bytes()
    assert report_bytes == (root / "deployment/cardio-site/data/metrics-insights.json").read_bytes()
    payload = json.loads(report_bytes)
    assert payload["inputs_unchanged"] is True
    for key, expected_n in (("brfss", 85748), ("uci", 303)):
        row = payload["datasets"][key]
        assert row["n"] == expected_n
        assert sum(group["n"] for group in row["missingness"]["groups"]) == expected_n
        assert sum(group["positive"] for group in row["missingness"]["groups"]) == row["positive"]
        assert row["ranking"][-1]["recall"] == row["ranking"][-1]["lift"] == 1
    def assert_aggregate(value):
        if isinstance(value, dict):
            assert not ({"row_id", "probability", "target"} & set(value))
            for child in value.values():
                assert_aggregate(child)
        elif isinstance(value, list):
            for child in value:
                assert_aggregate(child)
    assert_aggregate(payload)
