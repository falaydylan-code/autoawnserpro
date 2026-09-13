# Assignment Lab — working agreement

Two agents work on this repo: **Codex** and **Claude Code**. Dylan does not
write code. Both of you read this file; `CLAUDE.md` is just `@AGENTS.md`.

You cannot talk to each other directly. The repo is the channel:
`HANDOFF.md` is the conversation, git is the transport. Neither of you sees the
other's reasoning — only what gets written down. So write it down.

---

## Every session, in order

1. **Read `HANDOFF.md` first.** It says what the other agent last did, what is
   half-finished, and what is blocked. Do not start until you have read it.
2. **Check `git log --oneline -10`** for work that landed after that entry.
3. **Work on a branch.** Never commit straight to `main`.
4. **Append a `HANDOFF.md` entry before you finish**, even if the work is
   incomplete — especially then.

## Branch names

- Codex: `codex/<short-description>`
- Claude: `claude/<short-description>`

If you find uncommitted changes you did not make, **stop and say so**. Do not
commit over another agent's work in progress.

## The handoff entry

Append to the top of the list in `HANDOFF.md`:

    ## 2026-09-11 — claude — screenshot permissions
    Did: restored activeTab; captureVisibleTab had been failing silently since v0.1.2.
    Verified: live run on McGraw-Hill, screenshot now arrives.
    Left undone: batching several actions per step.
    Watch out: agent.py max_tokens is 8000 because working-out made replies longer.

Four lines: **Did / Verified / Left undone / Watch out.** Not a changelog — the
git log already is one. Write the things a competent stranger could not infer
from the diff.

---

## The plan review loop

Big changes get planned before they get built, and the plan gets a second
reader. Claude drafts, Codex reviews and **edits the plan directly**, Claude
answers. Up to three rounds. Nothing is built until both sides say ready.

    python planloop/planloop.py new <slug> "Title"    # start a plan
    python planloop/planloop.py review <slug>         # one Codex round
    python planloop/planloop.py status <slug>         # where it stands

Dylan triggers it, never the agents on their own:

- **"plan this: ..."** — Claude writes `plans/<slug>/PLAN.md` and stops
- **"review the plan"** — one round
- **"keep reviewing"** — until both agree, or three rounds are spent

Rules that make it mean something:

- A reply that is not a clear `ready` / `changes_needed` is refused. A malformed
  answer never counts as approval.
- Codex may edit `plans/<slug>/PLAN.md` and nothing else. Anything it changes
  elsewhere during a round is reverted; anything it creates elsewhere is moved
  into `round-N/rejected/`. Work already uncommitted before the round is left
  alone, because that is Claude mid-session.
- Both sides must say ready. One side alone is half an answer.
- Three rounds without agreement writes `OPEN DISAGREEMENT` into the plan,
  marks it `BLOCKED — NEEDS DYLAN`, and exits non-zero. Neither agent breaks
  the tie.
- Rejecting a concern requires a reason. "Disagree" on its own does not count.

Each round spends Dylan's Codex quota, which is why it is on request only.

## Who builds what

Once a plan is `READY TO SHIP` it gets a `## Tasks` section, and nothing is built
before it has one. Each task names an owner, the files it may touch, what it
waits on, and a ground for its owner:

    ## Tasks

    - [ ] **T1** · codex · files: `agent.py`, `tests/test_agent.py`
      Why codex: self-contained
      Add a press action to the closed vocabulary.
      Done when: pytest -q passes and a press action validates.

    - [ ] **T2** · claude · after: T1 · files: `extension/background.js`
      Why claude: needs-browser
      Wire press into the loop and watch it fire on a real page.

    python planloop/planloop.py tasks <slug>       # the split, and whether it holds
    python planloop/planloop.py run <slug> T1      # hand a codex task to Codex
    python planloop/planloop.py done <slug> T1     # tick it off

**One file, one owner.** Two agents editing the same file means the second to
finish overwrites the first and neither notices, so `tasks` refuses a split that
does it. It also refuses a task that declares no files, a dependency on a task
that does not exist, and a task that waits on itself. `run` bounds Codex to the
files its task declared; anything else it touches is put back, the same way a
review round is bounded to the plan folder.

**Ownership is argued from the harness, never from which model is better.** There
is no trustworthy head-to-head data on `gpt-6-astra` against Claude Opus 5 for
this work, so neither agent may claim the interesting half on that basis, in
either direction. The grounds are a closed list and anything else is refused:

`needs-browser`, `needs-sandbox`, `self-contained`, `needs-judgement`,
`sole-owner`, `follows-on`, `cross-cutting`, `either-could`.

`either-could` is the honest answer when no ground applies, and three of them
landing on one side is reported. The split is then part of what Codex reviews —
it may move any task whose ground does not hold, and say so. Claude drafting the
division and Codex being able to overturn it is what keeps it fair; a strengths
table written by one of the two would not.

## What this project is

A Chrome extension that reads the assignment page a student already has open,
and works through it one step at a time. It observes (screenshot + interactive
elements), decides one action via a model, acts, then looks again.

`ARCHITECTURE.md` is the map. Read it before changing the loop.
`CONTEXT_BROWSER_USE.md` compares our design to browser-use and lists what is
worth taking. `AGENTIC_PLAN.md` is historical. The current approved implementation
is `plans/question-coverage/PLAN.md`; its execution notes record Dylan's direct
authorization for Codex to own all tasks instead of the provisional split.

- `extension/` — the Manifest V3 extension. `background.js` owns the loop and
  every limit on it; `content.js` runs in the page and is the only thing that
  touches the DOM.
- `agent.py` — the decide step: observation in, one validated action out.
- `app.py` — FastAPI backend on Railway. Holds the API key. The extension never
  does, because anything shipped to a browser is readable by whoever installs it.
- `frontend/`, `adapters.py`, `runner.py` — the older selector-driven path, kept
  as a fallback. Not on the extension's code path.
- `deploy-source/` — **generated**, a copy made for Railway uploads. Never edit
  it directly and never commit it.

## Before you push

    pytest -q          # must stay green, no network and no API key needed

Deploy the backend with:

    cd deploy-source && railway up --ci --project 6195f77e-b5c7-4a03-b554-8b1e4e848474 \
      --environment 7c66aa24-8b5d-41cf-b41d-508dfc5a096a --service 50fe1453-47fb-46c0-b0bd-c007c5201f98

Bump `extension/manifest.json` version on any extension change, so Dylan can
tell whether Chrome actually reloaded it. It silently keeps the old build
otherwise, and he has lost an hour to that already.

## Things learned the hard way

Do not undo these without a reason, and add to the list when you find another.

- **Prompt instructions are suggestions; harness rules are rules.** Anything
  that must not happen is enforced in code. The read-check gate, the gated
  hand-in policy, and the action vocabulary are all enforced server-side
  or in the page, never by asking the model nicely. Each was tried the polite
  way first and each failed.
- **Hand-in changed in v0.6.0 by Dylan's explicit instruction.** Do not restore
  a blanket refusal. The hand-in switch defaults off. A terminal action needs
  every known part verified, every discovered part tab inspected, and no
  unplanned visible answer controls. A model claiming completion is insufficient.
  Verification means the intended value is present, not that it is academically
  correct. Unknown/closed-root controls may still require manual completion.
- **Worktree for question coverage:** `C:/Users/falay/assignment-agent-question-coverage`
  on `codex/question-coverage`. The original checkout has a pre-existing rebase;
  Codex deliberately did not resolve or overwrite it.
- **Never swallow an error.** `captureVisibleTab` failed silently for a day and
  the agent answered coursework with no screenshot at all. If something degrades
  the run, say so in the log, loudly, once.
- **A wrong coordinate is worse than none.** Where a frame offset cannot be
  measured through every ancestor, report no position rather than a partial one.
- **Token budgets bite twice.** Both this repo and `../model-eval` had replies
  cut off mid-JSON by a max_tokens set before the prompt grew. A truncated reply
  must say it was truncated, not look like a broken model.
- **Verify against the running thing, not the diff.** Several fixes looked right
  and were not: a regex with single backslashes in a JS string matched nothing
  while appearing correct.
- **Secrets:** `.env`, `data/` and logs are gitignored and must stay that way.
  There are tests asserting the key never reaches a response body or the
  database. Do not weaken them.

## Dylan

Not a programmer. Explain what changed and why it matters, in plain language.
Give him one clear next action, not a menu. He is running this on his own
coursework, so a silent wrong answer costs him marks — prefer stopping and
saying so over guessing.
