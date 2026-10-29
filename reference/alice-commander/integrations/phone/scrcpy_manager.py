from .security import run
from . import adb_manager
UNIT='alice-phone-mirror.service'
MARKER='Alice Phone Control owned scrcpy'
async def state():
    raw=await run(['/usr/bin/systemctl','--user','show',UNIT,'-p','ActiveState','-p','Description'],allowed=(0,1))
    props=dict(x.split('=',1) for x in raw.splitlines() if '=' in x)
    return {'running':props.get('ActiveState') in ('active','activating'),'owned':props.get('Description')==MARKER}
async def start():
    current=await state()
    if current['running']:
        if not current['owned']:raise ValueError('Имя службы занято чужим процессом')
        return {'state':'Экран уже отображается'}
    serial=await adb_manager.trusted()
    await run(['/usr/bin/systemd-run','--user','--quiet','--collect','--unit='+UNIT,'--description='+MARKER,'--property=Type=exec','--property=StandardOutput=null','--property=StandardError=null','--','/usr/bin/scrcpy','--serial='+serial,'--no-audio','--no-clipboard-autosync','--window-title=Alice Phone Control'],timeout=10)
    import asyncio
    await asyncio.sleep(1)
    if not (await state())['running']:raise ValueError('scrcpy завершился при запуске; проверьте разрешение отладки и экран телефона')
    return {'state':'scrcpy запущен; изображение и управление нужно подтвердить физически'}
async def stop():
    current=await state()
    if current['running']:
        if not current['owned']:raise ValueError('Чужая служба не будет остановлена')
        await run(['/usr/bin/systemctl','--user','stop',UNIT])
    return {'state':'Отображение Phone Control остановлено'}
