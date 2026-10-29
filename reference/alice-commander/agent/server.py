"""Small bounded asyncio HTTP server. Loopback + bearer + same-origin checks."""
import asyncio,fcntl,hmac,json,os,secrets,time,urllib.request
from pathlib import Path
from agent.router import Router
from agent.desktop import ROOT
from commands.registry import COMMANDS
from voice.bridge import status as voice_status
from integrations import rgb
PORT=8878
HOSTS={'127.0.0.1:8878','localhost:8878'}
TOKEN=ROOT/'data/token'
HEALTH={'station':{'ok':False},'homebrew':{'ok':False}}

async def monitor():
    # Read-only, bounded retry. No replay of failed commands or LED writes.
    delay=3
    def probe(url):
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=3) as r:return json.load(r)
    while True:
        config=json.loads((ROOT/'config/settings.json').read_text())
        urls={'station':config['station_url']+'/api/device','homebrew':config['station_url'].rsplit(':',1)[0]+':8088/api/status'}
        for key,url in urls.items():
            try:HEALTH[key]={'ok':True,'checked':time.time(),'data':await asyncio.to_thread(probe,url)}
            except Exception as e:HEALTH[key]={'ok':False,'checked':time.time(),'error':type(e).__name__}
        delay=15 if all(v['ok'] for v in HEALTH.values()) else min(60,delay*2)
        await asyncio.sleep(delay)

def snapshot(router):
    p=ROOT/'data/events.jsonl'
    logs=[json.loads(x) for x in p.read_text().splitlines()[-80:]] if p.exists() else []
    return {'running':True,'last_action':router.last_action,'enabled':not (ROOT/'data/disabled').exists(),'voice':voice_status(),'mode':router.desktop.mode,'health':HEALTH,'commands':list(COMMANDS.values()),'logs':logs,'settings':json.loads((ROOT/'config/settings.json').read_text()),'rgb_dashboard':'http://127.0.0.1:8877/','pc':{'load_average':os.getloadavg(),'logical_cpus':os.cpu_count(),'memory':{a:b.strip() for a,b in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines()) if a in ('MemTotal','MemAvailable')}}}

class Server:
    def __init__(self):self.router=Router();self.connections=0
    async def handle(self,r,w):
        self.connections+=1
        try:
            if self.connections>32:return
            await asyncio.wait_for(self.request(r,w),65)
        except Exception:
            pass
        finally:
            self.connections-=1;w.close()
            try:await w.wait_closed()
            except OSError:pass
    async def reply(self,w,code,data,kind='application/json; charset=utf-8'):
        raw=json.dumps(data,ensure_ascii=False).encode() if kind.startswith('application/json') else data
        reason={200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',413:'Too Large',409:'Conflict'}.get(code,'Error')
        hdr=f'HTTP/1.1 {code} {reason}\r\nContent-Type: {kind}\r\nContent-Length: {len(raw)}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Security-Policy: default-src \'self\'; script-src \'self\'; style-src \'self\'; connect-src \'self\'; frame-ancestors \'none\'; base-uri \'none\'; form-action \'none\'\r\nConnection: close\r\n\r\n'
        w.write(hdr.encode()+raw);await w.drain()
    async def request(self,r,w):
        try:
            head=await asyncio.wait_for(r.readuntil(b'\r\n\r\n'),5)
            if len(head)>8192:raise ValueError('headers too large')
            lines=head.decode('ascii').split('\r\n');method,path,version=lines[0].split(' ')
            headers={}
            for line in lines[1:]:
                if not line:continue
                k,v=line.split(':',1);k=k.lower()
                if k in headers:raise ValueError('duplicate header')
                headers[k]=v.strip()
            if headers.get('host') not in HOSTS or headers.get('origin') not in (None,*['http://'+x for x in HOSTS]):return await self.reply(w,403,{'error':'host/origin rejected'})
            if headers.get('sec-fetch-site') not in (None,'same-origin','none'):return await self.reply(w,403,{'error':'cross-site request'})
            if 'transfer-encoding' in headers:raise ValueError('transfer encoding forbidden')
            if method=='GET' and path in ('/','/app.js','/style.css'):
                name,kind={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}[path]
                return await self.reply(w,200,(ROOT/'web'/name).read_bytes(),kind)
            if method=='GET' and path=='/api/session':return await self.reply(w,200,{'token':TOKEN.read_text().strip()})
            if not hmac.compare_digest(headers.get('authorization',''),'Bearer '+TOKEN.read_text().strip()):return await self.reply(w,401,{'error':'unauthorized'})
            if method=='GET':
                if path=='/api/status':return await self.reply(w,200,snapshot(self.router))
                if path=='/api/phone':
                    from integrations.phone.phone_commands import status
                    return await self.reply(w,200,await status())
                if path=='/api/rgb':
                    try:return await self.reply(w,200,await rgb.call('/v1/status'))
                    except Exception:return await self.reply(w,409,{'error':'existing RGB coordinator unavailable'})
            if method=='POST' and path=='/api/run':
                size=int(headers.get('content-length','0'))
                if not 0<size<=2048:return await self.reply(w,413,{'error':'body limit'})
                data=json.loads(await asyncio.wait_for(r.readexactly(size),5))
                if not isinstance(data,dict) or set(data)!={'command_id'}:raise ValueError('only command_id is accepted')
                result=await self.router.execute(data['command_id'])
                return await self.reply(w,200 if result['ok'] else 409,result)
            return await self.reply(w,404,{'error':'unknown endpoint'})
        except (ValueError,KeyError,TypeError) as e:return await self.reply(w,400,{'error':str(e)[:200]})

async def main():
    os.umask(0o077)
    lock=(ROOT/'data/agent.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if not TOKEN.exists():TOKEN.write_text(secrets.token_urlsafe(32))
    TOKEN.chmod(0o600)
    server=Server();listener=await asyncio.start_server(server.handle,'127.0.0.1',PORT,limit=8192)
    monitor_task=asyncio.create_task(monitor())
    async with listener:await listener.serve_forever()
if __name__=='__main__':asyncio.run(main())
