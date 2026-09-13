"""Browser contracts for the real content script, not a duplicate executor."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1500, 'height': 1100}, reduced_motion='reduce')
        yield page
        browser.close()

def load(page, fixture):
    page.goto((ROOT / 'tests' / 'fixtures' / fixture).as_uri())
    page.add_script_tag(path=str(ROOT / 'extension' / 'content.js'))
    return page.evaluate('__assignmentLab.observe()')

def by_id(page, id):
    return page.evaluate('(id)=>__assignmentLab.observe().elements.find(e=>e.key.endsWith("#"+id))', id)

def act(page, action):
    return page.evaluate('(a)=>__assignmentLab.act(a)', action)

def test_prose_blanks_context_and_decoy_group(page):
    load(page, 'blanks_prose.html')
    fields = [by_id(page, s) for s in ['one','two','three']]
    assert [f['blank'] for f in fields] == ['blank 1 of 3','blank 2 of 3','blank 3 of 3']
    assert len({f['group'] for f in fields}) == 1
    assert by_id(page, 'decoy')['group'] != fields[0]['group']
    assert '[blank 1]' in fields[1]['context'] and '[blank 3]' in fields[1]['context']
    assert act(page, {'action':'fill','ref':fields[1]['ref'],'text':'Receivable'})['ok']

def test_table_context_survives_placeholder_and_colspan(page):
    load(page, 'table_blanks.html')
    for id,row,column in [('a','Cash services','Earned'),('b','On account','Earned'),('c','Advance payment','Deferred'),('d','Prior deposit','Earned')]:
        field=by_id(page,id)
        assert field['row'] == row
        assert column in field['column']

def test_open_shadow_root_fields_are_observed(page):
    obs=load(page, 'shadow_question.html')
    assert len([e for e in obs['elements'] if e['role']=='textbox'])==2
    assert any('shadow' in s.lower() for s in obs['warnings'])

@pytest.mark.parametrize('fixture,strategy',[('matching_html5.html','html5'),('matching_pointer.html','pointer')])
def test_drag_fallbacks_and_semantic_verification(page,fixture,strategy):
    load(page, fixture)
    for id in ['cash','receivable','deferred']:
        before=page.evaluate('__assignmentLab.observe().fingerprint')
        source=by_id(page,id); target=by_id(page,id+'Target')
        result=act(page,{'action':'drag','ref':source['ref'],'to':target['ref']})
        assert result['ok'], result
        assert result['strategy']==strategy
        assert page.locator('#'+id+'Target > #'+id).count()==1
        assert page.evaluate('__assignmentLab.observe().fingerprint') != before
    assert page.locator('#submit').is_enabled()
    page.locator('#submit').click()
    assert page.locator('#feedback').inner_text()=='Your Answer: correct'

def test_impossible_drag_never_claims_success(page):
    load(page,'matching_html5.html')
    page.evaluate('document.querySelector("fieldset").insertAdjacentHTML("beforeend",\'<div id="impossible" class="target" aria-label="Unavailable target" aria-dropeffect="move"></div>\')')
    s=by_id(page,'cash');t=by_id(page,'impossible')
    result=act(page,{'action':'drag','ref':s['ref'],'to':t['ref']})
    assert result['ok'] is False
    for strategy in ['click','keyboard','html5','pointer']: assert strategy in result['detail']
    assert page.locator('#pool > #cash').count()==1

def test_new_markers_and_global_badges(page):
    load(page,'blanks_prose.html')
    page.evaluate("document.querySelector('p').insertAdjacentHTML('beforeend','<input id=new>')")
    obs=page.evaluate('__assignmentLab.observe()')
    assert next(e for e in obs['elements'] if e['key'].endswith('#new'))['new']
    ref=next(e['ref'] for e in obs['elements'] if e['key'].endswith('#one'))
    page.evaluate('(ref)=>__assignmentLab.badges([{ref,globalRef:72}])',ref)
    assert page.locator('#__assignment_lab_badges').inner_text()=='[72]'
    page.evaluate('__assignmentLab.observe()')
    assert page.locator('#__assignment_lab_badges').inner_text()=='[72]'
    page.evaluate('__assignmentLab.badgesOff()')
    assert page.locator('#__assignment_lab_badges').count()==0

def test_terminal_requires_harness_permit_and_enter_cannot_bypass(page):
    load(page,'multipart_tabs.html')
    ref=by_id(page,'submit')['ref']
    assert not act(page,{'action':'click','ref':ref})['ok']
    assert not act(page,{'action':'press','ref':ref,'key':'Enter'})['ok']
    assert page.evaluate('window.submissions')==0

def test_pointer_drag_shows_held_cursor(page):
    load(page,'matching_pointer.html')
    s=by_id(page,'cash');t=by_id(page,'cashTarget')
    page.evaluate("window.heldSeen=[];document.addEventListener('pointermove',()=>heldSeen.push(__assignmentLab.cursorHeld()))")
    assert act(page,{'action':'drag','ref':s['ref'],'to':t['ref']})['ok']
    assert page.evaluate('heldSeen.length>2 && heldSeen.every(Boolean)')
    assert not page.evaluate('__assignmentLab.cursorHeld()')


@pytest.mark.parametrize('fixture,values',[
    ('blanks_prose.html',{'one':'Cash','two':'Receivable','three':'Unearned'}),
    ('table_blanks.html',{'a':'2600','b':'1400','c':'300','d':'100'}),
    ('shadow_question.html',{'a':'10','b':'20'}),
])
def test_all_blanks_can_be_filled_and_read_back(page,fixture,values):
    load(page,fixture)
    for id,value in values.items():
        field=by_id(page,id)
        assert act(page,{'action':'fill','ref':field['ref'],'text':value})['ok']
        result=page.evaluate('(e)=>__assignmentLab.verify(e)',{'key':field['key'],'answer':value,'kind':'fill'})
        assert result['verified']


@pytest.mark.parametrize('strategy',['click','keyboard'])
def test_accessible_drag_paths_precede_synthetic_drag(page,strategy):
    load(page,'matching_html5.html')
    if strategy=='click':
        page.evaluate("cash.onclick=()=>window.chosen=cash;cashTarget.onclick=()=>{if(window.chosen)cashTarget.append(chosen)}")
    else:
        page.evaluate("document.addEventListener('keydown',e=>{if(e.key===' '&&e.target===cash)window.chosen=cash;if(e.key===' '&&e.target===cashTarget&&window.chosen)cashTarget.append(chosen)})")
    s=by_id(page,'cash');t=by_id(page,'cashTarget')
    result=act(page,{'action':'drag','ref':s['ref'],'to':t['ref']})
    assert result['ok'] and result['strategy']==strategy


def test_wrong_target_change_does_not_count_as_verified_drop(page):
    load(page,'matching_html5.html')
    page.evaluate('() => { cash.onclick=()=>receivableTarget.append(cash); }')
    s=by_id(page,'cash');t=by_id(page,'cashTarget')
    result=act(page,{'action':'drag','ref':s['ref'],'to':t['ref']})
    assert not result['ok'] and 'without the expected drop' in result['detail']
    assert page.locator('#receivableTarget > #cash').count()==1


# --------------------------------------------------------------------------
# a plain multiple-choice question with styled options, and the controls the
# agent must never operate whatever the page or the model says
# --------------------------------------------------------------------------

def test_styled_option_buttons_are_plain_buttons_and_verify_by_page_state(page):
    """Courseware options are usually <button>s, not radios. A click on one
    must be verifiable from the state the page exposes, never from the click."""
    load(page, 'mcq_buttons.html')
    opt = by_id(page, 'optC')
    assert opt['role'] == 'button' and opt['control'] == ''
    key = opt['key']
    before = page.evaluate('(k)=>__assignmentLab.verify({key:k,answer:"Deferred Revenue",kind:"click"})', key)
    assert before['visible'] and not before['verified'], 'nothing is selected yet'
    assert act(page, {'action': 'click', 'ref': opt['ref']})['ok']
    after = page.evaluate('(k)=>__assignmentLab.verify({key:k,answer:"Deferred Revenue",kind:"click"})', key)
    assert after['verified'], 'the page marked it pressed, so it verifies'
    wrong = page.evaluate('(k)=>__assignmentLab.verify({key:k,answer:"Cash",kind:"click"})', key)
    assert not wrong['verified'], 'the label has to match too'


def test_destructive_account_and_consent_controls_are_refused_in_the_page(page):
    load(page, 'mcq_buttons.html')
    for id_, word in (('signout', 'Sign out'), ('reset', 'Reset progress')):
        el = by_id(page, id_)
        assert el['control'] == 'refused', f'{word} should be classified refused'
        out = act(page, {'action': 'click', 'ref': el['ref']})
        assert not out['ok'] and 'Refused' in out['detail']
        out = act(page, {'action': 'press', 'ref': el['ref'], 'key': 'Enter'})
        assert not out['ok'], 'Enter must not bypass the refusal'
    assert page.evaluate('document.body.dataset.signedOut') is None
    assert page.evaluate('document.body.dataset.reset') is None


def test_a_question_option_that_merely_contains_a_dangerous_word_is_not_refused(page):
    """'Deleted items report' is an answer option, not a Delete button."""
    load(page, 'mcq_buttons.html')
    assert by_id(page, 'optD')['control'] == ''


def test_links_that_leave_the_site_are_refused_but_same_page_anchors_are_not(page):
    load(page, 'mcq_buttons.html')
    away, here = by_id(page, 'away'), by_id(page, 'here')
    assert away['external'] is True and here['external'] is False
    out = act(page, {'action': 'click', 'ref': away['ref']})
    assert not out['ok'] and 'leaves the assignment site' in out['detail']
    assert page.url.startswith('file:'), 'nothing navigated'
