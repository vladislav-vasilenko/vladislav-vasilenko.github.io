import json,unittest
from unittest.mock import patch,Mock
from src.tests import test_career_agent as fixtures
from src.tests.test_recruiter import Operator,update
from src.workflow_bot import WorkflowBot
from src.application_workflow import packed,hashed
from src.telegram_analysis import card

class DetailedReviewTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  await fixtures.CareerAgentTests.asyncSetUp(self)
  self.bot=WorkflowBot(self.store,Operator(),42);self.ref='detail-fixture'
  self.store.setting('recommendation:'+self.ref,packed({'resume_id':self.f.cv['id'],'resume_hash':self.f.cv['content_hash'],'vacancy_id':self.f.jd['id'],'vacancy_hash':hashed(self.f.jd['description']),'goal':'Generative models'}))
 def counts(self):
  with self.store.connect() as db:return tuple(db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('applications','browser_commands','application_preparations'))
 async def test_direct_button_opens_modes_without_model_application_or_browser_job(self):
  before=self.counts()
  with patch('src.skill_analysis.analyze',side_effect=AssertionError('No model on navigation')):
   await self.bot.update(update(callback='w:rreview:'+self.ref))
  text,rows=self.bot.operator.messages[-1];self.assertIn('Подробный разбор',text);self.assertIn('один платный запрос',text)
  self.assertIn('w:rapi:'+self.ref,str(rows));self.assertIn('w:roff:'+self.ref,str(rows));self.assertEqual(self.counts(),before)
 async def test_detailed_pages_include_job_cv_evidence_and_next_action(self):
  analysis={'metrics':{'overall':{'percent':50}},'requirements':[{'requirement':'Requirement '+str(i),'status':'partial','explanation':'Связанный опыт','job_quote':'Точная цитата вакансии','resume_quotes':['Факт из CV'],'action':'Уточнить масштаб'} for i in range(7)]}
  await card(self.bot,self.ref,analysis);text,rows=self.bot.operator.messages[-1]
  self.assertIn('Факт из CV',text);self.assertIn('Точная цитата',text);self.assertIn('Уточнить масштаб',text);self.assertIn('1 из 4',text);self.assertLess(len(text),3900);self.assertIn('w:rpage:',str(rows))
 async def test_foreign_owner_and_stale_recommendation_cannot_trigger_model(self):
  model=Mock()
  with patch('src.skill_analysis.analyze',model):
   await self.bot.update(update(callback='w:rapi:'+self.ref,owner=99))
   data=json.loads(self.store.setting('recommendation:'+self.ref));data['resume_hash']='stale';self.store.setting('recommendation:'+self.ref,packed(data))
   await self.bot.update(update(callback='w:rapi:'+self.ref))
  model.assert_not_called();self.assertIn('изменились',self.bot.operator.messages[-1][0])
 async def test_same_api_button_does_not_repeat_ambiguous_paid_request(self):
  model=Mock(side_effect=ValueError('fixture model timeout'));before=self.counts()
  with patch('src.skill_analysis.analyze',model):
   await self.bot.update(update(callback='w:rapi:'+self.ref));await self.bot.update(update(callback='w:rapi:'+self.ref))
  self.assertEqual(model.call_count,1);self.assertEqual(self.counts(),before)
