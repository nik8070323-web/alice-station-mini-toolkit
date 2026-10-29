import asyncio,contextlib,copy,json,tempfile,time,unittest,os
from pathlib import Path
from unittest.mock import patch,AsyncMock
from voice.protocol import validate_v2
from voice.scenarios import TEST_SCENARIO

def event(launch='launch-1'):
    return {'kind':'event','token':'test','event_type':'yandex_scenario','event_id':'ctx-1','time_fired':time.time(),'from_integration':True,
        'scenario_id':'scenario-1','launch_id':launch,'launch_time':time.time(),
        'data':{'scenario_name':TEST_SCENARIO,'entity_id':'media_player.mini','instance':'text_action','value':'Ничего не делай'}}
def bindings():return {'scenario-1':{'name':TEST_SCENARIO,'entity_id':'media_player.mini','command_id':'rgb.rainbow'}}

class ProtocolV2(unittest.TestCase):
    def test_requires_bound_uuid_and_fresh_launch(self):
        self.assertEqual(validate_v2(event(),'media_player.mini',bindings(),time.time()),'rgb.rainbow')
        for key,value in [('scenario_id','other'),('launch_time',0),('launch_time',float('nan')),('command_id','terminal.open'),('launch_id','../../exec')]:
            data=event();data[key]=value
            with self.subTest(key=key,value=value):
                with self.assertRaises(ValueError):validate_v2(data,'media_player.mini',bindings(),time.time())
    def test_name_cannot_redirect_uuid(self):
        data=event();data['data']['scenario_name']='Компьютер Терминал'
        with self.assertRaises(ValueError):validate_v2(data,'media_player.mini',bindings(),time.time())

class DeliveryV2(unittest.IsolatedAsyncioTestCase):
    async def test_repeat_delivery_once_but_two_launches_twice_across_restart(self):
        import voice.scenario_bridge as module
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            root=Path(temp);data=root/'data/voice';data.mkdir(parents=True);(root/'config').mkdir()
            config=root/'config/scenario-bridge.json';config.write_text(json.dumps({'enabled':True,'entity_id':'media_player.mini'}))
            (data/'token').write_text('test');(data/'bindings.json').write_text(json.dumps(bindings()));(data/'protocol.json').write_text('{"version":2}')
            for key,value in {'ROOT':root,'DATA':data,'STATE':data/'state.json','TOKEN':data/'token','CONFIG':config,'DISABLED':data/'disabled','MIN_DISPATCH_SPACING':0}.items():stack.enter_context(patch.object(module,key,value))
            execute=stack.enter_context(patch.object(module,'commander',side_effect=lambda path,*args:{'running':True,'enabled':True} if path=='/api/status' else {'ok':True,'result':{}}))
            receiver=module.Bridge();sock=data/'test.sock';server=await asyncio.start_unix_server(receiver.handle,path=str(sock))
            async def send(message):
                r,w=await asyncio.open_unix_connection(str(sock));w.write(json.dumps(message).encode()+b'\n');await w.drain();reply=json.loads(await r.readline());w.close();await w.wait_closed();return reply
            try:
                first=event();self.assertTrue((await send(first))['accepted'])
                duplicate=copy.deepcopy(first);duplicate['event_id']='ctx-retry'
                self.assertEqual((await send(duplicate))['error'],'duplicate')
                second=event('launch-2');self.assertTrue((await send(second))['accepted'])
                await asyncio.wait_for(receiver.queue.join(),2)
                self.assertEqual(sum(c.args[0]=='/api/run' for c in execute.call_args_list),2)
                restored=module.Bridge();self.assertEqual(len(restored.seen),2)
                self.assertFalse((data/'verification.json').exists())
            finally:
                server.close();await server.wait_closed()
                if receiver.worker:receiver.worker.cancel()

class WakeSafety(unittest.IsolatedAsyncioTestCase):
    async def test_observe_only_and_no_start_from_reconnect_listening(self):
        from voice.wake import Wake
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);cfg=data/'config.json';cfg.write_text('{"wake_enabled":false}')
            wake=Wake(data,cfg)
            def signal(state,seq):return {'kind':'wake_state','token':'x','entity_id':'media_player.mini','state':state,'session':'session1','sequence':seq,'time':time.time()}
            with patch('voice.wake.call',new=AsyncMock()) as rgb:
                await wake.event(signal('IDLE',1),'media_player.mini');await wake.event(signal('LISTENING',2),'media_player.mini');rgb.assert_not_called()
                cfg.write_text(json.dumps({'wake_trial_until':time.time()+60,'wake_trial_pid':os.getpid()}))
                other=Wake(data,cfg);await other.event(signal('LISTENING',1),'media_player.mini');rgb.assert_not_called()
    async def test_stops_own_preview_on_end_of_listening(self):
        from voice.wake import Wake
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);cfg=data/'config.json';cfg.write_text(json.dumps({'wake_trial_until':time.time()+60,'wake_trial_pid':os.getpid()}));wake=Wake(data,cfg)
            def signal(state,seq):return {'kind':'wake_state','token':'x','entity_id':'media_player.mini','state':state,'session':'session1','sequence':seq,'time':time.time()}
            with patch('voice.wake.call',new=AsyncMock(return_value={'accepted':True})) as rgb:
                await wake.event(signal('IDLE',1),'media_player.mini');await wake.event(signal('LISTENING',2),'media_player.mini');await wake.event(signal('SPEAKING',3),'media_player.mini')
                self.assertEqual([c.args[1]['action'] for c in rgb.call_args_list],['start','stop'])
                self.assertEqual(rgb.call_args_list[0].args[1]['request_id'],rgb.call_args_list[1].args[1]['request_id'])
