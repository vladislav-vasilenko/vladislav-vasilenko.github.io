import json
import tempfile
import unittest
from pathlib import Path
from src.workspace_projects import read


class WorkspaceProjectsTests(unittest.TestCase):
    def test_safe_navigation_metadata_and_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'projects.json'
            self.assertEqual(read(path), {'portfolio': None, 'career': None})
            data = {'projects': {
                'portfolio': {'label': 'Portfolio', 'public_url': 'https://example.org/', 'private': 'hidden'},
                'career': {'label': 'Career', 'local_url': 'http://127.0.0.1:8788/', 'root': '/private'},
            }}
            path.write_text(json.dumps(data))
            self.assertEqual(read(path), {
                'portfolio': {'label': 'Portfolio', 'url': 'https://example.org/'},
                'career': {'label': 'Career', 'url': 'http://127.0.0.1:8788/'},
            })
            for url in ('https:///missing-host', 'https://user:pass@example.org/', 'javascript:alert(1)'):
                data['projects']['portfolio']['public_url'] = url
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    read(path)
