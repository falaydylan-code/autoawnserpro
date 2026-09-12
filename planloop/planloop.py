"""Plan review loop: Claude drafts, Codex reviews, repeat until both agree.

The two agents cannot talk to each other, so the plan document is the
conversation and this script is the postman. It runs exactly one review round
per invocation; Claude revises in between, which cannot be scripted because
Claude is not a subprocess.

    python planloop/planloop.py new <slug> "Title"
    python planloop/planloop.py review <slug>
    python planloop/planloop.py status <slug>

Standard library only. The only external thing it needs is the `codex` binary,
which is already installed.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLANS = REPO / "plans"
SCHEMA = REPO / "planloop" / "review-schema.json"
PROMPT = REPO / "planloop" / "review-prompt.md"

MAX_ROUNDS = 3
ROUND_TIMEOUT = 900          # seconds; a hung review must not hang the session

CODEX_CANDIDATES = [
    r"C:\Program Files\OpenAI\Codex\bin\codex.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe"),
    "codex",
]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def fail(message: str) -> None:
    print(f"\n  {message}\n", file=sys.stderr)
    raise SystemExit(1)


def codex_binary() -> str:
    for candidate in CODEX_CANDIDATES:
        if candidate == "codex":
            found = shutil.which("codex")
            if found:
                return found
        elif Path(candidate).exists():
            return candidate
    fail("Could not find the codex CLI. Install it, or add it to PATH.")


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return result.stdout


def changed_files() -> set[str]:
    """Paths git currently reports as modified, added or deleted."""
    lines = git("status", "--porcelain").splitlines()
    return {line[3:].strip().strip('"') for line in lines if line[3:].strip()}


def plan_dir(slug: str) -> Path:
    return PLANS / slug


def rounds_done(slug: str) -> int:
    directory = plan_dir(slug)
    if not directory.exists():
        return 0
    return len([d for d in directory.iterdir() if d.is_dir() and d.name.startswith("round-")])


def read_verdict(path: Path) -> dict:
    """Parse Codex's verdict, refusing anything that is not clearly a verdict.

    A malformed reply must never be read as approval.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Codex's verdict could not be read as JSON ({exc}). Nothing was accepted.")
    if not isinstance(data, dict) or data.get("verdict") not in ("ready", "changes_needed"):
        fail(
            "Codex did not return a usable verdict, so the round does not count. "
            f"Got: {str(data)[:200]}"
        )
    return data


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

PLAN_TEMPLATE = """# {title}

STATUS: DRAFT — not yet reviewed

## Context

Why this is being done, what problem it solves, and what "finished" looks like.

## Approach

## Files to change

## Verification

How this is proven to work against the running thing, not just the diff.
"""


def cmd_new(slug: str, title: str) -> None:
    directory = plan_dir(slug)
    if directory.exists():
        fail(f"plans/{slug} already exists. Pick another name, or review the one that is there.")
    directory.mkdir(parents=True)
    (directory / "PLAN.md").write_text(PLAN_TEMPLATE.format(title=title), encoding="utf-8")
    (directory / "LOG.md").write_text(
        f"# Review log — {title}\n\nOldest first. One entry per round, from each side.\n",
        encoding="utf-8",
    )
    print(f"\n  Created plans/{slug}/PLAN.md — write the plan into it, then run:")
    print(f"      python planloop/planloop.py review {slug}\n")


def cmd_review(slug: str) -> None:
    directory = plan_dir(slug)
    plan = directory / "PLAN.md"
    if not plan.exists():
        fail(f"No plan at plans/{slug}/PLAN.md. Create it with: planloop.py new {slug} \"Title\"")

    done = rounds_done(slug)
    if done >= MAX_ROUNDS:
        fail(
            f"{MAX_ROUNDS} rounds have already run on {slug}. If the two of you still "
            "disagree, that is Dylan's call to make, not another round's."
        )

    number = done + 1
    round_dir = directory / f"round-{number}"
    round_dir.mkdir()
    before = round_dir / "before.md"
    shutil.copy2(plan, before)

    baseline = changed_files()
    prompt = build_prompt(slug, number)
    (round_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    verdict_path = round_dir / "verdict.json"
    print(f"\n  Round {number} of {MAX_ROUNDS} — asking Codex to review plans/{slug}/PLAN.md")
    print("  It reads the real code, so this takes a few minutes.\n")

    command = [
        codex_binary(), "exec",
        "--sandbox", "workspace-write",
        "-C", str(REPO),
        "--skip-git-repo-check",
        "--color", "never",
        "--output-schema", str(SCHEMA),
        "-o", str(verdict_path),
        "-",                                  # prompt arrives on stdin
    ]
    try:
        # Windows would otherwise encode stdin as cp1252 and choke on any
        # character the plan happens to contain.
        result = subprocess.run(
            command, input=prompt, text=True, capture_output=True,
            timeout=ROUND_TIMEOUT, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        fail(f"Codex did not finish within {ROUND_TIMEOUT}s. Round {number} is void.")

    (round_dir / "codex-stdout.txt").write_text(
        (result.stdout or "") + (result.stderr or ""), encoding="utf-8"
    )
    if not verdict_path.exists():
        fail(
            f"Codex wrote no verdict (exit {result.returncode}). "
            f"See plans/{slug}/round-{number}/codex-stdout.txt"
        )

    strays = enforce_boundary(slug, baseline, round_dir)
    verdict = read_verdict(verdict_path)
    write_diff(before, plan, round_dir / "plan.diff")
    append_log(slug, number, verdict, strays)
    report(slug, number, verdict, strays)


def build_prompt(slug: str, number: int) -> str:
    directory = plan_dir(slug)
    parts = [
        PROMPT.read_text(encoding="utf-8"),
        "\n\n---\n\n",
        f"## This is review round {number} of at most {MAX_ROUNDS}\n\n",
        f"The plan under review is at `plans/{slug}/PLAN.md`. Edit that file directly.\n\n",
    ]

    history = []
    for earlier in range(1, number):
        verdict_file = directory / f"round-{earlier}" / "verdict.json"
        if verdict_file.exists():
            try:
                data = json.loads(verdict_file.read_text(encoding="utf-8"))
                history.append(f"### Round {earlier}, your verdict: {data.get('verdict')}\n"
                               f"{data.get('summary', '')}\n")
            except (OSError, json.JSONDecodeError):
                pass
    log = directory / "LOG.md"
    if history:
        parts.append("## What has already happened\n\n" + "\n".join(history) + "\n")
        parts.append(
            "Claude's replies to your earlier concerns are in `plans/"
            f"{slug}/LOG.md`. Read them. Do not re-raise a concern that was answered "
            "unless the answer was wrong.\n\n"
        )
    elif log.exists():
        parts.append(f"Claude's notes are in `plans/{slug}/LOG.md`.\n\n")

    parts.append("## The plan as it stands\n\n")
    parts.append((directory / "PLAN.md").read_text(encoding="utf-8"))
    return "".join(parts)


def enforce_boundary(slug: str, baseline: set[str] | None = None,
                     round_dir: Path | None = None,
                     allowed: list[str] | None = None) -> list[str]:
    """Codex stays inside what it was given. Everything else is put back.

    During a review round that means the plan folder only -- Codex reviews the
    code, it does not get to edit it through this door. During a task it means
    the files that task declared, and nothing else, because Claude may be
    editing the rest at the same time.

    Only files that changed *during* the round or task count. Whatever was
    already uncommitted belongs to Claude and is left alone -- reverting that
    would destroy work in progress.

    A tracked file is reverted. A file Codex newly created outside its bounds is
    moved into `rejected/` rather than deleted, so nothing is silently thrown
    away.
    """
    permitted = [p.replace("\\", "/") for p in (allowed or [f"plans/{slug}/"])]
    baseline = baseline or set()

    def inside(path: str) -> bool:
        """A permitted entry ending in `/` is a folder; anything else is one file."""
        normalised = path.replace("\\", "/")
        for entry in permitted:
            if entry.endswith("/"):
                if normalised.startswith(entry):
                    return True
            elif normalised == entry:
                return True
        return False

    strays = sorted(path for path in changed_files() - baseline if not inside(path))
    for path in strays:
        target = REPO / path
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=REPO, capture_output=True).returncode == 0
        if tracked:
            subprocess.run(["git", "checkout", "--", path], cwd=REPO, capture_output=True)
        elif round_dir and target.exists() and target.is_file():
            quarantine = round_dir / "rejected" / path.replace("\\", "/").replace("/", "__")
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(quarantine))
    return strays


def write_diff(before: Path, after: Path, target: Path) -> None:
    diff = difflib.unified_diff(
        before.read_text(encoding="utf-8").splitlines(keepends=True),
        after.read_text(encoding="utf-8").splitlines(keepends=True),
        fromfile="PLAN.md (before review)", tofile="PLAN.md (after review)",
    )
    target.write_text("".join(diff) or "(Codex made no edits to the plan.)\n", encoding="utf-8")


def append_log(slug: str, number: int, verdict: dict, strays: list[str]) -> None:
    lines = [
        f"\n## Round {number} — codex — {datetime.now():%Y-%m-%d %H:%M}\n",
        f"\n**Verdict:** {verdict['verdict']}\n",
        f"\n{verdict.get('summary', '').strip()}\n",
    ]
    if verdict.get("changes_made"):
        lines.append("\n**Edited the plan:**\n")
        lines += [f"- {c}\n" for c in verdict["changes_made"]]
    if verdict.get("concerns"):
        lines.append("\n**Concerns:**\n")
        for concern in verdict["concerns"]:
            lines.append(f"- **{concern.get('issue', '')}** — {concern.get('why_it_matters', '')}"
                         f" Suggested: {concern.get('suggested_fix', '')}\n")
    if verdict.get("questions"):
        lines.append("\n**Questions for Claude:**\n")
        lines += [f"- {q}\n" for q in verdict["questions"]]
    if strays:
        lines.append("\n**Reverted — changed outside this plan's folder:**\n")
        lines += [f"- {p}\n" for p in strays]
    with (plan_dir(slug) / "LOG.md").open("a", encoding="utf-8") as handle:
        handle.writelines(lines)


def report(slug: str, number: int, verdict: dict, strays: list[str]) -> None:
    print(f"  Verdict: {verdict['verdict'].upper()}")
    print(f"  {verdict.get('summary', '').strip()[:400]}\n")
    for concern in verdict.get("concerns", []):
        print(f"   - {concern.get('issue', '')}")
    if strays:
        print("\n  Codex changed files outside the plan folder. These were reverted:")
        for path in strays:
            print(f"   - {path}")
    print(f"\n  Edits: plans/{slug}/round-{number}/plan.diff")
    print(f"  Log:   plans/{slug}/LOG.md")
    if verdict["verdict"] == "ready":
        print("\n  Codex is satisfied. Claude reviews its edits and records its own verdict.\n")
    else:
        print("\n  Claude now answers each concern in LOG.md and revises the plan.\n")


def set_status(slug: str, status: str, banner: str = "") -> None:
    plan = plan_dir(slug) / "PLAN.md"
    text = plan.read_text(encoding="utf-8")
    lines = text.splitlines()
    kept = [line for line in lines if not line.startswith("STATUS:")]
    title = kept[0] if kept else f"# {slug}"
    rest = "\n".join(kept[1:]).lstrip("\n")
    plan.write_text(f"{title}\n\nSTATUS: {status}\n\n{banner}{rest}\n", encoding="utf-8")


def cmd_status(slug: str) -> None:
    directory = plan_dir(slug)
    if not directory.exists():
        fail(f"No plan called {slug}.")
    print(f"\n  plans/{slug}\n")
    codex_ready = False
    for number in range(1, MAX_ROUNDS + 1):
        verdict_file = directory / f"round-{number}" / "verdict.json"
        if not verdict_file.exists():
            continue
        try:
            data = json.loads(verdict_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print(f"  round {number}: unreadable verdict")
            continue
        codex_ready = data.get("verdict") == "ready"
        print(f"  round {number}: codex {data.get('verdict')}"
              f"  ({len(data.get('concerns', []))} concerns)")

    log = (directory / "LOG.md").read_text(encoding="utf-8") if (directory / "LOG.md").exists() else ""
    claude_ready = "CLAUDE VERDICT: ready" in log
    print(f"\n  codex ready:  {codex_ready}")
    print(f"  claude ready: {claude_ready}")

    done = rounds_done(slug)
    if codex_ready and claude_ready:
        set_status(slug, f"READY TO SHIP (after round {done})")
        print("\n  Both agree. The plan is ready to build.\n")
    elif done >= MAX_ROUNDS:
        set_status(
            slug, "BLOCKED — NEEDS DYLAN",
            "## OPEN DISAGREEMENT\n\n"
            f"Three rounds did not settle this. Codex's remaining concerns are in "
            f"`plans/{slug}/LOG.md`, with Claude's answer to each.\n\n"
            "Neither side gets to break the tie. Read both positions and choose.\n\n",
        )
        print("\n  Three rounds without agreement. Marked BLOCKED — this one is yours to decide.\n")
        raise SystemExit(2)
    else:
        print(f"\n  {done} of {MAX_ROUNDS} rounds used.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="start a plan")
    new.add_argument("slug")
    new.add_argument("title")

    review = sub.add_parser("review", help="run one Codex review round")
    review.add_argument("slug")

    status = sub.add_parser("status", help="show where a plan stands")
    status.add_argument("slug")

    tasks_cmd = sub.add_parser("tasks", help="show the task split and check it holds")
    tasks_cmd.add_argument("slug")

    run = sub.add_parser("run", help="hand one Codex-owned task to Codex")
    run.add_argument("slug")
    run.add_argument("task_id")

    done_cmd = sub.add_parser("done", help="tick a finished task off the plan")
    done_cmd.add_argument("slug")
    done_cmd.add_argument("task_id")

    args = parser.parse_args()
    PLANS.mkdir(exist_ok=True)

    if args.command == "new":
        cmd_new(args.slug, args.title)
    elif args.command == "review":
        cmd_review(args.slug)
    elif args.command == "status":
        cmd_status(args.slug)
    else:
        # The task commands live in their own module; this one stays about the
        # review loop. They reach back here for fail/plan_dir/enforce_boundary.
        import commands
        driver = sys.modules[__name__]
        if args.command == "tasks":
            commands.cmd_tasks(driver, args.slug)
        elif args.command == "run":
            commands.cmd_run(driver, args.slug, args.task_id)
        else:
            commands.cmd_done(driver, args.slug, args.task_id)


if __name__ == "__main__":
    main()
