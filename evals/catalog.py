"""Load the notebook the app serves, plus the price-tier rule from static/app.js."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Queries that exercise the cheap / splurge tier adjustments in score().
PRICE_CHEAP_QUERIES = ["cheap", "budget", "broke", "cheap eats"]
PRICE_SPLURGE_QUERIES = ["fancy", "splurge", "baller", "upscale"]

REQUIRED_SPOT_FIELDS = ("name", "city", "hood", "cat", "price", "tags", "take")


def load_json(name):
    return json.loads((DATA / name).read_text())


def load_spots():
    return load_json("spots.json")


def load_reviews():
    return load_json("reviews.json")


def load_chips():
    return load_json("chips.json")


def price_tier(price):
    """Same rule as static/app.js: count leading $ characters."""
    match = re.match(r"^\$+", price or "")
    return len(match.group(0)) if match else 0


def spots_by_name(spots=None):
    spots = load_spots() if spots is None else spots
    return {spot["name"]: spot for spot in spots}
