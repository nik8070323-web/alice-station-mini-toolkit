"""Local bridge lifecycle and explicit binding/verification; never receives network commands."""
import argparse,hashlib,json,re,subprocess,time
from pathlib import Path
from voice.bridge import status
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/voice';CFG=ROOT/'config/scenario-bridge.json'
COMPOSE=ROOT/'integrations/homeassistant/compose.yaml'
def run(args):subprocess.run(args,check=True)
def main():
    p=argparse.ArgumentParser(description='Narrow Yandex scenario bridge control')
    sub=p.add_subparsers(dest='cmd',required=True)
    for c in ('status','disable','enable','bind-mini','evidence'):sub.add_parser(c)
    s=sub.add_parser('confirm-physical');s.add_argument('--event-hash',required=True);s.add_argument('--human-confirmed',action='store_true',required=True)
    confirm=sub.add_parser('confirm-command');confirm.add_argument('--command-id',required=True);confirm.add_argument('--event-hash',required=True);confirm.add_argument('--human-confirmed',action='store_true',required=True)
    sub.add_parser('wake-trial')
    a=p.parse_args()
    if a.cmd=='wake-trial':
        state=json.loads((DATA/'state.json').read_text());cfg=json.loads(CFG.read_text())
        cfg.update(wake_trial_until=time.time()+75,wake_trial_pid=state['pid'])
        CFG.write_text(json.dumps(cfg,ensure_ascii=False,indent=2));print('Wake trial: 75 seconds, this process only; no permanent enable.');return
    if a.cmd=='confirm-command':
        from commands.registry import COMMANDS
        from voice.catalog import Catalog
        if a.command_id not in COMMANDS:raise SystemExit('Unknown command')
        catalog=Catalog(DATA);catalog.confirm(a.command_id,a.event_hash)
        print('Physical confirmation saved for actual event:',a.command_id);return
    if a.cmd=='status':print(json.dumps(status(),ensure_ascii=False,indent=2));return
    if a.cmd=='disable':
        (DATA/'disabled').touch(mode=0o600)
        run(['systemctl','--user','disable','--now','alice-scenario-bridge.service'])
        run(['docker','compose','-f',str(COMPOSE),'stop'])
        print('Scenario bridge and its HA stopped; Commander/RGB unchanged.');return
    if a.cmd=='enable':
        (DATA/'disabled').unlink(missing_ok=True)
        proof=DATA/'verification.json'
        confirmed=proof.exists() and json.loads(proof.read_text()).get('human_confirmed') is True
        run(['systemctl','--user','enable','--now','alice-scenario-bridge.service'] if confirmed else ['systemctl','--user','start','alice-scenario-bridge.service'])
        run(['docker','compose','-f',str(COMPOSE),'up','-d']);return
    state=json.loads((DATA/'state.json').read_text())
    if a.cmd=='bind-mini':
        candidates=[s['entity_id'] for s in state.get('speakers',[]) if s.get('platform')=='yandexmini']
        if len(candidates)!=1:raise SystemExit('Need exactly one yandexmini candidate; no automatic binding: '+str(candidates))
        if not re.fullmatch(r'media_player\.[a-z0-9_]{1,120}',candidates[0]):raise SystemExit('Invalid entity id')
        cfg=json.loads(CFG.read_text());cfg['entity_id']=candidates[0];CFG.write_text(json.dumps(cfg,ensure_ascii=False,indent=2))
        print('Bound Mini 1:',candidates[0]);return
    if a.cmd=='evidence':
        from integrations.rgb import request
        rgb=request('/v1/status')
        print(json.dumps({'bridge':state,'rgb_last_result':rgb.get('last_result'),'voice_status':status()},ensure_ascii=False,indent=2));return
    if a.cmd=='confirm-physical':
        from integrations.rgb import request
        if a.event_hash!=state.get('last_event_hash') or not re.fullmatch(r'[0-9a-f]{64}',a.event_hash):raise SystemExit('Event mismatch')
        if state.get('command_id')!='rgb.rainbow' or time.time()-state.get('last_real_event',0)>300 or not state.get('last_dispatch_ok'):raise SystemExit('Need fresh matched real event and successful dispatch')
        rgb=request('/v1/status');last=rgb.get('last_result',{})
        if last.get('state')!='completed' or last.get('job')!='rainbow':raise SystemExit('Coordinator completion missing')
        v={'human_confirmed':True,'time':time.time(),'event_hash':a.event_hash,'command_id':'rgb.rainbow','coordinator_completion':last}
        (DATA/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2));print('Recorded human confirmation for this event only.')
if __name__=='__main__':main()
