"""Persistent evidence per command, distinct from configured/CLI states."""
import json,time
from pathlib import Path
from commands.registry import COMMANDS
from voice.scenarios import ROWS,SCENARIOS,TEST_SCENARIO
ROOT=Path(__file__).resolve().parents[1]

def read(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def write(path,data):
    p=path.with_suffix('.tmp');p.write_text(json.dumps(data,ensure_ascii=False,indent=2));p.replace(path)

def initial():
    names={cid:name for name,cid in ROWS}
    return {cid:{'command_id':cid,'scenario_name':names[cid],'phrase':c['phrase'],
        'cli_status':'not_tested' if cid.startswith('phone.') else ('unsupported_by_current_player' if cid=='media.next' else 'verified_in_v1'),
        'scenario_created':False,'scenario_usable':False,'scenario_ids':[],
        'event_received':False,'physical_confirmed':False,'last_success':None,'error':None} for cid,c in COMMANDS.items()}

class Catalog:
    def __init__(self,data):
        self.data=data;self.path=data/'commands.json';self.rows=initial()
        saved=read(self.path,{})
        for cid,row in saved.items():
            if cid in self.rows:self.rows[cid].update(row)
        proof=read(data/'verification.json',{})
        if proof.get('human_confirmed') and proof.get('command_id')=='rgb.rainbow':
            self.rows['rgb.rainbow'].update(physical_confirmed=True,physical_event_hash=proof.get('event_hash'),physical_time=proof.get('time'))
    def physical(self):
        proofs=read(self.data/'physical.json',{})
        for cid,proof in proofs.items():
            if cid in self.rows and proof.get('human_confirmed') is True:
                self.rows[cid].update(physical_confirmed=True,physical_event_hash=proof['event_hash'],physical_time=proof['time'])
        return self.rows
    def save(self):
        self.physical();write(self.path,self.rows)
    def inventory(self,items):
        for row in self.rows.values():row.update(scenario_created=False,scenario_usable=False,scenario_ids=[],scenarios=[],scenario_error=None)
        bindings={}
        for item in items:
            cid=SCENARIOS[item['name']];row=self.rows[cid]
            row['scenario_created']=True;row['scenario_ids'].append(item['scenario_id']);row['scenarios'].append({k:item[k] for k in ('scenario_id','name','phrase','usable')})
            if item['usable']:
                row['scenario_usable']=True
                bindings[item['scenario_id']]={'name':item['name'],'command_id':cid,'entity_id':item['entity_id']}
            else:row['scenario_error']=item.get('error') or 'invalid scenario action'
            row['configured_phrase']=item.get('phrase') or row['phrase'].removeprefix('Алиса, ')
        write(self.data/'bindings.json',bindings);self.save()
        return bindings
    def event(self,cid,key,scenario_id=None,launch_id=None):
        self.rows[cid].update(event_received=True,last_event=time.time(),last_event_hash=key,last_scenario_id=scenario_id,last_launch_hash=launch_id,error=None,pending=True);self.save()
    def result(self,cid,key,result):
        row=self.rows[cid];row['pending']=False;row['last_execution_event_hash']=key
        if result.get('ok'):
            row.update(last_success=time.time(),error=None)
        else:row['error']=str(result.get('error','Desktop Agent error'))[:250]
        self.save()
    def confirm(self,cid,key):
        row=self.rows[cid]
        if row.get('last_execution_event_hash')!=key or row.get('error') or not row.get('last_success'):raise ValueError('No successful execution for that event')
        proofs=read(self.data/'physical.json',{});proofs[cid]={'human_confirmed':True,'event_hash':key,'time':time.time()}
        write(self.data/'physical.json',proofs);self.physical()

def snapshot(root=ROOT):
    rows=initial();stored=read(root/'data/voice/commands.json',{})
    for cid,row in stored.items():
        if cid in rows:rows[cid].update(row)
    proof=read(root/'data/voice/verification.json',{})
    if proof.get('human_confirmed') and proof.get('command_id')=='rgb.rainbow':rows['rgb.rainbow']['physical_confirmed']=True
    for cid,p in read(root/'data/voice/physical.json',{}).items():
        if cid in rows and p.get('human_confirmed') is True:rows[cid].update(physical_confirmed=True,physical_event_hash=p['event_hash'],physical_time=p['time'])
    excluded=read(root/'config/scenario-bridge.json',{}).get('excluded_commands',[])
    for cid in excluded:
        if cid in rows:rows[cid]['excluded_by_user']=True
    local=read(root/'data/phone/local-tests.json',{})
    checks={'phone.connect':local.get('ping_human_confirmed'),
            'phone.battery':local.get('battery_read'),
            'phone.mirror':local.get('screen_and_mouse_human_confirmed'),
            'phone.mirror.stop':local.get('scrcpy_process_isolation',{}).get('scrcpy_stop_succeeded')}
    for cid,verified in checks.items():
        if cid in rows and verified:rows[cid]['cli_status']='verified_phone'
    return list(rows.values())
