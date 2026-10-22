"""Contracts the ranker and the notebook have to keep, independent of taste."""

import re

import pytest

from evals.catalog import PRICE_CHEAP_QUERIES, PRICE_SPLURGE_QUERIES, load_reviews, price_tier
from evals.ranking import rank_queries

pytestmark = pytest.mark.mechanics


def test_spot_records_are_well_formed(world):
    names = [spot["name"] for spot in world.spots]
    assert names, "spots.json is empty"
    assert len(names) == len(set(names)), "duplicate restaurant names"
    required = ("name", "city", "hood", "cat", "price", "tags", "take")
    for spot in world.spots:
        for field in required:
            assert spot.get(field), f"{spot.get('name')} missing {field}"
        assert re.match(r"^\$+", spot["price"]), spot["name"]
        assert isinstance(spot["tags"], list) and spot["tags"], spot["name"]
        assert all(isinstance(tag, str) and tag.strip() for tag in spot["tags"]), spot["name"]
        for optional in ("get", "skip", "tip"):
            if optional in spot:
                assert isinstance(spot[optional], str) and spot[optional].strip(), spot["name"]


def test_reviews_point_at_real_spots(world):
    payload = load_reviews()
    styles = payload["outlet_style"]
    for name, reviews in payload["reviews"].items():
        assert name in world.by_name, name
        assert reviews, name
        for review in reviews:
            assert review.get("outlet") in styles, (name, review.get("outlet"))
            assert str(review.get("url", "")).startswith("http"), (name, review.get("url"))


def test_chips_are_non_empty_strings(world):
    chips = world.chips["chips"]
    surprises = world.chips["surprises"]
    assert chips and surprises
    assert all(isinstance(chip, str) and chip.strip() for chip in chips)
    assert all(isinstance(item, str) and item.strip() for item in surprises)
    assert "surprise me" in chips
    assert len(chips) == len(set(chips))


def test_craving_chips_retrieve_a_spot(world):
    for chip in world.chips["chips"]:
        names = world.ranked[chip].names
        if chip == "surprise me":
            assert names == [], "the literal chip is rewritten by the UI before search"
        else:
            assert names, chip


def test_surprise_pool_retrieves_a_spot(world):
    for query in world.chips["surprises"]:
        assert world.ranked[query].names, query


def test_results_are_notebook_spots_in_score_order(world):
    order = {spot["name"]: index for index, spot in enumerate(world.spots)}
    for query, ranked in world.ranked.items():
        assert len(ranked.scores) == len(world.spots), query
        seen = [name for name, _score in ranked.scores]
        assert seen == list(dict.fromkeys(seen)), query
        assert set(seen) == set(world.by_name), query
        for (left_name, left_score), (right_name, right_score) in zip(ranked.scores, ranked.scores[1:]):
            assert left_score >= right_score, (query, left_name, left_score, right_name, right_score)
            if left_score == right_score:
                assert order[left_name] < order[right_name], (query, left_name, right_name)
        expected = [name for name, score in ranked.scores if score > 0][:3]
        assert ranked.names == expected, (query, ranked.names, expected)
        assert len(ranked.names) == len(set(ranked.names)) <= 3


def test_ranking_a_real_query_is_deterministic():
    first = rank_queries(["pizza", "date night"])
    second = rank_queries(["pizza", "date night"])
    assert first.by_query["pizza"].names == second.by_query["pizza"].names
    assert first.by_query["date night"].scores == second.by_query["date night"].scores


def test_queries_are_case_insensitive(world):
    assert world.ranked["pizza"].names == world.ranked["Pizza"].names == world.ranked["PIZZA"].names


def test_blank_query_samples_three_real_spots_and_is_not_a_fixed_list(world):
    samples = world.empty_samples
    assert len(samples) >= 8
    for names in samples:
        assert len(names) == 3
        assert len(set(names)) == 3
        assert set(names) <= set(world.by_name)
    assert len({tuple(names) for names in samples}) >= 2


def test_cheap_words_exclude_the_top_price_tier(world):
    for query in PRICE_CHEAP_QUERIES:
        for name in world.ranked[query].names:
            tier = price_tier(world.by_name[name]["price"])
            assert tier <= 2, (query, name, world.by_name[name]["price"])


def test_splurge_words_keep_only_the_top_price_tier(world):
    for query in PRICE_SPLURGE_QUERIES:
        names = world.ranked[query].names
        assert names, query
        for name in names:
            tier = price_tier(world.by_name[name]["price"])
            assert tier >= 3, (query, name, world.by_name[name]["price"])
