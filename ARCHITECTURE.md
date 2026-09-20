> **0.10.18 structured table context:** Supplement the existing question text with rendered HTML table cells at zero-based row/column positions, explicit header/scope and merged-cell spans, literal units/signs, captions and frame IDs. Blank cells remain in position; answer cells are marked and their values remain in slots.current. The table snapshot never creates targets or contributes to identity. Exclude presentation tables, nested layout wrappers, hidden contents and option menus. Bound extraction to six tables/300 cells/12,000 text characters per frame, 200 rows/256 columns, and twelve tables/60,000 serialized characters per observation; incomplete flags disclose limits. Typed backend schema and planner guidance preserve the structure through the existing request and copy log. No extra provider calls or academic correctness validation. This does not add cross-frame question context or section-tab discovery.

> **0.10.13 dropdown controls:** Read-only dropdown inspection now returns opening-control evidence alongside options. The observer registers the same freshly resolved controls for execution: contained expand buttons, explicit slot/menu linkage, or a uniquely labelled detached button whose center overlays its answer cell. Text editors are excluded; multiple candidates stop execution. Live McGraw markup places its Show All Items button outside the TD. Temporary dropdown editors/buttons do not contribute to fallback question identity. Copy log records control status and ownership evidence. Model-requested inspect_options returns an object with options and opening_control; the existing backend evidence envelope accepts it without a protocol change.

> **0.10.15 dropdown discovery and inspection mapping:** Read existing DOM choices first. When choices do not yet exist, the coordinator may activate the cell and open its associated menu once per slot, read the options and dismiss it; discovery never selects an answer. Those allowances persist on resume, and existing values are reconciled before planning. Cache choices per slot/document, never by nearby column. Scripts run in the observed question iframe with a harness-provided `resolveSlot(slot_key)` helper; opaque slot keys are not HTML IDs/selectors. Slot metadata now includes `frame_id` and `dom_id`. Ambiguous frame mapping, stale documents, overlay/ownership failures and cancellation stop inspection. Backend capability `frame_scoped_inspection` is required before starting. This supersedes the 0.10.11 prohibition on discovery activation; model-authored scripts remain read-only and optional.

> **0.10.5 inspection contract:** Known-control inspections use an exact observed slot key. Question discovery uses an empty slot key with `inspect_question`, or a script-only request. Structured output constrains these forms and offered IDs. The backend rejects invalid inspection targets before execution; the coordinator may request one paid correction per question with fresh slot IDs, tracked durably and metered separately (`inspection_correction`, maximum one). Repeated rejection, uncertain cost, Stop, stale documents, deadlines and spend caps still stop the run. Inspection resolves fresh live targets, and custom menu discovery waits for cell activation, arrow and owned options. No inspection is mandatory for fully observed questions.

> **0.10.0 update (2026-09-15):** The structured planner is now the only extension workflow, by user request. There is no workflow toggle or legacy rollback in the installed extension. Model-authored JavaScript inspection remains on-demand for missing information. Earlier preview/rollback instructions below are historical. Live platform validation remains a separate gate.

> **0.10.16 interaction classification:** A focusable response cell is an answer location, not automatically a dropdown. Positive native/ARIA/menu evidence identifies selections; ambiguous cells are `unresolved`. The coordinator may activate an unresolved cell once, then inspect fresh evidence. A packaged jQuerySheet adapter recognizes the sheet container and formula control, double-clicks once to reveal an editor, and associates a unique visible overlay textarea with the active cell by geometry. Only observing that editor establishes `value`; an empty option list never does. The same logical slot survives editor creation/destruction. Identification actions and budgets persist on resume; cached editor evidence expires on a new question. Text execution reopens the editor, checks ownership/focus before typing, commits with Tab and reads the original cell. Contained numeric/textarea controls expose their current value directly. Unknown or ambiguous widgets remain unresolved. The planner cannot override interaction types, and verification requires both matching type and value. Classification evidence appears in the DOM/copy log. Required backend capability: `interaction_classification`.

> **0.10.17 offscreen answer targets:** Packaged measurement returns clipping/scroll state for every target, including the document viewport; previously only dropdown options received it. Hidden controls remain excluded. The executor reveals a rendered target with real wheel input, checks actual scroll-offset movement, refreshes frame origins/target geometry, then hit-tests before clicking. Enclosing frames are revealed from the page inward; cross-origin offsets are recomputed after scrolling. Page wheel points avoid unrelated scroll widgets/iframes and fixed/sticky overlays. Cell activation hit-tests run only after visibility is established. At most 12 scroll actions per measure, with existing task recovery/deadline/Stop guards; no additional model calls for revealing fields. Logs distinguish page versus container scrolling and record offsets, deltas and movement. This does not add full-question context collection, reference-graph reading or answer-tab enumeration.

## 0.10.38 discovery and bounded recovery (pending release)

Question text preserves aria-live containers; feedback roles/classes and explicit live feedback remain excluded. Structural choice discovery keeps complete rendered labels plus explicit accessibility labels, groups only repeated local sibling branches, shares navigation exclusions, and establishes single/multiple selection from visible instructions (including numeric counts). Native controls retain their existing adapters. Candidate groups initially remain unresolved; packaged `classify_choices` rechecks membership, labels, cardinality and boolean state attributes before promotion, preserving the logical slot. Missing/ambiguous evidence never authorizes an answer click. Discovery is bounded to 400 filtered candidates and reports overflow independently of DOM extraction completeness.

Named answer containers with unique option-N cards have a separate result contract: one complete single-choice group, one durable attempt, feedback on the exact executed card, and a screenshot cropped to that card. The verifier receives pre-answer question context and only the chosen option; wrong answers stop before any repair/screenshot request can disclose a revealed key. The result must remain stable across capture. A later question transition cannot redirect or replay the old task, and continuation follows the user's advance setting. SVG result icons and the CSS animated check component were observed by Claude on live Quizlet; exact animated-icon ancestry/live execution remain release-validation prerequisites. A missing marker, early transition, interrupted attempt, multiple answer groups or partial/offscreen crop stops explicitly. No fixed auto-advance delay is assumed.

Inspection facts accumulate with question/document scope, superseding the same fact without discarding distinct facts. A multi-frame script is one evidence entry containing its per-frame results. Fourteen entries/32 KB are hard limits with explicit overflow failure. Parent-frame context is retained and answer-frame tables have priority. Hard extraction limits stop before metered requests; transient incomplete data permits bounded inspection but no answer execution. Unknown controls prevent completion; jSheet cells lacking its existing editable `.response` marker are read-only only within the recognized table/formula contract, and are rechecked after row answers can unlock them.

Malformed JSON has a separate `InvalidJsonError` and one metered `format_correction` attempt per question, enforced on client and server across resume. Rejected raw output is never repaired heuristically or executed. Stop, stale identity, uncertain cost and existing budgets still abort. Backend capabilities `choice_discovery` and `bounded_format_correction` gate this extension; release both halves at 0.10.38, backend first.

# Protocol 4 planner preview

See [PLANNER_ROLLOUT.md](PLANNER_ROLLOUT.md) for the new opt-in architecture.
The description below is retained for the protocol-3 rollback loop.

# Architecture

Two halves that talk over HTTPS.

    Chrome extension  ->  FastAPI backend on Railway  ->  OpenRouter
    (reads the page,       (holds the API key,             (the model)
     performs actions)      meters spend, decides)

The extension never holds a provider key. Anything shipped to a browser is
readable by whoever installs it, so every model call goes through the backend.

## Browser input (0.8.0)

Every interaction is real browser input on the tab the run is bound to, driven
through `chrome.debugger` / CDP (`extension/visual.js`): pointer moves, single
and double clicks, button-held drags through waypoints, wheel scrolling, typed
text, and keys with modifiers (Enter, Tab, Shift+Tab, arrows, Escape, Backspace,
Delete, Control+a). The DOM is used to *find* controls and to *read their state
back*; it is never used to fake an interaction. Where a control has no DOM
presence (a canvas graph point, a closed-shadow widget) the model aims from the
screenshot and the point is checked against the current screen before use. The
DOM path survives only as the fallback for a frame whose offset cannot be
measured, and it says so when it is used.

Two facts were checked in a loaded extension before this was built, not assumed:
`Page.captureScreenshot` and `Input.*` both work on a background tab, so a run
continues while the student uses other tabs; and `Input.synthesizeScrollGesture`
hangs on a background tab, so scrolling uses wheel events with the result
confirmed by the scroll position actually moving.

## Bound to one tab

The run belongs to the tab Start was pressed on (`runSite`, `boundTab`). Same-
site navigation inside the assignment is followed; a move to another site, or
the tab closing, or the debugger detaching, stops the run. Switching tabs does
not move or cancel it and focus is never stolen back. A ~20 s heartbeat keeps
the MV3 worker alive across the long waits on the model.

## Page states

`content.js` classifies each screen: answering, editable_feedback (graded, retry
allowed), locked (graded, inputs disabled), loading, complete. On locked
feedback the worker records the outcome, retires the unfinished parts (never
marking them correct), and follows Next/Continue if continuing is on. On
editable feedback it allows a revised plan. On complete it stops.

## No question ceiling, bounded retries

A run continues until the assignment is complete, the student stops it, the
spending limit is reached, or a bounded retry runs out: six no-progress turns,
the same answer interaction failing three times, model answer flip-flop, or four
self-changes of the page mid-decision. Navigation and looking do not feed the
persistent-failure counter. A completed part resets its counters. The old fixed
per-run step ceiling is gone.

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
- **The action vocabulary is closed** — `read_check`, `look`, `fill`, `click`,
  `dblclick`, `hover`, `select`, `scroll`, `scroll_to`, `press`, `drag`,
  `reorder`, `visual_click`, `visual_drag`, `verify`, `done`, `give_up`. Anything
  else is rejected before execution, so a page cannot introduce a verb. `press`
  takes a key matched against a whitelist regex, never an arbitrary string.
  `verify` is accepted only in the verification phase and can never act.
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
