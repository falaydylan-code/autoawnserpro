import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate
from test_planner_executor import BOOT


@pytest.mark.parametrize('mode',['success','repeated','uncertain','stop','stale'])
def test_malformed_reply_gets_one_correction_without_executing_rejected_script(extension,mode):
    page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
    result=w.evaluate('''async mode=>{
      const normal=engine.b.request;let failures=0;
      engine.b.request=async(phase,body)=>{
        if(phase==='plan'&&(failures===0||mode==='repeated')){
          failures++;calls.push({phase,body});
          if(mode==='stop')engine.stop();
          if(mode==='stale')await chrome.scripting.executeScript({target:{tabId:engine.tabId},func:()=>document.querySelector('main').setAttribute('data-question-id','different-question')});
          return {cost:mode==='uncertain'?undefined:.001,detail:'SCHEMA_INVALID: invalid JSON at line 1, column 4: Extra data. Nothing was done.',format_correction:{kind:'invalid_json'},raw_reply:':"request_inspection","inspection":{"script":"document.body.dataset.rejected=1"}'};
        }
        return normal(phase,body);
      };
      const result=await engine.run();return {result,calls,corrections:engine.current?.formatCorrections};
    }''',mode)
    assert page.locator('body').get_attribute('data-rejected') is None
    plans=[c for c in result['calls'] if c['phase']=='plan']
    if mode=='success':
        assert result['result']['status']=='finished',result['result']['events'][-3:]
        assert len(plans)==2 and plans[1]['body']['format_correction'] is True
        assert result['corrections']==1
    else:
        assert result['result']['status']!='finished'
        assert len(plans)==(2 if mode=='repeated' else 1)
        assert not any(e.get('action_executed') for e in result['result']['events'])


def test_inspections_retain_distinct_context_and_explicitly_bound_it(extension):
    page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
    r=w.evaluate('''async()=>{
      let o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};
      const request=(script)=>({inspection:{slot_key:'',requests:[],script}});
      o=await engine.inspectRequest(request('return {units:"thousands"}'),o);
      o=await engine.inspectRequest(request('return {rounding:"two decimals"}'),o);
      const retained=engine.publicObservation(o).evidence;
      let code;try{engine.mergeEvidence(Array.from({length:15},(_,i)=>({operation:'fact'+i,result:i})),o)}catch(e){code=e.code}
      const afterOverflow=engine.publicObservation(o).evidence;
      const freshScope={...o,document_id:'new-document'};engine.current.document='new-document';
      const stale=engine.publicObservation(freshScope).evidence;
      return {retained,afterOverflow,code,stale};
    }''')
    assert [e['result'] for e in r['retained']]==[{'units':'thousands'},{'rounding':'two decimals'}]
    assert r['afterOverflow']==r['retained'] and r['code']=='QUESTION_INCOMPLETE'
    assert r['stale']==[]


def test_inspect_question_promotes_a_supported_candidate_with_same_ids(extension):
    page,w,tid=navigate(extension,'planner_discovery.html');w.evaluate(BOOT,tid)
    r=w.evaluate('''async()=>{
      const before=await engine.observe();engine.current={key:before.question_key,document:before.document_id,recovery:new AssignmentPlanner.Recovery()};
      const after=await engine.inspectRequest({inspection:{slot_key:'',requests:['inspect_question']}},before);
      return {before,after,evidence:engine.publicObservation(after).evidence};
    }''')
    assert r['before']['slots'][0]['kind']=='unresolved' and r['after']['slots'][0]['kind']=='choice'
    assert r['before']['question_key']==r['after']['question_key']
    assert r['before']['slots'][0]['slot_key']==r['after']['slots'][0]['slot_key']
    assert r['evidence'][0]['result']['slots'][0]['kind']=='choice'
    assert page.evaluate('clicks')==[]


@pytest.mark.parametrize('respond_with_plan',[False,True])
def test_incomplete_observation_allows_inspection_but_not_execution(extension,respond_with_plan):
    page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
    r=w.evaluate('''async respondWithPlan=>{
      const observe=engine.observe.bind(engine),normal=engine.b.request;let first=true,plans=0;
      engine.observe=async()=>{const o=await observe();if(first){first=false;o.completeness={complete:false,note:'Question is still being rendered'}}return o};
      engine.b.request=async(phase,body)=>{if(phase==='plan'&&++plans===1&&!respondWithPlan){calls.push({phase,body});const o=body.observation;return {cost:0,response:{kind:'request_inspection',question_key:o.question_key,observation_id:o.observation_id,inspection:{slot_key:'',requests:['inspect_question'],question:'Read the newly rendered question'}}}}return normal(phase,body)};
      return {result:await engine.run(),calls};
    }''',respond_with_plan)
    assert r['calls'][0]['body']['observation']['completeness']['complete'] is False
    if respond_with_plan:
        assert r['result']['status']=='needs_review'
        assert page.evaluate('entries')==0
        assert not page.locator('input[type=radio][value=B]').is_checked()
    else:
        assert r['result']['status']=='finished',r['result']['events'][-3:]
        assert len([c for c in r['calls'] if c['phase']=='plan'])==2


def test_size_limit_stops_before_paid_inspection(extension):
    page,w,tid=navigate(extension,'planner_standard.html');w.evaluate(BOOT,tid)
    r=w.evaluate('''async()=>{const observe=engine.observe.bind(engine);engine.observe=async()=>{const o=await observe();o.completeness={complete:false,note:'Question context exceeds 60000 characters'};return o};return {result:await engine.run(),calls}}''')
    assert r['result']['status']=='needs_review' and r['calls']==[]
    assert page.evaluate('entries')==0


def test_recognized_inactive_sheet_cells_are_not_confused_with_unknown_widgets(extension):
    page,w,tid=navigate(extension,'sheet_numeric.html?locked=forever')
    page.evaluate('''()=>{
      rev.className='response shuffled groupResponse styleRight col-row-element responseCell isN';
      exp.className='styleRight response shuffled groupResponse col-row-element responseCell isN';
      net.className='response valueTolerance aria-element col-row-element responseCell isN';
      ret.className='shuffled groupResponse styleRight col-row-element responseCell isN';
      const row=ret.closest('tr').cloneNode(true);row.removeAttribute('id');const second=row.querySelector('td.responseCell');second.id='spare2';second.setAttribute('aria-label','Second spare');second.className='styleRight shuffled groupResponse col-row-element responseCell isN';ret.closest('tr').after(row);
    }''')
    before=w.evaluate(BOOT,tid)
    spare=next(s for s in before['slots'] if s['dom_id']=='ret')
    assert spare['disabled'] is True and spare['interaction']['adapter']=='sheet_inactive'
    assert spare['interaction']['evidence']==['recognized_sheet_without_editable_marker']
    assert sum(s.get('interaction',{}).get('adapter')=='sheet_text' for s in before['slots'])==3
    assert sum(s.get('interaction',{}).get('adapter')=='sheet_inactive' for s in before['slots'])==2
    r=w.evaluate('''async()=>{const normal=engine.b.request;engine.b.request=async(phase,body)=>normal(phase,{...body,observation:{...body.observation,slots:body.observation.slots.filter(s=>s.kind!=='unresolved')}});return engine.run()}''')
    assert r['status']=='finished',r['events'][-3:]
    assert page.locator('#ret').inner_text()==''
    assert not any(e.get('click_details',{}).get('slot_label')=='Retained Earnings' for e in r['events'])
    assert '2 answer location(s) are currently read-only' in next(e['detail'] for e in r['events'] if e['phase']=='FINISH')


def test_row_account_selection_unlocks_and_plans_its_amount(extension):
    page,w,tid=navigate(extension,'sheet_numeric.html?locked=forever')
    page.evaluate('''()=>{const menu=document.createElement('select');menu.id='account';menu.innerHTML='<option></option><option>Asset</option>';menu.onchange=()=>{ret.classList.add('response');wire(ret)};ret.closest('tr').cells[0].append(menu)}''')
    w.evaluate(BOOT,tid)
    w.evaluate('''()=>{const normal=engine.b.request;engine.b.request=async(phase,body)=>normal(phase,{...body,observation:{...body.observation,slots:body.observation.slots.filter(s=>s.kind!=='unresolved')}})}''')
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',result['events'][-3:]
    assert page.locator('#ret').inner_text()=='42'
    assert len([c for c in w.evaluate('calls') if c['phase']=='plan'])==2
