/* The control surface. Arms the agent, starts and stops it, shows every step. */

const $ = (id) => document.getElementById(id);
const DEFAULT_BACKEND = 'https://positive-tranquility-production-9fdc.up.railway.app';
// Literally <all_urls>: captureVisibleTab accepts that or activeTab and nothing
// else, and https://*/* once cost a day of blind runs.
const ALL_SITES = ['<all_urls>'];

let armed = false;
let running = false;
let runPage = '';
let tabInfo = null;   // kept fresh so a permission request stays inside the user gesture

function paintEth() {
  const button = $('eth');
  button.classList.toggle('on', armed);
  button.classList.toggle('off', !armed);
  button.setAttribute('aria-pressed', String(armed));
  button.title = armed
    ? 'Armed: the agent may read and act on pages. Click to turn it off.'
    : 'Off: the agent cannot touch any page. Click to arm it and grant access.';
  $('start').disabled = !armed || running;
  $('stop').disabled = !running;
}

function banner(message, bad) {
  const el = $('banner');
  el.textContent = message || '';
  el.className = 'banner' + (bad ? ' bad' : '');
  el.hidden = !message;
}

const entries = [];

function addRow(row) {
  entries.push(row);
  paintActivity(row);
  if ($('log').querySelector('.muted')) $('log').replaceChildren();

  const li = document.createElement('li');
  li.dataset.kind = row.kind;
  if (row.kind === 'think' && !$('showthink').checked) li.className = 'hidden';

  const time = document.createElement('span');
  time.className = 't';
  time.textContent = row.time;
  const text = document.createElement('span');
  text.className = row.kind === 'question' ? 'question' : row.kind;
  text.textContent = row.message;
  if (row.click_details) {
    const box = document.createElement('details');
    box.className = 'click-details';
    const summary = document.createElement('summary');
    summary.textContent = row.message;
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(row.click_details, null, 2);
    box.append(summary, pre);
    li.append(time, box);
  } else li.append(time, text);

  if (row.opening_control) {
    const box = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Dropdown opening control: ' + row.opening_control.status;
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(row.opening_control, null, 2);
    box.append(summary, pre);
    li.append(box);
  }
  if (row.scroll_details) {
    const box = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Dropdown scroll details';
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(row.scroll_details, null, 2);
    box.append(summary, pre);
    li.append(box);
  }

  if (row.detail) {
    const detail = document.createElement('span');
    detail.className = 'd';
    detail.textContent = row.detail;
    li.append(detail);
  }

  if (row.sent || row.tokens) {
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = [row.sent, row.tokens,
      row.cost != null ? '$' + Number(row.cost).toFixed(5) : ''].filter(Boolean).join(' · ');
    li.append(meta);
  }

  if (row.working) {
    const box = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'thinking';
    const pre = document.createElement('pre');
    pre.textContent = row.working;
    box.append(summary, pre);
    li.append(box);
  }

  if (row.raw) {
    const box = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'raw reply';
    const pre = document.createElement('pre');
    pre.textContent = row.raw;
    box.append(summary, pre);
    li.append(box);
  }

  if (row.dom_observation) {
    const box = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'DOM sent to model';
    const pre = document.createElement('pre');
    pre.textContent = row.dom_observation;
    box.append(summary, pre);
    li.append(box);
  }

  $('log').append(li);
  $('log').scrollTop = $('log').scrollHeight;
}

$('showthink').onchange = () => {
  const show = $('showthink').checked;
  [...$('log').children].forEach((li) => {
    if (li.dataset.kind === 'think') li.className = show ? '' : 'hidden';
  });
};

$('copylog').onclick = async () => {
  const lines = entries.map((e) => {
    const bits = [`[${e.time}] ${e.kind.toUpperCase()}: ${e.message}`];
    if (e.detail) bits.push('  reason: ' + e.detail);
    if (e.sent) bits.push('  sent: ' + e.sent);
    if (e.tokens) bits.push('  tokens: ' + e.tokens + (e.cost != null ? '  cost: $' + Number(e.cost).toFixed(5) : ''));
    if (e.working) bits.push('  thinking: ' + e.working);
    if (e.raw) bits.push('  raw: ' + e.raw);
    if (e.dom_observation) bits.push('  DOM sent to model:\n' + e.dom_observation);
    if (e.click_details) bits.push('  Click details:\n' + JSON.stringify(e.click_details, null, 2));
    if (e.scroll_details) bits.push('  Scroll details:\n' + JSON.stringify(e.scroll_details, null, 2));
    for(const key of ['slot_count','screenshot_attached','dom_log_truncated','dom_log_characters','frame_id','target','inspection_source','opening_control','menu_scroll'])if(e[key]!=null)bits.push('  '+key+': '+JSON.stringify(e[key]));
    for(const key of ['request_id','model','requested_model','provider','reasoning_tokens','finish_reason','response_kind','output_format','format_corrections','phase','question_key','slot_key','task_id','adapter','requested_value','actual','failure_code','document_id','observation_id','action_executed','entry_verified','save_state','grade_state','duration'])if(e[key]!=null)bits.push('  '+key+': '+JSON.stringify(e[key]));
    return bits.join('\n');
  });
  const header = `Assignment Lab 2.0 log — ${new Date().toLocaleString()}\n`
    + `${$('questions').textContent} questions, ${$('steps').textContent} steps, ${$('cost').textContent}\n`
    + `model: ${[...new Set(entries.map(e => e.model).filter(Boolean))].join(', ') || '(no model call in this log)'}\n`
    + `page: ${runPage || $('page').textContent}\n${'-'.repeat(60)}`;
  try {
    await navigator.clipboard.writeText([header, ...lines].join('\n'));
    banner(`Copied ${entries.length} log entries.`);
  } catch (err) {
    banner('Could not copy. Select the log text manually.', true);
  }
};

function paintState(state) {
  running = state.running;
  if(state.runUrl)runPage=state.runUrl+' — '+(state.runTitle||'');
  $('questions').textContent = state.questions || 0;
  $('steps').textContent = state.steps;
  $('cost').textContent = '$' + (state.cost || 0).toFixed(4);
  $('progress').textContent = state.progress || 'No parts planned yet.';
  document.body.classList.toggle('running', running);
  const parts = (state.progress || '').match(/(\d+) of (\d+) parts/);
  $('part-meter').max = parts ? Math.max(1, Number(parts[2])) : 1;
  $('part-meter').value = parts ? Number(parts[1]) : 0;
  if (running) {
    if (!$('status-pill').dataset.tone) $('status-pill').textContent = 'Working';
    $('task-title').textContent = 'Working through your assignment';
    if ($('task-description').querySelector('br')) $('task-description').textContent = 'Reading, answering, and checking each part.';
  }
  else if ($('status-pill').textContent === 'Working') $('status-pill').textContent = 'Stopped';
  paintEth();
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab;
}

async function refreshPage() {
  const tab = await currentTab();
  if (!tab || !tab.url) { $('page').textContent = 'No tab in focus.'; return null; }
  if (!/^https?:/.test(tab.url)) {
    $('page').textContent = 'Switch to your assignment tab, then press Read this page.';
    tabInfo = null;
    return null;
  }
  $('page').textContent = new URL(tab.url).host + ' — ' + (tab.title || '').slice(0, 60);
  tabInfo = tab;
  return tab;
}

$('eth').onclick = async () => {
  const turningOn = !armed;

  if (turningOn) {
    // Nothing may be awaited before this: Chrome only accepts a permission
    // request raised directly by a click. If access was already granted this
    // resolves immediately and shows no dialog.
    let granted = false;
    try {
      granted = await chrome.permissions.request({ origins: ALL_SITES });
    } catch (err) {
      granted = false;
    }
    armed = true;
    await chrome.storage.local.set({ armed, blanket: granted });
    paintEth();
    banner(granted
      ? ''
      : 'Armed, but Chrome did not grant access to all sites. It will ask once per site instead.');
    return;
  }

  // Turning ETH off is a stop, not a colour change. A run in progress goes
  // through the same abort-and-cancel path as the Stop button, and the site
  // access granted on arming is handed back so red means what it says.
  armed = false;
  await chrome.storage.local.set({ armed });
  if (running) {
    await chrome.runtime.sendMessage({ type: 'stop' });
    running = false;
  }
  try {
    await chrome.permissions.remove({ origins: ALL_SITES });
  } catch (err) {
    // Chrome refuses to remove a permission that was never granted; that is fine.
  }
  paintEth();
  banner(running ? 'Stopping.' : 'Off. The agent cannot read or act on any page until ETH is armed again.');
};

async function accessGranted(origin) {
  try {
    return await chrome.permissions.contains({ origins: [origin] });
  } catch (err) {
    return false;
  }
}

function offerAccessFix(host) {
  banner('');
  const box = $('banner');
  box.className = 'banner bad';
  box.hidden = false;
  box.append(document.createTextNode(
    `Chrome is withholding access to ${host}. Open this extension's Details page and set `));
  const strong = document.createElement('strong');
  strong.textContent = 'Site access → On all sites';
  box.append(strong, document.createTextNode('. '));
  const link = document.createElement('button');
  link.textContent = 'Open Details';
  link.style.cssText = 'margin-top:6px;display:block';
  link.onclick = () => chrome.tabs.create({ url: 'chrome://extensions/?id=' + chrome.runtime.id });
  box.append(link);
}

$('start').onclick = async () => {
  const tab = tabInfo;
  if (!tab) { banner('Open the assignment page in this tab first.', true); return; }

  // Requesting first keeps this inside the click gesture; if access is already
  // held it resolves instantly with no dialog.
  const origin = new URL(tab.url).origin + '/*';
  let allowed = false;
  try {
    allowed = await chrome.permissions.request({ origins: [origin] });
  } catch (err) {
    allowed = await accessGranted(origin);
  }
  if (!allowed) allowed = await accessGranted(origin);
  if (!allowed) {
    offerAccessFix(new URL(tab.url).host);
    return;
  }

  banner('');
  $('log').replaceChildren();
  entries.length = 0;
  running = true;
  paintEth();
  const reply = await chrome.runtime.sendMessage({ type: 'start', tabId: tab.id });
  if (!reply || !reply.ok) {
    running = false;
    paintEth();
    banner((reply && reply.error) || 'Could not start.', true);
  }
};

$('stop').onclick = async () => {
  await chrome.runtime.sendMessage({ type: 'stop' });
};

$('advance').onchange = async () => {
  await chrome.storage.local.set({ advance: $('advance').checked });
};
for (const id of ['auto_submit', 'check_work']) {
  $(id).onchange = () => chrome.storage.local.set({ [id]: $(id).checked });
}
// The model runs as soon as it is chosen; it must not wait for Save like the text fields do.
$('model').onchange = async () => { await chrome.storage.local.set({ model: $('model').value.trim() }); banner($('model').value ? 'Model: ' + $('model').options[$('model').selectedIndex].text : 'Model: backend default'); };

$('save').onclick = async () => {
  await chrome.storage.local.set({
    backend: $('backend').value.trim() || DEFAULT_BACKEND,
    model: $('model').value.trim(),
    note: $('note').value.trim(),
    spend_limit: Number($('spend_limit').value) > 0 ? Number($('spend_limit').value) : 2.0
  });
  banner('Saved.');
};

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'log') {
    addRow(message.row);
    paintState(message.state);
  }
  if (message.type === 'finished') paintState(message.state);
});

(async function boot() {
  const stored = await chrome.storage.local.get(['backend', 'model', 'note', 'armed', 'advance', 'auto_submit', 'spend_limit', 'check_work']);
  $('check_work').checked = stored.check_work === true;
  $('spend_limit').value = stored.spend_limit || 2.0;
  $('backend').value = stored.backend || DEFAULT_BACKEND;
  $('model').value = stored.model || '';
  $('note').value = stored.note || '';
  armed = stored.armed === true;
  $('advance').checked = stored.advance === true;
  $('auto_submit').checked = stored.auto_submit === true;
  await refreshPage();
  const held = await accessGranted('<all_urls>');
  if (armed && !held) {
    $('page').textContent += '  ·  access withheld';
  }

  const status = await chrome.runtime.sendMessage({ type: 'status' });
  if (status) {
    (status.log || []).forEach(addRow);
    paintState(status);
  } else {
    paintEth();
  }
  chrome.tabs.onActivated.addListener(refreshPage);
  chrome.tabs.onUpdated.addListener(refreshPage);
})();


function paintActivity(row) {
  const labels = {think:'Planning next action', act:'Interacting with the page', question:'Reading your question', progress:'Checking progress', error:'Needs help', stop:'Stopped', submitted:'Submission sent'};
  if(row.phase){$('activity-title').textContent=({OBSERVE:'Reading question',PLAN:'Planning answers',EXECUTE:'Entering answers',VERIFY:'Verifying',INSPECT:'Inspecting widget',REPAIR:'Repairing task',LOCAL_RECOVERY:'Recovering widget',NEEDS_REVIEW:'Needs review',CANCELLED:'Stopped',FINISH:'Finished',ADVANCE:'Next question'})[row.phase]||row.phase;$('activity-detail').textContent=row.message;}
  if (!row.phase && labels[row.kind]) {
    $('activity-title').textContent = labels[row.kind];
    $('activity-detail').textContent = row.detail || row.message;
  }
  if (row.kind === 'question') {
    $('task-title').textContent = 'Working through your assignment';
    $('task-description').textContent = row.message;
  }
  if (row.kind === 'error' || row.kind === 'stop') {
    $('status-pill').textContent = labels[row.kind];
    $('status-pill').dataset.tone = row.kind;
  } else if (row.kind === 'info') {
    $('status-pill').dataset.tone = '';
  }
}
function showSettings(open) {
  $('settings-view').hidden = !open;
  $('workspace').hidden = open;
  $('settings-toggle').setAttribute('aria-expanded', String(open));
  $('settings-toggle').setAttribute('aria-label', open ? 'Close settings' : 'Open settings');
}
$('settings-toggle').onclick = () => showSettings($('settings-view').hidden);
$('settings-back').onclick = () => showSettings(false);
function displayPreferences() {
  $('activity-log').hidden = !$('show-log').checked;
  $('cost').parentElement.hidden = !$('show-cost').checked;
}
for (const id of ['show-log', 'show-cost']) $(id).onchange = () => {
  displayPreferences();
  chrome.storage.local.set({[id]: $(id).checked});
};
function paintSummaries() {
  $('continue-summary').textContent = 'Auto-continue ' + ($('advance').checked ? 'on' : 'off');
  $('submit-summary').textContent = 'Submission ' + ($('auto_submit').checked ? 'on' : 'off');
}
for (const id of ['advance', 'auto_submit']) $(id).addEventListener('change', paintSummaries);
chrome.storage.local.get(['show-log', 'show-cost', 'advance', 'auto_submit']).then(stored => {
  $('show-log').checked = stored['show-log'] !== false;
  $('show-cost').checked = stored['show-cost'] !== false;
  $('continue-summary').textContent = 'Auto-continue ' + (stored.advance ? 'on' : 'off');
  $('submit-summary').textContent = 'Submission ' + (stored.auto_submit ? 'on' : 'off');
  displayPreferences();
});

$('resume-run').onclick = async () => {
  if(!armed || !tabInfo) {banner('Arm ETH and select the original assignment tab to resume.',true);return;}
  const result=await chrome.runtime.sendMessage({type:'resume',tabId:tabInfo.id});
  if(!result?.ok)banner(result?.error||'Could not resume.',true);else showSettings(false);
};

chrome.storage.local.get(['planner_run']).then(({planner_run})=>{
  if(planner_run?.status==='running'&&!running)banner('A saved run was interrupted. Open Settings and choose Resume saved planner run to re-check entered answers before continuing.');
});
