"""Deterministic checks for a Jay's Take blurb.

These encode the rules in app.SYSTEM that can be checked without another model:
the blurb names a real candidate, does not name a restaurant absent from the
notes it was given, does not repeat press-only dish names, and stays in the
plain-text format the prompt demands. Claim-level grounding is the live judge.
"""

import re
from dataclasses import dataclass

from evals.catalog import load_reviews

BANNED_PHRASES = ("nestled", "hidden gem")
PROFANITY = ("fuck", "shit", "bitch", "asshole", "cunt")


@dataclass
class OutputGrade:
    ok: bool
    issues: list

    @property
    def message(self):
        return "\n".join(self.issues) if self.issues else "ok"


def catalog_names_in(text, catalog_names):
    """Longest-first, case-insensitive, non-overlapping name matches."""
    found = []
    occupied = [False] * len(text)
    lower = text.lower()
    for name in sorted(catalog_names, key=len, reverse=True):
        needle = name.lower()
        start = 0
        while True:
            index = lower.find(needle, start)
            if index < 0:
                break
            end = index + len(needle)
            if not any(occupied[index:end]):
                for pos in range(index, end):
                    occupied[pos] = True
                found.append(name)
            start = index + 1
    return found


def sentence_count(text):
    parts = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text.strip())
    return len([part for part in parts if part.strip()])


def press_only_phrases(spot_names):
    """Dish names and outlet names that appear in reviews but are not notes."""
    reviews = load_reviews()
    phrases = []
    for name in spot_names:
        for review in reviews.get("reviews", {}).get(name, []):
            outlet = (review.get("outlet") or "").strip()
            if len(outlet) >= 5:
                phrases.append(outlet)
            dishes = review.get("dishes") or ""
            for part in dishes.split(","):
                phrase = part.strip()
                if len(phrase) >= 4:
                    phrases.append(phrase)
    return phrases


def grade_blurb(text, *, candidate_names, notes, catalog_names):
    issues = []
    if not text or not str(text).strip():
        return OutputGrade(False, ["blurb is empty"])
    text = str(text).strip()
    lowered = text.lower()

    if "\u2014" in text or "\u2013" in text:
        issues.append("contains an em dash or en dash; the system prompt forbids em dashes")
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            issues.append(f"contains {phrase!r}, which the system prompt bans")
    for word in PROFANITY:
        if re.search(rf"\b{word}\b", lowered):
            issues.append(f"contains profanity {word!r}")
    if "```" in text or re.search(r"<[a-z][^>]*>", lowered) or text.lstrip().startswith("#"):
        issues.append("not plain text")

    count = sentence_count(text)
    if count < 2 or count > 3:
        issues.append(f"expected 2 to 3 sentences, found {count}")

    mentioned = catalog_names_in(text, catalog_names)
    if not any(name in candidate_names for name in mentioned):
        named = ", ".join(mentioned) if mentioned else "no catalog restaurant"
        issues.append(f"does not name a candidate spot ({named})")

    notes_lower = notes.lower()
    for name in mentioned:
        if name.lower() not in notes_lower:
            issues.append(f"names {name}, which is not in the notes given to the model")

    for phrase in press_only_phrases(candidate_names):
        if phrase.lower() in lowered and phrase.lower() not in notes_lower:
            issues.append(
                f"mentions {phrase!r}, which is in a press review but not in the notes sent to the model"
            )

    return OutputGrade(not issues, issues)
