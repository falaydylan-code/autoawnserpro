"""The task commands: list the split, hand a task to Codex, tick one off.

Kept apart from planloop.py so the driver stays about the review loop and this
stays about the work that follows it.
"""

from __future__ import annotations

import os
import subprocess

import tasks as tasklib
from dispatch import build_task_prompt


def load_tasks(driver, slug: str) -> list[dict]:
    plan = driver.plan_dir(slug) / "PLAN.md"
    if not plan.exists():
        driver.fail(f"No plan at plans/{slug}/PLAN.md.")
    return tasklib.parse_tasks(plan.read_text(encoding="utf-8"))


def cmd_tasks(driver, slug: str) -> None:
    items = load_tasks(driver, slug)
    if not items:
        driver.fail(
            f"plans/{slug}/PLAN.md has no Tasks section yet. "
            "Split the work before anyone starts building."
        )

    done = sum(1 for task in items if task["done"])
    print()
    print(f"  plans/{slug} - {done} of {len(items)} done")
    print()
    for line in tasklib.summarise(items):
        print(line)

    problems = tasklib.validate_split(items)
    if problems:
        print()
        print("  Problems with the split:")
        for problem in problems:
            print(f"   - {problem}")
        raise SystemExit(1)
    print()


def cmd_run(driver, slug: str, task_id: str) -> None:
    """Hand one Codex-owned task to Codex, bounded to the files it declared."""
    items = load_tasks(driver, slug)
    wanted = task_id.upper()
    task = next((t for t in items if t["id"] == wanted), None)

    if not task:
        driver.fail(f"No task {wanted} in plans/{slug}/PLAN.md.")
    if task["done"]:
        driver.fail(f"{wanted} is already done.")
    if task["owner"] != "codex":
        driver.fail(
            f"{wanted} belongs to claude. This command only dispatches Codex-owned work; "
            "Claude does its own."
        )

    problems = tasklib.validate_split(items)
    if problems:
        driver.fail("Fix the split before building:\n   - " + "\n   - ".join(problems))

    finished = {t["id"] for t in items if t["done"]}
    waiting = [d for d in task["after"] if d not in finished]
    if waiting:
        driver.fail(f"{wanted} waits on {', '.join(waiting)}, which is not finished.")

    work_dir = driver.plan_dir(slug) / "work" / wanted.lower()
    work_dir.mkdir(parents=True, exist_ok=True)

    baseline = driver.changed_files()
    plan_text = (driver.plan_dir(slug) / "PLAN.md").read_text(encoding="utf-8")
    prompt = build_task_prompt(task, plan_text)
    (work_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    result_path = work_dir / "result.md"

    print()
    print(f"  {wanted} - handing to Codex, bounded to: {', '.join(task['files'])}")
    print("  It writes real code, so this takes a few minutes.")
    print()

    command = [
        driver.codex_binary(), "exec",
        "--sandbox", "workspace-write",
        "-C", str(driver.REPO),
        "--skip-git-repo-check",
        "--color", "never",
        "-o", str(result_path),
        "-",
    ]
    try:
        run = subprocess.run(
            command, input=prompt, text=True, capture_output=True,
            timeout=driver.ROUND_TIMEOUT, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        driver.fail(f"Codex did not finish {wanted} within {driver.ROUND_TIMEOUT}s.")

    (work_dir / "codex-stdout.txt").write_text(
        (run.stdout or "") + (run.stderr or ""), encoding="utf-8")

    allowed = list(task["files"]) + [f"plans/{slug}/"]
    strays = driver.enforce_boundary(slug, baseline, work_dir, allowed=allowed)

    summary = result_path.read_text(encoding="utf-8").strip() if result_path.exists() else ""
    print("  " + (summary[:700] if summary else "Codex returned no summary."))
    print()
    if strays:
        print("  Changed files outside this task, and put back:")
        for path in strays:
            print(f"   - {path}")
        print()
    print(f"  Read the diff, run pytest, then: planloop.py done {slug} {wanted}")
    print()


def cmd_done(driver, slug: str, task_id: str) -> None:
    plan = driver.plan_dir(slug) / "PLAN.md"
    if not plan.exists():
        driver.fail(f"No plan at plans/{slug}/PLAN.md.")

    text, changed = tasklib.mark_done(plan.read_text(encoding="utf-8"), task_id)
    if not changed:
        driver.fail(f"No unfinished task {task_id.upper()} in plans/{slug}/PLAN.md.")
    plan.write_text(text, encoding="utf-8")

    items = tasklib.parse_tasks(text)
    left = [task for task in items if not task["done"]]
    print()
    print(f"  {task_id.upper()} done. {len(left)} left.")
    for task in tasklib.ready_tasks(items):
        print(f"   ready now: {task['id']} ({task['owner']})")
    print()
