"""Real extension tests for candidate discovery; no live services/model calls."""
import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate
from test_planner_executor import BOOT


def test_live_question_and_full_choice_text_survive_discovery(extension):
    page,w,tid=navigate(extension,'planner_discovery.html')
    before=w.evaluate(BOOT,tid)
    assert 'How is power distributed?' in before['question']
    assert 'Saved' not in before['question']
    assert len(before['slots'])==1
    slot=before['slots'][0]
    assert slot['kind']=='unresolved'
    assert slot['options']==['(Choice A) — Power is central.','(Choice B) — Power is shared.','(Choice C) — Power is local.']
    assert slot['interaction']['adapter']=='candidate_choices'
    result=w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};return engine.resolveInteractions(o)}''')
    assert result['question_key']==before['question_key']
    assert result['slots'][0]['slot_key']==slot['slot_key']
    assert result['slots'][0]['kind']=='choice'
    assert page.evaluate('clicks')==[]


# 'cards' (tabindex-only sections, no state attribute) became answerable in 0.10.41: the screen is their readback.
@pytest.mark.parametrize('mode,kind,count',[('multiple','choice_set',1),('two','choice',2),('ambiguous','unresolved',1),('cards','choice',1)])
def test_group_scope_and_unproved_semantics(extension,mode,kind,count):
    page,w,tid=navigate(extension,'planner_discovery.html?mode='+mode)
    before=w.evaluate(BOOT,tid)
    result=w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};return engine.resolveInteractions(o)}''')
    assert len(result['slots'])==count
    assert all(s['kind']==kind for s in result['slots'])
    assert not any(x in s['options'] for s in result['slots'] for x in ['Next','Show hint','Bookmark question'])
    assert result['question_key']==before['question_key']
    assert page.evaluate('clicks')==[]


def test_safe_toggle_group_executes_full_labels_and_verifies(extension):
    page,w,tid=navigate(extension,'planner_discovery.html')
    w.evaluate(BOOT,tid)
    w.evaluate('''()=>{engine.b.request=async(phase,body)=>{calls.push({phase,body});if(phase==='verify')return {cost:0,response:{kind:'verified'}};const o=body.observation;return {cost:0,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,tasks:o.slots.filter(s=>s.kind!=='unresolved').map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'choose_one',desired:{label:s.options[1]},depends_on:[]}))}}}}''')
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',result['events'][-3:]
    assert page.locator('#first button[aria-pressed=true]').inner_text()=='Power is shared.'
    assert page.evaluate('clicks')==['Power is shared.']
    assert [c['phase'] for c in w.evaluate('calls')]==['plan','verify']


def test_card_candidates_are_visible_but_never_blindly_clicked(extension):
    page,w,tid=navigate(extension,'planner_discovery.html?mode=cards')
    before=w.evaluate(BOOT,tid)
    assert len(before['slots'])==1 and before['slots'][0]['kind']=='unresolved'
    assert 'Power is shared.' in before['slots'][0]['options']
    w.evaluate('''()=>{engine.b.request=async(phase,body)=>{calls.push({phase,body});const o=body.observation;return {cost:0,response:{kind:'needs_review',question_key:o.question_key,observation_id:o.observation_id,reason:'Selection readback is unavailable'}}}}''')
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='needs_review'
    assert page.evaluate('clicks')==[]
    assert not any(e['phase']=='FINISH' for e in result['events'])


def test_new_state_evidence_promotes_same_card_slot_without_losing_context(extension):
    page,w,tid=navigate(extension,'planner_discovery.html?mode=cards');before=w.evaluate(BOOT,tid)
    page.locator('#first section').evaluate_all("es=>es.forEach(e=>e.setAttribute('aria-selected','false'))")
    after=w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};return engine.classifyCandidateChoices(o)}''')
    assert before['question_key']==after['question_key']
    assert before['slots'][0]['slot_key']==after['slots'][0]['slot_key']
    assert after['slots'][0]['kind']=='choice'
    assert before['slots'][0]['options']==after['slots'][0]['options']
    assert page.evaluate('clicks')==[]


@pytest.mark.parametrize('layout',['frame','shadow'])
def test_candidates_are_found_alongside_existing_inputs_in_other_scopes(extension,layout):
    page,w,tid=navigate(extension,'planner_discovery.html')
    if layout=='frame':
        page.goto(page.url.replace('planner_discovery.html','planner_standard.html'))
        page.evaluate("()=>{document.querySelector('main').insertAdjacentHTML('beforeend','<iframe src=planner_discovery.html style=width:1000px;height:700px></iframe>')}")
        page.frame_locator('iframe').locator('#first').wait_for()
    else:
        page.evaluate('''()=>{const h=document.createElement('div');document.querySelector('article').replaceWith(h);const shadow=h.attachShadow({mode:'open'});shadow.innerHTML='<div><p>Choose one answer.</p><ul><li><button aria-pressed=false>Left</button></li><li><button aria-pressed=false>Right</button></li></ul></div>';document.querySelector('main').insertAdjacentHTML('afterbegin','<label>Amount<input id=amount></label>')}''')
    before=w.evaluate(BOOT,tid)
    assert any(s['kind']=='value' for s in before['slots'])
    candidates=[s for s in before['slots'] if s.get('interaction',{}).get('adapter')=='candidate_choices']
    assert len(candidates)==1
    after=w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};return engine.classifyCandidateChoices(o)}''')
    assert after['question_key']==before['question_key']
    assert next(s for s in after['slots'] if s['slot_key']==candidates[0]['slot_key'])['kind']=='choice'


def test_candidate_targets_expire_after_question_or_member_replacement(extension):
    page,w,tid=navigate(extension,'planner_discovery.html');before=w.evaluate(BOOT,tid)
    page.locator('#first').evaluate("e=>e.firstElementChild.remove()")
    r=w.evaluate('''async old=>{const s=old.slots[0];try{return await engine.inspect(s.frame,s.target,'classify_choices')}catch(e){return {code:e.code}}}''',before)
    assert r['code']=='TARGET_STALE'
    assert page.evaluate('clicks')==[]


def test_multiple_toggle_answers_reconcile_the_entire_set(extension):
    page,w,tid=navigate(extension,'planner_discovery.html?mode=multiple')
    page.locator('#first button').nth(1).evaluate("e=>e.setAttribute('aria-pressed','true')")
    w.evaluate(BOOT,tid)
    w.evaluate('''()=>{engine.b.request=async(phase,body)=>{calls.push({phase,body});if(phase==='verify')return {cost:0,response:{kind:'verified'}};const o=body.observation,s=o.slots[0];return {cost:0,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,tasks:[{task_id:'t',slot_key:s.slot_key,operation:'set_choice_set',desired:{labels:[s.options[0],s.options[2]]},depends_on:[]}]}}}}''')
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',result['events'][-3:]
    assert page.locator('#first button[aria-pressed=true]').all_text_contents()==['Power is central.','Power is local.']
    assert page.locator('#hint').get_attribute('aria-pressed')=='false'


def test_feedback_and_toolbar_groups_never_supply_answer_candidates(extension):
    page,w,tid=navigate(extension,'planner_discovery.html')
    page.evaluate('''()=>{document.querySelector('main').insertAdjacentHTML('beforeend','<div class=answer-feedback><p>Choose one answer.</p><ul><li><button aria-pressed=false>SECRET KEY ONE</button></li><li><button aria-pressed=false>SECRET KEY TWO</button></li></ul></div>')}''')
    obs=w.evaluate(BOOT,tid)
    assert len(obs['slots'])==1
    assert 'SECRET KEY' not in obs['question']
    assert all('SECRET KEY' not in label for s in obs['slots'] for label in s['options'])


def test_plain_live_feedback_is_not_question_context(extension):
    page,w,tid=navigate(extension,'planner_discovery.html')
    page.evaluate('''()=>document.querySelector('main').insertAdjacentHTML('beforeend','<div aria-live=polite>The correct answer is SECRET KEY.</div><div aria-live=polite>Incorrect!</div>')''')
    obs=w.evaluate(BOOT,tid)
    assert 'How is power distributed?' in obs['question']
    assert 'SECRET KEY' not in obs['question'] and 'Incorrect!' not in obs['question']


@pytest.mark.parametrize('instruction,kind',[('Choose 1 answer:','choice'),('Select 2 answers.','choice_set'),('Choose 10 answers.','choice_set')])
def test_numeric_instruction_cardinality(extension,instruction,kind):
    page,w,tid=navigate(extension,'planner_discovery.html')
    page.locator('#instructions').evaluate('(e,text)=>e.textContent=text',instruction)
    w.evaluate(BOOT,tid)
    obs=w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};return engine.classifyCandidateChoices(o)}''')
    assert obs['slots'][0]['kind']==kind
    assert page.evaluate('clicks')==[]


def test_discovery_cap_does_not_count_unrelated_focusable_table_cells(extension):
    page,w,tid=navigate(extension,'planner_discovery.html')
    page.evaluate('''()=>{const table=document.createElement('table');table.innerHTML='<tr>'+Array.from({length:410},()=>'<td tabindex=0>Reference</td>').join('')+'</tr>';document.querySelector('main').append(table)}''')
    obs=w.evaluate(BOOT,tid)
    assert obs['discovery_complete'] is True and obs['completeness']['complete'] is True
    assert len(obs['slots'])==1
