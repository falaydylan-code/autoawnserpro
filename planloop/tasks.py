"""Splitting an agreed plan into work, and keeping each agent inside its own.

Once Claude and Codex both call a plan ready, it needs to say who builds what.
Tasks live in the plan itself, as a checklist:

    ## Tasks

    - [ ] **T1** · codex · files: `agent.py`, `tests/test_core.py`
      Why codex: self-contained
      Add a press action to the closed vocabulary.
      Done when: pytest -q passes and a press action validates.

    - [ ] **T2** · claude · after: T1 · files: `extension/background.js`
      Why claude: needs-browser
      Wire press into the loop and confirm it fires on a real page.

The rule that actually keeps the two apart is one file, one owner. Two agents
editing the same file means the second to finish overwrites the first, and
neither of them will notice.

## Why every task has to name a ground

The obvious way to divide work is "give each model what it is better at", and
nobody here can honestly do that. There is no trustworthy head-to-head data on
`gpt-6-astra` against Claude Opus 5 for this repository's work, so any table of
strengths would be invented, and a model inventing reasons to keep the
interesting half is the exact failure this is meant to prevent.

So ownership is argued from things that can be checked instead: which harness
the task needs, which files it touches, what it depends on. `GROUNDS` is that
closed list. A task whose real answer is "either of us could do this" says so
with `either-could`, which makes the balance visible rather than hiding it
behind a confident-sounding claim.

The split is then put through a Codex review round like the rest of the plan, so
the other side gets to move tasks it thinks were assigned wrongly. That is the
part that makes it fair -- not this module's opinion.
"""

from __future__ import annotations

import re

# Reasons a task may be assigned, and what each one asserts. Deliberately about
# the work and the harness, never about which model is cleverer.
GROUNDS = {
    "needs-browser": "requires driving a real Chrome tab and reading a live page",
    "needs-sandbox": "requires a long autonomous edit loop in the workspace sandbox",
    "self-contained": "one clear change with a mechanical done-when and nothing to ask Dylan, so it is safe to hand to a non-interactive run",
    "needs-judgement": "the done-when cannot be made mechanical; someone has to look at the result and may have to ask Dylan",
    "sole-owner": "these files are already this agent's in another task; splitting them would break one-file-one-owner",
    "follows-on": "continues a task the same agent holds, so handing it over would lose the context",
    "cross-cutting": "changes a contract across several files and needs whoever designed the surrounding part",
    "either-could": "no ground favours either side; assigned to balance the load",
}

WHY_LINE = re.compile(r"^why\s+(?P<owner>codex|claude)\s*:\s*(?P<ground>[a-z-]+)", re.IGNORECASE)

TASK_LINE = re.compile(
    r"^- \[(?P<done>[ xX])\]\s*\*\*(?P<id>T\d+)\*\*"
    r"\s*·\s*(?P<owner>codex|claude)"
    r"(?:\s*·\s*after:\s*(?P<after>[^·\n]*))?"
    r"(?:\s*·\s*files:\s*(?P<files>[^·\n]*))?"
    r"\s*$",
    re.IGNORECASE,
)

OWNERS = ("codex", "claude")


def parse_tasks(plan_text: str) -> list[dict]:
    """Read the checklist. Indented lines under a task are its detail."""
    tasks: list[dict] = []
    for raw in plan_text.splitlines():
        stripped = raw.strip()
        match = TASK_LINE.match(stripped) if stripped.startswith("- [") else None
        if match:
            files = [f.strip().strip("`") for f in (match["files"] or "").split(",") if f.strip()]
            after = [a.strip().upper() for a in (match["after"] or "").split(",")
                     if a.strip() and a.strip().lower() not in ("none", "-")]
            tasks.append({
                "id": match["id"].upper(),
                "owner": match["owner"].lower(),
                "done": match["done"].lower() == "x",
                "files": files,
                "after": after,
                "ground": "",
                "why_owner": "",
                "detail": [],
            })
        elif tasks and raw[:1] in (" ", "\t") and stripped:
            why = WHY_LINE.match(stripped)
            if why and not tasks[-1]["ground"]:
                # Kept out of `detail` so the first detail line is still the
                # description of the work.
                tasks[-1]["why_owner"] = why["owner"].lower()
                tasks[-1]["ground"] = why["ground"].lower()
            else:
                tasks[-1]["detail"].append(stripped)
    return tasks


def validate_split(tasks: list[dict]) -> list[str]:
    """Everything that would have the two agents tread on each other."""
    problems: list[str] = []
    ids = [t["id"] for t in tasks]

    for task in tasks:
        if not task["files"]:
            problems.append(
                f"{task['id']} declares no files, so nothing bounds what it may edit.")
        for dependency in task["after"]:
            if dependency not in ids:
                problems.append(
                    f"{task['id']} waits on {dependency}, which is not a task in this plan.")

    problems.extend(_grounds(tasks))
    problems.extend(_balance(tasks))

    owners: dict[str, set[str]] = {}
    for task in tasks:
        for path in task["files"]:
            owners.setdefault(path, set()).add(task["owner"])
    for path, who in sorted(owners.items()):
        if len(who) > 1:
            problems.append(
                f"`{path}` is owned by both {' and '.join(sorted(who))}. Give a file one "
                "owner, or whoever finishes second silently overwrites the first.")

    for identifier in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"{identifier} is used more than once.")

    problems.extend(_cycles(tasks))
    return problems


def _grounds(tasks: list[dict]) -> list[str]:
    """Every task must argue its owner from the closed list, and argue it for
    the owner it actually has."""
    problems = []
    for task in tasks:
        if not task["ground"]:
            problems.append(
                f"{task['id']} gives no reason for belonging to {task['owner']}. Add a "
                f"`Why {task['owner']}: <ground>` line, one of: {', '.join(sorted(GROUNDS))}.")
            continue
        if task["ground"] not in GROUNDS:
            problems.append(
                f"{task['id']} claims the ground `{task['ground']}`, which is not one of: "
                f"{', '.join(sorted(GROUNDS))}. A new ground has to be argued in the plan "
                "and agreed, not invented in a task line.")
        if task["why_owner"] != task["owner"]:
            problems.append(
                f"{task['id']} is owned by {task['owner']} but the reason is written for "
                f"{task['why_owner']}. One of the two is a slip, and the wrong agent would "
                "be handed the work.")
    return problems


def _balance(tasks: list[dict]) -> list[str]:
    """`either-could` work landing entirely on one side is the thing to catch.

    Tasks with a real ground belong where they are, however lopsided that looks.
    Tasks with no ground either way are the ones a self-interested split would
    quietly keep, so those are counted separately.
    """
    open_choice = [t for t in tasks if t["ground"] == "either-could"]
    if len(open_choice) < 3:
        return []
    for owner in OWNERS:
        mine = [t["id"] for t in open_choice if t["owner"] == owner]
        if len(mine) == len(open_choice):
            return [
                f"All {len(open_choice)} tasks marked `either-could` went to {owner} "
                f"({', '.join(mine)}). Where no ground favours a side, the work is meant to "
                "be shared, or one of them has a ground nobody wrote down."
            ]
    return []


def _cycles(tasks: list[dict]) -> list[str]:
    """A task waiting on itself, directly or through others, never runs."""
    graph = {t["id"]: [d for d in t["after"]] for t in tasks}
    seen: set[str] = set()
    found: list[str] = []

    def walk(node: str, trail: list[str]) -> None:
        if node in trail:
            found.append(" -> ".join(trail[trail.index(node):] + [node]) + " waits on itself.")
            return
        if node in seen:
            return
        seen.add(node)
        for nxt in graph.get(node, []):
            if nxt in graph:
                walk(nxt, trail + [node])

    for task in tasks:
        walk(task["id"], [])
    return found


def ready_tasks(tasks: list[dict]) -> list[dict]:
    """Unfinished tasks whose dependencies are all done."""
    finished = {t["id"] for t in tasks if t["done"]}
    return [t for t in tasks
            if not t["done"] and all(d in finished for d in t["after"])]


def mark_done(plan_text: str, task_id: str) -> tuple[str, bool]:
    """Tick one task. Returns the new text and whether anything changed."""
    target = task_id.upper()
    out, hit = [], False
    for line in plan_text.splitlines():
        stripped = line.strip()
        match = TASK_LINE.match(stripped) if stripped.startswith("- [") else None
        if match and match["id"].upper() == target and match["done"].lower() != "x":
            line = line.replace("- [ ]", "- [x]", 1)
            hit = True
        out.append(line)
    return "\n".join(out) + "\n", hit


def summarise(tasks: list[dict]) -> list[str]:
    """Human-readable state, one line per task."""
    unblocked = {t["id"] for t in ready_tasks(tasks)}
    lines = []
    for task in tasks:
        state = "done   " if task["done"] else ("ready  " if task["id"] in unblocked else "blocked")
        headline = task["detail"][0] if task["detail"] else ""
        lines.append(f"  [{state}] {task['id']:>3}  {task['owner']:<6}  {headline[:58]}")
        if task["ground"]:
            lines.append(f"                        why:   {task['ground']}")
        if task["files"]:
            lines.append(f"                        files: {', '.join(task['files'])}")
        if task["after"] and not task["done"]:
            lines.append(f"                        after: {', '.join(task['after'])}")
    return lines
