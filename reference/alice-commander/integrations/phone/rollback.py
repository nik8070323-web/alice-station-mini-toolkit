"""Restore only the phone extension's integration edits; refuse overwriting later edits."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    backup=Path((ROOT/'data/phone/implementation-backup').read_text());manifest=json.loads((backup/'manifest.json').read_text())
    for rel,entry in manifest.items():
        if digest(backup/rel)!=entry['before']:raise SystemExit('Backup checksum mismatch: '+rel)
        if digest(ROOT/rel)!=entry.get('installed'):raise SystemExit('File changed after phone install; manual merge needed: '+rel)
    cli=Path.home()/'.local/bin/alice-phone';cli_hash=(backup/'cli.sha256').read_text().strip()
    if cli.exists() and digest(cli)!=cli_hash:raise SystemExit('CLI changed; refusing overwrite')
    if a.check_only:print('Backup and installed checksums valid; rollback ready.');return
    subprocess.run(['/usr/bin/python3','-m','integrations.phone.cli','disable'],cwd=ROOT,check=True)
    for rel in manifest:shutil.copy2(backup/rel,ROOT/rel)
    retired=backup/'retired-extension';retired.mkdir(exist_ok=True,mode=0o700)
    if cli.exists():cli.rename(retired/'alice-phone')
    # Move, rather than delete, all created extension files and trust state.
    # Pairing, ADB keys, packages and firewall remain intact.
    for rel in ('tests/test_phone.py','scripts/check_phone_ui.py','config/phone.json',
                'PHONE_SETUP.md','PHONE_COMMANDS.md','data/phone','integrations/phone'):
        source=ROOT/rel
        if source.exists():
            target=retired/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(source),str(target))
    subprocess.run(['systemctl','--user','restart','alice-commander.service'],check=True)
    subprocess.run(['docker','restart','alice-commander-ha'],check=True)
    print('Phone Control detached. Commander, HA and other scenarios retained. See RECOVERY.md for optional LAN firewall cleanup.')
if __name__=='__main__':main()
