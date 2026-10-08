// J(AI) frontend: ranks Jay's notes locally as you type, then asks the
// server for a written pick from the top matches.

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

function score(spot, q){
  if(!q) return Math.random();
  const ql = q.toLowerCase();
  let s = 0;
  spot.tags.forEach(t => { if(t === ql || ql.includes(t) || (ql.length >= 3 && t.startsWith(ql))) s += 3; });
  [spot.name, spot.city, spot.hood, spot.cat, spot.take].forEach(f => {
    f.toLowerCase().split(/[^a-z]+/).forEach(w => {
      if(w.length > 3 && ql.includes(w)) s += 1;
    });
  });
  // craving synonyms
  const syn = {coffee:["coffee","cafe","latte","espresso"], cheap:["cheap","broke","budget"],
    date:["date","romantic"], hangover:["hangover","greasy","cure"], breakfast:["breakfast","brunch","morning"],
    veg:["vegetarian","veggie","veg"], splurge:["splurge","fancy","treat","baller"]};
  Object.keys(syn).forEach(k => { if(syn[k].some(w => ql.includes(w))) spot.tags.forEach(t=>{ if(t.includes(k)) s+=2; }); });
  const tier = (spot.price.match(/^\$+/) || [""])[0].length;
  if(/\b(splurge|fancy|baller|upscale)\b/.test(ql)) s += (tier >= 3 ? 4 : -5);
  if(/\b(cheap|budget|broke)\b/.test(ql)) s += (tier <= 1 ? 3 : (tier >= 3 ? -5 : 0));
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
