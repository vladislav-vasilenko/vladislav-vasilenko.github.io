import unittest
from src.vacancy_terms import mentions

class VacancyTermsTests(unittest.TestCase):
 def test_term_mentions_use_selected_cv_aliases_and_boundaries_without_claiming_skill(self):
  cv={'title':'Research Engineer','sections':[{'key':'experience','text':'Изучаю PyTorch, torch.compile, квантизацию. Профессиональный опыт Triton не подтверждён.'}]}
  rows={r['label']:r for r in mentions(cv,'Python, PyTorch, torch.compile, Triton, vLLM, квантование и квантизация, DeepSpeed, CUDA.')}
  self.assertTrue(rows['torch.compile']['in_cv']);self.assertFalse(rows['Python']['in_cv']);self.assertFalse(rows['vLLM']['in_cv']);self.assertTrue(rows['quantization']['in_cv']);self.assertIn('не подтверждён',rows['Triton']['quote']);self.assertNotIn('fit',rows['Triton'])
 def test_contacts_do_not_count_as_cv_skill_evidence(self):
  cv={'sections':[{'key':'contacts','text':'CUDA PyTorch'},{'key':'experience','text':'Python development'}]}
  rows={r['label']:r for r in mentions(cv,'CUDA and Python')};self.assertFalse(rows['CUDA']['in_cv']);self.assertTrue(rows['Python']['in_cv'])
