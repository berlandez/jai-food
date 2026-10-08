"""J(AI): craving in, Jay's restaurant pick out.

Serves the static UI and one API route that asks Claude to write a pick
from Jay's own notes. Search/ranking runs in the browser; the server only
does the part that needs a model.
"""
import json
import logging
import os
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
MODEL = os.environ.get("JAI_MODEL", "claude-opus-5-5")

app = Flask(__name__, static_folder="static", static_url_path="/static")
# Hosts like Render sit behind one proxy; trust its X-Forwarded-For for client IPs.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
log = logging.getLogger("jai")

SPOTS = json.loads((DATA / "spots.json").read_text())
SPOTS_BY_NAME = {s["name"]: s for s in SPOTS}

SYSTEM = (
    "You are Jay Tova, a food writer from Queens now in the SF Bay Area. "
    "Voice: dry, specific, hip-hop cadence, sensory, blunt. Keep it clean: no profanity or crude innuendo. "
    "NO em dashes, no AI cliches, no \"nestled\" or \"hidden gem\" slop. "
    "From ONLY the spots provided (these are your own notes, with your real takes), "
    "pick the single best one for the reader's craving and write a 2 to 3 sentence "
    "recommendation in your voice, grounded only in the notes given. Name the spot. "
    "Do not invent dishes or facts not in the notes. Return plain text only."
)

_client = None

# Abuse guards for a public deploy: every pick spends API credits.
PER_IP_HOURLY = int(os.environ.get("JAI_PER_IP_HOURLY", 30))
DAILY_CAP = int(os.environ.get("JAI_DAILY_CAP", 1000))
_hits = defaultdict(deque)
_day = {"date": None, "count": 0}
_cache = OrderedDict()
CACHE_SIZE = 500


def over_limit(ip):
    now = time.time()
    q = _hits[ip]
    while q and q[0] < now - 3600:
        q.popleft()
    today = time.strftime("%Y-%m-%d")
    if _day["date"] != today:
        _day.update(date=today, count=0)
    if len(q) >= PER_IP_HOURLY or _day["count"] >= DAILY_CAP:
        return True
    q.append(now)
    _day["count"] += 1
    return False


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def notes_for(spot):
    lines = [f"## {spot['name']} ({spot['cat']}, {spot['hood']}, {spot['city']}, {spot['price']})",
             f"Take: {spot['take']}"]
    for key in ("get", "skip", "tip"):
        if spot.get(key):
            lines.append(f"{key.capitalize()}: {spot[key]}")
    return "\n".join(lines)


@app.get("/")
def index():
    return send_from_directory(ROOT / "static", "index.html")


@app.get("/api/data")
def data():
    reviews = json.loads((DATA / "reviews.json").read_text())
    chips = json.loads((DATA / "chips.json").read_text())
    return jsonify(spots=SPOTS, **reviews, **chips)


@app.post("/api/pick")
def pick():
    body = request.get_json(silent=True) or {}
    q = str(body.get("q", "")).strip()[:200]
    # Only trust names that exist in the notebook; the notes come from disk, not the client.
    spots = [SPOTS_BY_NAME[n] for n in body.get("names", [])[:3] if n in SPOTS_BY_NAME]
    if len(q) < 2 or not spots:
        return jsonify(error="need a craving and at least one known spot"), 400

    key = (q.lower(), tuple(s["name"] for s in spots))
    if key in _cache:
        _cache.move_to_end(key)
        return jsonify(text=_cache[key])
    if over_limit(request.remote_addr or "?"):
        return jsonify(error="J(AI) needs a breather, try again later"), 429

    prompt = (f'The reader asked for: "{q}"\n\nYour notes on the candidate spots:\n\n'
              + "\n\n".join(notes_for(s) for s in spots))
    try:
        resp = client().beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        log.warning("Anthropic auth failed; set ANTHROPIC_API_KEY")
        return jsonify(error="AI picks are not configured"), 503
    except anthropic.RateLimitError:
        return jsonify(error="rate limited, try again in a moment"), 429
    except anthropic.APIStatusError as e:
        log.error("Anthropic API error %s: %s", e.status_code, e.message)
        return jsonify(error="AI pick failed"), 502
    except anthropic.APIConnectionError:
        return jsonify(error="could not reach the AI"), 502
    except (anthropic.AnthropicError, TypeError):
        # No credentials resolved (no ANTHROPIC_API_KEY or `ant auth login` profile).
        log.warning("No Anthropic credentials; AI picks disabled")
        return jsonify(error="AI picks are not configured"), 503

    if resp.stop_reason == "refusal":
        return jsonify(error="no pick for that one"), 422
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    _cache[key] = text
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return jsonify(text=text)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5050)), debug=True)
