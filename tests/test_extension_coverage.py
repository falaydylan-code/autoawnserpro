"""Load the actual MV3 extension and exercise its worker/page boundary."""
import functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import threading
import pytest
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def extension(tmp_path):
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    handler=functools.partial(Quiet,directory=str(ROOT/'tests'/'fixtures'))
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    # Site access is optional in the shipped manifest and granted by arming ETH,
    # which needs a real click -- chrome.permissions.request refuses to run
    # without a user gesture, so a headless test cannot take it. Load a copy of
    # the extension with that one grant already made. Every other byte is the
    # shipped code; the arming flow itself is covered by the manual checklist.
    import json,shutil
    ext=tmp_path/'extension';shutil.copytree(ROOT/'extension',ext)
    manifest=json.loads((ext/'manifest.json').read_text(encoding='utf-8'))
    manifest['host_permissions']=manifest.get('host_permissions',[])+manifest.pop('optional_host_permissions',[])
    (ext/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with sync_playwright() as p:
        context=p.chromium.launch_persistent_context(str(tmp_path/'profile'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={ext}',f'--load-extension={ext}'],
            viewport={'width':1500,'height':1100},reduced_motion='reduce')
        worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
        page=context.pages[0];page.goto(origin+'/multipart_tabs.html')
        tab_id=worker.evaluate('(url)=>chrome.tabs.query({}).then(t=>t.find(x=>x.url===url).id)',page.url)
        worker.evaluate('(origin)=>__assignmentHarness.reset(origin)',origin)
        worker.evaluate('(id)=>__assignmentHarness.injectAll(id)',tab_id)
        yield page,worker,tab_id,context,origin
        context.close()
    server.shutdown();server.server_close();thread.join(timeout=2)

def plan(worker,tab_id,include_b_ref=False):
    return worker.evaluate('''async ({id,b})=>{
      const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const find=s=>p.elements.find(e=>e.key.endsWith('#'+s))?.ref;
      h.coverage.read({question:'Calculate both amounts',plan:'a=4; b=6',parts:[
        {id:'a',what:'Part A',answer:'4',ref:find('a')},
        {id:'b',what:'Part B',answer:'6',ref:b?find('b'):null}]},p);
      return h.coverage.summary();
    }''',{'id':tab_id,'b':include_b_ref})

def execute(worker,tab_id,target,action='click',**fields):
    return worker.evaluate('''async ({id,target,action,fields})=>{
      const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const ref=p.elements.find(e=>e.key.endsWith('#'+target)).ref;
      return h.executeAction(id,{action,ref,...fields},p,{auto_submit:true,advance:false});
    }''',{'id':tab_id,'target':target,'action':action,'fields':fields})

def test_real_worker_refuses_early_submission_then_allows_verified_parts(extension):
    page,worker,tab_id,_,_=extension
    plan(worker,tab_id)
    assert execute(worker,tab_id,'a','fill',text='4',part_id='a')['ok']
    refused=execute(worker,tab_id,'submit')
    assert refused['blocked'] and 'Part B' in refused['detail']
    assert page.evaluate('submissions')==0
    # Continuing off must not prevent an intra-question Part transition.
    assert execute(worker,tab_id,'nextPart')['ok']
    plan(worker,tab_id,True)
    assert worker.evaluate('__assignmentHarness.coverage.questions.size')==1
    assert execute(worker,tab_id,'b','fill',text='6',part_id='b')['ok']
    assert execute(worker,tab_id,'submit')['ok']
    assert page.evaluate('submissions')==1
    assert page.locator('#feedback').inner_text()=='Your Answer: correct'

def test_current_observation_revokes_stale_verification(extension):
    page,worker,tab_id,_,_=extension
    plan(worker,tab_id)
    assert execute(worker,tab_id,'a','fill',text='4',part_id='a')['ok']
    execute(worker,tab_id,'submit')  # refreshes evidence, but refuses B
    page.locator('#a').fill('wrong')
    refused=execute(worker,tab_id,'submit')
    assert 'Part A' in refused['detail']
    assert page.evaluate('submissions')==0

def test_real_worker_detects_answer_oscillation(extension):
    page,worker,tab_id,_,_=extension;plan(worker,tab_id)
    for value in ['4','6','4']:
        assert execute(worker,tab_id,'a','fill',text=value,part_id='a')['ok']
    result=execute(worker,tab_id,'a','fill',text='6',part_id='a')
    assert result['blocked'] and '"4" and "6"' in result['detail']
    assert page.locator('#a').input_value()=='4'

def test_stability_wait_observes_two_equal_reads(extension):
    page,worker,tab_id,_,_=extension
    worker.evaluate('async id=>{globalThis.prior=(await __assignmentHarness.observeAllFrames(id)).digest}',tab_id)
    page.evaluate("setTimeout(()=>a.value='loading',100);setTimeout(()=>a.value='ready',300)")
    elapsed=worker.evaluate('''async id=>{const start=Date.now();const ok=await __assignmentHarness.waitForEffect(id,prior);return {ok,ms:Date.now()-start}}''',tab_id)
    assert elapsed['ok'] and elapsed['ms']>=500
    assert page.locator('#a').input_value()=='ready'

def test_badges_are_global_across_frames_and_removed_after_capture(extension):
    page,worker,tab_id,_,origin=extension
    page.evaluate('(url)=>{const f=document.createElement("iframe");f.src=url;f.style="width:900px;height:400px";document.body.append(f)}',origin+'/blanks_prose.html')
    page.frame_locator('iframe').locator('#one').wait_for()
    worker.evaluate('(id)=>__assignmentHarness.injectAll(id)',tab_id)
    result=worker.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);const image=await h.capture(id,p,true);return {refs:p.elements.map(e=>e.ref),image:image.slice(0,22)}}''',tab_id)
    assert len(set(result['refs']))==len(result['refs'])
    assert result['image'].startswith('data:image/png;base64,')
    assert page.locator('#__assignment_lab_badges').count()==0
    assert page.frame_locator('iframe').locator('#__assignment_lab_badges').count()==0

def test_stop_blocks_actions_even_with_a_completed_model_response(extension):
    page,worker,tab_id,_,_=extension;plan(worker,tab_id)
    worker.evaluate('__assignmentHarness.state.stopRequested=true')
    assert not execute(worker,tab_id,'a','fill',text='4',part_id='a')['ok']
    assert page.locator('#a').input_value()==''


def test_hidden_part_is_an_unanswered_placeholder_not_a_tab_target(extension):
    page,worker,tab_id,_,_=extension
    worker.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);h.coverage.read({question:'Calculate both amounts',parts:[
      {id:'a',what:'A',answer:'4',ref:p.elements.find(e=>e.key.endsWith('#a')).ref},
      {id:'b',what:'B unread',answer:'',ref:p.elements.find(e=>e.key.endsWith('#tabB')).ref}]},p)}''',tab_id)
    assert worker.evaluate('__assignmentHarness.coverage.ledger()[1].target_key')==''
    assert execute(worker,tab_id,'a','fill',text='4',part_id='a')['ok']
    assert execute(worker,tab_id,'tabB')['ok']
    plan(worker,tab_id,True)
    assert worker.evaluate('__assignmentHarness.coverage.ledger()[1].answer')=='6'
    assert not worker.evaluate('__assignmentHarness.coverage.ledger()[1].verified')


def test_hand_in_switch_is_independent_of_answer_completion(extension):
    page,worker,tab_id,_,_=extension
    plan(worker,tab_id)
    execute(worker,tab_id,'a','fill',text='4',part_id='a')
    execute(worker,tab_id,'tabB');plan(worker,tab_id,True)
    execute(worker,tab_id,'b','fill',text='6',part_id='b')
    result=worker.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);return h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.key.endsWith('#submit')).ref},p,{advance:true,auto_submit:false})}''',tab_id)
    assert result['blocked'] and 'switched off' in result['detail']
    assert page.evaluate('submissions')==0


def test_matching_ledger_verifies_the_planned_pair_not_answer_wording(extension):
    page,worker,tab_id,_,origin=extension
    page.goto(origin+'/matching_pointer.html')
    worker.evaluate('(id)=>__assignmentHarness.injectAll(id)',tab_id)
    worker.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      h.coverage.read({question:'Match descriptions',parts:[{id:'a',what:'Same-period collections match',answer:'Cash',ref:ref('cashTarget'),source_ref:ref('cash')}]},p);
    }''',tab_id)
    wrong=worker.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      return h.executeAction(id,{action:'drag',ref:ref('receivable'),to:ref('cashTarget'),part_id:'a'},p,{auto_submit:true,advance:false})}''',tab_id)
    assert not wrong['ok']
    result=worker.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      const result=await h.executeAction(id,{action:'drag',ref:ref('cash'),to:ref('cashTarget'),part_id:'a'},p,{auto_submit:true,advance:false});
      await h.refreshEvidence(id,await h.observeAllFrames(id));return {result,parts:h.coverage.ledger()}}''',tab_id)
    assert result['result']['ok']
    assert result['parts'][0]['verified'] and result['parts'][0]['answer']=='Cash'


# --------------------------------------------------------------------------
# a plain multiple-choice run on a model that never sends a parts checklist
# --------------------------------------------------------------------------

def mcq(worker,tab_id,page,origin):
    """Point the same tab at the styled-button MCQ fixture and re-inject."""
    page.goto(origin+'/mcq_buttons.html')
    worker.evaluate('(id)=>__assignmentHarness.injectAll(id)',tab_id)
    worker.evaluate('(origin)=>__assignmentHarness.reset(origin)',origin)

def test_an_answer_without_a_checklist_is_adopted_not_refused(extension):
    """The bug Dylan hit: every plain MCQ died because the model skipped the
    parts list and the worker refused every answer until the stall limit."""
    page,worker,tab_id,_,origin=extension
    mcq(worker,tab_id,page,origin)
    # read_check with no parts at all, as the old backend returns it
    worker.evaluate('''async (id)=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
        h.coverage.read({question:'Which account increases when a customer pays in advance?',plan:'Deferred Revenue',parts:[]},p);}''',tab_id)
    assert worker.evaluate('__assignmentHarness.coverage.summary()')=='0 of 0 parts done'
    out=execute(worker,tab_id,'optC')
    assert out['ok'],out
    ledger=worker.evaluate('__assignmentHarness.coverage.ledger()')
    assert len(ledger)==1 and ledger[0]['answer']=='Deferred Revenue', 'the click became the plan'
    worker.evaluate('''async (id)=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);await h.refreshEvidence(id,p);}''',tab_id)
    assert worker.evaluate('__assignmentHarness.coverage.summary()')=='1 of 1 parts done'
    # and with the answer verified, the only thing standing between the agent
    # and Next is the continue switch (off in this harness) -- not an outstanding part
    nxt=execute(worker,tab_id,'next')
    assert not nxt['ok'] and 'Continuing is switched off' in nxt['detail'],nxt

def test_a_planned_question_still_refuses_an_unplanned_answer(extension):
    """Adoption is only for a question with no plan. Once the model committed
    to parts, an answer aimed elsewhere still needs a fresh read_check."""
    page,worker,tab_id,_,origin=extension
    mcq(worker,tab_id,page,origin)
    worker.evaluate('''async (id)=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
        const ref=p.elements.find(e=>e.key.endsWith('#optA')).ref;
        h.coverage.read({question:'Which account increases?',plan:'Cash',parts:[{id:'a',what:'the option',answer:'Cash',ref}]},p);}''',tab_id)
    out=execute(worker,tab_id,'optC')
    assert not out['ok'] and 'not bound' in out['detail']

def test_worker_refuses_destructive_and_offsite_controls_before_the_page_does(extension):
    page,worker,tab_id,_,origin=extension
    mcq(worker,tab_id,page,origin)
    worker.evaluate('''async (id)=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
        h.coverage.read({question:'q',plan:'',parts:[]},p);}''',tab_id)
    for target in ('signout','reset','away'):
        out=execute(worker,tab_id,target)
        assert not out['ok'] and 'Refused' in out['detail'],(target,out)
    assert page.evaluate('document.body.dataset.signedOut') is None

def test_hand_in_accounts_for_every_answer_control_but_not_for_sibling_options(extension):
    """Greptile PR #3: the gate only looked for unplanned text boxes, so a
    visible unanswered radio or choice button would not stop a hand-in. The
    fix must not swing the other way and treat the three options the student
    did not pick as unanswered."""
    page,worker,tab_id,_,origin=extension
    mcq(worker,tab_id,page,origin)
    worker.evaluate('''async (id)=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
        const ref=p.elements.find(e=>e.key.endsWith('#optC')).ref;
        h.coverage.read({question:'Which account increases when a customer pays in advance?',plan:'Deferred Revenue',
          parts:[{id:'a',what:'the option',answer:'Deferred Revenue',ref}]},p);}''',tab_id)
    assert execute(worker,tab_id,'optC',part_id='a')['ok']
    refused=execute(worker,tab_id,'submitAll')
    assert refused['blocked'],refused
    # question 8's balance box is the unplanned control; optA/B/D must not be named
    assert 'Balance' in refused['detail'] and 'Cash' not in refused['detail'] and 'Accounts Receivable' not in refused['detail'],refused
    assert page.evaluate('submissions')==0
    # plan and answer question 8, then hand-in is allowed
    worker.evaluate('''async (id)=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
        const ref=p.elements.find(e=>e.key.endsWith('#balance')).ref;
        h.coverage.read({question:'Question 8. Enter the closing balance.',plan:'900',parts:[{id:'bal',what:'closing balance',answer:'900',ref}]},p);}''',tab_id)
    assert execute(worker,tab_id,'balance','fill',text='900',part_id='bal')['ok']
    allowed=execute(worker,tab_id,'submitAll')
    assert allowed['ok'],allowed
    assert page.evaluate('submissions')==1

def test_multiselect_siblings_seen_at_plan_time_are_decided_but_a_new_checkbox_blocks_hand_in(extension):
    """Greptile PR #3 round 2: checkboxes are independent, so 'one bound covers
    the group' would let a required tick go missing. But blocking every unticked
    sibling would make select-all-that-apply impossible to hand in. The line is
    whether the model could see the box when it planned: an unticked box it saw
    is a decision; one that appeared afterwards was never decided."""
    page,worker,tab_id,_,origin=extension
    page.goto(origin+'/multiselect.html')
    worker.evaluate('(id)=>__assignmentHarness.injectAll(id)',tab_id)
    worker.evaluate('(origin)=>__assignmentHarness.reset(origin)',origin)
    worker.evaluate('''async (id)=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
        const ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
        h.coverage.read({question:'Which of the following are current assets?',plan:'Cash, Accounts Receivable',
          parts:[{id:'a',what:'Cash',answer:'Cash',ref:ref('cash')},{id:'b',what:'Accounts Receivable',answer:'Accounts Receivable',ref:ref('ar')}]},p);}''',tab_id)
    assert execute(worker,tab_id,'cash',part_id='a')['ok']
    assert execute(worker,tab_id,'ar',part_id='b')['ok']
    # Land and Bonds Payable were on screen when the plan was made: leaving them
    # unticked is the answer, not an omission. Hand-in goes through.
    allowed=execute(worker,tab_id,'submitAll')
    assert allowed['ok'],allowed
    assert page.evaluate('submissions')==1
    # A checkbox that appears after planning was never decided. It blocks.
    page.evaluate('revealAnother()')
    refused=execute(worker,tab_id,'submitAll')
    assert refused['blocked'] and 'Inventory' in refused['detail'],refused
    assert 'Land' not in refused['detail'],'the seen siblings are still not named'
    assert page.evaluate('submissions')==1

def test_a_re_read_does_not_launder_a_checkbox_that_appeared_after_planning(extension):
    """Greptile PR #3 round 3: `seen` must not grow on later read_checks, or a
    mechanical recheck would count a newly revealed checkbox as decided. It is
    frozen at the first plan; a later box is covered only by a part naming it."""
    page,worker,tab_id,_,origin=extension
    page.goto(origin+'/multiselect.html')
    worker.evaluate('(id)=>__assignmentHarness.injectAll(id)',tab_id)
    worker.evaluate('(origin)=>__assignmentHarness.reset(origin)',origin)
    plan_js='''async ({id,extra})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
        const ref=s=>p.elements.find(e=>e.key.endsWith('#'+s))?.ref;
        const parts=[{id:'a',what:'Cash',answer:'Cash',ref:ref('cash')},{id:'b',what:'Accounts Receivable',answer:'Accounts Receivable',ref:ref('ar')}];
        if(extra)parts.push({id:'c',what:'Inventory',answer:'Inventory',ref:ref('inventory')});
        h.coverage.read({question:'Which of the following are current assets?',plan:'Cash, Accounts Receivable',parts},p);}'''
    worker.evaluate(plan_js,{'id':tab_id,'extra':False})
    assert execute(worker,tab_id,'cash',part_id='a')['ok']
    assert execute(worker,tab_id,'ar',part_id='b')['ok']
    page.evaluate('revealAnother()')
    # the intervening re-read that echoes the same parts -- the path Greptile named
    worker.evaluate(plan_js,{'id':tab_id,'extra':False})
    assert worker.evaluate('__assignmentHarness.coverage.questions.size')==1,'same question, not a new one'
    refused=execute(worker,tab_id,'submitAll')
    assert refused['blocked'] and 'Inventory' in refused['detail'],refused
    assert page.evaluate('submissions')==0
    # only an explicit part for the new box, entered and verified, unblocks hand-in
    worker.evaluate(plan_js,{'id':tab_id,'extra':True})
    assert execute(worker,tab_id,'inventory',part_id='c')['ok']
    allowed=execute(worker,tab_id,'submitAll')
    assert allowed['ok'],allowed
    assert page.evaluate('submissions')==1
