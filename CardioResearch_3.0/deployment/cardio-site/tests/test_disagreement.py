import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('disagreement', Path(__file__).resolve().parents[1]/'scripts/build-disagreement.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AgreementTests(unittest.TestCase):
    def setUp(self):
        self.names = ['Dummy', 'A', 'B', 'C']
        self.rows = [dict(zip(['row_id','target']+self.names, values)) for values in [
            ['a','1','.1','.9','.7','.5'], ['b','0','.1','.6','.1','.3'],
            ['c','1','.1','.1','.1','.1'], ['d','0','.1','.1','.6','.1']]]

    def test_joint_errors_and_disagreements_are_distinct(self):
        r = module.build_report(self.rows, self.names)
        self.assertEqual(r['summary'], {'disagreement_n':2,'unanimous_wrong_n':1,'split_vote_n':2,'unanimous_correct_n':1})
        self.assertEqual(r['pairs'][1][2], {'both_correct':1,'both_wrong':1,'only_a_correct':1,'only_b_correct':1,'disagree':2})
        self.assertEqual(r['models'][3]['tp'], 1)  # .5 belongs to class 1
        self.assertEqual(sum(p['n'] for p in r['patterns']), r['n'])
        self.assertNotIn('row_id', str(r))

    def test_diagonal_symmetry_and_count_conservation(self):
        r = module.build_report(self.rows, self.names)
        for a, row in enumerate(r['pairs']):
            self.assertEqual(row[a]['disagree'], 0)
            for b, p in enumerate(row):
                self.assertEqual(sum(p[k] for k in ['both_correct','both_wrong','only_a_correct','only_b_correct']), 4)
                self.assertEqual(p['disagree'], r['pairs'][b][a]['disagree'])
                self.assertEqual(p['only_a_correct'], r['pairs'][b][a]['only_b_correct'])

    def test_invalid_inputs_fail_instead_of_becoming_predictions(self):
        for value in ['nan','inf','-0.01','1.01']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.build_report([{**self.rows[0], 'A':value}], self.names)
        with self.assertRaises(ValueError): module.build_report([self.rows[0]]*2, self.names)
        with self.assertRaises(ValueError): module.build_report([{**self.rows[0], 'target':'2'}], self.names)


if __name__ == '__main__': unittest.main()
