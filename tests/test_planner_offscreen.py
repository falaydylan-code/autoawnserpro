"""Real wheel input must reveal rendered fields, never turn hidden fields visible."""
import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate
from test_planner_executor import BOOT

@pytest.mark.parametrize('mode',['page_down','page_up','horizontal','frame_below','frame_page','inner_container'])
def test_reveal_answer_before_typing(extension,mode):
    page,w,tid=navigate(extension,'planner_standard.html')
    if mode in ('frame_below','frame_page'):
        page.evaluate('''mode=>{document.body.innerHTML='<h1>Shared question</h1><iframe src="planner_standard.html" style="margin-left:80px;width:900px;height:600px"></iframe><div style="height:1500px"></div>';
          if(mode==='frame_below')document.querySelector('iframe').style.marginTop='2200px';}''',mode)
        frame=page.frame_locator('iframe');frame.locator('#amount').wait_for()
    else: frame=page
    frame.locator('body').evaluate('''(e,mode)=>{const d=e.ownerDocument;
      d.body.innerHTML='<main data-question-id="scroll"><h1>Enter 42</h1><div id="space"></div><label>Answer <input id="answer"></label><div style="height:1600px"></div><div hidden><input id="hidden"></div><input id="csshidden" style="display:none"><div aria-hidden="true"><input id="ariahidden"></div></main>';
      if(['page_down','page_up','frame_page'].includes(mode))d.getElementById('space').style.height='2200px';
      if(mode==='horizontal')d.getElementById('answer').parentElement.style.cssText='display:block;margin-left:2200px;width:300px';
      if(mode==='inner_container'){const label=d.getElementById('answer').parentElement,wrap=d.createElement('div');wrap.style.cssText='height:220px;overflow:auto;width:500px';label.before(wrap);wrap.innerHTML='<div style="height:1100px"></div>';wrap.append(label)}
      if(mode==='page_up')d.defaultView.scrollTo(0,3800);
    }''',mode)
    initial=w.evaluate(BOOT,tid)
    assert len(initial['slots'])==1 and initial['slots'][0]['dom_id']=='answer'
    result=w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};
      try{await engine.execute({task_id:'t',slot_key:o.slots[0].slot_key,operation:'enter_value',desired:{value:'42'}});return {ok:true,events:engine.ledger.events}}catch(e){return {code:e.code,detail:e.message,events:engine.ledger.events}}}''')
    assert result.get('ok'),result
    assert frame.locator('#answer').input_value()=='42'
    assert frame.locator('#hidden').input_value()=='' and frame.locator('#csshidden').input_value()==''
    assert frame.locator('#ariahidden').input_value()==''
    scrolls=[e['scroll_details'] for e in result['events'] if e.get('scroll_details')]
    assert scrolls and all(s['moved'] for s in scrolls)
    if mode!='inner_container': assert all(s['adapter']=='page_wheel' for s in scrolls)
    if mode=='page_up': assert scrolls[0]['delta']['y']<0
    if mode=='horizontal': assert scrolls[0]['delta']['x']>0
    assert not w.evaluate('calls')  # scrolling is deterministic, not paid model work

@pytest.mark.parametrize('mode',['stopped','no_movement','overlay','hidden_after_read','document_changed'])
def test_scroll_failures_do_not_click_or_type(extension,mode):
    page,w,tid=navigate(extension,'planner_standard.html')
    page.evaluate('''()=>document.body.innerHTML='<main data-question-id="scroll"><h1>Enter 42</h1><div style="height:2000px"></div><input id="answer" aria-label="Answer"><div style="height:1600px"></div></main>' ''')
    initial=w.evaluate(BOOT,tid)
    if mode=='no_movement': page.evaluate("()=>document.addEventListener('wheel',e=>e.preventDefault(),{passive:false})")
    if mode=='hidden_after_read': page.locator('#answer').evaluate("e=>e.style.display='none'")
    if mode=='overlay': page.evaluate("()=>{window.scrollTo(0,1900);const x=document.createElement('div');x.style.cssText='position:fixed;inset:0;background:white;z-index:9';document.body.append(x)}")
    result=w.evaluate('''async({mode,initial})=>{engine.current={key:initial.question_key,document:initial.document_id,recovery:new AssignmentPlanner.Recovery()};
      if(mode==='stopped'||mode==='document_changed'){const wheel=AssignmentVisual.wheel;AssignmentVisual.wheel=async(...args)=>{const r=await wheel(...args);if(mode==='stopped')engine.stop();else await chrome.tabs.reload(engine.tabId);return r}}
      try{await engine.execute({task_id:'t',slot_key:initial.slots[0].slot_key,operation:'enter_value',desired:{value:'42'}});return {ok:true}}catch(e){return {code:e.code,detail:e.message,events:engine.ledger.events}}}''',{'mode':mode,'initial':initial})
    assert not result.get('ok'),result
    assert result['code'] in ('INPUT_NO_EFFECT','GUARD_REJECTED','CANCELLED','TARGET_MISSING','TARGET_STALE','FRAME_UNREADABLE'),result
    assert not any(e.get('click_details') for e in result['events'])
    if mode!='document_changed': assert page.locator('#answer').input_value()==''

def test_offscreen_sheet_identification_and_typing_after_page_scroll(extension):
    page,w,tid=navigate(extension,'spreadsheet_text.html')
    page.evaluate("()=>{const spacer=document.createElement('div');spacer.style.height='2400px';document.querySelector('#sheet').before(spacer)}")
    initial=w.evaluate(BOOT,tid)
    assert sum(s['kind']=='unresolved' for s in initial['slots'])==9
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',result['events'][-4:]
    assert page.locator('td.response').all_text_contents()==['42']*9
    assert len(page.evaluate('entries'))==9
    assert [c['phase'] for c in w.evaluate('calls')].count('plan')==1
    assert any(e.get('scroll_details',{}).get('adapter')=='page_wheel' for e in result['events'])

def test_page_scroll_attempts_are_bounded(extension):
    page,w,tid=navigate(extension,'planner_standard.html')
    page.evaluate("()=>document.body.innerHTML='<main data-question-id=bounded><h1>Enter amount</h1><div style=height:20000px></div><input id=answer><div style=height:1200px></div></main>'")
    w.evaluate(BOOT,tid)
    result=w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};
      try{await engine.execute({slot_key:o.slots[0].slot_key,operation:'enter_value',desired:{value:'42'}})}catch(e){return {code:e.code,events:engine.ledger.events}}}''')
    assert result['code']=='TARGET_MISSING'
    assert len([e for e in result['events'] if e.get('scroll_details')])==12
    assert not any(e.get('click_details') for e in result['events'])
    assert page.locator('#answer').input_value()==''
