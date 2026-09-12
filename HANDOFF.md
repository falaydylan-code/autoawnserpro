# Handoff log

Newest first. Both agents append here before finishing a session. Four lines:
**Did / Verified / Left undone / Watch out.** See `AGENTS.md` for the protocol.

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
