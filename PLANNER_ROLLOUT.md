> **0.10.0 update (2026-09-15):** The structured planner is now the only extension workflow, by user request. There is no workflow toggle or legacy rollback in the installed extension. Model-authored JavaScript inspection remains on-demand for missing information. Earlier preview/rollback instructions below are historical. Live platform validation remains a separate gate.

﻿# Structured planner rollout (0.9.0 preview)

## What changed

The opt-in planner observes one question, requests a strict typed plan, then
executes and reads back its answer slots without a model decision per click.
A readable choice question takes one planning request; it sends no screenshot
and makes no model verification request. This is covered by a real loaded-
extension test with a scripted provider, not an inference from the prompt.

The original 0.8 loop remains available with **Structured planner** switched off.
The existing logo, sidebar tools, ETH, Stop, model/backend setup, spend control,
logs and optional legacy screenshot checking are retained.

## Enable or roll back

1. Reload the unpacked extension from `extension/` in Chrome Extensions.
2. Open Settings and enable **Structured planner (preview)**.
3. Arm ETH and start on the assignment tab. The run stays attached to this tab.
4. To roll back, Stop and switch Structured planner off. Never downgrade in the
   middle of a partially executed batch.

Planner startup explicitly requests `/api/capabilities?protocol=4`. The default
capabilities response remains protocol 3 for previously loaded 0.8 extensions;
`supported_protocols` advertises both. Server and extension version are 0.9.0.
A missing protocol-4 backend stops before the first paid request.

## Code map

- `planner.py`: strict plan, repair and visual-measurement contracts; no prose
  extraction or private-reasoning request. Verification must match desired data.
- `extension/planner_content.js`: bounded packaged inspection in the isolated
  world; frame/document IDs, answer slots, detached-menu ownership, readback,
  hit testing, SVG transforms, visible saving/grading state. No eval/MAIN bridge.
- `extension/planner_runtime.js`: coordinator, eight-task batch boundaries,
  typed adapters, fresh target resolution, native browser input, local assertions,
  recovery signatures and persistent progress.
- `extension/background.js`: feature switch, original-tab input, request abort,
  protocol negotiation and worker/sidepanel integration.
- `store.py`: transactional cost reservations, immutable call identities,
  per-question request limits and accounting reconciliation.
- `agent.py`: reserved one-shot planner transport. Uncertain provider outcomes
  retain their reservation. No hidden network or schema retries.
- `app.py`: authenticated `/api/agent/plan`, `/repair`, `/visual`, and
  `/api/agent/runs/{run_id}` usage reconciliation.

## Evidence and safety

Each task names a logical slot, not a saved pixel or future menu ref. Custom
menus need an evidenced owner. Every coordinate action measures and hit-tests
its current target. Password/payment/identity inputs are excluded. Buttons for
submission, navigation and checking work never enter ordinary answer batches.

Checkbox verification compares the entire set. Text verification preserves
exact entered text. Selects verify the owning field, not a highlighted menu.
Ordering recomputes after each move. SVG coordinates use screen transformation
matrices; unsupported frame transforms stop rather than guess.

Opaque graphs use a separately schema-validated visual measurement: visible
axis ticks and actual point positions, never the desired answer. The harness
fits the axes, validates tick consistency, checks a crop hash of the relevant
graph, performs a drag, and obtains fresh visual readback. There are at most two
visual corrections per graph task. This is not a claim that vision is infallible.

Saving and grading are separate from successful entry. A delayed save is checked
again before completion. Locked feedback retires entry work without marking an
incorrect attempt correct. Check work is separately opt-in and occurs once per
unchanged plan. Submission requires the explicit switch plus verified coverage
of every index in the page's observed question total. Without enumeration, the
user must submit manually. Ambiguous/missing Next controls stop clearly.

Only the coordinator mutates a tab, sequentially. Stop aborts the pending request
and releases input. Document replacement invalidates pending actions. A resumed
worker re-observes/reconciles completed tasks instead of replaying clicks.
A saved uncertain API call must be reconciled before another paid request.

## Limits and accounting

Defaults: UI wait 5 s, save/navigation 15 s, 90 s without meaningful question
progress, 5 min question deadline, 60 s provider request. Two local recoveries,
two repair requests and two missing-information follow-ups per question. A
repeated identical failure terminates earlier. Budgets survive resume and task
renaming. Healthy runs have no question-count ceiling.

A live-registry token-price reservation is made before each paid call. Text
uses a conservative UTF-8 input bound; vision reserves the model context bound.
Actual OpenRouter cost settles the charge. Missing cost is never assumed zero.
The server run cap cannot be increased by changing a repeated client's payload.
The existing per-owner allowance is also enforced. Unknown pricing blocks calls.

Model calls, tokens/cost, IDs, phase, adapter, requested and actual values, and
outcomes are recorded separately. Local browser events are retained up to 1000
entries per saved run; per-question plans/completion and server calls persist.
No telemetry is sent to a third party. No new dependencies or build step.

## Validation and release gates

Run `python -m pytest -q`. New tests live in `tests/test_planner_contract.py` and
`tests/test_planner_executor.py`. They execute the extension in Chromium with a
scripted provider, including 20 dropdowns, reused detached menus, delayed options,
offscreen controls, exact checkbox sets, delayed-save rejection, overlays,
background tabs, frames, nested SVG transforms, opaque visual fallback,
partial/full submission coverage, cancellation and resume.

**Do not promote the feature to default-on based on fixture success alone.**
Remaining production gates: authorized live McGraw Hill dropdown/choice runs,
fixed-corpus entry and academic-accuracy comparison with 0.8, and measured median
cost reduction at the same accuracy threshold. A quoted $0.04/question is not
an independently measured baseline. Any provider smoke results must be recorded
separately from deterministic tests. `planner_release: preview` is intentional.

## Browser references checked

- https://developer.chrome.com/docs/extensions/reference/api/scripting
- https://developer.chrome.com/docs/extensions/reference/manifest/content-security-policy
- https://developer.mozilla.org/en-US/docs/Web/API/SVGGraphicsElement/getScreenCTM

The inspection functions are packaged and parameterized; no CSP weakening,
network access, private state scanning, or arbitrary live-page JavaScript bridge.
