"""V2: same HA bus, stable launch IDs, read-only inventory and local state."""
import asyncio,json,logging,time,uuid
from pathlib import Path
from datetime import datetime,timedelta
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.event import async_track_time_interval
from .inventory import Inventory
_LOGGER=logging.getLogger(__name__)
DOMAIN='alice_commander_bridge';SOCKET='/commander-voice/bridge.sock';TOKEN=Path('/commander-voice/token')

async def async_setup(hass,config):
    def settings():
        directory=Path(__file__).parent
        return set(json.loads((directory/'scenarios.json').read_text())),json.loads((directory/'settings.json').read_text())
    allowed,cfg=await hass.async_add_executor_job(settings);target=cfg['entity_id'];canonical={' '.join(n.split()).casefold():n for n in allowed}
    inventory=Inventory(hass,allowed,target);session=uuid.uuid4().hex;sequence=0;last_state=None;stopped=False
    async def send(payload):
        try:
            token=await hass.async_add_executor_job(lambda:TOKEN.read_text().strip())
            r,w=await asyncio.wait_for(asyncio.open_unix_connection(SOCKET),2)
            try:
                w.write((json.dumps({**payload,'token':token},ensure_ascii=False)+'\n').encode());await w.drain()
                result=json.loads(await asyncio.wait_for(r.readline(),8))
                if not result.get('ok'):_LOGGER.warning('Commander rejected: %s',result.get('error','action failed'))
                return result
            finally:w.close();await w.wait_closed()
        except (OSError,asyncio.TimeoutError,ValueError):_LOGGER.debug('Commander unavailable; no replay')
    def owned(entity_id):
        return entity_id==target and any(x.get('entity') is not None and x['entity'].entity_id==target for x in hass.data.get('yandex_station',{}).get('speakers',{}).values())
    async def publish_inventory(_=None):
        try:
            await inventory.refresh()
            if inventory.checked:await send({'kind':'inventory','checked_at':inventory.checked,'scenarios':inventory.rows})
        except Exception as e:
            import traceback
            frames=[(Path(x.filename).name,x.name,x.lineno) for x in traceback.extract_tb(e.__traceback__)]
            _LOGGER.warning('Scenario inventory unavailable: %s at %s',type(e).__name__,frames)
    async def event_received(event):
        d=event.data
        name=canonical.get(' '.join(str(d.get('scenario_name','')).split()).casefold())
        if name is None or not owned(d.get('entity_id')):return
        d=dict(d,scenario_name=name)
        if d.get('instance')!='text_action':return
        row=inventory.resolve(d['scenario_name'])
        if row is None:
            await publish_inventory();row=inventory.resolve(d['scenario_name'])
        if row is None:return
        try:
            launch_id=d['scenario_launch_id'];launch_time=datetime.fromisoformat(d['scenario_launch_time'].replace('Z','+00:00')).timestamp()
        except (KeyError,AttributeError,TypeError,ValueError):
            _LOGGER.warning('Missing upstream launch metadata; event not executed');return
        await send({'kind':'event','event_type':'yandex_scenario','event_id':event.context.id,'time_fired':event.time_fired.timestamp(),
            'from_integration':True,'scenario_id':row['scenario_id'],'launch_id':launch_id,'launch_time':launch_time,
            'data':{k:d.get(k) for k in ('scenario_name','entity_id','instance','value')}})
    async def observe_state(state):
        nonlocal sequence,last_state
        if state not in ('IDLE','LISTENING','SPEAKING','BUSY','NONE','THINKING') or state==last_state:return
        sequence+=1;last_state=state
        await send({'kind':'wake_state','entity_id':target,'state':state,'session':session,'sequence':sequence,'time':time.time()})
    async def state_changed(event):
        if event.data.get('entity_id')!=target or not owned(target):return
        state=event.data.get('new_state')
        if state is not None:await observe_state(state.attributes.get('alice_state'))
    async def heartbeat(_=None):
        values=hass.data.get('yandex_station',{}).get('speakers',{}).values();speakers=[]
        for x in values:
            entity=x.get('entity')
            if entity is not None and entity.entity_id:speakers.append({'entity_id':entity.entity_id,'platform':entity.device_platform})
        await send({'kind':'heartbeat','integration_loaded':bool(speakers),'speakers':speakers})
        state=hass.states.get(target)
        if state:await observe_state(state.attributes.get('alice_state'))
    removes=[hass.bus.async_listen('yandex_scenario',event_received),hass.bus.async_listen('state_changed',state_changed),
        async_track_time_interval(hass,heartbeat,timedelta(seconds=10)),async_track_time_interval(hass,publish_inventory,timedelta(seconds=30))]
    def stop(_):
        nonlocal stopped
        stopped=True
        for remove in removes:remove()
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP,stop)
    async def startup():
        for _ in range(30):
            if stopped:return
            await heartbeat()
            if owned(target):await publish_inventory();return
            await asyncio.sleep(2)
    hass.async_create_task(startup())
    return True
