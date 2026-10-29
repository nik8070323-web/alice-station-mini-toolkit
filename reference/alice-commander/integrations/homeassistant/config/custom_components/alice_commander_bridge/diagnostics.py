"""Read only the configured test scenario; never writes cloud configuration."""
import json
from pathlib import Path

async def inspect_scenario(hass):
    output={'scenario_name':'Компьютерный режим','accounts':[]}
    for quasar in list(hass.data.get('yandex_station',{}).values()):
        if not hasattr(quasar,'session') or not hasattr(quasar,'load_scenarios'):continue
        info={}
        try:
            await quasar.load_scenarios()
            candidates=[x for x in quasar.scenarios if x.get('name','').strip().casefold()=='компьютерный режим']
            info['matching_count']=len(candidates)
            info['cloud_task_running']=quasar.updates_task is not None and not quasar.updates_task.done()
            info['similar_names']=[x['name'] for x in quasar.scenarios if 'комп' in x.get('name','').casefold()][:8]
            info['scenarios']=[]
            mini_ids={s['id'] for s in quasar.speakers if s.get('quasar_info',{}).get('platform')=='yandexmini'}
            for candidate in candidates:
                r=await quasar.session.get(f"https://iot.quasar.yandex.ru/m/v4/user/scenarios/{candidate['id']}/edit")
                raw=await r.json();scenario=raw.get('scenario',{})
                entry={'name':scenario.get('name'),'triggers':[], 'actions':[]}
                for t in scenario.get('triggers',[]):
                    t=t.get('trigger',t);value=t.get('value')
                    entry['triggers'].append({'type':t.get('type'),'expected_phrase':isinstance(value,str) and value.strip().casefold()=='компьютерный режим'})
                def walk(x):
                    if isinstance(x,dict):
                        if isinstance(x.get('capabilities'),list):
                            for cap in x['capabilities']:
                                state=cap.get('state') or {}
                                entry['actions'].append({'target_is_mini':x.get('id') in mini_ids,'capability':cap.get('type'),'instance':state.get('instance'),'expected_marker':state.get('value')=='ничего не делай'})
                        for value in x.values():walk(value)
                    elif isinstance(x,list):
                        for value in x:walk(value)
                walk(scenario.get('steps',[]));info['scenarios'].append(entry)
        except Exception as e:info['error']=type(e).__name__
        output['accounts'].append(info)
    await hass.async_add_executor_job(lambda:Path('/config/commander-scenario-diagnostic.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)))
