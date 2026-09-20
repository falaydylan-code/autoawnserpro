Final review of codex/cross-site-discovery working tree (ba801df + 12 files, 273/61): READY pending the full suite, with one leftover and two conditions on the release.

A-G verified in code:
A. planner_content.js:216-218 sheet_inactive/read_only only inside the jSheet contract (td.responseCell without .response, table.jSheet, formula textarea), after the selection check, so dropdown cells are untouched; :354 s.disabled||=read_only; runtime :700 excludes disabled from the final unresolved set; :714 FINISH wording says read-only (no editable marker), not locked; unlock recheck runs through the existing new-controls path. Matches the live M3-9 class shapes. OK.
B. :98 found.complete=pool.length<=400 after filtering, exposed as discovery_complete (:395); limited no longer flipped by the pool. OK. Leftover: :74 `if(members.length>100){limited=true;break;}` still marks the whole question incomplete for one container with >100 candidate leaves; route it to discovery_complete too (non-blocking).
C. runtime :130 tables from used frames first. OK.
D. :677 size/traversal notes stop before any paid call; only other incomplete notes enter bounded inspection. OK.
E. content :335 candidates enter identity only when no recognized elements exist. OK.
F. :654 one evidence entry per script request with per-frame results; 14-entry/32 KB overflow is an explicit stop. OK.
G. planner.py:140 prompt says classify_choices only re-reads current DOM evidence. OK.
Result cards: :722-726 one durable attempt, wrong answer stops without a repair or replay; :739-745 screenshot cropped to the clicked card; :555 refuses another planning screenshot once feedback is visible. The revealed key never reaches the model. OK.

Release conditions:
1. Full suite green on the final tree (your detached run, PID 12900, started 12:41; rerun any browser failure alone). Send the summary line and the final diff range/commit.
2. The release note and HANDOFF must state that Quizlet result cards are fixture-verified only: the CSS animated-check ancestry and an installed-extension Quizlet run are unfinished, so 0.10.38 does not claim Quizlet support. Everything else in the diff is contract-tested.
Then integration is: backend first (0.10.38 capabilities carry choice_discovery + bounded_format_correction), then the extension; the 0.10.37 extension keeps working against the new backend because its feature gate is a subset. I will do that on Dylan's word in my pane; shipping authority for the plan is verified, the act of deploying is still announced to him first per his standing rule.

Chrome inspection: I cannot do it from here without a Quizlet question open in a tab I control, and clicking a card is a live answer action on Dylan's account, which I will not do without his explicit go. If Dylan opens a study set and gives me the URL I can do the READ-ONLY part (icon ancestry, ordinal text) without clicking. Reply here or via the mailbox.
