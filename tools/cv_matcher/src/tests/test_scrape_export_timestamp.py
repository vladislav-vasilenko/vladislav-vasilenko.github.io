from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import scrape_online
from src.github_collection_import import normalize, timestamp


class ScrapeExportTimestampTests(unittest.TestCase):
    def test_description_collected_during_run_survives_real_export_import(self):
        now = datetime.now(timezone.utc)
        started = (now - timedelta(minutes=5)).isoformat()
        captured = (now - timedelta(seconds=10)).isoformat()
        row = {'id': 'yandex_46759', 'title': 'ML Engineer', 'company': 'Yandex',
               'link': 'https://yandex.ru/jobs/vacancies/ml-engineer-46759',
               'description': 'Требования: Python. Задачи: обучение и оценка моделей. ' * 5,
               'description_quality': 'full', 'collected_at': captured, 'first_seen': started}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'online_scraped.json'
            with patch.object(scrape_online, 'OUTPUT', output):
                scrape_online._save({row['id']: row}, {'yandex': {'new': 1, 'errors': 0}}, started)
            payload = json.loads(output.read_text())
        self.assertEqual(payload['collection_started_at'], started)
        imported = normalize(payload['vacancies'][0], timestamp(payload['last_updated']))
        self.assertEqual(imported['description_quality'], 'full')
        self.assertEqual(imported['collected_at'], timestamp(captured))
