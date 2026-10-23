// E.A.T. ranks the notebook in the browser as you type, then asks the
// server for a written pick from the top matches.
//
// score() matches whole tokens, not substrings. SF and San Francisco are
// one city, and NYC and New York are one city. A stacked query (cheap pizza,
// steak in Paris) has to satisfy every constraint.

let SPOTS = [], REVIEWS = {}, OUTLET_STYLE = {}, CHIPS = [], SURPRISES = [];

const $ = s => document.querySelector(s);
const results = $("#results");
let pickTimer = null;
let pickAbort = null;

function renderChips(){
  const c = $("#chips");
  CHIPS.forEach(t => {
    const b = document.createElement("span");
    b.className = "chip"; b.textContent = t;
    b.onclick = () => {
      $("#q").value = (t === "surprise me") ? SURPRISES[Math.floor(Math.random()*SURPRISES.length)] : t;
      onInput();
    };
    c.appendChild(b);
  });
}

const STOP = new Set(["a","an","the","for","in","on","at","and","or","with","to","of","me","my","it"]);
const CHEAP_WORDS = ["cheap","budget","broke"];
const SPLURGE_WORDS = ["splurge","fancy","baller","upscale"];
const SYN = {
  coffee: ["coffee","cafe","latte","espresso"],
  cheap: ["cheap","broke","budget"],
  date: ["date","romantic"],
  hangover: ["hangover","greasy","cure"],
  breakfast: ["breakfast","brunch","morning"],
  veg: ["vegetarian","veggie","veg","vegan"],
  splurge: ["splurge","fancy","treat","baller"]
};

function fold(value){
  return String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function tokenize(value){
  return fold(value).split(/[^a-z0-9]+/).filter(Boolean);
}

function hasWord(text, word){
  return new RegExp("\\b" + word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(fold(text));
}

function canonicalCity(phrase){
  const p = fold(phrase).replace(/[^a-z0-9]+/g, " ").trim();
  if(p === "sf" || p === "san francisco") return "sf";
  if(p === "nyc" || p === "new york" || p === "new york city") return "nyc";
  return p;
}

function cityPhrases(){
  const phrases = new Map();
  function add(phrase){
    const text = fold(phrase).replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
    if(text) phrases.set(text, canonicalCity(text));
  }
  SPOTS.forEach(spot => {
    add(spot.city);
    fold(spot.city).split(",").forEach(add);
  });
  add("san francisco");
  add("new york");
  add("new york city");
  return [...phrases.entries()].sort((a, b) => b[0].length - a[0].length);
}

function spotCityKeys(spot){
  const keys = new Set();
  fold(spot.city).split(",").forEach(part => {
    const text = part.trim();
    if(!text) return;
    keys.add(text);
    keys.add(canonicalCity(text));
  });
  if(keys.has("sf")) keys.add("sf");
  if(keys.has("nyc") || fold(spot.city).includes("nyc")) keys.add("nyc");
  return keys;
}

function tagMatchesToken(tag, token){
  return tokenize(tag).some(part => {
    if(part === token) return true;
    // Plurals (cocktail / cocktails) and a short typed prefix (piz / pizza).
    // The leftover has to be tiny so "cheap" does not match "cheesecake".
    return token.length >= 3 && part.startsWith(token) && part.length > token.length && part.length - token.length <= 2;
  });
}

function tagHasKey(tag, key){
  return tokenize(tag).some(part => part === key || (key.length >= 3 && part.startsWith(key) && part.length > key.length));
}

function synonymKeys(token){
  return Object.keys(SYN).filter(key => SYN[key].includes(token));
}

// Tags, name, neighborhood, city, category, and the "get" line. The freeform
// take is not searched: it mentions dishes the note tells you to skip.
function topicWeight(spot, token){
  let w = 0;
  if(spot.tags.some(tag => tagMatchesToken(tag, token))) w += 6;
  if(tokenize(spot.name).includes(token)) w += 4;
  if(tokenize(spot.hood).includes(token)) w += 4;
  if(tokenize(spot.city).includes(token)) w += 3;
  if(tokenize(spot.cat).includes(token)) w += 2;
  if(spot.get && tokenize(spot.get).includes(token)) w += 3;
  if(synonymKeys(token).some(key => spot.tags.some(tag => tagHasKey(tag, key)))) w += 2;
  return w;
}

function parseQuery(q){
  const text = fold(q).replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
  const padded = " " + text + " ";
  let city = null;
  let consumed = [];
  for(const [phrase, key] of cityPhrases()){
    if(padded.includes(" " + phrase + " ")){
      city = key;
      consumed = phrase.split(" ");
      break;
    }
  }
  let price = null;
  if(CHEAP_WORDS.some(word => hasWord(text, word))) price = "cheap";
  if(SPLURGE_WORDS.some(word => hasWord(text, word))) price = "splurge";
  const skip = new Set([...STOP, ...consumed, ...CHEAP_WORDS, ...SPLURGE_WORDS]);
  const topics = tokenize(text).filter(token => !skip.has(token) && SPOTS.some(spot => topicWeight(spot, token) > 0));
  return {city, price, topics};
}

function score(spot, q){
  if(!q) return Math.random();
  const parsed = parseQuery(q);
  if(parsed.city && !spotCityKeys(spot).has(parsed.city)) return 0;
  if(parsed.topics.some(token => topicWeight(spot, token) === 0)) return 0;

  let s = 0;
  if(parsed.city) s += 4;
  parsed.topics.forEach(token => { s += topicWeight(spot, token); });
  const tier = (String(spot.price).match(/^\$+/) || [""])[0].length;
  if(parsed.price === "splurge") s += (tier >= 3 ? 4 : -5);
  if(parsed.price === "cheap") s += (tier <= 1 ? 3 : (tier >= 3 ? -5 : 0));
  // A spot that already met every stacked constraint stays in the list.
  // The price tweak reorders it. It does not throw the only pizza out.
  if((parsed.city || parsed.topics.length) && s <= 0) s = 1;
  return s;
}

function pick(q){
  return SPOTS.map(s => ({s, v: score(s, q)}))
    .sort((a,b) => b.v - a.v)
    .filter((x,i) => i < 3 && (x.v > 0 || !q))
    .map(x => x.s);
}

function el(tag, cls, html){ const e=document.createElement(tag); if(cls)e.className=cls; if(html!=null)e.innerHTML=html; return e; }

function spotCard(s){
  const c = el("div","card");
  const lv = s.love ? ' <span class="love">🫰🫰 two snaps up</span>' : '';
  c.appendChild(el("h3",null,s.name+lv));
  const maps = s.maps || ("https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(s.name + " " + s.hood + " " + s.city));
  c.appendChild(el("div","meta",`<b>${s.cat}</b> &middot; <a class="loc" href="${maps}" target="_blank" rel="noopener noreferrer" title="Open in Google Maps">${s.hood}, ${s.city}</a> &middot; ${s.price}`));
  c.appendChild(el("div","take",s.take));
  if(s.get) c.appendChild(el("div","gst get","<b>Get:</b> "+s.get));
  if(s.skip) c.appendChild(el("div","gst skip","<b>Skip:</b> "+s.skip));
  if(s.tip) c.appendChild(el("div","gst tip","<b>Tip:</b> "+s.tip));
  const b = el("div","badges");
  s.tags.slice(0,5).forEach(t => b.appendChild(el("span","badge",t)));
  c.appendChild(b);
  const revs = REVIEWS[s.name];
  if(revs && revs.length){
    const r = el("div","reviews");
    r.appendChild(el("div","rhead","Press & reviews"));
    revs.forEach(rv => {
      const col = OUTLET_STYLE[rv.outlet] || "#1c1a17";
      let h = `<span class="outlet" style="color:${col}">${rv.outlet}</span>`;
      if(rv.score && rv.score !== "Feature"){
        const muted = (rv.score === "Unrated" || rv.score === "Listed");
        h += `<span class="score${muted ? " muted" : ""}">${rv.score}</span>`;
      }
      if(rv.dishes) h += `<div class="dishes"><b>Critics&rsquo; picks:</b> ${rv.dishes}</div>`;
      if(rv.list) h += `<div class="rlist">${rv.list}</div>`;
      h += `<div><a class="rlink" href="${rv.url}" target="_blank" rel="noopener noreferrer">Read the review &rarr;</a></div>`;
      const line = el("div","review"); line.innerHTML = h; r.appendChild(line);
    });
    c.appendChild(r);
  }
  return c;
}

function removeTopPick(){
  const t = results.querySelector(".pick, .pickloading");
  if(t) t.remove();
}

function renderCards(q, spots){
  const top = results.querySelector(".pick, .pickloading");
  results.innerHTML = "";
  if(top) results.appendChild(top);
  if(!q){
    results.appendChild(el("div","note","Start typing. Pizza, Korean BBQ, matcha, a hangover bite, Paris, London, or tap a craving above."));
    return;
  }
  if(!spots.length){
    results.appendChild(el("div","note","Nothing in the notebook matches that yet. Try pizza, Korean BBQ, coffee, a city, or a chip above."));
    return;
  }
  spots.forEach(s => results.appendChild(spotCard(s)));
}

async function fetchPick(q){
  const spots = pick(q);
  if(!spots.length) return;
  if(pickAbort) pickAbort.abort();
  pickAbort = new AbortController();
  removeTopPick();
  results.insertBefore(el("div","pickloading","J(AI) is writing a pick..."), results.firstChild);
  let ai = null;
  try{
    const res = await fetch("/api/pick", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({q, names: spots.map(s => s.name)}),
      signal: pickAbort.signal
    });
    if(res.ok) ai = (await res.json()).text || null;
  }catch(e){
    if(e.name === "AbortError") return;
  }
  if($("#q").value.trim() !== q) return; // stale, user kept typing
  removeTopPick();
  if(ai && ai.trim()){
    const p = el("div","pick");
    p.appendChild(el("div","pickhead","Jay's Take"));
    const blurb = el("div","blurb"); blurb.textContent = ai.trim();
    p.appendChild(blurb);
    results.insertBefore(p, results.firstChild);
  }
}

function onInput(){
  const q = $("#q").value.trim();
  renderCards(q, pick(q));
  clearTimeout(pickTimer);
  if(pickAbort) pickAbort.abort();
  removeTopPick();
  if(q.length >= 2){
    pickTimer = setTimeout(() => fetchPick(q), 450);
  }
}

async function init(){
  const d = await (await fetch("/api/data")).json();
  SPOTS = d.spots; REVIEWS = d.reviews; OUTLET_STYLE = d.outlet_style;
  CHIPS = d.chips; SURPRISES = d.surprises;
  $("#q").addEventListener("input", onInput);
  renderChips();
  renderCards("", []);
}

init();
