# Assignment Lab 2.0 — Standard Operating Procedure (extension 0.8.0)

Assignment Lab is a Chrome extension that works through a student's own online
coursework, in the tab they already have open and signed in, by looking at the
page, deciding one move at a time with an AI model, and performing that move
with real browser input — never claiming an answer is done until the page itself
proves it.

This SOP documents every piece of the running system, how each works, and how to
operate, deploy and troubleshoot it. Companion documents: `ARCHITECTURE.md` (the
map), `AGENTS.md` (the working agreement and the hard-won rules), `HANDOFF.md`
(session history), `CONTEXT_*.md` (evidence and open issues).

---

## 1. The principle everything follows

**The model proposes; the harness decides; the page proves.** The AI model is
clever but unreliable, so it may only *suggest* one move per turn from a fixed
list. The extension (the "harness") decides whether that move is allowed and
performs it. Nothing counts as done on the model's word — only on evidence read
back from the page. Anything that must never happen is enforced in code, never
by asking the model politely.

---

## 2. The parts of the system

| Piece | File | Role |
|---|---|---|
| Side panel | `extension/sidepanel.{html,js,css}` | The control surface: ETH arm/disarm, Start/Stop, settings, and the live step log. |
| Background worker ("the boss") | `extension/background.js` | Owns the run loop, holds every limit and safety rule, drives real input, keeps the ledger. Cannot see the page directly. |
| Content script | `extension/content.js` | Injected into every frame of the page. The only piece that touches the DOM: it reads controls, reports page state, and reads answers back. |
| Browser-input adapter | `extension/visual.js` | Real mouse/keyboard/scroll/screenshot through `chrome.debugger` (Chrome DevTools Protocol). |
| Coverage policy | `extension/coverage.js` | The per-question ledger, question identity, the hand-in gate, the oscillation guard — pure logic, shared with the tests. |
| Backend | `agent.py`, `app.py` (Railway) | Holds the OpenRouter key, builds the model prompt, validates the model's reply, returns one action. Speaks **protocol 3**. |
| Model | MiniMax (via OpenRouter) | Reads a screenshot, decides one move. Never sees the key; never trusted for verification. |

The extension never holds the API key: anything shipped to a browser can be read
by whoever installs it, so every model call goes through the backend.

---

## 3. Starting a run

1. The student opens the assignment and signs in as normal.
2. Opens the side panel and clicks **ETH** green. This requests the optional
   `<all_urls>` site permission (Chrome asks once). Red means the agent cannot
   touch any page; turning it red mid-run stops the run and hands the permission
   back.
3. Clicks **Start**. The worker's `run(tabId)` then, in order:
   - records the tab's **site** (`runSite`) — the run is bound to it from here on;
   - calls `compatible()` — GETs `/api/capabilities` and refuses to continue
     unless the backend reports `protocol: 3` and every required feature
     (`parts, ordering, visual_input, visual_verification, browser_input,
     page_states`). A stale backend produces a clear "Backend update required"
     message and no paid model call;
   - attaches the debugger to the tab (`AssignmentVisual.attach`);
   - injects the content script into every frame (`injectAll`);
   - starts a 20-second **heartbeat** so Chrome does not reap the worker during
     long waits on the model.

---

## 4. One turn of the loop (`run()` in `background.js`)

Every turn runs these steps. The loop repeats until a stop condition (§13).

### 4.1 Safety and re-read — `observeResilientFor` → `boundTab`
Before reading anything, `boundTab` confirms the tab is still on `runSite`. If it
left the site, or the tab closed, the run stops **before** the new page is read
or photographed. If the tab navigated within the same site (e.g. "Next" loaded a
new page), the content scripts were destroyed, so the worker re-injects them and
rebuilds the frame list, then reads. If a read still finds no frame, it
re-injects once more and retries.

### 4.2 Observe — `observeAllFrames` → `content.js observe()`
The content script builds the observation for each frame; the worker merges them
into one, renumbering every control with a **global ref** (a per-turn number the
model uses to name a control). Refs are reassigned every turn and never reused.
Each control carries: role, accessible name, table row/column, "blank N of M",
group (its enclosing question/table/list), whether it is a `dropdown`, a
`trigger` (a dropdown's arrow button), an `opaque` widget (a closed-shadow host
the DOM cannot see into), a drag `source`/`target`, `list_ref`/`order_index` for
ordering, `owner_ref` (which cell a menu option belongs to), `control`
classification (`terminal`/`advance`/`part`/`refused`), `external` (a link that
leaves the site), `disabled`, `box` (on-screen position), and a stable `key`.
The observation also reports **page state** (§10), a structural **digest** used
to detect change, and warnings.

### 4.3 Read back existing answers — `refreshEvidence`
For every answer already planned, the content script is asked what the control
holds *now* (witness #1, gathered before the model gets a turn). See §9.

### 4.4 Take the screenshot — `makeSnapshot` → `capture`
A screenshot of the tab (via `AssignmentVisual.screenshot`, CDP — works even if
the tab is in the background), stamped with a unique `observation_id`, plus the
viewport it was taken at and a pixel hash. `capture` first hides the green
cursor and takes a settled photo (two consecutive identical captures) so a
snapshot and its later re-check match. A screenshot that cannot be taken stops
the turn — the model is never called blind.

### 4.5 Decide — `decide` → backend → model
The worker POSTs the observation (screenshot, control list, page state,
progress, ledger, last action, phase) to `/api/agent/step`. `agent.py` builds
the prompt, calls MiniMax, and validates the reply with `parse_action`: only the
closed vocabulary is accepted, the reply is the **last** valid JSON object (so
quoted page text cannot smuggle a move), and a malformed reply gets one
corrective retry. A call is bounded by `DECISION_TIMEOUT_MS` (240 s). The model
returns exactly one action.

### 4.6 Gate — `executeAction` in `background.js`
Before performing the move, the worker: normalises the verb (a `select` on a
custom menu becomes the click it is; `dblclick` becomes `click` count 2);
resolves which planned part the move is for; and refuses anything unsafe —
destructive/account/consent/download controls, off-site links, disabled
controls, an answer aimed at an unplanned control, a menu option that belongs to
a different cell, or an oscillation (§11). A hand-in control needs a permit (§9).

### 4.7 Perform — real browser input (§7)
The gated move is done with a real mouse/keyboard through CDP, falling back to
the DOM only where a coordinate cannot be measured (and saying so).

### 4.8 Settle and verify — `waitForEffect`, `verifyVisual` (§9)
Wait for the page to stop changing (two identical readings), re-observe, read
the answer back, and — by default — confirm it against a fresh screenshot.

### 4.9 Score and continue
If a part became verified, reset the stall counter. Follow an advance/terminal
control's result; loop again.

---

## 5. The move vocabulary (`ACTIONS` in `agent.py`)

`read_check`, `look`, `fill`, `click`, `dblclick`, `hover`, `select`, `scroll`,
`scroll_to`, `press`, `drag`, `reorder`, `visual_click`, `visual_drag`,
`verify`, `done`, `give_up`.

- **read_check** — always the first move on a page: is there a question? If yes,
  the model returns the `parts` checklist (every answer, with the ref of its
  control or `null` when it can only be reached by screenshot).
- **look / hover** — re-observe or move the pointer without acting (exploration,
  not failure).
- **fill** — focus a field with a real click, select-all, type the text.
- **click / dblclick** — a real mouse click (or double) at the control.
- **select** — a native `<select>`: opened and driven by the **keyboard**
  (typeahead, then arrows), because a synthetic click does not reliably open a
  native popup.
- **scroll / scroll_to** — wheel-scroll the page or a container, or bring a ref
  into view; the result is confirmed by the scroll position actually moving.
- **press** — a key or chord (Enter, Tab, Shift+Tab, arrows, Escape, Backspace,
  Delete, Control+a, letters), matched against a whitelist.
- **drag / reorder** — a real button-held drag between two controls, or moving
  an ordering item before/after another in the same list.
- **visual_click / visual_drag** — a real click/drag at normalised screenshot
  coordinates (0..1), for controls with no DOM ref (graph points, closed-shadow
  fields). Tied to the current `observation_id`.
- **verify** — verification phase only: report what a control visibly shows;
  cannot perform any action.
- **done / give_up** — finish or abandon. `done` with parts outstanding is
  refused once with the list of what is missing.

---

## 6. Observation and control identity

- **Refs** are per-turn labels for controls; they change every observation, so a
  move always uses the current turn's refs.
- **Keys** are stable identities used by the worker to recognise a control
  across turns (for reading answers back and for question identity).
- **Groups** tie controls into a question; **owner_ref** ties a menu option to
  its dropdown cell; **list_ref/order_index** describe ordering lists.
- **Opaque widgets** — custom elements with a closed shadow root and no readable
  interior — are listed as `role: widget` with a position, only inside an answer
  region, so the model can click them by ref and the worker uses real input.

---

## 7. Browser input (`visual.js`, via `chrome.debugger` / CDP)

Every interaction is a real browser event on the bound tab, not a synthetic DOM
event or a direct value set. The DOM is used only to *find* and *read* controls.
Supported: pointer move/hover, left click, double-click, button-down/up, drag
through interpolated waypoints with the button held, wheel scroll (vertical and
horizontal, page or container), focus + type + select-all + clear, and keys with
Shift/Control/Alt/Meta. Custom dropdowns: open (a click on the cell or its arrow)
→ observe the menu → click the option → verify the cell. Graphs: normalised
screenshot coordinates converted to viewport pixels.

Two facts this rests on were **verified in a loaded extension, not assumed**:
`Page.captureScreenshot` and `Input.*` work on a background tab (so a run
continues while the student uses other tabs), and `Input.synthesizeScrollGesture`
hangs on a background tab (so scrolling uses wheel events). A held button or key
is always released on Stop, ETH-off, navigation, or failure — a cancelled drag
releases at its **origin**, never its destination.

---

## 8. Real input is bound to one tab

The run belongs to the tab Start was pressed on. Same-site navigation inside the
assignment (`siteOf` is public-suffix aware, so `github.io`/`co.uk` tenants are
distinct while courseware subdomains stay together) is followed by re-injecting
scripts. Any of these ends or stops the run: the tab leaving the site, the tab
closing, or the debugger detaching (e.g. the student presses Cancel on Chrome's
debugging bar). Switching to another tab does **not** move or cancel the run, and
focus is never stolen back.

---

## 9. Verification — two witnesses (`refreshEvidence`, `verifyVisual`, `settle`)

An answer is proven, never assumed. Four states are kept apart: *input executed*,
*field changed*, *entered value matches the plan*, *website graded it*. Only the
third means a part is "done", and it is judged by:

- **Witness 1 — the DOM.** The content script reads the control's value/state
  back (`domVerified`).
- **Witness 2 — a screenshot.** With the **Confirm each answer with a
  screenshot** switch on (default), a fresh photo is sent to the model in the
  `verify` phase, and it must read the planned value back (`visualConfirmed`).

`settle(part)` is the single place `verified` is decided: a DOM `false` always
wins (the value is not there); where the DOM cannot read the control (closed
shadow, canvas) the screenshot decides alone; with double-check on, both must
agree; an "inconclusive" screenshot does not veto a DOM that read the value.
Hand-in (`gate` in `coverage.js`) is refused unless every known part is verified
— including parts retired by graded feedback but never actually entered (a wrong
or unfinished answer still blocks submission, even though it no longer blocks
moving to the next question).

---

## 10. Page states (`content.js pageState`)

Each observation classifies the screen and the worker acts on it:

- **answering** — enter answers normally.
- **editable_feedback** — the page graded the attempt and allows another try;
  answers may be revised (a revised plan is allowed).
- **locked** — graded and inputs disabled; the worker records the outcome,
  retires the unfinished parts *without marking them correct*, and follows the
  page's Next/Continue if continuing is enabled.
- **loading** — wait once, then re-read.
- **complete** — the assignment reports it is finished; the run stops.

---

## 11. Question identity and the plan (`coverage.js`)

- The **answer controls are a question's identity**, not its wording. A re-read
  whose parts point at controls an existing (non-locked, non-retired) question
  owns is the same question, however the stem is rephrased; the page's own
  `data-question-id` overrides when present. A finished question never adopts new
  work.
- **One cell, one part** — a re-read that renames an owned cell adopts the
  existing part rather than growing a twin.
- **Before entry** the model may re-plan an answer freely. **After** a value has
  been entered, changing it is taken once (the part is reset) and refused the
  second time (the oscillation guard). Flip-flopping between two values, or the
  same signature four times, stops the run and names both values.

---

## 12. Settings (side panel → Setup)

- **Backend** — where thinking happens (default: the Railway service).
- **Model** — blank uses the backend default (MiniMax M3); must accept images.
- **Note for the agent** — optional guidance, e.g. "answer in decimals".
- **Keep going after each question** (`advance`) — lets the agent press
  Next/Continue and move on; off means it stops after one question.
- **Hand in when every known part is verified** (`auto_submit`) — off by
  default; even on, hand-in is refused until every part is verified.
- **Number controls in screenshots** (`badges`) — draws ref numbers on the photo.
- **Confirm each answer with a screenshot** (`double_check`) — on by default;
  adds the second witness (one extra model call per answer).
- **Stop a run after spending ($)** (`spend_limit`) — the only hard ceiling;
  default $2.00.

---

## 13. When a run stops

There is **no cap on questions or turns**. A run ends only when:

- the assignment reports **complete**, or a terminal hand-in is confirmed;
- the student presses **Stop**, turns **ETH** red, or **closes the tab**;
- the **spend limit** is reached;
- a **bounded retry** runs out: `STALL_LIMIT` 6 (turns with no verified
  progress), `INTERACTION_RETRIES` 3 (same move failing the same way — navigation
  and looking do not count), `VISUAL_FAILURES` 3 (a part's screenshot check),
  answer flip-flop, `SHIFT_LIMIT` 4 (the page changing itself mid-decision),
  `NAV_BUDGET` 8 (turns hunting for the next question), or the per-question
  action allowance `budget()` = min(240, 10 + 8 × parts).

Any stop that is not a clean completion names the specific part that needs the
student. Progress on a part resets its counters, so a healthy long run is never
capped.

---

## 14. Safety rules enforced in code (not by prompting the model)

- Closed action vocabulary, validated server-side; `verify` only in its phase.
- Credential/payment fields are never described to the model.
- Destructive/account/consent/download controls and off-site links are refused
  in the page and again in the worker, for click and Enter/Space.
- Hand-in requires the switch and full verification (§9).
- The run is bound to its site and stops on a cross-site move (§8), checked
  before any read of a redirected page.
- The model's decision, not the first JSON in its reply, is used.
- Every model call must report its cost or the action is discarded; per-network
  spend caps live on the backend.

---

## 15. Deploying (backend and extension ship together)

The extension refuses a backend older than its protocol, so deploy them
together. Backend:

    cd deploy-source && railway up --ci --project 6195f77e-b5c7-4a03-b554-8b1e4e848474 \
      --environment 7c66aa24-8b5d-41cf-b41d-508dfc5a096a --service 50fe1453-47fb-46c0-b0bd-c007c5201f98

(`deploy-source/` is a generated copy of the app files; never edit or commit it.)
Confirm `/api/capabilities` returns `protocol: 3`. Extension: bump
`extension/manifest.json` version, then **remove and re-load** the unpacked
`extension/` folder in `chrome://extensions` (a plain refresh can keep a stale
build). The panel prints the version on the first line of every run.

Testing: `pytest -q` must stay green (no network, no key). The loaded-extension
browser tests can flake under the full-suite load — re-run a browser failure in
isolation before treating it as real. `scripts/check_coverage_live.py` runs
MiniMax through the loaded extension against a fixture (real API credit; ordinary
`pytest` does not).

---

## 16. Troubleshooting

| Symptom | Cause / action |
|---|---|
| "Backend update required" | Extension and backend out of step. Deploy the backend from this commit. |
| "Browser input unavailable" | DevTools or another debugger is on the tab. Close it and Start again. |
| "Screenshot unavailable" | Chrome could not picture the tab. Re-open the page and Start. |
| "It says there's no question" | Usually correct — a menu/results page. Move to the question. |
| A part stays "entered, not yet verified" | The page took the input but the value is not where the agent looks, or the screenshot disagrees. The log names the part; check that field. |
| "cannot activate navigation, submission or sensitive controls" on a real answer field | The visual guard is over-strict on some real courseware (see `CONTEXT_MCGRAW_LOG_0813.md`). Known open issue. |

---

## 17. Known limits

- The model is the ceiling on the hardest cases (graph pixel math, occasional
  dithering). The harness always fails safe and names the blocked part; choosing
  a stronger model is `../model-eval`'s job.
- Closed shadow roots and cross-origin frames cannot be read; those fields are
  reachable only by screenshot coordinate.
- Verification proves the planned value is present, not that it is academically
  correct.
- Live McGraw Hill acceptance is not yet passing end to end — see
  `CONTEXT_MCGRAW_LOG_0813.md` for the specific gap (visual guard tuning,
  ref-less part identity, part-id stability).
