"""Grade real Jay's Take blurbs. Runs only when ANTHROPIC_API_KEY is set.

Generation goes through POST /api/pick, the same prompt and model the app uses.
A second Claude call then checks claims against those notes. Format, banned
phrases, catalog names, and press-only dishes are checked in grade_output
without that second call.
"""

import json
import time
from pathlib import Path

import pytest

import app as jai
from evals.grade_output import grade_blurb
from evals.judge import judge_blurb, judge_failures

pytestmark = pytest.mark.llm

OUTPUT_CASES = json.loads((Path(__file__).resolve().parent / "golden_output.json").read_text())["cases"]
CATALOG = list(jai.SPOTS_BY_NAME)


@pytest.fixture(scope="module")
def retrieved():
    from evals.ranking import rank_queries

    queries = [case["query"] for case in OUTPUT_CASES if "names" not in case]
    return rank_queries(queries).by_query


def _candidates(case, retrieved):
    if "names" in case:
        return list(case["names"])
    return list(retrieved[case["query"]].names)


def _post(query, names):
    jai._cache.clear()
    jai._hits.clear()
    jai._day.update(date=time.strftime("%Y-%m-%d"), count=0)
    client = jai.app.test_client()
    return client.post("/api/pick", json={"q": query, "names": names})


@pytest.mark.parametrize("case", OUTPUT_CASES, ids=lambda case: case["id"])
def test_live_blurb(case, retrieved):
    names = _candidates(case, retrieved)
    if not names:
        pytest.fail(
            f"{case['id']}: retrieval returned no spots, so the app shows the empty state "
            "and does not ask for a blurb"
        )
    response = _post(case["query"], names)
    if response.status_code == 422 and case.get("allow_refusal"):
        return
    body = response.get_json(silent=True) or {}
    if response.status_code != 200:
        pytest.fail(f"{case['id']}: /api/pick returned {response.status_code}: {body}")
    text = (body.get("text") or "").strip()
    notes = "\n\n".join(jai.notes_for(jai.SPOTS_BY_NAME[name]) for name in names if name in jai.SPOTS_BY_NAME)
    deterministic = grade_blurb(text, candidate_names=names, notes=notes, catalog_names=CATALOG)
    try:
        verdict = judge_blurb(
            query=case["query"],
            notes=notes,
            blurb=text,
            extra=case.get("judge_extra", ""),
        )
        judged = judge_failures(verdict)
    except Exception as exc:
        verdict = None
        judged = [f"judge call failed: {exc}"]
    problems = list(deterministic.issues) + judged
    if problems:
        rendered = json.dumps(verdict, indent=2) if verdict is not None else "(no judge verdict)"
        pytest.fail(
            f"{case['id']} query={case['query']!r} candidates={names}\n"
            f"blurb:\n{text}\n\n"
            + "\n".join(problems)
            + f"\n\njudge:\n{rendered}"
        )
