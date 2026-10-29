#!/usr/bin/env python3
"""CLI for the loopback-only Alice RGB notification agent."""
import argparse, json, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'data/config.json').read_text())
TOKEN = (ROOT / 'data/token').read_text().strip()
URL = f"http://127.0.0.1:{CONFIG['listen_port']}"

def call(path, payload=None):
    raw = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(URL + path, data=raw, method='GET' if raw is None else 'POST',
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            result = json.loads(response.read() or b'{}')
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}")
        return 1
    except Exception as exc:
        print(f"RGB agent unavailable: {type(exc).__name__}: {exc}")
        return 1

def main():
    p = argparse.ArgumentParser(prog='alice-notify')
    sub = p.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('notify'); n.add_argument('event', choices=['success','error','warning','info','status'])
    sub.add_parser('status')
    sub.add_parser('stop')
    n = sub.add_parser('package'); n.add_argument('id', choices=['purple-ring','rainbow-ring','breathing-ring','notification-success','notification-error','night-mode','mini-system-monitor'])
    e = sub.add_parser('effects'); e.add_argument('action', choices=['enable','disable','status','violet','blue','preview'])
    e.add_argument('effect', nargs='?', choices=['activation','thinking','response','error','idle','check','rainbow','static','breathing','rotation','wave','pulse'])
    a = p.parse_args()
    if a.cmd == 'stop': return call('/v1/stop', {})
    if a.cmd == 'package': return call('/v1/package', {'package':a.id})
    if a.cmd == 'status': return call('/v1/status')
    if a.cmd == 'notify': return call('/v1/status') if a.event == 'status' else call('/v1/notify', {'event':a.event})
    if a.action == 'status': return call('/v1/status')
    if a.action == 'enable': return call('/v1/effects', {'enabled':True})
    if a.action == 'disable': return call('/v1/effects', {'enabled':False})
    if a.action == 'violet': return call('/v1/effects', {'palette':'violet'})
    if a.action == 'blue': return call('/v1/effects', {'palette':'blue'})
    if a.action == 'preview': return call('/v1/preview', {'event':a.effect or 'activation'})
    return 2

if __name__ == '__main__': raise SystemExit(main())
