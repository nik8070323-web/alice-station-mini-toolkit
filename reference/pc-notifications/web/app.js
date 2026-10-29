'use strict';
let token='',pixels=Array(6).fill('#8B5CF6'),selected=-1,effect='static',pending=false;
const $=id=>document.getElementById(id);
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(d.error||d.reason||'HTTP '+r.status);return d;}
function message(s){$('message').textContent=s;}
function render(){const ring=$('ring');ring.replaceChildren();const radius=ring.clientWidth/2;pixels.forEach((c,i)=>{const dot=document.createElement('div');dot.className='dot';const a=(i/6*Math.PI*2)-Math.PI/2;dot.style.left=(radius+Math.cos(a)*radius-11)+'px';dot.style.top=(radius+Math.sin(a)*radius-11)+'px';dot.style.background=c;dot.style.boxShadow='0 0 24px '+c;ring.append(dot);const b=$('pixels').children[i];b.style.borderColor=c;b.classList.toggle('selected',selected===i);});$('hex').textContent=$('color').value.toUpperCase();}
function color(c){$('color').value=c;$('hex').textContent=c.toUpperCase();if(selected<0)pixels.fill(c);else pixels[selected]=c;render();}
for(let i=0;i<6;i++){const b=document.createElement('button');b.textContent=i+1;b.setAttribute('aria-label','Светодиод '+(i+1));b.onclick=()=>{selected=i;$('color').value=pixels[i];render();};$('pixels').append(b);}
$('all').onclick=()=>{selected=-1;render();};$('color').oninput=e=>color(e.target.value);
const wheel=$('wheel'),ctx=wheel.getContext('2d'),size=240,cx=size/2;
function hsv(h,s){let f=n=>{let k=(n+h*6)%6;return Math.round(255*(1-s*Math.max(0,Math.min(k,4-k,1))));};return '#'+[f(5),f(3),f(1)].map(x=>x.toString(16).padStart(2,'0')).join('');}
const image=ctx.createImageData(size,size);for(let y=0;y<size;y++)for(let x=0;x<size;x++){let dx=x-cx,dy=y-cx,r=Math.hypot(dx,dy)/cx;if(r>1)continue;let c=hsv((Math.atan2(dy,dx)/(2*Math.PI)+1)%1,r),i=(y*size+x)*4;image.data[i]=parseInt(c.slice(1,3),16);image.data[i+1]=parseInt(c.slice(3,5),16);image.data[i+2]=parseInt(c.slice(5,7),16);image.data[i+3]=255;}ctx.putImageData(image,0,0);
function pick(e){let b=wheel.getBoundingClientRect(),x=(e.clientX-b.left)/b.width*size-cx,y=(e.clientY-b.top)/b.height*size-cx,r=Math.hypot(x,y)/cx;if(r<=1)color(hsv((Math.atan2(y,x)/(2*Math.PI)+1)%1,r));}
wheel.onpointerdown=e=>{wheel.setPointerCapture(e.pointerId);pick(e);};wheel.onpointermove=e=>{if(e.buttons)pick(e);};
document.querySelectorAll('[data-effect]').forEach(b=>b.onclick=()=>{effect=b.dataset.effect;document.querySelectorAll('[data-effect]').forEach(x=>x.classList.toggle('selected',x===b));});
$('duration').oninput=()=>{$('durationValue').textContent=$('duration').value+' с';};
$('brightness').oninput=()=>{$('brightnessValue').textContent=$('brightness').value+'%';};
$('brightness').onchange=()=>api('/v1/effects',{brightness_percent:Number($('brightness').value)}).catch(e=>message(e.message));
$('play').onclick=async()=>{try{await api('/v1/preview',{effect,pixels,brightness:Number($('brightness').value),duration:Number($('duration').value)});message('Превью отправлено на колонку');}catch(e){message(e.message);}};
$('stop').onclick=()=>api('/v1/stop',{}).then(()=>message('Эффект останавливается')).catch(e=>message(e.message));
for(const [id,key] of [['enabled','enabled'],['nightSchedule','night_schedule_enabled'],['night','night_override'],['notifications','notifications_enabled']])$(id).onchange=()=>api('/v1/effects',{[key]:$(id).checked}).catch(e=>message(e.message));
document.querySelectorAll('[data-notify]').forEach(b=>b.onclick=()=>api('/v1/notify',{event:b.dataset.notify}).then(()=>message('Уведомление отправлено')).catch(e=>message(e.message)));
async function refresh(){if(pending)return;pending=true;try{const s=await api('/v1/status');$('connection').textContent=s.device.ok?'● MINI НА СВЯЗИ':'○ НЕТ СВЯЗИ';$('enabled').checked=s.effects_enabled;$('notifications').checked=s.notifications_enabled;$('night').checked=s.night_override;$('nightSchedule').checked=s.night_schedule_enabled;$('last').textContent=(s.busy?'Эффект выполняется · ':s.night_active?'Ночной лимит активен · ':'')+(s.last_result.state||'idle')+(s.last_result.error?' · '+s.last_result.error:'');}catch(e){$('connection').textContent='○ АГЕНТ НЕДОСТУПЕН';}finally{pending=false;}}
(async()=>{try{token=(await (await fetch('/v1/session')).json()).token;const s=await api('/v1/status');$('brightness').value=s.brightness_percent;$('brightnessValue').textContent=s.brightness_percent+'%';render();await refresh();const sensors=await api('/v1/sensors');$('sensor').textContent=sensors.map(s=>s.kind+': '+s.value+' '+s.unit).join(', ');setInterval(refresh,2500);}catch(e){message(e.message);}})();
