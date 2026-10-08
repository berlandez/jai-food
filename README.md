# J(AI)

Tell it what you're craving; it sends you where Jay would actually go.

Every recommendation comes from Jay's own restaurant notes (30 spots across the Bay Area, NYC, Paris, and London), with press and critic reviews attached. As you type, the app ranks the notebook instantly in the browser, then Claude writes a short "Jay's Take" in Jay's voice, grounded only in those notes.

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key-here
.venv/bin/python app.py
```

Open http://127.0.0.1:5050.

Without an API key the search and cards still work; only the "Jay's Take" blurb is skipped.

## Edit the notebook

All content lives in `data/`, no code changes needed:

- `data/spots.json`: the restaurants (name, city, neighborhood, category, price, tags, Jay's take, get / skip / tip). Set `"love": true` for the "two snaps up" badge, and `"maps"` to pin an exact Google Maps link.
- `data/reviews.json`: press and critic reviews keyed by spot name, plus outlet brand colors.
- `data/chips.json`: the quick-pick craving chips and the "surprise me" pool.

## How it works

- `static/`: the UI. Search scoring runs in `app.js` (tag matches, craving synonyms, price tiers for "cheap" vs "splurge").
- `app.py`: Flask server. `GET /api/data` serves the notebook; `POST /api/pick` takes the craving and the top matching spot names, loads those spots' notes from disk, and asks Claude (`claude-opus-5-5` by default, override with `JAI_MODEL`) for a 2 to 3 sentence pick.

## Deploy (Render)

1. Sign in at [render.com](https://render.com) with GitHub.
2. **New → Blueprint**, pick this repo. Render reads `render.yaml`.
3. Paste your `ANTHROPIC_API_KEY` when it asks, then **Apply**.

You get a public `https://jai-food.onrender.com`-style URL, and every push to `main` redeploys. The free plan sleeps after 15 idle minutes, so the first visit after a nap takes ~30 seconds to wake.

### Cost guards

Every AI pick spends API credits, so the server:

- caches picks (same craving + same spots = no new API call),
- limits each visitor to 30 picks an hour (`JAI_PER_IP_HOURLY`),
- caps the whole app at 1,000 picks a day (`JAI_DAILY_CAP`).

Over a limit, the search and cards keep working; only the AI blurb pauses. Also set a monthly spend limit in the Anthropic Console under Settings → Limits.
