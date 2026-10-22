"""Live claim grader. One Claude call, JSON back, no charm scoring."""

import json
import re

import anthropic

import app as jai

JUDGE_SYSTEM = (
    "You grade a restaurant blurb against source notes. Return one JSON object "
    "and nothing else, with these keys:\n"
    '- "invented_restaurant": true if the blurb names a venue that is neither a '
    "candidate nor mentioned in the notes\n"
    '- "mislocated": true if the blurb places a spot in a city or neighborhood '
    "the notes do not support\n"
    '- "unsupported_claims": array of short strings. Each item is a concrete '
    "factual claim about food, price, neighborhood, or quality that the notes do "
    "not support. Paraphrase is allowed. Use an empty array when every concrete "
    "claim is supported. Do not list style complaints.\n"
    '- "pass": true only when invented_restaurant is false, mislocated is false, '
    "and unsupported_claims is empty\n"
    "Do not grade charm or whether you would have picked a different candidate."
)


def parse_judge_json(text):
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"judge did not return a JSON object:\n{text}")
    data = json.loads(raw[start : end + 1])
    for key in ("invented_restaurant", "mislocated", "unsupported_claims", "pass"):
        if key not in data:
            raise ValueError(f"judge JSON missing {key}: {data}")
    if not isinstance(data["unsupported_claims"], list):
        raise ValueError(f"unsupported_claims was not a list: {data}")
    return data


def judge_blurb(*, query, notes, blurb, extra=""):
    user = (
        f"Reader asked: {query}\n\n"
        f"Notes the writer was allowed to use:\n{notes}\n\n"
        f"Blurb:\n{blurb}\n"
    )
    if extra:
        user += f"\nExtra grading note:\n{extra}\n"
    client = anthropic.Anthropic(timeout=90)
    resp = client.beta.messages.create(
        model=jai.MODEL,
        max_tokens=1024,
        system=JUDGE_SYSTEM,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    return parse_judge_json(text)


def judge_failures(verdict):
    reasons = []
    if verdict.get("invented_restaurant"):
        reasons.append("judge: invented a restaurant")
    if verdict.get("mislocated"):
        reasons.append("judge: placed a spot in a city the notes do not support")
    claims = [str(item) for item in verdict.get("unsupported_claims") or [] if str(item).strip()]
    if claims:
        reasons.append("judge: unsupported claims: " + "; ".join(claims))
    if not verdict.get("pass") and not reasons:
        reasons.append("judge: pass was false")
    return reasons
