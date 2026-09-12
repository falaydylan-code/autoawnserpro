/* Pure progress policy, shared by the worker and browser regression tests.
   Model output proposes a plan. Only observations can verify its completion. */
(() => {
  const normalize = value => String(value || '').normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim();
  function questionId(text, hint='') {
    const stem = normalize(hint || text).replace(/\bpart\s+[a-z0-9]+\s*[:.)-]?/g, '').trim();
    let hash = 2166136261;
    for (const ch of stem) hash = Math.imul(hash ^ ch.charCodeAt(0), 16777619);
    return (hash >>> 0).toString(16);
  }
  class Coverage {
    constructor() { this.questions = new Map(); this.current = null; this.history = []; }
    read(action, page) {
      const id = questionId(action.question, page.question_hint);
      let fresh = !this.questions.has(id);
      // A changed Part tab is not a new question. Keep the ledger while any
      // previously seen tabs still occur, even if the model rephrases the stem.
      if (this.current && page.part_tabs?.some(t => this.current.tabs.has(t.key))) fresh = false;
      let q = fresh ? {id, text:action.question, plan:action.plan || '', parts:new Map(), tabs:new Map(), steps:0, submitted:false} :
        (this.questions.get(id) || this.current);
      if (fresh) this.questions.set(id, q);
      this.current = q;
      if (action.plan && !q.plan) q.plan = action.plan;
      for (const incoming of action.parts || []) {
        const target = page.elements.find(e => e.ref === incoming.ref &&
          (['textbox','select','radio','checkbox','option','switch','combobox','spinbutton'].includes(e.role) || e.drag==='target'));
        const prev = q.parts.get(incoming.id);
        if (prev && prev.answer !== '' && normalize(prev.answer) !== normalize(incoming.answer)) {
          throw new Error(`Plan changed for ${prev.what}: "${prev.answer}" to "${incoming.answer}". Stop and review before replacing a committed answer.`);
        }
        const part = prev || {...incoming, entered:false, verified:false, target_key:'', evidence:null};
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
    record(action,page,outcome) {
      const found=this.bind(action,page);
      if (!found || !outcome.ok) return;
      const {part,target}=found;
      part.entered=true; part.verified=false;
      part.evidence={key:target.key,answer:part.source_label||part.answer,kind:action.action};
    }
    summary() {
      const parts=[...(this.current?.parts.values() || [])];
      const remaining=parts.filter(p=>!p.verified).map(p=>p.what);
      return `${parts.filter(p=>p.verified).length} of ${parts.length} parts done`+
        (remaining.length?'; remaining: '+remaining.join(', '):'');
    }
    ledger() { return [...(this.current?.parts.values() || [])].map(({id,what,answer,entered,verified,target_key,source_key='',source_label=''})=>({id,what,answer,entered,verified,target_key,source_key,source_label})); }
    budget() {return Math.min(100,6+4*(this.current?.parts.size || 1));}
    outstanding(all=true) {
      const questions=all?[...this.questions.values()]:[this.current].filter(Boolean);
      if(!questions.length)return ['No question has been planned'];
      const missing=[];
      for(const q of questions){
        if(!q.parts.size)missing.push('No parts planned for '+q.text);
        missing.push(...[...q.parts.values()].filter(p=>!p.verified).map(p=>p.what));
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
        const remaining=this.outstanding();
        if(remaining.length)return 'Cannot hand in; outstanding: '+remaining.join(', ');
        const bound=new Set([...this.questions.values()].flatMap(q=>[...q.parts.values()].map(p=>p.target_key)));
        const unplanned=page.elements.filter(e=>!e.disabled && (e.role==='textbox'||e.role==='select'||e.drag==='target') && !bound.has(e.key));
        if(unplanned.length)return 'Cannot hand in; unplanned answer controls: '+unplanned.map(e=>e.name||e.blank||e.key).join(', ');
        if(page.warnings?.length)return 'Cannot hand in while observation limitations remain: '+page.warnings.join('; ');
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
