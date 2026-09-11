/* The control surface. Arms the agent, starts and stops it, shows every step. */

const $ = (id) => document.getElementById(id);
const DEFAULT_BACKEND = 'https://positive-tranquility-production-9fdc.up.railway.app';
const ALL_SITES = ['https://*/*', 'http://*/*'];

let armed = false;
let running = false;
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
  li.append(time, text);

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
    return bits.join('\n');
  });
  const header = `Assignment Lab log — ${new Date().toLocaleString()}\n`
    + `${$('questions').textContent} questions, ${$('steps').textContent} steps, ${$('cost').textContent}\n`
    + `page: ${$('page').textContent}\n${'-'.repeat(60)}`;
  try {
    await navigator.clipboard.writeText([header, ...lines].join('\n'));
    banner(`Copied ${entries.length} log entries.`);
  } catch (err) {
    banner('Could not copy. Select the log text manually.', true);
  }
};

function paintState(state) {
  running = state.running;
  $('questions').textContent = state.questions || 0;
  $('steps').textContent = state.steps;
  $('cost').textContent = '$' + (state.cost || 0).toFixed(4);
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

  armed = false;
  await chrome.storage.local.set({ armed });
  paintEth();
  banner('');
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

$('save').onclick = async () => {
  await chrome.storage.local.set({
    backend: $('backend').value.trim() || DEFAULT_BACKEND,
    model: $('model').value.trim(),
    note: $('note').value.trim()
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
  const stored = await chrome.storage.local.get(['backend', 'model', 'note', 'armed', 'advance']);
  $('backend').value = stored.backend || DEFAULT_BACKEND;
  $('model').value = stored.model || '';
  $('note').value = stored.note || '';
  armed = stored.armed === true;
  $('advance').checked = stored.advance === true;
  await refreshPage();
  const held = await accessGranted('https://*/*');
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
