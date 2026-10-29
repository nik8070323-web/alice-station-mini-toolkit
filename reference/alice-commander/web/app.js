'use strict';
let token='',running=false,lastActionTime=0;
const el=id=>document.getElementById(id),pretty=x=>JSON.stringify(x,null,2);
async function api(path,body){const r=await fetch('/api/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const x=await r.json();if(!r.ok)throw Error(pretty(x));return x;}
const tabs={home:'Главная',commands:'Commands',rgb:'RGB',phone:'Phone Control',voice:'Voice',automation:'Automation',logs:'Logs',settings:'Settings',recovery:'Recovery'};
for(const [id,title] of Object.entries(tabs)){const b=document.createElement('button');b.textContent=title;b.classList.toggle('active',id==='home');b.onclick=()=>{for(const k of Object.keys(tabs))el(k).hidden=k!==id;for(const x of el('nav').children)x.classList.toggle('active',x===b);};el('nav').append(b);}
function card(title,text){const d=document.createElement('div');d.className='card';const h=document.createElement('strong');h.textContent=title;const p=document.createElement('p');p.textContent=text;d.append(h,p);return d;}
function action(c,parent){const d=card(c.phrase,c.id),b=document.createElement('button');b.textContent='Запустить';b.onclick=async()=>{if(running)return;running=true;b.disabled=true;el('result').textContent='Выполняется…';try{el('result').textContent=pretty(await api('run',{command_id:c.id}));}catch(e){el('result').textContent=e.message;}finally{running=false;b.disabled=false;refresh();}};d.append(b);el(parent).append(d);}
async function refresh(){try{const s=await api('status');if(s.last_action&&s.last_action.time>lastActionTime){lastActionTime=s.last_action.time;el('result').textContent=pretty(s.last_action);}
el('connection').textContent=s.enabled?'Агент доступен':'Отключён';el('history').textContent=pretty(s.logs.slice().reverse());renderVoice(s.voice);el('config').textContent=pretty(s.settings);el('cards').replaceChildren(card('Desktop Agent',s.enabled?'Готов к локальным командам':'Отключён'),card('Компьютер','Load '+s.pc.load_average.map(x=>x.toFixed(2)).join(' / ')+' • RAM доступно '+Math.round(parseInt(s.pc.memory.MemAvailable)/1024)+' MiB'),card('Станция Mini 1',s.health.station.ok?'BetterYAM доступен':'Нет связи / повторная проверка'),card('Voice Bridge',(s.voice.enabled?'Подключён':'Ожидает подключения')+' • '+s.voice.recognized_commands_verified+' подтверждённых голосовых команд'),card('Rainbow Wake',s.voice.wake_effect_enabled?'Включён после проверки':'Автоэффект выключен'));return s;}catch(e){el('connection').textContent='Нет соединения';el('result').textContent=e.message;}}

function renderVoice(v){
 const rows=v.commands||[],summary={...v};delete summary.commands;el('voice-status').textContent=pretty(summary);
 const body=el('voice-commands').querySelector('tbody');body.replaceChildren();
 const stamp=t=>t?new Date(t*1000).toLocaleString():'—';
 for(const c of rows){
  const tr=document.createElement('tr');
  const values=[c.scenario_name+'\n'+(c.configured_phrase||c.phrase)+'\n'+c.command_id,
   c.cli_status==='unsupported_by_current_player'?'Плеер не поддерживает':c.cli_status==='not_tested'?'Не проверено':c.cli_status==='verified_phone'?'Проверено локально':'Проверено ранее',
   (c.excluded_by_user?'Не нужен по просьбе пользователя':c.scenario_created?(c.scenario_usable?'Создан, UUID привязан':'Создан, нужна проверка'):'Нужно создать')+'\n'+(c.scenarios||[]).map(x=>x.name+' / '+x.scenario_id).join('\n')+(c.scenario_error?'\n'+c.scenario_error:''),
   (c.event_received?'Событие получено':'Ещё не получено')+'\nУспех: '+stamp(c.last_success)+(c.error?'\nОшибка: '+c.error:''),
   c.physical_confirmed?'Подтверждено':'Не подтверждено'];
  for(const value of values){const td=document.createElement('td');td.textContent=value;tr.append(td);}
  const td=document.createElement('td'),b=document.createElement('button');b.textContent='Локальный тест';
  b.onclick=async()=>{b.disabled=true;try{el('result').textContent=pretty(await api('run',{command_id:c.command_id}));}catch(e){el('result').textContent=e.message;}finally{b.disabled=false;refresh();}};
  td.append(b);tr.append(td);body.append(tr);
 }
}

(async()=>{try{token=(await(await fetch('/api/session')).json()).token;const s=await refresh();for(const c of s.commands){action(c,'actions');if(c.group==='Phone Control')action(c,'phone-actions');if(c.group==='RGB')action(c,'rgb-actions');if(c.group==='Режимы')action(c,'modes');}refreshPhone();setInterval(refresh,15000);setInterval(refreshPhone,15000);}catch(e){el('result').textContent=e.message;}})();

async function refreshPhone(){try{const p=await api('phone');el('phone-status').replaceChildren(card('Телефон',p.name),card('KDE Connect',p.enabled?p.kdeconnect:'Phone Control отключён'),card('Домашняя сеть',p.ip||'Нет связи'),card('Батарея',p.battery_percent===null?'Нет данных':p.battery_percent+'%'+(p.charging?' • Заряжается':'')),card('ADB',p.adb),card('Экран',p.scrcpy?'scrcpy работает':'Трансляция остановлена'),card('Последний результат',p.last_result&&p.last_result.command_id?p.last_result.command_id+' • '+(p.last_result.ok?'Запрос выполнен':'Ошибка / отмена'):'Ещё нет'));}catch(e){el('phone-status').replaceChildren(card('Phone Control','Статус временно недоступен'));}}
