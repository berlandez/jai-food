# E.A.T. evals

These grade two different things:

1. **Retrieval.** As you type, `static/app.js` ranks Jay's notes in the browser (`score` and `pick`) and keeps at most three spots. The eval loads that file and runs those functions. It does not reimplement them.
2. **The blurb.** `POST /api/pick` turns those names into notes and asks Claude for 2 to 3 sentences. Format and "did you name a real spot from the notes" are checked with string rules. Whether the sentences are actually true to the notes is a second Claude call, and it runs only when `ANTHROPIC_API_KEY` is set.

Nothing under `app.py`, `static/`, `data/`, or the Render config is modified. The ranker has gaps. The labeled cases that catch them fail on purpose. A failing quality case means that label missed.

## Run

From the repo root, with Node 18+ on `PATH` (the ranker is JavaScript):

```bash
python3 -m venv .venv
.venv/bin/pip install -r evals/requirements.txt
.venv/bin/python -m evals
```

That is the whole offline suite. It does not call Anthropic. At the bottom, pytest prints a retrieval scoreboard: passed and failed labels by group, then one line per miss. The scoreboard is the full golden file, including when pytest was filtered with `-k` or `-m`.

Live blurb graders run in the same command when `ANTHROPIC_API_KEY` is set. They call the real `/api/pick` route and then a judge, so they spend credits. To keep them off even if a key is present:

```bash
.venv/bin/python -m evals --offline
```

Other switches, all optional:

```bash
.venv/bin/python -m evals -- -m mechanics   # notebook, ranker, and route contracts
.venv/bin/python -m evals -- -m quality     # labeled retrieval cases only
.venv/bin/python -m evals --llm             # live blurbs only; skips cleanly with no key
```

Arguments after the script are pytest arguments. `python -m evals -- -k paris` works.

## How to read a result

Mechanics tests (`-m mechanics`) should pass. They check that the notebook is well formed, that `pick` returns at most three notebook spots in score order, that cheap and splurge words respect price tier, that craving chips retrieve something, and that `/api/pick` builds its prompt from the named notes only. Unknown restaurant names are dropped. Press reviews never enter the prompt. A blank query is random on purpose (`Math.random` in `score`) and is only checked for "three real spots, not a fixed list."

Quality tests (`-m quality`) are judgments in `golden_retrieval.json`. Each case has a `note` that says why the label is what it is. A failure prints the query, the spots `pick` actually returned, and which constraint missed. Constraints:

| Field | Meaning |
| --- | --- |
| `exact_set` | These spots and no others, any order |
| `hit_at_1` | Rank 1 is one of these |
| `include` | Each of these appears somewhere in the top 3 |
| `forbid` | None of these appear. Rank 1 can still be right |
| `cities` | Every candidate is in one of these notebook city strings |
| `max_tier` / `min_tier` | Price tier, counted as leading `$` the same way `app.js` does |
| `require_tag` | Every candidate has a tag containing this string |
| `expect_empty` | Nothing should match. The UI then shows the empty state and does not call Claude |

The scoreboard counts labels, not a smoothed percentage. Do not treat a forbid-case pass as "the query is fine" if its companion `hit_at_1` case failed, or the reverse. Several queries are labeled twice on purpose: once for "the right spot is first," once for "an irrelevant spot still leaked into the three names Claude will see."

Groups in the scoreboard:

- **chip, cuisine, city, price, synonym, conjunction** cover the craving chips, single-topic queries, cities, and queries that stack a constraint (cheap pizza, steak in Paris).
- **false-friend** is substring damage. Tag hits use `query.includes(tag)` with no word boundary (`tea` inside `steak`, `cheap` inside `cheesecake`). Note-words use the same containment (`past` inside `pastrami`, `over` inside `hangover`, `best` inside a take that is not about the craving).
- **out-of-notebook** is the graceful fallback: Tokyo, ramen, tacos, and other cravings with no note should return no spots.

The city string for San Francisco spots is `SF`. `NYC` matches because Michael's Bagels has an `nyc` tag. `SF` and `San Francisco` do not, and the word scorer ignores tokens of length 3 or less. Those labels are supposed to return SF spots. If they fail, that is the finding.

## Live blurbs

`golden_output.json` lists the cravings. For each one the suite:

1. Ranks with the real `pick`, unless the case pins `names` (the Tokyo case sends Jules on purpose, which is what a client is allowed to POST).
2. Calls `POST /api/pick` so the prompt, model (`JAI_MODEL`, otherwise `claude-opus-5-5`), and error mapping are the app's.
3. Checks the text: 2 to 3 sentences, plain text, no em dash, no "nestled" or "hidden gem", names a candidate, does not name a notebook restaurant that was not in the notes, does not repeat a press-review dish or outlet that the notes never mention.
4. Asks Claude for a JSON verdict on invented venues, wrong cities, and claims the notes do not support. Style is not graded. `evals/test_output_grader.py` shows the hole in step 3: a venue that is not in the notebook at all ("Nobu") is not caught by string matching when a real candidate is also named. The judge is there for that.

Out-of-notebook behavior is split the way the product is split:

- If `pick` returns nothing, the UI never requests a blurb. That is an offline label (`expect_empty`), and the route itself returns 400 when `names` is empty.
- If a client sends a covered spot for an uncovered city, the live case allows a refusal (HTTP 422) or a blurb that does not move the spot or invent a restaurant.

Without a key, those tests are skipped and reported as skipped. They are not counted as passes.

## Layout

```
evals/rank_bridge.js          loads static/app.js and calls score/pick
evals/ranking.py              Python wrapper around the bridge
evals/golden_retrieval.json   labeled queries
evals/grade_retrieval.py      scores a pick() result against a label
evals/grade_output.py         deterministic blurb checks
evals/golden_output.json      live blurb cases
evals/judge.py                claim grader (needs a key)
evals/test_invariants.py      mechanics
evals/test_retrieval.py       quality labels
evals/test_server.py          /api/pick without a live model
evals/test_output_grader.py   canned blurbs
evals/test_llm.py             live blurbs
```

`rank_bridge.js` refuses to guess if `score` / `pick` disappear or `app.js` no longer ends in a bare `init()` call. Init is the DOM boot (`fetch`, chips, cards). The bridge skips that call and loads `data/spots.json` into the `SPOTS` binding `pick` closes over. The strings passed in are the trimmed queries the input handler would pass to `pick`.

When the notebook grows, update labels whose sets changed. A new pizza spot should fail `chip-pizza` until the label names it.

## What this does not cover

The CSS, the map links, and typing in a browser are untested. The suite never starts the Render deploy. It does not claim a live pass rate unless you ran it with a key and kept the pytest output. Re-running the live cases spends credits and can trip Anthropic rate limits; the in-process hourly cap is reset inside the test process so the suite itself does not lock you out.
