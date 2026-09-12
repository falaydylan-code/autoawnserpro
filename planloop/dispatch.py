"""Handing one agreed task to Codex, bounded to the files that task declared.

Reviewing a plan and building from it are different jobs, so they get different
instructions. This is the building one.
"""

from __future__ import annotations

IMPLEMENT_PROMPT = """You are Codex, implementing one task from a plan that you and Claude
already reviewed and agreed on. Dylan does not write code, so what you build is what ships.

Read `AGENTS.md` first, especially "Things learned the hard way". Every line of
that list is a mistake this repository has already paid for.

## Your task: {task_id}

{detail}

## The only files you may change

{file_list}

Anything you touch outside that list is put back automatically, so do not try.
Claude owns the other files and may be editing them right now.

## Before you finish

- `pytest -q` must pass. If the change needs a test, write it.
- Never swallow an error. A failure has to say what happened and what to do.
- Enforce anything that must not happen in code, not by instructing a model.
- Do not guess a value where having none is safer.

Reply with what you changed, what you verified, and anything the next agent
needs to know.

---

## The agreed plan, for context

{plan}
"""


def build_task_prompt(task: dict, plan_text: str) -> str:
    detail = "\n".join(task["detail"]) or "(No detail was written for this task.)"
    files = "\n".join(f"- `{path}`" for path in task["files"]) or "- (none declared)"
    return IMPLEMENT_PROMPT.format(
        task_id=task["id"], detail=detail, file_list=files, plan=plan_text
    )
