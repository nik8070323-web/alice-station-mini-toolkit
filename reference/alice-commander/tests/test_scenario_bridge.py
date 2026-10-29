import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from voice.scenario_bridge import validate_event
from voice import bridge

def sample():return {'kind':'event','token':'test-only','event_type':'yandex_scenario','event_id':'test-context','time_fired':1000,'from_integration':True,'data':{'scenario_name':'Компьютерный режим','entity_id':'media_player.mini','instance':'text_action','value':'ничего не делай'}}
class EventSafety(unittest.TestCase):
    def test_fixed_mapping_without_execution(self):self.assertEqual(validate_event(sample(),'media_player.mini',1001),'rgb.rainbow')
    def test_capitalized_fixed_marker(self):
        event=sample();event['data']['value']='Ничего не делай'
        self.assertEqual(validate_event(event,'media_player.mini',1001),'rgb.rainbow')
    def test_complete_fixed_allowlist(self):
        from voice.scenarios import ROWS,SCENARIOS
        from commands.registry import COMMANDS
        self.assertEqual({cid for _,cid in ROWS},set(COMMANDS))
        self.assertEqual(len([cid for _,cid in ROWS if not cid.startswith("phone.")]),30)
        for name,cid in ROWS:
            event=sample();event['data']['scenario_name']=name
            self.assertEqual(validate_event(event,'media_player.mini',1001),cid)
    def test_rejections(self):
        cases=[]
        for field,value in [('kind','command'),('event_type','yandex_speaker'),('from_integration',False),('time_fired',900),('event_id',{}),('command_id','terminal.open')]:
            s=sample();s[field]=value;cases.append(s)
        for field,value in [('scenario_name','other'),('entity_id','media_player.other'),('instance','tts'),('value','echo arbitrary')]:
            s=sample();s['data'][field]=value;cases.append(s)
        for s in cases:
            with self.subTest(s=s):
                with self.assertRaises(ValueError):validate_event(s,'media_player.mini',1001)
        with self.assertRaises(ValueError):validate_event(sample(),None,1001)
    def test_unconfigured_status_is_closed(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(bridge,'ROOT',Path(temp)):
            s=bridge.status();self.assertFalse(s['enabled']);self.assertEqual(s['recognized_commands_verified'],0);self.assertFalse(s['wake_verified'])
    def test_dispatch_is_not_physical_verification(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(bridge,'ROOT',Path(temp)):
            r=Path(temp);(r/'config').mkdir();(r/'data/voice').mkdir(parents=True)
            (r/'config/scenario-bridge.json').write_text(json.dumps({'enabled':True,'entity_id':'media_player.mini'}))
            (r/'data/voice/state.json').write_text(json.dumps({'enabled':True,'last_heartbeat':time.time(),'last_dispatch_ok':True}))
            s=bridge.status();self.assertEqual(s['recognized_commands_verified'],0);self.assertFalse(s['wake_effect_enabled'])

class SocketSafety(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_deduplicated_single_mapping(self):
        import asyncio,contextlib
        from unittest.mock import Mock
        import voice.scenario_bridge as module
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            root=Path(temp);data=root/'data/voice';data.mkdir(parents=True);(root/'config').mkdir()
            token=data/'token';token.write_text('test-token')
            config=root/'config/scenario-bridge.json';config.write_text(json.dumps({'enabled':True,'entity_id':'media_player.mini'}))
            for key,value in {'ROOT':root,'DATA':data,'STATE':data/'state.json','TOKEN':token,'CONFIG':config,'DISABLED':data/'disabled'}.items():stack.enter_context(patch.object(module,key,value))
            execute=stack.enter_context(patch.object(module,'commander',side_effect=lambda path,*args:{'running':True,'enabled':True} if path=='/api/status' else {'ok':True,'result':{'accepted':True}}))
            receiver=module.Bridge();socket=data/'test.sock'
            server=await asyncio.start_unix_server(receiver.handle,path=str(socket))
            async def send(message):
                r,w=await asyncio.open_unix_connection(str(socket));w.write(json.dumps(message).encode()+b'\n');await w.drain()
                result=json.loads(await r.readline());w.close();await w.wait_closed();return result
            try:
                valid=sample();valid['time_fired']=time.time();valid['token']='test-token'
                unauthorized=copy.deepcopy(valid);unauthorized['token']='wrong'
                self.assertEqual((await send(unauthorized))['error'],'unauthorized')
                self.assertTrue((await send(valid))['ok'])
                self.assertEqual((await send(valid))['error'],'duplicate')
                injected=copy.deepcopy(valid);injected['command_id']='terminal.open'
                self.assertEqual((await send(injected))['error'],'schema')
                (data/'disabled').touch()
                self.assertEqual((await send(valid))['error'],'disabled')
                await asyncio.wait_for(receiver.queue.join(),1)
                self.assertEqual(sum(c.args[0]=='/api/run' for c in execute.call_args_list),1)
                self.assertFalse((data/'verification.json').exists())
            finally:
                server.close();await server.wait_closed()
                if receiver.worker:receiver.worker.cancel()
