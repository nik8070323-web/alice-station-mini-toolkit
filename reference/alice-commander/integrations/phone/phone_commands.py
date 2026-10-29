import asyncio,time,json
from .phone_state import ROOT,DATA,config,require_enabled,read,outcome,reserve
from .security import run
from . import kdeconnect,adb_manager,scrcpy_manager
ROWS=[
('phone.connect','подключи телефон','Телефон Подключить'),
('phone.mirror','покажи телефон','Телефон Экран'),('phone.mirror.stop','отключи трансляцию телефона','Телефон Остановить экран'),
('phone.find.notifications','покажи уведомления телефона','Телефон Уведомления'),('phone.battery','сколько заряда на телефоне','Телефон Заряд'),
('phone.share.link','отправь ссылку на телефон','Телефон Ссылка'),('phone.share.file','отправь файл на телефон','Телефон Файл'),
('phone.lock','заблокируй телефон','Телефон Блокировка'),('phone.disconnect','отключи телефон','Телефон Отключить')]
IDS={row[0] for row in ROWS}
async def dialog(kind):
    await kdeconnect.trusted();reserve('dialog',10)
    await run(['/usr/bin/systemd-run','--user','--quiet','--collect','--unit=alice-phone-dialog-'+str(time.time_ns()),'--description=Alice Phone Control owned dialog','--property=Type=exec','--property=StandardOutput=null','--property=StandardError=null','--working-directory='+str(ROOT),'--','/usr/bin/python3','-m','integrations.phone.dialog',kind])
    return {'state':'Открыто локальное окно. Завершите выбор/подтверждение на ПК; передача пока не подтверждена.'}
async def stop_dialogs():
    units=json.loads(await run(['/usr/bin/systemctl','--user','list-units','--all','--output=json','alice-phone-dialog-*.service','alice-phone-pairing.service']))
    for unit in units:
        if unit.get('description') in ('Alice Phone Control owned dialog','Alice Phone Control owned pairing'):
            await run(['/usr/bin/systemctl','--user','stop',unit['unit']])
async def execute(cid):
    if cid not in IDS:raise ValueError('Неизвестная команда Phone Control')
    require_enabled()
    try:
        if cid=='phone.connect':
            result=await kdeconnect.refresh()
            try:result['adb']=await adb_manager.reconnect()
            except (ValueError,RuntimeError):result['adb']='offline'
        elif cid=='phone.battery':result=await kdeconnect.battery()
        elif cid=='phone.mirror':result=await scrcpy_manager.start()
        elif cid=='phone.mirror.stop':result=await scrcpy_manager.stop()
        elif cid=='phone.find.notifications':result=await dialog('notifications')
        elif cid=='phone.share.link':result=await dialog('link')
        elif cid=='phone.share.file':result=await dialog('file')
        elif cid=='phone.lock':
            # This real Android does not advertise the official lockdevice capability.
            raise ValueError('Блокировка телефона не поддерживается подтверждённым API этого Android; ADB-подмена запрещена')
        elif cid=='phone.disconnect':
            await scrcpy_manager.stop()
            await stop_dialogs()
            c=config()
            if c.get('adb'):
                try:await adb_manager.disconnect()
                except (ValueError,RuntimeError):pass
            result={'state':'Отображение остановлено; сопряжение KDE Connect сохранено'}
        outcome(cid,True);return result
    except BaseException:
        outcome(cid,False);raise
_CACHE={};_STAMP=0;_LOCK=asyncio.Lock()
async def status():
    global _CACHE,_STAMP
    if time.monotonic()-_STAMP<8:return {**_CACHE,'last_result':read(DATA/'last.json')}
    async with _LOCK:
        c=config();out={'enabled':bool(c.get('enabled')) and not (DATA/'disabled').exists(),'name':c.get('label','Телефон не выбран'),'connected':False,'kdeconnect':'Нет соединения','adb':'Не настроен','scrcpy':False,'battery_percent':None,'ip':None,'lock_supported':False,'last_result':read(DATA/'last.json')}
        if out['enabled']:
            try:
                await kdeconnect.trusted();out.update(connected=True,kdeconnect='Сопряжён, LAN')
                out['ip']=', '.join(await kdeconnect.addresses())
                try:out.update(await kdeconnect.battery())
                except Exception:pass
            except Exception:pass
            try:out['scrcpy']=(await scrcpy_manager.state())['running']
            except Exception:pass
            if c.get('adb'):
                try:
                    await adb_manager.trusted();out['adb']='Подключён'
                    out['android']=c['adb'].get('android')
                except Exception:out['adb']='Недоступен'
        _CACHE=out;_STAMP=time.monotonic();return out
