# Cross-site discovery and recovery

Status: Dylan approved implementation and Codex takeover, then on September 20 explicitly instructed this session to continue and work with the other agents to ship changes. Base ba801df (0.10.37). Release is authorized after review/tests; b5 remains integrator. Revised second-reader verdict pending. Live Quizlet verification evidence remains a prerequisite for claiming its stateless cards supported.

Supersedes the ownership split in the earlier QUIZLET_DISCOVERY_PLAN.md proposal. Codex owns all implementation files below in this isolated branch; Claude 03 preserves its uncommitted work. Reuse its reviewed aria-live change; do not carry forward its unsafe aria-pressed classifier. Claude b5 reviews and remains sole integrator. No planloop invocation: Dylan requested implementation, not an automated review-loop run.

## Design

1. Preserve legitimate aria-live question content while retaining feedback/answer-key exclusion. Share navigation classification. Preserve accessibility labels and complete visible answer text separately from stable target identity.
2. Collect bounded question-local candidate groups from explicit groups and nearest repeated sibling/list structures. Never group all page toggles. Known native/ARIA controls keep their existing adapters. Unknown shape, ambiguous cardinality or missing selected-state readback is unresolved; it never becomes actionable solely on model assertion.
3. Offer stable candidate IDs, frame/document and visible evidence for structured inspection. A model proposal references only offered IDs and a closed packaged adapter; trusted content validation rechecks members, state attributes, grouping and semantics before registering an executable slot. No arbitrary selectors/actions or answer guessing. Initial and promoted representations retain the same question/slot identity.
4. Quizlet tabindex-only cards require actual observed post-action state evidence before a new verification adapter can be enabled. Read-only live capture is the first prerequisite. If the available live evidence cannot establish a safe contract, implement candidate visibility and explicit unsupported-verification handling, and report live verification as unfinished; do not claim full Quizlet support from a synthetic fixture.
5. Separate extraction integrity from coverage/readiness. Recoverable gaps permit bounded read-only inspection; execution still requires complete data and resolved typed controls. Preserve evidence across inspections, scoped to question/document/frame with explicit overflow failure. Preserve completed tasks and durable budgets. Unknown controls cannot be described as locked or finished; proven disabled locations can be reported separately.
6. One strict JSON-format correction request, metered and bounded across resume. No parsing salvage or execution from rejected raw output. Stale identity, stop, deadline and uncertain cost still abort. Retain current thinking/truncation retry policy separately.

## Tasks

- [ ] **T1** · codex · files: `extension/planner_content.js`, `tests/test_planner_discovery.py`, `tests/fixtures/planner_discovery.html`, `tests/fixtures/planner_result_cards.html`
  Why codex: sole-owner
  Preserve text, shared navigation classification, structural candidates/labels, trusted classification/promotion and stable identities. Done when actual observed markup fixtures and negative/multiple-group cases pass with no wrong clicks.
- [ ] **T2** · codex · after: T1 · files: `extension/planner_runtime.js`, `planner.py`, `app.py`, `store.py`, `extension/background.js`, `extension/manifest.json`, `tests/test_planner_discovery_contract.py`, `tests/test_planner_discovery_runtime.py`, `tests/test_planner_result_cards.py`, `tests/test_planner_sheet_entry.py`, `tests/test_planner_acceptance.py`, `tests/test_planner_executor.py`
  Why codex: follows-on
  Wire discovery/promotion, context retention, readiness and truthful completion; strict bounded format correction; capability/version coordination. Also owns `tests/test_inspection_mapping.py` to assert the new per-frame evidence envelope while preserving wrong-frame binding rejection. Done when contract and real-extension tests prove initial/repair/reveal/resume paths, budgets, stale-response guards and no false success.
- [ ] **T3** · codex · after: T2 · files: `ARCHITECTURE.md`, `HANDOFF.md`, `plans/cross-site-discovery/PLAN.md`
  Why codex: follows-on
  Focused tests then full suite, record exact live-evidence boundary, obtain review of finished diff. No new source edits by reviewer. Browser-test failure rerun alone. Backend-first coordinated release remains integrator's task under Dylan's existing shipping authorization.

No two tasks assign the same file. No changes to parked cross-page reading, unrelated slow input or existing nested-scroll behavior. Generic support does not imply every possible website is supported.
