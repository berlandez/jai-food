// Run the real ranking functions from static/app.js.
//
// Search lives in the browser. This harness loads that file unchanged,
// skips the DOM boot at the bottom (init), and injects data/spots.json
// into the SPOTS binding that pick() closes over. It does not reimplement
// scoring. If score/pick disappear or the file no longer ends in init(),
// the harness exits non-zero instead of guessing.

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const APP_JS = path.join(ROOT, "static", "app.js");
const SPOTS_PATH = path.join(ROOT, "data", "spots.json");

function loadRanker() {
  const src = fs.readFileSync(APP_JS, "utf8");
  if (!src.includes("function score(spot, q)") || !src.includes("function pick(q)")) {
    throw new Error(
      "static/app.js no longer defines function score(spot, q) and function pick(q); " +
        "the eval harness refuses to reimplement ranking"
    );
  }
  if (!/\ninit\(\);\s*$/.test(src)) {
    throw new Error(
      "static/app.js no longer ends with a bare init() call; " +
        "update evals/rank_bridge.js before trusting rankings"
    );
  }
  const patched = src.replace(
    /\ninit\(\);\s*$/,
    "\nfunction __loadSpots(spots){ SPOTS = spots; }\n" +
      "function __spotCount(){ return SPOTS.length; }\n"
  );
  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    document: {
      querySelector() {
        return {
          value: "",
          innerHTML: "",
          appendChild() {},
          addEventListener() {},
          querySelector() {
            return null;
          },
        };
      },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(patched, sandbox, { filename: APP_JS });
  const spots = JSON.parse(fs.readFileSync(SPOTS_PATH, "utf8"));
  sandbox.__loadSpots(spots);
  // `let SPOTS` is a script lexical binding, not a property of the global object,
  // so the length check goes through a function that closes over that binding.
  if (sandbox.__spotCount() !== spots.length) {
    throw new Error("failed to inject spots into the real pick() closure");
  }
  return { sandbox, spots };
}

function rankOne(sandbox, spots, query) {
  const rows = spots.map((s) => ({ name: s.name, score: sandbox.score(s, query) })).sort(
    (a, b) => b.score - a.score
  );
  const names = sandbox.pick(query).map((s) => s.name);
  return { query, names, scores: rows };
}

function main() {
  const raw = fs.readFileSync(0, "utf8");
  let req;
  try {
    req = JSON.parse(raw || "{}");
  } catch (err) {
    throw new Error("rank bridge expected a JSON object on stdin");
  }
  const { sandbox, spots } = loadRanker();
  const queries = Array.isArray(req.queries) ? req.queries : [];
  const results = queries.map((q) => rankOne(sandbox, spots, String(q)));
  const emptySamples = [];
  const nEmpty = Number(req.empty_samples || 0);
  for (let i = 0; i < nEmpty; i++) emptySamples.push(sandbox.pick("").map((s) => s.name));
  process.stdout.write(JSON.stringify({ results, empty_samples: emptySamples }));
}

try {
  main();
} catch (err) {
  process.stderr.write(String(err && err.stack ? err.stack : err) + "\n");
  process.exit(1);
}
