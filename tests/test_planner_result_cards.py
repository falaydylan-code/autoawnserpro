"""Observed result-card markup; real packaged extension, scripted provider only."""
import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate
from test_planner_executor import BOOT


SETUP='''()=>{engine.b.request=async(phase,body)=>{calls.push({phase,body});if(phase==='verify')return {cost:0,response:{kind:'verified'}};const o=body.observation,s=o.slots[0];return {cost:0,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,tasks:[{task_id:'t',slot_key:s.slot_key,operation:'choose_one',desired:{label:s.options[1]},depends_on:[]}]}}}}'''


def start(extension):
    page,w,tid=navigate(extension,'planner_result_cards.html')
    w.evaluate(BOOT,tid);w.evaluate(SETUP)
    return page,w,tid


def test_exact_card_result_and_cropped_second_witness(extension):
    page,w,tid=start(extension)
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',result['events'][-1]['detail']
    assert page.evaluate('clicks')==[1]
    assert [c['phase'] for c in w.evaluate('calls')]==['plan','verify']
    verified=w.evaluate("()=>calls.find(c=>c.phase==='verify').body.observation")
    assert verified['slots'][0]['options']==['Power is shared.']
    dimensions=w.evaluate('''async()=>{const c=calls.find(c=>c.phase==='verify');const b=await createImageBitmap(await(await fetch(c.body.observation.screenshot)).blob());return {w:b.width,h:b.height}}''')
    assert 600<=dimensions['w']<=640 and 50<=dimensions['h']<=85
    assert next(iter(result['questions'].values()))['completed'][verified['slots'][0]['slot_key']]['visual_verified']


def test_revealed_correct_sibling_is_not_our_selection_or_a_repair_source(extension):
    page,w,tid=start(extension)
    w.evaluate("()=>{const request=engine.b.request;engine.b.request=async(p,b)=>{const r=await request(p,b);if(p==='plan')r.response.tasks[0].desired.label=b.observation.slots[0].options[0];return r}}")
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='needs_review'
    assert page.evaluate('clicks')==[0]
    assert [c['phase'] for c in w.evaluate('calls')]==['plan']
    assert 'marked the selected answer incorrect' in result['events'][-1]['detail']
    assert not next(iter(result['questions'].values())).get('finished')


def test_preexisting_feedback_has_no_paid_request_or_click(extension):
    page,w,tid=start(extension)
    page.evaluate("()=>grade(document.querySelectorAll('section')[0],false)")
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='needs_review'
    assert page.evaluate('clicks')==[] and w.evaluate('calls')==[]


@pytest.mark.parametrize('during',['capture','verify','stop','mismatch'])
def test_transition_and_verification_failure_never_replay_an_answer(extension,during):
    page,w,tid=start(extension)
    if during=='capture':
        w.evaluate('''()=>{const capture=AssignmentVisual.screenshot;let n=0;AssignmentVisual.screenshot=async id=>{const r=await capture(id);if(++n===2)await chrome.scripting.executeScript({target:{tabId:id},world:'MAIN',func:()=>nextQuestion()});return r}}''')
    else:
        w.evaluate('''mode=>{const request=engine.b.request;engine.b.request=async(p,b)=>{const r=await request(p,b);if(p==='verify'){if(mode==='verify')await chrome.scripting.executeScript({target:{tabId:engine.tabId},world:'MAIN',func:()=>nextQuestion()});if(mode==='stop')engine.stop();if(mode==='mismatch')r.response={kind:'mismatch',mismatches:[b.expected[0].slot_key],reason:'Unclear'};}return r}}''',during)
    result=w.evaluate('()=>engine.run()')
    assert result['status']=={'capture':'needs_review','verify':'finished','stop':'cancelled','mismatch':'needs_review'}[during],result['events'][-3:]
    assert page.evaluate('clicks')==[1]
    if during in ('capture','verify'):assert page.locator('h1').inner_text()=='Which level has authority?'
    assert len([c for c in w.evaluate('calls') if c['phase']=='plan'])==1
    if during=='capture':assert not any(c['phase']=='verify' for c in w.evaluate('calls'))
    if during!='verify':assert not next(iter(result['questions'].values())).get('finished')


def test_interrupted_result_card_attempt_cannot_replay_on_resume(extension):
    page,w,tid=start(extension)
    w.evaluate('''()=>{const request=engine.b.request;engine.b.request=async(p,b)=>{const r=await request(p,b);if(p==='verify')engine.stop();return r}}''')
    stopped=w.evaluate('()=>engine.run()')
    w.evaluate('''saved=>{engine=new AssignmentPlanner.Engine(engine.b,engine.tabId,engine.config,saved)}''',stopped)
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='needs_review'
    assert page.evaluate('clicks')==[1]
    assert 'will not be replayed' in result['events'][-1]['detail'].lower()


def test_authorized_auto_advance_plans_the_new_question_without_replaying_old_task(extension):
    page,w,tid=start(extension)
    w.evaluate('''()=>{engine.config.advance=true;engine.b.config=async()=>engine.config;const request=engine.b.request;let plans=0;engine.b.request=async(p,b)=>{
      if(p==='plan'&&++plans===2){calls.push({phase:p,body:b});return {cost:0,response:{kind:'needs_review',reason:'Stop after observing the new question'}}}
      const r=await request(p,b);if(p==='verify')await chrome.scripting.executeScript({target:{tabId:engine.tabId},world:'MAIN',func:()=>nextQuestion()});return r;
    }}''')
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='needs_review'
    assert page.evaluate('clicks')==[1]
    calls=w.evaluate('calls')
    assert [c['phase'] for c in calls]==['plan','verify','plan']
    assert calls[0]['body']['observation']['question_key']!=calls[2]['body']['observation']['question_key']
    assert sum(bool(q.get('finished')) for q in result['questions'].values())==1
