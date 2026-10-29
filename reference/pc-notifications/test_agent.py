"""Safety/behavior tests without hardware writes."""
import datetime,importlib.util,pathlib,unittest,unittest.mock as mock
spec=importlib.util.spec_from_file_location('agent',pathlib.Path(__file__).with_name('agent.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class SafetyTests(unittest.TestCase):
 def test_night_wrap(self):
  c={'night_override':False,'night_schedule_enabled':True,'night_start':22,'night_end':7}
  for hour,want in [(0,True),(6,True),(7,False),(21,False),(22,True)]:
   self.assertEqual(a.night(c,datetime.datetime(2026,10,28,hour)),want)
 def test_payload_validation(self):
  for bad in [{'duration':100},{'duration':True},{'pixels':['#ffffff']},{'color':'$(reboot)'},{'effect':'exec'},{'brightness':-1}]:
   with self.assertRaises(ValueError):a.validate_effect(bad)
 def test_single_worker(self):
  a.BUSY=True
  with mock.patch.object(a,'cfg',return_value={'effects_enabled':True}):
   self.assertEqual(a.submit({'effect':'static'}),(False,'ring busy; event dropped'))
  a.BUSY=False
 def test_frames_bounds_and_individual_pixels(self):
  for effect in a.EFFECTS:
   f=a.frame(effect,['#FF0000','#00FF00','#0000FF','#FFFFFF','#000000','#8B5CF6'],.25,.4)
   self.assertEqual(len(f),6)
   for color in f:
    self.assertRegex(color,'^#[0-9A-F]{6}$')
    self.assertTrue(all(int(color[i:i+2],16)<=64 for i in (1,3,5)))
 def test_no_retry_after_failed_write(self):
  a.CANCEL.clear();a.EXIT.clear()
  c={'station_url':'http://unused','brightness_percent':25,'effects_enabled':True,'night_override':False,'night_schedule_enabled':False,'night_start':22,'night_end':7}
  calls=[]
  def request(path,*args,**kwargs):
   calls.append(path)
   if path=='device':return {'id':'yandexmini','led_count':6,'capabilities':{'led.ring.rgb':True}}
   if path=='plugins':return []
   raise TimeoutError('offline')
  with mock.patch.object(a,'cfg',return_value=c),mock.patch.object(a,'station',side_effect=request):
   with self.assertRaises(TimeoutError):a.run_frames({'effect':'static','pixels':['#8B5CF6']*6,'brightness':25,'duration':.2})
  self.assertEqual(calls,['device','plugins','led'])
if __name__=='__main__':unittest.main()
