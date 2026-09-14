"""Real extension + CDP input with a scripted planner, no provider calls."""
import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate

BOOT='''async id=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
 const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
 bridge.request=async(phase,body)=>{globalThis.calls.push({phase,body});return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks:body.observation.slots.map((s,i)=>{
 const ops={choice:'choose_one',choice_set:'set_choice_set',value:'enter_value',selection:'set_selection',ordering:'set_order',position:'place_points'};
 let desired=s.kind==='choice'?{label:'B'}:s.kind==='choice_set'?{labels:['A','C']}:s.kind==='value'?{value:'42'}:s.kind==='ordering'?{sequence:['Revenues','Expenses','Net Income']}:{label:s.label.includes('Statement')?'Balance Sheet':'Asset'};
 return {task_id:'t'+i,slot_key:s.slot_key,operation:ops[s.kind],desired,depends_on:[]};})}}};
 globalThis.calls=[];globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());return engine.observe();}'''

def test_one_plan_choices_text_readback_without_vision(extension):
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
 calls=w.evaluate('calls');assert len(calls)==1 and not calls[0]['body']['observation'].get('screenshot')
 q=next(iter(result['questions'].values()));assert len(q['completed'])==3
 assert all(p['entry_verified'] for p in q['completed'].values())

def test_twenty_dropdown_slots_one_plan(extension):
 page,w,tid=navigate(extension,'custom_dropdowns.html');obs=w.evaluate(BOOT,tid)
 assert len(obs['slots'])==20
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-1]['detail']
 assert page.locator('td[data-value=Asset]').count()==10
 assert page.locator('td[data-value="Balance Sheet"]').count()==10
 assert w.evaluate('calls.length')==1
 q=next(iter(result['questions'].values()));assert len(q['completed'])==20

def test_resume_reconciles_without_replaying_completed_input(extension):
 page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid);first=w.evaluate('()=>engine.run()');entries=page.evaluate('entries')
 result=w.evaluate('''async()=>{const old=engine;engine=new AssignmentPlanner.Engine(old.b,old.tabId,old.config,old.ledger);return engine.run()}''')
 assert result['status']=='finished',result['events'][-3:]
 assert page.evaluate('entries')==entries and w.evaluate('calls.length')==1

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
 page,w,tid=navigate(extension,'planner_standard.html');page.evaluate("()=>{const p=document.createElement('input');p.type='password';p.value='never-record-this';document.querySelector('main').append(p)}")
 obs=w.evaluate(BOOT,tid)
 assert 'never-record-this' not in str(obs)
 _,_,_,_,origin=extension
 page.evaluate("url=>{const f=document.createElement('iframe');f.src=url;document.querySelector('main').append(f)}",origin+'/custom_dropdowns.html')
 page.frame_locator('iframe').locator('#cell_0_0').wait_for()
 obs=w.evaluate('()=>engine.observe()');assert len(obs['slots'])==23

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
 assert page.locator('td[data-value]').count()==20 and w.evaluate('calls.length')==1

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

def test_permitted_cross_origin_frame_input_and_unreadable_frame(extension):
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
  w.evaluate(BOOT,tid);result=w.evaluate('()=>engine.run()')
  assert result['status']=='finished',result['events'][-1]['detail']
  assert page.frame_locator('iframe').locator('#amount').input_value()=='42'
  w.evaluate("()=>engine.b.allowed=origin=>!origin.includes('"+str(server.server_port)+"')")
  result=w.evaluate('async()=>{try{await engine.observe();return null}catch(e){return e.code}}')
  assert result=='FRAME_UNREADABLE'
 finally:server.shutdown();server.server_close();thread.join(timeout=2)
