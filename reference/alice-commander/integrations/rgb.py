"""Client of the existing coordinator. Never talks directly to LED hardware."""
import asyncio, json, urllib.request
from pathlib import Path
BASE=Path.home()/'station-mini-root/pc-notifications'

def request(path, body=None):
    config=json.loads((BASE/'data/config.json').read_text())
    token=(BASE/'data/token').read_text().strip()
    req=urllib.request.Request(f"http://127.0.0.1:{config['listen_port']}"+path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as response:
        return json.load(response)

async def call(path, body=None):
    return await asyncio.to_thread(request,path,body)

async def action(cid):
    if cid=='rgb.off':return await call('/v1/stop',{})
    if cid=='rgb.brighter':
        s=await call('/v1/status')
        return await call('/v1/effects',{'brightness_percent':min(100,s['brightness_percent']+5)})
    if cid=='rgb.night':return await call('/v1/effects',{'night_override':True})
    return await call('/v1/preview',{'effect':'rainbow' if cid=='rgb.rainbow' else 'static','color':'#8B5CF6','duration':2})
