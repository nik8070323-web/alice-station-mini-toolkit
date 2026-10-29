#!/usr/bin/env python3
import argparse,json,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from commands.registry import COMMANDS

def call(path,body=None):
    token=(ROOT/'data/token').read_text().strip()
    req=urllib.request.Request('http://127.0.0.1:8878'+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    for attempt in range(10):
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=60) as r:return json.load(r)
        except urllib.error.URLError as e:
            # Retry only connection refusal before a request could be delivered.
            if not isinstance(e.reason,ConnectionRefusedError) or attempt==9:raise
            time.sleep(.2)

def main():
    p=argparse.ArgumentParser(description='Alice Commander v1 — только зарегистрированные локальные действия')
    sub=p.add_subparsers(dest='action',required=True)
    for n in ('status','commands','doctor','disable','enable'):sub.add_parser(n)
    run=sub.add_parser('run');run.add_argument('command_id',choices=COMMANDS)
    for n in ('voice','rgb'):s=sub.add_parser(n);s.add_argument('operation',choices=['status'])
    a=p.parse_args()
    try:
        if a.action=='commands':result=list(COMMANDS.values())
        elif a.action in ('disable','enable'):
            marker=ROOT/'data/disabled'
            if a.action=='disable':
                marker.touch(mode=0o600)
                r=subprocess.run(['systemctl','--user','disable','--now','alice-commander.service'],check=False)
                if r.returncode:raise RuntimeError('systemd stop failed; command marker remains disabled')
            else:
                marker.unlink(missing_ok=True)
                subprocess.run(['systemctl','--user','enable','--now','alice-commander.service'],check=True)
            result={'enabled':a.action=='enable','existing_rgb_service':'unchanged'}
        elif a.action=='run':result=call('/api/run',{'command_id':a.command_id})
        elif a.action=='rgb':result=call('/api/rgb')
        else:
            result=call('/api/status')
            if a.action=='voice':result=result['voice']
            if a.action=='doctor':
                result={'agent':True,'enabled':result['enabled'],'health':result['health'],'voice':result['voice'],'rgb':call('/api/rgb'),'session':{'WAYLAND_DISPLAY':bool(__import__('os').environ.get('WAYLAND_DISPLAY'))}}
        print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if isinstance(result,dict) and result.get('ok') is False else 0
    except urllib.error.HTTPError as e:
        print(e.read().decode(errors='replace'),file=sys.stderr);return 1
    except Exception as e:print(f'Ошибка: {e}',file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
