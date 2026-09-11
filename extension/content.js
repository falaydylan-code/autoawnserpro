/* Runs inside the student's assignment tab.

   Two jobs, and nothing else: describe what is on the page, and carry out one
   named action. It makes no decisions and holds no strategy -- the model does
   that, from what this sends. Element references are rebuilt on every
   observation and never reused across steps, so a ref can never point at
   something that has since moved. */

(() => {
  if (window.__assignmentLabContent) return;
  window.__assignmentLabContent = true;

  let refs = new Map();

  const INTERACTIVE = [
    'input', 'textarea', 'select', 'button', 'a[href]',
    '[role=button]', '[role=radio]', '[role=checkbox]', '[role=textbox]',
    '[role=combobox]', '[role=link]', '[contenteditable=""]', '[contenteditable=true]'
  ].join(',');

  // Never describe these to the model, so it can never be asked to fill one.
  const FORBIDDEN_INPUT_TYPES = new Set(['password', 'hidden', 'file', 'image']);
  const SENSITIVE_HINT = /pass|card|cvv|cvc|ssn|social.?security|credit|iban|routing|account.?number/i;

  function visible(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return false;
    if (rect.bottom < 0 || rect.top > innerHeight * 3) return false;
    const style = getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity) > 0.05;
  }

  /* A worksheet table puts each answer box alone in its own cell, so the usual
     label lookups all come back empty and every box looks identical. Fall back
     to the row it sits in and the column it sits under, which is exactly how a
     person tells them apart. */
  function tableContext(el) {
    const cell = el.closest('td, th');
    const row = cell && cell.parentElement;
    if (!row || !row.children) return '';

    const cells = [...row.children];
    const label = cells
      .map((c) => (c === cell ? '' : c.innerText.trim()))
      .find((text) => text.length > 0) || '';

    let column = '';
    const table = el.closest('table');
    const headerRow = table && table.querySelector('tr');
    if (headerRow && headerRow !== row) {
      const heading = headerRow.children[cells.indexOf(cell)];
      if (heading) column = heading.innerText.trim();
    }

    if (!label && !column) return '';
    return (column ? column + ' for: ' : '') + label.slice(0, 180);
  }

  function accessibleName(el) {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    if (el.labels && el.labels[0]) return el.labels[0].innerText.trim();
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const target = document.getElementById(labelledby);
      if (target) return target.innerText.trim();
    }
    const own = (el.innerText || el.value || el.placeholder || el.title || '').trim();
    if (own) return own;

    const inTable = tableContext(el);
    if (inTable) return inTable;

    const parentText = (el.parentElement?.innerText || '').trim();
    if (parentText) return parentText.slice(0, 120);

    // Last resort: the nearest text before it, which is usually its prompt.
    let node = el.previousElementSibling;
    while (node) {
      const text = (node.innerText || '').trim();
      if (text) return text.slice(0, 120);
      node = node.previousElementSibling;
    }
    return '';
  }

  function role(el) {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') return (el.type || 'text') === 'text' ? 'textbox' : el.type;
    if (tag === 'a') return 'link';
    if (tag === 'textarea') return 'textbox';
    return tag;
  }

  // Controls that end the student's work. Refused in the page itself, so no
  // prompt wording and no model mistake can reach them.
  const HANDS_IN = /\b(?:submit\s+(?:the\s+)?(?:assignment|quiz|test|exam|work)|exit\s+assignment|finish\s+(?:assignment|attempt|quiz|test|exam)|hand\s+in|turn\s+in)\b/i;

  function endsTheAssignment(el) {
    return HANDS_IN.test(accessibleName(el) || '');
  }

  function sensitive(el) {
    if (el.tagName.toLowerCase() === 'input' && FORBIDDEN_INPUT_TYPES.has(el.type)) return true;
    const haystack = [el.name, el.id, el.getAttribute('autocomplete'), el.placeholder,
                      el.getAttribute('aria-label')].filter(Boolean).join(' ');
    return SENSITIVE_HINT.test(haystack);
  }

  function observe() {
    hideUI();
    refs = new Map();
    const elements = [];
    let ref = 1;
    for (const el of document.querySelectorAll(INTERACTIVE)) {
      if (!visible(el) || sensitive(el)) continue;
      if (el.closest('#__assignment_lab_cursor')) continue;
      const rect = el.getBoundingClientRect();
      refs.set(ref, el);
      elements.push({
        ref,
        role: role(el),
        name: accessibleName(el).slice(0, 200),
        value: (el.value !== undefined && el.type !== 'password' ? String(el.value) : '').slice(0, 200),
        checked: el.checked === true,
        disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
        box: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
      });
      ref += 1;
      if (ref > 300) break;
    }
    return {
      elements,
      text: (document.body?.innerText || '').replace(/\n{3,}/g, '\n\n').slice(0, 20000),
      host: location.host,
      title: document.title.slice(0, 200),
      // Used to tell whether an action actually changed anything.
      digest: (document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 4000)
    };
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

  async function act(action) {
    const el = refs.get(Number(action.ref));
    if (!el) return { ok: false, detail: 'That element is no longer on the page. Re-observing.' };
    if (sensitive(el)) return { ok: false, detail: 'Refused: that field looks like a credential or payment field.' };
    if (action.action === 'click' && endsTheAssignment(el)) {
      return { ok: false, detail: `Refused: "${accessibleName(el).slice(0, 40)}" hands in the assignment. That stays yours.` };
    }
    if (el.disabled) return { ok: false, detail: 'That control is disabled.' };

    el.scrollIntoView({ block: 'center', behavior: reduced ? 'instant' : 'smooth' });
    await settle(reduced ? 120 : 320);
    await moveTo(el, describe(action));
    await pressEffect();

    if (action.action === 'fill') {
      const setter = Object.getOwnPropertyDescriptor(
        el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value');
      el.focus();
      if (el.isContentEditable) {
        el.textContent = action.text;
      } else if (setter && setter.set) {
        setter.set.call(el, action.text);           // React-friendly value set
      } else {
        el.value = action.text;
      }
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      await settle(150);
      const readBack = el.isContentEditable ? el.textContent : el.value;
      return readBack === action.text
        ? { ok: true, detail: `Field now reads "${String(readBack).slice(0, 80)}".` }
        : { ok: false, detail: `The value did not stick. The field reads "${String(readBack).slice(0, 80)}".` };
    }

    if (action.action === 'click') {
      el.click();
      await settle(400);
      return { ok: true, detail: 'Clicked.' };
    }

    if (action.action === 'select') {
      if (el.tagName !== 'SELECT') return { ok: false, detail: 'That element is not a dropdown.' };
      const option = [...el.options].find((o) => o.text.trim() === action.option || o.value === action.option);
      if (!option) return { ok: false, detail: 'No option with that label.' };
      el.value = option.value;
      el.dispatchEvent(new Event('change', { bubbles: true }));
      await settle(200);
      return { ok: true, detail: `Selected "${option.text.trim()}".` };
    }

    return { ok: false, detail: 'Unsupported action.' };
  }

  // Exposed so the cursor and the observer can be exercised on a plain page,
  // outside the extension, without duplicating any of this code in a test.
  window.__assignmentLab = { observe, act, hideUI, moveTo, pressEffect, describe };

  if (!globalThis.chrome?.runtime?.onMessage) return;

  chrome.runtime.onMessage.addListener((message, _sender, reply) => {
    if (message.type === 'observe') {
      reply(observe());
      return true;
    }
    if (message.type === 'digest') {
      reply({ digest: (document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 4000) });
      return true;
    }
    if (message.type === 'cursor_off') {
      hideUI();
      reply({ ok: true });
      return true;
    }
    if (message.type === 'act') {
      if (message.action.action === 'scroll') {
        scrollBy({ top: message.action.direction === 'up' ? -innerHeight * 0.8 : innerHeight * 0.8, behavior: 'instant' });
        setTimeout(() => reply({ ok: true, detail: 'Scrolled.' }), 350);
        return true;
      }
      act(message.action).then(reply);
      return true;
    }
    return false;
  });
})();
