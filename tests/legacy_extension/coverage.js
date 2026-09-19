/* Pure progress policy, shared by the worker and browser regression tests.
   Model output proposes a plan. Only observations can verify its completion. */
(() => {
  const normalize = value => String(value || '').normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim();
  // Roles a planned part may point at. `button` is here because many courseware
  // multiple-choice options are styled buttons, not native radios; without it a
  // correct click could never be verified and the question could never advance.
  const ANSWER_ROLES = ['textbox','select','radio','checkbox','option','switch','combobox','spinbutton'];
  const answerTarget = e => ((ANSWER_ROLES.includes(e.role) || e.dropdown || e.opaque || e.role==='graph' || e.role==='point' || (e.role==='button' && e.choice)) && !e.control) || e.drag==='target';
  function questionId(text, hint='') {
    const stem = normalize(hint || text).replace(/\bpart\s+[a-z0-9]+\s*[:.)-]?/g, '').trim();
    let hash = 2166136261;
    for (const ch of stem) hash = Math.imul(hash ^ ch.charCodeAt(0), 16777619);
    return (hash >>> 0).toString(16);
  }
  class Coverage {
    constructor() { this.questions = new Map(); this.current = null; this.history = []; }
    read(action, page) {
      this.revised = [];
      // The page's own question id, taken from the container of the controls
      // this plan points at -- not the first one on the page, which on a
      // multi-question page made every read hash to the same question.
      const qids = [...new Set((action.parts || []).map(p => page.elements.find(e => e.ref === p.ref)?.qid).filter(Boolean))];
      const hint = qids.length === 1 ? qids[0] : (qids.length ? '' : page.question_hint);
      const id = questionId(action.question, hint);
      let fresh = !this.questions.has(id);
      // A changed Part tab is not a new question. Keep the ledger while any
      // previously seen tabs still occur, even if the model rephrases the stem.
      if (this.current && page.part_tabs?.some(t => this.current.tabs.has(t.key))) fresh = false;
      // Nor is a rephrased stem. The answer controls are the question's real
      // identity -- but only the controls with work still on them. A page that
      // reuses one input for every question (MathPapa does) must not fold the
      // next question into a finished one: that adopted the old part, tripped
      // the plan-change guard and killed the run. And when the page names its
      // questions (data-question-id), a different name is a different question
      // whatever the controls say.
      // The answer controls are a question's real identity, not its wording. A
      // control this run already owns belongs to the question that owns it,
      // whichever question the model's rephrased stem hashed to. This is what
      // stops a rephrased re-read of a big table splitting it into twins.
      const incoming = (action.parts || []).map(p => ({key: page.elements.find(e => e.ref === p.ref)?.key, answer: normalize(p.answer)})).filter(p => p.key);
      const onScreen = new Set(page.elements.map(e => e.key));
      let host = null;
      if (incoming.length) {
        // Prefer a question that already owns one of these controls, unless the
        // page NAMES its questions and names a different one, or the re-read
        // gives an owned control a genuinely different answer (the input reused
        // for the next question). Otherwise fall back to the id hash.
        for (const q of this.questions.values()) {
          if (hint && q.hint && hint !== q.hint) continue;
          if (q.attempt?.locked) continue;                   // a graded, locked question never adopts new work
          const shares = incoming.some(i => [...q.parts.values()].some(pt => pt.target_key === i.key && !pt.retired
            && (!pt.verified || i.answer === normalize(pt.answer) || i.answer.includes(normalize(pt.answer)) || normalize(pt.answer).includes(i.answer))));
          if (shares) { host = q; break; }
        }
      } else if (this.current && this.current.parts.size) {
        // A plan-less re-read stays on the current question while its unfinished
        // controls are still on screen.
        const owned = [...this.current.parts.values()].filter(p => !p.verified).map(p => p.target_key).filter(Boolean);
        if (owned.length && owned.every(k => onScreen.has(k))) host = this.current;
      }
      if (host) fresh = false;
      let q = host || (fresh ? {id, text:action.question, hint, plan:action.plan || '', parts:new Map(), tabs:new Map(), steps:0, submitted:false} :
        (this.questions.get(id) || this.current));
      fresh = !this.questions.has(q.id) && q !== this.current;
      if (fresh || host) this.questions.set(q.id, q);
      this.current = q;
      // Every control on screen when the plan was FIRST made, and never widened:
      // a later re-read may be a mechanical recheck that echoes the old parts,
      // so it must not quietly count a newly revealed checkbox as "decided".
      // A control that appears after planning is covered only by an explicit
      // part naming it; otherwise hand-in refuses by name and the student decides.
      // "First made" means the first read whose parts bind to at least one real
      // answer control (or the first adopted answer). A plan-less read, or one
      // whose refs point at nothing usable, has decided nothing yet.
      if (action.plan && !q.plan) q.plan = action.plan;
      for (let incoming of action.parts || []) {
        let target = page.elements.find(e => e.ref === incoming.ref && (answerTarget(e)||incoming.kind==='ordering'||incoming.order?.length||incoming.sequence?.length>=2));
        // A menu option is not where an answer lives; the cell that owns the
        // menu is. A plan that points at the option is re-aimed at its cell.
        if (target?.role === 'option' && target.owner_ref) {
          const cell = page.elements.find(e => e.ref === target.owner_ref);
          if (cell) { if (!incoming.answer) incoming = {...incoming, answer: target.name}; target = cell; }
        }
        // One cell, one part. A re-read that gives an owned cell a new id is
        // talking about the existing part; adopt its id so the ledger does not
        // grow twins that both track the same control.
        // -- except a graph: several points legitimately share one surface.
        const owner = target && target.role !== 'graph' && !q.parts.has(incoming.id)
          ? [...q.parts.values()].find(p => p.target_key === target.key) : null;
        if (owner) incoming = {...incoming, id: owner.id};
        const prev = q.parts.get(incoming.id);
        if (prev && prev.answer !== '' && normalize(prev.answer) !== normalize(incoming.answer)) {
          // This guard exists to catch a model re-deriving a different answer.
          // Sharpening an answer it has not entered yet to the label the page
          // actually offers -- "Equity" becoming "Stockholders' Equity" once
          // the menu is open -- is not that, and stopping there killed a run
          // that had planned all twenty cells correctly. One answer containing
          // the other, before entry, is a refinement and is kept.
          // Nothing has been entered yet: the model is still deciding what the
          // answer is. Changing its mind then is re-planning, not oscillation,
          // and a model reasoning its way from a bad first guess to a right one
          // must be allowed to. The oscillation guard is on ENTERED answers.
          if (!prev.entered && !prev.everEntered) {
            prev.answer = incoming.answer;
          } else if ((prev.revisions || 0) >= 1 && !q.retryable) {
            // It has been entered, then changed, and is being changed again:
            // the flip-flop this guard exists for. Stop.
            throw new Error(`Plan changed again for ${prev.what}: "${prev.answer}" to "${incoming.answer}". Stop and review before replacing a committed answer.`);
          } else {
            // Entered once, now revised: take it, undo the part's progress so
            // it is re-entered and re-verified, and say so loudly.
            this.revised.push(`${prev.what}: "${prev.answer}" -> "${incoming.answer}"`);
            prev.answer=incoming.answer; prev.revisions=(prev.revisions||0)+1;
            prev.entered=false; prev.verified=false; prev.visualConfirmed=false; prev.domVerified=undefined; prev.evidence=null;
            prev.target_key='';                                   // a revised answer may live in a different control
          }
        }
        const part = prev || {...incoming, entered:false, verified:false, target_key:'', evidence:null};
        if(incoming.kind!=='ordering'&&(incoming.order?.length||(incoming.sequence?.length>=2&&target&&!answerTarget(target))))incoming={...incoming,kind:'ordering'};
        if(incoming.kind==='ordering'){
          const keys=(incoming.order||[]).map(ref=>page.elements.find(e=>e.ref===ref)?.key);
          if(keys.some(k=>!k))throw new Error('Ordering plan contains an unavailable item. Re-observe.');
          if(prev?.order_keys?.length && JSON.stringify(prev.order_keys)!==JSON.stringify(keys))throw new Error('The committed ordering sequence changed. Stop and review.');
          part.kind='ordering';part.order_keys=keys;part.sequence=incoming.sequence||[];
        }
        if (prev && prev.answer === '' && !prev.entered) { part.answer=incoming.answer; part.what=incoming.what; }
        if (target && (!part.target_key || !page.elements.some(e=>e.key===part.target_key))) {
          part.target_key=target.key; part.verified=false; part.evidence=null;
        }
        const source=page.elements.find(e=>e.ref===incoming.source_ref && e.drag==='source');
        if(source){
          if(part.source_key && part.source_key!==source.key && page.elements.some(e=>e.key===part.source_key))
            throw new Error('The planned drag source changed for '+part.what+'. Review the pairing.');
          part.source_key=source.key;part.source_label=source.name;
        }
        q.parts.set(incoming.id, part);
      }
      if (!q.seen && [...q.parts.values()].some(p => p.target_key)) q.seen = new Set(page.elements.map(e => e.key));
      this.observe(page);
      return fresh;
    }
    observe(page) {
      const q = this.current; if (!q) return;
      for (const tab of page.part_tabs || []) {
        const prior=q.tabs.get(tab.key);
        q.tabs.set(tab.key,{...tab,visited:!!(prior?.visited || tab.checked)});
      }
    }
    partFor(action, page) {
      const target=page.elements.find(e=>e.ref===(action.action==='drag'?action.to:action.ref));
      if (!target || !this.current) return null;
      const part=action.part_id ? this.current.parts.get(action.part_id) : [...this.current.parts.values()].find(p=>p.target_key===target.key);
      if (!part) return null;
      // Rebinding requires a fresh read_check, never a blind action to another box.
      if (part.target_key && part.target_key!==target.key) return null;
      if(action.action==='drag' && (!part.source_key || page.elements.find(e=>e.ref===action.ref)?.key!==part.source_key)) return null;
      return {part,target};
    }
    bind(action,page) {
      const found=this.partFor(action,page); if(!found)return null;
      const {part,target}=found;
      part.target_key=target.key;
      return {part,target};
    }
    // The model answered a question it never planned parts for. Refusing that
    // outright killed every plain multiple-choice run on a model that skipped
    // the checklist. Instead the answer it is giving becomes the plan: one part,
    // bound to the control it chose, verified the same way as a declared one.
    // Only for an unplanned question -- a planned one still has to name its part.
    adopt(action,page) {
      const q=this.current; if(!q || q.parts.size) return null;
      const target=page.elements.find(e=>e.ref===(action.action==='drag'?action.to:action.ref));
      if(!target || !answerTarget(target)) return null;
      const source=action.action==='drag'?page.elements.find(e=>e.ref===action.ref&&e.drag==='source'):null;
      if(action.action==='drag' && !source) return null;
      const answer=action.text || action.option || source?.name || target.name || '';
      const part={id:'answer',what:(target.name||target.blank||'the answer').slice(0,120),answer,
        entered:false,verified:false,target_key:target.key,evidence:null,adopted:true};
      if(source){part.source_key=source.key;part.source_label=source.name;}
      q.parts.set(part.id,part);
      if(!q.seen) q.seen=new Set(page.elements.map(e=>e.key));   // the adopted answer is the plan
      return {part,target};
    }
    record(action,page,outcome) {
      const found=this.bind(action,page);
      if (!found || !outcome.ok) return;
      const {part,target}=found;
      part.entered=true; part.everEntered=true; part.verified=false;
      part.evidence={key:target.key,answer:part.source_label||part.answer,kind:action.action};
    }
    summary() {
      const parts=[...(this.current?.parts.values() || [])];
      const remaining=parts.filter(p=>!p.verified&&!p.retired).map(p=>p.what);
      const retired=parts.filter(p=>p.retired).length;
      return `${parts.filter(p=>p.verified).length} of ${parts.length} parts done`+
        (remaining.length?'; remaining: '+remaining.join(', '):'')+
        (retired?`; ${retired} retired by graded feedback`:'')+
        (this.current?.attempt?`; graded ${this.current.attempt.outcome}`:'');
    }
    // The page graded this attempt and will not take more input. Record the
    // outcome, stop owing the unfinished parts, and never call them correct.
    retire(outcome, feedback) {
      const q=this.current; if(!q) return [];
      q.attempt={outcome,feedback:(feedback||'').slice(0,120),locked:true};
      const retired=[];
      for(const p of q.parts.values()) if(!p.verified){p.retired=true;retired.push(p.what);}
      return retired;
    }
    // Editable feedback: the page allows another try, so a revised answer is a
    // new attempt rather than the model changing its mind.
    allowRetry(feedback){const q=this.current;if(!q)return;q.retryable=true;q.attempt={outcome:'incorrect',feedback:(feedback||'').slice(0,120),locked:false};for(const p of q.parts.values())p.revisions=0;}
    ledger() { return [...(this.current?.parts.values() || [])].map(({id,what,answer,entered,verified,target_key,source_key='',source_label='',kind='value',sequence=[],retired=false})=>({id,what,answer,entered,verified,retired,target_key,source_key,source_label,kind,sequence})); }
    // A bounded retry allowance per question, not a ceiling on healthy work:
    // enough for every part plus discovery, opening menus and corrections.
    budget() {return Math.min(240,10+8*(this.current?.parts.size || 1));}
    // scope 'nav' (default): what still blocks moving on -- a locked question is
    // done. scope 'submit': what blocks handing in the whole assignment -- a
    // locked question whose parts were retired without being verified (wrong or
    // unfinished) still counts, because you must not hand in an incomplete or
    // incorrect assignment. `all=false` limits to the current question.
    outstanding(all=true, scope='nav') {
      const questions=all?[...this.questions.values()]:[this.current].filter(Boolean);
      if(!questions.length)return ['No question has been planned'];
      const missing=[];
      for(const q of questions){
        if(q.attempt?.locked){
          if(scope==='submit'){
            const unmet=[...q.parts.values()].filter(p=>!p.verified);
            if(unmet.length)missing.push(...unmet.map(p=>p.what+' ('+(q.attempt.outcome||'graded')+', not verified)'));
          }
          continue;
        }
        if(!q.parts.size)missing.push('No parts planned for '+q.text);
        missing.push(...[...q.parts.values()].filter(p=>!p.verified&&!p.retired).map(p=>p.what));
        missing.push(...[...q.tabs.values()].filter(t=>!t.visited).map(t=>t.name+' has not been inspected'));
      }
      return missing;
    }
    gate(action,page,config) {
      const target=page.elements.find(e=>e.ref===action.ref);
      const activating=action.action==='click'||(action.action==='press'&&['Enter','Space'].includes(action.key));
      if(!activating||!target)return '';
      if(target.control==='terminal') {
        if(!config.auto_submit)return 'Hand-in is switched off.';
        const remaining=this.outstanding(true,'submit');
        if(remaining.length)return 'Cannot hand in; outstanding: '+remaining.join(', ');
        // Every control the extension would treat as an answer has to be
        // accounted for before hand-in, not only text boxes. Siblings of a
        // bound answer are covered in two different ways:
        //  - radios and single-choice buttons: picking one decides them all.
        //  - checkboxes and switches: independent, so an unticked one is only a
        //    decision if it was on screen when the plan was made (`seen`). One
        //    that appeared afterwards was never decided and blocks hand-in.
        const bound=new Set([...this.questions.values()].flatMap(q=>[...q.parts.values()].map(p=>p.target_key)));
        const boundGroups=new Set(page.elements.filter(e=>bound.has(e.key)&&e.group!=null).map(e=>e.group));
        const seenAtPlan=new Set([...this.questions.values()].flatMap(q=>[...(q.seen||[])]));
        const exclusive=e=>e.role==='radio'||e.role==='option'||(e.role==='button'&&e.choice);
        const independent=e=>e.role==='checkbox'||e.role==='switch';
        const covered=e=>e.group!=null && boundGroups.has(e.group) && (exclusive(e) || (independent(e) && seenAtPlan.has(e.key)));
        const orderMembers=new Set([...this.questions.values()].flatMap(q=>[...q.parts.values()].filter(p=>p.kind==='ordering'&&p.verified).flatMap(p=>p.order_keys||[])));
        // A graph is NOT exempt from the unplanned-answer check: a canvas graph
        // has no separate point elements, so an unplanned one would otherwise let
        // auto hand-in submit with the graph blank. A graph that is a planned part
        // is in `bound` (and, if unverified, already blocks via outstanding()).
        const unplanned=page.elements.filter(e=>!e.disabled && answerTarget(e) && !bound.has(e.key) && !orderMembers.has(e.key) && !covered(e));
        if(unplanned.length)return 'Cannot hand in; unplanned answer controls: '+unplanned.map(e=>e.name||e.blank||e.key).join(', ');
        const blockers=(page.warnings||[]).filter(w=>!w.startsWith('Some custom elements expose no open shadow root'));
        if(blockers.length)return 'Cannot hand in while observation limitations remain: '+blockers.join('; ');
        return '';
      }
      if(target.control==='advance') {
        const remaining=this.outstanding(false);
        if(remaining.length)return 'Complete the current question before advancing: '+remaining.join(', ');
        if(!config.advance)return 'All parts entered. Continuing is switched off.';
      }
      return '';
    }
    oscillation(action,page) {
      if(!['fill','select','click','drag','press'].includes(action.action))return '';
      const target=page.elements.find(e=>e.ref===(action.to || action.ref));
      if(!target)return '';
      // Use stable identities, not ephemeral refs. Radios in one group are one
      // answer target, so A/B/A/B is visible even though each changes the DOM.
      const group=page.elements.find(e=>e.ref===target.group);
      const key=target.role==='radio' ? (group?.key || target.key) : target.key;
      const source=page.elements.find(e=>e.ref===action.ref);
      const value=action.text || action.option || (action.action==='drag'?source?.name:'') || target.name || action.key;
      const signature=action.action+':'+key+':'+normalize(value);
      this.history.push({key,value,signature});this.history=this.history.slice(-8);
      if(this.history.filter(h=>h.signature===signature).length>=4)return 'Repeated the same action four times on '+target.name+'. Stopped.';
      const writes=this.history.filter(h=>h.key===key).slice(-4);
      if(writes.length===4 && normalize(writes[0].value)!==normalize(writes[1].value) && normalize(writes[0].value)===normalize(writes[2].value) && normalize(writes[1].value)===normalize(writes[3].value))
        return `Stopped answer oscillation between "${writes[0].value}" and "${writes[1].value}".`;
      return '';
    }
  }
  globalThis.AssignmentCoverage={Coverage,questionId};
})();
