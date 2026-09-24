# Handoff log

## 2026-09-24 - claude (kimchi, integrator) - 0.10.46 merged and deployed: multi-part reach + contextual navigation

**Did:** Fast-forwarded codex/optional-numbering 04a605c -> 1f26700 on Dylan's ship go. The release is three commits of code: ff3e060 (kimchi, multi-part: ownership by evidence + reaching parts the wording names without role=tab), 82b5739 (codex, contextual navigation: label + local context, answer_submit separated from check and from final hand-in, bounded metered decision for unknown controls, durable pending-submission record), and ad718f8 (kimchi, the regression the merge surfaced: a control owned by an answer is not a workflow control). Deployed backend-first from a refreshed deploy-source -- app.py, planner.py and store.py differed (planner.py carries the new navigation contract, store.py the navigation phase), frontend identical, local capabilities 0.10.46. `railway up` complete; live `/api/capabilities?protocol=4` reported 0.10.46 on the FIRST poll with the new `contextual_navigation` feature listed, `/api/health` ok. Dylan reloads the extension himself.

**Verified:** Full suite on the shipped tree: 502 passed, 1 `TargetClosedError` browser crash that passed alone in 3.9 s (the known flake). Codex's own two files 30 passed; the regression it left running 81 passed; navigation file 16 passed after the new opener test. The opener regression was proven both ways: twenty `unknown` candidates on the unfixed content script, zero on the fixed one. Live capability handshake verified after deploy.

**Left undone:** EVERY live verification. Neither half has run against a real page: the multi-part fixtures were built from Dylan's 9:32 PM Ch.3 log and the navigation work from the 9:41 PM SmartBook log, never from a live DOM read (the Connect activity URL needs the LTI handshake). First real tests: Ch.3 Q1 (multi-part) and a SmartBook confidence question (navigation). Formative bundle still held -- the standing packaging blocker. Nothing pushed to origin.

**Watch out:** New base for every branch: 1f26700. The navigation scan is far wider than the old label-only filter: anything reachable by `button,a,[role=button],input[type=submit],input[type=button]` that `navigationInfo` does not reject becomes a candidate with `kind:'unknown'`, and an unknown candidate is what spends a metered navigation call. The answer-owned exclusion is the only thing keeping a sheet of dropdown openers from doing that -- do not narrow it back to equality. `navigationInfo` calls `renderedText` over up to three ancestors per candidate on every observe. A confidence rating now submits the current answer when Check work is on; if Dylan wants that off, the switch is `check_work`.

## 2026-09-23 - claude (kimchi, integrator) - 0.10.46 integration: a control that belongs to an answer is not a workflow control

**Did:** Picked up Codex's contextual-navigation work where it stopped (it left everything uncommitted and its regression still running), committed it on its own branch as 82b5739, and merged it with the part-reach fix. Two conflicts, both one line, both resolved by keeping BOTH sides: the choice-candidate pool now excludes asserted part switchers (mine) and confidence-group members (Codex's); the observation carries `candidate_parts` beside the new `navigation`/`navigation_complete` fields. `planner_runtime.js` regions were disjoint and auto-merged; both branches had independently bumped to 0.10.46, so the version lines merged clean and one release covers both. Then fixed the one real regression the merged full suite found: widening the navigation scan to unlabelled buttons (`input[type=button]`, and any control `navigationInfo` does not reject) turned every dropdown-opening arrow INSIDE a response cell into an `unknown` navigation candidate -- twenty on one sheet. That is wrong on its own, and the extra payload pushed the observation past its 100 KB reply limit part-way through a run (`planner_content.js` :619), ending it `QUESTION_INCOMPLETE: Observation exceeds 100 KB` at "Entering 9 of 20". The navigation scan now excludes anything owned by an answer -- inside `answerCells`, inside a listbox/option, or contained by a slot's or choice's element. Containment, not equality: the opener sits inside the cell, it is not the cell.

**Full suite on the fixed merge (final):** 502 passed, 1 failed -- `test_planner_choice_mode::test_an_instruction_on_screen_counts_even_when_aria_hidden_and_chrome_is_not_offered`, a `TargetClosedError` browser crash at launch, which passed alone in 3.9 s. That is the known crash-alone flake, not a real failure.

**Verified:** Codex's own work, which it had not been able to confirm: `test_navigation_contract.py` + `test_planner_navigation.py` 30 passed; the transitions/acceptance/executor regression it left running, 81 passed. The merged tree's first full suite: 500 passed, 2 failed -- `test_inspection_mapping::test_twenty_initially_inactive_cells_in_frame` (the 100 KB regression above, traced to the exact event and fixed) and `test_finalize::test_a_long_assignment...` (passes alone, 80 s; the known crash-alone flake). New regression test `test_a_cell_opener_is_never_a_workflow_control` in `test_planner_navigation.py`: proven to fail on the unfixed content script (twenty `unknown` candidates) and pass on the fixed one; navigation file now 16 passed. Full suite on the fixed merge: see the following entry.

**Left undone:** No live verification of either half. Codex's confidence-rating submission path and my tab-ownership fix were both built against fixtures derived from Dylan's logs, never against a real page. Not deployed; not pushed.

**Watch out:** The navigation scan is now much wider than the old label-only filter, so anything that can be reached by `button,a,[role=button],input[type=submit],input[type=button]` and is not rejected becomes a candidate with `kind:'unknown'` -- and an unknown candidate is what triggers a metered model call. The answer-owned exclusion is what keeps a sheet of openers from doing that; do not narrow it back to equality. `navigationInfo` walks up to three ancestors calling `renderedText` for every candidate, so a page with many controls pays that on every observe.

## 2026-09-23 - claude (kimchi, integrator) - a part is owned by the tab that is lit, and parts the wording names can be reached without role=tab (0.10.46)

**Did:** McGraw Connect Ch.3 Q1 (9:32 PM, 0.10.45): tab 1 read fully, tab 2 clicked, `TARGET_MISSING ... (no declared tab panel; no tab widget inferred)` after 5 s, no model call. Cause: the page half-declares its tabs -- `<li role=tab id=tab-N>` with no `aria-controls`, plus a `role=tabpanel` no tab claims. `panels.length` was 1 so the widget inference block was skipped entirely (`planner_content.js` :356), `partOf` stayed empty so every slot fell to `part_scope: fallback` (:394), and `showPart` (:891) only accepted `panel` or `inferred`. This is a 0.10.43 regression, not a 0.10.45 one: before 0.10.43 `showPart` settled on "selected + two agreeing slot lists" with no scope rule, so this page worked. Built on Dylan's go, two layers. (1) Ownership by evidence: `showPart` accepts the part when its tab is selected, its frame holds answer controls, and no OTHER part claims them; the scope labels keep their separate job in the identity key. The part box is now found whenever parts exist -- first by walking up from the tab strip to a box holding a real answer control, then, when the strip and the content are siblings under the root, by the widest box holding every answer control that still leaves the strip out -- and serves as `identity.part_content` even when it is not the identity widget, so the settle check that stops one tab's answers being written under another is no longer blind on this shape. (2) Reaching parts the page does not declare with `role=tab`: the content script reports `candidate_parts`, conservative groups of 2-12 plain controls whose labels are part names (a number, "Part 2", "Required 3"), never forbidden/navigation labels, and only when the group shows which member is current. Nothing there is a part until the harness asserts it, and it asserts only when the model's `parts_declared` exceeds the parts found (`planner_runtime.js` :797, previously an immediate PART_UNREACHABLE throw): `reachDeclaredParts` asks the page via the new `assert_parts` inspect operation, keeps the group only if the page then reports it as this question's parts, reveals them and re-plans through the existing round loop, and otherwise throws the same fault. The model contributes a COUNT and nothing else -- it never names or clicks a control. Three bugs found while building and fixed: an asserted switcher is no longer also offered as a candidate choice group; reading a question as multi-part changes its own fingerprint, so the question is re-pinned and its ledger record moved rather than abandoned as stale; and a tab strip that marks no tab as current now stops in `revealParts` with a plain message instead of reaching "Logical answer slot is not unique" after entering one answer. Versions 0.10.46 (manifest, app.py).

**Verified:** New `tests/test_planner_part_reach.py` (8) on new fixtures `half_declared_tabs.html` (the Ch.3 shape) and `numbered_parts.html`: the half-declared widget is owned and both halves filled through a 300 ms rebuild; an unmarked tab strip stops with nothing entered; numbered buttons become parts only because the wording names two, and the switcher is never clicked when it names one; a switcher with no current-marker, a Previous/Next row, and a switcher that changes nothing are each refused. Full suite on this branch: **472 passed** in 24:23, clean. One EXISTING expectation moved on purpose: `test_planner_worksheet_tabs.py` `shorttext=1` now stops `TARGET_STALE (stem)` instead of `TARGET_MISSING` -- ownership no longer depends on the scope label, so the tab is accepted and the honest failure is that with no anchor the switch moves the question's own fingerprint. Nothing is entered either way, one tab click either way.

**Left undone:** Live Ch.3 Q1 and Q12 reruns (Dylan). Never tested against a real page -- the Connect URL needs the LTI handshake, so both fixtures were built from the logs, not from a live DOM read. Not merged, not deployed, not pushed. Continuation/navigation is Codex's branch (`codex/contextual-navigation`), also at 0.10.46; the two collide only on `planner_content.js` base lines 75 and 445 (one clause each) and on the version lines -- `planner_runtime.js` regions are disjoint.

**Watch out:** `assert_parts` is the only door through which a non-tab control becomes a part; widen the label rule or drop the current-marker requirement and the harness starts clicking unknown buttons on live coursework. The search runs at most once per question (`current.partSearch`) and never at all when `parts_declared` is 1, so a simple question pays nothing. A numbered row is still offered as an unresolved candidate choice group before it is asserted, which keeps a single-part question from finishing cleanly -- that is the pre-existing "unresolved leftovers" item, asserted in the tests so it is visible when it is fixed.
## 2026-09-23 - codex - contextual navigation build

**Did:** Built the user-approved generic workflow-navigation fix on branch codex/contextual-navigation in C:/Users/falay/orca/workspaces/assignment-agent-question-coverage/codex-contextual-navigation. Added bounded contextual candidates and confidence-aware answer submission in extension/planner_content.js, strict metered navigation contracts and /api/agent/navigation in planner.py, app.py, and store.py, runtime candidate revalidation and action-specific transitions in extension/planner_runtime.js, the 0.10.46 capability/version bump, fixtures, tests, and architecture documentation. Added a durable pending-navigation record before an answer submission click so resume cannot repeat an uncertain click after a DOM redraw.

**Verified:** node --check passed for extension/planner_content.js and extension/planner_runtime.js. tests/test_navigation_contract.py plus tests/test_planner_navigation.py passed 30 tests. The duplicate-submission resume case passed alone after the durable guard. The earlier service-worker startup failure reran alone and passed. The transition/acceptance/executor regression command was still running when this handoff was written.

**Left undone:** Collect the running regression result; run any necessary final focused tests; update the shared vault state/log and export the session. No commit, merge, push, deployment, or live Quizlet/McGraw verification was done. Full suite was deferred because free memory was about 1.11 GB and the project requires at least 4 GB.

**Watch out:** A pending navigation outcome deliberately stops the resumed run rather than risking a duplicate answer submission. Unknown, ambiguous, overflow, unlabeled, or unsafe workflow controls still stop for review. The missing Quizlet question stem in the old DOM observation is a separate unresolved issue. Kimchi is the integrator; if shipping is later authorized, deploy backend before extension.

## 2026-09-21 - claude (kimchi, integrator) - 0.10.45 merged and deployed: tab anchor + harness-caused transitions

**Did:** Fast-forwarded codex/optional-numbering dfaadcd -> af38808 = claude/tab-anchor bcfef4f (kimchi: position marker optional, tab signature = visible text) + merge of claude/expected-transitions 4a12a42 (Mira: guard() pins lifted only inside settle() for Check/Next/Submit and the post-answer look, repin() on the same question, visual.js begin() clears `cancelled`). Integrator review of Mira's runtime diff: `identityMovers` exists (:48), `this.current.key` is the key same() uses, node --check clean on runtime/content/visual; only HANDOFF.md conflicted at merge (both entries kept). Deployed backend from deploy-source (only app.py differed: the version line; frontend identical; local capabilities 0.10.45); `railway up` complete; live `/api/capabilities?protocol=4` reported 0.10.45 on the first poll, `/api/health` ok. Dylan reloads the extension himself.

**Verified:** Full suite on af38808: 464 passed in 21:28, no flakes (two earlier full runs were killed by the machine for memory -- Dylan's own Chrome held 9.6 GB; the one F seen, test_greptile_pr4 double-check-off, passed alone in 8 s). Not verified: the installed extension (reload pending), live Q12 on 0.10.45, live Ch.1 Q1 with Check work on, the new panel-less tab path on any real page.

**Left undone:** Live Q12 rerun (the first real proof of both fixes). Live McGraw DOM never read this session (direct activity URL = blank page, LTI handshake) -- the box-search gate (`planner_content.js` :356-358) is the one 0.10.43 gate still unproven on the page. Mira's nav-confidence fix (8:17 PM "No unique next-question control found") is queued, no go. Formative bundle held (ship blocker for packaging). Nothing pushed to origin.

**Watch out:** New base for every branch: af38808. Do not run two Playwright suites at once on this machine; check free memory (>= 4 GB) before a full run. If the Copy log's `TARGET_MISSING` after a tab click now says "no box below the question root", that is the last gate and needs the live DOM.

## 2026-09-21 - claude (mira, site session) - a page change the harness caused on purpose is not a stale target

**Did:** Ch.1 Q1 (8:39 PM, 0.10.44): twelve answers entered and verified, Check work pressed "Check my work", and the first look 150 ms later ended the run `TARGET_STALE: Document was replaced.` -- that string is `guard()` (`planner_runtime.js` :74), which asserts the frame documents pinned at the start of the question (`:754`) before every look and every input; McGraw answers a Check by reloading the frame that holds the question, so the pin failed on the click's own result. Next reloads it too, and the same two pins (guard, and `same()` via `measure()` :174 before any later click) would have ended the run after Next. Built on Dylan's go, in the integrator's file with his override of the split: (1) `guard()` lifts the frame pins only while `this.transition` is set, and when a pin does fail it names the frame and how it moved (`stopped responding` / `holds a new document`) in `failure_data` -- the old bare message could not say which of two frames McGraw reloaded. (2) New `settle(purpose, before, done)`: the only clicks whose expected result IS a different page (Check, Next, Submit) and the first look after a finished answer wait it out with the pins lifted, polling every 150 ms up to `LIMITS.navigation`; the page counts as settled when `done` holds on two consecutive agreeing polls (key, document, slot count, feedback, page state); a frame caught between documents (`FRAME_UNREADABLE`) is neither settled nor fatal until the deadline. (3) After Check: the graded page is accepted only as the SAME question -- same key on a new document -> `repin()` (document, identity, frameDocuments) and carry on to Next, logged `Website feedback received {document_replaced:true}`; a different key -> `TARGET_STALE: Question identity changed after Check (<movers>)` and stop. Feedback in another frame still counts. (4) After Next: a different question counts once it is readable (has answer controls, or is locked/complete) -- a frame that has loaded its stem but not its inputs is not settled on; if a different page never becomes readable in 15 s the loop reads it as it is and says so; no change at all is still `INPUT_NO_EFFECT`, now saying whether the document moved. (5) The post-answer look (`:972`) runs pinless when `current.finished`: a page that replaced its own document after the verified answer with the same key is re-pinned and logged; a new key takes the existing "page advanced" branch. (6) `visual.js` `begin()` (my file): the second trip. `chrome.tabs.onUpdated` sets `cancelled` on any navigation, including a subframe reload, and `begin()` checked it before clearing it -- so the first gesture after a frame reload (Next after Check) was refused "Browser input cancelled." A new gesture now starts clean; a navigation DURING a gesture is still caught by every event's guard (gestureUrl / loading). Nothing changes for a document change the harness did not cause mid-entry: still fatal, now named. Fixtures `tests/fixtures/transitions.html` (shell: Check/Next buttons, question in an iframe; `?check=reload|redraw|top|stem|none`, `delay`, `slow`, `next=reload|swap|same|none`, `stray`) + `transitions_q.html`; `tests/test_planner_transitions.py` (10). No version bump (kimchi: 0.10.45 covers both).

**Verified:** New file 10 passed: Check reloads + Next reloads across three questions (answers kept, `loads` = q1, q1 graded, q2, q2 graded, q3, q3 graded; feedback events carry `document_replaced`); in-place redraw + swap unchanged (one document all run); shell-frame feedback counts; a 700 ms-late reload whose inputs render 800 ms after load is waited for, never settled on, no `INPUT_NO_EFFECT`/`FRAME_UNREADABLE`; a rewritten stem after Check stops `TARGET_STALE: Question identity changed after Check (stem)` with nothing entered into the new page; Check with no effect still `INPUT_NO_EFFECT`; Next that reloads the same question -> `INPUT_NO_EFFECT: Next replaced the page's document but no different question settled`; a frame that reloads itself as a value is typed -> `TARGET_STALE: Document was replaced (frame N ...)` with `failure_data.frame_id`/`reason`, Check never reached; a site that redraws its frame once after the verified answer is re-pinned and checked; `guard()` alone names the frame. Focused suites on this branch: worksheet_tabs (kimchi's `Document was replaced` expectation holds), parts, executor, result_cards = 85 passed; acceptance, visual_readback, choice_mode, sheet_entry, openers, nested_scroll, discovery_runtime = 62 passed. Full suite: started on this branch, killed by the system at ~35% for low machine memory (about 150 dots and ONE `F` right after a fixture-server `ConnectionResetError`, test name not captured) -- not rerun on my own (memory was still short); the 10 new tests were rerun alone on the final code after the last predicate change, 10 passed. The full suite must run green (and that `F` be identified) before merge. NOT verified live: McGraw Ch.1 Q1 with Check work on, and Next on McGraw (Dylan reloads 0.10.45 and reruns).

**Left undone:** The nav-confidence content-script rule (McGraw "Rate your confidence" High/Medium/Low = submit-answer; `planner_content.js` :21-23, :430-432) -- diagnosed, not started, no go. Whether McGraw's graded page keeps the question key (stem/structure unchanged by grading) is unproven from logs: if grading rewrites the stem, the next log will say `Question identity changed after Check (stem)` and the fix is the fingerprint item in the Formative bundle, not this. Merge + deploy: kimchi's (integrator).

**Watch out:** `this.transition` is engine state, not ledger state: a resumed run never starts inside a transition. Every finished question now waits two agreeing polls (>= 300 ms) before the Next search; a page whose status text ticks continuously never "agrees" and falls back to the last look after 15 s (same as the old single look, later). The after-Check page counts as settled only once it is readable again (answer controls back, or locked/complete) -- a site whose grading removes every input and leaves the page 'answering' waits the full 15 s then reports `INPUT_NO_EFFECT`; a site that re-creates the iframe element rather than reloading it gets a new frame id, which is part of the key, and reports `TARGET_STALE: Question identity changed after Check (frames [old] -> [new])`. `visual.js` no longer refuses the first gesture after a navigation: the engine's own guard (frame pins) and settle() are what protect against acting on a replaced page, so do not move a click outside them.
## 2026-09-21 - claude (kimchi, integrator) - the tab-widget anchor no longer needs a position marker; tab labels carrying progress no longer move the key (0.10.45)

**Did:** First live run on 0.10.44 (McGraw Q12, 8:14 PM): tab 1 read fine, tab 2 clicked, then `TARGET_MISSING: ... (no declared tab panel; no question position outside the tab widget)` after 5 s, no model call. Cause: the 0.10.43 inference gate (`planner_content.js` old :359-360) required a `[aria-current=step|page]` / `.question-number` element outside the widget before trusting it; that selector dates from 0.9.0 and only our fixture ever matched it -- the McGraw frame has none, so every slot stayed `part_scope: fallback` and `showPart` (`planner_runtime.js` :868) could never own the part. 0.10.43 never engaged on the page it was built for; it moved Q12 from `TARGET_STALE` to `TARGET_MISSING`. Built (Dylan's go, Mira's yes on the region): (1) the anchor is 40+ characters of question text outside the widget (the check that already ran second); a position element still joins the key when the page has one, it is just not required; (2) the tab signature reads the tab's value/innerText, aria-label last -- McGraw names its tabs "Transaction Number 2 not yet entered Record the entry ..." and the name flips once a value is in, which under 0.10.43 moved the key (proved on the old code: `KEY_SAME False` after one entry). The model-facing part label keeps the full name. Fixture `worksheet_tabs.html` gains `?status=1` (McGraw's aria-labels, flipped on entry); `?noposition` / `?inpos` now document the live frame. Versions 0.10.45 (manifest, app.py).

**Verified:** On the OLD content script first: `noposition=1` refused with the live message; `status=1` moved the key after one entry. On the fix: `test_planner_worksheet_tabs.py` 13/13 (`noposition`/`inpos` infer, switch tabs, full run fills all three tabs; `status=1&noposition=1` full run finishes while every entry flips a label; `shorttext=1` still refuses with `TARGET_MISSING` and one honest tab click). Focused suites (tabs, parts, sheet_entry, openers, executor, acceptance, choice_mode, visual_readback, nested_scroll, discovery_contract, contract, tables, interactions, sidepanel_ui): 198 passed. Full suite: see the merge commit. NOT verified live: Q12 on 0.10.45 -- the direct URL gives a blank page (LTI handshake), so the live DOM was not read; the remaining unproven gate is the box search (`planner_content.js` :356-358, "no box below the question root holds both the tabs and an answer control"), which names itself in the log if it bites.

**Left undone:** Live Q12 rerun. Deploy -- Dylan wants this shipped together with Mira's work (claude/expected-transitions: `planner_runtime.js` guard/settle for Check-triggered frame reloads, 8:39 PM run; and the queued nav-confidence content-script fix, 8:17 PM run). Formative bundle still held (ship blocker). Not pushed.

**Watch out:** New base for every branch stays dfaadcd until this merges. The tab signature is VISIBLE text: a site that writes status into the visible tab label (a check mark appended to "2") would still move the key -- the stale message names `tabs` if so. `?inpos` now infers with the position dropped from the key (it sits inside the widget); the outside stem and the tab signature are the anchor there.

## 2026-09-21 - claude (integrator) - 0.10.43 + Codex side panel merged and deployed as 0.10.44

**Did:** Fast-forwarded codex/optional-numbering to claude/question-formats 165a716 (0.10.43, worksheet-tab identity), then merged codex/sidepanel-home-redesign 366f589 (Codex's compact side panel) as 0b335b1; conflicts were only the two version lines (kept 0.10.44) and the two HANDOFF entries (both kept). Integrator review of the UI diff: JS changes are wording, a `latestSteps` variable for the Copy log header, and hiding the progress card when idle; every `$('id')` the script uses exists in the new HTML; `node --check` clean. Deployed backend-first from a refreshed deploy-source (only app.py differed; frontend identical; local capabilities 0.10.44); live `/api/capabilities?protocol=4` reported 0.10.44 on the first poll, `/api/health` ok.

**Verified:** Merged tree: test_sidepanel_ui + copy-log + discovery-contract + worksheet_tabs (11) + parts (9) = 23 passed. 0.10.43 alone: full suite 450 passed + one TargetClosedError crash that passed alone. Not verified: the installed extension (Dylan reloads it), the live Q12 rerun, the new panel on a real run.

**Left undone:** Live Q12 rerun on 0.10.44. Formative bundle (held). Codex's own Watch out stands: internal diagnostics still count steps although Home no longer shows them.

**Watch out:** New base for every branch: 0b335b1. If the Copy log header of the next run says 0.10.43 or older, the extension was not reloaded.

## 2026-09-21 - codex - compact white-and-purple side-panel home (0.10.44 candidate)

**Did:** Built Dylan's requested side-panel redesign on isolated branch `codex/sidepanel-home-redesign` from clean integration `7df72e1`. Home now has Enable/Enabled browser access, model selection, Auto Continue and cost visibility; metrics show only questions and optional cost. Removed the idle `No parts planned` display and visible step tile. Moved Copy log and model-thinking visibility to Settings, tightened spacing, and strengthened the existing white-and-purple brand treatment. Updated user-facing README language and kept backend/manifest versions matched at candidate 0.10.44.
**Verified:** `node --check extension/sidepanel.js`; sidepanel ID integrity script; `git diff --check`; `python -m pytest tests/test_sidepanel_ui.py tests/test_planner_executor.py::test_copy_log_contains_model_reply_and_validation_details tests/test_planner_discovery_contract.py::test_extension_requires_matching_discovery_backend -q` (3 passed). Headless Chromium screenshots at 390x900 for Home and Settings show no horizontal overflow (`scrollWidth=390`), and visual inspection confirms the requested hierarchy and Copy log placement.
**Left undone:** No merge, push, backend deployment, extension reload or live assignment run. The active worksheet identity change owns 0.10.43 and is being implemented separately; rebase or cherry-pick this 0.10.44 candidate onto that finished integration before release.
**Watch out:** Internal diagnostic copies still include step count even though Home no longer displays it. The visible `eth` DOM ID and stored `armed` key remain for compatibility; only the user-facing name changed to Enable. The Figma connector was not exposed to this running session, so the redesign was implemented and browser-rendered directly.

## 2026-09-21 - claude - a tab strip that declares no panels no longer forks the question (0.10.43)

**Did:** McGraw Q12 (E4-15 Algo, 12:38 PM, 0.10.42): the journal-entry worksheet's inner tabs 1 2 3 4 are bare `<input type=button role=tab>` with no `aria-controls`, no id, no `tabpanel`. `revealParts` clicked tab 2 (`show_part`), `showPart` asserted `same()` on its first 120 ms poll (`planner_runtime.js` old :851) and the run ended `TARGET_STALE` before any model call. Cause, vetted by Codex (read-only, agree 0.9) and 04 (checked all seven points against HEAD): tab content leaves the identity only through `panels` (`planner_content.js` :335-343, `aria-controls`/`[role=tabpanel]`); with nothing declared the transaction text and the rebuilt cells were in the fingerprint, and the key flipped. A second, independent trigger sat at runtime :120 (`used = active.length ? active : frames`): an instant with zero slots switched the key to ALL frames. Built after a three-round plan review (Codex changes_needed x2 -> agree; 04 agree, and it granted `planner_content.js` for this fix): (1) content script infers the tab WIDGET when no panel is declared -- the single tab group's nearest ancestor holding a real answer control (never a tab or a button) below the question root -- only when an anchor survives outside it: a question position read outside the widget AND >= 40 characters of question text; otherwise no inference and `identity.no_inference` says why. The widget's contents leave `identityStem` and `structure` as declared panels do, the tab count + labels join the key (`tabs:3:1/2/3`), model-facing text/tables/slots are untouched; declared panels are never widened. Slots carry `part_scope: panel|inferred|fallback`; every observation carries `identity` (stem/structure hashes, position, tabs, panels, inferred_widget, part_content, busy). (2) runtime: aggregate key over frames with slots OR a tab strip; `same()` names the mover ("Document was replaced" vs "Question identity changed (stem|structure|position|tabs|frames)") with old/new snapshots in `failure_data`; `showPart` asserts identity on the pre-click view, checks only the document while polling, settles when the requested part is selected AND shows panel/inferred slots of its own in its own frame (or that frame is locked/complete) AND two consecutive polls agree on slots + key + `part_content` (busy resets), then asserts identity once; the deadline `TARGET_MISSING` says what was missing. (3) versions 0.10.43 (manifest, app.py). Fixture `worksheet_tabs.html` (no `data-question-id`; the fallback identity path had no bare-tab fixture) with `?delay/wrapper/noposition/shorttext/inpos/twostrips/docswap/latetext`, `worksheet_parent.html` (worksheet in an iframe beside an always-present field); `tests/test_planner_worksheet_tabs.py` (11).

**Verified:** New file 11 passed; parts/sheet_entry/openers/executor/acceptance/choice_mode/visual_readback/nested_scroll/discovery/contract/tables 187 passed; full suite 450 passed + one TargetClosedError browser crash (`test_finalize.py` long-assignment) that passed alone. Fixture proves: identity and per-part slot keys survive the switch and the return; a 300 ms empty gap (longer than two polls) is waited out and no tab is recorded empty (old code settled on two empty polls); a field in another frame does not make an empty tab look settled; declared panels without a platform id are unchanged (`inferred_widget:false`, scope `panel`); same URL with a changed position, stem or tab count gives a different key; a navigating tab click ends "Document was replaced"; no anchor -> no inference, one tab click, no input, no part recorded, `TARGET_MISSING` names the reason; two tab groups -> no inference; a late description behind `aria-busy` reaches the model. NOT verified live: Q12 itself. Not proven from the old log: whether McGraw's inner tabs really lack `aria-controls` -- the fix covers both readings, and the next stale log will name the ingredient.

**Left undone:** Live rerun of Q12 (Dylan). Merge + deploy (waiting for Dylan's go; backend first, then reload). Formative bundle still held; Codex's note recorded: the React-id item must cover `key()` :29 and `slotKey()` :364 too, a structure-only cleanup keeps the key but old slot keys still fail. Pre-existing, seen while building: a pair of `<button>`s inside a worksheet ("Record entry" / "clear") is discovered as a candidate choice group and, being fallback-scoped, gets one slot key per part in the merged plan; McGraw-style `<input type=button>` pairs are not (the fixture uses those).

**Watch out:** Settling is a bounded heuristic and the log says so: a part whose text is swapped later with no busy marker and no control change is not caught. A tab with no answer controls of its own (an instructions-only tab) now ends `TARGET_MISSING` after 5 s instead of being recorded empty -- deliberate (Codex R2), say so if a site does that. `AssignmentVisual.attach` is a no-op when already attached and does not clear `cancelled`; a test that navigates and runs twice in one function must `detach()` first (the new `run()` helper does).

## 2026-09-21 - claude (integrator) - 0.10.41 and 0.10.42 merged and deployed

**Did:** Merged claude/question-formats twice into codex/optional-numbering: a8c1b30 (0.10.41, screen readback for markerless choice groups) and 5ab6e29 (0.10.42, multi-part retry keeps every tab). Both deployed backend-first from a refreshed deploy-source (diff clean, local capabilities check), live `/api/capabilities?protocol=4` reports 0.10.42, health ok. Dylan reloads the extension himself.

**Verified:** Full suites on the branches: 438 passed + one TargetClosedError crash that passes alone (0.10.41); 440 passed clean (0.10.42). Live: Khan single-choice completed and verified on 0.10.40 (5:02 PM, answer E) before ending "incomplete" over the Previous/Next chrome group; Quizlet single-choice completed live per Dylan; M3-9 completed on 0.10.37.

**Left undone:** Live Quizlet multi-select on 0.10.41+ (first real screen-readback run); live M4-14 on 0.10.42. Formative bundle (role before `e.type`; candidates must not be cut out of the stem; fingerprint too sensitive to post-answer redraw -> false TARGET_STALE; trailing-empty slot keys; one-label aliases; duplicated option text; chrome labels). Khan/Formative "unresolved leftovers" ending. MathPapa graph candidates by drag-handle signals. Check/submit-after-answer policy (parked by Dylan). Site allow-list for packaging.

**Watch out:** New base for every branch: 5ab6e29. The other Claude session (assignment-agent-04) has not acknowledged the 0.10.41 design/diff messages; its aria-live/aria-pressed patch remains uncommitted on claude/site-compat.

## 2026-09-20 - claude - a retry re-asks the same multi-part question, not the tab on screen (0.10.42)

**Did:** M4-14 (Ch.4 Q3, 1:31 PM on 0.10.38): the first plan call returned all thinking (15,900 of 15,900 tokens, provider AtlasCloud); the harness retried without that provider -- correct -- but `paid()` retried with `fresh = await this.observe()`, which sees only the tab on screen, so "Required 2 -- Net Income" fell out of the request (28 slots -> 27, `Required 2 … slots: 0`); the model planned the 27 it was shown (correct accounting, NI 7,850) and `validate(plan, obs)` refused it against the original 28-slot union: `Plan does not cover every answerable slot`. Same lines at 0.10.35 and 0.10.37 -- a latent bug in every retry path on a multi-part question (all-thinking, thinking-off, format correction, inspection-target correction). Built (Dylan: "make the McGraw Hill update you recommended earlier"): `paid()` keeps the fresh observe only as the staleness check; when `obs` is a multi-part union it retries with `{...obs, observation_id: new}` (`again`), else with `fresh`; all four retry sites and the inspection-correction `offered_slots` use `again`.

**Verified:** New `test_a_retry_after_an_all_thinking_reply_still_plans_every_part` in `tests/test_planner_parts.py` (`tabs_parts.html`, two tabs, 3+2 slots): the scripted model's first reply is the live truncation, the second plans what it is shown -> both requests carried 5 slots / parts [3,2] with distinct observation ids, run finished, all five cells hold their values. On the unfixed runtime the same test stops with exactly the live message. Parts suite 9/9; acceptance + discovery-runtime + choice-mode 34 passed. Full suite: see the merge commit.

**Left undone:** Live M4-14 rerun. Formative bundle (no go yet): role before `e.type` for non-input controls; candidates must not be cut out of the question stem (numbers vanished: "labor force is million and million"); question fingerprint too sensitive to a page's own post-answer redraw (`TARGET_STALE` after a correct click); trailing-empty-segment slot keys; one-label aliases; duplicated option text; chrome labels. Khan "unresolved leftovers" ending. MathPapa graph candidates. Quizlet multi-select live proof of 0.10.41.

**Watch out:** `again` reuses the union's slots and frames as they were when the first call was made; the staleness check (`fresh.question_key`/`document_id` must match) still runs first, so a page that actually changed still aborts with TARGET_STALE rather than replanning stale content.

## 2026-09-20 - claude - the screen is the readback for choice groups with no DOM selected-state (0.10.41)

**Did:** Quizlet "Select all that apply" (5:01 PM on 0.10.40): group found, read as pick-many, model chose the right five, harness refused to click -- `No supported selected-state readback` (cards carry only a class; the other session's evidence file confirms no ARIA state before or after). Dylan: build the screen readback as an extra measure that only triggers on that failure; the other Claude session did not receive the design message (sent twice), so built on his instruction and left the diff for its review. `planner_content.js` discoverChoices: `verification` = result_icon | state_attribute | **visual_change** (the last only when neither of the first two exists); such a group is `ready` when its labels are unique and its mode is known; `evidence.counter` = the integer from "(N left)" / "N of M selected" in the scope text. `planner_runtime.js`: `slot()` serves these slots' `current`/`checked` from harness memory (`this.current.visualSelections`), because the page cannot; `visualToggle()` per member: `park()` the pointer off the group's box, `cropPixels()` = CDP `Page.captureScreenshot` with a CSS-pixel `clip` of the member's box, hit-tested click, park again, crop again, `changedFraction()` >= 1% of pixels (any channel > 24/255) AND the counter moved by one when present; pass -> remembered + `VERIFY: Screen readback confirmed the click (pixel change + counter)`; fail -> `INPUT_NO_EFFECT`, the card goes on `this.current.visualDead` and is never clicked again (a second click on a toggle could undo an invisible selection). If the page graded on a click (`obs.feedback`, any `result_feedback`, `grade_state` known) the attempt is spent: no further clicks, `GUARD_REJECTED` names how many planned choices were not entered, and `confirmVisually` skips that slot so no whole-page screenshot (with a revealed key) goes to the model.

**Verified:** `tests/test_planner_visual_readback.py` on `choice_mode.html?mode=visual|visual_noop|visual_grade` (six cards, selection = class only, "(3 left)" counter, hover glow on every card): three planned picks -> three confirmed clicks with `3 -> 2 -> 1 -> 0`, pointer parked >= 6 times, page shows exactly those three selected, one end-of-question screenshot witness; a card that ignores clicks -> readback fails on its own pixels (hover glow did not fool it), `INPUT_NO_EFFECT`, one click only, A stays confirmed; grading after two picks -> stop with `GUARD_REJECTED`, third click never sent, zero model screenshots. Updated expectations: `test_group_scope_and_unproved_semantics[cards]` (Codex's) now expects `choice` -- tabindex-only cards are answerable; my `noreadback` case now expects one honest click then stop. Choice-mode 8/8, visual 3/3, discovery + result cards + interactions + contracts 109 passed. Full suite: see the merge commit.

**Left undone:** Live Quizlet multi-select run on 0.10.41 (the first real test). Formative fixes not started (no go): non-input controls should take their kind from the ARIA role, not `e.type` (`planner_content.js:362`, pre-existing); group slot keys should not end in an empty segment; safe aliases choose_one<->set_choice_set for one label; chrome labels previous/next/hint/feedback/strikethrough. MathPapa graph candidates; multi-part retry bug; the two-tab and Khan "unresolved leftovers" ending.

**Watch out:** Do not crop a full `Page.captureScreenshot` by the layout-metrics ratio: under Playwright the captured surface is 1484x949 for a 1500x1100 layout viewport and the ratio lands the crop on the wrong pixels -- that is why `cropPixels` uses a CDP `clip`. The result-card path (Codex, 0.10.38) still uses the ratio crop; fine in a real window (ratio = DPR) but worth converting to `clip` when next touched. `visualSelections` and `visualDead` live in `this.current` and persist with the ledger; they are per question and die with it.

## 2026-09-20 - claude - the fieldset owns the legend; links are never choices; the planned operation is the model's pick-one/pick-many reading (0.10.40)

**Did:** 0.10.39 did not close Khan live (3:51 PM rerun): the A-E group stayed unresolved with the mode reason, `selection_mode_source: null`, and the model planned `choose_one` E directly (correct) and was refused. Read the live DOM again (read-only): the choices sit in `button < li < ul[role=list] < div#…-scroll[role=group] < fieldset`, the legend directly under the fieldset -- `discoverChoices` took the NEAREST grouping element (`closest('fieldset,[role=radiogroup],[role=group],…')`), i.e. the scroll wrapper, which does not contain the legend; my 0.10.39 fixture lacked that wrapper, so its test passed and the page failed. The breadcrumb ("Course… / Unit 6") is `a[href][tabindex=0]` links in the course accordion, not a `<nav>`, so the chrome exclusion missed it; share buttons and exercise controls were dropped as intended. And the model never sent the optional `classify_choices` + `selection_mode` round -- it plans directly, every run. Agreed with the other Claude session (both watch-items noted by it, no amendments) and built, general by construction: (1) classification scope = the enclosing `fieldset` when one exists (a legend is by definition its fieldset's caption; no inner wrapper may cut it off), else the nearest radiogroup/group/article/question root; (2) candidate members are never `a[href]` links nor inside one (a link with a destination is navigation on every site); (3) the planned operation IS the reading: `planner.py` `mode_assertable()` -- an unresolved `candidate_choices` slot whose reason starts "Single or multiple selection" and that has a state attribute or result-icon verification -- may be named by a plan with `choose_one` (pick one) or `set_choice_set` (pick many); the plan must still cover every resolved slot and may name no other unresolved slot; the runtime `validate()` mirrors it and `execute()` calls `classify_choices` with the mode derived from the operation before anything is clicked, logs `Model read this group as pick one; accepted because the page text says neither` (or `not accepted` -> `GUARD_REJECTED`, nothing clicked), re-observes the promoted slot, then executes and verifies as before with the VERIFY `cardinality` caveat. The explicit request path from 0.10.39 stays; prompt rewritten to say plan directly.

**Verified:** Fixture `choice_mode.html` rebuilt to the exact live chain (fieldset > div[role=group] scroll wrapper > ul > li > button; breadcrumb as accordion links). `tests/test_planner_choice_mode.py` 7/7: aria-hidden legend behind the wrapper -> classified from page text, single slot, finished; no instruction + direct `choose_one` plan -> one plan call, accepted, A pressed, INSPECT + VERIFY caveat lines; explicit classify request path still works; genuinely hidden legend -> unresolved; "Select all that apply" beats a model "choice"; a self-contradicting legend -> `GUARD_REJECTED` before any click; buttons without `aria-pressed` (Quizlet-like) -> `QUESTION_INCOMPLETE`, never planned. Contract: `choose_one`/`set_choice_set` accepted on a mode-only group, `set_selection` refused, a no-readback group refused. Contract + discovery + result-card + interaction suites: 104 passed. Full suite: see the merge commit.

**Left undone:** Live Khan run on 0.10.40. Quizlet multi-select readback (cards carry only a class; the "(N left)" counter is the independent check) -- needs one anonymous live click's evidence first. MathPapa graph candidates by drag-handle signals. Multi-part retry bug (M4-14). General probing-click + before/after verifier via the plan loop.

**Watch out:** `mode_assertable` is the only door through which an unresolved slot enters a plan; widen it and the "no readback -> no click" rule goes with it. The fieldset-first scope will mix text from two groups that share one fieldset -- conflicting phrases then yield mode null and the guard refuses any reading, which is the safe outcome.

## 2026-09-20 - claude - on-screen instructions count even when aria-hidden; the model may fill pick-one vs pick-many when the page says neither (0.10.39)

**Did:** First Khan Academy run on 0.10.38 (2:06 PM, MiniMax M3): the new candidate path found the A-D group with `aria-pressed` readback and full labels, but it stayed unresolved with `Single or multiple selection is not established by the visible instructions`; the model planned it anyway (correct answer A, correctly dismissed the breadcrumb, share buttons and exercise controls it was also offered) and `planner.py:327` refused the plan because unresolved slots are never planned. The other Claude session read the live page: Khan's "Choose 1 answer:" is a `<legend aria-hidden="true">` -- on screen for a person, skipped by our text walk because `shown()` honours aria-hidden; Quizlet's "Select all that apply" is hidden the same way. I confirmed read-only on the live Khan DOM: share buttons sit in `<header>`, "Draw on exercise / Start over / Skip / Check" in the content footer. Joint conclusion with that session, four parts, built together (Dylan: "go ahead and build 0.10.39 once 03 agrees"; owner of planner_content.js said yes): (1) `planner_content.js` `renderedText` takes a visibility test; the classification scope text uses `onScreen` (display/visibility/clientRects, ignoring aria-hidden) -- `shown()` itself is untouched and still gates every target, candidate and hit test; (2) `classify_choices` may carry `selection_mode: choice|choice_set` (`planner.py` Inspection schema + prompt; runtime passes it through); the page-side classifier stores it per container (`assertedModes`) and applies it only while the page text says neither, reports `evidence.selection_mode_source: page_text|model_assertion`, and drops a claim that did not promote; the runtime logs `Model read this group as pick one; accepted because the page text says neither` (or `not accepted`) and the VERIFY event carries `cardinality: asserted by the model; verified by selected-state readback only` when a result rested on the claim; (3) post-click verification is the existing `matches()` exactly-one / exact-set readback -- no new logic, the residual risk is now named in the log; (4) candidates never come from `header, footer, nav, [role=navigation|banner|contentinfo|toolbar]`, and members whose label starts with draw / start over / skip / report / share / flag are not answer choices.

**Verified:** New fixture `choice_mode.html` (the live Khan shape with chrome) and `tests/test_planner_choice_mode.py`: aria-hidden legend -> group promoted from page text, one slot offered (no chrome), run finishes with A pressed and no cardinality caveat; no instruction -> unresolved, then the scripted model's classify_choices with selection_mode "choice" is accepted, the plan runs, A pressed, VERIFY carries the caveat and the INSPECT event names the acceptance; display:none legend -> still unresolved (genuinely hidden text does not count); "Select all that apply" + model says "choice" -> refused, page text wins, kind stays choice_set, nothing clicked. Contract: selection_mode only with classify_choices, otherwise SCHEMA_INVALID; bad values rejected by schema. Discovery + result-card + interactions + discovery-contract suites: 54 passed unchanged. Full suite: see the merge commit.

**Left undone:** First live Khan run on 0.10.39 (should now classify from the legend and answer; the model path shows up in the log the first time a real page has no instruction). Still queued for Dylan's go: the multi-part retry bug (M4-14: `paid()` retries with a one-tab observation); graph candidates by behaviour signals (MathPapa's Graphie: invisible `cursor:move` drag circles, no data-point-id); the general probing-click + before/after verifier (plan loop). An independent cardinality counter (Quizlet's "N left") is not read yet.

**Watch out:** `onScreen` must stay confined to the classification text walk; using it for targets would let aria-hidden decoys become clickable. `assertedModes` is keyed by container element and survives observes within a page load only; a refused or non-promoting claim is deleted in the classify handler, so a later observe never shows a stale `model_assertion`. Fixture buttons inside a `<form>` need `type="button"` -- the first fixture draft submitted the form on click and the run stopped with `TARGET_STALE: Document was replaced`, which is the correct harness behaviour for a navigation, not a bug.

## 2026-09-20 - claude (integrator) - 0.10.38 merged and deployed; M3-9 confirmed on 0.10.37

**Did:** Dylan confirmed M3-9 completed on 0.10.37 (the opener-label fix held live) and said to deploy the Codex update. Committed Codex's finished tree on codex/cross-site-discovery (5612367), merged into codex/optional-numbering (3e065df, clean, no conflicts), refreshed deploy-source file by file (diff clean, local capabilities check 0.10.38 with choice_discovery + bounded_format_correction), `railway up`, live `/api/capabilities?protocol=4` reports 0.10.38, health ok. Backend first; the 0.10.37 extension keeps working against it (its feature gate is a subset) until Dylan reloads.

**Verified:** Full suite on the exact tree by the other Claude session: 426 passed + 1 Playwright TargetClosedError (browser crash) that passes alone. Merged-tree smoke: discovery contract + planner contract + core + result cards + openers + sheet entry = 141 passed. Review record: plans/cross-site-discovery/REVIEW-b5-final.md (A-G verified in code).

**Left undone:** Dylan reloading the extension to 0.10.38 and a first live run on it (M3-9 again is the regression check; a Khan MCQ is the new-path check). Quizlet result cards are fixture-verified only -- live CSS-check ancestry and an installed-extension Quizlet run are unfinished; 0.10.38 does not claim Quizlet support. Two prior items unchanged: same-frame nested scroll (`area` field), and the >100-candidate container still flipping `limited` (planner_content.js discoverChoices).

**Watch out:** New base for every branch is 3e065df. Worktrees: assignment-agent-formats (claude/question-formats), assignment-agent-sites (claude/site-compat, the other Claude session, aria-live/aria-pressed work still uncommitted), orca/workspaces/.../codex-cross-site-discovery (codex/cross-site-discovery, now committed). The stale checkout C:/Users/falay/assignment-agent is still stale.

## 2026-09-20 — claude 03 — final suite reran, green

**Did:** Ran the exact command the prior entry left pending: `python -m pytest -q --tb=short --junitxml=C:/Users/falay/AppData/Local/Temp/assignment-discovery-full-suite-final.xml` on this tree (uncommitted 0.10.38, base ba801df). No source edited.

**Verified:** 426 passed, 1 failed on first pass -- `tests/test_planner_parts.py::test_confirmed_sheet_cells_survive_the_tab_being_rebuilt`, `playwright._impl._errors.TargetClosedError: Worker.evaluate: Target page, context or browser has been closed` (a browser process crash mid-run, not an assertion failure). Reran alone per the existing "browser-test failure rerun alone" convention: passed in 9.29s. Full suite: 427/427 effectively green. Total wall time 19m14s.

**Left undone:** Commit, integration, backend deploy, extension release -- still b5's, per existing authorization. Live exact CSS-check ancestry and installed-extension Quizlet run remain unverified (my Chrome connection was disconnected, per the prior entry; now back, but this task only asked for the suite rerun).

**Watch out:** Nothing new; see the entry below for what still applies (do not merge my older root-wide aria-pressed classifier; do not edit the stale `assignment-agent` checkout or `deploy-source/`).

## 2026-09-20 — codex — resume here: final suite must be rerun after test-envelope fix

**Did:** Dylan asked for a handoff. The working tree is `C:/Users/falay/orca/workspaces/assignment-agent-question-coverage/codex-cross-site-discovery` on branch `codex/cross-site-discovery`, based at `ba801df` (0.10.37). The uncommitted tree contains the approved cross-site discovery/recovery implementation and version 0.10.38. b5 reviewed the production diff and marked it READY pending a green final suite; b5 approved the one test-only evidence-envelope adjustment below. Dylan’s implementation/shipping authorization is already recorded; b5 remains the integrator/deployer.

**Verified:** Discovery/result-card focused tests passed (26 before the final observation-context tightening; the final result-card run passed 8 tests plus the automatic-advance case). Runtime/contract/executor/sheet/parts checks passed 72 tests in 270.51 seconds. The isolated inspection test variants passed 2 tests in 5.92 seconds after updating `tests/test_inspection_mapping.py` to assert the new grouped `results[]` evidence envelope for question-wide scripts: only the answer iframe resolves `#amount`, while the top frame reports a missing binding. b5 approved that test-only change. No paid model calls were made. The detached full suite PID 12900 was started before this test-only adjustment and reached 67%; its only failure was the stale frame-envelope assertion, so its result is not the final-tree result.

**Left undone:** Rerun `python -m pytest -q --tb=short --junitxml=C:/Users/falay/AppData/Local/Temp/assignment-discovery-full-suite-final.xml` on the current tree and rerun any browser failure alone. Then send b5 the final summary, commit this branch, and have b5 integrate and deploy backend first followed by the matching extension. The live Quizlet CSS check ancestry and an installed-extension Quizlet run remain unverified because Claude 03’s Chrome connection is disconnected; the release must say Quizlet result cards are fixture-verified only. Do not claim live Quizlet support. No commit, merge, push, deployment, or publication has occurred.

**Watch out:** Do not merge Claude 03’s older root-wide `aria-pressed` classifier. Do not edit `C:/Users/falay/assignment-agent` or `deploy-source/` directly. Keep the result-card guard: one durable attempt, exact clicked-card result marker, cropped screenshot containing only the selected card, pre-answer context, no repair request after feedback, and no replay when the question changes. b5 noted one nonblocking edge case: a single candidate group with more than 100 members still marks discovery incomplete; it remains a safe stop and was intentionally left unchanged for this release.

## 2026-09-20 — codex — cross-site discovery implementation and result-card verification, not released

**Did:** Implemented the approved discovery/recovery scope in isolated `codex/cross-site-discovery`, base ba801df; local extension/backend 0.10.38. Preserves aria-live stems, groups structural candidates with full labels, trusted read-only classification, retained scoped inspection evidence, explicit incompleteness and one metered malformed-JSON correction. Addressed b5 A-G review, including exact jSheet spare/active classes and post-answer unlock. Corrected 03's numeric-cardinality finding. Added one-attempt result-card execution with exact-card result witness and cropped verification using pre-answer context; no repair from revealed answers. User paused for questions and explicitly resumed. b5 remains integrator/deployer under existing shipping authorization; source remains uncommitted here.

**Verified:** Focused discovery/result-card suite: 26 passed in 55.95s before the subsequent pre-answer-context tightening. Earlier recovery/sheet/parts/contract checks: 31 passed; runtime/sheet/parts/executor: 79 passed before final review refinements. Real packaged-extension fixtures cover wrong/revealed sibling, screenshot-capture transition, transition during verification, Stop and interrupted resume. Test failure was reproduced alone and traced to result text contaminating labels; fixed explicit-accessibility label extraction. A separate transition fixture initially called its page helper in the wrong execution world; corrected and asserted the actual stem change. No paid provider calls in these tests.

**Left undone:** Current focused regression run and final full pytest suite; finished-diff Claude reviews; live exact CSS-check ancestry and installed-extension Quizlet run; commit, integration, backend deployment and extension release. Claude API/connection errors and b5 sign-in currently delay reviews. An independent Playwright request reached Quizlet's human-verification challenge; did not bypass it. See `plans/cross-site-discovery/PLAN.md` and the pending 0.10.38 architecture section.

**Watch out:** Actual Quizlet evidence is in `C:/Users/falay/assignment-agent-sites/QUIZLET_LIVE_EVIDENCE.md`: option-N is a descendant of SECTION, SVG check can reveal an unclicked correct answer, selected-correct uses a CSS animated check, and automatic advance occurs with timing unmeasured. Only exact-card feedback counts. Do not merge 03's older root-wide aria-pressed patch. Do not claim every site is supported or this build has shipped. The stale `assignment-agent` checkout is not the release source.

## 2026-09-19 - claude - a shared opener label is evidence, not a veto; every refused opener is logged (0.10.37)

**Did:** First live run on 0.10.36 (MiniMax M3, 1:20 PM, M3-9) got past this morning's wall -- t3 `Service Revenue` chosen after three listbox scrolls with no page scroll -- and filled 6 of 18, then t7 (`c0_r7`, the "Expenses" section-header dropdown) stopped: `opening_control: missing`, ladder fell to `open_combobox` + ArrowDown + Alt+ArrowDown, `WRONG_MENU_OWNER`, identical retry, `REPEATED_STATE`. Cause (`planner_content.js` `openingControls`, old lines 116-125): McGraw's shared "Show All Items" arrow carries the ACTIVE cell's accessible name as its aria-label, and McGraw names the active cell after the header above it -- `c0_r7` became "Revenues" on activation (log: `resolved_target.label`). `c0_r3` had shown the text "Revenues" since t2, so the label matched two cells; `matches.length===1` failed and `if(matches.length||...)continue;` threw the arrow away although its centre sat inside this cell and no other. Codex vetted the diagnosis before it was built (read-only `codex exec`, prompt + verdict in the session scratchpad): "unsure 0.88" -- the veto is real and replay-confirmed, but the log could not prove it was the only thing that happened at 1:23:00 because no rejected candidate was ever recorded; and my first proposed condition would have accepted a label matching only OTHER cells. Built (Dylan: "go ahead a run"; owner of `planner_content.js` said yes): (1) `openingControls` records every explicit opener it refuses -- `{label,title,why,matches|cells,local,viewport}`, capped at 8 -- as `opening_control.rejected`, which reaches the log through the existing click details and the `WRONG_MENU_OWNER` fault; (2) a label that names a different cell (`label_names_another_cell`) or a set that leaves this cell out (`label_excludes_this_cell`) still refuses; a label shared WITH this cell falls through to the geometry test and is accepted as `overlay_geometry` with `shared_label` on the candidate; unique label unchanged. Other refusal reasons named: `contained_in_another_cell`, `controls_another_cell`, `menu_owned_by_another_cell`, `not_a_button`, `outside_this_cell`, `inside_another_cell`.

**Verified:** New fixture `dropdown_shared_label.html` (header already "Revenues", an account row, a second header; one shared arrow over the active cell with the active cell's name as its label; modes shared / foreign / excludes) and three tests in `test_planner_openers.py`: shared -> run finishes, both empties filled, sec2 opened by `open_menu_by_geometry` with `shared_label:"Revenues"`; foreign (label names the header alone) -> arrow never clicked, `WRONG_MENU_OWNER`, `rejected[].why == label_names_another_cell`, `matches == ['id:sec1']`; excludes (stale name on the account row) -> the account row, whose name is in the set, is filled; the second header, whose name is not, is refused with `label_excludes_this_cell`, `matches == [row_a, sec1]`. On the 0.10.36 content script the shared case reproduces the live log exactly (`WRONG_MENU_OWNER` -> `REPEATED_STATE`). Openers file 11/11. Full suite: see the merge commit.

**Left undone:** Live M3-9 rerun on 0.10.37 -- not yet seen. If t7 still stops, the log now carries `rejected[]` and the diagnosis is read off it, not inferred. Same-frame nested-scroll case from this morning's entry still open (needs `area` from `scrollInfo`; owner asked, awaiting Dylan's go).

**Watch out:** The exact set of cells that collided at 1:23:00 was never observed (no DOM access from the session); the shared case is the one consistent with the log and the code, and it is now logged. `key(c)` in `rejected[].matches` registers unregistered nodes in the serial map -- bounded by the cap of 8. Discovery also clicks the shared arrow once per cell (`clicks` in the fixture shows it), so a fixture assertion on "never clicked" must exclude discovery.

## 2026-09-19 - claude - reveal the scroll area, not the target: nested scroll across frames (0.10.36)

**Did:** First live run on 0.10.35 (MiniMax M3, 12:20 PM, M3-9): plan accepted with the two blank spare rows (t5/t14 label ""), answers 1-2 filled and verified, then task 3 (`Service Revenue`, item 22 of 25) stopped: `planner_runtime.js:179` picked the OUTERMOST clipped frame and scrolled the page (`node:3`) 472 px toward the option's rendered position, which dragged the open list under the fixed header (list at page y=-33, pane visible from y=97); the wheel meant for the list was then sent to page (383,43) -- the header -- so `moved:false` beside `wheel_hit:true` (the hit test is per-frame and knows nothing of outer clipping), `INPUT_NO_EFFECT`, identical retry, `REPEATED_STATE`. Not a budget or truncation problem: plan call 110 s, `finish_reason:stop`, failure 8 s later in EXECUTE. Built (Dylan: "go ahead and update the system"): the frame walk now projects the wheel point of the innermost clipped scroll container outward (`mover`/`reveal`), so outer layers are asked to show the scroll area that must move, never the target; `route.find` (outermost clipped) is then correct, and a wrongly scrolled page self-corrects on the next measurement (the pane scrolls back UP). New guard: every frame outside the mover must report `hit` at the projected point or the wheel is refused with `GUARD_REJECTED: An outer layer covers the scroll area that must move; no wheel was sent.` -- no separate scroll-restore step is needed because the retry re-derives geometry from the page as it is. Two-session setup this morning: worktrees `assignment-agent-formats` (`claude/question-formats`, this) and `assignment-agent-sites` (`claude/site-compat`, the other Claude session: site compatibility), both cut from c94c820; the live folder is merge + deploy base only.

**Verified:** New `tests/test_planner_nested_scroll.py` (6 cases, the live page's shape: 97 px fixed header, pane at (205,97) 1214x686, iframe 21 px inside, `scroll_dropdown.html` extended to 27 options so the wanted one renders 728 px below the list top; native and nicescroll variants): list in view + option below the pane -> only the list scrolls, pane `scrollTop` stays 0, every wheel lands inside the pane; the exact live state (pane pre-scrolled 451, list at -33..79) -> pane scrolls up first (delta<0), then the list, selection made, nothing sent above y=97; list itself below the pane -> pane scrolls toward the LIST's centre (534, not the option's clamped 600), then the list; a fixed banner over the list in the top page -> `GUARD_REJECTED`, zero wheels, zero clicks. All 6 fail at c94c820, all 6 pass with the fix. Existing 8 scroll_dropdown + 12 offscreen tests unchanged. Full suite: 378 passed, 1 error = `test_floating_editor_ownership_and_stop_before_typing[wrong_cell]` fixture `serviceworker` 30 s wait under load; passed alone (3/3 params, 21 s).

**Left undone:** Live M3-9 rerun on 0.10.36 -- not yet seen end to end. Same-frame nested case (a scroll container that is itself fully hidden by an outer container in the SAME frame) still scrolls the outer one toward the target, as before, because the content script reports a container's visible rect only, not its full box; a one-field addition (`area` in page coords at `planner_content.js:197`) would let the runtime treat it like the cross-frame case -- that file is the other session's, asked as a follow-up. Grok's earlier omission of the $3,500 utilities bill: MiniMax M3 included it this run (NI 4,170, margin 24.8%).

**Watch out:** `reveal()` only switches the projected point when the innermost clipped container has an in-frame wheel point; otherwise the target's own point is projected (old behaviour). The overlay guard checks `measurement.hit` of frames OUTSIDE the mover only -- the mover's own frame may legitimately report `hit:false` (its point is under the header when the pane is what has to move). The other session edited `planner_runtime.js` (lines 202-204, 810: error detail surfacing) on its branch without asking the owner first -- additive, different region, no conflict expected, but a breach of the split; flagged to Dylan and to that session. Version constant lives in BOTH `extension/manifest.json` and `app.py:449`; bump both at merge.

## 2026-09-19 - claude (site-compat, worktree assignment-agent-sites, branch claude/site-compat) - decorative canvas/svg no longer misclassified as a graph

**Did:** Live Khan Academy run (M copy log, 12:26 PM, real interest rates question): `GUARD_REJECTED: An overlay blocks the exact target`, $0 cost, zero model calls, phase INSPECT "Reading visible graph geometry." Verified live via browser inspection (not guessed): the page is a plain 4-option MCQ with an inert `<canvas>` (500x500, `pointer-events:none`) mounted inline in the content -- Khan Academy's confetti/celebration canvas. `planner_content.js:297`'s classifier treated any bare `svg`/`canvas` (or an svg containing `circle[tabindex]`/`circle[data-point-id]`) as a graph "position" slot with no interactivity check; `planner_runtime.js:631` then eagerly visually-measures every uncalibrated position slot before any plan call, and `measure()`'s hit-test (`planner_content.js` `inspect()`) can never succeed on a `pointer-events:none` element, so it always throws `GUARD_REJECTED`. Confirmed via `git log -S` this selector is unchanged since 678d595 (0.9.0, 2026-09-15) -- not a regression, latent since the planner's first version. Fix: `planner_content.js:297` classifier now also requires `getComputedStyle(e).pointerEvents!=='none'`. Separately: `planner_runtime.js`'s top-level Fault catch (line ~810) discarded a Fault's `actual` diagnostic payload; now surfaces it as `failure_data` on the NEEDS_REVIEW event. The two `measure()` GUARD_REJECTED throws (`planner_runtime.js:202,204`) now pass `hit_info`/`target_info`/`click_point` as that payload.

**Verified:** First attempt dropped bare `canvas` from the match entirely and broke an existing, previously-passing test (`test_planner_executor.py::test_opaque_graph_visual_fallback_uses_fresh_measurements`, a real draggable canvas graph fixture with no `data-graph`/`role=graph` markup) -- caught by running the full suite before considering this done, not assumed safe. Corrected to keep the existing match shape and add only the `pointer-events` guard. New tests in `tests/test_planner_interactions.py` (mine to own): `test_decorative_noninteractive_canvas_is_not_classified_as_a_graph` (new fixture `planner_decorative_graphic.html`, a plain radio-group MCQ plus the inert canvas: slot classification is `['choice']` only, `engine.run()` finishes, no `visual` phase call ever made) and `test_real_overlay_still_refused_and_now_reports_what_was_hit` (new fixture `planner_overlay_blocked.html`, a real opaque pointer-events:auto div placed exactly over option B: still correctly refused with `GUARD_REJECTED`, and `failure_data` now names the actual blocker element and the intended target). Full offline suite: 374 passed, 1 error (`test_planner_sheet_entry.py::test_nothing_is_committed_when_the_editor_does_not_hold_the_planned_value`), 17m27s. That one test passed alone in 23s on rerun -- the known "loaded-extension tests flake under full-suite load" case (AGENTS.md), unrelated file, not caused by this change.

**Left undone:** Not touched: the model-facing prompt, verification logic, or any other question-type/site handling -- this is a narrow classification + diagnostic-logging fix, not new graph-answering capability. Not pushed, merged, or deployed -- per the working agreement this worktree never merges into `assignment-agent-question-coverage` directly; `assignment-agent-b5` (branch `claude/question-formats`) is the integrator. Not live-verified against the actual Khan Academy question yet (that requires Dylan reloading the merged, deployed build).

**Watch out:** A canvas-based graph that lacks both `data-graph`/`role=graph` markup AND calibratable DOM circles still only works through the pre-existing bare-`canvas` visual-measurement fallback (unchanged) -- this fix did not add or remove that path, only gated it on actual pointer-interactivity. First attempt at this fix dropped bare `canvas` from the match entirely and silently broke `test_opaque_graph_visual_fallback_uses_fresh_measurements` (a real draggable canvas graph with no `data-graph`/`role=graph` attribute) -- caught only by running the full suite, not by reasoning about it. Do not narrow that match again without rerunning that specific test.

## 2026-09-18 - claude - blank is a legal answer when the page offers it (spare statement rows) (0.10.35)

**Did:** First live run on 0.10.34 (Grok, 10:00 PM, M3-9): setup fast, plan call 95.5 s and COMPLETED (past the old 60 s), 18 tasks correctly omitting the 2 locked cells -- then `planner.py parse_plan` refused it: `SCHEMA_INVALID: empty option label` on `set_selection` label "" for c0_r5/r10/r11, the 3 spare rows of a 13-row income statement (Grok's reason: "Unused lines left blank"). The contract made that unavoidable: prompt "exactly one task per supplied slot" + `validate_context` "plan must cover every resolved offered slot" force a task for spare rows; the page's menus offer "" as their first entry (read by discovery); the 0.9.0 rule forbade choosing it; no leave-empty operation exists. Built (Dylan: "go ahead and make the blank row fix"): removed the unconditional rule from `parse_plan`; `validate_context` now accepts a blank label exactly when the slot's `options` include "" and otherwise refuses with `OPTION_MISSING: blank is not an offered choice for this slot` (also for `choose_one`/`set_choice_set`); PLANNER_PROMPT explains: empty final state -> set_selection "" when offered / enter_value "", "Never park a wrong account in a spare row to fill it." No runtime change was needed: `execute()` already skips a task whose slot shows the desired value (L254), the menu path matches label "" like any other (`norm`), and `enter_value` already handles an empty target (`if(typed)... else Backspace`, pre-commit `sameValue('','')`). Fixture `dropdown_openers.html?prefill=<label>` starts the cell filled.

**Verified:** Replayed Grok's exact rejected `raw` against the exact `DOM sent to model` from the 10:00 PM log through `parse_plan`+`validate_context`: ACCEPTED, 18 tasks, blanks on c0_r5, c0_r10, c1_r10, c0_r11. Contract `test_blank_is_a_legal_answer_exactly_when_the_page_offers_a_blank_choice` (accepted with verify `selection_equals ""`; refused for a menu without a blank entry and for whitespace). Browser: `test_a_planned_blank_clears_a_filled_dropdown_and_leaves_an_empty_one_untouched` (prefilled "At March 31" -> blanked through the menu, `choose_option` clicked), `test_a_planned_blank_on_an_already_blank_dropdown_touches_nothing` (no execution-phase click; the single menu open is discovery), `test_a_planned_empty_amount_clears_a_filled_cell_and_skips_an_empty_one` (91,300 -> cleared and committed empty; second run no click). contract+core 109 passed; openers+sheet 16 passed; full suite 372 passed + 1 error (`test_svg_math_coordinates_nested_transform_and_resize`, a Playwright fixture TimeoutError at setup under full-suite load -- unrelated SVG graph test; passed alone in 4.4 s, the known load flake). Live `/api/capabilities?protocol=4` -> `extension 0.10.35`, health ok.

**Left undone:** Not yet seen end to end live: the next M3-9 run should now execute -- watch the three spare rows stay blank and c1_r10 stay empty. Grok's plan content excluded the $3,500 July utilities bill; that is the model's accounting, flagged to Dylan, not the harness's call. The 5:11/9:11 PM slow-click cause is still unknown (every click logs `input_ms`). Everything in the entries below still stands.

**Watch out:** A blank label passes only through `validate_context` (needs the observation); `parse_plan` alone no longer rejects "" -- any new caller of `parse_plan` without `validate_context` would accept a blank on a slot that cannot be blanked. Within one browser test, a second `navigate()` after a stubbed `run()` fails with "Browser input cancelled." (debugger still attached across the navigation; `attach()` returns early and `begin()` guards before clearing `cancelled`) -- use one navigation per test.

## 2026-09-18 - claude - model-call deadline from the token allowance; unconfirmed cost charged at worst case, never frozen (0.10.34)

**Did:** M3-9 9:13 PM run on 0.10.33: setup completed despite 14 more ~5 s clicks (`input_ms` 5,061-5,256 with `dom_ms` 36-189 -> the time is in Chrome accepting the input, not our DOM; slow only between 9:11:55 and 9:13:05, cause still unknown), a complete 20-slot plan request went out, and the run died at exactly 60 s: `background.js` aborted the request (`setTimeout(...,60000)`, 0.9.0 code) and Railway's HTTP log shows `POST /api/agent/plan` 60,005 ms status 499 "client has closed the request before the server could send a response"; `agent.py planner_complete` had the same fixed `httpx timeout=60`. The allowance was 3,000 answer + 10,500 thinking = 13,500 tokens; MiniMax measured 120-260 tok/s in live logs -> 52-112 s. Old limit, hit because 0.10.25 (thinking on) and 0.10.32 (budget scaled by slots) lengthened replies without moving it. Second consequence found in `store.py`: `reserve_plan` counts every reservation as `usage.unknown+1`, only `settle_plan` clears it, a timed-out call never settled, and `reserve_plan` refuses every later call for that identity ("prior provider cost is unconfirmed") with no code path that could clear it -- Dylan would have been locked out of planning. Built (Dylan: "ok go ahead and build it"): (1) `planner.request_deadline(max_tokens)=min(300, 30+tokens/50)` and `REQUEST_DEADLINE_MAX=300`; `app.py` passes it to `planner_complete(deadline=)`, which uses it as the httpx timeout; `/api/capabilities` advertises `request_wait_seconds` (300). (2) `background.js`: `requestWaitMs` = advertised wait + 15 s (default 75 s until capabilities are read), error names the actual wait; the resume path accepts status `charged_worst_case` as settled. (3) `planner_runtime.js`: `Recovery.exclude(ms)` and `Engine.modelCall(phase,body)` wrap the three model calls (plan/repair, visual, verify) so model wait time is taken out of the 90 s no-progress and 5-minute question clocks; unused `LIMITS.request` removed. (4) `agent.py`: any outcome whose cost cannot be confirmed -- timeout (`PROVIDER_TIMEOUT: ... within N s`), transport failure, 5xx, malformed body, 200 without cost -- is settled at the reserved worst-case amount with status `charged_worst_case` (`worst_case()` helper); 4xx rejections stay free at 0. (5) `store.py`: `planner_calls.created` column (ALTER on first use; NULL = pre-0.10.34), `STALE_RESERVATION_SECONDS=360`, `_reconcile_stale` charges pending rows older than that (or NULL) at their reserved amount; runs at app startup (`lifespan`) and inside every `reserve_plan`. `settle_plan` gained `status=`. Test hook: `__assignmentHarness.requestWaitMs` / `setRequestWait(ms)`.

**Verified:** Contract: `test_request_deadline_scales_with_the_token_allowance_and_is_advertised` (3000->90, 9000->210, 13500->300 cap, STALE>MAX, capabilities field), `test_timed_out_call_is_charged_at_worst_case_and_does_not_freeze_the_identity` (MockTransport raising ReadTimeout: message names 300 s and $0.07, httpx client got timeout=300, row `charged_worst_case`, next reserve_plan succeeds), `test_unconfirmed_outcomes_all_charge_the_worst_case` (502 / non-JSON / no cost -> charged; 402 -> settled at 0), `test_stale_pending_reservations_are_reconciled_at_startup_and_on_the_next_reservation` (NULL-created row and aged row reconciled; fresh pending still blocks -- `test_reserved_amount_and_uncertain_charge` unchanged and passing). Extension: `test_model_wait_is_excluded_from_the_question_and_progress_clocks` (1.3 s stubbed model wait with 1 s/1.5 s clocks: excluded -> ok, plain Recovery -> trips), `test_extension_waits_as_long_as_the_backend_advertises_and_names_the_wait_when_it_gives_up` (caps 240 -> 255,000 ms; never-answering plan with a 1.5 s wait -> "No answer from the backend within 2 seconds ... reserved worst case"). contract+core 108 passed; acceptance 15 passed; full suite 369 passed (19 min, no flakes). First live run on 0.10.34 (Grok, 10:00 PM): plan call completed in 95.5 s -- past the old 60 s -- and was then rejected by `planner.py:268` 'empty option label' (spare statement rows; see next entry if built). Live: `/api/capabilities?protocol=4` -> `extension 0.10.34`, `request_wait_seconds 300`; `/api/health` ok; startup log clean (the stale sweep runs inside lifespan, so the 9:13 PM reservation is charged at its reserved amount now -- not readable directly: no SSH key on this machine for `railway ssh`).

**Left undone:** Why Chrome accepted clicks slowly for ~70 s in two runs (5:11 PM, 9:11 PM) is still unknown; every click now logs `input_ms`/`dom_ms`, ask Dylan what was on screen when the "Browser input is slow" line appears. A big question can now legitimately spend up to 5 min thinking before the first click (Dylan accepted the trade; the alternative -- tie the thinking budget to a shorter deadline -- was offered, not chosen). Reading passage on a different page than its questions: nothing carries context across pages; parked by Dylan ("a problem to fix for later"). The fixed 3,000-token answer cap (`call_limits`) does not scale with slot count -- ~30 tasks would truncate; not changed. Everything in the two entries below still stands (plan-time screenshot never scrolls; Khan Academy freeze needs a log; Check-my-work `TARGET_STALE`; Grok spend limit >= 2.11; PR #9; working tree uncommitted since 0.10.18 -- commit/push only when Dylan asks).

**Watch out:** `charged_worst_case` is a real charge against the run cap and the invite allowance (MAX_COST_PER_INVITE=5 on Railway): a timed-out screenshot call costs its full reservation, by design (never under-count). The startup sweep charges EVERY pre-0.10.34 pending row (created NULL) for whichever identity owns it -- correct for the frozen ones, and any identity that was not frozen had no pending rows (`unknown` would have blocked it). `httpx` `timeout=deadline` applies per operation (connect/read/write/pool); the read phase is the one a non-streaming completion spends. Dylan's standing rule (memory `no-unrequested-code-changes`) still applies: diagnose and propose; build only on an explicit go.

## 2026-09-18 - claude - click timing recorded; identification/discovery windows start after the click (0.10.33)

**Did:** Diagnosis of the M3-9 5:11 PM run (0.10.32, no model call, `REPEATED_STATE` at 5:12:44) from the copy log against the code: the first seven clicks were same-second; from 5:11:19 every one of the next 14 clicks (sheet cells, all 12 dropdown cells, the part tab, part 2's cell) was logged ~5 s after the step that asked for it, while observe/inspect between clicks stayed same-second. `click()` has no wait of its own and the only click-specific step is the CDP input dispatch, so the slowness was in the browser/page accepting input -- cause unknown, the log recorded no durations. Consequence: the identification loop (resolveInteractions) and the dropdown-discovery loop (revealSelectionOptions) set `until=Date.now()+LIMITS.ui` BEFORE their click, so a 5 s click spent the whole window; each loop did one click, one look, and quit -> c1_r13 and Net Profit Margin (both `response` cells) never got the identify double-click, 12/12 dropdowns ended OPTION_MISSING (never reached the arrow click that read menus at 2:18 PM), no progress mark for 90 s after c1_r10 (5:11:14 + 90 s = 5:12:44 exactly), guard fired one step before the plan request. The execution-phase loops (enter_value L256, place_points L336, settle L301, waitTask L235) and showPart already start their wait after the input -- which is why execution has worked for Dylan and setup broke. Fix (Dylan: "ok go ahead and build it"): (1) `click()` records `timing:{dom_ms,input_ms}` on every click's details and emits ONE loud event per run when `input_ms>LIMITS.slowInput` (1000 ms): "Browser input is slow: the page took X s to accept this click ..."; (2) the two setup loops restart `until` after each click returns (`let until`), matching the execution loops. Fixtures `sheet_numeric.html` and `dropdown_openers.html` take `?slow=<ms>`: the first mousedown busy-waits that long synchronously (CDP `Input.dispatchMouseEvent` does wait for it -- measured `input_ms>=5000` in the tests). Nothing McGraw-specific in the change. Backend change is the version string only; deployed.

**Verified:** New `tests/test_planner_sheet_entry.py::test_a_slow_first_click_does_not_starve_identification_and_is_reported_once` (`?slow=5200`: run finishes, all three cells typed, first click `input_ms>=5000`, exactly one slow-input event) and `tests/test_planner_openers.py::test_a_slow_click_does_not_starve_dropdown_discovery` (`mode=overlay&slow=5200`: choices read before planning, no OPTION_MISSING, one slow-input event). Both FAIL with the two `until` restarts removed (needs_review / OPTION_MISSING) and pass with them. sheet_entry + openers 13 passed; contract + parts + acceptance 64 passed; full suite 363 passed (16.5 min, no flakes). Live: `/api/capabilities?protocol=4` reports `extension 0.10.33`, `/api/health` ok.

**Left undone:** WHY the clicks were slow at 5:11:19 is not known -- the next slow run's log will say `input_ms` vs `dom_ms` per click and the loud line; ask Dylan what was on screen (tab hidden/occluded, window switch, DevTools/debugger bar) when it happens again. If clicks stay ~5 s on a 20-slot question, setup takes 2-3 min and `LIMITS.question` (300 s) is the next wall -- not changed. Everything in the 09-16/17 entry's Left undone still stands (plan-time screenshot never scrolls the answer area into view; Khan Academy freeze needs a log; Check-my-work `TARGET_STALE`; Grok spend limit >= 2.11; PR #9; working tree uncommitted since 0.10.18 -- commit/push only when Dylan asks). Two pre-existing `SyntaxWarning: invalid escape sequence '\d'` in test_planner_sheet_entry.py (0.10.32 tests, non-raw strings) -- harmless, not touched.

**Watch out:** Dylan's standing rule (memory `no-unrequested-code-changes`): a pasted log or a question is a QUESTION -- diagnose and propose; change code, bump or deploy only on an explicit go, one go = one fix. The `slow_input_reported` flag lives on `this.ledger` (once per run, not per question); every click still carries its own `timing`. The `?slow` busy-wait blocks the page's main thread, so observe() during it also waits -- sequential, fine, but keep `slow` well under `LIMITS.request`.

## 2026-09-16/17 - claude - model selection, question stem from all frames, computed answers as inputs, caret-free captures, model actually logged, thinking on, numeric sheet entry, multi-part questions, Grok pricing shapes, sheet memory by slot key, dropdown opening ladder, one spelling for a cell's name, thinking truncation ladder + locked cells (0.10.19-0.10.32)

**Did:** 0.10.19: model dropdown in the side panel (Backend default / minimax-m3 / qwen3-vl-235b / glm-4.6v / grok-4.6 / kimi-k3) and an `ALLOWED_MODELS` allowlist in `app.py` `models()`; anything outside it is refused with "Select an allowed model with image input". 0.10.20: deploy bundle broke (see Watch out). 0.10.21: `planner_runtime.js` built `observation.question` only from slot-bearing frames, so on McGraw M1-14 the parent-page instruction ("Required: ... solve for the missing amounts") never reached the model and it guessed the task; `question` now joins the stem of every readable frame (deduped, 60k cap). Prompt tripwire: answer slots with no task statement anywhere -> needs_review "no task statement found". 0.10.22: after the stem fix, Grok stated the right formula (Total Assets = Liabilities + Common Stock + RE End) but entered L + CS for all three companies -- RE End is an answer cell, blank in the observed table, and the model sourced the input from the page instead of the 43/25/260 it had computed in the same plan. `PLANNER_PROMPT` (planner.py ~L190) now says: use the value you computed in this plan as the input, the blank cell is not an input, declare depends_on. Two sentences; no chain-reasoning section. No commit/push.

0.10.24: two Copy logs Dylan compared as "MiniMax vs Grok" both printed `model: ""`. That field was `body.model` -- what the extension SENT -- and the backend falls back to `OPENROUTER_MODEL` (= minimax/minimax-m3 on Railway) when it is empty, so both runs were MiniMax; the near-identical cost was the same model twice, not Grok being token-efficient (Grok's list output price alone, 379 x $6/M = $0.0023, exceeds the whole $0.0012 run). Cause: the side panel persisted the model only on the Save button while advance/auto_submit/check_work save on change. Fixed: model saves on change with a banner; PLAN/VERIFY/INSPECT events now log `model` from the backend's record (`data.model`, the model it ran), plus `provider` and `requested_model`; the Copy-log header prints the model line. Found (now built in 0.10.25): the backend never sent OpenRouter's `reasoning` parameter; MiniMax's 9-answer plan used 518 output tokens (~the JSON alone), i.e. no thinking, and its three Total Assets entries each dropped one of three terms (40+7, 17+25, 360+110). Grok 4.6 reasons regardless; Qwen3-VL *Instruct* cannot. Proposed: `reasoning:{effort:'medium',exclude:true}` for models whose supported_parameters include `reasoning`, with max_tokens raised.

0.10.25 (Dylan: "turn reasoning on for minimax"): `planner.reasoning_request(entry, setting PLANNER_REASONING='medium')` builds OpenRouter's `reasoning` object from the registry's per-model metadata (now kept by `models()`): optional reasoning (MiniMax M3: `mandatory:false`, default off) -> `{max_tokens: REASONING_TOKENS=6000, exclude:true}`; mandatory (Grok 4.6: `mandatory:true, default high`) -> `{exclude:true}` only, so Grok keeps its own effort. Reasoning tokens count against max_tokens (OpenRouter docs), so every reasoning call gets +6000 max_tokens and the reservation covers it. MEASURED, not assumed: with ANY response_format (json_schema or json_object) MiniMax M3 produced 0 reasoning tokens on Together and CoreWeave; without response_format it thought (39-90 tokens on a 3-term sum); Grok kept thinking under json_schema (238). Hence `planner.thinking_replaces_schema`: optional-reasoning models get prompt-JSON (no response_format, `output_format:'prompt_json'` in the log); `unwrap_fence` accepts exactly one whole-reply ```json fence (MiniMax fenced once live); the prompt says no fences. `agent.planner_complete` records `reasoning_tokens` from `usage.completion_tokens_details`; the panel tokens line reads `5212 in / 968 out (466 thinking)`. Live probe of the real PLANNER_PROMPT on the rebuilt M1-14 observation, text only, two runs: 9/9 correct both times (90/82/730), 466 and 656 thinking tokens, ~$0.002 each; before this the same model with thinking off dropped a term in 1-3 of 3 Total Assets cells across three runs.

0.10.26 (E1-9 income statement, 6:28 PM log, MiniMax with thinking): plan correct ($139,000/$91,300/$47,700, 195 thinking tokens), every click hit its cell id, executor auto-scrolled 442px -- and the run still died on Operating Expenses. Two harness bugs: (A) `matches` compared the readback "91,300" as a string to the planned "$91,300" (the styleNumber row displays "$139,000" so t1 matched by luck) -> VALUE_MISMATCH on a correct, present answer; (B) the retry's Ctrl+A did not clear the live jSheet editor, insertText appended ("91300"+"91300" -> "9,130,091,300"), and Tab committed it blind; the next retry compounded. Fixes in `planner_runtime.js`: `numeric/sameValue/plainDigits` -- enter_value verification compares amounts numerically when both sides parse (currency, thousands separators, whitespace, parentheses-negative, %), exact text otherwise; number fields (`input[type=number]`, inputmode numeric/decimal, jSheet `isN`) get digits only; after Ctrl+A the editor is measured (`measure_target` now returns `selection` and `inputmode`), and if the text is not selected it is deleted key by key (End + Backspace x len, capped at 200) before typing; the editor is measured again before commit and on mismatch Escape cancels the edit and INPUT_NO_EFFECT names typed vs editor -- nothing is committed; the confirming screenshot asks about what the page SHOWS (`s.current`) for value slots, not the model's spelling. LOCAL_RECOVERY rows now carry the fault message and data (previously only the code, so the reason was lost). New fixture `sheet_numeric.html` behaves like the live widget (swallows select-all, formats on commit, Escape cancels, records raw commits); `tests/test_planner_sheet_entry.py` (4) covers all of it. NOT the cause, checked: scrolling (executor scrolled and hit), the question text (all figures were in the payload), the plan, the screenshot.

0.10.27 (multi-part questions; E1-9's Balance Sheet tab was never touched): before this, 'question' meant 'the answer controls visible at the first observe' -- `shown()` (planner_content.js:13) drops hidden tab panels from slots, tables and text, nothing knew what a tab was, and `finished` fired when the observed slots verified. Built from the E1-9 log + the ARIA tab standard + the model's reading of the wording, nothing else: (1) `planner_content.js` discovers the tab strip inside the question root (`role=tab`, `aria-selected`, `aria-controls`; forbidden/navigation labels never count), reports `parts`, tags each slot with `part_id`, and keeps identity stable across tabs by leaving tab-panel contents out of the identity stem and structure (the question TEXT still includes the visible panel); (2) `planner_runtime.js` `revealParts` clicks each tab (what a student does), prepares each part while visible (unresolved widgets, dropdown choices), merges slots/tables/text into one observation (`added()` keeps only what each part adds, cut at sentence boundaries) -> ONE paid plan across parts; `showPart` switches to a slot's part before acting, reconciling, or confirming by screenshot; (3) the plan carries `parts_declared` (how many parts the WORDING names, default 1; prompt guidance + schema) and finish requires parts revealed >= parts declared, else `PART_UNREACHABLE` needs_review; (4) after finishing, every part is re-observed: controls that appeared after the answers are planned in a further round (`LIMITS.plan_rounds=2`, one extra paid plan covering only the new slots) or `NEW_PART_APPEARED` stops the run when the budget is spent. Nothing hidden is read; slots come only from observed controls. New fixture `tabs_parts.html` (ARIA tabs; `?lazy=1` builds part 2's controls on click; `?sequential=1` adds a control after part 1 is filled); `tests/test_planner_parts.py` (5): parts observed + identity stable with and without a platform id, both parts filled in one plan, lazy panel revealed, PART_UNREACHABLE on a tab-less page with parts_declared=2, late control planned in round 2. UNVERIFIED on the live page: whether McGraw's tab strip carries ARIA roles (the console snippet Dylan was asked to run). If it does not, the run now logs `parts: []`, the model declares 2, and the harness stops with PART_UNREACHABLE instead of finishing at 3 of 10 -- the next log then shows the markup to add.

0.10.28 (first live multi-part run, Grok, 8:36 PM): McGraw's tabs DO carry `role=tab` (`<li id=tab-2 role=tab class="tab last-tab">`), so the reveal worked live -- Balance Sheet clicked, its cells identified, the merged observation carried `parts` and 7 slots. Two bugs surfaced. (1) BUDGET_EXHAUSTED before the plan call: Grok 4.6's OpenRouter pricing dict has `web_search: 0.005` and `overrides: [{min_prompt_tokens: 200000, prompt: 4e-6, completion: 12e-6, ...}]`; the guard at app.py (any key outside prompt/completion/request/cache/internal_reasoning with a positive value -> refuse) tripped on web_search, and float(list) on overrides raised TypeError -> same message. Now `planner.reservation_prices(pricing, bound)` takes the tier whose min_prompt_tokens the reserved bound reaches (the image bound = full context = 500k crosses Grok's 200k tier, so $4/M in, $12/M out are reserved: $2.11 for one plan call with a screenshot) and `planner.unknown_charges` names any genuinely unknown positive component; web_search is known (this backend never enables the web plugin). CONSEQUENCE: Grok + screenshot needs a run spend limit >= $2.11 -- at the default 2.0 the run cap refuses, now with the numbers and the remedy in the message (store.py). MAX_COST_PER_INVITE on Railway is 5. (2) The live log showed the Balance Sheet's Cash and Accounts Receivable cells were silently lost: each tab's jSheet numbers cells 0_table0_cell_c1_rN, so Cash (part 2, r4) had the same slot key as Operating Expenses (part 1, r4) and the merge deduped it; the resolver also waited 5 s twice on those keys because part 1 had spent their identification budget. Slot keys now carry the part (`question_key/<part>/id:...`, also for choice groups and menu owners), merged tables are keyed per part and tagged `part_id` (SourceTable.part_id), and `tabs_parts.html?dupids=1` reproduces the collision with a test proving all five cells survive and land in their own tabs.

0.10.29 (Dylan: "fix the sticky note thing"): first full multi-part plans came back from Qwen and Grok (9 tasks across both tabs, parts_declared 2, distinct `tab-1/` `tab-2/` keys), then `GUARD_REJECTED: Control type changed` at 'Entering 1 of 9' on both. Cause: `planner_content.js` remembered a confirmed sheet cell in a WeakSet OF DOM NODES (`confirmedSheetValues`, Codex 0.10.15/16). The parts flow identifies tab 1, visits tab 2, returns; McGraw rebuilds the sheet on return, the remembered nodes are gone, every cell reads `unresolved` again and the executor refuses to type. Latent in existing code; the tab round-trip was the first sequence to trip it (anything re-rendering the sheet between identification and typing would). Fix: the memory is a Set of SLOT KEYS (question/part/cell id); `interaction()` takes the key. Fixture `tabs_sheet.html` (two jSheet-like parts in ARIA tabs, duplicate cell ids, sheet rebuilt on every tab show) reproduces the live failure verbatim with the old memory and passes with the new; asserts the node really was replaced and all six cells committed in their own tabs. Not verified live yet.

0.10.30 (Dylan: "build it"; M3-2 9:19 PM log): the parts flow ran clean on a two-tab question with 12 slots and a correct MiniMax plan (720 thinking tokens), then task 1 -- the statement's TITLE-ROW date dropdown (`0_table0_cell_c0_r2`, no row/column label) -- died `WRONG_MENU_OWNER` twice -> REPEATED_STATE. Cause (old code, Codex 0.10.13-0.10.16, `planner_content.js openingControls`): a detached arrow button with no ARIA link was accepted ONLY with `unique_slot_label_and_overlay_geometry`, i.e. button aria-label == exactly one cell's label; an unlabelled cell can never satisfy it, so the button next to it was invisible to the harness. Inevitable, not new: M2-1 passed this morning only because its cells were labelled; McGraw puts a date-line dropdown on most statement exercises. Built the broad version -- an OPENING LADDER in `planner_runtime.js` set_selection: (1) explicit trigger / activate cell (unchanged), (2) `overlay_geometry` trigger: a button whose center lies inside the activated cell's box and inside no other cell's (new evidence in `openingControls`, ranked BELOW explicit; `geometry_only` flag), (3) click the cell's own `[role=combobox]` (`slot.combobox`, new), (4) keyboard `ArrowDown` then `Alt+ArrowDown` on the focused field (ARIA combobox pattern). After every rung the same proof: a visible menu OWNED by this cell (existing `owner()` evidence); no rung chooses an option; failure names every rung tried. Fixture `dropdown_openers.html?mode=overlay|click|keyboard|stray` (one unlabelled cell, four opener shapes; `stray` puts the arrow outside the cell box); `tests/test_planner_openers.py` (5): each rung reached, choose_option only after a proven-open menu, stray button never clicked and the stop lists the rungs, labelled cells still resolve non-geometry. Pre-ladder code fails the overlay fixture exactly as live (REPEATED_STATE). Dropdown-heavy suites (executor 20 dropdowns, interactions, acceptance, offscreen, inspection mapping) 98 passed unchanged. Not yet verified live.

0.10.31 (M3-2 1:38 PM log, Dylan: "make the fix"): the ladder WORKED live -- `open_menu_by_geometry` found the unlabelled 'Show All Items' arrow (`evidence: overlay_geometry`) and the menu opened -- then `WRONG_MENU_OWNER: Dropdown owner changed before input.` MY bug from 0.10.28: the click-time owner re-check (`planner_content.js` measure_target, `expected_menu_owner`) rebuilt the owning cell's name by hand as `question_key/id:...` while every slot and menu-owner key had carried the PART since 0.10.28 (`question_key/tab-1/id:...`); same cell, two spellings, never equal. Untested because every dropdown test ran on a single-part page where both spellings coincide; this was the first dropdown executed inside a multi-part question. Fix: the re-check reads the owning cell's RECORDED slot key (one source of truth; grep shows no other hand-built key remains) and reports expected vs actual; `fail()` now carries `data` and `requireOK` passes it into the Fault so the log shows both keys. `tabs_sheet.html?dateline=1` adds an unlabelled title-row date dropdown to each part (hidden menu created on activation, overlay arrow reveals it -- as live); test proves all 8 controls (2 dropdowns + 6 amounts) land in their own tabs, and the old comparison fails the fixture exactly as live (REPEATED_STATE). Fixture gotcha: ids starting with a digit are invalid in `#id` selectors -- use `[id="..."]`. parts/openers/executor/interactions 78 passed. Not yet verified live.

0.10.32 (M3-9 2:19 PM log, Dylan: "do the solution you see most fit" -> both): (1) TRUNCATION BY THINKING: 6522 in / 9000 out with reasoning_tokens 9000 -- provider Venice ignored `reasoning.max_tokens: 6000`, the model thought to the total limit and returned no content; agent.py reported it as `SCHEMA_INVALID: provider did not return text` ($0.0127 for nothing). Now agent.py names it `TRUNCATED_BY_THINKING: reply cut off -- N of M output tokens went to thinking, none to the answer (provider P)` (finish_reason recorded before raising); `planner.reasoning_budget(observation)` scales the thinking budget with slot count (6000 + 300/slot beyond 5, cap 16000: 20 slots -> 10500) and the reservation follows; `PlanRequest` carries retry hints `avoid_providers` (-> OpenRouter `provider.ignore`) and `reasoning_mode:'off'` (-> no reasoning param, json_schema again); the coordinator's `paid()` ladder on TRUNCATED_BY_THINKING: retry once avoiding that provider, then once with thinking off, then stop named -- three plan calls, the question's existing plan budget. (2) LOCKED CELLS: two amount cells (`responseCell isN` without `response`) stayed `unresolved` after identification -- correct reading, Dylan confirmed they cannot be clicked -- but the rules made the question unplannable (plan had to cover every slot; never an unresolved one). Now an unresolved-after-identification slot is NOT required (runtime validate + backend validate_context; prompt says leave it out), the post-batch rounds re-identify unresolved cells with a fresh action budget (a cell that unlocks after its row is set is planned in the next round), and FINISH names any that stayed locked (`not_answerable`). Fixtures: `sheet_numeric.html?locked=forever|until_revenue`. Tests: contract (truncation named + hints honoured + budget scaling; unresolved not required but still unplannable), acceptance (coordinator ladder: calls carry [] -> avoid Venice -> reasoning off), sheet-entry (locked forever -> finished + named; unlocks -> planned in round 2). 201 across the planner suites. Bug caught by test on the way: a trailing comment swallowed the `push` on the same line. Not yet verified live.

**Verified:** `tests/test_planner_acceptance.py::test_question_stem_in_parent_frame_reaches_the_model` on fixture `stem_parent_iframe.html` (stem in parent `<main>`, answers in iframe) -- old logic dropped the stem, new keeps it. `tests/test_planner_contract.py::test_prompt_names_computed_answers_as_inputs_to_dependent_formulas` locks the 0.10.22 line into PLANNER_PROMPT and REPAIR_PROMPT. Contract + core: 95 passed. 0.10.32 live: `/api/capabilities?protocol=4` reports `extension 0.10.32`, `/api/health` ok. parts/sheet/interactions/offscreen suites 33 passed. Contract 41 passed; parts 6 passed. Contract + core 100 passed; new tests: reasoning policy by metadata, reasoning requested with headroom reserved and tokens reported, schema dropped only for optional-reasoning models (fenced reply accepted end-to-end), whole-reply fence absorbed / fence-plus-prose still rejected, extension log shows thinking count. New test `test_log_records_the_model_the_backend_ran_not_only_the_requested_one`; acceptance + contract 45 passed. Diagnosis of both failures came from the actual plan payload and model `reason` in the Copy log, not from output alone (see the 8:05 PM 0.10.21 log: `depends_on: []` on all nine tasks; 47/57/470 = 40+7, 40+17, 360+110 exactly).

**Left undone:** Scroll gaps Dylan has seen live and that the code confirms: the plan-time screenshot (`planner_runtime.js` paid()) is one viewport wherever the page sits, nothing scrolls the answer area into view first; the confirming screenshot covers only visible slots (by design). On pages where the question and answers are several scrolls down (Khan Academy) the run freezes -- not yet reproduced in a fixture. E1-9's Balance Sheet tab: confirmed live in 0.10.27 that McGraw's tabs expose ARIA roles and the reveal works; 0.10.28 fixes the cell-id collision and the Grok pricing refusal found in that run. Next: one E1-9 or M3-2 run (MiniMax at the default spend limit, or Grok at 5) to see both tabs filled end to end, including the title-row dropdown. Dylan has to reload the extension and rerun M1-14 on Grok to see whether the prompt line takes. If it does not, the structural fix is layered planning: execute tasks with empty depends_on, re-observe (dependent inputs now filled in the DOM), re-plan the remaining slots -- one extra plan call per dependency layer, new phase budget, tests. Not built. Still open: Copy log prints `model: ""` (logs the requested field, not the backend-selected model); `TARGET_STALE: Document was replaced` after "Check my work" re-render. PR #9 (`claude/planner-reasoning-redesign`) at Greptile 3/5 with only the accepted JS-extraction security finding; Dylan has not chosen keep vs narrow.

**Watch out:** Full suite after 0.10.22 was 328 passed / 1 failed: `test_greptile_pr6::test_a_real_same_site_navigation...`, which loads the retired worker from `tests/legacy_extension/` against the shipped `visual.js`. Not a load flake (failed 2/2 in isolation; passes at HEAD 0.9.4). Diagnosed by recording every capture and diffing the mismatching pair: a 1x15 px box -- the blinking TEXT CARET in the focused answer box, not the pointer overlay. The frozen worker's stale-screenshot guard hashes two captures ~330 ms apart; the pointer hide/restore round trips shifted timing into the other blink phase. First attempt (archiving HEAD's visual.js beside the retired worker) broke 6 planner tests in non-`test_planner*` modules (`resolveSlot is not defined`) because the fixture overlays legacy js by module-name prefix -- reverted. Fix (0.10.23, shipped `visual.js`): the injected `cursor()` also sets `caret-color: transparent` on the document root for `hide` and restores it on `restore` and `remove` (so a detach never leaves the student caret-less). No paint wait needed: 5/5 back-to-back captures hash equal without it. New test `test_capture_hides_the_caret_and_puts_it_back` (uses `navigates.html`; `planner_standard.html` has a 25 ms `Date.now()` ticker so it can never hash equal). 0.10.20 outage: `rm -rf deploy-source` half-deleted and errored "busy"; `cp frontend/* ... 2>/dev/null` hid that `frontend/` and `railway.json` never landed; `StaticFiles` raised `Directory '/app/frontend' does not exist`, healthcheck failed, live 502 for ~15 min. Refresh the bundle file-by-file with no error suppression, `diff -rq` it against the source, and run `python -c "import asyncio,app; asyncio.run(app.capabilities(4))"` inside `deploy-source/` before `railway up`. Prompt lines are suggestions (AGENTS.md); the harness cannot check the arithmetic because it has no answer key, so the only proof of 0.10.22 is the rerun log.

## 2026-09-16 - codex - preserve table source structure (0.10.18)

**Did:** User authorized table extraction improvements only after a wrong numeric plan. Added a supplemental tables snapshot containing zero-based row/column positions, literal text, TH/scope metadata, row/column spans (including rowspan=0 and row-group clamping), captions, DOM IDs and frame IDs. Keep blanks in position, omit hidden cells without shifting later columns, skip presentation tables/nested layout wrappers and keep answer cells empty/marked rather than mixing current answers into givens. Existing question text, screenshots, slot identities and action execution remain the same. Added typed backend models and prompt guidance, including that TD cells may be labels. Table context flows through normal planning and Copy log. Bounded extraction flags incomplete results. Version 0.10.18. No additional model calls or academic correctness review; table questions add input tokens. No commit/push/merge.

**Verified:** Four new actual-extension tests cover the supplied financial table in top page and iframe, source values through backend schema/request text/copy log, stable identities after typing, merged headers, rowspan=0 and overlong spans, blank/hidden columns, nested presentation wrappers, offscreen content, truncation and unchanged non-table slots. New suite + backend contracts: 37 passed. Existing executor/interaction/acceptance regression batch: 73 passed, including 20 dropdowns and spreadsheet typing. Final merged-header case and all 33 backend contracts rerun after review adjustments, passed. Syntax and whitespace checks passed. High-level review traced reader -> frame aggregation -> public observation -> schema -> planner input -> log and confirmed no new action pathway. No paid model calls or live coursework mutations.

**Left undone:** Backend deployment ed5b37a6-9615-4d1c-957b-290090458a53 reached SUCCESS; live capabilities report 0.10.18/protocol 4 and /api/health reports ok. User must reload extension and refresh the page. Improved input structure does not establish academic correctness; no live model comparison was performed. Cross-frame question context, section-tab discovery and Next navigation guard behavior remain separate.

**Watch out:** Per-frame limits are six tables, 300 cells, 12,000 cell-text characters; individual tables 200 rows/256 columns, cells 1,000 text characters. Runtime limits twelve tables/60,000 serialized characters and exposes table_context_complete. Backend observation-size/spend checks remain. Only HTML tables in the existing chosen question frames are added; this does not extract graphs or hidden tabs. Existing dirty-tree work is prior authorized work. Generated allowlisted deployment source: deploy-source/table-context-0.10.18 (19 application files, no credentials/data).

## 2026-09-16 - codex - scroll offscreen answer fields (0.10.17)

**Did:** User authorized only offscreen answer-field handling. Extended packaged scroll/clipping measurement to all targets and the document viewport. Hidden/display-none/aria-hidden controls stay excluded; offscreen rendered controls remain discoverable. The executor reveals enclosing frames from the outer page inward, uses actual wheel input in the appropriate page/container, verifies scroll offsets changed, refreshes frame offsets and target geometry, then performs the final activation/hit test. This fixes activation checks occurring before a containing page/frame is visible and stale cross-origin offsets after page scrolling. Wheel locations avoid unrelated scrolling widgets, iframes and fixed/sticky overlays. No movement, overlays, disappearance, replacement, Stop and the 12-scroll ceiling stop input. Added page/container scroll details to the log and typed frame-message failures. No added provider calls. Version 0.10.17; backend version metadata synchronized. No commit/push/merge.

**Verified:** New offscreen + existing interaction tests: 21 passed. Existing executor/mapping/acceptance regression batch: 71 passed, including all 20 dropdowns, menu scrollbars, graphs and mixed spreadsheet inputs. Additional cross-origin visible/offscreen, scroll-budget, backend contract/core batch: 97 passed. New tests use the actual extension and CDP wheels to cover scrolling down/up/horizontally, iframe below the fold, scrolling inside an iframe, ordinary scroll containers, hidden fields, blocked wheels, overlays, Stop, document reload and spreadsheet double-click/type/readback after a 2400px page scroll. Fixed the synthetic spreadsheet fixture's absolute editor coordinates to account for document scrolling. Syntax and whitespace checks passed; no paid model calls or live coursework entries.

**Left undone:** Full-question text/context collection, reference graph handling and answer-tab enumeration are intentionally separate from this authorization. Thus this update alone does not establish complete/correct handling of the two-statement question. Reload extension and refresh the assignment page to replace the already-injected inspector. Railway deployment 6be471b8-0879-4d4d-98d7-671a49e721eb reached SUCCESS; live capabilities report 0.10.17/protocol 4 and /api/health reports ok.

**Watch out:** Measure now refreshes observations and updates the caller's frame object so downstream focus/ownership checks use current observation IDs. Page scrolling can move an iframe without changing child-local target coordinates, so retain fresh outer-frame geometry. Do not treat a failed wheel or empty option list as evidence that the widget is hidden or has a different input type. Existing working-tree edits are prior authorized work; original checkout's unrelated rebase remains untouched.

## 2026-09-16 - codex - evidence-based interaction classification (0.10.16)

**Did:** Removed the assumption that every focusable response cell is a dropdown. Generic answer cells are unresolved until positive control evidence establishes an interaction type. Added bounded activation and a packaged jQuerySheet adapter: identify the sheet/table/formula control, double-click to reveal its detached editor, associate a unique visible textarea with the active cell and geometry, preserve the cell slot, and cancel discovery without entering answers. Execution reopens the editor, checks ownership/focus before input, types through CDP, commits with Tab and verifies the original cell. Contained numeric/textarea values read back from their editor. Native controls and existing dropdown discovery retain their paths. Classification allowances persist on resume; confirmed-editor evidence clears when question identity changes. Empty options never imply text input. Planner schema/prompt, execution/verification type guards and backend capability gating now support unresolved slots. Version bumped together to 0.10.16; log includes classification evidence. No commit/push/merge.

**Verified:** Live read-only DOM confirmed the actual table.jSheet / .jSheetParent / textarea.jSheetControls_formula association; earlier user-authorized activation had established the floating .jSheetInPlaceEdit behavior. Nine new real-extension/CDP tests cover a nine-cell sheet mixed with dropdown/native fields (top page and iframe), delayed editor/menu creation, unknown cells, duplicate/wrong-owner editors, Stop, fresh classification after question reuse and cancellation/resume without replay. Existing executor + mapping suites: 63 passed; backend contract/core/acceptance: 102 passed; final new suite plus standard input and 20-dropdown regression rerun: 11 passed. No provider calls. node --check passed; diff whitespace check passed. Backend deployment eeecc5ab-99d2-4423-9bde-d332e49d729c reached SUCCESS; live capabilities report 0.10.16/protocol 4/interaction_classification and /api/health reports ok. No paid live run was made.

**Left undone:** A live answer-entry smoke test on the user's actual worksheet was not performed; local executable fixtures validate interaction mechanics, not academic answer accuracy. Unknown widget libraries may need additional evidence-based adapters; this is not universal format recognition. Reload the unpacked extension and refresh the assignment page for the new inspector.

**Watch out:** The floating textarea is outside the TD under jaws-div. Single click only selects the cell and can focus the tiny aria-hidden formula control; it does not expose the editable overlay. The live root has id jQuerySheet, class jSheetParent (not class jQuerySheet). Do not use lack of options as a text classification rule or restore all-response-cell dropdown classification. Existing accumulated working-tree changes are authorized previous work; original checkout still has an unrelated rebase. Deploy source remains ignored/generated.

## 2026-09-16 - codex - frame-scoped slot inspection and inactive dropdown discovery (0.10.15)

**Did:** Live read-only inspection of the 20-cell McGraw table confirmed zero select/listbox/option/arrow nodes before activation, so corrected mapping alone cannot recover those choices. Added trusted element bindings and resolveSlot(slot_key) for model scripts, correct question-frame CDP isolated-world routing, document checks before/after inspection, cancellation checks, and frame/document evidence. Public slots now expose frame_id/dom_id; backend prompt explicitly distinguishes opaque slot keys from HTML IDs. Added frame_scoped_inspection capability gating. Existing DOM inspection stays first; missing choices permit one durable cell activation and one menu opening per slot, with no answer selection. Cache choices per slot/document across shared-editor destruction, close known menus, preserve existing answers and reconcile before planning. Cell activation hit-tests a point outside text editors/buttons instead of blindly clicking the center. No column-wide option borrowing. Updated fixtures to support Escape dismissal, isolated read-only/guard tests from the new preflight, and added initially inactive 20-slot iframe and mapping regressions.

**Verified:** New eight-case mapping suite passed: all 20 initially inactive iframe cells get independent options and complete from one scripted plan, targeted/broad inspection stays in the child frame despite duplicate top-page IDs, idless/open-shadow targets resolve, stale/cancelled inspection is refused, and failed activation is not replayed on resume. Broad mapping/executor/contract run: 92 passed, two failures identified; one obsolete expected inspection result updated, one genuine editor-center click fixed. Final focused 14-case run passed including both failures and all scrolling variants; four additional standard/20-slot/reused-menu-below-fold/overlay tests passed after the activation-point fix. Backend contract suite 32 passed; core/acceptance suites 69 passed. Syntax and diff checks passed. Reviewed observation -> fresh binding -> frame/document mapping -> bounded discovery -> plan -> fresh activation target -> exact option -> readback. Railway deployment 9f87bca2-02d5-4b18-a551-89d00f7da814 SUCCESS; public capabilities confirm 0.10.15 and frame_scoped_inspection. No live coursework mutations or paid model calls.

**Left undone:** User live smoke test requires reloading local extension 0.10.15 and refreshing the assignment page. No commit, push or merge. Prior instruction-extraction/academic-answer-quality limitations remain outside this fix; deterministic fixture success is not a claim of live graded correctness.

**Watch out:** This explicitly supersedes 0.10.11's discovery-click prohibition under the user's approved necessary-fixes proposal. Discovery scripts themselves remain read-only; only the coordinator can activate/open, with logged purpose and durable limits. Ambiguous iframe URLs, unowned menus, unsupported dismissal and missing choices still stop explicitly. A pre-opened iframe menu may need its positively associated opener focused before Escape can dismiss it. Model-authored JavaScript retains the existing best-effort denylist and bounded output; isolated-world routing is not a claim of an arbitrary-code read-only security sandbox. Staging deploy-source remains generated/ignored.

## 2026-09-15 - codex - reveal clipped dropdown options before clicking (0.10.14)

**Did:** Added read-only overflow/clipping and scroll-position inspection, plus option visibility and menu scroll metadata to option discovery. Before clicking a clipped option, executor targets the associated container with real browser wheel input, confirms scrollTop/scrollLeft changed with bounded polling, then re-measures and hit-tests before clicking. Checks fresh menu ownership during measurement/polling. Visible-overflow worksheet wrappers are not mistaken for clipping containers. Live read-only DOM inspection found McGraw uses a sibling NiceScroll rail with overflow:hidden; added a scoped NiceScroll wheel adapter requiring that visible rail and a unique listbox. Unrelated hidden-overflow containers are not assumed scrollable. Real overlays still stop input; wheel no-effect and cancellation stop without clicking. Expandable scroll details and Copy log show option, container, coordinates, delta and before/after scroll state.
**Verified:** Full executor suite passed (53 cases at collection), then all four native/custom-scrollbar x top-level/iframe combinations passed after final metadata changes (two additional custom-scrollbar cases). Six-row fixture starts with first answer already entered and second menu open, then completes the other five with one plan and no page scrolling. Upward scrolling, blocked wheel, overlay and Stop tested; clipboard export covered. Initial four test-helper failures were corrected by initializing the required Recovery object, then passed in the full suite. Syntax/diff checks pass. Reviewed inspection -> clipping classification -> owned-container wheel -> movement evidence -> fresh hit-test -> click -> answer verification. No live coursework mutations or paid model calls.
**Left undone:** User live smoke run requires reload 0.10.14 and refresh assignment page. No backend change/deploy, commit or merge. Answer-planning/instruction extraction limitations from prior handoff remain outside this scrolling change.
**Watch out:** Discovery stays read-only; actual scrolling happens only during planned answer execution. Custom scrollbar support is based on observed NiceScroll DOM and confirmed scroll-position movement, not assumptions about every overflow:hidden widget. Missing/blocked/unresponsive scroll containers remain explicit failures. No arbitrary JavaScript scroll mutation or removal of overlay protection.

## 2026-09-15 - codex - inspect and resolve dropdown opening controls (0.10.13)

**Did:** Read-only live inspection confirmed McGraw's Show All Items input.dropdownButton is outside the TD, under scrollPane, with no own aria-controls; its unique aria-label matches the active cell and its center overlays that cell. Added shared packaged openingControls discovery used by both observe and inspect_options. Returns registered targets, labels/title/type, geometry, disabled state, ownership evidence and resolved/missing/ambiguous status alongside answer options. Supports contained openers, explicit slot/menu linkage, and detached unique-label plus overlay-geometry association. Excludes text editors; multiple candidates stop rather than picking the first. Executor re-resolves on each observation and logs ownership in click details. Model-requested option inspection now returns options plus opening_control; preflight and Copy log show control evidence, with an expandable panel entry. Transient child dropdown editors and input buttons no longer change the fallback question fingerprint.
**Verified:** 19 loaded-extension browser tests and 31 backend contract tests passed. New two-row fixture reproduces detached shared arrow and separate editor without a platform question ID: first click opens the existing arrow; next row activation reveals/rebinds it without TARGET_STALE or text-editor focus. Wrong label/geometry, ambiguous and disabled buttons checked. Existing six/twenty-dropdown workflows, reused menus below fold, delayed triggers, missing options, standard inputs, question/document replacement, overlay guards and clipboard output pass. Live read-only geometry confirmed the association criteria; no live clicks/entries/submission or provider calls. Reviewed observation -> registered target -> inspection evidence -> fresh resolution -> hit-test -> browser input -> readback; syntax/diff checks passed.
**Left undone:** User must reload 0.10.13 and refresh the page for a live execution smoke test. Separate model outflow-parentheses mistake and incomplete outer-frame instructions were not changed by this target-discovery update. No backend change/deploy, commit or merge; existing protocol 4 evidence envelope accepts the richer inspection result.
**Watch out:** Missing triggers may still require answer-phase cell activation before a trigger exists. Discovery itself remains read-only. Do not associate buttons by proximity alone, copy another row's choices, or retain an old arrow association after it moves. The TARGET_STALE change addresses transient dropdown controls, not every possible question/document identity change.

## 2026-09-15 - codex - expandable browser click diagnostics (0.10.12)

**Did:** Every Browser click executed entry now expands in the side panel and exports its details through Copy log. Records the executor's purpose/reason separately from the model's supplied plan explanation, task/slot identity, desired answer, pre-click state, resolved target metadata, hit-tested element, CSS viewport coordinates and target bounds. Custom option clicks include exact matching rule, menu owner and bounded candidate list. Covers cell activation, trigger opening, option selection, checking/unchecking, text/native-select focus and navigation/check/submit. Repair explanations follow the repaired task. Reuses existing pre-click measurements; no extra paid calls or changes to target selection/discovery behavior.
**Verified:** Three loaded-extension browser tests passed: radio/checkbox/text execution and click-state evidence; six-row collapsed-menu discovery followed by entry with correct option/target/hit evidence; expandable panel details and clipboard export, including literal rendering of HTML-looking target text. Existing single-plan and zero-discovery-click assertions pass. Reviewed observer measurement -> executor context -> durable event -> panel/clipboard flow; JS syntax and diff checks pass.
**Left undone:** Live wrong-choice diagnosis awaits a new user log. This release adds evidence, not a claimed fix for that unknown cause. No backend change/deployment, paid model call, commit or merge.
**Watch out:** Reload extension 0.10.12 and refresh the assignment tab. Browser input completion is explicitly marked not yet verified; subsequent verification remains separate. Backend 0.10.11 is protocol-compatible. The plan explanation is model-provided; per-click reasons describe deterministic executor decisions, not private model reasoning.

## 2026-09-15 - codex - read-only dropdown discovery (0.10.11)

**Did:** On explicit user request, replaced automatic menu-opening discovery with packaged JavaScript reads of existing native, nested-select and associated collapsed listbox option nodes. No click/key/focus or popup dismissal in discovery, including model-requested inspect_options. Unknown/ambiguous choices return empty evidence and a named source; model may request bounded read-only scripts or needs_review using DOM + screenshot. Answer-plan execution still uses browser clicks. Updated backend planner/repair instructions to match, and copied logs include inspection_source and actual options. Kept password-block removal and 0.10.8 rollback. No question-identity rewrite.
**Verified:** 81 planner executor/acceptance/backend contract checks passed; four ownership/disabled-option checks repeated after tightening nested-menu ownership. Six-row hidden-menu fixture supplies exact distinct choices before planning with zero clicks/entries, then completes answer entry. Dynamic menus absent from DOM stay unknown with zero discovery clicks; Stop/resume, foreign/ambiguous owners, disabled options, twenty-slot executor, native choices and existing JS inspection tested. Reviewed inspection -> owner evidence -> cache -> model prompt -> answer execution; syntax/diff checks pass.
**Left undone:** Actual McGraw dropdown smoke remains user-side; if it creates choices only after activation, this deliberately read-only mode may need review. No paid model call, commit or merge. Railway deployment b4670814-8ee5-49b4-b45d-658793fdadb2 reached SUCCESS; live capabilities confirmed protocol 4 / 0.10.11.
**Watch out:** Reload 0.10.11 and refresh the assignment tab. Discovery runs local packaged JS first for known dropdowns; the model receives that evidence + screenshot and can request additional read-only JS. Do not describe every preflight inspection as model-authored. Existing TARGET_STALE checks remain; this change prevents discovery clicks, not every potential identity failure during answer execution.

## 2026-09-15 - codex - remove password-specific field exclusion at user request (0.10.10)

**Did:** Live read-only browser diagnosis confirmed BOTH McGraw fitb inputs are visible, inside the selected main container, and rejected solely because autocomplete is new-password. User explicitly requested removal of the whole password block, rather than the proposed narrow widget exception. Removed password from the sensitive-attribute regex and type=password from the excluded types in the shared safe() check (observation and target inspection). Kept hidden/file, financial/government identifier exclusions, log credential-key redaction and other guards. Removed the inaccurate side-panel promise that password entry is blocked. No root/slot workflow changes.
**Verified:** Four loaded-extension tests passed: text and password-type inputs with password names/labels and new-password autocomplete register and accept dummy text through real browser input; credit-card exclusion/frames and log redaction remain tested. JS syntax/diff checks passed. No live coursework entries or submissions, no provider calls.
**Left undone:** User must reload 0.10.10 and refresh the assignment tab before rerunning; backend unchanged and no deployment/commit/merge performed.
**Watch out:** Real password fields are now eligible for registration/readback and typing; question planning is not a substitute for sensitive-field exclusion. This is the explicit requested behavior, not a narrow fix. Prior 0.10.8 suspected root/table explanation was disproved for the inspected live inputs; do not restore that rollback without separate evidence.

## 2026-09-15 - codex - user-requested rollback of 0.10.8 (0.10.9)

**Did:** Reverted only the 0.10.8 reader changes: restored prior root selection, control selectors/filtering, responseCell classification, nested text-field exclusion/labels and aggregate completeness rule. Removed the corresponding new blank-field fixture/tests. Kept 0.10.7 DOM Copy log and all earlier fixes. Version 0.10.9 identifies the rollback; functional reader behavior is back to 0.10.7.
**Verified:** Four loaded-extension checks passed: standard choices/text, twenty dropdowns, clipboard DOM output and DOM snapshot/redaction. JS syntax and diff checks passed; searched for removed 0.10.8 helpers/fixture references and found none.
**Left undone:** Original missing-slot issue remains unresolved. No new attempted fix, backend change, deployment, commit or merge.
**Watch out:** User reported 0.10.8 broke DOM reading; exact new error was not supplied. Reload extension AND refresh assignment tab to remove the already-injected reader, then start a new run. Earlier 0.10.8 entry below is historical and no longer describes current behavior.

## 2026-09-15 - codex - register rendered fill-in answer fields (0.10.8)

**Did:** Fixed question-root selection so a heading-only main landmark cannot hide a sibling question container. Prefer a populated question scope and fall back to the rendered document when landmarks contain no eligible controls. Register plain text/number/textarea and custom editable text fields; exclude nested editors only when a real dropdown/parent editor already owns the slot. Plain responseCell text fields, including tabindex cells without dropdown evidence, are value slots. Ignore navigation/search/sensitive/hidden fields. Report zero aggregate slots as incomplete; an empty parent frame alone does not invalidate a readable child frame. Existing backend rejects unregistered IDs unchanged.
**Verified:** Nine focused browser checks passed, including five blank layouts (sibling scope, body fallback, table, editable text, open shadow), empty-slot reporting, existing radio/checkbox/text and six/twenty-dropdown workflows. Final full planner executor, acceptance and backend contract suites: 80 passed (no paid model calls). JS syntax and diff checks passed. Reviewed root selection -> slot registration -> stable identity -> browser typing -> value readback and multi-frame aggregation.
**Left undone:** Actual McGraw Hill DOM was not supplied beyond the new extraction log, so the precise live markup still needs a user smoke run. No provider calls, deployment, commit or merge. Extension-only change remains compatible with backend protocol 4 / 0.10.6.
**Watch out:** Reload 0.10.8, refresh the assignment tab (old content scripts persist until navigation), start a new run. The log proves native text inputs exist and were unregistered; it does not itself prove their ancestors. Fixtures reproduce identified reader gaps without asserting they are the exact live DOM. No raw input IDs from scripts are promoted to executable slots by the model.

## 2026-09-15 - codex - DOM evidence in Copy log (0.10.7)

**Did:** Log an immutable serialized copy of the outbound structured DOM observation before each plan, repair, graph measurement and screenshot verification request. Includes question, slot IDs/count, current values/options, completeness and inspection evidence, correlated by request/document/observation IDs. Side panel provides an expandable DOM section; Copy log includes it beside existing explanations, raw responses and actions. Excludes screenshot data, redacts known credential keys/Bearer strings, marks per-snapshot truncation over 64K characters and bounds durable DOM history to 1M characters. Adds frame/target fields to copied actions.
**Verified:** Four loaded-extension tests passed: request-to-log payload equality for planning and verification, rejected-plan diagnostics, actual clipboard output, empty slots/redaction/immutable snapshots/truncation. JS syntax and diff checks passed. Reviewed all three outbound request paths and event -> storage -> panel -> clipboard flow.
**Left undone:** No live provider calls, deployment, commit or merge needed/performed. This is extension-only diagnostic output; protocol and backend request shape remain unchanged and compatible with backend 0.10.6. Actual missing-input discovery is not fixed by this change.
**Watch out:** Reload extension 0.10.7, refresh the assignment tab and start a new run; prior logs cannot retroactively include DOM snapshots. This logs the structured DOM actually sent to the model, not full-page HTML or private model reasoning. Long logs explicitly mark omitted snapshots; existing event count limits still apply.

## 2026-09-15 - codex - deterministic dropdown option discovery (0.10.6)

**Did:** Before the first plan, locally open known selection slots whose options are missing; read each owned menu, preserve exact labels/disabled state under that question/document/slot, and dismiss without entering an answer. publicObservation now supplies observed custom-menu choices rather than permanent empty arrays. Prefer fresh visible options over retained evidence; never copy one row's options to another. Existing native/readable choices need no opening. Generic scripts remain optional for other missing information, with the same two-round limit. Script source changes alone no longer count as new inspection evidence. Fixed reused-popup ownership: current explicit owner label wins over stale aria-controls references; a unique expanded owner resolves shared controls. Resume handles a leftover open menu before approaching another row.
**Verified:** Six-row executable cash-flow fixture completed in one planning call, no page scripts, no model-inspection rounds, no entries during discovery; preserves parentheses and distinct per-row option lists. Broad run: 130 checks passed; one delayed-arrow fixture lacked dismissal behavior and was updated to provide Escape, then all six focused cases passed. Seven final Stop/resume, nondismissable popup, twenty-slot, reused-menu and ownership checks passed. Added explicit arrow priority over an adjacent text editor with role=combobox; two final browser checks passed with that exact fixture. Thirty backend contract checks passed, including narrow removal of inert inspection metadata from otherwise valid plans; real requests/scripts remain rejected alongside plans. Reviewed discovery -> ownership -> payload -> exact-label execution -> readback, cancellation and popup occlusion. JS syntax/diff checks passed.
**Live:** First hosted smoke produced all six correct labels but included an inert inspection object ($0.0006456); added explicit inspection:null prompt plus narrow logged normalization for empty target/requests/script only. Final deployment 5dad42c0-54ed-4c39-8e8e-4d67bb341672 SUCCESS. Second real MiniMax M3 smoke passed: six exact labels including parentheses, inspection:null, no further inspection requested, 281 output tokens, $0.00059448. This hosted check uses supplied options; browser discovery is separately exercised by fixtures.
**Left undone:** Actual McGraw Hill page smoke remains user-side. No merge or push performed.
**Watch out:** Reload 0.10.6. Expected log starts Reading choices for N dropdowns, then one Planning answers call. Failure to open/read/dismiss a menu stops with a specific local error rather than spending the model-inspection budget on repeated scripts. scripts/smoke_planner_format.py --cashflow is an explicit paid smoke using supplied choice lists; no coursework page is controlled.

## 2026-09-15 - codex - inspection targeting and one correction (0.10.5)

**Did:** Split known-slot inspection (exact offered ID) from question discovery (empty ID plus inspect_question or a script-only request). Constrain IDs/forms in the provider JSON schema, clarify prompt examples, and return a typed correction marker for invalid inspection references. The coordinator retries that class once with fresh IDs, evidence, a new reserved request and a durable per-question counter; backend inspection_correction phase independently caps it at one. Unknown charges, unrelated errors and Stop do not trigger correction. Rejected scripts never execute. Fixed a regression uncovered by the new test: paid() refreshed live refs before inspectRequest tried to use old ones. Inspections now re-resolve and wait for cell -> arrow -> owned menu; native/choice option reads return actual options. Missing slots on an otherwise readable question may request discovery; final plans still require observed slots.
**Verified:** 122 core, planner contract and loaded-extension tests passed. Tests cover invalid-ID -> corrected inspection -> completed selection, question/script discovery, delayed arrow/options, repeated rejection, resume retaining the limit, server billing/cap and schema ID enums. JS syntax and diff checks passed. Reviewed observation -> schema -> validation -> charged correction -> fresh target -> inspection -> next plan. Railway deployment e46bbd36-8026-42be-8b31-26d32ef6f794 pending terminal confirmation.
**Live verification:** Railway deployment e46bbd36-8026-42be-8b31-26d32ef6f794 reached SUCCESS; live protocol 4 / extension 0.10.5 confirmed. Real MiniMax M3 returned request_inspection with the EXACT supplied dropdown ID, inspect_options and an empty script; 92 output tokens, $0.00026714. Provider accepted the constrained JSON schema. No page script or action ran in this live contract check.
**Left undone:** Actual McGraw Hill worksheet smoke remains user-side; fixture success is not a guarantee for every widget. No merge or push performed.
**Watch out:** Reload extension 0.10.5; backend and extension both changed. JavaScript remains optional/on-demand. A corrected request costs one additional bounded model call; it does not disable target validation or re-run the rejected script. scripts/smoke_planner_format.py --inspection is an explicit paid live contract check, never automatic pytest; it requests evidence but executes no page script or action.

## 2026-09-15 - codex - stable run ownership and visible cursor (0.10.4)

**Did:** Separate planner run authorization (guest/session identity) from the network spending bucket. Pin the allowance on run creation and settle against that bucket. Persist hashed access tokens in SQLite; bearer renewal preserves the proven identity through the 24-hour post-expiry window. The extension sends its prior token when renewing. Restore the green cursor in the shared browser input adapter, hide it for screenshots, remove it on Stop/detach, and guard late cursor updates after cancellation. Preserve GUARD_REJECTED when screenshot verification fails instead of mislabeling it VALUE_MISMATCH.
**Verified:** 92 targeted core/contract/browser checks passed, then 54 complete planner-contract and loaded-extension executor checks passed after final changes. Includes real API plan -> screenshot verify with network change, simulated restart and token renewal (provider mocked); stranger access remains refused before a provider call. Browser checks cover cursor click-through, exclusion from screenshots, cleanup, twenty dropdowns, graph transforms, background tabs and cancellation. Reviewed auth -> reservation -> settlement -> verification/status and mouse -> screenshot -> Stop. JS syntax and diff checks passed.
**Left undone:** Actual McGraw Hill smoke run is still user-side. Railway deployment 3eb36e1d-f2ad-4919-8c6a-9afa5dda0bb7 reached SUCCESS. No merge or push performed.
**Watch out:** Reload extension 0.10.4 and START A NEW RUN. Old network-owned runs cannot safely be reassigned to an arbitrary guest; do not resume the failed pre-update ledger. Session persistence requires the same SQLite data volume; token digests (not bearer plaintext) are stored. This is not removal of run privacy or spending limits.

## 2026-09-15 - codex - enforce planner response shape (0.10.3)

**Did:** Traced raw text from OpenRouter through planner_complete and Copy log; no prefix slicing occurs (only key redaction). Added a complete checkbox plan example. Read live supported_parameters and request strict json_schema where advertised, json_object when only JSON mode is advertised, otherwise retain prompt/validation. Each task operation has its own desired-field schema; no free-form verifier in model task output. Added the single known alias choice_set -> set_choice_set before validation; full context/coverage/desired checks remain. Malformed prefixes still fail rather than being guessed. Format choice and alias corrections appear in Copy log. No new dependencies or auto-paid retries.
**Verified:** 24 contract tests and 2 loaded-extension diagnostic/clipboard tests passed. Real MiniMax M3 smoke: complete JSON, correct set_choice_set, exact question/observation/slot IDs, correct even-number set; 82 output tokens, actual cost $0.0001627. First live smoke exposed desired fields too broad in initial generated schema ($0.00029998); fixed by operation-specific variants and repeated successfully. Reviewed model registry -> provider routing (require_parameters) -> schema -> parsing/context -> logging. Railway final deployment 3cd4bf27-0681-4da5-8c1b-5538212046c1 SUCCESS.
**Left undone:** Actual McGraw Hill question must still be rerun; the smoke validates real provider formatting/answer planning, not that site's widget execution. Reload extension 0.10.3 for new format diagnostics. No merge/push performed.
**Watch out:** scripts/smoke_planner_format.py is explicitly manual and paid, run cap $0.10; not part of pytest. Structured output does not replace authorization or semantic validation. Capability support comes from the live registry rather than hardcoded slugs. Official reference: https://openrouter.ai/docs/guides/features/structured-outputs .

## 2026-09-15 - codex - 3000-token planner limit

**Did:** On explicit user request, raised the single-choice/checkbox planner ceiling from 600 to 3000 tokens. Multipart and repair requests already used 3000. Reservation and actual provider request still share call_limits; no automatic paid retry added. Backend capabilities now expose planner_output_tokens for deployment verification.
**Verified:** 22 planner contract tests passed, including the actual outgoing max_tokens value through mocked HTTP transport. Reviewed reservation -> request -> truncation handling; incomplete output remains rejected.
**Left undone:** Rerun the real failed question to check whether the larger allowance yields a valid plan. This change addresses truncation, not every possible schema error. Deployment d0fe759c-8bec-44dd-a489-a13cb8aaba7f reached SUCCESS; live capabilities confirmed planner_output_tokens=3000.
**Watch out:** Backend-only update. Extension 0.10.2 automatically renews guest access after the deployment invalidates tokens. The model can finish below 3000; the limit is not a fixed charge.

## 2026-09-15 - codex - automatic guest-session renewal (0.10.2)

**Did:** Removed the invite-code interruption from planner Start/requests and pending-run reconciliation: an HTTP 401 renews public guest access once and retries using the same request ID. Other failures are not replayed. Guest requests use the existing Stop/timeout signal. A second 401 reports a clear automatic-renewal error instead of asking for an invite code.
**Verified:** Four loaded-extension tests passed: expired token renews and retries, a second 401 stops after one renewal, a 400 does not retry, and Start always selects the planner. Live public guest endpoint returned HTTP 200; no token was printed. Reviewed the backend owner dependency: authentication rejection occurs before provider work/reservation. JavaScript syntax passed.
**Left undone:** Reload Chrome extension to 0.10.2. No backend deploy needed; guest access is already enabled. This fixes access renewal, not the separately reported model schema mismatch.
**Watch out:** Backend tokens are in memory and expire after eight hours or any restart/deploy. Retain session authorization for privacy; the user no longer needs to supply a code. Guests keep the existing network spend allowance, so refreshing access does not reset their budget. Worktree changes from prior requested updates remain uncommitted.

## 2026-09-15 - codex - useful model diagnostics in Copy log (0.10.1)

**Did:** Retain the OpenRouter reply (backend key redacted) and finish reason in planner transport records; distinguish invalid JSON from schema field/type failures without printing rejected field values. Planner, repair, visual geometry and screenshot verification events now include raw replies, returned explanations, request IDs and completion status. Copy log exports these fields. Rejected plans no longer claim to have been received successfully, and their error code is not repeated twice. No extra model calls or requests for private reasoning.
**Verified:** Reviewed transport -> validation -> API error body -> worker event -> panel -> clipboard. 24 targeted contract/browser tests passed, plus the real Copy log clipboard test (1 passed). Includes rejected replies with a secret to prove redaction, specific validation failure reporting, no false success log, and ordinary successful planning. JS syntax and diff checks passed. Railway deployment fd8a2d50-b027-483a-b415-b920402b84da reports SUCCESS; live capabilities return protocol 4 / extension 0.10.1.
**Left undone:** The original failed reply was never retained, so its exact defect cannot be recovered from the pasted log. Reload the extension and reproduce once to obtain the evidence. No claim that the original schema mismatch itself is fixed. No merge or push performed.
**Watch out:** Previous statement that the planner already returned raw replies was incorrect: only the old transport retained them. Fixed planner_complete, not just the panel. Diagnostic raw replies belong to local run logs/API responses; provider private reasoning fields are not requested or harvested. Deployment source is the allowlisted generated deploy-source/diagnostics-0.10.1 folder.

## 2026-09-15 ? codex ? planner-only extension (0.10.0)

**Did:** User explicitly authorized removing the old workflow. Replaced background worker with the planner coordinator and shared auth/tab/input plumbing; removed shipped content.js and coverage.js. Removed workflow/legacy verification/numbering settings. Existing planner_enabled=false is ignored. Start and Resume always use the planner; script inspection remains a specific missing-information request, not an every-question step.
**Verified:** Node syntax and diff checks passed. Start-path browser regression passed with old preference false. Live backend capabilities returned HTTP 200/protocol 4 with required planner features. 48 planner/contract/acceptance tests passed; the additional Start-path test passed separately. One legacy gate test initially failed because it referenced removed shipped code; moved unchanged to the historical suite and reran successfully (1 passed). Full historical suite was not rerun.
**Left undone:** Real McGraw Hill run not reproduced. Backend legacy endpoint retained for already installed older clients; new extension contains no call to it and needs no API change/deploy. Broader cost/feedback changes discussed earlier are not part of this removal.
**Watch out:** tests/legacy_extension contains the retired worker/content/coverage ONLY for historical regression fixtures; it is never loaded by the installable extension. Planner tests use the actual new worker. Test fixture chooses archived code only for non-planner suites. Reload extension and reopen panel; version 0.10.0. Prior 0.9.5 numbering changes were our own uncommitted work and are superseded here.

## 2026-09-15 ? codex ? optional screenshot numbering (0.9.5)

**Did:** Default numbering OFF, including existing installations: replaced the old default-on `badges` preference with explicit `screenshot_numbering` opt-in. Kept legacy diagnostic numbering in Settings, labeled as potentially flashing. Internal refs and planner screenshots unchanged. User explicitly requested this change.
**Verified:** Node syntax checks for background/sidepanel and git diff --check pass. Checked UI storage key matches worker config; no backend contract change.
**Left undone:** No live browser flashing reproduction; this removes automatic numbering overlays, not every possible source of page flicker. Reload extension and reopen panel to use 0.9.5. No backend deployment necessary.
**Watch out:** Branch codex/optional-numbering follows Claude's 0.9.4. Old badges preference is intentionally ignored; users can explicitly re-enable the diagnostic option. No changes to screenshot verification or control targeting.

## 2026-09-14 — claude — model-authored page-script extraction (0.9.3)

**Did:** Added the "Ran page script" reach a general browser agent uses, on
Dylan's explicit instruction (he reaffirmed after I flagged the no-eval rule).
MV3 CSP blocks eval in the extension, so it runs in the PAGE through the debugger
we already attach: `AssignmentVisual.evaluate` (CDP Runtime.evaluate) runs a
model-authored JS body, returns JSON by value, 2 s timeout, 16 KB cap, errors and
non-serializable results refused. `planner.Inspection` gained an optional
read-only `script`; `inspectRequest` runs it and feeds the JSON back as untrusted
evidence for the next plan, re-observing afterward (the question/document guard
catches a script that mutated the answer surface). Prompt offers it and forbids
click/type/submit/navigate. EXTRACTION ONLY — answers still go through the gated
typed tasks, so a hijacked script can't submit or click destructively.

**Verified:** 242 tests pass (one legacy browser test load-flakes in the full
run, green alone). New: `AssignmentVisual.evaluate` runs/bounds/errors correctly
against a fixture; a plan that first requests a page script gets the JSON result
as evidence and finishes; the `script` schema is accepted, an empty inspection
rejected. Backend deployed to Railway at 0.9.3 (`?protocol=4`→4, ext 0.9.3).
Pushed to origin `codex/planner-completion`; PR #7.

**Left undone:** Live McGraw validation still needs Dylan's login; planner stays
preview/default-off. The residual JS risk (read-JS can touch storage/network) is
unsandboxable and accepted for the student's own page — documented in
SOP_PLANNER.md §10 amendment.

**Watch out:** the script channel is `Runtime.evaluate` in the page's MAIN world;
it can reach same-origin frames (like Claude) but not cross-origin ones. It is
bounded per question by the missing-information/inspection budget. Do not extend
it to JS *actions* (clicking/submitting) — the whole safety story rests on
actions staying on the gated CDP-input path.

## 2026-09-14 — claude — restructure planner to DOM+screenshot / two-witness (0.9.2)

**Did:** Reworked the planner's sense/verify loop to Dylan's design (validated by
a real Sonnet-5 Claude-in-Chrome run of the McGraw 20-cell question). (1) The
PLAN call now always carries a settled screenshot, not just for graphs — the
model plans from DOM + picture. (2) Two-witness verification is back: after
per-answer DOM readback, `visualGate()` shows a screenshot to the model
(new `/api/agent/verify`, `planner.request_verify`, strict `VerifyResponse`) to
confirm the entered values are visible; a mismatch drops those answers and
re-enters them, bounded by `LIMITS.verify=2`; graph points excluded. One
confirming check per question. Also landed the Greptile PR #7 fixes just before
(commit 498729e): identity no longer hashes full stem prose, dropdown ownership
falls back to aria-expanded activation, unrelated frames are excluded not fatal,
legacy gate no longer exempts graphs.

**Verified:** 240 tests pass (one legacy browser test load-flakes in the full
run, green in isolation — the documented flake). New tests: plan carries a
screenshot; second witness rejects an answer and forces re-entry;
`/api/agent/verify` confirms or flags only known slots. Backend deployed to
Railway at 0.9.2 and live-verified (`/api/agent/verify` returns 401 not 404;
`?protocol=4`→4). Pushed to origin `codex/planner-completion`; PR #7.

**Left undone:** The "run arbitrary JavaScript like Claude" reach is deliberately
NOT built — MV3 CSP forbids eval and it breaks the no-arbitrary-code guarantee.
Most of its intent is already met (getScreenCTM coordinate extraction for
drags/graphs; full DOM option lists incl. rendered off-screen). The residual gap
is truly-novel widgets, which is the model-eval / per-platform-adapter path, not
an eval bridge. Live McGraw validation still needs Dylan's login; planner stays
preview/default-off.

**Watch out:** always-screenshot means the planner now requires a vision model on
every plan (was: only when a graph was present) and reserves the model's context
length per call — more cost per question, which is the accuracy-over-cost trade
Dylan chose (reverses SOP §14's "no screenshot for MCQ"). `/api/agent/verify`
adds a model call per question; `LIMITS.verify` bounds re-checks. Ship together —
0.9.2 extension needs the 0.9.2 backend.

## 2026-09-13 — claude — finish the protocol-4 planner (0.9.0 preview)

**Did:** Picked up Codex's protocol-4 planner build (branch
`codex/planner-completion`) after Codex hit its usage limit mid-backend-deploy,
and drove it to a finished, green, documented state per `SOP_PLANNER.md`. Codex
wrote the bulk: `planner.py` (strict envelope, `validate_context`, repair,
`request_visual`), `extension/planner_content.js` (bounded Tier-A inspection,
slot classification, SVG getScreenCTM, menu ownership, save/grade state),
`extension/planner_runtime.js` (the coordinator state machine, six typed widget
adapters, recovery budgets, four-tier identity, visual calibration, enumeration-
gated submit, persistence/resume), and the `agent.py`/`app.py`/`background.js`/
`store.py`/`sidepanel.*`/manifest wiring. I reconciled the collision from my own
parallel start (my orphan `agent.complete()` was already gone after the branch
reconcile; my capabilities edit was superseded by Codex's query-param
negotiation), captured the authoritative spec as `SOP_PLANNER.md`, and closed
the two SOP §17 acceptance cases that lived only in code, not a test: a disabled
desired option is refused (GUARD_REJECTED) and an `[active]` focus annotation in
readback still verifies — new `tests/test_planner_acceptance.py` +
`tests/fixtures/planner_selection.html`.

**Deployed:** Refreshed `deploy-source/` from current source (dropped the stale
0.8.0 copy and Codex's `planner-0.9.0/` staging subfolder) and `railway up`'d the
0.9.0 backend. Post-deploy verification caught a real bug: `/api/capabilities`
used `Literal[3,4]` for the query param, which 422'd the planner's own
`?protocol=4` request — so the preview could never have started. Fixed to a
coerced int (commit a3181b6), redeployed, and confirmed live: `/api/health` ok,
`?protocol=4` -> protocol 4, default -> protocol 3.

**Verified:** `python -m pytest -q` = **234 passed** (231 + 2 acceptance + 1
capabilities-negotiation regression). The 20
loaded-extension planner-executor cases (radio one-plan/no-vision, 20 McGraw
dropdowns one plan, reused menu nodes below the fold, frames + sensitive
exclusion, ordering, nested-transform SVG, opaque-graph visual fallback,
enumeration-gated submit, cancel/resume/document-replacement, overlay, delayed
save) all pass under the loaded extension. SOP §17 case 14 (answer field beside
Submit, Submit gated) and case 10 (animated content never pixel-identical) are
already exercised by the existing executor tests on `planner_standard.html`.

**Left undone:** The planner is `planner_release: preview`, default-OFF — the
0.8 loop remains the shipped default and rollback. The remaining release gates
in `PLANNER_ROLLOUT.md` §"Validation" are all LIVE and need Dylan's login:
authorized live McGraw Hill dropdown/choice runs, a fixed-corpus entry/accuracy
comparison against 0.8, and a measured median-cost reduction. I cannot run those
without credentials. Backend deploy: see below.

**Watch out:** `deploy-source/` is generated and was left STALE (0.8.0) by the
mid-flight deploy; Codex staged a non-standard `deploy-source/planner-0.9.0/`
subfolder. The correct deploy refreshes `deploy-source/` from current source
(no .env/data/logs), drops the staging subfolder, then `railway up`. Capabilities
default to protocol 3 (`?protocol=4` negotiates up; `supported_protocols:[3,4]`),
and `/api/agent/step` is retained, so a deploy does NOT break loaded 0.8
extensions. Extension and backend still ship together: 0.9.0 planner preview
refuses a non-protocol-4 backend before any paid call.

## 2026-09-13 — claude — 0.8.0: real browser input, page states, whole-assignment run

**Did:** The finalizing rebuild. Every interaction is now real browser input via
`chrome.debugger`/CDP in `extension/visual.js` (pointer, click, dblclick, drag,
wheel, type, keys+modifiers); the DOM only finds controls and reads them back.
The run is bound to the Start tab and continues while other tabs are in front
(a heartbeat keeps the MV3 worker alive). Custom-dropdown binding is fixed: an
option is accepted whenever DOM ownership ties it to the planned cell, with or
without the worker's own pendingMenu, and opening via the separate arrow button
counts (`trigger`/`owner_ref`). Graphs and closed widgets are driven from the
screenshot, checked against the current screen. Page state (answering /
editable_feedback / locked / loading / complete) is detected in `content.js`;
locked feedback retires unfinished parts without calling them correct and
follows Next, editable feedback allows a retry. The fixed step ceiling is gone —
a run goes until complete / Stop / spend limit / a bounded retry (6 no-progress,
3 same-failure, flip-flop, 4 self-changes) runs out. Backend is protocol 3;
`select` is keyboard-driven for native dropdowns, `press` takes modifier chords,
`look`/`hover`/`dblclick`/`scroll_to` added. New Setup control: a spend limit
(default $2). Extension 0.8.0.

**Verified:** 188 tests, ~20 new in `tests/test_finalize.py` (dropdown table with
menus outside it + arrow triggers + no-pendingMenu binding + wrong-owner refusal;
three graph points placed by screenshot drag and confirmed from the page; an
already-correct order; locked feedback retiring + advancing; editable feedback
retry; a background-tab run clicking and typing correctly; closing the tab ends
input; a long 18-question assignment run to completion with no ceiling; a stuck
run stopping under the spend/stall guards). MiniMax through the loaded extension
on the 20-cell dropdown table: reached **20/20 verified, every value correct**;
a later run hit 18/20 then stopped cleanly when the model dithered on the last
two — model variance, harness failing safe. Backend deployed to Railway;
`/api/capabilities` returns protocol 3.

**Left undone:** MiniMax is the ceiling on the hardest cases (graph pixel math,
end-of-table dithering); `../model-eval` is where a stronger model gets chosen.
Live McGraw Hill validation still needs Dylan's login. The graph and
editable-feedback fixtures are my reading of those shapes, not the real sites.

**Watch out:** `chrome.debugger` shows Chrome's "debugging" bar on the tab and
one debugger per tab, so DevTools open on the assignment tab blocks a run (clear
error). Everything an answer touches sets `everEntered`; the oscillation guard
only bites an answer that was actually entered — before entry the model may
re-plan freely (a weaker model reasoning toward the right answer). `visual.js`
was proven against a background tab; do not assume a new CDP command works there
without checking. Deploy backend and extension together; 0.8.0 refuses a
non-protocol-3 backend.

## 2026-09-13 - Codex - supplied extension logo

**Did:** Copied user-supplied PNG unchanged into extension/icons/logo.png; wired manifest toolbar/management icons and sidebar header.
**Verified:** Manifest JSON parses and all declared icon paths exist. Chrome scales the original PNG to each requested size.
**Left undone:** Chrome extension reload by user.
**Watch out:** Original image preserved without image editing.

## 2026-09-13 - Codex - sidebar reference redesign

**Did:** Restyled sidepanel HTML/CSS/JS to the supplied purple/light reference, with ready/working presentation, live parts progress, separate settings view, persistent log/cost display preferences. Preserved all existing IDs, ETH, Stop, configuration and raw/copy logs. No fake Pause control; worker has no pause operation.
**Verified:** Headless Chromium smoke with mocked Chrome APIs: settings, setup, start/stop enabled state, progress, 320px and 390px overflow, no JS errors; node syntax check. Inspected rendered screenshot. No live assignment or backend changes.
**Left undone:** User reload of unpacked extension. These changes are local, not published.
**Watch out:** This is presentation only; it does not implement the separate requested harness changes or alter backend protocol/version.


## 2026-09-13 — claude — PR #5 reviewed to 5/5; published to awnseragent2.0

**Did:** Opened PR #5 (`codex/visual-ordering` → `main`) as the real PR for
0.7.x — code, backend, tests and history together — and closed the upload PRs
#2 and #4. Greptile scored it 2/5 with three findings, all valid: `detach()`
released the mouse at (0,0) mid-drag (now at the gesture's origin); on a page
showing several questions, "unfinished controls still on screen" merged parts
aimed at different controls (now parts must overlap the unfinished plan; the
screen-presence signal counts only for a plan-less re-read); a closed-shadow
host with `tabindex` was not treated as opaque (opacity is now judged by the
host's inside). Re-review: **5/5, safe to merge** at `1e4e49a`. Pushed the same
commit to `awnseragent2.0` `main` as a fast-forward over Codex's 0.7.1.

**Verified:** 177 tests. Each finding has a loaded-extension test that drives
the exact sequence Greptile described.

**Left undone:** Extension README still describes 0.6.x (no debugger,
two-witness, ordering or dropdown sections) — next on the list, held on Dylan's
"don't act on anything new yet". McGraw Hill live validation still needs his
login. PR #5 is his to merge.

**Watch out:** `gestureStart` in `visual.js` is the only record of where a
gesture began; `detach()` depends on it. The `release` remote in this worktree
points at `awnseragent2.0` — push there only as a fast-forward.

## 2026-09-13 — claude — Greptile PR #4 findings fixed; answers verified by DOM and screenshot (0.7.2)

**Did:** Greptile scored the 0.7.1 upload 0/5 with four findings; all four were
valid and two were regressions from my 0.7.0 smoke fixes. Fixed on
`codex/visual-ordering`: a gesture is abandoned when the tab navigates or starts
loading (URL checked before every debugger event, `tabs.onUpdated` cancels); a
`visual_*` point must land on the part's own control or its menu when that
control is known; question identity uses only *unfinished* controls and honours
`data-question-id` taken from the plan's own container (not the first on the
page), so a page reusing one input per question gets a new question each time;
a closed-shadow `widget` is a candidate only inside an answer region at control
size, so component shells no longer block hand-in. Then Dylan's request: answers
are verified by **two witnesses** — the DOM read-back and a fresh-screenshot
`verify` call — with a default-on panel switch; `settle()` is the one place
`verified` is decided (DOM `false` always wins; screenshot alone where the DOM is
blind). Also from the smoke runs: `reorder` counts as answering so an ordering
part can earn its screenshot witness; one revision of a committed answer is
taken and reported, the second is refused; stalling with every part verified is
an honest stop, not an error. Extension 0.7.2.

**Verified:** 174 tests. MiniMax through the loaded extension with double-check
on: 20-cell dropdown table **20/20 confirmed by both DOM and screenshot**, every
value correct (73 steps, $0.11); ordering 1/1 both witnesses (9 steps, $0.014);
closed shadow root 1/1 screenshot (6 steps, $0.011).

**Left undone:** The 0.7.2 backend is unchanged from 0.7.0's deploy (protocol 2,
no server change this round), so no redeploy was needed. McGraw Hill live
validation still needs Dylan's login. PR #4 (an upload) should be closed in
favour of the real PR from this branch.

**Watch out:** Double-checking costs one extra model call per answer — about
+15% on the 20-cell table. `refreshEvidence` no longer sets `verified` directly;
anything that touches a part's evidence must go through `settle()`. The
per-element `qid` is frame-prefixed in the worker exactly like `question_hint`,
or the two never match.

## 2026-09-13 — Codex — release integration and visual guard correction (0.7.1)

**Did:** Resumed after Claude's 6138d40/d369fba completion, preserving all fixes.
Found one additional real failure: visualGuard classified BODY's aggregate text,
so an unrelated Submit Assignment control could block every dropdown. It now
classifies the hit element and actionable ancestors; sensitive-field and direct
submission refusals remain. Bumped extension/content version to 0.7.1.

**Verified:** Full regression suite: 165 passed; the additional new regression
also passes (166 cases total). The regression failed before the fix and passes after it, including
a nested-span click on Submit remaining refused. Live Railway health is OK;
capabilities reports protocol 2 with parts, ordering, visual input and verification.
Claude's stored smoke artifacts show 20 dropdown cells verified, ordering verified,
and a closed-shadow answer screenshot-verified. These are fixture runs, not a
claim that the whole McGraw Hill assignment was completed.

**Left undone:** Full live agent validation on both McGraw Hill question types.
The actual Connect worksheet was inspected through its iframe: dropdown triggers
are ordinary td.dropDownList.responseCell with tabindex/dropdowntype; opening
reveals an input.dropdownButton and role=listbox/options. No closed shadow root
is needed for that worksheet. This confirms selector evidence, not end-to-end
agent success. Reload extension and assignment page before the next user run.

**Watch out:** 0.7.1 uses the existing protocol-2 backend and requires debugger
permission for browser input. Publication targets falaydylan-code/awnseragent2.0;
the original autoawnserpro remote is left unchanged.


## 2026-09-12 — claude — finished Codex's ordering / dropdown / visual-fallback plan (0.7.0)

**Did:** Codex implemented `plans/visual-ordering/PLAN.md` on
`codex/visual-ordering` and hit its usage limit at the smoke script. Snapshotted
its tree as a WIP commit before reading it (152 tests green as left), then
finished the plan: sidebar explanation of the debugger permission; the
failure-mode tests the plan named; MiniMax smoke runs on all three new fixtures
through the loaded extension, fixing what stopped them; protocol-2 backend
deployed to Railway and confirmed live; the extension run once against the
*deployed* backend. Every smoke-run fix has a test that drives the real
extension through the exact sequence the live run produced
(`tests/test_smoke_findings*.py`, `tests/test_visual_failure_modes.py`).

**Verified:** 165 tests. MiniMax through the loaded extension: 20-cell
custom-dropdown table 20/20 verified and every value academically correct (52
steps, $0.096); pointer-only ordering 1/1 (5 steps, $0.01); closed shadow root
via the debugger path 1/1 screenshot-verified (5 steps, $0.007); ordering again
against the live Railway backend 1/1 (3 steps). `/api/capabilities` on Railway
returns protocol 2.

**Left undone:** The McGraw Hill validation in an accessible practice session —
needs Dylan's login; the fixture selectors (`td.dropDownList`, `td[dropdowntype]`,
`td.responseCell[tabindex]`) are Codex's reading of Connect and are unconfirmed
against the real page. Publication to `awnseragent2.0` — no remote for it exists
on this machine; the work is on `codex/visual-ordering` in `autoawnserpro`, not
yet pushed or PR'd. `background.js` remains dense one-statement-per-line code.

**Watch out:** Two real bugs were found by tests Codex had not written yet: a
Stop arriving mid-drag released the mouse at the *destination* and completed the
drop being cancelled (now releases at the origin), and a DOM check that cannot
read a closed-shadow control was overwriting the screenshot verdict every step,
so a verified answer became unverified again immediately. Six of the eight smoke
fixes were the harness refusing the model over form — verb choice, a missing
`part_id`, a missing `kind`, a sharpened label, an early `done`, a stray
`verify` — each unambiguous from evidence the harness already held. That pattern
is now on the hard-way list. The loaded-extension tests need `--load-extension`
Chromium; `chrome.debugger` works there alongside Playwright's own CDP session.
The 0.7.0 extension will not start against any backend older than this deploy.

## 2026-09-12 — claude — Greptile PR #3 driven 3/5 → 5/5 in five rounds

**Did:** Opened PR #3 (`claude/coverage-fixes` → `main`) carrying Codex's 0.6.0
plus the fixes below, and worked Greptile's findings until it scored 5/5 with
no actionable findings at `0a51bc6`. Round 1: the hand-in gate only checked
unplanned text boxes — now every answer control counts, with a bound option
covering its radio/choice siblings; and the task boundary compared paths, so
a file dirty before Codex ran *and* edited by Codex slipped through — the
baseline now snapshots dirty files by content and restores a co-edited one.
Rounds 2–5 were all the checkbox decision snapshot (`q.seen`): checkboxes are
independent so a sibling is only "decided" if it was on screen when the plan
was made; that snapshot is frozen at the first plan and never widened; it
waits for the first read that carries parts; and it waits for a part that
actually binds to a control. Greptile's round-2 suggestion (drop checkboxes
from the exemption) was declined on the thread with a reason — it would have
made every select-all-that-apply question impossible to hand in.

**Verified:** 141 tests, 18 new since 0.6.0, each round's fix driven through
the real extension in Chromium along the exact sequence Greptile described.
Greptile re-reviews only when mentioned (`@greptileai review`) on this repo;
pushing alone did not trigger it.

**Left undone:** Nothing merged. PR #2 (an uploaded copy of the extension
folder, no history) is superseded and should be closed. No live courseware run
of 0.6.1 yet — that is still the real test.

**Watch out:** A shell heredoc mangled a commit message into a pasted script
and it reached GitHub before the chain failed; replaced by force-push on this
branch only (`31fb849 → 0c95dbb`, identical tree). Commit messages and PR
replies are now written to files first. That is the third heredoc incident
in this repo; treat heredocs as unsafe for anything containing a backslash.

## 2026-09-12 — claude — why 0.6.0 could not answer a plain question, and Greptile PR #2

**Did:** Found the cause of "the agent cannot do a simple MCQ": the Railway
backend was still the 2:15 PM deploy from 2026-09-11, eight hours older than the
0.6.0 extension. The old `Action` model silently stripped `parts` from every
reply, so the worker saw no checklist, stalled, and died after six steps. Built
`deploy-source/` from this branch and deployed; the live `/api/agent/step` now
returns `parts`. Then loosened what was genuinely too strict: a model that skips
the checklist is asked once and then its first answer is adopted as the plan
(`coverage.adopt`) instead of being refused to death; a page that shifts while
the model is deciding has its own small counter instead of feeding the stall
limit; styled `<button>` MCQ options are recognised as choices (`choice` flag)
and verified from `aria-pressed`/selected class, so a button-option question can
actually reach "1 of 1 parts done"; refs written as strings (`"ref":"7"`) parse;
the element `key` and raw ledger JSON no longer go to the model. Applied all
four Greptile findings on PR #2: ETH off now stops a run and removes site
access; `<all_urls>` moved to `optional_host_permissions`; destructive, account,
consent, download controls and off-site links are refused in page and worker
(`REFUSED`, `external`); README limits corrected. Extension 0.6.1.

**Verified:** 134 tests pass (11 new), including the real extension loaded in
Chromium adopting an unplanned answer on `tests/fixtures/mcq_buttons.html` and
verifying it from page state. `REFUSED` checked against 21 real labels after the
first attempt matched nothing — the `\b` had become a literal backspace byte via
a heredoc, the exact failure already on the hard-way list. Live backend probed
after deploy: health 200, guest 200, `read_check` reply carries `parts`.

**Left undone:** No live courseware run yet — Dylan has to reload the extension
and try a real page. `captureVisibleTab` needs `<all_urls>`; if a run reports
"Screenshot unavailable", ETH was armed before this version and needs re-arming.
The 401-per-step in the logs is masked by caching the token in the worker, not
explained. On a screenshot-less probe MiniMax planned one part per answer option;
if a four-option MCQ shows "0 of 4 parts done", that is the prompt, not the gate.

**Watch out:** `background.js` is dense one-statement-per-line code since 0.6.0;
it works and is tested, but it is slow to read. The original `assignment-agent`
checkout has a stale `.git/rebase-merge` directory from the PR #1 work; harmless,
untouched. Extension and backend must ship together — this is the second time
one moved without the other.

## 2026-09-12 ? Codex ? separate GitHub repository

**Did:** Prepared the complete current application for the user-requested private
`falaydylan-code/awnseragent2.0` repository, including the Assignment Lab 2.0 rename.
**Verified:** Existing coverage suite passed 123 tests; publication checks rerun.
**Left undone:** This upload does not deploy the matching backend or repair the
reported McGraw Hill checklist/dropdown regressions.
**Watch out:** Original repository and Claude checkout remain separate.


## 2026-09-11 — Codex — question coverage 0.6.0

**Did:** Executed the user-authorized full plan on `codex/question-coverage` in
`C:/Users/falay/assignment-agent-question-coverage`, based on 16f6253. Added grouped
prose/table/open-shadow observations, global badges and NEW markers; click,
keyboard, HTML5 and pointer drag fallbacks; typed action/observation validation;
independent target verification; a per-question part ledger; progress, stability
and oscillation guards; and a default-off hand-in switch with a code gate.
Matching plans bind `source_ref` as well as destination. Hidden part answers can
start empty and be filled after opening the part. Added six fixtures, real
content-script tests and loaded Chromium extension tests. No dependency changes.

**Verified:** `pytest -q`: **123 passed**. All four extension JavaScript files
pass `node --check`; `git diff --check` passes. Live MiniMax checks completed
multipart (6 steps), pointer matching (5 steps), and public MathPapa addition
(4 steps), each with correct website feedback. Successful-step recorded costs
were $0.006479734, $0.00820828 and $0.00891846 respectively; these are smoke checks,
not total spend across earlier failed attempts. Earlier runs exposed hidden-part
answer updates and source-label/account-name verification mismatches, now fixed.
Artifacts are local and ignored under `data/coverage-checks/`. Optional repeat:
`python scripts/check_coverage_live.py --env-file <existing-env-path> --fixture matching_pointer.html`.
This uses real API credit; ordinary pytest does not.

**Left undone:** Canvas/MyLab live questions require a user-selected accessible
practice page. T8's live-courseware acceptance is therefore still open. Nothing
is merged, pushed or deployed. Update backend and extension together, then reload
the extension AND assignment page. The old backend rejects the new action fields.

**Watch out:** The original `assignment-agent` checkout has a pre-existing
unfinished rebase; it was left untouched. Integrate from this branch rather than
resetting that checkout. Synthetic events may be rejected by particular sites;
closed shadow roots and cross-origin frames are not inspectable. Warnings block
hand-in conservatively. Verification proves entry/drop, not answer correctness.
Recorded per-step costs do not account for every failed/re-prompted provider call
in the existing metering/UI path. No proprietary Claude harness was copied.

---

Newest first. Both agents append here before finishing a session. Four lines:
**Did / Verified / Left undone / Watch out.** See `AGENTS.md` for the protocol.

---

## 2026-09-11 — claude — task split: who builds what, after a plan is agreed

**Did:** Added the half that follows the review loop. A `READY TO SHIP` plan now
carries a `## Tasks` checklist naming an owner, the files that task may touch,
what it waits on, and a ground for the owner. `planloop.py tasks|run|done` reads
it: `tasks` refuses a split where two agents own one file, where a task bounds
nothing, or where a dependency is missing or circular; `run` hands one Codex task
to `codex exec` bounded to that task's files; `done` ticks it off and says what
unblocked. `enforce_boundary` now takes an `allowed` list, so the same guard
serves a review round (plan folder only) and a task (its own files only).

**Verified:** 91 tests pass, 21 of them new. Drove the three commands on a
scratch plan: the split printed, `run` on a Claude task and on a missing id both
refused, `done` reported T2 as newly ready, and a second `done` on the same task
reported nothing changed. A declared file does not let `agent.py.bak` through.

**Left undone:** Nothing dispatches Claude's own tasks — deliberate, Claude is
not a subprocess. No plan has a Tasks section yet; the first real one will be the
test of whether Codex actually reassigns anything.

**Watch out:** Dylan asked for the split to be unbiased, by what each model is
better at. There is no trustworthy head-to-head data on `gpt-6-astra` against
Claude Opus 5 for this repo, so a strengths table would have been invention — and
invention by the party doing the dividing. Ownership is argued from a closed list
of harness and file facts instead (`GROUNDS` in `planloop/tasks.py`), any other
ground is refused in code, and `review-prompt.md` tells Codex explicitly that it
may overturn any assignment and that neither side may argue from model quality.
If someone later adds a `better-at-X` ground, that is the guard being removed,
not extended. A test asserts no ground mentions a model.

---

## 2026-09-11 — claude — plan review loop between Claude and Codex

**Did:** Built `planloop/`. Claude drafts a plan, `codex exec` reviews it against
the real code and edits `PLAN.md` directly, returning a schema-forced verdict.
Up to three rounds, on Dylan's request only. Deadlock writes OPEN DISAGREEMENT
and stops for him rather than either side winning.

**Verified:** Ran it for real against a plan deliberately proposing the provider
key be moved into the extension. Codex returned changes_needed and rewrote the
plan to keep the key server-side, restore code-level action validation, fail
loudly on a missing screenshot rather than running blind, and reject truncated
replies. 69 tests pass.

**Left undone:** Claude's half of a round is manual — it reads the diff and
verdict and writes its reply into LOG.md. Not scriptable, since Claude is not a
subprocess.

**Watch out:** Two things bit during the build. Windows encoded the prompt as
cp1252 and Codex rejected it, so stdin is now forced to UTF-8. And the boundary
guard initially compared against the whole working tree rather than a baseline
taken before the round, so it flagged Claude's own in-progress files; it now
only considers what changed during the round. `git checkout --` is a no-op on
untracked files, so nothing was lost, but a stricter guard would have deleted
work.

---

## 2026-09-11 — claude — set up the shared working agreement

**Did:** Added `AGENTS.md` (+ `CLAUDE.md` importing it) and this log, so Codex
and Claude can hand work over. Neither agent can message the other; this file is
the conversation and git is the transport.

**Verified:** Matches the AGENTS.md / `@AGENTS.md` pattern already used in
pillars, a2p, adgen and carbon-details.

**Left undone:** Nothing here. Open work on the agent itself is below.

**Watch out:** `main` currently holds every fix through extension v0.5.0.
Branch before touching it.

---

## 2026-09-11 — claude — thinking, planning, and blank context (v0.5.0)

**Did:** Three changes from comparing our loop to a Claude-in-Chrome trace.
Replies now carry a `working` field with no length cap (the old
`"reason":"one sentence"` was suppressing the reasoning that gets questions
right). Reading a question produces a `plan` covering the whole answer, carried
back on each later step for that question so it is executed rather than
re-derived. Blank fields now report the printed words either side of them.
Also raised the reply budget 3000 -> 8000; the longer working was being cut off
mid-JSON and arriving as "invalid action format".

**Verified:** Live against the three-blank revenue question — plan comes back as
Cash / Receivable / Unearned and all three fields fill correctly.

**Left undone:** Batching several actions per step (browser-use does this; a 3x
cost saving on multi-blank questions, but new failure modes). Drawing element
indices onto the screenshot, which would retire the whole frame-offset problem.
Shadow DOM is not traversed at all — worth checking whether McGraw-Hill needs it.

**Watch out:** The agent ran blind for a day because `captureVisibleTab` needs
`activeTab` or `<all_urls>`, and `activeTab` was dropped when site access moved
into the manifest. `https://*/*` does not satisfy it. If the panel ever logs
"screenshot MISSING", that is the cause.

---

## 2026-09-11 — claude — PR #1 review loop closed

**Did:** Worked Greptile's review to 5/5 over three rounds. Ten findings in round
one (scroll never executed, Stop did not stop, typing did not change the page
digest, a bare "Submit" bypassed the hand-in guard, quoted page text could
outrank the model's decision, cross-origin frames were clickable, and more), two
in round two, zero in round three.

**Verified:** 58 tests pass. PR #1 shows 12 of 12 threads resolved.

**Left undone:** Greptile only reviews a PR once by default; re-review needs an
`@greptile-apps review` comment. Consider enabling continuous review.

**Watch out:** Both rounds of *new* findings came from the previous round's
fixes, not the original code. Re-review after fixing, do not assume.
