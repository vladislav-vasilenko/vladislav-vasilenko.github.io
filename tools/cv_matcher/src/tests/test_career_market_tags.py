import unittest
from src.career_analytics import classify,TAXONOMY

class CareerMarketTagsTests(unittest.TestCase):
 def tags(self,**d):return classify(d)['tags']
 def test_industry_tags_preserve_ml_specialization_and_show_evidence(self):
  r=classify({'title':'Research Engineer','description':'PyTorch training for autonomous driving. Sensor fusion, LiDAR and cameras.'})
  self.assertEqual(r['primary'],'research');self.assertTrue({'automotive','sensors'}<=set(r['tags']))
  self.assertTrue(any(e['category']=='sensors' and e['basis'] and e['source']=='job_text' for e in r['evidence']))
 def test_drones_are_not_automatically_defense_or_automotive(self):
  for title in ('Инженер БПЛА','UAV software engineer','Разработчик дронов','PX4 / ArduPilot инженер'):
   tags=self.tags(title=title);self.assertIn('drones',tags);self.assertNotIn('defense',tags);self.assertNotIn('government',tags);self.assertNotIn('automotive',tags)
 def test_bureau1440_is_employer_evidence_not_defense_assertion(self):
  r=classify({'title':'Python developer','company':'БЮРО 1440'})
  self.assertTrue({'space','backend'}<=set(r['tags']));self.assertNotIn('bureau1440',r['tags']);self.assertEqual(r['primary'],'space');self.assertNotIn('defense',r['tags']);self.assertNotIn('government',r['tags'])
  self.assertTrue(any(e['category']=='space' and e['source']=='company' for e in r['evidence']))
  self.assertNotIn('bureau1440',[key for key,_,_ in TAXONOMY])
  self.assertNotIn('space',self.tags(title='Python developer',description='Монитор 1440 пикселей.'))
  self.assertNotIn('space',self.tags(title='Python developer',company='Bureau 14401'))
  self.assertIn('space',self.tags(title='Embedded engineer',company='Bureau 1440'))
  self.assertEqual(classify({'title':'LLM Pretraining Engineer','company':'Бюро 1440'})['primary'],'pretraining')
 def test_direct_defense_and_government_are_mentions_and_negation_is_respected(self):
  tags=self.tags(title='Инженер',description='Работа с гособоронзаказом (ГОЗ). Проекты военно-промышленного комплекса.')
  self.assertTrue({'defense','government'}<=set(tags))
  self.assertIn('government',self.tags(description='Сопровождение государственных контрактов и госзакупок.'))
  for description in ('Военный билет, ДМС, бронь от мобилизации.','Работаем в гражданском секторе. Не работаем с ГОЗ.','Мы не связаны с ОПК.'):
   tags=self.tags(description=description);self.assertNotIn('defense',tags);self.assertNotIn('government',tags)
 def test_possible_employer_link_is_explicit_and_does_not_claim_contract(self):
  r=classify({'title':'Backend engineer','company':'Концерн Калашников'})
  e=next(e for e in r['evidence'] if e['category']=='defense');self.assertIn('Возможная связь',e['basis']);self.assertNotIn('government',r['tags'])
 def test_car_benefits_and_gnss_use_do_not_assert_automotive_or_satellite_job(self):
  self.assertNotIn('automotive',self.tags(description='Условия: парковка автомобиля, скидки на страхование автомобиля.'))
  self.assertNotIn('space',self.tags(title='Инженер БПЛА',description='Работа с GPS и спутниковой навигацией.'))
 def test_title_roles_do_not_match_generic_skills_in_every_vacancy(self):
  tags=self.tags(title='Auto QA Python (Hadoop, Spark)',description='Python, bare metal и Kubernetes.')
  self.assertIn('qa',tags);self.assertNotIn('apple',tags)
  self.assertIn('data_engineering',self.tags(title='Lead data platform developer',description='Python FastAPI'))
  self.assertNotIn('backend',self.tags(title='Data Analyst',description='Будет плюсом опыт Python.'))
 def test_domain_names_are_unique_and_bad_cta_is_left_unclassified(self):
  keys=[r[0] for r in TAXONOMY];self.assertEqual(len(keys),len(set(keys)));self.assertEqual(self.tags(title='Откликнуться'),['other'])
