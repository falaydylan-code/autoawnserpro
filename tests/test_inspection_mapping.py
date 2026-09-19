"""Frame routing and initially absent controls, exercised through real CDP."""
import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate
from test_planner_executor import BOOT


def test_twenty_initially_inactive_cells_in_frame(extension):
 page,w,tid=navigate(extension,'planner_standard.html')
 page.evaluate("()=>document.body.innerHTML='<iframe src=custom_dropdowns.html style=\"width:950px;height:850px;border:0\"></iframe>'")
 frame=page.frame_locator('iframe');frame.locator('#cell_0_0').wait_for()
 frame.locator('body').evaluate('''e=>{
  const d=e.ownerDocument,v=d.defaultView;v.entries=0;
  for(const cell of d.querySelectorAll('td.responseCell')){
   const arrow=cell.querySelector('.dropdownButton');arrow.remove();
   cell.onclick=()=>{if(!cell.contains(arrow)){const editor=d.createElement('input');editor.type='text';editor.style.width='40px';cell.append(editor);setTimeout(()=>cell.append(arrow),40)}};
   cell.addEventListener('click',e=>{if(e.target.role==='option')v.entries++});
  }
 }''')
 assert frame.locator('[role=option],.dropdownButton').count()==0
 obs=w.evaluate(BOOT,tid);assert len(obs['slots'])==20
 w.evaluate('''()=>{const normal=engine.b.request;engine.b.request=async(phase,b)=>{
  if(phase==='plan'){
   if(b.observation.slots.some(s=>!s.options.length||s.current!==''))throw new Error('Plan arrived before complete discovery or after answer entry');
   if(b.observation.slots.some(s=>!s.dom_id||s.frame_id===0))throw new Error('Frame/element metadata missing');
  }return normal(phase,b);
 }}''')
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='finished',result['events'][-3:]
 assert frame.locator('td[data-value=Asset]').count()==10
 assert frame.locator('td[data-value="Balance Sheet"]').count()==10
 q=next(iter(result['questions'].values()));assert len(q['completed'])==20
 assert all(a=={'activate':True,'open':True} for a in q['discoveryActions'].values())
 assert len([c for c in w.evaluate('calls') if c['phase']=='plan'])==1


@pytest.mark.parametrize('targeted',[True,False])
def test_script_resolves_slot_in_question_frame_not_top_page(extension,targeted):
 page,w,tid=navigate(extension,'planner_standard.html')
 page.evaluate("()=>document.body.innerHTML='<div id=amount>WRONG TOP FRAME</div><iframe src=planner_standard.html style=\"width:950px;height:850px\"></iframe>'")
 frame=page.frame_locator('iframe');frame.locator('#amount').wait_for()
 w.evaluate(BOOT,tid)
 result=w.evaluate('''async targeted=>{
  const o=await engine.observe(),s=o.slots.find(s=>s.kind==='value');
  engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};
  await engine.inspectRequest({inspection:{slot_key:targeted?s.slot_key:'',requests:[],
   script:'const el=resolveSlot('+JSON.stringify(s.slot_key)+');return {id:el.id,tag:el.tagName,heading:document.querySelector("h1").textContent};'}},o);
  return engine.current.evidence;
 }''',targeted)
 assert len(result)==1
 assert result[0]['frame_id']>0 and result[0]['document_id']
 assert result[0]['result']['tag']=='INPUT'
 assert result[0]['result']['id']=='amount'


@pytest.mark.parametrize('mode',['idless','shadow','stale','cancelled'])
def test_inspection_binding_and_stale_cancel_guards(extension,mode):
 page,w,tid=navigate(extension,'planner_standard.html')
 if mode=='idless':page.locator('#amount').evaluate("e=>e.removeAttribute('id')")
 if mode=='shadow':
  page.locator('#amount').evaluate("e=>{const host=document.createElement('div');e.before(host);host.attachShadow({mode:'open'}).append(e)}")
 w.evaluate(BOOT,tid)
 result=w.evaluate('''async mode=>{const o=await engine.observe(),s=o.slots.find(s=>s.kind==='value');
  const info=await engine.inspect(s.frame,s.target,'inspect_slot');
  if(mode==='stale')s.frame.browser_document='expired';
  return AssignmentVisual.evaluate(engine.tabId,'const el=resolveSlot('+JSON.stringify(s.slot_key)+');return {tag:el.tagName,id:el.id};',
   {frame:s.frame,bindings:{[s.slot_key]:info.binding},stopped:()=>mode==='cancelled'});
 }''',mode)
 if mode in ('stale','cancelled'):
  assert not result['ok'] and ('TARGET_STALE' if mode=='stale' else 'CANCELLED') in result['detail']
 else:
  assert result=={'ok':True,'value':{'tag':'INPUT','id':'' if mode=='idless' else 'amount'}}


def test_failed_discovery_does_not_replay_activation_on_resume(extension):
 page,w,tid=navigate(extension,'planner_selection.html')
 page.evaluate("()=>{arrow.remove();window.activations=0;cell.onclick=()=>activations++}")
 w.evaluate(BOOT,tid)
 w.evaluate("()=>engine.b.request=async()=>({cost:0,response:{kind:'needs_review',reason:'No choices available'}})")
 result=w.evaluate('()=>engine.run()')
 assert result['status']=='needs_review' and page.evaluate('activations')==1
 result=w.evaluate('''async()=>{const old=engine;engine=new AssignmentPlanner.Engine(old.b,old.tabId,old.config,old.ledger);return engine.run()}''')
 assert result['status']=='needs_review' and page.evaluate('activations')==1
 assert not page.locator('#cell').get_attribute('data-value')
