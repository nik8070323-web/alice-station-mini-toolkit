from .security import run,device_id
from .kdeconnect import dbus,BASE
async def paired_phones():
    # Explicit local enrollment only; never automatically selects a discovered peer.
    ids=(await run(['/usr/bin/kdeconnect-cli','--list-available','--id-only'])).splitlines();result=[]
    for did in ids:
        device_id(did)
        if await dbus(BASE+did,'org.kde.kdeconnect.device.type')=='phone':
            result.append({'id':did,'name':await dbus(BASE+did,'org.kde.kdeconnect.device.name')})
    return result
