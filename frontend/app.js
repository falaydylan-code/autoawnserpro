const $=id=>document.getElementById(id);
const API=(window.AGENT_API_BASE||'').replace(/\/$/,'');
let token=sessionStorage.getItem('agent_token')||'', current=null, activeId=sessionStorage.getItem('agent_session')||'', pollBusy=false;
const accessToken=new URLSearchParams(location.hash.slice(1)).get('access');
if(accessToken){token=accessToken;sessionStorage.setItem('agent_token',token);window.history.replaceState(null,'',location.pathname+location.search);}
let recordRunId='', expandedRecords=new Set();
const defaults={question:'[data-agent-question]',choices:'input[type=radio]',answer:'[data-agent-answer]',check:'',next:'[data-agent-next]',submit:'[data-agent-submit]',complete:'[data-agent-complete]'};
for(const [key,value] of Object.entries(defaults)){const label=document.createElement('label');label.textContent=key==='complete'?'Submission confirmation':key==='check'?'check answer (optional)':key;const input=document.createElement('input');input.id='sel_'+key;input.value=value;label.append(input);$('selectors').append(label);}
function error(message){$('error').textContent=message;$('error').hidden=!message;clearTimeout(error.timer);error.timer=setTimeout(()=>$('error').hidden=true,12000);}
async function api(path,body){let r;try{r=await fetch(API+path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});}catch{throw Error('Cannot reach the backend. Start the server or check the configured Railway URL.');}if(!r.ok){let data;try{data=await r.json();}catch{}throw Error(typeof data?.detail==='string'?data.detail:'Request failed. Check your inputs and server setup.');}return r.json();}
async function action(button,fn){button.disabled=true;try{await fn();}catch(e){error(e.message);}finally{button.disabled=false;if(current)controls(current);}}
async function enter(){const setup=await api('/api/setup');$('connection').textContent=setup.browser_mode==='cloud'?'CLOUD BROWSER':'LOCAL BROWSER';$('checks').replaceChildren();for(const [name,ok] of [['Browser: '+setup.browser_mode,true],['OpenRouter key',!setup.missing.includes('OPENROUTER_API_KEY')],['Default model',!!setup.model],...(setup.browser_mode==='cloud'?[['Browserbase key',!setup.missing.includes('BROWSERBASE_API_KEY')],['Browserbase project',!setup.missing.includes('BROWSERBASE_PROJECT_ID')]]:[])]){const row=document.createElement('div');row.className='checkrow '+(ok?'ok':'missing');row.textContent=(ok?'✓  ':'○  ')+name;$('checks').append(row);}if(setup.missing.length){$('notice').hidden=false;$('notice').textContent='AI setup remaining: '+setup.missing.join(', ')+'. Configure these on the backend and restart. You can test the browser workflow in Practice mode now.';}if(setup.model){$('model').replaceChildren(new Option(setup.model,setup.model));}await refreshHistory();if(activeId){try{render(await api('/api/sessions/'+activeId));}catch{activeId='';sessionStorage.removeItem('agent_session');}}}
$('mode').onchange=()=>{const mode=$('mode').value;$('modelBox').hidden=mode==='practice';$('liveBox').hidden=mode!=='live';$('modeHelp').textContent=mode==='practice'?'Four built-in questions, including a graph. Fixture answers test the browser loop—not model accuracy.':mode==='practice_ai'?'MiniMax solves the practice questions using text and screenshots. This spends real API credits.':'Log in inside your session browser, open one question, and check the configured website controls before starting.';};
$('loadModels').onclick=e=>action(e.target,async()=>{const list=await api('/api/models');$('model').replaceChildren(new Option('Select a vision model',''));for(const model of list){const option=new Option(model.id+(model.vision?' · vision':' · text only'),model.id);option.disabled=!model.vision;$('model').append(option);}if(!list.length)error('No MiniMax models were found in the live registry. Try again later.');});
$('open').onclick=e=>{if(!requireArmed())return;action(e.target,async()=>{const selectors=Object.fromEntries(Object.keys(defaults).map(k=>[k,$('sel_'+k).value]));const run=await api('/api/sessions',{mode:$('mode').value,url:$('url').value,model:$('model').value,selectors,auto_submit:$('auto').checked,question_limit:Number($('limit').value)});activeId=run.id;recordRunId=run.id;expandedRecords.clear();sessionStorage.setItem('agent_session',activeId);render(run);});};
$('start').onclick=e=>{if(!requireArmed())return;action(e.target,async()=>render(await api('/api/sessions/'+activeId+'/start',{auto_submit:$('auto').checked,page_index:Number($('pages').value)})));};
$('stop').onclick=e=>action(e.target,async()=>render(await api('/api/sessions/'+activeId+'/stop',{})));
$('close').onclick=e=>action(e.target,async()=>{render(await api('/api/sessions/'+activeId+'/close',{}));activeId='';sessionStorage.removeItem('agent_session');await refreshHistory();});
$('refreshPages').onclick=e=>action(e.target,async()=>{const list=await api('/api/sessions/'+activeId+'/pages');$('pages').replaceChildren(...list.map(p=>new Option(p.title||'Untitled tab',p.index)));});
function controls(run){const open=!!activeId&&!['closed','expired','interrupted'].includes(run.status);$('open').disabled=open;$('start').disabled=!open||['opening','running','completed'].includes(run.status);$('stop').disabled=!open||!['opening','running'].includes(run.status);$('close').disabled=!open;$('refreshPages').disabled=!open||run.status==='opening';$('inspect').disabled=!open||['opening','running'].includes(run.status);$('export').disabled=!run.results.length;}
function render(run){current=run;controls(run);$('state').textContent=run.status.toUpperCase();$('stateText').textContent=run.message+(run.browser_engine?' · '+run.browser_engine:'');$('verified').textContent=run.results.filter(r=>r.status==='verified').length;$('cost').textContent='$'+run.cost.toFixed(4)+(run.unknown_costs?' + unconfirmed':'');$('time').textContent=['closed','expired','interrupted'].includes(run.status)?'Ended':Math.max(0,Math.ceil((run.expires-Date.now()/1000)/60))+' min';if(run.live_url){if($('live').getAttribute('src')!==run.live_url)$('live').src=run.live_url;$('live').hidden=false;$('browserEmpty').hidden=true;$('externalLive').href=run.live_url;$('externalLive').hidden=false;}else{$('live').hidden=true;$('live').removeAttribute('src');$('externalLive').hidden=true;$('browserEmpty').hidden=false;if(activeId)$('browserEmpty').querySelector('h3').textContent=run.status==='opening'?'Opening your browser…':'Check the separate browser window.';}$('log').replaceChildren();for(const item of run.logs){const li=document.createElement('li'),time=document.createElement('time'),text=document.createElement('span');time.textContent=item.time;text.textContent=item.message;li.append(time,text);$('log').append(li);}if(!recordRunId||recordRunId===run.id){recordRunId=run.id;renderResults(run.results);}}
function renderResults(rows){$('results').replaceChildren();rows.forEach((row,i)=>{const tr=document.createElement('tr');tr.className='record';const values=[i+1,row.question.slice(0,160),row.answer||'—',row.confidence==null?'—':row.confidence+'%',row.status,row.cost==null?'Unconfirmed':'$'+row.cost.toFixed(5)];values.forEach((v,index)=>{const td=document.createElement('td');td.textContent=v;if(index===4)td.className='status-'+row.status;tr.append(td);});const detail=document.createElement('tr');detail.className='detail';detail.hidden=!expandedRecords.has(i);const td=document.createElement('td');td.colSpan=6;td.textContent='Reasoning: '+(row.reasoning||'—')+'\nVerification: '+row.verification+'\nInput / output tokens: '+(row.input_tokens??'—')+' / '+(row.output_tokens??'—')+'\nLatency: '+(row.latency??'—')+'s\nRaw reply: '+(row.raw_reply||'No model call / no reply');detail.append(td);tr.onclick=()=>{detail.hidden=!detail.hidden;if(detail.hidden)expandedRecords.delete(i);else expandedRecords.add(i);};$('results').append(tr,detail);});}
async function refreshHistory(){const list=await api('/api/history');$('history').replaceChildren();if(!list.length)$('history').textContent='No previous sessions.';for(const run of list){const row=document.createElement('div');row.className='historyrow';const div=document.createElement('div'),title=document.createElement('strong'),sub=document.createElement('p'),button=document.createElement('button');title.textContent=new Date(run.created).toLocaleString()+' · '+run.mode;sub.textContent=run.status+' · '+run.results.filter(r=>r.status==='verified').length+' verified · $'+run.cost.toFixed(4);button.textContent='View records';button.onclick=()=>{recordRunId=run.id;expandedRecords.clear();renderResults(run.results);$('export').disabled=!run.results.length;document.querySelector('.results').scrollIntoView();};div.append(title,sub);row.append(div,button);$('history').append(row);}}
async function download(id){try{const r=await fetch(API+'/api/history/'+id+'/csv',{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('Export failed. Sign in and try again.');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download='assignment-'+id+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){error(e.message);}}
$('export').onclick=()=>recordRunId&&download(recordRunId);$('historyRefresh').onclick=e=>action(e.target,refreshHistory);
setInterval(async()=>{if(!activeId||!token||pollBusy)return;pollBusy=true;try{render(await api('/api/sessions/'+activeId));}catch(e){error(e.message);}finally{pollBusy=false;}},1800);

$('inspect').onclick=e=>action(e.target,async()=>{const selectors=Object.fromEntries(Object.keys(defaults).map(k=>[k,$('sel_'+k).value]));const data=await api('/api/sessions/'+activeId+'/inspect',{selectors,page_index:Number($('pages').value)});$('previewText').textContent=data.question.text;$('previewImage').src=data.image;$('preview').hidden=false;$('preview').open=true;});

/* ---- ETH: arming switch for browser control -------------------------------
   Red means browser control is off; green means it is armed. It exists so a
   stray click cannot start a paid browser session. It is a convenience, not a
   security boundary -- the backend's own rate limits and session caps are what
   actually bound usage. */
let armed=localStorage.getItem('eth_armed')==='true';

function ethControls(){return ['open','start','stop','inspect','refreshPages'];}

function paintEth(){
  const b=$('eth');
  if(!b)return;
  b.classList.toggle('on',armed);
  b.classList.toggle('off',!armed);
  b.setAttribute('aria-pressed',String(armed));
  b.title=armed?'Browser control is armed. Click to turn it off.':'Browser control is off. Click to arm it.';
  if(!armed){
    ethControls().forEach(id=>{const el=$(id);if(el)el.disabled=true;});
    $('stateText').textContent='Browser control is off. Click ETH to turn it on.';
  }else if($('stateText').textContent.startsWith('Browser control is off')){
    $('stateText').textContent=current?$('stateText').textContent:'No session open';
  }
}

function requireArmed(){
  if(armed)return true;
  error('Browser control is off. Click the red ETH button in the top right to turn it on.');
  return false;
}

if($('eth'))$('eth').onclick=()=>{
  armed=!armed;
  localStorage.setItem('eth_armed',String(armed));
  paintEth();
  if(armed){error('');openDashboard();}
};

async function openDashboard(){
  $('open').disabled=true;
  if(!armed){paintEth();$('connection').textContent='BROWSER CONTROL OFF';$('notice').hidden=false;
    $('notice').textContent='Browser control is off. Click the red ETH button in the top right to turn it on, then open a session.';
    return;}
  if(!token&&API){
    // Public dashboard: everyone gets their own guest identity, no code needed.
    try{
      const r=await fetch(API+'/api/guest',{method:'POST',headers:{'Content-Type':'application/json'}});
      if(r.ok){token=(await r.json()).token;sessionStorage.setItem('agent_token',token);}
    }catch{}
  }
  if(token){try{await enter();if(!activeId)$('open').disabled=false;paintEth();return;}catch{token='';sessionStorage.removeItem('agent_token');}}
  $('connection').textContent=API?'BACKEND UNAVAILABLE':'SETUP PENDING';
  $('notice').hidden=false;
  $('notice').textContent=API?'The backend did not accept a session. It may be restarting -- wait a moment and click ETH again.':'The dashboard is ready. Backend connection is pending.';
  $('stateText').textContent=API?'Waiting for the backend':'Browser controls awaiting backend setup';
  $('checks').textContent=API?'Backend unavailable':'Backend setup pending';
  $('loadModels').disabled=true;
  $('historyRefresh').disabled=true;
}
paintEth();
openDashboard();
