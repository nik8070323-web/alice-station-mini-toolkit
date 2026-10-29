#!/usr/bin/env python3
"""Local Mini 1 panel and single bounded LED coordinator; standard library only."""
from __future__ import annotations
import collections, colorsys, datetime, fcntl, hmac, json, logging, math, os, re, secrets, signal, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG, TOKEN = ROOT/'data/config.json', ROOT/'data/token'
logging.basicConfig(filename=ROOT/'data/agent.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('alice-rgb')
LOCK = threading.RLock()
CONTROL = threading.Lock()
CANCEL = threading.Event()
EXIT = threading.Event()
BUSY = False
ACTIVE_JOB = None
LAST_END = 0.0
LAST_RESULT = {'state': 'idle'}
HISTORY = collections.deque(maxlen=30)
PACKAGES = {'purple-ring','rainbow-ring','breathing-ring','notification-success','notification-error','night-mode','mini-system-monitor'}
EFFECTS = {'static','rainbow','breathing','rotation','wave','pulse'}
EVENT_COLORS = {'success':'#22C55E','error':'#EF4444','warning':'#FACC15','info':'#38BDF8','status':'#38BDF8'}
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def cfg():
    with LOCK:
        c = json.loads(CONFIG.read_text())
    c.setdefault('brightness_percent',25)
    c.setdefault('night_schedule_enabled',True)
    c.setdefault('night_start',22)
    c.setdefault('night_end',7)
    c.setdefault('night_brightness_percent',5)
    c.setdefault('night_override',False)
    return c


def save(c):
    with LOCK:
        temp=CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(c,indent=2)+'\n'); temp.chmod(0o600); temp.replace(CONFIG)


def night(c, now=None):
    hour=(now or datetime.datetime.now().astimezone()).hour
    start,end=c['night_start'],c['night_end']
    scheduled=(hour>=start or hour<end) if start>end else start<=hour<end
    return c['night_override'] or (c['night_schedule_enabled'] and scheduled)


def station(path, body=None, method=None, timeout=1.0):
    raw=None if body is None else json.dumps(body).encode()
    request=urllib.request.Request(cfg()['station_url'].rstrip('/')+'/api/'+path, data=raw,
        method=method or ('POST' if raw is not None else 'GET'), headers={'Content-Type':'application/json'})
    with HTTP.open(request,timeout=timeout) as r:
        content=r.read()
        if 'json' in r.headers.get('Content-Type','') and content:return json.loads(content)
        return content.decode(errors='replace')


def plugins():return station('plugins')


def led_conflict():
    return [p['manifest']['id'] for p in plugins() if p.get('running') and 'led' in p['manifest'].get('permissions',[])]


def snapshot():
    c=cfg()
    try:
        device=station('device')
        device['ok']=True
    except Exception as exc:device={'ok':False,'error':type(exc).__name__}
    with LOCK:
        return {'running':True,'device':device,'busy':BUSY,'last_result':dict(LAST_RESULT),
            'history':list(HISTORY),'effects_enabled':c['effects_enabled'],
            'notifications_enabled':c['notifications_enabled'],'gestures_enabled':False,
            'gesture_calibrated':False,'brightness_percent':c['brightness_percent'],
            'night_active':night(c),'night_schedule_enabled':c['night_schedule_enabled'],
            'night_override':c['night_override'],'night_start':c['night_start'],'night_end':c['night_end'],
            'duration_limit_seconds':2,'ownership':'unavailable; bounded previews only'}


def shade(color, level):
    return '#'+''.join(f'{round(int(color[i:i+2],16)*max(0,min(1,level))):02X}' for i in (1,3,5))


def frame(effect, pixels, level, t):
    out=[]
    for i,color in enumerate(pixels):
        factor=1
        if effect=='rainbow':
            palette=['#8B5CF6','#38BDF8','#22C55E','#EC4899','#F59E0B']
            phase=((i/len(pixels)+t/3)%1)*len(palette)
            first=int(phase); blend=phase-first
            a,b=palette[first],palette[(first+1)%len(palette)]
            color='#'+''.join(f'{round(int(a[k:k+2],16)*(1-blend)+int(b[k:k+2],16)*blend):02X}' for k in (1,3,5))
        elif effect=='breathing':factor=(1-math.cos(t*2*math.pi))/2
        elif effect=='rotation':factor=1 if i==int(t*len(pixels))%len(pixels) else .08
        elif effect=='wave':factor=.12+.88*(math.sin(t*2*math.pi-i*2*math.pi/len(pixels))+1)/2
        elif effect=='pulse':factor=.2+.8*(math.sin(t*4*math.pi)+1)/2
        out.append(shade(color,level*factor))
    return out


def run_frames(job):
    c=cfg()
    d=station('device')
    if d.get('id')!='yandexmini' or d.get('led_count')!=6 or not d.get('capabilities',{}).get('led.ring.rgb'):
        raise RuntimeError('expected Mini 1 six RGB LEDs')
    conflict=led_conflict()
    if conflict:raise RuntimeError('another LED package is running: '+','.join(conflict))
    level=min(job['brightness'], c['brightness_percent'])/100
    if night(c):level=min(level,c['night_brightness_percent']/100)
    start=time.monotonic(); deadline=start+job['duration']; count=0
    # No retries or replay after reconnect: a failed write cancels this effect.
    while time.monotonic()<deadline and not CANCEL.is_set() and not EXIT.is_set():
        if not cfg()['effects_enabled']:break
        t=(time.monotonic()-start)/job['duration']
        station('led',{'colors':frame(job['effect'],job['pixels'],level,t)},timeout=.45)
        count+=1
        if job['effect']=='static':
            CANCEL.wait(max(0,deadline-time.monotonic()));break
        CANCEL.wait(.08)
    # One final black frame ends this preview; no recurring background ring writer.
    # During a Wi-Fi failure do not issue delayed cleanup later.
    if not job.get('_native_yield'):station('led/off',{},timeout=.45)
    return {'yielded_to_native':bool(job.get('_native_yield')),'frames':count,'duration_ms':round((time.monotonic()-start)*1000)}


def run_package(job):
    pid=job['package']; items=plugins(); item=next((p for p in items if p['manifest']['id']==pid),None)
    if not item or not item.get('compatible'):raise RuntimeError('package missing or incompatible')
    uses_led='led' in item['manifest'].get('permissions',[])
    if uses_led:
        if night(cfg()):raise RuntimeError('use panel effects at night: Lua package brightness is fixed')
        if led_conflict():raise RuntimeError('another LED package is running')
    was_enabled=item['enabled']
    try:
        if not was_enabled:station('plugins/'+pid+'/toggle',{},timeout=2)
        station('plugins/'+pid+'/invoke',{},timeout=2)
        deadline=time.monotonic()+8
        while True:
            time.sleep(.12)
            current=next(p for p in plugins() if p['manifest']['id']==pid)
            if not current['running']:break
            if CANCEL.is_set() or time.monotonic()>deadline:
                # Explicit user stop: stop our known active package and clear its LEDs once.
                station('plugins/'+pid+'/stop',{},timeout=2)
                raise RuntimeError('package cancelled or timeout')
        logs=station('plugins/'+pid+'/logs')
        return {'package':pid,'runtime_log':logs,'verification':'finished; Lua output is in daemon.log'}
    finally:
        current=next((p for p in plugins() if p['manifest']['id']==pid),None)
        if current and current['enabled']!=was_enabled:station('plugins/'+pid+'/toggle',{},timeout=2)


def execute(job):
    global BUSY, LAST_END, LAST_RESULT, ACTIVE_JOB
    result={'state':'completed','job':job.get('effect',job.get('package'))}
    if job.get('_wake_request'):result['wake_request_id']=job['_wake_request']
    try:
        with CONTROL:
            if CANCEL.is_set():raise RuntimeError('cancelled')
            result.update(run_package(job) if 'package' in job else run_frames(job))
    except Exception as exc:
        result.update(state='failed',error=str(exc));log.warning('job failed: %s',exc)
    finally:
        with LOCK:
            LAST_RESULT=result;HISTORY.append(result);LAST_END=time.monotonic();BUSY=False;ACTIVE_JOB=None
        log.info('job result %s',json.dumps(result))


def submit(job, notify=False):
    global BUSY, ACTIVE_JOB
    c=cfg()
    if not c['effects_enabled'] and job.get('package')!='mini-system-monitor':return False,'effects disabled'
    if notify and not c['notifications_enabled']:return False,'notifications disabled'
    with LOCK:
        if BUSY:return False,'ring busy; event dropped'
        if time.monotonic()-LAST_END<2:return False,'cooldown; event dropped'
        BUSY=True;ACTIVE_JOB=job;CANCEL.clear()
    threading.Thread(target=execute,args=(job,),daemon=True).start()
    return True,'accepted'



def wake_control(data):
    if not isinstance(data,dict) or set(data)!={'action','request_id'}:raise ValueError('wake schema')
    request=data['request_id']
    if not isinstance(request,str) or not re.fullmatch('[0-9a-f]{32}',request):raise ValueError('wake request id')
    if data['action']=='start':
        job=validate_effect({'effect':'rainbow','duration':2});job['_wake_request']=request
        ok,reason=submit(job)
        return {'accepted':ok,'reason':reason,'request_id':request}
    if data['action'] in ('stop','cancel'):
        with LOCK:
            owned=BUSY and ACTIVE_JOB is not None and ACTIVE_JOB.get('_wake_request')==request
            if owned:
                ACTIVE_JOB['_native_yield']=data['action']=='stop';CANCEL.set()
        return {'ok':True,'cancelled':bool(owned)}
    raise ValueError('wake action')


def validate_effect(data):
    if not isinstance(data,dict):raise ValueError('object required')
    effect=data.get('effect','static')
    c=cfg(); key='blue' if c.get('palette')=='blue' else 'purple'
    color=data.get('color',c.get('colors',{}).get(key,'#8B5CF6'))
    pixels=data.get('pixels',[color]*6)
    if effect not in EFFECTS:raise ValueError('unknown effect')
    if not isinstance(pixels,list) or len(pixels)!=6 or any(not isinstance(c,str) or not re.fullmatch('#[0-9a-fA-F]{6}',c) for c in pixels):raise ValueError('six #RRGGBB pixels required')
    duration=data.get('duration',1.5); brightness=data.get('brightness',cfg()['brightness_percent'])
    for name,value,low,high in [('duration',duration,.2,2),('brightness',brightness,0,100)]:
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not low<=value<=high:raise ValueError(name+' out of range')
    return {'effect':effect,'pixels':pixels,'duration':duration,'brightness':brightness}


class Handler(BaseHTTPRequestHandler):
    server_version='MiniPurple/2.0'
    def log_message(self,fmt,*args):log.debug(fmt,*args)
    def headers_ok(self):
        allowed={'127.0.0.1:8877','localhost:8877'}
        if self.headers.get('Host') not in allowed:return False
        origin=self.headers.get('Origin')
        return origin is None or origin in {'http://'+host for host in allowed}
    def auth(self):
        supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
        expected=TOKEN.read_text().strip()
        return self.headers_ok() and hmac.compare_digest(supplied,expected)
    def reply(self,code,obj,kind='application/json'):
        raw=json.dumps(obj,ensure_ascii=False).encode() if kind=='application/json' else obj
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'")
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if not self.headers_ok():return self.reply(403,{'error':'invalid host/origin'})
        if self.path in ('/','/app.js','/style.css'):
            name,kind={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css')}[self.path]
            return self.reply(200,(ROOT/'web'/name).read_bytes(),kind)
        if self.path=='/v1/session':
            # Same-origin local UI bootstrap. No CORS; no external assets or scripts.
            if self.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):return self.reply(403,{'error':'same origin required'})
            return self.reply(200,{'token':TOKEN.read_text().strip()})
        if not self.auth():return self.reply(401,{'error':'unauthorized'})
        if self.path=='/v1/status':return self.reply(200,snapshot())
        if self.path=='/v1/sensors':
            try:return self.reply(200,station('sensors'))
            except Exception as exc:return self.reply(503,{'error':str(exc)})
        return self.reply(404,{'error':'not found'})
    def do_POST(self):
        if not self.auth():return self.reply(401,{'error':'unauthorized'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096:return self.reply(413,{'error':'invalid length'})
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('object required')
            if self.path=='/v1/wake':
                result=wake_control(data);return self.reply(202 if result.get('accepted') else 200,result)
            if self.path=='/v1/stop':
                CANCEL.set();return self.reply(200,{'cancelled':True})
            if self.path=='/v1/notify':
                event=data.get('event')
                if event not in EVENT_COLORS:raise ValueError('unknown notification')
                job=validate_effect({'effect':'pulse' if event=='error' else 'static','color':EVENT_COLORS[event],'duration':.65})
                ok,reason=submit(job,True);return self.reply(202 if ok else 429,{'accepted':ok,'reason':reason})
            if self.path=='/v1/preview':
                aliases={'activation':'breathing','thinking':'breathing','check':'static','response':'wave','idle':'static','error':'pulse'}
                data['effect']=aliases.get(data.get('event'),data.get('event',data.get('effect','static')))
                if data.get('event') in ('response','error') and 'color' not in data:
                    data['color']=EVENT_COLORS['success' if data['event']=='response' else 'error']
                job=validate_effect(data);ok,reason=submit(job);return self.reply(202 if ok else 429,{'accepted':ok,'reason':reason})
            if self.path=='/v1/package':
                pid=data.get('package')
                if pid not in PACKAGES:raise ValueError('package not allowed; gestures remain disabled')
                ok,reason=submit({'package':pid});return self.reply(202 if ok else 429,{'accepted':ok,'reason':reason})
            if self.path=='/v1/effects':
                c=cfg();mapping={'enabled':'effects_enabled','notifications_enabled':'notifications_enabled','night_schedule_enabled':'night_schedule_enabled','night_override':'night_override'}
                for key,dest in mapping.items():
                    if key in data:
                        if not isinstance(data[key],bool):raise ValueError(key+' must be boolean')
                        c[dest]=data[key]
                if data.get('gestures_enabled'):raise ValueError('gestures require calibrated sensor; disabled')
                if 'brightness_percent' in data:
                    value=data['brightness_percent']
                    if isinstance(value,bool) or not isinstance(value,(float,int)) or not 0<=value<=100:raise ValueError('brightness 0..100 required')
                    c['brightness_percent']=value
                # Legacy palette CLI retained.
                if 'palette' in data and data['palette'] in ('violet','blue'):c['palette']=data['palette']
                c['gestures_enabled']=False;c['gesture_calibrated']=False
                save(c)
                if not c['effects_enabled']:CANCEL.set()
                return self.reply(200,{'saved':True,'effects_enabled':c['effects_enabled'],'night_active':night(c)})
            return self.reply(404,{'error':'not found'})
        except (ValueError,TypeError,KeyError) as exc:return self.reply(400,{'error':str(exc)})
        except Exception as exc:
            log.exception('request failed');return self.reply(503,{'error':type(exc).__name__})


class Server(ThreadingHTTPServer):
    daemon_threads=True;allow_reuse_address=True


def main():
    instance_lock=(ROOT/'data/agent.lock').open('w')
    try:fcntl.flock(instance_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('another RGB coordinator is running')
    c=cfg()
    if c['listen_host']!='127.0.0.1' or c['listen_port']!=8877:raise SystemExit('loopback :8877 required')
    if not TOKEN.exists():TOKEN.write_text(secrets.token_hex(32));TOKEN.chmod(0o600)
    def stop(*_):EXIT.set();CANCEL.set()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    server=Server(('127.0.0.1',8877),Handler);server.timeout=.5
    log.info('coordinator started; no ambient loop; no offline replay')
    while not EXIT.is_set():server.handle_request()
    CANCEL.set()
    with CONTROL:pass
    server.server_close()

if __name__=='__main__':main()
