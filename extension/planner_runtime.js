/* Protocol 4 deterministic execution. No answer model calls inside widget adapters. */
(() => {
  const norm=s=>String(s??'').replace(/\s+/g,' ').replace(/\s*\[active\]\s*/g,' ').trim();
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

  const LIMITS={ui:5000,navigation:15000,local:2,repairs:2,inspections:2,verify:2,noProgress:90000,question:300000,request:60000};
  // The value a task intends, rendered for the second-witness screenshot check.
  // place_points has no textual value -- the graph is confirmed by its own
  // calibrated readback, so it is excluded from the visual answer list.
  const plannedValue=task=>{const d=task.desired||{};switch(task.operation){
    case 'choose_one':case 'set_selection':return d.label||'';
    case 'enter_value':return d.value||'';
    case 'set_choice_set':return (d.labels||[]).join(', ');
    case 'set_order':return (d.sequence||[]).join(' > ');
    default:return '';}};
  class Fault extends Error{constructor(code,detail,actual=null){super(code+': '+detail);this.code=code;this.actual=actual}}
  const requireOK=r=>{if(!r?.ok)throw new Fault(r?.code||'INPUT_NO_EFFECT',r?.detail||'Browser operation failed.');return r};
  class Recovery {
    constructor(saved={}){Object.assign(this,{started:Date.now(),progressAt:Date.now(),local:{},signatures:{},states:{},repairs:0,inspections:0,history:[]},saved)}
    check(){if(Date.now()-this.started>LIMITS.question)throw new Fault('BUDGET_EXHAUSTED','Question deadline reached.');if(Date.now()-this.progressAt>LIMITS.noProgress)throw new Fault('REPEATED_STATE','No meaningful question progress for 90 seconds.')}
    progress(){this.progressAt=Date.now()}
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

    async persist(){await chrome.storage.local.set({planner_run:JSON.parse(JSON.stringify(this.ledger))})}
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
      const obs={question_key,document_id,observation_id:crypto.randomUUID(),question:used.map(f=>f.question).join('\n'),slots,frames,
        completeness:{complete:slots.length<=100&&frames.every(f=>f.completeness.complete),note:(slots.length>100?'More than 100 answer slots; narrow the question scope. ':'')+frames.map(f=>f.completeness.note).filter(Boolean).join('; ')},
        enumeration:frames.find(f=>f.enumeration)?.enumeration||null,
        page_state:frames.find(f=>f.page_state!=='answering')?.page_state||'answering',host:frames[0].host,
        navigation:frames.flatMap(f=>f.navigation.map(n=>({...n,frame:f}))),feedback:frames.map(f=>f.feedback).filter(Boolean).join('; '),
        grade_state:frames.find(f=>f.grade_state!=='unknown')?.grade_state||'unknown',save_state:frames.some(f=>f.save_state==='pending')?'pending':frames.some(f=>f.save_state==='confirmed')?'confirmed':'unavailable',visual:frames.some(f=>f.visual)};
      if(new Set(slots.map(s=>s.slot_key)).size!==slots.length)throw new Fault('TARGET_AMBIGUOUS','Duplicate logical slots.');
      return obs;
    }
    same(obs){if(!this.current||obs.question_key!==this.current.key||obs.document_id!==this.current.document)throw new Fault('TARGET_STALE','Question or document changed; pending task discarded.')}
    slot(obs,key){this.same(obs);const s=obs.slots.filter(s=>s.slot_key===key);if(s.length===1&&!s[0].geometry?.calibrated&&this.current.visual?.[key]){s[0].geometry=this.current.visual[key];s[0].current=s[0].geometry.points;}if(s.length!==1)throw new Fault(s.length?'TARGET_AMBIGUOUS':'TARGET_MISSING','Logical answer slot is not unique.');return s[0]}
    async inspect(frame,target,operation='measure_target',extra={}){await this.guard();const r=await chrome.tabs.sendMessage(this.tabId,{type:'planner_inspect',operation,target,document_id:frame.document_id,observation_id:frame.observation_id,...extra},{frameId:frame.frame_id});requireOK(r);if(r.local&&!r.viewport&&frame.measured_offset)r.viewport={...r.local,x:r.local.x+frame.measured_offset.x,y:r.local.y+frame.measured_offset.y};return r}
    async measure(frame,target){
      for(let i=0;i<12;i++){
        const r=await this.inspect(frame,target);if(!r.viewport)throw new Fault('GEOMETRY_UNCALIBRATED','Frame transform is not measurable.');
        const v=await this.b.viewport(this.tabId),box=r.viewport;
        if(box.y>=0&&box.y+Math.min(box.h,30)<=v.height&&box.x>=0&&box.x<v.width){if(!r.actionable)throw new Fault('GUARD_REJECTED','Target is disabled.');if(!r.hit)throw new Fault('GUARD_REJECTED','An overlay blocks the exact target.');return r}
        const dy=box.y<0?Math.max(-600,box.y-50):Math.min(600,box.y-v.height/2);
        await this.guard();await AssignmentVisual.wheel(this.tabId,{x:Math.max(2,Math.min(v.width-2,box.x+box.w/2)),y:Math.max(2,Math.min(v.height-2,box.y<0?30:v.height-30))},0,dy,()=>this.cancelled||this.b.stopped());await sleep(80);
      }throw new Fault('TARGET_MISSING','Could not scroll the target into view.');
    }
    async click(frame,target){const r=await this.measure(frame,target);await this.guard();await AssignmentVisual.click(this.tabId,{x:r.viewport.x+r.viewport.w/2,y:r.viewport.y+r.viewport.h/2},{},()=>this.cancelled||this.b.stopped());this.steps++;await this.event('EXECUTE','Browser click executed',{target,frame_id:frame.frame_id,document_id:frame.document_id,observation_id:frame.observation_id,action_executed:true});return r}
    async key(key){await this.guard();return AssignmentVisual.key(this.tabId,key,()=>this.cancelled||this.b.stopped())}
    matches(task,s){const d=task.desired;
      switch(task.operation){
        case 'choose_one':return JSON.stringify((s.current||[]).map(norm))===JSON.stringify([norm(d.label)]);
        case 'set_choice_set':return JSON.stringify((s.current||[]).map(norm).sort())===JSON.stringify(d.labels.map(norm).sort());
        case 'enter_value':return String(s.current??'')===d.value;
        case 'set_selection':return norm(s.current)===norm(d.label);
        case 'set_order':return JSON.stringify(s.current.map(norm))===JSON.stringify(d.sequence.map(norm));
        case 'place_points':if(s.geometry?.visual&&!s.geometry.labeled)return d.points.length===s.geometry.points.length&&d.points.every(p=>s.geometry.points.some(a=>Math.abs(a.x-p.x)<=s.geometry.tolerance&&Math.abs(a.y-p.y)<=s.geometry.tolerance));return !!s.geometry?.calibrated&&d.points.length===s.geometry.points.length&&d.points.every(p=>{const a=s.geometry.points.find(a=>a.id===p.id);return a&&Math.abs(a.x-p.x)<=s.geometry.tolerance&&Math.abs(a.y-p.y)<=s.geometry.tolerance});
        default:throw new Fault('GUARD_REJECTED','Unknown task operation.');
      }
    }
    async waitTask(task,budget=LIMITS.ui){const until=Date.now()+budget;let obs,s;do{await this.guard();obs=await this.observe();s=this.slot(obs,task.slot_key);if(this.matches(task,s))return {obs,s};await sleep(100)}while(Date.now()<until);throw new Fault('VALUE_MISMATCH','Expected answer did not appear in its logical slot.',s.current)}
    async execute(task){
      let obs=await this.observe(),s=this.slot(obs,task.slot_key);if(this.matches(task,s))return {obs,s,skipped:true};
      if(s.disabled)throw new Fault('GUARD_REJECTED','Answer field is disabled.');
      const d=task.desired;
      if(task.operation==='choose_one'||task.operation==='set_choice_set'){
        const wanted=task.operation==='choose_one'?[d.label]:d.labels;
        if(wanted.some(label=>s.choices.filter(c=>norm(c.label)===norm(label)).length!==1))throw new Fault('TARGET_AMBIGUOUS','Choice label is missing or repeated within its group.');
        // Checkboxes reconcile every member, including unintended checked choices.
        for(const label of s.choices.map(c=>c.label)){obs=await this.observe();s=this.slot(obs,task.slot_key);const c=s.choices.find(c=>c.label===label),want=wanted.some(w=>norm(w)===norm(label));
          if(c.checked===want||task.operation==='choose_one'&&!want)continue;
          if(c.disabled)throw new Fault('GUARD_REJECTED','Desired choice is disabled.');await this.click(s.frame,c.target);await sleep(70);}
      }else if(task.operation==='enter_value'){
        await this.click(s.frame,s.target);if(!(await this.inspect(s.frame,s.target)).focused)throw new Fault('INPUT_NO_EFFECT','Text field did not acquire focus.');await this.key('Control+a');await this.guard();if(!(await this.inspect(s.frame,s.target)).focused)throw new Fault('TARGET_STALE','Focus changed before typing.');if(d.value)await AssignmentVisual.insertText(this.tabId,d.value,()=>this.cancelled||this.b.stopped());else await this.key('Backspace');
        // Blur through Tab, never Enter (which can submit a form).
        const focused=await this.inspect(s.frame,s.target);if(!focused.focused)throw new Fault('TARGET_STALE','Focus moved before commit.');await this.key('Tab');
      }else if(task.operation==='set_selection'){
        if(s.native){
          await this.click(s.frame,s.target);await this.key('Escape');let m=await this.inspect(s.frame,s.target);
          const targets=m.options.filter(o=>norm(o.label)===norm(d.label));if(targets.length!==1)throw new Fault('TARGET_AMBIGUOUS','Native option label is not unique.');if(targets[0].disabled)throw new Fault('GUARD_REJECTED','Desired native option is disabled.');
          const enabled=m.options.filter(o=>!o.disabled);let seen=new Set();
          for(let i=0;i<=enabled.length;i++){m=await this.inspect(s.frame,s.target);if(norm(m.value)===norm(d.label))break;if(!m.focused)throw new Fault('TARGET_STALE','Dropdown lost focus.');
            if(seen.has(m.selectedIndex))throw new Fault('INPUT_NO_EFFECT','Native selection did not move.');seen.add(m.selectedIndex);
            const index=m.options.findIndex(o=>norm(o.label)===norm(d.label));await this.key(index>m.selectedIndex?'ArrowDown':'ArrowUp');await sleep(70)}await this.key('Tab');
        }else{
          // Cell, activated editor and detached option keep the same logical slot.
          let menu=s.frame.menus.filter(m=>m.owner===s.local_slot);
          if(!menu.length){const arrow=s.representations?.[0];await this.click(s.frame,arrow||s.target);this.current.opened||={};this.current.opened[s.slot_key]=!!arrow;this.current.recovery.progress();
            const until=Date.now()+LIMITS.ui;do{obs=await this.observe();s=this.slot(obs,task.slot_key);menu=s.frame.menus.filter(m=>m.owner===s.local_slot);if(menu.length)break;
              // A cell can expose an arrow only after activation; click it once.
              if(s.representations?.length&&!this.current.opened?.[s.slot_key]){this.current.opened||={};this.current.opened[s.slot_key]=true;await this.click(s.frame,s.representations[0]);}
              await sleep(100);}while(Date.now()<until);
          }
          if(!menu.length)throw new Fault('WRONG_MENU_OWNER','No open menu is associated with this answer field.');
          const options=menu.filter(m=>norm(m.label)===norm(d.label));if(!options.length)throw new Fault('OPTION_MISSING','Desired option absent.',menu.map(o=>o.label));if(options.length!==1)throw new Fault('TARGET_AMBIGUOUS','Two menu options share that label.');if(options[0].disabled)throw new Fault('GUARD_REJECTED','Desired option is disabled.');
          await this.click(s.frame,options[0].target);
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
      const data=await this.b.request('visual',body,this.abort.signal);
      if(Number.isFinite(data.cost)){this.ledger.cost+=data.cost;this.ledger.pending_request=null}await this.persist();await this.guard();
      if(generation!==this.generation)throw new Fault('CANCELLED','Discarded late visual measurement.');
      const fresh=await this.observe(),current=this.slot(fresh,slot.slot_key),after=await this.inspect(current.frame,current.target);
      if(fresh.document_id!==obs.document_id||JSON.stringify(after.viewport)!==JSON.stringify(box))throw new Fault('TARGET_STALE','Graph moved during visual inspection.');
      const newShot=await AssignmentVisual.screenshot(this.tabId);if(await regionHash(newShot,box)!==beforeHash)throw new Fault('TARGET_STALE','Graph content changed during visual inspection.');
      await this.event('INSPECT','Read graph coordinates from a fresh screenshot',{model_calls:1,cost:data.cost,input_tokens:data.input_tokens,output_tokens:data.output_tokens,slot_key:slot.slot_key});
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
    publicObservation(obs){return {question_key:obs.question_key,document_id:obs.document_id,observation_id:obs.observation_id,question:obs.question,slots:obs.slots.map(s=>{s=this.current?this.slot(obs,s.slot_key):s;return ({slot_key:s.slot_key,kind:s.kind,label:s.label,options:s.options,current:s.current,...(s.geometry?{geometry:s.geometry}:{})})}),completeness:obs.completeness,host:obs.host,task_note:this.config.note||'',evidence:this.current?.evidence||[]}}
    async paid(obs,task=null,error=null){await this.guard();await this.event(task?'REPAIR':'PLAN',task?'Repairing the failed task':'Planning answers for this question');const generation=this.generation;const body={run_id:this.id,request_id:crypto.randomUUID(),spend_limit:this.config.spend_limit,model:this.config.model,observation:this.publicObservation(obs)};
      // See what a human sees: the planner always gets DOM + a settled screenshot
      // together, not the scraped controls alone. Redesign per Dylan -- the model
      // plans from the picture (rendered math, diagrams, layout the DOM omits),
      // and the same applies to a repair so it sees the page it is correcting.
      const shot=await AssignmentVisual.screenshot(this.tabId);body.observation.screenshot=shot.dataUrl;
      if(task)Object.assign(body,{task,failure:{code:error.code,detail:error.message,actual:error.actual},completed_slots:Object.keys(this.current.completed),history:this.current.recovery.history});
      this.ledger.pending_request=body.request_id;await this.persist();const start=Date.now();let data;
      try{data=await this.b.request(task?'repair':'plan',body,this.abort.signal)}catch(e){this.ledger.status='needs_review';throw e}
      if(Number.isFinite(data.cost)){this.ledger.cost+=data.cost;this.ledger.pending_request=null}
      await this.persist();await this.guard();if(generation!==this.generation)throw new Fault('CANCELLED','Discarded late model response.');
      const fresh=await this.observe();if(fresh.question_key!==obs.question_key||fresh.document_id!==obs.document_id)throw new Fault('TARGET_STALE','Discarded model response after question/document changed.');
      await this.event(task?'REPAIR':'PLAN',task?'Received a bounded task repair':'Received the question plan',{model_calls:1,cost:data.cost,input_tokens:data.input_tokens,output_tokens:data.output_tokens,duration:Date.now()-start});
      if(!data.response)throw new Fault(data.detail?.split(':')[0]||'FAILED',data.detail||'Backend returned no plan.');
      const r=data.response;
      if(r.question_key!==obs.question_key||r.observation_id!==obs.observation_id)throw new Fault('TARGET_STALE','Response evidence ID differs.');
      return r;
    }
    validate(plan,obs,failed=null){
      if(plan.kind!=='plan')return;
      const tasks=plan.tasks||[],allowed={choice:'choose_one',choice_set:'set_choice_set',value:'enter_value',selection:'set_selection',ordering:'set_order',position:'place_points'};
      if(!obs.completeness.complete||!tasks.length)throw new Fault('QUESTION_INCOMPLETE','Cannot execute an incomplete plan.');
      if(failed&&(tasks.length!==1||tasks[0].slot_key!==failed.slot_key||tasks[0].task_id!==failed.task_id||JSON.stringify(tasks[0].depends_on||[])!==JSON.stringify(failed.depends_on||[])))throw new Fault('GUARD_REJECTED','Repair widened its scope.');
      if(!failed&&(tasks.length!==obs.slots.length||new Set(tasks.map(t=>t.slot_key)).size!==obs.slots.length))throw new Fault('QUESTION_INCOMPLETE','Plan does not cover every answer slot.');
      for(const t of tasks){const s=this.slot(obs,t.slot_key);if(allowed[s.kind]!==t.operation)throw new Fault('GUARD_REJECTED','Task operation does not match the slot.');}
      const remaining=new Set(tasks.map(t=>t.task_id)),ordered=[];while(remaining.size){const t=tasks.find(t=>remaining.has(t.task_id)&&(t.depends_on||[]).every(id=>ordered.some(x=>x.task_id===id)||(failed?.depends_on||[]).includes(id)));if(!t)throw new Fault('GUARD_REJECTED','Dependency cycle or unknown task.');ordered.push(t);remaining.delete(t.task_id)}return ordered;
    }
    async inspectRequest(response,obs){
      const r=this.current.recovery;if(++r.inspections>LIMITS.inspections)throw new Fault('BUDGET_EXHAUSTED','Missing-information rounds exhausted.');await this.persist();
      const req=response.inspection,evidence=[];
      // Model-authored read-only page script (the "Ran page script" reach). Run
      // it in the page through the debugger, size- and time-bounded; the result
      // is untrusted evidence for the next plan, never an action. If it mutated
      // the answer surface, the question/document guard on the re-observe below
      // catches it.
      if(req.script){
        await this.guard();await this.event('INSPECT','Running the read-only page script the model requested',{script:req.script.slice(0,200)});
        const out=await AssignmentVisual.evaluate(this.tabId,req.script);
        evidence.push(out.ok?{operation:'script',script:req.script.slice(0,400),result:out.value}:{operation:'script',script:req.script.slice(0,400),error:out.detail});
      }
      if(req.requests?.length){
        const slot=obs.slots.find(s=>s.slot_key===req.slot_key);
        if(!slot)throw new Fault('TARGET_MISSING','A packaged inspection needs a specific offered slot.');
        for(const op of req.requests){if(!['inspect_frame','inspect_slot','inspect_options','read_control_state','measure_target','inspect_svg_geometry','inspect_scroll_container'].includes(op))throw new Fault('GUARD_REJECTED','Unknown inspection.');
          if(op==='inspect_options'&&slot.kind==='selection'&&!slot.native&&!slot.frame.menus.some(m=>m.owner===slot.local_slot)){await this.click(slot.frame,slot.representations?.[0]||slot.target);await sleep(150);}
          const fresh=await this.observe(),s=this.slot(fresh,slot.slot_key);evidence.push({slot_key:s.slot_key,operation:op,result:op==='inspect_options'?s.frame.menus.filter(m=>m.owner===s.local_slot).map(m=>({label:m.label,disabled:m.disabled})):await this.inspect(s.frame,s.target,op)});
        }
      }
      if(!evidence.length)throw new Fault('TARGET_MISSING','The inspection produced no evidence.');
      const serialized=JSON.stringify(evidence);if(this.current.inspectionSignature===serialized)throw new Fault('REPEATED_STATE','Inspection returned no new evidence.');this.current.inspectionSignature=serialized;this.current.evidence=evidence;r.progress();return this.observe();
    }
    async runQuestion(obs){
      let saved=this.ledger.questions[obs.question_key];
      this.current=saved||{key:obs.question_key,document:obs.document_id,completed:{},recovery:new Recovery(),plan:null};
      this.current.recovery=new Recovery(this.current.recovery);this.current.document=obs.document_id;this.current.frameDocuments=obs.frames.map(f=>({frame_id:f.frame_id,document_id:f.document_id}));this.current.enumeration=obs.enumeration;this.ledger.questions[obs.question_key]=this.current;
      await this.event('OBSERVE','Reading question');
      if(!obs.completeness.complete)throw new Fault('QUESTION_INCOMPLETE',obs.completeness.note);
      if(!obs.slots.length)throw new Fault('QUESTION_INCOMPLETE','No answer slots were found; inspect the page before continuing.');
      for(const slot of obs.slots)if(slot.kind==='position'&&!slot.geometry?.calibrated){await this.readVisual(obs,slot);obs=await this.observe();this.slot(obs,slot.slot_key)}
      if(!this.current.plan){let plan=await this.paid(obs);while(plan.kind==='request_inspection'){obs=await this.inspectRequest(plan,obs);plan=await this.paid(obs)}if(plan.kind==='needs_review')throw new Fault('QUESTION_INCOMPLETE',plan.reason);this.validate(plan,obs);this.current.plan=plan;await this.persist()}
      const tasks=this.validate(this.current.plan,obs);let count=0;
      for(let task of tasks){
        // Resume always reads the value, including previously completed tasks.
        let complete=false;
        while(!complete){await this.guard();await this.event('EXECUTE',`Entering ${count+1} of ${tasks.length}`,{slot_key:task.slot_key,task_id:task.task_id,adapter:task.operation,requested_value:task.desired});
          try{const result=await this.execute(task);this.current.completed[task.slot_key]={entry_verified:true,action_executed:!result.skipped,actual:result.s.current,save_state:result.obs.save_state,grade_state:result.obs.grade_state,document_id:result.obs.document_id};this.current.recovery.progress();complete=true;count++;
            await this.event('VERIFY',`${count} of ${tasks.length} answers verified`,{slot_key:task.slot_key,actual:result.s.current,entry_verified:true});this.b.progress(count,tasks.length,Object.keys(this.ledger.questions).length,this.ledger.cost,this.steps);
          }catch(e){if(!(e instanceof Fault))throw e;if(['CANCELLED','TARGET_STALE','BUDGET_EXHAUSTED','GEOMETRY_UNCALIBRATED','FRAME_UNREADABLE'].includes(e.code))throw e;
            const fresh=await this.observe(),s=this.slot(fresh,task.slot_key);let local=false;try{local=this.current.recovery.failure(task,e,{current:s.current,options:s.frame.menus.filter(m=>m.owner===s.local_slot).map(m=>m.label)})}finally{await this.persist()}
            if(local&&['TARGET_MISSING','INPUT_NO_EFFECT','VALUE_MISMATCH','WRONG_MENU_OWNER'].includes(e.code)){await this.event('LOCAL_RECOVERY','Re-observing the failed widget',{failure_code:e.code});continue}
            if(++this.current.recovery.repairs>LIMITS.repairs)throw new Fault('BUDGET_EXHAUSTED','Question repair budget reached.');await this.persist();
            const patch=await this.paid(fresh,task,e);if(patch.kind!=='plan')throw new Fault('QUESTION_INCOMPLETE',patch.reason||'Repair needs more evidence.');this.validate(patch,fresh,task);task=patch.tasks[0];const index=this.current.plan.tasks.findIndex(t=>t.slot_key===task.slot_key);this.current.plan.tasks[index]=task;await this.persist();
          }
        }
        if(count%8===0){await this.event('OBSERVE','Reconciling completed batch');await this.reconcile()}
      }
      await this.reconcile();await this.visualGate();this.current.finished=true;await this.event('FINISH','All observed answers entered and verified by DOM and a confirming screenshot. Save and grade evidence are reported separately.');
    }
    // Second witness. After every answer is confirmed by DOM readback, a
    // screenshot is shown to the model to confirm the entered values are actually
    // visible. A mismatch drops those answers and re-enters them, bounded by
    // LIMITS.verify; graph points are excluded (their own calibrated readback is
    // the witness). No confirming screenshot for a question with no textual
    // answers to see.
    async confirmVisually(obs){
      const expected=this.current.plan.tasks.filter(t=>this.current.completed[t.slot_key]&&plannedValue(t)!=='')
        .map(t=>{const s=this.slot(obs,t.slot_key);return {slot_key:t.slot_key,label:s.label,value:plannedValue(t)}});
      if(!expected.length)return {kind:'verified'};
      const shot=await AssignmentVisual.screenshot(this.tabId),generation=this.generation;
      const observation=this.publicObservation(obs);observation.screenshot=shot.dataUrl;
      const body={run_id:this.id,request_id:crypto.randomUUID(),spend_limit:this.config.spend_limit,model:this.config.model,observation,expected};
      this.ledger.pending_request=body.request_id;await this.persist();
      await this.event('VERIFY','Confirming answers from a screenshot (second witness)',{slot_count:expected.length});
      const data=await this.b.request('verify',body,this.abort.signal);
      if(Number.isFinite(data.cost)){this.ledger.cost+=data.cost;this.ledger.pending_request=null}await this.persist();await this.guard();
      if(generation!==this.generation)throw new Fault('CANCELLED','Discarded late verification.');
      if(!data.response)throw new Fault('VALUE_MISMATCH',data.detail||'Visual verification returned nothing.');
      await this.event('VERIFY','Screenshot verification: '+data.response.kind,{model_calls:1,cost:data.cost,input_tokens:data.input_tokens,output_tokens:data.output_tokens,mismatches:data.response.mismatches});
      return data.response;
    }
    async visualGate(){
      for(let round=0;round<=LIMITS.verify;round++){
        const obs=await this.observe();this.same(obs);
        const result=await this.confirmVisually(obs);
        if(result.kind==='verified'){this.current.recovery.progress();return}
        if(round>=LIMITS.verify)throw new Fault('VALUE_MISMATCH','A screenshot could not confirm these answers after re-entry: '+result.mismatches.join(', ')+'. '+(result.reason||''));
        for(const k of result.mismatches){
          const task=this.current.plan.tasks.find(t=>t.slot_key===k);if(!task)continue;
          delete this.current.completed[k];await this.event('LOCAL_RECOVERY','Screenshot disagreed; re-entering answer',{slot_key:k,failure_code:'VALUE_MISMATCH',detail:result.reason});
          const r=await this.execute(task);this.current.completed[k]={entry_verified:true,action_executed:!r.skipped,actual:r.s.current,save_state:r.obs.save_state,grade_state:r.obs.grade_state,document_id:r.obs.document_id};
        }
      }
    }
    async reconcile(){
      let obs=await this.observe();this.same(obs);
      if(obs.save_state==='pending'){
        const until=Date.now()+LIMITS.navigation;await this.event('VERIFY','Waiting for save');
        do{await sleep(150);obs=await this.observe();this.same(obs);if(obs.save_state!=='pending')break}while(Date.now()<until);
        if(obs.save_state==='pending')throw new Fault('SAVE_TIMEOUT','Page still reports saving.');
      }
      for(const task of this.current.plan.tasks){if(!this.current.completed[task.slot_key])continue;const s=this.slot(obs,task.slot_key);
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
          if(this.config.check_work&&this.current?.finished&&obs.page_state==='answering'){
            const checks=obs.navigation.filter(n=>n.kind==='check'&&!n.disabled),signature=hash(JSON.stringify(this.current.plan));this.current.checks||=[];
            if(checks.length===1&&!this.current.checks.includes(signature)){
              this.current.checks.push(signature);await this.persist();await this.event('VERIFY','Checking work once for this answer plan.');await this.click(checks[0].frame,checks[0].target);
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
              this.ledger.submission_sent=true;await this.persist();await this.event('FINISH','Submitting the enumerated, verified assignment.');await this.click(buttons[0].frame,buttons[0].target);
              const until=Date.now()+LIMITS.navigation;let confirmed=false;do{await sleep(150);const p=await this.observe();if(p.page_state==='complete'){confirmed=true;await this.event('FINISH','Assignment submission confirmed by the page.',{save_state:p.save_state,grade_state:p.grade_state});break}}while(Date.now()<until);
              if(!confirmed)throw new Fault('SAVE_TIMEOUT','Submission was sent but not confirmed. Do not repeat it without reviewing the page.');this.ledger.status='completed';break;
            }
            if(next.length>1)throw new Fault('TARGET_AMBIGUOUS','More than one Next control.');this.ledger.status='finished';await this.event('FINISH','Observed question complete. No unique next-question control found.');break;
          }
          const signature=obs.question_key+':'+next[0].target;if(navigationStates.has(signature))throw new Fault('REPEATED_STATE','Navigation returned to the same question.');navigationStates.add(signature);
          await this.event('ADVANCE','Moving to the next question');await this.click(next[0].frame,next[0].target);
          const until=Date.now()+LIMITS.navigation;let changed=false;do{await sleep(150);const p=await this.observe();if(p.question_key!==obs.question_key||p.page_state==='complete'){changed=true;break}}while(Date.now()<until);if(!changed)throw new Fault('INPUT_NO_EFFECT','Next did not reach a different question.');
        }
      }catch(e){this.ledger.status=this.cancelled||this.b.stopped()?'cancelled':'needs_review';await this.event(this.ledger.status==='cancelled'?'CANCELLED':'NEEDS_REVIEW',e.message,{failure_code:e.code||'FAILED'});}
      finally{this.busy=false;await this.persist()}
      return this.ledger;
    }
  }
  globalThis.AssignmentPlanner={Engine,Recovery,Fault,LIMITS,visualGeometry};
})();
