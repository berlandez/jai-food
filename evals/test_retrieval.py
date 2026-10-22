"""Labeled retrieval judgments. A failure is a ranker miss, not a harness crash."""

import pytest

from evals.grade_retrieval import grade_case, load_cases

pytestmark = pytest.mark.quality


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_labeled_query(case, world):
    grade = grade_case(case, world.ranked[case["query"]], world.by_name)
    if not grade.ok:
        pytest.fail(grade.message)
