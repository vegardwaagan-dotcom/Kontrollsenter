// Kontrollsenter – alt kan ordnes selv (25):
//  • hold fingeren på en flis, en snarvei eller et kort i hvilken som helst fane → tilpass-modus;
//    dra til ny plass (de andre glir unna). Rekkefølgen huskes per fane.
//  • S / M / L / XL i hjørnet endrer størrelsen
//  • trykk på en flis → ark med mye info om kategorien (graf, nøkkeltall, hva som bruker mest)
// Pluss varselvalg under Innstillinger (på telefonen og på PC-en).
"use strict";

const DASH_KEY = "ks_dash_v1";
const SIZES = { tile: ["s", "m", "l", "xl"], card: ["m", "xl"] };
const SZ_TXT = { s: "S", m: "M", l: "L", xl: "XL" };
const DETAIL = { cpu: "cpu", gpu: "gpu", mem: "mem", hot: "temps", watt: "watt", disk: "disk", net: "net", bat: "bat", temps: "temps", health: "health", info: "info", batteries: "bat" };
let dashEditing = false, dashDrag = null, dashJustPressed = 0;

const dashBox = () => $("#tiles");
const dashItems = () => Array.from(dashBox().children).filter((e) => e.dataset && e.dataset.k);
const vibe = (ms) => { try { if (KS && KS.vibrate) KS.vibrate(); else if (navigator.vibrate) navigator.vibrate(ms || 10); } catch (e) {} };
const calm = () => document.body.classList.contains("eco") || matchMedia("(prefers-reduced-motion: reduce)").matches;

let dashPreset = (() => { try { return localStorage.getItem("ks_dash_preset") || "standard"; } catch (e) { return "standard"; } })();
const dashKey = () => DASH_KEY + (dashPreset === "standard" ? "" : "@" + dashPreset);
const DEF_HIDDEN = ["down", "cal"];
function dashLoad() { try { return JSON.parse(localStorage.getItem(dashKey())) || {}; } catch (e) { return {}; } }
function dashHidden() { const d = dashLoad(); return new Set(d.hidden || DEF_HIDDEN); }
function dashSave() {
  const d = { order: dashItems().map((e) => e.dataset.k), size: {}, hidden: dashItems().filter((e) => e.classList.contains("dhid")).map((e) => e.dataset.k) };
  dashItems().forEach((e) => (d.size[e.dataset.k] = e.dataset.sz));
  try { localStorage.setItem(dashKey(), JSON.stringify(d)); } catch (e) {}
}
function dashApplyHidden() { const h = dashHidden(); dashItems().forEach((e) => e.classList.toggle("dhid", h.has(e.dataset.k))); }
let presetBefore = null;
function dashGame(playing) {
  if (!pref("auto_layout", true)) return;
  if (playing && dashPreset !== "spill") { presetBefore = dashPreset; dashSetPreset("spill"); }
  else if (!playing && presetBefore) { const p = presetBefore; presetBefore = null; dashSetPreset(p); }
}
function dashSetPreset(p) {
  if (p === dashPreset) return;
  dashSave();
  const had = (() => { try { return !!localStorage.getItem(DASH_KEY + (p === "standard" ? "" : "@" + p)); } catch (e) { return false; } })();
  dashPreset = p;
  try { localStorage.setItem("ks_dash_preset", p); } catch (e) {}
  if (!had) dashSave();                               // nytt oppsett starter som en kopi
  const C = dashBox().ksC, L = dashLoad();
  flip(C, () => { dashItems().forEach((e) => { if (L.size && L.size[e.dataset.k]) dashSetSize(e, L.size[e.dataset.k]); }); C.apply(); dashApplyHidden(); });
  $$("#dash-presets button").forEach((b) => b.classList.toggle("on", b.dataset.p === p));
}
const kindOf = (el) => (el.classList.contains("tile") ? "tile" : "card");

function dashReset0() {
  try { localStorage.removeItem(DASH_KEY); } catch (e) {}
  const box = dashBox(), C = box.ksC;
  flip(C, () => {
    const items = dashItems();
    const tiles = items.filter((e) => e.classList.contains("tile")), cards = items.filter((e) => !e.classList.contains("tile"));
    const KEYS = ["cpu", "gpu", "mem", "hot", "watt", "disk", "net", "bat"], CK = ["temps", "health", "info"];
    tiles.sort((a, b) => KEYS.indexOf(a.dataset.k) - KEYS.indexOf(b.dataset.k));
    cards.sort((a, b) => CK.indexOf(a.dataset.k) - CK.indexOf(b.dataset.k));
    applying = true;
    tiles.forEach((e, i) => { box.appendChild(e); dashSetSize(e, i < 3 ? "m" : "s"); });
    cards.forEach((e) => { box.appendChild(e); dashSetSize(e, "xl"); });
    applying = false;
  });
}

function dashSetSize(el, sz) {
  const list = SIZES[kindOf(el)];
  if (!list.includes(sz)) sz = list[list.length - 1];
  list.forEach((x) => el.classList.remove("sz-" + x));
  el.classList.add("sz-" + sz);
  el.dataset.sz = sz;
  const b = el.querySelector(":scope > .dsz");
  if (b) b.textContent = SZ_TXT[sz];
}

function dashPrep(el, def) {
  if (el.dataset.prep) return;
  el.dataset.prep = "1";
  const L = dashLoad();
  dashSetSize(el, (L.size || {})[el.dataset.k] || def);
  const b = document.createElement("button");
  b.type = "button"; b.className = "dsz"; b.textContent = SZ_TXT[el.dataset.sz];
  b.setAttribute("aria-label", "Endre størrelse");
  b.addEventListener("pointerdown", (e) => e.stopPropagation());
  b.onclick = (e) => {
    e.stopPropagation();
    const list = SIZES[kindOf(el)], i = list.indexOf(el.dataset.sz);
    flip(dashBox().ksC, () => dashSetSize(el, list[(i + 1) % list.length]), el);
    dashSave(); vibe(8);
  };
  el.appendChild(b);
  const x = document.createElement("button");
  x.type = "button"; x.className = "dhide"; x.textContent = "✕"; x.setAttribute("aria-label", "Skjul");
  x.addEventListener("pointerdown", (e) => e.stopPropagation());
  x.onclick = (e) => { e.stopPropagation(); flip(dashBox().ksC, () => el.classList.toggle("dhid")); dashSave(); vibe(8); };
  el.appendChild(x);
  if (dashHidden().has(el.dataset.k)) el.classList.add("dhid");
}

// ---------- alt som kan flyttes: flisene, snarveiene og kortene i alle fanene ----------
const ORDER_KEY = "ks_order_v1";
const CONTAINERS = [];
let ordSeq = 0, applying = false;
function orderLoad() { try { return JSON.parse(localStorage.getItem(ORDER_KEY)) || {}; } catch (e) { return {}; } }
const itemKey = (e) => e.dataset.k || e.dataset.q || e.id
  || ((e.querySelector("h2") || {}).textContent || "").trim() || "i" + e.dataset.ord;

function makeContainer(el, key, sel, opts) {
  const C = Object.assign({ el, key, sel, horiz: false }, opts || {});
  C.items = () => Array.from(el.children).filter((e) => e.matches(sel) && e.offsetParent !== null);
  C.all = () => Array.from(el.children).filter((e) => e.matches(sel));
  C.save = C.save || (() => {
    const d = orderLoad(); d[key] = C.all().map(itemKey);
    try { localStorage.setItem(ORDER_KEY, JSON.stringify(d)); } catch (e) {}
  });
  C.apply = C.apply || (() => {
    const order = orderLoad()[key] || [];
    const all = C.all();
    const rank = (e) => { const i = order.indexOf(itemKey(e)); return i >= 0 ? i : 1000 + Number(e.dataset.ord || 0); };
    const want = all.slice().sort((x, y) => rank(x) - rank(y));
    if (want.every((e, i) => e === all[i])) return;
    applying = true;
    // flytt bare elementene som er med (andre barn – overskrifter, lister – blir stående)
    const anchor = document.createComment("ks");
    el.insertBefore(anchor, all[0]);
    want.forEach((e) => el.insertBefore(e, anchor));
    anchor.remove();
    applying = false;
  });
  C.prep = () => C.all().forEach((e) => {
    if (e.dataset.ord == null) e.dataset.ord = String(ordSeq++);
    e.classList.add("s-item");
    if (C.sizes && !e.querySelector(":scope > .dsz")) cardSizePrep(C, e);
  });
  if (C.sizes) el.classList.add("sgrid");
  C.reset = C.reset || (() => {
    const d = orderLoad(); delete d[key]; delete d[key + "#sz"];
    if (C.sizes) C.all().forEach((e) => cardSetSize(e, C.defSize || "m"));
    try { localStorage.setItem(ORDER_KEY, JSON.stringify(d)); } catch (e) {}
    flip(C, () => C.apply());
  });
  el.classList.add("sortable");
  el.ksC = C;
  C.prep(); C.apply();
  new MutationObserver(() => { if (applying || dashDrag) return; C.prep(); C.apply(); if (dashEditing) el.classList.add("editing"); })
    .observe(el, { childList: true });
  CONTAINERS.push(C);
  return C;
}

// størrelse på kortene i fanene: S (halv på mobil, en tredel på brett/PC), M (hel / halv), L (alltid hel)
const CSZ = ["s", "m", "l"];
function cardSetSize(e, sz) {
  CSZ.forEach((x) => e.classList.remove("csz-" + x));
  e.classList.add("csz-" + sz); e.dataset.csz = sz;
  const b = e.querySelector(":scope > .dsz"); if (b) b.textContent = sz.toUpperCase();
}
function cardSizePrep(C, e) {
  cardSetSize(e, ((orderLoad()[C.key + "#sz"]) || {})[itemKey(e)] || C.defSize || "m");
  const b = document.createElement("button");
  b.type = "button"; b.className = "dsz"; b.textContent = e.dataset.csz.toUpperCase();
  b.setAttribute("aria-label", "Endre størrelse");
  b.addEventListener("pointerdown", (ev) => ev.stopPropagation());
  b.onclick = (ev) => {
    ev.stopPropagation();
    const nx = CSZ[(CSZ.indexOf(e.dataset.csz) + 1) % CSZ.length];
    flip(C, () => cardSetSize(e, nx), e);
    const d = orderLoad(); d[C.key + "#sz"] = Object.assign(d[C.key + "#sz"] || {}, { [itemKey(e)]: nx });
    try { localStorage.setItem(ORDER_KEY, JSON.stringify(d)); } catch (er) {}
    vibe(8);
  };
  applying = true; e.appendChild(b); applying = false;
}

// FLIP: mål før, endre, mål etter – og la alle gli myk fra gammel til ny plass
function flip(C, change, popped) {
  const items = C.items(), before = new Map(items.map((e) => [e, e.getBoundingClientRect()]));
  change();
  if (calm()) return;
  items.forEach((e) => {
    if (e === (dashDrag && dashDrag.el)) return;
    const a = before.get(e), b = e.getBoundingClientRect();
    const dx = a.left - b.left, dy = a.top - b.top;
    if (e === popped) {
      e.animate([{ transform: `translate(${dx}px,${dy}px) scale(.94)` }, { transform: "none" }],
        { duration: 460, easing: "cubic-bezier(.2,1.4,.4,1)" });
      glow(e);
    } else if (dx || dy) {
      e.animate([{ transform: `translate(${dx}px,${dy}px)` }, { transform: "none" }], { duration: 280, easing: "cubic-bezier(.2,.8,.2,1)" });
    }
  });
}
function glow(e) {
  e.classList.remove("dglow"); void e.offsetWidth; e.classList.add("dglow");
  setTimeout(() => e.classList.remove("dglow"), 900);
}

function dashOrder() { const C = dashBox().ksC; if (C) C.apply(); }

// app.js → renderOverview → hit med flisene (k, html)
function dashTiles(list) {
  const box = dashBox();
  const keep = new Set(list.map((t) => t.k));
  list.forEach((t, i) => {
    let el = box.querySelector(`:scope > .tile[data-k="${t.k}"]`);
    if (!el) {
      el = document.createElement("div");
      el.className = "tile"; el.dataset.k = t.k;
      el.dataset.ord = String(i - 100);               // standard: flisene før kortene
      el.innerHTML = '<div class="tc"></div>';
      dashPrep(el, i < 3 ? "m" : "s");
      box.insertBefore(el, box.querySelector(":scope > .card"));
    }
    el.querySelector(".tc").innerHTML = t.html;
  });
  dashItems().forEach((e) => { if (e.classList.contains("tile") && !keep.has(e.dataset.k)) e.remove(); });
}

const pageEl = () => document.getElementById(tab);
function dashEdit(on) {
  if (dashEditing === on) return;
  dashEditing = on;
  document.body.classList.toggle("dash-edit", on);
  CONTAINERS.forEach((C) => C.el.classList.toggle("editing", on));
  const pg = pageEl();
  if (pg) pg.toggleAttribute("data-noswipe", on);
  if (!on) $$(".page[data-noswipe]").forEach((p) => p.removeAttribute("data-noswipe"));
  $("#dash-bar").hidden = !on;
  $("#dash-bar span").innerHTML = "Dra for å flytte<br><b>S M L</b> = størrelse";
  if (on) vibe(15);
}

function dashReset() {
  const pg = pageEl();
  CONTAINERS.filter((C) => pg && pg.contains(C.el)).forEach((C) => C.reset());
}

// ---------- dra ----------
function dragStart(C, el, ev) {
  const r = el.getBoundingClientRect();
  dashDrag = { C, el, id: ev.pointerId, gx: ev.clientX - r.left, gy: ev.clientY - r.top, x: ev.clientX, y: ev.clientY, last: 0, raf: 0 };
  el.classList.add("dragging");
  try { el.setPointerCapture(ev.pointerId); } catch (e) {}
  dragPlace();
  vibe(12);
  const loop = () => {                       // rull siden når du drar nær kanten
    if (!dashDrag) return;
    const y = dashDrag.y, h = innerHeight, edge = 90;
    const v = y < edge ? -(edge - y) / 5 : y > h - edge - 80 ? (y - (h - edge - 80)) / 5 : 0;
    if (v) { (document.scrollingElement || document.documentElement).scrollBy(0, v); dragPlace(); }
    if (C.horiz) {
      const cr = C.el.getBoundingClientRect(), x = dashDrag.x;
      const hv = x < cr.left + 40 ? -8 : x > cr.right - 40 ? 8 : 0;
      if (hv) { C.el.scrollLeft += hv; dragPlace(); }
    }
    dashDrag.raf = requestAnimationFrame(loop);
  };
  dashDrag.raf = requestAnimationFrame(loop);
}
function dragPlace() {
  const d = dashDrag; if (!d) return;
  d.el.style.transform = "";
  const r = d.el.getBoundingClientRect();
  const big = r.height > 260;
  d.el.style.transform = `translate(${d.x - d.gx - r.left}px, ${d.y - d.gy - r.top}px) scale(${big ? 1.02 : 1.06}) rotate(${big ? -0.4 : -1}deg)`;
}
function dragMove(ev) {
  const d = dashDrag; if (!d || ev.pointerId !== d.id) return;
  d.x = ev.clientX; d.y = ev.clientY;
  dragPlace();
  if (Date.now() - d.last < 140) return;
  const over = d.C.items().find((e) => {
    if (e === d.el) return false;
    const r = e.getBoundingClientRect();
    return d.x >= r.left && d.x <= r.right && d.y >= r.top && d.y <= r.bottom;
  });
  if (!over) return;
  const r = over.getBoundingClientRect();
  const after = !d.C.horiz && r.width > r.height * 2.2 ? d.y > r.top + r.height / 2 : d.x > r.left + r.width / 2;
  const ref = after ? over.nextSibling : over;
  if (ref === d.el || (after ? over.nextSibling === d.el : over.previousSibling === d.el)) return;
  d.last = Date.now();
  flip(d.C, () => d.C.el.insertBefore(d.el, ref));
  dragPlace();
  vibe(5);
}
function dragEnd(ev) {
  const d = dashDrag; if (!d || (ev && ev.pointerId !== d.id)) return;
  cancelAnimationFrame(d.raf);
  dashDrag = null;
  const from = d.el.style.transform;
  d.el.classList.remove("dragging");
  d.el.style.transform = "";
  if (!calm()) d.el.animate([{ transform: from }, { transform: "scale(.97)", offset: 0.7 }, { transform: "none" }],
    { duration: 520, easing: "cubic-bezier(.2,1.3,.4,1)" });
  glow(d.el);
  d.C.save();
  vibe(10);
}

function dashWire() {
  const box = dashBox();
  if (!box || box.dataset.wired) return;
  box.dataset.wired = "1";
  dashItems().forEach((e) => dashPrep(e, "xl"));
  // flisene har egen lagring (rekkefølge + størrelse)
  makeContainer(box, "tiles", "[data-k]", {
    save: dashSave,
    apply() {
      const order = dashLoad().order || [], all = Array.from(box.children).filter((e) => e.dataset.k);
      const rank = (e) => { const i = order.indexOf(e.dataset.k); return i >= 0 ? i : 1000 + Number(e.dataset.ord || 0); };
      const want = all.slice().sort((x, y) => rank(x) - rank(y));
      if (want.every((e, i) => e === all[i])) return;
      applying = true; want.forEach((e) => box.appendChild(e)); applying = false;
    },
    reset() { dashReset0(); },
  });
  makeContainer($("#quick"), "quick", "button[data-q]", { horiz: true });
  $$("main .page").forEach((pg) => {
    if (pg.id === "pair") return;
    makeContainer(pg, "p:" + pg.id, ".card", { sizes: pg.id !== "oversikt", defSize: "l" });
    Array.from(pg.children).filter((e) => e.classList.contains("grid")).forEach((g, i) => makeContainer(g, `g:${pg.id}:${i}`, ".card", { sizes: true }));
  });

  let lp = null;
  const itemAt = (t) => { const it = t.closest(".s-item"); return it && it.parentElement && it.parentElement.ksC ? it : null; };
  document.addEventListener("pointerdown", (ev) => {
    if (ev.button > 0) return;
    const el = itemAt(ev.target);
    if (!el) return;
    const C = el.parentElement.ksC;
    if (dashEditing) {
      if (ev.target.closest(".dsz")) return;
      ev.preventDefault();
      dragStart(C, el, ev);
      return;
    }
    // glidebrytere og tekstfelt reagerer med en gang – der kan du ikke starte et langt trykk. Knapper går fint.
    if (ev.target.closest('input[type=range], input[type=text], input[type=search], input[type=number], input:not([type]), textarea, select, [contenteditable]')) return;
    const sx = ev.clientX, sy = ev.clientY;
    lp = { sx, sy, t: setTimeout(() => { lp = null; dashJustPressed = Date.now(); dashEdit(true); dragStart(C, el, ev); }, 480) };
  });
  document.addEventListener("pointermove", (ev) => {
    if (lp && Math.hypot(ev.clientX - lp.sx, ev.clientY - lp.sy) > 9) { clearTimeout(lp.t); lp = null; }
    dragMove(ev);
  });
  const up = (ev) => { if (lp) { clearTimeout(lp.t); lp = null; } dragEnd(ev); };
  document.addEventListener("pointerup", up);
  document.addEventListener("pointercancel", up);
  // når du drar, skal ikke siden rulle eller bytte fane
  document.addEventListener("touchmove", (ev) => { if (dashDrag) ev.preventDefault(); }, { passive: false });
  document.addEventListener("contextmenu", (ev) => { if (itemAt(ev.target)) ev.preventDefault(); });
  // etter et langt trykk (og mens du tilpasser) skal ikke knapper inne i kortene trykkes
  document.addEventListener("click", (ev) => {
    if (!itemAt(ev.target) || ev.target.closest(".dsz")) return;
    if (dashEditing || Date.now() - dashJustPressed < 700) { ev.preventDefault(); ev.stopPropagation(); }
  }, true);
  box.addEventListener("click", (ev) => {
    if (dashEditing || Date.now() - dashJustPressed < 700) return;
    if (ev.target.closest("button, a, input, select, summary, label")) return;
    const el = ev.target.closest("#tiles > [data-k]");
    if (el && DETAIL[el.dataset.k]) openDetail(DETAIL[el.dataset.k]);
  });
  const bar = document.createElement("div");
  bar.id = "dash-bar"; bar.className = "dash-bar"; bar.hidden = true;
  bar.innerHTML = `<span></span>
    <button type="button" class="soft" id="dash-unhide">Vis skjulte</button>
    <button type="button" class="soft" id="dash-reset">Tilbakestill</button><button type="button" id="dash-done">Ferdig</button>`;
  document.body.appendChild(bar);
  $("#dash-done").onclick = () => dashEdit(false);
  $("#dash-reset").onclick = () => { dashReset(); vibe(10); };
  $("#dash-unhide").onclick = () => { const C = dashBox().ksC; flip(C, () => dashItems().forEach((e) => e.classList.remove("dhid"))); dashSave(); vibe(8); };
  const pr = document.createElement("div");
  pr.id = "dash-presets"; pr.className = "seg dash-presets";
  pr.innerHTML = [["standard", "Standard"], ["spill", "Spill"], ["jobb", "Jobb"], ["natt", "Natt"]]
    .map(([k, n]) => `<button type="button" data-p="${k}" class="${k === dashPreset ? "on" : ""}">${n}</button>`).join("");
  box.parentElement.insertBefore(pr, box);
  pr.querySelectorAll("button").forEach((b) => (b.onclick = () => { dashSetPreset(b.dataset.p); vibe(6); }));
  const prevBack = window.ksBack;
  window.ksBack = () => {
    if (dashEditing) { dashEdit(false); return true; }
    if (detOpen) { closeDetail(); return true; }
    return prevBack ? prevBack() : false;
  };
}

// ---------- detaljer ----------
let detOpen = null, detTimer = 0;
const detBack = document.createElement("div");
detBack.className = "sheet-back"; detBack.hidden = true;
detBack.innerHTML = `<div class="sheet det-sheet" role="dialog" aria-modal="true"><div class="grab"></div>
  <div class="sheet-head"><b id="det-t"></b><button class="icon" id="det-x" aria-label="Lukk">✕</button></div>
  <div class="sheet-list" id="det-body"></div></div>`;
document.body.appendChild(detBack);
detBack.onclick = (e) => { if (e.target === detBack) closeDetail(); };
detBack.querySelector("#det-x").onclick = () => closeDetail();

function openDetail(k) {
  detOpen = k;
  $("#det-t").textContent = { cpu: "Prosessor", gpu: "Skjermkort", mem: "Minne", temps: "Temperaturer", watt: "Strømforbruk",
    disk: "Disk", net: "Nettverk", bat: "Batteri", health: "Helse", info: "Maskin", fans: "Vifter", mode: "Strømmodus" }[k] || "";
  $("#det-body").innerHTML = '<p class="dim" style="padding:20px 6px">Henter …</p>';
  detBack.hidden = false;
  requestAnimationFrame(() => detBack.classList.add("open"));
  vibe(6);
  loadDetail();
  clearInterval(detTimer);
  detTimer = setInterval(() => !document.hidden && loadDetail(), 2500);
}
function closeDetail() {
  detOpen = null;
  clearInterval(detTimer);
  detBack.classList.remove("open");
  setTimeout(() => { if (!detOpen) detBack.hidden = true; }, 230);
}
async function loadDetail() {
  const k = detOpen; if (!k) return;
  try {
    const d = await X("detail", "k=" + encodeURIComponent(k));
    if (detOpen === k) renderDetail(d);
  } catch (e) {
    if (detOpen === k && !$("#det-body .det-hero")) $("#det-body").innerHTML = `<p class="dim" style="padding:20px 6px">${esc(e.message)}</p>`;
  }
}
const pctCls = (p) => (p >= 85 ? "bad" : p >= 70 ? "warn" : "ok");
function renderDetail(d) {
  const body = $("#det-body");
  const scroll = body.scrollTop;
  const ser = (d.series || []).filter((s) => s.pts && s.pts.length);
  let h = `<div class="det-hero"><div><div class="det-title">${esc(d.title)}</div>${d.sub ? `<div class="dim small">${esc(d.sub)}</div>` : ""}</div>
    <div class="det-val">${esc(d.value || "")}</div></div>`;
  if (ser.length) {
    h += `<div class="det-chart"><canvas id="det-cv"></canvas><div class="det-ax"><span>10 min siden</span><span>nå</span></div>`;
    if (ser.length > 1) h += `<div class="det-leg">${ser.map((s) => `<span><i style="background:${esc(s.color)}"></i>${esc(s.name)}</span>`).join("")}</div>`;
    h += "</div>";
  }
  (d.sections || []).forEach((s) => {
    h += `<div class="sheet-group">${esc(s.title)}</div>`;
    if (s.bars) {
      h += `<div class="det-bars">${s.bars.map(([n, p, t]) => `<div class="det-bar"><div class="row between"><span>${esc(n)}</span><span class="dim num">${esc(t)}</span></div>
        <div class="det-track"><i class="${pctCls(p)}" style="width:${Math.max(0, Math.min(100, p))}%"></i></div></div>`).join("")}</div>`;
    } else {
      h += `<div class="kv det-kv">${(s.rows || []).map(([a, b]) => `<div class="${String(b).length > 34 ? "long" : ""}"><b>${esc(a)}</b><span>${esc(b)}</span></div>`).join("")}</div>`;
    }
  });
  body.innerHTML = h;
  body.scrollTop = scroll;
  if (ser.length) drawDetail($("#det-cv"), ser);
}
function drawDetail(cv, ser) {
  const dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d"); g.scale(dpr, dpr);
  const top = Math.max(...ser.map((s) => s.max || 0), ...ser.map((s) => Math.max(...s.pts) * 1.15), 0.0001);
  const css = getComputedStyle(document.documentElement);
  g.strokeStyle = css.getPropertyValue("--line"); g.lineWidth = 1;
  for (let i = 1; i < 4; i++) { const y = (h * i) / 4; g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
  ser.forEach((s) => {
    const n = Math.max(s.pts.length - 1, 1);
    const xy = s.pts.map((v, i) => [(w * i) / n, 4 + (h - 8) * (1 - v / top)]);
    g.beginPath(); g.moveTo(xy[0][0], xy[0][1]);
    for (let i = 1; i < xy.length; i++) { const mx = (xy[i - 1][0] + xy[i][0]) / 2; g.bezierCurveTo(mx, xy[i - 1][1], mx, xy[i][1], xy[i][0], xy[i][1]); }
    const line = new Path2D(); line.moveTo(xy[0][0], xy[0][1]);
    for (let i = 1; i < xy.length; i++) { const mx = (xy[i - 1][0] + xy[i][0]) / 2; line.bezierCurveTo(mx, xy[i - 1][1], mx, xy[i][1], xy[i][0], xy[i][1]); }
    g.lineTo(xy[xy.length - 1][0], h); g.lineTo(0, h); g.closePath();
    const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, s.color + "66"); gr.addColorStop(1, s.color + "00");
    g.fillStyle = gr; g.fill();
    g.strokeStyle = s.color; g.lineWidth = 2.2; g.lineJoin = "round"; g.stroke(line);
  });
  const u = ser[0].unit || "", lab = u === "B/s" ? fmtR(top) : Math.round(top) + " " + u;
  g.fillStyle = css.getPropertyValue("--dim"); g.font = "11px system-ui"; g.fillText(lab, 4, 14);
}

// ---------- varsler (Innstillinger) ----------
const PHONE_KINDS = [["offline", "En PC slutter å svare", "Den var på, men ble ikke slått av fra Kontrollsenter."],
  ["appupdate", "Ny versjon av appen", "Når en ny versjon av Kontrollsenter-appen er klar."]];
function swRow(id, name, desc, on, cls) {
  return `<div class="row nf-row ${cls || ""}"><span><b>${esc(name)}</b>${desc ? `<small class="dim">${esc(desc)}</small>` : ""}</span>
    <label class="switch"><input type="checkbox" data-nf="${esc(id)}" ${on ? "checked" : ""}><i></i></label></div>`;
}
async function loadNotify() {
  $$(".pcname-here").forEach((e) => (e.textContent = (last && last.name) || "PC-en"));
  let pc = null;
  try { pc = await X("notify"); } catch (e) {}
  if (pc) {
    $("#nf-pc").innerHTML = swRow("all", "Vis varsler på PC-en", "Hovedbryter", pc.all, "nf-master")
      + `<div class="nf-kinds${pc.all ? "" : " off"}">` + pc.kinds.map((k) => swRow(k.id, k.name, k.desc, k.on)).join("") + "</div>";
    $$("#nf-pc input[data-nf]").forEach((i) => (i.onchange = () => {
      if (i.dataset.nf === "all") $("#nf-pc .nf-kinds").classList.toggle("off", !i.checked);
      act({ a: "notify", kind: i.dataset.nf, on: i.checked }, true);
    }));
  } else {
    $("#nf-pc").innerHTML = '<p class="dim small">Oppdater Kontrollsenter på PC-en for å velge varsler herfra.</p>';
  }
  if (KS && KS.getNotify) {
    let st = {};
    try { st = JSON.parse(KS.getNotify()) || {}; } catch (e) {}
    const on = (k) => st[k] !== false;
    const kinds = (pc ? pc.kinds.map((k) => [k.id, k.name, k.desc]) : []).filter((k) => k[0] !== "bg").concat(PHONE_KINDS);
    $("#nf-phone-card").hidden = false;
    $("#nf-phone").innerHTML = swRow("all", "Varsler på telefonen", "Hovedbryter for alle PC-ene", on("all"), "nf-master")
      + `<div class="nf-kinds${on("all") ? "" : " off"}">` + kinds.map(([id, n, d]) => swRow(id, n, d, on(id))).join("") + "</div>";
    $$("#nf-phone input[data-nf]").forEach((i) => (i.onchange = () => {
      if (i.dataset.nf === "all") $("#nf-phone .nf-kinds").classList.toggle("off", !i.checked);
      try { KS.setNotify(i.dataset.nf, i.checked); } catch (e) {}
      vibe(6);
    }));
  }
}

// ---------- scener: én knapp setter hele rommet og PC-en ----------
const sceneCard = document.createElement("div");
sceneCard.className = "card"; sceneCard.id = "c-scenes"; sceneCard.dataset.ord = "-10";
sceneCard.innerHTML = '<div class="row between"><h2>Scener</h2><span class="dim small" id="scene-now"></span></div><div class="scenes" id="scenes"></div>';
{ const g = $("#kontroll .grid"); if (g) g.insertBefore(sceneCard, g.firstChild); }
async function loadScenes() {
  let d;
  try { d = await X("scenes"); } catch (e) { sceneCard.hidden = true; return; }
  sceneCard.hidden = !d.scenes.length;
  const cur = d.scenes.find((x) => x.id === d.active);
  $("#scene-now").textContent = cur ? "Nå: " + cur.name : "";
  $("#scenes").innerHTML = d.scenes.map((x) => `<button type="button" class="scene${x.id === d.active ? " on" : ""}" data-id="${esc(x.id)}"
      style="--sc:${esc(x.color || "#8a5cff")}"><span class="si">${esc(x.icon || "✨")}</span><span class="sn">${esc(x.name)}</span>
      <span class="ss">${esc(x.summary)}</span>${x.auto ? `<span class="st">⚡ ${esc(x.trigger)}</span>` : ""}</button>`).join("");
  $$("#scenes .scene").forEach((b) => (b.onclick = async () => {
    vibe(12);
    $$("#scenes .scene").forEach((x) => x.classList.toggle("on", x === b));
    b.classList.remove("fire"); void b.offsetWidth; b.classList.add("fire");
    await act({ a: "scene", id: b.dataset.id });
    setTimeout(loadScenes, 2500);
  }));
}
setInterval(() => tab === "kontroll" && !document.hidden && loadScenes(), 15000);

// ---------- mål og belønning + ukesrapport (familie) ----------
const goalCard = document.createElement("div");
goalCard.className = "card"; goalCard.id = "c-goals";
goalCard.innerHTML = '<h2>Mål og belønning</h2><p class="dim small">Ferdig med lekser? Trykk – foreldrene godkjenner fra telefonen, og ekstra spilletid kommer med en gang.</p>'
  + '<div class="goals" id="goals"></div><div id="goal-pending"></div><div id="goal-msg" class="dim small"></div>';
const weekCard = document.createElement("div");
weekCard.className = "card"; weekCard.id = "c-week";
weekCard.innerHTML = '<h2>Ukesrapport</h2><div id="weekly" class="dim small">Henter …</div>';
{ const fg = $("#fam-grid"); if (fg) { const fc = $("#c-family"); fg.insertBefore(weekCard, fc ? fc.nextSibling : null); fg.insertBefore(goalCard, weekCard); } }
async function loadGoals() {
  let g; try { g = await X("goals"); } catch (e) { goalCard.hidden = true; return; }
  goalCard.hidden = false;
  $("#goals").innerHTML = g.goals.map((x) => '<button type="button" class="goal" data-g="' + esc(x.id) + '"><span class="gi">' + esc(x.icon)
    + '</span><span>' + esc(x.name) + '</span><small>+' + x.minutes + ' min</small></button>').join("");
  $$("#goals .goal").forEach((b) => (b.onclick = async () => { vibe(10); await act({ a: "goal_req", goal: b.dataset.g }); loadGoals(); }));
  const full = !document.body.classList.contains("limited");
  $("#goal-pending").innerHTML = g.pending.map((r) => '<div class="row between goal-req"><span>' + esc(r.icon) + ' <b>' + esc(r.name)
    + '</b><br><small class="dim">' + esc(r.pc || "") + ' · ' + esc(r.by || "") + ' · +' + r.minutes + ' min</small></span>'
    + (full ? '<span class="row"><button class="primary" data-ok="' + esc(r.id) + '">Godkjenn</button><button class="soft" data-no="' + esc(r.id) + '">Avslå</button></span>'
      : '<span class="dim small">Venter …</span>') + '</div>').join("");
  $$("#goal-pending [data-ok]").forEach((b) => (b.onclick = async () => { await act({ a: "goal_ok", id: b.dataset.ok, ok: true }); loadGoals(); }));
  $$("#goal-pending [data-no]").forEach((b) => (b.onclick = async () => { await act({ a: "goal_ok", id: b.dataset.no, ok: false }); loadGoals(); }));
}
async function loadWeekly() {
  try {
    const r = await X("weekly");
    const hm = (s) => Math.floor(s / 3600) + " t " + Math.floor(s % 3600 / 60) + " min";
    const top = Math.max(1, ...r.rows.map((x) => x.play_s));
    $("#weekly").innerHTML = r.rows.length ? r.rows.map((x) => '<div class="wk"><div class="row between"><b>' + esc(x.name) + '</b><span>' + hm(x.play_s)
      + '</span></div><div class="det-track"><i style="width:' + Math.round(100 * x.play_s / top) + '%"></i></div><small class="dim">'
      + [x.top ? "mest " + esc(x.top) : "", x.sessions ? x.sessions + " økter" : "", x.kwh ? x.kwh + " kWh" : ""].filter(Boolean).join(" · ")
      + '</small></div>').join("")
      + (r.top_games.length ? '<p class="small">Mest spilt i huset: ' + r.top_games.slice(0, 3).map(([g, v]) => esc(g) + " (" + hm(v) + ")").join(", ") + '</p>' : "")
      : "Ingen tall ennå.";
  } catch (e) { $("#weekly").textContent = e.message; }
}

// ---------- «Hvorfor er PC-en treg?» (Verktøy) ----------
const slowCard = document.createElement("div");
slowCard.className = "card"; slowCard.id = "c-slow";
slowCard.innerHTML = '<h2>Hvorfor er PC-en treg?</h2><p class="dim small">Ser på prosessor, minne, disk, temperatur, strømmodus og hva som kjører.</p>'
  + '<button type="button" class="primary wide" id="slow-go">Finn ut hvorfor</button><div id="slow-res"></div>';
{ const g = $("#mer .grid"); if (g) g.insertBefore(slowCard, g.firstChild); }
$("#slow-go").onclick = async () => {
  const b = $("#slow-go"); b.disabled = true; b.textContent = "Sjekker …";
  try {
    const r = await X("slow");
    const ic = { bad: "❌", warn: "⚠️", ok: "✅" };
    $("#slow-res").innerHTML = '<p><b>' + esc(r.summary) + '</b></p>' + r.items.map((x, i) => '<div class="row between slow-row"><span>' + ic[x.level] + ' <b>'
      + esc(x.title) + '</b>' + (x.detail ? '<br><small class="dim">' + esc(x.detail) + '</small>' : '') + '</span>'
      + (x.action ? '<button class="soft" data-fix="' + i + '">' + esc(x.action.label || "Fiks") + '</button>' : '') + '</div>').join("");
    $$("#slow-res [data-fix]").forEach((fb) => (fb.onclick = async () => {
      const a = Object.assign({}, r.items[+fb.dataset.fix].action); delete a.label;
      await act(a); fb.disabled = true;
    }));
  } catch (e) { $("#slow-res").textContent = e.message; }
  b.disabled = false; b.textContent = "Sjekk på nytt";
};

// ---------- kobling ----------
const dashSetTab = setTab;
setTab = function (t) {                              // eslint-disable-line no-global-assign
  if (t !== "oversikt") dashEdit(false);
  if (detOpen) closeDetail();
  dashSetTab(t);
  if (t === "system") loadNotify();
  if (t === "kontroll") loadScenes();
  if (t === "spill") { loadGoals(); loadWeekly(); }
};
dashWire();
if (tab === "system") loadNotify();
if (tab === "kontroll") loadScenes();
