"""The plan review loop.

The parts worth testing are the ones that decide whether work gets built: does a
malformed reply ever read as approval, can Codex edit source through this door,
and does a deadlock actually stop.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planloop"))
import planloop  # noqa: E402


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A throwaway plans/ directory so tests never touch real plans."""
    plans = tmp_path / "plans"
    plans.mkdir()
    monkeypatch.setattr(planloop, "PLANS", plans)
    monkeypatch.setattr(planloop, "REPO", tmp_path)
    return plans


# --------------------------------------------------------------------------
# a bad reply must never read as approval
# --------------------------------------------------------------------------

def test_a_malformed_verdict_is_refused_not_assumed_ready(tmp_path):
    path = tmp_path / "verdict.json"

    path.write_text("this is not json at all", encoding="utf-8")
    with pytest.raises(SystemExit):
        planloop.read_verdict(path)

    path.write_text('{"summary": "looks fine to me"}', encoding="utf-8")
    with pytest.raises(SystemExit):
        planloop.read_verdict(path)

    path.write_text('{"verdict": "looks good"}', encoding="utf-8")
    with pytest.raises(SystemExit):
        planloop.read_verdict(path)


def test_a_real_verdict_parses(tmp_path):
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps({
        "verdict": "changes_needed", "summary": "The key would reach the client.",
        "changes_made": [], "concerns": [], "questions": [],
    }), encoding="utf-8")
    assert planloop.read_verdict(path)["verdict"] == "changes_needed"


# --------------------------------------------------------------------------
# Codex reviews the code; it does not get to edit it through this door
# --------------------------------------------------------------------------

def test_changes_outside_the_plan_folder_are_reverted(monkeypatch):
    touched = [
        "plans/demo/PLAN.md",     # allowed
        "agent.py",               # not allowed
        "extension/content.js",   # not allowed
    ]
    monkeypatch.setattr(planloop, "changed_files", lambda: set(touched))

    reverted = []

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "checkout", "--"]:
            reverted.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, "", "")   # 0 = file is tracked

    monkeypatch.setattr(planloop.subprocess, "run", fake_run)

    strays = planloop.enforce_boundary("demo", baseline=set())
    assert strays == ["agent.py", "extension/content.js"]
    assert reverted == ["agent.py", "extension/content.js"]
    assert "plans/demo/PLAN.md" not in reverted, "its own plan must survive"


def test_windows_style_paths_are_still_caught(monkeypatch):
    monkeypatch.setattr(planloop, "changed_files", lambda: {"plans\\demo\\PLAN.md", "app.py"})
    monkeypatch.setattr(
        planloop.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    assert planloop.enforce_boundary("demo", baseline=set()) == ["app.py"]


# --------------------------------------------------------------------------
# rounds, and the deadlock that stops for Dylan
# --------------------------------------------------------------------------

def test_a_fourth_round_is_refused(workspace, monkeypatch):
    directory = workspace / "demo"
    directory.mkdir()
    (directory / "PLAN.md").write_text("# demo\n", encoding="utf-8")
    for number in range(1, planloop.MAX_ROUNDS + 1):
        (directory / f"round-{number}").mkdir()

    with pytest.raises(SystemExit):
        planloop.cmd_review("demo")


def test_three_rounds_without_agreement_blocks_and_asks_dylan(workspace, capsys):
    directory = workspace / "demo"
    directory.mkdir()
    (directory / "PLAN.md").write_text("# Demo plan\n\nSTATUS: DRAFT\n\nbody\n", encoding="utf-8")
    (directory / "LOG.md").write_text("# log\n", encoding="utf-8")
    for number in range(1, 4):
        round_dir = directory / f"round-{number}"
        round_dir.mkdir()
        (round_dir / "verdict.json").write_text(json.dumps({
            "verdict": "changes_needed", "summary": "still not right",
            "changes_made": [], "concerns": [], "questions": [],
        }), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        planloop.cmd_status("demo")
    assert exit_info.value.code == 2, "a deadlock must not look like success"

    plan = (directory / "PLAN.md").read_text(encoding="utf-8")
    assert "STATUS: BLOCKED — NEEDS DYLAN" in plan
    assert "OPEN DISAGREEMENT" in plan
    assert "Neither side gets to break the tie" in plan


def test_both_ready_marks_the_plan_shippable(workspace, capsys):
    directory = workspace / "demo"
    directory.mkdir()
    (directory / "PLAN.md").write_text("# Demo plan\n\nSTATUS: DRAFT\n\nbody\n", encoding="utf-8")
    (directory / "LOG.md").write_text("# log\n\nCLAUDE VERDICT: ready\n", encoding="utf-8")
    round_dir = directory / "round-1"
    round_dir.mkdir()
    (round_dir / "verdict.json").write_text(json.dumps({
        "verdict": "ready", "summary": "good", "changes_made": [], "concerns": [], "questions": [],
    }), encoding="utf-8")

    planloop.cmd_status("demo")
    plan = (directory / "PLAN.md").read_text(encoding="utf-8")
    assert "STATUS: READY TO SHIP (after round 1)" in plan
    assert "OPEN DISAGREEMENT" not in plan


def test_codex_ready_alone_is_not_enough(workspace, capsys):
    """Both sides must agree. One side saying yes is half an answer."""
    directory = workspace / "demo"
    directory.mkdir()
    (directory / "PLAN.md").write_text("# Demo\n\nSTATUS: DRAFT\n\nbody\n", encoding="utf-8")
    (directory / "LOG.md").write_text("# log\n", encoding="utf-8")   # no Claude verdict
    round_dir = directory / "round-1"
    round_dir.mkdir()
    (round_dir / "verdict.json").write_text(json.dumps({
        "verdict": "ready", "summary": "good", "changes_made": [], "concerns": [], "questions": [],
    }), encoding="utf-8")

    planloop.cmd_status("demo")
    assert "STATUS: READY TO SHIP" not in (directory / "PLAN.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# the prompt Codex receives
# --------------------------------------------------------------------------

def test_the_review_prompt_names_this_repo_s_past_failures():
    prompt = Path(__file__).resolve().parents[1].joinpath("planloop/review-prompt.md").read_text(encoding="utf-8")
    for expected in ("enforced by prompt instead of code", "swallowed error",
                     "token or step budget", "guessed value", "Secrets"):
        assert expected.lower() in prompt.lower(), f"review prompt should check for: {expected}"


def test_the_schema_only_allows_two_verdicts():
    schema = json.loads(
        Path(__file__).resolve().parents[1].joinpath("planloop/review-schema.json")
        .read_text(encoding="utf-8"))
    assert schema["properties"]["verdict"]["enum"] == ["ready", "changes_needed"]
    for field in ("verdict", "summary", "changes_made", "concerns", "questions"):
        assert field in schema["required"]


def test_work_already_in_progress_is_not_reverted(monkeypatch):
    """Claude is mid-session during a review. Reverting its uncommitted work
    would destroy it."""
    monkeypatch.setattr(planloop, "changed_files",
                        lambda: {"planloop/planloop.py", "agent.py", "plans/demo/PLAN.md"})
    reverted = []
    monkeypatch.setattr(
        planloop.subprocess, "run",
        lambda cmd, **kw: (reverted.append(cmd[-1]) if cmd[:3] == ["git", "checkout", "--"] else None)
        or subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    # planloop.py was already modified before the round started
    strays = planloop.enforce_boundary("demo", baseline={"planloop/planloop.py"})
    assert strays == ["agent.py"], "only what changed during the round counts"
    assert "planloop/planloop.py" not in reverted


def test_a_file_dirty_before_the_round_and_edited_during_it_is_restored(tmp_path, monkeypatch):
    """Greptile PR #3: a path-only baseline let Codex overwrite a file Claude was
    mid-edit on, because the path was in both the before and after sets. The
    baseline now carries content hashes and a snapshot, so a co-edited file is
    put back exactly as Claude left it and Codex's version is kept aside."""
    monkeypatch.setattr(planloop, "REPO", tmp_path)
    round_dir = tmp_path / "plans" / "demo" / "round-1"
    round_dir.mkdir(parents=True)
    claude_file = tmp_path / "agent.py"
    claude_file.write_text("claude was here, unsaved\n", encoding="utf-8")

    # before the round: agent.py is already dirty
    monkeypatch.setattr(planloop, "changed_files", lambda: {"agent.py"})
    baseline = planloop.snapshot_dirty(round_dir)
    assert set(baseline) == {"agent.py"} and baseline["agent.py"] is not None
    assert (round_dir / "baseline" / "agent.py").read_text(encoding="utf-8") == "claude was here, unsaved\n"

    # during the round: Codex edits it as well
    claude_file.write_text("codex overwrote this\n", encoding="utf-8")
    monkeypatch.setattr(planloop.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))

    strays = planloop.enforce_boundary("demo", baseline=baseline, round_dir=round_dir)
    assert strays == ["agent.py"], "a co-edited file counts as a stray"
    assert claude_file.read_text(encoding="utf-8") == "claude was here, unsaved\n", "Claude's version is back"
    assert (round_dir / "rejected" / "agent.py").read_text(encoding="utf-8") == "codex overwrote this\n", \
        "Codex's version is kept for inspection, not thrown away"


def test_a_dirty_file_codex_did_not_touch_is_still_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(planloop, "REPO", tmp_path)
    round_dir = tmp_path / "plans" / "demo" / "round-1"
    round_dir.mkdir(parents=True)
    (tmp_path / "agent.py").write_text("claude mid-edit\n", encoding="utf-8")
    monkeypatch.setattr(planloop, "changed_files", lambda: {"agent.py"})
    baseline = planloop.snapshot_dirty(round_dir)
    reverted = []
    monkeypatch.setattr(
        planloop.subprocess, "run",
        lambda cmd, **kw: (reverted.append(cmd[-1]) if cmd[:3] == ["git", "checkout", "--"] else None)
        or subprocess.CompletedProcess(cmd, 0, "", ""))
    assert planloop.enforce_boundary("demo", baseline=baseline, round_dir=round_dir) == []
    assert reverted == []
    assert (tmp_path / "agent.py").read_text(encoding="utf-8") == "claude mid-edit\n"
