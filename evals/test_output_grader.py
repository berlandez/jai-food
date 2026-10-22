"""The blurb grader, checked against canned text so it can fail offline.

A made-up venue that is not in the notebook at all is intentionally left to
the live judge. These tests pin that boundary instead of pretending the
string checks cover it.
"""

import pytest

import app as jai
from evals.grade_output import grade_blurb

pytestmark = pytest.mark.mechanics

CATALOG = list(jai.SPOTS_BY_NAME)


def _grade(text, candidates):
    notes = "\n\n".join(jai.notes_for(jai.SPOTS_BY_NAME[name]) for name in candidates)
    return grade_blurb(text, candidate_names=candidates, notes=notes, catalog_names=CATALOG)


def test_grounded_jules_blurb_passes():
    text = "Get the Hot Sailor at Jules. Anchovy salinity on a spicy sauce, crust burnt well done."
    grade = _grade(text, ["Jules"])
    assert grade.ok, grade.message


def test_press_only_dish_is_rejected():
    text = "Get the Drunken Sailor at Jules. The crust is burnt and the anchovies are the point."
    grade = _grade(text, ["Jules"])
    assert not grade.ok
    assert any("Drunken Sailor" in issue for issue in grade.issues)


def test_catalog_spot_outside_the_notes_is_rejected():
    text = "Skip Jules and go to Rintaro. The yakitori char is the whole point."
    grade = _grade(text, ["Jules"])
    assert not grade.ok
    assert any("Rintaro" in issue for issue in grade.issues)


def test_a_name_mentioned_inside_the_notes_is_allowed():
    text = (
        "Loquat Bakery's kubaneh is the move, amba and silky labneh. "
        "Jules did pop-ups here, and the cinnamon rugelach is pillowy."
    )
    grade = _grade(text, ["Loquat Bakery"])
    assert grade.ok, grade.message


def test_format_rules_from_the_system_prompt():
    em = "Get the Hot Sailor at Jules \u2014 anchovy on a spicy sauce. The crust is burnt well done."
    assert any("em dash" in issue for issue in _grade(em, ["Jules"]).issues)
    gem = "Jules is a hidden gem. Get the Hot Sailor."
    assert any("hidden gem" in issue for issue in _grade(gem, ["Jules"]).issues)
    nestled = "Jules is nestled in the city. Get the Hot Sailor."
    assert any("nestled" in issue for issue in _grade(nestled, ["Jules"]).issues)
    short = "Get the Hot Sailor at Jules."
    assert any("sentences" in issue for issue in _grade(short, ["Jules"]).issues)
    long = "Go to Jules. Get the Hot Sailor. The crust is burnt. Add the feta salad. Drink the Lambrusco."
    assert any("sentences" in issue for issue in _grade(long, ["Jules"]).issues)
    empty = _grade("   ", ["Jules"])
    assert not empty.ok


def test_blurb_must_name_a_candidate():
    text = "The anchovy pie is the one to get. Ask for it burnt well done."
    grade = _grade(text, ["Jules"])
    assert not grade.ok
    assert any("does not name" in issue for issue in grade.issues)


def test_unknown_venue_is_not_fully_caught_without_the_judge():
    # Nobu is not a notebook restaurant, and Jules is a real candidate, so the
    # string checks have nothing to reject. The live judge owns this case.
    text = "Start at Jules, then walk to Nobu for omakase. The crust at Jules is still the one."
    grade = _grade(text, ["Jules"])
    assert grade.ok, grade.message
    assert not any("Nobu" in issue for issue in grade.issues)
