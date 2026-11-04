import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.archive_store import ArchiveStore, digest
from src import portfolio_blocks as blocks
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
        self.assertEqual(result['payload']['title'], self.resume['title'])
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

    def test_reviewed_experience_translation_preserves_dates_and_expires_on_source_change(self):
        proposal = publication.preview(self.archive)
        rows = [{**proposal['payload']['experience'][0], 'period': 'January 2023 — February 2025',
                 'duration': '2 years', 'description': 'Implemented a PyTorch experiment and documented metrics.'}]
        data = {'language': 'en', 'basis': proposal['experience_basis'], 'items': rows, 'reviewed': True}
        with self.assertRaises(ValueError):
            publication.save_experience_translation(self.archive, {**data, 'reviewed': False})
        with self.assertRaises(ValueError):
            publication.save_experience_translation(self.archive, {**data, 'items': [{**rows[0], 'period': 'January 2023 — March 2025'}]})
        with self.assertRaises(ValueError):
            publication.save_experience_translation(self.archive, {**data, 'items': rows + rows})
        with self.assertRaises(ValueError):
            publication.save_experience_translation(self.archive, {**data, 'items': [{**rows[0], 'description': 'Contact person@example.org'}]})
        publication.save_experience_translation(self.archive, data)
        current = publication.preview(self.archive)
        self.assertEqual(current['payload']['experience_translations']['en']['items'], rows)
        self.assertEqual(current['payload']['source']['language'], 'ru')
        fake = Publisher()
        publication.publish(self.archive, fake)
        self.assertEqual(fake.calls[0]['experience_translations']['en']['items'], rows)
        changed = {**self.resume, 'sections': [{**self.resume['sections'][0], 'text': EXPERIENCE.replace('описал метрики', 'описал обновлённые метрики')}]}
        self.archive.sync({'client_id': 'publication-test', 'records': [record('resume', changed)]})
        fresh = publication.preview(self.archive)
        self.assertEqual(fresh['experience_needs_review'], ['en'])
        self.assertEqual(fresh['payload']['experience_translations'], {})
        self.assertIn('обновлённые', fresh['payload']['experience'][0]['description'])
        with self.assertRaises(ValueError):
            publication.save_experience_translation(self.archive, data)

    def test_translation_does_not_follow_another_primary_resume_with_identical_work(self):
        from src.portfolio_translations import current_translations
        proposal = publication.preview(self.archive)
        rows = [{**proposal['payload']['experience'][0], 'period': 'January 2023 — February 2025', 'duration': '2 years'}]
        publication.save_experience_translation(self.archive, {'language': 'en', 'basis': proposal['experience_basis'], 'items': rows, 'reviewed': True})
        _, translations, stale = current_translations(publication.read(self.archive), 'another-primary', proposal['payload']['experience'], 'ru')
        self.assertEqual(translations, {})
        self.assertEqual(stale, ['en'])


class BlockPublisher(Publisher):
    def __init__(self, site): super().__init__(); self.site = site
    def read_site(self): return json.loads(json.dumps(self.site))
    def publish(self, payload): self.site = json.loads(json.dumps(payload)); return super().publish(payload)


NEW_JOB = '''New Lab
1
год
Research Engineer
Март
2025
—
Июнь
2026
(
1
год
)
Обучал видеомодели на PyTorch и измерял качество.
'''


class BlockReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.archive = ArchiveStore(Path(self.tmp.name) / 'archive.sqlite3')
        self.resume = cv()
        self.resume['sections'] = [{'key': 'experience', 'heading': 'Опыт работы', 'text': EXPERIENCE}]
        self.archive.sync({'client_id': 'block-test', 'records': [record('resume', self.resume),
                          {'kind': 'profile', 'id': 'profile', 'data': {'primary_id': self.resume['id']}, 'digest': digest({'primary_id': self.resume['id']})}]})
        self.fake = BlockPublisher({}); publication.publish(self.archive, self.fake); self.fake.calls.clear()

    def capture(self, text):
        self.resume = {**self.resume, 'sections': [{'key': 'experience', 'heading': 'Опыт работы', 'text': text}], 'content_hash': digest(text)}
        self.archive.sync({'client_id': 'block-test', 'records': [record('resume', self.resume)]})

    def block(self, comparison, company):
        return next(b for b in comparison['blocks'] if b['kind'] == 'experience' and company in b['label'])

    def test_unchanged_capture_shows_nothing_pending(self):
        value = blocks.compare(self.archive, self.fake)
        self.assertEqual(value['counts']['pending'], 0)
        self.assertEqual({b['status'] for b in value['blocks']}, {'same'})

    def test_changed_and_added_blocks_are_reported_with_a_word_diff(self):
        self.capture(EXPERIENCE.replace('описал метрики', 'опубликовал метрики') + NEW_JOB)
        value = blocks.compare(self.archive, self.fake)
        changed, added = self.block(value, 'Example'), self.block(value, 'New Lab')
        self.assertEqual((changed['status'], changed['fields_changed']), ('changed', ['description']))
        self.assertEqual(added['status'], 'added')
        ops = {part['op']: part['text'] for part in changed['diff']['description'] if part['op'] != 'same'}
        self.assertIn('описал', ops['del']); self.assertIn('опубликовал', ops['add'])

    def test_block_mode_stops_automatic_publication_from_overwriting_the_site(self):
        blocks.set_mode(self.archive, True, self.fake)
        original = self.fake.site['experience']
        self.capture(EXPERIENCE.replace('описал метрики', 'опубликовал метрики'))
        publication.publish(self.archive, self.fake)
        self.assertEqual(self.fake.site['experience'], original)
        blocks.set_mode(self.archive, False)
        publication.publish(self.archive, self.fake)
        self.assertIn('опубликовал', self.fake.site['experience'][0]['description'])

    def test_applies_one_block_and_keeps_the_other_on_the_site(self):
        self.capture(EXPERIENCE.replace('описал метрики', 'опубликовал метрики') + NEW_JOB)
        value = blocks.compare(self.archive, self.fake)
        added = self.block(value, 'New Lab')
        result = blocks.apply_blocks(self.archive, {'basis': value['basis'], 'reviewed': True, 'decisions': {added['key']: {'action': 'hh'}}}, self.fake)
        self.assertEqual(result['phase'], 'published')
        self.assertEqual([row['company'] for row in self.fake.site['experience']], ['New Lab', 'Example Company'])
        self.assertEqual([row['id'] for row in self.fake.site['experience']], ['hh-0', 'hh-1'])
        self.assertIn('описал', self.fake.site['experience'][1]['description'])
        self.assertEqual(result['comparison']['counts']['pending'], 1)

    def test_rewrite_is_published_acknowledged_and_reopens_when_hh_changes_again(self):
        self.capture(EXPERIENCE.replace('описал метрики', 'опубликовал метрики'))
        value = blocks.compare(self.archive, self.fake); block = self.block(value, 'Example')
        rewritten = {**block['hh'], 'description': 'Своя редакция описания проекта на PyTorch.'}
        result = blocks.apply_blocks(self.archive, {'basis': value['basis'], 'reviewed': True, 'decisions': {block['key']: {'action': 'rewrite', 'value': rewritten}}}, self.fake)
        self.assertEqual(self.fake.site['experience'][0]['description'], rewritten['description'])
        self.assertEqual(result['comparison']['counts']['pending'], 0)
        self.assertEqual(result['comparison']['counts']['acknowledged'], 1)
        self.capture(EXPERIENCE.replace('описал метрики', 'пересчитал метрики'))
        self.assertEqual(blocks.compare(self.archive, self.fake)['counts']['pending'], 1)

    def test_rewrites_reject_contacts_and_applying_needs_review_and_fresh_basis(self):
        self.capture(EXPERIENCE.replace('описал метрики', 'опубликовал метрики'))
        value = blocks.compare(self.archive, self.fake); block = self.block(value, 'Example')
        accept = {block['key']: {'action': 'hh'}}
        with self.assertRaises(ValueError): blocks.apply_blocks(self.archive, {'basis': value['basis'], 'decisions': accept}, self.fake)
        with self.assertRaises(ValueError): blocks.apply_blocks(self.archive, {'basis': 'stale', 'reviewed': True, 'decisions': accept}, self.fake)
        with self.assertRaises(ValueError): blocks.apply_blocks(self.archive, {'basis': value['basis'], 'reviewed': True, 'decisions': {'unknown': {'action': 'hh'}}}, self.fake)
        with self.assertRaises(ValueError): blocks.apply_blocks(self.archive, {'basis': value['basis'], 'reviewed': True, 'decisions': {block['key']: {'action': 'rewrite', 'value': {**block['hh'], 'description': 'Пишите на person@example.org'}}}}, self.fake)
        self.assertEqual(self.fake.calls, [])

    def test_changed_block_requires_translation_and_other_rows_keep_theirs(self):
        source = publication.preview(self.archive)['payload']['experience']
        translation = [{**source[0], 'company': 'Example Company', 'role': 'ML Engineer', 'period': 'January 2023 — February 2025', 'duration': '2 years', 'description': 'Built a PyTorch experiment.'}]
        publication.save_experience_translation(self.archive, {'language': 'en', 'basis': publication.preview(self.archive)['experience_basis'], 'items': translation, 'reviewed': True})
        publication.publish(self.archive, self.fake)
        self.capture(EXPERIENCE.replace('описал метрики', 'опубликовал метрики') + NEW_JOB)
        value = blocks.compare(self.archive, self.fake); added = self.block(value, 'New Lab')
        self.assertEqual(value['translation_language'], 'en')
        with self.assertRaises(ValueError): blocks.apply_blocks(self.archive, {'basis': value['basis'], 'reviewed': True, 'decisions': {added['key']: {'action': 'hh'}}}, self.fake)
        english = {'company': 'New Lab', 'role': 'Research Engineer', 'period': 'March 2025 — June 2026', 'duration': '1 year', 'description': 'Trained video models.'}
        blocks.apply_blocks(self.archive, {'basis': value['basis'], 'reviewed': True, 'decisions': {added['key']: {'action': 'hh', 'translation': english}}}, self.fake)
        rows = self.fake.site['experience_translations']['en']['items']
        self.assertEqual(self.fake.site['experience_translations']['en']['basis'], self.fake.site['experience_basis'])
        self.assertEqual([row['description'] for row in rows], ['Trained video models.', 'Built a PyTorch experiment.'])

    def test_failed_publication_restores_the_previous_decisions(self):
        self.capture(EXPERIENCE.replace('описал метрики', 'опубликовал метрики'))
        value = blocks.compare(self.archive, self.fake); block = self.block(value, 'Example')
        class Broken(BlockPublisher):
            def publish(self, payload): raise publication.GitHubError('GitHub не принял публикацию.')
        with self.assertRaises(ValueError): blocks.apply_blocks(self.archive, {'basis': value['basis'], 'reviewed': True, 'decisions': {block['key']: {'action': 'hh'}}}, Broken(self.fake.site))
        state = publication.read(self.archive)
        self.assertFalse(state.get('block_review')); self.assertFalse(state.get('block_decisions'))
        self.assertEqual(blocks.compare(self.archive, self.fake)['counts']['pending'], 1)
