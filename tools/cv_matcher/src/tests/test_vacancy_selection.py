import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src import vacancy_selection as selection
from src.tests import test_workflow as fixtures
from src.tests.test_archive import job, record, CLIENT
from src.resume_source import content_hash


def context(result):
    return json.loads(result['prompt'].split('ДАННЫЕ ДЛЯ ОТБОРА (JSON):\n', 1)[1])


class VacancySelectionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WorkflowTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.archive=self.f.archive;self.data={'resume_id':self.f.cv['id']}

    def sync(self,*jobs):
        for start in range(0,len(jobs),100):
            result=self.archive.sync({'client_id':CLIENT,'records':[record('vacancy',j) for j in jobs[start:start+100]]})
            self.assertFalse(result['rejected'])

    def test_prompt_includes_selected_cv_short_cards_and_known_application_without_api(self):
        snippet=job('hh_2',text='Исследования DiT, PyTorch',description_quality='snippet',source_page='https://hh.ru/search/vacancy?text=ML')
        self.sync(snippet,job('hh_3',archived=True))
        with patch('src.extension_ranking.OpenAIBackend.embed_documents',side_effect=AssertionError('No embeddings')),patch('openai.OpenAI',side_effect=AssertionError('No LLM')):
            result=selection.build(self.archive,{**self.data,'goal':'Diffusion research','comments':'Приоритет R&D'})
        data=context(result);jobs={j['id']:j for j in data['vacancies']}
        self.assertEqual(result['api_requests'],0);self.assertEqual(set(jobs),{'hh_1','hh_2'})
        self.assertEqual(data['resume']['id'],self.f.cv['id']);self.assertIn('Transformer',data['resume']['professional_text'])
        self.assertEqual(jobs['hh_2']['text_kind'],'listing_snippet');self.assertEqual(jobs['hh_2']['availability'],'unknown')
        self.assertEqual(jobs['hh_1']['existing_application']['id'],self.f.id)
        self.assertIn('не отклоняй позицию только',result['prompt']);self.assertIn('отдельный отклик в каждом источнике допустим',result['prompt'])

    def test_filters_match_company_search_and_quality_selection_instead_of_first_visible_page(self):
        self.sync(job('hh_2',company='Yandex',text='PyTorch diffusion text'),job('hh_3',company='Sber',text='Python services',description_quality='snippet'))
        result=selection.build(self.archive,{**self.data,'companies':['yandex'],'q':'diffusion','status':'full'})
        self.assertEqual([j['id'] for j in context(result)['vacancies']],['hh_2'])
        with self.assertRaisesRegex(ValueError,'нет вакансий'):selection.build(self.archive,{**self.data,'companies':[]})

    def test_large_selection_is_explicitly_paginated_without_omission_or_overlap(self):
        self.sync(*(job('hh_'+str(i),text='PyTorch research snippet',description_quality='snippet') for i in range(2,107)))
        results=[selection.build(self.archive,{**self.data,'limit':50,'packet':p}) for p in (1,2,3)]
        ids=[j['id'] for r in results for j in context(r)['vacancies']]
        self.assertEqual(len(ids),106);self.assertEqual(len(set(ids)),106)
        self.assertEqual([r['included'] for r in results],[50,50,6]);self.assertTrue(all(r['total']==106 and r['packets']==3 for r in results))
        with self.assertRaisesRegex(ValueError,'3 пакетов'):selection.build(self.archive,{**self.data,'limit':50,'packet':4})

    def test_entire_archive_exceeds_page_and_prompt_limits_without_silent_truncation(self):
        self.sync(*(job('hh_'+str(i),text='PyTorch research. '*90,description_quality='snippet',source_page='https://hh.ru/search/vacancy') for i in range(2,212)),job('hh_212',archived=True))
        with patch.object(self.archive,'detail',wraps=self.archive.detail) as detail:
            result=selection.build(self.archive,{**self.data,'all_vacancies':True,'companies':['yandex'],'q':'no-match','status':'closed','ranked_only':True,'limit':-1,'packet':10000,'description_chars':1200})
        data=context(result);ids={j['id'] for j in data['vacancies']}
        self.assertEqual(len(ids),211);self.assertNotIn('hh_212',ids);self.assertEqual(result['included'],result['total']);self.assertEqual(result['packets'],1);self.assertEqual(result['packet'],1)
        self.assertTrue(result['all_vacancies']);self.assertTrue(result['large_prompt']);self.assertGreater(result['characters'],250000)
        self.assertEqual(data['selection']['scope'],'entire_archive');self.assertIsNone(data['selection']['companies']);self.assertEqual(data['selection']['q'],'')
        self.assertIn('Сравни все карточки',result['prompt']);self.assertNotIn('Сравни только карточки данного пакета',result['prompt'])
        self.assertEqual(detail.call_count,1) # CV only, not one expensive query per job.
        self.assertEqual(result['api_requests'],0)
        self.assertEqual(len(self.archive.entities('vacancy',limit=9999)['items']),200)

    def test_all_flag_is_strict_and_description_length_is_explicit(self):
        with self.assertRaises(ValueError):selection.build(self.archive,{**self.data,'all_vacancies':'true'})
        with self.assertRaises(ValueError):selection.build(self.archive,{**self.data,'description_chars':0})
        self.sync(job('hh_2',text='PyTorch research. '*100))
        result=selection.build(self.archive,{**self.data,'all_vacancies':True,'description_chars':400})
        self.assertTrue(all(len(j['short_description'])<=401 for j in context(result)['vacancies']))

    def test_shortened_text_label_contacts_and_missing_text_are_preserved_honestly(self):
        self.sync(job('hh_2',text=('Research requirement. '*180)+' secret.person@example.com +7 999 123 45 67'),job('hh_3',text='',description_quality='missing'))
        result=selection.build(self.archive,self.data);jobs={j['id']:j for j in context(result)['vacancies']}
        self.assertTrue(jobs['hh_2']['text_shortened']);self.assertLessEqual(len(jobs['hh_2']['short_description']),1201)
        self.assertEqual(jobs['hh_2']['text_kind'],'shortened_full_description');self.assertEqual(jobs['hh_3']['short_description'],'')
        self.assertNotIn('secret.person@example.com',result['prompt']);self.assertNotIn('+7 999 123 45 67',result['prompt'])

    def test_only_selected_resume_facts_are_included_and_wishes_are_separate(self):
        from src.candidate_facts import save
        save(self.f.store,self.f.cv['id'],'research','Использовал Diffusers для подключения LoRA')
        other={**self.f.cv,'id':'b'*38,'source_url':'https://hh.ru/resume/'+'b'*38,'title':'Other CV'}
        other['content_hash']=content_hash(other)
        self.archive.sync({'client_id':CLIENT,'records':[record('resume',other)]})
        save(self.f.store,other['id'],'other','Другой кандидат и другой опыт')
        result=selection.build(self.archive,{**self.data,'comments':'Хочу заниматься FLUX'})
        data=context(result);self.assertEqual(data['comments'],'Хочу заниматься FLUX')
        self.assertIn('Diffusers',data['user_stated_facts'][0]['text']);self.assertNotIn('Другой кандидат',result['prompt'])

    def test_invalid_context_and_empty_ranking_fail_without_fabricated_recommendations(self):
        for extra in ({'resume_id':''},{'limit':0},{'limit':101},{'packet':0},{'top':31},{'limit':True},{'companies':'Sber'},{'goal':'x'*2001},{'model':[]},{'ranked_only':'false'}):
            with self.assertRaises(ValueError,msg=str(extra)):selection.build(self.archive,{**self.data,**extra})
        with self.assertRaisesRegex(ValueError,'нет вакансий'):selection.build(self.archive,{**self.data,'ranked_only':True})

    def test_http_is_authenticated_and_cookie_ui_can_copy_without_token_in_browser_code(self):
        from resume_import_server import create_app
        with TestClient(create_app('fixture',archive_path=self.archive.path)) as client:
            body={'op':'vacancy_selection_prompt',**self.data}
            self.assertEqual(client.post('/archive/workflow',json=body).status_code,401)
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
            result=client.post('/archive/workflow',json=body,headers={'Origin':'http://127.0.0.1:8788'})
            self.assertEqual(result.status_code,200);self.assertEqual(result.json()['api_requests'],0)
            self.assertEqual(client.get('/assets/vacancy-selection.js').status_code,200)
