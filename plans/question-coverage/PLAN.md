> Execution update ? 2026-09-11: Dylan explicitly authorized Codex to execute the
> whole plan, overriding the provisional owner split and review-loop prerequisite.
> No joint Claude approval is claimed. T1?T7 are implemented in the isolated
> `codex/question-coverage` worktree. T8 documentation is complete; its Canvas/MyLab
> live-courseware acceptance remains pending a selected accessible practice page.
>
> Implementation adjustments: coverage policy lives in `extension/coverage.js` for
> direct testing. Matching plans include `source_ref` so account-name answers can
> still verify the exact source/destination pair. Hidden parts may have an empty
> answer until opened. Closed shadow roots cannot be inspected or reliably
> detected; unresolved custom elements produce a conservative warning. Tests were
> expanded after implementation for newly discovered failures; one negative-test
> callback installer was corrected to avoid executing the callback during setup.
> The original pre-implementation observation tests did fail against old code.
>
> Live evidence: MiniMax completed multipart and pointer-matching fixtures and one
> public MathPapa addition question with correct page feedback. These are smoke
> checks, not an accuracy benchmark or proof of Canvas/MyLab compatibility.

# Question coverage: read hard answer boxes, drag, and finish every part

## Context

The agent handles a multiple-choice question and a simple text blank. Everything
harder fails, and Dylan has hit three failures on his own coursework:

1. **It cannot read answer boxes more complex than a radio button** — fill-in-the-blank
   in running prose, drag-and-drop matching, blanks inside a table.
2. **It cannot drag anything at all.**
3. **On a multi-part question it submits after part A** instead of moving to part 2.

He also said this list is not exhaustive, and it is not. But each of the three
traces to a specific, findable gap, and the evidence is already in the code:

| Symptom | Actual cause |
|---|---|
| Cannot read complex boxes | `observe()` emits a **flat list**. No table geometry, no `draggable` items, no drop targets, no `role=gridcell/option/listbox`, nothing inside shadow DOM. `fieldContext()` returns `''` for every `<textarea>` because `el.type` is `'textarea'`, which is not in its whitelist. `tableContext()` is reached only as the *fifth* label fallback, so any blank with a placeholder never gets its row and column at all. |
| Cannot drag | The vocabulary is `read_check, fill, click, select, scroll, done, give_up`. There is no pointer event, no `DataTransfer`, no key press anywhere in the repo. `click` is `el.click()` only, so a widget listening on `pointerdown` never hears it. `actOnRef` rewrites exactly one `ref`, so a two-ended action has no route to the page. |
| Submits after part A | `answered` is a **boolean** set by any successful `fill`/`click`/`select`. `plan` is one string, discarded at every question boundary. A `read_check` on part B counts as a brand-new question and resets the step budget. And the prompt *tells* the model that "Submit Answer" is how you advance. |

There is also a fourth gap that hides the other three: `digest` is the first 4000
characters of `innerText` plus every form value. A drag that only moves a node
changes neither, so **a successful drag and a failed drag look identical** to
`waitForEffect` and to the repeat detector. Oscillation ("picks the right answer,
then the wrong one") is invisible for the mirror-image reason — every radio click
flips a `checked` bit, so the digest always changes and `repeats` resets to zero.

Two documents outside the repo's paper trail already diagnosed most of this and
were never acted on: `C:\Users\falay\video-review-20260911\review-notes.md` (a
frame-by-frame review of Claude in Chrome solving exactly the McGraw-Hill
three-pair matching question we cannot express) and `browser-use-context.md`
alongside it. This plan is largely their backlog, made concrete. It also takes
the four cheapest wins from `CONTEXT_BROWSER_USE.md`: structure instead of a flat
list, marking what is new since the last step, drawing the element index onto the
screenshot, and growing `plan` into a real running memory.

**Dylan's decisions for this plan:** target MathPapa/open practice, Pearson
MyLab/Mastering, and Canvas/Blackboard quizzes first. Drags try the click path
before any synthetic gesture. The agent **is** allowed to hand in the assignment.

That last one reverses a rule this repo enforced in code, so it is worth one
sentence of disagreement: handing in unattended means a wrong answer is graded
before he sees it, and `AGENTS.md` says a silent wrong answer costs him marks. So
it is built, but the terminal click is gated in code on the part ledger saying
every part of every question is complete and verified, and there is an off switch
in the panel. The bug he actually hit — submitting after part A — is fixed by
that gate, not by forbidding the button.

## Shape of the change

Four layers, in dependency order. Each is useful on its own and the later ones
depend on the earlier ones, which is also the task order.

    1. SEE      observe() emits structure, not a longer list
    2. ACT      new verbs: drag, press, click modes, scroll to element
    3. TRACK    a part ledger replaces the `answered` boolean
    4. PROVE    verification and loop control that can see a move

---

## 1. SEE — structure instead of a longer list

`extension/content.js`, `observe()` and its helpers.

**Serialise as a shallow tree.** Each element gains `group` (the ref of its
nearest enclosing question/fieldset/table/list container) and `depth`, and
`agent.py` renders children indented under their group. A table of six answer
boxes and two radio groups belonging to different questions stop looking like
eight interchangeable siblings. This is `CONTEXT_BROWSER_USE.md`'s item 3, and it
is the single change that most directly addresses "cannot read complex boxes".

**Extend what counts as interactive.** Add to `INTERACTIVE`:

- `[draggable=true]`, `[aria-grabbed]`, and the library markers the target sites
  actually ship: `[data-rbd-draggable-id]`, `[data-rbd-droppable-id]`,
  `[data-dnd-kit-id]`, `.ui-draggable`, `.ui-droppable`, `[aria-dropeffect]`
- `[role=gridcell]`, `[role=cell]`, `[role=option]`, `[role=listbox]`,
  `[role=tab]`, `[role=switch]`, `[role=spinbutton]`, `[role=slider]`
- `[contenteditable]` as a plain attribute selector, plus an `el.isContentEditable`
  test, so `plaintext-only` and odd casing stop being invisible

Each element gains `drag: 'source' | 'target' | null` so the model can see what is
draggable without inferring it from a name.

**Traverse open shadow roots.** `querySelectorAll` does not cross a shadow
boundary, so any courseware built on web components is currently invisible.
Recurse into `el.shadowRoot` where it is open; a closed root cannot be traversed
and must be reported as such, not silently skipped.

**Fix the two silent label failures.**
- `fieldContext()`: `<textarea>` has `el.type === 'textarea'`, which fails the
  input-type whitelist, so every textarea gets no context. Gate on tag, not type.
- `tableContext()`: promote it out of the label fallback chain into its own
  structured fields `row` and `column` on the descriptor, always populated for a
  control inside a `<td>`. Resolve the header properly — `<thead>`, `scope=`,
  `colspan` offsets, and the nearest header row rather than the table's first
  `<tr>`. Today a blank with a placeholder never learns which row it is in.

**Number the blanks.** A sentence with three blanks gets
`blank 2 of 3` on each field, and `fieldContext()` marks where its siblings sit in
the prose rather than returning only the words either side of one.

**Mark what is new.** Elements absent from the previous observation are flagged
`NEW` (browser-use's `*[38]`). A validation message, a revealed Part 2 tab, or a
drop target that only appears mid-drag becomes obvious instead of being something
the model has to notice by diffing two lists it cannot see at once.

**Draw the refs onto the screenshot.** The model reads `[12]` off the picture
instead of correlating a list of coordinates against pixels — browser-use's
highest-value item, and it retires the frame-offset problem for reading.

There is a trap here worth naming, because the obvious implementation is wrong.
Refs are **per-frame and local** inside `content.js`; the numbers the model
actually sees are assigned in `background.js` by `observeAllFrames`, which
renumbers globally. So badges cannot be painted during `observe()` — that would
label every frame `1, 2, 3…` and the model would act on the wrong element. The
order must be: `observeAllFrames` returns, then `background.js` sends each frame a
`badges` message carrying *its* elements' global refs, then `captureVisibleTab`,
then `badges_off`. That is one extra round trip per step. `observe()` also calls
`hideUI()` at its top, so the badge layer must be separate from the cursor layer
or observing will erase it.

Badges are drawn at box corners, partially transparent, offset outward where they
would cover the element's own text. An element with `box: null` gets no badge, the
same way it already gets `position unknown` rather than a guessed coordinate. Risk
is occlusion, so there is a side-panel toggle.

## 2. ACT — the verbs the pages need

`extension/content.js` `act()`, `extension/background.js` `actOnRef`, `agent.py`
`ACTIONS` and `Action`.

Four new verbs. The vocabulary stays **closed and validated server-side** — this
adds entries to `ACTIONS`, it does not loosen the check:

    {"action":"drag",      "ref":7, "to":12}
    {"action":"press",     "ref":7, "key":"Enter"|"Tab"|"ArrowDown"|"Escape"|"Backspace"}
    {"action":"scroll_to", "ref":7}
    {"action":"click",     "ref":7, "mode":"pointer"}     // mode is optional

`press` takes a **closed key list**, not arbitrary key strings. `drag` requires
both refs to resolve to the **same frame** and refuses otherwise, because a
cross-frame drag cannot be synthesised. `actOnRef` is generalised to translate
every ref-shaped field (`ref`, `to`) through `refMap`, instead of rewriting the
single key `ref`.

Two existing details must move with the vocabulary or they will rot silently:

- `agent.py`'s `require == 'act'` gate is implemented as "anything that is not
  `read_check`", so new verbs pass it automatically — but its **re-prompt message
  hard-codes the old list** ("fill, click, select, scroll, done or give_up"). Left
  alone it would tell the model a vocabulary that no longer matches.
- `content.js` `act()` ends in `'Unsupported action.'` and `background.js`
  branches on literal verb names in four places. Neither is a declared allow-list.
  The new verbs must be added to both, and the closed list in `agent.py` remains
  the only authority.

**The drag executor**, in `content.js`, tries strategies in this order and
re-observes between each — Dylan's choice, and the right one, because a synthetic
drag that half-works is worse than one that visibly fails:

1. **Click the source, then click the target.** Most matching widgets on the
   target platforms accept this, and Canvas matching is usually `<select>`
   anyway. Cheapest and most reliable.
2. **Keyboard.** Where the source takes focus and responds to Space/Arrow/Space,
   which is what an accessible dnd library exposes.
3. **HTML5 drag-and-drop** with a real `DataTransfer`: `dragstart` on the source,
   then `dragenter`/`dragover` on the target — each `dragover` must have
   `preventDefault()` observed or `drop` will not be accepted — then `drop`, then
   `dragend`.
4. **Pointer gesture**: `pointerdown` on the source, several `pointermove` steps
   past the library's movement threshold using `elementFromPoint` at each
   waypoint, `pointerup` on the target, with `mousedown`/`mousemove`/`mouseup`
   mirrors for widgets that only listen to mouse events.

**The honest part:** synthesised events carry `isTrusted: false`. Native HTML5
drag-and-drop is driven by the browser's own drag loop, which a content script
cannot start, so strategy 3 works only where the page implements its own handlers
and does not check `isTrusted` — and strategies 3 and 4 will each fail outright on
some widgets. So every strategy is followed by a **verification re-observation**,
and if none of the four verifies, `drag` returns `ok:false` with which strategies
were tried. It never reports a success it did not confirm. If `chrome.debugger`
turns out to be the only path for a specific platform, that is a separate decision
for Dylan — it shows a "being debugged" banner across his browser and is not
something to adopt quietly.

**The green cursor learns to hold a press.** Today `moveTo` is one 420 ms
transform hop and `pressEffect` is a fire-and-forget pulse. A drag needs a
pressed state held across several waypoints, so `place()` gains a waypoint walk
and the dot gains a `.held` class. Without this a drag is invisible to Dylan,
which defeats the point of the visible cursor.

## 3. TRACK — a part ledger, not a boolean

`extension/background.js`.

`read_check` gains a `parts` array: the parts the model has committed to
completing before this question is finished, each with the answer it intends.

    {"action":"read_check", ..., "parts":[
       {"id":"a", "what":"blank 1 — cash collected", "answer":"2600"},
       {"id":"b", "what":"blank 2 — on account",     "answer":"1400"}]}

`background.js` holds this as the **ledger** for the current question and, per
step, marks each part `entered` (an action targeting it succeeded) and `verified`
(a fresh observation shows that value present). `answered` — a boolean set by any
successful action — is deleted. In its place:

- **A terminal control is refused in code unless the ledger is complete.** The
  existing `HANDS_IN` / `TERMINAL_EXACT` regexes stop being a blanket refusal and
  become a *classification*: terminal vs advance. A terminal click with parts
  outstanding is refused, naming them. A terminal click with every part verified
  is allowed, if Dylan's hand-in switch is on. This is the fix for the reported
  bug, and it is in the harness, not the prompt.
- **The advance-off guard stops firing early.** Today `answered && !advance &&
  click` ends the run on the first click after *any* answer, which kills every
  multi-part question. It becomes `ledgerComplete() && !advance && terminal`.
- **Stable question identity.** A normalised hash of the question text decides
  whether a `read_check` is a new question or a re-read of the current one. A
  re-read keeps the ledger, the plan, and the step budget. Today every re-read
  counts as a new question and resets everything — which is why a drag that
  changes the page mid-question loses the plan.
- **Progress-aware budget.** `STEP_BUDGET` becomes `6 + 4 × parts`, capped, with a
  **separate stall counter** so a long legitimate question and a stuck one are no
  longer the same number.
- The observation gains a `PROGRESS` line: `2 of 3 parts done; remaining: blank 3
  (on account)`. The model stops having to infer where it is from a screenshot.

## 4. PROVE — verification that can see a move

**A structural fingerprint alongside the digest.** The digest cannot see a
reordering, so add an ordered list of `(containerRef, childIndex, first 30 chars
of text)` for every container holding drag sources or targets. A drop that moves a
node changes the fingerprint even when text and form values are identical. This is
what makes `waitForEffect` and the repeat detector work for drags at all.

**Semantic drop verification.** After a drag, confirm the source is now a
descendant of the target (or that the target's text contains the item's label) —
not merely that *something* changed.

**Four separate states, never conflated:** action executed, answer entered, part
verified, question submitted. `review-notes.md` calls this out and it is the
difference between "I clicked" and "it counted".

**Catch oscillation.** Keep the last eight action signatures
(`verb:ref:text|to`). Two different values written to the same target twice, or
the same signature four times, stops the run and says which answer it kept
flip-flopping between. Today this is invisible and shows up as "used the step
budget".

**`waitForEffect` waits for stability, not first change.** It currently returns on
the first differing byte, so a re-render mid-flight is read as settled. Require
two consecutive identical reads, keeping the 4 s ceiling.

## Files to change

| File | What |
|---|---|
| `extension/content.js` | tree/group fields, extended `INTERACTIVE`, shadow roots, `drag` flags, `row`/`column`, blank numbering, `fieldContext` textarea fix, ref badges, drag executor, `press`, `scroll_to`, held cursor, structural fingerprint |
| `extension/background.js` | generalised `actOnRef`, part ledger, question identity, progress budget, oscillation detector, stability wait, terminal gate |
| `agent.py` | `ACTIONS` additions, `Action` fields (`to`, `key`, `mode`, `parts`), grouped/indented element rendering, `PROGRESS` and `NEW` in the observation, prompt sections for drag / multi-part / tables |
| `app.py` | accept and bound the new observation fields; keep the phase gate |
| `extension/sidepanel.js`, `.html` | hand-in switch, ref-badge toggle, per-part progress in the log |
| `extension/manifest.json` | version → `0.6.0` (Chrome silently keeps the old build otherwise) |
| `tests/fixtures/*.html` | new — the regression pages below |
| `tests/test_core.py` | extend the vocabulary and prompt assertions |
| `tests/test_interaction.py` | new — Playwright over the fixtures |
| `ARCHITECTURE.md`, `AGENTS.md`, `HANDOFF.md`, `CONTEXT_BROWSER_USE.md` | record the new vocabulary, the ledger, and that the hand-in rule changed |
| `CONTEXT_RECORDING_REVIEW.md` | new — the recording review, brought in from outside the repo |

The recording review currently lives only at
`C:\Users\falay\video-review-20260911\review-notes.md`, is referenced by no
document in the repo, and is the strongest evidence behind this plan. It comes in
at the root as `CONTEXT_RECORDING_REVIEW.md`, matching the existing
`CONTEXT_BROWSER_USE.md` naming, so the next session can find it without being
told it exists.

## Verification

Unit tests alone cannot prove any of this, because the failure mode this repo
keeps hitting is a change that looks right and does nothing. So the fixtures come
first and are driven in a real browser — `tests/test_browser.py` already runs
Playwright against local pages, so the harness exists.

`content.js` already exposes exactly the hook this needs and **nothing currently
uses it**:

    window.__assignmentLab = { observe, act, hideUI, moveTo, pressEffect, describe };

with the comment that it exists so the observer and cursor can be exercised on a
plain page without duplicating code in a test. Attach `content.js` to a fixture
page with Playwright's `add_script_tag` and call `__assignmentLab.act(...)`
directly. That makes the whole observe/act layer — including every drag strategy —
mechanically testable, and it is the reason the drag work can be verified without
loading the extension. `background.js` is the opposite case: it is a service worker
built on `chrome.*` APIs, there is no JS test runner in this repo, and nothing
tests it today, so the ledger and the terminal gate can only be proven by running
the extension for real.

**Fixture pages** (`tests/fixtures/`), each a single self-contained file:

1. `matching_html5.html` — three-pair matching using native HTML5 DnD, targets
   disabled until all three are placed, graded feedback on submit.
2. `matching_pointer.html` — the same question implemented with pointer events
   and a movement threshold, i.e. the jQuery-UI/SortableJS shape. Strategy 3 must
   fail here and strategy 4 must succeed, proving the fallback chain works.
3. `blanks_prose.html` — one sentence, three blanks, with a decoy input outside
   the question.
4. `table_blanks.html` — a 4×3 table with a blank per row, `<thead>` headers and
   a `colspan`, so header resolution is actually tested.
5. `multipart_tabs.html` — Part 1 and Part 2 tabs, a "Submit Answer" that advances
   within the question, and a "Submit Assignment" that ends it. **The regression
   test for Dylan's bug:** the agent must not touch the second until both parts
   verify.
6. `shadow_question.html` — the same blanks question inside an open shadow root.

**What each proves**

- Observation: on `table_blanks.html` every blank reports the correct `row` and
  `column`; on `blanks_prose.html` each blank reports `blank N of 3` and the decoy
  is in a different `group`; on `shadow_question.html` the fields are visible at
  all.
- Drag: `matching_html5.html` completes via strategy 3; `matching_pointer.html`
  via strategy 4; and a deliberately impossible drag returns `ok:false` naming
  every strategy tried, rather than a false success. **A false success here is the
  failure mode that matters most** — it is how a wrong answer gets graded.
- Ledger: `multipart_tabs.html` — a terminal click with part B outstanding is
  refused in code with part B named; after both verify, it is allowed. Assert the
  refusal happens with the model *asking* for it, so the gate and not the prompt
  is what stopped it.
- Oscillation: a scripted sequence writing two different values to one field
  twice stops with a message naming both values.
- Drag visibility: with the cursor on, the held-press class is present for the
  whole gesture. Dylan should be able to watch a drag happen.

**Then a real run,** because fixtures are not the running thing: one MathPapa
question, one Canvas or MyLab quiz question of each shape he has, with the debug
panel open. Bump the manifest version first and remove-and-reload the extension —
Chrome has silently served a stale build before and cost an hour.

`pytest -q` must stay green: 91 tests today, and the prompt-substring assertions
in `tests/test_core.py` will need extending rather than deleting.

## Cost and risk

Each step still costs one model call with an image, and this plan adds steps per
question (a drag is several). Expect a matching question to cost 5-10 calls. The
`model-eval` rig is the place to decide whether the chosen model can actually do
this before trusting it on graded work.

The real risk is not cost. It is a synthesised drag that lands an answer in the
wrong bucket and reports success — which is exactly what the recording shows
Claude in Chrome doing twice and recovering from. Hence: verify every drop
structurally, recover locally rather than restarting the question, and never mark
a part verified on the strength of the action having executed.

## Tasks

Provisional. Codex reviews this split in the same round as the plan and may move
anything whose ground does not hold.

The split is argued from **what can be proven mechanically**, which after the
checks above is a sharp line rather than a matter of taste. The observe/act layer
has a test hook (`window.__assignmentLab`) and Playwright with Chromium already
installed, so its done-when is a passing test. `background.js` is a service worker
with no JS test runner in the repo and no existing coverage, so its done-when is a
live extension run. That puts more work on Codex than on Claude, which is the
mechanism working rather than failing — the tasks with a mechanical done-when are
genuinely the larger half here.

- [x] **T1** · codex · files: `agent.py`, `tests/test_core.py`
  Why codex: self-contained
  Add `drag`, `press`, `scroll_to` and the optional `mode` field to the closed
  vocabulary with server-side validation (`to` required for `drag`, closed key
  list for `press`), fix the stale verb list in the `require == 'act'` re-prompt,
  render elements grouped and indented, add `NEW` and `PROGRESS`, and write the
  prompt sections for drag, tables and multi-part.
  Done when: `pytest -q` green, unknown verbs still refused, `drag` without `to`
  refused, and the existing prompt-substring assertions extended not deleted.

- [x] **T2** · codex · files: `tests/fixtures/matching_html5.html`, `tests/fixtures/matching_pointer.html`, `tests/fixtures/blanks_prose.html`, `tests/fixtures/table_blanks.html`, `tests/fixtures/multipart_tabs.html`, `tests/fixtures/shadow_question.html`
  Why codex: self-contained
  The six fixture pages. Each must imitate its courseware shape faithfully — in
  particular `matching_pointer.html` must ignore HTML5 drag events entirely and
  require a movement threshold, or it does not test the fallback chain at all.
  Done when: a Playwright script solves each page by hand, and the pointer one
  demonstrably cannot be solved with HTML5 drag events.

- [x] **T3** · codex · after: T1, T2 · files: `tests/test_interaction.py`
  Why codex: self-contained
  Playwright over the fixtures via `__assignmentLab`, written **before** the
  executor exists so it encodes the contract rather than the implementation:
  observation structure, each drag strategy, the false-success regression, and
  oscillation.
  Done when: it fails against today's `content.js` for the right reasons.

- [x] **T4** · codex · after: T3 · files: `extension/content.js`
  Why codex: self-contained
  Everything in the page: observation structure (`group`/`depth`, extended
  `INTERACTIVE`, open shadow roots, `drag` flags, structured `row`/`column` with
  real header resolution, blank numbering, the `fieldContext` textarea fix), the
  badge layer kept separate from the cursor layer, the four-strategy drag
  executor, `press`, `scroll_to`, the held-press cursor, and the structural
  fingerprint. The largest task in the plan; `one file, one owner` keeps it whole.
  Done when: `tests/test_interaction.py` passes without being edited.

- [x] **T5** · codex · after: T1 · files: `app.py`
  Why codex: self-contained
  Accept and bound the new observation fields without weakening the phase gate.
  Done when: oversized or malformed part lists are refused with a clear message.

- [x] **T6** · claude · after: T4 · files: `extension/background.js`
  Why claude: needs-browser
  Generalised `actOnRef`, the badge round trip in the right order, the part
  ledger, stable question identity, progress-aware budget, oscillation detector,
  stability wait, and the terminal gate that refuses a hand-in with parts
  outstanding.
  Done when: loaded in Chrome against `multipart_tabs.html`, the model asking to
  click Submit Assignment with part B outstanding is refused by the gate, and
  allowed once both parts verify.

- [x] **T7** · claude · after: T6 · files: `extension/sidepanel.js`, `extension/sidepanel.html`, `extension/manifest.json`
  Why claude: needs-browser
  Hand-in switch, ref-badge toggle, per-part progress in the log, version 0.6.0.
  Done when: Dylan can watch a drag happen and read "2 of 3 parts done".

- [ ] **T8** · claude · after: T7 · files: `ARCHITECTURE.md`, `AGENTS.md`, `HANDOFF.md`, `CONTEXT_BROWSER_USE.md`, `CONTEXT_RECORDING_REVIEW.md`
  Why claude: needs-judgement
  Record the new vocabulary, the ledger, and — prominently — that hand-in is now
  permitted under a code gate, since that reverses a rule `AGENTS.md` lists as
  learned the hard way. Bring the recording review into the repo as
  `CONTEXT_RECORDING_REVIEW.md`. The handoff entry carries the live-courseware
  result, so this task is also where the real run gets reported.
  Done when: one MathPapa, one Canvas or MyLab question of each shape has been run
  live with the debug panel open, and a stranger reading `AGENTS.md` would not
  re-add the blanket refusal.

## First step

This plan is written for the review loop it will go through, not applied
directly. On approval: copy it to `plans/question-coverage/PLAN.md`, then

    python planloop/planloop.py review question-coverage

and work the rounds until Codex and Claude both say ready. Nothing is built
before that, and the Tasks split above is part of what Codex is reviewing — it may
move any task whose ground does not hold.
