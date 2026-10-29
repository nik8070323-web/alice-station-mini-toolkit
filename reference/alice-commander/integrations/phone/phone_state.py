import json,os,time,secrets
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/phone'
CONFIG=ROOT/'config/phone.json'
def read(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {} if default is None else default

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name('.'+path.name+'.'+secrets.token_hex(8)+'.tmp')
    try:
        temp.write_text(json.dumps(value,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(path)
    finally:temp.unlink(missing_ok=True)

def config():return read(CONFIG)
def require_enabled():
    c=config()
    if not c.get('enabled') or (DATA/'disabled').exists():raise ValueError('Phone Control отключён')
    return c

def reserve(key,seconds):
    # Cross-process and persistent: service restart must not reset ring cooldown.
    import fcntl
    DATA.mkdir(exist_ok=True,mode=0o700)
    with (DATA/'rate.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        p=DATA/'rate.json';state=read(p);now=time.time()
        if now-state.get(key,0)<seconds:raise ValueError('Повторите позже: ограничение частоты Phone Control')
        state[key]=now;write(p,state)

def outcome(cid,ok):
    # No URL, selected filename, notification, ADB serial or process output.
    write(DATA/'last.json',{'command_id':cid,'ok':ok,'time':time.time()})
