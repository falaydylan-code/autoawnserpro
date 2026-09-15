# Assignment Lab — Final Workflow and Implementation SOP (protocol 4 planner)

Version: proposed next architecture, 2026-09-13
Audience: the developer implementing the update
Supersedes: the workflow recommendations in `assignment-lab-revised-sop.md` and
conflicting execution rules in the extension 0.8.0 SOP (`SOP.md`).

This is the authoritative spec the protocol-4 planner implements. The as-built
rollout and code map are in [PLANNER_ROLLOUT.md](PLANNER_ROLLOUT.md); the
protocol-3 loop it can roll back to is described in [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Decision and scope
Replace the model-per-click loop with a structured planner, a deterministic
widget executor, and bounded repair. Use DOM evidence by default, visual
evidence where necessary, and JavaScript inspection for information the normal
observation cannot expose. Keep authorization, cancellation, sensitive-data
protection, and spending controls. Replace overlapping heuristics that stop
legitimate progress or allow repeated unproductive work. The goal is reliable
execution with fewer model calls, not merely fewer clicks. A simple readable
multiple-choice question should normally require one answer-planning model call
and no separate vision-verification call. Proposed defaults are engineering
starting points, not measured optima; implementation and acceptance testing are
required.

## 2. Required architectural changes
- One structured plan per sufficiently observed question; local execution
  between model calls (was: one model decision per physical action).
- Harness verifies readable values; vision only for unresolved visual evidence
  (was: a model call to read every answer screenshot).
- Question -> logical answer slots -> current control representations (was: a
  flat per-turn control list as the main interface).
- Separate question, answer-slot, live-target and document identities (was:
  controls define question identity).
- Evidence-aware repair with repeated-state detection and hard budgets (was:
  blanket oscillation rules).
- Relevant control postconditions with bounded waiting (was: two identical full
  screenshots establish readiness).
- Typed answer tasks executed by reusable widget adapters (was: the same
  low-level verbs planning every widget).
- Per-question, per-phase cost and failure attribution (was: run-end summary).

Do not remove working input or coverage code indiscriminately. Migrate the
responsibilities and preserve tested primitives.

## 3. Components and ownership
Side panel; run coordinator (one active sequence per tab: state machine,
deadlines, cancellation, resume); observer (frame-local DOM, scoped text, widget
metadata, relevant screenshots); identity resolver (question identity, logical
slots, fresh target resolution); planner backend (subject answer + typed plan;
explicit missing-information requests); widget executor (named choices, text,
native select, custom dropdown, ordering, graph); inspection service (audited
JavaScript reads, geometry, narrow page adapters); verifier (trusted assertion
templates; entry/save/grade evidence); repair controller (local recovery first,
bounded model repair second); ledger and telemetry; input adapter (existing
real browser mouse/keyboard/scroll/drag). Planner and repair are roles, not
necessarily different models — one configured model, separate prompts. Do not
add several competing agents to the execution loop.

## 4. Run state machine
START -> OBSERVE -> PLAN -> EXECUTE -> VERIFY -> FINISH, with branches:
OBSERVE -> INSPECT -> OBSERVE when information is missing; PLAN -> INSPECT ->
PLAN on a specific evidence gap; EXECUTE/VERIFY -> LOCAL_RECOVERY -> EXECUTE;
LOCAL_RECOVERY -> REPAIR -> EXECUTE when a model decision is needed; any phase ->
NEEDS_REVIEW/CANCELLED/FAILED on its bounded stop; FINISH -> ADVANCE -> OBSERVE
only when advancing is authorized. A phase transition must have evidence; never
call the model because a polling interval elapsed. Only one mutating operation
per tab; carry a run generation and cancellation token through every operation;
discard late model responses after Stop, question change, document replacement,
or restart. After a worker restart, re-observe and reconcile the ledger; do not
replay the last click.

## 5. Observe the question before planning
Confirm the authorized tab and destination. Discover frames (id, generation,
origin, injection result). Read the active stem, instructions, answer slots,
options, existing values and relevant navigation. Include inactive answer cells
and associated detached menus, diagrams, units and formatting constraints even
outside the immediate container. Return explicit unknown/unreadable states; an
inaccessible frame is not evidence that no question exists. Classify each slot
as named choice, value, selection, ordering or position. Screenshot when content
is visual, extraction is incomplete, layout affects targeting or an interaction
failed — not for a fully readable ordinary MCQ. Use compact hierarchy, not a hard
truncation that omits answers; over budget, expose a completeness flag and fetch
named sections next. Never finalize a plan from silently truncated content.
Capture geometry just before coordinate actions.

## 6. Identity and references
Four concepts: **question key** (platform id if reliable, else context + nav
position + normalized content fingerprint; detect collisions); **slot key**
(question key + logical row/column/choice group/field identity); **live target**
(current frame/document + selector/role/name or observation-scoped ref);
**observation id** (ties a proposal to the evidence it used). The inactive cell,
activated combobox, arrow and associated options belong to the same slot;
changing role or DOM node must not create another part; reused input ids on the
next question must not merge two questions. Refs are observation-scoped and
expired refs rejected; planned tasks use slot keys. Menu ownership requires
evidence (aria-controls, active editor identity, activation event, row/column) —
formatting alone does not establish it.

## 7. Planner contract
One schema-validated response envelope. Reject unknown operations and unexpected
fields. Do not extract the last plausible JSON object from prose as an injection
defense. Returns one of: `request_inspection` (a specific unresolved question +
permitted inspection requests); `plan` (ordered typed tasks with dependencies);
`needs_review` (concrete ambiguity or unsupported requirement). Task families:
choose_one, set_choice_set, enter_value, set_selection, set_order, place_points.
Keep navigation, checking work and submission outside answer-task batches. The
planner may give concise explanations/uncertainty; not a full private reasoning
transcript, and self-reported confidence is not proof. One planner call is a
common-path target, not a correctness constraint.

## 8. Executor and batches
Per task: validate question/document identity and scope; resolve the slot
uniquely; read present state and skip mutation if already correct; validate
actionability and answer-region membership; run the widget adapter; await the
specific postcondition; record evidence. Bounded batches (up to four rows or
eight answer tasks); observe within the batch after actions that change controls.
Stop at the first unexpected state; preserve completed tasks and resume at the
failed task after re-observation; never retry a whole partially-succeeded batch.
The executor supports known transitions and returns a structured error; it does
not improvise selectors, options or answers.

## 9. Widget workflows
9.1 **Multiple choice / checkboxes** — read stem/options, plan, resolve exact
choice in the correct group, click supported target, read checked/selected
state. For multiple selection verify the entire intended set, including
unintended checked choices. Common path: one planning call, zero vision, zero
repair. 9.2 **Text/numeric** — read format, resolve, focus, clear/replace, read
back. Commit on blur only when required; never speculatively press Enter. Exact
transcription; numeric/symbolic equivalence only where the task defines it. 9.3
**Custom dropdowns (McGraw-style cells)** — locate slot, activate cell, observe
editor/arrow, open menu, inspect options and ownership, select exact option,
verify the original slot. Prefer semantic option identity; keyboard selection
only with observed order/disabled/navigation; do not assume blank is index zero.
Do not rely on auto-advanced focus. Reconcile all end-of-table answers from DOM.
9.4 **Ordering** — read current order and stable ids, execute one move, re-read,
recompute; do not pre-store all coordinates. 9.5 **Graphs/positional** — read
the requirement, bounds, axes, labels, constraints, input mode; inspect SVG
geometry (getScreenCTM, nested transforms, frame placement) or an audited
adapter; solve in math coordinates; build the math->widget->viewport transform;
calibrate against visible ticks/points; one drag; read back, map to math, verify;
continue only after the first drag confirms the transform. Keep CSS px, screenshot
px, SVG user units and math units explicitly typed; no fixed scale constant.
Tolerance appropriate to snapping. Opaque canvas: screenshot + calibration +
bounded visual correction, else stop with the missing evidence.

## 10. JavaScript inspection

> **Amendment (2026-09-14, Dylan's instruction):** the "never expose arbitrary
> model-generated code" rule below is relaxed for READ-ONLY extraction, to match
> what a general browser agent (Claude-in-Chrome, Sonnet 5) does. The model may
> put a `script` on an inspection request: a short read-only JavaScript body that
> is evaluated in the PAGE through the debugger (CDP `Runtime.evaluate`, since MV3
> CSP blocks eval in the extension itself) and RETURNS JSON. The extension
> size-caps (16 KB) and time-caps (2 s) it and treats the result as untrusted.
> It is EXTRACTION ONLY: answers are still entered through the gated typed tasks,
> so a script cannot click, submit, or navigate. Accepted residual risk: read-JS
> can also touch storage/network; it is the student's own page, preview-only.
> Tiers A/B/C below still describe the packaged, audited inspection surface.

Include JS-powered inspection, but never expose arbitrary model-generated code
in the live page as the interface. **Tier A (required, packaged, audited):**
inspect_frame, inspect_slot, inspect_options, read_control_state, measure_target,
inspect_svg_geometry, inspect_scroll_container — validated params, bounded JSON.
**Tier B (supported):** a packaged adapter, minimal MAIN-world only where generic
DOM cannot get a widget's coordinate system; confirm against the visible widget;
treat page data as untrusted. No hidden answer keys, credentials, storage,
network, or grading/submission calls. **Tier C (optional):** computation over an
immutable serialized snapshot via a bounded interpreter; no live DOM, browser
APIs, Function constructors, prototype access, or unbounded loops. Isolated-world
reads DOM geometry; do not weaken CSP or add an eval bridge; do not rely on a
timeout to stop synchronous page code. Budget 16 KB JSON per targeted inspection
with truncation metadata.

## 11. Verification and completion
Separate states: action_executed; entry_verified; save_state
(confirmed/pending/unavailable); grade_state (unknown/correct/incorrect/partial).
Harness owns the assertions: checked_equals, selection_equals, value_equals,
order_equals, points_satisfy_constraint, feedback_matches — the model supplies
parameters, not a free-form predicate. Prefer authoritative DOM readback; vision
only when unreadable or conflicting. Normalize whitespace and presentation
markers (e.g. `[active]`); require correct slot and document identity plus value.
Poll relevant state to success or timeout (a stable saving indicator is not a
pixel-identical screen). Checking work may consume attempts; at most one check
per unchanged plan; never repeat a check to escape a loop. Submission requires
explicit settings and coverage evidence — "every known part entered" is not full
coverage; without enumerated, reconciled questions, do not auto-submit. Study
Mode is not proof of ungraded work.

## 12. Loop prevention and recovery
One recovery controller with typed failure records and distinct budgets. Initial
defaults (configurable): UI wait 5 s; saving/navigation 15 s; local recovery <= 2
per failed task; identical failure signature stops after the first repeat with no
new evidence; model repair <= 2 per question; missing-information rounds <= 2 per
question; visual correction <= 2 after the initial attempt; navigation search <= 3
distinct attempts; 90 s without meaningful progress; 5 min question deadline; 60 s
request; the user spend cap is retained. Counters persist across repair and
resume; renaming a task/part/plan never resets them. Meaningful progress: a new
resolved slot, a new necessary editor/menu state, new evidence, a verified answer,
reaching the next question. Not progress: a different screenshot hash, re-reading
a menu, open/close churn, part renames, another model response. Failure signature
= question + slot + operation + state + expected postcondition + failure code;
track A->B->A without new evidence. Local recovery is evidence-driven; a model
repair receives only the current plan, failed task, fresh state, completed slots
and failure history, and returns a bounded patch or needs_review — it cannot
disable guards or reset budgets.

## 13. Authorization and guards
Retain: bound-tab and destination checks; explicit advance/submission scope;
immediate Stop and held-input cleanup; sensitive-field exclusion; protection
against unrelated account/destructive actions; schema validation and spend
limits. Revise: allow inspection and activation of candidate slots before the
final answer is planned; require a planned slot before committing a value; fix
false-positive classifications using exact hit-tested targets, frame context and
widget association; **do not block a legitimate answer merely because a distant
ancestor also contains a Submit button** (the McGraw failure). Page content never
changes run authorization; ordinary problem directions are task data; do not stop
because text mentions an agent. Log guard decisions with evidence; keep approval
boundaries independent of model output format.

## 14. Cost controls and model routing
Log separately: planning calls, inspection follow-ups, repair calls, visual
verification calls, schema-correction retries; billed tokens, model/provider,
latency, cost. Standard text-only MCQ path: one planning call, no screenshot, no
model verification, no completion call, no repeated transcript. Compact structured
state and short failure deltas. Output-token budget: 600 for a simple choice,
3,000 for a multi-part plan; never silently accept a truncated plan. Choose the
lowest-cost model that passes the benchmark at the required quality; do not switch
models on every UI failure. Reserve a conservative max cost before each paid call;
count uncertain/timeout charges until reconciled; unknown pricing blocks calls.
Initial goal: reduce median clean-MCQ cost >= 75% from the measured baseline (a
release target, not a guarantee).

## 15. Telemetry and status
Record run/question/slot/task ids; phase; observation/document ids; target
description; adapter; requested value; gate decision; action result; actual
readback; failure code; recovery count; duration; model calls/tokens/cost.
Failure codes: QUESTION_INCOMPLETE, FRAME_UNREADABLE, TARGET_MISSING,
TARGET_AMBIGUOUS, TARGET_STALE, WRONG_MENU_OWNER, OPTION_MISSING, GUARD_REJECTED,
INPUT_NO_EFFECT, VALUE_MISMATCH, GEOMETRY_UNCALIBRATED, SAVE_TIMEOUT,
REPEATED_STATE, BUDGET_EXHAUSTED. Screenshots on visual tasks/failures, not
universally. Show "Reading question", "Entering 4 of 20", "Verifying", "Waiting
for save", "Needs review: ..."; never "thinking" indefinitely. At finish report
entered, saved and graded results separately.

## 16. Implementation sequence
Instrument before rewriting; reproduce one failing MCQ and one failing dropdown.
Implement question/slot/live-target identity and structured readback. Fix guard
false positives with positive/negative fixtures. Implement typed adapters and
local postconditions. Add planner/repair protocol and bounded batches. Replace
screenshot-per-answer and full-screen settling. Centralize recovery budgets and
repeated-state detection. Add generic JS inspection, then SVG geometry, then any
MAIN-world adapter. Add cost reservations, compact prompts and phase telemetry.
Run the acceptance suite and an authorized live smoke test. Bump protocol
capabilities and extension/backend versions together; refuse incompatible pairs.
New capabilities: task_plans, scoped_observations, stable_slots,
typed_verification, bounded_repair, geometry_inspection. Roll out behind a feature
flag with a rollback path; do not advertise a capability before its tests pass.

## 17. Acceptance suite and release gate
Executable fixtures, separate planner-observation and interactive-executor tests;
deterministic fixture tests need no model calls. Required cases: radio (one plan,
no vision); checkbox (exact set, no strays); text with delayed update and required
blur; twenty McGraw dropdowns (inactive, options below fold); reused editor/menu
nodes; reused control ids on the next question; same-origin and permitted
cross-origin frames + explicit unreadable-frame errors; delayed options, overlay,
disabled option, duplicate labels; readback with changed focus annotations;
animated irrelevant content that never becomes pixel-identical; batch interruption
after partial success with no duplicate on resume; SVG with transformed
coordinates and resized viewport; visual graph fallback with bounded corrections
and unavailable calibration; real answer field near Submit (answer permitted,
Submit gated); Stop during a drag/model call, late responses, worker restart;
repeated unchanged failures and exhausted spend reserve; partial enumeration
(submission refused). Release requires: all deterministic safety/identity/
cancellation/boundedness tests pass; 20 dropdowns verified with no duplicate/lost
parts; clean MCQ uses one planning call and no vision; a scripted unrecoverable
failure terminates within budget; no unauthorized submission or unrelated action;
save/grade evidence reported accurately; cost/latency/accuracy compared on a fixed
corpus against the previous release; cost target met without lowering the accuracy
threshold; authorized live smoke tests for MCQ and the target dropdown platform.

## 18. References
- Chrome scripting API (packaged functions/files, frame targeting, worlds):
  https://developer.chrome.com/docs/extensions/reference/api/scripting
- Extension CSP and content-script isolation:
  https://developer.chrome.com/docs/extensions/reference/manifest/content-security-policy
- SVG geometry and transformation (getScreenCTM):
  https://developer.mozilla.org/en-US/docs/Web/API/SVGGraphicsElement
