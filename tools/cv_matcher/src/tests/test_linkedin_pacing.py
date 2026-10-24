import json
import unittest
from unittest.mock import patch
from src import linkedin_pacing as pace

class PacingTests(unittest.TestCase):
 def test_each_batch_and_each_delay_are_selected_once_then_survive_serialization(self):
  targets=iter([8,12,9]);delays=iter([3100,7900]*30)
  def choose(low,high):return next(targets) if (low,high)==(8,12) else next(delays)
  config={}
  with patch.object(pace,'choose',side_effect=choose) as random:
   self.assertEqual(pace.state(config)['target'],8)
   sizes=[];observed_delays=[];now=1000
   for index in range(20):
    now+=100;before=config['read_pacing']['done'];pace.complete(config,'unit-'+str(index),now=now)
    observed_delays.append(config['read_pacing']['last_delay_ms'])
    if config['read_pacing']['done']==0:sizes.append(config['read_pacing']['last_batch_size'])
    calls=random.call_count;duplicate=pace.complete(config,'unit-'+str(index),now=now)
    self.assertEqual(random.call_count,calls)
    self.assertEqual(config['read_pacing']['done'],0 if index in (7,19) else before+1)
    config=json.loads(json.dumps(config));self.assertEqual(pace.status(config,now=now),duplicate)
   self.assertEqual(sizes,[8,12]);self.assertEqual(config['read_pacing']['target'],9)
   self.assertEqual(set(observed_delays),{3100,7900});self.assertEqual(pace.status(config,now=now)['wait_ms'],60000)
   self.assertEqual(pace.status(config,now=now+60)['wait_ms'],0)
 def test_invalid_ranges_fail_before_scheduling(self):
  for values in ({'batch_min':13,'batch_max':8},{'batch_min':True},{'delay_min_seconds':9,'delay_max_seconds':3},{'batch_pause_seconds':0},{'delay_max_seconds':float('nan')}):
   with self.assertRaises(ValueError):pace.options(values)
