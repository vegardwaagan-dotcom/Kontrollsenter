// Kontrollsenter – Oversikt som du kan ordne selv (25):
//  • hold fingeren på en flis → tilpass-modus; dra flisene til nye plasser (de andre glir unna)
//  • S / M / L / XL i hjørnet endrer størrelsen
//  • trykk på en flis → ark med mye info om kategorien (graf, nøkkeltall, hva som bruker mest)
// Pluss varselvalg under Innstillinger (på telefonen og på PC-en).
"use strict";

const DASH_KEY = "ks_dash_v1";
const SIZES = { tile: ["s", "m", "l", "xl"], card: ["m", "xl"] };
const SZ_TXT = { s: "S", m: "M", l: "L", xl: "XL" };
const DETAIL = { cpu: "cpu", gpu: "gpu", mem: "mem", hot: "temps", watt: "watt", disk: "disk", net: "net", bat: "bat", temps: "temps", health: "health", info: "info" };
let dashEditing = false, dashDrag = null, dashJustPressed = 0;

const dashBox = () => $("#tiles");
const dashItems = () => Array.from(dashBox().children).filter((e) => e.dataset && e.dataset.k);
const vibe = (ms) => { try { if (KS && KS.vibrate) KS.vibrate(); else if (navigator.vibrate) navigator.vibrate(ms || 10); } catch (e) {} };
const calm = () => document.body.classList.contains("eco") || matchMedia("(prefers-reduced-motion: reduce)").matches;

function dashLoad() { try { return JSON.parse(localStorage.getItem(DASH_KEY)) || {}; } catch (e) { return {}; } }
function dashSave() {
  const d = { order: dashItems().map((e) => e.dataset.k), size: {} };
  dashItems().forEach((e) => (d.size[e.dataset.k] = e.dataset.sz));
  try { localStorage.setItem(DASH_KEY, JSON.stringify(d)); } catch (e) {}
}
const kindOf = (el) => (el.classList.contains("tile") ? "tile" : "card");

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
    flip(() => dashSetSize(el, list[(i + 1) % list.length]), el);
    dashSave(); vibe(8);
  };
  el.appendChild(b);
}

// FLIP: mål før, endre, mål etter – og la alle gli myk fra gammel til ny plass
function flip(change, popped) {
  const items = dashItems(), before = new Map(items.map((e) => [e, e.getBoundingClientRect()]));
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

function dashOrder() {
  const L = dashLoad(), order = L.order || [];
  const items = dashItems(), def = new Map(items.map((e, i) => [e, i]));
  const rank = (e) => { const i = order.indexOf(e.dataset.k); return i >= 0 ? i : 1000 + def.get(e); };
  items.slice().sort((a, b) => rank(a) - rank(b)).forEach((e) => dashBox().appendChild(e));
}

// app.js → renderOverview → hit med flisene (k, html)
function dashTiles(list) {
  const box = dashBox();
  let added = false;
  const keep = new Set(list.map((t) => t.k));
  list.forEach((t, i) => {
    let el = box.querySelector(`:scope > .tile[data-k="${t.k}"]`);
    if (!el) {
      el = document.createElement("div");
      el.className = "tile"; el.dataset.k = t.k;
      el.innerHTML = '<div class="tc"></div>';
      const firstCard = box.querySelector(":scope > .card");
      box.insertBefore(el, firstCard);
      dashPrep(el, i < 3 ? "m" : "s");
      added = true;
    }
    el.querySelector(".tc").innerHTML = t.html;
  });
  dashItems().forEach((e) => { if (e.classList.contains("tile") && !keep.has(e.dataset.k)) e.remove(); });
  if (added) dashOrder();
}

function dashEdit(on) {
  if (dashEditing === on) return;
  dashEditing = on;
  document.body.classList.toggle("dash-edit", on);
  dashBox().classList.toggle("editing", on);
  $("#oversikt").toggleAttribute("data-noswipe", on);
  $("#dash-bar").hidden = !on;
  if (on) vibe(15);
}

function dashReset() {
  try { localStorage.removeItem(DASH_KEY); } catch (e) {}
  flip(() => {
    const items = dashItems();
    const tiles = items.filter((e) => e.classList.contains("tile")), cards = items.filter((e) => !e.classList.contains("tile"));
    const KEYS = ["cpu", "gpu", "mem", "hot", "watt", "disk", "net", "bat"], CK = ["temps", "health", "info"];
    tiles.sort((a, b) => KEYS.indexOf(a.dataset.k) - KEYS.indexOf(b.dataset.k));
    cards.sort((a, b) => CK.indexOf(a.dataset.k) - CK.indexOf(b.dataset.k));
    tiles.forEach((e, i) => { dashBox().appendChild(e); dashSetSize(e, i < 3 ? "m" : "s"); });
    cards.forEach((e) => { dashBox().appendChild(e); dashSetSize(e, "xl"); });
  });
}

// ---------- dra ----------
function dragStart(el, ev) {
  const r = el.getBoundingClientRect();
  dashDrag = { el, id: ev.pointerId, gx: ev.clientX - r.left, gy: ev.clientY - r.top, x: ev.clientX, y: ev.clientY, last: 0, raf: 0 };
  el.classList.add("dragging");
  try { el.setPointerCapture(ev.pointerId); } catch (e) {}
  dragPlace();
  vibe(12);
  const loop = () => {                       // rull siden når du drar nær kanten
    if (!dashDrag) return;
    const y = dashDrag.y, h = innerHeight, edge = 90;
    const v = y < edge ? -(edge - y) / 5 : y > h - edge - 80 ? (y - (h - edge - 80)) / 5 : 0;
    if (v) { (document.scrollingElement || document.documentElement).scrollBy(0, v); dragPlace(); }
    dashDrag.raf = requestAnimationFrame(loop);
  };
  dashDrag.raf = requestAnimationFrame(loop);
}
function dragPlace() {
  const d = dashDrag; if (!d) return;
  d.el.style.transform = "";
  const r = d.el.getBoundingClientRect();
  d.el.style.transform = `translate(${d.x - d.gx - r.left}px, ${d.y - d.gy - r.top}px) scale(1.06) rotate(-1deg)`;
}
function dragMove(ev) {
  const d = dashDrag; if (!d || ev.pointerId !== d.id) return;
  d.x = ev.clientX; d.y = ev.clientY;
  dragPlace();
  if (Date.now() - d.last < 140) return;
  const over = dashItems().find((e) => {
    if (e === d.el) return false;
    const r = e.getBoundingClientRect();
    return d.x >= r.left && d.x <= r.right && d.y >= r.top && d.y <= r.bottom;
  });
  if (!over) return;
  const r = over.getBoundingClientRect();
  const after = r.width > r.height * 2.2 ? d.y > r.top + r.height / 2 : d.x > r.left + r.width / 2;
  const ref = after ? over.nextSibling : over;
  if (ref === d.el || (after ? over.nextSibling === d.el : over.previousSibling === d.el)) return;
  d.last = Date.now();
  flip(() => dashBox().insertBefore(d.el, ref));
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
  dashSave();
  vibe(10);
}

function dashWire() {
  const box = dashBox();
  if (!box || box.dataset.wired) return;
  box.dataset.wired = "1";
  dashItems().forEach((e) => dashPrep(e, "xl"));
  dashOrder();
  let lp = null;
  box.addEventListener("pointerdown", (ev) => {
    const el = ev.target.closest("#tiles > [data-k]");
    if (!el || ev.button > 0) return;
    if (dashEditing) {
      if (ev.target.closest("button, input, select, a")) return;
      ev.preventDefault();
      dragStart(el, ev);
      return;
    }
    const sx = ev.clientX, sy = ev.clientY;
    lp = { el, sx, sy, t: setTimeout(() => { dashEdit(true); dashJustPressed = Date.now(); dragStart(el, ev); lp = null; }, 480) };
  });
  box.addEventListener("pointermove", (ev) => {
    if (lp && Math.hypot(ev.clientX - lp.sx, ev.clientY - lp.sy) > 9) { clearTimeout(lp.t); lp = null; }
    dragMove(ev);
  });
  const up = (ev) => { if (lp) { clearTimeout(lp.t); lp = null; } dragEnd(ev); };
  box.addEventListener("pointerup", up);
  box.addEventListener("pointercancel", up);
  // når du drar, skal ikke siden rulle eller bytte fane
  box.addEventListener("touchmove", (ev) => { if (dashDrag) ev.preventDefault(); }, { passive: false });
  box.addEventListener("contextmenu", (ev) => ev.preventDefault());
  box.addEventListener("click", (ev) => {
    if (dashEditing || Date.now() - dashJustPressed < 600) return;
    if (ev.target.closest("button, a, input, select, summary, label")) return;
    const el = ev.target.closest("#tiles > [data-k]");
    if (el && DETAIL[el.dataset.k]) openDetail(DETAIL[el.dataset.k]);
  });
  const bar = document.createElement("div");
  bar.id = "dash-bar"; bar.className = "dash-bar"; bar.hidden = true;
  bar.innerHTML = `<span>Dra for å flytte<br><b>S M L</b> = størrelse</span>
    <button type="button" class="soft" id="dash-reset">Tilbakestill</button><button type="button" id="dash-done">Ferdig</button>`;
  document.body.appendChild(bar);
  $("#dash-done").onclick = () => dashEdit(false);
  $("#dash-reset").onclick = () => { dashReset(); vibe(10); };
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

// ---------- kobling ----------
const dashSetTab = setTab;
setTab = function (t) {                              // eslint-disable-line no-global-assign
  if (t !== "oversikt") dashEdit(false);
  if (detOpen) closeDetail();
  dashSetTab(t);
  if (t === "system") loadNotify();
};
dashWire();
if (tab === "system") loadNotify();
