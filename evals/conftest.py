"""Shared notebook fixture and the retrieval scoreboard printed after the run."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.catalog import (  # noqa: E402
    PRICE_CHEAP_QUERIES,
    PRICE_SPLURGE_QUERIES,
    load_chips,
    load_spots,
)
from evals.grade_retrieval import format_scoreboard, grade_all, load_cases  # noqa: E402
from evals.ranking import rank_queries  # noqa: E402


def pytest_collection_modifyitems(config, items):
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY is not set; live blurb graders stay off")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def world():
    spots = load_spots()
    chips = load_chips()
    cases = load_cases()
    queries = []
    seen = set()

    def add(query):
        if query not in seen:
            seen.add(query)
            queries.append(query)

    for case in cases:
        add(case["query"])
    for query in chips["chips"] + chips["surprises"]:
        add(query)
    for query in PRICE_CHEAP_QUERIES + PRICE_SPLURGE_QUERIES + ["Pizza", "PIZZA"]:
        add(query)
    batch = rank_queries(queries, empty_samples=10)
    return SimpleNamespace(
        spots=spots,
        by_name={spot["name"]: spot for spot in spots},
        chips=chips,
        cases=cases,
        ranked=batch.by_query,
        empty_samples=batch.empty_samples,
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.write_sep("=", "J(AI) retrieval scoreboard")
    try:
        spots = load_spots()
        by_name = {spot["name"]: spot for spot in spots}
        cases = load_cases()
        batch = rank_queries([case["query"] for case in cases])
        grades = grade_all(cases, batch.by_query, by_name)
        terminalreporter.write_line(format_scoreboard(grades))
    except Exception as exc:
        terminalreporter.write_line(f"scoreboard unavailable: {exc}")
