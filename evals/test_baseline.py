"""Fail the build when retrieval gets worse than evals/baseline.json.

The file is a real run's pass counts, plus every labeled case id. Deleting a
label, or a group slipping, fails here even if someone rewrites the totals.
"""

import json
from pathlib import Path

import pytest

from evals.grade_retrieval import format_scoreboard, grade_all

pytestmark = pytest.mark.mechanics

BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"


def _by_group(grades):
    counts = {}
    for grade in grades:
        passed, total = counts.get(grade.group, (0, 0))
        counts[grade.group] = (passed + int(grade.ok), total + 1)
    return counts


def test_retrieval_does_not_regress(world):
    grades = grade_all(world.cases, world.ranked, world.by_name)
    baseline = json.loads(BASELINE_PATH.read_text())
    present = {case["id"] for case in world.cases}
    missing = [case_id for case_id in baseline["case_ids"] if case_id not in present]
    passed = sum(1 for grade in grades if grade.ok)
    problems = []
    if missing:
        problems.append("labeled cases removed: " + ", ".join(missing))
    if passed < baseline["passed"]:
        problems.append(f"passed {passed}, baseline is {baseline['passed']}")
    if len(grades) < baseline["total"]:
        problems.append(f"label count {len(grades)}, baseline is {baseline['total']}")
    groups = _by_group(grades)
    for name, row in baseline["groups"].items():
        got_passed, got_total = groups.get(name, (0, 0))
        if got_passed < row["passed"]:
            problems.append(f"{name} passed {got_passed}, baseline is {row['passed']}")
        if got_total < row["total"]:
            problems.append(f"{name} has {got_total} labels, baseline is {row['total']}")
    if problems:
        pytest.fail(format_scoreboard(grades) + "\n" + "\n".join(problems))
