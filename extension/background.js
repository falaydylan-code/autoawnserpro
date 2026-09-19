/* Structured question planner is the only execution workflow. */
import './visual.js';
import './planner_runtime.js';
const DEFAULT_BACKEND = 'https://positive-tranquility-production-9fdc.up.railway.app';
const state = {running:false,stopRequested:false,tabId:null,steps:0,questions:0,cost:0,progress:'',pageState:'',log:[]};
let decisionAbort=null,runToken='',runUrl='',runTitle='',runSite='',runOrigin='';
const stopped=()=>state.stopRequested;
async function settings() {
  const s = await chrome.storage.local.get(['backend', 'token', 'model', 'note', 'advance', 'auto_submit', 'spend_limit', 'check_work']);
  return {
    check_work: s.check_work === true,
    backend: (s.backend || DEFAULT_BACKEND).replace(/\/+$/, ''), token: s.token || '', model: s.model || '', note: s.note || '',
    advance: s.advance === true, auto_submit: s.auto_submit === true,
    spend_limit: Number.isFinite(Number(s.spend_limit)) && Number(s.spend_limit) > 0 ? Number(s.spend_limit) : 2.0,
  };
}
function snapshot() { return {running: state.running, steps: state.steps, questions: state.questions, cost: state.cost, progress: state.progress, pageState: state.pageState, runUrl, runTitle}; }
function emit(entry) {
  const row = {time: new Date().toLocaleTimeString(), ...entry};
  state.log.push(row); if (state.log.length > 400) state.log.shift();
  chrome.runtime.sendMessage({type: 'log', row, state: snapshot()}).catch(() => {});
}

const MULTI_SUFFIX = new Set(['co.uk','ac.uk','org.uk','gov.uk','com.au','edu.au','gov.au','net.au','co.nz','ac.nz','co.za','com.br','co.in','ac.in','edu.in','github.io','githubusercontent.com','web.app','firebaseapp.com','pages.dev','vercel.app','netlify.app','herokuapp.com','instructure.com','blackboard.com']);
function siteOf(url) {
  try {
    const h = new URL(url).hostname.toLowerCase().split('.');
    if (h.length <= 2) return h.join('.');
    const lastTwo = h.slice(-2).join('.'), lastThree = h.slice(-3).join('.');
    return (MULTI_SUFFIX.has(lastTwo) && h.length >= 3) ? lastThree : lastTwo;
  } catch { return ''; }
}
async function boundTab(tabId) {
  let tab; try { tab = await chrome.tabs.get(tabId); } catch { throw new Error('The assignment tab was closed. The run is over.'); }
  if (!/^https?:/.test(tab.url || '')) throw new Error('The assignment tab moved to a page the agent cannot read (' + (tab.url || 'no URL') + ').');
  if (siteOf(tab.url) !== runSite) throw new Error('The tab moved to a different site (' + new URL(tab.url).host + '). Run stopped rather than following it.');
  return tab;
}
chrome.tabs.onRemoved.addListener(tabId => { if (state.running && tabId === state.tabId) { state.stopRequested = true; emit({kind: 'error', message: 'The assignment tab was closed. Stopping.'}); } });
chrome.debugger.onDetach.addListener(({tabId}, reason) => {
  if (state.running && tabId === state.tabId && !state.stopRequested) { state.stopRequested = true; emit({kind: 'error', message: 'Chrome ended the browser-input session (' + reason + '). If you pressed Cancel on the debugging bar, press Start to continue.'}); }
});

async function guestToken(backend, signal, previousToken='') {
  const res = await fetch(backend + '/api/guest', {method: 'POST', signal,headers:previousToken?{Authorization:'Bearer '+previousToken}:{}});
  if (!res.ok) throw new Error('The backend would not issue access. It may be restarting.');
  const data = await res.json();
  await chrome.storage.local.set({token: data.token});
  return data.token;
}
// Sole execution path: structured planner, with on-demand inspection.
let plannerEngine=null,launching=false;
// How long a backend request may take: the backend's own maximum model wait (from /api/capabilities) plus a margin,
// so the backend's deadline always fires first and settles the charge. Never a number chosen here.
let requestWaitMs=75000;
async function plannerRequest(phase,body,signal){
  const config=await settings();let token=runToken||config.token;
  const controller=new AbortController(),onStop=()=>controller.abort(),timeout=setTimeout(()=>controller.abort(),requestWaitMs);
  signal.addEventListener('abort',onStop,{once:true});if(signal.aborted)controller.abort();
  try{
    if(!token)token=await guestToken(config.backend,controller.signal);runToken=token;
    const send=()=>fetch(config.backend+'/api/agent/'+phase,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(body),signal:controller.signal});
    let response=await send();
    // owner() rejects expired tokens before the provider or cost reservation runs.
    // Renew guest access once; reuse the same request ID, never replay other failures.
    if(response.status===401){token=await guestToken(config.backend,controller.signal,token);runToken=token;response=await send();}
    const data=await response.json();
    if(response.status===401)data.detail='ACCESS_EXPIRED: Automatic access renewal failed. Stop and start again.';
    if(!response.ok&&!data.detail)data.detail='BACKEND_ERROR: Backend HTTP '+response.status;return data;
  }catch{throw new Error(signal.aborted?'CANCELLED: stopped while waiting for the model.':'No answer from the backend within '+Math.round(requestWaitMs/1000)+' seconds, or the connection failed. Nothing was executed; a model call the backend had started is charged by the backend at its reserved worst case. Resume checks that charge before continuing.');}
  finally{clearTimeout(timeout);signal.removeEventListener('abort',onStop)}
}
function plannerBridge(){return {bound:boundTab,allowed:origin=>siteOf(origin)===runSite,stopped,config:settings,request:plannerRequest,
  viewport:async id=>{const r=await chrome.debugger.sendCommand({tabId:id},'Page.getLayoutMetrics');const v=r.cssVisualViewport||r.visualViewport;return {width:v.clientWidth,height:v.clientHeight}},
  emit:row=>{if(Number.isFinite(row.cost))state.cost+=row.cost;if(row.input_tokens!=null)row.tokens=String(row.input_tokens)+' in / '+String(row.output_tokens||0)+' out'+(row.reasoning_tokens?' ('+row.reasoning_tokens+' thinking)':'');emit(row)},
  progress:(done,total,questions,cost,steps)=>{Object.assign(state,{questions,cost,steps,progress:done+' of '+total+' parts done'});emit({kind:'progress',message:state.progress})}}}
async function runPlanner(tabId,config,resume=false){
  Object.assign(state,{running:true,stopRequested:false,tabId,steps:0,questions:0,cost:0,progress:'',log:[]});decisionAbort=new AbortController();
  const keepAlive=setInterval(()=>chrome.runtime.getPlatformInfo().catch(()=>{}),20000);
  try{
    const tab=await chrome.tabs.get(tabId);runOrigin=new URL(tab.url).origin;runSite=siteOf(tab.url);runUrl=tab.url;runTitle=tab.title;runToken='';
    const response=await fetch(config.backend+'/api/capabilities?protocol=4',{signal:decisionAbort.signal});const caps=await response.json();
    requestWaitMs=(Number(caps.request_wait_seconds)||60)*1000+15000;
    if(caps.protocol!==4||!['task_plans','stable_slots','typed_verification','bounded_repair','frame_scoped_inspection','interaction_classification'].every(f=>caps.features?.includes(f)))throw new Error('Backend update required: structured planner needs protocol 4 with frame-scoped inspection and interaction classification. No paid request was made.');
    await boundTab(tabId);await AssignmentVisual.attach(tabId);
    const held=(await chrome.storage.local.get('planner_run')).planner_run;
    if(resume&&(!held||held.tab_id!==tabId||held.url!==tab.url))throw new Error('Cannot resume: select the original assignment tab and URL.');
    if(resume&&held.pending_request){
      let token=config.token||await guestToken(config.backend,decisionAbort.signal);runToken=token;
      const reconcile=()=>fetch(config.backend+'/api/agent/runs/'+encodeURIComponent(held.id),{headers:{Authorization:'Bearer '+token},signal:decisionAbort.signal});
      let reconciliation=await reconcile();
      if(reconciliation.status===401){token=await guestToken(config.backend,decisionAbort.signal,token);runToken=token;reconciliation=await reconcile();}
      if(!reconciliation.ok)throw new Error('Saved request usage cannot be reconciled. Review provider usage before resuming.');
      const usage=await reconciliation.json();const call=usage.calls.find(c=>c.request_id===held.pending_request);
      if(!call||!['settled','charged_worst_case'].includes(call.status))throw new Error('Previous provider charge is still unconfirmed. Reconcile usage before resuming.');held.pending_request=null;held.cost=usage.cost;
    }
    plannerEngine=new AssignmentPlanner.Engine(plannerBridge(),tabId,config,resume?held:null);plannerEngine.ledger.tab_id=tabId;plannerEngine.ledger.url=tab.url;
    await plannerEngine.run();
  }catch(e){emit({kind:'error',message:e.message})}
  finally{clearInterval(keepAlive);await AssignmentVisual.detach();state.running=false;decisionAbort=null;plannerEngine=null;chrome.runtime.sendMessage({type:'finished',state:snapshot()}).catch(()=>{})}
}
async function startSelected(tabId,resume=false){if(launching||state.running)throw new Error('Already running.');launching=true;try{const config=await settings();if(!((await chrome.storage.local.get('armed')).armed))throw new Error('Arm ETH before starting.');await runPlanner(tabId,config,resume)}finally{launching=false}}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  // Control messages originate in the extension panel, never a content script.
  if (sender.tab && !String(sender.url || '').startsWith(chrome.runtime.getURL('')) && ['start', 'resume', 'stop'].includes(message.type)) { reply({ok: false, error: 'Use the extension panel.'}); return true; }
  if (message.type === 'start' || message.type === 'resume') { if (state.running || launching) { reply({ok: false, error: 'Already running.'}); return true; } startSelected(message.tabId,message.type==='resume').catch(e => emit({kind: 'error', message: e.message})); reply({ok: true}); return true; }
  if (message.type === 'stop') { state.stopRequested = true; plannerEngine?.stop(); decisionAbort?.abort(); AssignmentVisual.detach();  reply({ok: true}); return true; }
  if (message.type === 'status') { reply({...snapshot(), log: state.log}); return true; }
  return false;
});
chrome.action.onClicked.addListener(tab => chrome.sidePanel.open({windowId: tab.windowId}).catch(() => {}));
chrome.runtime.onInstalled.addListener(() => chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).catch(() => {}));

// Test inspection surface; never exposes the removed per-click loop.
globalThis.__assignmentHarness={plannerBridge,runPlanner,startSelected,siteOf,boundTab,
 reset(origin){runOrigin=origin;runSite=siteOf(origin);state.stopRequested=false;},
 get requestWaitMs(){return requestWaitMs},setRequestWait(ms){requestWaitMs=ms},
 async injectAll(id){await boundTab(id);await chrome.scripting.executeScript({target:{tabId:id},files:['planner_content.js']});},
 get state(){return state;}
};
