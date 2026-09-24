"""Real extension + CDP input with a scripted planner, no provider calls."""
import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate

BOOT='''async id=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
 const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
 bridge.request=async(phase,body)=>{globalThis.calls.push({phase,body});
 if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
 return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks:body.observation.slots.map((s,i)=>{
 const ops={choice:'choose_one',choice_set:'set_choice_set',value:'enter_value',selection:'set_selection',ordering:'set_order',position:'place_points'};
 let desired=s.kind==='choice'?{label:'B'}:s.kind==='choice_set'?{labels:['A','C']}:s.kind==='value'?{value:'42'}:s.kind==='ordering'?{sequence:['Revenues','Expenses','Net Income']}:{label:s.label.includes('Statement')?'Balance Sheet':'Asset'};
 return {task_id:'t'+i,slot_key:s.slot_key,operation:ops[s.kind],desired,depends_on:[]};})}}};
 globalThis.calls=[];globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());return engine.observe();}'''

def test_one_plan_choices_text_readback_single_call_with_screenshot(extension):
 page,w,tid=navigate(extension,'planner_standard.html');obs=w.evaluate(BOOT,tid)
 assert len(obs['slots'])==3
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-3:]
 assert page.locator('input[value=B][type=radio]').is_checked()
 assert page.locator('input[value=A][type=checkbox]').is_checked()
 assert not page.locator('input[value=B][type=checkbox]').is_checked()
 assert page.locator('input[value=C][type=checkbox]').is_checked()
 assert page.locator('#amount').input_value()=='42'
 assert page.evaluate('submitted')==0
 # Still ONE planning call, and it now carries a screenshot: the model plans
 # from what a human sees (DOM + picture). A second-witness verify call confirms
 # the answers from a screenshot before finishing.
 calls=w.evaluate('calls');plan=[c for c in calls if c['phase']=='plan']
 assert len(plan)==1 and plan[0]['body']['observation'].get('screenshot')
 assert any(c['phase']=='verify' for c in calls)
 import json
 for call in calls:
  snapshot=next(e for e in result['events'] if e.get('dom_observation') and e['request_id']==call['body']['request_id'])
  expected={k:v for k,v in call['body']['observation'].items() if k!='screenshot'}
  assert json.loads(snapshot['dom_observation'])==expected
  assert snapshot['screenshot_attached'] and not snapshot['dom_log_truncated']
 q=next(iter(result['questions'].values()));assert len(q['completed'])==3
 assert all(p['entry_verified'] for p in q['completed'].values())
 clicks=[e['click_details'] for e in result['events'] if e.get('click_details')]
 assert {c['purpose'] for c in clicks}=={'check_choice','uncheck_choice','focus_text'}
 unchecked=next(c for c in clicks if c['purpose']=='uncheck_choice')
 assert unchecked['matched_option']=='B' and unchecked['checked_before'] is True
 assert unchecked['checked_wanted'] is False and unchecked['desired']=={'labels':['A','C']}
 assert all(c['hit_test']['passed'] and c['coordinates']['units']=='CSS viewport pixels' for c in clicks)
 assert all(c['executor_reason'] and c['task_id'] and c['slot_key'] for c in clicks)
 assert all('Not yet verified' in c['verification'] for c in clicks)

def test_twenty_dropdown_slots_one_plan(extension):
 page,w,tid=navigate(extension,'custom_dropdowns.html');obs=w.evaluate(BOOT,tid)
 assert len(obs['slots'])==20
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-1]['detail']
 assert page.locator('td[data-value=Asset]').count()==10
 assert page.locator('td[data-value="Balance Sheet"]').count()==10
 assert [c['phase'] for c in w.evaluate('calls')].count('plan')==1
 q=next(iter(result['questions'].values()));assert len(q['completed'])==20
 # Both columns must have separately discovered choices before the one plan.
 slots=next(c for c in w.evaluate('calls') if c['phase']=='plan')['body']['observation']['slots']
 assert all(s['options']==(['Income Statement','Balance Sheet'] if 'Statement' in s['label'] else ['Asset','Expense','Liability','Revenue',"Stockholders' Equity"]) for s in slots)
 preplan=result['events'][:next(i for i,e in enumerate(result['events']) if e['detail']=='Planning answers for this question')]
 assert all(e['click_details']['purpose'].startswith('discover_') for e in preplan if e.get('click_details'))


@pytest.mark.parametrize('framed',[False,True])
@pytest.mark.parametrize('custom_scrollbar',[False,True])
def test_scroll_dropdown_reveals_options_and_finishes_remaining_rows(extension,framed,custom_scrollbar):
 page,w,tid=navigate(extension,'scroll_dropdown.html')
 if framed:
  page.goto(page.url.replace('scroll_dropdown.html','planner_standard.html'))
  page.evaluate("()=>{document.body.innerHTML='<iframe src=scroll_dropdown.html style=\"margin:60px;width:850px;height:700px;border:0\"></iframe>'}")
  frame=page.frame_locator('iframe');frame.locator('#row1').wait_for()
 else:frame=page
 if custom_scrollbar:
  frame.locator('body').evaluate('''e=>{const d=e.ownerDocument,menu=d.getElementById('menu'),wrapper=d.createElement('div');menu.before(wrapper);wrapper.append(menu);menu.style.overflowY='hidden';
   const rail=d.createElement('div');rail.className='nicescroll-rails-vr';rail.style.cssText='position:absolute;right:0;top:0;width:8px;height:112px';wrapper.append(rail);
   menu.addEventListener('wheel',e=>{e.preventDefault();menu.scrollTop+=e.deltaY},{passive:false});
  }''')
 w.evaluate(BOOT,tid)
 inspection=w.evaluate('''async()=>{const o=await engine.observe(),s=o.slots[1];return engine.inspect(s.frame,s.target,'inspect_options')}''')
 assert inspection['menu_scroll']['top']==0
 assert inspection['menu_scroll']['adapter']==('nicescroll_wheel' if custom_scrollbar else 'native_wheel')
 assert next(o for o in inspection['options'] if o['label']=='Operating')['visible'] is False
 w.evaluate('''()=>{engine.b.request=async(phase,body)=>{calls.push({phase,body});if(phase==='verify')return {cost:0,response:{kind:'verified'}};
 const desired=['(Financing)','Operating','Financing','(Operating)','(Investing)','Financing'];
 return {cost:0,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label:desired[i]},depends_on:[]}))}}};}''')
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-3:]
 assert frame.locator('td.responseCell span').all_text_contents()==['(Financing)','Operating','Financing','(Operating)','(Investing)','Financing']
 assert frame.locator('body').evaluate('(e)=>e.ownerDocument.defaultView.entries.length')==5
 scrolls=[e['scroll_details'] for e in result['events'] if e.get('scroll_details')]
 assert scrolls and scrolls[0]['target_label']=='Operating'
 assert all(s['moved'] for s in scrolls)
 assert scrolls[0]['after']['scroll_adapter']==('nicescroll_wheel' if custom_scrollbar else 'native_wheel')
 assert frame.locator('body').evaluate('(e)=>e.ownerDocument.defaultView.scrollY')==0
 assert len([c for c in w.evaluate('calls') if c['phase']=='plan'])==1


@pytest.mark.parametrize('mode',['up','blocked_wheel','overlay','stop'])
def test_scroll_dropdown_bounds_overlay_and_cancellation(extension,mode):
 page,w,tid=navigate(extension,'scroll_dropdown.html')
 page.evaluate('''mode=>{const menu=document.getElementById('menu');
 if(mode==='up')menu.scrollTop=menu.scrollHeight;
 if(mode==='blocked_wheel')menu.addEventListener('wheel',e=>e.preventDefault(),{passive:false});
 if(mode==='overlay'){const r=menu.getBoundingClientRect(),cover=document.createElement('div');cover.style.cssText=`position:absolute;left:${r.x}px;top:${r.y}px;width:${r.width}px;height:${r.height}px;background:white;z-index:99`;document.body.append(cover)}
 }''',mode)
 obs=w.evaluate(BOOT,tid)
 result=w.evaluate('''async mode=>{const obs=await engine.observe(),s=obs.slots[1];
 engine.current={key:obs.question_key,document:obs.document_id,recovery:new AssignmentPlanner.Recovery()};
 if(mode==='stop'){const wheel=AssignmentVisual.wheel;AssignmentVisual.wheel=async(...args)=>{const r=await wheel(...args);engine.stop();return r}}
 const task={task_id:'scroll-test',slot_key:s.slot_key,operation:'set_selection',desired:{label:mode==='up'?'(Financing)':'Operating'}};
 try{await engine.execute(task);return {ok:true,events:engine.ledger.events}}catch(e){return {code:e.code,detail:e.message,events:engine.ledger.events}}
 }''',mode)
 if mode=='up':
  assert result.get('ok'),result
  assert page.locator('#row1 span').inner_text()=='(Financing)'
  assert next(e['scroll_details'] for e in result['events'] if e.get('scroll_details'))['delta']['y']<0
 else:
  assert result['code']=={'blocked_wheel':'INPUT_NO_EFFECT','overlay':'GUARD_REJECTED','stop':'CANCELLED'}[mode]
  assert page.evaluate('entries')==[]
  assert not any(e.get('click_details') for e in result['events'])


def test_detached_expand_control_discovered_and_rebound_without_editor_click(extension):
 page,w,tid=navigate(extension,'detached_dropdown.html');obs=w.evaluate(BOOT,tid)
 assert len(obs['slots'])==2
 first=obs['slots'][0];second=obs['slots'][1]
 assert first['opening_control']['status']=='resolved'
 assert first['opening_control']['candidates'][0]['evidence']=='unique_slot_label_and_overlay_geometry'
 assert second['opening_control']['status']=='missing'
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-3:]
 assert page.evaluate('cellActivations')==['cash','equipment','cash']  # discovery then fresh execution binding
 assert page.evaluate('arrowClicks')==['equipment','cash']
 assert page.evaluate('editorFocus')==0
 assert page.locator('.dropdownValue').all_text_contents()==['Asset','Asset']
 inspections=[e for e in result['events'] if e.get('adapter')=='read_only_selection_options']
 assert inspections[0]['opening_control']['status']=='resolved' and inspections[0]['action_executed'] is False
 clicks=[e['click_details'] for e in result['events'] if e.get('click_details')]
 opening=next(c for c in clicks if c['purpose']=='open_menu')
 assert opening['resolved_target']['type']=='button'
 assert [c['slot_label'] for c in clicks if c['purpose']=='open_menu']==['Equipment','Cash']
 assert w.evaluate('engine.current.key')==obs['question_key']  # transient editor did not fork question


@pytest.mark.parametrize('mode',['foreign_label','wrong_geometry','ambiguous','disabled'])
def test_detached_expand_control_rejects_unowned_or_ambiguous_button(extension,mode):
 page,w,tid=navigate(extension,'detached_dropdown.html')
 page.evaluate('''mode=>{const a=document.querySelector('.dropdownButton');
 if(mode==='foreign_label')a.setAttribute('aria-label','Cash');
 if(mode==='wrong_geometry')a.style.left='900px';
 if(mode==='ambiguous')a.after(a.cloneNode(true));
 if(mode==='disabled')a.disabled=true;
 }''',mode)
 obs=w.evaluate(BOOT,tid)
 control=obs['slots'][0]['opening_control']
 assert control['status']==('ambiguous' if mode=='ambiguous' else 'resolved' if mode=='disabled' else 'missing')
 assert page.evaluate('arrowClicks')==[] and page.evaluate('cellActivations')==[]
 if mode in ('ambiguous','disabled'):
  w.evaluate('()=>engine.revealSelectionOptions=async()=>{}')  # isolate execution guard
  result=w.evaluate('()=>engine.run()')
  assert result['status']=='needs_review'
  assert not any(e.get('action_executed') for e in result['events'])


def add_collapsed_cashflow_menus(page):
 page.evaluate("""()=>{for(const [i,cell] of [...document.querySelectorAll('td.responseCell')].entries()){
   const menu=document.createElement('ul');menu.hidden=true;menu.role='listbox';menu.id='choices_'+i;
   menu.setAttribute('aria-labelledby',cell.id);cell.setAttribute('aria-controls',menu.id);
   const labels=i%2?['Operating','Financing']:['(Financing)','(Investing)','Financing'];if(i===3)labels.push('(Operating)');
   for(const label of labels){const option=document.createElement('li');option.role='option';option.textContent=label;menu.append(option)}
   document.body.append(menu);
 }}""")


def test_cashflow_hidden_choices_read_before_model_without_clicks(extension):
 page,w,tid=navigate(extension,'cashflow_discovery.html');add_collapsed_cashflow_menus(page);w.evaluate(BOOT,tid)
 w.evaluate('''()=>{globalThis.atPlanning=[];
   engine.b.request=async(phase,body)=>{
     calls.push({phase,body});if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
     const state=await chrome.scripting.executeScript({target:{tabId:engine.tabId},world:'MAIN',func:()=>({opens:window.menuOpens,entries:window.answerEntries})});atPlanning.push(state[0].result);
     const desired=['(Financing)','Operating','Financing','(Operating)','(Investing)','Financing'];
     return {cost:.001,response:{kind:'plan',reason:'Classify each cash flow using its activity and direction.',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label:desired[i]},depends_on:[]}))}};
   };}''')
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-3:]
 plans=[c for c in w.evaluate('calls') if c['phase']=='plan'];assert len(plans)==1
 assert w.evaluate('atPlanning')[0]=={'opens':[],'entries':0}
 slots=plans[0]['body']['observation']['slots']
 assert slots[0]['options']==['(Financing)','(Investing)','Financing']
 assert slots[1]['options']==['Operating','Financing']
 assert slots[3]['options']==['Operating','Financing','(Operating)']
 assert plans[0]['body']['observation']['screenshot'].startswith('data:image/')
 assert page.locator('td.responseCell').evaluate_all('(es)=>es.map(e=>e.dataset.value)')==['(Financing)','Operating','Financing','(Operating)','(Investing)','Financing']
 assert w.evaluate('''async()=>{const o=await engine.observe();return engine.knownOptions({...o,document_id:'replacement'},o.slots[0]).length}''')==0
 clicks=[e for e in result['events'] if e.get('click_details')]
 assert {'activate_cell','open_menu','choose_option'}<={e['click_details']['purpose'] for e in clicks}
 choices=[e for e in clicks if e['click_details']['purpose']=='choose_option']
 assert len(choices)==6
 for event in choices:
  c=event['click_details']
  assert c['desired']['label']==c['matched_option']==c['resolved_target']['label']
  assert c['plan_explanation']=='Classify each cash flow using its activity and direction.'
  assert c['resolved_target']['ref']==event['target'] and event['observation_id']
  assert any(o['label']==c['matched_option'] and o['ref']==event['target'] for o in c['available_options'])
  assert c['hit_test']['passed'] and c['hit_test']['element']['label']==c['matched_option']


def test_stop_read_only_discovery_then_resume_without_open_menu(extension):
 page,w,tid=navigate(extension,'cashflow_discovery.html');add_collapsed_cashflow_menus(page);w.evaluate(BOOT,tid)
 w.evaluate('''()=>{const emit=engine.b.emit;let stopped=false;engine.b.emit=row=>{
   emit(row);if(!stopped&&row.message==='Read dropdown choices without clicking'){stopped=true;engine.stop()}
 };}''')
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='cancelled' and w.evaluate('calls')==[]
 assert page.evaluate('({opens:menuOpens,entries:answerEntries})')=={'opens':[],'entries':0}
 # Resume into another read-only observation; no saved click is replayed.
 result=w.evaluate('''async()=>{const old=engine;engine=new AssignmentPlanner.Engine(old.b,old.tabId,old.config,old.ledger);
 engine.b.request=async(phase,body)=>{calls.push({phase,body});return {cost:0,response:{kind:'needs_review',reason:'Inspection-only test'}}};return engine.run()}''')
 assert result['status']=='needs_review'
 assert page.evaluate('({opens:menuOpens,entries:answerEntries})')=={'opens':[],'entries':0}
 assert len(w.evaluate('calls')[0]['body']['observation']['slots'][5]['options'])==2


def test_uncreated_options_are_discovered_without_answer_entry(extension):
 page,w,tid=navigate(extension,'cashflow_discovery.html');w.evaluate(BOOT,tid)
 w.evaluate('''()=>{engine.b.request=async(phase,body)=>{
   calls.push({phase,body});const o=body.observation;
   return {cost:0,response:calls.length===1?{kind:'request_inspection',question_key:o.question_key,observation_id:o.observation_id,tasks:[],inspection:{slot_key:o.slots[0].slot_key,requests:['inspect_options'],script:'',question:'Read existing choices'}}:{kind:'needs_review',reason:'Inspection-only test'}};
 }}''')
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='needs_review'
 assert page.evaluate('({opens:menuOpens,entries:answerEntries})')=={'opens':list(range(6)),'entries':0}
 assert page.locator('td.responseCell input').count()==12
 assert len(w.evaluate('calls'))==2
 inspection=w.evaluate('calls')[1]['body']['observation']['evidence'][0]['result']
 assert inspection['options']==[] and inspection['opening_control']['status']=='resolved'
 assert w.evaluate('calls')[1]['body']['observation']['slots'][0]['options']==['(Financing)','(Investing)','Financing']  # retained per-slot evidence after menu destruction
 assert all(e['click_details']['purpose'].startswith('discover_') for e in result['events'] if e.get('click_details'))
 assert any(e.get('inspection_source')=='not_present_in_dom' for e in result['events'])


@pytest.mark.parametrize('mode',['linked','foreign','ambiguous','nested_select'])
def test_collapsed_options_require_owner_and_preserve_disabled_choices(extension,mode):
 page,w,tid=navigate(extension,'planner_selection.html')
 page.evaluate('''mode=>{
   const cell=document.getElementById('cell');
   if(mode==='nested_select'){
     const select=document.createElement('select');select.hidden=true;select.setAttribute('aria-hidden','true');
     select.innerHTML='<option>Asset</option><optgroup disabled label="Unavailable"><option>Liability</option></optgroup>';
     cell.append(select);return;
   }
   const menu=document.createElement('ul');menu.id='menu_cell';menu.role='listbox';menu.hidden=true;
   menu.innerHTML='<li role="option">Asset</li><li role="option" aria-disabled="true">Liability</li>';
   if(mode==='linked')menu.setAttribute('aria-labelledby','cell');
   if(mode!=='linked'){
     const row=document.querySelector('table').insertRow();row.insertCell().textContent='Other field';
     const other=row.insertCell();other.id='other';other.className='dropDownList';other.tabIndex=0;other.setAttribute('aria-controls','menu_cell');
     if(mode==='foreign')menu.setAttribute('aria-labelledby','other');
   }
   document.body.append(menu);
 }''',mode)
 w.evaluate(BOOT,tid)
 w.evaluate('()=>engine.revealSelectionOptions=async()=>{}')  # isolate read-only ownership
 result=w.evaluate('''async()=>{engine.b.request=async(phase,body)=>{calls.push({phase,body});return {cost:0,response:{kind:'needs_review',reason:'Read-only test'}}};return engine.run()}''')
 slots=w.evaluate('calls')[0]['body']['observation']['slots']
 cell=next(s for s in slots if s['label']=='Accounts Payable Account Type')
 assert cell['options']==(['Asset'] if mode in ('linked','nested_select') else [])
 assert all(not e.get('action_executed') for e in result['events'])
 if mode in ('linked','nested_select'):
  evidence=next(e for e in result['events'] if e.get('actual') and e.get('slot_key')==cell['slot_key'])
  assert evidence['actual'][1]['disabled'] is True
 else:
  other=next(s for s in slots if s['slot_key']!=cell['slot_key'])
  assert other['options']==(['Asset'] if mode=='foreign' else [])


@pytest.mark.parametrize('mode',['targeted','delayed_arrow','discovery','script_discovery','repeated'])
def test_invalid_inspection_corrects_once_before_any_script_or_input(extension,mode):
 page,w,tid=navigate(extension,'planner_selection.html')
 if mode=='delayed_arrow':
  page.evaluate('''()=>{const arrow=document.getElementById('arrow'),cell=document.getElementById('cell');arrow.remove();
    cell.onclick=()=>{if(!cell.contains(arrow))setTimeout(()=>cell.append(arrow),100)};
    document.addEventListener('keydown',e=>{if(e.key==='Escape'){document.querySelector('ul')?.remove();cell.setAttribute('aria-expanded','false')}});
    arrow.onclick=e=>{e.stopPropagation();setTimeout(()=>openMenu(cell),150)};}''')
 w.evaluate(BOOT,tid)
 w.evaluate('()=>engine.revealSelectionOptions=async()=>{}')  # isolate rejected model requests
 w.evaluate('''mode=>{const normal=engine.b.request;globalThis.inspectionCalls=[];
 const evaluate=AssignmentVisual.evaluate;globalThis.scriptsRun=0;
 AssignmentVisual.evaluate=async(...args)=>{scriptsRun++;return evaluate(...args)};
 engine.b.request=async(phase,body,signal)=>{
   if(phase!=='plan')return normal(phase,body,signal);
   inspectionCalls.push(body);const n=inspectionCalls.length;
   if(n===1||mode==='repeated')return {cost:.001,detail:'TARGET_MISSING: inspection slot was not offered.',inspection_correction:{kind:'inspection_target',rejected_slot_key:body.observation.question_key+'/options'},raw_reply:'rejected inspection with a script'};
   if(n===2)return {cost:.001,response:{kind:'request_inspection',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks:[],inspection:{slot_key:mode.includes('discovery')?'':body.observation.slots[0].slot_key,question:'What options exist?',requests:mode==='script_discovery'?[]:[mode==='discovery'?'inspect_question':'inspect_options'],script:mode==='script_discovery'?'return {heading:document.querySelector("h1").innerText,table:document.querySelector("table").innerText}':''}}};
   return normal(phase,body,signal);
 };}''',mode)
 result=w.evaluate('()=>engine.run()');calls=w.evaluate('inspectionCalls')
 assert w.evaluate('scriptsRun')==(1 if mode=='script_discovery' else 0)
 assert calls[1]['inspection_target_correction'] is True
 evidence=calls[1]['observation']['evidence'][-1]
 assert evidence['operation']=='inspection_request_correction' and evidence['offered_slots'][0]['slot_key']==calls[1]['observation']['slots'][0]['slot_key']
 q=next(iter(result['questions'].values()));assert q['inspectionTargetCorrections']==1
 if mode=='repeated':
  assert len(calls)==2 and result['status']=='needs_review'
  assert not page.locator('#cell').get_attribute('data-value')
  # Worker resume cannot acquire another correction allowance.
  w.evaluate('''()=>{const old=engine;engine=new AssignmentPlanner.Engine(old.b,old.tabId,old.config,old.ledger)}''')
  resumed=w.evaluate('()=>engine.run()')
  assert len(w.evaluate('inspectionCalls'))==3 and resumed['status']=='needs_review'
 else:
  assert len(calls)==3 and result['status']=='finished',result['events'][-1]['detail']
  assert page.locator('#cell').get_attribute('data-value')=='Asset'
  inspection=next(e for e in calls[2]['observation']['evidence'] if e['operation']!='inspection_request_correction')
  assert inspection['operation']==('inspect_question' if mode=='discovery' else 'script' if mode=='script_discovery' else 'inspect_options')
  if mode in ('targeted','delayed_arrow'):
   assert inspection['result']['options']==[]  # options are created only on later answer entry
   assert 'opening_control' in inspection['result']
  assert not calls[2].get('inspection_target_correction')

def test_resume_reconciles_without_replaying_completed_input(extension):
 page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid);first=w.evaluate('()=>engine.run()');entries=page.evaluate('entries')
 result=w.evaluate('''async()=>{const old=engine;engine=new AssignmentPlanner.Engine(old.b,old.tabId,old.config,old.ledger);return engine.run()}''')
 assert result['status']=='finished',result['events'][-3:]
 assert page.evaluate('entries')==entries and [c['phase'] for c in w.evaluate('calls')].count('plan')==1

def test_wrong_menu_duplicate_label_stops_in_budget(extension):
 page,w,tid=navigate(extension,'custom_dropdowns.html')
 page.evaluate("()=>{const old=openMenu;openMenu=(c,j)=>{old(c,j);const n=document.querySelector('li');n.parentElement.append(n.cloneNode(true));};}")
 w.evaluate(BOOT,tid);result=w.evaluate('()=>engine.run()')
 assert result['status']=='needs_review'
 assert len(next(iter(result['questions'].values()))['completed'])==0
 assert w.evaluate('calls.length')<=3

def test_expired_observation_cannot_measure(extension):
 page,w,tid=navigate(extension,'planner_standard.html');obs=w.evaluate(BOOT,tid)
 result=w.evaluate('''async()=>{let a=await engine.observe();let s=a.slots[0];await engine.observe();try{await engine.inspect(s.frame,s.target);return {ok:true}}catch(e){return {code:e.code}}}''')
 assert result['code']=='TARGET_STALE'

def test_cancel_discards_pending_model_response(extension):
 page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
 result=w.evaluate('''async()=>{const original=engine.b.request;engine.b.request=async(...args)=>{const r=await original(...args);engine.stop();return r};return engine.run()}''')
 assert result['status']=='cancelled'
 assert page.locator('#amount').input_value()==''
 assert not page.locator('input[value=B][type=radio]').is_checked()

def test_recovery_budget_ignores_task_rename(extension):
 _,w,_,_,_=extension
 result=w.evaluate('''()=>{const r=new AssignmentPlanner.Recovery();const t={slot_key:'q/a',operation:'set_selection',desired:{label:'B'}};r.failure(t,new AssignmentPlanner.Fault('VALUE_MISMATCH','wrong'),'A');try{r.failure({...t,task_id:'renamed'},new AssignmentPlanner.Fault('VALUE_MISMATCH','wrong'),'A');return false}catch(e){return e.code}}''')
 assert result=='REPEATED_STATE'

def test_svg_math_coordinates_nested_transform_and_resize(extension):
 page,w,tid=navigate(extension,'planner_graph.html');w.evaluate(BOOT,tid)
 page.set_viewport_size({'width':1100,'height':900})
 result=w.evaluate('''async()=>{engine.b.request=async(phase,b)=>{calls.push({phase});return {cost:.001,response:{kind:'plan',question_key:b.observation.question_key,observation_id:b.observation.observation_id,tasks:[{task_id:'plot',slot_key:b.observation.slots[0].slot_key,operation:'place_points',desired:{points:[{id:'A',x:-2,y:-4},{id:'B',x:0,y:2},{id:'C',x:2,y:8}]}}]}}};return engine.run()}''')
 assert result['status']=='finished',result['events'][-3:]
 actual=w.evaluate('async()=> (await engine.observe()).slots[0].geometry.points')
 assert [round(p['x']) for p in actual]==[-2,0,2]
 assert [round(p['y']) for p in actual]==[-4,2,8]

def test_background_tab_and_partial_enumeration(extension):
 page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
 _,_,_,context,origin=extension
 other=context.new_page();other.goto(origin+'/ordering.html');other.bring_to_front()
 result=w.evaluate('''async()=>{engine.b.config=async()=>({advance:true,auto_submit:true});return engine.run()}''')
 assert result['status']=='needs_review'
 assert 'enumeration' in result['events'][-1]['detail']
 assert page.locator('#amount').input_value()=='42' and page.evaluate('submitted')==0
 assert other.locator('li').first.inner_text()=='Net Income'

def test_ordering_recomputes_after_each_move(extension):
 page,w,tid=navigate(extension,'ordering.html');w.evaluate(BOOT,tid)
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-3:]
 assert page.locator('li').all_text_contents()==['Revenues','Expenses','Net Income']

def test_same_input_ids_next_question_different_identity(extension):
 page,w,tid=navigate(extension,'planner_standard.html');before=w.evaluate(BOOT,tid)
 page.locator('main').evaluate("e=>e.setAttribute('data-question-id','fixture-q2')")
 after=w.evaluate('()=>engine.observe()')
 assert before['question_key']!=after['question_key']

def test_document_replacement_during_model_call_no_input(extension):
 page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
 w.evaluate('''()=>{const original=engine.b.request;engine.b.request=async(...args)=>{globalThis.pendingPlan=await original(...args);return new Promise(resolve=>globalThis.finishPlan=()=>resolve(pendingPlan))};globalThis.runningPlan=engine.run()}''')
 w.evaluate('async()=>{for(let i=0;i<100&&!globalThis.finishPlan;i++)await new Promise(r=>setTimeout(r,20));if(!globalThis.finishPlan)throw new Error(\"Planner did not reach request\")}')
 page.reload();w.evaluate('()=>finishPlan()')
 result=w.evaluate('()=>runningPlan')
 assert result['status']=='needs_review'
 assert page.locator('#amount').input_value()==''

def test_frame_observation_and_sensitive_input_exclusion(extension):
 page,w,tid=navigate(extension,'planner_standard.html');page.evaluate("()=>{const p=document.createElement('input');p.name='credit_card';p.value='never-record-this';document.querySelector('main').append(p)}")
 obs=w.evaluate(BOOT,tid)
 assert 'never-record-this' not in str(obs)
 _,_,_,_,origin=extension
 page.evaluate("url=>{const f=document.createElement('iframe');f.src=url;document.querySelector('main').append(f)}",origin+'/custom_dropdowns.html')
 page.frame_locator('iframe').locator('#cell_0_0').wait_for()
 obs=w.evaluate('()=>engine.observe()');assert len(obs['slots'])==23


@pytest.mark.parametrize('input_type',['text','password'])
def test_password_filter_removed_from_observation_and_target_inspection(extension,input_type):
 page,w,tid=navigate(extension,'planner_standard.html')
 page.locator('#amount').evaluate("(e,type)=>{e.type=type;e.autocomplete='new-password';e.name='password';e.setAttribute('aria-label','Password test field')}",input_type)
 obs=w.evaluate(BOOT,tid)
 assert len(obs['slots'])==3
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-3:]
 assert page.locator('#amount').input_value()=='42'
 assert page.evaluate('submitted')==0

def test_opaque_graph_visual_fallback_uses_fresh_measurements(extension):
 page,w,tid=navigate(extension,'graph_points.html')
 page.evaluate('()=>{window.points={A:{x:0,y:0},B:{x:0,y:1},C:{x:0,y:2}};draw()}')
 w.evaluate(BOOT,tid)
 result=w.evaluate('''async()=>{engine.b.request=async(phase,b)=>{calls.push({phase});if(phase==='visual'){
 // Scripted vision provider reads fixture CURRENT positions only. Production
 // code has no MAIN-world bridge and does not read the fixture answer key.
 const actual=(await chrome.scripting.executeScript({target:{tabId:engine.tabId},world:'MAIN',func:()=>Object.entries(window.points).map(([id,p])=>({id,x:(40+p.x*64)/402,y:(360-p.y*64)/402}))}))[0].result;
 return {cost:.001,response:{kind:'geometry',x_ticks:[{value:0,fraction:40/402},{value:5,fraction:360/402}],y_ticks:[{value:0,fraction:360/402},{value:5,fraction:40/402}],points:actual}}}
 return {cost:.001,response:{kind:'plan',question_key:b.observation.question_key,observation_id:b.observation.observation_id,tasks:[{task_id:'graph',slot_key:b.observation.slots[0].slot_key,operation:'place_points',desired:{points:[{id:'A',x:1,y:2},{id:'B',x:3,y:1},{id:'C',x:4,y:4}]}}]}}};return engine.run()}''')
 assert result['status']=='finished',result['events'][-1]['detail']
 assert page.evaluate('window.points')=={'A':{'x':1,'y':2},'B':{'x':3,'y':1},'C':{'x':4,'y':4}}
 assert [c['phase'] for c in w.evaluate('calls')].count('plan')==1
 assert [c['phase'] for c in w.evaluate('calls')].count('visual')>=4

def test_missing_visual_calibration_stops_before_drag(extension):
 page,w,tid=navigate(extension,'graph_points.html');w.evaluate(BOOT,tid)
 result=w.evaluate('''async()=>{engine.b.request=async()=>({cost:.001,response:{kind:'needs_review',reason:'Axis labels unreadable'}});return engine.run()}''')
 assert result['status']=='needs_review' and 'Axis labels unreadable' in result['events'][-1]['detail']
 assert page.evaluate('window.points.A')=={'x':0,'y':0}

def test_complete_enumeration_gates_actual_submission(extension):
 page,w,tid=navigate(extension,'planner_standard.html')
 page.locator('h1').evaluate("e=>e.textContent='Question 1 of 1: choose and enter the requested values'")
 page.locator('#submit').evaluate("e=>e.onclick=()=>{window.submitted++;saved.textContent='Assignment complete'}")
 w.evaluate(BOOT,tid)
 result=w.evaluate('''async()=>{engine.b.config=async()=>({advance:true,auto_submit:true});return engine.run()}''')
 assert result['status']=='completed',result['events'][-1]['detail']
 assert page.evaluate('submitted')==1

def test_reused_menu_nodes_delayed_options_below_fold(extension):
 page,w,tid=navigate(extension,'custom_dropdowns.html')
 page.evaluate('''()=>{const original=openMenu;let held=null;
 openMenu=(cell,j)=>{original(cell,j);const created=document.querySelector('ul');
 if(!held)held=created;else{held.id=created.id;held.setAttribute('aria-labelledby',cell.id);held.style.cssText=created.style.cssText;held.replaceChildren(...created.childNodes);created.replaceWith(held)}
 const options=[...held.children];held.replaceChildren();setTimeout(()=>held.append(...options),100);};
 document.querySelector('table').style.marginTop='900px';}''')
 w.evaluate(BOOT,tid);result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-1]['detail']
 assert page.locator('td[data-value]').count()==20 and [c['phase'] for c in w.evaluate('calls')].count('plan')==1

def test_overlay_guard_records_failure_without_click(extension):
 page,w,tid=navigate(extension,'planner_standard.html')
 page.evaluate("()=>{const overlay=document.createElement('div');overlay.style='position:fixed;inset:0;background:#ffffff80;z-index:9999';document.body.append(overlay)}")
 w.evaluate(BOOT,tid);result=w.evaluate('()=>engine.run()')
 assert result['status']=='needs_review' and result['events'][-1]['failure_code']=='GUARD_REJECTED'
 assert page.locator('#amount').input_value()==''

def test_delayed_save_reverts_value_not_verified(extension):
 page,w,tid=navigate(extension,'planner_standard.html')
 page.evaluate("()=>amount.addEventListener('blur',()=>{saved.textContent='Saving';setTimeout(()=>{amount.value='rejected';saved.textContent='Saved'},150)})")
 w.evaluate(BOOT,tid);result=w.evaluate('()=>engine.run()')
 assert result['status']=='needs_review'
 q=next(iter(result['questions'].values()))
 assert not any(c.get('actual')=='42' for c in q['completed'].values())

@pytest.mark.parametrize('offscreen',[False,True])
def test_permitted_cross_origin_frame_input_and_unreadable_frame(extension,offscreen):
 import functools,threading
 from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
 from pathlib import Path
 page,w,tid,_,origin=extension
 class Quiet(SimpleHTTPRequestHandler):
  def log_message(self,*a):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(Path(__file__).parent/'fixtures')))
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  page.goto(origin+'/ordering.html')
  child=f'http://127.0.0.1:{server.server_port}/planner_standard.html'
  page.evaluate("url=>{document.body.innerHTML='<iframe style=\"width:900px;height:850px;border:0\"></iframe>';document.querySelector('iframe').src=url}",child)
  page.frame_locator('iframe').locator('#amount').wait_for()
  if offscreen:page.locator('iframe').evaluate("e=>{e.style.marginTop='2400px';e.style.marginLeft='80px'}")
  w.evaluate(BOOT,tid);result=w.evaluate('()=>engine.run()')
  assert result['status']=='finished',result['events'][-1]['detail']
  assert page.frame_locator('iframe').locator('#amount').input_value()=='42'
  if offscreen:assert any(e.get('scroll_details',{}).get('adapter')=='page_wheel' for e in result['events'])
  w.evaluate("()=>engine.b.allowed=origin=>!origin.includes('"+str(server.server_port)+"')")
  result=w.evaluate('async()=>{try{await engine.observe();return null}catch(e){return e.code}}')
  assert result=='FRAME_UNREADABLE'
 finally:server.shutdown();server.server_close();thread.join(timeout=2)


def test_start_ignores_old_workflow_preference_and_uses_planner(extension):
 _,w,tid,_,_=extension
 result=w.evaluate("""async id=>{
   await chrome.storage.local.set({armed:true,planner_enabled:false});
   let ran=0;const Original=AssignmentPlanner.Engine,originalFetch=fetch;
   AssignmentPlanner.Engine=class {constructor(){this.ledger={}}async run(){ran++}};
   globalThis.fetch=async u=>String(u).includes('/api/capabilities')?new Response(JSON.stringify({protocol:4,features:['task_plans','stable_slots','typed_verification','bounded_repair','frame_scoped_inspection','interaction_classification','choice_discovery','bounded_format_correction','contextual_navigation']})):originalFetch(u);
   try {await __assignmentHarness.startSelected(id);return {ran,legacy:typeof __assignmentHarness.run,errors:__assignmentHarness.state.log.filter(e=>e.kind==='error')}}
   finally{AssignmentPlanner.Engine=Original;globalThis.fetch=originalFetch}
 }""",tid)
 assert result=={'ran':1,'legacy':'undefined','errors':[]}


def test_rejected_plan_logs_raw_and_failure_without_false_success(extension):
 _,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
 result=w.evaluate("""async()=>{engine.b.request=async()=>({cost:.001,raw_reply:'{"kind":"plan"}',finish_reason:'stop',detail:'SCHEMA_INVALID: question_key: missing'});return engine.run()}""")
 assert result['status']=='needs_review'
 rows=result['events'];failure=next(e for e in rows if e.get('raw'))
 assert failure['raw']=='{"kind":"plan"}' and failure['finish_reason']=='stop'
 assert 'question_key: missing' in failure['detail']
 assert not any('Received validated' in e['detail'] for e in rows)
 assert 'SCHEMA_INVALID: SCHEMA_INVALID' not in rows[-1]['detail']


def test_copy_log_contains_model_reply_and_validation_details(extension):
 _,w,_,context,_=extension
 panel=context.new_page()
 panel.goto(w.url.rsplit('/',1)[0]+'/sidepanel.html')
 panel.evaluate("""()=>{
   Object.defineProperty(navigator.clipboard,'writeText',{configurable:true,value:async text=>{globalThis.copied=text}});
   addRow({time:'test',kind:'info',message:'Model response rejected; no plan accepted',
     detail:'SCHEMA_INVALID: tasks.0.slot_key: missing',raw:'{"kind":"plan"}',
     finish_reason:'stop',request_id:'test-request',model:'test-model',phase:'PLAN'});
   addRow({time:'test',kind:'info',message:'DOM observation sent to model',
     dom_observation:JSON.stringify({question:'Two blanks',slots:[],completeness:{complete:true}},null,2),
     request_id:'test-request',observation_id:'test-observation',slot_count:0,screenshot_attached:true,dom_log_truncated:false});
   addRow({time:'test',kind:'info',message:'Browser click executed',click_details:{
     purpose:'choose_option',executor_reason:'Exact planned label matched.',desired:{label:'(Financing)'},
     matched_option:'(Financing)',plan_explanation:'Dividend cash outflow.',coordinates:{x:120,y:240},
     resolved_target:{label:'<script>not executable</script>'}}});
   addRow({time:'test',kind:'info',message:'Read dropdown choices without clicking',
     opening_control:{status:'resolved',candidates:[{target:'arrow',evidence:'unique_slot_label_and_overlay_geometry'}]}});
   addRow({time:'test',kind:'info',message:'Scrolled dropdown to reveal the planned option',
     scroll_details:{target_label:'Operating',before:{top:0},after:{top:56},moved:true}});
 }""")
 summary=panel.locator('.click-details summary',has_text='Browser click executed')
 assert summary.count()==1
 summary.click()
 assert panel.locator('.click-details').evaluate('(e)=>e.open')
 assert 'Exact planned label matched.' in panel.locator('.click-details pre').inner_text()
 assert panel.locator('.click-details script').count()==0
 panel.evaluate("()=>document.getElementById('copylog').click()")
 panel.wait_for_function("typeof copied==='string'")
 copied=panel.evaluate('copied')
 for expected in ['tasks.0.slot_key: missing','{"kind":"plan"}','finish_reason: "stop"','test-request','test-model','DOM sent to model:', '"slots": []','slot_count: 0','test-observation']:
  assert expected in copied
 assert panel.locator('summary',has_text='DOM sent to model').count()==1
 assert 'Click details:' in copied and 'Dividend cash outflow.' in copied
 assert '"matched_option": "(Financing)"' in copied and '"x": 120' in copied
 assert 'opening_control:' in copied and 'unique_slot_label_and_overlay_geometry' in copied
 assert panel.locator('summary',has_text='Dropdown opening control: resolved').count()==1
 assert 'Scroll details:' in copied and '"top": 56' in copied
 assert panel.locator('summary',has_text='Dropdown scroll details').count()==1
 panel.close()


def test_dom_log_empty_slots_redaction_bounds_and_immutable_snapshot(extension):
 import json
 _,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
 result=w.evaluate('''async()=>{
   const body={request_id:'missing-slots',observation:{question_key:'q',document_id:'d',observation_id:'o',
     question:'Two blanks',slots:[],evidence:[{password:'secret-value',result:'Bearer private-token'}],screenshot:'data:image/png;base64,PRIVATE'}};
   await engine.logObservation('PLAN',body);
   body.observation.question='changed after logging';
   await engine.logObservation('REPAIR',{request_id:'large',observation:{slots:[],question:'x'.repeat(70000)}});
   return {events:engine.ledger.events,original:body.observation.evidence};
 }''')
 first,large=result['events']
 assert json.loads(first['dom_observation'])['slots']==[]
 assert 'Two blanks' in first['dom_observation'] and 'changed after' not in first['dom_observation']
 assert not any(s in first['dom_observation'] for s in ['secret-value','private-token','PRIVATE','screenshot'])
 assert result['original'][0]['password']=='secret-value'
 assert large['dom_log_truncated'] and len(large['dom_observation'])<66000


@pytest.mark.parametrize('first_status,second_status,expected_calls,expected_guests',[(401,200,2,1),(401,401,2,1),(400,200,1,0)])
def test_planner_renews_expired_access_once_without_invite(extension,first_status,second_status,expected_calls,expected_guests):
 _,w,_,_,_=extension
 result=w.evaluate("""async ({first,second})=>{
   await chrome.storage.local.set({token:'expired-session'});
   const original=fetch;let calls=[],guests=0;
   globalThis.fetch=async (url,options)=>{
     if(String(url).endsWith('/api/guest')){guests++;return new Response(JSON.stringify({token:'renewed-session'}));}
     calls.push({body:JSON.parse(options.body),auth:options.headers.Authorization});
     const status=calls.length===1?first:second;
     return new Response(JSON.stringify(status===200?{response:{kind:'plan'}}:{detail:'Sign in with your invite code to continue.'}),{status});
   };
   try {const data=await __assignmentHarness.plannerBridge().request('plan',{request_id:'same-request'},new AbortController().signal);return {data,calls,guests,stored:(await chrome.storage.local.get('token')).token}}
   finally{globalThis.fetch=original}
 }""",{'first':first_status,'second':second_status})
 assert len(result['calls'])==expected_calls and result['guests']==expected_guests
 assert all(c['body']['request_id']=='same-request' for c in result['calls'])
 if first_status==401:
  assert result['calls'][1]['auth']=='Bearer renewed-session'
  assert result['stored']=='renewed-session'
  if second_status==401:assert result['data']['detail'].startswith('ACCESS_EXPIRED:')

def test_visible_cursor_is_click_through_hidden_for_capture_and_removed_on_stop(extension):
 page,w,tid,_,_=extension
 result=w.evaluate("""async id=>{
   await AssignmentVisual.move(id,{x:250,y:250},()=>false);
   const inspect=()=>chrome.scripting.executeScript({target:{tabId:id},func:()=>{
     const p=document.getElementById('__assignment_lab_cursor');return {visible:p&&getComputedStyle(p).visibility==='visible',intercepts:document.elementFromPoint(250,250)===p};}});
   const before=(await inspect())[0].result;
   const withMarker=await chrome.debugger.sendCommand({tabId:id},'Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false});
   const clean=await AssignmentVisual.screenshot(id);const after=(await inspect())[0].result;
   await AssignmentVisual.detach();return {before,after,excluded:withMarker.data!==clean.dataUrl.split(',')[1]};
 }""",tid)
 assert result=={'before':{'visible':True,'intercepts':False},'after':{'visible':True,'intercepts':False},'excluded':True}
 assert page.locator('#__assignment_lab_cursor').count()==0
