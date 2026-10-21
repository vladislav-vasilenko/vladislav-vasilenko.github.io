from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.cover_letter import generate_cover_letter, validate_draft, OpenAICoverWriter, SCHEMA, source_passages
from src.resume_source import content_hash
from resume_import_server import create_app

NOW=datetime(2026,10,14,12,tzinfo=timezone.utc)
CV1='В МТС дообучал LLaMA 3 методом SFT и улучшал качество ответов на внутренних данных.'
CV2='В самостоятельном проекте обучал Transformer на PyTorch и сравнивал варианты attention.'
JD1='Дообучать языковые модели методом SFT и оценивать качество ответов.'
JD2='Нужны знание PyTorch, опыт обучения Transformer и воспроизводимых экспериментов.'

def raw():return {'ready':True,'matches':[{'text':CV1,'resume_quote':CV1,'vacancy_quote':JD1},{'text':CV2,'resume_quote':CV2,'vacancy_quote':JD2}],'note':''}
def payload():
    cv={'id':'file_'+'a'*64,'file_hash':'a'*64,'source_type':'file','title':'Research CV','quality':'full','checked_at':'2025-01-01T00:00:00Z','reviewed_at':'2026-10-14T10:00:00Z','sections':[{'key':'document','heading':'CV','text':CV1+' '+CV2}]};cv['content_hash']=content_hash(cv)
    job={'id':'hh_1','link':'https://hh.ru/vacancy/1','title':'Research Engineer','company':'Example','description':JD1+' '+JD2+' Команда исследует генеративные модели и поддерживает воспроизводимые эксперименты.','description_quality':'full'}
    return {'resume_id':cv['id'],'bundle':{'schema_version':2,'primary_id':cv['id'],'resumes':[cv]},'vacancy':job}
class FakeWriter:
    contexts=[]
    def __init__(self,model):self.model=model
    def generate(self,context):
        self.contexts.append(context);draft=raw();draft['matches']=draft['matches'][:context.get('sentence_count',2)]
        return draft,{'input_tokens':100,'output_tokens':150}
class CoverLetterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);FakeWriter.contexts=[]
        self.env=patch.dict('os.environ',{'COVER_LETTER_MODEL':'gpt-4.1-mini'});self.env.start();self.addCleanup(self.env.stop)
    def generate(self,p=None):return generate_cover_letter(p or payload(),self.root,writer_factory=FakeWriter,now=NOW)
    def test_short_grounded_draft_is_cached_and_has_provenance(self):
        first=self.generate();self.assertLessEqual(first['word_count'],50);self.assertLessEqual(first['char_count'],480);self.assertEqual(first['api_requests'],1)
        self.assertEqual(len(first['evidence']),2);self.assertEqual(first['resume_hash'],payload()['bundle']['resumes'][0]['content_hash'])
        second=self.generate();self.assertTrue(second['cached']);self.assertEqual(second['api_requests'],0);self.assertEqual(second['input_tokens'],0);self.assertEqual(len(FakeWriter.contexts),1)
        self.assertEqual(next(self.root.glob('*.json')).stat().st_mode&0o777,0o600)
    def test_cv_job_and_model_changes_invalidate_cached_draft(self):
        original=self.generate();p=payload();p['vacancy']['description']+=' Важна оценка качества.'
        self.assertNotEqual(self.generate(p)['cache_key'],original['cache_key'])
        p=payload();r=p['bundle']['resumes'][0];r['sections'][0]['text']+=' Добавлен новый проект.';r['content_hash']=content_hash(r)
        self.assertNotEqual(self.generate(p)['cache_key'],original['cache_key'])
        with patch.dict('os.environ',{'COVER_LETTER_MODEL':'gpt-4.1-mini-2025-04-14'}):self.assertNotEqual(self.generate()['cache_key'],original['cache_key'])
        self.assertEqual(len(FakeWriter.contexts),4)
    def test_explicit_model_selection_is_validated_and_separately_cached(self):
        p=payload();p['model']='luna';first=self.generate(p);self.assertEqual(first['model'],'gpt-6-luna')
        p['model']='terra';other=self.generate(p);self.assertEqual(other['model'],'gpt-5.6-terra');self.assertNotEqual(first['cache_key'],other['cache_key'])
        p['model']='luna';self.assertTrue(self.generate(p)['cached']);self.assertEqual(len(FakeWriter.contexts),2)
        p['model']='arbitrary-model'
        with self.assertRaises(ValueError):self.generate(p)
    def test_comments_and_sentence_count_are_cached_as_separate_variants(self):
        original=self.generate();p=payload();p.update(sentence_count=1,comments='  Подчеркни исследовательский интерес.  ')
        custom=self.generate(p);self.assertNotEqual(original['cache_key'],custom['cache_key'])
        self.assertEqual(len(custom['evidence']),1);self.assertEqual(custom['sentence_count'],1)
        self.assertEqual(FakeWriter.contexts[-1]['comments'],'Подчеркни исследовательский интерес.')
        self.assertTrue(self.generate(p)['cached']);self.assertEqual(len(FakeWriter.contexts),2)
        p['comments']='Сделай акцент на самостоятельном проекте.'
        self.assertNotEqual(self.generate(p)['cache_key'],custom['cache_key'])
    def test_invalid_settings_fail_before_api_and_wrong_sentence_count_is_rejected(self):
        for value in [0,51,True,2.0,'2',None]:
            p=payload();p['sentence_count']=value
            with self.assertRaises(ValueError):self.generate(p)
        for value in [None,[], 'x'*2001]:
            p=payload();p['comments']=value
            with self.assertRaises(ValueError):self.generate(p)
        self.assertEqual(FakeWriter.contexts,[])
        with self.assertRaisesRegex(ValueError,'ровно 3'):validate_draft(raw(),CV1+' '+CV2,JD1+' '+JD2,sentence_count=3)
    def test_user_motivation_is_cited_separately_and_cannot_supply_work_experience(self):
        comment='Меня интересует развитие генеративных моделей в сильной исследовательской команде.'
        draft={'ready':True,'matches':[{'text':comment,'comment_quote':comment,'vacancy_quote':JD1}],'note':''}
        result=validate_draft(draft,CV1,JD1,sentence_count=1,comments=comment)
        self.assertEqual(result['evidence'][0]['source_type'],'comment');self.assertEqual(result['evidence'][0]['resume_quote'],'')
        with self.assertRaises(ValueError):validate_draft(draft,CV1,JD1,sentence_count=1,comments='Другой комментарий пользователя.')
        bad='Меня интересует эта команда, я внедрил генеративные модели в продакшен.'
        draft['matches'][0].update(text=bad,comment_quote=bad)
        with self.assertRaisesRegex(ValueError,'опыт'):validate_draft(draft,CV1,JD1,sentence_count=1,comments=bad)
    def test_extended_motivation_and_all_invalid_claims_are_reported_for_one_repair(self):
        comment='Особенно интересны Flow Matching и математическая основа диффузионных моделей для генерации видео.'
        draft={'ready':True,'matches':[{'text':comment,'comment_quote':comment,'vacancy_quote':JD1}],'note':''}
        self.assertEqual(validate_draft(draft,CV1,JD1,comments=comment)['evidence'][0]['source_type'],'comment')
        draft['matches']=[{'text':'Хочу применять RLHF для генерации видео и развития моделей.','comment_quote':comment,'vacancy_quote':JD1}, {'text':'Меня интересует эта команда, я внедрил генеративные модели в продакшен.','comment_quote':comment,'vacancy_quote':JD1}]
        with self.assertRaises(ValueError) as raised:validate_draft(draft,CV1,JD1,comments=comment)
        self.assertIn('Предложение 1:',str(raised.exception));self.assertIn('Предложение 2:',str(raised.exception))
    def test_requested_length_supports_one_to_five_complete_sentences(self):
        texts=['Исследовал модели и проверял качество ответов на внутренних данных команды.',
               'Сравнивал результаты экспериментов и выбирал подход к обучению генеративной модели.',
               'Готовил наборы данных и проверял воспроизводимость проведённых исследовательских экспериментов.',
               'Оптимизировал вычисления и оценивал требования к ресурсам при генерации ответов.',
               'Разрабатывал инструменты для анализа ошибок и проверки качества готовых решений.']
        cv=' '.join(texts)
        for count in range(1,6):
            draft={'ready':True,'matches':[{'text':t,'resume_quote':t,'vacancy_quote':JD1} for t in texts[:count]],'note':''}
            self.assertEqual(len(validate_draft(draft,cv,JD1,sentence_count=count)['evidence']),count)
    def test_fifty_sentences_round_trip_through_endpoint_and_cache_with_paragraphs(self):
        texts=[f'В проекте {i} исследовал генеративные модели и проверял качество ответов на внутренних данных команды.' for i in range(1,51)]
        p=payload();cv=p['bundle']['resumes'][0];cv['sections'][0]['text']=' '.join(texts);cv['content_hash']=content_hash(cv);p['sentence_count']=50
        class FiftyWriter:
            calls=0
            def __init__(self,model):pass
            def generate(self,context):
                FiftyWriter.calls+=1
                assert context['sentence_count']==50
                return {'ready':True,'matches':[{'text':t,'resume_quote':t,'vacancy_quote':JD1} for t in texts],'note':''},{'input_tokens':100,'output_tokens':5000}
        def writer(body,path):return generate_cover_letter(body,self.root,writer_factory=FiftyWriter,now=NOW)
        with TestClient(create_app('fixture-token',cover_writer=writer)) as client:
            response=client.post('/cover-letter',json=p,headers={'X-Resume-Import-Token':'fixture-token'});self.assertEqual(response.status_code,200)
            result=response.json();self.assertEqual(result['sentence_count'],50);self.assertEqual(len(result['evidence']),50)
            self.assertIn(texts[-1],result['text']);self.assertGreater(result['text'].count('\n\n'),10)
            cached=client.post('/cover-letter',json=p,headers={'X-Resume-Import-Token':'fixture-token'}).json()
            self.assertEqual(cached['text'],result['text']);self.assertTrue(cached['cached']);self.assertEqual(cached['api_requests'],0)
        self.assertEqual(FiftyWriter.calls,1)
        with self.assertRaises(ValueError):validate_draft({'ready':True,'matches':[{'text':t,'resume_quote':t,'vacancy_quote':JD1} for t in texts]+[{'text':texts[0],'resume_quote':texts[0],'vacancy_quote':JD1}]},' '.join(texts),JD1)
    def test_sdk_allocates_enough_output_and_time_for_fifty_sentences(self):
        import json
        indexed={'ready':True,'matches':[{'text':CV1,'resume_passage_id':'R1','comment_passage_id':'','vacancy_passage_id':'J1'} for _ in range(50)],'note':''}
        response=SimpleNamespace(status='completed',output_text=json.dumps(indexed),usage=SimpleNamespace(input_tokens=100,output_tokens=5000))
        client=MagicMock();client.responses.create.return_value=response
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fixture-secret'}),patch('openai.OpenAI',return_value=client):
            draft,_=OpenAICoverWriter('gpt-4.1-mini').generate({'resume_text':CV1,'vacancy':{'description':JD1},'sentence_count':50})
        self.assertEqual(len(draft['matches']),50)
        args=client.responses.create.call_args.kwargs
        self.assertGreater(args['max_output_tokens'],10000);self.assertGreaterEqual(args['timeout'],120)
    def test_motivation_remains_one_source_when_it_spans_multiple_paragraphs(self):
        import json
        comment='Меня интересуют исследования генеративных моделей. '*9+'Хочу искать разумный компромисс между качеством моделей и ресурсами inference.'
        indexed={'ready':True,'matches':[{'text':'Хочу искать разумный компромисс между качеством моделей и ресурсами inference.','resume_passage_id':'','comment_passage_id':'C1','vacancy_passage_id':'J1'}],'note':''}
        response=SimpleNamespace(status='completed',output_text=json.dumps(indexed),usage=SimpleNamespace(input_tokens=100,output_tokens=100))
        client=MagicMock();client.responses.create.return_value=response
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fixture-secret'}),patch('openai.OpenAI',return_value=client):
            draft,_=OpenAICoverWriter('gpt-4.1-mini').generate({'resume_text':CV1,'vacancy':{'description':JD1},'sentence_count':1,'comments':comment})
        self.assertGreater(len(draft['matches'][0]['comment_quote']),400)
        self.assertIn('inference',draft['matches'][0]['comment_quote'])
    def test_no_quote_no_invented_technologies_no_invented_numbers(self):
        for change in [{'resume_quote':'Опыт, которого в резюме нет.'},{'text':'В МТС дообучал LLaMA 3 методом SFT на 128 GPU.'},{'text':'Использовал FSDP для распределённого обучения.'}]:
            draft=raw();draft['matches'][0].update(change)
            with self.assertRaises(ValueError):validate_draft(draft,CV1+' '+CV2,JD1+' '+JD2)
    def test_learning_and_plans_cannot_be_promoted_to_completed_experience(self):
        for quote,text in [('Планирую настроить обучение Transformer на PyTorch в новом проекте.','Настроил обучение Transformer на PyTorch в новом проекте.'),('Изучаю обучение Transformer на PyTorch в учебных лабораторных.','Обучал Transformer на PyTorch в проектах.')]:
            draft={'ready':True,'matches':[{'text':text,'resume_quote':quote,'vacancy_quote':JD2}],'note':''}
            with self.assertRaises(ValueError):validate_draft(draft,quote,JD2)
    def test_draft_only_uses_explicitly_selected_cv(self):
        p=payload();other=deepcopy(p['bundle']['resumes'][0]);other['id']='file_'+'b'*64;other['file_hash']='b'*64;other['sections'][0]['text']='Разрабатывал приложения на Swift и iOS. '*10;other['content_hash']=content_hash(other)
        p['bundle']['resumes'].append(other);p['resume_id']=other['id']
        with self.assertRaises(ValueError):self.generate(p)
        self.assertNotIn('LLaMA',FakeWriter.contexts[-1]['resume_text']);self.assertIn('Swift',FakeWriter.contexts[-1]['resume_text'])
    def test_professional_machine_learning_is_not_a_studying_qualifier(self):
        quote='Разрабатывал Machine Learning модели и оценивал качество ответов в команде МТС.'
        draft={'ready':True,'matches':[{'text':'В команде МТС разрабатывал модели и оценивал качество ответов.','resume_quote':quote,'vacancy_quote':JD1}],'note':''}
        self.assertIn('МТС',validate_draft(draft,quote,JD1)['text'])
    def test_stale_cv_snippet_and_archived_job_fail_before_api(self):
        for kind in ['stale','snippet','archived']:
            p=payload()
            if kind=='stale':p['bundle']['resumes'][0].update(source_type='hh',id='a'*38,source_url='https://hh.ru/resume/'+'a'*38);p['resume_id']='a'*38
            else:p['vacancy'].update({'description_quality':'snippet'} if kind=='snippet' else {'archived':True})
            with self.assertRaises(ValueError):self.generate(p)
        self.assertEqual(FakeWriter.contexts,[])
    def test_endpoint_requires_pairing_token_and_does_not_expose_secrets(self):
        def writer(p,path):return self.generate(p)
        token='fixture-local-token'
        with TestClient(create_app(token,cover_writer=writer)) as client:
            self.assertEqual(client.post('/cover-letter',json=payload()).status_code,401)
            r=client.post('/cover-letter',json=payload(),headers={'X-Resume-Import-Token':token});self.assertEqual(r.status_code,200)
            self.assertNotIn(token,r.text);self.assertEqual(r.json()['vacancy_id'],'hh_1')
    def test_sdk_uses_structured_output_selected_sources_and_server_key(self):
        import json
        indexed={'ready':True,'matches':[{'text':CV1,'resume_passage_id':'R1','vacancy_passage_id':'J1'}],'note':''}
        response=SimpleNamespace(status='completed',output_text=json.dumps(indexed),usage=SimpleNamespace(input_tokens=100,output_tokens=150))
        client=MagicMock();client.responses.create.return_value=response
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fixture-secret'}),patch('openai.OpenAI',return_value=client) as constructor:
            writer=OpenAICoverWriter('gpt-4.1-mini');draft,_=writer.generate({'resume_text':CV1,'vacancy':{'description':JD1}})
            args=client.responses.create.call_args.kwargs
            self.assertFalse(args['store']);self.assertEqual(args['model'],'gpt-4.1-mini');self.assertTrue(args['text']['format']['strict'])
            self.assertEqual(args['text']['format']['schema'],SCHEMA);self.assertEqual(constructor.call_args.kwargs['api_key'],'fixture-secret')
            self.assertIn(CV1,args['input'][1]['content']);self.assertNotIn('fixture-secret',str(args['input']))
            self.assertEqual(draft['matches'][0]['resume_quote'],CV1)
            self.assertEqual(draft['matches'][0]['vacancy_quote'],JD1)
            indexed['matches'][0]['resume_passage_id']='R9999';response.output_text=json.dumps(indexed)
            with self.assertRaisesRegex(ValueError,'неизвестный фрагмент'):writer.generate({'resume_text':CV1,'vacancy':{'description':JD1}})
    def test_numbered_passages_preserve_sources_and_cover_long_documents(self):
        source=' '.join(f'Факт{i}: исследовал модели и сравнивал качество обучения.' for i in range(200))
        passages=source_passages(source,'R')
        self.assertGreater(len(passages),2)
        self.assertTrue(all(15<=len(q)<=400 and q in source for q in passages.values()))
        self.assertTrue(all(f'Факт{i}:' in ' '.join(passages.values()) for i in range(200)))
        fact='- Реализовал на PyTorch модель Transformer Decoder на основе архитектуры GPT-2, посимвольную и BPE-токенизацию, полный цикл обучения и авторегрессионную генерацию.'
        self.assertIn(fact,source_passages('Заголовок и предыдущий контекст. '*15+fact+' Следующий факт.','R').values())
    def test_one_repair_reports_actual_usage_and_never_accepts_unconfirmed_technology(self):
        import json
        def response(text):return SimpleNamespace(status='completed',output_text=json.dumps({'ready':True,'matches':[{'text':text,'resume_passage_id':'R1','vacancy_passage_id':'J1'}],'note':''}),usage=SimpleNamespace(input_tokens=100,output_tokens=50))
        client=MagicMock();client.responses.create.side_effect=[response('В МТС применял FSDP для обучения моделей на внутренних данных.'),response(CV1)]
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fixture-secret'}),patch('openai.OpenAI',return_value=client):
            draft,usage=OpenAICoverWriter('gpt-4.1-mini').generate({'resume_text':CV1,'vacancy':{'description':JD1}})
            self.assertEqual(draft['matches'][0]['text'],CV1);self.assertEqual(usage,{'api_requests':2,'input_tokens':200,'output_tokens':100})
            self.assertIn('FSDP',client.responses.create.call_args.kwargs['input'][1]['content'])
        client.responses.create.side_effect=None;client.responses.create.return_value=response('В МТС применял FSDP для обучения моделей на внутренних данных.');client.responses.create.reset_mock()
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fixture-secret'}),patch('openai.OpenAI',return_value=client):
            with self.assertRaisesRegex(ValueError,'FSDP'):OpenAICoverWriter('gpt-4.1-mini').generate({'resume_text':CV1,'vacancy':{'description':JD1}})
        self.assertEqual(client.responses.create.call_count,2)
    def test_candidate_project_and_github_repo_can_ground_experience_and_close_gaps(self):
        project='В открытом самостоятельном проекте https://github.com/vlad/flow-matching-lab реализовал Flow Matching на PyTorch и провел benchmark.'
        jd_gap='Требуется знание современных генеративных моделей, включая Flow Matching.'
        text='В самостоятельном проекте https://github.com/vlad/flow-matching-lab реализовал Flow Matching на PyTorch.'
        draft={'ready':True,'matches':[{'text':text,'project_quote':project,'vacancy_quote':jd_gap}],'note':''}
        result=validate_draft(draft,CV1,jd_gap,sentence_count=1,projects=project)
        self.assertEqual(result['evidence'][0]['source_type'],'project')
        self.assertEqual(result['evidence'][0]['project_quote'],project)
        self.assertIn('https://github.com/vlad/flow-matching-lab',result['text'])
    def test_foreign_or_invented_url_in_project_draft_is_rejected(self):
        project='В самостоятельном проекте https://github.com/vlad/flow-matching-lab реализовал Flow Matching на PyTorch.'
        jd_gap='Требуется знание Flow Matching.'
        bad_text='В самостоятельном проекте https://github.com/vlad/flow-matching-lab реализовал Flow Matching на PyTorch https://external.site.'
        draft={'ready':True,'matches':[{'text':bad_text,'project_quote':project,'vacancy_quote':jd_gap}],'note':''}
        with self.assertRaises(ValueError):validate_draft(draft,CV1,jd_gap,sentence_count=1,projects=project)
        invented_repo='В самостоятельном проекте https://github.com/other/invented-repo реализовал Flow Matching на PyTorch.'
        draft={'ready':True,'matches':[{'text':invented_repo,'project_quote':project,'vacancy_quote':jd_gap}],'note':''}
        with self.assertRaises(ValueError):validate_draft(draft,CV1,jd_gap,sentence_count=1,projects=project)

if __name__=='__main__':unittest.main()
