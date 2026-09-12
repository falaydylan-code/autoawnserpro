# Handoff log

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
