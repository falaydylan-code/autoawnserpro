/* Protocol 4 deterministic execution. No answer model calls inside widget adapters. */
(() => {
  const norm=s=>String(s??'').replace(/\s+/g,' ').replace(/\s*\[active\]\s*/g,' ').trim();
  // A number as a page shows it ("$91,300", "(1,200)", "47,700.00", "12 %") and as a model writes it ("91300") are the
  // same answer. Returns the number, or null when the text is not a plain amount; null keeps the exact-text rule.
  const numeric=text=>{let t=String(text??'').replace(/[\s$€£¥,]/g,'');if(!t)return null;let neg=false;
    if(/^\(.*\)$/.test(t)){neg=true;t=t.slice(1,-1)}if(t.startsWith('-')){neg=!neg;t=t.slice(1)}else if(t.startsWith('+'))t=t.slice(1);
    if(!/^\d+(\.\d+)?%?$/.test(t))return null;const v=parseFloat(t.replace('%',''));return neg?-v:v};
  const sameValue=(shown,wanted)=>{const a=numeric(shown),b=numeric(wanted);return a!==null&&b!==null?Math.abs(a-b)<1e-9:String(shown??'')===String(wanted??'')};
  // Digits only into a number field: "$91,300" typed into a numeric cell is either reformatted by the page or refused.
  const plainDigits=text=>{const v=numeric(text);return v===null?String(text??''):String(v)};
  const hash=s=>{let n=2166136261;for(const c of s)n=Math.imul(n^c.charCodeAt(0),16777619);return (n>>>0).toString(16)};
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  async function regionHash(shot,box){const bitmap=await createImageBitmap(await (await fetch(shot.dataUrl)).blob());const scale=bitmap.width/shot.viewport.width;
    const canvas=new OffscreenCanvas(Math.max(1,Math.round(box.w*scale)),Math.max(1,Math.round(box.h*scale))),ctx=canvas.getContext('2d');
    ctx.drawImage(bitmap,box.x*scale,box.y*scale,box.w*scale,box.h*scale,0,0,canvas.width,canvas.height);bitmap.close();
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',ctx.getImageData(0,0,canvas.width,canvas.height).data))).map(x=>x.toString(16).padStart(2,'0')).join('');}
  function visualGeometry(r,box){
    const fit=ticks=>{if(ticks.length<2)return null;const a=ticks[0],b=ticks.find(t=>t.value!==a.value);if(!b)return null;const scale=(b.fraction-a.fraction)/(b.value-a.value),origin=a.fraction-a.value*scale;
      if(!Number.isFinite(scale)||Math.abs(scale)<1e-12||ticks.some(t=>Math.abs(t.fraction-(origin+t.value*scale))>.015))return null;
      return {scale,origin,min:Math.min(...ticks.map(t=>t.value)),max:Math.max(...ticks.map(t=>t.value))};};
    const x=fit(r.x_ticks||[]),y=fit(r.y_ticks||[]);
    if(r.kind!=='geometry'||!x||!y||!(r.points?.length))throw new Fault('GEOMETRY_UNCALIBRATED',r.reason||'Visible ticks do not establish consistent axes.');
    return {calibrated:true,visual:true,labeled:r.points.some(p=>!/^p\d+$/.test(p.id)),units:'math',x,y,matrix:{a:box.w,b:0,c:0,d:box.h,e:box.x,f:box.y},
      tolerance:Math.max(2/(box.w*Math.abs(x.scale)),2/(box.h*Math.abs(y.scale))),
      points:r.points.map(p=>({id:p.id,x:(p.x-x.origin)/x.scale,y:(p.y-y.origin)/y.scale,viewport:{x:box.x+p.x*box.w,y:box.y+p.y*box.h}}))};
  }

  const LIMITS={ui:5000,navigation:15000,local:2,repairs:2,inspections:2,verify:2,noProgress:90000,question:300000,plan_rounds:2,slowInput:1000};   // model wait time is excluded from the clocks (Recovery.exclude); the request deadline is the backend's
  const TASK_OPERATION={value:'enter_value',selection:'set_selection',choice:'choose_one',choice_set:'set_choice_set',ordering:'set_order',position:'place_points'};
  // The value a task intends, rendered for the second-witness screenshot check.
  // place_points has no textual value -- the graph is confirmed by its own
  // calibrated readback, so it is excluded from the visual answer list.
  // What `other` says that `base` does not: the shared stem before and after the tab panel is stripped.
  // What `other` says that `base` does not: the shared stem before and after the tab panel is stripped, cut back to
  // sentence boundaries so a clause that merely starts like another ("Prepare an..." / "Prepare the...") stays whole.
  const added=(base,other)=>{let i=0;while(i<base.length&&i<other.length&&base[i]===other[i])i++;const cut=other.lastIndexOf('. ',i);i=cut>=0?cut+2:0;
    let j=0;while(j<base.length-i&&j<other.length-i&&base[base.length-1-j]===other[other.length-1-j])j++;const end=other.indexOf('. ',other.length-j);j=end>=0?other.length-(end+1):0;
    const mid=other.slice(i,other.length-j).trim();return mid||other};
  const plannedValue=task=>{const d=task.desired||{};switch(task.operation){
    case 'choose_one':case 'set_selection':return d.label||'';
    case 'enter_value':return d.value||'';
    case 'set_choice_set':return (d.labels||[]).join(', ');
    case 'set_order':return (d.sequence||[]).join(' > ');
    default:return '';}};
  class Fault extends Error{constructor(code,detail,actual=null){super(code+': '+detail);this.code=code;this.actual=actual}}
  const requireOK=r=>{if(!r?.ok)throw new Fault(r?.code||'INPUT_NO_EFFECT',r?.detail||'Browser operation failed.',r?.data??null);return r};
  class Recovery {
    constructor(saved={}){Object.assign(this,{started:Date.now(),progressAt:Date.now(),local:{},signatures:{},states:{},repairs:0,inspections:0,history:[]},saved)}
    check(){if(Date.now()-this.started>LIMITS.question)throw new Fault('BUDGET_EXHAUSTED','Question deadline reached.');if(Date.now()-this.progressAt>LIMITS.noProgress)throw new Fault('REPEATED_STATE','No meaningful question progress for 90 seconds.')}
    progress(){this.progressAt=Date.now()}
    // Time spent waiting for the model is not the page stalling: it is taken out of both clocks, so a long think (a
    // large token allowance) cannot end the run as 'no progress' or 'deadline reached' while the answer is on its way.
    exclude(ms){this.started+=ms;this.progressAt+=ms}
    failure(task,error,actual){this.check();const slot=task.slot_key;const sig=hash(JSON.stringify([slot,task.operation,task.desired,error.code,actual]));const seen=(this.signatures[sig]||0)+1;this.signatures[sig]=seen;
      this.history.push({slot,code:error.code,detail:error.message,signature:sig,actual});this.history=this.history.slice(-10);
      const states=this.states[slot]||[];states.push(sig);this.states[slot]=states.slice(-3);
      if(seen>=2||states.length>=3&&states.at(-1)===states.at(-3))throw new Fault('REPEATED_STATE','The same task failed again without new evidence.',actual);
      if(error.code==='GUARD_REJECTED')throw error;
      const n=this.local[slot]||0;this.local[slot]=n+1;return n<LIMITS.local;
    }
  }
  class Engine {
    constructor(bridge,tabId,config,saved=null){this.b=bridge;this.tabId=tabId;this.config=config;this.id=saved?.id||crypto.randomUUID();this.generation=crypto.randomUUID();this.abort=new AbortController();this.ledger=saved||{id:this.id,questions:{},cost:0,events:[],status:'ready'};this.current=null;this.busy=false;this.cancelled=false;this.steps=0;this.frameDocs=new Map()}
    stop(){this.cancelled=true;this.abort.abort();this.generation=crypto.randomUUID()}
    async guard(){if(this.cancelled||this.b.stopped())throw new Fault('CANCELLED','Stopped by user.');await this.b.bound(this.tabId);this.current?.recovery.check();
      if(this.current?.frameDocuments)for(const f of this.current.frameDocuments){let identity;try{identity=await chrome.tabs.sendMessage(this.tabId,{type:'planner_inspect',operation:'identity'},{frameId:f.frame_id})}catch{throw new Fault('TARGET_STALE','Document was replaced.')}if(identity?.document_id!==f.document_id)throw new Fault('TARGET_STALE','Document was replaced.');}}

    async persist(){
      // Bound durable DOM history so diagnostics cannot exhaust extension storage.
      let chars=0;
      for(const row of [...this.ledger.events].reverse())if(row.dom_observation){
        chars+=row.dom_observation.length;
        if(chars>1048576){row.dom_observation='[Older DOM snapshot omitted from saved history: 1 MB retention limit]';row.dom_log_truncated=true;}
      }
      await chrome.storage.local.set({planner_run:JSON.parse(JSON.stringify(this.ledger))});
    }
    async logObservation(phase,body){
      // Record the actual outbound structured DOM, not a later re-observation.
      // Never copy pixels, request credentials, or unrelated page HTML.
      const {screenshot,...dom}=body.observation;
      const text=JSON.stringify(dom,(key,value)=>{
        if(/^(password|passwd|authorization|cookie|access_token|refresh_token|api_key|secret)$/i.test(key))return '[redacted]';
        return typeof value==='string'?value.replace(/\bBearer\s+[A-Za-z0-9._~+\/-]+=*/gi,'Bearer [redacted]'):value;
      },2);
      const limit=65536;
      await this.event(phase,'DOM observation sent to model',{
        request_id:body.request_id,question_key:dom.question_key,document_id:dom.document_id,
        observation_id:dom.observation_id,slot_count:dom.slots?.length||0,
        screenshot_attached:!!screenshot,dom_observation:text.length>limit?text.slice(0,limit)+'\n[DOM log truncated; request was unchanged]':text,
        dom_log_truncated:text.length>limit,dom_log_characters:text.length,
      });
    }
    async event(phase,detail,fields={}){this.ledger.phase=phase;const row={time:new Date().toISOString(),run_id:this.id,question_key:this.current?.key,phase,detail,...fields};this.ledger.events.push(row);if(this.ledger.events.length>1000)this.ledger.events.shift();await this.persist();this.b.emit({kind:phase==='NEEDS_REVIEW'?'error':'info',message:detail,phase,...fields});}
    async observe(){await this.guard();
      const locations=await chrome.scripting.executeScript({target:{tabId:this.tabId,allFrames:true},func:()=>({origin:location.origin,url:location.href})});
      const frames=[],queue=[locations.find(f=>f.frameId===0)],visited=new Set();let excluded=0;
      while(queue.length){const f=queue.shift();if(!f)throw new Fault('FRAME_UNREADABLE','Top assignment frame unavailable.');if(visited.has(f.frameId))continue;visited.add(f.frameId);
        // The top frame is the bound tab (its site is already enforced). Any other
        // queued frame outside the authorized site is EXCLUDED, never fatal -- an
        // unrelated cross-site ad, video or support widget must not stop a readable
        // question. Whether an exclusion actually matters is decided below, once we
        // know if any answer slot survived.
        if(f.frameId!==0&&!this.b.allowed(f.result.origin)){excluded++;continue;}
        await this.guard();await chrome.scripting.executeScript({target:{tabId:this.tabId,frameIds:[f.frameId]},files:['planner_content.js']});let p;
        try{p=await chrome.tabs.sendMessage(this.tabId,{type:'planner_inspect',operation:'observe'},{frameId:f.frameId})}catch{if(f.frameId===0)throw new Fault('FRAME_UNREADABLE','Top assignment frame did not respond.');excluded++;continue}
        requireOK(p);frames.push({...p,frame_id:f.frameId,browser_document:f.documentId});
        for(const child of p.frames){const candidates=locations.filter(n=>n.frameId!==f.frameId&&n.result.url===child.src);
          // Follow a child only when it resolves to exactly one allowed same-site
          // frame. An ambiguous (duplicate-URL) or cross-site child is excluded,
          // not fatal; the no-slot check below turns it into FRAME_UNREADABLE only
          // if the question actually depended on it.
          if(candidates.length===1&&this.b.allowed(candidates[0].result.origin))queue.push(candidates[0]);else excluded++;}
      }
      if(!frames.length)throw new Fault('FRAME_UNREADABLE','No readable assignment frame.');
      const frameOffset=(f,seen=new Set())=>{if(f.frame_id===0)return {x:0,y:0};if(seen.has(f.frame_id))return null;seen.add(f.frame_id);
        const owners=frames.flatMap(parent=>parent.frames.filter(child=>child.src===f.url).map(child=>({parent,child})));if(owners.length!==1||!owners[0].child.exact)return null;
        const {parent,child}=owners[0],above=frameOffset(parent,seen);return above?{x:above.x+child.x,y:above.y+child.y}:null};
      for(const f of frames)f.measured_offset=frameOffset(f);
      const active=frames.filter(f=>f.slots.length),used=active.length?active:frames;
      const question_key=hash(used.map(f=>f.frame_id+':'+f.question_key).join('|'));
      const document_id=hash(frames.map(f=>f.frame_id+':'+f.document_id+':'+f.browser_document).join('|'));
      const slots=active.flatMap(f=>f.slots.map(s=>({...s,slot_key:question_key+'/'+f.frame_id+'/'+s.slot_key,local_slot:s.slot_key,frame_id:f.frame_id,frame:f})));
      // Excluding an unrelated frame is fine as long as a readable frame still
      // holds answer slots. If nothing readable has a slot AND a frame was
      // excluded, the question may have lived in the excluded frame: say so
      // explicitly rather than planning on a partial view.
      if(!slots.length&&excluded)throw new Fault('FRAME_UNREADABLE','A frame that may hold the question could not be read (cross-site, ambiguous, or unresponsive); its contents were excluded.');
      let table_context_complete=frames.every(f=>f.table_context_complete!==false),tableBytes=0;const tables=[];
      for(const f of [...used,...frames.filter(f=>!used.includes(f))])for(const t of f.tables||[]){const item={...t,frame_id:f.frame_id},size=JSON.stringify(item).length;
        if(tables.length>=12||tableBytes+size>60000){table_context_complete=false;continue}tables.push(item);tableBytes+=size;}
      // The question TEXT comes from EVERY observed frame, not only the frames that
      // hold answer cells. Courseware routinely puts the stem/instructions in the
      // parent page (or a middle LTI frame) and the widget in an iframe; keying the
      // text to slot frames silently dropped "solve for the missing amounts" and
      // left the model to guess the task. Identity (question_key, above) still
      // hashes the slot frames only, so the key stays stable. Frames are in BFS
      // order so the stem leads; deduped so a single-frame page repeats nothing;
      // bounded under the backend's question limit.
      const fullQuestionText=[...new Set(frames.map(f=>f.question).filter(Boolean))].join('\n'),questionText=fullQuestionText.slice(0,60000);
      const parts=frames.flatMap(f=>(f.parts||[]).map(p=>({...p,frame_id:f.frame_id,frame:f})));
      const obs={question_key,document_id,observation_id:crypto.randomUUID(),question:questionText,tables,table_context_complete,slots,frames,parts,discovery_complete:frames.every(f=>f.discovery_complete!==false),
        completeness:{complete:fullQuestionText.length<=60000&&slots.length<=100&&frames.every(f=>f.completeness.complete),note:(fullQuestionText.length>60000?'Question context exceeds 60000 characters; missing context must be recovered. ':'')+(slots.length>100?'More than 100 answer slots; narrow the question scope. ':'')+frames.map(f=>f.completeness.note).filter(Boolean).join('; ')},
        enumeration:frames.find(f=>f.enumeration)?.enumeration||null,
        page_state:frames.find(f=>f.page_state!=='answering')?.page_state||'answering',host:frames[0].host,
        navigation:frames.flatMap(f=>f.navigation.map(n=>({...n,frame:f}))),feedback:frames.map(f=>f.feedback).filter(Boolean).join('; '),
        grade_state:frames.find(f=>f.grade_state!=='unknown')?.grade_state||'unknown',save_state:frames.some(f=>f.save_state==='pending')?'pending':frames.some(f=>f.save_state==='confirmed')?'confirmed':'unavailable',visual:frames.some(f=>f.visual)};
      if(new Set(slots.map(s=>s.slot_key)).size!==slots.length)throw new Fault('TARGET_AMBIGUOUS','Duplicate logical slots.');
      return obs;
    }
    same(obs){if(!this.current||obs.question_key!==this.current.key||obs.document_id!==this.current.document)throw new Fault('TARGET_STALE','Question or document changed; pending task discarded.')}
    slot(obs,key){this.same(obs);const s=obs.slots.filter(s=>s.slot_key===key);if(s.length===1&&!s[0].geometry?.calibrated&&this.current.visual?.[key]){s[0].geometry=this.current.visual[key];s[0].current=s[0].geometry.points;}
      // A group with no DOM selected-state cannot report what is selected; the harness remembers what it confirmed
      // on screen, and every readback of that slot goes through this memory.
      if(s.length===1&&s[0].interaction?.evidence?.verification==='visual_change'){const seen=this.current?.visualSelections?.[key]||[];s[0].current=[...seen];for(const c of s[0].choices||[])c.checked=seen.includes(c.label);}
      if(s.length!==1)throw new Fault(s.length?'TARGET_AMBIGUOUS':'TARGET_MISSING','Logical answer slot is not unique.');return s[0]}
    async inspect(frame,target,operation='measure_target',extra={}){await this.guard();let r;try{r=await chrome.tabs.sendMessage(this.tabId,{type:'planner_inspect',operation,target,document_id:frame.document_id,observation_id:frame.observation_id,...extra},{frameId:frame.frame_id})}catch{await this.guard();throw new Fault('FRAME_UNREADABLE','The target frame stopped responding during inspection.')}requireOK(r);if(r.local&&!r.viewport&&frame.measured_offset)r.viewport={...r.local,x:r.local.x+frame.measured_offset.x,y:r.local.y+frame.measured_offset.y};for(const c of r.scroll?.containers||r.containers||[]){if(c.local&&!c.viewport&&frame.measured_offset)c.viewport={...c.local,x:c.local.x+frame.measured_offset.x,y:c.local.y+frame.measured_offset.y}}return r}
    async measure(frame,target,context={}){
      const check={...(context.menu_owner?{expected_menu_owner:context.menu_owner}:{}),...(context.value_owner?{expected_value_owner:context.value_owner}:{}),...(['activate_cell','discover_activate_cell','identify_cell','identify_editor'].includes(context.purpose)?{activation_only:true}:{})};
      for(let i=0;i<12;i++){
        // Page scrolling moves iframe origins too. Refresh the frame tree, but
        // preserve the caller's frame object so later focus checks use fresh refs.
        const obs=await this.observe();if(this.current)this.same(obs);
        const live=obs.frames.find(f=>f.frame_id===frame.frame_id&&f.document_id===frame.document_id);
        if(!live)throw new Fault('TARGET_STALE','Answer frame was replaced while revealing its target.');
        Object.assign(frame,live);
        const r=await this.inspect(frame,target,'measure_target',{...check,activation_only:false});
        if(!r.viewport)throw new Fault('GEOMETRY_UNCALIBRATED','Frame transform is not measurable.');
        // Reveal enclosing frames from the outer page inward. An iframe is a
        // boundary to inspect, not an answer to click. Clamp to its viewport
        // when the actual target first needs scrolling within the child page.
        // What an outer layer must show is the SCROLL AREA that has to move,
        // never the target itself: an option far down a long list renders
        // below the page fold while its list is in view, and chasing the option
        // dragged the open list under the fixed header (M3-9, 12:22 PM).
        const mover=m=>m.scroll?.clipped?m.scroll.containers.find(c=>c.clipped&&c.scrollable&&(c.delta.x||c.delta.y)&&c.viewport?.w>2&&c.viewport?.h>2)||null:null;
        const reveal=m=>{const c=mover(m);return c?.wheel_hit&&c.wheel_point?c.wheel_point:null};
        const route=[{frame,target,measurement:r,check}];let child=frame,point=reveal(r)||r.click_point;
        const seen=new Set();
        while(child.frame_id!==0){
          if(seen.has(child.frame_id))throw new Fault('FRAME_UNREADABLE','Frame ancestry is cyclic.');seen.add(child.frame_id);
          const owners=obs.frames.flatMap(parent=>parent.frames.filter(f=>f.src===child.url).map(f=>({parent,box:f})));
          if(owners.length!==1||!owners[0].box.exact)throw new Fault('GEOMETRY_UNCALIBRATED','Frame ancestry is not uniquely measurable.');
          const {parent,box}=owners[0];
          point={x:box.x+Math.max(2,Math.min(box.w-2,point.x)),y:box.y+Math.max(2,Math.min(box.h-2,point.y))};
          const measured=await this.inspect(parent,box.target,'measure_target',{point});
          route.unshift({frame:parent,target:box.target,measurement:measured,check:{point}});child=parent;point=reveal(measured)||point;
        }
        const blocked=route.find(step=>step.measurement.scroll?.clipped);
        if(blocked){
          const m=blocked.measurement;
          const c=mover(m);
          if(!c)throw new Fault('TARGET_MISSING','Target is clipped; no visible scroll area can reveal it.',m.scroll);
          if(!c.wheel_hit||!c.wheel_point)throw new Fault('GUARD_REJECTED','No unobstructed wheel position in the required scroll area.',c);
          // A wheel lands on whatever the top page shows at that point. Every
          // frame outside the mover must show the answer frame there, or the
          // wheel goes to a header or overlay and nothing moves.
          if(route.slice(0,route.indexOf(blocked)).some(step=>!step.measurement.hit))throw new Fault('GUARD_REJECTED','An outer layer covers the scroll area that must move; no wheel was sent.',{container:c.id,frame_id:blocked.frame.frame_id});
          const v=await this.b.viewport(this.tabId),point={x:c.viewport.x+c.wheel_point.x-c.local.x,y:c.viewport.y+c.wheel_point.y-c.local.y};
          if(point.x<0||point.y<0||point.x>=v.width||point.y>=v.height)throw new Fault('TARGET_MISSING','Required scroll area is outside the browser viewport.');
          const dx=Math.max(-600,Math.min(600,c.delta.x)),dy=Math.max(-600,Math.min(600,c.delta.y));
          await this.guard();await AssignmentVisual.wheel(this.tabId,point,dx,dy,()=>this.cancelled||this.b.stopped());
          let after,moved=false;const until=Date.now()+800;
          // Check scroll offsets without running activation hit-tests mid-scroll.
          do{await sleep(60);after=await this.inspect(blocked.frame,blocked.target,'measure_target',blocked.check.point?{point:blocked.check.point}:{});
            const next=after.scroll?.containers.find(n=>n.id===c.id);moved=!!next&&(Math.abs(next.top-c.top)>.5||Math.abs(next.left-c.left)>.5);if(moved)break;
          }while(Date.now()<until);
          await this.event('EXECUTE',c.scroll_adapter==='page_wheel'?'Scrolled page to reveal answer target':'Scrolled container to reveal answer target',{
            target,frame_id:blocked.frame.frame_id,slot_key:context.slot_key,task_id:context.task_id,action_executed:true,
            scroll_details:{reason:'The rendered target is outside the visible scroll area.',target_label:r.target_info?.label,container:c.id,adapter:c.scroll_adapter,
              before:{top:c.top,left:c.left},after:after.scroll?.containers.find(n=>n.id===c.id),coordinates:point,delta:{x:dx,y:dy},moved}});
          if(!moved)throw new Fault('INPUT_NO_EFFECT','Required scroll position did not change; no target was clicked.');
          continue;
        }
        // An overlay is not evidence to scroll or to switch widget type.
        if(route.slice(0,-1).some(step=>!step.measurement.hit))throw new Fault('GUARD_REJECTED','An overlay blocks the answer frame.',route.find(step=>!step.measurement.hit).measurement.hit_info);
        const ready=check.activation_only?await this.inspect(frame,target,'measure_target',check):r;
        if(!ready.hit)throw new Fault('GUARD_REJECTED','An overlay blocks the exact target.',{target_info:ready.target_info,hit_info:ready.hit_info,click_point:ready.click_point});
        if(!ready.actionable)throw new Fault('GUARD_REJECTED','Target is disabled.');
        return ready;
      }
      throw new Fault('TARGET_MISSING','Could not reveal the target within 12 scroll actions.');
    }
    answerClick(task,slot,purpose,reason,extra={}){
      return {purpose,executor_reason:reason,task_id:task.task_id,slot_key:task.slot_key,slot_label:slot.label,
        operation:task.operation,desired:task.desired,slot_value_before:slot.current,
        plan_explanation:this.current?.taskExplanations?.[task.task_id]??this.current?.plan?.reason??null,...extra};
    }
    async click(frame,target,context={}){
      const started=Date.now();
      const r=await this.measure(frame,target,context),point=r.click_point?{x:r.viewport.x+r.click_point.x-r.local.x,y:r.viewport.y+r.click_point.y-r.local.y}:{x:r.viewport.x+r.viewport.w/2,y:r.viewport.y+r.viewport.h/2};
      await this.guard();const measured=Date.now();await AssignmentVisual.click(this.tabId,point,{count:context.click_count===2?2:1},()=>this.cancelled||this.b.stopped());this.steps++;
      // Every click records how long the page took to accept the browser input (input_ms) apart from our own DOM
      // measurement (dom_ms). A slow input channel is reported once per run, loudly: it is never silent again.
      const timing={dom_ms:measured-started,input_ms:Date.now()-measured};
      const details=JSON.parse(JSON.stringify({purpose:'unspecified',executor_reason:'Caller supplied no click purpose.',...context,
        resolved_target:{ref:target,...r.target_info},target_value_before:r.value,target_checked_before:r.checked,
        hit_test:{passed:r.hit,element:r.hit_info},coordinates:{...point,units:'CSS viewport pixels'},target_bounds:r.viewport,timing,
        verification:'Not yet verified; this record confirms browser input only.'}));
      await this.event('EXECUTE','Browser click executed',{target,frame_id:frame.frame_id,document_id:frame.document_id,observation_id:frame.observation_id,
        task_id:context.task_id,slot_key:context.slot_key,action_executed:true,click_details:details});
      if(timing.input_ms>LIMITS.slowInput&&!this.ledger.slow_input_reported){this.ledger.slow_input_reported=true;
        await this.event('EXECUTE',`Browser input is slow: the page took ${(timing.input_ms/1000).toFixed(1)} s to accept this click (DOM measurement ${timing.dom_ms} ms). Each click's timing is recorded in its details; waits for the page start after the click, so slow input makes the run slower, not blind.`,{slow_input:true,...timing,slot_key:context.slot_key,purpose:details.purpose});}
      return r;
    }
    async key(key){await this.guard();return AssignmentVisual.key(this.tabId,key,()=>this.cancelled||this.b.stopped())}
    async modelCall(phase,body){const start=Date.now();try{return await this.b.request(phase,body,this.abort.signal)}finally{this.current?.recovery?.exclude(Date.now()-start)}}
    // Visual readback for choice groups with no DOM selected-state (Quizlet's cards, any styled tile): the clicked
    // member's own pixels before vs after, with the pointer parked off the group so hover styling cannot pass for a
    // selection, plus the page's own counter when it shows one. What was confirmed is remembered in
    // this.current.visualSelections and served back through slot(); nothing else reads these groups' state.
    async park(frame,groupTarget){
      const v=await this.b.viewport(this.tabId);let box=null;try{box=(await this.inspect(frame,groupTarget)).viewport}catch{box=null}
      const pt=box&&box.y>40?{x:Math.min(v.width-4,Math.max(4,box.x+box.w/2)),y:Math.max(4,box.y-24)}:box&&box.y+box.h<v.height-40?{x:Math.min(v.width-4,Math.max(4,box.x+box.w/2)),y:box.y+box.h+24}:{x:4,y:4};
      await AssignmentVisual.move(this.tabId,pt,()=>this.cancelled||this.b.stopped());await sleep(120);return pt;
    }
    async cropPixels(box){
      // A clipped capture, in CSS pixels, of exactly this box. A full-surface screenshot cannot be cropped by the
      // layout-metrics ratio: under automation the surface is smaller than the layout viewport (infobar, scrollbar)
      // and the ratio lands the crop on the wrong pixels.
      const v=await this.b.viewport(this.tabId);
      if(box.x<0||box.y<0||box.x+box.w>v.width||box.y+box.h>v.height||box.w<4||box.h<4)throw new Fault('GUARD_REJECTED','The choice was not fully visible for a screen readback.');
      await AssignmentVisual.attach(this.tabId);
      const shot=await chrome.debugger.sendCommand({tabId:this.tabId},'Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false,clip:{x:box.x,y:box.y,width:box.w,height:box.h,scale:1}});
      const bitmap=await createImageBitmap(await (await fetch('data:image/png;base64,'+shot.data)).blob());
      const canvas=new OffscreenCanvas(bitmap.width,bitmap.height),ctx=canvas.getContext('2d');ctx.drawImage(bitmap,0,0);bitmap.close();
      return ctx.getImageData(0,0,canvas.width,canvas.height).data;
    }
    changedFraction(a,b){if(a.length!==b.length)return 1;let changed=0;const n=a.length/4;for(let i=0;i<a.length;i+=4){if(Math.abs(a[i]-b[i])>24||Math.abs(a[i+1]-b[i+1])>24||Math.abs(a[i+2]-b[i+2])>24)changed++}return changed/n}
    async visualToggle(task,s,c,want){
      const key=task.slot_key,memory=this.current.visualSelections||={},dead=this.current.visualDead||={};
      // A card that showed no change when clicked is not clicked again: on a toggle a second click could undo an
      // invisible selection, and there is no witness either way. One honest click, then the question stops.
      if((dead[key]||[]).includes(c.label))throw new Fault('GUARD_REJECTED',`"${c.label}" showed no visible change when it was clicked; it will not be clicked again.`,{slot_key:key,matched_option:c.label});
      const before=await this.measure(s.frame,c.target,{purpose:want?'check_choice':'uncheck_choice'}),box=before.viewport;
      await this.park(s.frame,s.target);const pixelsBefore=await this.cropPixels(box);const counterBefore=s.interaction?.evidence?.counter??null;
      await this.click(s.frame,c.target,this.answerClick(task,s,want?'check_choice':'uncheck_choice',want?'This choice is in the planned answer set and is not yet confirmed selected.':'This choice is outside the planned answer set and was confirmed selected.',{matched_option:c.label,checked_before:c.checked,checked_wanted:want,readback:'visual_change'}));
      await this.park(s.frame,s.target);const pixelsAfter=await this.cropPixels(box),changed=this.changedFraction(pixelsBefore,pixelsAfter);
      const obs=await this.observe(),fresh=this.slot(obs,key),counterAfter=fresh.interaction?.evidence?.counter??null;
      const counterOk=counterBefore==null||counterAfter==null||counterAfter===counterBefore+(want?-1:1);
      const detail={slot_key:key,matched_option:c.label,pixels_changed:Math.round(changed*1000)/10+'%',counter:counterBefore==null?'none':counterBefore+' -> '+counterAfter,checked_wanted:want};
      if(changed<0.01||!counterOk){dead[key]=[...(dead[key]||[]),c.label];await this.persist();await this.event('VERIFY','Screen readback did not confirm the click',{...detail,entry_verified:false});
        throw new Fault('INPUT_NO_EFFECT',changed<0.01?'The clicked choice did not visibly change.':'The page counter did not move by one after the click.',detail);}
      memory[key]=want?[...new Set([...(memory[key]||[]),c.label])]:(memory[key]||[]).filter(l=>l!==c.label);await this.persist();
      await this.event('VERIFY','Screen readback confirmed the click',{...detail,entry_verified:true,readback:'visual_change (pixel change + counter)'});
      // The page graded on this click (feedback appeared): the attempt is spent. Nothing more is clicked on this group
      // and no whole-page screenshot goes to the model, so a revealed answer never reaches it.
      if(obs.feedback||obs.slots.some(x=>x.result_feedback)||obs.grade_state!=='unknown'){this.current.graded||={};this.current.graded[key]=true;
        const wanted=task.operation==='choose_one'?[task.desired.label]:task.desired.labels,missing=wanted.filter(l=>!memory[key].includes(l));
        if(missing.length)throw new Fault('GUARD_REJECTED',`The page graded before every planned choice was entered; ${missing.length} choice(s) were not clicked and nothing more will be.`,{missing});}
    }
    modeAssertable(s){const e=s?.interaction?.evidence;return s?.kind==='unresolved'&&s.interaction?.adapter==='candidate_choices'&&String(e?.reason||'').startsWith('Single or multiple selection')&&!!(e?.state_attribute||e?.verification==='result_icon')}
    async noteAssertion(s,result){if(!result?.asserted_mode)return;const word=result.asserted_mode==='choice'?'pick one':'pick many';
      await this.event('INSPECT',result.accepted?`Model read this group as ${word}; accepted because the page text says neither`:`Model read this group as ${word}; not accepted`,{slot_key:s.slot_key,adapter:'candidate_choices',asserted_mode:result.asserted_mode,accepted:!!result.accepted,actual:result.evidence,action_executed:false})}
    matches(task,s){const d=task.desired;
      if(!TASK_OPERATION[s.kind]||TASK_OPERATION[s.kind]!==task.operation)return false;
      switch(task.operation){
        case 'choose_one':return JSON.stringify((s.current||[]).map(norm))===JSON.stringify([norm(d.label)]);
        case 'set_choice_set':return JSON.stringify((s.current||[]).map(norm).sort())===JSON.stringify(d.labels.map(norm).sort());
        case 'enter_value':return sameValue(s.current,d.value);
        case 'set_selection':return norm(s.current)===norm(d.label);
        case 'set_order':return JSON.stringify(s.current.map(norm))===JSON.stringify(d.sequence.map(norm));
        case 'place_points':if(s.geometry?.visual&&!s.geometry.labeled)return d.points.length===s.geometry.points.length&&d.points.every(p=>s.geometry.points.some(a=>Math.abs(a.x-p.x)<=s.geometry.tolerance&&Math.abs(a.y-p.y)<=s.geometry.tolerance));return !!s.geometry?.calibrated&&d.points.length===s.geometry.points.length&&d.points.every(p=>{const a=s.geometry.points.find(a=>a.id===p.id);return a&&Math.abs(a.x-p.x)<=s.geometry.tolerance&&Math.abs(a.y-p.y)<=s.geometry.tolerance});
        default:throw new Fault('GUARD_REJECTED','Unknown task operation.');
      }
    }
    async waitTask(task,budget=LIMITS.ui){const until=Date.now()+budget;let obs,s;do{await this.guard();obs=await this.observe();s=this.slot(obs,task.slot_key);if(this.matches(task,s))return {obs,s};await sleep(100)}while(Date.now()<until);throw new Fault('VALUE_MISMATCH','Expected answer did not appear in its logical slot.',s.current)}
    async execute(task,force=false){
      // `force` re-performs the input even when the DOM already matches -- used
      // by the second witness so a screenshot mismatch triggers a REAL re-entry
      // (clear+retype / re-select), never a silent skip that leaves the same
      // unchanged state to be re-checked.
      const partId=this.current?.slot_parts?.[task.slot_key];let obs=partId?await this.showPart(null,partId):await this.observe(),s=this.slot(obs,task.slot_key);
      if(this.modeAssertable(s)){
        // The plan's operation is the model's reading of pick-one vs pick-many. The page decides whether it stands
        // (its own text silent, a selected-state readback present); only then does the group become a typed slot.
        const mode=task.operation==='choose_one'?'choice':'choice_set';
        const verdict=await this.inspect(s.frame,s.target,'classify_choices',{selection_mode:mode});await this.noteAssertion(s,verdict);
        if(!verdict.accepted)throw new Fault('GUARD_REJECTED',`The page does not support reading this group as ${mode==='choice'?'pick one':'pick many'}; nothing was clicked.`,verdict.evidence);
        obs=await this.observe();s=this.slot(obs,task.slot_key);
      }
      if(!TASK_OPERATION[s.kind]||TASK_OPERATION[s.kind]!==task.operation)throw new Fault('GUARD_REJECTED','Control type changed; the planned operation no longer applies.');
      if(!force&&this.matches(task,s))return {obs,s,skipped:true};
      if(force&&s.interaction?.evidence?.verification==='result_icon'&&s.current?.length)throw new Fault('GUARD_REJECTED','A graded result-card answer cannot be replayed or changed automatically.');
      if(s.disabled)throw new Fault('GUARD_REJECTED','Answer field is disabled.');
      const d=task.desired;
      if(task.operation==='choose_one'||task.operation==='set_choice_set'){
        const wanted=task.operation==='choose_one'?[d.label]:d.labels;
        if(wanted.some(label=>s.choices.filter(c=>norm(c.label)===norm(label)).length!==1))throw new Fault('TARGET_AMBIGUOUS','Choice label is missing or repeated within its group.');
        // Checkboxes reconcile every member, including unintended checked choices.
        for(const label of s.choices.map(c=>c.label)){obs=await this.observe();s=this.slot(obs,task.slot_key);const c=s.choices.find(c=>c.label===label),want=wanted.some(w=>norm(w)===norm(label));
          if(c.checked===want||task.operation==='choose_one'&&!want)continue;
          if(s.interaction?.evidence?.verification==='result_icon')await this.inspect(s.frame,c.target,'begin_choice',{expected_choice_owner:s.local_slot,expected_label:c.label});
          if(c.disabled)throw new Fault('GUARD_REJECTED','Desired choice is disabled.');
          if(s.interaction?.evidence?.verification==='visual_change'){await this.visualToggle(task,s,c,want);continue}
          await this.click(s.frame,c.target,this.answerClick(task,s,want?'check_choice':'uncheck_choice',want?'This choice is in the planned answer set and is currently unchecked.':'This choice is outside the planned answer set and is currently checked.',{matched_option:c.label,checked_before:c.checked,checked_wanted:want}));
          if(s.interaction?.evidence?.verification==='result_icon')return this.waitTask(task);
          await sleep(70);}
      }else if(task.operation==='enter_value'){
        if(s.interaction?.adapter==='sheet_text'&&!s.interaction.editor_target){
          await this.click(s.frame,s.target,this.answerClick(task,s,'activate_cell','Open the previously identified spreadsheet text editor.',{click_count:2}));
          const until=Date.now()+LIMITS.ui;
          do{obs=await this.observe();s=this.slot(obs,task.slot_key);if(s.kind!=='value')throw new Fault('GUARD_REJECTED','Spreadsheet field changed interaction type.');if(s.interaction.editor_target)break;await sleep(100)}while(Date.now()<until);
          if(!s.interaction.editor_target)throw new Fault('TARGET_MISSING','Spreadsheet editor did not appear for this cell.');
        }
        const target=s.interaction?.editor_target||s.target,ownership=target!==s.target?{expected_value_owner:s.local_slot}:{};
        const cellClass=String(s.interaction?.adapter==='sheet_text'?(await this.inspect(s.frame,s.target)).target_info?.class_name||'':'');
        await this.click(s.frame,target,this.answerClick(task,s,'focus_text','Focus the planned text editor before replacing its value.',target!==s.target?{value_owner:s.local_slot}:{}));
        let editor=await this.inspect(s.frame,target,'measure_target',ownership);if(!editor.focused)throw new Fault('INPUT_NO_EFFECT','Text field did not acquire focus.');
        // A number field gets digits only; the page applies its own $ and commas and the readback is compared numerically.
        const numericField=editor.target_info?.type==='number'||/^(numeric|decimal)$/.test(editor.target_info?.inputmode||'')||/\bisN\b/.test(cellClass);
        const typed=numericField?plainDigits(d.value):d.value;
        // Clear what is there. Select-all first; if the widget swallowed it (the live jSheet did: the retry appended
        // "91300" to "91300"), delete the measured text key by key so the field is empty before anything is typed.
        await this.key('Control+a');await this.guard();editor=await this.inspect(s.frame,target,'measure_target',ownership);if(!editor.focused)throw new Fault('TARGET_STALE','Focus changed before typing.');
        const held=String(editor.value??''),selected=editor.selection&&editor.selection.start===0&&editor.selection.end>=held.length;
        if(held&&!selected){
          if(held.length>200)throw new Fault('INPUT_NO_EFFECT','Existing text is too long to clear safely.',held.slice(0,40));
          await this.key('End');for(let i=0;i<held.length;i++)await this.key('Backspace');
          editor=await this.inspect(s.frame,target,'measure_target',ownership);
          if(String(editor.value??''))throw new Fault('INPUT_NO_EFFECT','Existing text could not be cleared before typing.',{held,remaining:String(editor.value)});
          await this.event('EXECUTE','Cleared existing text key by key (select-all did not take)',{task_id:task.task_id,slot_key:task.slot_key,cleared:held});
        }
        if(typed)await AssignmentVisual.insertText(this.tabId,typed,()=>this.cancelled||this.b.stopped());else if(held&&selected)await this.key('Backspace');
        // Never commit blind: the editor must hold the planned value before it is committed. Otherwise cancel the edit
        // (Escape, which the sheet discards) and fail precisely, so a retry starts from the untouched cell.
        const before=await this.inspect(s.frame,target,'measure_target',ownership);if(!before.focused)throw new Fault('TARGET_STALE','Focus moved before commit.');
        if(!sameValue(before.value,typed)){await this.key('Escape');throw new Fault('INPUT_NO_EFFECT','Editor did not hold the planned value; edit cancelled, nothing committed.',{typed,editor:String(before.value??'')})}
        // Blur through Tab, never Enter (which can submit a form).
        await this.key('Tab');
      }else if(task.operation==='set_selection'){
        if(s.native){
          await this.click(s.frame,s.target,this.answerClick(task,s,'focus_native_select','Focus the native dropdown; keyboard input will choose the planned label.'));await this.key('Escape');let m=await this.inspect(s.frame,s.target);
          const targets=m.options.filter(o=>norm(o.label)===norm(d.label));if(targets.length!==1)throw new Fault('TARGET_AMBIGUOUS','Native option label is not unique.');if(targets[0].disabled)throw new Fault('GUARD_REJECTED','Desired native option is disabled.');
          const enabled=m.options.filter(o=>!o.disabled);let seen=new Set();
          for(let i=0;i<=enabled.length;i++){m=await this.inspect(s.frame,s.target);if(norm(m.value)===norm(d.label))break;if(!m.focused)throw new Fault('TARGET_STALE','Dropdown lost focus.');
            if(seen.has(m.selectedIndex))throw new Fault('INPUT_NO_EFFECT','Native selection did not move.');seen.add(m.selectedIndex);
            const index=m.options.findIndex(o=>norm(o.label)===norm(d.label));await this.key(index>m.selectedIndex?'ArrowDown':'ArrowUp');await sleep(70)}await this.key('Tab');
        }else{
          // Cell, activated editor and detached option keep the same logical slot.
          let menu=s.frame.menus.filter(m=>m.owner===s.local_slot);
          if(s.opening_control?.status==='ambiguous')throw new Fault('TARGET_AMBIGUOUS','Multiple expand buttons are associated with this dropdown.',s.opening_control);
          if(!menu.length){
            // Opening ladder. Pages expose a dropdown's opener in different ways, so the standard ways are tried in
            // order and the SAME proof is demanded after each: a visible menu that belongs to this cell (ARIA link or
            // the one expanded cell). No rung chooses an option. The cell's box is the boundary for every click.
            const tried=[];const settle=async()=>{const until=Date.now()+1500;do{obs=await this.observe();s=this.slot(obs,task.slot_key);menu=s.frame.menus.filter(m=>m.owner===s.local_slot);if(menu.length)return true;await sleep(100)}while(Date.now()<until);return false};
            const openWith=async(target,purpose,reason,extra={})=>{tried.push(purpose);await this.click(s.frame,target,this.answerClick(task,s,purpose,reason,{trigger_candidates:s.representations||[],opening_control:s.opening_control,...extra}));return settle()};
            // 1. explicit trigger already known, else activate the cell (which may expose one)
            let opened=s.representations?.[0]&&!s.opening_control?.geometry_only?await openWith(s.representations[0],'open_menu','Click the detected dropdown trigger to enter the planned selection.'):await openWith(s.target,'activate_cell','Activate the answer cell because no dropdown trigger is currently exposed.');
            if(!opened&&s.opening_control?.status==='ambiguous')throw new Fault('TARGET_AMBIGUOUS','Multiple expand buttons are associated with this dropdown.',s.opening_control);
            if(!opened&&s.representations?.[0]&&!s.opening_control?.geometry_only)opened=await openWith(s.representations[0],'open_menu','The activated cell exposed a trigger; open its menu for the planned answer.');
            // 2. geometry trigger: a button whose center is inside this cell's box and no other cell's
            if(!opened&&s.representations?.[0]&&s.opening_control?.geometry_only)opened=await openWith(s.representations[0],'open_menu_by_geometry','No labelled trigger; this button sits inside the activated cell and inside no other cell.',{evidence:'overlay_geometry'});
            // 3. the combobox itself
            if(!opened&&s.combobox)opened=await openWith(s.combobox,'open_combobox','Click the cell\'s combobox; many widgets open on the field itself.');
            // 4. keyboard, the ARIA combobox pattern
            if(!opened){const focus=await this.inspect(s.frame,s.combobox||s.target);if(focus.focused){for(const k of ['ArrowDown','Alt+ArrowDown']){tried.push('key:'+k);await this.key(k);if(await settle()){opened=true;break}}}}
            if(!opened)throw new Fault('WRONG_MENU_OWNER','No menu owned by this answer field appeared after: '+tried.join(', ')+'.',{tried,opening_control:s.opening_control});
          }
          const options=menu.filter(m=>norm(m.label)===norm(d.label));if(!options.length)throw new Fault('OPTION_MISSING','Desired option absent.',menu.map(o=>o.label));if(options.length!==1)throw new Fault('TARGET_AMBIGUOUS','Two menu options share that label.');if(options[0].disabled)throw new Fault('GUARD_REJECTED','Desired option is disabled.');
          await this.click(s.frame,options[0].target,this.answerClick(task,s,'choose_option','Exactly one enabled option in this slot\'s menu matches the planned label.',{
            matched_option:options[0].label,menu_owner:options[0].owner,match_rule:'Exact label equality after whitespace and [active] normalization',
            available_options:menu.slice(0,100).map(m=>({label:m.label,ref:m.target,owner:m.owner,disabled:m.disabled})),option_count:menu.length,options_truncated:menu.length>100}));
        }
      }else if(task.operation==='set_order'){
        for(let n=0;n<d.sequence.length;n++){
          obs=await this.observe();s=this.slot(obs,task.slot_key);if(this.matches(task,s))break;
          if(new Set(s.current).size!==s.current.length||JSON.stringify([...s.current].sort())!==JSON.stringify([...d.sequence].sort()))throw new Fault('TARGET_AMBIGUOUS','Ordering items changed or have duplicate labels.');
          const i=s.current.findIndex((v,i)=>v!==d.sequence[i]),source=s.items.find(c=>c.label===d.sequence[i]),target=s.items[i];
          await this.measure(s.frame,target.target);const a=await this.measure(s.frame,source.target),b=await this.measure(s.frame,target.target);
          await this.guard();await AssignmentVisual.input(this.tabId,{x:a.viewport.x+a.viewport.w/2,y:a.viewport.y+a.viewport.h/2},{x:b.viewport.x+b.viewport.w/2,y:b.viewport.y+3},()=>this.cancelled||this.b.stopped());await sleep(150);
        }
      }else if(task.operation==='place_points'){
        if(s.geometry?.visual||!s.geometry?.calibrated)return this.executeVisualPoints(task,obs);
        for(const p of d.points){obs=await this.observe();s=this.slot(obs,task.slot_key);await this.measure(s.frame,s.target);const g=(await this.inspect(s.frame,s.target,'inspect_svg_geometry')).geometry;
          if(!g?.calibrated)throw new Fault('GEOMETRY_UNCALIBRATED',g?.reason||'Cannot establish graph coordinates.');
          const source=g.points.find(x=>x.id===p.id);if(!source||p.x<g.x.min||p.x>g.x.max||p.y<g.y.min||p.y>g.y.max)throw new Fault('GEOMETRY_UNCALIBRATED','Point ID or mathematical destination is outside the calibrated graph.');
          if(Math.abs(source.x-p.x)<=g.tolerance&&Math.abs(source.y-p.y)<=g.tolerance)continue;
          const x=g.x.origin+p.x*g.x.scale,y=g.y.origin+p.y*g.y.scale,m=g.matrix,to={x:m.a*x+m.c*y+m.e,y:m.b*x+m.d*y+m.f};
          await this.guard();await AssignmentVisual.input(this.tabId,source.viewport,to,()=>this.cancelled||this.b.stopped());
          const until=Date.now()+LIMITS.ui;let placed=false;do{obs=await this.observe();s=this.slot(obs,task.slot_key);const a=s.geometry?.points?.find(x=>x.id===p.id);if(a&&Math.abs(a.x-p.x)<=g.tolerance&&Math.abs(a.y-p.y)<=g.tolerance){placed=true;break}await sleep(100)}while(Date.now()<until);
          if(!placed)throw new Fault('VALUE_MISMATCH','First graph drag did not confirm the coordinate transform.');
        }
      }else throw new Fault('GUARD_REJECTED','Unsupported typed task.');
      await this.event('VERIFY','Verifying the entered answer',{slot_key:task.slot_key,task_id:task.task_id,action_executed:true});
      return this.waitTask(task);
    }
    async readVisual(obs,slot){
      await this.guard();await this.event('INSPECT','Reading visible graph geometry');await this.measure(slot.frame,slot.target);obs=await this.observe();slot=this.slot(obs,slot.slot_key);
      const measured=await this.inspect(slot.frame,slot.target),box=measured.viewport,shot=await AssignmentVisual.screenshot(this.tabId),generation=this.generation;
      if(!box||box.x<0||box.y<0||box.x+box.w>shot.viewport.width||box.y+box.h>shot.viewport.height)throw new Fault('GEOMETRY_UNCALIBRATED','The entire graph must fit in the viewport for calibration.');
      const beforeHash=await regionHash(shot,box);const observation=this.publicObservation(obs);observation.screenshot=shot.dataUrl;
      // Geometry reader receives current pixels and a rectangle, never the desired answer.
      const body={run_id:this.id,request_id:crypto.randomUUID(),spend_limit:this.config.spend_limit,model:this.config.model,observation,slot_key:slot.slot_key,box,viewport:shot.viewport};
      this.ledger.pending_request=body.request_id;await this.persist();
      await this.logObservation('INSPECT',body);
      const data=await this.modelCall('visual',body);
      if(Number.isFinite(data.cost)){this.ledger.cost+=data.cost;this.ledger.pending_request=null}await this.persist();await this.guard();
      if(generation!==this.generation)throw new Fault('CANCELLED','Discarded late visual measurement.');
      const fresh=await this.observe(),current=this.slot(fresh,slot.slot_key),after=await this.inspect(current.frame,current.target);
      if(fresh.document_id!==obs.document_id||JSON.stringify(after.viewport)!==JSON.stringify(box))throw new Fault('TARGET_STALE','Graph moved during visual inspection.');
      const newShot=await AssignmentVisual.screenshot(this.tabId);if(await regionHash(newShot,box)!==beforeHash)throw new Fault('TARGET_STALE','Graph content changed during visual inspection.');
      await this.event('INSPECT',data.response?'Received graph measurement response':'Graph measurement response rejected',{model_calls:1,cost:data.cost,input_tokens:data.input_tokens,output_tokens:data.output_tokens,reasoning_tokens:data.reasoning_tokens,slot_key:slot.slot_key,request_id:body.request_id,model:data.model||body.model||'(backend default)',requested_model:body.model||'',provider:data.provider||undefined,finish_reason:data.finish_reason,raw:data.raw_reply,detail:data.response?.reason||data.detail||'',response_kind:data.response?.kind});
      if(!data.response)throw new Fault('GEOMETRY_UNCALIBRATED',data.detail||'No visual calibration returned.');
      const geometry=visualGeometry(data.response,box);geometry.pixelHash=beforeHash;geometry.box=box;
      this.current.visual||={};this.current.visual[slot.slot_key]=geometry;this.current.recovery.progress();await this.persist();return geometry;
    }
    async executeVisualPoints(task,obs){
      let s=this.slot(obs,task.slot_key),g=await this.readVisual(obs,s);const d=task.desired;
      if(g.points.length!==d.points.length)throw new Fault('GEOMETRY_UNCALIBRATED','Visual point count differs from the planned graph.');
      for(const desired of d.points){
        if(g.points.some(a=>(!g.labeled||a.id===desired.id)&&Math.abs(a.x-desired.x)<=g.tolerance&&Math.abs(a.y-desired.y)<=g.tolerance))continue;
        let placed=false;
        for(let attempt=0;attempt<3;attempt++){
          this.current.visualCorrections||={};if(attempt){const n=this.current.visualCorrections[task.slot_key]||0;if(n>=2)throw new Fault('BUDGET_EXHAUSTED','Visual correction budget exhausted.');this.current.visualCorrections[task.slot_key]=n+1;await this.persist()}
          if(desired.x<g.x.min||desired.x>g.x.max||desired.y<g.y.min||desired.y>g.y.max)throw new Fault('GEOMETRY_UNCALIBRATED','Desired point lies outside observed axis bounds.');
          const source=g.labeled?g.points.find(a=>a.id===desired.id):g.points.find(a=>!d.points.some(p=>Math.abs(a.x-p.x)<=g.tolerance&&Math.abs(a.y-p.y)<=g.tolerance));if(!source)throw new Fault('GEOMETRY_UNCALIBRATED','Cannot distinguish a point that still needs moving.');
          const currentShot=await AssignmentVisual.screenshot(this.tabId);if(await regionHash(currentShot,g.box)!==g.pixelHash)throw new Fault('TARGET_STALE','Graph changed since the calibrated observation.');
          const x=g.x.origin+desired.x*g.x.scale,y=g.y.origin+desired.y*g.y.scale,m=g.matrix;
          await this.guard();await AssignmentVisual.input(this.tabId,source.viewport,{x:m.a*x+m.e,y:m.d*y+m.f},()=>this.cancelled||this.b.stopped());
          await sleep(120);obs=await this.observe();s=this.slot(obs,task.slot_key);g=await this.readVisual(obs,s);
          placed=g.points.some(a=>(!g.labeled||a.id===desired.id)&&Math.abs(a.x-desired.x)<=g.tolerance&&Math.abs(a.y-desired.y)<=g.tolerance);if(placed)break;
        }
        if(!placed)throw new Fault('VALUE_MISMATCH','Visual drag corrections did not place the point.');
      }
      obs=await this.observe();s=this.slot(obs,task.slot_key);if(!this.matches(task,s))throw new Fault('VALUE_MISMATCH','Complete graph did not match all planned points.');return {obs,s};
    }
    knownOptions(obs,s){
      if(s.options?.length)return s.options;
      const live=s.kind==='selection'?s.frame?.menus.filter(m=>m.owner===s.local_slot):[];
      if(live?.length)return live.filter(o=>!o.disabled).map(o=>o.label);
      const saved=this.current?.optionEvidence?.[s.slot_key];
      return saved?.document===obs.document_id&&saved.label===s.label?saved.options.filter(o=>!o.disabled).map(o=>o.label):[];
    }
    async selectionOptions(key,withControls=false){
      const obs=await this.observe(),s=this.slot(obs,key);
      if(s.kind!=='selection')throw new Fault('GUARD_REJECTED','Option discovery requires a selection slot.');
      if(s.disabled)throw new Fault('GUARD_REJECTED','Dropdown is disabled.');
      const result=await this.inspect(s.frame,s.target,'inspect_options'),options=result.options||[];
      this.current.optionEvidence||={};
      const previous=this.current.optionEvidence[key];
      // A destroyed shared editor does not erase choices already observed for
      // this exact slot/document. Do not borrow another slot's cached choices.
      if(options.length||previous?.document!==obs.document_id||previous?.label!==s.label)this.current.optionEvidence[key]={document:obs.document_id,label:s.label,options};
      if(options.length&&JSON.stringify(previous)!==JSON.stringify(this.current.optionEvidence[key]))this.current.recovery.progress();
      await this.event('INSPECT',options.length?'Read dropdown choices without clicking':'No dropdown choices found by read-only inspection',{
         slot_key:key,actual:options,opening_control:result.opening_control,menu_scroll:result.menu_scroll,adapter:'read_only_selection_options',inspection_source:result.source,action_executed:false});
      return withControls?{options,opening_control:result.opening_control,...(result.menu_scroll?{menu_scroll:result.menu_scroll}:{})}:options;
    }
    async discoverSelectionOptions(obs){
      const missing=obs.slots.filter(s=>s.kind==='selection'&&!s.disabled&&!this.knownOptions(obs,s).length);
      if(!missing.length)return obs;
      await this.event('INSPECT',`Inspecting existing DOM choices for ${missing.length} dropdowns without clicking`);
      for(const s of missing){await this.guard();const options=await this.selectionOptions(s.slot_key);if(!options.length)await this.revealSelectionOptions(s.slot_key);}
      const fresh=await this.observe();this.same(fresh);
      for(const before of obs.slots){const after=this.slot(fresh,before.slot_key);if(JSON.stringify(after.current)!==JSON.stringify(before.current))throw new Fault('VALUE_MISMATCH','Discovery changed an existing answer.',{slot_key:before.slot_key,before:before.current,after:after.current});}
      return fresh;
    }
    async classifyCandidateChoices(obs){
      for(const before of obs.slots.filter(s=>s.kind==='unresolved'&&s.interaction?.adapter==='candidate_choices')){
        const fresh=await this.observe(),s=this.slot(fresh,before.slot_key);
        if(s.kind==='unresolved')await this.inspect(s.frame,s.target,'classify_choices');
      }
      const fresh=await this.observe();this.same(fresh);return fresh;
    }
    async resolveInteractions(obs){
      const unknown=obs.slots.filter(s=>s.kind==='unresolved'&&!s.disabled);
      this.current.interactionActions||={};
      for(const initial of unknown){
        let fresh=await this.observe(),s=this.slot(fresh,initial.slot_key);
        if(s.kind!=='unresolved')continue;
        if(s.interaction?.adapter==='candidate_choices'){
          const result=await this.inspect(s.frame,s.target,'classify_choices');
          await this.event('INSPECT',result.promoted?'Established answer group and selected-state readback':'Answer group needs more interaction evidence',{slot_key:s.slot_key,adapter:'candidate_choices',actual:result.evidence,action_executed:false});
          continue; // No exploratory answer clicks. Unknown is not a spreadsheet cell.
        }
        const actions=this.current.interactionActions[s.slot_key]||={};
        await this.event('INSPECT','Identifying answer interaction',{slot_key:s.slot_key,actual:s.interaction});
        if(fresh.frames.some(f=>f.menus.length)){
          await this.key('Escape');fresh=await this.observe();s=this.slot(fresh,s.slot_key);
          if(fresh.frames.some(f=>f.menus.length))throw new Fault('INPUT_NO_EFFECT','Open menu must close before identifying another answer cell.');
        }
        // The bounded look at the page (LIMITS.ui) starts after each click RETURNS. The execution loops already wait
        // that way; this one counted our own input time against the window, so a page slow to accept a click left no
        // time to see what the click revealed (M3-9 5:11 PM: 5 s clicks, no double-click, nothing identified).
        let until=Date.now()+LIMITS.ui;
        do{
          await this.guard();
          if(s.interaction?.ambiguous)throw new Fault('TARGET_AMBIGUOUS','Multiple editors could belong to this answer cell.');
          const action=!actions.activate?'activate':s.interaction?.adapter==='sheet_text'&&!actions.edit?'edit':null;
          if(action){
            actions[action]=true;await this.persist();
            await this.click(s.frame,s.target,{purpose:action==='edit'?'identify_editor':'identify_cell',slot_key:s.slot_key,slot_label:s.label,click_count:action==='edit'?2:1,
              executor_reason:action==='edit'?'The recognized spreadsheet widget requires double-click to reveal its editor.':'Activate the unresolved answer cell, then inspect the controls it exposes.'});
            until=Date.now()+LIMITS.ui;
          }
          fresh=await this.observe();s=this.slot(fresh,initial.slot_key);
          if(s.current!==initial.current)throw new Fault('VALUE_MISMATCH','Identification changed an answer unexpectedly.');
          if(s.kind!=='unresolved')break;
          await sleep(100);
        }while(Date.now()<until);
        await this.event('INSPECT',s.kind==='unresolved'?'Answer interaction remains unresolved':'Answer interaction identified',{slot_key:s.slot_key,actual:s.interaction});
        if(s.kind==='value'&&s.interaction?.adapter==='sheet_text'&&s.interaction.editor_target){
          if(!(await this.inspect(s.frame,s.interaction.editor_target,'measure_target',{expected_value_owner:s.local_slot})).focused)throw new Fault('TARGET_STALE','Identified editor lost focus.');
          await this.key('Escape');fresh=await this.observe();s=this.slot(fresh,initial.slot_key);
          if(s.current!==initial.current)throw new Fault('VALUE_MISMATCH','Closing identification changed an answer.');
          if(s.interaction.editor_target)throw new Fault('INPUT_NO_EFFECT','Identification editor did not close.');
        }
        if(s.kind!=='unresolved')this.current.recovery.progress();
      }
      return this.observe();
    }
    async revealSelectionOptions(key){
      // Durable two-action ceiling: activation and opening only, never selection.
      this.current.discoveryActions||={};
      const actions=this.current.discoveryActions[key]||={};
      let obs=await this.observe(),s=this.slot(obs,key);const before=s.current;
      if(s.native)return; // Native options are already readable without input.
      await this.event('INSPECT','Choices are not in the DOM; revealing this dropdown without choosing an answer',{slot_key:key});
      // Dismiss a known menu before targeting another cell; never click through it.
      if(obs.frames.some(f=>f.menus.length)&&!s.frame.menus.some(m=>m.owner===s.local_slot)){
        await this.key('Escape');obs=await this.observe();s=this.slot(obs,key);
        if(obs.frames.some(f=>f.menus.length)){
          // An already-open iframe menu may not own keyboard focus. Focus its
          // positively associated opener with real input, then dismiss once.
          const owners=obs.slots.filter(a=>a.frame.menus.some(m=>m.owner===a.local_slot));
          if(owners.length===1&&owners[0].opening_control?.status==='resolved'&&owners[0].representations?.length===1){
            const owner=owners[0];await this.click(owner.frame,owner.representations[0],{purpose:'discover_focus_menu',slot_key:owner.slot_key,
              executor_reason:'The open menu did not receive Escape; focus its associated trigger before dismissing it.'});
            await this.key('Escape');obs=await this.observe();s=this.slot(obs,key);
          }
        }
        if(obs.frames.some(f=>f.menus.length))throw new Fault('INPUT_NO_EFFECT','Existing dropdown did not close; discovery stopped.');
      }
      let until=Date.now()+LIMITS.ui;   // restarted after each discovery click: the wait is for the page's response, not our input
      do{
        await this.guard();obs=await this.observe();s=this.slot(obs,key);
        if(s.current!==before)throw new Fault('VALUE_MISMATCH','Dropdown discovery changed the answer; stopped.',s.current);
        const info=await this.inspect(s.frame,s.target,'inspect_options');
        if(info.options?.length){
          await this.selectionOptions(key);
          if(s.frame.menus.some(m=>m.owner===s.local_slot)){
            await this.key('Escape');const fresh=await this.observe(),slot=this.slot(fresh,key);
            if(slot.current!==before)throw new Fault('VALUE_MISMATCH','Closing discovery changed the answer.',slot.current);
            if(slot.frame.menus.some(m=>m.owner===slot.local_slot))throw new Fault('INPUT_NO_EFFECT','Discovered menu did not close.');
          }
          return;
        }
        if(s.opening_control?.status==='ambiguous')throw new Fault('TARGET_AMBIGUOUS','Discovery found multiple dropdown triggers.');
        const arrow=s.representations?.[0],action=arrow?'open':'activate';
        if(!actions[action]&&!(action==='activate'&&actions.open)){
          actions[action]=true;await this.persist();
          await this.click(s.frame,arrow||s.target,{purpose:arrow?'discover_open_menu':'discover_activate_cell',slot_key:key,slot_label:s.label,
            executor_reason:arrow?'Open the associated dropdown to read missing choices; do not select an answer.':'Activate the inactive answer cell to expose its dropdown controls.',opening_control:s.opening_control});
          until=Date.now()+LIMITS.ui;
        }
        await sleep(100);
      }while(Date.now()<until);
      await this.event('INSPECT','Dropdown choices remain unavailable after bounded discovery',{slot_key:key,failure_code:'OPTION_MISSING'});
    }
    mergeEvidence(items,obs){
      this.same(obs);const scope=obs.question_key+'|'+obs.document_id;
      const previous=this.current.evidence_scope===scope?this.current.evidence||[]:[];
      const key=e=>JSON.stringify([e.operation,e.frame_id??null,e.slot_key||'',e.inspection_key||'']);
      const evidence=new Map(previous.map(e=>[key(e),e]));
      for(const e of items)evidence.set(key(e),{...e,question_key:obs.question_key,document_id:obs.document_id});
      const merged=[...evidence.values()];
      // Never silently evict instructions to fit the request. Same-source facts replace superseded facts;
      // unrelated facts survive, and overflow is an explicit stop before another paid plan or action.
      if(merged.length>14||new TextEncoder().encode(JSON.stringify(merged)).length>32000)throw new Fault('QUESTION_INCOMPLETE','Inspection context exceeds its evidence budget; essential evidence was retained and no answer was executed.');
      this.current.evidence=merged;this.current.evidence_scope=scope;
    }
    publicObservation(obs){return {question_key:obs.question_key,document_id:obs.document_id,observation_id:obs.observation_id,question:obs.question,...(obs.tables?.length||obs.table_context_complete===false?{tables:obs.tables||[],table_context_complete:obs.table_context_complete!==false}:{}),...(obs.parts?.length?{parts:obs.parts.map(p=>({part_id:p.part_id,label:p.label,selected:!!p.selected,slots:obs.slots.filter(s=>s.part_id===p.part_id).length}))}:{}),slots:obs.slots.map(s=>{s=this.current?this.slot(obs,s.slot_key):s;return ({slot_key:s.slot_key,frame_id:s.frame_id,dom_id:s.dom_id||null,kind:s.kind,label:s.label,...(s.part_id?{part_id:s.part_id}:{}),options:this.knownOptions(obs,s),current:s.current,...(s.interaction?{interaction:{adapter:s.interaction.adapter,evidence:s.interaction.evidence}}:{}),...(s.geometry?{geometry:s.geometry}:{})})}),completeness:obs.completeness,host:obs.host,task_note:this.config.note||'',evidence:this.current?.evidence_scope===obs.question_key+'|'+obs.document_id?this.current.evidence||[]:[]}}
    async paid(obs,task=null,error=null,inspectionCorrection=false,formatCorrection=false){await this.guard();await this.event(task?'REPAIR':'PLAN',task?'Repairing the failed task':'Planning answers for this question');const generation=this.generation;const body={run_id:this.id,request_id:crypto.randomUUID(),spend_limit:this.config.spend_limit,model:this.config.model,observation:this.publicObservation(obs)};
      if(obs.slots.some(s=>s.result_feedback))throw new Fault('GUARD_REJECTED','Answer feedback is already visible; another planning screenshot could expose the revealed answer. Review this attempt manually.');
      if(inspectionCorrection)body.inspection_target_correction=true;
      if(formatCorrection)body.format_correction=true;
      const textSize=new TextEncoder().encode(JSON.stringify(body.observation)).length;
      if(textSize>100000)throw new Fault('QUESTION_INCOMPLETE','Question and retained inspection evidence exceed 100 KB; no paid request was made.');
      if(this.current?.planHints?.avoid_providers?.length)body.avoid_providers=this.current.planHints.avoid_providers;
      if(this.current?.planHints?.reasoning_mode)body.reasoning_mode=this.current.planHints.reasoning_mode;
      // See what a human sees: the planner always gets DOM + a settled screenshot
      // together, not the scraped controls alone. Redesign per Dylan -- the model
      // plans from the picture (rendered math, diagrams, layout the DOM omits),
      // and the same applies to a repair so it sees the page it is correcting.
      const shot=await AssignmentVisual.screenshot(this.tabId);body.observation.screenshot=shot.dataUrl;
      if(task)Object.assign(body,{task,failure:{code:error.code,detail:error.message,actual:error.actual},completed_slots:Object.keys(this.current.completed),history:this.current.recovery.history});
      this.ledger.pending_request=body.request_id;await this.persist();const start=Date.now();let data;
      await this.logObservation(task?'REPAIR':'PLAN',body);
      try{data=await this.modelCall(task?'repair':'plan',body)}catch(e){this.ledger.status='needs_review';throw e}
      if(Number.isFinite(data.cost)){this.ledger.cost+=data.cost;this.ledger.pending_request=null}
      await this.persist();await this.guard();if(generation!==this.generation)throw new Fault('CANCELLED','Discarded late model response.');
      const fresh=await this.observe();if(fresh.question_key!==obs.question_key||fresh.document_id!==obs.document_id)throw new Fault('TARGET_STALE','Discarded model response after question/document changed.');
      const diagnostic={model_calls:1,cost:data.cost,input_tokens:data.input_tokens,output_tokens:data.output_tokens,reasoning_tokens:data.reasoning_tokens,duration:Date.now()-start,
        request_id:body.request_id,observation_id:obs.observation_id,model:data.model||body.model||'(backend default)',requested_model:body.model||'',provider:data.provider||undefined,
        finish_reason:data.finish_reason,raw:data.raw_reply,detail:data.response?.reason||data.detail||'',response_kind:data.response?.kind,output_format:data.output_format,format_corrections:data.format_corrections};
      if(!data.response){
        await this.event(task?'REPAIR':'PLAN','Model response rejected; no plan accepted',diagnostic);
        const code=data.detail?.split(':')[0]||'FAILED';
        if(code==='SCHEMA_INVALID'&&data.format_correction?.kind==='invalid_json'&&Number.isFinite(data.cost)&&!this.ledger.pending_request&&!this.current.formatCorrections){
          this.current.formatCorrections=1;await this.persist();
          this.mergeEvidence([{operation:'format_correction',instruction:'The previous reply was invalid JSON and was not executed. Return exactly one valid JSON object for this fresh observation.'}],fresh);
          await this.event(task?'REPAIR':'PLAN','Requesting one JSON format correction; rejected output was not executed',{failure_code:code,correction_attempt:1});
          return this.paid(fresh,task,error,false,true);
        }
        if(code==='TARGET_MISSING'&&data.inspection_correction?.kind==='inspection_target'&&Number.isFinite(data.cost)&&!this.ledger.pending_request){
          if(!this.current.inspectionTargetCorrections){
            this.current.inspectionTargetCorrections=1; // durable per-question limit, including resume/replanning
            const correction={operation:'inspection_request_correction',rejected_slot_key:data.inspection_correction.rejected_slot_key,
              instruction:'The rejected inspection was NOT executed. Use an exact offered slot_key for inspect_options, or slot_key="" with inspect_question (or a script-only request) to discover missing controls.',
              offered_slots:fresh.slots.map(s=>({slot_key:s.slot_key,label:s.label,kind:s.kind}))};
            this.mergeEvidence([correction],fresh);
            await this.event(task?'REPAIR':'PLAN','Correcting the inspection target once; no page action executed',{failure_code:code,correction_attempt:1});
            return this.paid(fresh,task,error,true);
          }
          await this.event(task?'REPAIR':'PLAN','Inspection target correction exhausted; stopping without page actions',{failure_code:code});
        }
        if(code==='TRUNCATED_BY_THINKING'&&Number.isFinite(data.cost)&&!this.ledger.pending_request){
          // The model spent every output token thinking. Retry ladder, one paid call per rung, inside the question's plan
          // budget: (1) ask the router to avoid the provider that let the thinking run past its cap, (2) plan without
          // thinking at all. A third failure stops with the truncation named.
          const hints=this.current.planHints||={avoid_providers:[],reasoning_mode:''};
          // One provider retry, then thinking off: the question has three plan calls in total.
          if(data.provider&&!hints.avoid_providers.length&&!hints.reasoning_mode){hints.avoid_providers.push(data.provider);await this.persist();
            await this.event(task?'REPAIR':'PLAN',`Reply was all thinking (${data.reasoning_tokens||'?'} tokens) and no answer; retrying without provider ${data.provider}`,{failure_code:code,avoid_providers:hints.avoid_providers});return this.paid(fresh,task,error);}
          if(!hints.reasoning_mode){hints.reasoning_mode='off';await this.persist();
            await this.event(task?'REPAIR':'PLAN','Reply was all thinking and no answer again; retrying with thinking off',{failure_code:code});return this.paid(fresh,task,error);}
        }
        throw new Fault(code,(data.detail||'Backend returned no plan.').replace(new RegExp('^'+code+':\\s*'),''));
      }
      await this.event(task?'REPAIR':'PLAN','Received validated model response',diagnostic);
      const r=data.response;
      if(r.question_key!==obs.question_key||r.observation_id!==obs.observation_id)throw new Fault('TARGET_STALE','Response evidence ID differs.');
      return r;
    }
    validate(plan,obs,failed=null){
      if(plan.kind!=='plan')return;
      const tasks=plan.tasks||[],allowed=TASK_OPERATION;
      if(!obs.completeness.complete||!tasks.length)throw new Fault('QUESTION_INCOMPLETE','Cannot execute an incomplete plan.');
      if(failed&&(tasks.length!==1||tasks[0].slot_key!==failed.slot_key||tasks[0].task_id!==failed.task_id||JSON.stringify(tasks[0].depends_on||[])!==JSON.stringify(failed.depends_on||[])))throw new Fault('GUARD_REJECTED','Repair widened its scope.');
      // A slot that stayed unresolved after identification (a locked or computed cell) is not required in the plan; the
      // rounds after the batch re-check it in case answering unlocked it.
      const required=obs.slots.filter(s=>s.kind!=='unresolved');
      // The one unresolved slot a plan may name: a candidate choice group whose only missing evidence is pick-one vs
      // pick-many. The operation is the model's reading; execute() has the page confirm it before anything is clicked.
      const keys=new Set(tasks.map(t=>t.slot_key)),assertable=obs.slots.filter(s=>this.modeAssertable(s));
      if(!failed&&(keys.size!==tasks.length||!required.every(r=>keys.has(r.slot_key))||![...keys].every(k=>required.some(r=>r.slot_key===k)||assertable.some(a=>a.slot_key===k))))throw new Fault('QUESTION_INCOMPLETE','Plan does not cover every answerable slot.');
      for(const t of tasks){const s=this.slot(obs,t.slot_key);if(this.modeAssertable(s)){if(!['choose_one','set_choice_set'].includes(t.operation))throw new Fault('GUARD_REJECTED','A candidate choice group takes choose_one or set_choice_set only.');continue}if(!allowed[s.kind]||allowed[s.kind]!==t.operation)throw new Fault('GUARD_REJECTED','Task operation does not match the slot.');}
      const remaining=new Set(tasks.map(t=>t.task_id)),ordered=[];while(remaining.size){const t=tasks.find(t=>remaining.has(t.task_id)&&(t.depends_on||[]).every(id=>ordered.some(x=>x.task_id===id)||(failed?.depends_on||[]).includes(id)));if(!t)throw new Fault('GUARD_REJECTED','Dependency cycle or unknown task.');ordered.push(t);remaining.delete(t.task_id)}return ordered;
    }
    async inspectRequest(response,obs){
      const r=this.current.recovery;if(++r.inspections>LIMITS.inspections)throw new Fault('BUDGET_EXHAUSTED','Missing-information rounds exhausted.');await this.persist();
      const req=response.inspection,evidence=[];
      this.same(obs);
      obs=await this.observe();this.same(obs); // paid() refreshed DOM refs while validating the reply
      const requestedSlot=obs.slots.find(s=>s.slot_key===req.slot_key);
      // Validate BOTH forms before running a script or inspecting any target.
      if((req.slot_key&&(!requestedSlot||req.requests?.includes('inspect_question')))||(!req.slot_key&&req.requests?.some(op=>op!=='inspect_question')))
        throw new Fault('TARGET_MISSING','Inspection must name an offered slot or use question discovery.');
      // Route inspection to observed question frames. Slot keys are harness IDs,
      // resolved by trusted bindings; the model never has to construct selectors.
      if(req.script){
        const frames=requestedSlot?[requestedSlot.frame]:obs.frames;
        if(frames.length>8)throw new Fault('FRAME_UNREADABLE','Inspection spans too many frames; request a specific slot.');
        const scriptResults=[];
        for(const frame of frames){
          await this.guard();const bindings={};
          for(const slot of obs.slots.filter(s=>s.frame_id===frame.frame_id)){
            const info=await this.inspect(frame,slot.target,'inspect_slot');if(info.binding)bindings[slot.slot_key]=info.binding;
          }
          await this.event('INSPECT','Running read-only inspection in the question frame',{frame_id:frame.frame_id,slot_key:req.slot_key,script:req.script.slice(0,200)});
          const out=await AssignmentVisual.evaluate(this.tabId,req.script,{frame,bindings,stopped:()=>this.cancelled||this.b.stopped()});
          await this.guard();
          if(!out.ok&&/TARGET_STALE|CANCELLED|FRAME_UNREADABLE/.test(out.detail))throw new Fault(/TARGET_STALE|CANCELLED|FRAME_UNREADABLE/.exec(out.detail)[0],out.detail);
          scriptResults.push({frame_id:frame.frame_id,source_document:frame.browser_document,...(out.ok?{result:out.value}:{error:out.detail})});
        }
        evidence.push({operation:'script',inspection_key:hash(req.script),script:req.script.slice(0,400),...(scriptResults.length===1?scriptResults[0]:{results:scriptResults})});
      }
      if(req.requests?.length){
        if(!req.slot_key){
          const observed=await this.observe();this.same(observed);const fresh=await this.classifyCandidateChoices(observed);
          evidence.push({operation:'inspect_question',result:{question:fresh.question,slots:this.publicObservation(fresh).slots,completeness:fresh.completeness}});
        }else{
        for(const op of req.requests){if(!['inspect_frame','inspect_slot','inspect_options','read_control_state','measure_target','inspect_svg_geometry','inspect_scroll_container','classify_choices'].includes(op))throw new Fault('GUARD_REJECTED','Unknown inspection.');
          let fresh=await this.observe(),s=this.slot(fresh,req.slot_key);
          const result=op==='inspect_options'?(s.kind==='selection'?await this.selectionOptions(s.slot_key,true):s.choices?.map(c=>({label:c.label,disabled:c.disabled}))):await this.inspect(s.frame,s.target,op,op==='classify_choices'&&req.selection_mode?{selection_mode:req.selection_mode}:{});
          evidence.push({slot_key:s.slot_key,operation:op,result});
          if(op==='classify_choices')await this.noteAssertion(s,result);
        }
        }
      }
      if(!evidence.length)throw new Fault('TARGET_MISSING','The inspection produced no evidence.');
      const serialized=JSON.stringify(evidence.map(({script,...data})=>data));if(this.current.inspectionSignature===serialized)throw new Fault('REPEATED_STATE','Inspection returned no new evidence.');this.current.inspectionSignature=serialized;this.mergeEvidence(evidence,obs);r.progress();return this.observe();
    }
    async runQuestion(obs){
      let saved=this.ledger.questions[obs.question_key];
      this.current=saved||{key:obs.question_key,document:obs.document_id,completed:{},recovery:new Recovery(),plan:null};
      this.current.recovery=new Recovery(this.current.recovery);this.current.document=obs.document_id;this.current.frameDocuments=obs.frames.map(f=>({frame_id:f.frame_id,document_id:f.document_id}));this.current.enumeration=obs.enumeration;this.ledger.questions[obs.question_key]=this.current;
      await this.event('OBSERVE','Reading question');
      if(obs.discovery_complete===false)throw new Fault('QUESTION_INCOMPLETE','Too many unfamiliar answer candidates to establish coverage; no paid request was made.');
      if(!obs.completeness.complete&&/exceeds? \d+|More than \d+|traversal or identity limit/i.test(obs.completeness.note))throw new Fault('QUESTION_INCOMPLETE',obs.completeness.note+' This extraction limit cannot be repaired by repeating a model request.');
      if(!obs.completeness.complete)await this.event('INSPECT','Question extraction is incomplete; only bounded inspection is allowed',{missing:obs.completeness.note});
      if(obs.completeness.complete)obs=await this.classifyCandidateChoices(obs);
      if(obs.completeness.complete&&(!this.current.plan||this.current.parts?.length>1))obs=await this.revealParts(obs);
      // A readable question with missing controls may request bounded discovery.
      // No answer plan may execute until actual slots have been observed.
      for(const slot of obs.slots)if(obs.completeness.complete&&slot.kind==='position'&&!slot.geometry?.calibrated){await this.readVisual(obs,slot);obs=await this.observe();this.slot(obs,slot.slot_key)}
      if(!this.current.plan){let plan=await this.paid(obs);while(plan.kind==='request_inspection'){obs=await this.inspectRequest(plan,obs);plan=await this.paid(obs)}if(plan.kind==='needs_review')throw new Fault('QUESTION_INCOMPLETE',plan.reason);this.validate(plan,obs);this.current.plan=plan;await this.persist()}
      if(obs.slots.some(s=>s.interaction?.evidence?.verification==='result_icon'))return this.runResultCard(obs);
      await this.executeTasks(this.validate(this.current.plan,obs));
      // Finished means every PART is finished, not every slot seen at the first observe. Two independent sources
      // must agree: the parts the harness could reveal (structure) and the parts the model read in the wording.
      // Controls that appear only after the planned answers are entered (a part revealed by answering) are planned
      // and entered in a further round, within the plan budget.
      for(let round=0;;round++){
        await this.reconcile();await this.visualGate();
        const found=Math.max(1,this.current.parts?.length||1),declared=Math.max(1,this.current.plan.parts_declared||1);
        if(declared>found)throw new Fault('QUESTION_INCOMPLETE',`PART_UNREACHABLE: the instruction names ${declared} parts but only ${found} could be revealed; a person must finish the rest.`,{parts_declared:declared,parts_found:found});
        const views=[];const recheck=async o=>{for(const sl of o.slots)if(sl.kind==='unresolved')delete this.current.interactionActions?.[sl.slot_key];return this.resolveInteractions(o)};
        if(this.current.parts?.length>1){for(const part of this.current.parts)views.push(await recheck(await this.showPart(null,part.part_id)))}else{const after=await this.observe();this.same(after);views.push(await recheck(after))}
        const newSlots=views.flatMap(v=>v.slots).filter(s=>!this.current.plan.tasks.some(t=>t.slot_key===s.slot_key)&&s.kind!=='unresolved');
        const unresolved=views.flatMap(v=>v.slots).filter(s=>s.kind==='unresolved');
        this.current.not_answerable=unresolved.map(s=>s.label||s.slot_key);
        this.current.unresolved=unresolved.filter(s=>!s.disabled).map(s=>({slot_key:s.slot_key,label:s.label}));
        if(!newSlots.length)break;
        if(round>=LIMITS.plan_rounds)throw new Fault('QUESTION_INCOMPLETE',`NEW_PART_APPEARED: ${newSlots.length} answer control(s) appeared after the planned answers were entered and the plan budget is spent; they were not planned.`,newSlots.map(s=>s.label).slice(0,10));
        await this.event('OBSERVE',`${newSlots.length} answer control(s) appeared after the planned answers; planning them`,{labels:newSlots.map(s=>s.label).slice(0,10)});
        const base=views[views.length-1];let extra={...base,observation_id:crypto.randomUUID(),slots:newSlots,question:this.current.question_text||base.question};
        for(const sl of newSlots)if(sl.part_id)(this.current.slot_parts||={})[sl.slot_key]=sl.part_id;
        let plan=await this.paid(extra);while(plan.kind==='request_inspection'){const o=await this.inspectRequest(plan,extra);extra={...o,slots:o.slots.filter(s=>newSlots.some(n=>n.slot_key===s.slot_key)),question:this.current.question_text||o.question};plan=await this.paid(extra)}
        if(plan.kind==='needs_review')throw new Fault('QUESTION_INCOMPLETE',plan.reason);this.validate(plan,extra);
        this.current.plan.tasks.push(...plan.tasks);if(plan.parts_declared>this.current.plan.parts_declared)this.current.plan.parts_declared=plan.parts_declared;await this.persist();
        await this.executeTasks(plan.tasks);
      }
      const unknown=this.current.unresolved||[];
      if(unknown.length){this.current.finished=false;throw new Fault('QUESTION_INCOMPLETE','Answer controls remain unresolved; they are not proven locked and the question is unfinished.',{unresolved:unknown});}
      this.current.finished=true;const left=this.current.not_answerable||[];
      await this.event('FINISH',left.length?`All answerable answers entered and verified by DOM and a confirming screenshot; ${left.length} answer location(s) are currently read-only (no editable marker) or explicitly disabled and were left empty: ${left.slice(0,10).join(', ')}. Save and grade evidence are reported separately.`:'All observed answers entered and verified by DOM and a confirming screenshot. Save and grade evidence are reported separately.',{parts_found:Math.max(1,this.current.parts?.length||1),parts_declared:this.current.plan.parts_declared||1,...(left.length?{not_answerable:left.slice(0,20)}:{})});
    }
    async runResultCard(obs){
      const tasks=this.validate(this.current.plan,obs),s=obs.slots[0],task=tasks[0];
      // A grading click may replace the whole question. Do not start it while any other
      // answer or part would be left behind, and never replay an uncertain attempt.
      if(obs.slots.length!==1||tasks.length!==1||task.operation!=='choose_one'||(this.current.plan.parts_declared||1)>1||this.current.parts?.length>1)
        throw new Fault('QUESTION_INCOMPLETE','A result-card question must expose one complete answer group before automatic entry.');
      if(this.current.result_card_attempt)throw new Fault('GUARD_REJECTED','This result-card attempt was already sent or interrupted. It will not be replayed automatically.');
      this.current.result_card_attempt=true;await this.persist();
      await this.event('EXECUTE','Entering the planned answer once',{slot_key:task.slot_key,requested_value:task.desired});
      const result=await this.execute(task);
      if(result.s.answer_result!=='correct')throw new Fault('VALUE_MISMATCH','The website marked the selected answer incorrect. No revealed answer or repair request was sent to the model.');
      const chosen=result.s.choices.find(c=>c.label===task.desired.label);
      const measured=await this.inspect(result.s.frame,chosen.target),box=measured.viewport;
      const shot=await AssignmentVisual.screenshot(this.tabId);
      // Freeze the two witnesses before the model call. A transition during capture is
      // unverified; a transition after this check cannot redirect the pending answer.
      const fresh=await this.observe(),again=this.slot(fresh,task.slot_key);
      if(!this.matches(task,again)||again.answer_result!=='correct')throw new Fault('TARGET_STALE','Result changed during screenshot capture.');
      const liveChoice=again.choices.find(c=>c.label===task.desired.label),after=(await this.inspect(again.frame,liveChoice.target)).viewport;
      if(!box||!after||['x','y','w','h'].some(k=>Math.abs(box[k]-after[k])>1)||box.x<0||box.y<0||box.x+box.w>shot.viewport.width||box.y+box.h>shot.viewport.height)
        throw new Fault('GUARD_REJECTED','The selected card was not fully visible and stable for verification.');
      const bitmap=await createImageBitmap(await (await fetch(shot.dataUrl)).blob());
      const sx=bitmap.width/shot.viewport.width,sy=bitmap.height/shot.viewport.height;
      const crop=new OffscreenCanvas(Math.floor(box.w*sx),Math.floor(box.h*sy)),ctx=crop.getContext('2d');
      ctx.drawImage(bitmap,box.x*sx,box.y*sy,box.w*sx,box.h*sy,0,0,crop.width,crop.height);bitmap.close();
      const bytes=new Uint8Array(await (await crop.convertToBlob({type:'image/png'})).arrayBuffer());
      let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      const observation=this.publicObservation(obs);observation.observation_id=fresh.observation_id;observation.screenshot='data:image/png;base64,'+btoa(binary);
      // The verifier sees only the chosen card and its pre-existing label, never
      // another card's revealed correct marker or the page's answer-key feedback.
      observation.evidence=[];observation.slots=observation.slots.map(sl=>({...sl,options:[task.desired.label],current:[task.desired.label]}));
      const verdict=await this.verifySnapshot(observation,[{slot_key:task.slot_key,label:s.label,value:task.desired.label}]);
      if(verdict.kind!=='verified')throw new Fault('VALUE_MISMATCH','The selected-card screenshot did not confirm this attempt. It will not be replayed.');
      this.current.completed[task.slot_key]={entry_verified:true,visual_verified:true,action_executed:!result.skipped,actual:[task.desired.label],document_id:fresh.document_id,grade_state:'correct',save_state:fresh.save_state};
      this.current.finished=true;this.current.recovery.progress();
      await this.event('FINISH','Selected answer confirmed by its own result marker and a cropped screenshot.',{entry_verified:true,grade_state:'correct'});
      this.b.progress(1,1,Object.keys(this.ledger.questions).length,this.ledger.cost,this.steps);
    }
    async executeTasks(tasks){let count=0;
      for(let task of tasks){
        // Resume always reads the value, including previously completed tasks.
        let complete=false;
        while(!complete){await this.guard();await this.event('EXECUTE',`Entering ${count+1} of ${tasks.length}`,{slot_key:task.slot_key,task_id:task.task_id,adapter:task.operation,requested_value:task.desired});
          try{const result=await this.execute(task);this.current.completed[task.slot_key]={entry_verified:true,action_executed:!result.skipped,actual:result.s.current,save_state:result.obs.save_state,grade_state:result.obs.grade_state,document_id:result.obs.document_id};this.current.recovery.progress();complete=true;count++;
            // A pick-one/pick-many group whose mode came from the model, not the page, says so here: the readback
            // proved what is selected, not that the question wanted that many.
            await this.event('VERIFY',`${count} of ${tasks.length} answers verified`,{slot_key:task.slot_key,actual:result.s.current,entry_verified:true,...(result.s.interaction?.evidence?.selection_mode_source==='model_assertion'?{cardinality:'asserted by the model; verified by selected-state readback only'}:{})});this.b.progress(count,tasks.length,Object.keys(this.ledger.questions).length,this.ledger.cost,this.steps);
          }catch(e){if(!(e instanceof Fault))throw e;if(['CANCELLED','TARGET_STALE','BUDGET_EXHAUSTED','GEOMETRY_UNCALIBRATED','FRAME_UNREADABLE'].includes(e.code))throw e;
            const partId=this.current?.slot_parts?.[task.slot_key];const fresh=partId?await this.showPart(null,partId):await this.observe(),s=this.slot(fresh,task.slot_key);let local=false;try{local=this.current.recovery.failure(task,e,{current:s.current,options:s.frame.menus.filter(m=>m.owner===s.local_slot).map(m=>m.label)})}finally{await this.persist()}
            if(local&&['TARGET_MISSING','INPUT_NO_EFFECT','VALUE_MISMATCH','WRONG_MENU_OWNER'].includes(e.code)){await this.event('LOCAL_RECOVERY','Re-observing the failed widget: '+e.message,{failure_code:e.code,...(e.actual!=null?{actual:e.actual}:{})});continue}
            if(++this.current.recovery.repairs>LIMITS.repairs)throw new Fault('BUDGET_EXHAUSTED','Question repair budget reached.');await this.persist();
            let repairObs=fresh,patch=await this.paid(repairObs,task,e);while(patch.kind==='request_inspection'){repairObs=await this.inspectRequest(patch,repairObs);patch=await this.paid(repairObs,task,e)}if(patch.kind!=='plan')throw new Fault('QUESTION_INCOMPLETE',patch.reason||'Repair needs more evidence.');this.validate(patch,repairObs,task);task=patch.tasks[0];const index=this.current.plan.tasks.findIndex(t=>t.slot_key===task.slot_key);this.current.plan.tasks[index]=task;this.current.recovery.progress();await this.persist();
          }
        }
        if(count%8===0){await this.event('OBSERVE','Reconciling completed batch');await this.reconcile()}
      }
    }
    // Parts. A tab strip means only the selected part's controls are visible. Reveal each part by clicking its tab
    // (what a student does), observe it while visible, and plan across the union -- nothing hidden is ever read.
    async showPart(obs,partId){
      let o=obs||await this.observe();if(!o.parts?.length)return o;
      if(o.parts.find(p=>p.selected)?.part_id===partId)return o;
      const part=o.parts.find(p=>p.part_id===partId);if(!part)throw new Fault('TARGET_MISSING','Part tab is not present.',partId);
      if(part.disabled)throw new Fault('GUARD_REJECTED','Part tab is disabled.',part.label);
      await this.click(part.frame,part.target,{purpose:'show_part',executor_reason:'Reveal this part of the question; only the selected part\'s answer controls are visible.',part_id:partId,part_label:part.label});
      const until=Date.now()+LIMITS.ui;let previous=null;
      do{await sleep(120);o=await this.observe();this.same(o);
        if(o.parts.find(p=>p.selected)?.part_id===partId){const keys=o.slots.map(s=>s.slot_key).sort().join('|');if(previous===keys)return o;previous=keys}
      }while(Date.now()<until);
      throw new Fault('TARGET_MISSING','Part did not become selected and settle after clicking its tab.',part.label);
    }
    async revealParts(obs){
      // Each part is prepared while it is the visible one: its unresolved widgets identified and its dropdown
      // choices read, exactly as a single-part question is. Then the parts are merged into one observation.
      const prepare=async o=>{o=await this.resolveInteractions(o);return this.discoverSelectionOptions(o)};
      if(!obs.parts||obs.parts.length<2)return prepare(obs);
      const start=obs.parts.find(p=>p.selected)?.part_id,seen=new Map();
      const record=o=>{const id=o.parts.find(p=>p.selected)?.part_id||null;seen.set(id,{question:o.question,complete:o.completeness.complete,note:o.completeness.note,tableComplete:o.table_context_complete,slots:o.slots.filter(s=>(s.part_id||id)===id),tables:(o.tables||[]).map(t=>({...t,part_id:id}))})};
      record(await prepare(obs));
      for(const part of obs.parts){if(seen.has(part.part_id)||part.disabled)continue;const shown=await prepare(await this.showPart(null,part.part_id));record(shown);
        await this.event('OBSERVE',`Revealed part "${part.label}"`,{part_id:part.part_id,slots:seen.get(part.part_id).slots.length});}
      if(start)await this.showPart(null,start);
      // Merge: every part's slots once; the question text is the first part's text plus what each other part adds.
      const slots=[],keys=new Set();for(const [,v] of seen)for(const s of v.slots)if(!keys.has(s.slot_key)){keys.add(s.slot_key);slots.push(s)}
      const base=seen.get(start)?.question||obs.question;const extra=[...seen.entries()].filter(([id])=>id!==start).map(([id,v])=>{const label=obs.parts.find(p=>p.part_id===id)?.label||id;return `[Part "${label}"] `+added(base,v.question)});
      const tables=[],tkeys=new Set();for(const [,v] of seen)for(const t of v.tables){const k=(t.part_id||'')+':'+t.frame_id+':'+(t.dom_id||JSON.stringify(t.rows?.[0]||''));if(!tkeys.has(k)){tkeys.add(k);tables.push(t)}}
      const fullText=[base,...extra].join('\n\n'),complete=[...seen.values()].every(v=>v.complete)&&fullText.length<=60000;
      this.current.parts=obs.parts.map(p=>({part_id:p.part_id,label:p.label}));this.current.slot_parts=Object.fromEntries(slots.filter(s=>s.part_id).map(s=>[s.slot_key,s.part_id]));this.current.question_text=fullText.slice(0,60000);await this.persist();
      if(slots.length>100)throw new Fault('QUESTION_INCOMPLETE','More than 100 answer slots across parts; narrow the question scope.');
      return {...obs,observation_id:crypto.randomUUID(),slots,tables:tables.slice(0,12),table_context_complete:[...seen.values()].every(v=>v.tableComplete)&&tables.length<=12,question:fullText.slice(0,60000),
        completeness:{complete,note:complete?'':fullText.length>60000?'Question context across parts exceeds 60000 characters.':[...seen.values()].map(v=>v.note).filter(Boolean).join('; ')}};
    }
    // Second witness. After every answer is confirmed by DOM readback, a
    // screenshot is shown to the model to confirm the entered values are actually
    // visible. A mismatch drops those answers and re-enters them, bounded by
    // LIMITS.verify; graph points are excluded (their own calibrated readback is
    // the witness). No confirming screenshot for a question with no textual
    // answers to see.
    async confirmVisually(obs){
      // Only confirm answers actually VISIBLE in the current viewport: a human
      // (and the screenshot) cannot see an off-screen slot, so verifying it would
      // be a false mismatch. Off-screen answers stay DOM-verified. Slots are
      // measured against the live viewport, not assumed on screen.
      const v=await this.b.viewport(this.tabId),expected=[];
      for(const t of this.current.plan.tasks){
        if(!this.current.completed[t.slot_key]||plannedValue(t)==='')continue;
        if(!obs.slots.some(x=>x.slot_key===t.slot_key))continue;   // another part's slot: confirmed when that part is shown
        if(this.current.graded?.[t.slot_key])continue;                 // screen-readback group the page already graded: its icons are the witness, the model sees no revealed key
        const s=this.slot(obs,t.slot_key);let box=null;try{box=(await this.inspect(s.frame,s.target)).viewport}catch{box=null}
        if(!box||box.y+box.h<0||box.y>v.height||box.x+box.w<0||box.x>v.width)continue;
        expected.push({slot_key:t.slot_key,label:s.label,value:t.operation==='enter_value'&&s.current!=null&&String(s.current)!==''?String(s.current):plannedValue(t)});
      }
      if(!expected.length)return {kind:'verified'};
      const shot=await AssignmentVisual.screenshot(this.tabId);
      const observation=this.publicObservation(obs);observation.screenshot=shot.dataUrl;
      return this.verifySnapshot(observation,expected);
    }
    async verifySnapshot(observation,expected){
      await this.guard();const generation=this.generation;
      const body={run_id:this.id,request_id:crypto.randomUUID(),spend_limit:this.config.spend_limit,model:this.config.model,observation,expected};
      this.ledger.pending_request=body.request_id;await this.persist();
      await this.event('VERIFY','Confirming answers from a screenshot (second witness)',{slot_count:expected.length});
      await this.logObservation('VERIFY',body);
      const data=await this.modelCall('verify',body);
      if(Number.isFinite(data.cost)){this.ledger.cost+=data.cost;this.ledger.pending_request=null}await this.persist();await this.guard();
      if(generation!==this.generation)throw new Fault('CANCELLED','Discarded late verification.');
      await this.event('VERIFY',data.response?'Screenshot verification: '+data.response.kind:'Screenshot verification response rejected',{model_calls:1,cost:data.cost,input_tokens:data.input_tokens,output_tokens:data.output_tokens,reasoning_tokens:data.reasoning_tokens,mismatches:data.response?.mismatches,request_id:body.request_id,model:data.model||body.model||'(backend default)',requested_model:body.model||'',provider:data.provider||undefined,finish_reason:data.finish_reason,raw:data.raw_reply,detail:data.response?.reason||data.detail||'',response_kind:data.response?.kind});
      if(!data.response){const message=data.detail||'Visual verification returned nothing.';const code=/^([A-Z_]+):/.exec(message)?.[1]||'VALUE_MISMATCH';throw new Fault(code,message.replace(/^[A-Z_]+:\s*/,''));}
      return data.response;
    }
    async visualGate(){
      if(this.current.parts?.length>1){for(const part of this.current.parts){await this.showPart(null,part.part_id);await this.visualGateView()}return}
      return this.visualGateView();
    }
    async visualGateView(){
      for(let round=0;round<=LIMITS.verify;round++){
        const obs=await this.observe();this.same(obs);
        const result=await this.confirmVisually(obs);
        if(result.kind==='verified'){this.current.recovery.progress();return}
        if(round>=LIMITS.verify)throw new Fault('VALUE_MISMATCH','A screenshot could not confirm these answers after re-entry: '+result.mismatches.join(', ')+'. '+(result.reason||''));
        for(const k of result.mismatches){
          const task=this.current.plan.tasks.find(t=>t.slot_key===k);if(!task)continue;
          delete this.current.completed[k];await this.event('LOCAL_RECOVERY','Screenshot disagreed; re-entering answer',{slot_key:k,failure_code:'VALUE_MISMATCH',detail:result.reason});
          const r=await this.execute(task,true);this.current.completed[k]={entry_verified:true,action_executed:!r.skipped,actual:r.s.current,save_state:r.obs.save_state,grade_state:r.obs.grade_state,document_id:r.obs.document_id};
        }
      }
    }
    async reconcile(){
      if(this.current.parts?.length>1){let last=null;for(const part of this.current.parts){const view=await this.showPart(null,part.part_id);last=await this.reconcileView(view,t=>this.current.slot_parts?.[t.slot_key]===part.part_id)}return last}
      return this.reconcileView(await this.observe(),()=>true);
    }
    async reconcileView(obs,include){
      this.same(obs);
      if(obs.save_state==='pending'){
        const until=Date.now()+LIMITS.navigation;await this.event('VERIFY','Waiting for save');
        do{await sleep(150);obs=await this.observe();this.same(obs);if(obs.save_state!=='pending')break}while(Date.now()<until);
        if(obs.save_state==='pending')throw new Fault('SAVE_TIMEOUT','Page still reports saving.');
      }
      for(const task of this.current.plan.tasks){if(!this.current.completed[task.slot_key]||!include(task))continue;const s=this.slot(obs,task.slot_key);
        if(!this.matches(task,s)){delete this.current.completed[task.slot_key];throw new Fault('VALUE_MISMATCH','Previously completed answer changed during reconciliation.',s.current)}
        Object.assign(this.current.completed[task.slot_key],{actual:s.current,save_state:obs.save_state,grade_state:obs.grade_state});
      }
      return obs;
    }
    async run(){if(this.busy)throw new Fault('GUARD_REJECTED','One operation is already running.');this.busy=true;this.ledger.status='running';await this.persist();
      try{if(this.ledger.pending_request)throw new Fault('BUDGET_EXHAUSTED','Prior request cost is uncertain; reconcile before resuming.');let navigationStates=new Set();
        while(true){this.current=null;let obs=await this.observe();if(obs.page_state==='complete'){await this.event('FINISH','Page reports assignment complete.',{grade_state:obs.grade_state,save_state:obs.save_state});this.ledger.status='completed';break}
          if(obs.page_state!=='locked')await this.runQuestion(obs);else await this.event('FINISH','Attempt is graded and locked; answer entry is retired.',{grade_state:obs.grade_state,save_state:obs.save_state});
          obs=await this.observe();this.config=await this.b.config();
          if(this.current?.finished&&obs.question_key!==this.current.key){
            if(!this.config.advance){this.ledger.status='finished';break}
            await this.event('ADVANCE','The page advanced after the verified answer; observing the new question.');continue;
          }
          if(this.config.check_work&&this.current?.finished&&obs.page_state==='answering'){
            const checks=obs.navigation.filter(n=>n.kind==='check'&&!n.disabled),signature=hash(JSON.stringify(this.current.plan));this.current.checks||=[];
            if(checks.length===1&&!this.current.checks.includes(signature)){
              this.current.checks.push(signature);await this.persist();await this.event('VERIFY','Checking work once for this answer plan.');await this.click(checks[0].frame,checks[0].target,{purpose:'check_work',executor_reason:'Check work is authorized and this answer plan has not been checked yet.',navigation_label:checks[0].label});
              const until=Date.now()+LIMITS.navigation;let feedback=false;do{await sleep(150);const fresh=await this.observe();if(fresh.feedback!==obs.feedback||fresh.page_state!==obs.page_state||fresh.question_key!==obs.question_key){obs=fresh;feedback=true;break}}while(Date.now()<until);
              if(!feedback)throw new Fault('INPUT_NO_EFFECT','Check produced no new feedback. It will not be repeated.');
              await this.event('VERIFY','Website feedback received',{grade_state:obs.grade_state,save_state:obs.save_state});
              if(obs.grade_state==='incorrect'&&obs.page_state!=='locked')throw new Fault('VALUE_MISMATCH','Website graded this attempt incorrect and permits editing. Review feedback before another attempt.');
            }
          }
          if(!this.config.advance){this.ledger.status='finished';break}
          const next=obs.navigation.filter(n=>n.kind==='advance'&&!n.disabled);
          if(next.length!==1){
            if(this.config.auto_submit&&obs.navigation.some(n=>n.kind==='submit')){
              const questions=Object.values(this.ledger.questions),total=obs.enumeration?.total,indices=new Set(questions.filter(q=>q.finished&&q.enumeration&&q.enumeration.total===total).map(q=>q.enumeration.index));
              if(!Number.isInteger(total)||total<1||indices.size!==total||Array.from({length:total},(_,i)=>i+1).some(i=>!indices.has(i)))throw new Fault('QUESTION_INCOMPLETE','Full assignment enumeration is unavailable. Automatic submission is withheld; review and submit manually.');
              if(this.current)obs=await this.reconcile()||await this.observe();const buttons=obs.navigation.filter(n=>n.kind==='submit'&&!n.disabled);if(buttons.length!==1)throw new Fault('TARGET_AMBIGUOUS','Submission target is not unique.');
              if(this.ledger.submission_sent)throw new Fault('REPEATED_STATE','Submission was already sent; review its result.');
              this.ledger.submission_sent=true;await this.persist();await this.event('FINISH','Submitting the enumerated, verified assignment.');await this.click(buttons[0].frame,buttons[0].target,{purpose:'submit_assignment',executor_reason:'Submission is enabled and assignment enumeration and verification gates passed.',navigation_label:buttons[0].label});
              const until=Date.now()+LIMITS.navigation;let confirmed=false;do{await sleep(150);const p=await this.observe();if(p.page_state==='complete'){confirmed=true;await this.event('FINISH','Assignment submission confirmed by the page.',{save_state:p.save_state,grade_state:p.grade_state});break}}while(Date.now()<until);
              if(!confirmed)throw new Fault('SAVE_TIMEOUT','Submission was sent but not confirmed. Do not repeat it without reviewing the page.');this.ledger.status='completed';break;
            }
            if(next.length>1)throw new Fault('TARGET_AMBIGUOUS','More than one Next control.');this.ledger.status='finished';await this.event('FINISH','Observed question complete. No unique next-question control found.');break;
          }
          const signature=obs.question_key+':'+next[0].target;if(navigationStates.has(signature))throw new Fault('REPEATED_STATE','Navigation returned to the same question.');navigationStates.add(signature);
          await this.event('ADVANCE','Moving to the next question');await this.click(next[0].frame,next[0].target,{purpose:'advance',executor_reason:'Automatic continuation is enabled and the current attempt is complete or locked.',navigation_label:next[0].label});
          const until=Date.now()+LIMITS.navigation;let changed=false;do{await sleep(150);const p=await this.observe();if(p.question_key!==obs.question_key||p.page_state==='complete'){changed=true;break}}while(Date.now()<until);if(!changed)throw new Fault('INPUT_NO_EFFECT','Next did not reach a different question.');
        }
      }catch(e){this.ledger.status=this.cancelled||this.b.stopped()?'cancelled':'needs_review';
        // A Fault's `actual` (e.g. what was actually hit, or which scroll container) was captured at the failure
        // site and then silently dropped here -- the Copy log could never show what an occlusion/geometry guard saw.
        await this.event(this.ledger.status==='cancelled'?'CANCELLED':'NEEDS_REVIEW',e.message,{failure_code:e.code||'FAILED',...(e.actual!=null?{failure_data:e.actual}:{})});}
      finally{this.busy=false;await this.persist()}
      return this.ledger;
    }
  }
  globalThis.AssignmentPlanner={Engine,Recovery,Fault,LIMITS,visualGeometry,numeric,sameValue,plainDigits};
})();
