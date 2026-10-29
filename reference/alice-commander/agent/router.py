import asyncio,json,time
from pathlib import Path
from commands.registry import COMMANDS
from agent.desktop import Desktop,ROOT

class Router:
    def __init__(self):
        self.desktop=Desktop();self.lock=asyncio.Lock();self.last={};self.recent=[];self.last_action=None
        self.handlers={cid:(lambda key=cid:self.desktop.run(key)) for cid in COMMANDS}
        from integrations.phone.phone_commands import IDS,execute
        self.handlers.update({cid:(lambda key=cid:execute(key)) for cid in IDS})
    async def execute(self,cid,args=None):
        if not isinstance(cid,str) or cid not in COMMANDS:raise ValueError('unknown command_id')
        if args not in (None,{}):raise ValueError('arguments are not accepted')
        if (ROOT/'data/disabled').exists():raise ValueError('Commander disabled')
        if self.lock.locked():raise ValueError('another action is running')
        now=time.monotonic();self.recent=[t for t in self.recent if now-t<60]
        if now-self.last.get(cid,-100)<2 or len(self.recent)>=30:raise ValueError('rate limit')
        self.last[cid]=now;self.recent.append(now)
        async with self.lock:
            start=time.time()
            try:result={'ok':True,'result':await asyncio.wait_for(self.handlers[cid](),55)}
            except Exception as e:result={'ok':False,'error':str(e)[:500]}
            self.last_action={'time':time.time(),'command_id':cid,'response':result}
            record={'time':start,'command_id':cid,'ok':result['ok']}
            log=ROOT/'data/events.jsonl'
            if log.exists() and log.stat().st_size>1_000_000:log.replace(ROOT/'data/events.previous.jsonl')
            with log.open('a') as f:f.write(json.dumps(record)+'\n')
            return result
