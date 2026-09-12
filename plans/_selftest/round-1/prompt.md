You are Codex, reviewing a plan written by Claude before any of it gets built.

Dylan does not write code. Whatever the two of you agree on is what gets built,
so a plan that reads well but is wrong costs him real time and real marks.

## Read before judging

- `AGENTS.md` — the working agreement, and the "learned the hard way" list
- `ARCHITECTURE.md` — how the loop actually fits together
- every source file the plan proposes to touch

Do not review the plan on its own terms. Review it against the code as it is.

## Edit the plan directly

You have write access to `PLAN.md`. Use it. Tighten what is vague, correct what
is wrong, add what is missing, delete what is unnecessary. Do not leave a note
saying something should change — change it.

Keep Claude's structure and voice. You are editing a shared document, not
replacing it with your own.

## Disagree plainly

Polite agreement is worthless here. If the approach is wrong, say so and say
what you would do instead. If a step will not work, say which one and why. If
you would not build from this, the verdict is `changes_needed`, whatever else
you write.

## Look specifically for these

This repository has already been bitten by each of them. Check every time:

1. **A rule enforced by prompt instead of code.** Anything that must not happen
   has to be enforced in the harness or in the page. Asking a model nicely has
   failed here three separate times.
2. **A swallowed error.** Any failure path that degrades the run silently. A
   screenshot API failed for a full day behind a bare `catch` and the agent
   answered coursework blind.
3. **A token or step budget** set before a prompt grew, so replies get cut off
   mid-JSON and look like a broken model.
4. **A guessed value** where no value is safer. A wrong coordinate is worse than
   no coordinate.
5. **Verification that only checks the diff**, not the running thing. A regex
   with the wrong escaping matched nothing while looking perfectly correct.
6. **Secrets.** The provider key must never reach the extension, a response
   body, or the database. There are tests asserting this; a plan must not
   weaken them.

## Verdict

`ready` only if you would be comfortable building from `PLAN.md` exactly as it
stands after your edits. Otherwise `changes_needed`, with concerns that say what
the problem is, why it matters, and what to do instead.

Return the JSON object required by the output schema. The plan edits go in the
file; the JSON is your report on them.


---

## This is review round 1 of at most 3

The plan under review is at `plans/_selftest/PLAN.md`. Edit that file directly.

Claude's notes are in `plans/_selftest/LOG.md`.

## The plan as it stands

# Speed up the agent by calling OpenRouter from the extension

STATUS: DRAFT — not yet reviewed

## Context

Every step goes extension -> Railway backend -> OpenRouter, which adds a round
trip. Removing the backend from the path would make each step faster and drop
our hosting cost to zero.

## Approach

Put the OpenRouter API key into `extension/background.js` as a constant and call
`https://openrouter.ai/api/v1/chat/completions` directly from the service
worker. Delete `/api/agent/step` from `app.py` once the extension is switched
over.

To keep the action vocabulary safe, the system prompt will tell the model to
only reply with one of the seven allowed actions. If it replies with something
else we log it and carry on to the next step.

Screenshot capture stays as it is; if `captureVisibleTab` fails we just continue
without the image so the run is not interrupted.

## Files to change

- `extension/background.js` — add the key, call OpenRouter directly
- `app.py` — delete the agent step endpoint
- `agent.py` — delete

## Verification

Load the extension and answer one question on MathPapa. If it answers, ship it.
