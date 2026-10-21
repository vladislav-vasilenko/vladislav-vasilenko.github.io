import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from src.tests import test_workflow as fixtures
from src.tests.test_archive import cv, record
from src import resume_portfolio as portfolio, resume_review as review
from resume_import_server import create_app


class PortfolioTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    sync=fixtures.WorkflowTests.sync

    def request(self,count=2,**extra):
        chosen=[]
        for i in range(count):
            value=cv(text='Компания Example; Research Engineer; 2020-01 — 2024-12. Реализовал обучение Transformer на PyTorch. '+str(i))
            value.update(id=format(i+1,'x')*38,title='Research CV '+str(i),source_url='https://hh.ru/resume/'+format(i+1,'x')*38)
            self.archive.sync({'client_id':'portfolio-test','records':[record('resume',value)]})
            snap=self.archive.detail('resume',value['id']);chosen.append({'id':value['id'],'version':snap['version_id']})
        return {'snapshots':chosen,'track_id':'generative','model':'luna',**extra}

    def output(self,ctx):
        refs=[next((k,v) for k,v in ctx['passages'].items() if v['kind']=='resume' and v['snapshot_key']==s['snapshot_key']) for s in ctx['snapshots']]
        evidence=lambda pair:[{'source_id':pair[0],'quote':pair[1]['text']}]
        return {'context_key':ctx['key'],'summary':'Сравнить подтверждения под выбранный трек.','recommended_snapshot':ctx['snapshots'][0]['snapshot_key'],
          'ranking':[{'snapshot_key':s['snapshot_key'],'reason':'Есть описанная практика; обучение диффузии нужно подтвердить отдельно.','evidence':evidence(refs[i])} for i,s in enumerate(ctx['snapshots'])],
          'timeline':[{'employer':'Example','role':'Research Engineer','start':'2020-01','end':'2024-12','status':'consistent','comment':'Согласуется по переданным текстам.','evidence':evidence(refs[0])}],
          'findings':[{'kind':'uncertain','priority':'high','action':'validate','comment':'Уточнить масштаб обучения.','evidence':evidence(refs[0])}],
          'edits':[{'snapshot_key':ctx['snapshots'][0]['snapshot_key'],'source_id':refs[0][0],'original':refs[0][1]['text'],'replacement':'Исследования и обучение моделей на PyTorch; уточнить масштаб.','reason':'Сделать описание конкретнее после проверки.','requires_confirmation':True,'evidence':evidence(refs[0])}],
          'questions':['Какие артефакты можно приложить?'],'limitations':['Выписка пользователя не проверена на подлинность.']}

    def test_seven_snapshots_track_revision_and_private_fields_in_offline_prompt(self):
        request=self.request(7,employment_record='Example — Research Engineer, 2020-01 — 2024-12\nСНИЛС: 123-456-789 00\nmail@example.org',record_reviewed=True)
        result=portfolio.prepare(self.archive,request);ctx=result['context'];text=review.prompt(ctx)
        self.assertEqual(len(ctx['snapshots']),7);self.assertEqual(result['api_requests'],0)
        self.assertIn('WORK_',text);self.assertNotIn('123-456-789',text);self.assertNotIn('mail@example.org',text)
        self.assertIn('revision',text);self.assertIn('не технологии',text)
        output=review.run(self.archive,ctx['key'],raw=self.output(ctx));self.assertEqual(len(output['ranking']),7);self.assertEqual(output['api_requests'],0)

    def test_paid_call_needs_confirmation_is_cached_and_does_not_auto_repeat(self):
        ctx=portfolio.prepare(self.archive,self.request())['context'];client=MagicMock()
        with self.assertRaisesRegex(ValueError,'Подтвердите'):review.run(self.archive,ctx['key'],client_factory=lambda:client)
        client.responses.create.assert_not_called()
        client.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps(self.output(ctx)))
        review.run(self.archive,ctx['key'],confirmed=True,client_factory=lambda:client)
        self.assertTrue(review.run(self.archive,ctx['key'],client_factory=lambda:client)['cached']);self.assertEqual(client.responses.create.call_count,1)
        self.assertFalse(client.responses.create.call_args.kwargs['store'])
        request=self.request(model='terra');other=portfolio.prepare(self.archive,request)['context']
        client.responses.create.side_effect=TimeoutError()
        for _ in range(2):
            with self.assertRaises(ValueError):review.run(self.archive,other['key'],confirmed=True,client_factory=lambda:client)
        self.assertEqual(client.responses.create.call_count,2)

    def test_wrong_snapshot_duplicate_selection_record_consent_and_quote_fabrication_rejected(self):
        request=self.request()
        for modified in [{**request,'snapshots':[request['snapshots'][0]]*2},{**request,'employment_record':'Example 2020–2024'}, {**request,'snapshots':[{**request['snapshots'][0],'id':'z'*38},request['snapshots'][1]]}]:
            with self.assertRaises(ValueError):portfolio.prepare(self.archive,modified)
        ctx=portfolio.prepare(self.archive,request)['context'];good=self.output(ctx)
        for mutation in ('quote','edit','conflict','missing_cv'):
            bad=copy.deepcopy(good)
            if mutation=='quote':bad['ranking'][0]['evidence'][0]['quote']='Вымышленное обучение на тысяче GPU.'
            if mutation=='edit':bad['edits'][0]['snapshot_key']=ctx['snapshots'][1]['snapshot_key']
            if mutation=='conflict':bad['timeline'][0]['status']='conflict'
            if mutation=='missing_cv':bad['ranking'].pop()
            with self.assertRaises(ValueError):review.run(self.archive,ctx['key'],raw=bad)

    def test_new_facts_and_track_revision_invalidate_context_but_old_snapshot_remains_explicit(self):
        from src.candidate_facts import save
        from src import career_skills_store
        request=self.request();ctx=portfolio.prepare(self.archive,request)['context']
        save(self.archive,request['snapshots'][0]['id'],'project','Проект PyTorch подтверждён локальным экспериментом.')
        with self.assertRaisesRegex(ValueError,'Источники'):review.run(self.archive,ctx['key'],raw=self.output(ctx))
        newer=portfolio.prepare(self.archive,request)['context'];self.assertNotEqual(ctx['key'],newer['key'])
        track=copy.deepcopy(newer['track']);track['label']='Новая цель';career_skills_store.save_track(self.archive,track)
        with self.assertRaisesRegex(ValueError,'Трек'):review.run(self.archive,newer['key'],raw=self.output(newer))

    def test_multiple_named_sources_are_reviewed_independently_and_part_of_context_version(self):
        request=self.request(additional_sources=[{'label':'Выписка','kind':'employment_record','text':'Example; приём 2020-01, увольнение 2024-12.','reviewed':False}])
        with self.assertRaisesRegex(ValueError,'каждого'):portfolio.prepare(self.archive,request)
        request['additional_sources'][0]['reviewed']=True
        ctx=portfolio.prepare(self.archive,request)['context'];self.assertEqual(ctx['passages']['EXTRA_1_1']['label'],'Выписка')
        request['additional_sources'].append({'label':'Моя заметка','kind':'user_note','text':'В 2023 году работа частичная, не полный день.','reviewed':True})
        newer=portfolio.prepare(self.archive,request)['context'];self.assertNotEqual(ctx['key'],newer['key'])
        self.assertEqual(newer['passages']['EXTRA_2_1']['kind'],'user_note');self.assertEqual(len(newer['additional_sources']),2)

    def test_cookie_routes_keep_both_modes_and_block_unconfirmed_paid_calls(self):
        request=self.request();app=create_app('fixture',archive_path=self.path)
        with TestClient(app) as client:
            headers={'Origin':'http://127.0.0.1:8788'}
            body={'op':'prepare_portfolio',**request}
            self.assertEqual(client.post('/archive/resume-review',json=body).status_code,401)
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
            response=client.post('/archive/resume-review',json=body,headers=headers);self.assertEqual(response.status_code,200)
            ctx=response.json()['context']
            with patch('openai.OpenAI') as factory:
                denied=client.post('/archive/resume-review',json={'op':'generate','context_key':ctx['key']},headers=headers)
                self.assertEqual(denied.status_code,422);factory.assert_not_called()
                exported=client.post('/archive/resume-review',json={'op':'prompt','context_key':ctx['key']},headers=headers)
                self.assertIn('target_track',exported.json()['prompt'])
                imported=client.post('/archive/resume-review',json={'op':'import','context_key':ctx['key'],'analysis':self.output(ctx)},headers=headers)
                self.assertEqual(imported.status_code,200);factory.assert_not_called()
