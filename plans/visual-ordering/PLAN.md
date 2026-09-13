> Release follow-up (2026-09-13): Codex resumed Claude's completed implementation,
> verified the live protocol-2 backend and prepared publication to awnseragent2.0.
> Extension 0.7.1 corrects a visual guard that treated unrelated Submit text as
> the clicked control. Actual Connect iframe dropdown markup was inspected; full
> live agent validation remains open. See the newest HANDOFF entry.

> Execution update — 2026-09-12: Dylan authorized Codex to implement this plan
> directly on `codex/visual-ordering`. Codex completed sections 1–4 and the
> fixtures and tests of section 5, then hit its usage limit at the end of the
> smoke script. Claude picked it up from that line: verified the snapshot
> (152 tests green as left), added the four failure-mode tests the plan names
> that were missing — which found that a Stop arriving mid-drag would have
> *completed* the drop instead of abandoning it (fixed: cancelled gestures
> release at their origin) — added the sidebar explanation of the debugger
> permission, ran the MiniMax smoke checks, deployed the protocol-2 backend,
> and recorded the result in `HANDOFF.md`. No joint review round was run;
> this plan was executed on Dylan's direct instruction.
>
> Not done: the McGraw Hill validation in an accessible practice session
> (needs Dylan's login) and publication to `awnseragent2.0` (no remote for it
> exists on this machine; the work is on `codex/visual-ordering` in
> `autoawnserpro`).

# Support ordering questions and custom dropdowns

## Summary

Fix two distinct failures while keeping MiniMax and the existing extension/backend architecture:

- Ordering: The agent currently treats "inside the list" as equivalent to "in the correct position."
- Dropdowns: The agent can read the table in a screenshot but cannot act because the dropdowns have no usable
  control references. The log does not prove they use closed shadow roots.

Use page controls when available, with the screenshot-based fallback Dylan selected. Keep the parts checklist, but
verify each question using evidence appropriate to its controls.

## 1. Discover and operate custom dropdowns

- Inspect the affected McGraw Hill table before implementing selectors. Determine whether the missing controls
  are ordinary custom elements, shadow content, or embedded frames.
- Expand discovery to include focusable custom triggers and menu-opening attributes. Associate each trigger with
  its table row, column, current value, and stable identity.
- Separate opening a dropdown from answering it. Opening the menu is a permitted preparatory action; it must not
  complete the part.
- After opening, observe again, discover the visible options, select the intended option, then verify the value
  displayed in the original cell.
- Preserve all 20 planned parts. Bind previously missing references as controls become available without
  recreating or losing completed parts.

## 2. Add screenshot-based input and verification

- Add Chrome's debugger permission and a bounded browser-input adapter using CDP mouse events. Attach only to
  the active assignment tab when fallback is needed; detach on Stop, ETH off, completion, or failure. Explain
  Chrome's additional permission in the sidebar.
- Add visual_click and visual_drag actions tied to a planned part and the exact screenshot observation that
  produced them. The model supplies normalized screenshot coordinates; the extension converts them to viewport
  coordinates using recorded screenshot dimensions and viewport measurements.
- Reject stale coordinates after scrolling, resizing, navigation, or a detected page change. Recheck the active
  tab before every action.
- Limit visual actions to the identified answer area and its open menu. Keep submission and unrelated-control
  restrictions; do not use visual fallback to bypass blocked frames or sensitive fields.
- Capture a fresh screenshot after the action settles. Run a separate verification request that returns the
  observed cell value or ordered sequence, plus confirmed, mismatch, or uncertain.
- Compare the observed result against the stored plan. Never accept the acting model's claim of success as
  verification. If DOM and screenshot evidence disagree, reobserve; do not mark complete.
- Allow at most two recovery actions for an unchanged part before pausing with a specific explanation. Log the
  verification method and count all additional model costs.

## 3. Make ordering a distinct question type

- Represent an ordering answer as a list identity plus an ordered sequence of stable item identities — not three
  matching pairs pointing to the same container.
- Observe current item positions using ordering metadata and rendered geometry. Preserve duplicate labels
  through distinct item identities.
- Add a reorder action: move a source item before or after another item within the same list. Use the widget's
  supported keyboard interaction when available; otherwise use browser drag input.
- Verify the entire resulting sequence after each move. Being inside the container never proves an item is
  correctly positioned.
- If the sequence already matches the plan, verify it without dragging. If the page still requires an
  interaction before continuing, inspect its available controls; do not invent a no-op drag or claim the answer
  was registered.
- Use screenshot verification when the list's order cannot be read reliably from page elements.

## 4. Update the backend and extension contract together

- Extend request and response types for ordering plans, screenshot observation IDs, visual coordinates, and
  verification evidence. Retain existing parts and actions for ordinary questions.
- Update MiniMax's instructions with examples for opening custom dropdowns, filling table cells, reordering
  items, and recognizing already-correct answers.
- Add a verification phase that permits reporting observed state but cannot issue browser actions.
- Treat invalid model actions as recoverable: return explicit corrective feedback once, preserving the plan and
  accounting for both calls. Configuration and authentication failures still stop immediately.
- Add /api/capabilities with a protocol version and supported features. The extension checks compatibility
  before its first paid call.
- Separate general observation notices from evidence that required controls are missing. A generic custom-
  element warning must not permanently block submission after every required part has been verified.
- Fix copied logs to retain the original run's tab and URL; switching to GitHub or Chess.com must not relabel
  the assignment run.

## 5. Tests and rollout

- Dropdown tests: A 10-row, two-column table; unlabeled custom triggers; menus rendered outside their cells;
  closed-shadow fixture; and selection that fails to persist. Confirm opening a menu does not count as
  answering.
- Ordering tests: Shuffled lists, already-correct lists, duplicate labels, pointer-only widgets, and visual
  order differing from DOM order. Confirm container membership cannot falsely pass verification.
- Fallback tests: Browser zoom, display scaling, scroll changes, stale screenshots, tab switches, debugger
  attachment failure, Stop during a drag, and conflicting visual/DOM evidence.
- Backend tests: New fields survive parsing, verification cannot execute actions, malformed moves get useful
  feedback, older backends fail compatibility checks without spending credit, and retry/verification costs are
  included.
- Run the full regression suite, then MiniMax through a loaded extension against the representative fixtures.
- Validate both reported McGraw Hill question types in an accessible practice session. Without that session,
  report fixture success separately and leave site acceptance pending.
- Publish the tested changes to awnseragent2.0, deploy the matching Railway backend, verify its capabilities,
  and release extension version 0.7.0. Refresh both the extension and assignment page before testing.

## Assumptions

- Screenshot fallback is enabled as selected; no new paid browser service or model is introduced.
- Existing submission settings remain authoritative.
- Verification establishes that the planned answer is visibly entered — not that its academic content is correct.
- Review and preserve any concurrent Claude changes before implementation.
