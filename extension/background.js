/* Extension-owned execution policy. The model proposes; the worker gates. */
import './coverage.js';
import './visual.js';
const DEFAULT_BACKEND='https://positive-tranquility-production-9fdc.up.railway.app';
const SESSION_STEPS=900, STALL_LIMIT=6, NAV_BUDGET=8;
const state={running:false,stopRequested:false,tabId:null,steps:0,questions:0,cost:0,progress:'',log:[]};
let coverage=new AssignmentCoverage.Coverage(), decisionAbort=null, runToken='',runUrl='',runTitle='';
let decisionSnapshot=null, pendingMenu=null,lastCapture=0;
const visualFailures=new Map();
let refMap=new Map(), frameIds=[0], activeFrameIds=[],runOrigin='',actionFrameId=0;
async function settings(){const s=await chrome.storage.local.get(['backend','token','model','note','advance','auto_submit','badges','double_check']);return {backend:(s.backend||DEFAULT_BACKEND).replace(/\/+$/,''),token:s.token||'',model:s.model||'',note:s.note||'',advance:s.advance===true,auto_submit:s.auto_submit===true,badges:s.badges!==false,double_check:s.double_check!==false};}
function snapshot(){return {running:state.running,steps:state.steps,questions:state.questions,cost:state.cost,progress:state.progress,runUrl,runTitle};}
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
      merged.elements.push({...el,ref,key,qid:el.qid?frameId+':'+el.qid:'',group:localToGlobal.get(el.group)||null,list_ref:localToGlobal.get(el.list_ref)||null,owner_ref:localToGlobal.get(el.owner_ref)||null,box});
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
    if(part.kind==='ordering'){evidence.kind='ordering';evidence.order_keys=(part.order_keys||[]).map(k=>k.slice(k.indexOf(':')+1));}
    if(part.source_key)evidence.source_key=part.source_key.slice(part.source_key.indexOf(':')+1);
    const observed=await chrome.tabs.sendMessage(tabId,{type:'verify',evidence},{frameId:mapped.frameId});
    if(observed.visible){
      part.domEvidence=observed;
      // The DOM decides only when it can actually read this control. For a
      // closed shadow root it cannot, and letting its blind `false` overwrite a
      // screenshot verdict un-verified a finished answer on every step.
      if(observed.supported!==false){part.domVerified=observed.verified===true;if(part.domVerified)part.entered=true;}
      else part.domVerified=null;                       // the DOM cannot read this control
      settle(part);
    }
  }
  state.progress=coverage.summary();
}
async function capture(tabId,page,badgeEnabled){
  const delay=550-(Date.now()-lastCapture);if(delay>0)await new Promise(r=>setTimeout(r,delay));lastCapture=Date.now();
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
const norm=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/\s+/g,' ').trim();
async function compatible(config){const r=await fetch(config.backend+'/api/capabilities',{signal:decisionAbort?.signal});if(!r.ok)throw new Error('Backend update required: this extension needs protocol 2. No model call was made.');const c=await r.json();if(c.protocol!==2||!['ordering','visual_input','visual_verification'].every(x=>c.features?.includes(x)))throw new Error('Backend update required: missing ordering or visual support. No model call was made.');}
async function makeSnapshot(tabId,page){
  const viewport=await chrome.tabs.sendMessage(tabId,{type:'viewport'},{frameId:0});
  const screenshot=await capture(tabId,page,false);
  return {id:crypto.randomUUID(),viewport,screenshot,hash:await AssignmentVisual.pixels(screenshot),digest:page.digest,url:(await chrome.tabs.get(tabId)).url};
}
async function currentSnapshot(tabId,snap,page){
  if(state.stopRequested)throw new Error('Stopped before browser input.');
  const tab=await chrome.tabs.get(tabId),v=await chrome.tabs.sendMessage(tabId,{type:'viewport'},{frameId:0});
  if(!tab.active||tab.url!==snap.url||JSON.stringify(v)!==JSON.stringify(snap.viewport)||await digestNow(tabId)!==snap.digest)throw new Error('Stale visual observation: page, tab or viewport changed. Read again.');
  if(await AssignmentVisual.pixels(await capture(tabId,page,false))!==snap.hash)throw new Error('Stale screenshot: visible page changed. Read again.');
}
async function browserInput(tabId,start,end){
  for(const point of [start,end].filter(Boolean)){
    const v=await chrome.tabs.sendMessage(tabId,{type:'viewport'},{frameId:0});
    if(point.x<0||point.y<0||point.x>=v.width||point.y>=v.height)return {ok:false,detail:'Target is outside the viewport. Scroll and observe again.'};
    // A refused point is the model's aim to correct, not the run's end.
    const guard=await chrome.tabs.sendMessage(tabId,{type:'visual_guard',point},{frameId:0});if(!guard.ok)return {ok:false,detail:guard.detail+' Look at the screenshot again and aim at the answer control itself.'};
  }
  return AssignmentVisual.input(tabId,start,end,()=>state.stopRequested);
}
// Two witnesses. The DOM reads the control back; the screenshot shows what the
// student would see. With double-checking on (the default), a part is verified
// only when both agree. Where the DOM cannot read the control at all, the
// screenshot decides alone. A DOM `false` always wins: the value is not there.
let doubleCheck=false;
function settle(part){
  if(part.domVerified===false){part.verified=false;return;}
  if(part.domVerified===null||part.domVerified===undefined){part.verified=part.visualConfirmed===true;return;}
  part.verified=doubleCheck?part.visualConfirmed===true:true;
}
async function verifyVisual(tabId,page,part,config){
  const snap=await makeSnapshot(tabId,page);
  const result=await decide(config,{screenshot:snap.screenshot,host:page.host,elements:[],text:'',phase:'verify',observation_id:snap.id,
    verification:{part_id:part.id,what:part.what,kind:part.kind||'value'},model:config.model});
  state.steps++;state.cost+=result.cost||0;
  emit({kind:'think',message:'Verify '+part.what,detail:result.action.reason,raw:result.raw,cost:result.cost,tokens:`${result.input_tokens||0} in / ${result.output_tokens||0} out`});
  await currentSnapshot(tabId,snap,page);
  const a=result.action;
  let matches=a.action==='verify'&&a.part_id===part.id&&a.observation_id===snap.id&&a.status==='confirmed';
  if(part.kind==='ordering')matches=matches&&JSON.stringify((a.observed_sequence||[]).map(norm))===JSON.stringify((part.sequence||[]).map(norm));
  else matches=matches&&norm(a.observed)===norm(part.answer);
  part.visualConfirmed=matches;part.visual=true;settle(part);
  if(part.verified){part.entered=true;visualFailures.delete(part.id);}
  else if(!matches){const n=(visualFailures.get(part.id)||0)+1;visualFailures.set(part.id,n);if(n>=3)throw new Error('Visual verification failed after two recovery attempts for '+part.what+'. Inspect the field manually.');}
  const witness=part.domVerified==null?'Screenshot':'DOM and screenshot';
  emit({kind:part.verified?'progress':'warn',message:(part.verified?witness+' verified: ':(matches?'Screenshot agreed but the DOM does not: ':'Screenshot did not confirm: '))+part.what,detail:a.observed||(a.observed_sequence||[]).join(' → ')});
  return part.verified;
}
function answering(action,page){const e=page.elements.find(e=>e.ref===action.ref);return ['fill','select','drag'].includes(action.action)||(action.action==='click'&&(['radio','checkbox','option','switch'].includes(e?.role)||(e?.role==='button'&&e?.choice)));}
// The model said `select` but pointed at a custom menu, not a <select>. The
// intent is unambiguous -- pick this option -- so treat it as the click it is
// rather than refusing over the verb. If it named the cell and the option text,
// find that option in the open menu. Only ever resolves to a visible option.
function normaliseCustomSelect(action,page){
  if(action.action!=='select')return action;
  const target=page.elements.find(e=>e.ref===action.ref);
  if(target?.role==='option')return {...action,action:'click',purpose:'answer',option:undefined};
  if(target?.dropdown&&action.option){
    const option=page.elements.find(e=>e.role==='option'&&e.owner_ref===target.ref&&norm(e.name)===norm(action.option));
    if(option)return {...action,action:'click',ref:option.ref,purpose:'answer',option:undefined};
  }
  return action;
}
async function executeAction(tabId,action,page,config){
  await refreshEvidence(tabId,page);
  action=normaliseCustomSelect(action,page);
  const selected=page.elements.find(e=>e.ref===action.ref);
  // The plan already bound every dropdown cell to a part at read time, and an
  // open menu belongs to exactly one cell. So a cell click or option click that
  // forgot part_id is not ambiguous; resolve it from the plan rather than
  // letting it fall through to the plain click path, where the menu opens
  // unregistered and every option is then refused as unbound.
  let part=coverage.current?.parts.get(action.part_id);
  if(!part&&selected&&coverage.current){
    const parts=[...coverage.current.parts.values()];
    if(selected.dropdown||selected.opaque)part=parts.find(p=>p.target_key===selected.key)||(selected.opaque&&parts.length===1&&!parts[0].target_key?parts[0]:undefined);
    else if(selected.role==='option'){
      const ownerKey=page.elements.find(e=>e.ref===selected.owner_ref)?.key;
      part=(pendingMenu&&coverage.current.parts.get(pendingMenu.part))||parts.find(p=>p.target_key&&p.target_key===ownerKey);
    }
    if(part)action={...action,part_id:part.id};
  }
  if(action.action==='reorder'){
    const anchor=page.elements.find(e=>e.ref===action.to);
    if(!part)return {ok:false,detail:'Reorder needs part_id of the ordering part.'};
    if(part.kind!=='ordering'||!part.order_keys?.length)return {ok:false,detail:`Part "${part.id}" is not an ordering plan. Re-read with order:[item refs in the desired order] for the list.`};
    if(!part.order_keys.includes(selected?.key)||!part.order_keys.includes(anchor?.key))return {ok:false,detail:'Both refs must be items named in the ordering plan; refs change every observation, so use the current ones.'};
    if(selected.key===anchor.key||selected.list_ref!==anchor.list_ref||!selected.list_ref||!selected.box||!anchor.box)return {ok:false,detail:'Reorder needs two distinct items in the same visible list.'};
    const s=selected.box,t=anchor.box,start={x:s.x+s.w/2,y:s.y+s.h/2},end={x:t.x+t.w/2,y:t.y+(action.placement==='before'?2:t.h-2)};
    if(!['before','after'].includes(action.placement))return {ok:false,detail:'Specify before or after.'};
    part.verified=false;part.visualConfirmed=false;return browserInput(tabId,start,end);
  }
  if(action.action.startsWith('visual_')){
    if(!part||!decisionSnapshot||action.observation_id!==decisionSnapshot.id)return {ok:false,detail:'Visual action lacks a planned part or current screenshot.'};
    await currentSnapshot(tabId,decisionSnapshot,page);
    const v=decisionSnapshot.viewport,p=action.point,d=action.destination;
    if(!p||![p.x,p.y,...(d?[d.x,d.y]:[])].every(n=>Number.isFinite(n)&&n>=0&&n<=1))return {ok:false,detail:'Invalid visual coordinates.'};
    const start={x:p.x*v.width,y:p.y*v.height},end=d?{x:d.x*v.width,y:d.y*v.height}:null;
    // When the part's control is known, the point has to land on it -- or on
    // the menu that control owns -- not merely somewhere in the same table.
    // Otherwise a mis-aimed click fills a neighbouring cell and is booked to
    // this part. For a drag the destination is what must hit the target.
    const planned=part.target_key&&page.elements.find(e=>e.key===part.target_key);
    if(planned?.box){
      const boxes=[planned.box,...page.elements.filter(e=>e.owner_ref===planned.ref&&e.box).map(e=>e.box)];
      const hits=pt=>boxes.some(b=>pt.x>=b.x-2&&pt.x<=b.x+b.w+2&&pt.y>=b.y-2&&pt.y<=b.y+b.h+2);
      if(!hits(end||start))return {ok:false,detail:`That point is not on the control planned for "${part.what}" (ref ${planned.ref}) or its open menu. Aim at that control, or click it by ref.`};
    }
    part.visual=true;if(action.purpose!=='open'){part.verified=false;part.visualConfirmed=false;}
    return browserInput(tabId,start,end);
  }
  if(action.action==='click' && selected?.opaque){
    // The page draws this box but we cannot see inside it (closed shadow root).
    // el.click() on the host reaches nothing; a real mouse click at its centre
    // does. Nothing the DOM can read back, so this part is verified visually.
    if(!part)return {ok:false,detail:'Clicking a widget needs part_id of the part it answers.'};
    if(!selected.box)return {ok:false,detail:'That widget has no measurable position.'};
    if(part.target_key&&part.target_key!==selected.key)return {ok:false,detail:'Widget does not match the planned part.'};
    // A screenshot already confirmed this part. Clicking the widget again would
    // reopen it and throw that evidence away, which is how a finished answer
    // became unfinished in a live run.
    if(part.verified)return {ok:false,detail:`"${part.what}" is already verified from the screenshot. Do not click it again; move to the next part or the control that continues.`};
    part.target_key=selected.key;part.visual=true;
    // The first click on a widget opens it; whatever the model calls the next
    // one, it is acting inside the open widget and the result needs checking.
    // Relying on the model's purpose label left a chosen answer unverified.
    const opening=!part.opened&&action.purpose!=='answer';
    const b=selected.box,out=await browserInput(tabId,{x:b.x+b.w/2,y:b.y+b.h/2});
    if(out.ok){if(opening){part.opened=true;out.preparation=true;}else{part.entered=true;part.verified=false;part.visualConfirmed=false;part.opened=false;out.needsVerification=true;out.partId=part.id;}}
    return out;
  }
  if(action.action==='click' && part && (selected?.dropdown||action.purpose==='open'||(pendingMenu?.part===part.id&&selected?.role==='option'))){
    if(selected?.control||!selected?.box)return {ok:false,detail:'Dropdown action requires a visible non-navigation control.'};
    const mapped=refMap.get(selected.ref);
    if(selected.dropdown){
      if(part.target_key&&part.target_key!==selected.key)return {ok:false,detail:'Dropdown does not match the planned cell.'};
      part.target_key=selected.key;pendingMenu={part:part.id,frame:mapped.frameId};
    }else{
      // The option must belong to the planned cell's menu. If the worker saw
      // the menu open it also checks it was this part's; a menu it did not see
      // open (the cell was clicked through the plain path) is still acceptable
      // when the option's owner cell is provably the planned one.
      const ownerKey=page.elements.find(e=>e.ref===selected.owner_ref)?.key;
      if(ownerKey!==part.target_key||(pendingMenu&&(pendingMenu.part!==part.id||pendingMenu.frame!==mapped.frameId)))return {ok:false,detail:'Open the planned dropdown first; the menu control must belong to that cell.'};
    }
    if(selected.role==='option'&&norm(selected.name)!==norm(part.answer))return {ok:false,detail:'Option differs from the planned answer.'};
    const b=selected.box,out=await browserInput(tabId,{x:b.x+b.w/2,y:b.y+b.h/2});
    if(selected.role==='option'){part.entered=true;part.verified=false;part.visualConfirmed=false;pendingMenu=null;out.needsVerification=true;out.partId=part.id;}
    else out.preparation=true;
    return out;
  }
  const refusal=coverage.gate(action,page,config);
  if(refusal)return {ok:false,blocked:true,detail:refusal};
  // Non-answer clicks: only classified controls (part tabs, advance, terminal),
  // answer controls, and neutral buttons may be clicked. Links that leave the
  // page and anything named like a destructive, account or consent action are
  // refused here as well as in the page, so a page instruction the model
  // repeats cannot reach them.
  const clickTarget=page.elements.find(e=>e.ref===action.ref);
  if(clickTarget&&(action.action==='click'||(action.action==='press'&&['Enter','Space'].includes(action.key)))){
    if(clickTarget.control==='refused')return {ok:false,blocked:false,detail:'Refused: "'+(clickTarget.name||'').slice(0,60)+'" is a destructive, account, consent or download control. Those stay with the student.'};
    if(clickTarget.role==='link'&&clickTarget.external)return {ok:false,detail:'Refused: that link leaves the assignment site.'};
  }
  if(answering(action,page)&&!coverage.bind(action,page)&&!coverage.adopt(action,page))return {ok:false,detail:'Action is not bound to a planned answer or drag pairing. Re-read with parts/ref and source_ref for a drag before acting.'};
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

  let token = runToken || config.token || await guestToken(config.backend);
  let res = await call(token);
  if (res.status === 401) {                       // token expired or backend restarted
    token = await guestToken(config.backend);
    res = await call(token);
  }
  runToken = token;
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      if(Number.isFinite(body.cost)){state.cost+=body.cost;emit({kind:'warn',message:'Provider usage for rejected proposal',cost:body.cost,tokens:`${body.input_tokens||0} in / ${body.output_tokens||0} out`});}
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
  coverage=new AssignmentCoverage.Coverage();decisionAbort=new AbortController();runToken='';
  decisionSnapshot=null;pendingMenu=null;visualFailures.clear();
  let checked=false,recheck=false,stalls=0,navSteps=0,lastAction={},lastDigest='',sinceRead=0,askedForParts=false,shifted=0,doneRefused=false;
  try{
    const tab=await chrome.tabs.get(tabId);runOrigin=new URL(tab.url).origin;runUrl=tab.url;runTitle=tab.title;
    await compatible(await settings());
    await injectAll(tabId);emit({kind:'info',message:'Reading '+new URL(tab.url).host+' · extension '+chrome.runtime.getManifest().version});
    while(!state.stopRequested&&state.steps<SESSION_STEPS){
      const config=await settings(),current=await chrome.tabs.get(tabId);doubleCheck=config.double_check;
      if(new URL(current.url).origin!==runOrigin)throw new Error('The tab moved to a different site. Run stopped.');
      if(!current.active)throw new Error('Select the assignment tab to continue. Run stopped before acting on another tab.');
      const page=await observeAllFrames(tabId);await refreshEvidence(tabId,page);
      if(page.warnings.length)emit({kind:'warn',message:page.warnings.join(' ')});
      const changed=page.digest!==lastDigest;lastDigest=page.digest;
      if(stalls>=STALL_LIMIT){
        // Stalling with everything verified is not a failure: the work is done
        // and the page simply offers nothing further to press. Say that.
        if(coverage.questions.size&&!coverage.outstanding().length){emit({kind:'stop',message:'Every part is verified. Nothing further to press was found on this page -- no hand-in or next-question control.'});break;}
        throw new Error('No verified progress after '+STALL_LIMIT+' attempts. Review the last action and place the answer manually.');
      }
      decisionSnapshot=await makeSnapshot(tabId,page);
      const observation={screenshot:config.badges?await capture(tabId,page,true):decisionSnapshot.screenshot,observation_id:decisionSnapshot.id,elements:page.elements,text:page.text,host:page.host,
        step:(coverage.current?.steps||0)+1,step_budget:coverage.budget(),page_changed:changed,last_action:lastAction,
        task_note:config.note,plan:coverage.current?.plan||'',progress:coverage.summary(),ledger:coverage.ledger(),warnings:page.warnings,
        phase:!checked||recheck?'read_check':navSteps?'navigate':'act',advance:config.advance,auto_submit:config.auto_submit,model:config.model};
      state.steps++;let result;
      try{result=await decide(config,observation);}
      catch(e){
        // A reply the backend could not turn into an action is the model's slip,
        // not the run's end: the backend already asked once for a correction and
        // billed both calls. Spend one stall and look again. Anything else -- a
        // missing key, a bad model, an unreachable backend -- stops here.
        if(/Nothing was done|invalid action format|Invalid proposal|not an allowed action|would not (?:choose|perform)|Verification may only be returned/.test(e.message)){
          stalls++;recheck=false;lastAction={action:'invalid',ok:false,detail:e.message.replace(/^The backend refused this step \(HTTP \d+\): /,'')};
          emit({kind:'warn',message:'The model answered in a form the harness could not use. Asking again.',detail:lastAction.detail});continue;
        }
        throw e;
      }
      const action=result.action;state.cost+=result.cost||0;
      emit({kind:'think',message:`step ${state.steps} · ${observation.phase} · ${action.action}`,detail:action.reason||'',working:result.working||'',raw:result.raw||'',cost:result.cost,tokens:`${result.input_tokens||0} in / ${result.output_tokens||0} out`});
      if(state.stopRequested)break;
      const latest=await chrome.tabs.get(tabId);
      if(!latest.active||new URL(latest.url).origin!==runOrigin)throw new Error('The active tab or origin changed while the model was answering. Nothing was clicked.');
      if(await digestNow(tabId)!==page.digest){
        // A live region or animation can shift the page during the model call.
        // That is a reason to look again, not evidence the agent is stuck, so it
        // has its own small counter instead of feeding the stall limit.
        if(++shifted>=4)throw new Error('The page kept changing on its own while the model was deciding, four times in a row. Wait for it to settle, then start again.');
        recheck=true;emit({kind:'warn',message:'Page changed while deciding. Discarded the stale action and looking again.'});continue;}
      shifted=0;
      if(!checked&&action.action!=='read_check'){stalls++;continue;}
      if(action.action==='read_check'){
        if(!action.has_question){
          if(!checked||!config.advance){emit({kind:'stop',message:'No question to answer. '+(action.reason||'')});break;}
          if(++navSteps>NAV_BUDGET)throw new Error('Could not reach another question.');recheck=false;continue;
        }
        if(!action.parts?.length){
          // Ask for the checklist once. If the model still will not give one, let
          // it answer anyway and adopt that answer as the plan (coverage.adopt).
          // Stalling here six times was how every plain multiple-choice run died.
          if(!askedForParts){askedForParts=true;recheck=true;emit({kind:'warn',message:'Model omitted the parts checklist. Asking once more before proceeding without one.'});continue;}
          emit({kind:'warn',message:'No parts checklist. Proceeding: the first answer entered will be taken as the plan for this question.'});
        }
        const before=coverage.summary(),fresh=coverage.read(action,page);
        if(coverage.revised.length){stalls++;emit({kind:'warn',message:'The plan changed an answer it had already committed. Taken once; the part must be re-entered.',detail:coverage.revised.join('; ')});}
        if(fresh){state.questions++;stalls=0;askedForParts=false;}
        else if(before===coverage.summary()&&sinceRead===0)stalls++;
        checked=true;recheck=false;navSteps=0;sinceRead=0;
        await refreshEvidence(tabId,page);
        for(const p of coverage.current.parts.values())if(p.kind==='ordering'&&p.verified)emit({kind:'progress',message:'Already in the planned order; no drag needed: '+p.what});
        emit({kind:'question',message:action.question});emit({kind:'progress',message:coverage.summary()});lastAction={action:'read_check'};continue;
      }
      if(action.action==='done'||action.action==='give_up'){
        const remaining=coverage.outstanding();
        // The model's word that it is finished is not evidence. The first time
        // it says done with parts still unverified, tell it exactly which and
        // let it look again; a plan one click from finished was being thrown
        // away here. give_up, or a second done, stops for real.
        if(remaining.length&&action.action==='done'&&!doneRefused){
          doneRefused=true;stalls++;
          lastAction={action:'done',ok:false,detail:'Refused: these parts are not verified yet: '+remaining.join(', ')+'. A value showing inside an open widget is not chosen until you click it.'};
          emit({kind:'warn',message:'Model said done with parts outstanding. Asking it to finish them.',detail:remaining.join(', ')});continue;
        }
        emit({kind:remaining.length?'warn':'stop',message:(remaining.length?'Stopped with outstanding parts: '+remaining.join(', '):'Finished: ')+(action.reason||'')});break;
      }
      if(coverage.current&&++coverage.current.steps>coverage.budget())throw new Error('Question action budget reached. Completed parts were retained; inspect the remaining parts.');
      // Honor a switch changed while the model request was in flight.
      if(page.elements.find(e=>e.ref===action.ref)?.control==='terminal')for(const q of coverage.questions.values())for(const p of q.parts.values())if((p.visual||doubleCheck)&&!p.visualConfirmed&&p.domVerified!==false&&p.target_key)await verifyVisual(tabId,page,p,config);
      const before=coverage.summary();let outcome;
      try{outcome=await executeAction(tabId,action,page,await settings());}catch(e){if(/^Stale/.test(e.message)){recheck=true;lastAction={action:action.action,ok:false,detail:e.message};continue;}throw e;}sinceRead++;
      emit({kind:outcome.ok?'act':'warn',message:action.action+(action.ref?' ref '+action.ref:''),detail:outcome.detail});
      if(outcome.blocked)break;
      let landed=false;if(outcome.ok)landed=await waitForEffect(tabId,page.digest);
      const updated=await observeAllFrames(tabId);await refreshEvidence(tabId,updated);
      const actedPart=coverage.current?.parts.get(outcome.partId||action.part_id);
      // A screenshot verification is a paid model call. Spend it only when the
      // page gives the DOM nothing to read back (closed shadow root, canvas);
      // a cell whose value the content script can read has already been judged
      // by refreshEvidence above, and a second opinion from a picture adds cost
      // without adding evidence.
      // With double-checking on, every answer the DOM accepted is also shown to
      // the model in a fresh screenshot. A DOM rejection needs no second opinion.
      const domDecided=actedPart?.domEvidence?.supported===true;
      // One list of what counts as entering an answer, shared with the bind
      // check: a reorder is one, and leaving it out meant an ordering part
      // could never earn its screenshot witness and never complete.
      const answered=outcome.needsVerification||action.action.startsWith('visual_')||action.action==='reorder'||answering(action,page);
      if(outcome.ok&&actedPart&&answered&&action.purpose!=='open'&&(!domDecided||(doubleCheck&&actedPart.domVerified===true&&!actedPart.visualConfirmed)))await verifyVisual(tabId,updated,actedPart,config);
      const progress=before!==coverage.summary();stalls=progress?0:outcome.preparation&&landed?stalls:stalls+1;if(progress)doneRefused=false;
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
    await AssignmentVisual.detach();
    await Promise.all(frameIds.map(frameId=>chrome.tabs.sendMessage(tabId,{type:'cursor_off'},{frameId}).catch(()=>{})));
    state.running=false;decisionAbort=null;chrome.runtime.sendMessage({type:'finished',state:snapshot()}).catch(()=>{});
  }
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  // Control messages originate in the extension panel, never a content script.
  if(sender.tab && !String(sender.url || '').startsWith(chrome.runtime.getURL('')) && ['start','stop'].includes(message.type)){reply({ok:false,error:'Use the extension panel.'});return true;}
  if(message.type==='start'){if(state.running){reply({ok:false,error:'Already running.'});return true;}run(message.tabId).catch(e=>emit({kind:'error',message:e.message}));reply({ok:true});return true;}
  if(message.type==='stop'){state.stopRequested=true;decisionAbort?.abort();AssignmentVisual.detach();if(state.tabId)for(const frameId of frameIds)chrome.tabs.sendMessage(state.tabId,{type:'cancel'},{frameId}).catch(()=>{});reply({ok:true});return true;}
  if(message.type==='status'){reply({...snapshot(),log:state.log});return true;}return false;
});
chrome.action.onClicked.addListener(tab=>chrome.sidePanel.open({windowId:tab.windowId}).catch(()=>{}));
chrome.runtime.onInstalled.addListener(()=>chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true}).catch(()=>{}));
// DevTools-only integration surface: not exposed to website messages or DOM.
globalThis.__assignmentHarness={injectAll,observeAllFrames,actOnRef,executeAction,refreshEvidence,waitForEffect,capture,compatible,makeSnapshot,currentSnapshot,verifyVisual,
  setSnapshot(s){decisionSnapshot=s;},setDoubleCheck(v){doubleCheck=!!v;},settle,
  get coverage(){return coverage;},get state(){return state;},
  reset(origin){runOrigin=origin;coverage=new AssignmentCoverage.Coverage();state.stopRequested=false;}};
