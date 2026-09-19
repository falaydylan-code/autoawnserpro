/* Packaged, bounded DOM inspection. No eval, MAIN-world code, storage or network.
   All tokens refer to this observation, not arbitrary selectors supplied by a model. */
(() => {
  if(globalThis.__assignmentPlannerInspector)return;
  const doc=crypto.randomUUID(), nodes=new WeakMap(); let serial=0,last=null,limited=false;
  const norm=s=>String(s??'').replace(/\s+/g,' ').trim();
  const fail=(code,detail,data)=>({ok:false,code,detail,...(data!==undefined?{data}:{})});
  const dropdown='select,[role=combobox],td.dropDownList,td[dropdowntype]';
  const answerCells=dropdown+',td.responseCell[tabindex],[role=gridcell][tabindex]';
  // A sheet cell whose editor was confirmed is remembered by its SLOT KEY (question + part + cell id), not by its DOM
  // node: courseware rebuilds a sheet's nodes when its tab is shown again, and a memory pinned to the old node
  // forgot every confirmed cell the moment the harness returned to type (E1-9, 8:51 PM: GUARD_REJECTED on cell 1).
  let confirmedSheetValues=new Set(),classificationQuestion='';
  const sensitive=/credit.?card|card.?number|cvv|cvc|social.?security|ssn|iban|routing|account.?number/i;
  const forbidden=/^(?:delete|remove|discard|reset|sign\s*(?:in|out)|log\s*(?:in|out)|register|accept|agree|allow|consent|download|export|purchase|buy|pay|checkout)\b/i;
  const shown=e=>!!e?.isConnected&&!e.closest('[hidden],[aria-hidden=true],script,style,template')&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none'&&!!e.getClientRects().length;
  const name=e=>norm(e.getAttribute('aria-label')||[...(e.labels||[])].map(l=>l.innerText).join(' ')||e.innerText||e.getAttribute('title')||e.getAttribute('placeholder')||'');
  const safe=e=>!sensitive.test([e.type,e.name,e.id,e.autocomplete,e.getAttribute('aria-label')].join(' '))&&!['hidden','file'].includes(e.type);
  const key=e=>e.id?'id:'+e.id:(e.matches('td,th')?'cell:'+(e.closest('table')?.id||'table')+':'+e.parentElement.rowIndex+':'+e.cellIndex:(e.getAttribute('data-slot-id')?'slot:'+e.getAttribute('data-slot-id'):(nodes.has(e)?nodes.get(e):(nodes.set(e,'node:'+(++serial)),nodes.get(e)))));
  function binding(e){const path=[];let n=e;while(n!==document){if(path.length>80)return null;if(n.nodeType===11&&n.host){path.unshift('shadow');n=n.host;continue}const p=n.parentNode;if(!p)return null;path.unshift([...p.children].indexOf(n));n=p;}return {path,tag:e.tagName,id:e.id||null};}
  const hash=s=>{let n=2166136261;for(const c of s)n=Math.imul(n^c.charCodeAt(0),16777619);return (n>>>0).toString(16)};
  function all(root,selector){const found=[];let budget=12000;
    const scan=(r,depth)=>{if(depth>12){limited=true;return}const walker=document.createTreeWalker(r,NodeFilter.SHOW_ELEMENT);let el;
      while((el=walker.nextNode())){if(--budget<0){limited=true;return}if(el.matches(selector))found.push(el);if(el.shadowRoot)scan(el.shadowRoot,depth+1);if(budget<0)return}};
    scan(root,0);return found;
  }
  function value(e){if(e.tagName==='SELECT')return norm(e.selectedOptions[0]?.text);if(e.matches('input,textarea'))return e.value;
    const copy=e.cloneNode(true);copy.querySelectorAll('button,input,textarea,[role=listbox],[role=option],.dropdownButton,[aria-hidden=true]').forEach(n=>n.remove());
    return norm(e.getAttribute('aria-valuetext')||e.querySelector('.dropdownValue')?.innerText||copy.textContent);}
  function offset(){let x=0,y=0,w=window;try{while(w!==w.top){const f=w.frameElement;if(!f)return null;const st=w.parent.getComputedStyle(f),r=f.getBoundingClientRect();if(st.transform!=='none'||st.zoom&&Number(st.zoom)!==1||Math.abs(r.width-f.offsetWidth)>1)return null;x+=r.x+f.clientLeft;y+=r.y+f.clientTop;w=w.parent;}return {x,y};}catch{return null}}
  function rect(e){const r=e.getBoundingClientRect(),off=offset();return {local:{x:r.x,y:r.y,w:r.width,h:r.height},viewport:off?{x:r.x+off.x,y:r.y+off.y,w:r.width,h:r.height}:null}}
  function owner(option,cells){const menu=option?.closest('[role=listbox]');if(!menu)return null;
    const labelled=(menu.getAttribute('aria-labelledby')||'').split(/\s+/);
    // A reused popup may be referenced by every row's old arrow. Its current
    // explicit owner label is stronger evidence than those stale references.
    const named=cells.filter(c=>c.id&&labelled.includes(c.id));
    if(named.length)return named.length===1?named[0]:null;
    const owners=cells.filter(c=>(c.getAttribute('aria-controls')||'').split(/\s+/).includes(menu.id)||[...c.querySelectorAll('[aria-controls]')].some(t=>t.getAttribute('aria-controls')===menu.id));
    const activeOwners=owners.filter(c=>c.getAttribute('aria-expanded')==='true');
    if(activeOwners.length===1)return activeOwners[0];
    if(owners.length===1)return owners[0];
    if(owners.length>1)return null;                    // ambiguous ARIA linkage: refuse
    // No ARIA link (real McGraw-style cells often omit it). Fall back to
    // ACTIVATION evidence, not formatting: the cell the runtime just opened
    // marks itself aria-expanded="true". Exactly one expanded cell unambiguously
    // owns the single open menu; anything else stays null (WRONG_MENU_OWNER).
    const expanded=cells.filter(c=>c.getAttribute('aria-expanded')==='true');
    return expanded.length===1?expanded[0]:null;}
  function renderedText(root,exclude){let parts=[],count=0,complete=true;const walk=n=>{if(++count>12000){complete=false;return}if(n.nodeType===3){if(norm(n.textContent))parts.push(n.textContent);return}if(n.nodeType!==1)return;
    if(exclude.has(n)||!shown(n)||n.matches('script,style,template,button,nav,output,[role=listbox],[role=option],[role=status],[role=alert],[aria-live],[class*=feedback],[class*=result],[class*=correct],[class*=grade],[class*=score],[class*=saved],[class*=attempt],#__assignment_lab_cursor,#__assignment_lab_badges'))return;
    if(n.matches('input,textarea,select'))return;for(const c of n.childNodes)walk(c);if(n.shadowRoot)for(const c of n.shadowRoot.childNodes)walk(c)};walk(root);return {text:norm(parts.join(' ')),complete};}
  // Supplemental source data only: never register targets or change question identity.
  function readTables(root,excluded){
    const tables=[];let complete=true,remaining=300,characters=12000;
    const candidates=all(root,'table').filter(t=>shown(t)&&!t.matches('[role=presentation],[role=none]')&&!t.closest('nav,[role=listbox],[role=option],.feedback,.correct-answer'));
    for(const table of candidates){
      const rows=[...table.rows];
      // Nested wrapper/layout tables are not another copy of the inner data.
      if(table.querySelector('table')||rows.length<2||!rows.some(r=>r.cells.length>1))continue;
      if(tables.length>=6||remaining<=0||characters<=0){complete=false;break}
      const data={dom_id:table.id||null,caption:'',rows:[],complete:true};
      const caption=table.caption||null;
      data.caption=norm(caption&&shown(caption)?renderedText(caption,excluded).text:table.getAttribute('aria-label')||table.getAttribute('summary')||'').slice(0,1000);
      const occupied=[];
      for(let r=0;r<rows.length;r++){
        if(r>=200){data.complete=false;break}
        const row=rows[r],entries=[];let column=0;
        for(const cell of row.cells){
          while((occupied[column]||0)>r)column++;
          const groupRemaining=[...row.parentElement.rows].length-row.sectionRowIndex;
          const rowSpan=Math.min(cell.rowSpan||groupRemaining,groupRemaining);
          const colSpan=cell.colSpan;
          if(column+colSpan>256||rowSpan>200){data.complete=false;break}
          for(let c=column;c<column+colSpan;c++)occupied[c]=r+rowSpan;
          if(shown(row)&&shown(cell)){
            if(remaining<=0||characters<=0){data.complete=false;break}
            const answer=excluded.has(cell)||cell.matches(answerCells)||!!cell.querySelector('input,textarea,select,[contenteditable=true]');
            // Answer values live in slots[].current; do not pass them off as givens.
            const read=answer?{text:'',complete:true}:renderedText(cell,excluded),text=read.text;
            const value=text.slice(0,Math.min(1000,characters));
            if(!read.complete||value.length!==text.length)data.complete=false;
            characters-=value.length;remaining--;
            entries.push({column,text:value,row_span:rowSpan,column_span:colSpan,header:cell.tagName==='TH',...(cell.getAttribute('scope')?{scope:cell.getAttribute('scope').slice(0,100)}:{}),...(cell.id?{dom_id:cell.id}:{}),...(answer?{answer:true}:{})});
          }
          column+=colSpan;
        }
        if(entries.length)data.rows.push({row:r,cells:entries});
        if(!data.complete)break;
      }
      if(data.rows.length)tables.push(data);
      if(!data.complete)complete=false;
    }
    return {tables,complete};
  }
  function openingControls(e,cells,register){
    if(e.tagName==='SELECT')return {status:'native',candidates:[]};
    const candidates=[];
    // A text editor is not an expand button. Detached buttons must have
    // ownership evidence, not just be the nearest clickable element.
    for(const n of all(document,'.dropdownButton,button,input[type=button],[role=button],[aria-haspopup]')){
      if(n===e||!shown(n)||!safe(n)||n.matches('input:not([type=button]),textarea,select,[contenteditable=true],td,th'))continue;
      const isButton=n.matches('.dropdownButton,button,input[type=button],[role=button]');
      const explicit=n.matches('.dropdownButton')||['true','listbox'].includes(n.getAttribute('aria-haspopup'))||/^(?:show all items|open(?: options| menu| dropdown)?|expand(?: options| menu| dropdown)?)$/i.test(n.getAttribute('title')||name(n));
      if(!explicit)continue;
      const containing=cells.filter(c=>c.contains(n));let evidence='';
      if(containing.length){if(containing.length!==1||containing[0]!==e)continue;evidence='contained_opening_control';}
      else {
        const ids=(n.getAttribute('aria-controls')||'').split(/\s+/);
        const direct=cells.filter(c=>c.id&&ids.includes(c.id));
        if(direct.length){if(direct.length!==1||direct[0]!==e)continue;evidence='controls_slot';}
        else {
          const linked=ids.map(id=>document.getElementById(id)).filter(m=>m?.matches('[role=listbox]'));
          const owners=linked.map(m=>owner(m.querySelector('[role=option]'),cells)).filter(Boolean);
          if(owners.length){if(owners.some(c=>c!==e))continue;evidence='associated_menu';}
          else {
            const label=norm(n.getAttribute('aria-label')),matches=cells.filter(c=>label&&norm(c.getAttribute('aria-label')||name(c))===label);
            const a=n.getBoundingClientRect(),b=e.getBoundingClientRect(),x=a.x+a.width/2,y=a.y+a.height/2;
            const inside=x>=b.left&&x<=b.right&&y>=b.top&&y<=b.bottom;
            if(!isButton||!inside)continue;
            if(matches.length===1&&matches[0]===e)evidence='unique_slot_label_and_overlay_geometry';
            else {
              // No usable label (a statement's title-row dropdown has none): the button's center lies inside THIS
              // cell's box and inside no other cell's. Weaker than a label match, so the runtime tries it only
              // after explicit evidence, and still proves the opened menu belongs to this cell before choosing.
              if(matches.length||cells.some(c=>c!==e&&(()=>{const r=c.getBoundingClientRect();return x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom})()))continue;
              evidence='overlay_geometry';
            }
          }
        }
      }
      candidates.push({target:register(n),label:name(n),title:n.getAttribute('title')||'',tag:n.tagName,type:n.getAttribute('type'),evidence,disabled:!!n.disabled||n.getAttribute('aria-disabled')==='true',...rect(n)});
    }
    // Explicit evidence outranks geometry: when both exist only the explicit candidates decide the status.
    const explicitOnes=candidates.filter(c=>c.evidence!=='overlay_geometry'),ranked=explicitOnes.length?explicitOnes:candidates;
    return {status:ranked.length===1?'resolved':ranked.length?'ambiguous':'missing',candidates:ranked,geometry_only:!explicitOnes.length&&ranked.length===1};
  }
  function sheetCell(e){return e.matches('td.responseCell.response')&&!!e.closest('table.jSheet')&&!!e.closest('.jSheetParent')?.querySelector('textarea.jSheetControls_formula');}
  function interaction(e,cells,register,memoryKey){
    memoryKey=memoryKey||key(e);
    const opening=openingControls(e,cells,register);
    const selection=e.matches(dropdown)||!!e.querySelector('[role=combobox]')||opening.status!=='missing'||all(document,'[role=listbox] [role=option]').some(o=>owner(o,cells)===e);
    if(selection)return {kind:'selection',adapter:'selection',evidence:['dropdown_markup_or_associated_menu'],opening_control:opening};
    if(sheetCell(e)){
      const active=cells.filter(c=>sheetCell(c)&&c.matches('.jSheetCellActive'));
      const b=e.getBoundingClientRect();
      const editors=active.length===1&&active[0]===e?all(document,'textarea.jSheetInPlaceEdit').filter(n=>{
        if(!shown(n)||!safe(n)||n.readOnly||n.disabled)return false;const r=n.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
        return x>=b.left&&x<=b.right&&y>=b.top&&y<=b.bottom&&r.width>5&&r.height>5;
      }):[];
      if(editors.length>1)return {kind:'unresolved',adapter:'sheet_text',evidence:['multiple_editors_for_active_cell'],ambiguous:true};
      if(editors.length===1){confirmedSheetValues.add(memoryKey);return {kind:'value',adapter:'sheet_text',editor_target:register(editors[0]),evidence:['active_spreadsheet_cell','unique_overlay_textarea']};}
      const remembered=confirmedSheetValues.has(memoryKey);
      return {kind:remembered?'value':'unresolved',adapter:'sheet_text',evidence:[remembered?'previously_observed_cell_editor':'spreadsheet_cell_requires_editor_activation']};
    }
    const editors=[...e.querySelectorAll('input[type=number],textarea,input[inputmode=numeric],input[inputmode=decimal]')].filter(n=>shown(n)&&safe(n)&&!n.disabled&&!n.readOnly&&!n.matches('[role=combobox],[aria-haspopup]'));
    if(editors.length===1)return {kind:'value',adapter:'contained_text',editor_target:register(editors[0]),evidence:['contained_numeric_or_multiline_input']};
    return {kind:'unresolved',adapter:'unknown',evidence:[editors.length>1?'multiple_possible_editors':'answer_location_without_interaction_evidence']};
  }
  function scrollInfo(e,point=null){
    const box=e.getBoundingClientRect(),cx=point?.x??box.x+box.width/2,cy=point?.y??box.y+box.height/2,ancestors=[];
    // Overflow size alone is not clipping: visible-overflow worksheet wrappers
    // can be smaller than a popup without being scroll containers.
    for(let n=e.parentElement;n&&ancestors.length<24;n=n.parentElement){
      if(n===document.scrollingElement)continue; // viewport scrolling is measured separately below
      const css=getComputedStyle(n),clipX=/^(auto|scroll|hidden|clip)$/.test(css.overflowX),clipY=/^(auto|scroll|hidden|clip)$/.test(css.overflowY);
      if(!clipX&&!clipY)continue;
      // NiceScroll (used by the live worksheet) hides native overflow and owns
      // wheel handling. Require its visible sibling rail and a unique listbox;
      // arbitrary overflow:hidden containers are not assumed scrollable.
      const customY=n.matches('[role=listbox]')&&n.parentElement?.querySelectorAll('[role=listbox]').length===1&&[...n.parentElement.children].some(s=>s.matches('.nicescroll-rails-vr')&&shown(s));
      const r=n.getBoundingClientRect(),sx=n.offsetWidth?r.width/n.offsetWidth:1,sy=n.offsetHeight?r.height/n.offsetHeight:1;
      const area={x:r.x+n.clientLeft*sx,y:r.y+n.clientTop*sy,w:n.clientWidth*sx,h:n.clientHeight*sy};
      ancestors.push({n,area,clipX,clipY,customY,scrollX:/^(auto|scroll)$/.test(css.overflowX)&&n.scrollWidth>n.clientWidth+1,scrollY:(/^(auto|scroll)$/.test(css.overflowY)||customY)&&n.scrollHeight>n.clientHeight+1});
    }
    const page=document.scrollingElement;
    if(page)ancestors.push({n:page,area:{x:0,y:0,w:innerWidth,h:innerHeight},clipX:true,clipY:true,page:true,
      scrollX:page.scrollWidth>innerWidth+1&&!/hidden|clip/.test(getComputedStyle(page).overflowX),
      scrollY:page.scrollHeight>innerHeight+1&&!/hidden|clip/.test(getComputedStyle(page).overflowY)});
    const intersect=(a,b,x=true,y=true)=>{const left=x?Math.max(a.x,b.x):a.x,top=y?Math.max(a.y,b.y):a.y;return {x:left,y:top,w:Math.max(0,(x?Math.min(a.x+a.w,b.x+b.w):a.x+a.w)-left),h:Math.max(0,(y?Math.min(a.y+a.h,b.y+b.h):a.y+a.h)-top)}};
    const off=offset();
    const containers=ancestors.map((a,i)=>{
      const clippedX=a.clipX&&(cx<a.area.x||cx>=a.area.x+a.area.w),clippedY=a.clipY&&(cy<a.area.y||cy>=a.area.y+a.area.h);
      let visible=intersect(a.area,{x:0,y:0,w:innerWidth,h:innerHeight});
      for(const outer of ancestors.slice(i+1))visible=intersect(visible,outer.area,outer.clipX,outer.clipY);
      const wheelPoints=a.page?[{x:12,y:innerHeight/2},{x:innerWidth-24,y:innerHeight/2},{x:innerWidth/2,y:24},{x:innerWidth/2,y:innerHeight-24},{x:innerWidth/2,y:innerHeight/2}]:[{x:visible.x+visible.w/2,y:visible.y+visible.h/2}];
      const wheelPoint=visible.w>2&&visible.h>2?wheelPoints.find(p=>{
        const hit=document.elementFromPoint(p.x,p.y);if(!hit||!(hit===a.n||a.n.contains(hit)))return false;
        if(!a.page)return true;
        // A page wheel must not land inside another scrolling widget or iframe.
        if(hit.closest('iframe,frame'))return false;
        for(let n=hit;n&&n!==a.n;n=n.parentElement){const css=getComputedStyle(n);
          if(css.position==='fixed'||css.position==='sticky'||(/auto|scroll/.test(css.overflowY)&&n.scrollHeight>n.clientHeight+1)||(/auto|scroll/.test(css.overflowX)&&n.scrollWidth>n.clientWidth+1))return false;}
        return true;
      }):null;
      const delta={x:clippedX&&a.scrollX?cx-(a.area.x+a.area.w/2):0,y:clippedY&&a.scrollY?cy-(a.area.y+a.area.h/2):0};
      return {id:key(a.n),role:a.n.getAttribute('role'),top:a.n.scrollTop,left:a.n.scrollLeft,max_y:a.n.scrollHeight-a.n.clientHeight,max_x:a.n.scrollWidth-a.n.clientWidth,
        clipped:clippedX||clippedY,scrollable:a.scrollX||a.scrollY,scroll_adapter:a.page?'page_wheel':a.customY?'nicescroll_wheel':'native_wheel',delta,local:visible,viewport:off?{...visible,x:visible.x+off.x,y:visible.y+off.y}:null,
        wheel_point:wheelPoint,wheel_hit:!!wheelPoint};
    });
    return {clipped:containers.some(c=>c.clipped),containers};
  }
  function readOptions(e){
    // Read existing UI option nodes, including collapsed menus. Never activate
    // a widget, read framework internals, or borrow an unrelated menu's choices.
    const option=o=>({label:norm(o.getAttribute('aria-label')||o.textContent),selected:!!o.selected||o.getAttribute('aria-selected')==='true',disabled:!!o.disabled||o.getAttribute('aria-disabled')==='true'||o.parentElement?.disabled===true});
    if(e.tagName==='SELECT')return {options:[...e.options].map(option),source:'native_select'};
    const nested=all(e,'select');
    if(nested.length>1)return {options:[],source:'ambiguous_nested_select'};
    if(nested.length===1)return {options:[...nested[0].options].map(option),source:'nested_select'};
    const cells=last.slots.filter(s=>s.kind==='selection').map(s=>last.targets.get(s.target));
    const menus=all(document,'[role=listbox]').filter(menu=>{
      const first=menu.querySelector('[role=option]');if(!first)return false;
      const named=(menu.getAttribute('aria-labelledby')||'').split(/\s+/).includes(e.id)&&!!e.id;
      const linked=!!menu.id&&[e,...e.querySelectorAll('[aria-controls]')].some(n=>(n.getAttribute('aria-controls')||'').split(/\s+/).includes(menu.id));
      const actualOwner=owner(first,cells);
      if(actualOwner&&actualOwner!==e)return false;
      if(e.contains(menu))return true;
      return (shown(menu)||named||linked)&&actualOwner===e;
    });
    if(menus.length>1)return {options:[],source:'ambiguous_menus'};
    const menu=menus[0];
    return {options:menu?all(menu,'[role=option]').map(o=>({...option(o),visible:shown(o)&&!scrollInfo(o).clipped})):[],source:menu?'associated_dom_menu':'not_present_in_dom',
      menu_scroll:menu?{top:menu.scrollTop,left:menu.scrollLeft,height:menu.clientHeight,content_height:menu.scrollHeight,overflow_y:getComputedStyle(menu).overflowY,
        adapter:menu.firstElementChild?scrollInfo(menu.firstElementChild).containers.find(c=>c.id===key(menu))?.scroll_adapter:null}:null};
  }
  function geometry(svg){
    if(svg.tagName.toLowerCase()!=='svg')return {calibrated:false,reason:'Opaque graph needs visual calibration.'};
    const circles=[...svg.querySelectorAll('circle[data-point-id],circle[tabindex],circle[draggable=true]')].filter(shown);
    // Labeled SVG ticks define the transformation; never read page answer keys or private state.
    const labels=[...svg.querySelectorAll('text')].filter(shown).map(e=>({e,n:Number(norm(e.textContent))})).filter(p=>Number.isFinite(p.n)&&norm(p.e.textContent)!=='');
    const axis=which=>labels.filter(p=>p.e.getAttribute('data-axis')===which).map(p=>({math:p.n,user:Number(p.e.getAttribute(which))}));
    const fit=points=>{if(points.length<2)return null;const a=points[0],b=points.find(p=>p.math!==a.math);if(!b)return null;const scale=(b.user-a.user)/(b.math-a.math),origin=a.user-a.math*scale;if(!scale||!Number.isFinite(scale)||points.some(p=>Math.abs(p.user-(origin+p.math*scale))>.5))return null;return {scale,origin,min:Math.min(...points.map(p=>p.math)),max:Math.max(...points.map(p=>p.math))}};
    const x=fit(axis('x')),y=fit(axis('y')),ctm=svg.getScreenCTM(),off=offset();
    if(!x||!y||!ctm||!off||!circles.length)return {calibrated:false,reason:'Need two labeled ticks per axis, visible point IDs and measurable frame transform.',svg:svg.viewBox.baseVal?{width:svg.viewBox.baseVal.width,height:svg.viewBox.baseVal.height}:null};
    const points=circles.map(c=>{const mat=c.getScreenCTM(),screen=new DOMPoint(c.cx.baseVal.value,c.cy.baseVal.value).matrixTransform(mat),u=screen.matrixTransform(ctm.inverse());return {id:c.getAttribute('data-point-id')||c.id||key(c),x:(u.x-x.origin)/x.scale,y:(u.y-y.origin)/y.scale,viewport:{x:screen.x+off.x,y:screen.y+off.y}}});
    return {calibrated:true,units:'math',x,y,matrix:{a:ctm.a,b:ctm.b,c:ctm.c,d:ctm.d,e:ctm.e+off.x,f:ctm.f+off.y},points,tolerance:.02};
  }
  function observe(){
    limited=false;
    const candidates=all(document,'[data-question-id],main,[role=main],.question-content').filter(shown);
    const root=candidates.find(e=>e.matches('[data-question-id]')&&e.querySelector('input,textarea,select,td.responseCell,svg,canvas'))||candidates.find(e=>e.matches('main,[role=main]'))||document.body;
    let elements=all(root,'input,textarea,[role=radio],[role=checkbox],'+answerCells+',ol[data-sortable],[data-rbd-droppable-id],svg,canvas').filter(e=>shown(e)&&safe(e));
    const cells=elements.filter(e=>e.matches(answerCells)&&!(e.closest('td.responseCell,[role=gridcell]')&&e.closest('td.responseCell,[role=gridcell]')!==e));
    // A sheet's floating editor is a representation of its cell, not a new slot
    // or question. Keep identity stable when it appears, moves, or disappears.
    if(cells.some(sheetCell))elements=elements.filter(e=>!e.matches('textarea.jSheetControls_formula,textarea.jSheetInPlaceEdit'));
    const excluded=new Set(elements.filter(e=>!['radio','checkbox'].includes(e.type)&&!e.matches('[role=radio],[role=checkbox]')));
    // Parts. A tab strip inside the question root (the ARIA tab pattern: role=tab, aria-selected, aria-controls) means
    // the question has several separately answered parts and only the selected one is visible. Each tab is reported
    // as a part; the runtime reveals the others by clicking them, one at a time, and observes each while it is visible.
    // Nothing hidden is read here. Tabs whose label is in the forbidden vocabulary are never parts.
    const tabs=all(root,'[role=tab]').filter(t=>shown(t)&&!forbidden.test(name(t))&&!/^(?:next|continue|submit|check)\b/i.test(name(t)));
    const partOf=new Map(),panels=[];
    const parts=tabs.length>=2?tabs.map((t,i)=>{const panel=t.getAttribute('aria-controls')?document.getElementById(t.getAttribute('aria-controls')):null;if(panel){panels.push(panel);partOf.set(panel,'part:'+key(t))}
      return {part_id:'part:'+key(t),label:name(t)||('Part '+(i+1)),selected:t.getAttribute('aria-selected')==='true'||t.matches('.ui-tabs-active,.ui-state-active,.active,[aria-current=true]'),tab:t,disabled:!!t.disabled||t.getAttribute('aria-disabled')==='true'}}):[];
    for(const panel of all(root,'[role=tabpanel]'))if(parts.length&&!panels.includes(panel))panels.push(panel);
    if(parts.length&&!parts.some(p=>p.selected)){const active=panels.find(shown);const owner=active?[...partOf.entries()].find(([pn])=>pn===active):null;if(owner)parts.find(p=>p.part_id===owner[1]).selected=true;}
    // Identity must not change when the student switches tabs, so the identity stem and structure ignore the tab
    // panels' contents; the question TEXT sent to the model still includes the visible panel.
    const identityExcluded=new Set([...excluded,...panels]);
    const stem=renderedText(root,excluded),identityStem=parts.length?renderedText(root,identityExcluded):stem; const position=norm(document.querySelector('[aria-current=step],[aria-current=page],.question-number')?.textContent);
    const platform=root.getAttribute('data-question-id')||'';
    const positionMatch=norm(document.body.innerText).match(/\bQuestion\s+(\d+)\s+(?:of|\/)\s*(\d+)\b/i);
    const enumeration=positionMatch?{index:Number(positionMatch[1]),total:Number(positionMatch[2])}:null;
    // Identity that survives dynamic answer-state text. A platform question id is
    // authoritative and used alone. Without one, use the STABLE answer-control
    // structure (element keys, not their changing labels) plus the navigation
    // position and the feedback-stripped stem -- so a "completed" note, an attempt
    // counter or a "saved" annotation appearing after input does not fork the
    // question into a new key and abandon the verified answer.
    // Transient dropdown editors and expand buttons do not define a question.
    const structure=elements.filter(e=>!e.matches('input[type=button],input[type=submit],input[type=reset]')&&!cells.some(c=>c!==e&&c.contains(e))&&!panels.some(pn=>pn.contains(e))).map(e=>key(e)).join(',');
    const question_key=hash(platform ? location.pathname+'|qid:'+platform
      : location.pathname+'|'+location.hash+'|'+position+'|'+structure+'|'+identityStem.text);
    if(classificationQuestion!==question_key){classificationQuestion=question_key;confirmedSheetValues=new Set();}
    const targets=new Map(),slots=[],groups=new Map();let incomplete=!stem.complete||elements.length>2000;
    const target=e=>{const token=key(e);if(targets.has(token)&&targets.get(token)!==e){incomplete=true;return token}targets.set(token,e);return token};
    const selectedPart=parts.find(p=>p.selected)?.part_id||null;const partFor=e=>{for(const [panel,id] of partOf)if(panel.contains(e))return id;return selectedPart};
    // A slot key is unique across PARTS as well as within one: each tab's sheet here reuses the same cell ids
    // (0_table0_cell_c1_r4 is Operating Expenses on one tab and Cash on the other), so the key carries the part.
    const slotKey=e=>{const pid=parts.length?partFor(e):null;return question_key+'/'+(pid?pid.slice(5)+'/':'')+key(e)};
    const add=(e,kind,label,options=[],current='')=>{const token=target(e);const slot={slot_key:slotKey(e),kind,label:label||kind,options,current,target:token,dom_id:e.id||null,disabled:e.disabled===true||e.getAttribute('aria-disabled')==='true',native:e.tagName==='SELECT',...(parts.length?{part_id:partFor(e)}:{})};slots.push(slot);return slot};
    for(const e of elements){
      if(e.matches('input[type=radio],input[type=checkbox],[role=radio],[role=checkbox]')){
        const type=e.type||e.getAttribute('role'),group=e.closest('fieldset,[role=radiogroup],[role=group]')||root;
        const gid=type+':'+key(group)+':'+(type==='radio'?(e.name||''): '');
        if(!groups.has(gid))groups.set(gid,[]);groups.get(gid).push(e);
      }else if(cells.includes(e)){const detected=interaction(e,cells,target,slotKey(e)),s=add(e,detected.kind,name(e)||norm(e.closest('tr')?.cells[0]?.textContent),e.tagName==='SELECT'?[...e.options].map(o=>norm(o.text)):[],value(e));
        // The editable combobox often precedes the arrow in DOM order. Prefer
        // the explicit menu button; clicking the text editor won't open it.
        s.interaction=detected;if(detected.adapter==='contained_text')s.current=targets.get(detected.editor_target).value;
        s.opening_control=detected.opening_control||{status:'missing',candidates:[]};
        {const combo=e.matches('[role=combobox]')?e:e.querySelector('[role=combobox]');if(combo&&shown(combo))s.combobox=target(combo);}
        s.representations=s.opening_control.status==='resolved'?s.opening_control.candidates.map(c=>c.target):[];
      }else if(e.matches('input:not([type=button]):not([type=submit]):not([type=reset]),textarea')&&!e.closest('td.responseCell,[role=combobox],[role=gridcell]'))add(e,'value',name(e),[],value(e));
      else if(e.matches('ol[data-sortable],[data-rbd-droppable-id]')){const items=[...e.children].filter(shown);const s=add(e,'ordering',name(e),items.map(name),items.map(name));s.items=items.map(n=>({label:name(n),target:target(n)}));}
      else if(e.matches('svg,canvas')&&(e.matches('[data-graph],[role=graph],canvas')||e.querySelector('circle[data-point-id],circle[tabindex]'))){const g=geometry(e),s=add(e,'position',name(e)||'Graph',[],g.points||[]);s.geometry=g;}
    }
    for(const [gid,es] of groups){const group=es[0].closest('fieldset,[role=radiogroup],[role=group]')||es[0];const s=add(group,gid.startsWith('radio')?'choice':'choice_set',name(group)||'Choose',es.map(name),es.filter(e=>e.checked||e.getAttribute('aria-checked')==='true').map(name));
      s.slot_key=question_key+'/'+(parts.length&&partFor(group)?partFor(group).slice(5)+'/':'')+gid;s.choices=es.map(e=>({label:name(e),target:target(e),checked:!!e.checked||e.getAttribute('aria-checked')==='true',disabled:!!e.disabled||e.getAttribute('aria-disabled')==='true'}));}
    const menus=all(document,'[role=listbox] [role=option]').filter(shown).map(e=>{const c=owner(e,cells);return {label:name(e),target:target(e),owner:c?slotKey(c):null,disabled:!!e.disabled||e.getAttribute('aria-disabled')==='true'}});
    const navigation=all(document,'button,a,[role=button],input[type=submit]').filter(shown).map(e=>{
      const label=name(e)||e.value||'';let kind='';
      if(forbidden.test(label))return null;
      if(/^(next(?: question| part)?|continue)$/i.test(label))kind='advance';
      else if(/^(try it!?|check(?: my work| answer)?|submit answer)$/i.test(label))kind='check';
      else if(/^(submit(?: assignment| all answers)?|finish(?: assignment)?|hand in|turn in)$/i.test(label))kind='submit';
      return kind?{kind,label,target:target(e),disabled:!!e.disabled||e.getAttribute('aria-disabled')==='true'}:null}).filter(Boolean);
    const feedback=all(document,'[role=status],[role=alert],output,.feedback,.correct-answer').filter(shown).map(e=>norm(e.innerText)).join(' ');
    const locked=/correct|incorrect|your answer/i.test(feedback)&&slots.length>0&&slots.every(s=>s.disabled||s.choices?.every(c=>c.disabled));
    const page_state=/assignment (?:is )?(?:complete|submitted)/i.test(feedback)?'complete':locked?'locked':'answering';
    const observation_id=crypto.randomUUID();
    const tableContext=readTables(root,excluded);
    const partList=parts.map(p=>({part_id:p.part_id,label:p.label,selected:p.selected,disabled:p.disabled,target:target(p.tab)}));
    last={observation_id,question_key,document_id:doc,question:stem.text||norm(document.title),tables:tableContext.tables,table_context_complete:tableContext.complete,slots,menus,navigation,feedback,page_state,enumeration,parts:partList,
      save_state:/\bsaved\b/i.test(feedback)?'confirmed':/\bsaving\b/i.test(feedback)?'pending':'unavailable',
      grade_state:/incorrect|wrong/i.test(feedback)?'incorrect':/partial/i.test(feedback)?'partial':/correct/i.test(feedback)?'correct':'unknown',
      completeness:{complete:!incomplete&&!limited,note:(incomplete||limited)?'QUESTION_INCOMPLETE: traversal or identity limit; inspect a smaller question.':''},targets,
      frames:all(root,'iframe,frame').filter(shown).map(e=>{const r=e.getBoundingClientRect();let exact=true;for(let n=e;n;n=n.parentElement)if(getComputedStyle(n).transform!=='none')exact=false;return {target:target(e),src:e.src,title:e.title,x:r.x+e.clientLeft,y:r.y+e.clientTop,w:e.clientWidth,h:e.clientHeight,exact:exact&&Math.abs(r.width-e.offsetWidth)<1}}),visual:!!root.querySelector('img,svg,canvas')};
    const {targets:ignored,...publicState}=last;
    return {ok:true,...publicState,origin:location.origin,url:location.href,host:location.host};
  }
  function inspect(m){
    if(m.operation==='identity')return {ok:true,document_id:doc};
    if(m.operation==='observe')return observe();
    if(!last||m.document_id!==doc||m.observation_id!==last.observation_id)return fail('TARGET_STALE','Expired document or observation.');
    const freshQuestion=(()=>{const prior=last;const current=observe();last=prior;return current.question_key})();
    if(freshQuestion!==last.question_key)return fail('TARGET_STALE','Question changed.');
    const e=last.targets.get(m.target);
    if(!e||!shown(e)||!safe(e))return fail('TARGET_MISSING','Target unavailable or excluded.');
    if(m.expected_menu_owner){const owners=last.slots.filter(s=>s.kind==='selection'),cells=owners.map(s=>last.targets.get(s.target)),cell=owner(e,cells);
      // The owning cell is named by its RECORDED slot key -- the one spelling every other check uses (it carries the
      // part since 0.10.28). Rebuilding the name by hand here compared two spellings of the same cell and refused
      // every dropdown inside a multi-part question with 'owner changed' (M3-2, 1:38 PM).
      const actual=cell?owners.find(s=>last.targets.get(s.target)===cell)?.slot_key||null:null;
      if(actual!==m.expected_menu_owner)return fail('WRONG_MENU_OWNER','Dropdown owner changed before input.',{expected:m.expected_menu_owner,actual});}
    if(m.expected_value_owner){
      const prior=last;observe();const current=last;last=prior;
      const slot=current.slots.find(s=>s.slot_key===m.expected_value_owner);
      if(!slot||slot.kind!=='value'||slot.interaction?.editor_target!==m.target||current.targets.get(m.target)!==e)return fail('TARGET_STALE','Text editor no longer belongs to the intended cell.');
    }
    if(m.operation==='inspect_options'){
      if(!last.slots.some(s=>s.kind==='selection'&&s.target===m.target))return fail('GUARD_REJECTED','Option inspection requires a selection slot.');
      const cells=last.slots.filter(s=>s.kind==='selection').map(s=>last.targets.get(s.target));
      const register=n=>{const token=key(n);if(last.targets.has(token)&&last.targets.get(token)!==n)throw new Error('Ambiguous opening-control identity');last.targets.set(token,n);return token};
      return {ok:true,...readOptions(e),opening_control:openingControls(e,cells,register)};
    }
    if(m.operation==='inspect_svg_geometry')return {ok:true,geometry:geometry(e)};
    if(m.operation==='inspect_scroll_container')return {ok:true,...scrollInfo(e)};
    if(!['inspect_frame','inspect_slot','inspect_options','read_control_state','measure_target'].includes(m.operation))return fail('GUARD_REJECTED','Unknown packaged inspection.');
    const box=rect(e),s=last.slots.find(s=>s.target===m.target);
    let point=m.point||{x:box.local.x+box.local.w/2,y:box.local.y+box.local.h/2};
    const hitAt=p=>{let h=document.elementFromPoint(p.x,p.y);while(h?.shadowRoot?.elementFromPoint(p.x,p.y))h=h.shadowRoot.elementFromPoint(p.x,p.y);return h};
    let hit=hitAt(point);
    const scroll=scrollInfo(e,point);
    if(m.activation_only&&!scroll.clipped&&point.x>=0&&point.x<innerWidth&&point.y>=0&&point.y<innerHeight){
      const b=box.local,candidates=[point,{x:b.x+3,y:b.y+b.h/2},{x:b.x+b.w-3,y:b.y+b.h/2},{x:b.x+b.w/2,y:b.y+3},{x:b.x+b.w/2,y:b.y+b.h-3}];
      const safePoint=candidates.find(p=>{const h=hitAt(p),interactive=h?.closest('input,textarea,button,select,a,[contenteditable=true],[role=button],[role=combobox],[role=option]');return h&&(h===e||e.contains(h))&&(!interactive||interactive===e)});
      if(!safePoint)return fail('TARGET_MISSING','No unobstructed cell activation point outside its editor and buttons.');
      point=safePoint;hit=hitAt(point);
    }
    const actionable=shown(e)&&!e.disabled&&e.getAttribute('aria-disabled')!=='true';
    const focused=(e.getRootNode().activeElement||document.activeElement)===e;
    const describe=n=>n?{tag:n.tagName,id:n.id,role:n.getAttribute('role'),type:n.getAttribute('type'),inputmode:n.getAttribute('inputmode'),label:name(n).slice(0,240),class_name:String(n.className||'').slice(0,240)}:null;
    const selection=e.matches('input,textarea')&&typeof e.selectionStart==='number'?{start:e.selectionStart,end:e.selectionEnd,length:String(e.value??'').length}:undefined;
    return {ok:true,...box,actionable,hit:!!hit&&(hit===e||e.contains(hit)||[...(e.labels||[])].some(l=>l===hit||l.contains(hit))),focused,tag:e.tagName,value:value(e),selection,
      target_info:describe(e),hit_info:describe(hit),binding:binding(e),click_point:point,scroll,
      visibility:scroll.clipped?'offscreen_or_clipped':hit&&(hit===e||e.contains(hit))?'visible':'occluded',
      checked:!!e.checked||e.getAttribute('aria-checked')==='true',options:e.tagName==='SELECT'?[...e.options].map(o=>({label:norm(o.text),selected:o.selected,disabled:o.disabled||o.parentElement.disabled===true})):undefined,
      slot:s?.slot_key,interaction:s?.interaction,selectedIndex:e.tagName==='SELECT'?e.selectedIndex:undefined};
  }
  globalThis.__assignmentPlannerInspector=true;
  chrome.runtime.onMessage.addListener((m,sender,reply)=>{if(m.type!=='planner_inspect')return false;try{const result=inspect(m);const bytes=new TextEncoder().encode(JSON.stringify(result)).length;
    if(m.operation!=='observe'&&bytes>16384)reply(fail('QUESTION_INCOMPLETE','Inspection exceeds 16 KB; narrow its scope.'));
    else if(bytes>100000)reply(fail('QUESTION_INCOMPLETE','Observation exceeds 100 KB; narrow its scope.'));
    else reply(result);}catch{reply(fail('FRAME_UNREADABLE','Inspection could not read this frame.'));}return true});
})();
