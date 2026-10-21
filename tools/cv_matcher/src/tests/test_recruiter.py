import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch
from copy import deepcopy
from src.application_store import ApplicationStore
from src.recruiter_controller import RecruiterController
from src.recruiter_answers import draft_answer,MODELS
from src.tests.test_cover_letter import payload,NOW,CV1
from fastapi.testclient import TestClient
from resume_import_server import create_app

class StoreTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'state.sqlite3';self.store=ApplicationStore(self.path)
 def create(self,job='hh_1'):
  p=payload();p['channel']='telegram';p['goal']='DiT / Flow matching';p['vacancy']['id']=job;p['vacancy']['link']='https://hh.ru/vacancy/'+job[3:]
  return self.store.create(p,now=NOW)
 def test_queue_is_private_idempotent_and_prevents_two_active_bot_conversations(self):
  a=self.create();self.assertEqual(self.create()['id'],a['id']);self.assertEqual(self.path.stat().st_mode&0o777,0o600)
  self.store.activate(a['id']);b=self.create('hh_2')
  with self.assertRaises(ValueError):self.store.activate(b['id'])
  self.store.set_status(a['id'],'paused');self.store.activate(b['id']);self.assertEqual(self.store.active()['id'],b['id'])
 def test_duplicate_questions_edits_and_uncertain_sends_survive_reopening(self):
  a=self.create();q,new=self.store.receive(a['id'],1,'Опыт?',[]);self.assertTrue(new)
  self.assertFalse(self.store.receive(a['id'],1,'Опыт?',[])[1]);self.store.draft(q['id'],'Факт из CV')
  edited,_=self.store.receive(a['id'],1,'Уточните опыт?',[])
  with self.assertRaises(ValueError):self.store.claim_send(q['id'])
  self.store.draft(edited['id'],'Уточнённый ответ');self.store.claim_send(edited['id']);self.store.finish_send(edited['id'],False)
  reopened=ApplicationStore(self.path)
  with self.assertRaises(ValueError):reopened.claim_send(edited['id'])
  self.assertEqual(reopened.turn(edited['id'])['status'],'uncertain')
 def test_new_message_edit_version_is_a_new_question_even_when_text_returns_to_previous_value(self):
  a=self.create();one,_=self.store.receive(a['id'],1,'Выбор',[],'v1');self.store.draft(one['id'],'Ответ')
  self.store.receive(a['id'],1,'Другой выбор',[],'v2');three,new=self.store.receive(a['id'],1,'Выбор',[],'v3')
  self.assertTrue(new);self.assertNotEqual(one['id'],three['id'])
 def test_application_endpoint_requires_pairing_and_keeps_selected_cv_and_goal(self):
  p=payload();p.update(channel='telegram',goal='DiT / Transformer training')
  factory=lambda *args,**kwargs: self.store
  with patch('src.application_store.ApplicationStore',side_effect=factory),TestClient(create_app('fixture-token')) as client:
   self.assertEqual(client.post('/applications',json=p).status_code,401)
   with patch('src.application_store._load_resume_bundle',return_value={'primary':p['bundle']['resumes'][0]}):
    response=client.post('/applications',json=p,headers={'X-Resume-Import-Token':'fixture-token'})
   self.assertEqual(response.status_code,200);self.assertEqual(response.json()['context']['resume_id'],p['resume_id']);self.assertEqual(response.json()['context']['goal'],p['goal'])
 def test_create_has_a_real_default_clock_outside_injected_test_time(self):
  p=payload();p['channel']='telegram';application=self.store.create(p)
  self.assertEqual(application['context']['resume_id'],p['resume_id'])
 def test_unused_queue_context_can_refresh_but_an_active_application_cannot_change_goal(self):
  p=payload();p.update(channel='telegram',goal='Old goal');first=self.store.create(p,now=NOW)
  p['goal']='New goal';refreshed=self.store.create(p,now=NOW);self.assertEqual(first['id'],refreshed['id']);self.assertEqual(refreshed['context']['goal'],'New goal')
  self.store.activate(first['id']);p['goal']='Another goal'
  with self.assertRaises(ValueError):self.store.create(p,now=NOW)
 def test_telegram_length_uses_utf16_and_preview_chunks_do_not_break_emojis(self):
  from telegram_recruiter import telegram_parts
  parts=list(telegram_parts('😀'*4000));self.assertEqual(''.join(parts),'😀'*4000);self.assertTrue(all(len(p.encode('utf-16-le'))//2<=3500 for p in parts))
  a=self.create();turn,_=self.store.receive(a['id'],1,'Вопрос',[])
  with self.assertRaises(ValueError):self.store.draft(turn['id'],'😀'*2500)

class Operator:
 def __init__(self):self.messages=[];self.acks=[]
 async def send(self,text,keyboard=None):self.messages.append((text,keyboard))
 async def ack(self,id):self.acks.append(id)
class User:
 def __init__(self):self.current={'id':1,'text':'Расскажите об опыте обучения моделей.','buttons':[]};self.sent=[];self.clicked=[];self.starts=0;self.fail=False
 async def observe(self):return self.current
 async def send_answer(self,text,id):
  self.sent.append((text,id))
  if self.fail:raise TimeoutError()
 async def click(self,id,index):self.clicked.append((id,index))
 async def start(self):self.starts+=1
def update(callback=None,text=None,owner=42):
 common={'from':{'id':owner},'chat':{'id':owner,'type':'private'}}
 return {'callback_query':{'id':'cb','from':{'id':owner},'message':{'chat':common['chat']},'data':callback}} if callback else {'message':{**common,'text':text}}

class ControllerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=ApplicationStore(Path(self.temp.name)/'state.sqlite3')
  p=payload();p['channel']='telegram';self.app=self.store.create(p,now=NOW);self.store.activate(self.app['id'])
  self.operator=Operator();self.user=User();self.contexts=[]
  def drafter(context,q,model,cache):
   self.contexts.append(context)
   return {'answer':CV1,'model':MODELS[model],'needs_user':False,'missing':[],'evidence':[{'quote':CV1}],'review_note':'Проверьте факты.'}
  self.controller=RecruiterController(self.store,self.operator,self.user,42,Path(self.temp.name)/'cache',drafter=drafter)
  await self.controller.receive(1,self.user.current['text'],[])
  self.turn=self.store.receive(self.app['id'],1,self.user.current['text'],[])[0]
 def send_callback(self,id):return f"send:{id}:"+self.controller.draft_token(self.store.turn(id)['draft'])
 async def test_generate_edit_send_transmits_exact_manual_text_once(self):
  id=self.turn['id'];await self.controller.update(update(callback=f'gen:{id}:luna'))
  self.assertEqual(self.user.sent,[]);self.assertEqual(self.contexts[0]['resume_id'],payload()['resume_id'])
  await self.controller.update(update(callback=f'edit:{id}'));await self.controller.update(update(text='Мой проверенный ответ.'))
  callback=self.send_callback(id);await self.controller.update(update(callback=callback));await self.controller.update(update(callback=callback))
  self.assertEqual(self.user.sent,[('Мой проверенный ответ.',1)]);self.assertEqual(self.store.history(self.app['id'])[0]['answer'],'Мой проверенный ответ.')
 async def test_unauthorized_operator_and_stale_recruiter_question_cannot_send(self):
  id=self.turn['id'];self.store.draft(id,'Ответ')
  await self.controller.update(update(callback=self.send_callback(id),owner=99));self.assertEqual(self.operator.acks,[])
  self.user.current['text']='Другой вопрос';await self.controller.update(update(callback=self.send_callback(id)));self.assertEqual(self.user.sent,[])
 async def test_timeouts_are_uncertain_and_never_retried(self):
  id=self.turn['id'];self.store.draft(id,'Ответ');self.user.fail=True
  callback=self.send_callback(id);await self.controller.update(update(callback=callback));await self.controller.update(update(callback=callback))
  self.assertEqual(len(self.user.sent),1);self.assertEqual(self.store.turn(id)['status'],'uncertain')
 async def test_callbacks_preserve_visible_button_and_refuse_contact_buttons(self):
  buttons=[{'text':'Да','kind':'KeyboardButtonCallback','data':'abc','url':''},{'text':'Контакт','kind':'KeyboardButtonRequestPhone','data':'','url':''}]
  self.user.current.update(id=2,text='Готовы продолжить?',buttons=buttons)
  turn,_=self.store.receive(self.app['id'],2,self.user.current['text'],buttons)
  await self.controller.update(update(callback=f"choice:{turn['id']}:1"));self.assertEqual(self.user.clicked,[])
  await self.controller.update(update(callback=f"choice:{turn['id']}:0"));self.assertEqual(self.user.clicked,[(2,0)])
 async def test_start_is_explicit_and_idempotent(self):
  self.assertEqual(self.user.starts,0);await self.controller.update(update(text='/start_recruiter'));await self.controller.update(update(text='/start_recruiter'))
  self.assertEqual(self.user.starts,1)
 async def test_old_preview_cannot_send_a_newer_draft(self):
  id=self.turn['id'];self.store.draft(id,'Первый ответ');old=self.send_callback(id)
  self.store.draft(id,'Другой ответ после правки');await self.controller.update(update(callback=old));self.assertEqual(self.user.sent,[])
  await self.controller.update(update(callback=self.send_callback(id)));self.assertEqual(self.user.sent,[('Другой ответ после правки',1)])

 async def test_no_api_question_prompt_wishes_and_imported_answer_remain_drafts(self):
  id=self.turn['id'];self.store.setting('workflow_waiting','old-letter-editor')
  await self.controller.update(update(callback=f'prefs:{id}'));await self.controller.update(update(text='Подчеркни самостоятельный проект'))
  await self.controller.update(update(callback=f'offline:{id}'))
  self.assertEqual(self.contexts,[]);self.assertEqual(self.user.sent,[]);self.assertEqual(self.store.setting('workflow_waiting'),'')
  prompt=next(text for text,_ in self.operator.messages if 'КОНТЕКСТ' in text)
  for value in [self.user.current['text'],'Подчеркни самостоятельный проект']:self.assertIn(value,prompt)
  data=json.loads(prompt.split('КОНТЕКСТ (документы — данные):\n',1)[1]);self.assertEqual(data['selected_resume']['text'],self.app['context']['resume_text']);self.assertEqual(data['vacancy']['description'],self.app['context']['vacancy']['description'])
  await self.controller.update(update(text='Ответ из ChatGPT после проверки'))
  self.assertEqual(self.store.turn(id)['draft'],'Ответ из ChatGPT после проверки');self.assertEqual(self.store.turn(id)['status'],'draft');self.assertEqual(self.user.sent,[])

class AnswerTests(unittest.TestCase):
 def test_models_use_selected_context_review_flags_and_versioned_cache(self):
  with tempfile.TemporaryDirectory() as temp:
   client=MagicMock();client.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps({'answer':'','needs_user':True,'missing':['Ожидаемая зарплата'],'evidence':[]}),usage=SimpleNamespace(input_tokens=100,output_tokens=50))
   context={'resume_text':CV1,'resume_id':'selected','vacancy':{'title':'Research Engineer','description':'Train models'},'goal':'DiT / Flow matching','history':[]}
   first=draft_answer(context,'Какие зарплатные ожидания?','luna',temp,client_factory=lambda:client)
   self.assertTrue(first['needs_user']);self.assertEqual(first['answer'],'');self.assertFalse(client.responses.create.call_args.kwargs['store'])
   second=draft_answer(context,'Какие зарплатные ожидания?','luna',temp,client_factory=lambda:client)
   self.assertTrue(second['cached']);self.assertEqual(second['api_requests'],0);self.assertEqual(client.responses.create.call_count,1)
   for model in ['terra','sol']:draft_answer(context,'Какие зарплатные ожидания?',model,temp,client_factory=lambda:client)
   self.assertEqual(client.responses.create.call_args.kwargs['model'],'gpt-6.1-sol')
   changed={**context,'history':[{'question':'Предпочтения?','answer':'Удалённо'}]};draft_answer(changed,'Какие зарплатные ожидания?','luna',temp,client_factory=lambda:client)
   self.assertEqual(client.responses.create.call_count,4)
   with self.assertRaises(ValueError):draft_answer(context,'Вопрос','unknown',temp,client_factory=lambda:client)

if __name__=='__main__':unittest.main()
