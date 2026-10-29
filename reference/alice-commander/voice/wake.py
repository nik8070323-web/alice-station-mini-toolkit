"""Read-only by default. Own bounded coordinator job; never captures audio."""
import asyncio,json,time,uuid,os
from voice.protocol import fresh,identity
from voice.catalog import read,write
from integrations.rgb import call
class Wake:
    def __init__(self,data,config):
        self.data=data;self.config=config;self.session=None;self.sequence=-1;self.previous=None;self.active=None;self.history=[]
    async def stop(self,reason):
        if self.active is None:return
        request=self.active;self.active=None
        try:await call('/v1/wake',{'action':'stop' if reason in ('native_speaking','native_busy','native_none','native_thinking') else 'cancel','request_id':request})
        except Exception:pass
        self.record(last_stop=time.time(),stop_reason=reason,active=False)
    def record(self,**fields):
        p=self.data/'wake-state.json';state=read(p,{})
        state.update(fields);state['updated']=time.time();state['history']=self.history[-80:];write(p,state)
    async def event(self,message,entity):
        if set(message)!={'kind','token','entity_id','state','session','sequence','time'}:raise ValueError('wake_schema')
        if not entity or message['entity_id']!=entity or not fresh(message['time'],time.time(),4):raise ValueError('wake_source')
        state=message['state'];session=message['session'];seq=message['sequence']
        if state not in ('IDLE','LISTENING','SPEAKING','BUSY','NONE','THINKING') or not identity(session) or isinstance(seq,bool) or not isinstance(seq,int):raise ValueError('wake_state')
        if session!=self.session:
            await self.stop('session_changed');self.session=session;self.sequence=-1;self.previous=None
        if seq<=self.sequence:return {'ok':True,'duplicate_state':True}
        self.sequence=seq;previous=self.previous;self.previous=state
        self.history.append({'time':message['time'],'state':state});self.history=self.history[-80:]
        self.record(state=state,last_signal=time.time(),source='local Glagol aliceState',listening_observed=any(x['state']=='LISTENING' for x in self.history),speaking_observed=any(x['state']=='SPEAKING' for x in self.history))
        if state!='LISTENING':await self.stop('native_'+state.lower())
        cfg=read(self.config,{})
        proof=read(self.data/'wake-verification.json',{})
        enabled=cfg.get('wake_enabled',False) and proof.get('human_confirmed') is True
        trial=0<cfg.get('wake_trial_until',0)-time.time()<=90 and cfg.get('wake_trial_pid')==os.getpid()
        if state=='LISTENING' and previous=='IDLE' and (enabled or trial):
            request=uuid.uuid4().hex
            try:
                result=await call('/v1/wake',{'action':'start','request_id':request})
                if result.get('accepted'):self.active=request;self.record(last_start=time.time(),active=True,request_id=request)
                else:self.record(last_skip=result.get('reason','coordinator declined'))
            except Exception as e:self.record(last_error=type(e).__name__)
        return {'ok':True,'observed':True}
