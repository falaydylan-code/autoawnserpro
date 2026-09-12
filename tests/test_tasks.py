"""The task split, and the guards that stop the two agents colliding.

What matters here is not that the parser reads a checklist. It is that a split
which would quietly break -- two owners on one file, a task waiting on itself, a
task whose owner nobody justified -- is refused before anyone builds from it.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planloop"))
import planloop  # noqa: E402
import tasks  # noqa: E402
from dispatch import build_task_prompt  # noqa: E402


PLAN = """# Demo

## Tasks

- [x] **T1** · codex · files: `agent.py`
  Why codex: self-contained
  Add a press action to the vocabulary.
  Done when: pytest -q passes.

- [ ] **T2** · claude · after: T1 · files: `extension/background.js`
  Why claude: needs-browser
  Wire press into the loop.

- [ ] **T3** · codex · after: T2 · files: `tests/test_agent.py`
  Why codex: follows-on
  Cover the new action.
"""


# --------------------------------------------------------------------------
# reading the split
# --------------------------------------------------------------------------

def test_the_checklist_parses_into_owned_work():
    items = tasks.parse_tasks(PLAN)
    assert [t["id"] for t in items] == ["T1", "T2", "T3"]
    assert [t["owner"] for t in items] == ["codex", "claude", "codex"]
    assert items[0]["done"] and not items[1]["done"]
    assert items[1]["after"] == ["T1"]
    assert items[1]["files"] == ["extension/background.js"]


def test_the_reason_line_is_not_mistaken_for_the_description():
    """`summarise` shows the first detail line, so the Why line must not be it."""
    task = tasks.parse_tasks(PLAN)[1]
    assert task["ground"] == "needs-browser"
    assert task["detail"][0] == "Wire press into the loop."


def test_a_valid_split_has_nothing_to_complain_about():
    assert tasks.validate_split(tasks.parse_tasks(PLAN)) == []


def test_only_unblocked_work_is_offered():
    items = tasks.parse_tasks(PLAN)
    assert [t["id"] for t in tasks.ready_tasks(items)] == ["T2"]


def test_ticking_a_task_unblocks_the_next():
    text, changed = tasks.mark_done(PLAN, "t2")
    assert changed
    items = tasks.parse_tasks(text)
    assert [t["id"] for t in tasks.ready_tasks(items)] == ["T3"]

    _, changed_again = tasks.mark_done(text, "T2")
    assert not changed_again, "ticking an already-done task must report nothing changed"


# --------------------------------------------------------------------------
# the splits that would break
# --------------------------------------------------------------------------

def test_two_owners_on_one_file_is_refused():
    """Whoever finishes second overwrites the first, and neither notices."""
    plan = """
- [ ] **T1** · codex · files: `agent.py`
  Why codex: self-contained
  One.

- [ ] **T2** · claude · files: `agent.py`
  Why claude: cross-cutting
  Two.
"""
    problems = tasks.validate_split(tasks.parse_tasks(plan))
    assert any("agent.py" in p and "both" in p for p in problems)


def test_a_task_bounded_by_nothing_is_refused():
    plan = "- [ ] **T1** · codex\n  Why codex: either-could\n  Do something.\n"
    problems = tasks.validate_split(tasks.parse_tasks(plan))
    assert any("declares no files" in p for p in problems)


def test_a_dependency_that_does_not_exist_is_refused():
    plan = "- [ ] **T1** · codex · after: T9 · files: `a.py`\n  Why codex: either-could\n  Do it.\n"
    assert any("T9" in p for p in tasks.validate_split(tasks.parse_tasks(plan)))


def test_a_cycle_is_caught_rather_than_hanging():
    plan = (
        "- [ ] **T1** · codex · after: T2 · files: `a.py`\n  Why codex: either-could\n  One.\n\n"
        "- [ ] **T2** · claude · after: T1 · files: `b.py`\n  Why claude: either-could\n  Two.\n"
    )
    items = tasks.parse_tasks(plan)
    assert any("waits on itself" in p for p in tasks.validate_split(items))
    assert tasks.ready_tasks(items) == [], "neither can start, and neither should be offered"


# --------------------------------------------------------------------------
# ownership has to be argued, not asserted
# --------------------------------------------------------------------------

def test_an_unjustified_owner_is_refused():
    plan = "- [ ] **T1** · codex · files: `a.py`\n  Do something.\n"
    problems = tasks.validate_split(tasks.parse_tasks(plan))
    assert any("no reason for belonging" in p for p in problems)


def test_a_ground_claiming_one_model_is_better_is_refused():
    """The whole point: neither side may argue from a comparison nobody can
    check. Only the closed list is accepted."""
    plan = ("- [ ] **T1** · claude · files: `a.py`\n"
            "  Why claude: better-at-reasoning\n  Do the hard part.\n")
    problems = tasks.validate_split(tasks.parse_tasks(plan))
    assert any("better-at-reasoning" in p for p in problems)
    assert "better-at-reasoning" not in tasks.GROUNDS


def test_no_ground_on_the_list_compares_the_two_models():
    for ground, description in tasks.GROUNDS.items():
        text = f"{ground} {description}".lower()
        for smell in ("better", "stronger", "smarter", "worse", "weaker",
                      "claude", "codex", "gpt", "opus"):
            assert smell not in text, (
                f"ground `{ground}` argues from model quality, which nobody here "
                "has data for")


def test_a_reason_written_for_the_wrong_owner_is_refused():
    plan = "- [ ] **T1** · codex · files: `a.py`\n  Why claude: needs-browser\n  Do it.\n"
    problems = tasks.validate_split(tasks.parse_tasks(plan))
    assert any("owned by codex" in p and "written for claude" in p for p in problems)


def test_open_choices_stacked_on_one_side_are_called_out():
    plan = "".join(
        f"- [ ] **T{n}** · claude · files: `f{n}.py`\n  Why claude: either-could\n  Task {n}.\n\n"
        for n in (1, 2, 3)
    )
    problems = tasks.validate_split(tasks.parse_tasks(plan))
    assert any("either-could" in p and "claude" in p for p in problems)


def test_a_lopsided_split_with_real_grounds_is_left_alone():
    """Only unargued work is balanced. A task that genuinely needs one harness
    belongs there however uneven the totals look."""
    plan = "".join(
        f"- [ ] **T{n}** · claude · files: `f{n}.py`\n  Why claude: needs-browser\n  Task {n}.\n\n"
        for n in (1, 2, 3)
    )
    assert tasks.validate_split(tasks.parse_tasks(plan)) == []


# --------------------------------------------------------------------------
# what Codex is handed, and how far it may reach
# --------------------------------------------------------------------------

def test_codex_is_told_which_files_it_may_touch():
    task = tasks.parse_tasks(PLAN)[2]
    prompt = build_task_prompt(task, PLAN)
    assert "T3" in prompt
    assert "tests/test_agent.py" in prompt
    assert "Cover the new action." in prompt
    assert "AGENTS.md" in prompt, "it has to read the hard-won list first"


def test_a_task_may_only_change_the_files_it_declared(monkeypatch):
    """The review round bounds Codex to the plan folder. A task bounds it to its
    own files, because Claude may be editing the rest at the same moment."""
    monkeypatch.setattr(planloop, "changed_files",
                        lambda: {"agent.py", "extension/content.js", "plans/demo/work/t1/result.md"})
    reverted = []

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "checkout", "--"]:
            reverted.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(planloop.subprocess, "run", fake_run)

    strays = planloop.enforce_boundary(
        "demo", baseline=set(), allowed=["agent.py", "plans/demo/"])
    assert strays == ["extension/content.js"]
    assert reverted == ["extension/content.js"]
    assert "agent.py" not in reverted, "the file the task declared must survive"


def test_a_declared_file_does_not_let_a_lookalike_through(monkeypatch):
    """`agent.py` must not permit `agent.py.bak` or `my_agent.py`."""
    monkeypatch.setattr(planloop, "changed_files",
                        lambda: {"agent.py", "agent.py.bak", "my_agent.py"})
    monkeypatch.setattr(
        planloop.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    strays = planloop.enforce_boundary("demo", baseline=set(), allowed=["agent.py"])
    assert strays == ["agent.py.bak", "my_agent.py"]


def test_the_review_prompt_forbids_arguing_from_model_quality():
    prompt = (Path(__file__).resolve().parents[1] / "planloop" / "review-prompt.md").read_text(
        encoding="utf-8")
    assert "Tasks" in prompt
    assert "no trustworthy head-to-head data" in prompt.lower()
    for ground in tasks.GROUNDS:
        assert ground in prompt, f"Codex is never told about the `{ground}` ground"


@pytest.mark.parametrize("command", ["tasks", "run", "done"])
def test_the_task_commands_are_reachable_from_the_cli(command):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "planloop" / "planloop.py"),
         command, "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
