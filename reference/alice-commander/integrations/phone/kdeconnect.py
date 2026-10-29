import asyncio
from .security import run,device_id
from .phone_state import require_enabled,reserve
SERVICE='org.kde.kdeconnect'
BASE='/modules/kdeconnect/devices/'
async def dbus(path,member,*args):return (await run(['/usr/bin/qdbus6',SERVICE,path,member,*args])).strip()
async def trusted(reachable=True):
    c=require_enabled();did=device_id(c.get('kde_id'));path=BASE+did
    if await dbus(path,'org.kde.kdeconnect.device.isPaired')!='true':raise ValueError('Доверенный телефон больше не сопряжён')
    if await dbus(path,'org.kde.kdeconnect.device.type')!='phone':raise ValueError('Доверенное устройство не является телефоном')
    if reachable and await dbus(path,'org.kde.kdeconnect.device.isReachable')!='true':
        # Rediscover only through the existing KDE daemon, at most once per
        # 20 seconds; no command or file is replayed after a disconnect.
        try:
            reserve('auto_refresh',20)
            await run(['/usr/bin/kdeconnect-cli','--refresh'])
            for _ in range(3):
                await asyncio.sleep(1)
                if await dbus(path,'org.kde.kdeconnect.device.isReachable')=='true':break
        except (ValueError,RuntimeError):pass
        if await dbus(path,'org.kde.kdeconnect.device.isReachable')!='true':
            raise ValueError('Телефон недоступен: проверьте Wi-Fi и KDE Connect на Android')
    return did
async def plugin(name):
    did=await trusted();plugins=(await dbus(BASE+did,'org.kde.kdeconnect.device.loadedPlugins')).splitlines()
    if name not in plugins:raise ValueError('Телефон не предоставляет эту функцию KDE Connect')
    return did
async def refresh():
    await trusted(False)
    try:
        await trusted();return {'connected':True,'already_connected':True}
    except ValueError:
        pass
    reserve('connect',15)
    await run(['/usr/bin/kdeconnect-cli','--refresh'])
    for i in range(3):
        try:await trusted();return {'connected':True}
        except ValueError:
            if i==2:raise
            await asyncio.sleep(1)
async def battery():
    did=await plugin('kdeconnect_battery');path=BASE+did+'/battery'
    charge=int(await dbus(path,'org.kde.kdeconnect.device.battery.charge'))
    if 0<=charge<=100:
        return {'battery_percent':charge,'charging':await dbus(path,'org.kde.kdeconnect.device.battery.isCharging')=='true','battery_source':'KDE Connect'}
    # KDE sometimes reports -1 immediately after reconnect. Do not show stale
    # values; use the separately authorised and fingerprint-checked phone.
    from . import adb_manager
    try:
        serial=await adb_manager.trusted()
        raw=await run(['/usr/bin/adb','-s',serial,'shell','dumpsys','battery'])
        fields=dict(line.strip().split(':',1) for line in raw.splitlines() if ':' in line)
        charge=int(fields.get('level','-1').strip())
        if not 0<=charge<=100:raise ValueError('Недействительный уровень заряда')
        return {'battery_percent':charge,'charging':fields.get('status','').strip() in ('2','5'),'battery_source':'ADB (только чтение)'}
    except (ValueError,RuntimeError,KeyError):
        raise ValueError('Телефон ещё не передал заряд; проверьте KDE Connect и отладку') from None
async def ping():
    did=await plugin('kdeconnect_ping');await run(['/usr/bin/kdeconnect-cli','--device',did,'--ping-msg','Alice Phone Control: проверка связи'])
    return {'state':'Ping отправлен'}
async def share(value):
    did=await plugin('kdeconnect_share')
    def send():
        # Keep selected URLs and paths out of process arguments and journals.
        import dbus
        obj=dbus.SessionBus().get_object(SERVICE,BASE+did+'/share')
        obj.get_dbus_method('shareUrl','org.kde.kdeconnect.device.share')(value,timeout=10)
    try:await asyncio.wait_for(asyncio.to_thread(send),12)
    except Exception:raise RuntimeError('KDE Connect не принял запрос передачи') from None
async def addresses():
    did=await trusted();return (await dbus(BASE+did,'org.kde.kdeconnect.device.reachableAddresses')).splitlines()
