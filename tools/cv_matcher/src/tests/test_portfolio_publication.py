import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.archive_store import ArchiveStore, digest
from src import portfolio_publication as publication
from src.career_trajectory import save_evidence
from src.tests.test_archive import cv, record

EXPERIENCE = '''Опыт работы
Example Company
2
года
ML Engineer
Январь
2023
—
Февраль
2025
(
2
года
)
Реализовал эксперимент PyTorch и описал метрики. Email: person@example.org
'''


class Publisher:
    def __init__(self): self.calls = []
    def public_repository(self, owner, repo): return repo != 'private'
    def publish(self, payload): self.calls.append(json.loads(json.dumps(payload))); return 'a' * 40


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.archive = ArchiveStore(Path(self.tmp.name) / 'archive.sqlite3')
        self.resume = cv()
        self.resume['sections'] = [{'key': 'experience', 'heading': 'Опыт работы', 'text': EXPERIENCE}, {'key': 'contacts', 'text': 'SECRET'}]
        self.archive.sync({'client_id': 'publication-test', 'records': [record('resume', self.resume),
                          {'kind': 'profile', 'id': 'profile', 'data': {'primary_id': self.resume['id'], 'goal': 'private goal'}, 'digest': digest({'primary_id': self.resume['id'], 'goal': 'private goal'})}]})

    def test_reuses_hh_parser_and_exports_only_work_history(self):
        result = publication.preview(self.archive)
        self.assertEqual(len(result['payload']['experience']), 1)
        self.assertEqual(result['payload']['experience'][0]['company'], 'Example Company')
        self.assertNotIn('person@example.org', json.dumps(result['payload']))
        self.assertNotIn('SECRET', json.dumps(result['payload']))
        self.assertNotIn('private goal', json.dumps(result['payload']))
        self.assertNotIn('resume_id', result['payload']['source'])
        self.assertEqual(result['payload']['confirmed_skills'], [])

    def evidence(self, kind, url, state='confirmed'):
        return save_evidence(self.archive, {'kind': kind, 'skill_ids': ['pytorch'],
           'note': 'Реализован воспроизводимый проект с кодом, метриками и анализом результатов.',
           'url': url, 'state': state, 'reviewed': True})

    def test_only_confirmed_practice_and_public_repos_are_published(self):
        self.evidence('project', 'https://github.com/example/public')
        self.evidence('research', 'https://github.com/example/private')
        self.evidence('learning', 'https://github.com/example/course', 'completed')
        fake = Publisher(); result = publication.publish(self.archive, fake)
        self.assertEqual(result['phase'], 'published')
        skills = fake.calls[0]['confirmed_skills']; self.assertEqual(len(skills), 1)
        self.assertEqual([l['url'] for l in skills[0]['links']], ['https://github.com/example/public'])
        self.assertNotIn('note', json.dumps(skills))
        self.assertEqual(publication.publish(self.archive, fake)['phase'], 'up_to_date')
        self.assertEqual(len(fake.calls), 1)

    def test_bad_parser_and_retracted_evidence_are_not_published_as_facts(self):
        with self.assertRaises(ValueError): publication.parse_experience('Unknown format without dates')
        evidence = self.evidence('project', 'https://github.com/example/public')
        save_evidence(self.archive, {**evidence, 'state': 'retracted', 'reviewed': True})
        self.assertEqual(publication.confirmed_skills(self.archive), [])
        for url in ('https://github.com/a/private?token=secret', 'https://evil.org/github.com/a/b', 'https://github.com@evil.org/a/b'):
            self.assertIsNone(publication.github_url(url))

    def test_recapture_without_changed_content_does_not_republish(self):
        fake = Publisher(); publication.publish(self.archive, fake)
        updated = {**self.resume, 'checked_at': '2026-10-21T12:00:00Z'}
        self.archive.sync({'client_id': 'publication-test', 'records': [record('resume', updated)]})
        self.assertEqual(publication.publish(self.archive, fake)['phase'], 'up_to_date')
        self.assertEqual(len(fake.calls), 1)

    def test_about_draft_is_reviewed_bound_to_source_and_never_silently_sent_to_hh(self):
        self.resume['sections'].append({'key': 'about', 'text': 'О себе: Исследую модели и проверяю результаты на PyTorch.'})
        self.archive.sync({'client_id': 'publication-test', 'records': [record('resume', self.resume)]})
        proposal = publication.preview(self.archive)
        self.assertNotIn('О себе:', proposal['payload']['about']['text'])
        with self.assertRaises(ValueError): publication.save_about(self.archive, {'text':'x' * 50,'language':'ru','basis':proposal['about_basis']})
        publication.save_about(self.archive, {'text':'Исследую генеративные модели с воспроизводимыми экспериментами.', 'language':'ru', 'basis':proposal['about_basis'], 'reviewed': True})
        self.assertEqual(publication.preview(self.archive)['payload']['about']['origin'], 'reviewed')
        publication.save_about(self.archive, {'text':'I research generative models through reproducible experiments.', 'language':'en', 'basis':proposal['about_basis'], 'reviewed':True})
        versions=publication.preview(self.archive)['payload']['about']
        self.assertTrue(versions['text'].startswith('Исследую'))
        self.assertTrue(versions['translations']['en'].startswith('I research'))
        changed={**self.resume, 'sections':self.resume['sections'][:-1]+[{'key':'about','text':'Новый исходный текст HH о текущих исследованиях.'}]}
        self.archive.sync({'client_id':'publication-test','records':[record('resume',changed)]})
        value=publication.preview(self.archive)
        self.assertTrue(value['about_needs_review']);self.assertEqual(value['payload']['about']['origin'],'hh')
        self.assertIn('Новый исходный текст',value['payload']['about']['text'])
        with self.assertRaises(ValueError): publication.save_about(self.archive, {'text':'person@example.org '+ 'x'*40,'language':'ru','basis':value['about_basis'],'reviewed':True})

    def test_routes_protect_publication_and_scheduler_defaults_off(self):
        app = create_app('fixture', archive_path=self.archive.path)
        with TestClient(app) as client:
            self.assertEqual(client.get('/archive/portfolio-publication').status_code, 401)
            client.post('/archive/login', json={}, headers={'X-Resume-Import-Token': 'fixture'})
            self.assertFalse(client.get('/archive/portfolio-publication').json()['enabled'])
            self.assertEqual(client.post('/archive/portfolio-publication', json={'op': 'publish'}, headers={'Origin': 'https://evil.org'}).status_code, 401)
            response = client.post('/archive/portfolio-publication', json={'op': 'preview'}, headers={'Origin': 'http://127.0.0.1:8788'})
            self.assertEqual(response.status_code, 200)
