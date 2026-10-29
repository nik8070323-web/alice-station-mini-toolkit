import json,subprocess,time,sys
for _ in range(15):
    try:
        p=subprocess.run(['hyprctl','monitors','-j'],capture_output=True,timeout=2)
        if p.returncode==0 and json.loads(p.stdout):sys.exit(0)
    except Exception:pass
    time.sleep(1)
sys.exit(1)
