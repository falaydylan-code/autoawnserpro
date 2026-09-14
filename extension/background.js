/* The worker owns the run. The model proposes one move per turn; everything
   here decides whether that move is allowed, performs it with real browser
   input on the ONE tab the run is bound to, and refuses to believe anything
   about the result that the page itself (and, by default, a fresh screenshot)
   does not confirm.

   Reading order: settings and state -> observing -> browser input helpers ->
   evidence and verification -> executeAction (the gate) -> the run loop. */
import './coverage.js';
import './visual.js';
import './planner_runtime.js';

const DEFAULT_BACKEND = 'https://positive-tranquility-production-9fdc.up.railway.app';
const PROTOCOL = 3;
const REQUIRED_FEATURES = ['parts', 'ordering', 'visual_input', 'visual_verification', 'browser_input', 'page_states'];

// Bounded retries, not ceilings. There is no limit on how many questions or
// turns a healthy run may take; these stop a run that is not going anywhere.
const STALL_LIMIT = 6;            // consecutive turns with no verified progress
const NAV_BUDGET = 8;             // consecutive turns hunting for the next question
const SHIFT_LIMIT = 4;            // page changed under the model, in a row
const VISUAL_FAILURES = 3;        // screenshot checks that did not confirm one part
const INTERACTION_RETRIES = 3;    // the same interaction failing the same way

const state = {running: false, stopRequested: false, tabId: null, steps: 0, questions: 0, cost: 0, progress: '', pageState: '', log: []};

let coverage = new AssignmentCoverage.Coverage();
let decisionAbort = null, runToken = '', runUrl = '', runTitle = '', runSite = '';
let decisionSnapshot = null, pendingMenu = null, lastOpened = null, lastCapture = 0;
let doubleCheck = false;
const visualFailures = new Map();
const interactionFailures = new Map();
let refMap = new Map(), frameIds = [0], activeFrameIds = [], frameOffsets = new Map(), runOrigin = '', actionFrameId = 0;
const injectState = {url: ''};   // the document the content scripts were injected into

// A same-site full-document navigation (Next loading a new page) destroys the
// injected content scripts and renumbers frames. Every observe goes through
// this. The site boundary is enforced FIRST, before injecting into or reading
// the page, so a control that redirects to another site is stopped before its
// content is ever read or screenshotted -- not one iteration later. Then it
// re-injects when the URL moved since injection, and once more if a read still
// finds no frame; a dead page fails after that retry.
async function observeResilientFor(tabId) {
  const now = await boundTab(tabId);
  if (now.url !== injectState.url) { await pause(400); await boundTab(tabId); await injectAll(tabId); injectState.url = now.url; runOrigin = new URL(now.url).origin; emit({kind: 'info', message: 'The page navigated; re-reading it.'}); }
  try { return await observeAllFrames(tabId); }
  catch (e) {
    if (!/No assignment frame/.test(e.message)) throw e;
    const settled = await boundTab(tabId);           // boundary again before the retry inject
    await pause(500); await injectAll(tabId); injectState.url = settled.url; runOrigin = new URL(settled.url).origin;
    return await observeAllFrames(tabId);
  }
}

const norm = s => String(s || '').normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim();
const pause = ms => new Promise(r => setTimeout(r, ms));
const stopped = () => state.stopRequested;

async function settings() {
  const s = await chrome.storage.local.get(['backend', 'token', 'model', 'note', 'advance', 'auto_submit', 'badges', 'double_check', 'spend_limit', 'planner_enabled', 'check_work']);
  return {
    planner_enabled: s.planner_enabled === true, check_work: s.check_work === true,
    backend: (s.backend || DEFAULT_BACKEND).replace(/\/+$/, ''), token: s.token || '', model: s.model || '', note: s.note || '',
    advance: s.advance === true, auto_submit: s.auto_submit === true, badges: s.badges !== false, double_check: s.double_check !== false,
    spend_limit: Number.isFinite(Number(s.spend_limit)) && Number(s.spend_limit) > 0 ? Number(s.spend_limit) : 2.0,
  };
}
function snapshot() { return {running: state.running, steps: state.steps, questions: state.questions, cost: state.cost, progress: state.progress, pageState: state.pageState, runUrl, runTitle}; }
function emit(entry) {
  const row = {time: new Date().toLocaleTimeString(), ...entry};
  state.log.push(row); if (state.log.length > 400) state.log.shift();
  chrome.runtime.sendMessage({type: 'log', row, state: snapshot()}).catch(() => {});
}

// ---------------------------------------------------------------- the tab

// The run belongs to the tab the student pressed Start on. Same-site
// navigation inside the assignment is allowed (connect.x.com -> newconnect.x.com);
// anything else ends the run rather than following it.
// Registrable domain, aware of the common multi-label public suffixes so that
// two tenants under github.io / co.uk / edu.au are NOT treated as one site.
// Not the whole Public Suffix List, but the shapes courseware and the reported
// attacks actually use; anything unlisted falls back to the last two labels.
const MULTI_SUFFIX = new Set(['co.uk','ac.uk','org.uk','gov.uk','com.au','edu.au','gov.au','net.au','co.nz','ac.nz','co.za','com.br','co.in','ac.in','edu.in','github.io','githubusercontent.com','web.app','firebaseapp.com','pages.dev','vercel.app','netlify.app','herokuapp.com','instructure.com','blackboard.com']);
function siteOf(url) {
  try {
    const h = new URL(url).hostname.toLowerCase().split('.');
    if (h.length <= 2) return h.join('.');
    const lastTwo = h.slice(-2).join('.'), lastThree = h.slice(-3).join('.');
    return (MULTI_SUFFIX.has(lastTwo) && h.length >= 3) ? lastThree : lastTwo;
  } catch { return ''; }
}
async function boundTab(tabId) {
  let tab; try { tab = await chrome.tabs.get(tabId); } catch { throw new Error('The assignment tab was closed. The run is over.'); }
  if (!/^https?:/.test(tab.url || '')) throw new Error('The assignment tab moved to a page the agent cannot read (' + (tab.url || 'no URL') + ').');
  if (siteOf(tab.url) !== runSite) throw new Error('The tab moved to a different site (' + new URL(tab.url).host + '). Run stopped rather than following it.');
  return tab;
}
chrome.tabs.onRemoved.addListener(tabId => { if (state.running && tabId === state.tabId) { state.stopRequested = true; emit({kind: 'error', message: 'The assignment tab was closed. Stopping.'}); } });
chrome.debugger.onDetach.addListener(({tabId}, reason) => {
  if (state.running && tabId === state.tabId && !state.stopRequested) { state.stopRequested = true; emit({kind: 'error', message: 'Chrome ended the browser-input session (' + reason + '). If you pressed Cancel on the debugging bar, press Start to continue.'}); }
});

// ------------------------------------------------------------- observing

async function injectAll(tabId) {
  const results = await chrome.scripting.executeScript({target: {tabId, allFrames: true}, files: ['content.js']});
  frameIds = results.map(r => r.frameId);
  await Promise.all(frameIds.map(frameId => chrome.tabs.sendMessage(tabId, {type: 'reset'}, {frameId}).catch(() => {})));
  return frameIds;
}

async function observeAllFrames(tabId) {
  const merged = {elements: [], text: '', host: '', digest: '', warnings: [], part_tabs: [], question_hint: '', page_state: 'answering', feedback: '', attempts_left: null};
  refMap = new Map(); activeFrameIds = []; frameOffsets = new Map(); let next = 1;
  for (const frameId of frameIds) {
    let page;
    try { page = await chrome.tabs.sendMessage(tabId, {type: 'observe'}, {frameId}); }
    catch { merged.warnings.push('Frame ' + frameId + ' unavailable; re-open the page if required content is missing.'); continue; }
    if (!page) continue;
    if (runOrigin && page.origin !== runOrigin && siteOf(page.origin) !== siteOf(runOrigin)) { merged.warnings.push('A different-site frame is excluded from control.'); continue; }
    activeFrameIds.push(frameId); merged.host ||= page.host;
    merged.text += (merged.text ? '\n\n' : '') + page.text;
    merged.digest += JSON.stringify([frameId, page.digest]);
    merged.warnings.push(...(page.warnings || []));
    if (page.question_hint) merged.question_hint += frameId + ':' + page.question_hint;
    merged.part_tabs.push(...(page.part_tabs || []).map(t => ({...t, key: frameId + ':' + t.key})));
    // The top frame's state wins; a subframe reports feedback only if the top has none.
    if (frameId === 0 || merged.page_state === 'answering') { if (page.page_state && page.page_state !== 'answering') merged.page_state = page.page_state; merged.feedback ||= page.feedback || ''; if (page.attempts_left != null) merged.attempts_left = page.attempts_left; }
    if (!merged.elements.length) actionFrameId = frameId;
    const offset = page.frameOffset || {x: 0, y: 0, exact: false};
    frameOffsets.set(frameId, offset);
    const localToGlobal = new Map(page.elements.map(e => [e.ref, next++]));
    for (const el of page.elements) {
      if (merged.elements.length >= 400) { merged.warnings.push('Observation exceeds 400 elements; some controls are not listed.'); break; }
      const ref = localToGlobal.get(el.ref), key = frameId + ':' + el.key;
      refMap.set(ref, {frameId, ref: el.ref, key, localKey: el.key});
      const box = el.box && offset.exact !== false ? {...el.box, x: el.box.x + offset.x, y: el.box.y + offset.y} : null;
      merged.elements.push({...el, ref, key, qid: el.qid ? frameId + ':' + el.qid : '', group: localToGlobal.get(el.group) || null,
        list_ref: localToGlobal.get(el.list_ref) || null, owner_ref: localToGlobal.get(el.owner_ref) || null, box});
    }
  }
  merged.warnings = [...new Set(merged.warnings)].slice(0, 30);
  if (!activeFrameIds.length) throw new Error('No assignment frame can be read. Reload the page and grant site access.');
  state.pageState = merged.page_state;
  return merged;
}

async function digestNow(tabId) {
  let combined = '';
  for (const frameId of activeFrameIds) { try { const r = await chrome.tabs.sendMessage(tabId, {type: 'digest'}, {frameId}); combined += JSON.stringify([frameId, r.digest]); } catch { combined += JSON.stringify([frameId, 'gone']); } }
  return combined;
}
// "Settled" means two identical readings after a change, not the first change.
async function waitForEffect(tabId, prior, budgetMs = 4000) {
  const start = Date.now(); let last = null, identical = 0;
  while (Date.now() - start < budgetMs && !state.stopRequested) {
    await pause(180);
    const now = await digestNow(tabId);
    identical = now === last ? identical + 1 : 0; last = now;
    if (now !== prior && identical >= 2) return true;
  }
  return false;
}

// ---------------------------------------------------------- browser input

// The visible green cursor mirrors the browser pointer. Top frame only: its
// coordinates are the viewport's.
async function cursor(tabId, pt, label, held) { await chrome.tabs.sendMessage(tabId, {type: 'cursor', x: pt.x, y: pt.y, label, held, instant: true}, {frameId: 0}).catch(() => {}); }
const centre = box => ({x: Math.round(box.x + box.w / 2), y: Math.round(box.y + box.h / 2)});

// Scroll a ref into view and return where it is NOW, in viewport coordinates.
// null when the frame's offset cannot be measured -- then browser input has no
// safe coordinate and the caller falls back to the DOM path for that one move.
async function reveal(tabId, el) {
  const mapped = refMap.get(el.ref); if (!mapped) return null;
  let r; try { r = await chrome.tabs.sendMessage(tabId, {type: 'reveal', ref: mapped.ref}, {frameId: mapped.frameId}); } catch { return null; }
  if (!r?.ok || !r.visible) return null;
  // Use the offset the frame measured AFTER scrolling, not the one cached at
  // observation time; scrolling may have moved the iframe. Top frame offset is
  // {0,0}. A frame that cannot place itself exactly has no safe coordinate.
  const offset = mapped.frameId === 0 ? {x: 0, y: 0, exact: true} : (r.offset || frameOffsets.get(mapped.frameId));
  if (!offset || offset.exact === false) return null;
  return {...r, box: {...r.box, x: r.box.x + offset.x, y: r.box.y + offset.y}, frameId: mapped.frameId, localRef: mapped.ref};
}

// Every point handed to the browser is checked in the page first: inside the
// viewport, not over a navigation, submission, sensitive or off-site control.
// A refused point is returned to the model to re-aim, never thrown.
async function browserInput(tabId, start, end, {region = false} = {}) {
  for (const point of [start, end].filter(Boolean)) {
    const v = await chrome.tabs.sendMessage(tabId, {type: 'viewport'}, {frameId: 0});
    if (point.x < 0 || point.y < 0 || point.x >= v.width || point.y >= v.height) return {ok: false, detail: 'Target is outside the viewport. Scroll and observe again.'};
    const guard = await chrome.tabs.sendMessage(tabId, {type: 'visual_guard', point, region}, {frameId: 0});
    if (!guard.ok) return {ok: false, detail: guard.detail + ' Look at the screenshot again and aim at the answer control itself.'};
  }
  await cursor(tabId, start, end ? 'drag' : 'click', !!end);
  try { return await AssignmentVisual.input(tabId, start, end, stopped); }
  finally { await cursor(tabId, end || start, null, false); }
}
async function clickAt(tabId, pt, label, count = 1) {
  await cursor(tabId, pt, label, false);
  return AssignmentVisual.click(tabId, pt, {count}, stopped);
}

// The DOM path, used only where browser input has no coordinate to aim at
// (an unmeasurable frame) or where a real gesture demonstrably did not take.
async function actOnRef(tabId, action, permit = {}) {
  if (state.stopRequested) return {ok: false, detail: 'Stopped before action.'};
  const payload = {...action}; let frame = actionFrameId;
  if (action.action !== 'scroll') {
    const target = refMap.get(action.ref); if (!target) return {ok: false, detail: 'That element is no longer listed. Re-observe.'};
    frame = target.frameId;
    for (const field of ['ref', 'to']) if (action[field] != null) { const mapped = refMap.get(action[field]); if (!mapped || mapped.frameId !== frame) return {ok: false, detail: 'Cross-frame or missing drag destination refused.'}; payload[field] = mapped.ref; }
  }
  try { const out = await chrome.tabs.sendMessage(tabId, {type: 'act', action: payload, permit}, {frameId: frame}); return {...out, method: 'dom'}; }
  catch { return {ok: false, detail: 'The frame went away before the action landed. Re-open the page.'}; }
}

// ------------------------------------------------------ evidence, witnesses

// Two witnesses. The DOM reads the control back; the screenshot shows what the
// student sees. With double-checking on, a part is verified only when both
// agree. Where the DOM cannot read the control, the screenshot decides alone.
// A DOM `false` always wins: the value is not there.
function settle(part) {
  if (part.domVerified === false) { part.verified = false; return; }
  if (part.domVerified === null || part.domVerified === undefined) { part.verified = part.visualConfirmed === true; return; }
  part.verified = doubleCheck ? (part.visualConfirmed === true || part.visualConfirmed === 'inconclusive') : true;
}
async function refreshEvidence(tabId, page) {
  coverage.observe(page);
  for (const q of coverage.questions.values()) for (const part of q.parts.values()) {
    if (part.retired) continue;
    if (!part.target_key || (part.answer === '' && !part.source_label)) continue;
    const mapped = [...refMap.values()].find(e => e.key === part.target_key);
    if (!mapped) continue;                                  // a verified part may sit on a hidden tab
    const evidence = {key: mapped.localKey, answer: part.source_label || part.answer, kind: part.evidence?.kind || (part.source_key || page.elements.find(e => e.key === part.target_key)?.drag === 'target' ? 'drag' : 'fill')};
    if (part.kind === 'ordering') { evidence.kind = 'ordering'; evidence.order_keys = (part.order_keys || []).map(k => k.slice(k.indexOf(':') + 1)); }
    if (part.source_key) evidence.source_key = part.source_key.slice(part.source_key.indexOf(':') + 1);
    let observed; try { observed = await chrome.tabs.sendMessage(tabId, {type: 'verify', evidence}, {frameId: mapped.frameId}); } catch { continue; }
    if (observed?.visible) {
      part.domEvidence = observed;
      if (observed.supported !== false) { part.domVerified = observed.verified === true; if (part.domVerified) { part.entered = true; part.everEntered = true; } }
      else part.domVerified = null;                          // the DOM cannot read this control
      settle(part);
    }
  }
  state.progress = coverage.summary();
}

// A screenshot of the bound tab through the debugger: works whether or not the
// tab is in front. captureVisibleTab is the fallback only while the tab is
// active, and a missing screenshot stops the turn -- no blind model call.
async function capture(tabId, page, badgeEnabled) {
  const delay = 350 - (Date.now() - lastCapture); if (delay > 0) await pause(delay); lastCapture = Date.now();
  // The green cursor is for the student, not the model: it is hidden for the
  // picture, exactly as observe() hides it, so two captures of an unchanged
  // page compare equal.
  await Promise.all(activeFrameIds.map(frameId => chrome.tabs.sendMessage(tabId, {type: 'hide_cursor'}, {frameId}).catch(() => {})));
  try {
    if (badgeEnabled) for (const frameId of activeFrameIds) {
      const entries = page.elements.filter(e => e.box).map(e => ({e, m: refMap.get(e.ref)})).filter(v => v.m?.frameId === frameId).map(v => ({ref: v.m.ref, globalRef: v.e.ref}));
      await chrome.tabs.sendMessage(tabId, {type: 'badges', entries}, {frameId}).catch(() => {});
    }
    try {
      // A capture taken the instant after input can be a transitional frame
      // (focus ring, checked state still painting). Return a settled one: two
      // consecutive captures that agree, so a snapshot and its re-check match.
      let shot = await AssignmentVisual.screenshot(tabId), hash = await AssignmentVisual.pixels(shot.dataUrl);
      for (let i = 0; i < 3; i++) {
        await pause(70);
        const again = await AssignmentVisual.screenshot(tabId), h2 = await AssignmentVisual.pixels(again.dataUrl);
        if (h2 === hash) return again.dataUrl;
        shot = again; hash = h2;
      }
      return shot.dataUrl;
    }
    catch (cdpError) {
      const tab = await chrome.tabs.get(tabId);
      if (!tab.active) throw new Error('the debugger screenshot failed (' + cdpError.message + ') and the tab is not in front, so Chrome offers no other way to see it');
      const shot = await chrome.tabs.captureVisibleTab(tab.windowId, {format: 'png'});
      if (!shot) throw new Error('empty screenshot');
      return shot;
    }
  } catch (e) { throw new Error('Screenshot unavailable: ' + e.message + '. No blind model call was made.'); }
  finally { await Promise.all(activeFrameIds.map(frameId => chrome.tabs.sendMessage(tabId, {type: 'badges_off'}, {frameId}).catch(() => {}))); }
}

async function compatible(config) {
  const r = await fetch(config.backend + '/api/capabilities', {signal: decisionAbort?.signal}).catch(() => null);
  if (!r || !r.ok) throw new Error('Backend update required: this extension (' + chrome.runtime.getManifest().version + ') needs protocol ' + PROTOCOL + ' and the backend did not answer /api/capabilities. Deploy the matching backend. No model call was made.');
  const c = await r.json();
  if (c.protocol !== PROTOCOL && !c.supported_protocols?.includes(PROTOCOL)) throw new Error('Backend update required: the backend speaks protocol ' + c.protocol + ', this extension needs ' + PROTOCOL + '. Deploy the matching backend. No model call was made.');
  const missing = REQUIRED_FEATURES.filter(x => !c.features?.includes(x));
  if (missing.length) throw new Error('Backend update required: missing ' + missing.join(', ') + '. No model call was made.');
}

async function makeSnapshot(tabId, page) {
  const viewport = await chrome.tabs.sendMessage(tabId, {type: 'viewport'}, {frameId: 0});
  const screenshot = await capture(tabId, page, false);
  return {id: crypto.randomUUID(), viewport, screenshot, hash: await AssignmentVisual.pixels(screenshot), digest: page.digest, url: (await chrome.tabs.get(tabId)).url, tabId};
}
// A coordinate the model chose is only valid against the exact picture it saw.
async function currentSnapshot(tabId, snap, page) {
  if (state.stopRequested) throw new Error('Stopped before browser input.');
  if (snap.tabId !== undefined && snap.tabId !== tabId) throw new Error('Stale visual observation: that screenshot is of a different tab.');
  const tab = await chrome.tabs.get(tabId), v = await chrome.tabs.sendMessage(tabId, {type: 'viewport'}, {frameId: 0});
  if (tab.url !== snap.url || JSON.stringify(v) !== JSON.stringify(snap.viewport) || await digestNow(tabId) !== snap.digest) throw new Error('Stale visual observation: page, scroll or viewport changed. Read again.');
  if (await AssignmentVisual.pixels(await capture(tabId, page, false)) !== snap.hash) throw new Error('Stale screenshot: visible page changed. Read again.');
}

async function verifyVisual(tabId, page, part, config) {
  const snap = await makeSnapshot(tabId, page);
  const result = await decide(config, {screenshot: snap.screenshot, host: page.host, elements: [], text: '', phase: 'verify', observation_id: snap.id,
    verification: {part_id: part.id, what: part.what, kind: part.kind || 'value'}, model: config.model});
  state.steps++; state.cost += result.cost || 0;
  emit({kind: 'think', message: 'Verify ' + part.what, detail: result.action.reason, raw: result.raw, cost: result.cost, tokens: `${result.input_tokens || 0} in / ${result.output_tokens || 0} out`});
  await currentSnapshot(tabId, snap, page);
  const a = result.action;
  const sane = a.action === 'verify' && a.part_id === part.id && a.observation_id === snap.id;
  // What the model READ, judged loosely: a value reported inside a sentence
  // ("Statement = Income Statement") still reads the value. Its status is
  // taken as: confirmed/uncertain-but-read = agrees, mismatch or a different
  // value read = contradicts, nothing readable = inconclusive.
  let reads, contradicts;
  if (part.kind === 'ordering') {
    const seq = (a.observed_sequence || []).map(norm), want = (part.sequence || []).map(norm);
    reads = seq.length > 0 && JSON.stringify(seq) === JSON.stringify(want);
    contradicts = a.status === 'mismatch' || (seq.length > 0 && !reads);
  } else {
    const seen = norm(a.observed), want = norm(part.answer);
    reads = !!want && !!seen && (seen === want || seen.includes(want));
    contradicts = a.status === 'mismatch' || (!!seen && !reads && !/^(?:empty|blank|none|unclear|unreadable|not (?:visible|readable)|cannot|can't|n\/a)/i.test(seen));
  }
  const matches = sane && reads && a.status !== 'mismatch';
  // An inconclusive witness ("I can't tell") does not veto a DOM witness that
  // read the value; a contradicting one does.
  part.visualConfirmed = matches ? true : (sane && !contradicts && part.domVerified === true ? 'inconclusive' : false);
  part.visual = true; settle(part);
  if (part.verified) { part.entered = true; part.everEntered = true; visualFailures.delete(part.id); }
  else if (!matches && part.visualConfirmed !== 'inconclusive') { const n = (visualFailures.get(part.id) || 0) + 1; visualFailures.set(part.id, n); if (n >= VISUAL_FAILURES) throw new Error('The screenshot did not confirm "' + part.what + '" after ' + (VISUAL_FAILURES - 1) + ' recovery attempts (it shows "' + (a.observed || '') + '"). Inspect that field yourself.'); }
  const witness = part.domVerified == null ? 'Screenshot' : (part.visualConfirmed === 'inconclusive' ? 'DOM (screenshot inconclusive)' : 'DOM and screenshot');
  emit({kind: part.verified ? 'progress' : 'warn', message: (part.verified ? witness + ' verified: ' : (matches ? 'Screenshot agreed but the DOM does not: ' : 'Screenshot did not confirm: ')) + part.what, detail: a.observed || (a.observed_sequence || []).join(' → ')});
  return part.verified;
}

// ---------------------------------------------------------- the gate

const ANSWER_ROLES = ['radio', 'checkbox', 'option', 'switch'];
function answering(action, page) {
  const e = page.elements.find(e => e.ref === action.ref);
  return ['fill', 'select', 'drag', 'reorder'].includes(action.action) || (action.action === 'click' && (ANSWER_ROLES.includes(e?.role) || (e?.role === 'button' && e?.choice)));
}

// The model said `select` on a custom menu, not a <select>. The intent is
// unambiguous -- pick this option -- so treat it as the click it is.
function normaliseVerb(action, page) {
  const target = page.elements.find(e => e.ref === action.ref);
  if (action.action === 'dblclick') return {...action, action: 'click', count: 2};
  if (action.action !== 'select') return action;
  if (target?.role === 'option') return {...action, action: 'click', purpose: 'answer', option: undefined};
  if ((target?.dropdown || target?.trigger) && action.option) {
    const cell = target.dropdown ? target : page.elements.find(e => e.ref === target.owner_ref);
    const option = page.elements.find(e => e.role === 'option' && (e.owner_ref === cell?.ref || e.owner_ref === target.ref) && norm(e.name) === norm(action.option));
    if (option) return {...action, action: 'click', ref: option.ref, purpose: 'answer', option: undefined};
    const open = page.elements.filter(e => e.role === 'option' && (e.owner_ref === cell?.ref || e.owner_ref === target.ref));
    if (open.length) return {...action, refusal: `No option "${action.option}" in the open menu for ${cell?.name || 'that cell'}. Its options are: ${open.map(o => o.name).slice(0, 12).join(' | ')}. Pick one of those by ref, or re-read to change the plan.`};
    if (cell) return {...action, action: 'click', ref: target.ref, purpose: 'open', option: undefined, wanted: action.option};
  }
  return action;
}

// The dropdown relationship, written down once. Who owns a menu option:
//   1. the option's owner cell in the DOM (aria-labelledby / aria-controls / label);
//   2. the menu the worker itself saw open (pendingMenu);
//   3. the one dropdown cell currently marked expanded;
//   4. the cell whose part was opened on the last turn.
// The option is accepted for a part when the owner IS that part's field.
function menuOwner(option, page) {
  const direct = page.elements.find(e => e.ref === option.owner_ref);
  if (direct) return direct.dropdown ? direct : (page.elements.find(e => e.ref === direct.owner_ref) || direct);
  if (pendingMenu) { const cell = page.elements.find(e => e.key === pendingMenu.cellKey); if (cell) return cell; }
  const expanded = page.elements.filter(e => e.dropdown && e.expanded);
  if (expanded.length === 1) return expanded[0];
  if (lastOpened && Date.now() - lastOpened.at < 60000) { const cell = page.elements.find(e => e.key === lastOpened.cellKey); if (cell) return cell; }
  return null;
}
// Which planned part an action is for, when the model did not say.
function resolvePart(action, selected, page) {
  let part = coverage.current?.parts.get(action.part_id);
  if (part || !selected || !coverage.current) return part;
  const parts = [...coverage.current.parts.values()];
  if (selected.dropdown || selected.opaque) part = parts.find(p => p.target_key === selected.key) || (selected.opaque && parts.length === 1 && !parts[0].target_key ? parts[0] : undefined);
  else if (selected.trigger) { const cell = page.elements.find(e => e.ref === selected.owner_ref); part = cell && parts.find(p => p.target_key === cell.key); }
  else if (selected.role === 'option') { const owner = menuOwner(selected, page); part = owner && parts.find(p => p.target_key === owner.key); }
  return part;
}

async function executeAction(tabId, action, page, config) {
  await refreshEvidence(tabId, page);
  action = normaliseVerb(action, page);
  if (action.refusal) return {ok: false, detail: action.refusal};
  const selected = page.elements.find(e => e.ref === action.ref);
  const part = resolvePart(action, selected, page);
  if (part && !action.part_id) action = {...action, part_id: part.id};

  if (action.action === 'look') return {ok: true, look: true, detail: 'Looked again without acting.'};
  if (action.action === 'hover') {
    const at = selected ? await reveal(tabId, selected) : null;
    if (!at) return {ok: false, detail: 'Nothing to hover: that element has no measurable position.'};
    await cursor(tabId, centre(at.box), 'hover', false); return AssignmentVisual.move(tabId, centre(at.box), stopped);
  }

  // ---- scrolling: wheel over the container (or the page), confirmed by the
  //      scroll position actually moving; DOM scroll only if the wheel did not.
  if (action.action === 'scroll') {
    const dir = action.direction || 'down', amount = Math.max(80, Math.min(2000, Number(action.amount) || 0)) || null;
    const container = selected && selected.box ? selected : null;
    const localRef = container ? refMap.get(container.ref)?.ref : null, frameId = container ? refMap.get(container.ref)?.frameId : 0;
    const before = await chrome.tabs.sendMessage(tabId, {type: 'scrollpos', ref: localRef}, {frameId}).catch(() => null);
    const v = await chrome.tabs.sendMessage(tabId, {type: 'viewport'}, {frameId: 0});
    const pt = container ? centre(container.box) : {x: Math.round(v.width / 2), y: Math.round(v.height / 2)};
    const step = amount || Math.round((dir === 'left' || dir === 'right' ? v.width : v.height) * 0.8);
    const dx = dir === 'left' ? -step : dir === 'right' ? step : 0, dy = dir === 'up' ? -step : dir === 'down' ? step : 0;
    await cursor(tabId, pt, 'scroll', false);
    try { await AssignmentVisual.wheel(tabId, pt, dx, dy, stopped); } catch (e) { return {ok: false, detail: e.message}; }
    await pause(250);
    const after = await chrome.tabs.sendMessage(tabId, {type: 'scrollpos', ref: localRef}, {frameId}).catch(() => null);
    if (before && after && (before.top !== after.top || before.left !== after.left)) return {ok: true, detail: 'Scrolled ' + dir + '.'};
    if (before && after && before.max <= 0 && !container) return {ok: false, detail: 'The page does not scroll ' + dir + ': it already fits.'};
    // The wheel did not move it. Scroll the DOM directly -- this is view
    // navigation, not an answer -- and say which path was used.
    await chrome.tabs.sendMessage(tabId, {type: 'domscroll', ref: localRef, dx, dy}, {frameId}).catch(() => {});
    const final = await chrome.tabs.sendMessage(tabId, {type: 'scrollpos', ref: localRef}, {frameId}).catch(() => null);
    const moved = before && final && (before.top !== final.top || before.left !== final.left);
    return moved ? {ok: true, detail: 'Scrolled ' + dir + ' (DOM scroll; the wheel event did not move this container).', method: 'dom'} : {ok: false, detail: 'Could not scroll ' + dir + '; the container may already be at its end.'};
  }

  // ---- reorder: a real drag from one planned item to another in the same list
  if (action.action === 'reorder') {
    const anchor = page.elements.find(e => e.ref === action.to);
    if (!part) return {ok: false, detail: 'Reorder needs part_id of the ordering part.'};
    if (part.kind !== 'ordering' || !part.order_keys?.length) return {ok: false, detail: `Part "${part.id}" is not an ordering plan. Re-read with order:[item refs in the desired order] for the list.`};
    if (!part.order_keys.includes(selected?.key) || !part.order_keys.includes(anchor?.key)) return {ok: false, detail: 'Both refs must be items named in the ordering plan; refs change every observation, so use the current ones.'};
    if (selected.key === anchor.key || selected.list_ref !== anchor.list_ref || !selected.list_ref || !selected.box || !anchor.box) return {ok: false, detail: 'Reorder needs two distinct items in the same visible list.'};
    if (!['before', 'after'].includes(action.placement)) return {ok: false, detail: 'Specify before or after.'};
    const s = selected.box, t = anchor.box, start = centre(s), end = {x: Math.round(t.x + t.w / 2), y: Math.round(t.y + (action.placement === 'before' ? 2 : t.h - 2))};
    part.verified = false; part.visualConfirmed = false;
    return browserInput(tabId, start, end);
  }

  // ---- visual: a coordinate on the exact screenshot the model saw
  if (action.action.startsWith('visual_')) {
    if (!decisionSnapshot || action.observation_id !== decisionSnapshot.id) return {ok: false, detail: 'That screenshot is not the current one (observation_id ' + (action.observation_id || 'missing') + '). Use the OBSERVATION ID of this turn.'};
    if (!part) return {ok: false, detail: 'Visual input needs the part_id of the part it answers; add the part in read_check first if it is new.'};
    await currentSnapshot(tabId, decisionSnapshot, page);
    const v = decisionSnapshot.viewport, p = action.point, d = action.destination;
    if (!p || ![p.x, p.y, ...(d ? [d.x, d.y] : [])].every(n => Number.isFinite(n) && n >= 0 && n <= 1)) return {ok: false, detail: 'Invalid visual coordinates: use fractions 0..1 of the screenshot.'};
    const start = {x: Math.round(p.x * v.width), y: Math.round(p.y * v.height)}, end = d ? {x: Math.round(d.x * v.width), y: Math.round(d.y * v.height)} : null;
    // When the part's control is known, the point (the destination, for a
    // drag) has to land on it or on the menu it owns.
    const planned = part.target_key && page.elements.find(e => e.key === part.target_key);
    if (planned?.box && planned.role !== 'graph') {
      const boxes = [planned.box, ...page.elements.filter(e => e.owner_ref === planned.ref && e.box).map(e => e.box)];
      const hits = pt => boxes.some(b => pt.x >= b.x - 2 && pt.x <= b.x + b.w + 2 && pt.y >= b.y - 2 && pt.y <= b.y + b.h + 2);
      if (!hits(end || start)) return {ok: false, detail: `That point is not on the control planned for "${part.what}" (ref ${planned.ref}) or its open menu. Aim at that control, or click it by ref.`};
    }
    if (planned?.role === 'graph' && planned.box) {
      const b = planned.box, m = 12, inside = pt => pt.x >= b.x - m && pt.x <= b.x + b.w + m && pt.y >= b.y - m && pt.y <= b.y + b.h + m;
      const v2 = decisionSnapshot.viewport;
      const frac = pt => `x≈${(pt.x / v2.width).toFixed(2)}, y≈${(pt.y / v2.height).toFixed(2)}`;
      const bounds = `The graph fills x ${(b.x / v2.width).toFixed(2)}..${((b.x + b.w) / v2.width).toFixed(2)}, y ${(b.y / v2.height).toFixed(2)}..${((b.y + b.h) / v2.height).toFixed(2)} of the screenshot`;
      if (!inside(start)) return {ok: false, detail: `The point you are dragging FROM (${frac(start)}) is outside the graph "${part.what}". ${bounds}. Aim at where the point sits on the graph.`};
      if (end && !inside(end)) return {ok: false, detail: `The point you are dragging TO (${frac(end)}) is outside the graph "${part.what}". ${bounds}. Aim inside the plotting area at the target coordinates.`};
    }
    part.visual = true; if (action.purpose !== 'open') { part.verified = false; part.visualConfirmed = false; }
    const out = await browserInput(tabId, start, end, {region: true});
    if (out.ok && action.purpose !== 'open') { part.entered = true; part.everEntered = true; out.needsVerification = true; out.partId = part.id; }
    else if (out.ok) out.preparation = true;
    return out;
  }

  // ---- a closed-shadow widget: a real click at its centre, verified by screenshot
  if (action.action === 'click' && selected?.opaque) {
    if (!part) return {ok: false, detail: 'Clicking a widget needs the part_id of the part it answers.'};
    if (!selected.box) return {ok: false, detail: 'That widget has no measurable position.'};
    if (part.target_key && part.target_key !== selected.key) return {ok: false, detail: 'Widget does not match the planned part.'};
    if (part.verified) return {ok: false, detail: `"${part.what}" is already verified from the screenshot. Do not click it again; move to the next part or the control that continues.`};
    part.target_key = selected.key; part.visual = true;
    const opening = !part.opened && action.purpose !== 'answer';
    const out = await browserInput(tabId, centre(selected.box));
    if (out.ok) { if (opening) { part.opened = true; out.preparation = true; } else { part.entered = true; part.everEntered = true; part.verified = false; part.visualConfirmed = false; part.opened = false; out.needsVerification = true; out.partId = part.id; } }
    return out;
  }

  // ---- custom dropdown: the cell (or its arrow) opens; an option answers.
  //      Entered whenever the click is on a dropdown cell, a trigger, or a menu
  //      option -- resolving the part happens INSIDE, so a missing pendingMenu
  //      or a forgotten part_id is recovered here instead of falling through.
  if (action.action === 'click' && (selected?.dropdown || selected?.trigger || selected?.role === 'option' || action.purpose === 'open')) {
    if (!selected) return {ok: false, detail: 'That ref is not on the page any more. Look again.'};
    if (selected.control || !selected.box) return {ok: false, detail: 'Dropdown action requires a visible, non-navigation control with a position.'};
    const cell = selected.dropdown ? selected : selected.trigger ? page.elements.find(e => e.ref === selected.owner_ref) : selected.role === 'option' ? menuOwner(selected, page) : null;
    if (!cell) return {ok: false, detail: selected.role === 'option' ? `Menu option "${selected.name}" (ref ${selected.ref}) belongs to no dropdown the worker can identify. Click the answer cell for this part first, then pick the option.` : 'That control is not part of a dropdown.'};
    const owner = part || [...(coverage.current?.parts.values() || [])].find(p => p.target_key === cell.key);
    if (!owner) return {ok: false, detail: `The dropdown cell "${cell.name || cell.row || 'ref ' + cell.ref}" (ref ${cell.ref}) is not a planned part. Add it in read_check, then act.`};
    if (owner.target_key && owner.target_key !== cell.key) return {ok: false, detail: `Menu option "${selected.name}" belongs to the cell "${cell.name || cell.row}" (ref ${cell.ref}), not to the field planned for "${owner.what}". Open that field's own menu.`};
    owner.target_key = cell.key;
    if (selected.role === 'option') {
      const want = norm(owner.answer), label = norm(selected.name);
      if (label !== want) {
        const near = !!want && (label.includes(want) || want.includes(label));
        const siblings = page.elements.filter(e => e.role === 'option' && e.owner_ref === selected.owner_ref && (norm(e.name).includes(want) || want.includes(norm(e.name))));
        if (!near || siblings.length > 1) return {ok: false, detail: `Option "${selected.name}" differs from the planned answer "${owner.answer}" for ${owner.what}.` + (siblings.length > 1 ? ' Several options match that word: ' + siblings.map(e => e.name).join(' | ') + '.' : '') + ' Pick the planned option, or re-read to change the plan.'};
        owner.answer = selected.name; owner.refined = true;            // "Equity" -> "Stockholders' Equity"
      }
      const out = await clickAt(tabId, centre(selected.box), owner.answer);
      if (out.ok) { owner.entered = true; owner.everEntered = true; owner.verified = false; owner.visualConfirmed = false; pendingMenu = null; out.needsVerification = true; out.partId = owner.id; out.detail = 'Chose "' + selected.name + '" for ' + owner.what + '; checking the field.'; }
      return out;
    }
    // opening: the cell itself or its arrow
    const out = await clickAt(tabId, centre(selected.box), 'open');
    if (out.ok) { pendingMenu = {part: owner.id, cellKey: cell.key}; lastOpened = {cellKey: cell.key, at: Date.now()}; out.preparation = true; out.detail = 'Opened the menu for ' + owner.what + '. Look again and pick the option.'; if (action.wanted) out.detail += ' (wanted: ' + action.wanted + ')'; }
    return out;
  }

  // ---- everything else: refusals first, then binding, then the interaction
  const refusal = coverage.gate(action, page, config);
  if (refusal) return {ok: false, blocked: true, detail: refusal};
  const activating = action.action === 'click' || (action.action === 'press' && ['Enter', 'Space'].includes(action.key));
  if (selected && activating) {
    if (selected.control === 'refused') return {ok: false, detail: 'Refused: "' + (selected.name || '').slice(0, 60) + '" is a destructive, account, consent or download control. Those stay with the student.'};
    if (selected.role === 'link' && selected.external) return {ok: false, detail: 'Refused: that link leaves the assignment site.'};
  }
  if (selected?.disabled && ['click', 'fill', 'select', 'press'].includes(action.action)) return {ok: false, detail: `"${selected.name || 'ref ' + selected.ref}" is disabled. The page is not taking input there` + (page.page_state === 'locked' ? '; this attempt has been graded and locked. Move on with the control that continues.' : '.')};
  if (answering(action, page) && !coverage.bind(action, page) && !coverage.adopt(action, page)) return {ok: false, detail: `That ${selected?.role || 'control'} (ref ${action.ref}) is not one of this question's planned answers. Use the ref of a planned part, or re-read to add it.`};
  const oscillation = coverage.oscillation(action, page);
  if (oscillation) return {ok: false, blocked: true, detail: oscillation};
  const terminal = selected?.control === 'terminal';
  const permit = {terminal: terminal && config.auto_submit && coverage.outstanding().length === 0};

  const outcome = await perform(tabId, action, selected, permit);
  coverage.record(action, page, outcome);
  if (outcome.ok && terminal) { coverage.current.submitted = true; emit({kind: 'submitted', message: 'Submission control executed; checking the resulting page.'}); }
  return outcome;
}

// Perform a gated action with browser input, falling back to the DOM path only
// where there is no coordinate to aim at, and saying so.
async function perform(tabId, action, selected, permit) {
  if (!selected) return actOnRef(tabId, action, permit);
  const at = await reveal(tabId, selected);
  if (!at) { const out = await actOnRef(tabId, action, permit); if (out.ok) out.detail += ' (DOM path: this frame has no measurable position.)'; return out; }
  const pt = centre(at.box), verb = action.action;
  // Anything that hands in the assignment goes through the page's permit check
  // as well, so the DOM-side refusal still applies to a real click.
  if (selected.control === 'terminal' && !permit.terminal) return {ok: false, detail: 'Refused: hand-in requires the hand-in switch and every part verified.'};
  try {
    if (verb === 'click') {
      const out = await clickAt(tabId, pt, selected.name?.slice(0, 40) || 'click', action.count === 2 ? 2 : 1);
      out.detail = (action.count === 2 ? 'Double-clicked' : 'Clicked') + ' "' + (selected.name || '').slice(0, 40) + '" with browser input; verify the resulting answer separately.';
      return out;
    }
    if (verb === 'fill') {
      if (!['textbox', 'combobox', 'spinbutton', 'searchbox'].includes(selected.role) && at.tag !== 'INPUT' && at.tag !== 'TEXTAREA') return {ok: false, detail: 'That control is not a text field.'};
      await clickAt(tabId, pt, 'type');
      await AssignmentVisual.selectAll(tabId, stopped);
      if (String(action.text).length) await AssignmentVisual.insertText(tabId, action.text, stopped); else await AssignmentVisual.key(tabId, 'Backspace', stopped);
      await pause(120);
      const after = await reveal(tabId, selected);
      if (after && norm(after.value) === norm(action.text)) return {ok: true, detail: `Typed; the field now reads "${String(after.value).slice(0, 80)}".`};
      // The keystrokes did not take (an editor that ignores insertText). Try the
      // DOM path once, and say so.
      const dom = await actOnRef(tabId, action, permit);
      if (dom.ok) dom.detail += ' (DOM path: browser typing did not take in this field.)';
      return dom;
    }
    if (verb === 'select') {
      if (at.tag !== 'SELECT') return {ok: false, detail: 'That element is not a native dropdown. Click it to open, then click the option.'};
      const options = at.options || [], wanted = options.find(o => norm(o) === norm(action.option));
      if (!wanted) return {ok: false, detail: 'No option "' + action.option + '". Available: ' + options.slice(0, 12).join(' | ')};
      // Focus with a real click, close the popup, then drive the selection with
      // the keyboard: typeahead first, arrows if that misses. Checked in a
      // loaded extension: this changes the value and fires change.
      await clickAt(tabId, pt, 'select'); await AssignmentVisual.key(tabId, 'Escape', stopped); await pause(60);
      await AssignmentVisual.typeKeys(tabId, wanted.slice(0, 12), stopped); await pause(120);
      let now = await reveal(tabId, selected);
      if (now && norm(now.value) !== norm(wanted)) {
        for (let i = 0; i < options.length; i++) await AssignmentVisual.key(tabId, 'ArrowUp', stopped);
        for (let i = 0; i < options.indexOf(wanted); i++) await AssignmentVisual.key(tabId, 'ArrowDown', stopped);
        await pause(120); now = await reveal(tabId, selected);
      }
      if (now && norm(now.value) === norm(wanted)) return {ok: true, detail: 'Selected "' + wanted + '" with the keyboard.'};
      const dom = await actOnRef(tabId, action, permit);
      if (dom.ok) dom.detail += ' (DOM path: keyboard selection did not take.)';
      return dom;
    }
    if (verb === 'press') {
      if (!at.focused && !/^(?:Escape)$/.test(action.key)) await clickAt(tabId, pt, 'focus');
      const out = await AssignmentVisual.key(tabId, action.key, stopped);
      return {ok: true, detail: out.detail + ' Verify the effect separately.'};
    }
    if (verb === 'drag') {
      const target = await reveal(tabId, {ref: action.to});
      if (!target) return {ok: false, detail: 'The drag destination has no measurable position.'};
      const src = refMap.get(action.ref), dst = refMap.get(action.to);
      if (!src || !dst || src.frameId !== dst.frameId) return {ok: false, detail: 'A drag must stay inside one frame.'};
      const priorText = target.value || '';
      const dragged = await browserInput(tabId, pt, centre(target.box));
      if (!dragged.ok) return dragged;
      await pause(200);
      let landed = await chrome.tabs.sendMessage(tabId, {type: 'landed', ref: src.ref, to: dst.ref, priorText}, {frameId: src.frameId}).catch(() => ({landed: false}));
      if (landed.landed) return {ok: true, detail: 'Dragged "' + (selected.name || '').slice(0, 40) + '" and the destination now holds it.'};
      // Many matching widgets take click-source-then-click-target instead.
      await clickAt(tabId, pt, 'pick'); await pause(150); await clickAt(tabId, centre(target.box), 'place'); await pause(200);
      landed = await chrome.tabs.sendMessage(tabId, {type: 'landed', ref: src.ref, to: dst.ref, priorText}, {frameId: src.frameId}).catch(() => ({landed: false}));
      if (landed.landed) return {ok: true, detail: 'Placed "' + (selected.name || '').slice(0, 40) + '" by clicking the item and then the destination.'};
      return {ok: false, detail: 'Neither a drag nor click-to-place put "' + (selected.name || '').slice(0, 40) + '" into the destination. The widget may need a different gesture; look at the page again.'};
    }
    if (verb === 'scroll_to') return {ok: true, detail: 'Scrolled to the control.'};
    return actOnRef(tabId, action, permit);
  } catch (e) {
    if (/cancelled|Stopped|navigated|tab is gone/i.test(e.message)) return {ok: false, detail: e.message};
    throw e;
  }
}

// ------------------------------------------------------------- backend

async function guestToken(backend) {
  const res = await fetch(backend + '/api/guest', {method: 'POST'});
  if (!res.ok) throw new Error('The backend would not issue access. It may be restarting.');
  const data = await res.json();
  await chrome.storage.local.set({token: data.token});
  return data.token;
}
const DECISION_TIMEOUT_MS = 240000;   // the backend's own retries fit inside this; nothing waits forever
async function decide(config, observation) {
  const call = async token => {
    const timer = new AbortController(), t = setTimeout(() => timer.abort(), DECISION_TIMEOUT_MS);
    const onStop = () => timer.abort(); decisionAbort?.signal.addEventListener('abort', onStop, {once: true});
    try { return await fetch(config.backend + '/api/agent/step', {method: 'POST', headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + token}, body: JSON.stringify(observation), signal: timer.signal}); }
    catch (e) { if (state.stopRequested) throw e; if (timer.signal.aborted) throw new Error('The backend did not answer within ' + DECISION_TIMEOUT_MS / 1000 + ' s. Nothing was done. Check the Railway service and try again.'); throw e; }
    finally { clearTimeout(t); decisionAbort?.signal.removeEventListener('abort', onStop); }
  };
  let token = runToken || config.token || await guestToken(config.backend);
  let res = await call(token);
  if (res.status === 401) { token = await guestToken(config.backend); res = await call(token); }
  runToken = token;
  if (!res.ok) {
    let detail = '';
    try { const body = await res.json(); if (Number.isFinite(body.cost)) { state.cost += body.cost; emit({kind: 'warn', message: 'Provider usage for rejected proposal', cost: body.cost, tokens: `${body.input_tokens || 0} in / ${body.output_tokens || 0} out`}); } detail = body.error || body.detail || ''; }
    catch { try { detail = (await res.text()).slice(0, 300); } catch { detail = ''; } }
    throw new Error(`The backend refused this step (HTTP ${res.status})` + (detail ? `: ${detail}` : '. It returned no reason.'));
  }
  return res.json();
}
const RECOVERABLE = /Nothing was done|invalid action format|Invalid proposal|not an allowed action|would not (?:choose|perform)|Verification may only be returned/;

// ------------------------------------------------------------- the run

async function run(tabId) {
  if (state.running) throw new Error('Already running.');
  Object.assign(state, {running: true, stopRequested: false, tabId, steps: 0, questions: 0, cost: 0, progress: '', pageState: '', log: []});
  coverage = new AssignmentCoverage.Coverage(); decisionAbort = new AbortController(); runToken = '';
  decisionSnapshot = null; pendingMenu = null; lastOpened = null; visualFailures.clear(); interactionFailures.clear();
  let checked = false, recheck = false, stalls = 0, navSteps = 0, lastAction = {}, lastDigest = '', sinceRead = 0;
  let askedForParts = false, shifted = 0, doneRefused = false, waitedForLoad = false, retiredFor = '', retryFor = '';
  // Chrome reaps an MV3 service worker that goes quiet, and a run spends much
  // of its time waiting on the model. A cheap extension API call every 20 s
  // keeps the worker -- and the run -- alive. Observed: multi-question runs
  // died mid-loop without this and survived with it.
  const keepAlive = setInterval(() => { chrome.runtime.getPlatformInfo().catch(() => {}); chrome.storage.local.set({heartbeat: Date.now()}).catch(() => {}); }, 20000);
  try {
    const tab = await chrome.tabs.get(tabId);
    runOrigin = new URL(tab.url).origin; runUrl = tab.url; runTitle = tab.title; runSite = siteOf(tab.url);
    await compatible(await settings());
    await AssignmentVisual.attach(tabId);                      // every interaction is real browser input
    await injectAll(tabId);
    injectState.url = tab.url;
    const observeResilient = () => observeResilientFor(tabId);
    emit({kind: 'info', message: 'Reading ' + new URL(tab.url).host + ' · extension ' + chrome.runtime.getManifest().version + ' · bound to this tab; switching tabs will not move or stop it'});

    while (!state.stopRequested) {
      const config = await settings(); doubleCheck = config.double_check;
      if (state.cost >= config.spend_limit) { emit({kind: 'stop', message: `Spending limit reached ($${state.cost.toFixed(3)} of $${config.spend_limit.toFixed(2)}). Raise it in Setup to continue.`}); break; }
      await boundTab(tabId);
      const page = await observeResilient();
      await refreshEvidence(tabId, page);
      if (page.warnings.length) emit({kind: 'warn', message: page.warnings.join(' ')});
      const changed = page.digest !== lastDigest; lastDigest = page.digest;

      // ---- page state, before any paid call
      if (page.page_state === 'loading') {
        if (!waitedForLoad) { waitedForLoad = true; emit({kind: 'info', message: 'The page is still loading. Waiting once before reading it.'}); await pause(1500); continue; }
      } else waitedForLoad = false;
      if (page.page_state === 'complete') { emit({kind: 'stop', message: 'The assignment reports it is complete. ' + (page.feedback || '')}); break; }
      if (page.page_state === 'locked' && coverage.current && retiredFor !== coverage.current.id) {
        const outcome = /incorrect|wrong/i.test(page.feedback) ? 'incorrect' : /correct|right/i.test(page.feedback) ? 'correct' : 'graded';
        const retired = coverage.retire(outcome, page.feedback); retiredFor = coverage.current.id;
        emit({kind: 'question', message: `Graded ${outcome} and locked: "${page.feedback}".` + (retired.length ? ' Unfinished parts retired (not marked correct): ' + retired.join(', ') : '')});
        if (!config.advance) { emit({kind: 'stop', message: 'This attempt is graded and locked. Continuing to the next question is switched off, so the rest is yours.'}); break; }
        recheck = true; stalls = 0;
      }
      if (page.page_state === 'editable_feedback' && coverage.current && retryFor !== coverage.current.id) {
        coverage.allowRetry(page.feedback); retryFor = coverage.current.id;
        emit({kind: 'question', message: `The page graded this attempt ("${page.feedback}") and allows another try. Answers may be revised.`});
        recheck = true;
      }

      if (stalls >= STALL_LIMIT) {
        if (coverage.questions.size && !coverage.outstanding().length) { emit({kind: 'stop', message: 'Every part is verified. Nothing further to press was found on this page -- no hand-in or next-question control.'}); break; }
        throw new Error('No verified progress after ' + STALL_LIMIT + ' turns. Last: ' + (lastAction.detail || lastAction.action || 'nothing') + '. Review that part of the page yourself.');
      }

      decisionSnapshot = await makeSnapshot(tabId, page);
      const observation = {
        screenshot: config.badges ? await capture(tabId, page, true) : decisionSnapshot.screenshot, observation_id: decisionSnapshot.id,
        elements: page.elements, text: page.text, host: page.host, page_state: page.page_state, feedback: page.feedback, attempts_left: page.attempts_left,
        step: (coverage.current?.steps || 0) + 1, step_budget: coverage.budget(), page_changed: changed, last_action: lastAction,
        task_note: config.note, plan: coverage.current?.plan || '', progress: coverage.summary(), ledger: coverage.ledger(), warnings: page.warnings,
        phase: !checked || recheck ? 'read_check' : navSteps ? 'navigate' : 'act', advance: config.advance, auto_submit: config.auto_submit, model: config.model,
      };
      state.steps++;
      let result;
      try { result = await decide(config, observation); }
      catch (e) {
        if (RECOVERABLE.test(e.message)) { stalls++; recheck = false; lastAction = {action: 'invalid', ok: false, detail: e.message.replace(/^The backend refused this step \(HTTP \d+\): /, '')}; emit({kind: 'warn', message: 'The model answered in a form the harness could not use. Asking again.', detail: lastAction.detail}); continue; }
        throw e;
      }
      const action = result.action; state.cost += result.cost || 0;
      emit({kind: 'think', message: `step ${state.steps} · ${observation.phase} · ${action.action}`, detail: action.reason || '', working: result.working || '', raw: result.raw || '', cost: result.cost, tokens: `${result.input_tokens || 0} in / ${result.output_tokens || 0} out`});
      if (state.stopRequested) break;
      await boundTab(tabId);
      if (await digestNow(tabId) !== page.digest) {
        if (++shifted >= SHIFT_LIMIT) throw new Error('The page kept changing on its own while the model was deciding, ' + SHIFT_LIMIT + ' times in a row. Wait for it to settle, then start again.');
        recheck = true; emit({kind: 'warn', message: 'Page changed while deciding. Discarded the stale action and looking again.'}); continue;
      }
      shifted = 0;

      if (!checked && action.action !== 'read_check') { stalls++; lastAction = {action: action.action, ok: false, detail: 'The first step on a page is read_check.'}; continue; }
      if (action.action === 'read_check') {
        if (!action.has_question) {
          if (!checked || !config.advance) { emit({kind: 'stop', message: 'No question to answer. ' + (action.reason || '')}); break; }
          if (++navSteps > NAV_BUDGET) throw new Error('Could not reach another question after ' + NAV_BUDGET + ' turns. ' + (action.reason || ''));
          recheck = false; continue;
        }
        if (!action.parts?.length) {
          if (!askedForParts) { askedForParts = true; recheck = true; emit({kind: 'warn', message: 'Model omitted the parts checklist. Asking once more before proceeding without one.'}); continue; }
          emit({kind: 'warn', message: 'No parts checklist. Proceeding: the first answer entered will be taken as the plan for this question.'});
        }
        const before = coverage.summary(), fresh = coverage.read(action, page);
        if (coverage.revised.length) { stalls++; emit({kind: 'warn', message: 'The plan changed an answer it had already committed. Taken once; the part must be re-entered.', detail: coverage.revised.join('; ')}); }
        if (fresh) { state.questions++; stalls = 0; askedForParts = false; doneRefused = false; interactionFailures.clear(); }
        else if (before === coverage.summary() && sinceRead === 0) stalls++;
        checked = true; recheck = false; navSteps = 0; sinceRead = 0;
        await refreshEvidence(tabId, page);
        for (const p of coverage.current.parts.values()) if (p.kind === 'ordering' && p.verified) emit({kind: 'progress', message: 'Already in the planned order; no drag needed: ' + p.what});
        emit({kind: 'question', message: action.question}); emit({kind: 'progress', message: coverage.summary()}); lastAction = {action: 'read_check'}; continue;
      }
      if (action.action === 'done' || action.action === 'give_up') {
        const remaining = coverage.outstanding();
        if (remaining.length && action.action === 'done' && !doneRefused) {
          doneRefused = true; stalls++;
          lastAction = {action: 'done', ok: false, detail: 'Refused: these parts are not verified yet: ' + remaining.join(', ') + '. A value showing inside an open widget is not chosen until you click it.'};
          emit({kind: 'warn', message: 'Model said done with parts outstanding. Asking it to finish them.', detail: remaining.join(', ')}); continue;
        }
        emit({kind: remaining.length ? 'warn' : 'stop', message: (remaining.length ? 'Stopped with outstanding parts: ' + remaining.join(', ') : 'Finished: ') + (action.reason || '')}); break;
      }
      if (coverage.current && ++coverage.current.steps > coverage.budget()) throw new Error('This question used its whole action allowance (' + coverage.budget() + ' turns) without finishing. Completed parts were kept; look at the remaining ones yourself.');

      // Before a hand-in, every part still missing its screenshot witness gets one.
      if (page.elements.find(e => e.ref === action.ref)?.control === 'terminal') for (const q of coverage.questions.values()) for (const p of q.parts.values()) if (!p.retired && (p.visual || doubleCheck) && !p.visualConfirmed && p.domVerified !== false && p.target_key) await verifyVisual(tabId, page, p, config);

      const before = coverage.summary();
      let outcome;
      try { outcome = await executeAction(tabId, action, page, await settings()); }
      catch (e) { if (/^Stale/.test(e.message)) { recheck = true; lastAction = {action: action.action, ok: false, detail: e.message}; continue; } throw e; }
      sinceRead++;
      emit({kind: outcome.ok ? 'act' : 'warn', message: action.action + (action.ref ? ' ref ' + action.ref : '') + (outcome.method === 'dom' ? ' (DOM path)' : ''), detail: outcome.detail});
      if (outcome.blocked) break;

      // The same interaction failing the same way, repeatedly, is a persistent
      // failure -- stop with the reason instead of paying to repeat it.
      // Navigation and looking are exploration, not answer interactions: a
      // scroll that finds nothing is not a "persistent failure", it is the
      // stall limit's job. Only answer-shaped moves feed the persistent-failure
      // counter.
      if (!outcome.ok && !['scroll', 'scroll_to', 'look', 'hover'].includes(action.action)) {
        const sig = action.action + ':' + (action.ref ?? '') + ':' + (outcome.detail || '').slice(0, 60);
        const n = (interactionFailures.get(sig) || 0) + 1; interactionFailures.set(sig, n);
        if (n >= INTERACTION_RETRIES) {
          if (coverage.questions.size && !coverage.outstanding().length) { emit({kind: 'stop', message: 'Every part is verified. The page offers nothing further that works (' + action.action + ': ' + outcome.detail + ').'}); break; }
          throw new Error('The same interaction failed ' + n + ' times: ' + action.action + (action.ref ? ' on ref ' + action.ref : '') + ' -- ' + outcome.detail + ' This needs you.');
        }
      }

      let landed = false; if (outcome.ok && !outcome.look) landed = await waitForEffect(tabId, page.digest);
      const updated = await observeResilient(); await refreshEvidence(tabId, updated);
      const actedPart = coverage.current?.parts.get(outcome.partId || action.part_id);
      const domDecided = actedPart?.domEvidence?.supported === true;
      const answered = outcome.needsVerification || action.action.startsWith('visual_') || action.action === 'reorder' || answering(action, page);
      if (outcome.ok && actedPart && answered && action.purpose !== 'open' && (!domDecided || (doubleCheck && actedPart.domVerified === true && !actedPart.visualConfirmed))) await verifyVisual(tabId, updated, actedPart, config);
      const progress = before !== coverage.summary();
      stalls = progress ? 0 : (outcome.preparation && landed) || (outcome.look && updated.digest !== page.digest) ? stalls : stalls + 1;
      if (progress) { doneRefused = false; interactionFailures.clear(); }
      state.progress = coverage.summary(); emit({kind: 'progress', message: state.progress});
      lastAction = {action: action.action, ref: action.ref, ok: outcome.ok, detail: outcome.detail, landed};
      const control = page.elements.find(e => e.ref === action.ref)?.control;
      recheck = (outcome.ok && ['part', 'advance', 'terminal'].includes(control)) || !outcome.ok || !!outcome.look;
      if (control === 'terminal' && outcome.ok) {
        const feedback = updated.feedback || (updated.text.match(/(?:your answer\s*:?\s*(?:correct|incorrect)|successfully submitted|submission confirmed|assignment submitted)/i) || [])[0];
        if (updated.page_state === 'complete' || /submitted|confirmed/i.test(feedback || '')) { emit({kind: 'stop', message: 'Handed in. ' + (feedback ? 'Page feedback: ' + feedback : '')}); break; }
        emit({kind: 'question', message: 'Submission control executed. ' + (feedback ? 'Page feedback: ' + feedback : 'Acceptance not yet confirmed; looking again.')});
      }
    }
  } catch (error) { emit({kind: 'error', message: state.stopRequested ? 'Stopped by you.' : error.message}); }
  finally {
    clearInterval(keepAlive);
    await AssignmentVisual.detach();
    await Promise.all(frameIds.map(frameId => chrome.tabs.sendMessage(tabId, {type: 'cursor_off'}, {frameId}).catch(() => {})));
    state.running = false; decisionAbort = null;
    chrome.runtime.sendMessage({type: 'finished', state: snapshot()}).catch(() => {});
  }
}

// New coordinator is opt-in until live release gates pass. The legacy loop
// remains an explicit rollback path; no automatic downgrade after a failed task.
let plannerEngine=null,launching=false;
async function plannerRequest(phase,body,signal){
  const config=await settings();let token=runToken||config.token;
  if(!token)token=await guestToken(config.backend);runToken=token;
  const controller=new AbortController(),onStop=()=>controller.abort(),timeout=setTimeout(()=>controller.abort(),60000);
  signal.addEventListener('abort',onStop,{once:true});if(signal.aborted)controller.abort();
  try{const response=await fetch(config.backend+'/api/agent/'+phase,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(body),signal:controller.signal});
    const data=await response.json();if(!response.ok&&!data.detail)data.detail='Backend HTTP '+response.status;return data;
  }catch{throw new Error(signal.aborted?'CANCELLED: stopped while waiting for the model.':'Provider request did not complete within 60 seconds or connection failed. Reservation remains pending; inspect usage before resuming.');}
  finally{clearTimeout(timeout);signal.removeEventListener('abort',onStop)}
}
function plannerBridge(){return {bound:boundTab,allowed:origin=>siteOf(origin)===runSite,stopped,config:settings,request:plannerRequest,
  viewport:async id=>{const r=await chrome.debugger.sendCommand({tabId:id},'Page.getLayoutMetrics');const v=r.cssVisualViewport||r.visualViewport;return {width:v.clientWidth,height:v.clientHeight}},
  emit:row=>{if(Number.isFinite(row.cost))state.cost+=row.cost;if(row.input_tokens!=null)row.tokens=String(row.input_tokens)+' in / '+String(row.output_tokens||0)+' out';emit(row)},
  progress:(done,total,questions,cost,steps)=>{Object.assign(state,{questions,cost,steps,progress:done+' of '+total+' parts done'});emit({kind:'progress',message:state.progress})}}}
async function runPlanner(tabId,config,resume=false){
  Object.assign(state,{running:true,stopRequested:false,tabId,steps:0,questions:0,cost:0,progress:'',log:[]});decisionAbort=new AbortController();
  const keepAlive=setInterval(()=>chrome.runtime.getPlatformInfo().catch(()=>{}),20000);
  try{
    const tab=await chrome.tabs.get(tabId);runOrigin=new URL(tab.url).origin;runSite=siteOf(tab.url);runUrl=tab.url;runTitle=tab.title;runToken='';
    const response=await fetch(config.backend+'/api/capabilities?protocol=4',{signal:decisionAbort.signal});const caps=await response.json();
    if(caps.protocol!==4||!['task_plans','stable_slots','typed_verification','bounded_repair'].every(f=>caps.features?.includes(f)))throw new Error('Backend update required: planner preview needs protocol 4. No paid request was made.');
    await boundTab(tabId);await AssignmentVisual.attach(tabId);
    const held=(await chrome.storage.local.get('planner_run')).planner_run;
    if(resume&&(!held||held.tab_id!==tabId||held.url!==tab.url))throw new Error('Cannot resume: select the original assignment tab and URL.');
    if(resume&&held.pending_request){
      const token=config.token||await guestToken(config.backend);runToken=token;
      const reconciliation=await fetch(config.backend+'/api/agent/runs/'+encodeURIComponent(held.id),{headers:{Authorization:'Bearer '+token},signal:decisionAbort.signal});
      if(!reconciliation.ok)throw new Error('Saved request usage cannot be reconciled. Review provider usage before resuming.');
      const usage=await reconciliation.json();const call=usage.calls.find(c=>c.request_id===held.pending_request);
      if(!call||call.status!=='settled')throw new Error('Previous provider charge is still unconfirmed. Reconcile usage before resuming.');held.pending_request=null;held.cost=usage.cost;
    }
    plannerEngine=new AssignmentPlanner.Engine(plannerBridge(),tabId,config,resume?held:null);plannerEngine.ledger.tab_id=tabId;plannerEngine.ledger.url=tab.url;
    await plannerEngine.run();
  }catch(e){emit({kind:'error',message:e.message})}
  finally{clearInterval(keepAlive);await AssignmentVisual.detach();state.running=false;decisionAbort=null;plannerEngine=null;chrome.runtime.sendMessage({type:'finished',state:snapshot()}).catch(()=>{})}
}
async function startSelected(tabId,resume=false){if(launching||state.running)throw new Error('Already running.');launching=true;try{const config=await settings();if(!((await chrome.storage.local.get('armed')).armed))throw new Error('Arm ETH before starting.');if(config.planner_enabled)await runPlanner(tabId,config,resume);else await run(tabId)}finally{launching=false}}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  // Control messages originate in the extension panel, never a content script.
  if (sender.tab && !String(sender.url || '').startsWith(chrome.runtime.getURL('')) && ['start', 'resume', 'stop'].includes(message.type)) { reply({ok: false, error: 'Use the extension panel.'}); return true; }
  if (message.type === 'start' || message.type === 'resume') { if (state.running || launching) { reply({ok: false, error: 'Already running.'}); return true; } startSelected(message.tabId,message.type==='resume').catch(e => emit({kind: 'error', message: e.message})); reply({ok: true}); return true; }
  if (message.type === 'stop') { state.stopRequested = true; plannerEngine?.stop(); decisionAbort?.abort(); AssignmentVisual.detach(); if (state.tabId) for (const frameId of frameIds) chrome.tabs.sendMessage(state.tabId, {type: 'cancel'}, {frameId}).catch(() => {}); reply({ok: true}); return true; }
  if (message.type === 'status') { reply({...snapshot(), log: state.log}); return true; }
  return false;
});
chrome.action.onClicked.addListener(tab => chrome.sidePanel.open({windowId: tab.windowId}).catch(() => {}));
chrome.runtime.onInstalled.addListener(() => chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).catch(() => {}));

// DevTools-only integration surface for the loaded-extension tests. Not
// reachable from web pages.
globalThis.__assignmentHarness = {
  plannerBridge, runPlanner,
  injectAll, observeAllFrames, observeResilient: observeResilientFor, boundTab, actOnRef, executeAction, refreshEvidence, waitForEffect, capture, compatible, makeSnapshot, currentSnapshot, verifyVisual, run, settle, perform, reveal, siteOf,
  setSnapshot(s) { decisionSnapshot = s; }, setDoubleCheck(v) { doubleCheck = !!v; }, setPendingMenu(m) { pendingMenu = m; },
  get coverage() { return coverage; }, get state() { return state; }, get pendingMenu() { return pendingMenu; },
  reset(origin) { runOrigin = origin; runSite = siteOf(origin); injectState.url = ''; coverage = new AssignmentCoverage.Coverage(); state.stopRequested = false; pendingMenu = null; lastOpened = null; interactionFailures.clear(); visualFailures.clear(); },
};
