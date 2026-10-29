"""Desktop-only selection/confirmation. Never export private dialog content to API/logs."""
import asyncio,sys,tempfile,os,time,signal
from pathlib import Path
from .security import run,safe_url,read_share_file,endpoint
from .phone_state import DATA,ROOT,outcome,require_enabled,write
from . import kdeconnect,adb_manager
async def prompt(*args,wait=45):
    return (await run(['/usr/bin/zenity',*args],timeout=wait)).strip()
async def confirmed(text):
    # Data goes over stdin, not process arguments readable in /proc.
    await run(['/usr/bin/zenity','--text-info','--title=Alice Phone Control',
        '--checkbox=Я проверил данные и подтверждаю отправку',
        '--ok-label=Отправить','--cancel-label=Отмена','--width=650','--height=350'],
        timeout=90,input_data=text.encode())
async def main(kind):
    require_enabled()
    cid={'file':'phone.share.file','link':'phone.share.link','notifications':'phone.find.notifications','pair':'phone.adb.setup'}[kind]
    stage='start'
    try:
        if kind=='notifications':
            did=await kdeconnect.plugin('kdeconnect_notifications')
            content=await run(['/usr/bin/kdeconnect-cli','--device',did,'--list-notifications'])
            await run(['/usr/bin/zenity','--text-info','--title=Уведомления телефона — только локально','--width=700','--height=500'],timeout=180,input_data=(content or 'Нет доступных уведомлений').encode(),allowed=(0,1,5))
        elif kind=='link':
            url=safe_url(await prompt('--entry','--title=Ссылка для телефона','--text=Вставьте ссылку, которую хотите отправить. Приватные вкладки автоматически не читаются.'))
            await confirmed('Отправить на ваш телефон эту ссылку?\n'+url)
            await kdeconnect.share(url)
        elif kind=='file':
            selected=await prompt('--file-selection','--title=Выберите файл для телефона','--filename='+str(Path.home()/'AlicePhoneShare')+'/')
            name,data=read_share_file(selected)
            await confirmed('Отправить файл '+name+' на телефон?\nУбедитесь, что он не содержит паролей, ключей и личных секретов.')
            # Snapshot prevents changing a confirmed path into another file before sending.
            # Keep the snapshot in the user's private runtime filesystem, not
            # on persistent storage if the machine loses power mid-transfer.
            runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))
            info=runtime.stat()
            if not runtime.is_dir() or info.st_uid!=os.getuid() or info.st_mode & 0o077:
                raise ValueError('Недоступен закрытый пользовательский runtime')
            with tempfile.TemporaryDirectory(prefix='alice-phone-share-',dir=runtime) as temp:
                staged=Path(temp)/name;staged.write_bytes(data);staged.chmod(0o600)
                await kdeconnect.share(staged.as_uri());outcome(cid,True)
                # KDE transfer is asynchronous; keep the private snapshot alive briefly.
                await asyncio.sleep(120)
        elif kind=='pair':
            addresses=await kdeconnect.addresses();ip=next((x for x in addresses if x.count('.')==3),None)
            address=endpoint(sys.argv[2],ip)
            stage='code_entry'
            code=await prompt('--password','--title=Код сопряжения Android','--text=Введите шестизначный код из окна «Сопряжение устройства» телефона. Код не сохраняется.',wait=180)
            if len(code)!=6 or not code.isdigit():raise ValueError('Нужен шестизначный код')
            stage='pair_request'
            answer=await run(['/usr/bin/adb','pair',address],timeout=20,input_data=(code+'\n').encode());code=''
            if 'Successfully paired' not in answer:raise ValueError('Сопряжение ADB не подтверждено')
            stage='connect_address'
            connect=endpoint(await prompt('--entry','--title=Адрес подключения ADB','--text=Закройте окно кода на телефоне. Введите IP:порт из основного экрана «Беспроводная отладка» (порт отличается).',wait=180),ip)
            stage='connect_request'
            answer=await run(['/usr/bin/adb','connect',connect],timeout=12)
            if 'connected to' not in answer:raise ValueError('ADB не подключился')
            stage='identity'
            identity=await adb_manager.identity(connect)
            stage='owner_confirmation'
            await confirmed('Доверять этому Android для scrcpy?\nМодель: '+identity['model']+'\nAndroid: '+identity['android'])
            await adb_manager.bind(connect)
        outcome(cid,True)
    except Exception as error:
        write(DATA/'dialog-error.json',{'kind':kind,'stage':stage,'error_type':type(error).__name__,'time':time.time()})
        outcome(cid,False)
        await run(['/usr/bin/zenity','--warning','--title=Alice Phone Control','--text=Операция отменена или не выполнена. Проверьте разрешения, связь и введённые данные. Секреты и содержимое не журналируются.'],timeout=30,allowed=(0,1,5))
async def supervised():
    task=asyncio.current_task();asyncio.get_running_loop().add_signal_handler(signal.SIGTERM,task.cancel)
    await main(sys.argv[1])
if __name__=='__main__':
    os.umask(0o077)
    try:asyncio.run(supervised())
    except Exception:sys.exit(1)
