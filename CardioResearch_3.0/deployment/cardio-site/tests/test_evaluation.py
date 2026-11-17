"""Run: python -m unittest discover -s tests -p test_evaluation.py -v"""

import hashlib
import importlib.util
import json
import math
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_evaluation", ROOT / "scripts" / "build-evaluation.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


class MathematicalDiagnosticsTests(unittest.TestCase):
    def test_ties_are_grouped_without_arbitrary_ordering(self):
        y, p = [1, 0, 1, 0], [.9, .9, .1, .1]
        auc, ap = evaluation.rank_metrics(y, p)
        self.assertEqual(auc, .5)
        self.assertEqual(ap, .5)
        self.assertEqual(evaluation.rank_metrics(list(reversed(y)), list(reversed(p))), (auc, ap))

    def test_average_precision_is_not_trapezoidal_pr_area(self):
        # Ordered labels are positive, negative, positive: AP=(1 + 2/3)/2.
        auc, ap = evaluation.rank_metrics([1, 0, 1], [.9, .8, .7])
        self.assertEqual(auc, .5)
        self.assertAlmostEqual(ap, 5 / 6)

    def test_perfect_predictions_and_probability_endpoints(self):
        result = evaluation.evaluate([0, 1], [0., 1.], .5)
        for key in ("roc_auc", "average_precision", "accuracy", "balanced_accuracy", "mcc", "npv"):
            self.assertEqual(result["metrics"][key], 1.)
        self.assertEqual(result["metrics"]["brier"], 0.)
        self.assertEqual(result["metrics"]["ece"], 0.)
        self.assertTrue(math.isfinite(result["metrics"]["log_loss"]))
        self.assertLess(result["metrics"]["log_loss"], 2e-15)

    def test_undefined_denominators_remain_null(self):
        result = evaluation.evaluate([0, 0], [.1, .2], .5)
        for key in ("roc_auc", "average_precision", "recall", "precision", "f1", "mcc", "balanced_accuracy", "brier_skill", "ap_lift"):
            self.assertIsNone(result["metrics"][key], key)
        self.assertIsNone(result["intervals"]["precision"])
        self.assertIsNone(result["intervals"]["recall"])
        self.assertEqual(result["metrics"]["specificity"], 1.)
        self.assertEqual(result["metrics"]["npv"], 1.)
        # A constant positive classifier also has undefined NPV/specificity
        # when only positives are present, without inventing a zero score.
        positive = evaluation.evaluate([1, 1], [.9, .8], .5)
        self.assertIsNone(positive["metrics"]["npv"])
        self.assertIsNone(positive["metrics"]["specificity"])
        self.assertEqual(positive["metrics"]["average_precision"], 1.)

    def test_fixed_width_bins_preserve_samples_and_empty_bins(self):
        result = evaluation.evaluate([0, 1, 0, 1], [0., .1, .95, 1.], .5)
        bins = result["calibration"]
        self.assertEqual(len(bins), 10)
        self.assertEqual(sum(b["n"] for b in bins), 4)
        self.assertEqual(bins[0]["n"], 1)
        self.assertEqual(bins[1]["n"], 1)
        self.assertEqual(bins[9]["n"], 2)
        self.assertEqual(bins[9]["observed_rate"], .5)
        for field in ("mean_probability", "observed_rate", "ci"):
            self.assertIsNone(bins[2][field])
        self.assertEqual(sum(b["positive"] for b in result["distribution"]), 2)
        self.assertEqual(sum(b["negative"] for b in result["distribution"]), 2)
        self.assertEqual(sum(map(sum, result["confusion"])), 4)

    def test_threshold_equality_is_positive(self):
        result = evaluation.evaluate([0, 1], [.5, .5], .5)
        self.assertEqual(result["confusion"], [[0, 1], [0, 1]])

    def test_wilson_interval_does_not_collapse_at_zero_recall(self):
        low, high = evaluation.wilson_interval(0, 10)
        self.assertAlmostEqual(low, 0, places=14)
        self.assertAlmostEqual(high, .2775327998628892)
        one_low, one_high = evaluation.wilson_interval(10, 10)
        self.assertAlmostEqual(one_low, 1 - high)
        self.assertAlmostEqual(one_high, 1.)
        self.assertIsNone(evaluation.wilson_interval(0, 0))

    def test_bad_predictions_fail_before_export(self):
        for y, p, threshold in (([], [], .5), ([0], [.1, .2], .5), ([2], [.5], .5),
                                ([0], [math.nan], .5), ([1], [1.1], .5), ([0], [.1], -1)):
            with self.subTest(y=y, p=p, threshold=threshold), self.assertRaises(ValueError):
                evaluation.evaluate(y, p, threshold)
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluation.parse_predictions(b"row_id,target,p\na,0,0.1\na,1,0.8\n", "p")


class FrozenArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = ROOT.parents[1] / "CardioResearch_project.zip"
        if not cls.archive.exists():
            raise unittest.SkipTest("Frozen integration inputs absent; provide CardioResearch_project.zip two directories above the site checkout")
        cls.saved = json.loads((ROOT / "data" / "evaluation.json").read_text(encoding="utf-8"))
        cls.actual = evaluation.build_evaluation(cls.archive, ROOT / "data" / "reports.json", created=cls.saved["created"])

    def test_committed_payload_is_exactly_reproducible(self):
        self.assertEqual(self.actual, self.saved)
        json.dumps(self.actual, allow_nan=False)

    def test_selected_brfss_fixed_test_reconciliation(self):
        report = self.actual["datasets"]["brfss"]
        self.assertEqual(report["evaluation"], "locked_independent_test")
        self.assertEqual(report["model"], "Logistic Regression")
        self.assertEqual(report["n"], 85748)
        self.assertEqual(report["positive"], 7262)
        self.assertEqual(report["confusion"], [[70294, 8192], [3578, 3684]])
        self.assertAlmostEqual(report["metrics"]["roc_auc"], .8388685147257342, places=12)
        self.assertAlmostEqual(report["metrics"]["average_precision"], .32087306860285136, places=12)
        self.assertAlmostEqual(report["metrics"]["balanced_accuracy"], .7014614811695249, places=12)
        self.assertLessEqual(report["provenance"]["reconciliation"]["max_absolute_metric_delta"], 1e-10)
        self.assertEqual(report["validation"]["n"], 51449)

    def test_uci_uses_patient_oof_not_mean_fold_scores(self):
        report = self.actual["datasets"]["uci"]
        self.assertEqual(report["evaluation"], "averaged_patient_oof")
        self.assertEqual(report["n"], 303)
        self.assertEqual(report["confusion"], [[141, 23], [29, 110]])
        self.assertAlmostEqual(report["metrics"]["roc_auc"], .909062993507633, places=12)
        self.assertAlmostEqual(report["metrics"]["average_precision"], .9031627612571037, places=12)
        self.assertNotAlmostEqual(report["metrics"]["average_precision"], .9066114232, places=5)
        self.assertNotIn("validation", report)

    def test_hashes_bind_original_files_and_exact_prediction_members(self):
        source = self.actual["sources"]
        self.assertEqual(source["archive_sha256"], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual(source["reports_sha256"], hashlib.sha256((ROOT / "data" / "reports.json").read_bytes()).hexdigest())
        with ZipFile(self.archive) as archive:
            for report in self.actual["datasets"].values():
                provenance = report["provenance"]
                payload = archive.read(provenance["prediction_member"])
                expected_hash = hashlib.sha256(payload).hexdigest()
                self.assertEqual(provenance["prediction_sha256"], expected_hash)
                self.assertEqual(source["prediction_sha256"][provenance["prediction_member"]], expected_hash)

    def test_all_aggregate_counts_cover_the_complete_evaluation_sample(self):
        for report in self.actual["datasets"].values():
            self.assertEqual(sum(b["n"] for b in report["calibration"]), report["n"])
            self.assertEqual(sum(b["positive"] for b in report["distribution"]), report["positive"])
            self.assertEqual(sum(b["negative"] for b in report["distribution"]), report["negative"])
            self.assertEqual(sum(map(sum, report["confusion"])), report["n"])
            self.assertFalse(report["provenance"]["retrained"])
            self.assertFalse(report["provenance"]["selection_changed"])
            self.assertFalse(report["provenance"]["row_identifiers_exported"])

    def test_reconciliation_refuses_changed_scores(self):
        report = self.actual["datasets"]["brfss"]
        wrong_reference = {**report["reference_metrics"], "average_precision": .99}
        with self.assertRaisesRegex(ValueError, "average_precision"):
            evaluation.reconcile(report, wrong_reference)


if __name__ == "__main__":
    unittest.main()
