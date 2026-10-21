"""Facts from the owner are citeable even before CV is updated; zero real API calls."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from src.recruiter_answers import draft_answer,SYSTEM
from src.tests import test_workflow as fixtures
from src.candidate_facts import save,read,answer_context
from src.external_prompt import build_prompt

class GroundingTests(unittest.TestCase):
 def test_new_practice_and_diffusers_are_citeable_user_sources_and_invalidate_cache(self):
  with tempfile.TemporaryDirectory() as temp:
   context={'resume_id':'cv','resume_text':'Самостоятельно изучаю диффузионные модели и Flow Matching.','goal':'Research Engineer','vacancy':{'title':'Research','description':'Diffusers experience'},'user_facts':[{'text':'В исследовательском стенде воспроизводил Stable Diffusion, применял LoRA и запускал SDXL.'}],'preferences':'Использовал Diffusers: pipeline, scheduler и подключение LoRA.'}
   client=MagicMock();result={'answer':'В стенде воспроизводил Stable Diffusion, подключал LoRA и использовал Diffusers.','needs_user':False,'missing':[],'evidence':['U1']}
   client.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps(result),usage=SimpleNamespace(input_tokens=100,output_tokens=50))
   a=draft_answer(context,'Опыт Diffusers?','terra',temp,client_factory=lambda:client)
   self.assertEqual(a['evidence'][0]['id'],'U1');self.assertIn('Stable Diffusion',a['evidence'][0]['quote'])
   data=json.loads(client.responses.create.call_args.kwargs['input'][1]['content']);joined=' '.join(data['user_statements'].values());self.assertIn('scheduler',joined);self.assertIn('SDXL',joined)
   self.assertTrue(draft_answer(context,'Опыт Diffusers?','terra',temp,client_factory=lambda:client)['cached'])
   context['user_facts'].append({'text':'Новый подтверждённый факт о дополнительной исследовательской практике.'})
   self.assertFalse(draft_answer(context,'Опыт Diffusers?','terra',temp,client_factory=lambda:client)['cached']);self.assertEqual(client.responses.create.call_count,2)
   self.assertIn('Неизвестно НЕ означает отсутствует',SYSTEM);self.assertIn('не заменяй их перечислением курсов',SYSTEM)
 def test_fact_versions_separate_from_cv_and_no_api_package_has_same_facts(self):
  f=fixtures.WorkflowTests();f.setUp();self.addCleanup(f.doCleanups);before=f.store.get(f.id)['context']['resume_hash']
  save(f.store,f.cv['id'],'diffusers','Использовал Diffusers для pipeline и LoRA.')
  save(f.store,f.cv['id'],'diffusers','Использовал Diffusers для pipeline, scheduler и LoRA.')
  facts=read(f.store,f.cv['id']);self.assertEqual(len(facts),1);self.assertIn('scheduler',facts[0]['text'])
  context=answer_context(f.store,f.store.get(f.id)['context']);prompt=build_prompt(context,'answer',question='Как использовали Diffusers?')
  self.assertIn('scheduler',prompt);self.assertIn('additional_user_facts',prompt);self.assertEqual(f.store.get(f.id)['context']['resume_hash'],before)
  with f.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM candidate_facts').fetchone()[0],2)
 def test_unknown_user_source_citation_is_still_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   context={'resume_text':'Обучал Transformer на PyTorch в рабочем проекте.','vacancy':{'title':'Research','description':'Diffusers'},'user_facts':[]}
   client=MagicMock();client.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps({'answer':'Факт','needs_user':False,'missing':[],'evidence':['U99']}),usage=SimpleNamespace(input_tokens=1,output_tokens=1))
   with self.assertRaises(ValueError):draft_answer(context,'Опыт?','terra',temp,client_factory=lambda:client)
