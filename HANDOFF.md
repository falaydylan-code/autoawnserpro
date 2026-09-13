# Handoff log

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
