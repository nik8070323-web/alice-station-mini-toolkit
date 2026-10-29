"""Read-only inventory via the already authenticated upstream session."""
import asyncio,time,re
class Inventory:
    def __init__(self,hass,names,target):self.hass=hass;self.names=names;self.canonical={' '.join(n.split()).casefold():n for n in names};self.target=target;self.cache={};self.rows=[];self.lock=asyncio.Lock();self.checked=0
    async def refresh(self):
        if self.lock.locked():return
        async with self.lock:
            speakers=self.hass.data.get('yandex_station',{}).get('speakers',{})
            entity=next((x.get('entity') for x in speakers.values() if x.get('entity') is not None and x['entity'].entity_id==self.target),None)
            if entity is None:return
            quasar=entity.quasar
            await quasar.load_scenarios()
            candidates=[dict(x,name=self.canonical[' '.join(x['name'].split()).casefold()]) for x in quasar.scenarios if ' '.join(x.get('name','').split()).casefold() in self.canonical]
            counts={x['name']:sum(y.get('name')==x['name'] for y in candidates) for x in candidates}
            rows=[]
            for candidate in candidates:
                sid=candidate['id']
                if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',sid):raise ValueError('Invalid scenario identifier')
                cached=self.cache.get(sid)
                if cached and time.monotonic()-cached[0]<120:row=dict(cached[1])
                else:
                    r=await quasar.session.get(f'https://iot.quasar.yandex.ru/m/v4/user/scenarios/{sid}/edit')
                    definition=(await r.json())['scenario'];actions=[];phrases=[]
                    for t in definition.get('triggers',[]):
                        t=t.get('trigger',t)
                        if t.get('type')=='scenario.trigger.voice' and isinstance(t.get('value'),str):phrases.append(t['value'][:160])
                    def walk(x):
                        if isinstance(x,dict):
                            if 'id' in x and isinstance(x.get('capabilities'),list):
                                for cap in x['capabilities']:actions.append((x['id'],cap))
                            for v in x.values():walk(v)
                        elif isinstance(x,list):
                            for v in x:walk(v)
                    walk(definition.get('steps',[]))
                    valid=False
                    if len(actions)==1:
                        device,cap=actions[0];state=cap.get('state') or {};value=state.get('value')
                        valid=device==entity.device['id'] and cap.get('type')=='devices.capabilities.quasar.server_action' and state.get('instance')=='text_action' and isinstance(value,str) and value.strip().casefold()=='ничего не делай'
                    row={'scenario_id':sid,'name':candidate['name'],'entity_id':self.target,'phrase':phrases[0] if phrases else '',
                        'usable':bool(valid and phrases and candidate.get('is_active',True) is not False),'error':None if valid and phrases else 'Check Mini, voice condition and fixed action marker'}
                    self.cache[sid]=(time.monotonic(),row)
                    await asyncio.sleep(.1)
                if counts[candidate['name']]!=1:row.update(usable=False,error='Duplicate scenario name')
                rows.append(row)
            self.rows=rows;self.checked=time.time()
    def resolve(self,name):
        rows=[r for r in self.rows if r['name']==name and r['usable']]
        return rows[0] if len(rows)==1 else None
