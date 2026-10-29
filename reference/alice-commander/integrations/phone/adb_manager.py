import hashlib,json
from .security import run,adb_serial,endpoint
from .phone_state import config,write,CONFIG,require_enabled
async def devices():
    raw=await run(['/usr/bin/adb','devices','-l']);result={}
    for line in raw.splitlines()[1:]:
        p=line.split()
        if len(p)>=2:result[p[0]]={'state':p[1],'description':' '.join(p[2:])}
    return result
async def identity(serial):
    serial=adb_serial(serial);items=await devices();item=items.get(serial)
    if not item or item['state']!='device':raise ValueError('Разрешённое ADB-устройство недоступно; подтвердите отладку на телефоне')
    if any(x in item['description'].lower() for x in ('yandex','quasar','yandexmini','yndx')):raise ValueError('Яндекс Станция не является разрешённым телефоном')
    props={}
    for key in ('ro.product.manufacturer','ro.product.model','ro.product.device','ro.build.version.release','ro.build.version.sdk','ro.serialno'):
        props[key]=(await run(['/usr/bin/adb','-s',serial,'shell','getprop',key])).strip()
    if any(x in json.dumps(props).lower() for x in ('yandex','quasar','yndx')) or int(props.get('ro.build.version.sdk') or 0)<23:raise ValueError('Устройство не подходит для управления телефоном')
    if not props['ro.serialno']:raise ValueError('Нет стабильного идентификатора Android для проверки устройства')
    fingerprint=hashlib.sha256(json.dumps({k:v for k,v in props.items() if k not in ('ro.build.version.release','ro.build.version.sdk')},sort_keys=True).encode()).hexdigest()
    return {'fingerprint':fingerprint,'model':props['ro.product.model'],'android':props['ro.build.version.release']}
async def trusted():
    c=require_enabled();bound=c.get('adb')
    if not bound:raise ValueError('ADB ещё не сопряжён: настройте защищённую беспроводную отладку или USB')
    serial=adb_serial(bound['serial'])
    try:actual=await identity(serial)
    except ValueError:
        # Android may announce the same paired TLS device under an mDNS serial
        # after reconnect. Only use the alias captured during owner enrollment.
        alias=bound.get('mdns_alias')
        if not alias or alias==serial:raise
        actual=await identity(adb_serial(alias))
        if actual['fingerprint']!=bound['fingerprint']:raise ValueError('ADB-устройство не совпадает с доверенным телефоном')
        bound['serial']=alias;write(CONFIG,c);return alias
    if actual['fingerprint']!=bound['fingerprint']:raise ValueError('ADB-устройство не совпадает с доверенным телефоном')
    return serial
async def bind(serial):
    # Called only by explicit local owner-confirmed enrollment, never by a voice ID.
    actual=await identity(serial);c=require_enabled()
    if c.get('adb') and c['adb']['fingerprint']!=actual['fingerprint']:raise ValueError('Для замены телефона требуется отдельное локальное изменение доверия')
    bound={'serial':adb_serial(serial),**actual}
    if ':' in serial:
        # Remember only the TLS service announced at the confirmed endpoint.
        services=await run(['/usr/bin/adb','mdns','services'])
        names=[parts[0]+'._adb-tls-connect._tcp' for line in services.splitlines()
               if len(parts:=line.split())==3 and parts[1]=='_adb-tls-connect._tcp' and parts[2]==serial]
        if len(names)==1:bound['mdns_alias']=adb_serial(names[0])
    c['adb']=bound;write(CONFIG,c);return actual
async def disconnect():
    c=config();bound=c.get('adb')
    if bound and (':' in bound['serial'] or bound['serial'].endswith('._adb-tls-connect._tcp')):
        # Disconnect only a verified current transport, not every ADB device.
        serial=await trusted();await run(['/usr/bin/adb','disconnect',serial])

async def reconnect():
    """Reconnect only the already paired, previously enrolled TLS service."""
    c=require_enabled();bound=c.get('adb')
    if not bound:return 'not_configured'
    try:
        await trusted();return 'connected'
    except ValueError:pass
    alias=bound.get('mdns_alias','');suffix='._adb-tls-connect._tcp'
    if not alias.endswith(suffix):return 'offline'
    from . import kdeconnect
    addresses=await kdeconnect.addresses()
    services=await run(['/usr/bin/adb','mdns','services'])
    candidates=[]
    for line in services.splitlines():
        parts=line.split()
        if len(parts)!=3 or parts[0]+suffix!=alias or parts[1]!='_adb-tls-connect._tcp':continue
        for ip in addresses:
            try:candidates.append(endpoint(parts[2],ip))
            except ValueError:pass
    if len(set(candidates))!=1:return 'offline'
    address=candidates[0]
    try:
        response=await run(['/usr/bin/adb','connect',address],timeout=12)
        if 'connected to' not in response:return 'offline'
        actual=await identity(address)
        if actual['fingerprint']!=bound['fingerprint']:
            await run(['/usr/bin/adb','disconnect',address]);return 'offline'
        bound['serial']=address;write(CONFIG,c);return 'connected'
    except (ValueError,RuntimeError):return 'offline'
