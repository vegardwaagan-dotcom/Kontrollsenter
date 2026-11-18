// Kontrollsenter – ekstra kort i appen (tidslinje, strøm, nettverk, media, send til PC, skjermbilde, programmer,
// NAS, helse, spillmodus, avslåing, spilletid, CS2-historikk, WoW-mål, andreskjerm, tema, språk, roller, sikkerhet).
"use strict";
const pref = (k, d) => { try { const v = localStorage.getItem("ks_" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } };
const setPref = (k, v) => { try { localStorage.setItem("ks_" + k, JSON.stringify(v)); } catch (e) {} };
const X = (w, q) => api("/api/x/" + w + (q ? "?" + q : ""));
const hhmm = (t) => new Date(t * 1000).toLocaleString("nb-NO", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const hours = (s) => (s >= 3600 ? (s / 3600).toFixed(1) + " t" : Math.round(s / 60) + " min");

// ---------- sikkerhet: fingeravtrykk før farlige handlinger (13) ----------
const DANGER = new Set(["system", "kill", "fans", "timer", "msi", "gamemode"]);
function bioOk(reason) {
  if (!pref("bio", true) || !KS || !KS.authenticate) return Promise.resolve(true);
  return new Promise((res) => { window.ksBio = (ok) => res(!!ok); KS.authenticate(reason || "Bekreft"); });
}
const actPlain = act;
act = async function (body, quiet) {               // eslint-disable-line no-global-assign
  if (DANGER.has(body.a) && !(body.a === "fans" && body.value === "auto")) {
    if (!(await bioOk("Bekreft: " + (body.do || body.a)))) { toast("Avbrutt"); return; }
  }
  return actPlain(body, quiet);
};

// ---------- roller (26) ----------
async function loadMe() {
  try {
    const me = await X("me");
    const lim = me.role === "begrenset";
    document.body.classList.toggle("limited", lim);
    $("#role-badge").hidden = !lim;
    if (lim && tab === "kontroll") setTab("oversikt");
  } catch (e) {}
}

// ---------- tema, enkel visning og språk (24, 25) ----------
function applyLook() {
  const th = pref("theme", "auto");
  const lk = typeof curLook === "function" ? curLook() : "standard";
  const lt = (window.KS_THEMES || []).find((t) => t.k === lk);
  if (lk === "eget") document.documentElement.dataset.theme = "dark";
  else if (lt && lt.k !== "standard") document.documentElement.dataset.theme = lt.dark === false ? "light" : "dark";   // fargetema bestemmer
  else if (th === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = th;
  $$("#theme button").forEach((b) => b.classList.toggle("on", b.dataset.v === th));
  document.body.classList.toggle("simple", !!pref("simple", false));
  $("#simple").checked = !!pref("simple", false);
  $("#auto-second").checked = !!pref("auto_second", true);
  $("#bio").checked = !!pref("bio", true);
  $("#bio-note").textContent = KS && KS.authenticate ? "" : "Krever Android-appen (versjon 0.9 eller nyere).";
  applyLang();
}
$$("#theme button").forEach((b) => (b.onclick = () => { setPref("theme", b.dataset.v); applyLook(); if (KS && KS.setTheme) KS.setTheme(b.dataset.v); }));

// ---------- fargetema: samme temaer som på PC-en; deles med startskjermen og alle PC-ene via appen ----------
function curLook() {
  try { return (KS && KS.getLook && KS.getLook()) || localStorage.getItem("ks_look") || "standard"; } catch (e) { return "standard"; }
}
function setLook(k) {
  try { localStorage.setItem("ks_look", k); } catch (e) {}
  try { if (KS && KS.setLook) KS.setLook(k); } catch (e) {}
  const root = document.documentElement;
  root.classList.add("ks-fade");
  if (k === "standard") root.removeAttribute("data-ks"); else root.setAttribute("data-ks", k);
  setTimeout(() => root.classList.remove("ks-fade"), 700);
  if (typeof applyOwn === "function") applyOwn();
  applyLook();
  drawLooks();
}
function drawLooks() {
  const box = $("#ks-themes"); if (!box || !window.KS_THEMES) return;
  const cur = curLook();
  box.innerHTML = KS_THEMES.map((t) => `<button type="button" class="theme-sw${t.k === cur ? " on" : ""}" data-k="${esc(t.k)}">
    <span class="tp" style="background:radial-gradient(70% 90% at 10% 0%, ${t.a}cc, transparent 70%),radial-gradient(60% 80% at 100% 10%, ${t.b}bb, transparent 70%),radial-gradient(70% 60% at 50% 120%, ${t.c}88, transparent 70%),${t.bg}">
      <i class="tc" style="background:${t.card}"><b style="background:${t.fg}"></b><b style="background:${t.fg}"></b><b style="background:${t.fg}"></b></i>
      <i class="tg" style="background:linear-gradient(90deg, ${t.a}, ${t.b})"></i></span>
    <span class="tn">${esc(t.name)}</span><span class="td">${esc(t.desc)}</span></button>`).join("");
  box.querySelectorAll(".theme-sw").forEach((b) => (b.onclick = () => { setLook(b.dataset.k); if (KS && KS.vibrate) KS.vibrate(); }));
  const std = cur === "standard";
  $("#theme").hidden = !std; $("#theme-label").hidden = !std;
}
drawLooks();

// eget tema: to farger -> variablene settes rett på siden
function hexRgb(h) { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); }
function shade(h, f) { const c = hexRgb(h); return "#" + c.map((v) => Math.round(f < 0 ? v * (1 + f) : v + (255 - v) * f).toString(16).padStart(2, "0")).join(""); }
function mixHex(a, b) { const x = hexRgb(a), y = hexRgb(b); return "#" + x.map((v, i) => Math.round((v + y[i]) / 2).toString(16).padStart(2, "0")).join(""); }
function applyOwn() {
  const r = document.documentElement.style;
  const vars = ["--bg", "--bg2", "--card", "--card-solid", "--ga", "--gb", "--gc", "--acc", "--acc2", "--c1", "--grad", "--aurora"];
  if (curLook() !== "eget") { vars.forEach((v) => r.removeProperty(v)); return; }
  let c = {}; try { c = JSON.parse(localStorage.getItem("ks_own") || (KS && KS.getLookColors && KS.getLookColors()) || "{}"); } catch (e) {}
  const a = c.a || "#ff5e9c", b = c.b || "#5b8cff", m = mixHex(a, b), ra = hexRgb(a), rb = hexRgb(b);
  const set = { "--bg": shade(m, -0.9), "--bg2": shade(m, -0.86) + "e0", "--card-solid": shade(m, -0.8), "--card": `rgba(${hexRgb(shade(m, -0.8)).join(",")},.62)`,
    "--ga": a, "--gb": b, "--gc": shade(m, 0.35), "--acc": a, "--acc2": b, "--c1": a, "--grad": `linear-gradient(135deg, ${a} 0%, ${b} 100%)`,
    "--aurora": `radial-gradient(60% 45% at 8% -5%, rgba(${ra.join(",")},.34), transparent 70%), radial-gradient(50% 40% at 100% 0%, rgba(${rb.join(",")},.30), transparent 70%)` };
  Object.entries(set).forEach(([k, v]) => r.setProperty(k, v));
  document.documentElement.dataset.theme = "dark";
}
$("#look-own").onclick = () => {
  const c = JSON.stringify({ a: $("#look-a").value, b: $("#look-b").value });
  try { localStorage.setItem("ks_own", c); } catch (e) {}
  try { if (KS && KS.setLookColors) KS.setLookColors(c); } catch (e) {}
  setPref("look_time", false); $("#look-time").checked = false;
  setLook("eget");
};
applyOwn();
// tema etter tid på døgnet (myk overgang med fade)
const LOOK_TIMES = [[7 * 60, "arktis"], [18 * 60, "solnedgang"], [22 * 60 + 30, "nordlys"]];
function timeLook() {
  const d = new Date(), m = d.getHours() * 60 + d.getMinutes();
  let cur = LOOK_TIMES[LOOK_TIMES.length - 1][1];
  LOOK_TIMES.forEach(([t, k]) => { if (m >= t) cur = k; });
  return cur;
}
function lookTick() {
  if (!pref("look_time", false)) return;
  const k = timeLook();
  if (k !== curLook()) setLook(k);
}
$("#look-time").checked = !!pref("look_time", false);
$("#look-time").onchange = () => { setPref("look_time", $("#look-time").checked); lookTick(); };
setInterval(lookTick, 60000); lookTick();
// levende bakgrunn: aurora beveger seg; styrken følger CPU-belastningen
$("#look-live").checked = !!pref("look_live", false);
function applyLive() { document.body.classList.toggle("live-bg", !!pref("look_live", false)); }
$("#look-live").onchange = () => { setPref("look_live", $("#look-live").checked); applyLive(); };
applyLive();
setInterval(() => { if (last && last.cpu) document.documentElement.style.setProperty("--live", String(0.55 + Math.min(1, (last.cpu.load || 0) / 80) * 0.45)); }, 2000);
$("#simple").onchange = () => { setPref("simple", $("#simple").checked); applyLook(); };
$("#simple-off").onclick = () => { setPref("simple", false); applyLook(); toast("Enkel visning er av"); };
$("#auto-second").onchange = () => setPref("auto_second", $("#auto-second").checked);
$("#bio").onchange = () => setPref("bio", $("#bio").checked);

const EN = {
  "Hjem": "Home", "Styr": "Control", "Verktøy": "Tools", "Innstillinger": "Settings", "Statistikk": "Statistics",
  "Lås PC-en": "Lock PC", "Andreskjerm": "Second screen", "Vis alle": "Show all", "Hver vifte": "Each fan",
  "Volum per program": "Volume per app", "Grense per dag": "Daily limit", "Nytt mål": "New goal", "Start et spill": "Start a game",
  "Programmer som bruker nettet": "Programs using the network", "Åpne lenke": "Open link", "Kopier": "Copy", "Hent utklipp": "Get clipboard",
  "Glem paringen": "Forget pairing", "Åpne på PC-en": "Open on the PC", "Bruk": "Apply", "Lagre": "Save", "NAS": "NAS",
  "CS2 kamp for kamp": "CS2 match by match", "Ladegrense": "Charge limit", "Klipp": "Clips", "Lagre klipp": "Save clip",
  "Oversikt": "Overview", "Kontroll": "Control", "Historikk": "History", "Spill": "Games", "Mer": "More", "System": "System",
  "Temperaturer": "Temperatures", "Maskin": "Machine", "Helse": "Health", "Strømmodus": "Power mode", "Vifter": "Fans",
  "Lyd": "Sound", "RGB-lys": "RGB lighting", "Spill-overlay": "Game overlay", "Spillmodus": "Game mode",
  "Spillstatistikk": "Game statistics", "Spilletid": "Playtime", "CS2 – kamp for kamp": "CS2 – match by match",
  "WoW-mål": "WoW goals", "Tidslinje": "Timeline", "Strømkostnad": "Power cost", "Nettverk": "Network", "Media": "Media",
  "Send til PC-en": "Send to PC", "Skjermbilde": "Screenshot", "Programmer": "Programs",
  "NAS og sikkerhetskopi": "NAS and backup", "PC-en": "The PC", "Slå av senere": "Shut down later", "Utseende": "Appearance",
  "Sikkerhet": "Security", "Appen": "The app", "Denne enheten": "This device", "Temperatur": "Temperature",
  "Belastning": "Load", "Strøm": "Power", "Vis vinduet": "Show window", "Lås skjermen": "Lock screen",
  "Hvilemodus": "Sleep", "Start på nytt": "Restart", "Slå av": "Shut down", "Se etter oppdatering": "Check for update",
  "Glem paringen på denne enheten": "Forget pairing on this device", "Bruk farge": "Use colour", "Profil": "Profile", "Av": "Off",
  "Mål på nytt": "Measure again", "Oppdater": "Refresh", "Lagre grenser": "Save limits", "Lagre mål": "Save goal",
  "Sjekk på nytt": "Check again", "Åpne Systemsjekk på PC-en": "Open System check on the PC",
  "Åpne lenke på PC-en": "Open link on the PC", "Kopier til PC-en": "Copy to the PC",
  "Hent PC-ens utklippstavle": "Get the PC clipboard", "Ta skjermbilde av PC-en": "Take a screenshot of the PC",
  "Ta sikkerhetskopi av lagrede spill nå": "Back up saved games now", "Om 30 min": "In 30 min", "Om 1 time": "In 1 hour",
  "Om 2 timer": "In 2 hours", "Når nedlastingene er ferdige": "When downloads are finished", "Avbryt": "Cancel",
  "Start et spill på PC-en": "Start a game on the PC", "Spill litt, så dukker statistikken opp her.": "Play a bit and the statistics appear here.",
  "Familie": "Family", "Ranking": "Ranking", "Send": "Send", "🍽️ Middag!": "🍽️ Dinner!", "Belønning og leggetid": "Reward and bedtime",
  "+15 min": "+15 min", "+1 time": "+1 hour", "Lagre leggetid": "Save bedtime", "Ytelse per spill": "Performance per game",
  "Prestasjoner": "Achievements", "Måneden i tall": "The month in numbers", "Tilbud på ønskelisten": "Wishlist sales", "Sjekk nå": "Check now",
  "Knappebord": "Button board", "Endre": "Edit", "Ferdig": "Done", "Skjermen live": "Live screen", "Hjemmenett": "Home network",
  "Sikkerhetssjekk": "Security check", "Sjekk": "Check", "Oppstartsprogrammer": "Startup programs", "Hue-lys": "Hue lights",
  "Bruk farge": "Apply colour", "På": "On", "Koble til": "Connect", "Selvtest og feilrapport": "Self-test and error report",
  "Kjør selvtest": "Run self-test", "Send feilrapport til NAS-en": "Send error report to the NAS", "Gi navn": "Name",
  "Sikkerhetskopi av innstillingene": "Settings backup", "Ta kopi nå (NAS)": "Back up now (NAS)", "Gjenopprett valgt": "Restore selected",
  "Panelet": "Panel", "Batterier": "Batteries", "Installer": "Install", "Vis og skjul kort": "Show and hide cards", "Lukk": "Close", "Bli med": "Join",
};
const NB = {};
function applyLang() {
  const en = pref("lang", "nb") === "en";
  $$("#lang button").forEach((b) => b.classList.toggle("on", b.dataset.v === (en ? "en" : "nb")));
  document.documentElement.lang = en ? "en" : "nb";
  $$("h2, button, .label, #tabs span, .quick .ql, summary").forEach((el) => {
    if (el.children.length) return;
    const cur = el.textContent.trim();
    if (!NB[cur] && EN[cur]) NB[EN[cur]] = cur;
    const no = NB[cur] || cur;
    const target = en ? (EN[no] || no) : no;
    if (target !== cur) el.textContent = target;
  });
}
$$("#lang button").forEach((b) => (b.onclick = () => { setPref("lang", b.dataset.v); applyLang(); }));

// ---------- helse (22) ----------
async function loadHealth(force) {
  try {
    const h = await X("health", force ? "force=1" : "");
    $("#grade").textContent = h.grade; $("#grade").className = "grade " + h.grade;
    const bad = h.items.filter((i) => i.level === "warn" || i.level === "error");
    const info = h.items.filter((i) => i.level !== "ok" && !bad.includes(i));
    $("#health-sum").textContent = bad.length ? `${bad.length} ting bør sjekkes` : "Alt ser bra ut ✓";
    $("#health-items").innerHTML = bad.map((i) => `<p class="small"><b>${i.level === "error" ? "❌" : "⚠️"} ${esc(i.title)}</b><br><span class="dim">${esc(String(i.detail).slice(0, 200))}</span></p>`).join("")
      + (info.length ? `<details><summary>Til info (${info.length})</summary>${info.map((i) => `<p class="small"><b>${esc(i.title)}</b><br><span class="dim">${esc(String(i.detail).slice(0, 200))}</span></p>`).join("")}</details>` : "");
  } catch (e) { $("#health-sum").textContent = e.message; }
}
$("#health-refresh").onclick = () => { $("#health-sum").textContent = "Sjekker …"; loadHealth(true); };
$("#health-open").onclick = () => act({ a: "syscheck" });

// ---------- spillmodus (14) og avslåing (20) ----------
$("#gm-on").onchange = () => { holdFor("gm", 6000); act({ a: "gamemode", on: $("#gm-on").checked, color: $("#gm-color").value }); };
let timerPick = null;
function timerMark(t) {
  if (!t.at && !t.when_idle) timerPick = null;
  else if (t.when_idle) timerPick = "idle";
  $$("[data-timer]").forEach((x) => x.classList.toggle("on", x.dataset.timer !== "off" && x.dataset.timer === timerPick));
}
$$("[data-timer]").forEach((b) => (b.onclick = () => {
  const v = b.dataset.timer;
  timerPick = v === "off" ? null : v; holdFor("timer", 4000);
  $$("[data-timer]").forEach((x) => x.classList.toggle("on", x.dataset.timer !== "off" && x.dataset.timer === timerPick));
  act({ a: "timer", minutes: /^\d+$/.test(v) ? +v : null, when_idle: v === "idle" });
}));
// ---------- hurtigknapper på Hjem ----------
const PNAME = { "power-saver": "Strømsparing", balanced: "Balansert", performance: "Max ytelse" };
$$("#quick button").forEach((b) => (b.onclick = async () => {
  const q = b.dataset.q;
  if (q === "second") return openSecond();
  if (q === "lock") return act({ a: "system", do: "lock" });
  if (q === "clip") { const r = await act({ a: "clip" }); setTimeout(loadClips, 5000); return r; }
  if (q === "gamemode") { const on = !b.classList.contains("on"); b.classList.toggle("on", on); holdFor("gm", 6000);
    return act({ a: "gamemode", on, color: $("#gm-color").value }); }
  if (q === "power" && last && last.power) {
    const keys = last.power.modes.map((m) => m[0]); const nxt = keys[(keys.indexOf(last.power.active) + 1) % keys.length];
    $("#q-power").textContent = PNAME[nxt] || nxt; holdFor("power"); return act({ a: "power", mode: nxt });
  }
}));
$("#temps-more").onclick = () => { const c = $("#temps").classList.toggle("collapsed"); $("#temps-more").textContent = c ? "Vis alle" : "Vis færre"; };

function renderExtraStatus(s) {
  if (!held("gm")) { $("#quick [data-q=gamemode]").classList.toggle("on", !!s.gamemode); $("#q-gm").textContent = s.gamemode ? "På" : "Av"; }
  if (s.power && !held("power")) $("#q-power").textContent = PNAME[s.power.active] || s.power.active || "–";
  $("#quick [data-q=power]").hidden = !s.power;
  $("#temps-more").hidden = (s.temps || []).length <= 8;
  if (!held("gm")) $("#gm-on").checked = !!s.gamemode;
  const t = s.timer || {};
  if (!held("timer")) timerMark(t);
  if (typeof deckState === "function") deckState(s);
  $("#timer-state").textContent = t.at ? "PC-en slås av kl. " + new Date(t.at * 1000).toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" })
    : t.when_idle ? `Slås av når nettet har vært stille i 5 min (stille nå: ${Math.round((t.idle_for || 0) / 60)} min)` : "Ingen planlagt avslåing";
  // andreskjerm: start automatisk når et spill starter
  const playing = s.game || (s.cs2 && s.cs2.map);
  if (playing && !lastPlaying && pref("auto_second", true)) openSecond();
  lastPlaying = !!playing;
  if (!$("#second").hidden) renderSecond(s);
}
let lastPlaying = false;

// ---------- andreskjerm (5) ----------
function openSecond() { $("#second").hidden = false; if (KS && KS.keepAwake) KS.keepAwake(true); if (last) renderSecond(last); }
$("#btn-second").onclick = openSecond;
$("#second-close").onclick = () => { $("#second").hidden = true; if (KS && KS.keepAwake) KS.keepAwake(false); };
function renderSecond(s) {
  const c = s.cs2, g = [];
  const big = (n, v, cls) => `<div class="big"><div class="n">${esc(n)}</div><div class="v ${cls || ""}">${esc(v)}</div></div>`;
  $("#second-game").textContent = c ? `CS2 · ${c.map} · CT ${c.ct ?? 0} – ${c.t ?? 0} T` : (s.game ? "🎮 " + s.game : s.name);
  if (c && c.mine) g.push(big("K / D / A", `${c.kills}/${c.deaths}/${c.assists}`), big("Headshot", c.hs_pct || "–"), big("ADR", c.adr ?? "–"),
    big("Liv", c.health ?? "–", c.health < 30 ? "t-bad" : ""), big("Penger", "$" + (c.money ?? 0)));
  const ct = s.cpu && s.cpu.temp, gt = s.gpu && s.gpu.temp;
  g.push(big("CPU", ct != null ? Math.round(ct) + "°" : "–", ct >= 85 ? "t-bad" : ct >= 70 ? "t-warn" : ""),
    big("GPU", gt != null ? Math.round(gt) + "°" : "–", gt >= 85 ? "t-bad" : gt >= 70 ? "t-warn" : ""),
    big("CPU-last", Math.round((s.cpu && s.cpu.load) || 0) + " %"), big("GPU-last", Math.round((s.gpu && s.gpu.util) || 0) + " %"),
    big("Strøm", (s.watts || 0) + " W"), big("Klokka", new Date().toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" })));
  $("#second-grid").innerHTML = g.join("");
}

// ---------- tidslinje og varsler mens appen er åpen (21, 1) ----------
let evSince = pref("ev_since", 0), evFirst = true;
async function loadEvents() {
  try {
    const r = await X("events");
    const evs = r.events.slice().reverse();
    $("#events").innerHTML = evs.map((e) => `<div class="ev ${esc(e.level)}"><span class="t">${hhmm(e.t)}</span><div><b>${esc(e.title)}</b>${e.body ? `<div class="dim small">${esc(e.body)}</div>` : ""}</div></div>`).join("")
      || '<p class="dim">Ingen hendelser ennå.</p>';
    const fresh = r.events.filter((e) => e.t > evSince && e.level !== "info");
    if (!evFirst && fresh.length) toast(fresh[fresh.length - 1].title);
    if (r.events.length) { evSince = Math.max(evSince, r.events[r.events.length - 1].t); setPref("ev_since", evSince); }
    evFirst = false;
  } catch (e) {}
}

// ---------- strøm (19) ----------
async function loadEnergy() {
  try {
    const e = await X("energy");
    $("#energy-sum").innerHTML = kv([["I dag", e.today_kr.toFixed(2) + " kr"], ["Siste 7 dager", e.week_kr.toFixed(2) + " kr"],
      ["Denne måneden", e.month_kr.toFixed(2) + " kr"], ["Strømpris", e.price.toFixed(2) + " kr/kWh"]].map(([a, b]) => [a, b])).replace(/^<div class="kvgrid">|<\/div>$/g, "");
    bars($("#en-chart"), e.days.slice(-14).map((d) => [d.day.slice(8) + ".", d.kr]), "kr");
  } catch (err) { $("#energy-sum").textContent = err.message; }
}
function bars(cv, data, unit) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight || 200;
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement), max = Math.max(0.0001, ...data.map((d) => d[1]));
  const bw = (w - 10) / Math.max(1, data.length);
  g.font = "11px system-ui"; g.fillStyle = css.getPropertyValue("--dim");
  data.forEach(([lab, v], i) => {
    const bh = (h - 34) * (v / max), x = 5 + i * bw;
    g.fillStyle = css.getPropertyValue("--c1"); g.fillRect(x + 3, h - 18 - bh, bw - 6, bh);
    g.fillStyle = css.getPropertyValue("--dim"); g.fillText(lab, x + 3, h - 4);
    if (bw > 34) g.fillText((v >= 10 ? Math.round(v) : v.toFixed(1)) + (unit ? "" : ""), x + 3, h - 22 - bh);
  });
}

// ---------- nettverk (16) ----------
async function loadNetwork() {
  $("#net-ping").innerHTML = '<p class="dim">Måler …</p>';
  try {
    const n = await X("network");
    $("#net-ping").innerHTML = n.ping.map((p) => `<div><b>${esc(p.name)}</b><span class="${p.ms == null ? "t-bad" : p.ms > 80 ? "t-warn" : "t-ok"}">${p.ms == null ? "svarer ikke" : p.ms + " ms"}${p.loss ? ` · ${p.loss} % tap` : ""}</span></div>`).join("");
    $("#net-progs").innerHTML = n.programs.map((p) => `<div><b>${esc(p.name)}</b><span>${p.count} forb.</span></div>`).join("") || '<p class="dim">Ingen</p>';
  } catch (e) { $("#net-ping").textContent = e.message; }
}
$("#net-refresh").onclick = loadNetwork;

// ---------- media og volum per program (9) ----------
async function loadMedia() {
  try {
    const m = await X("media");
    const p = m.players.find((x) => x.status === "Playing") || m.players[0];
    $("#media-now").textContent = p ? `${p.status === "Playing" ? "▶" : "⏸"} ${p.title || p.app}${p.artist ? " – " + p.artist : ""}` : (m.keys ? "Medietastene sendes til PC-en" : "Ingen mediespiller kjører");
    $("#app-vols").innerHTML = m.apps.map((a) => `<div class="fan" data-id="${esc(a.id)}"><div class="h"><span>${esc(a.name)}</span><span class="dim num">${a.volume} %</span></div>
      <div class="r"><input type="range" min="0" max="100" value="${Math.min(100, a.volume)}"></div></div>`).join("") || '<p class="dim">Ingen programmer spiller lyd nå</p>';
    $$("#app-vols .fan").forEach((el) => {
      const sl = el.querySelector("input");
      sl.onchange = () => act({ a: "appvolume", id: el.dataset.id, volume: +sl.value }, true);
      sl.oninput = () => (el.querySelector(".num").textContent = sl.value + " %");
    });
  } catch (e) { $("#media-now").textContent = e.message; }
}
$$("[data-media]").forEach((b) => (b.onclick = async () => { await act({ a: "media", cmd: b.dataset.media }, true); setTimeout(loadMedia, 600); }));

// ---------- send til PC (10) ----------
$("#send-open").onclick = () => { const t = $("#send-text").value.trim(); if (t) act({ a: "open_url", url: /^https?:\/\//.test(t) ? t : "https://" + t }); };
$("#send-clip").onclick = () => { const t = $("#send-text").value; if (t) act({ a: "clipboard", text: t }); };
$("#get-clip").onclick = async () => {
  try { const r = await X("clipboard"); $("#clip-out").textContent = r.text || "(tom)"; if (r.text && navigator.clipboard) navigator.clipboard.writeText(r.text).catch(() => {}); }
  catch (e) { $("#clip-out").textContent = e.message; }
};
window.ksShared = (t) => { $("#send-text").value = t; setTab("mer"); toast("Trykk «Åpne lenke» eller «Kopier» for å sende til PC-en"); };
if (KS && KS.sharedText) { const st = KS.sharedText(); if (st) setTimeout(() => window.ksShared(st), 400); }
if (KS && KS.setActive) setTimeout(() => KS.setActive(pcName || ($("#pc-name").textContent || ""), location.origin), 1500);

// ---------- skjermbilde (8) ----------
$("#shot-go").onclick = async () => {
  $("#shot-go").disabled = true; $("#shot-go").textContent = "Tar skjermbilde …";
  try {
    const r = await fetch("/api/x/screenshot", { headers: { Authorization: "Bearer " + token } });
    if (!r.ok) throw new Error((await r.json()).error || r.statusText);
    const url = URL.createObjectURL(await r.blob());
    $("#shot-img").src = url; $("#shot-img").hidden = false;
  } catch (e) { toast("Skjermbilde: " + e.message); }
  $("#shot-go").disabled = false; $("#shot-go").textContent = "Ta skjermbilde av PC-en";
};

// ---------- programmer (11) ----------
async function loadProcs() {
  try {
    const r = await X("processes");
    $("#procs").innerHTML = r.processes.map((p) => `<div class="proc"><span>${esc(p.name)}</span><span class="dim num">${p.cpu} %</span>
      <span class="dim num">${fmtB(p.mem)}</span>${p.protected ? "" : `<button class="danger" data-kill="${esc(p.name)}">Avslutt</button>`}</div>`).join("");
    $$("[data-kill]").forEach((b) => (b.onclick = async () => {
      if (!(await confirmDlg(`Avslutte ${b.dataset.kill}? Ulagret arbeid i programmet går tapt.`))) return;
      await act({ a: "kill", name: b.dataset.kill }); setTimeout(loadProcs, 1500);
    }));
  } catch (e) { $("#procs").textContent = e.message; }
}
$("#procs-refresh").onclick = loadProcs;

// ---------- NAS og backup (12) ----------
async function loadNas() {
  try {
    const n = await X("nas");
    const rows = [["NAS-en", n.online ? "svarer ✓" : "svarer ikke"]];
    if (n.total) rows.push(["Ledig", fmtB(n.free) + " av " + fmtB(n.total)]);
    rows.push(["Siste sikkerhetskopi", n.backup_last ? hhmm(n.backup_last) : "aldri"], ["Automatisk", n.backup_auto ? "på" : "av"]);
    $("#nas").innerHTML = rows.map(([a, b]) => `<div><b>${esc(a)}</b><span>${esc(b)}</span></div>`).join("");
  } catch (e) { $("#nas").textContent = e.message; }
}
$("#backup-go").onclick = () => act({ a: "backup" });

// ---------- spilletid og grenser (7) ----------
async function loadPlaytime() {
  try {
    const p = await X("playtime");
    bars($("#pt-chart"), p.days.slice(-14).map((d) => [d.day.slice(8) + ".", d.total / 3600]), "t");
    $("#pt-week").innerHTML = p.week.slice(0, 8).map(([g, s]) => `<div><b>${esc(g)}</b><span>${hours(s)}</span></div>`).join("") || '<p class="dim">Ingen spilletid de siste 7 dagene</p>';
    $("#lim-on").checked = p.limits.enabled; $("#lim-wd").value = p.limits.weekday; $("#lim-we").value = p.limits.weekend;
  } catch (e) {}
}
$("#lim-save").onclick = () => act({ a: "playlimits", enabled: $("#lim-on").checked, weekday: +$("#lim-wd").value, weekend: +$("#lim-we").value });

// ---------- CS2-historikk og kart (6, 18) ----------
async function loadCs2() {
  try {
    const h = await X("cs2");
    const rows = h.matches.map((m, i) => [i, m.deaths ? m.kills / m.deaths : m.kills, m.kills ? (100 * (m.hs || 0)) / m.kills : 0]);
    $("#cs-chart").hidden = rows.length < 2;
    if (rows.length > 1) {
      const norm = rows.map((r) => [r[0], r[1] * 25, r[2]]);                 // K/D ×25 for samme skala som %
      chart($("#cs-chart"), norm, [1, 2], ["--c1", "--c2"], 100);
    }
    $("#cs-maps").innerHTML = h.maps.length ? `<div class="label">Per kart</div>` + kv(h.maps.map((m) => [m.map, `${m.played} kamper · ${m.winrate ?? "–"} % seier · K/D ${m.kd ?? "–"}`]))
      : '<p class="dim small">Kampene lagres når de er ferdige (CS2 må startes på nytt én gang etter at Kontrollsenter la inn oppsettet).</p>';
  } catch (e) {}
}

// ---------- WoW-mål (17) ----------
let wowChars = [];
async function loadGoals() {
  try {
    const [g, st] = await Promise.all([X("wowgoals"), api("/api/gamestats")]);
    wowChars = st.wow || [];
    $("#goal-char").innerHTML = wowChars.map((c, i) => `<option value="${i}">${esc(c.title)}</option>`).join("") || "<option>Ingen WoW-karakterer ennå</option>";
    $("#wow-goals").innerHTML = g.goals.map((x) => {
      const by = x.by ? new Date(x.by * 1000).toLocaleDateString("nb-NO") : "–";
      const est = x.est_play_s != null ? hours(x.est_play_s) : "ukjent (trenger noen leveler først)";
      const per = x.per_day_s != null ? hours(x.per_day_s) + " per dag" : "";
      return `<div class="kvgrid"><div><b>${esc(String(x.key).split("-").pop())}</b><span>level ${x.target} innen ${by}</span></div>
        <div><b>Leveler igjen</b><span>${x.levels_left}</span></div><div><b>Anslått spilletid</b><span>${est}</span></div>
        ${per ? `<div><b>Trenger</b><span>${per}</span></div>` : ""}</div>`;
    }).join("") || '<p class="dim">Ingen mål ennå.</p>';
  } catch (e) {}
}
$("#goal-save").onclick = () => {
  const c = wowChars[+$("#goal-char").value];
  if (!c) return;
  const name = c.title.split(" – ")[0], realm = c.sub.split(" · ")[0];
  const by = $("#goal-by").value ? new Date($("#goal-by").value).getTime() / 1000 : null;
  act({ a: "wowgoal", key: `${realm}-${name}`, level: +$("#goal-level").value || null, by }).then(loadGoals);
};

// ---------- klipp: opptak i bakgrunnen ----------
const lenName = (s) => (s < 60 ? s + " s" : s / 60 + " min");
async function loadClips() {
  try {
    const c = await X("clips");
    $("#clip-on").checked = !!c.enabled; $("#clip-og").checked = !!c.only_games;
    $("#clip-linux").hidden = c.os === "windows";
    $("#clip-len").innerHTML = (c.lengths || []).map((s) => `<button data-s="${s}" class="${s === c.length ? "on" : ""}">${lenName(s)}</button>`).join("");
    $$("#clip-len button").forEach((b) => (b.onclick = () => act({ a: "clipcfg", length: +b.dataset.s }, true).then(loadClips)));
    $("#q-clip").textContent = c.os === "windows" ? (c.engine === "medal" ? "Medal" : "Game Bar") : "Siste " + lenName(c.length);
    const KEYS = ["F8", "F9", "F10", "F12", "Alt+F10", "Ctrl+Shift+S", "Print"];
    const cur = c.hotkey || "F8";
    $("#clip-keys").innerHTML = [...new Set([cur, ...KEYS])].map((k) => `<button class="${k === cur ? "on" : ""}" data-key="${esc(k)}">${esc(k)}</button>`).join("");
    $$("[data-key]").forEach((b) => (b.onclick = () => act({ a: "clipkey", key: b.dataset.key }).then(() => setTimeout(loadClips, 700))));
    $("#clip-key-status").textContent = c.hotkey_testing ? "Trykk tasten på PC-en nå …"
      : c.hotkey_tested && Date.now() / 1000 - c.hotkey_tested < 60 ? "✅ Tasten virker!"
      : c.hotkey_error ? "⚠️ " + c.hotkey_error : c.enabled ? (c.hotkey_ok ? "Registrert" : "Ikke registrert ennå") : "";
    $("#clip-status").textContent = !c.enabled ? "av" : c.os === "linux" && !c.installed ? "mangler opptaksprogram (installer på PC-en)"
      : c.running ? "🔴 tar opp" : c.only_games ? "venter på spill" : "starter …";
    if (false) $("#clip-list").innerHTML = c.clips.slice(0, 12).map((x) => `<div class="clip"><div><b>${esc(x.name)}</b><span class="dim small">${fmtB(x.size)} · ${hhmm(x.t)}</span></div>
      <button class="soft" data-play="${esc(x.name)}">▶</button><button class="danger" data-del="${esc(x.name)}">Slett</button></div>`).join("")
      || '<p class="dim small">Ingen klipp ennå. Slå på opptak, spill litt og trykk F8.</p>';
    if (false) $$("[data-play]").forEach((b) => (b.onclick = () => {
      const v = $("#clip-video"); v.hidden = false;
      v.src = `/api/clipfile?name=${encodeURIComponent(b.dataset.play)}&k=${encodeURIComponent(token)}`; v.play().catch(() => {});
      v.scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    $$("[data-del]").forEach((b) => (b.onclick = async () => {
      if (await confirmDlg(`Slette ${b.dataset.del}?`)) { await act({ a: "clipdel", name: b.dataset.del }); loadClips(); }
    }));
  } catch (e) { $("#clip-status").textContent = e.message; }
}
$("#clip-on").onchange = () => act({ a: "clipcfg", enabled: $("#clip-on").checked }, true).then(loadClips);
$("#clip-og").onchange = () => act({ a: "clipcfg", only_games: $("#clip-og").checked }, true).then(loadClips);
$("#clip-test").onclick = async () => {
  await act({ a: "cliptest" });
  let n = 0; const t = setInterval(async () => { n++; await loadClips(); if (n > 16 || /virker/.test($("#clip-key-status").textContent)) clearInterval(t); }, 1000);
};
$("#clip-save").onclick = async () => { await act({ a: "clip" }); setTimeout(() => { loadClips(); loadClips2(); }, 6000); };

// ---------- klipp: galleri, redigering, deling, montasje, statistikk ----------
let clipData = null, curClip = null, picked = new Set();
const enc = encodeURIComponent;
const fileUrl = (n, pc) => `/api/clipfile?name=${enc(n)}&k=${enc(token)}` + (pc ? `&pc=${enc(pc)}` : "");
// reserve-bilde når PC-en ikke kan lage miniatyrbilde (f.eks. Windows uten ffmpeg)
window.NOTHUMB = (icon) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2a3570"/><stop offset="1" stop-color="#402a7a"/></linearGradient></defs><rect width="160" height="90" fill="url(#g)"/><text x="80" y="56" font-size="34" text-anchor="middle">${icon}</text></svg>`;
const SHARE_IC = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg>`;
const thumbUrl = (n) => `/api/clipthumb?name=${enc(n)}&k=${enc(token)}`;
async function loadClips2() {
  try {
    const c = clipData = await X("clips");
    const games = [...new Set(c.clips.map((x) => x.game))];
    const f = $("#clip-filter").value;
    $("#clip-filter").innerHTML = `<option value="">Alle spill (${c.clips.length})</option><option value="fav">★ Favoritter</option>`
      + games.map((g) => `<option ${g === f ? "selected" : ""}>${esc(g)}</option>`).join("");
    if (f === "fav") $("#clip-filter").value = "fav";
    renderClipGrid();
    $("#clip-images").innerHTML = c.images.map((x) => `<div class="ct"><img loading="lazy" src="${thumbUrl(x.name)}" data-img="${esc(x.name)}" onerror="this.onerror=null;this.classList.add('nothumb');this.src='data:image/svg+xml,'+encodeURIComponent(NOTHUMB('🖼️'))"><div class="cb"><b>${esc(x.name)}</b></div>
      <div class="ca"><button data-share="${esc(x.name)}" aria-label="Del">${SHARE_IC}</button><button data-dl="${esc(x.name)}">⬇</button><button data-cdel="${esc(x.name)}">🗑</button></div></div>`).join("") || '<p class="dim small">Ingen skjermbilder ennå.</p>';
    $$("[data-img]").forEach((im) => (im.onclick = () => window.open(fileUrl(im.dataset.img))));
    wireClipButtons();
    const jobs = Object.values(c.jobs || {}).filter((j) => Date.now() / 1000 - j.t < 900);
    $("#clip-jobs").textContent = jobs.map((j) => `${j.state === "kjører" ? "⏳" : j.state === "ferdig" ? "✅" : "❌"} ${j.title}${j.error ? " – " + j.error : ""}`).join(" · ");
    if (jobs.some((j) => j.state === "kjører")) setTimeout(loadClips2, 3000);
    $("#clip-make").hidden = !c.ffmpeg;
    for (const k of ["quality", "fps", "keep_days", "max_gb", "nas_days", "watermark"]) if ($("#o-" + k) && document.activeElement !== $("#o-" + k)) $("#o-" + k).value = c[k] ?? "";
    for (const k of ["mic", "webcam", "auto_cs2", "cs2_match", "wow_log", "idle_pause", "controller", "share_nas"]) $("#o-" + k).checked = !!c[k];
    $("#o-tracks").checked = c.tracks === "separate";
  } catch (e) {}
}
function renderClipGrid() {
  const f = $("#clip-filter").value;
  const list = clipData.clips.filter((x) => !f || (f === "fav" ? x.fav : x.game === f));
  $("#clip-list").innerHTML = list.map((x) => {
    const cs = (x.meta && x.meta.cs2) || {};
    const tag = x.kind === "highlight" ? "🏆 " + (x.meta && x.meta.label || "Høydepunkt") : x.kind === "boss" ? "🐉 Boss" : x.kind === "bookmark" ? "🔖" : "";
    return `<div class="ct ${picked.has(x.name) ? "picked" : ""}" data-n="${esc(x.name)}"><button class="sel-tick" data-pick="${esc(x.name)}">✓</button>
      ${tag ? `<span class="badge2">${esc(tag)}</span>` : ""}<img loading="lazy" src="${thumbUrl(x.name)}" data-play="${esc(x.name)}" onerror="this.onerror=null;this.classList.add('nothumb');this.src='data:image/svg+xml,'+encodeURIComponent(NOTHUMB('🎬'))">
      <div class="cb"><b>${esc(x.name)}</b><span class="dim">${fmtB(x.size)} · ${hhmm(x.t)}${cs.map ? ` · ${esc(cs.map)} ${cs.kills ?? ""}/${cs.deaths ?? ""}` : ""}</span></div>
      <div class="ca"><button data-fav="${esc(x.name)}" data-on="${x.fav ? 1 : 0}">${x.fav ? "★" : "☆"}</button><button data-share="${esc(x.name)}" aria-label="Del">${SHARE_IC}</button><button data-dl="${esc(x.name)}">⬇</button><button data-cdel="${esc(x.name)}">🗑</button></div></div>`;
  }).join("") || '<p class="dim small">Ingen klipp ennå. Slå på opptak, spill litt og trykk hurtigtasten.</p>';
  wireClipButtons();
}
function wireClipButtons() {
  $$("[data-play]").forEach((b) => (b.onclick = () => playClip(b.dataset.play)));
  $$("[data-fav]").forEach((b) => (b.onclick = () => act({ a: "clipfav", name: b.dataset.fav, on: b.dataset.on !== "1" }, true).then(loadClips2)));
  $$("[data-cdel]").forEach((b) => (b.onclick = async () => { if (await confirmDlg(`Slette ${b.dataset.cdel}?`)) { await act({ a: "clipdel", name: b.dataset.cdel }); loadClips2(); } }));
  $$("[data-dl]").forEach((b) => (b.onclick = () => download(b.dataset.dl)));
  $$("[data-share]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); shareFile(b.dataset.share); }));
  $$("[data-pick]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); const n = b.dataset.pick; picked.has(n) ? picked.delete(n) : picked.add(n); renderClipGrid(); }));
}
function playClip(name, pc) {
  curClip = { name, pc };
  $("#clip-player").hidden = false;
  const v = $("#clip-video"); v.src = fileUrl(name, pc); v.play().catch(() => {});
  const x = clipData && clipData.clips.find((y) => y.name === name);
  const cs = x && x.meta && x.meta.cs2;
  $("#clip-meta").textContent = name + (cs ? ` — ${cs.map} · runde ${cs.round} · CT ${cs.ct}–${cs.t} T · ${cs.kills}/${cs.deaths}/${cs.assists} · HS ${cs.hs_pct || "–"}` : "");
  v.onloadedmetadata = () => { for (const id of ["trim-a", "trim-b"]) $("#" + id).max = v.duration.toFixed(1); $("#trim-b").value = v.duration.toFixed(1); $("#trim-a").value = 0; trimLabels(); };
  $("#clip-player").scrollIntoView({ behavior: "smooth", block: "start" });
}
function trimLabels() { $("#trim-av").textContent = (+$("#trim-a").value).toFixed(1) + " s"; $("#trim-bv").textContent = (+$("#trim-b").value).toFixed(1) + " s"; }
$("#trim-a").oninput = () => { trimLabels(); $("#clip-video").currentTime = +$("#trim-a").value; };
$("#trim-b").oninput = () => { trimLabels(); $("#clip-video").currentTime = +$("#trim-b").value; };
$("#trim-go").onclick = () => curClip && act({ a: "clipexport", name: curClip.name, kind: "trim", start: +$("#trim-a").value, end: +$("#trim-b").value }).then(() => setTimeout(loadClips2, 1500));
$$("[data-mk]").forEach((b) => (b.onclick = () => curClip && act({ a: "clipexport", name: curClip.name, kind: b.dataset.mk }).then(() => setTimeout(loadClips2, 1500))));
function download(name, pc) {
  const url = location.origin + fileUrl(name, pc);
  if (KS && KS.download) { KS.download(url, name); toast("Lastes ned til telefonen – del den fra Varsler eller Galleri"); }
  else window.open(url);
}
$("#clip-dl").onclick = () => curClip && download(curClip.name, curClip.pc);
$("#clip-share").onclick = () => curClip && shareFile(curClip.name, curClip.pc);
// del et skjermbilde/klipp: Android-appen henter filen og åpner delemenyen; i nettleser brukes Web Share
async function shareFile(name, pc) {
  const url = location.origin + fileUrl(name, pc);
  if (KS && KS.share) { toast("Henter " + name + " fra PC-en …"); KS.share(url, name); return; }
  try {
    if (navigator.canShare) {
      toast("Henter " + name + " …");
      const blob = await (await fetch(url)).blob();
      const file = new File([blob], name, { type: blob.type || (/\.(png|jpe?g|webp)$/i.test(name) ? "image/jpeg" : "video/mp4") });
      if (navigator.canShare({ files: [file] })) { await navigator.share({ files: [file], title: name }); return; }
    }
  } catch (e) { if (e.name === "AbortError") return; }
  if (KS && KS.download) { download(name, pc); toast("Denne versjonen av appen kan ikke dele – lastet ned i stedet. Oppdater appen for deling."); }
  else window.open(url);
}
window.ksShareReady = () => {};
$("#clip-link").onclick = async () => {
  if (!curClip) return;
  const r = await api("/api/action", { a: "clipshare", name: curClip.name, pc: curClip.pc || "" });
  const link = location.origin + r.msg;
  try { await navigator.clipboard.writeText(link); toast("Lenken er kopiert – virker i 24 timer på hjemmenettet/Tailscale"); } catch (e) { $("#clip-meta").textContent = link; }
};
$("#clip-shot").onclick = () => act({ a: "clipshot" }).then(() => setTimeout(loadClips2, 2500));
$("#clip-rec").onclick = () => act({ a: "cliprecord" });
$("#clip-weekly").onclick = () => act({ a: "clipweekly" }).then(() => setTimeout(loadClips2, 2000));
$("#clip-filter").onchange = renderClipGrid;
$("#mont-go").onclick = () => {
  if (!picked.size) return toast("Trykk ✓ på klippene du vil ha med først");
  act({ a: "clipmontage", names: [...picked], music: $("#mont-music").value || null, title: $("#mont-title").value || "Montasje" })
    .then(() => { picked.clear(); setTimeout(loadClips2, 2000); });
};
async function loadClipExtras() {
  try {
    const m = await X("music");
    $("#mont-music").innerHTML = `<option value="">Uten musikk (spillets lyd)</option>` + m.music.map((x) => `<option>${esc(x)}</option>`).join("");
  } catch (e) {}
  try {
    const s = await X("clipstats");
    const rows = [["Klipp", s.count], ["Favoritter", s.favs], ["Plass", fmtB(s.size)]]
      .concat(s.best_week ? [["Beste uke", `${s.best_week[0]} (${s.best_week[1]})`]] : [])
      .concat(s.per_game.map(([g, n]) => [g, n + " klipp"])).concat(s.maps.map(([mp, n]) => ["Kart " + mp, n]));
    $("#clip-stats").innerHTML = rows.map(([a, b]) => `<div><b>${esc(a)}</b><span>${esc(b)}</span></div>`).join("");
    if (s.on_this_day.length) toast(`📅 Denne dagen i fjor: ${s.on_this_day[0].name}`);
  } catch (e) {}
  try {
    const n = await X("nasclips");
    $("#clip-nas").innerHTML = n.clips.map((x) => `<div class="clip"><div><b>${esc(x.name)}</b><span class="dim small">${esc(x.pc)} · ${fmtB(x.size)}</span></div>
      <button class="soft" data-nplay="${esc(x.name)}" data-pc="${esc(x.pc)}">▶</button></div>`).join("") || '<p class="dim small">Ingen delte klipp på NAS-en.</p>';
    $$("[data-nplay]").forEach((b) => (b.onclick = () => playClip(b.dataset.nplay, b.dataset.pc)));
  } catch (e) {}
}
const optSave = (k, v) => act({ a: "clipopts", [k]: v }, true);
for (const k of ["quality"]) $("#o-" + k).onchange = () => optSave(k, $("#o-" + k).value);
$("#o-fps").onchange = () => optSave("fps", +$("#o-fps").value);
for (const k of ["mic", "webcam", "auto_cs2", "cs2_match", "wow_log", "idle_pause", "controller", "share_nas"]) $("#o-" + k).onchange = () => optSave(k, $("#o-" + k).checked);
$("#o-tracks").onchange = () => optSave("tracks", $("#o-tracks").checked ? "separate" : "mixed");
for (const k of ["keep_days", "max_gb", "nas_days"]) $("#o-" + k).onchange = () => optSave(k, +$("#o-" + k).value || 0);
$("#o-watermark").onchange = () => optSave("watermark", $("#o-watermark").value);

// ---------- kobling til fanene ----------
const baseSetTab = setTab;
setTab = function (t) {                              // eslint-disable-line no-global-assign
  baseSetTab(t);
  if (t === "mer") { loadEvents(); loadEnergy(); loadNetwork(); loadProcs(); loadNas(); }
  if (t === "kontroll") loadMedia();
  if (t === "spill") { loadClips(); loadClips2(); loadClipExtras(); loadPlaytime(); loadCs2(); loadGoals(); }
  if (t === "oversikt") X("clips").then((c) => { $("#q-clip").textContent = c.os === "windows" ? (c.engine === "medal" ? "Medal" : "Game Bar") : "Siste " + lenName(c.length); }).catch(() => {});
  if (t === "oversikt") loadHealth(false);
  applyLang();
};
$$("#tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
const basePoll = poll;
poll = async function () {                           // eslint-disable-line no-global-assign
  await basePoll();
  if (last) renderExtraStatus(last);
};
setInterval(loadEvents, 30000);
applyLook(); loadMe(); loadEvents();
if (tab === "oversikt") loadHealth(false);
