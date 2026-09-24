from test_extension_coverage import extension  # noqa: F401
from test_ordering_visual import navigate


def run(worker, tid, config=None, nav_mode='normal', resume=False):
    return worker.evaluate('''async ({id,config,nav_mode,resume})=>{
      const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();
      bridge.config=async()=>({advance:true,check_work:true,auto_submit:false,spend_limit:2,model:'test',...config});
      const calls=[];bridge.request=async(phase,body)=>{
        calls.push({phase,body});
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        if(phase==='navigation'){
          let c=body.candidates.find(c=>c.label==='Medium')||body.candidates[0];
          let action=body.requested_actions.includes('advance')?'advance':c.kind==='unknown'?'check':c.kind;
          if(nav_mode==='stale')await chrome.scripting.executeScript({target:{tabId:id},func:()=>document.querySelector('footer').innerHTML='<button>Changed</button>'});
          if(nav_mode==='stop')globalThis.engine.stop();
          if(nav_mode==='disabled')await chrome.scripting.executeScript({target:{tabId:id},func:()=>document.querySelectorAll('footer button').forEach(e=>e.disabled=true)});
          if(nav_mode==='denied')config.check_work=false;
          const r={kind:'action',question_key:body.observation.question_key,observation_id:body.observation.observation_id,candidate_id:c.candidate_id,action,reason:'Medium reflects the supplied pre-submission reasoning, not the entry check.'};
          if(nav_mode==='invented')r.candidate_id='other:invented';
          if(nav_mode==='final')r.action='submit';
          if(nav_mode==='review'){r.kind='needs_review';r.action=null;r.candidate_id='';r.reason='These are display controls, not question workflow actions.';}
          return {cost:.001,response:r};
        }
        const o=body.observation;
        return {cost:.001,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,
          tasks:o.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_choice_set',desired:{labels:['Keep accurate records','Protect stored records']},depends_on:[]})),
          reason:'Record keeping and protection support internal controls.',parts_declared:1}};
      };
      const saved=resume?(await chrome.storage.local.get('planner_run')).planner_run:null;
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config(),saved);
      const result=await engine.run();
      return {status:result.status,calls,ledger:result.navigation,events:result.events};
    }''', dict(id=tid,config=config or {},nav_mode=nav_mode,resume=resume))


def details(result):
    return [e['detail'] for e in result['events']]


def test_confidence_submission_then_next_and_no_revealed_answers_in_request(extension):
    page,w,tid=navigate(extension,'navigation_actions.html')
    result=run(w,tid)
    assert result['status']=='completed', details(result)[-4:]
    assert page.evaluate('clicks')==['Medium','next']
    calls=[c for c in result['calls'] if c['phase']=='navigation']
    assert len(calls)==1
    body=calls[0]['body']
    assert body['observation']['slots']==[] and 'screenshot' not in body['observation']
    assert all(c['confidence'] and c['kind']=='answer_submit' for c in body['candidates'])
    assert 'Rate your confidence' in body['candidates'][0]['context']
    assert any('Submitting this answer once' in s for s in details(result))


def test_submission_can_automatically_advance(extension):
    page,w,tid=navigate(extension,'navigation_actions.html?mode=auto')
    result=run(w,tid)
    assert result['status']=='completed',details(result)[-4:]
    assert page.evaluate('clicks')==['Medium','next']


def test_unfamiliar_check_and_continue_use_two_bounded_decisions(extension):
    page,w,tid=navigate(extension,'navigation_actions.html?mode=unknown')
    result=run(w,tid)
    assert result['status']=='completed',details(result)[-5:]
    assert page.evaluate('clicks')==['Evaluate response','next']
    assert len([c for c in result['calls'] if c['phase']=='navigation'])==2


def test_common_check_variant_uses_no_navigation_model_call(extension):
    page,w,tid=navigate(extension,'navigation_actions.html?mode=variant')
    result=run(w,tid)
    assert result['status']=='completed',details(result)[-4:]
    assert page.evaluate('clicks')==['Verify answer','next']
    assert not [c for c in result['calls'] if c['phase']=='navigation']


def test_check_setting_off_does_not_submit_confidence(extension):
    page,w,tid=navigate(extension,'navigation_actions.html')
    result=run(w,tid,config={'check_work':False})
    assert page.evaluate('clicks')==[]
    assert not [c for c in result['calls'] if c['phase']=='navigation']
    assert any('Check work is off' in s for s in details(result))


def test_continue_off_checks_but_does_not_press_next(extension):
    page,w,tid=navigate(extension,'navigation_actions.html')
    result=run(w,tid,config={'advance':False})
    assert result['status']=='finished'
    assert page.evaluate('clicks')==['Medium']


import pytest


@pytest.mark.parametrize('mode',['invented','final','stale','disabled','denied','stop'])
def test_invalid_stale_disabled_revoked_and_cancelled_decisions_do_not_click(extension,mode):
    page,w,tid=navigate(extension,'navigation_actions.html')
    result=run(w,tid,nav_mode=mode)
    assert result['status'] in ('needs_review','cancelled'),details(result)[-4:]
    assert page.evaluate('clicks')==[]


def test_unrelated_confidence_words_are_not_submission(extension):
    page,w,tid=navigate(extension,'navigation_actions.html?mode=decoy')
    result=run(w,tid,nav_mode='review')
    assert result['status']=='needs_review'
    assert page.evaluate('clicks')==[]
    offered=[c for call in result['calls'] if call['phase']=='navigation' for c in call['body']['candidates']]
    assert offered and all(not c['confidence'] for c in offered)


def test_final_assignment_is_not_downgraded_to_answer_submission(extension):
    page,w,tid=navigate(extension,'navigation_actions.html?mode=final')
    result=run(w,tid,nav_mode='final')
    assert page.evaluate('clicks')==[]
    assert not [c for c in result['calls'] if c['phase']=='navigation']


def test_uncertain_submission_is_not_repeated_on_resume(extension):
    page,w,tid=navigate(extension,'navigation_actions.html?mode=noop')
    first=run(w,tid)
    assert first['status']=='needs_review'
    assert page.evaluate('clicks')==['Medium']
    second=run(w,tid,resume=True)
    assert second['status']=='needs_review'
    assert page.evaluate('clicks')==['Medium'], (first['ledger'],second['ledger'],details(second))


def test_a_cell_opener_is_never_a_workflow_control(extension):
    """The widened scan reads unlabelled buttons too, so every dropdown arrow INSIDE a response cell became an
    'unknown' navigation candidate -- twenty on one sheet. Wrong on its own, and enough extra payload to push the
    observation past its 100 KB limit part-way through a run (test_inspection_mapping, merged 0.10.46).
    A control that belongs to an answer is not a workflow control: containment, not equality."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    found = w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});const o=await e.observe();
      return {navigation:o.navigation.map(n=>({label:n.label,kind:n.kind})),slots:o.slots.length,
        openers:await chrome.scripting.executeScript({target:{tabId:id,allFrames:true},func:()=>document.querySelectorAll('.dropdownButton').length}).then(r=>r.reduce((s,x)=>s+(x.result||0),0))}}''', tid)
    assert found['slots'] > 0 and found['openers'] > 0, found          # the page really does have cells and arrows
    assert found['navigation'] == [], found['navigation']              # and not one of them is a workflow control
