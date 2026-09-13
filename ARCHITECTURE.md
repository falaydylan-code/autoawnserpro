# Architecture

Two halves that talk over HTTPS.

    Chrome extension  ->  FastAPI backend on Railway  ->  OpenRouter
    (reads the page,       (holds the API key,             (the model)
     performs actions)      meters spend, decides)

The extension never holds a provider key. Anything shipped to a browser is
readable by whoever installs it, so every model call goes through the backend.

## The agent loop

`extension/background.js` owns it and runs one step at a time:

1. **Observe** — screenshot the whole visible tab (`chrome.tabs.captureVisibleTab`)
   and gather interactive elements from every frame, renumbered into one global
   list with a private map back to the owning frame.
2. **Decide** — POST that to `/api/agent/step`. `agent.py` builds the prompt and
   returns exactly one action from a closed list.
3. **Act** — `extension/content.js` performs it and reads the result back.
4. **Settle** — poll for a changed structural fingerprint followed by two equal
   readings, bounded to four seconds. A DOM change is not answer verification.
5. **Verify** — independently re-read the planned target value or containment
   using the frame map. Update the part ledger; only then consider navigation.

The screenshot is the source of truth for reading. The element index exists only
so the model has something to name when acting.

## Files worth reviewing closely

| file | what to look at |
|---|---|
| `agent.py` | the system prompt, the closed action vocabulary, `parse_action` validation |
| `app.py` | auth, throttles, `safe_url`, CORS, the `/api/agent/step` endpoint |
| `extension/content.js` | what is exposed to the model, what is refused in the page |
| `extension/background.js` | step and session caps, loop detection, origin checks |
| `store.py` | per-owner spend metering (`reserve_call` / `settle_call`) |

## Security model

Informed by observed browser-agent behavior; this is our own implementation.

- **Instructions come only from the system prompt.** Page text is fenced as
  `BEGIN UNTRUSTED PAGE TEXT` and is data, never commands.
- **The action vocabulary is closed** — `read_check`, `fill`, `click`, `select`,
  `scroll`, `drag`, `reorder`, `visual_click`, `visual_drag`, `verify`, `press`,
  `scroll_to`, `done`, `give_up`. Anything else is rejected before execution, so a
  page cannot introduce a verb. `verify` is accepted only in the verification
  phase and can never execute anything.
- **Real mouse input is a bounded fallback, not the default.** `reorder`, the
  `visual_*` verbs and clicks on a `widget` (a closed-shadow host the DOM cannot
  see into) go through `chrome.debugger` (`extension/visual.js`). It attaches to
  the assignment tab only, only while needed, and detaches on Stop, ETH off,
  completion or failure. Every visual action is tied to the exact screenshot
  the model saw (`observation_id`); a changed viewport, URL, digest or pixel hash
  makes it stale and it is refused. Guard refusals — off the answer area, on a
  navigation or sensitive control, cross-origin — are returned to the model to
  re-aim, never thrown. A gesture interrupted by Stop releases the button at its
  origin, because releasing at the destination would complete the drop.
- **The extension checks `/api/capabilities` before its first paid call** and
  refuses to run against a backend without protocol 2. Extension and backend
  ship together; this is the seam that broke silently in 0.6.0.
- **Two witnesses verify an answer.** The DOM reads the control back, and a
  separate `verify`-phase model call reads a fresh screenshot and may only
  report what is visible. With the panel's "confirm each answer with a
  screenshot" switch on (the default) a part is verified only when both agree
  (`settle()` in `background.js`); where the DOM cannot read the control, the
  screenshot decides alone; a DOM `false` always wins. A model's claim of
  success is never evidence. The screenshot witness is a paid call, so with the
  switch off the DOM alone verifies and the screenshot is used only where the
  DOM is blind.
- **A visual point must hit the planned control.** When the part's control is
  known, a `visual_*` point (the destination, for a drag) has to land on it or
  on the menu it owns, not merely in the same table. A gesture is abandoned the
  moment the tab navigates or starts loading. A closed-shadow `widget` is an
  answer candidate only inside an answer region and at control size — not page
  chrome — so component shells cannot block hand-in or attract a click.
- **The unfinished controls are the question's identity.** A re-read that points
  at controls the current plan still has work on is the same question however
  the stem is phrased; a finished question never absorbs the next one, so a page
  that reuses one input per question gets a new question each time. When the
  page names its questions (`data-question-id`, taken from the container of the
  plan's own controls), a different name is a different question. A cell already
  owned keeps its part rather than growing a twin. Sharpening an unentered
  answer to the visible label is a refinement; changing an answer outright is
  taken once — the part is reset and re-entered — and refused the second time.
- **Credential and payment fields are never described to the model**, so it
  cannot be asked to fill one (`sensitive()` in `content.js`).
- **Hand-in requires a worker-issued permit**, produced only with the hand-in
  switch on and all known parts verified. The page executor defaults to refusal,
  including Enter/Space on terminal buttons. Enter in a field is refused because
  it can implicitly submit a form. Part tabs work independently of Keep going.
- **Destructive, account, consent and download controls are refused** in the
  page (`REFUSED` in `content.js`, classified `control: 'refused'`) and again in
  the worker, for click and Enter/Space. So are links that leave the site
  (`external`). Same-origin navigation and neutral buttons like Check or Show
  hint stay clickable, because courseware needs them.
- **Site access is optional and ETH owns it.** The manifest requires only the
  backend host; `<all_urls>` is an optional permission taken when ETH is armed
  and handed back when it is disarmed, which also stops a run in progress. It has
  to be literally `<all_urls>` — `captureVisibleTab` accepts nothing narrower.
- **An answer without a plan becomes the plan.** A model that skips the parts
  checklist is asked once more, then its first answer is adopted as a one-part
  ledger (`coverage.adopt`) and verified from page state like any declared part.
  A question that *was* planned still refuses an answer aimed at an unplanned
  control. Refusing the unplanned case outright killed every plain MCQ run.
- **Private and internal addresses are blocked** (`safe_url` in `app.py`), so
  the public endpoint cannot be aimed at the host's own network.
- **The run stops if the tab changes origin**, and controls from frames of any
  other origin are never added to the action map, so an embedded third-party
  frame cannot be clicked.
- **The model's own decision wins**, not the first JSON-looking thing in its
  reply, so a page cannot smuggle an action through by being quoted.

Repeated lesson, worth keeping in mind while reviewing: prompt instructions are
suggestions, harness rules are rules. Anything that must not happen is enforced
in code, and the prompt only explains why.

## Known weak points

- Synthetic pointer/keyboard events cannot satisfy every site's trusted-input
  requirement. Closed shadow roots and cross-origin frames remain unavailable;
  warnings pause hand-in rather than claiming complete coverage.
- Verification proves the planned value or drop landed, not academic correctness.
- MiniMax passed public MathPapa and local multipart/matching checks. Canvas and
  MyLab have not been validated with this version.

- The public dashboard has no authentication by design; spend is bounded by
  per-network caps rather than by identity.
- Guest identity is a random token; the spend budget is keyed to a hash of the
  client IP, which conflates users behind one NAT.
- The agentic path writes no server-side history, so runs cannot be audited
  after the fact.
- `safe_url` cannot pin the browser to the address it validated. It remembers
  the first answer per host and refuses a later change, which narrows the
  rebinding window without closing it.
- `frontend/` and `adapters.py` are the older selector-driven path, kept as a
  fallback. They are not on the extension's code path.

## Reference reading

`CONTEXT_BROWSER_USE.md` compares this loop against browser-use, the most mature
open-source version of the same idea, and lists what is worth taking from it.
The context file distinguishes the ideas adopted in 0.6.0 from future work.

## Question coverage (0.6.0)

`extension/coverage.js` owns the per-question part ledger and navigation policy.
Plans use stable target keys across observations; matching also binds a source
key through `source_ref`. A successful action is followed by independent value
or containment verification. Hidden unfinished parts remain outstanding. Hand-in
defaults off and requires all discovered parts/tabs covered, no unplanned visible
answer controls, and no observation warnings. Keep going is a separate switch.

Observation includes grouped controls, prose blank context, table headers, open
shadow roots, NEW markers and global screenshot badges. Drag tries click,
keyboard, HTML5 and pointer paths in that order, stopping on unexpected changes.
The worker caps work, detects repeated/oscillating actions, rechecks stale pages,
and cancels pending calls on Stop. These checks do not guarantee discovery of
every custom widget; site-specific validation is still required.

## Running it

    pip install -r requirements.txt
    pytest -q            # offline regression suite, no key needed
    python app.py        # serves on 127.0.0.1:8010

Load `extension/` unpacked at `chrome://extensions` with Developer mode on.
After an upgrade, reload the extension AND the assignment page. Use the matching
backend version; the older deployed backend does not accept the new action fields.
