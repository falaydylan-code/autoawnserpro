# Contextual navigation — user-approved build, 2026-09-23

Dylan approved the seven-step proposal in this conversation and transferred Mira's
navigation scope to Codex. Implement in an isolated branch from 04a605c; no commit,
push or deployment is authorized by this build request.

## Tasks

- [ ] **T1** · codex · files: extension/planner_content.js, tests/fixtures/navigation_actions.html
  Why codex: sole-owner
  Preserve bounded contextual candidates; broaden clear labels; distinguish check,
  answer submission, confidence groups, advancement and final submission.
- [ ] **T2** · codex · after: T1 · files: planner.py, app.py, store.py, extension/planner_runtime.js, extension/background.js, extension/manifest.json
  Why codex: follows-on
  Strict metered navigation decisions, action permissions, fresh candidate validation,
  durable one-attempt submission and action-specific settled outcome handling.
- [ ] **T3** · codex · after: T2 · files: tests/test_navigation_contract.py, tests/test_planner_navigation.py, tests/test_planner_transitions.py, tests/test_planner_acceptance.py, tests/test_planner_executor.py, ARCHITECTURE.md, HANDOFF.md
  Why codex: follows-on
  Verify variants, negative cases, stale decisions, permission gates, resume and
  transitions; document actual results and remaining live verification.

Confidence policy: the model may select only an offered rating, using the saved
pre-submission answer reasoning. Entry verification alone is never confidence in
academic correctness. If reasoning is insufficient it must choose a lower justified
rating or request review. Navigation receives action-area context, never a fresh
whole-page screenshot of revealed answers.

Clear controls use deterministic rules. Ambiguous controls use at most two metered
navigation decisions per question (answer submission then continuation), validated
against current scoped candidates. Unknown cost, Stop, stale evidence, forbidden
controls and final-assignment gates remain enforced by the harness.
