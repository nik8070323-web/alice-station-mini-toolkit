import asyncio, json, os, signal, time
from pathlib import Path
from integrations import rgb
ROOT=Path(__file__).resolve().parents[1]

async def process(argv, cwd=None, timeout=12):
    p=await asyncio.create_subprocess_exec(*argv,cwd=cwd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True)
    # Drain all output but retain only a bounded prefix.
    async def drain(stream):
        result=bytearray()
        while chunk:=await stream.read(4096):
            if len(result)<12000:result.extend(chunk[:12000-len(result)])
        return result.decode(errors='replace')
    tasks=[asyncio.create_task(drain(p.stdout)),asyncio.create_task(drain(p.stderr))]
    try:
        await asyncio.wait_for(p.wait(),timeout)
        out,err=await asyncio.wait_for(asyncio.gather(*tasks),2)
    except (asyncio.TimeoutError,asyncio.CancelledError):
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        await p.wait()
        for task in tasks:task.cancel()
        raise RuntimeError('process timeout/cancelled')
    if p.returncode:raise RuntimeError(f'process exit {p.returncode}: {err[:300]}')
    if out.strip().lower().startswith(('error','invalid','unknown')):raise RuntimeError(out[:300])
    return {'exit_code':p.returncode,'output':out[:12000]}

async def launch(argv,cwd=None):
    # A transient user unit contains application lifetime; no subprocess shell.
    unit='alice-commander-app-'+str(time.time_ns())
    result=await process(['systemd-run','--user','--quiet','--collect','--unit='+unit,'--property=Type=exec','--property=ExitType=cgroup','--property=StandardOutput=null','--property=StandardError=null',*(['--working-directory='+str(cwd)] if cwd else []),'--',*argv])
    return {**result,'state':'launched; visual confirmation required','unit':unit}

class Desktop:
    def __init__(self):
        self.mode=(ROOT/'data/mode').read_text().strip() if (ROOT/'data/mode').exists() else 'default'
        self.previous_workspace=None
    def project(self):
        c=json.loads((ROOT/'config/settings.json').read_text());p=Path(c['project']).expanduser().resolve()
        allowed=[Path(x).expanduser().resolve() for x in c['allowed_directories']]
        if p not in allowed or not p.is_dir():raise ValueError('project directory not allowlisted')
        return p
    async def run(self,cid):
        if cid=='terminal.open':return await launch(['/usr/bin/kitty'])
        if cid=='browser.open':return await process(['/usr/share/omarchy/bin/omarchy-launch-browser'])
        if cid=='github.open':return await process(['/usr/share/omarchy/bin/omarchy-launch-browser','https://github.com'])
        if cid=='desktop.lock':
            # Omarchy's shell lock target is absent in this customized session.
            # Keep the user's installed Hyprlock/config and verify the compositor.
            result=await launch(['/usr/local/bin/hyprlock','-c',str(Path.home()/'.config/hypr/hyprlock.conf')])
            for _ in range(20):
                try:
                    await process(['/usr/share/omarchy/bin/omarchy-hyprland-session-locked'],timeout=2)
                    return {**result,'compositor_locked':True}
                except RuntimeError:await asyncio.sleep(.1)
            raise RuntimeError('Hyprlock launched but compositor lock was not confirmed')
        if cid=='workspace.next':return await process(['hyprctl','dispatch','hl.dsp.focus({ workspace = "+1" })'])
        if cid=='desktop.show':
            if self.previous_workspace is None:
                current=json.loads((await process(['hyprctl','activeworkspace','-j']))['output'])['id']
                spaces=json.loads((await process(['hyprctl','workspaces','-j']))['output'])
                used={w['id'] for w in spaces};target=next(i for i in range(90,100) if i not in used)
                result=await process(['hyprctl','dispatch',f'hl.dsp.focus({{ workspace = "{target}" }})'])
                self.previous_workspace=current
            else:
                result=await process(['hyprctl','dispatch',f'hl.dsp.focus({{ workspace = "{self.previous_workspace}" }})']);self.previous_workspace=None
            return result
        if cid.startswith('volume.'):
            return await process(['wpctl','set-mute','@DEFAULT_AUDIO_SINK@','toggle'] if cid=='volume.mute' else ['wpctl','set-volume','@DEFAULT_AUDIO_SINK@','5%+' if cid=='volume.up' else '5%-'])
        if cid.startswith('media.'):return await process(['playerctl','--player=%any','pause' if cid=='media.pause' else 'next'])
        if cid in ('editor.open','project.open'):return await launch(['/usr/bin/code',str(self.project())])
        if cid=='git.status':return await process(['git','--no-optional-locks','-c','core.fsmonitor=false','status','--short','--branch'],cwd=self.project())
        if cid=='project.test':
            if self.project()!=ROOT:raise ValueError('only fixed commander-selftest profile approved; configure a reviewed profile in code')
            started=time.time()
            try:r=await process(['/usr/bin/python3','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,timeout=45)
            except Exception:
                (ROOT/'data/build.json').write_text(json.dumps({'profile':'commander-selftest','ok':False,'time':started}));raise
            (ROOT/'data/build.json').write_text(json.dumps({'profile':'commander-selftest','ok':True,'time':started}));return r
        if cid=='build.status':
            p=ROOT/'data/build.json'
            return json.loads(p.read_text()) if p.exists() else {'state':'no registered build'}
        if cid in ('system.health','system.memory'):
            mem={a:int(b.split()[0]) for a,b in (l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines())}
            return {'load_average':os.getloadavg(),'logical_cpus':os.cpu_count(),'ram_available_MiB':mem['MemAvailable']//1024,'ram_total_MiB':mem['MemTotal']//1024}
        if cid=='system.temperature':
            sensors=[]
            for p in Path('/sys/class/hwmon').glob('hwmon*/temp*_input'):
                try:
                    label=p.with_name(p.name.replace('_input','_label'));name=p.parent/'name'
                    sensors.append({'sensor':(name.read_text().strip() if name.exists() else p.parent.name)+':'+(label.read_text().strip() if label.exists() else p.stem),'celsius':int(p.read_text())/1000})
                except (OSError,ValueError):continue
            return {'sensors':sensors,'state':'read' if sensors else 'no readable sensors'}
        if cid=='network.check':
            try:
                r,w=await asyncio.wait_for(asyncio.open_connection('1.1.1.1',443),4);w.close();await w.wait_closed()
                return {'tcp_443_reachable':True,'scope':'1.1.1.1 only; DNS and general Internet not proven'}
            except (OSError,asyncio.TimeoutError):return {'tcp_443_reachable':False}
        if cid.startswith('rgb.'):return await rgb.action(cid)
        if cid.startswith('mode.'):
            mode=cid.split('.')[1];results=[]
            if mode in ('work','study'):
                results.append(await self.run('project.open' if mode=='work' else 'terminal.open'))
                results.append(await process(['/usr/share/omarchy/bin/omarchy-launch-browser','https://docs.python.org/3/' if mode=='study' else 'https://github.com']))
            if mode=='away':
                results.append(await self.run('desktop.lock'))
            try:
                if mode in ('work','study','back'):await rgb.call('/v1/effects',{'night_override':False})
                results.append(await rgb.action('rgb.off' if mode=='away' else 'rgb.night' if mode=='rest' else 'rgb.purple'))
            except Exception as e:results.append({'rgb_error':type(e).__name__})
            self.mode=mode
            (ROOT/'data/mode').write_text(mode)
            return {'mode':mode,'results':results,'note':'RGB preview max 2s; back does not unlock; rest changes Commander profile only'}
        raise ValueError('unregistered command')
