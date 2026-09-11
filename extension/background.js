/* The harness. Owns the observe / decide / act loop and every limit on it.

   The model decides; this file is what actually spends money, touches the tab,
   and refuses. Caps are enforced here as well as on the backend, so a confused
   model cannot run away with a session. */

const DEFAULT_BACKEND = 'https://positive-tranquility-production-9fdc.up.railway.app';

const STEP_BUDGET = 16;       // per question; worksheets need one step per box
const SESSION_STEPS = 900;    // enough for a long set: ~60+ questions
const REPEAT_LIMIT = 4;       // identical observations before we stop
const NAV_BUDGET = 8;         // consecutive steps hunting for the next question

const state = {
  running: false,
  stopRequested: false,
  tabId: null,
  steps: 0,
  questions: 0,
  cost: 0,
  log: []
};

async function settings() {
  const stored = await chrome.storage.local.get(['backend', 'token', 'model', 'note', 'advance']);
  return {
    backend: (stored.backend || DEFAULT_BACKEND).replace(/\/+$/, ''),
    token: stored.token || '',
    model: stored.model || '',
    note: stored.note || '',
    advance: stored.advance === true
  };
}

function emit(entry) {
  const row = { time: new Date().toLocaleTimeString(), ...entry };
  state.log.push(row);
  if (state.log.length > 300) state.log.shift();
  chrome.runtime.sendMessage({ type: 'log', row, state: snapshot() }).catch(() => {});
}

function snapshot() {
  return { running: state.running, steps: state.steps, questions: state.questions, cost: state.cost };
}

/* Reading and acting come from different places on purpose.

   The screenshot is of the whole visible tab, so it already contains every
   frame composited together -- that is what the model reads the question from,
   and it is why no frame has to be guessed at. The element index is only the
   vocabulary for acting, and it is gathered from every frame at once, with
   refs renumbered globally so one list can address the whole page. */

let refMap = new Map();     // global ref -> { frameId, ref } in that frame
let frameIds = [0];
let runOrigin = '';         // only frames from this origin are ever acted on
let actionFrameId = 0;      // frame to send frame-wide actions such as scroll
let activeFrameIds = [];    // frames that passed the origin check this step

async function injectAll(tabId) {
  const injected = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true }, files: ['content.js']
  });
  frameIds = injected.map((r) => r.frameId);
  return frameIds;
}

async function observeAllFrames(tabId) {
  const merged = { elements: [], text: '', host: '', digest: '' };
  refMap = new Map();
  activeFrameIds = [];
  let next = 1;

  for (const frameId of frameIds) {
    let page;
    try {
      page = await chrome.tabs.sendMessage(tabId, { type: 'observe' }, { frameId });
    } catch (error) {
      continue;                       // frame gone or not injectable; skip it
    }
    if (!page) continue;

    // A page may embed a third-party frame. Its controls are not ours to touch,
    // so they never enter the action map the model chooses from.
    if (runOrigin && page.origin && page.origin !== runOrigin) continue;

    // Remembered so the settle check later measures exactly these frames. If
    // the two digests covered different frames they could never match, and
    // every action would look as though it had landed instantly.
    activeFrameIds.push(frameId);
    if (!merged.host) merged.host = page.host;
    if (page.text) merged.text += (merged.text ? '\n\n' : '') + page.text;
    merged.digest += page.digest;
    const offset = page.frameOffset || { x: 0, y: 0, exact: true };
    if (merged.elements.length === 0) actionFrameId = frameId;
    for (const el of page.elements) {
      refMap.set(next, { frameId, ref: el.ref });
      // Shift into whole-tab coordinates so the list agrees with the screenshot.
      // Where the offset could not be measured through every ancestor, the
      // control stays usable by ref but reports no position at all.
      const box = el.box && offset.exact !== false
        ? { ...el.box, x: el.box.x + offset.x, y: el.box.y + offset.y }
        : null;
      merged.elements.push({ ...el, ref: next, box });
      next += 1;
      if (next > 300) break;
    }
  }
  return merged;
}

async function actOnRef(tabId, action) {
  // Scroll moves a whole frame and names no element, so there is nothing to
  // look up. Sending it through the ref map made scrolling impossible.
  if (action.action === 'scroll') {
    try {
      return await chrome.tabs.sendMessage(tabId, { type: 'act', action }, { frameId: actionFrameId });
    } catch (error) {
      return { ok: false, detail: 'Could not scroll that frame.' };
    }
  }

  const target = refMap.get(Number(action.ref));
  if (!target) return { ok: false, detail: 'That element is no longer listed. Re-observing.' };
  try {
    return await chrome.tabs.sendMessage(
      tabId, { type: 'act', action: { ...action, ref: target.ref } }, { frameId: target.frameId });
  } catch (error) {
    return { ok: false, detail: 'That frame went away before the action landed.' };
  }
}

async function digestNow(tabId) {
  let combined = '';
  // Exactly the frames the last observation covered, in the same order.
  for (const frameId of (activeFrameIds.length ? activeFrameIds : frameIds)) {
    try {
      const reply = await chrome.tabs.sendMessage(tabId, { type: 'digest' }, { frameId });
      if (reply) combined += reply.digest;
    } catch (error) { /* frame gone */ }
  }
  return combined;
}

/* Every screenshot belongs to exactly one decision, and is taken only once the
   previous action has visibly landed. Without this the loop photographs the
   page mid-transition and the model sees the question it has just answered --
   which looks like it is working from a stale picture, because it is. */
async function waitForEffect(tabId, priorDigest, budgetMs = 4000) {
  const started = Date.now();
  await new Promise((r) => setTimeout(r, 250));
  while (Date.now() - started < budgetMs) {
    const now = await digestNow(tabId);
    if (now !== priorDigest) {
      await new Promise((r) => setTimeout(r, 300));   // let it finish painting
      return true;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

async function guestToken(backend) {
  const res = await fetch(backend + '/api/guest', { method: 'POST' });
  if (!res.ok) throw new Error('The backend would not issue access. It may be restarting.');
  const data = await res.json();
  await chrome.storage.local.set({ token: data.token });
  return data.token;
}

async function decide(config, observation) {
  const call = async (token) => fetch(config.backend + '/api/agent/step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
    body: JSON.stringify(observation)
  });

  let token = config.token || await guestToken(config.backend);
  let res = await call(token);
  if (res.status === 401) {                       // token expired or backend restarted
    token = await guestToken(config.backend);
    res = await call(token);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.error || body.detail || '';
    } catch {
      try { detail = (await res.text()).slice(0, 300); } catch { detail = ''; }
    }
    throw new Error(`The backend refused this step (HTTP ${res.status})`
      + (detail ? `: ${detail}` : '. It returned no reason.'));
  }
  return res.json();
}

let screenshotWarned = false;

async function screenshot(windowId) {
  try {
    const shot = await chrome.tabs.captureVisibleTab(windowId, { format: 'png' });
    if (shot) return shot;
    throw new Error('Chrome returned an empty image.');
  } catch (error) {
    // Running without the picture is close to useless, and silently carrying on
    // is how it went unnoticed for a whole day. Say it once, loudly.
    if (!screenshotWarned) {
      screenshotWarned = true;
      emit({ kind: 'error', message: 'No screenshot could be taken — the agent is working from page text alone.',
             detail: (error && error.message ? error.message + ' ' : '')
                   + 'Reload the extension at chrome://extensions. If it persists, its permissions '
                   + 'no longer allow capturing the tab.' });
    }
    return '';
  }
}

async function run(tabId) {
  const config = await settings();
  const tab = await chrome.tabs.get(tabId);
  const origin = new URL(tab.url).origin;
  runOrigin = origin;

  state.running = true;
  state.stopRequested = false;
  state.tabId = tabId;
  state.steps = 0;
  state.questions = 0;
  state.cost = 0;
  state.log = [];
  emit({ kind: 'info', message: `Watching ${new URL(tab.url).host}` });

  let lastAction = null;
  let lastDigest = '';
  let repeats = 0;
  let stepInQuestion = 0;
  let checked = false;
  let recheck = false;   // a new question means looking again before acting
  let answered = false;  // one answering action has landed for the question on screen
  let navSteps = 0;      // consecutive steps spent looking for the next question
  let idleChecks = 0;    // read checks returned when an action was due
  let plan = '';         // the answer worked out when the question was read

  try {
    await injectAll(tabId);
      emit({ kind: 'info', message: `Reading the screenshot of this tab (${frameIds.length} frame${frameIds.length === 1 ? '' : 's'} merged for controls).` });

    while (!state.stopRequested && state.steps < SESSION_STEPS) {
      const current = await chrome.tabs.get(tabId);
      if (new URL(current.url).origin !== origin) {
        emit({ kind: 'stop', message: 'The tab moved to a different site. Stopping rather than following it.' });
        break;
      }

      const page = await observeAllFrames(tabId);
      const changed = page.digest !== lastDigest;
      // A read check changes nothing by design. Counting it as an unresponsive
      // page is what froze runs on questions the model kept re-reading.
      const lastWasAction = lastAction && lastAction.action !== 'read_check';
      if (!changed && lastWasAction) {
        repeats += 1;
        if (repeats >= REPEAT_LIMIT) {
          emit({ kind: 'stop', message: 'The page stopped responding to actions. Stopping instead of repeating.' });
          break;
        }
      } else {
        repeats = 0;
      }
      // The page moving on after we have acted means a different question is
      // probably on screen. Look again rather than acting on a stale reading.
      if (changed && checked && stepInQuestion > 0) recheck = true;
      lastDigest = page.digest;

      const observation = {
        screenshot: await screenshot(current.windowId),
        elements: page.elements,
        text: page.text,
        host: page.host,
        step: stepInQuestion + 1,
        step_budget: STEP_BUDGET,
        page_changed: changed,
        last_action: lastAction || {},
        task_note: checked ? config.note : '',
        plan,
        phase: navSteps > 0 ? 'navigate'
          : (!checked || recheck) ? 'read_check'
          : (idleChecks > 0 ? 'must_act' : 'act'),
        advance: config.advance,
        model: config.model
      };

      state.steps += 1;
      const result = await decide(config, observation);
      const action = result.action;
      state.cost += result.cost || 0;

      // Everything the model was given and everything it said, kept verbatim so
      // a misbehaving run can be read rather than guessed at.
      const sent = result.sent || {};
      emit({
        kind: 'think',
        message: `step ${state.steps} · ${sent.phase || 'act'} · ${action.action}`,
        detail: action.reason || '',
        sent: `${sent.elements} elements, ${sent.text_chars} chars of text, `
            + `screenshot ${sent.screenshot ? 'yes' : 'MISSING'}, `
            + `continuing ${sent.advance ? 'on' : 'off'}, model ${sent.model || '?'}`,
        working: result.working || '',
        raw: result.raw || '',
        cost: result.cost,
        tokens: `${result.input_tokens || 0} in / ${result.output_tokens || 0} out`
      });

      // The first step on any page is always the read check.
      if (!checked) {
        if (action.action !== 'read_check') {
          emit({ kind: 'info', message: 'Expected a read check first; asking again.' });
          lastAction = { action: 'read_check' };
          continue;
        }
        if (!action.has_question) {
          emit({ kind: 'stop', message: `No academic question found. ${action.reason || ''}`.trim() });
          break;
        }
        checked = true;
        state.questions += 1;
        plan = action.plan || '';
        if (plan) emit({ kind: 'plan', message: 'Plan: ' + plan });
        stepInQuestion = 0;
        emit({ kind: 'question', message: action.question, detail: `${action.kind || 'unknown'} · confidence ${action.confidence || 0}` });
        lastAction = { action: 'read_check' };
        continue;
      }

      if (action.action === 'read_check' && checked && navSteps === 0 && !recheck) {
        // The question is already known; re-reading it achieves nothing.
        idleChecks += 1;
        if (idleChecks > 2) {
          emit({ kind: 'stop', message: 'The model kept re-reading the question instead of answering it.' });
          break;
        }
        emit({ kind: 'info', message: 'Question already read; asking for an action.' });
        lastAction = { action: 'read_check' };
        continue;
      }

      if (action.action === 'read_check') {
        if (!action.has_question) {
          // Reading material, a summary or a loading screen between questions.
          // Keep going and look for the way forward instead of stopping.
          if (!config.advance) {
            emit({ kind: 'stop', message: `No question on screen. ${action.reason || ''}`.trim() });
            break;
          }
          plan = '';               // a new screen means the old plan is spent
          navSteps += 1;
          if (navSteps > NAV_BUDGET) {
            emit({ kind: 'stop', message:
              `Could not reach another question after ${NAV_BUDGET} tries. ${action.reason || ''}`.trim() });
            break;
          }
          emit({ kind: 'info', message: 'No question on screen — looking for the way forward.',
                 detail: action.reason || '' });
          recheck = false;
          lastAction = { action: 'read_check' };
          continue;
        }
        state.questions += 1;
        emit({ kind: 'question', message: action.question });
        plan = action.plan || '';
        if (plan) emit({ kind: 'plan', message: 'Plan: ' + plan });
        stepInQuestion = 0;
        recheck = false;
        navSteps = 0;
        idleChecks = 0;
        answered = false;            // a new question starts unanswered
        lastAction = { action: 'read_check' };
        continue;
      }

      if (action.action === 'done' || action.action === 'give_up') {
        emit({ kind: 'stop', message: `${action.action === 'done' ? 'Finished' : 'Gave up'}: ${action.reason || ''}` });
        break;
      }

      // With continuing switched off, the job is to answer and stop. Asking the
      // model nicely is not enough -- it will press Submit if left to itself.
      // Filling another box is still answering the same question; a click after
      // an answer is what submits or moves on.
      if (answered && !config.advance && action.action === 'click') {
        emit({ kind: 'stop', message:
          'Answer entered. Continuing is switched off, so the rest is yours — '
          + 'press the control that moves to the next question.' });
        break;
      }

      stepInQuestion += 1;
      if (stepInQuestion > STEP_BUDGET) {
        emit({ kind: 'stop', message: 'Used the step budget on one question without finishing. Stopping.' });
        break;
      }

      // The model call takes seconds. If Stop was pressed during it, the run
      // ends here rather than acting on a decision the user already cancelled.
      if (state.stopRequested) {
        emit({ kind: 'stop', message: 'Stopped by you before the next action was taken.' });
        break;
      }

      const outcome = await actOnRef(tabId, action);
      emit({
        kind: outcome.ok ? 'act' : 'warn',
        message: `${action.action}${action.ref ? ' ref ' + action.ref : ''}${action.text ? ' "' + action.text + '"' : ''}`,
        detail: `${action.reason || ''} ${outcome.detail || ''}`.trim()
      });
      if (outcome.ok && (action.action === 'fill' || action.action === 'click' || action.action === 'select')) {
        answered = true;
      }

      // Hold here until the page reacts. The next screenshot is then a picture
      // of the result of this action, never of the state that prompted it.
      let landed = true;
      if (outcome.ok && action.action !== 'scroll') {
        landed = await waitForEffect(tabId, page.digest);
      }

      lastAction = {
        action: action.action, ref: action.ref, ok: outcome.ok,
        detail: outcome.detail || '', landed
      };
    }
  } catch (error) {
    emit({ kind: 'error', message: error.message });
  } finally {
    // Never leave the pointer sitting on the student's page after a run.
    frameIds.forEach((frameId) =>
      chrome.tabs.sendMessage(tabId, { type: 'cursor_off' }, { frameId }).catch(() => {}));
    if (state.stopRequested) emit({ kind: 'stop', message: 'Stopped by you.' });
    state.running = false;
    chrome.runtime.sendMessage({ type: 'finished', state: snapshot() }).catch(() => {});
  }
}

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  if (message.type === 'start') {
    if (state.running) { reply({ ok: false, error: 'Already running.' }); return true; }
    run(message.tabId).catch(() => {});
    reply({ ok: true });
    return true;
  }
  if (message.type === 'stop') {
    state.stopRequested = true;
    reply({ ok: true });
    return true;
  }
  if (message.type === 'status') {
    reply({ ...snapshot(), log: state.log });
    return true;
  }
  return false;
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});
