import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from fastapi.testclient import TestClient
from src.archive_store import ArchiveStore
from src.skill_analysis import analyze,context,cached,validate,metrics,MODEL
from src.cover_letter import source_passages
from src.tests.test_extension_ranking import cv,job,NOW
from resume_import_server import create_app

class SkillAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=ArchiveStore(Path(self.tmp.name)/'state.sqlite3')
        self.cv=cv('a','PyTorch Transformer');self.job=job(1,'PyTorch Transformer');self.goal='Generative research'
        with self.store.connect() as db:
            self.store._entity(db,'resume',self.cv['id'],self.cv,NOW.isoformat());self.store._entity(db,'vacancy',self.job['id'],self.job,NOW.isoformat())
        ctx=context(self.store,self.cv['id'],self.job['id'],self.goal);self.cv_parts=source_passages(ctx['cv_text'],'R');self.jd_parts=source_passages(ctx['jd_text'],'J')
        self.raw={'requirements':[{'requirement':'Разработка моделей на PyTorch','dimension':'engineering','importance':'must','status':'confirmed','job_passage_id':'J1','job_quote':self.jd_parts['J1'][:80],'resume_passage_ids':['R1'],'explanation':'В CV приведён практический проект, масштаб требует уточнения.','action':'Уточнить детали эксперимента.'},{'requirement':'Обучение Transformer','dimension':'models','importance':'nice','status':'not_evidenced','job_passage_id':'J1','job_quote':self.jd_parts['J1'][:90],'resume_passage_ids':[],'explanation':'Нужны детали обучения.','action':'Уточнить опыт.'}],'goal_alignment':'Направление близко цели.','recommendation':'clarify','recommendation_reason':'Стоит уточнить масштаб и требования.','questions':['Какие модели вы обучали?'],'limitations':['Рассматривается только текст CV.']}
        self.client=Mock();self.client.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps(self.raw),usage=SimpleNamespace(input_tokens=100,output_tokens=80))
    def run_analysis(self,**kwargs):return analyze(self.store,self.cv['id'],self.job['id'],self.goal,client_factory=lambda:self.client,now=NOW,**kwargs)
    def test_cited_review_is_saved_and_reopened_without_api(self):
        first=self.run_analysis();self.assertEqual(first['metrics']['overall']['percent'],67)
        self.assertEqual(first['requirements'][0]['resume_quotes'],[self.cv_parts['R1']])
        self.assertEqual(self.client.responses.create.call_args.kwargs['model'],MODEL);self.assertFalse(self.client.responses.create.call_args.kwargs['store'])
        schema=self.client.responses.create.call_args.kwargs['text']['format']['schema']['properties']['requirements']['items']['properties']
        self.assertEqual(schema['resume_passage_ids']['items']['enum'],list(self.cv_parts));self.assertEqual(schema['job_passage_id']['enum'],list(self.jd_parts))
        second=self.run_analysis();self.assertTrue(second['cached']);self.assertEqual(second['api_requests'],0);self.assertEqual(self.client.responses.create.call_count,1)
        self.assertIsNotNone(cached(ArchiveStore(self.store.path),context(self.store,self.cv['id'],self.job['id'],self.goal)))
    def test_missing_evidence_is_not_equivalent_to_explicit_skill_gap(self):
        raw=copy.deepcopy(self.raw);raw['requirements'][1]['status']='explicit_gap';raw['requirements'][1]['resume_passage_ids']=['R1']
        with self.assertRaisesRegex(ValueError,'Нельзя объявить'):validate(raw,self.cv_parts,self.jd_parts)
    def test_invented_quotes_and_sources_are_rejected_and_never_persisted(self):
        for index,(field,value) in enumerate([('job_quote','A fabricated vacancy requirement'),('resume_passage_ids',['R999'])]):
            self.goal='Test validation '+str(index)
            raw=copy.deepcopy(self.raw);raw['requirements'][0][field]=value;self.client.responses.create.return_value.output_text=json.dumps(raw)
            with self.assertRaises(ValueError):self.run_analysis()
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM skill_analyses').fetchone()[0],0)
    def test_evidence_limit_is_in_strict_schema_and_failure_is_not_recharged(self):
        self.run_analysis();schema=self.client.responses.create.call_args.kwargs['text']['format']['schema']['properties']['requirements']['items']['properties']
        self.assertEqual(schema['resume_passage_ids']['maxItems'],3)
        with self.store.connect() as db:db.execute('DELETE FROM skill_analyses')
        self.raw['requirements'][0]['resume_passage_ids']=['R999'];self.client.responses.create.return_value.output_text=json.dumps(self.raw)
        for _ in range(2):
            with self.assertRaisesRegex(ValueError,'несуществующий R-ID'):self.run_analysis()
        self.assertEqual(self.client.responses.create.call_count,2)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM skill_analysis_failures').fetchone()[0],1)
    def test_too_many_references_is_not_reported_as_an_unknown_cv_fragment(self):
        raw=copy.deepcopy(self.raw);raw['requirements'][0]['resume_passage_ids']=['R1','R2','R3','R4']
        with self.assertRaisesRegex(ValueError,'больше трёх'):validate(raw,{k:'Практический опыт.' for k in ['R1','R2','R3','R4']},self.jd_parts)
    def test_learning_and_plans_are_not_scored_as_completed_practice(self):
        raw=copy.deepcopy(self.raw)
        result=validate(raw,{'R1':'Самостоятельно изучаю диффузионные модели; выполняю лабораторные работы.'},self.jd_parts)
        self.assertEqual(result['requirements'][0]['status'],'studying')
        result=validate(raw,{'R1':'Планирую реализовать модель и выполнить обучение.'},self.jd_parts)
        self.assertEqual(result['requirements'][0]['status'],'not_evidenced')
    def test_cv_jd_goal_changes_get_separate_cache_and_empty_dimension_has_no_fake_percent(self):
        self.run_analysis();ctx=context(self.store,self.cv['id'],self.job['id'],'Another goal');self.assertIsNone(cached(self.store,ctx))
        changed={**self.job,'description':self.job['description']+' CUDA kernels'}
        with self.store.connect() as db:self.store._entity(db,'vacancy',changed['id'],changed,(NOW+timedelta(hours=1)).isoformat())
        self.assertIsNone(cached(self.store,context(self.store,self.cv['id'],self.job['id'],self.goal)))
        self.assertEqual(metrics([])['overall']['percent'],None)
    def test_reading_cache_cannot_call_api_and_paid_cookie_post_requires_same_origin(self):
        with TestClient(create_app('fixture',archive_path=self.store.path)) as client:
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
            params={'resume_id':self.cv['id'],'vacancy_id':self.job['id'],'goal':self.goal}
            with patch('src.skill_analysis.analyze',return_value={'api_requests':1}) as writer:
                self.assertEqual(client.get('/archive/skill-analysis',params=params).json(),{'analysis':None});writer.assert_not_called()
                self.assertEqual(client.post('/archive/skill-analysis',json=params).status_code,401)
                self.assertEqual(client.post('/archive/skill-analysis',json=params,headers={'Origin':'https://evil.example'}).status_code,401)
                self.assertEqual(client.post('/archive/skill-analysis',json=params,headers={'Origin':'http://127.0.0.1:8788'}).status_code,200);self.assertEqual(writer.call_count,1)
                self.assertEqual(client.post('/rank',json={},headers={'Origin':'http://127.0.0.1:8788'}).status_code,401)
    def test_snippets_are_not_sent_and_incomplete_model_output_is_not_cached(self):
        self.client.responses.create.return_value.status='incomplete'
        with self.assertRaisesRegex(ValueError,'не завершила'):self.run_analysis()
        snippet={**self.job,'description_quality':'snippet'}
        # A new separate snippet record cannot borrow the full description of another ID.
        snippet.update(id='hh_2',link='https://hh.ru/vacancy/2')
        with self.store.connect() as db:self.store._entity(db,'vacancy','hh_2',snippet,NOW.isoformat())
        with self.assertRaisesRegex(ValueError,'полное'):analyze(self.store,self.cv['id'],'hh_2',self.goal,client_factory=lambda:self.client,now=NOW)

    def test_history_keeps_exact_inputs_after_both_documents_change_and_reuses_reverted_text(self):
        from src.skill_history import history,detail
        first=self.run_analysis();original=detail(self.store,first['key'])
        with self.store.connect() as db:
            changed_cv=copy.deepcopy(self.cv);changed_cv['sections'][0]['text']+=' Updated CUDA experience'
            from src.resume_source import content_hash
            changed_cv['content_hash']=content_hash(changed_cv)
            self.store._entity(db,'resume',self.cv['id'],changed_cv,(NOW+timedelta(hours=1)).isoformat())
            self.store._entity(db,'vacancy',self.job['id'],{**self.job,'description':self.job['description']+' CUDA kernels'},(NOW+timedelta(hours=1)).isoformat())
        saved=detail(ArchiveStore(self.store.path),first['key'])
        for kind in ('resume','vacancy'):
            self.assertEqual(saved['sources'][kind]['text'],original['sources'][kind]['text'])
            self.assertEqual(saved['sources'][kind]['version_id'],original['sources'][kind]['version_id'])
            self.assertFalse(saved['sources'][kind]['matches_current'])
        self.assertEqual(saved['analysis']['api_requests'],0)
        second=self.run_analysis();self.assertNotEqual(second['key'],first['key'])
        self.assertEqual(history(self.store,self.cv['id'])['total'],2)
        with self.store.connect() as db:
            self.store._entity(db,'resume',self.cv['id'],self.cv,(NOW+timedelta(hours=2)).isoformat())
            self.store._entity(db,'vacancy',self.job['id'],self.job,(NOW+timedelta(hours=2)).isoformat())
        third=self.run_analysis();self.assertEqual(third['key'],first['key']);self.assertEqual(third['api_requests'],0)
        self.assertEqual(self.client.responses.create.call_count,2)
        self.assertEqual(history(self.store)['total'],2)

    def test_legacy_history_links_matching_old_versions_never_current_substitutes(self):
        from src.skill_history import detail
        report=self.run_analysis()
        with self.store.connect() as db:
            db.execute('DELETE FROM skill_analysis_sources')
            self.store._entity(db,'vacancy',self.job['id'],{**self.job,'description':self.job['description']+' Changed'},(NOW+timedelta(hours=1)).isoformat())
        migrated=detail(self.store,report['key'])
        self.assertEqual(migrated['sources']['vacancy']['text'],context(self.store,self.cv['id'],self.job['id'],self.goal)['jd_text'].removesuffix(' Changed'))
        self.assertFalse(migrated['sources']['vacancy']['matches_current'])
        with self.store.connect() as db:
            db.execute('DELETE FROM skill_analysis_sources')
            db.execute('DELETE FROM versions WHERE kind=? AND id=?',('vacancy',migrated['sources']['vacancy']['version_id']))
        missing=detail(self.store,report['key']);self.assertIsNone(missing['sources']['vacancy']['text'])
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_history_routes_are_read_only_authenticated_and_backup_includes_inputs(self):
        report=self.run_analysis()
        with TestClient(create_app('fixture',archive_path=self.store.path)) as client:
            self.assertEqual(client.get('/archive/skill-history').status_code,401)
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
            with patch('src.skill_analysis.analyze',side_effect=AssertionError('No paid calls')):
                listed=client.get('/archive/skill-history').json();self.assertEqual(listed['total'],1)
                self.assertEqual(client.get('/archive/skill-history',params={'resume_id':'other'}).json()['total'],0)
                saved=client.get('/archive/skill-history/'+report['key']).json()
                self.assertEqual(saved['analysis']['key'],report['key']);self.assertTrue(saved['sources']['resume']['text'])
                self.assertEqual(client.get('/archive/skill-history/missing').status_code,404)
                backup=client.get('/archive/export').json()['tables'];self.assertEqual(len(backup['skill_analysis_sources']),1)

    def test_hh_badges_return_only_current_evidence_without_model_calls(self):
        from src.hh_badges import lookup
        report=self.run_analysis();params={'ids':[self.job['id'],'hh_999'],'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'goal':self.goal}
        with patch('src.skill_analysis.analyze',side_effect=AssertionError('No API')):
            data=lookup(self.store,params);self.assertTrue(data['cv_ready']);self.assertEqual(len(data['items']),1)
            self.assertEqual(data['items'][0]['coverage'],67);self.assertEqual(data['items'][0]['missing_skills'],['Обучение Transformer'])
            self.assertNotIn('resume_quotes',json.dumps(data));self.assertNotIn('sections',json.dumps(data))
            wrong=lookup(self.store,{**params,'resume_hash':'changed'});self.assertFalse(wrong['cv_ready']);self.assertNotIn('coverage',wrong['items'][0])
            other=lookup(self.store,{**params,'goal':'different'});self.assertNotIn('coverage',other['items'][0]);self.assertTrue(other['items'][0]['analysis_stale'])
            with self.store.connect() as db:self.store._entity(db,'vacancy',self.job['id'],{**self.job,'description':self.job['description']+' CHANGED'},(NOW+timedelta(hours=1)).isoformat())
            stale=lookup(self.store,params);self.assertNotIn('coverage',stale['items'][0]);self.assertTrue(stale['items'][0]['analysis_stale'])
            with self.assertRaises(ValueError):lookup(self.store,{**params,'ids':['board_foreign']})
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_inline_analysis_reuses_sqlite_and_rejects_a_different_browser_cv(self):
        from src.hh_inline import run
        report=self.run_analysis();params={'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'vacancy_id':self.job['id'],'goal':self.goal,'action':'analysis_read'}
        saved=run(self.store,params,Path(self.tmp.name));self.assertEqual(saved['result']['key'],report['key'])
        again=run(self.store,{**params,'action':'analysis'},Path(self.tmp.name));self.assertEqual(again['result']['api_requests'],0)
        with self.assertRaisesRegex(ValueError,'Версия CV'):run(self.store,{**params,'resume_hash':'other'},Path(self.tmp.name))
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_inline_letter_and_question_use_existing_generators_and_one_selected_cv(self):
        from src.hh_inline import run
        params={'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'vacancy_id':self.job['id'],'goal':self.goal}
        with patch('src.cover_letter.generate_cover_letter',return_value={'text':'Draft'}) as cover:
            result=run(self.store,{**params,'action':'cover','sentence_count':50,'comments':'Математическая мотивация'},Path(self.tmp.name))
            self.assertEqual(result['result']['text'],'Draft');payload=cover.call_args.args[0]
            self.assertEqual(len(payload['bundle']['resumes']),1);self.assertEqual(payload['sentence_count'],50);self.assertEqual(payload['comments'],'Математическая мотивация')
        with patch('src.recruiter_answers.draft_answer',return_value={'answer':'Draft'}) as answer:
            result=run(self.store,{**params,'action':'answer','question':'Какие модели обучали?','model':'terra'},Path(self.tmp.name))
            ctx,question,model,_=answer.call_args.args;self.assertEqual(question,'Какие модели обучали?');self.assertEqual(model,'terra');self.assertEqual(ctx['vacancy']['id'],self.job['id']);self.assertEqual(ctx['goal'],self.goal)
            self.assertIn('PyTorch',ctx['resume_text']);self.assertNotIn('source_page',ctx['vacancy'])

    def test_inline_endpoint_requires_extension_token_even_when_dashboard_is_logged_in(self):
        self.run_analysis()
        with TestClient(create_app('fixture',archive_path=self.store.path)) as client:
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
            params={'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'vacancy_id':self.job['id'],'goal':self.goal,'action':'analysis_read'}
            self.assertEqual(client.post('/archive/hh-inline',json=params,headers={'Origin':'http://127.0.0.1:8788'}).status_code,401)
            response=client.post('/archive/hh-inline',json=params,headers={'X-Resume-Import-Token':'fixture'});self.assertEqual(response.status_code,200);self.assertEqual(response.json()['result']['api_requests'],0)

    def test_prompt_upgrade_does_not_recharge_unchanged_cv_vacancy_and_goal(self):
        first=self.run_analysis()
        with patch('src.skill_analysis.VERSION','skills-future'):
            reused=self.run_analysis()
        self.assertEqual(reused['key'],first['key']);self.assertEqual(reused['api_requests'],0)
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_sources_are_bound_to_inputs_even_if_sync_arrives_during_generation(self):
        from src.skill_history import detail
        response=self.client.responses.create.return_value
        def concurrent_sync(**kwargs):
            with self.store.connect() as db:self.store._entity(db,'vacancy',self.job['id'],{**self.job,'description':self.job['description']+' NEW REQUIREMENTS'},(NOW+timedelta(hours=1)).isoformat())
            return response
        self.client.responses.create.side_effect=concurrent_sync
        report=self.run_analysis();saved=detail(self.store,report['key'])
        self.assertFalse(saved['sources']['vacancy']['matches_current'])
        self.assertNotIn('NEW REQUIREMENTS',saved['sources']['vacancy']['text'])


    def test_verbatim_quote_crossing_a_fragment_boundary_is_valid_only_in_original_source(self):
        raw=copy.deepcopy(self.raw);raw['requirements']=raw['requirements'][:1]
        quote='Будет преимуществом опыт внедрения решений в крупных продуктах с высокими требованиями к безопасности'
        raw['requirements'][0].update(job_passage_id='J2',job_quote=quote)
        passages={'J1':'Участие в разработке сервиса. Будет преимуществом','J2':'опыт внедрения решений в крупных продуктах с высокими требованиями к безопасности и надежности'}
        text='Участие в разработке сервиса. '+quote+' и надежности'
        result=validate(raw,self.cv_parts,passages,jd_text=text);self.assertEqual(result['requirements'][0]['job_quote'],quote)
        for original in (None,text.replace('внедрения','разработки')):
            with self.assertRaisesRegex(ValueError,'цитатой'):validate(raw,self.cv_parts,passages,jd_text=original)
        raw['requirements'][0]['job_passage_id']='J3';passages['J3']='Иное требование, которое не относится к выбранной цитате.'
        with self.assertRaisesRegex(ValueError,'цитатой'):validate(raw,self.cv_parts,passages,jd_text=text+' '+passages['J3'])


    def test_model_sentence_separator_is_replaced_with_exact_original_without_changing_words(self):
        raw=copy.deepcopy(self.raw);raw['requirements']=raw['requirements'][:1]
        original='Знаете RAG-фреймворки, search-eval-подходы Знакомы с методами DPO, GRPO'
        raw['requirements'][0].update(job_passage_id='J1',job_quote=original.replace('подходы Знакомы','подходы. Знакомы'))
        result=validate(raw,self.cv_parts,{'J1':original},jd_text=original)
        self.assertEqual(result['requirements'][0]['job_quote'],original)
        for change in ('Не знакомы с методами DPO, GRPO','Знакомы с методами DPO, PPO'):
            raw['requirements'][0]['job_quote']=original.replace('Знакомы с методами DPO, GRPO',change)
            with self.assertRaisesRegex(ValueError,'цитатой'):validate(raw,self.cv_parts,{'J1':original},jd_text=original)


    def test_wrong_job_fragment_id_is_reanchored_only_to_one_verbatim_source(self):
        raw=copy.deepcopy(self.raw);raw['requirements']=raw['requirements'][:1]
        quote='В этой роли вы сможете влиять на архитектуру моделей и обучающие пайплайны.'
        raw['requirements'][0].update(job_passage_id='J1',job_quote=quote)
        passages={'J1':'Здесь описаны обязанности разработчика моделей.','J2':quote}
        result=validate(raw,self.cv_parts,passages,jd_text=' '.join(passages.values()))['requirements'][0]
        self.assertEqual(result['job_passage_id'],'J2');self.assertEqual(result['citation_reanchored_from'],'J1');self.assertEqual(result['job_quote'],quote)
        passages['J3']=quote
        with self.assertRaisesRegex(ValueError,'цитатой'):validate(raw,self.cv_parts,passages)

if __name__=='__main__':unittest.main()
