import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.github_collection_export import prepare


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'source.json'
        self.target = Path(self.tmp.name) / 'artifact'
        self.payload = {'collection_run': {'id': '100', 'attempt': '2', 'sha': 'a' * 40},
                        'last_updated': '2026-10-22T10:00:00Z', 'total': 1,
                        'vacancies': [{'id': '123', 'description': 'Public vacancy'}],
                        'stats_last_run': {'yandex': {'new': 1, 'errors': 0},
                                           'meta': {'new': 0, 'errors': 1}}}

    def export(self, payload):
        self.source.write_text(json.dumps(payload), encoding='utf-8')
        return prepare(self.source, self.target, run_id='100', attempt='2', sha='a' * 40)

    def test_partial_results_are_preserved_and_reported_without_vacancy_text(self):
        summary = self.export(self.payload)
        self.assertIn('| meta | 0 | 1 |', summary)
        self.assertIn('Partial source failures', summary)
        self.assertNotIn('Public vacancy', summary)
        self.assertEqual(json.loads((self.target / 'online_scraped.json').read_text()), self.payload)

    def test_previous_run_attempt_or_commit_cannot_be_advertised_as_fresh(self):
        for key, value in [('id', '99'), ('attempt', '1'), ('sha', 'b' * 40)]:
            with self.subTest(key=key):
                stale = copy.deepcopy(self.payload)
                stale['collection_run'][key] = value
                with self.assertRaises(ValueError):
                    self.export(stale)
                self.assertFalse(self.target.exists())

    def test_missing_identity_and_malformed_export_are_rejected(self):
        for changes in ({'collection_run': {}}, {'total': 2}, {'vacancies': [None]},
                        {'stats_last_run': {}}, {'last_updated': '2026-10-22'},
                        {'stats_last_run': {'meta': {'errors': 'bad'}}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.export({**self.payload, **changes})
        self.assertFalse(self.target.exists())
        with self.assertRaises(ValueError):
            prepare(self.source, self.target, run_id=None, attempt='2', sha='a' * 40)

    def test_valid_empty_collection_is_reported_honestly(self):
        summary = self.export({**self.payload, 'vacancies': [], 'total': 0})
        self.assertIn('Exported 0 saved vacancies', summary)
