"""Pure catalog merge checks; no FastAPI, model or patient-row dependencies."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('literature', ROOT / 'python/cardio/literature.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
merge = module.with_literature_additions


class LiteratureMergeTests(unittest.TestCase):
    def test_optional_none_archive_and_lists(self):
        base = dict(atherosclerosis=None, papers=None, books=None, software=None, counts=None)
        result = merge(base, {'records': [{'id': 'P1', 'title': 'Supplementary review'}]})
        self.assertEqual(result['counts'], dict(books=0, papers=1, software=0, atherosclerosis=0))
        self.assertIsNone(result['atherosclerosis'])
        self.assertIsNone(base['papers'])

    def test_copies_nested_records_and_preserves_archive_count(self):
        base = {'papers': [{'id': 'P1', 'title': 'Existing'}],
                'atherosclerosis': {'archive': {'pdf_count': 12}, 'records': [{'id': 'A1'}]}}
        addition = {'records': [{'id': 'P2', 'title': 'Added', 'authors': ['Author']}]}
        result = merge(base, addition)
        result['papers'][0]['title'] = 'Mutated result'
        result['papers'][1]['authors'][0] = 'Changed author'
        self.assertEqual(base['papers'][0]['title'], 'Existing')
        self.assertEqual(addition['records'][0]['authors'], ['Author'])
        self.assertEqual(result['atherosclerosis']['archive']['pdf_count'], 12)
        self.assertEqual(result['counts']['atherosclerosis'], 1)

    def test_deduplicates_doi_across_archive_and_paper_ids(self):
        base = {'papers': [{'id': 'P1', 'title': 'Existing'}],
                'atherosclerosis': {'records': [{'id': 'A1', 'doi': '10.1234/example'}]}}
        addition = {'records': [
            {'id': 'P2', 'title': 'Duplicate DOI', 'doi': ' HTTPS://DOI.ORG/10.1234/EXAMPLE '},
            {'id': 'P1', 'title': 'Duplicate ID'},
            {'id': 'P3', 'title': 'New', 'doi': '10.1234/new'},
            {'id': 'P4', 'title': 'Repeated new DOI', 'doi': 'doi:10.1234/NEW'},
        ]}
        result = merge(base, addition)
        self.assertEqual([paper['id'] for paper in result['papers']], ['P1', 'P3'])
        self.assertEqual(result, merge(result, addition))


if __name__ == '__main__':
    unittest.main()
