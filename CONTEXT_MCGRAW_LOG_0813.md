# Live McGraw Hill failure — 0.8.0, 2026-09-13 14:47 (context for the next change)

A real Connect "Fill in the Blank" question (4 blanks: income / retained /
balance / cash). The model REASONED it correctly on step 1 and never entered a
single answer. 2 "questions", 12 steps, $0.036, stopped after 3 identical
refusals. What actually went wrong, in order of how much it mattered:

1. **The visual guard refuses the real answer fields.** Every `visual_click`
   aimed at a blank came back "Visual input cannot activate navigation,
   submission or sensitive controls." On this page the blanks sit inside a big
   Connect widget whose ancestors (or a same-labelled control) trip
   `visualGuard`'s nav/submission/sensitive/region checks. The guard is tuned to
   the fixtures, not to real courseware, and it is blocking the thing it should
   allow. This is the #1 fix.

2. **part_id churn breaks binding.** The model planned parts with ids
   `1,2,3,4`, then re-read as `blank1..blank4`, then acted with `part_id:"a"`
   and `"b"`. `resolvePart`/visual binding needs the action's part_id to match a
   planned part; when it does not, the harness answers "Visual input needs the
   part_id ... add the part in read_check first." The ids must be stabilised
   (the model changes them every read) or the harness must resolve a visual
   click to a planned part by position when the id does not match.

3. **Re-read fragmentation, again.** The ledger went from 4 parts to 8 (two
   questions) because the blanks have no DOM key (closed shadow, ref:null), so
   the "same controls = same question" identity has nothing to match on and a
   re-read forks a new question. Ref-less parts need an identity that is not the
   control key (question stem + blank index).

4. **The model re-reads instead of acting.** Half the steps were `read_check`
   re-planning the same answer it already had. With a plan in hand and refused
   actions, it falls back to reading rather than trying a different aim. The
   loop should push it to act, and a refusal should carry a coordinate hint.

5. **The closed-shadow warning fires every step** and mentions "a different-site
   frame is excluded" — noise that may also mean a needed frame is being
   dropped; worth confirming the blanks are in an excluded frame vs a closed
   shadow root.

Take-away for the redesign: on real Connect the blanks are reachable ONLY by
coordinate, so the visual path has to actually work end to end — a permissive-
but-safe guard, position-based part binding, and ref-less question identity.
The model's accounting reasoning was correct; the harness never let it type.
