"""Grade pick() results against the labeled queries in golden_retrieval.json."""

import json
from dataclasses import dataclass
from pathlib import Path

from evals.catalog import price_tier

GOLDEN_PATH = Path(__file__).resolve().parent / "golden_retrieval.json"
CONSTRAINTS = (
    "expect_empty",
    "exact_set",
    "hit_at_1",
    "include",
    "forbid",
    "cities",
    "max_tier",
    "min_tier",
    "require_tag",
)
META = ("id", "query", "group", "note")


@dataclass
class Grade:
    case_id: str
    query: str
    group: str
    ok: bool
    failures: list
    names: list
    note: str

    @property
    def message(self):
        shown = ", ".join(self.names) if self.names else "(no spots)"
        lines = [f"{self.case_id}  query={self.query!r}  group={self.group}", self.note, f"got: {shown}"]
        lines.extend(self.failures)
        return "\n".join(lines)

    @property
    def one_liner(self):
        shown = ", ".join(self.names) if self.names else "(no spots)"
        reason = self.failures[0] if self.failures else "failed"
        return f"got {shown}. {reason}"


def load_cases(path=GOLDEN_PATH):
    data = json.loads(path.read_text())
    cases = data["cases"] if isinstance(data, dict) else data
    ids = [case["id"] for case in cases]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate golden ids: {dupes}")
    for case in cases:
        missing = [key for key in META if key not in case]
        if missing:
            raise ValueError(f"golden case missing {missing}: {case.get('id')}")
        if not any(key in case for key in CONSTRAINTS):
            raise ValueError(f"golden case {case['id']} has no constraint")
        if case.get("expect_empty") and any(key in case for key in CONSTRAINTS if key != "expect_empty"):
            raise ValueError(f"golden case {case['id']} combines expect_empty with other constraints")
    return cases


def _names_ok(values, by_name, case_id, failures):
    unknown = [name for name in values if name not in by_name]
    if unknown:
        failures.append(f"label bug: {unknown} are not names in data/spots.json ({case_id})")
    return not unknown


def grade_case(case, ranked, by_name):
    failures = []
    names = list(ranked.names)
    for key in ("exact_set", "hit_at_1", "include", "forbid"):
        if key in case:
            _names_ok(case[key], by_name, case["id"], failures)
    if "cities" in case:
        known = {spot["city"] for spot in by_name.values()}
        bad = [city for city in case["cities"] if city not in known]
        if bad:
            failures.append(f"label bug: cities {bad} are not city values in data/spots.json")

    if case.get("expect_empty"):
        if names:
            failures.append("expected no spots, because nothing in the notebook fits")
    else:
        if "exact_set" in case and set(names) != set(case["exact_set"]):
            failures.append(f"expected exactly these spots: {case['exact_set']}")
        if "hit_at_1" in case and (not names or names[0] not in case["hit_at_1"]):
            failures.append(f"expected rank 1 to be one of {case['hit_at_1']}")
        if "include" in case:
            missing = [name for name in case["include"] if name not in names]
            if missing:
                failures.append(f"missing {missing}")
        if "forbid" in case:
            leaked = [name for name in case["forbid"] if name in names]
            if leaked:
                failures.append(f"irrelevant spot in the candidate list: {leaked}")
        if "cities" in case:
            for name in names:
                spot = by_name.get(name)
                if spot and spot["city"] not in case["cities"]:
                    failures.append(f"{name} is in {spot['city']}, not in {case['cities']}")
            if not names:
                failures.append(f"expected spots in {case['cities']}, got none")
        if "max_tier" in case or "min_tier" in case:
            if not names:
                failures.append("expected at least one spot so the price filter could be checked")
            for name in names:
                spot = by_name.get(name)
                if not spot:
                    continue
                tier = price_tier(spot["price"])
                if "max_tier" in case and tier > case["max_tier"]:
                    failures.append(
                        f"{name} is price tier {tier} ({spot['price']}), above max {case['max_tier']}"
                    )
                if "min_tier" in case and tier < case["min_tier"]:
                    failures.append(
                        f"{name} is price tier {tier} ({spot['price']}), below min {case['min_tier']}"
                    )
        if "require_tag" in case:
            needle = case["require_tag"].lower()
            if not names:
                failures.append(f"expected a spot tagged {needle!r}, got none")
            for name in names:
                spot = by_name.get(name)
                tags = [tag.lower() for tag in spot["tags"]] if spot else []
                if not any(needle in tag for tag in tags):
                    failures.append(f"{name} has tags {spot['tags'] if spot else []}, none containing {needle!r}")

    # De-duplicate while keeping order (a city loop may append once per spot).
    deduped = list(dict.fromkeys(failures))
    return Grade(
        case_id=case["id"],
        query=case["query"],
        group=case["group"],
        ok=not deduped,
        failures=deduped,
        names=names,
        note=case["note"],
    )


def grade_all(cases, by_query, by_name):
    grades = []
    for case in cases:
        ranked = by_query.get(case["query"])
        if ranked is None:
            grades.append(
                Grade(
                    case_id=case["id"],
                    query=case["query"],
                    group=case["group"],
                    ok=False,
                    failures=["ranker returned no row for this query"],
                    names=[],
                    note=case["note"],
                )
            )
            continue
        grades.append(grade_case(case, ranked, by_name))
    return grades


def format_scoreboard(grades):
    by_group = {}
    for grade in grades:
        passed, total = by_group.get(grade.group, (0, 0))
        by_group[grade.group] = (passed + int(grade.ok), total + 1)
    passed = sum(1 for grade in grades if grade.ok)
    lines = [f"Retrieval labels: {passed} passed, {len(grades) - passed} failed, {len(grades)} total"]
    for group in sorted(by_group):
        got, total = by_group[group]
        lines.append(f"  {group:<16} {got}/{total}")
    failed = [grade for grade in grades if not grade.ok]
    if failed:
        lines.append("Failed labels:")
        for grade in failed:
            lines.append(f"  {grade.case_id}: {grade.one_liner}")
    else:
        lines.append("Failed labels: none")
    return "\n".join(lines)
