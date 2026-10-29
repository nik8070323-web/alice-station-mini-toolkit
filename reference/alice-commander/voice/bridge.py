"""Read-only live status. Verification is recorded only after a human test."""
import json,time
from commands.registry import COMMANDS
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def status():
    base={'enabled':False,'source':None,'recognized_commands_verified':0,
        'wake_verified':False,'wake_effect_enabled':False,
        'reason':'No verified local wake event; scenario bridge awaiting setup.'}
    data=ROOT/'data/voice';state=data/'state.json';config=ROOT/'config/scenario-bridge.json'
    try:
        live=json.loads(state.read_text());cfg=json.loads(config.read_text())
        fresh=time.time()-live.get('last_heartbeat',0)<35 and (data/'bridge.sock').exists()
        enabled=fresh and live.get('enabled',False) and cfg.get('enabled',False) and bool(cfg.get('entity_id')) and not (data/'disabled').exists() and not (ROOT/'data/disabled').exists()
        base.update(source='home_assistant:yandex_scenario',enabled=bool(enabled),stage=live.get('stage'),
            home_assistant_alive=fresh,integration_loaded=live.get('integration_loaded',False),
            entity_id=cfg.get('entity_id'),scenario_name='Компьютерный режим',allowed_command='rgb.rainbow',allowed_commands_count=len(COMMANDS) if cfg.get('expanded') else 1,
            last_real_event=live.get('last_real_event'),last_dispatch_ok=live.get('last_dispatch_ok'),
            reason='Scenario events only; automatic wake RGB remains disabled.')
        observation=data/'wake-observation.json'
        if observation.exists():
            observed=json.loads(observation.read_text()).get('states',[])
            enums={x.get('alice_state') for x in observed}
            base.update(wake_source_candidate='local Glagol aliceState',listening_state_observed='LISTENING' in enums,response_state_observed='SPEAKING' in enums)
        v=json.loads((data/'verification.json').read_text()) if (data/'verification.json').exists() else {}
        if v.get('human_confirmed') is True and v.get('command_id')=='rgb.rainbow' and v.get('event_hash'):
            base['recognized_commands_verified']=1
        from voice.catalog import snapshot,read
        rows=snapshot(ROOT);base['commands']=rows
        base['recognized_commands_verified']=sum(bool(x.get('physical_confirmed')) for x in rows)
        base['scenarios_created_count']=sum(len(x.get('scenario_ids',[])) for x in rows)
        base['commands_with_scenario']=sum(bool(x.get('scenario_usable')) for x in rows)
        base['inventory_checked']=live.get('inventory_checked')
        base['protocol']=live.get('protocol',1)
        wake=read(data/'wake-state.json',{});base['wake']=wake
        base['wake_physical_test']=read(data/'wake-verification.json',{})
        base['inventory_stale']=time.time()-live.get('inventory_checked',0)>150
        base['wake_effect_enabled']=bool(cfg.get('wake_enabled') and read(data/'wake-verification.json',{}).get('human_confirmed'))
        return base
    except (OSError,ValueError,TypeError):return base
