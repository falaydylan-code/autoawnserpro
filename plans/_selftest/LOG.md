# Review log — Speed up the agent by calling OpenRouter from the extension

Oldest first. One entry per round, from each side.

## Round 1 — codex — 2026-09-11 22:02

**Verdict:** changes_needed

Review stopped because the workspace contains uncommitted files I did not create: planloop/, plans/, and tests/test_planloop.py. AGENTS.md explicitly requires stopping in this situation. The proposed approach also conflicts with the documented architecture: it exposes the provider key, removes server-side validation, and allows silent screenshot failure. Source-level review remains incomplete.

**Concerns:**
- **Existing uncommitted work blocks editing.** — The working agreement requires stopping to avoid interfering with another agent's work. Suggested: Confirm that I may edit plans/_selftest/PLAN.md and append HANDOFF.md while preserving the other uncommitted files.
- **The plan puts the provider key in the extension and replaces code validation with prompt instructions.** — Browser-shipped keys are readable, and prompt instructions cannot enforce the action vocabulary. Suggested: Keep provider calls and action validation on the backend; measure latency before choosing an optimization.
- **Screenshot failures are silently tolerated, and verification covers only one successful answer.** — The agent could answer coursework without its source of truth, while failure paths remain unchecked. Suggested: Require visible screenshot failure handling and verification of invalid actions, truncation, budgets, and secret isolation alongside a live run.

**Questions for Claude:**
- May I proceed with the plan review and required handoff entry while preserving the existing uncommitted work?

**Reverted — changed outside this plan's folder:**
- planloop/
- plans/
- tests/test_planloop.py
