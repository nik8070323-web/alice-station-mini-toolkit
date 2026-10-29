"""Narrow Unix-socket receiver: a pinned allowlist of scenario actions.
Never accepts command_id, shell text, credentials, or microphone data.
"""
import asyncio,collections,fcntl,hashlib,hmac,json,os,signal,time
from pathlib import Path
from cli import call as commander
from voice.scenarios import SCENARIOS,TEST_SCENARIO
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/voice';CONFIG=ROOT/'config/scenario-bridge.json'
SOCKET=DATA/'bridge.sock';STATE=DATA/'state.json'
TOKEN=DATA/'token';DISABLED=DATA/'disabled'
MIN_DISPATCH_SPACING=2.1

def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)

def validate_event(data,entity,now):
    if not isinstance(data,dict) or set(data)!={'kind','token','event_type','event_id','time_fired','data','from_integration'}:raise ValueError('schema')
    if data['kind']!='event' or data['event_type']!='yandex_scenario' or data['from_integration'] is not True:raise ValueError('event_source')
    if not isinstance(data['event_id'],str) or not 1<=len(data['event_id'])<=128:raise ValueError('event_id')
    stamp=data['time_fired']
    if isinstance(stamp,bool) or not isinstance(stamp,(float,int)) or not -2<=now-stamp<=8:raise ValueError('stale_event')
    d=data['data']
    if not isinstance(d,dict) or set(d)!={'scenario_name','entity_id','instance','value'}:raise ValueError('event_fields')
    if not entity or d['entity_id']!=entity:raise ValueError('station_not_bound')
    if not isinstance(d['scenario_name'],str) or d['scenario_name'] not in SCENARIOS:raise ValueError('scenario_not_allowed')
    if d['instance']!='text_action' or not isinstance(d['value'],str) or d['value'].strip().casefold()!='ничего не делай':raise ValueError('action_not_allowed')
    return SCENARIOS[d['scenario_name']]

class Bridge:
    def __init__(self):
        from voice.catalog import Catalog,read
        from voice.wake import Wake
        self.state={'enabled':True,'stage':'waiting_for_home_assistant','source':'home_assistant:yandex_scenario','wake_verified':False,'wake_effect_enabled':False}
        self.catalog=Catalog(DATA);self.bindings=read(DATA/'bindings.json',{});self.protocol=read(DATA/'protocol.json',{}).get('version',1)
        self.seen=read(DATA/'seen.json',{});self.seen={k:v for k,v in self.seen.items() if time.time()-v<120}
        self.clients=0;self.queue=asyncio.Queue(maxsize=8);self.worker=None;self.recent=[];self.last_dispatch={};self.wake=Wake(DATA,CONFIG)
    def update(self,**fields):
        self.state['recognized_commands_verified']=sum(bool(x.get('physical_confirmed')) for x in self.catalog.physical().values())
        self.state.update(fields);self.state['updated']=time.time();atomic(STATE,self.state)
    def log(self,kind,**fields):
        path=DATA/'events.jsonl'
        if path.exists() and path.stat().st_size>262144:path.replace(DATA/'events.previous.jsonl')
        with path.open('a') as f:f.write(json.dumps({'time':time.time(),'kind':kind,**fields},ensure_ascii=False)+'\n')
    async def dispatch(self):
        while True:
            cid,key,received=await self.queue.get()
            try:
                wait=max(0,MIN_DISPATCH_SPACING-(time.monotonic()-self.last_dispatch.get(cid,-100)))
                if wait:await asyncio.sleep(wait)
                if cid.startswith(('rgb.','mode.')) and cid!='mode.away':
                    from voice.catalog import read
                    stop=read(DATA/'wake-state.json',{}).get('last_stop',0)
                    if 0<=time.time()-stop<3:await asyncio.sleep(3-(time.time()-stop))
                if time.time()-received>55 or DISABLED.exists() or (ROOT/'data/disabled').exists():raise ValueError('action expired/disabled')
                health=await asyncio.wait_for(asyncio.to_thread(commander,'/api/status'),4)
                if not health.get('running') or not health.get('enabled'):raise ValueError('Desktop Agent unavailable')
                self.last_dispatch[cid]=time.monotonic()
                result=await asyncio.wait_for(asyncio.to_thread(commander,'/api/run',{'command_id':cid}),58)
            except Exception as e:result={'ok':False,'error':str(e)[:200] if isinstance(e,ValueError) else type(e).__name__}
            self.catalog.result(cid,key,result)
            self.update(last_dispatch_ok=result.get('ok') is True,last_dispatch_time=time.time(),queue_depth=self.queue.qsize())
            self.log('commander_result',ok=result.get('ok') is True,command_id=cid,event_hash=key)
            self.queue.task_done()
    def inventory(self,message,entity):
        from voice.protocol import identity,fresh
        if set(message)!={'kind','token','checked_at','scenarios'} or not fresh(message['checked_at'],time.time(),60):raise ValueError('inventory_schema')
        if not isinstance(message['scenarios'],list) or len(message['scenarios'])>64:raise ValueError('inventory_limit')
        rows=[]
        for row in message['scenarios']:
            if not isinstance(row,dict) or set(row)!={'scenario_id','name','entity_id','phrase','usable','error'}:raise ValueError('inventory_row')
            if not identity(row['scenario_id']) or row['name'] not in SCENARIOS or row['entity_id']!=entity:raise ValueError('inventory_binding')
            if not isinstance(row['usable'],bool) or not isinstance(row['phrase'],str) or len(row['phrase'])>160:raise ValueError('inventory_values')
            if row['error'] is not None and (not isinstance(row['error'],str) or len(row['error'])>160):raise ValueError('inventory_error')
            rows.append(row)
        self.bindings=self.catalog.inventory(rows);self.protocol=2;atomic(DATA/'protocol.json',{'version':2})
        self.update(inventory_checked=message['checked_at'],scenario_count=len(rows),protocol=2)
        return {'ok':True,'bound':len(self.bindings)}
    async def handle(self,r,w):
        self.clients+=1
        try:
            if self.clients>8:return
            line=await asyncio.wait_for(r.readline(),3)
            if len(line)>32768:raise ValueError('message_limit')
            d=json.loads(line)
            if not isinstance(d,dict) or not isinstance(d.get('token'),str) or not hmac.compare_digest(d['token'],TOKEN.read_text().strip()):raise ValueError('unauthorized')
            if d.get('kind')!='inventory' and len(line)>4096:raise ValueError('event_limit')
            if (ROOT/'data/disabled').exists() or DISABLED.exists():raise ValueError('disabled')
            cfg=json.loads(CONFIG.read_text());entity=cfg.get('entity_id')
            if d.get('kind')=='heartbeat':
                if set(d)!={'kind','token','integration_loaded','speakers'} or not isinstance(d['integration_loaded'],bool) or not isinstance(d['speakers'],list):raise ValueError('heartbeat_schema')
                speakers=[{'entity_id':x['entity_id'][:128],'platform':x['platform'][:64]} for x in d['speakers'][:20] if isinstance(x,dict) and isinstance(x.get('entity_id'),str) and isinstance(x.get('platform'),str)]
                self.update(last_heartbeat=time.time(),integration_loaded=d['integration_loaded'],speakers=speakers,stage='connected' if entity and d['integration_loaded'] else 'waiting_for_yandex_login')
                result={'ok':True}
            elif d.get('kind')=='inventory':result=self.inventory(d,entity)
            elif d.get('kind')=='wake_state':result=await self.wake.event(d,entity)
            else:
                from voice.protocol import validate_v2
                if 'launch_id' in d:
                    cid=validate_v2(d,entity,self.bindings,time.time());identity=d['scenario_id']+':'+d['launch_id']
                else:
                    if self.protocol>=2:raise ValueError('launch_metadata_required')
                    cid=validate_event(d,entity,time.time());identity=d['event_id']
                if not cfg.get('enabled',False):raise ValueError('disabled_in_config')
                if cid in cfg.get('excluded_commands',[]):raise ValueError('disabled_by_user')
                if d['data']['scenario_name']!=TEST_SCENARIO:
                    proof=DATA/'verification.json'
                    confirmed=proof.exists() and json.loads(proof.read_text()).get('human_confirmed') is True
                    if not cfg.get('expanded',False) or not confirmed:raise ValueError('test_only')
                key=hashlib.sha256(identity.encode()).hexdigest()
                self.seen={k:v for k,v in self.seen.items() if time.time()-v<120}
                if key in self.seen:raise ValueError('duplicate')
                self.recent=[t for t in self.recent if time.monotonic()-t<60]
                if len(self.recent)>=30 or self.queue.full():raise ValueError('rate/queue limit')
                self.seen[key]=time.time();atomic(DATA/'seen.json',self.seen);self.recent.append(time.monotonic())
                self.catalog.event(cid,key,d.get('scenario_id'),hashlib.sha256(d.get('launch_id','').encode()).hexdigest())
                self.update(last_event_hash=key,last_real_event=time.time(),command_id=cid,queue_depth=self.queue.qsize()+1)
                self.log('matched_scenario',event_hash=key,scenario_id=d.get('scenario_id'),command_id=cid)
                self.queue.put_nowait((cid,key,time.time()))
                if self.worker is None or self.worker.done():self.worker=asyncio.create_task(self.dispatch())
                result={'ok':True,'accepted':True,'queued':True,'event_hash':key}
            w.write(json.dumps(result).encode()+b'\n');await w.drain()
        except Exception as e:
            reason=str(e) if isinstance(e,ValueError) else type(e).__name__;self.log('rejected',reason=reason[:80])
            try:w.write(json.dumps({'ok':False,'error':reason[:80]}).encode()+b'\n');await w.drain()
            except Exception:pass
        finally:
            self.clients-=1;w.close()
            try:await w.wait_closed()
            except OSError:pass

async def main():
    os.umask(0o077);DATA.mkdir(exist_ok=True)
    lock=(DATA/'bridge.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);SOCKET.unlink(missing_ok=True)
    bridge=Bridge()
    if STATE.exists():
        try:
            previous=json.loads(STATE.read_text())
            for key in ('last_event_hash','last_real_event','last_dispatch_ok','last_dispatch_time','command_id'):
                if key in previous:bridge.state[key]=previous[key]
        except Exception:pass
    for row in bridge.catalog.rows.values():
        if row.get('pending'):row.update(pending=False,error='Bridge restarted; pending action was not replayed')
    bridge.catalog.save();bridge.update(pid=os.getpid(),protocol=bridge.protocol)
    server=await asyncio.start_unix_server(bridge.handle,path=str(SOCKET),limit=32769)
    SOCKET.chmod(0o600);done=asyncio.Event();loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,done.set)
    async def watchdog():
        while not done.is_set():
            if time.time()-bridge.state.get('last_heartbeat',0)>25:await bridge.wake.stop('ha_disconnected')
            if bridge.wake.active:
                from voice.catalog import read
                if time.time()-read(DATA/'wake-state.json',{}).get('last_start',0)>2.8:
                    bridge.wake.active=None;bridge.wake.record(active=False,stop_reason='two_second_deadline')
            await asyncio.sleep(.5)
    watch=asyncio.create_task(watchdog())
    async with server:await done.wait()
    watch.cancel()
    await bridge.wake.stop('bridge_shutdown')
    if bridge.worker:bridge.worker.cancel()
    bridge.update(enabled=False,stage='stopped');SOCKET.unlink(missing_ok=True)
if __name__=='__main__':asyncio.run(main())
