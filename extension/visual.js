/* Browser-level input for the assignment tab, through chrome.debugger (CDP).

   Every interaction the agent performs goes through here: pointer moves,
   clicks, drags, wheel scrolling, typing and keys are real browser input
   events on the ONE tab the run is bound to, whether or not that tab is in
   front. The DOM is used to find and read controls; it is never used to fake
   an interaction. Two things were checked in a loaded extension before this
   was written, not assumed: Page.captureScreenshot and Input.* both work on a
   background tab, and Input.synthesizeScrollGesture hangs forever there, so
   scrolling is done with wheel events. */
(() => {
  let attached = null;          // tabId the debugger is attached to
  let cancelled = false;        // set by detach, navigation, or the tab going away
  let gestureUrl = '';          // the document a gesture was validated against
  let gestureStart = null;      // where the button went down, for a safe release
  let buttonHeld = false;
  const keysHeld = new Set();
  const pause = ms => new Promise(r => setTimeout(r, ms));

  const KEYS = {
    Enter: {code: 'Enter', vk: 13, text: '\r'}, Tab: {code: 'Tab', vk: 9}, Space: {code: 'Space', vk: 32, text: ' '},
    Escape: {code: 'Escape', vk: 27}, Backspace: {code: 'Backspace', vk: 8}, Delete: {code: 'Delete', vk: 46},
    ArrowUp: {code: 'ArrowUp', vk: 38}, ArrowDown: {code: 'ArrowDown', vk: 40}, ArrowLeft: {code: 'ArrowLeft', vk: 37}, ArrowRight: {code: 'ArrowRight', vk: 39},
    Home: {code: 'Home', vk: 36}, End: {code: 'End', vk: 35}, PageUp: {code: 'PageUp', vk: 33}, PageDown: {code: 'PageDown', vk: 34},
  };
  const MODIFIERS = {Alt: 1, Control: 2, Meta: 4, Shift: 8};

  function cdp(id, method, params) { return chrome.debugger.sendCommand({tabId: id}, method, params || {}); }

  async function attach(id) {
    if (attached === id) return;
    if (attached != null) await detach();
    cancelled = false;
    try { await chrome.debugger.attach({tabId: id}, '1.3'); attached = id; }
    catch (e) { throw new Error('Browser input unavailable: Chrome refused to attach its debugger to the assignment tab (' + (e.message || e) + '). Close DevTools or another debugger for that tab and start again.'); }
    // The very first capture after attaching differs from every later one (an
    // attach-time repaint), which made a fresh snapshot read as stale. Take a
    // throwaway capture so the first one anybody compares is settled.
    try { await cdp(id, 'Page.captureScreenshot', {format: 'png', fromSurface: true}); await pause(80); } catch {}
  }

  // Releases whatever is held, then lets go of the tab. Called on Stop, ETH off,
  // completion and failure. A held button is released where the gesture BEGAN:
  // at the destination it would complete a cancelled drop, at (0,0) it would
  // drop at the page corner.
  async function releaseAll(id) {
    if (id == null) return;
    if (buttonHeld && gestureStart) { try { await cdp(id, 'Input.dispatchMouseEvent', {type: 'mouseReleased', x: gestureStart.x, y: gestureStart.y, button: 'left', buttons: 0, clickCount: 1}); } catch {} }
    buttonHeld = false;
    for (const key of [...keysHeld]) { const k = KEYS[key] || {code: key}; try { await cdp(id, 'Input.dispatchKeyEvent', {type: 'keyUp', key, code: k.code}); } catch {} }
    keysHeld.clear();
  }
  async function detach() {
    cancelled = true;
    const id = attached; attached = null;
    if (id != null) { await releaseAll(id); try { await chrome.debugger.detach({tabId: id}); } catch {} }
    gestureStart = null;
  }
  chrome.debugger.onDetach.addListener(({tabId}) => { if (tabId === attached) { attached = null; cancelled = true; buttonHeld = false; keysHeld.clear(); } });
  chrome.tabs.onUpdated.addListener((tabId, change) => { if (tabId === attached && (change.url || change.status === 'loading')) cancelled = true; });
  chrome.tabs.onRemoved.addListener(tabId => { if (tabId === attached) { attached = null; cancelled = true; } });

  // Every event re-checks that the tab is still the document the caller
  // validated. It does NOT check that the tab is active: input is bound to the
  // target tab, and the student switching tabs must not redirect or cancel it.
  async function guard(id, stopped) {
    if (cancelled || attached !== id) throw new Error('Browser input cancelled.');
    if (stopped?.()) throw new Error('Stopped before browser input.');
    let tab; try { tab = await chrome.tabs.get(id); } catch { throw new Error('The assignment tab is gone.'); }
    if (gestureUrl && (tab.url !== gestureUrl || tab.status === 'loading')) throw new Error('The page navigated during browser input; the gesture was abandoned.');
    return tab;
  }
  // Adopt the current document as this gesture's, THEN guard. Guarding first
  // would compare the fresh page against the previous gesture's URL and reject
  // the first move after any navigation.
  async function begin(id, stopped) { await attach(id); gestureUrl = ''; const tab = await guard(id, stopped); gestureUrl = tab.url; cancelled = false; return tab; }

  async function mouse(id, type, pt, extra, stopped) {
    await guard(id, stopped);
    await cdp(id, 'Input.dispatchMouseEvent', {type, x: pt.x, y: pt.y, button: 'left', clickCount: 1, ...extra});
  }

  async function move(id, pt, stopped) { await begin(id, stopped); await mouse(id, 'mouseMoved', pt, {button: 'none', clickCount: 0}, stopped); return {ok: true, detail: 'Pointer moved.'}; }

  async function click(id, pt, {count = 1, button = 'left'} = {}, stopped) {
    await begin(id, stopped);
    await mouse(id, 'mouseMoved', pt, {button: 'none', clickCount: 0}, stopped);
    for (let n = 1; n <= count; n++) {
      gestureStart = pt; buttonHeld = true;
      await mouse(id, 'mousePressed', pt, {button, buttons: 1, clickCount: n}, stopped);
      await pause(30);
      await mouse(id, 'mouseReleased', pt, {button, buttons: 0, clickCount: n}, stopped);
      buttonHeld = false; gestureStart = null;
      if (n < count) await pause(60);
    }
    return {ok: true, detail: count > 1 ? 'Double-clicked.' : 'Clicked with browser input.'};
  }
  async function down(id, pt, stopped) { await begin(id, stopped); await mouse(id, 'mouseMoved', pt, {button: 'none', clickCount: 0}, stopped); gestureStart = pt; buttonHeld = true; await mouse(id, 'mousePressed', pt, {buttons: 1}, stopped); return {ok: true, detail: 'Button held.'}; }
  async function up(id, pt, stopped) { await guard(id, stopped); await mouse(id, 'mouseReleased', pt, {buttons: 0}, stopped); buttonHeld = false; gestureStart = null; return {ok: true, detail: 'Button released.'}; }

  // Drag with the button held through intermediate points, then release. A
  // gesture halted by Stop, navigation or an error releases at its START.
  async function input(id, start, end, stopped) {
    await begin(id, stopped);
    let completed = false;
    gestureStart = start;
    try {
      await mouse(id, 'mouseMoved', start, {button: 'none', clickCount: 0}, stopped);
      buttonHeld = true;
      await mouse(id, 'mousePressed', start, {buttons: 1}, stopped);
      if (end) for (let i = 1; i <= 16; i++) { await pause(25); await mouse(id, 'mouseMoved', {x: start.x + (end.x - start.x) * i / 16, y: start.y + (end.y - start.y) * i / 16}, {buttons: 1}, stopped); }
      await pause(60);
      await mouse(id, 'mouseReleased', end || start, {buttons: 0}, stopped);
      buttonHeld = false; completed = true;
      return {ok: true, detail: 'Browser input executed; awaiting independent verification.'};
    } finally {
      if (!completed && attached === id) { try { await cdp(id, 'Input.dispatchMouseEvent', {type: 'mouseReleased', x: start.x, y: start.y, button: 'left', buttons: 0, clickCount: 1}); } catch {} buttonHeld = false; }
      gestureStart = null;
    }
  }

  // Wheel scrolling at a point (over a container to scroll it, or anywhere over
  // the page). The caller confirms the scroll position actually moved.
  async function wheel(id, pt, dx, dy, stopped) {
    await begin(id, stopped);
    await mouse(id, 'mouseMoved', pt, {button: 'none', clickCount: 0}, stopped);
    await guard(id, stopped);
    await cdp(id, 'Input.dispatchMouseEvent', {type: 'mouseWheel', x: pt.x, y: pt.y, deltaX: dx, deltaY: dy, pointerType: 'mouse'});
    return {ok: true, detail: 'Wheel scrolled.'};
  }

  // Keys. `spec` is "Enter", "Shift+Tab", "Control+a", "ArrowDown", "a" ...
  function parseKey(spec) {
    const parts = String(spec).split('+').filter(Boolean);
    const key = parts.pop();
    let modifiers = 0; for (const m of parts) { if (!(m in MODIFIERS)) throw new Error('Unsupported modifier ' + m); modifiers |= MODIFIERS[m]; }
    if (KEYS[key]) return {key: key === 'Space' ? ' ' : key, code: KEYS[key].code, vk: KEYS[key].vk, text: modifiers ? undefined : KEYS[key].text, modifiers, name: key};
    if (key.length === 1) { const upper = key.toUpperCase(); const code = /[A-Z]/.test(upper) ? 'Key' + upper : /[0-9]/.test(upper) ? 'Digit' + upper : ''; return {key, code, vk: upper.charCodeAt(0), text: modifiers & ~MODIFIERS.Shift ? undefined : key, modifiers, name: key}; }
    throw new Error('Unsupported key ' + spec);
  }
  async function key(id, spec, stopped) {
    await begin(id, stopped);
    const k = parseKey(spec);
    const commands = k.modifiers === MODIFIERS.Control && k.key.toLowerCase() === 'a' ? ['selectAll'] : undefined;
    keysHeld.add(k.name);
    await guard(id, stopped);
    await cdp(id, 'Input.dispatchKeyEvent', {type: k.text ? 'keyDown' : 'rawKeyDown', key: k.key, code: k.code, windowsVirtualKeyCode: k.vk, nativeVirtualKeyCode: k.vk, modifiers: k.modifiers, text: k.text, unmodifiedText: k.text, commands});
    await cdp(id, 'Input.dispatchKeyEvent', {type: 'keyUp', key: k.key, code: k.code, windowsVirtualKeyCode: k.vk, nativeVirtualKeyCode: k.vk, modifiers: k.modifiers});
    keysHeld.delete(k.name);
    return {ok: true, detail: 'Pressed ' + spec + '.'};
  }
  async function selectAll(id, stopped) { return key(id, 'Control+a', stopped); }
  async function insertText(id, text, stopped) {
    await begin(id, stopped);
    await guard(id, stopped);
    await cdp(id, 'Input.insertText', {text: String(text)});
    return {ok: true, detail: 'Typed.'};
  }
  // Type letter by letter as key events -- what a native <select>'s typeahead
  // and some editors listen for. insertText does not reach them.
  async function typeKeys(id, text, stopped) {
    for (const ch of String(text)) { if (ch === ' ') await key(id, 'Space', stopped); else if (/[A-Za-z0-9]/.test(ch)) await key(id, ch, stopped); await pause(20); }
    return {ok: true, detail: 'Typed key by key.'};
  }

  // A screenshot of the bound tab, front or back. Returns a data URL plus the
  // CSS viewport it was taken at, so callers can convert normalised points.
  async function screenshot(id) {
    await attach(id);
    if (cancelled) { cancelled = false; }
    const shot = await cdp(id, 'Page.captureScreenshot', {format: 'png', fromSurface: true, captureBeyondViewport: false});
    const metrics = await cdp(id, 'Page.getLayoutMetrics');
    const v = metrics.cssVisualViewport || metrics.visualViewport;
    return {dataUrl: 'data:image/png;base64,' + shot.data, viewport: {width: Math.round(v.clientWidth), height: Math.round(v.clientHeight), scrollX: Math.round(v.pageX), scrollY: Math.round(v.pageY), scale: v.scale || 1}};
  }

  async function pixels(data) {
    const bitmap = await createImageBitmap(await (await fetch(data)).blob());
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height), ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0); bitmap.close();
    const bytes = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).join(',');
  }

  globalThis.AssignmentVisual = {attach, detach, input, move, click, down, up, wheel, key, selectAll, insertText, typeKeys, screenshot, pixels, parseKey,
    get attachedTab() { return attached; }, get held() { return buttonHeld; }};
})();
