"""V2 validates stable scenario and launch identities, not speech text."""
import math,re
from voice.scenarios import SCENARIOS
ID=re.compile(r'[A-Za-z0-9_-]{1,128}')
def identity(value):return isinstance(value,str) and bool(ID.fullmatch(value))
def fresh(stamp,now,limit=8):return not isinstance(stamp,bool) and isinstance(stamp,(int,float)) and math.isfinite(stamp) and -2<=now-stamp<=limit

def validate_v2(message,entity,bindings,now):
    if not isinstance(message,dict) or set(message)!={'kind','token','event_type','event_id','time_fired','data','from_integration','scenario_id','launch_id','launch_time'}:raise ValueError('schema')
    if message['kind']!='event' or message['event_type']!='yandex_scenario' or message['from_integration'] is not True:raise ValueError('event_source')
    if not identity(message['event_id']) or not identity(message['scenario_id']) or not identity(message['launch_id']):raise ValueError('identifiers')
    if not fresh(message['time_fired'],now) or not fresh(message['launch_time'],now,12):raise ValueError('stale_event')
    d=message['data']
    if not isinstance(d,dict) or set(d)!={'scenario_name','entity_id','instance','value'}:raise ValueError('event_fields')
    if not entity or d['entity_id']!=entity:raise ValueError('station_not_bound')
    binding=bindings.get(message['scenario_id'])
    if not binding or binding['entity_id']!=entity or binding['name']!=d['scenario_name']:raise ValueError('scenario_id_not_bound')
    if SCENARIOS.get(d['scenario_name'])!=binding['command_id']:raise ValueError('scenario_mapping')
    if d['instance']!='text_action' or not isinstance(d['value'],str) or d['value'].strip().casefold()!='ничего не делай':raise ValueError('action_not_allowed')
    return binding['command_id']
