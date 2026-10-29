import asyncio,copy,importlib.util,json,tempfile,types,unittest
from pathlib import Path
from voice.catalog import Catalog
p=Path(__file__).resolve().parents[1]/'integrations/homeassistant/config/custom_components/alice_commander_bridge/inventory.py'
spec=importlib.util.spec_from_file_location('scenario_inventory',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def definition(device='mini',marker='Ничего не делай'):
 return {'triggers':[{'trigger':{'type':'scenario.trigger.voice','value':'открой терминал'}}], 'steps':[{'parameters':{'items':[{'value':{'id':device,'capabilities':[{'type':'devices.capabilities.quasar.server_action','state':{'instance':'text_action','value':marker}}]}}]}}]}
class InventorySafety(unittest.IsolatedAsyncioTestCase):
 async def make(self,raw,extra=None):
  class Response:
   async def json(self):return {'scenario':raw}
  class Session:
   def __init__(self):self.gets=[]
   async def get(self,url):self.gets.append(url);return Response()
  class Quasar:
   def __init__(self):self.session=Session();self.scenarios=[{'id':'scenario-1','name':'компьютер терминал'}]+(extra or [])
   async def load_scenarios(self):pass
  quasar=Quasar();entity=types.SimpleNamespace(entity_id='media_player.mini',quasar=quasar,device={'id':'mini'})
  hass=types.SimpleNamespace(data={'yandex_station':{'speakers':{'mini':{'entity':entity}}}})
  inventory=module.Inventory(hass,{'Компьютер Терминал'},'media_player.mini');await inventory.refresh();return inventory,quasar
 async def test_case_normalization_and_exact_device_marker(self):
  inventory,quasar=await self.make(definition());self.assertEqual(inventory.rows[0]['name'],'Компьютер Терминал');self.assertTrue(inventory.rows[0]['usable'])
  await inventory.refresh();self.assertEqual(len(quasar.session.gets),1)
 async def test_wrong_target_or_extra_action_not_usable(self):
  for raw in (definition('lamp'),definition(marker='запусти что угодно')):
   inventory,_=await self.make(raw);self.assertFalse(inventory.rows[0]['usable'])
  raw=definition();raw['steps'][0]['parameters']['items'].append({'value':{'id':'lamp','capabilities':[{'type':'devices.capabilities.on_off','state':{'instance':'on','value':True}}]}})
  inventory,_=await self.make(raw);self.assertFalse(inventory.rows[0]['usable'])
 async def test_duplicate_names_not_bound(self):
  inventory,_=await self.make(definition(),[{'id':'scenario-2','name':'Компьютер Терминал'}]);self.assertTrue(all(not r['usable'] for r in inventory.rows))

class CatalogSafety(unittest.TestCase):
 def test_created_event_and_physical_are_distinct(self):
  with tempfile.TemporaryDirectory() as temp:
   data=Path(temp);catalog=Catalog(data);row={'scenario_id':'sid','name':'Компьютер Терминал','entity_id':'media_player.mini','usable':True,'phrase':'открой терминал','error':None}
   catalog.inventory([row]);self.assertTrue(catalog.rows['terminal.open']['scenario_created']);self.assertFalse(catalog.rows['terminal.open']['event_received'])
   catalog.event('terminal.open','hash','sid');catalog.result('terminal.open','hash',{'ok':True,'result':{'output':'private output'}})
   self.assertFalse(catalog.rows['terminal.open']['physical_confirmed']);self.assertNotIn('private output',(data/'commands.json').read_text())
   with self.assertRaises(ValueError):catalog.confirm('terminal.open','different-hash')
   catalog.confirm('terminal.open','hash');self.assertTrue(Catalog(data).rows['terminal.open'].get('physical_confirmed') or Catalog(data).physical()['terminal.open']['physical_confirmed'])
