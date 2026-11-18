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
const planCard = document.createElement("div");
planCard.className = "card"; planCard.id = "c-plan";
planCard.innerHTML = '<h2>Ukeplan</h2><p class="dim small">Felles for hele huset. PC-ene minner om avtalene sine.</p>'
  + '<div id="plan-list" class="dim small">Henter …</div>'
  + '<div class="row wrap plan-form"><select id="plan-day"></select><input id="plan-at" type="time" value="17:00">'
  + '<input id="plan-text" placeholder="Hva skjer?"><input id="plan-who" placeholder="Hvem (tomt = alle)">'
  + '<button class="primary" id="plan-add">Legg til</button></div>';
const shopCard = document.createElement("div");
shopCard.className = "card"; shopCard.id = "c-shop";
shopCard.innerHTML = '<h2>Belønningsbutikk <span id="shop-stars" class="chip"></span></h2>'
  + '<p class="dim small">Godkjente mål gir stjerner. Løs dem inn her – en voksen godkjenner.</p>'
  + '<div class="goals" id="shop-items"></div><div id="shop-pending"></div>';
{ const fg = $("#fam-grid"); if (fg) { fg.insertBefore(shopCard, weekCard); fg.insertBefore(planCard, shopCard); } }
const safeCard = document.createElement("div");
safeCard.className = "card full-only"; safeCard.id = "c-safe"; safeCard.hidden = true;
safeCard.innerHTML = '<h2>Trygg på nettet og leksetid</h2>'
  + '<div class="row between"><span>Nettfilter</span><select id="safe-dns"></select></div>'
  + '<div class="row between" style="margin-top:8px"><span>📚 Leksetid <small class="dim" id="safe-when"></small></span>'
  + '<label class="switch"><input type="checkbox" id="safe-school"><i></i></label></div>'
  + '<div class="dim small" id="safe-msg"></div>';
{ const fg = $("#fam-grid"); if (fg) fg.appendChild(safeCard); }
async function loadSafe() {
  if (document.body.classList.contains("limited")) { safeCard.hidden = true; return; }
  let st; try { st = await X("familysafe"); } catch (e) { safeCard.hidden = true; return; }
  safeCard.hidden = false;
  const sel = $("#safe-dns");
  sel.innerHTML = '<option value="">Av</option>' + Object.entries(st.providers).map(([k, v]) => '<option value="' + k + '"' + (st.dns === k ? " selected" : "") + '>' + esc(v) + '</option>').join("");
  sel.onchange = async () => { $("#safe-msg").textContent = "Endrer …"; const r = await act({ a: "dnsfilter", provider: sel.value || null }); $("#safe-msg").textContent = (r && r.msg) || ""; };
  const days = ["ma", "ti", "on", "to", "fr", "lø", "sø"];
  $("#safe-when").textContent = st.school.from + "–" + st.school.to + " · " + st.school.days.map((d) => days[d]).join(" ") + (st.school_now ? " · nå" : "");
  const sw = $("#safe-school"); sw.checked = st.school.enabled;
  sw.onchange = () => act({ a: "school", enabled: sw.checked });
}
const vrCard = document.createElement("div");
vrCard.className = "card full-only"; vrCard.id = "c-vr"; vrCard.hidden = true;
vrCard.innerHTML = '<h2>🥽 VR – Meta Quest 3</h2><div class="seg" id="vr-mode"><button data-m="wireless">📶 Trådløst</button><button data-m="wired">🔌 Kabel</button></div>'
  + '<div id="vr-checks" class="dim small" style="margin-top:8px"></div>'
  + '<div class="row" style="margin-top:8px"><button class="primary" id="vr-start">Start VR</button><button class="soft" id="vr-fix">Fiks alt</button><button class="soft" id="vr-stop">Stopp</button></div>'
  + '<div class="dim small" id="vr-msg"></div>';
{ const fg = $("#fam-grid"); const sp = $("#spill .grid") || fg; if (sp) sp.insertBefore(vrCard, sp.firstChild); }
async function loadVr() {
  if (document.body.classList.contains("limited")) return;
  let st; try { st = await X("vr"); } catch (e) { vrCard.hidden = true; return; }
  vrCard.hidden = false;
  $$("#vr-mode button").forEach((b) => { b.classList.toggle("on", b.dataset.m === st.mode); b.onclick = async () => { await act({ a: "vr", do: "noop" }).catch(() => {}); st.mode = b.dataset.m; $$("#vr-mode button").forEach((x) => x.classList.toggle("on", x === b)); }; });
  const h = st.headset || {};
  const hsTxt = "🔌 Kabel: " + (h.usb ? "tilkoblet" + (h.battery != null ? " · 🔋 " + h.battery + " %" : "") : "ikke tilkoblet")
    + "<br>📶 Wi-Fi: " + (h.streaming ? "strømmer nå" + (h.via ? " (" + esc(h.via) + ")" : "") : h.wifi_online ? "på nettet (" + esc(h.wifi_ip || "") + ")" : "ikke funnet");
  const bad = st.checks.filter((c) => !c.ok && !c.warn);
  $("#vr-checks").innerHTML = '<div style="margin-bottom:6px">' + hsTxt + '</div>' + (bad.length ? bad.map((c) => "❌ " + esc(c.title)).join("<br>") : "✅ Alt er klart")
    + (st.quest && st.quest.state === "device" ? "<br>🥽 Questen er koblet til" : "") + (st.vr_running ? "<br>▶ SteamVR kjører" : "");
  const mode = () => (($("#vr-mode .on") || {}).dataset || {}).m || st.mode;
  $("#vr-start").onclick = async () => { $("#vr-msg").textContent = "Starter …"; const r = await act({ a: "vr", do: "start", mode: mode() }); $("#vr-msg").textContent = (r && r.msg) || ""; loadVr(); };
  $("#vr-fix").onclick = async () => { $("#vr-msg").textContent = "Retter … (kan ta noen minutter)"; const r = await act({ a: "vr", do: "fixall", mode: mode() }); $("#vr-msg").textContent = (r && r.msg) || ""; loadVr(); };
  $("#vr-stop").onclick = async () => { const r = await act({ a: "vr", do: "stop" }); $("#vr-msg").textContent = (r && r.msg) || ""; };
}
// ---------- «Dagen i dag» (Hjem) og prestasjoner (Spill) ----------
const todayCard = document.createElement("div");
todayCard.className = "card"; todayCard.id = "c-today"; todayCard.hidden = true;
todayCard.innerHTML = '<h2>Dagen i dag</h2><div class="today-big" id="today-big"></div><div class="dim small" id="today-sub"></div>';
{ const g = $("#oversikt .grid") || $("#tiles"); if (g && g.parentElement) g.parentElement.insertBefore(todayCard, g.nextSibling); }
const achCard = document.createElement("div");
achCard.className = "card"; achCard.id = "c-ach"; achCard.hidden = true;
achCard.innerHTML = '<h2>🏆 Prestasjoner <span class="chip" id="ach-n"></span></h2><div class="ach-grid" id="ach-grid"></div>';
{ const sp = $("#spill .grid") || $("#fam-grid"); if (sp) sp.appendChild(achCard); }
async function loadToday() {
  let d; try { d = await X("today"); } catch (e) { return; }
  todayCard.hidden = false;
  $("#today-big").textContent = Math.floor(d.play_s / 3600) + " t " + Math.floor(d.play_s % 3600 / 60) + " min spilt" + (d.kr != null ? " · " + d.kr.toFixed(2) + " kr" : "");
  $("#today-sub").textContent = (d.text || "").split(" · ").slice(1).join(" · ") || "Ingen spill i dag ennå";
  const got = d.achievements.filter((a) => a.unlocked);
  achCard.hidden = false;
  $("#ach-n").textContent = got.length + " / " + d.achievements.length;
  $("#ach-grid").innerHTML = d.achievements.sort((a, b) => (!!b.unlocked) - (!!a.unlocked)).map((a) =>
    '<div class="ach' + (a.unlocked ? " on" : "") + '"><span>' + (a.unlocked ? a.icon : "🔒") + '</span><b>' + esc(a.name)
    + '</b><small>' + esc(a.desc) + '</small></div>').join("");
}
setTimeout(loadToday, 2500);
// ---------- venner: PC-er utenfor hjemmet ----------
const frCard = document.createElement("div");
frCard.className = "card"; frCard.id = "c-friends"; frCard.hidden = true;
frCard.innerHTML = '<h2>👥 Venner <span class="chip" id="fr-n"></span></h2><div id="fr-list"></div>'
  + '<div class="row full-only" style="margin-top:8px"><input id="fr-inv" placeholder="Lim inn ks-venn://…" style="flex:1;min-width:0">'
  + '<button class="soft" id="fr-add">Legg til</button></div><div class="dim small" id="fr-msg"></div>';
{ const sp = $("#spill .grid") || $("#fam-grid"); if (sp) sp.insertBefore(frCard, sp.firstChild); }
let frOpen = null;
async function loadFriends() {
  let st; try { st = await X("friends"); } catch (e) { return; }
  frCard.hidden = false;
  const on = st.friends.filter((f) => f.online);
  $("#fr-n").textContent = on.length + " på";
  const val = (v, u) => (v == null ? "–" : (typeof v === "number" ? Math.round(v) : v) + (u || ""));
  $("#fr-list").innerHTML = st.friends.length ? st.friends.map((f) => {
    const det = frOpen === f.addr ? '<div class="fr-det">' + [
      ["Spiller", f.game ? "🎮 " + f.game + (f.fps ? " · " + f.fps + " FPS" : "") : "–"],
      ["Spilt i dag", f.play_s != null ? Math.floor(f.play_s / 3600) + " t " + Math.floor(f.play_s % 3600 / 60) + " min" : "–"],
      ["CPU", val(f.cpu_t, "°") + " · " + val(f.cpu_l, " %")], ["GPU", val(f.gpu_t, "°") + " · " + val(f.gpu_l, " %")],
      ["Minne", f.ram_used != null ? f.ram_used + " / " + f.ram_total + " GB" : "–"], ["Strøm", val(f.watts, " W")],
      ["Prosessor", f.cpu || "–"], ["Skjermkort", f.gpu || "–"], ["Hovedkort", f.board || "–"], ["System", f.os || "–"],
    ].map(([k, v]) => '<div class="row between"><span class="dim">' + k + '</span><b>' + esc(String(v)) + '</b></div>').join("") + '</div>' : "";
    return '<div class="fr" data-fr="' + esc(f.addr) + '"><div class="row between"><b>' + (f.online ? "🟢 " : "⚫ ") + esc(f.friend)
      + '</b><span class="dim small">' + (f.online ? [f.cpu_t != null ? "CPU " + Math.round(f.cpu_t) + "°" : "", f.gpu_t != null ? "GPU " + Math.round(f.gpu_t) + "°" : ""].filter(Boolean).join(" · ") : "av") + '</span></div>'
      + (f.online && f.game ? '<div class="small">🎮 ' + esc(f.game) + '</div>' : "") + det + '</div>';
  }).join("") : '<p class="dim small">Ingen venner ennå – lim inn en invitasjon fra en venn.</p>';
  $$("[data-fr]").forEach((el) => (el.onclick = () => { frOpen = frOpen === el.dataset.fr ? null : el.dataset.fr; loadFriends(); }));
  $("#fr-add").onclick = async () => { const r = await act({ a: "friend", do: "add", invite: $("#fr-inv").value }); $("#fr-msg").textContent = (r && r.msg) || ""; $("#fr-inv").value = ""; loadFriends(); };
}
async function loadPlan() {
  let p; try { p = await X("plan"); } catch (e) { planCard.hidden = true; return; }
  planCard.hidden = false;
  const today = (new Date().getDay() + 6) % 7;
  const sel = $("#plan-day");
  if (!sel.options.length) { sel.innerHTML = p.days.map((d, i) => '<option value="' + i + '">' + esc(d) + '</option>').join(""); sel.value = today; }
  let last = -1;
  $("#plan-list").innerHTML = p.items.length ? p.items.map((x) => {
    const h = x.day !== last ? '<div class="plan-day"><b>' + esc(p.days[x.day]) + (x.day === today ? " · i dag" : "") + '</b></div>' : "";
    last = x.day;
    return h + '<div class="row between plan-it"><span>' + esc(x.at) + ' &nbsp;' + esc(x.text)
      + (x.who && x.who !== "*" ? ' <small class="dim">· ' + esc(x.who) + '</small>' : "") + '</span><button class="soft" data-pdel="' + esc(x.id) + '">✕</button></div>';
  }).join("") : "Ingen avtaler ennå.";
  $$("[data-pdel]").forEach((b) => (b.onclick = async () => { await act({ a: "plan_del", id: b.dataset.pdel }); loadPlan(); }));
}
$("#plan-add").onclick = async () => {
  const text = $("#plan-text").value.trim(); if (!text) { toast("Skriv hva det gjelder"); return; }
  await act({ a: "plan_add", day: +$("#plan-day").value, at: $("#plan-at").value, text, who: $("#plan-who").value.trim() || "*", remind: 15 });
  $("#plan-text").value = ""; loadPlan();
};
async function loadShop() {
  let s; try { s = await X("shop"); } catch (e) { shopCard.hidden = true; return; }
  shopCard.hidden = false;
  $("#shop-stars").textContent = "⭐ " + s.stars;
  $("#shop-items").innerHTML = s.items.map((x) => '<button type="button" class="goal" data-shop="' + esc(x.id) + '"' + (s.stars < x.price ? " disabled" : "")
    + '><span class="gi">' + esc(x.icon) + '</span><span>' + esc(x.name) + '</span><small>' + x.price + ' ⭐</small></button>').join("");
  $$("[data-shop]").forEach((b) => (b.onclick = async () => { vibe(10); await act({ a: "shop_req", item: b.dataset.shop }); loadShop(); }));
  const full = !document.body.classList.contains("limited");
  $("#shop-pending").innerHTML = s.pending.map((r) => '<div class="row between goal-req"><span>' + esc(r.icon) + ' <b>' + esc(r.name)
    + '</b><br><small class="dim">' + esc(r.pc || "") + ' · ' + r.price + ' ⭐</small></span>'
    + (full ? '<span class="row"><button class="primary" data-sok="' + esc(r.id) + '">Godkjenn</button><button class="soft" data-sno="' + esc(r.id) + '">Avslå</button></span>'
      : '<span class="dim small">Venter …</span>') + '</div>').join("");
  $$("[data-sok]").forEach((b) => (b.onclick = async () => { await act({ a: "shop_ok", id: b.dataset.sok, ok: true }); loadShop(); }));
  $$("[data-sno]").forEach((b) => (b.onclick = async () => { await act({ a: "shop_ok", id: b.dataset.sno, ok: false }); loadShop(); }));
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

// ---------- Discord (Styr) ----------
const dcCard = document.createElement("div");
dcCard.className = "card"; dcCard.id = "c-discord"; dcCard.dataset.ord = "-5"; dcCard.hidden = true;
dcCard.innerHTML = '<div class="row between"><h2>Discord</h2><span class="dim small" id="dc-st"></span></div>'
  + '<div class="dc-big"><button type="button" id="dc-mic">🎙️<span>Mikrofon av</span></button><button type="button" id="dc-deaf">🎧<span>Lyd av</span></button>'
  + '<button type="button" id="dc-leave" class="danger">📞<span>Forlat</span></button></div>'
  + '<div id="dc-ch" class="dim small"></div>'
  + '<div id="dc-full"><div class="row"><span>Mikrofonvolum</span><input type="range" id="dc-in" min="0" max="100"></div>'
  + '<div class="row"><span>Volum på samtalen</span><input type="range" id="dc-out" min="0" max="200"></div>'
  + '<div class="row"><span>Når snakker du?</span><select id="dc-mode" data-title="Når snakker du?"><option value="VOICE_ACTIVITY">Stemmeaktivering</option><option value="PUSH_TO_TALK">Trykk for å snakke</option></select></div>'
  + '<div class="row"><span>Støydemping</span><label class="switch"><input type="checkbox" id="dc-noise"><i></i></label></div>'
  + '<div class="row"><span>Ekkodemping</span><label class="switch"><input type="checkbox" id="dc-echo"><i></i></label></div>'
  + '<div class="row"><span>Automatisk forsterkning</span><label class="switch"><input type="checkbox" id="dc-agc"><i></i></label></div></div>'
  + '<div id="dc-sys" class="row"><span>Discord-volum</span><input type="range" id="dc-sysvol" min="0" max="150"></div>'
  + '<p class="dim small" id="dc-note"></p>';
{ const g = $("#kontroll .grid"); if (g) g.insertBefore(dcCard, g.children[1] || null); }
let dcState = null, dcHold = 0;
const dcAct = (body) => { dcHold = Date.now() + 2500; return act(Object.assign({ a: "discord" }, body), true).then(() => setTimeout(loadDiscord, 700)); };
async function loadDiscord() {
  let st; try { st = await X("discord"); } catch (e) { dcCard.hidden = true; return; }
  dcState = st;
  dcCard.hidden = !st.running && !st.linked;
  if (Date.now() < dcHold) return;
  const v = st.voice, a = st.audio || {};
  $("#dc-st").textContent = !st.running ? "ikke startet" : v ? "koblet til" : "via lydsystemet";
  const mic = v ? v.mute : !!(a.mic && a.mic[1]), deaf = v ? v.deaf : !!(a.out && a.out[1]);
  $("#dc-mic").classList.toggle("on", !!mic); $("#dc-deaf").classList.toggle("on", !!deaf);
  $("#dc-mic").disabled = !v && !a.mic; $("#dc-deaf").disabled = !v && !a.out; $("#dc-leave").disabled = !st.channel;
  $("#dc-ch").innerHTML = st.channel ? "🔊 " + esc(st.channel.name || "Samtale") + " · " + st.channel.members.map((m) => esc(m.name || "?") + (m.mute ? " 🔇" : "")).join(", ")
    : (v ? "Ikke i en samtale." : "Bli med i en samtale i Discord for å styre den her.");
  $("#dc-full").hidden = !v; $("#dc-sys").hidden = !!v || !a.out;
  if (v) {
    $("#dc-in").value = v.in_vol; $("#dc-out").value = v.out_vol; $("#dc-mode").value = v.mode;
    $("#dc-noise").checked = !!v.noise; $("#dc-echo").checked = !!v.echo; $("#dc-agc").checked = !!v.agc;
  } else if (a.out) $("#dc-sysvol").value = a.out[0];
  $("#dc-note").textContent = st.linked ? (st.error ? "Discord: " + st.error : "") :
    "Volum, mikrofonmodus og demping: koble Kontrollsenter til Discord på PC-en (siden Discord, nederst).";
}
$("#dc-mic").onclick = () => { const on = !$("#dc-mic").classList.contains("on"); $("#dc-mic").classList.toggle("on", on); vibe(10);
  dcAct(dcState && dcState.voice ? { do: "mute", on } : { do: "mic_mute_sys", on }); };
$("#dc-deaf").onclick = () => { const on = !$("#dc-deaf").classList.contains("on"); $("#dc-deaf").classList.toggle("on", on); vibe(10);
  dcAct(dcState && dcState.voice ? { do: "deaf", on } : { do: "out_mute_sys", on }); };
$("#dc-leave").onclick = async () => { if (await confirmDlg("Forlate samtalen i Discord?")) dcAct({ do: "leave" }); };
$("#dc-in").onchange = () => dcAct({ do: "in_vol", value: +$("#dc-in").value });
$("#dc-out").onchange = () => dcAct({ do: "out_vol", value: +$("#dc-out").value });
$("#dc-sysvol").onchange = () => dcAct({ do: "out_vol_sys", value: +$("#dc-sysvol").value });
$("#dc-mode").onchange = () => dcAct({ do: "mode", value: $("#dc-mode").value });
["noise", "echo", "agc"].forEach((k) => ($("#dc-" + k).onchange = () => dcAct({ do: k, on: $("#dc-" + k).checked })));
setInterval(() => tab === "kontroll" && !document.hidden && loadDiscord(), 4000);
// servere, kanaler og chat (lesing – svar i Discord)
{ const b = document.createElement("button"); b.type = "button"; b.className = "soft wide"; b.id = "dc-servers"; b.textContent = "💬 Servere og chat";
  $("#dc-note").before(b); b.onclick = () => dcServers(); }
const dcSheet = document.createElement("div");
dcSheet.className = "sheet-back"; dcSheet.hidden = true;
dcSheet.innerHTML = '<div class="sheet det-sheet dc-sheet" role="dialog"><div class="grab"></div><div class="sheet-head"><button class="icon" id="dcs-back" aria-label="Tilbake">‹</button>'
  + '<b id="dcs-t">Discord</b><button class="icon" id="dcs-x" aria-label="Lukk">✕</button></div><div class="sheet-list" id="dcs-body"></div><div id="dcs-foot"></div></div>';
document.body.appendChild(dcSheet);
let dcView = null, dcTimer = 0;
const dcOpen = () => { dcSheet.hidden = false; requestAnimationFrame(() => dcSheet.classList.add("open")); };
const dcClose = () => { clearInterval(dcTimer); dcView = null; dcSheet.classList.remove("open"); setTimeout(() => { if (!dcView) dcSheet.hidden = true; }, 230); };
dcSheet.onclick = (e) => { if (e.target === dcSheet) dcClose(); };
$("#dcs-x").onclick = dcClose;
$("#dcs-back").onclick = () => { if (dcView && dcView.c) dcChannels(dcView.g, dcView.gname); else if (dcView && dcView.g) dcServers(); else dcClose(); };
const openOut = (u) => { if (KS && KS.openUrl) KS.openUrl(u); else if (KS && KS.openApp) KS.openApp("com.discord"); else window.open(u, "_blank"); };
async function dcServers() {
  clearInterval(dcTimer); dcView = {}; $("#dcs-t").textContent = "Servere"; $("#dcs-foot").innerHTML = ""; $("#dcs-back").hidden = true;
  $("#dcs-body").innerHTML = '<p class="dim small" style="padding:16px">Henter …</p>'; dcOpen();
  try {
    const r = await X("dc_guilds");
    if (r.need_relink) { $("#dcs-body").innerHTML = '<p class="dim" style="padding:16px">Trykk «Koble til på nytt» på Discord-siden på PC-en én gang til, så får Kontrollsenter lov til å lese chatten.</p>'; return; }
    $("#dcs-body").innerHTML = r.guilds.map((g) => '<button class="sheet-row" data-g="' + esc(g.id) + '" data-n="' + esc(g.name) + '">'
      + (g.icon ? '<span class="pk-ic"><img src="' + esc(g.icon) + '" alt="" style="width:36px;height:36px;border-radius:12px"></span>' : '<span class="pk-ic">💬</span>')
      + '<span class="pk-t"><b>' + esc(g.name) + '</b></span></button>').join("") || '<p class="dim" style="padding:16px">Ingen servere – er Kontrollsenter koblet til Discord på PC-en?</p>';
    $$("#dcs-body [data-g]").forEach((b) => (b.onclick = () => dcChannels(b.dataset.g, b.dataset.n)));
  } catch (e) { $("#dcs-body").innerHTML = '<p class="dim" style="padding:16px">' + esc(e.message) + '</p>'; }
}
async function dcChannels(g, name) {
  clearInterval(dcTimer); dcView = { g, gname: name }; $("#dcs-t").textContent = name; $("#dcs-back").hidden = false; $("#dcs-foot").innerHTML = "";
  $("#dcs-body").innerHTML = '<p class="dim small" style="padding:16px">Henter kanaler …</p>';
  try {
    const r = await X("dc_channels", "g=" + encodeURIComponent(g));
    const ic = { text: "#", news: "📣", forum: "💬", voice: "🔊", stage: "🎙️" };
    $("#dcs-body").innerHTML = r.channels.map((c) => '<button class="sheet-row" data-c="' + esc(c.id) + '" data-k="' + c.kind + '" data-n="' + esc(c.name) + '"><span class="pk-ic">'
      + ic[c.kind] + '</span><span class="pk-t"><b>' + esc(c.name) + '</b></span></button>').join("");
    $$("#dcs-body [data-c]").forEach((b) => (b.onclick = () => (b.dataset.k === "text" || b.dataset.k === "news")
      ? dcChat(g, name, b.dataset.c, b.dataset.n) : openOut("https://discord.com/channels/" + g + "/" + b.dataset.c)));
  } catch (e) { $("#dcs-body").innerHTML = '<p class="dim" style="padding:16px">' + esc(e.message) + '</p>'; }
}
async function dcChat(g, gname, c, name) {
  dcView = { g, gname, c }; $("#dcs-t").textContent = "# " + name;
  $("#dcs-body").innerHTML = '<p class="dim small" style="padding:16px">Henter chatten …</p>';
  $("#dcs-foot").innerHTML = '<button class="primary wide" id="dcs-open">Svar i Discord</button>';
  $("#dcs-open").onclick = () => openOut("https://discord.com/channels/" + g + "/" + c);
  let lastId = null;
  const load = async () => {
    try {
      const d = await X("dc_chat", "g=" + encodeURIComponent(g) + "&c=" + encodeURIComponent(c));
      const ms = d.messages; const id = ms.length ? ms[ms.length - 1].id : "";
      if (id === lastId) return; lastId = id;
      const body = $("#dcs-body"), atEnd = body.scrollTop + body.clientHeight >= body.scrollHeight - 40;
      let prev = null;
      body.innerHTML = ms.map((m) => { const head = m.author !== prev; prev = m.author;
        const t = new Date(m.t * 1000).toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
        return '<div class="dc-msg' + (m.mine ? " mine" : "") + '">' + (head ? '<div class="dc-who"><b style="color:' + esc(m.color || "var(--acc)") + '">' + esc(m.author) + '</b> <small class="dim">' + t + '</small></div>' : "")
          + '<div class="dc-bub">' + esc(m.content) + '</div></div>'; }).join("") || '<p class="dim" style="padding:16px">Ingen meldinger ennå.</p>';
      if (atEnd || lastId === id) body.scrollTop = body.scrollHeight;
    } catch (e) { $("#dcs-body").innerHTML = '<p class="dim" style="padding:16px">' + esc(e.message) + '</p>'; }
  };
  await load();
  clearInterval(dcTimer); dcTimer = setInterval(() => !document.hidden && dcView && dcView.c === c && load(), 4000);
}

// ---------- glød på flisene: lys som følger fingeren / musa, og glød rundt ----------
(() => {
  const SEL = "#tiles > [data-k], .scene, .quick button[data-q], .dc-big button, .goal";
  let cur = null, off = 0;
  const place = (el, ev) => {
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", (ev.clientX - r.left) + "px");
    el.style.setProperty("--my", (ev.clientY - r.top) + "px");
  };
  const light = (el, ev) => {
    if (cur && cur !== el) cur.classList.remove("glowing");
    clearTimeout(off);
    cur = el; place(el, ev); el.classList.add("glowing");
  };
  const dim = () => { const el = cur; off = setTimeout(() => { if (el) el.classList.remove("glowing"); if (cur === el) cur = null; }, 380); };
  document.addEventListener("pointerdown", (ev) => {
    if (dashEditing || document.body.classList.contains("eco")) return;
    const el = ev.target.closest(SEL); if (el) light(el, ev);
  }, true);
  document.addEventListener("pointermove", (ev) => {
    if (dashEditing) return;
    const el = ev.target.closest && ev.target.closest(SEL);
    if (ev.pointerType === "mouse") { if (el) light(el, ev); else if (cur) dim(); }
    else if (cur && ev.buttons) place(cur, ev);
  }, true);
  document.addEventListener("pointerup", (ev) => { if (ev.pointerType !== "mouse") dim(); }, true);
  document.addEventListener("pointercancel", dim, true);
})();

// ---------- snarveier på Hjem: del siste klipp, fjernstyr (RustDesk) og live-status mens du spiller ----------
(() => {
  const q = $("#quick"); if (!q) return;
  const mk = (key, icon, label, sub) => { const b = document.createElement("button"); b.dataset.q = key;
    b.innerHTML = '<span class="qi">' + icon + '</span><span class="ql">' + label + '</span><span class="qs">' + sub + '</span>'; q.appendChild(b); return b; };
  mk("shareclip", "📤", "Del klipp", "Siste klipp").onclick = async () => {
    try {
      const c = await X("clips");
      const list = (c.clips || []).slice().sort((a, b) => (b.t || 0) - (a.t || 0));
      if (!list.length) { toast("Ingen klipp ennå"); return; }
      if (typeof shareFile === "function") shareFile(list[0].name, list[0].pc);
    } catch (e) { toast(e.message); }
  };
  const RAPPS = { rustdesk: ["RustDesk", "com.carriez.flutter_hbb"], anydesk: ["AnyDesk", "com.anydesk.anydeskandroid"],
    teamviewer: ["TeamViewer", "com.teamviewer.teamviewer.market.mobile"], parsec: ["Parsec", "com.parsec.app"],
    chromerd: ["Chrome Remote Desktop", "com.google.chromeremotedesktop"], remmina: ["RustDesk", "com.carriez.flutter_hbb"] };
  const rb = mk("remote", "🖥️", "Fjernstyr", "RustDesk");
  X("stream").then((st) => { const a = RAPPS[st.remote_app]; if (a) rb.querySelector(".qs").textContent = a[0]; }).catch(() => {});
  rb.onclick = async () => {
    try {
      const st = await X("stream");
      const app = RAPPS[st.remote_app] || RAPPS.rustdesk;
      if (app[0] === "RustDesk") {
        const id = st.rustdesk && st.rustdesk.id;
        if (id) { try { await navigator.clipboard.writeText(id); } catch (e) {} toast("RustDesk-ID " + id + " er kopiert"); }
        else toast("RustDesk er ikke satt opp på PC-en (Strømming)");
      }
      if (KS && KS.openApp && !KS.openApp(app[1])) toast("Installer " + app[0] + " på telefonen først");
    } catch (e) { toast(e.message); }
  };
})();
let liveAsked = false;
function liveCheck(s) {                                     // levende varsel med FPS og temperatur mens du spiller
  if (!s || !KS || !KS.startLive || liveAsked || !pref("live_note", true)) return;
  if (s.game) { liveAsked = true; try { KS.startLive(); } catch (e) {} }
}
{ const _ro = window.renderOverview; if (_ro) window.renderOverview = function (s) { _ro(s); liveCheck(s); }; }

// ---------- lyd- og skjermprofiler, nattlys og lysstyrke (Styr) ----------
const avCard = document.createElement("div");
avCard.className = "card"; avCard.id = "c-avprof"; avCard.hidden = true;
avCard.innerHTML = '<h2>Lyd og skjerm</h2><div class="dim small">Lydprofil</div><div class="seg wrap" id="av-audio"></div>'
  + '<div class="dim small" style="margin-top:8px">Skjermprofil</div><div class="seg wrap" id="av-display"></div>'
  + '<div class="row between" id="av-nrow" style="margin-top:10px"><span>🌙 Nattlys</span><label class="switch"><input type="checkbox" id="av-night"><i></i></label></div>'
  + '<div class="row between" id="av-brow"><span>☀️ Lysstyrke</span><input type="range" min="1" max="100" id="av-bri" style="flex:1;margin-left:12px"></div>';
{ const g = $("#kontroll .grid"); if (g) g.insertBefore(avCard, $("#c-power") ? $("#c-power").nextSibling : null); }
async function pushScenesToPhone() {
  try { if (KS && KS.setScenes) { const sc = await X("scenes"); KS.setScenes(JSON.stringify((sc.scenes || []).map((x) => ({ id: x.id, name: x.name, icon: x.icon })))); } } catch (e) {}
}
setTimeout(pushScenesToPhone, 4000);
const pushCard = document.createElement("div");
pushCard.className = "card full-only"; pushCard.id = "c-push"; pushCard.hidden = true;
pushCard.innerHTML = '<h2>Pushvarsler med ntfy</h2><p class="dim small">Varsler fra PC-en med en gang – uten at appen er åpen, '
  + 'og uten skytjenester. ntfy-appen kobler seg direkte til PC-en og bruker nesten ikke batteri.</p>'
  + '<div class="row between"><span>Send varsler til ntfy</span><label class="switch"><input type="checkbox" id="push-on"><i></i></label></div>'
  + '<div class="row" style="margin-top:8px"><button class="primary" id="push-add">Legg til i ntfy</button><button class="soft" id="push-get">Hent ntfy</button></div>'
  + '<div class="dim small" id="push-url" style="margin-top:6px;word-break:break-all"></div>';
{ const g = $("#system .grid"); if (g) g.appendChild(pushCard); }
const fxCard = document.createElement("div");
fxCard.className = "card"; fxCard.id = "c-fx";
fxCard.innerHTML = '<h2>Effekter</h2><p class="dim small">Kort som glir inn, knapper som gir etter og levende bakgrunn.</p>'
  + '<div class="seg" id="fx-seg"><button data-fx="full">Full</button><button data-fx="rolig">Rolig</button><button data-fx="av">Av</button></div>';
{ const g = $("#system .grid"); if (g) g.insertBefore(fxCard, g.children[1] || null); }
$$("#fx-seg button").forEach((b) => {
  b.classList.toggle("on", b.dataset.fx === pref("fx", "full"));
  b.onclick = () => { setPref("fx", b.dataset.fx); applyFx(); $$("#fx-seg button").forEach((x) => x.classList.toggle("on", x === b)); fxEnter("system"); };
});
async function loadPush() {
  if (document.body.classList.contains("limited")) return;
  let st; try { st = await X("push"); } catch (e) { return; }
  pushCard.hidden = false;
  const host = location.hostname, url = "http://" + host + ":" + st.port + "/" + st.topic;
  $("#push-on").checked = st.enabled;
  $("#push-on").onchange = async () => { await act({ a: "push", on: $("#push-on").checked }); loadPush(); };
  $("#push-url").textContent = st.enabled ? "Server: http://" + host + ":" + st.port + " · emne: " + st.topic : "";
  $("#push-add").onclick = async () => {
    if (!$("#push-on").checked) { await act({ a: "push", on: true }); }
    const deep = "ntfy://" + host + ":" + st.port + "/" + st.topic + "?secure=false";
    if (KS && KS.openUrl) KS.openUrl(deep); else location.href = deep;
    try { await navigator.clipboard.writeText(url); } catch (e) {}
    toast("Åpner ntfy – trykk «Abonner». Adressen er også kopiert.");
  };
  $("#push-get").onclick = () => { if (KS && KS.openApp) KS.openApp("io.heckel.ntfy"); else window.open("https://ntfy.sh/docs/subscribe/phone/"); };
}
async function loadAv() {
  let st; try { st = await X("avprofiles"); } catch (e) { avCard.hidden = true; return; }
  avCard.hidden = false;
  const btns = (list, cur, kind) => list.length ? list.map((p) => '<button data-av="' + kind + '" data-id="' + esc(p.id) + '" class="'
    + (p.id === cur ? "on" : "") + '">' + esc((p.icon || "") + " " + p.name) + '</button>').join("") : '<span class="dim small">Lag profiler på PC-en</span>';
  $("#av-audio").innerHTML = btns(st.audio, st.audio_active, "audio");
  $("#av-display").innerHTML = btns(st.display, st.display_active, "display");
  $$("[data-av]").forEach((b) => (b.onclick = async () => { vibe(10); await act({ a: "avprofile", kind: b.dataset.av, id: b.dataset.id }); loadAv(); }));
  const n = $("#av-night"); n.checked = !!(st.night && st.night.on); $("#av-nrow").hidden = !st.night;
  n.onchange = () => act({ a: "nightlight", on: n.checked, temp: 3400 });
  const r = $("#av-bri"); $("#av-brow").hidden = st.brightness == null; if (st.brightness != null) r.value = st.brightness;
  r.onchange = () => act({ a: "brightness", value: +r.value });
}


// ================================================================================================
// «Alt fra PC-en»: PC-funksjonene som kort – tegnes automatisk ut fra det PC-en beskriver (apppanels.py)
// ================================================================================================
const pnWrap = document.createElement("div");
pnWrap.id = "pc-panels";
pnWrap.innerHTML = '<h2 class="sec-h">Alt fra PC-en</h2><div id="pn-list"></div>';
{ const m = $("#mer"); if (m) m.insertBefore(pnWrap, m.firstChild); }
const pnOpen = new Set(JSON.parse(localStorage.getItem("ks_pn_open") || '["commands","games"]'));
function pnSave() { try { localStorage.setItem("ks_pn_open", JSON.stringify([...pnOpen])); } catch (e) {} }
async function pnRun(act_, confirmText) {
  if (confirmText && !confirm(confirmText)) return;
  vibe(10);
  const r = await act(act_);
  if (r && r.msg) toast(r.msg);
  setTimeout(loadPanels, 1500);
}
function pnBtn(b) {
  return '<button class="' + (b.primary ? "primary" : "soft") + ' small" data-pa=\'' + esc(JSON.stringify(b.action)) + '\''
    + (b.confirm ? ' data-pc="' + esc(b.confirm) + '"' : "") + '>' + esc(b.label) + '</button>';
}
function pnImg(src) {
  if (!src) return "";
  const u = src.startsWith("/api/") ? src + (src.includes("?") ? "&" : "?") + "k=" + encodeURIComponent(token) : src;
  return '<img loading="lazy" src="' + esc(u) + '" onerror="this.remove()">';
}
function pnRender(p) {
  const open = pnOpen.has(p.id);
  let h = '<div class="card pn' + (open ? " open" : "") + '" data-pn="' + esc(p.id) + '"><div class="pn-h"><span class="pn-i">' + esc(p.icon || "•")
    + '</span><b>' + esc(p.title) + '</b><span class="pn-c">' + (open ? "▾" : "▸") + '</span></div>';
  if (open) {
    if (p.desc) h += '<p class="dim small">' + esc(p.desc) + '</p>';
    if (p.search) h += '<input class="pn-q" placeholder="Søk …" data-pq="' + esc(p.id) + '">';
    if (p.rows && p.rows.length) h += '<div class="pn-rows">' + p.rows.map(([k, v]) => '<div class="row between"><span class="dim">' + esc(k) + '</span><b>' + esc(String(v)) + '</b></div>').join("") + '</div>';
    if (p.select) h += '<div class="row between"><span>' + esc(p.select.label) + '</span><select data-ps=\'' + esc(JSON.stringify(p.select.action)) + '\''
      + (p.select.confirm ? ' data-pc="' + esc(p.select.confirm) + '"' : "") + '>' + p.select.options.map(([v, t]) => '<option value="' + esc(v) + '"' + (v === p.select.value ? " selected" : "") + '>' + esc(t) + '</option>').join("") + '</select></div>';
    const wheelList = p.items && p.items.length > 10 && !p.grid && p.items.every((it) => it.tap);
    if (wheelList) {
      h += '<div class="row pn-wheel"><select data-title="' + esc(p.title) + '">' + p.items.map((it) => '<option value=\'' + esc(JSON.stringify(it.tap)) + '\'>'
        + esc(it.title) + '</option>').join("") + '</select><button class="primary small" data-pw="1">Kjør</button></div>';
    } else if (p.items && p.items.length) h += '<div class="pn-items' + (p.grid ? " grid" : "") + '">' + p.items.map((it) =>
      '<div class="pn-it" data-q="' + esc((it.title + " " + (it.sub || "")).toLowerCase()) + '"' + (it.detail ? ' data-pd=\'' + esc(JSON.stringify(it.detail)) + '\'' : "")
      + (it.tap ? ' data-pa=\'' + esc(JSON.stringify(it.tap)) + '\'' : "") + '>' + pnImg(it.img)
      + '<div class="pn-t"><b>' + esc(it.title) + '</b>' + (it.badge ? ' <span class="chip">' + esc(it.badge) + '</span>' : "")
      + (it.sub ? '<small class="dim">' + esc(it.sub) + '</small>' : "") + '</div>'
      + (it.buttons && it.buttons.length > 3 ? '<div class="row pn-wheel"><select data-title="' + esc(it.title) + '">' + it.buttons.map((b) => '<option value=\''
          + esc(JSON.stringify(b.action)) + '\'' + (b.confirm ? ' data-pc="' + esc(b.confirm) + '"' : "") + '>' + esc(b.label) + '</option>').join("") + '</select><button class="primary small" data-pw="1">▶</button></div>'
        : it.buttons && it.buttons.length ? '<div class="pn-b">' + it.buttons.map(pnBtn).join("") + '</div>' : "") + '</div>').join("") + '</div>';
    if (p.buttons && p.buttons.length) h += '<div class="row wrap pn-bb">' + p.buttons.map(pnBtn).join("") + '</div>';
  }
  return h + '</div>';
}
let pnData = [];
function pnRedraw() {
  // hvert panel tegnes og flyttes til riktig fane og kategori (layout.js)
  document.querySelectorAll(".card.pn").forEach((el) => el.parentNode.removeChild(el));
  $("#pn-list").innerHTML = pnData.map(pnRender).join("");
  if (window.ksPlacePanels) window.ksPlacePanels();
  pnWire();
}
async function loadPanels() {
  if (document.body.classList.contains("limited")) { pnWrap.hidden = true; return; }
  let d; try { d = await X("panels"); } catch (e) { return; }
  pnData = d.panels || [];
  pnRedraw();
}
function pnWire() {
  $$(".card.pn .pn-h").forEach((el) => (el.onclick = () => { const id = el.parentElement.dataset.pn; pnOpen.has(id) ? pnOpen.delete(id) : pnOpen.add(id); pnSave(); pnRedraw(); }));
  $$(".card.pn [data-pa]").forEach((el) => (el.onclick = (e) => { e.stopPropagation(); pnRun(JSON.parse(el.dataset.pa), el.dataset.pc); }));
  $$(".card.pn [data-ps]").forEach((el) => (el.onchange = () => pnRun({ ...JSON.parse(el.dataset.ps), value: el.value }, el.dataset.pc)));
  $$(".card.pn [data-pw]").forEach((el) => (el.onclick = (e) => {      // rullehjul + «Kjør»
    e.stopPropagation(); const sel = el.parentElement.querySelector("select"); if (!sel || !sel.value) return;
    const o = sel.options[sel.selectedIndex]; pnRun(JSON.parse(sel.value), o.dataset.pc);
  }));
  $$(".card.pn [data-pd]").forEach((el) => (el.onclick = () => pnDetail(JSON.parse(el.dataset.pd))));
  $$(".card.pn [data-pq]").forEach((el) => (el.oninput = () => {
    const q = el.value.toLowerCase(); el.parentElement.querySelectorAll(".pn-it").forEach((it) => (it.hidden = q && !it.dataset.q.includes(q)));
  }));
}
// detaljvindu (f.eks. «Alt om PC-en»)
const pnSheet = h(`<div id="pn-sheet" class="pn-sheet" hidden><div class="pn-sheet-in"><div class="row between"><h2 id="pn-st"></h2><button class="icon" id="pn-x">✕</button></div><div id="pn-sb"></div></div></div>`);
document.body.appendChild(pnSheet);
$("#pn-x").onclick = () => { pnSheet.hidden = true; clearInterval(pnSheet._t); };
pnSheet.onclick = (e) => { if (e.target === pnSheet) $("#pn-x").onclick(); };
async function pnDetail(det) {
  pnSheet.hidden = false;
  const draw = async () => {
    const qs = new URLSearchParams(det.q || {}).toString();
    let d; try { d = await X(det.what, qs); } catch (e) { $("#pn-sb").textContent = e.message; return; }
    $("#pn-st").textContent = (d.online ? "🟢 " : "⚫ ") + d.title;
    $("#pn-sb").innerHTML = d.sections.map(([t, rows]) => '<div class="pn-sec"><div class="dim small">' + esc(t) + '</div>'
      + rows.map(([k, v]) => '<div class="row between"><span>' + esc(k) + '</span><b>' + esc(String(v)) + '</b></div>').join("") + '</div>').join("");
  };
  $("#pn-sb").textContent = "Henter …";
  await draw();
  clearInterval(pnSheet._t); pnSheet._t = setInterval(() => { if (!pnSheet.hidden) draw(); }, 5000);
}

// ---------- fremdrift fra PC-en (installasjoner, opprydding, sjekker …) ----------
const tasksBar = h('<div id="pc-tasks" class="pc-tasks" hidden></div>');
document.body.appendChild(tasksBar);
function renderTasks(s) {
  const ts = (s && s.tasks) || [];
  tasksBar.hidden = !ts.length;
  tasksBar.innerHTML = ts.map((t) => '<div class="pt' + (t.done ? (t.ok ? " ok" : " bad") : "") + '"><div class="row between"><b>' + esc(t.title)
    + '</b><b>' + (t.done ? (t.ok ? "✓" : "✗") : (t.pct != null ? t.pct + " %" : "")) + '</b></div><div class="pt-bar"><i style="width:'
    + (t.done ? 100 : (t.pct || 0)) + '%"' + (t.pct == null && !t.done ? ' class="pulse"' : "") + '></i></div><div class="row between dim small"><span>'
    + esc(t.done ? (t.result || "") : (t.detail || "")) + '</span><span>' + esc(t.eta || "") + '</span></div></div>').join("");
}
{ const _ro2 = window.renderOverview; if (_ro2) window.renderOverview = function (s) { _ro2(s); renderTasks(s); }; }

// ---------- stue-modus på telefonen/nettbrettet ----------
const amb = h(`<div id="amb" class="amb" hidden><div class="amb-clock" id="amb-c"></div><div class="amb-date" id="amb-d"></div>
  <div class="amb-grid"><div class="amb-card"><small>VÆRET</small><b id="amb-w">–</b></div><div class="amb-card"><small>PC-EN</small><b id="amb-t">–</b></div>
  <div class="amb-card"><small>I DAG</small><b id="amb-p">–</b></div></div><div class="amb-card amb-fam" id="amb-f"></div></div>`);
document.body.appendChild(amb);
const DAGER = ["søndag", "mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag"];
const MND = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "desember"];
function ambTick() {
  const d = new Date();
  $("#amb-c").textContent = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  $("#amb-d").textContent = DAGER[d.getDay()][0].toUpperCase() + DAGER[d.getDay()].slice(1) + " " + d.getDate() + ". " + MND[d.getMonth()];
  if (last) $("#amb-t").textContent = (last.cpu && last.cpu.temp != null ? Math.round(last.cpu.temp) + "°" : "–") + " / " + (last.gpu && last.gpu.temp != null ? Math.round(last.gpu.temp) + "°" : "–");
}
async function ambData() {
  try { const t = await X("today"); $("#amb-p").textContent = Math.floor(t.play_s / 3600) + " t " + Math.floor(t.play_s % 3600 / 60) + " min"; } catch (e) {}
  try { const w = last && last.info && last.info.weather; if (w && w.temp != null) $("#amb-w").textContent = (w.icon || "") + " " + w.temp + "°"; } catch (e) {}
  try { const f = await X("family"); const now = Date.now() / 1000;
    $("#amb-f").innerHTML = '<small>HJEMME</small>' + f.pcs.map((p) => { const on = !p.off && now - (p.time || 0) < 900; return '<div>' + (on ? "🟢 " : "⚫ ") + esc(p.name) + (on && p.game ? " · 🎮 " + esc(p.game) : "") + '</div>'; }).join(""); } catch (e) {}
}
function openAmbient() {
  amb.hidden = false; ambTick(); ambData();
  amb._t1 = setInterval(ambTick, 1000); amb._t2 = setInterval(ambData, 20000);
  try { amb.requestFullscreen && amb.requestFullscreen(); } catch (e) {}
  try { if (window.KS && KS.keepScreenOn) KS.keepScreenOn(true); } catch (e) {}
}
amb.onclick = () => { amb.hidden = true; clearInterval(amb._t1); clearInterval(amb._t2); try { document.fullscreenElement && document.exitFullscreen(); } catch (e) {} };
{ const q = $("#quick"); if (q) { const b = document.createElement("button"); b.dataset.q = "ambient";
  b.innerHTML = '<span class="qi">📺</span><span class="ql">Stue-modus</span><span class="qs">Klokke og status</span>'; b.onclick = openAmbient; q.appendChild(b); } }

// ---------- nytt tema hver dag (appen) ----------
function dailyTheme() {
  if (!pref("daily_theme", false) || !window.KS_THEMES) return;
  const d = new Date().toISOString().slice(0, 10);
  const list = KS_THEMES.filter((t) => t.k !== "standard" && (t.dark !== false) === pref("daily_dark", true));
  let hsh = 0; for (const c of d) hsh = (hsh * 31 + c.charCodeAt(0)) >>> 0;
  const pick = list[hsh % list.length];
  if (pick && window.setLook) window.setLook(pick.k);
  else if (pick) { document.documentElement.setAttribute("data-ks", pick.k); try { localStorage.setItem("ks_look", pick.k); } catch (e) {} }
}
dailyTheme();
{ const fx = $("#c-fx"); if (fx) { const r = h('<div class="row between" style="margin-top:8px"><span>Nytt tema hver dag</span><label class="switch"><input type="checkbox" id="dt-on"><i></i></label></div>');
  fx.appendChild(r); $("#dt-on").checked = pref("daily_theme", false); $("#dt-on").onchange = () => { setPref("daily_theme", $("#dt-on").checked); dailyTheme(); }; } }

// ---------- kobling ----------
const dashSetTab = setTab;
// effekter: kortene glir inn ved fanebytte (Innstillinger → Utseende → Effekter)
function applyFx() {
  const lv = pref("fx", "full");
  document.body.classList.toggle("fx", lv !== "av");
  document.body.classList.toggle("fx-bg", lv === "full");
}
applyFx();
function fxEnter(t) {
  if (pref("fx", "full") === "av") return;
  const sec = $("#" + t); if (!sec) return;
  sec.querySelectorAll(":scope > .grid > *, :scope > .card, :scope > .tiles > *, :scope > .quick > *").forEach((el, i) => el.style.setProperty("--i", Math.min(i, 10)));
  sec.classList.remove("fx-enter"); void sec.offsetWidth; sec.classList.add("fx-enter");
  setTimeout(() => sec.classList.remove("fx-enter"), 1100);
}
setTab = function (t) {                              // eslint-disable-line no-global-assign
  if (t !== "oversikt") dashEdit(false);
  if (detOpen) closeDetail();
  dashSetTab(t);
  fxEnter(t);
  if (t === "system") loadNotify();
  if (t === "kontroll") { loadScenes(); loadDiscord(); loadAv(); pushScenesToPhone(); }
  if (t === "system") loadPush();
  if (t === "mer") loadPanels();
  if (t === "spill") { loadGoals(); loadWeekly(); loadPlan(); loadShop(); loadSafe(); loadVr(); loadToday(); loadFriends(); }
  if (t === "oversikt") loadToday();
};
dashWire();
if (tab === "system") loadNotify();
if (tab === "kontroll") loadScenes();
