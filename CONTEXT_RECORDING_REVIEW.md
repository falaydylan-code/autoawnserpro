# Claude in Chrome recording review — September 11, 2026

Original review status: observations and proposed backlog only. The review itself changed no code.

Implementation update (0.6.0): staged drag fallbacks, independent drop verification,
part tracking, and gated submission are now implemented. See HANDOFF.md for actual
checks and remaining site validation; this recording is not a test of our code.

Source: C:/Users/falay/Videos/Screen Recordings/Screen Recording 2026-09-11 112346.mp4 (77.83 seconds). Inspected locally using extracted frames at five-second intervals. No external upload or model call. Audio was not transcribed. Times below are approximate sampling windows; quick intermediate gestures may be absent.

## Observed sequence

- Start: McGraw Hill accounting matching practice, three descriptions to pair with Cash, Accounts Receivable, and Deferred Revenue. User asks to complete this singular practice question.
- Around 15–25 seconds: sidebar shows Capturing page, Clicking, Capturing page, Dragging. Same-period collections description is visibly placed against Accounts Receivable, which is an incorrect pairing.
- Around 30–40 seconds: that description moves to Cash. Sidebar shows further captures and drags. A visible browser_batch group contains two Dragging actions and Capturing page. This proves grouped tools are exposed, not how many model calls occurred.
- Around 40–55 seconds: advance collections appears at Deferred Revenue; later the prior-to-collections description temporarily occupies that row, then moves to Accounts Receivable. There are intermediate wrong placements followed by corrections. Cannot tell whether their cause is reasoning, targeting, or widget behavior.
- Around 60–65 seconds: all three intended matches are present and confidence submission buttons are enabled.
- Around 70–77 seconds: page displays Your Answer correct, with three green checks. Claude reports success and stops, offering to continue because the request was only one question. Sidebar shows 21 steps; this does NOT establish 21 paid model calls.

The sidebar reveals tool activity and short status summaries, not full private reasoning or proprietary implementation. The Chrome debugger banner alone does not establish the exact input implementation.

## Comparison with inspected local autoawnserpro checkout

- agent.py ACTIONS contains read_check, fill, click, select, scroll, done, give_up; no drag, source/destination targets, or batch schema.
- extension/content.js uses element.click(), input/change events, and native select values. Its animated pointer is visual feedback, not a general mouse-down/move/mouse-up executor.
- Current screenshots and waitForEffect already implement part of observe/act/observe. Preserve this foundation.
- agent.py receives the latest screenshot and last-action summary, with no explicit retained answer plan or per-match completion ledger.
- content.js digest uses page text and input values. This is not proof that the intended item landed in the intended target; some positional changes may not affect the digest.
- background.js sets answered=true after any successful fill/click/select. This is not equivalent to completing all parts of a multi-part question.
- read_check has_question=true resets counters and increments question count, including rechecks. A stable question identity should distinguish within-question changes from a new question.
- Per-question action budget is 16. Claude's visible 21 steps include captures, so it is invalid to conclude directly that our budget would fail this recording. Budgets should reflect measured progress and separately cap stalls, spend, and total actions.
- Screenshot failures currently continue text-only with a warning. Visual interaction tasks need an explicit pause/retry when essential visual evidence is unavailable.

## Proposed priorities (not implemented)

1. Add validated drag source/destination actions and an executor that supports the actual courseware widgets, including moving an already placed item. Verify source and target after every move; remeasure after layout changes. Evaluate browser input mechanisms with a local reproduction before choosing implementation.
2. Represent a whole multi-part answer as intended pairings, current observed pairings, remaining items, and mismatches. Keep this compact state across turns; still require a fresh page observation before acting.
3. Add semantic verification: item X is inside target Y; all required targets are filled; submission is enabled; graded feedback confirms acceptance/correctness when available. Separate action executed, answer entered, question submitted, and answer graded.
4. Recover locally from a wrong placement, refreshing targets and changing the action instead of looping or restarting the entire question. Pause on repeated nonprogress with a clear reason.
5. Add stable question identity and progress-aware budgets. Do not reset state/count a new question merely because a drag changed the page.
6. Only after individual actions are reliable, allow small sequential batches with intermediate assertions and abort on unexpected layout/state changes. Never batch blindly across question transitions.
7. Persist readable action traces, timestamps, model-call counts/costs, intended and observed outcomes, and optional screenshots for diagnosis. User-facing examples: Matched 2 of 3; corrected placement; submitted; page marked correct.
8. Add a local regression fixture resembling this three-pair matching widget with reflow, wrong-drop recovery, disabled-until-complete submission, and graded feedback. Measure model answer correctness separately from interaction success, recovery rate, time, and actual cost.

Conclusion: this recording provides strong evidence for improving interaction coverage, state tracking, and outcome verification. It does not establish comparative model accuracy, Claude's private harness design, or MiniMax's ability to equal this result. Evaluate MiniMax after providing the missing tools and the same task.
