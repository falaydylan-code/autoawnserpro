# Assignment Lab — cloud session briefing (written 2026-09-24 by Claude "kimchi", integrator)

Paste this whole file into the session. It is self-contained. Everything in it is fact as of writing;
verify against the repo before acting, because Dylan may have pushed a version bump after this was written.

---

## 1. Who you are and the rules you work under

You are continuing an in-progress project for **Dylan**. He is not a programmer — explain things in plain
words first, and use file:line only as proof, not as the explanation. Read `AGENTS.md` in this repo; it is
the working agreement and it is binding. The short version:

- **Start every reply with `king dylan`** on its own line.
- **A question or a pasted log is a QUESTION.** Diagnose it, name the cause with file:line evidence, propose
  the fix — then STOP. Do not change code until Dylan says "go". One go = one change.
- **Nothing ships without his confirmation.** No deploy, no push, no publish on your own initiative.
- **Fix broadly, not for the one page in front of you.** Say plainly what a change prevents everywhere and
  what it does not.
- **Prefer stopping and saying so over guessing.** He runs this on his own graded coursework; a silent wrong
  answer costs him marks.
- Work on a branch (`claude/<short-description>`), and append a `HANDOFF.md` entry before you finish.
- Never give the model an answer key. The OpenRouter key never reaches the model, a response body, or the
  extension.

## 2. What this project is

A Chrome extension that works through the assignment page a student already has open. It observes
(screenshot + interactive elements), decides ONE action via a model, acts, then looks again.

- `extension/planner_content.js` — runs inside the page; the only thing that touches the DOM.
- `extension/planner_runtime.js` — owns the loop, the identity guards, and every limit on it.
- `planner.py` — the decide step: observation in, one validated action out. Also the navigation contract.
- `app.py` — FastAPI backend on Railway. Holds the API key; the extension never does.
- `ARCHITECTURE.md` is the map. `HANDOFF.md` is the running log — read its top 3 entries.

## 3. Where things stand right now

- **Live branch:** `codex/optional-numbering`, HEAD `0d05df5` (a HANDOFF-only commit) on code commit `1f26700`.
  Cut any new branch from `1f26700`.
- **Version 0.10.46 is DEPLOYED.** Railway `/api/capabilities?protocol=4` reports `0.10.46` with the
  `contextual_navigation` feature. Dylan has reloaded the extension and run it live.
- **Full suite on the shipped tree: 502 passed**, plus one `TargetClosedError` browser crash that passes
  when rerun alone (a known flake — always rerun a browser failure alone before believing it).

### What 0.10.46 shipped (three commits)

1. `ff3e060` — **multi-part.** A part is owned by the tab that is lit, judged by evidence (tab selected,
   answer controls in its frame, no other part claims them) rather than by a `part_scope` label the page has
   to supply. Plus: when the model's `parts_declared` count exceeds the parts found, the harness asks the
   page to treat a conservative group of numbered controls as a part switcher (`candidate_parts` +
   `assert_parts`), and only then gives up.
2. `82b5739` — **contextual navigation** (built by Codex). Workflow controls are read from their label PLUS
   the instructions around them, not a fixed word list. `answer_submit` is separated from `check` and from
   final hand-in. Controls the rules cannot read go to a bounded metered model call: at most 2 per question,
   permission-gated, revalidated against the live page before clicking, and unable to name a target the page
   did not offer. A submission click is recorded as pending before the input so a resumed run cannot repeat it.
3. `ad718f8` — a control owned by an answer is not a workflow control (the widened scan had turned 20
   dropdown openers inside response cells into workflow candidates and blown the 100 KB observation limit
   mid-run).

### Both of those fixes are CONFIRMED WORKING on the real site

McGraw Connect Ch.3 Q1 (2026-09-24 12:10 AM). Twelve cells across two tabs — entered, DOM-verified,
screenshot-verified. The page graded it **"Answer is complete and correct."** The navigation layer then found
"Check my work" by itself and pressed it. That question had never been completed before.

---

## 4. THE CURRENT PROBLEM — this is your task

### What happens

Immediately after the successful "Check my work" click, the run dies:

```
TARGET_STALE: Question identity changed after Check (frames [1747] -> [1752]); the graded page was not entered.
```

Everything before that point is correct. The answer is in, it is right, and the page says so.

### Why

McGraw does not refresh the question box when it grades. It **destroys the iframe and builds a new one**.
Chrome assigns the new element a different internal frame id: `1747` became `1752`.

That number is baked into the question's fingerprint — `extension/planner_runtime.js:151`:

```js
const question_key = hash(used.map(f => f.frame_id + ':' + f.question_key).join('|'));
```

and the identity that reports movers, `:153`:

```js
const identity = { frames: used.map(f => f.frame_id), detail: used.map(f => ({ frame_id: f.frame_id, ...(f.identity || {}) })) };
```

So a new frame number reads as a new question. The guard in `same()` (`:184-186`) then refuses to act on what
it believes is a different page, and the Check branch in the run loop throws rather than continuing.

**The guard itself is correct and must stay.** It is what stops one question's answers being typed into a
different question after a page moves. Its INPUT is what is wrong: a session-local browser handle is being
treated as part of a question's identity. Do not remove the check — fix what it is fed.

Codex/Mira predicted this exact case in the `HANDOFF.md` entry for 0.10.45 ("a site that re-creates the iframe
element rather than reloading it gets a new frame id, which is part of the key"). This is the first page seen
doing it.

### The proposed fix (reviewed with Dylan, NOT yet given a go — confirm before building)

Identify a frame by its **address**, not by Chrome's throwaway number. Every frame already reports its URL —
`extension/planner_content.js:534` returns `url: location.href` — so the stable value is already in hand.

- Build the key from the frame's URL. Where two frames on one page share a URL, add an occurrence index
  (`#1`, `#2`) so genuinely distinct sibling widgets stay distinct.
- Make `identityMovers` (`planner_runtime.js:48-52`) report addresses rather than raw numbers so the failure
  message stays readable.
- Leave `document_id` (`:154`) alone. It is SUPPOSED to change on a reload; `settle()`/`repin()` already
  handle that case correctly.

Once the key stops moving, the existing path takes over: `repin()` adopts the redrawn page, logs
"Website feedback received", and the loop goes on to look for Next. That machinery is already built and
tested — it simply never ran here because the key falsely moved.

**General, not McGraw-specific:** any site that rebuilds its question frame on grading hits this.

### What to expect immediately after this fix

In Dylan's screenshot of the graded page, the **Next button is greyed out** and a "Return to question" button
appears top-right. So the run may reach Next and find it disabled, then end with "No unique next-question
control found". Do not pre-emptively build for that — ask Dylan for the new log and diagnose it from evidence.

---

## 5. How to verify your work

```
python -m pytest -q                 # full suite, ~22 min, ~503 tests. No network, no API key needed.
node --check extension/planner_runtime.js extension/planner_content.js
```

- Relevant suites for this change: `test_planner_transitions.py`, `test_planner_worksheet_tabs.py`,
  `test_planner_part_reach.py`, `test_planner_navigation.py`, `test_navigation_contract.py`.
- **Prove a fix both ways** where you can: show the new test failing on the unfixed code and passing on the
  fixed code. That is the house standard and it has caught several fixes that only looked right.
- Browser tests need Playwright and a real Chromium. If the cloud box cannot run them, **say so plainly**
  rather than reporting a pass you did not get.
- Known flakes: a `TargetClosedError` browser crash, and a service-worker 30 s wait. Rerun alone before
  treating either as real.

## 6. What you CANNOT do from a cloud session

- **You cannot deploy.** `deploy-source/` is gitignored and the Railway credentials are on Dylan's machine.
  Deployment stays with him. Backend always deploys BEFORE the extension is reloaded, and the manifest
  version must be bumped on any extension change.
- **You do not have the vault.** `C:/Users/falay/vault` holds `STATE.md` and the project log and is never
  committed. `HANDOFF.md` in this repo is your handoff. Write your entry there.
- **You have no API key**, so no real model calls. The tests are all scripted and need none.

## 7. The queue after this, in priority order

1. **The frame-identity fix above** — the one thing standing between a correct answer and moving to the next
   question.
2. Whatever the next live log shows (likely the disabled Next button).
3. **Formative bundle — HELD SHIP BLOCKER.** Dylan's standing instruction: do not call the extension ready to
   ship/package until this lands. Items: role before `e.type` for non-input controls; tool groups excluded by
   a mirror rule; discovered groups optional in the plan; framework-generated ids (React `:r..:`, `_r_.._`)
   out of the fingerprint AND out of `key()`/`slotKey()`; candidate discovery must not cut text out of the
   question stem; slot keys without a trailing empty segment; one-label aliases; duplicated option text;
   chrome labels as whole-group rules.
4. The "unresolved leftovers" ending: a numbered row is offered as an unresolved candidate choice group and
   blocks a clean finish on an otherwise-answered question.
5. MathPapa graph candidates; packaging site allow-list.

## 8. Things learned the hard way — do not undo these

- **Prompt instructions are suggestions; harness rules are rules.** Anything that must not happen is enforced
  in code, not by asking the model nicely. Each was tried the polite way first and each failed.
- **Never swallow an error.** If something degrades a run, say so in the log, loudly, once.
- **A wrong coordinate is worse than none.** Report no position rather than a partial one.
- **Verify against the running thing, not the diff.** Several fixes looked right and were not.
- **Do not build against a fixture you invented.** 0.10.43 was written against a made-up page shape, shipped,
  and never once engaged on the real site. Build fixtures from Dylan's actual logs.
- The navigation scan is now much wider than a label list: anything reachable by
  `button,a,[role=button],input[type=submit],input[type=button]` that `navigationInfo` does not reject becomes
  a candidate with `kind:'unknown'`, and an unknown candidate is what spends a metered model call. The
  answer-owned exclusion is the only thing keeping a sheet of dropdown openers from doing that — do not narrow
  it back to equality.
