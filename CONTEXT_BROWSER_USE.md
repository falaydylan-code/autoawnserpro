# Reference: what browser-use does, and where we differ

**Implementation update (0.6.0):** The historical notes below predate the changes.
Grouped observations, NEW markers, screenshot reference badges and explicit part
tracking are now implemented. Browser-use itself is not installed; action batching
is not implemented. See HANDOFF.md for verification and remaining site checks.

Notes on https://github.com/browser-use/browser-use, read on 2026-09-11 from its
own system prompt and DOM serializer. Kept as **context only** — nothing here has
been implemented. It is the most mature open-source version of the loop we are
building, so it is worth knowing where they landed differently.

Fetched from:
- `browser_use/agent/system_prompts/system_prompt.md`
- `browser_use/dom/serializer/serializer.py`, `clickable_elements.py`

---

## 1. The page is a tree, not a list

They serialise interactive elements as indented XML, so structure survives:

    [33]<div />
        User form
        [35]<input type=text placeholder=Enter name />
        *[38]<button aria-label=Submit form />
            Submit

Indentation means parent/child. Text content sits as child lines. Only elements
with `[index]` are interactive.

**We send a flat list.** Every element is a sibling as far as the model can
tell. That is why blanks looked interchangeable until we added the words either
side of each one — we were reconstructing by hand what a tree gives for free.
For a table of six answer boxes, or radios belonging to two different questions
on one page, a tree is strictly better.

## 2. New elements since the last step are starred

`*[38]` means that element appeared since the previous step. The prompt tells the
model its own last action probably caused it, and to consider whether it needs
interacting with — an autocomplete dropdown, a validation message, a modal.

**We have nothing like this.** We tell the model only whether the page changed,
not *what* changed. This is cheap to add and would have helped on every
confidence-rating screen.

## 3. Indices are drawn on the screenshot

`<browser_vision>` is a screenshot with bounding boxes and index labels painted
onto it. The model reads `[35]` off the image directly.

**We send a clean screenshot plus a separate list of coordinates** and ask the
model to correlate the two. Drawing the index on the pixels removes that join
entirely, and would make our frame-offset work unnecessary — the label is
wherever the element actually is.

## 4. Real memory between steps

Every step carries an explicit history:

    <step_3>
    Evaluation of Previous Step: ...
    Memory: ...
    Next Goal: ...
    Action Results: ...
    </step_3>

And each reply must contain `evaluation_previous_goal`, `memory`, `next_goal`,
plus an optional `plan_update` todo list and `current_plan_item` pointer.

**We added a single carried `plan` string per question.** That fixed the
re-deriving problem, but it is one field where they have a running log, an
explicit verdict on whether the last action worked, and a plan the model can
revise. Their `memory` examples are worth copying almost verbatim: *"Previous
click on search button failed — page did not change. Will try pressing Enter in
the search field instead."*

## 5. Several actions per step

`"action": [ {...}, {...} ]` — a list, never empty. They encourage sensible
combinations, and the list stops early if the page changes underneath it.

**We do one action per turn.** For a three-blank question that is three model
calls where they would spend one. This is the batching change already discussed
and deliberately deferred.

## 6. Verification is mandatory before finishing

The prompt requires an explicit verification pass before `done(success=true)`,
and the critical reminders are blunt:

- always verify success from the screenshot before proceeding
- always handle popups, modals and cookie banners first
- never repeat a failing action more than 2-3 times, try something else
- never assume success

**We verify per action** (read the value back) which they do not, and we have a
repeat limit. We lack the "check the whole answer before submitting" pass.

## 7. Shadow DOM

Elements inside shadow DOM get normal `[index]` markers and are clicked the same
way. The prompt explicitly forbids reaching for `evaluate` to click them.

**We never traverse shadow DOM at all.** `querySelectorAll` does not cross a
shadow boundary, so any courseware using web components is invisible to us
today. Worth checking whether McGraw-Hill or D2L do.

---

## What to consider taking, in order of value

1. **Draw indices on the screenshot.** Removes the list-to-picture join, and
   makes frame offsets moot.
2. **Star what is new since the last step.** Cheap, and directly useful on pages
   that reveal a control after an answer.
3. **Serialise as a tree rather than a flat list.** Structure for free.
4. **Grow `plan` into a running memory** with a verdict on the last action.
5. **Traverse shadow DOM** — check first whether the target sites need it.
6. **Batch actions** — biggest cost saving, most new failure modes.

## What we do that they do not

- Refuse hand-in controls in the page itself rather than by prompt.
- Never describe credential or payment fields to the model at all.
- Read every value back after typing it.
- Closed action vocabulary validated server-side before anything executes.
- Per-network spend metering.

Their agent is built to browse anything; ours is built to be safe on a student's
own signed-in coursework. Where the two conflict, ours should stay stricter.
