/* Extension-owned execution policy. The model proposes; the worker gates. */
import './coverage.js';
const DEFAULT_BACKEND='https://positive-tranquility-production-9fdc.up.railway.app';
const SESSION_STEPS=900, STALL_LIMIT=6, NAV_BUDGET=8;
const state={running:false,stopRequested:false,tabId:null,steps:0,questions:0,cost:0,progress:'',log:[]};
let coverage=new AssignmentCoverage.Coverage(), decisionAbort=null;
let refMap=new Map(), frameIds=[0], activeFrameIds=[],runOrigin='',actionFrameId=0;
async function settings(){const s=await chrome.storage.local.get(['backend','token','model','note','advance','auto_submit','badges']);return {backend:(s.backend||DEFAULT_BACKEND).replace(/\/+$/,''),token:s.token||'',model:s.model||'',note:s.note||'',advance:s.advance===true,auto_submit:s.auto_submit===true,badges:s.badges!==false};}
function snapshot(){return {running:state.running,steps:state.steps,questions:state.questions,cost:state.cost,progress:state.progress};}
function emit(entry){const row={time:new Date().toLocaleTimeString(),...entry};state.log.push(row);if(state.log.length>300)state.log.shift();chrome.runtime.sendMessage({type:'log',row,state:snapshot()}).catch(()=>{});}
async function injectAll(tabId){const results=await chrome.scripting.executeScript({target:{tabId,allFrames:true},files:['content.js']});frameIds=results.map(r=>r.frameId);await Promise.all(frameIds.map(frameId=>chrome.tabs.sendMessage(tabId,{type:'reset'},{frameId}).catch(()=>{})));return frameIds;}
async function observeAllFrames(tabId){
  const merged={elements:[],text:'',host:'',digest:'',warnings:[],part_tabs:[],question_hint:''};
  refMap=new Map();activeFrameIds=[];let next=1;
  for(const frameId of frameIds){
    let page;try{page=await chrome.tabs.sendMessage(tabId,{type:'observe'},{frameId});}catch{merged.warnings.push('Frame '+frameId+' unavailable; re-open the page if required content is missing.');continue;}
    if(!page)continue;
    if(runOrigin&&page.origin!==runOrigin){merged.warnings.push('A different-origin frame is excluded from control.');continue;}
    activeFrameIds.push(frameId);merged.host ||= page.host;
    merged.text+=(merged.text?'\n\n':'')+page.text;
    merged.digest+=JSON.stringify([frameId,page.digest]);
    merged.warnings.push(...(page.warnings||[]));
    if(page.question_hint)merged.question_hint+=frameId+':'+page.question_hint;
    merged.part_tabs.push(...(page.part_tabs||[]).map(t=>({...t,key:frameId+':'+t.key})));
    if(!merged.elements.length)actionFrameId=frameId;
    const offset=page.frameOffset||{x:0,y:0,exact:false};
    const localToGlobal=new Map(page.elements.map(e=>[e.ref,next++]));
    for(const el of page.elements){
      if(merged.elements.length>=400){merged.warnings.push('Observation exceeds 400 elements; some controls are not listed.');break;}
      const ref=localToGlobal.get(el.ref),key=frameId+':'+el.key;
      refMap.set(ref,{frameId,ref:el.ref,key,localKey:el.key});
      const box=el.box&&offset.exact!==false?{...el.box,x:el.box.x+offset.x,y:el.box.y+offset.y}:null;
      merged.elements.push({...el,ref,key,group:localToGlobal.get(el.group)||null,box});
    }
  }
  merged.warnings=[...new Set(merged.warnings)].slice(0,30);
  if(!activeFrameIds.length)throw new Error('No assignment frame can be read. Reload the page and grant site access.');
  return merged;
}
async function actOnRef(tabId, action, permit={}){
  if(state.stopRequested)return {ok:false,detail:'Stopped before action.'};
  const payload={...action};let frame=actionFrameId;
  if(action.action!=='scroll'){
    const target=refMap.get(action.ref);if(!target)return {ok:false,detail:'That element is no longer listed. Re-observe.'};frame=target.frameId;
    for(const field of ['ref','to'])if(action[field]!=null){const mapped=refMap.get(action[field]);if(!mapped||mapped.frameId!==frame)return {ok:false,detail:'Cross-frame or missing drag destination refused.'};payload[field]=mapped.ref;}
  }
  try{return await chrome.tabs.sendMessage(tabId,{type:'act',action:payload,permit},{frameId:frame});}
  catch{return {ok:false,detail:'The frame went away before the action landed. Re-open the page.'};}
}
async function digestNow(tabId){let combined='';for(const frameId of activeFrameIds){const r=await chrome.tabs.sendMessage(tabId,{type:'digest'},{frameId});combined+=JSON.stringify([frameId,r.digest]);}return combined;}
async function waitForEffect(tabId,prior,budgetMs=4000){
  const start=Date.now();let last=null,identical=0;
  while(Date.now()-start<budgetMs&&!state.stopRequested){await new Promise(r=>setTimeout(r,180));const now=await digestNow(tabId);identical=now===last?identical+1:0;last=now;if(now!==prior&&identical>=2)return true;}
  return false;
}
async function refreshEvidence(tabId,page){
  coverage.observe(page);
  for(const q of coverage.questions.values())for(const part of q.parts.values()){
    if(!part.target_key || (part.answer==='' && !part.source_label))continue;
    const mapped=[...refMap.values()].find(e=>e.key===part.target_key);
    if(!mapped)continue; // A previously verified part may be on a hidden tab.
    const evidence={key:mapped.localKey,answer:part.source_label||part.answer,kind:part.evidence?.kind || (part.source_key || page.elements.find(e=>e.key===part.target_key)?.drag==='target'?'drag':'fill')};
    if(part.source_key)evidence.source_key=part.source_key.slice(part.source_key.indexOf(':')+1);
    const observed=await chrome.tabs.sendMessage(tabId,{type:'verify',evidence},{frameId:mapped.frameId});
    if(observed.visible){part.verified=observed.verified===true;if(part.verified)part.entered=true;}
  }
  state.progress=coverage.summary();
}
async function capture(tabId,page,badgeEnabled){
  const current=await chrome.tabs.get(tabId);
  if(!current.active)throw new Error('Assignment tab is no longer active. Select it and restart; a different tab must not be captured.');
  try{
    if(badgeEnabled)for(const frameId of activeFrameIds){
      const entries=page.elements.filter(e=>e.box).map(e=>({e,m:refMap.get(e.ref)})).filter(v=>v.m?.frameId===frameId).map(v=>({ref:v.m.ref,globalRef:v.e.ref}));
      await chrome.tabs.sendMessage(tabId,{type:'badges',entries},{frameId});
    }
    const shot=await chrome.tabs.captureVisibleTab(current.windowId,{format:'png'});
    if(!shot)throw new Error('Empty screenshot');
    const after=await chrome.tabs.get(tabId);if(!after.active||after.url!==current.url)throw new Error('Tab changed during capture');
    return shot;
  }catch(e){throw new Error('Screenshot unavailable: '+e.message+'. Re-select the assignment tab and grant site access. No blind model call was made.');}
  finally{await Promise.all(activeFrameIds.map(frameId=>chrome.tabs.sendMessage(tabId,{type:'badges_off'},{frameId}).catch(()=>{})));}
}
function answering(action,page){const e=page.elements.find(e=>e.ref===action.ref);return ['fill','select','drag'].includes(action.action)||(action.action==='click'&&['radio','checkbox','option','switch'].includes(e?.role));}
async function executeAction(tabId,action,page,config){
  await refreshEvidence(tabId,page);
  const refusal=coverage.gate(action,page,config);
  if(refusal)return {ok:false,blocked:true,detail:refusal};
  if(answering(action,page)&&!coverage.bind(action,page))return {ok:false,detail:'Action is not bound to a planned answer or drag pairing. Re-read with parts/ref and source_ref for a drag before acting.'};
  const oscillation=coverage.oscillation(action,page);if(oscillation)return {ok:false,blocked:true,detail:oscillation};
  const target=page.elements.find(e=>e.ref===action.ref);
  const terminal=target?.control==='terminal';
  const outcome=await actOnRef(tabId,action,{terminal:terminal&&config.auto_submit&&coverage.outstanding().length===0});
  coverage.record(action,page,outcome);
  if(outcome.ok&&terminal){coverage.current.submitted=true;emit({kind:'submitted',message:'Submission control executed; checking the resulting page.'});}
  return outcome;
}
async function guestToken(backend) {
  const res = await fetch(backend + '/api/guest', { method: 'POST' });
  if (!res.ok) throw new Error('The backend would not issue access. It may be restarting.');
  const data = await res.json();
  await chrome.storage.local.set({ token: data.token });
  return data.token;
}

async function decide(config, observation) {
  const call = async (token) => fetch(config.backend + '/api/agent/step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
    body: JSON.stringify(observation), signal: decisionAbort?.signal
  });

  let token = config.token || await guestToken(config.backend);
  let res = await call(token);
  if (res.status === 401) {                       // token expired or backend restarted
    token = await guestToken(config.backend);
    res = await call(token);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.error || body.detail || '';
    } catch {
      try { detail = (await res.text()).slice(0, 300); } catch { detail = ''; }
    }
    throw new Error(`The backend refused this step (HTTP ${res.status})`
      + (detail ? `: ${detail}` : '. It returned no reason.'));
  }
  return res.json();
}


async function run(tabId){
  if(state.running)throw new Error('Already running.');
  Object.assign(state,{running:true,stopRequested:false,tabId,steps:0,questions:0,cost:0,progress:'',log:[]});
  coverage=new AssignmentCoverage.Coverage();decisionAbort=new AbortController();
  let checked=false,recheck=false,stalls=0,navSteps=0,lastAction={},lastDigest='',sinceRead=0;
  try{
    const tab=await chrome.tabs.get(tabId);runOrigin=new URL(tab.url).origin;
    await injectAll(tabId);emit({kind:'info',message:'Reading '+new URL(tab.url).host+' · extension 0.6.0'});
    while(!state.stopRequested&&state.steps<SESSION_STEPS){
      const config=await settings(),current=await chrome.tabs.get(tabId);
      if(new URL(current.url).origin!==runOrigin)throw new Error('The tab moved to a different site. Run stopped.');
      if(!current.active)throw new Error('Select the assignment tab to continue. Run stopped before acting on another tab.');
      const page=await observeAllFrames(tabId);await refreshEvidence(tabId,page);
      if(page.warnings.length)emit({kind:'warn',message:page.warnings.join(' ')});
      const changed=page.digest!==lastDigest;lastDigest=page.digest;
      if(stalls>=STALL_LIMIT)throw new Error('No verified progress after '+STALL_LIMIT+' attempts. Review the last action and place the answer manually.');
      const observation={screenshot:await capture(tabId,page,config.badges),elements:page.elements,text:page.text,host:page.host,
        step:(coverage.current?.steps||0)+1,step_budget:coverage.budget(),page_changed:changed,last_action:lastAction,
        task_note:config.note,plan:coverage.current?.plan||'',progress:coverage.summary(),ledger:coverage.ledger(),warnings:page.warnings,
        phase:!checked||recheck?'read_check':navSteps?'navigate':'act',advance:config.advance,auto_submit:config.auto_submit,model:config.model};
      state.steps++;const result=await decide(config,observation),action=result.action;state.cost+=result.cost||0;
      emit({kind:'think',message:`step ${state.steps} · ${observation.phase} · ${action.action}`,detail:action.reason||'',working:result.working||'',raw:result.raw||'',cost:result.cost,tokens:`${result.input_tokens||0} in / ${result.output_tokens||0} out`});
      if(state.stopRequested)break;
      const latest=await chrome.tabs.get(tabId);
      if(!latest.active||new URL(latest.url).origin!==runOrigin)throw new Error('The active tab or origin changed while the model was answering. Nothing was clicked.');
      if(await digestNow(tabId)!==page.digest){stalls++;recheck=true;emit({kind:'warn',message:'Page changed while deciding. Discarded the stale action.'});continue;}
      if(!checked&&action.action!=='read_check'){stalls++;continue;}
      if(action.action==='read_check'){
        if(!action.has_question){
          if(!checked||!config.advance){emit({kind:'stop',message:'No question to answer. '+(action.reason||'')});break;}
          if(++navSteps>NAV_BUDGET)throw new Error('Could not reach another question.');recheck=false;continue;
        }
        if(!action.parts?.length){stalls++;recheck=true;emit({kind:'warn',message:'Model omitted the parts checklist. Asking it to read all parts before acting.'});continue;}
        const before=coverage.summary(),fresh=coverage.read(action,page);
        if(fresh){state.questions++;stalls=0;}
        else if(before===coverage.summary()&&sinceRead===0)stalls++;
        checked=true;recheck=false;navSteps=0;sinceRead=0;
        await refreshEvidence(tabId,page);emit({kind:'question',message:action.question});emit({kind:'progress',message:coverage.summary()});lastAction={action:'read_check'};continue;
      }
      if(action.action==='done'||action.action==='give_up'){
        const remaining=coverage.outstanding();
        emit({kind:remaining.length?'warn':'stop',message:(remaining.length?'Stopped with outstanding parts: '+remaining.join(', '):'Finished: ')+(action.reason||'')});break;
      }
      if(coverage.current&&++coverage.current.steps>coverage.budget())throw new Error('Question action budget reached. Completed parts were retained; inspect the remaining parts.');
      // Honor a switch changed while the model request was in flight.
      const before=coverage.summary();const outcome=await executeAction(tabId,action,page,await settings());sinceRead++;
      emit({kind:outcome.ok?'act':'warn',message:action.action+(action.ref?' ref '+action.ref:''),detail:outcome.detail});
      if(outcome.blocked)break;
      let landed=false;if(outcome.ok)landed=await waitForEffect(tabId,page.digest);
      const updated=await observeAllFrames(tabId);await refreshEvidence(tabId,updated);
      const progress=before!==coverage.summary();stalls=progress?0:stalls+1;
      state.progress=coverage.summary();emit({kind:'progress',message:state.progress});
      lastAction={action:action.action,ref:action.ref,ok:outcome.ok,detail:outcome.detail,landed};
      const control=page.elements.find(e=>e.ref===action.ref)?.control;
      recheck=outcome.ok&&['part','advance','terminal'].includes(control) || !outcome.ok;
      if(control==='terminal'&&outcome.ok){
        const feedback=updated.text.match(/(?:your answer\s*:?\s*(?:correct|incorrect)|successfully submitted|submission confirmed|assignment submitted)/i);
        emit({kind:'stop',message:feedback?'Page feedback: '+feedback[0]:'Submission action completed, but acceptance was not confirmed. Inspect the page.'});break;
      }
    }
    if(state.steps>=SESSION_STEPS)emit({kind:'stop',message:'Session step limit reached.'});
  }catch(error){emit({kind:'error',message:state.stopRequested?'Stopped by you.':error.message});}
  finally{
    await Promise.all(frameIds.map(frameId=>chrome.tabs.sendMessage(tabId,{type:'cursor_off'},{frameId}).catch(()=>{})));
    state.running=false;decisionAbort=null;chrome.runtime.sendMessage({type:'finished',state:snapshot()}).catch(()=>{});
  }
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  // Control messages originate in the extension panel, never a content script.
  if(sender.tab && !String(sender.url || '').startsWith(chrome.runtime.getURL('')) && ['start','stop'].includes(message.type)){reply({ok:false,error:'Use the extension panel.'});return true;}
  if(message.type==='start'){if(state.running){reply({ok:false,error:'Already running.'});return true;}run(message.tabId).catch(e=>emit({kind:'error',message:e.message}));reply({ok:true});return true;}
  if(message.type==='stop'){state.stopRequested=true;decisionAbort?.abort();if(state.tabId)for(const frameId of frameIds)chrome.tabs.sendMessage(state.tabId,{type:'cancel'},{frameId}).catch(()=>{});reply({ok:true});return true;}
  if(message.type==='status'){reply({...snapshot(),log:state.log});return true;}return false;
});
chrome.action.onClicked.addListener(tab=>chrome.sidePanel.open({windowId:tab.windowId}).catch(()=>{}));
chrome.runtime.onInstalled.addListener(()=>chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true}).catch(()=>{}));
// DevTools-only integration surface: not exposed to website messages or DOM.
globalThis.__assignmentHarness={injectAll,observeAllFrames,actOnRef,executeAction,refreshEvidence,waitForEffect,capture,
  get coverage(){return coverage;},get state(){return state;},
  reset(origin){runOrigin=origin;coverage=new AssignmentCoverage.Coverage();state.stopRequested=false;}};
