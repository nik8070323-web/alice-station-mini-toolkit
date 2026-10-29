import asyncio,os,re,signal,stat,ipaddress
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl

async def run(argv,timeout=8,input_data=None,allowed=(0,)):
    p=await asyncio.create_subprocess_exec(*argv,stdin=asyncio.subprocess.PIPE if input_data is not None else asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
    async def collect():
        if input_data is not None:
            p.stdin.write(input_data);await p.stdin.drain();p.stdin.close()
        out=bytearray()
        while chunk:=await p.stdout.read(4096):
            if len(out)+len(chunk)>262144:raise ValueError('Ответ инструмента превышает лимит')
            out.extend(chunk)
        await p.wait();return out.decode(errors='replace')
    try:out=await asyncio.wait_for(collect(),timeout)
    except BaseException:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        await p.wait();raise
    if p.returncode not in allowed:raise RuntimeError('Локальный инструмент не выполнил запрос; проверьте подключение и разрешения')
    return out

def device_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}',value):raise ValueError('Некорректный идентификатор телефона')
    return value

def adb_serial(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:\-]{0,180}',value) or any(x in value.lower() for x in ('yandex','quasar','192.168.1.123')):raise ValueError('ADB-устройство не разрешено')
    return value

def endpoint(value,phone_ip):
    try:host,port=value.rsplit(':',1);ip=ipaddress.ip_address(host);port=int(port)
    except (ValueError,AttributeError):raise ValueError('Нужен IPv4:порт из окна беспроводной отладки')
    if ip.version!=4 or not ip.is_private or host!=phone_ip or host=='192.168.1.123' or not 1024<=port<=65535 or port==5555:raise ValueError('Разрешён только адрес доверенного телефона и порт защищённой отладки, не 5555')
    return f'{host}:{port}'

def safe_url(value):
    if not isinstance(value,str) or len(value)>2048 or any(ord(x)<32 for x in value):raise ValueError('Некорректная ссылка')
    u=urlsplit(value)
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password:raise ValueError('Разрешены только обычные HTTP(S)-ссылки без пароля')
    if any(re.search(r'token|password|secret|auth|signature|api.?key|^code$',k,re.I) for k,v in parse_qsl(u.query)):raise ValueError('Ссылка содержит параметры доступа; передача запрещена')
    return value

DENIED=re.compile(r'(secret|credential|password|token|id_rsa|id_ed25519|\.env|keystore|wallet)',re.I)
EXTENSIONS={'.txt','.csv','.pdf','.png','.jpg','.jpeg','.webp','.gif','.mp3','.mp4','.zip'}
def safe_file(path,home=None):
    home=Path.home() if home is None else Path(home)
    p=Path(path).expanduser();resolved=p.resolve(strict=True)
    roots=[home/x for x in ('Downloads','Documents','Pictures','AlicePhoneShare')]
    if not any(resolved.is_relative_to(x) for x in roots):raise ValueError('Выберите файл в Downloads, Documents, Pictures или AlicePhoneShare')
    # No hidden directories, symlink traversal, credential names or executable/system types.
    if p.absolute()!=resolved or any(x.startswith('.') or DENIED.search(x) for x in resolved.relative_to(home).parts):raise ValueError('Секретные, скрытые файлы и символические ссылки запрещены')
    if resolved.suffix.lower() not in EXTENSIONS or resolved.suffix.lower()=='.zip':raise ValueError('Этот тип файла не разрешён; архивы могут содержать секреты')
    info=resolved.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_size>25*1024*1024:raise ValueError('Нужен обычный пользовательский файл до 25 MiB')
    return resolved

def read_share_file(path):
    p=safe_file(path)
    # Traverse beneath the home directory with O_NOFOLLOW at every component.
    directory=os.open(Path.home(),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parts=p.relative_to(Path.home()).parts
        for part in parts[:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=nxt
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
    finally:os.close(directory)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_size>25*1024*1024:raise ValueError('Файл изменился')
        with os.fdopen(fd,'rb',closefd=False) as f:data=f.read(25*1024*1024+1)
    finally:os.close(fd)
    if len(data)>25*1024*1024:raise ValueError('Файл слишком большой')
    if any(x in data for x in (b'PRIVATE KEY-----',b'"refresh_token"',b'"access_token"',b'aws_secret_access_key',b'ghp_',b'sk-proj-')):raise ValueError('В файле обнаружены признаки секретов')
    return p.name,data
