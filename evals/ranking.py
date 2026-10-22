"""Execute the real score() and pick() in static/app.js.

The browser ranks spots before the server ever sees a request. Reimplementing
that function in Python would let the eval drift from the app, so this module
shells out to evals/rank_bridge.js, which loads app.js and injects the notebook.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path(__file__).resolve().parent / "rank_bridge.js"


@dataclass
class RankedQuery:
    query: str
    names: list
    scores: list  # (name, score) best first, one row per spot


@dataclass
class RankBatch:
    by_query: dict
    empty_samples: list


def rank_queries(queries, empty_samples=0):
    if shutil.which("node") is None:
        raise RuntimeError(
            "Node.js is required so the eval can run the real score() and pick() "
            "in static/app.js. Install Node and re-run."
        )
    payload = json.dumps({"queries": list(queries), "empty_samples": empty_samples})
    proc = subprocess.run(
        ["node", str(BRIDGE)],
        input=payload,
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "rank bridge exited non-zero").strip()
        raise RuntimeError(detail)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"rank bridge returned non-JSON:\n{proc.stdout[:500]}") from exc
    ranked = []
    for row in data["results"]:
        scores = [(item["name"], item["score"]) for item in row["scores"]]
        ranked.append(RankedQuery(query=row["query"], names=list(row["names"]), scores=scores))
    by_query = {item.query: item for item in ranked}
    missing = [q for q in queries if q not in by_query]
    if missing:
        raise RuntimeError(f"rank bridge dropped queries: {missing}")
    return RankBatch(by_query=by_query, empty_samples=data.get("empty_samples") or [])
