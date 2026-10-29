import argparse,asyncio,json,sys
from .phone_state import DATA,CONFIG,config,write
from . import kdeconnect,scrcpy_manager,adb_manager
async def local(a):
    if a.command=='status':
        from .phone_commands import status
        return await status()
    if a.command=='disable':
        await scrcpy_manager.stop()
        from .phone_commands import stop_dialogs
        await stop_dialogs()
        try:await adb_manager.disconnect()
        except (ValueError,RuntimeError):pass
        (DATA/'disabled').touch(mode=0o600);return {'enabled':False,'pairing_preserved':True}
    if a.command=='enable':
        (DATA/'disabled').unlink(missing_ok=True);c=config();c['enabled']=True;write(CONFIG,c);return {'enabled':True}
    if a.command=='ping':return await kdeconnect.ping()
    if a.command=='pair':
        from .security import endpoint,run
        from .phone_state import ROOT
        addresses=await kdeconnect.addresses()
        accepted=[]
        for ip in addresses:
            try:accepted.append(endpoint(a.endpoint,ip))
            except ValueError:pass
        if len(set(accepted))!=1:raise ValueError('Адрес должен принадлежать доверенному телефону в домашней сети')
        await run(['/usr/bin/systemd-run','--user','--quiet','--collect','--unit=alice-phone-pairing',
            '--description=Alice Phone Control owned pairing','--property=Type=exec','--property=StandardOutput=null',
            '--property=StandardError=null','--working-directory='+str(ROOT),'--','/usr/bin/python3','-m',
            'integrations.phone.dialog','pair',accepted[0]])
        return {'state':'Открыт локальный мастер; код вводится только в окне ПК'}
    if a.command=='bind-adb':
        if not a.confirm_owner:raise ValueError('Требуется явное подтверждение владельца --confirm-owner')
        return await adb_manager.bind(a.serial)
    from cli import call
    cid={'connect':'phone.connect','mirror':'phone.mirror','mirror-stop':'phone.mirror.stop','disconnect':'phone.disconnect','battery':'phone.battery','notifications':'phone.find.notifications','share-link':'phone.share.link','share-file':'phone.share.file','lock':'phone.lock'}[a.command]
    return await asyncio.to_thread(call,'/api/run',{'command_id':cid})
def main():
    p=argparse.ArgumentParser(description='Alice Phone Control — только доверенный Android')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('status','connect','mirror','mirror-stop','disconnect','disable','enable','ping','battery','notifications','share-link','share-file','lock'):sub.add_parser(name)
    b=sub.add_parser('bind-adb');b.add_argument('serial');b.add_argument('--confirm-owner',action='store_true')
    pair=sub.add_parser('pair',help='Открыть мастер беспроводного ADB pairing');pair.add_argument('endpoint',help='IP:порт из окна кода на Android (не сам код)')
    a=p.parse_args()
    try:
        result=asyncio.run(local(a));print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if result.get('ok') is False else 0
    except Exception as e:
        # HTTP bodies from Commander contain only sanitized phone action outcomes.
        from urllib.error import HTTPError
        if isinstance(e,HTTPError):print(e.read().decode(errors='replace'),file=sys.stderr)
        else:print('Ошибка Phone Control: '+str(e),file=sys.stderr)
        return 1
if __name__=='__main__':sys.exit(main())
