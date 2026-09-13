/* Observation and bounded DOM actions. No model credentials or strategy here. */
(() => {
  const VERSION = '0.7.2';
  if (window.__assignmentLabContent === VERSION) return;
  window.__assignmentLabContent = VERSION;
  let refs = new Map(), previousKeys = new Set(), cancelled = false;
  const nodeKeys = new WeakMap();
  let keySerial = 0;
  const epoch = Math.random().toString(36).slice(2, 9);
  const SOURCES = '[draggable=true],[aria-grabbed],[data-rbd-draggable-id],[data-dnd-kit-id],.ui-draggable';
  const TARGETS = '[data-rbd-droppable-id],.ui-droppable,[aria-dropeffect]';
  const DROPDOWNS = '[aria-haspopup=listbox],[role=combobox],td.dropDownList,td[dropdowntype],td.responseCell[tabindex]';
  const LISTS = '[data-rbd-droppable-id],[data-sortable],ol,[role=list],[role=listbox]';
  const GROUPS = 'fieldset,table,[role=group],[role=radiogroup],[role=grid],[role=listbox],[role=tablist],[role=tabpanel],[data-question-id],main,section,form';
  const INTERACTIVE = ['input','textarea','select','button','a[href]','[contenteditable]',
    '[role=button]','[role=radio]','[role=checkbox]','[role=textbox]','[role=combobox]',
    '[role=link]','[role=gridcell]','[role=cell]','[role=option]','[role=listbox]',
    '[role=tab]','[role=switch]','[role=spinbutton]','[role=slider]','[tabindex]:not([tabindex="-1"])','[aria-haspopup]',DROPDOWNS,LISTS,SOURCES,TARGETS].join(',');
  const FORBIDDEN_INPUT_TYPES = new Set(['password','hidden','file','image']);
  const SENSITIVE_HINT = /pass|card|cvv|cvc|ssn|social.?security|credit|iban|routing|account.?number/i;
  const HANDS_IN = /\b(?:submit\s+(?:the\s+)?(?:assignment|quiz|test|exam|work|attempt)|exit\s+assignment|finish\s+(?:assignment|attempt|quiz|test|exam)|hand\s+in|turn\s+in)\b/i;
  const TERMINAL_EXACT = /^(?:submit|submit\s+all(?:\s+answers)?|finish|finish\s+and\s+submit|submit\s+and\s+finish|hand\s+in|turn\s+in|end\s+(?:quiz|test|exam|assignment))$/i;
  const KEYS = new Set(['Enter','Tab','Space','ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Escape','Backspace']);
  // Destructive, account, consent and download controls. Refused in the page for
  // click and Enter/Space, the same way hand-in is, so a page instruction the
  // model repeats cannot reach them. Kept to whole words so "Delete" is caught
  // but "Deleted items report" as a question option is not.
  const REFUSED = /^(?:delete|remove|discard|clear(?:\s+all)?|reset|sign\s*out|log\s*out|logout|sign\s*in|log\s*in|login|register|create\s+account|accept(?:\s+all)?|agree|i\s+agree|allow(?:\s+all)?|consent|download|export|unenroll|drop\s+course|withdraw|purchase|buy|pay(?:\s+now)?|checkout)\b.*$/i;
  const clean = s => String(s || '').replace(/\s+/g,' ').trim();
  const parent = el => el.parentElement || el.getRootNode()?.host || null;
  function closest(el, selector) { for(let n=el;n;n=parent(n)) if(n.matches?.(selector)) return n; return null; }
  function owned(el) { return !!closest(el,'#__assignment_lab_cursor,#__assignment_lab_badges'); }
  function all(root=document) {
    const found=[];
    for(const el of root.querySelectorAll('*')) {
      if(owned(el)) continue;
      found.push(el);
      if(el.shadowRoot) found.push(...all(el.shadowRoot));
    }
    return found;
  }
  function key(el) {
    if(!nodeKeys.has(el)) {
      const root=el.getRootNode();
      const prefix=root.host ? key(root.host)+'/' : epoch+'/';
      const unique=el.id && root.querySelectorAll('[id]').length < 20000 && [...root.querySelectorAll('[id]')].filter(n=>n.id===el.id).length===1;
      nodeKeys.set(el, prefix+(unique ? '#'+el.id : 'n'+(++keySerial)));
    }
    return nodeKeys.get(el);
  }
  function visible(el) {
    if(!el.isConnected) return false;
    const rect=el.getBoundingClientRect();
    if(rect.width<2 || rect.height<2) return false;
    for(let n=el;n;n=parent(n)) {
      const s=getComputedStyle(n);
      if(n.hidden || s.visibility==='hidden' || s.display==='none' || Number(s.opacity)<0.05) return false;
    }
    return true;
  }
  function sensitive(el) {
    if(el.tagName==='INPUT' && FORBIDDEN_INPUT_TYPES.has(el.type)) return true;
    return SENSITIVE_HINT.test([el.name,el.id,el.getAttribute('autocomplete'),el.getAttribute('aria-label'),el.placeholder].filter(Boolean).join(' '));
  }
  function editable(el) {return el.tagName==='TEXTAREA' || el.isContentEditable || (el.tagName==='INPUT' && ['text','number','search','tel','url','email'].includes(el.type));}
  function text(el) {return clean(el?.innerText || el?.textContent);}
  function accessibleName(el) {
    const root=el.getRootNode();
    const ids=(el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    const labelled=ids.map(id=>text(root.getElementById?.(id))).join(' ').trim();
    return labelled || clean(el.getAttribute('aria-label')) || text(el.labels?.[0]) ||
      (editable(el) ? clean(el.placeholder || el.title) : text(el)) || text(el.querySelector?.(':scope > legend,:scope > caption')) || '';
  }
  function role(el) {
    if(el.getAttribute('role')) return el.getAttribute('role');
    if(el.localName.includes('-')&&!el.shadowRoot) return 'widget';
    if(editable(el)) return 'textbox';
    if(el.tagName==='INPUT') return el.type;
    if(el.tagName==='A') return 'link';
    return el.tagName.toLowerCase();
  }
  function external(el) {
    if(el.tagName!=='A'||!el.getAttribute('href'))return false;
    try{const url=new URL(el.href,location.href);return /^https?:$/.test(url.protocol)&&url.origin!==location.origin;}catch{return false;}
  }
  // A styled multiple-choice option, as opposed to a Check or Next button: it
  // carries a pressed/selected state, or it stands among sibling buttons inside
  // a group. Without this a click on an option could never be tied to the plan.
  function isChoice(el) {
    if(role(el)!=='button'||classification(el))return false;
    if(['aria-pressed','aria-checked','aria-selected'].some(a=>el.hasAttribute(a)))return true;
    const group=closest(el,'[role=group],[role=radiogroup],[role=listbox]');
    return !!group&&[...group.querySelectorAll('button,[role=button]')].filter(b=>!classification(b)).length>=2;
  }
  function classification(el) {
    const name=accessibleName(el);
    if(TERMINAL_EXACT.test(name)||HANDS_IN.test(name)) return 'terminal';
    if(REFUSED.test(name)) return 'refused';
    if(el.getAttribute('role')==='tab' || /^part\s*[a-z0-9]+$/i.test(name)) return 'part';
    if(/^submit answer$/i.test(name) && closest(el,'fieldset,main,form')?.querySelector('[role=tab]')) return 'part';
    if(/^(?:next(?: question)?|continue|proceed|submit answer|high|medium|low)$/i.test(name)) return 'advance';
    return '';
  }
  function endsTheAssignment(el) {return classification(el)==='terminal';}
  function tableContext(el) {
    const cell=closest(el,'td,th'), table=cell && closest(cell,'table');
    if(!table) return {row:'',column:''};
    const rows=[...table.rows], grid=[];
    let at=null;
    rows.forEach((r,ri)=>{grid[ri] ||= [];let ci=0;for(const c of r.cells){
      while(grid[ri][ci])ci++;
      const rs=c.rowSpan || rows.length-ri;
      for(let dy=0;dy<rs;dy++){grid[ri+dy] ||= [];for(let dx=0;dx<c.colSpan;dx++)grid[ri+dy][ci+dx]=c;}
      if(c===cell)at=[ri,ci];ci+=c.colSpan;
    }});
    if(!at) return {row:'',column:''};
    const [ri,ci]=at, r=rows[ri];
    const row=text([...r.cells].find(c=>c!==cell && c.getAttribute('scope')==='row') || [...r.cells].find(c=>c!==cell&&text(c)));
    let headings=[];
    for(let i=0;i<ri;i++) {const h=grid[i]?.[ci];if(h?.tagName==='TH' && h.getAttribute('scope')!=='row' && text(h)) headings.push(text(h));}
    const explicit=(cell.getAttribute('headers')||'').split(/\s+/).map(id=>table.getRootNode().getElementById?.(id)).filter(Boolean);
    if(explicit.length) headings=explicit.filter(h=>h.scope!=='row'&&!h.classList.contains('rowHeader')).map(text);
    return {row:row.slice(0,300),column:[...new Set(headings)].join(' / ').slice(0,300)};
  }
  function blankContext(el) {
    if(!editable(el)) return {context:'',blank:''};
    let container=closest(parent(el),'p,td,li,[role=tabpanel],fieldset,section,main') || parent(el);
    if(!container) return {context:'',blank:''};
    const fields=all(container).filter(n=>editable(n)&&visible(n)&&!sensitive(n));
    const index=fields.indexOf(el); if(index<0)return {context:'',blank:''};
    function walk(n) {
      if(n.nodeType===Node.TEXT_NODE) return n.textContent;
      if(n.nodeType!==Node.ELEMENT_NODE || owned(n))return '';
      const i=fields.indexOf(n);if(i>=0)return `[blank ${i+1}]`;
      if(['SCRIPT','STYLE'].includes(n.tagName))return '';
      return [...(n.shadowRoot || n).childNodes].map(walk).join('');
    }
    return {blank:`blank ${index+1} of ${fields.length}`,context:clean(walk(container)).slice(0,1000)};
  }
  function fieldContext(el) {return blankContext(el).context;}
  function frameOffset() {
    let x=0,y=0,win=window,exact=true;
    for(let depth=0;win!==win.parent;depth++) {
      if(depth>=10){exact=false;break;}let rect;
      try{rect=win.frameElement?.getBoundingClientRect();}catch{rect=null;}
      if(!rect){exact=false;break;}x+=rect.left;y+=rect.top;win=win.parent;
    }
    return {x:Math.round(x),y:Math.round(y),exact};
  }
  function valueOf(el) {
    if(el.matches(DROPDOWNS)&&el.tagName!=='SELECT')return clean(el.getAttribute('data-value') || el.getAttribute('aria-valuetext') || el.innerText);
    if(el.matches(TARGETS)) return [...el.querySelectorAll(SOURCES)].map(text).join(' | ') || text(el);
    return clean(el.isContentEditable ? el.textContent : el.value);
  }
  function fingerprint() {
    return all().filter(n=>!sensitive(n)&&(n.matches(INTERACTIVE)||n.matches(GROUPS))).map(n=>
      [key(n),parent(n)?key(parent(n)):'',parent(n)?[...parent(n).children].indexOf(n):0,text(n).slice(0,30),valueOf(n),n.checked||n.getAttribute('aria-checked')==='true',n.getAttribute('aria-selected'),visible(n)]);
  }
  function digest() {return JSON.stringify([innerWidth,innerHeight,scrollX,scrollY,visualViewport?.scale,fingerprint()]);}
  function listItems(list) {
    return all().filter(n=>list.contains(n)&&n!==list&&n.matches(SOURCES+',li,[role=listitem]')&&visible(n))
      .filter(n=>!closest(parent(n),SOURCES+',li,[role=listitem]') || !list.contains(closest(parent(n),SOURCES+',li,[role=listitem]')))
      .sort((a,b)=>{const x=a.getBoundingClientRect(),y=b.getBoundingClientRect();return Math.abs(x.top-y.top)>4?x.top-y.top:x.left-y.left;});
  }
  function observe() {
    hideUI();refs=new Map();
    const nodes=all(), warnings=[];
    if(nodes.some(n=>n.localName.includes('-')&&!n.shadowRoot)) warnings.push('Some custom elements expose no open shadow root; closed shadow contents cannot be inspected or reliably detected. Use the screenshot; pause if required controls are missing.');
    // A closed-shadow custom element is an answer candidate only with evidence
    // it is one: it sits inside an answer region (a table cell, form, fieldset,
    // group or question container), not in page chrome, and it is the size of a
    // control rather than a layout shell. Without this every <app-header> and
    // icon element on a component-built site became an "unplanned answer" and
    // blocked hand-in.
    const ANSWER_REGION='td,th,[role=gridcell],[role=cell],fieldset,form,label,[role=group],[role=radiogroup],[data-question-id]';
    const opaque=n=>{
      // Opacity is about what is inside the host, not what is on it: a host that
      // carries tabindex is still a closed box, and still needs a real click.
      if(!(n.localName.includes('-')&&!n.shadowRoot&&!n.querySelector(INTERACTIVE)))return false;
      if(!closest(parent(n),ANSWER_REGION)||closest(n,'header,nav,footer,aside,[role=banner],[role=navigation],[role=contentinfo]'))return false;
      const r=n.getBoundingClientRect();return r.width>=16&&r.height>=10&&r.width<=800&&r.height<=300;
    };
    const interactive=nodes.filter(n=>((n.matches(INTERACTIVE)&&(!n.hasAttribute('contenteditable')||n.isContentEditable||n.matches('input,textarea,button,select,[role]')))||opaque(n))&&visible(n)&&!sensitive(n));
    const selected=new Set(interactive);
    for(const el of interactive) for(let n=parent(el);n;n=parent(n)) if(n.matches(GROUPS))selected.add(n);
    const ordered=nodes.filter(n=>selected.has(n));
    if(ordered.length>400)warnings.push('More than 400 controls/groups: observation truncated; do not submit until all required parts are visible and planned.');
    const chosen=ordered.slice(0,400), local=new Map(chosen.map((n,i)=>[n,i+1]));
    const elements=chosen.map(el=>{
      const ref=local.get(el);refs.set(ref,el);
      let group=parent(el);while(group&&!local.has(group))group=parent(group);
      let depth=0;for(let n=group;n;n=parent(n))if(local.has(n))depth++;
      const rect=el.getBoundingClientRect(), k=key(el);
      const ownerId=closest(el,'[role=listbox]')?.getAttribute('aria-labelledby');
      const menuOwner=ownerId?chosen.find(n=>n.id===ownerId):chosen.find(n=>n!==el&&n.matches(DROPDOWNS)&&clean(n.getAttribute('aria-label'))===clean(el.getAttribute('aria-label'))&&clean(el.getAttribute('aria-label')));
      return {ref,key:k,group:local.get(group)||null,depth:Math.min(depth,20),role:role(el),
        name:accessibleName(el).slice(0,400),...blankContext(el),...tableContext(el),
        dropdown:el.matches(DROPDOWNS),opaque:opaque(el),qid:closest(el,'[data-question-id]')?.getAttribute('data-question-id')||'',
        owner_ref:local.get(menuOwner)||null,
        list_ref:local.get(closest(parent(el),LISTS))||null,
        order_index:closest(parent(el),LISTS)?listItems(closest(parent(el),LISTS)).indexOf(el):null,
        drag:el.matches(SOURCES)?'source':el.matches(TARGETS)?'target':null,
        control:classification(el),external:external(el),choice:isChoice(el),value:valueOf(el).slice(0,1000),
        checked:el.checked===true||['aria-checked','aria-selected','aria-pressed'].some(a=>el.getAttribute(a)==='true'),
        disabled:el.disabled===true||el.getAttribute('aria-disabled')==='true',new:!previousKeys.has(k),
        box:{x:Math.round(rect.x),y:Math.round(rect.y),w:Math.round(rect.width),h:Math.round(rect.height)}};
    });
    previousKeys=new Set(elements.map(e=>e.key));
    const pageText=nodes.filter(n=>n.matches('p,legend,h1,h2,h3,output,[role=status],[role=alert]')&&visible(n)).map(text).join('\n');
    const question=nodes.find(n=>visible(n)&&n.matches('[data-question-id]'));
    return {elements,warnings,text:(pageText+'\n'+(document.body?.innerText||'')).slice(0,20000),host:location.host,title:document.title,
      origin:location.origin,frameOffset:frameOffset(),digest:digest(),fingerprint:JSON.stringify(fingerprint()),
      question_hint:question?question.getAttribute('data-question-id'):'',
      part_tabs:elements.filter(e=>e.role==='tab').map(e=>({key:e.key,name:e.name,checked:e.checked}))};
  }
  let badgeHost=null;
  function badgesOff(){badgeHost?.remove();badgeHost=null;}
  function badges(entries) {
    badgesOff();badgeHost=document.createElement('div');badgeHost.id='__assignment_lab_badges';
    badgeHost.style.cssText='position:fixed;inset:0;pointer-events:none;z-index:2147483646';
    badgeHost.setAttribute('aria-hidden','true');
    for(const entry of entries){const el=refs.get(entry.ref);if(!el||!visible(el))continue;
      const r=el.getBoundingClientRect();if(r.bottom<0||r.top>innerHeight)continue;
      const tag=document.createElement('span');tag.textContent=`[${entry.globalRef}]`;
      tag.style.cssText=`position:fixed;left:${Math.max(0,r.left-5)}px;top:${Math.max(0,r.top-16)}px;font: bold 12px/16px monospace;color:white;background:#143d70e8;padding:0 2px;border-radius:2px;pointer-events:none`;
      badgeHost.append(tag);
    }document.documentElement.append(badgeHost);
  }
  /* ---- the visible cursor -------------------------------------------------
     The agent should never move things without the student seeing it happen.
     A green pointer travels to each element and the target is outlined before
     anything is touched. It lives in a shadow root so page CSS cannot restyle
     it, and it never takes pointer events, so it cannot intercept a real
     click. It is hidden during observation so it never appears in the
     screenshot the model reads. */

  let ui = null;
  let cursorAt = { x: innerWidth / 2, y: innerHeight / 2 };
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const MOVE_MS = reduced ? 0 : 420;

  function ensureUI() {
    if (ui && document.documentElement.contains(ui.host)) return ui;
    const host = document.createElement('div');
    host.id = '__assignment_lab_cursor';
    host.style.cssText = 'all:initial;position:fixed;inset:0;pointer-events:none;z-index:2147483647';
    const root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = `
      <style>
        .layer { position:fixed; inset:0; pointer-events:none; }
        .dot {
          position:fixed; left:0; top:0; width:22px; height:22px; margin:-3px 0 0 -3px;
          transition: transform ${MOVE_MS}ms cubic-bezier(.22,.61,.36,1);
          will-change: transform; opacity:0;
        }
        .dot.held { filter: drop-shadow(0 0 5px #16c46a); }
        .dot svg { display:block; filter: drop-shadow(0 2px 4px rgba(0,0,0,.45)); }
        .ring {
          position:fixed; left:0; top:0; width:44px; height:44px; margin:-22px 0 0 -22px;
          border:3px solid #16c46a; border-radius:50%; opacity:0;
          transition: transform 260ms ease-out, opacity 260ms ease-out;
        }
        .box {
          position:fixed; border:2.5px solid #16c46a; border-radius:6px; opacity:0;
          box-shadow: 0 0 0 4px rgba(22,196,106,.25), 0 0 14px rgba(22,196,106,.55);
          transition: opacity 160ms ease-out; background: rgba(22,196,106,.10);
        }
        .tag {
          position:fixed; transform: translate(14px, 16px);
          background:#0f7a43; color:#fff; font:600 11px/1.35 ui-sans-serif,system-ui,sans-serif;
          padding:3px 7px; border-radius:5px; white-space:nowrap; opacity:0;
          transition: opacity 160ms ease-out; box-shadow:0 2px 6px rgba(0,0,0,.35);
          max-width:280px; overflow:hidden; text-overflow:ellipsis;
        }
        .on { opacity:1 !important; }
      </style>
      <div class="layer">
        <div class="box"></div>
        <div class="ring"></div>
        <div class="dot">
          <svg width="22" height="22" viewBox="0 0 22 22">
            <path d="M3 2 L3 17 L7.2 13.2 L9.8 19 L12.6 17.7 L10 12 L15.5 12 Z"
                  fill="#16c46a" stroke="#0b3d24" stroke-width="1.2" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="tag"></div>
      </div>`;
    (document.body || document.documentElement).append(host);
    ui = {
      host,
      dot: root.querySelector('.dot'),
      ring: root.querySelector('.ring'),
      box: root.querySelector('.box'),
      tag: root.querySelector('.tag')
    };
    place(cursorAt.x, cursorAt.y, true);
    return ui;
  }

  function place(x, y, instant) {
    const u = ensureUI();
    if (instant) u.dot.style.transition = 'none';
    u.dot.style.transform = `translate(${x}px, ${y}px)`;
    u.ring.style.transform = `translate(${x}px, ${y}px) scale(.4)`;
    u.tag.style.transform = `translate(${x + 14}px, ${y + 16}px)`;
    if (instant) { void u.dot.offsetWidth; u.dot.style.transition = ''; }
    cursorAt = { x, y };
  }

  async function moveTo(el, label) {
    const u = ensureUI();
    const rect = el.getBoundingClientRect();
    const x = Math.round(rect.left + Math.min(rect.width / 2, 60));
    const y = Math.round(rect.top + rect.height / 2);

    u.box.style.left = rect.left + 'px';
    u.box.style.top = rect.top + 'px';
    u.box.style.width = rect.width + 'px';
    u.box.style.height = rect.height + 'px';
    u.box.classList.add('on');
    u.tag.textContent = label;
    u.tag.classList.add('on');
    u.dot.classList.add('on');

    place(x, y, false);
    await settle(MOVE_MS + 60);
  }

  async function pressEffect() {
    const u = ensureUI();
    u.ring.style.transition = 'none';
    u.ring.style.transform = `translate(${cursorAt.x}px, ${cursorAt.y}px) scale(.35)`;
    u.ring.style.opacity = '1';
    void u.ring.offsetWidth;
    u.ring.style.transition = 'transform 300ms ease-out, opacity 300ms ease-out';
    u.ring.style.transform = `translate(${cursorAt.x}px, ${cursorAt.y}px) scale(1.15)`;
    u.ring.style.opacity = '0';
    await settle(200);
  }

  function hideUI() {
    if (!ui) return;
    ui.dot.classList.remove('on');
    ui.box.classList.remove('on');
    ui.tag.classList.remove('on');
    ui.ring.style.opacity = '0';
  }

  function describe(action) {
    if (action.action === 'fill') return `type "${String(action.text).slice(0, 40)}"`;
    if (action.action === 'select') return `choose "${String(action.option).slice(0, 40)}"`;
    return action.action;
  }

  function settle(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }


  function checkCancelled(){if(cancelled)throw new Error('Stopped by you before the next gesture.');}
  async function pause(ms){await settle(ms);checkCancelled();}
  function center(el){const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};}
  function elementAt(point) {
    let el=document.elementFromPoint(point.x,point.y);
    for(let depth=0;el?.shadowRoot&&depth<20;depth++) {
      const child=el.shadowRoot.elementFromPoint?.(point.x,point.y);
      if(!child||child===el)break;el=child;
    }
    return el;
  }
  function pointer(el,type,point,buttons=0) {
    checkCancelled();
    el.dispatchEvent(new PointerEvent(type,{bubbles:true,composed:true,cancelable:true,pointerId:1,pointerType:'mouse',isPrimary:true,button:0,buttons,clientX:point.x,clientY:point.y}));
    const mouse={pointerdown:'mousedown',pointermove:'mousemove',pointerup:'mouseup'}[type];
    if(mouse)el.dispatchEvent(new MouseEvent(mouse,{bubbles:true,composed:true,cancelable:true,button:0,buttons,clientX:point.x,clientY:point.y}));
  }
  function keypress(el,keyName){
    const keyValue=keyName==='Space'?' ':keyName;
    for(const type of ['keydown','keyup']){checkCancelled();el.dispatchEvent(new KeyboardEvent(type,{key:keyValue,code:keyName==='Space'?'Space':keyName,bubbles:true,composed:true,cancelable:true}));}
  }
  function landed(source,target,label,priorText) {
    if(!source.isConnected || !target.isConnected)return false;
    return target!==source && (target.contains(source) || (text(target)!==priorText && !priorText.includes(label) && label.length>0 && text(target).includes(label)));
  }
  async function drag(source,target) {
    if(source===target || sensitive(target))return {ok:false,detail:'Invalid or sensitive drag destination.'};
    if(!source.matches(SOURCES)||!target.matches(TARGETS+', [role=gridcell],[role=cell],[role=listbox]'))return {ok:false,detail:'Source/target is not identified as a drag control.'};
    const label=text(source),priorText=text(target),tried=[];
    if(target.contains(source))return {ok:true,verified:true,strategy:'already',detail:'Item is already inside that target.'};
    const u=ensureUI();await moveTo(source,'drag '+label.slice(0,40));
    u.dot.classList.add('held');u.host.dataset.held='true';
    try {
      for(const strategy of ['click','keyboard','html5','pointer']) {
        checkCancelled();if(!source.isConnected||!target.isConnected)return {ok:false,detail:'Drag controls re-rendered. Re-observe before another gesture; tried '+tried.join(', ')};
        const before=digest();tried.push(strategy);
        if(strategy==='click'){source.click();await pause(100);if(!target.isConnected)break;target.click();}
        if(strategy==='keyboard') {
          if(source.tabIndex>=0){source.focus();keypress(source,'Space');const a=center(source),b=center(target);
            keypress(source,Math.abs(b.x-a.x)>Math.abs(b.y-a.y)?(b.x>a.x?'ArrowRight':'ArrowLeft'):(b.y>a.y?'ArrowDown':'ArrowUp'));
            if(target.tabIndex>=0)target.focus();keypress(document.activeElement||source,'Space');}
        }
        if(strategy==='html5') {
          const dataTransfer=new DataTransfer();dataTransfer.setData('text/plain',source.id||label);
          const fire=(el,type)=>{const point=center(el);const event=new DragEvent(type,{dataTransfer,bubbles:true,composed:true,cancelable:true,clientX:point.x,clientY:point.y});el.dispatchEvent(event);return event.defaultPrevented;};
          try{fire(source,'dragstart');fire(target,'dragenter');if(fire(target,'dragover'))fire(target,'drop');}finally{fire(source,'dragend');}
        }
        if(strategy==='pointer') {
          const a=center(source),b=center(target);pointer(source,'pointerdown',a,1);
          try{for(let i=1;i<=12;i++){const point={x:a.x+(b.x-a.x)*i/12,y:a.y+(b.y-a.y)*i/12};place(point.x,point.y,true);pointer(elementAt(point)||target,'pointermove',point,1);await pause(30);}
            pointer(elementAt(b)||target,'pointerup',b,0);
          }finally{if(cancelled)source.dispatchEvent(new PointerEvent('pointercancel',{bubbles:true,pointerId:1}));}
        }
        await pause(180);
        if(landed(source,target,label,priorText))return {ok:true,verified:true,strategy,detail:`Verified: ${label} is in ${accessibleName(target)} (${strategy}).`};
        if(digest()!==before) return {ok:false,detail:`${strategy} changed the layout or an answer without the expected drop. Re-observe and correct it; tried ${tried.join(', ')}.`};
      }
      return {ok:false,detail:'Drop could not be verified. Tried '+tried.join(', ')+'. Synthetic events may be unsupported; place the item manually.'};
    }finally{u.dot.classList.remove('held');delete u.host.dataset.held;}
  }
  async function act(action, permit={}) {
    checkCancelled();
    const verbs=new Set(['fill','click','select','drag','press','scroll','scroll_to']);
    if(!verbs.has(action.action))return {ok:false,detail:'Unsupported action.'};
    if(action.action==='scroll'){scrollBy({top:action.direction==='up'?-innerHeight*.8:innerHeight*.8,behavior:'instant'});return {ok:true,detail:'Scrolled.'};}
    const el=refs.get(Number(action.ref));
    if(!el?.isConnected)return {ok:false,detail:'That element is no longer on the page. Re-observing.'};
    if(sensitive(el))return {ok:false,detail:'Refused: credential or payment field.'};
    const activating=action.action==='click'||(action.action==='press'&&['Enter','Space'].includes(action.key));
    if(endsTheAssignment(el)&&activating&&!permit.terminal)return {ok:false,detail:'Refused: hand-in requires the harness to verify all parts and the hand-in switch.'};
    if(activating&&classification(el)==='refused')return {ok:false,detail:'Refused: "'+accessibleName(el).slice(0,60)+'" is a destructive, account, consent or download control. That stays with the student.'};
    if(activating&&external(el))return {ok:false,detail:'Refused: that link leaves the assignment site.'};
    if(action.action==='press'&&action.key==='Enter'&&editable(el))return {ok:false,detail:'Enter in a field can submit its form. Use the classified button instead.'};
    if(el.disabled||el.getAttribute('aria-disabled')==='true')return {ok:false,detail:'That control is disabled.'};
    el.scrollIntoView({block:'center',behavior:'instant'});await pause(60);
    if(action.action==='scroll_to')return {ok:true,detail:'Scrolled to the control.'};
    if(action.action==='drag') {
      const target=refs.get(Number(action.to));if(!target?.isConnected)return {ok:false,detail:'Drag destination is no longer listed.'};
      return drag(el,target);
    }
    await moveTo(el,describe(action));checkCancelled();await pressEffect();checkCancelled();
    if(action.action==='fill') {
      if(!editable(el))return {ok:false,detail:'That control is not a text field.'};
      el.focus();
      if(el.isContentEditable)el.textContent=action.text;
      else {const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,action.text);}
      el.dispatchEvent(new Event('input',{bubbles:true,composed:true}));el.dispatchEvent(new Event('change',{bubbles:true,composed:true}));await pause(150);
      const ok=clean(valueOf(el))===clean(action.text);
      return {ok,detail:ok?`Field now reads "${valueOf(el).slice(0,80)}".`:'The entered value did not stick.'};
    }
    if(action.action==='select') {
      if(el.tagName!=='SELECT')return {ok:false,detail:'That element is not a native dropdown. Use click/press on its options.'};
      const option=[...el.options].find(o=>o.text.trim()===action.option||o.value===action.option);
      if(!option)return {ok:false,detail:'No option with that label.'};
      el.value=option.value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));await pause(120);
      return {ok:el.value===option.value,detail:'Selected '+option.text};
    }
    if(action.action==='press') {
      if(!KEYS.has(action.key))return {ok:false,detail:'Unsupported key.'};
      const before=digest();el.focus();keypress(el,action.key);await pause(150);
      return {ok:digest()!==before,detail:digest()!==before?'Key changed the page.':'Synthetic key had no observable effect; use another control.'};
    }
    if(action.action==='click') {
      if(action.mode && action.mode!=='pointer')return {ok:false,detail:'Unsupported click mode.'};
      if(action.mode==='pointer'){const c=center(el);pointer(el,'pointerdown',c,1);pointer(el,'pointerup',c);}
      el.click();await pause(180);return {ok:true,detail:'Click executed; verify the resulting answer separately.'};
    }
  }
  function verify(evidence) {
    const nodes=all();const el=nodes.find(n=>key(n)===evidence.key);
    if(!el || !visible(el))return {visible:false,verified:false};
    if(sensitive(el))return {visible:true,verified:false};
    const expected=clean(evidence.answer).toLowerCase();
    // `supported` means a branch below actually judged this control. Only a
    // control nothing here can read -- a closed shadow host, a canvas -- is
    // unsupported, and for those the screenshot verdict stands instead.
    let actual=valueOf(el),verified=false,supported=true;
    if(evidence.kind==='ordering') {
      const items=listItems(el);const actualKeys=items.map(key);
      verified=!!evidence.order_keys?.length && JSON.stringify(actualKeys)===JSON.stringify(evidence.order_keys);
      return {visible:true,verified,supported:!!evidence.order_keys?.length,actual:items.map(text).join(' | '),sequence:items.map(text),method:'dom-order'};
    }
    else if(el.matches(DROPDOWNS)&&el.tagName!=='SELECT')verified=!!expected&&clean(actual).toLowerCase()===expected;
    else if(evidence.kind==='drag')verified=expected.length>0&&[...el.querySelectorAll(SOURCES)].some(s=>text(s).toLowerCase()===expected&&(!evidence.source_key||key(s)===evidence.source_key));
    else if(['radio','checkbox','option','switch'].includes(role(el))) {actual=accessibleName(el);verified=(el.checked===true||el.getAttribute('aria-checked')==='true'||el.getAttribute('aria-selected')==='true')&&clean(actual).toLowerCase()===expected;}
    else if(role(el)==='button') {
      // Styled multiple-choice options. Only a state the page itself exposes
      // counts; the click having happened does not.
      actual=accessibleName(el);
      const stateOn=['aria-pressed','aria-checked','aria-selected'].some(a=>el.getAttribute(a)==='true')
        ||/(?:^|[\s_-])(?:selected|active|checked|chosen|is-selected|is-active)(?:$|[\s_-])/i.test(el.className||'')
        ||!!el.querySelector('input:checked');
      verified=stateOn&&clean(actual).toLowerCase()===expected;
    }
    else if(el.tagName==='SELECT'){const option=el.selectedOptions[0];verified=!!option&&(clean(option.text).toLowerCase()===expected||clean(option.value).toLowerCase()===expected);}
    else if(editable(el))verified=clean(actual).toLowerCase()===expected;
    else supported=false;
    return {visible:true,verified,supported,actual:clean(actual).slice(0,1000)};
  }
  function visualGuard(point) {
    let doc=document,x=point.x,y=point.y,el;
    for(let depth=0;depth<12;depth++) {
      el=doc.elementFromPoint(x,y);if(!el)return {ok:false,detail:'No visible target at that point.'};
      while(el.shadowRoot?.elementFromPoint(x,y)&&el.shadowRoot.elementFromPoint(x,y)!==el)el=el.shadowRoot.elementFromPoint(x,y);
      if(el.tagName!=='IFRAME')break;
      try {if(el.contentWindow.location.origin!==location.origin||!el.contentDocument)return {ok:false,detail:'Cross-origin frame input refused.'};const r=el.getBoundingClientRect();x-=r.left+el.clientLeft;y-=r.top+el.clientTop;doc=el.contentDocument;}catch{return {ok:false,detail:'Inaccessible frame input refused.'};}
    }
    for(let n=el;n;n=parent(n)) {
      // Classify the hit control and actionable ancestors, not the whole body's
      // descendant text: an unrelated Submit button must not block every cell.
      const actionable=n.matches?.('button,input,select,textarea,a[href],[role=button],[role=link],[tabindex],[onclick]');
      if(sensitive(n)||n.matches?.('a[href],iframe')||((n===el||actionable)&&['terminal','advance','refused'].includes(classification(n))))
        return {ok:false,detail:'Visual input cannot activate navigation, submission or sensitive controls.'};
    }
    const label=clean(el.getAttribute('aria-label'));
    const owner=label&&[...doc.querySelectorAll(DROPDOWNS)].find(n=>clean(n.getAttribute('aria-label'))===label);
    const region=closest(el,'table,[role=listbox],[role=list],ol,[data-sortable],[data-rbd-droppable-id]')||(owner&&closest(owner,'table'));
    if(!region)return {ok:false,detail:'Point is outside a recognized answer table, menu or ordering list.'};
    return {ok:true};
  }
  window.__assignmentLab={observe,act,hideUI,moveTo,pressEffect,describe,badges,badgesOff,verify,digest,visualGuard,cursorHeld:()=>!!ui?.dot.classList.contains('held')};
  if(!globalThis.chrome?.runtime?.onMessage)return;
  chrome.runtime.onMessage.addListener((message,_sender,reply)=>{
    if(message.type==='observe'){reply(observe());return true;}
    if(message.type==='digest'){reply({digest:digest()});return true;}
    if(message.type==='viewport'){reply({width:innerWidth,height:innerHeight,scrollX,scrollY,scale:visualViewport?.scale||1});return true;}
    if(message.type==='visual_guard'){reply(visualGuard(message.point));return true;}
    if(message.type==='verify'){reply(verify(message.evidence));return true;}
    if(message.type==='badges'){badges(message.entries);reply({ok:true});return true;}
    if(message.type==='badges_off'){badgesOff();reply({ok:true});return true;}
    if(message.type==='cancel'){cancelled=true;badgesOff();hideUI();reply({ok:true});return true;}
    if(message.type==='reset'){cancelled=false;reply({ok:true});return true;}
    if(message.type==='cursor_off'){hideUI();badgesOff();reply({ok:true});return true;}
    if(message.type==='act'){act(message.action,message.permit||{}).then(reply).catch(e=>reply({ok:false,detail:e.message}));return true;}
    return false;
  });
})();
