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
  if (window.ksAero) window.ksAero.apply();
}
function drawLooks() {
  const box = $("#ks-themes"); if (!box || !window.KS_THEMES) return;
  const cur = curLook();
  const sw = (t) => `<button type="button" class="theme-sw${t.k === cur ? " on" : ""}" data-k="${esc(t.k)}">
    <span class="tp" style="background:radial-gradient(70% 90% at 10% 0%, ${t.a}cc, transparent 70%),radial-gradient(60% 80% at 100% 10%, ${t.b}bb, transparent 70%),radial-gradient(70% 60% at 50% 120%, ${t.c}88, transparent 70%),${t.bg}">
      <i class="tc" style="background:${t.card}"><b style="background:${t.fg}"></b><b style="background:${t.fg}"></b><b style="background:${t.fg}"></b></i>
      <i class="tg" style="background:linear-gradient(90deg, ${t.a}, ${t.b})"></i></span>
    <span class="tn">${esc(t.name)}</span><span class="td">${esc(t.desc)}</span></button>`;
  if (window.ksDesign && ksDesign.isNew() && window.KS_DESIGN) {     // nytt design: 8 utvalgte først, resten under «Flere temaer»
    const C = KS_DESIGN.curated, top = KS_THEMES.filter((t) => C.includes(t.k) || t.k === cur);
    const rest = KS_THEMES.filter((t) => !top.includes(t));
    box.innerHTML = top.map(sw).join("") + (rest.length ? `<details class="ks-more-themes"><summary>Flere temaer (${rest.length})</summary>
      <div class="themes">${rest.map(sw).join("")}</div></details>` : "");
  } else box.innerHTML = KS_THEMES.map(sw).join("");
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
  "Hjem": "Home", "Styr": "Control", "Verktøy": "Tools", "PC-en": "PC", "Hjemmet": "Household", "Innstillinger": "Settings", "Statistikk": "Statistics",
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
window.ksShared = (t) => { $("#send-text").value = t; setPref("cat_kontroll", "fjern"); setTab("kontroll"); toast("Trykk «Åpne lenke» eller «Kopier» for å sende til PC-en"); };
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
    const on = curClip && curClip.name === x.name && !curClip.pc;
    return `<div class="ct ${picked.has(x.name) ? "picked" : ""}${on ? " playing" : ""}" data-n="${esc(x.name)}"><button class="sel-tick" data-pick="${esc(x.name)}">✓</button>
      ${on ? '<span class="ct-now">▶ Spilles nå</span>' : ""}
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
  $$(".clipgrid .ct").forEach((el) => {                 // tydelig markering av klippet som spilles
    const on = !pc && el.dataset.n === name;
    el.classList.toggle("playing", on);
    const tag = el.querySelector(".ct-now");
    if (on && !tag) el.insertAdjacentHTML("afterbegin", '<span class="ct-now">▶ Spilles nå</span>');
    if (!on && tag) tag.remove();
  });
  $("#clip-now").textContent = "▶ " + name;
  const v = $("#clip-video"); v.src = fileUrl(name, pc); v.play().catch(() => {});
  const x = clipData && clipData.clips.find((y) => y.name === name);
  const cs = x && x.meta && x.meta.cs2;
  $("#clip-meta").textContent = name + (cs ? ` — ${cs.map} · runde ${cs.round} · CT ${cs.ct}–${cs.t} T · ${cs.kills}/${cs.deaths}/${cs.assists} · HS ${cs.hs_pct || "–"}` : "");
  v.onloadedmetadata = () => { for (const id of ["trim-a", "trim-b"]) $("#" + id).max = v.duration.toFixed(1); $("#trim-b").value = v.duration.toFixed(1); $("#trim-a").value = 0; trimLabels(); };
  $("#clip-player").scrollIntoView({ behavior: "smooth", block: "start" });
}
// trykk på videoen: fullskjerm og liggende (landskap); tilbake = vanlig visning
async function clipFullscreen() {
  const v = $("#clip-video");
  try {
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      await (document.exitFullscreen || document.webkitExitFullscreen).call(document);
      return;
    }
    await (v.requestFullscreen || v.webkitRequestFullscreen || v.webkitEnterFullscreen).call(v);
    try { await screen.orientation.lock("landscape"); } catch (e) { if (KS && KS.landscape) KS.landscape(true); }
  } catch (e) { if (KS && KS.landscape) KS.landscape(true); }
}
{ const v = $("#clip-video");
  let t0 = 0;
  v.addEventListener("click", (e) => {                   // ett trykk på bildet (ikke på kontrollene nederst)
    const r = v.getBoundingClientRect();
    if (e.clientY - r.top > r.height - 48) return;
    if (Date.now() - t0 < 350) return; t0 = Date.now();
    e.preventDefault(); clipFullscreen();
  });
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) { try { screen.orientation.unlock(); } catch (e) {} if (KS && KS.landscape) KS.landscape(false); }
  });
}
$("#clip-fs").onclick = clipFullscreen;
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
  if (t === "kontroll") { loadEvents(); loadEnergy(); loadNetwork(); loadProcs(); loadNas(); }
  if (t === "kontroll") { loadMedia(); try { spkLoad(); dispLoad(); pcplusLoad(); } catch (e) {} }
  if (t === "mer") { try { hjem5Load(); } catch (e) {} }
  if (t === "spill") { loadClips(); loadClips2(); loadClipExtras(); loadPlaytime(); loadCs2(); try { spill3Load(); } catch (e) {} }
  if (t === "mer") loadGoals();
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

// ---- test av hodesett og høyttalere (på PC-en, mono → 9.1) + hodesettet på telefonen ----
(() => {
  let info = null, pollT = 0;
  const lay = () => info && info.layouts.find((l) => l.key === $("#spk-lay").value);
  function room() {
    const l = lay(), box = $("#spk-room"); if (!l || !box) return;
    box.innerHTML = l.ch.map((c) => { const d = info.ch[c], [x, y] = d.pos;
      return `<button class="soft${info.playing === c ? " on" : ""}" data-ch="${c}" title="${esc(d.name)}" style="grid-column:${x + 1};grid-row:${y + 1}">${c === "LFE" ? "🔉" : "🔊"}<br>${esc(d.short || d.name)}</button>`; }).join("") +
      '<div class="me">🧑</div>';
  }
  async function load() {
    if (!$("#c-spk")) return;
    try { info = await api("/api/x/lydtest"); } catch (e) { $("#c-spk").hidden = true; return; }
    $("#c-spk").hidden = false;
    const s = $("#spk-sink"), keep = s.value;
    s.innerHTML = info.sinks.map((x) => `<option value="${esc(x.name)}">${esc(x.desc)} (${x.n} kan.)</option>`).join("");
    s.value = keep || info.sink; s.hidden = info.sinks.length < 2;
    const l = $("#spk-lay"); if (!l.options.length) {
      l.innerHTML = info.layouts.map((x) => `<option value="${x.key}">${esc(x.name)}</option>`).join("");
      l.value = info.suggest;
      $("#spk-snd").innerHTML = info.sounds.map((x) => `<option value="${x.key}">${esc(x.name)}</option>`).join("");
    }
    room();
    const f = info.filter || {};                    // lydfiltrene (Linux)
    $("#spk-filters").hidden = !f.available;
    if ($("#hs71-row")) { $("#hs71-row").hidden = !f.available; $("#hs71-name").textContent = f.headset ? "· " + f.headset.replace(/ Analog Stereo$/, "") : ""; }
    if (f.available) {
      document.querySelectorAll("[data-lf]").forEach((x) => (x.checked = !!f[x.dataset.lf]));
      const e = $("#spk-eq"); if (!e.options.length) e.innerHTML = f.presets.map((p) => `<option value="${p.key}">${esc(p.name)}</option>`).join("");
      e.value = f.eq_preset;
    }
    calShow(info.cal);
  }
  function calShow(c) {
    const el = $("#spk-calres"); if (!el || !c) return;
    if (c.running) { el.textContent = "🎯 " + c.step; setTimeout(async () => { try { const j = await api("/api/x/lydtest"); calShow(j.cal); } catch (e) {} }, 1000); return; }
    const r = c.result; if (!r) return;
    if (r.error) { el.textContent = "✗ " + r.error; return; }
    const ok = Object.keys(r.levels).filter((k) => !r.weak.includes(k));
    el.textContent = (ok.length ? "✓ Justert: " + ok.map((k) => `${info.ch[k].short} ${r.adjust[k] > 0 ? "+" : ""}${r.adjust[k]} dB`).join(" · ") : "") +
      (r.weak.length ? ` ⚠ Mikrofonen hørte ikke: ${r.weak.map((k) => info.ch[k].short).join(", ")}` : "");
  }
  document.addEventListener("change", (e) => {
    const lf = e.target.closest && e.target.closest("[data-lf]");
    if (lf) act({ a: "lydfilter", kind: lf.dataset.lf, on: lf.checked });
    if (e.target.id === "spk-eq") act({ a: "lydfilter", preset: e.target.value });
  });
  document.addEventListener("click", async (e) => {
    if (e.target.id !== "spk-cal") return;
    if (!(await confirmDlg("Kalibrere nivåene? PC-en spiller støy fra hver høyttaler, og mikrofonen på PC-en måler. Vær stille i rommet i ca. 20 sekunder."))) return;
    await act({ a: "lydkal", layout: $("#spk-lay").value, sink: $("#spk-sink").value || null });
    setTimeout(async () => { try { const j = await api("/api/x/lydtest"); calShow(j.cal); } catch (e) {} }, 600);
  });
  async function poll() {                       // marker høyttaleren som spiller, så lenge noe spilles
    clearTimeout(pollT);
    try { const j = await api("/api/x/lydtest"); info.playing = j.playing; room(); if (j.playing) pollT = setTimeout(poll, 700); } catch (e) {}
  }
  async function play(ch) {
    await act({ a: "lydtest", layout: $("#spk-lay").value, ch, sound: $("#spk-snd").value, sink: $("#spk-sink").value || null });
    if (ch !== "stop") setTimeout(poll, 500); else { info.playing = null; room(); }
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("#spk-room [data-ch], #c-spk [data-spk]"); if (b) return play(b.dataset.ch || b.dataset.spk);
    const h = e.target.closest("#c-spk [data-hp]"); if (h) hp(h.dataset.hp);
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "spk-lay") room();
    if (e.target.id === "spk-sink" && info) { const s = info.sinks.find((x) => x.name === e.target.value); if (s) load(); }
  });
  // hodesettet på telefonen: rosa-aktig støy, panorert venstre/høyre, eller i motfase
  let ctx = null;
  function hp(v) {
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      const n = ctx.sampleRate * 1.5, buf = ctx.createBuffer(2, n, ctx.sampleRate);
      let b = 0; const L = buf.getChannelData(0), R = buf.getChannelData(1);
      for (let i = 0; i < n; i++) { b = 0.97 * b + (Math.random() * 2 - 1) * 0.12; const f = Math.min(1, i / 2000, (n - i) / 2000);
        const s = b * f; L[i] = v === "1" ? 0 : s; R[i] = v === "-1" ? 0 : (v === "phase" ? -s : s); }
      const src = ctx.createBufferSource(); src.buffer = buf; src.connect(ctx.destination); src.start();
      toast({ "-1": "Venstre øre", "0": "Begge ører", "1": "Høyre øre", phase: "Motfase: skal høres diffust, «inne i hodet»" }[v]);
    } catch (e) { toast("Telefonen kan ikke spille lyd her: " + e.message); }
  }
  window.spkLoad = load;
  setTimeout(load, 1500);
})();

// ---- oppløsning og Hz på PC-en (med «Behold» / «Angre») ----
(() => {
  let d = null, keepT = 0;
  const cur = () => d && d.displays.find((x) => x.id === $("#disp-out").value) || (d && d.displays[0]);
  function fillHz() {
    const o = cur(); if (!o) return;
    const [w, h] = $("#disp-res").value.split("x").map(Number);
    const hz = [...new Set(o.modes.filter((m) => m[0] === w && m[1] === h).map((m) => m[2]))].sort((a, b) => b - a);
    $("#disp-hz").innerHTML = hz.map((x, i) => `<option value="${x}">${x} Hz${i ? "" : " ★"}</option>`).join("");
    $("#disp-hz").value = (w === o.w && h === o.h && hz.includes(o.hz)) ? o.hz : hz[0];
  }
  function fill() {
    const o = cur(); if (!o) return;
    const res = []; o.modes.forEach((m) => { const k = m[0] + "x" + m[1]; if (!res.includes(k)) res.push(k); });
    res.sort((a, b) => { const [aw, ah] = a.split("x"), [bw, bh] = b.split("x"); return bw * bh - aw * ah; });
    $("#disp-res").innerHTML = res.map((k, i) => `<option value="${k}">${k.replace("x", " × ")}${i ? "" : " ★"}</option>`).join("");
    $("#disp-res").value = o.w + "x" + o.h;
    fillHz();
    $("#disp-now").textContent = `Nå: ${o.w} × ${o.h} @ ${o.hz} Hz`;
  }
  async function load() {
    if (!$("#c-disp")) return;
    try { d = await api("/api/x/skjerm"); } catch (e) { return; }
    if (!d.displays.length) return;
    $("#c-disp").hidden = false;
    const s = $("#disp-out"), keep = s.value;
    s.innerHTML = d.displays.map((x) => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("");
    s.value = keep || d.displays[0].id; $("#disp-outw").hidden = d.displays.length < 2;
    fill(); showKeep(d.pending);
  }
  function showKeep(left) {
    clearTimeout(keepT);
    $("#disp-keep").hidden = !left;
    if (left) { $("#disp-left").textContent = `Går tilbake om ${left} s`; keepT = setTimeout(async () => {
      try { const j = await api("/api/x/skjerm"); d = j; showKeep(j.pending); if (!j.pending) fill(); } catch (e) {} }, 1000); }
  }
  document.addEventListener("change", (e) => {
    if (e.target.id === "disp-out") fill();
    if (e.target.id === "disp-res") fillHz();
  });
  document.addEventListener("click", async (e) => {
    const id = e.target.id;
    if (id === "disp-go") {
      const o = cur(); const [w, h] = $("#disp-res").value.split("x").map(Number);
      const r = await act({ a: "skjermmodus", id: o.id, w, h, hz: Number($("#disp-hz").value) });
      if (r && r.ok) showKeep(20);
    } else if (id === "disp-yes") { await act({ a: "skjermbehold" }); showKeep(0); load(); }
    else if (id === "disp-no") { await act({ a: "skjermangre" }); showKeep(0); setTimeout(load, 900); }
    else if (id === "t-pcscreen") act({ a: "skjermtest" });
    else if (id === "t-screen") screenTest();
    else if (id === "t-pad") padTest();
  });
  window.dispLoad = load;
  setTimeout(load, 1800);

  // ---- skjermtest for telefonen / TV-en selv ----
  const TESTS = [["#f00", "Rødt – se etter prikker som ikke er røde"], ["#0f0", "Grønt"], ["#00f", "Blått"],
    ["#fff", "Hvitt – svarte prikker er døde piksler"], ["#000", "Svart – lyse prikker er fastlåste piksler"],
    ["grad", "Fargebånd: overgangene skal være jevne"], ["black", "Svartnivå: du skal så vidt se rute 2–3"],
    ["ufo", "Bevegelse: følg romskipet – skarpt = rask skjerm"], ["hz", "Faktisk Hz"]];
  function screenTest() {
    const ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;z-index:9999;background:#000;touch-action:none";
    ov.tabIndex = 0;
    const cv = document.createElement("canvas"); cv.style.cssText = "width:100%;height:100%;display:block";
    const tip = document.createElement("div");
    tip.style.cssText = "position:absolute;left:0;right:0;bottom:0;padding:10px 14px;background:rgba(0,0,0,.6);color:#fff;font:14px sans-serif";
    ov.append(cv, tip); document.body.append(ov);
    try { ov.requestFullscreen && ov.requestFullscreen(); } catch (e) {}
    try { KS.landscape && KS.landscape(true); } catch (e) {}
    let i = 0, raf = 0, frames = [], t0 = performance.now();
    const ctx = cv.getContext("2d");
    function frame(t) {
      const W = cv.width = ov.clientWidth * devicePixelRatio, H = cv.height = ov.clientHeight * devicePixelRatio;
      const [k, txt] = TESTS[i];
      if (k[0] === "#") { ctx.fillStyle = k; ctx.fillRect(0, 0, W, H); }
      else if (k === "grad") { ["255,255,255", "255,0,0", "0,255,0", "0,0,255"].forEach((c, n) => {
        const g = ctx.createLinearGradient(0, 0, W, 0); g.addColorStop(0, "#000"); g.addColorStop(1, `rgb(${c})`);
        ctx.fillStyle = g; ctx.fillRect(0, n * H / 4, W, H / 4 + 1); }); }
      else if (k === "black") { ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H); for (let s = 1; s <= 10; s++) {
        const v = s * 3; ctx.fillStyle = `rgb(${v},${v},${v})`; ctx.fillRect(W / 12 * s, H * .35, W / 13, H * .3);
        ctx.fillStyle = "#777"; ctx.font = `${16 * devicePixelRatio}px sans-serif`; ctx.fillText(s, W / 12 * s + 6, H * .72); } }
      else if (k === "ufo") { ctx.fillStyle = "#141a29"; ctx.fillRect(0, 0, W, H); const el = (t - t0) / 1000;
        [960, 480].forEach((sp, n) => { const x = (el * sp * devicePixelRatio) % (W + 100) - 50, y = H * (.35 + n * .3);
          ctx.fillStyle = "#4de680"; ctx.beginPath(); ctx.arc(x, y, 26 * devicePixelRatio, Math.PI, 0); ctx.fill();
          ctx.fillStyle = "#c0c0d8"; ctx.fillRect(x - 46 * devicePixelRatio, y, 92 * devicePixelRatio, 14 * devicePixelRatio); }); }
      else if (k === "hz") { frames.push(t); frames = frames.slice(-120);
        const dd = frames.slice(1).map((v, n) => v - frames[n]).sort((a, b) => a - b), med = dd[dd.length >> 1];
        ctx.fillStyle = "#0d0f19"; ctx.fillRect(0, 0, W, H); ctx.fillStyle = "#fff"; ctx.font = `bold ${H / 7}px sans-serif`;
        ctx.textAlign = "center"; ctx.fillText(med ? Math.round(1000 / med) + " Hz" : "måler …", W / 2, H * .5); ctx.textAlign = "start";
        const c = frames.length % 60; for (let n = 0; n < 60; n++) { ctx.fillStyle = n === c ? "#40ccff" : "#262b3f"; ctx.fillRect(n * W / 60 + 1, H * .62, W / 60 - 2, H * .05); } }
      tip.textContent = `${i + 1}/${TESTS.length} · ${txt} · Trykk = neste · Tilbake/Esc = avslutt`;
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
    const next = () => { i++; frames = []; t0 = performance.now(); if (i >= TESTS.length) close(); };
    function close() { cancelAnimationFrame(raf); ov.remove(); try { document.fullscreenElement && document.exitFullscreen(); } catch (e) {}
      try { KS.landscape && KS.landscape(false); } catch (e) {} document.removeEventListener("keydown", key, true); }
    function key(e) { e.preventDefault(); e.stopPropagation(); if (e.key === "Escape" || e.key === "Backspace" || e.keyCode === 4) close(); else next(); }
    ov.addEventListener("click", next); document.addEventListener("keydown", key, true); ov.focus();
  }

  // ---- kontrollertest (kontroller koblet til telefonen eller TV-en) ----
  const NAMES = ["A ✕", "B ○", "X □", "Y △", "LB", "RB", "LT", "RT", "View", "Menu", "L3", "R3", "▲", "▼", "◀", "▶", "Guide"];
  let padRaf = 0;
  function padTest() {
    const v = $("#t-padview");
    if (!v.hidden) { v.hidden = true; cancelAnimationFrame(padRaf); return; }
    v.hidden = false;
    const seen = new Set();
    v.innerHTML = `<div class="dim small" id="pad-name">Trykk på en knapp på kontrolleren …</div>
      <div class="pad-sticks"><canvas id="pad-l" width="120" height="120"></canvas><canvas id="pad-r" width="120" height="120"></canvas></div>
      <div class="pad-btns">${NAMES.map((n, i) => `<span data-b="${i}">${n}</span>`).join("")}</div>
      <div class="row wrap"><button class="soft" id="pad-vib">📳 Vibrer</button><button class="soft" id="pad-drift">Mål drift</button></div>
      <div id="pad-msg" class="dim small"></div>`;
    const stick = (c, x, y) => { const g = c.getContext("2d"); g.clearRect(0, 0, 120, 120); g.fillStyle = "rgba(128,128,150,.2)";
      g.beginPath(); g.arc(60, 60, 55, 0, 7); g.fill(); g.fillStyle = Math.hypot(x, y) < .1 ? "#33d17a" : "#5b8cff";
      g.beginPath(); g.arc(60 + x * 50, 60 + y * 50, 8, 0, 7); g.fill(); };
    let drift = null;
    function loop() {
      const p = [...(navigator.getGamepads ? navigator.getGamepads() : [])].find((g) => g);
      if (p) {
        $("#pad-name").textContent = p.id;
        p.buttons.forEach((b, i) => { const el = v.querySelector(`[data-b="${i}"]`); if (!el) return;
          el.classList.toggle("on", b.pressed || b.value > .5); if (b.pressed) seen.add(i); el.classList.toggle("seen", seen.has(i)); });
        const a = p.axes; stick($("#pad-l"), a[0] || 0, a[1] || 0); stick($("#pad-r"), a[2] || 0, a[3] || 0);
        if (drift) { drift.push(a.slice(0, 4)); if (drift.length > 90) {
          const m = (i) => Math.max(...drift.map((s) => Math.hypot(s[i], s[i + 1])));
          const l = m(0), r = m(2), txt = (x) => x < .06 ? "✓ ingen drift" : x < .12 ? "⚠ litt drift" : "❌ tydelig drift";
          $("#pad-msg").textContent = `Venstre: ${txt(l)} (${l.toFixed(2)}) · Høyre: ${txt(r)} (${r.toFixed(2)}) · Dødsone: ${Math.round(Math.min(.3, Math.max(l, r) + .03) * 100)} %`;
          drift = null; } }
      }
      if (!v.hidden) padRaf = requestAnimationFrame(loop);
    }
    padRaf = requestAnimationFrame(loop);
    $("#pad-vib").onclick = () => { const p = [...navigator.getGamepads()].find((g) => g);
      const a = p && p.vibrationActuator; if (a && a.playEffect) a.playEffect("dual-rumble", { duration: 700, strongMagnitude: 1, weakMagnitude: 1 });
      else $("#pad-msg").textContent = "Denne kontrolleren (eller nettleseren) støtter ikke vibrasjon her."; };
    $("#pad-drift").onclick = () => { drift = []; $("#pad-msg").textContent = "Slipp stikkene og ikke rør kontrolleren … (3 s)"; };
  }
})();

// ---- spill runde 3: spillkveld og nett, spillår, før/etter og plass ----
(() => {
  const host = () => { const s = $("#spill"); return s && (s.querySelector(":scope > .grid") || s); };
  const mk = (id, html) => { let c = document.getElementById(id); if (!c && host()) { c = document.createElement("div");
    c.className = "card"; c.id = id; c.innerHTML = html; host().appendChild(c); } return c; };
  let d = null;
  function render() {
    if (!d) return;
    // spillkveld: turnering
    const t = d.tourney || {}, tc = mk("c-tourney", "<h2>🏆 LAN-turnering</h2><div id='tn-body'></div>");
    const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest("#c-tourney input");
    if (typing) { /* ikke tegn på nytt mens du skriver */ }
    else if (t.teams && t.teams.length) {
      const best = Math.max(...t.teams.map((x) => x.score));
      $("#tn-body").innerHTML = `<div><b>${esc(t.name)}</b>${t.game ? " · " + esc(t.game) : ""}</div>` +
        t.teams.map((x, i) => ({ x, i })).sort((a, b) => b.x.score - a.x.score).map(({ x, i }) =>
          `<div class="row"><span style="flex:1">${x.score === best && best ? "🥇 " : ""}${esc(x.name)}</span><b style="font-size:1.3em;margin:0 8px">${x.score}</b>
           <button class="soft" data-tn="${i}" data-d="-1">−</button><button class="primary" data-tn="${i}" data-d="1">+1</button></div>`).join("") +
        `<div class="row wrap"><button class="soft" id="tn-gm">🎮 Spillmodus på alle</button><button class="danger" id="tn-end">Avslutt og kår vinner</button></div>`;
    } else if (!typing) {
      $("#tn-body").innerHTML = (t.last ? `<div class="dim small">Sist: ${esc(t.last.winner)} vant ${esc(t.last.name)} (${t.last.score} poeng)</div>` : "") +
        `<input id="tn-name" placeholder="Navn, f.eks. Fredagsturnering"><input id="tn-game" placeholder="Spill, f.eks. CS2">
         <input id="tn-teams" placeholder="Lag eller spillere, med komma: Rød, Blå"><button class="primary" id="tn-new">Start turneringen</button>`;
    }
    tc.hidden = false;
    // nettet i spillet
    const n = d.net || {}, last = (n.hist || []).slice(-1)[0];
    const f = (v, l) => v == null ? "–" : Math.round(v) + " ms" + (l ? ` (${l} % tap)` : "");
    mk("c-net", "<h2>📶 Nettet i spillet</h2><div id='net-v'></div><div id='net-d' class='dim small'></div>");
    $("#net-v").innerHTML = last ? `<b>${esc(n.verdict)}</b>` : "<span class='dim'>Starter når du spiller på PC-en</span>";
    $("#net-d").textContent = last ? `${n.game || ""} · Server ${last.server || "?"}: ${f(last.srv, last.srv_loss)} · Internett ${f(last.net, last.net_loss)} · Ruter ${f(last.gw, last.gw_loss)}` : "";
    // spillår
    const w = d.wrapped || {};
    mk("c-wrapped", "<h2>🎁 Ditt spillår</h2><div id='wr-t' style='white-space:pre-line'></div><button class='soft' id='wr-share'>💬 Del i chatten</button>");
    $("#wr-t").textContent = w.text || ""; $("#wr-share").hidden = !w.total_h;
    // før og etter
    const cp = d.compare || {};
    mk("c-compare", "<h2>⚖️ Før og etter</h2><div class='dim small'>Skal du bytte driver eller innstillinger? Merk det, spill som vanlig, og se om FPS ble bedre.</div><div class='row'><input id='cp-l' placeholder='Hva endrer du?' style='flex:1'><button class='soft' id='cp-m'>Merk</button></div><div id='cp-r'></div>");
    $("#cp-r").innerHTML = !cp.mark ? "<div class='dim small'>Ingen endring merket ennå.</div>" :
      `<div class="dim small">Siden «${esc(cp.mark.label)}»:</div>` + (cp.games.length ? cp.games.map((g) =>
        `<div>${g.pct > 2 ? "🟢 +" : g.pct < -2 ? "🔴 " : "⚪ "}${g.pct} % ${esc(g.game)}: ${g.before} → ${g.after} FPS</div>`).join("") : "<div class='dim small'>Spill noen økter først.</div>");
    // plass
    const s = d.storage || {};
    mk("c-storage", "<h2>💾 Plass per spill</h2><div id='st-h' class='dim small'></div><div id='st-l'></div><div class='row' id='st-nr'><span style='flex:1'>Spilloppdateringer bare om natten (billigste strøm)</span><label class='switch'><input type='checkbox' id='st-night'><i></i></label></div>");
    $("#st-h").textContent = `Spillene bruker ${Math.round(s.total_gb || 0)} GB. Ikke spilt på 6 måneder: ${(s.old || []).length} spill, ${Math.round(s.old_gb || 0)} GB.`;
    $("#st-l").innerHTML = (s.old || []).slice(0, 10).map((g) => `<div class="row"><span style="flex:1">${esc(g.name)} · ${g.gb} GB · ${g.days == null ? "aldri spilt" : g.days + " d siden"}</span><button class="soft" data-uninst="${g.appid}">Avinstaller</button></div>`).join("");
    $("#st-night").checked = !!d.night; $("#st-nr").hidden = !!d.win;
  }
  async function load() { try { d = await api("/api/x/spill3"); render(); } catch (e) {} }
  window.spill3Load = load;
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-tn]");
    if (b) { await act({ a: "turnscore", team: +b.dataset.tn, d: +b.dataset.d }, true); return load(); }
    const u = e.target.closest("[data-uninst]");
    if (u) { await act({ a: "spill3uninst", appid: u.dataset.uninst }); return; }
    const id = e.target.id;
    if (id === "tn-new") { await act({ a: "turnnew", name: $("#tn-name").value, game: $("#tn-game").value, teams: $("#tn-teams").value }); load(); }
    else if (id === "tn-end") { if (await confirmDlg("Avslutte turneringen og kåre vinneren?")) { await act({ a: "turnend" }); load(); } }
    else if (id === "tn-gm") act({ a: "turngm" });
    else if (id === "wr-share") act({ a: "spill3share" });
    else if (id === "cp-m") { await act({ a: "spill3mark", label: $("#cp-l").value }); $("#cp-l").value = ""; load(); }
  });
  document.addEventListener("change", (e) => { if (e.target.id === "st-night") act({ a: "spill3night", on: e.target.checked }); });
  setTimeout(load, 2500);
  setInterval(() => tab === "spill" && !document.hidden && load(), 20000);
})();

// ---- PC runde 4: helse, stille nå, strømbudsjett og stresstest ----
(() => {
  const host = () => { const s = $("#kontroll"); return s && (s.querySelector(":scope > .grid") || s); };
  const mk = (id, html) => { let c = document.getElementById(id); if (!c && host()) { c = document.createElement("div");
    c.className = "card"; c.id = id; c.innerHTML = html; host().appendChild(c); } return c; };
  let st = 0;
  async function load() {
    let d; try { d = await api("/api/x/pcplus"); } catch (e) { return; }
    const h = d.health || { score: "…", word: "regner ut", items: [] };
    if (!d.health) setTimeout(load, 4000);
    const tile = document.getElementById("c-health");    // helsepoengene i den samme Helse-flisen på Hjem
    if (tile && !document.getElementById("hl-s")) {
      const x = document.createElement("div"); x.className = "hp-box";
      x.innerHTML = "<div id='hl-s'></div><div id='hl-i' class='small'></div><div id='hl-b' class='dim small'></div>";
      tile.querySelector("h2").after(x);
    }
    if (document.getElementById("hl-s")) {
      $("#hl-s").innerHTML = `❤️ <b style="font-size:1.4em">${h.score}</b><span class="dim"> / 100 · ${esc(h.word)}</span>`;
      $("#hl-i").innerHTML = h.items.map((x) => `<div>${{ bad: "❌", warn: "⚠️", info: "ℹ️" }[x.level] || "•"} ${esc(x.title)} <span class="dim">(−${x.minus})</span></div>`).join("");
      $("#hl-b").textContent = d.bios ? d.bios.text : "";
    }
    mk("c-pcquiet", "<h2>🤫 Stille nå</h2><div class='dim small'>Rolige vifter og lavere effekt i noen timer.</div><div class='row wrap'><button class='soft' data-q='1'>1 time</button><button class='soft' data-q='2'>2 timer</button><button class='soft' data-q='4'>4 timer</button><button class='soft' data-q='0'>Av</button></div><div id='q-s' class='dim small'></div>");
    $("#q-s").textContent = d.quiet ? `På – ${Math.floor(d.quiet / 60)} t ${d.quiet % 60} min igjen` : "Av";
    const b = d.budget;
    mk("c-budget", "<h2>💡 Strømbudsjett</h2><div class='row'><span style='flex:1'>Kr per måned (0 = av)</span><input id='bg-kr' type='number' min='0' step='25' style='width:90px'></div><div id='bg-t' class='dim small'></div>");
    if (document.activeElement !== $("#bg-kr")) $("#bg-kr").value = b ? b.budget : 0;
    $("#bg-t").textContent = b ? b.text : "";
    const s = d.stress;
    mk("c-stress", "<h2>🔥 Stresstest</h2><div class='dim small'>Prosessor og minne på full guffe – sjekker stabilitet og temperatur.</div><div class='row wrap'><select id='ss-m'><option value='2'>2 min</option><option value='5' selected>5 min</option><option value='15'>15 min</option></select><button class='primary' id='ss-go'>Start</button><button class='soft' id='ss-stop'>Stopp</button></div><div id='ss-t'></div>");
    $("#ss-t").textContent = s.running ? `Kjører … ${Math.floor(s.t / 60)}:${String(s.t % 60).padStart(2, "0")} · CPU ${s.temp || "?"} °C` :
      s.result ? `${s.result.verdict} · maks ${s.result.max_temp || "?"} °C · ${s.result.errors} regnefeil` : "";
    clearTimeout(st); if (s.running) st = setTimeout(load, 3000);
  }
  window.pcplusLoad = load;
  document.addEventListener("click", async (e) => {
    const q = e.target.closest("[data-q]"); if (q) { await act({ a: "pcquiet", hours: +q.dataset.q }); return load(); }
    if (e.target.id === "ss-go") { if (await confirmDlg("Starte stresstesten? PC-en blir varm og viftene går opp i noen minutter.")) { await act({ a: "pcstress", minutes: +$("#ss-m").value }); setTimeout(load, 1500); } }
    if (e.target.id === "ss-stop") { await act({ a: "pcstress", stop: true }); setTimeout(load, 1500); }
  });
  document.addEventListener("change", (e) => { if (e.target.id === "bg-kr") act({ a: "pcbudget", kr: +e.target.value }).then(load); });
  setTimeout(load, 3000);
})();

// ---- hjemmet runde 5: middagsplan, pakker, beskjed til alle, søvnrapport og minnevegg ----
(() => {
  const host = () => { const s = $("#mer"); return s && (s.querySelector(":scope > .grid") || s); };
  const mk = (id, html) => { let c = document.getElementById(id); if (!c && host()) { c = document.createElement("div");
    c.className = "card"; c.id = id; c.innerHTML = html; host().appendChild(c); } return c; };
  let d = null, lastSay = 0, firstSay = true;
  const typing = (sel) => document.activeElement && document.activeElement.closest && document.activeElement.closest(sel);
  function render() {
    if (!d) return;
    mk("c-meals", "<h2>🍽️ Middagsplan</h2><div id='ml-l'></div><div class='row wrap'><button class='soft' id='ml-shop'>🛒 Ukas ingredienser til handlelista</button></div>");
    if (!typing("#c-meals")) $("#ml-l").innerHTML = d.menu.map((m) => `<div class="row"><span style="width:48px">${m.wd} ${+m.day.slice(8)}.</span>
      <input data-ml="${m.day}" data-f="dish" value="${esc(m.dish)}" placeholder="Rett" style="flex:1"><input data-ml="${m.day}" data-f="ing" value="${esc(m.ing)}" placeholder="Ingredienser" style="flex:1"></div>`).join("");
    mk("c-pkgs", "<h2>📦 Pakker</h2><div class='row'><input id='pk-nr' placeholder='Sporingsnummer' style='flex:1'><button class='primary' id='pk-add'>Legg til</button></div><div class='row'><input id='pk-name' placeholder='Hva er det?' style='flex:1'><input id='pk-eta' type='date'></div><div id='pk-l'></div>");
    $("#pk-l").innerHTML = d.packages.length ? d.packages.map((p) => `<div class="row"><span style="flex:1">${p.done ? "✅" : "📦"} ${esc(p.name)} · ${esc(p.carrier)}${p.eta ? " · " + p.eta.slice(8) + "." + p.eta.slice(5, 7) : ""}</span>
      <a class="btn soft" href="${esc(p.url)}" target="_blank" rel="noopener">Spor →</a><button class="soft" data-pk="${esc(p.nr)}" data-rm="${p.done ? 1 : 0}">${p.done ? "Fjern" : "Hentet"}</button></div>`).join("") : "<div class='dim small'>Ingen pakker på vei.</div>";
    mk("c-say", "<h2>📢 Beskjed til alle</h2><div class='dim small'>Vises på alle PC-ene (over spillet), telefonene og TV-en.</div><div class='row'><input id='say-t' placeholder='Skriv en beskjed …' style='flex:1'><button class='primary' id='say-go'>Send</button></div><div class='row wrap'><button class='soft' data-say='Kom ned nå'>Kom ned nå</button><button class='soft' data-say='Middag om 5 min'>Middag om 5 min</button><button class='soft' data-say='Legg dere nå 😴'>Legg dere nå</button></div>");
    const s = d.sleep || { rows: [], days: [] };
    mk("c-sleep", "<h2>😴 Søvnrapport</h2><div id='sl-t'></div><div class='row'><span style='flex:1'>Slå av TV-en ved leggetid</span><label class='switch'><input type='checkbox' id='sl-tv'><i></i></label></div>");
    $("#sl-t").innerHTML = s.rows.length ? `<table class="small" style="width:100%"><tr><td></td>${s.days.map((x) => `<td class="dim">${["Søn", "Man", "Tir", "Ons", "Tor", "Fre", "Lør"][new Date(x).getDay()]}</td>`).join("")}</tr>` +
      s.rows.map((r) => `<tr><td>${esc(r.pc)}</td>${r.nights.map((n) => `<td style="${n.over > 0 ? "color:#e01b24;font-weight:700" : ""}">${n.off || "–"}</td>`).join("")}</tr>`).join("") + "</table>"
      : "<div class='dim small'>Ingen kvelder logget ennå.</div>";
    $("#sl-tv").checked = !!d.tv_bedtime;
    mk("c-mem", "<h2>🖼️ Minnevegg</h2><div id='mem-n' class='dim small'></div><button class='primary' id='mem-go'>Start lysbildeshow</button>");
    $("#mem-n").textContent = d.mem.length ? `${d.mem.length} bilder fra chatten` : "Ingen bilder i chatten ennå.";
    $("#mem-go").disabled = !d.mem.length;
    // beskjed til alle: vis stort på TV-en / i appen når en ny kommer
    if (d.say && d.say.t > lastSay) { if (!firstSay && d.say.t > Date.now() / 1000 - 300) bigSay(d.say); lastSay = d.say.t; }
    firstSay = false;
  }
  function bigSay(s) {
    const o = document.createElement("div");
    o.style.cssText = "position:fixed;inset:0;z-index:9998;display:grid;place-items:center;background:rgba(0,0,0,.82);color:#fff;text-align:center;padding:24px";
    o.innerHTML = `<div><div style="font-size:3em">📢</div><div style="font-size:2em;font-weight:800;margin:12px 0">${esc(s.text)}</div><div class="dim">fra ${esc(s.frm)} · trykk for å lukke</div></div>`;
    o.tabIndex = 0; o.onclick = () => o.remove(); o.onkeydown = () => o.remove();
    document.body.append(o); o.focus(); setTimeout(() => o.remove(), 60000);
  }
  function slideshow() {
    if (!d || !d.mem.length) return;
    let i = 0;
    const o = document.createElement("div"); o.tabIndex = 0;
    o.style.cssText = "position:fixed;inset:0;z-index:9999;background:#000;display:grid;place-items:center";
    const img = document.createElement("img"); img.style.cssText = "max-width:100%;max-height:100%;object-fit:contain;transition:opacity .6s";
    o.append(img); document.body.append(o);
    try { o.requestFullscreen && o.requestFullscreen(); } catch (e) {}
    const show = () => { const m = d.mem[i % d.mem.length]; img.style.opacity = 0;
      setTimeout(() => { img.src = "/api/chatfile?k=" + encodeURIComponent(token) + "&sha=" + encodeURIComponent(m.sha) + "&name=" + encodeURIComponent(m.name); img.style.opacity = 1; }, 300); };
    show(); const tm = setInterval(() => { i++; show(); }, 7000);
    const close = () => { clearInterval(tm); o.remove(); try { document.fullscreenElement && document.exitFullscreen(); } catch (e) {} };
    o.onclick = () => { i++; show(); };
    o.onkeydown = (e) => { if (e.key === "Escape" || e.key === "Backspace" || e.keyCode === 4) close(); else { i += e.key === "ArrowLeft" ? -1 : 1; show(); } e.preventDefault(); };
    o.focus();
  }
  async function load() { try { d = await api("/api/x/hjem5"); render(); } catch (e) {} }
  window.hjem5Load = load;
  document.addEventListener("change", (e) => {
    const m = e.target.closest && e.target.closest("[data-ml]");
    if (m) { const day = m.dataset.ml, row = [...document.querySelectorAll(`[data-ml="${day}"]`)];
      act({ a: "h5meal", day, dish: row.find((x) => x.dataset.f === "dish").value, ing: row.find((x) => x.dataset.f === "ing").value }, true); }
    if (e.target.id === "sl-tv") act({ a: "h5tv", on: e.target.checked });
  });
  document.addEventListener("click", async (e) => {
    const id = e.target.id;
    if (id === "ml-shop") act({ a: "h5shop" });
    else if (id === "pk-add") { await act({ a: "h5pkg", nr: $("#pk-nr").value, name: $("#pk-name").value, eta: $("#pk-eta").value }); $("#pk-nr").value = ""; $("#pk-name").value = ""; load(); }
    else if (id === "say-go") { await act({ a: "h5say", text: $("#say-t").value }); $("#say-t").value = ""; }
    else if (id === "mem-go") slideshow();
    const p = e.target.closest("[data-pk]"); if (p) { await act({ a: "h5pkgdone", nr: p.dataset.pk, remove: p.dataset.rm === "1" }); load(); }
    const s = e.target.closest("[data-say]"); if (s) act({ a: "h5say", text: s.dataset.say });
  });
  setTimeout(load, 3500);
  setInterval(() => !document.hidden && (tab === "mer" || (KS && KS.isTv && KS.isTv())) && load(), 20000);
})();

// ---- styreflate: telefonen / TV-fjernkontrollen som mus og tastatur for PC-en ----
(() => {
  const host = () => { const s = $("#kontroll"); return s && (s.querySelector(":scope > .grid") || s); };
  function build() {
    if (document.getElementById("c-touchpad") || !host()) return;
    const c = document.createElement("div"); c.className = "card"; c.id = "c-touchpad";
    c.innerHTML = `<h2>🖱️ Styreflate</h2><div class="dim small">Dra = flytt musa · trykk = klikk · to fingre = høyreklikk / rull. På TV-en: piltastene flytter, OK klikker, Tilbake avslutter.</div>
      <div id="tp-area" tabindex="0" style="height:220px;border-radius:16px;margin:8px 0;background:rgba(128,128,150,.14);touch-action:none;display:grid;place-items:center;color:var(--dim,#999)">Styreflate</div>
      <div class="row wrap"><button class="soft" data-tp="left">Venstreklikk</button><button class="soft" data-tp="right">Høyreklikk</button><button class="soft" data-tp="double">Dobbeltklikk</button></div>
      <div class="row wrap">${[["esc", "Esc"], ["tab", "Tab"], ["enter", "Enter"], ["backspace", "⌫"], ["up", "↑"], ["down", "↓"], ["left", "←"], ["right", "→"], ["alt-tab", "Alt+Tab"], ["playpause", "⏯"], ["voldown", "🔉"], ["volup", "🔊"], ["f11", "F11"]].map(([k, l]) => `<button class="soft" data-tk="${k}">${l}</button>`).join("")}</div>
      <div class="row"><input id="tp-text" placeholder="Skriv tekst på PC-en …" style="flex:1"><button class="primary" id="tp-send">Skriv</button></div>`;
    host().appendChild(c);
    const area = c.querySelector("#tp-area");
    let acc = [0, 0], timer = 0, last = null, fingers = 0, moved = false, t0 = 0, sc = 0;
    const send = (b) => api("/api/action", { a: "pcinput", ...b }).catch(() => {});
    const flush = () => { timer = 0; if (acc[0] || acc[1]) { const [dx, dy] = acc; acc = [0, 0]; send({ do: "move", dx, dy }); } };
    const queue = (dx, dy) => { acc[0] += dx; acc[1] += dy; if (!timer) timer = setTimeout(flush, 35); };
    area.addEventListener("touchstart", (e) => { fingers = e.touches.length; moved = false; t0 = Date.now(); last = [e.touches[0].clientX, e.touches[0].clientY]; e.preventDefault(); }, { passive: false });
    area.addEventListener("touchmove", (e) => {
      const p = [e.touches[0].clientX, e.touches[0].clientY], dx = p[0] - last[0], dy = p[1] - last[1]; last = p;
      if (Math.abs(dx) + Math.abs(dy) > 1) moved = true;
      if (e.touches.length >= 2) { sc += dy; if (Math.abs(sc) > 18) { send({ do: "scroll", dy: sc > 0 ? -1 : 1 }); sc = 0; } }
      else { const f = 1.6 + Math.min(2.5, Math.hypot(dx, dy) / 12); queue(dx * f, dy * f); }
      e.preventDefault();
    }, { passive: false });
    area.addEventListener("touchend", (e) => { if (!moved && Date.now() - t0 < 300) send({ do: "click", button: fingers >= 2 ? "right" : "left" }); e.preventDefault(); }, { passive: false });
    // mus (nettbrett/PC-nettleser) og TV-fjernkontrollens piltaster
    let down = null;
    area.addEventListener("mousedown", (e) => { down = [e.clientX, e.clientY]; moved = false; });
    area.addEventListener("mousemove", (e) => { if (!down) return; const dx = e.clientX - down[0], dy = e.clientY - down[1]; down = [e.clientX, e.clientY]; if (dx || dy) { moved = true; queue(dx * 1.5, dy * 1.5); } });
    area.addEventListener("mouseup", () => { if (!moved) send({ do: "click" }); down = null; });
    let speed = 8, held = 0;
    area.addEventListener("keydown", (e) => {
      const k = e.key, now = Date.now();
      speed = now - held < 150 ? Math.min(60, speed * 1.25) : 8; held = now;
      const m = { ArrowLeft: [-speed, 0], ArrowRight: [speed, 0], ArrowUp: [0, -speed], ArrowDown: [0, speed] }[k];
      if (m) { queue(m[0], m[1]); e.preventDefault(); e.stopPropagation(); }
      else if (k === "Enter" || e.keyCode === 23) { send({ do: "click" }); e.preventDefault(); e.stopPropagation(); }
      else if (k === "Escape" || k === "Backspace" || e.keyCode === 4) { area.blur(); e.preventDefault(); }
    });
    area.addEventListener("focus", () => (area.textContent = "Piltastene flytter musa – OK klikker"));
    area.addEventListener("blur", () => (area.textContent = "Styreflate"));
    c.addEventListener("click", (e) => {
      const b = e.target.closest("[data-tp]"); if (b) send(b.dataset.tp === "double" ? { do: "click", double: true } : { do: "click", button: b.dataset.tp });
      const k = e.target.closest("[data-tk]"); if (k) send({ do: "key", key: k.dataset.tk });
      if (e.target.id === "tp-send") { send({ do: "text", text: $("#tp-text").value }); $("#tp-text").value = ""; }
    });
  }
  setTimeout(build, 1200);
})();

// ---- TV-dashbord / infoskjerm, Andreskjerm, talekommandoer og testvarsel til klokka ----
(() => {
  const isTv = () => { try { return !!(KS && KS.isTv && KS.isTv()); } catch (e) { return false; } };
  const full = (o) => { try { o.requestFullscreen && o.requestFullscreen(); } catch (e) {} };
  const exitFull = () => { try { document.fullscreenElement && document.exitFullscreen(); } catch (e) {} };
  // ---------- TV-dashbord: klokke, vær, strømpris, dagens plan og alle PC-ene ----------
  let dashEl = null, dashT = 0;
  async function dashFill() {
    if (!dashEl) return;
    let d; try { d = await api("/api/x/tvdash"); } catch (e) { return; }
    const now = new Date(), w = d.weather || {}, p = d.price || {};
    dashEl.querySelector(".td-clock").textContent = now.toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
    dashEl.querySelector(".td-date").textContent = now.toLocaleDateString("nb-NO", { weekday: "long", day: "numeric", month: "long" });
    dashEl.querySelector(".td-wx").innerHTML = w.temp != null ? `${w.icon || ""} <b>${w.temp}°</b> <span>${esc(w.text || "")}${w.place ? " · " + esc(w.place) : ""}</span>` : "";
    dashEl.querySelector(".td-price").textContent = p && p.now != null ? `⚡ ${p.now} kr/kWh nå` : "";
    dashEl.querySelector(".td-today").innerHTML = (d.today || []).length ? d.today.map((x) => `<div>${x.icon || "•"} ${x.time ? x.time + " " : ""}${esc(x.title)}</div>`).join("") : "<div class='td-dim'>Ingenting i kalenderen i dag</div>";
    dashEl.querySelector(".td-pcs").innerHTML = (d.pcs || []).map((x) => `<div class="td-pc${x.online ? "" : " off"}"><b>${esc(x.name)}</b>
      <span>${x.online ? (x.game ? "🎮 " + esc(x.game) : "🟢 På") : "⚫ Av"}</span>${x.online ? `<span>CPU ${Math.round(x.cpu_t || 0)}°${x.gpu_t ? " · GPU " + Math.round(x.gpu_t) + "°" : ""}${x.watts ? " · " + Math.round(x.watts) + " W" : ""}</span>` : ""}</div>`).join("");
  }
  window.ksTvDash = () => {
    if (dashEl) return;
    dashEl = document.createElement("div"); dashEl.className = "tvdash"; dashEl.tabIndex = 0;
    dashEl.innerHTML = `<div class="td-top"><div><div class="td-clock"></div><div class="td-date"></div></div><div class="td-right"><div class="td-wx"></div><div class="td-price"></div></div></div>
      <div class="td-grid"><div class="td-box"><h3>📅 I dag</h3><div class="td-today"></div></div><div class="td-box"><h3>🖥️ PC-ene</h3><div class="td-pcs"></div></div></div>
      <div class="td-dim td-hint">Trykk en knapp for å gå tilbake</div>`;
    document.body.append(dashEl); full(dashEl); dashEl.focus();
    const close = () => { if (!dashEl) return; clearInterval(dashT); dashEl.remove(); dashEl = null; exitFull(); idleReset(); };
    dashEl.onclick = close; dashEl.onkeydown = (e) => { e.preventDefault(); close(); };
    dashFill(); dashT = setInterval(dashFill, 15000);
  };
  // på TV-en: dashbordet kommer av seg selv etter 5 minutter uten bruk
  let idleT = 0;
  const idleReset = () => { clearTimeout(idleT); if (isTv()) idleT = setTimeout(() => { if (!document.hidden) window.ksTvDash(); }, 5 * 60000); };
  ["keydown", "click", "touchstart"].forEach((ev) => document.addEventListener(ev, () => { if (!dashEl) idleReset(); }, true));
  idleReset();
  // ---------- Andreskjerm: telefonen ved siden av tastaturet mens du spiller ----------
  let sEl = null, sT = 0;
  async function sFill() {
    if (!sEl) return;
    let st; try { st = await api("/api/status"); } catch (e) { return; }
    const g = (id) => sEl.querySelector(id);
    g(".as-game").textContent = st.game ? "🎮 " + st.game : "Ingen spill akkurat nå";
    g(".as-fps").textContent = st.fps ? Math.round(st.fps) : "–";
    g(".as-cpu").textContent = st.cpu_t != null ? Math.round(st.cpu_t) + "°" : "–";
    g(".as-gpu").textContent = st.gpu && st.gpu.temp != null ? Math.round(st.gpu.temp) + "°" : (st.gpu_t != null ? Math.round(st.gpu_t) + "°" : "–");
    g(".as-w").textContent = st.watts ? Math.round(st.watts) + " W" : "–";
    g(".as-time").textContent = new Date().toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
  }
  window.ksSecondScreen = () => {
    if (sEl) return;
    sEl = document.createElement("div"); sEl.className = "andreskjerm"; sEl.tabIndex = 0;
    sEl.innerHTML = `<div class="as-head"><span class="as-game"></span><span class="as-time"></span><button class="as-x">✕</button></div>
      <div class="as-big"><div><small>FPS</small><b class="as-fps">–</b></div><div><small>CPU</small><b class="as-cpu">–</b></div><div><small>GPU</small><b class="as-gpu">–</b></div><div><small>Strøm</small><b class="as-w">–</b></div></div>
      <div class="as-btns"><button data-as="mute">🎙️ Mikrofon av/på</button><button data-as="deaf">🎧 Lyd av/på</button><button data-as="clip">🎬 Lagre klipp</button><button data-as="overlay">📊 Overlay</button></div>`;
    document.body.append(sEl); full(sEl);
    try { KS && KS.landscape && KS.landscape(true); } catch (e) {}
    try { navigator.wakeLock && navigator.wakeLock.request("screen").then((l) => (sEl._lock = l)); } catch (e) {}
    const close = () => { clearInterval(sT); try { sEl._lock && sEl._lock.release(); } catch (e) {} sEl.remove(); sEl = null; exitFull(); try { KS && KS.landscape && KS.landscape(false); } catch (e) {} };
    sEl.querySelector(".as-x").onclick = close;
    sEl.addEventListener("click", (e) => { const b = e.target.closest("[data-as]"); if (!b) return;
      const k = b.dataset.as;
      if (k === "mute" || k === "deaf") { sEl["_" + k] = !sEl["_" + k]; b.classList.toggle("on", sEl["_" + k]);
        b.style.background = sEl["_" + k] ? "#e01b24" : ""; act({ a: "discord", do: k, on: sEl["_" + k] }); }
      else if (k === "clip") act({ a: "clip" });
      else if (k === "overlay") act({ a: "overlay", on: true }); });
    sFill(); sT = setInterval(sFill, 2000);
  };
  // ---------- talekommandoer (mikrofonknappen på TV-fjernkontrollen, eller knappen) ----------
  window.ksVoiceKey = () => {
    if (!(KS && KS.listen)) { toast("Talegjenkjenning finnes bare i appen"); return; }
    const prev = window.ksHeard;
    window.ksHeard = async (text, err) => {
      window.ksHeard = prev;
      if (err || !text) { toast(err || "Hørte ingenting"); return; }
      toast("🎙️ «" + text + "»");
      const r = await api("/api/action", { a: "voice", text }).catch((e) => ({ ok: false, msg: e.message }));
      toast((r.ok ? "✓ " : "") + r.msg);
      try { KS.speak && r.msg && KS.speak(r.msg.replace(/[«»✓]/g, "")); } catch (e) {}
    };
    toast("🎙️ Si en kommando …"); KS.listen("nb-NO");
  };
  // ---------- knappene ----------
  function buttons() {
    const host = (() => { const s = $("#kontroll"); return s && (s.querySelector(":scope > .grid") || s); })();
    if (host && !document.getElementById("c-extra-screens")) {
      const c = document.createElement("div"); c.className = "card"; c.id = "c-extra-screens";
      c.innerHTML = `<h2>📺 Skjermer og tale</h2><div class="dim small">Andreskjerm: telefonen ved siden av tastaturet mens du spiller. TV-dashbord: klokke, vær, dagens plan og alle PC-ene (kommer av seg selv på TV-en etter 5 min).</div>
        <div class="row wrap"><button class="soft" id="x-second">🎮 Andreskjerm</button><button class="soft" id="x-tvdash">📺 TV-dashbord</button><button class="soft" id="x-voice">🎙️ Talekommando</button></div>`;
      host.appendChild(c);
    }
    const nf = $("#nf-phone-card");
    if (nf && !document.getElementById("x-watch")) {
      const d = document.createElement("div");
      d.innerHTML = `<div class="label">⌚ Klokka</div><div class="dim small">Varslene fra Kontrollsenter kommer på smartklokka (Wear OS, Galaxy Watch) av seg selv når telefonen viser dem – slå på varsler for ntfy/Kontrollsenter i klokke-appen på telefonen.</div><button class="soft" id="x-watch">Send testvarsel</button>`;
      nf.appendChild(d);
    }
  }
  document.addEventListener("click", (e) => {
    const id = e.target.id;
    if (id === "x-second") window.ksSecondScreen();
    else if (id === "x-tvdash") window.ksTvDash();
    else if (id === "x-voice") window.ksVoiceKey();
    else if (id === "x-watch") act({ a: "watchtest" });
  });
  setTimeout(buttons, 1500);
})();

// ---- lydsirkelen (mobil og TV): dra knappen rundt – lyden flytter seg dit på PC-en ----
(() => {
  const ANG = { FL: -30, FR: 30, FC: 0, RL: -145, RR: 145, FLW: -60, FRW: 60, RC: 180, SL: -100, SR: 100, MONO: 0 };
  let angle = 0, on = false, spin = false, sendT = 0, pend = null, spinT = 0;
  const cv = () => document.getElementById("pan-c");
  const lay = () => (document.getElementById("spk-lay") || {}).value || "2.0";
  const sink = () => (document.getElementById("spk-sink") || {}).value || null;
  function chans() {
    const sel = document.getElementById("spk-lay"); const t = sel && sel.options[sel.selectedIndex];
    const m = { "1.0": ["MONO"], "2.0": ["FL", "FR"], "2.1": ["FL", "FR"], "3.0": ["FL", "FR", "FC"], "3.1": ["FL", "FR", "FC"], "4.0": ["FL", "FR", "RL", "RR"], "4.1": ["FL", "FR", "RL", "RR"],
      "5.0": ["FL", "FR", "FC", "RL", "RR"], "5.1": ["FL", "FR", "FC", "RL", "RR"], "6.0": ["FL", "FR", "FC", "RC", "SL", "SR"], "6.1": ["FL", "FR", "FC", "RC", "SL", "SR"],
      "7.0": ["FL", "FR", "FC", "RL", "RR", "SL", "SR"], "7.1": ["FL", "FR", "FC", "RL", "RR", "SL", "SR"], "5.1.2": ["FL", "FR", "FC", "RL", "RR"], "5.1.4": ["FL", "FR", "FC", "RL", "RR"],
      "7.1.2": ["FL", "FR", "FC", "RL", "RR", "SL", "SR"], "9.0": ["FL", "FR", "FC", "RL", "RR", "FLW", "FRW", "SL", "SR"], "9.1": ["FL", "FR", "FC", "RL", "RR", "FLW", "FRW", "SL", "SR"] };
    return m[t ? t.value : "2.0"] || ["FL", "FR"];
  }
  function draw() {
    const c = cv(); if (!c) return;
    const g = c.getContext("2d"), w = c.width, h = c.height, cx = w / 2, cy = h / 2, r = w / 2 - 44;
    g.clearRect(0, 0, w, h);
    g.fillStyle = "rgba(128,128,150,.12)"; g.beginPath(); g.arc(cx, cy, r + 18, 0, 7); g.fill();
    g.strokeStyle = "rgba(160,160,180,.5)"; g.lineWidth = 2; g.beginPath(); g.arc(cx, cy, r, 0, 7); g.stroke();
    g.font = "11px sans-serif"; g.textAlign = "center"; g.fillStyle = getComputedStyle(document.body).color;
    chans().forEach((k) => { const a = ANG[k] * Math.PI / 180;
      g.beginPath(); g.arc(cx + Math.sin(a) * r, cy - Math.cos(a) * r, 5, 0, 7); g.fill();
      g.fillText(k === "MONO" ? "Mono" : k, cx + Math.sin(a) * (r + 18), cy - Math.cos(a) * (r + 18) + 4); });
    g.font = "24px sans-serif"; g.fillText("🧑", cx, cy + 8);
    const a = angle * Math.PI / 180, kx = cx + Math.sin(a) * r, ky = cy - Math.cos(a) * r;
    const acc = getComputedStyle(document.documentElement).getPropertyValue("--acc").trim() || "#5b8cff";
    g.globalAlpha = on ? .3 : .15; g.fillStyle = acc; g.beginPath(); g.arc(kx, ky, 24, 0, 7); g.fill();
    g.globalAlpha = 1; g.fillStyle = on ? acc : "#8a90a6"; g.beginPath(); g.arc(kx, ky, 15, 0, 7); g.fill();
    g.fillStyle = "#fff"; g.beginPath(); g.arc(kx, ky, 5, 0, 7); g.fill();
    const l = document.getElementById("pan-l"); if (l) l.textContent = on ? `${Math.round(angle)}°` : "";
  }
  function send(extra) {
    pend = { a: "lydpan", layout: lay(), sink: sink(), angle, ...(extra || {}) };
    if (sendT) return;
    sendT = setTimeout(() => { sendT = 0; const p = pend; pend = null; api("/api/action", p).catch(() => {}); }, 80);
  }
  function at(x, y) {
    const c = cv(), rc = c.getBoundingClientRect(), sx = c.width / rc.width;
    const dx = (x - rc.left) * sx - c.width / 2, dy = (y - rc.top) * sx - c.height / 2;
    if (dx * dx + dy * dy < 100) return;
    angle = Math.atan2(dx, -dy) * 180 / Math.PI; stopSpin(); on = true; send(); draw();
  }
  function stopSpin() { spin = false; clearInterval(spinT); const b = document.getElementById("pan-spin"); if (b) b.classList.remove("on"); }
  function bind() {
    const c = cv(); if (!c || c._b) return; c._b = true;
    c.addEventListener("pointerdown", (e) => { c.setPointerCapture(e.pointerId); c._down = true; at(e.clientX, e.clientY); e.preventDefault(); });
    c.addEventListener("pointermove", (e) => { if (c._down) { at(e.clientX, e.clientY); e.preventDefault(); } });
    c.addEventListener("pointerup", () => (c._down = false));
    c.addEventListener("keydown", (e) => {                       // TV: piltastene drar knappen rundt
      const d = { ArrowRight: 15, ArrowUp: 15, ArrowLeft: -15, ArrowDown: -15 }[e.key];
      if (d) { angle = ((angle + d + 540) % 360) - 180; stopSpin(); on = true; send(); draw(); e.preventDefault(); e.stopPropagation(); }
      else if (e.key === "Enter" || e.keyCode === 23) { document.getElementById(on ? "pan-stop" : "pan-go").click(); e.preventDefault(); }
    });
    document.getElementById("pan-go").onclick = () => { on = true; send(); draw(); };
    document.getElementById("pan-stop").onclick = () => { on = false; stopSpin(); clearTimeout(sendT); sendT = 0; api("/api/action", { a: "lydpan", on: false }).catch(() => {}); draw(); };
    document.getElementById("pan-spin").onclick = (e) => {
      if (spin) { stopSpin(); send({ spin: false }); return; }
      spin = true; on = true; e.target.classList.add("on"); send({ spin: true });
      spinT = setInterval(() => { angle = ((angle + 72 * 0.1 + 540) % 360) - 180; draw(); }, 100);   // samme fart som på PC-en
    };
    const sel = document.getElementById("spk-lay"); if (sel) sel.addEventListener("change", draw);
    draw();
  }
  setTimeout(bind, 2500);
  document.addEventListener("click", (e) => { if (e.target.closest && e.target.closest('[data-spk="stop"]')) { on = false; stopSpin(); draw(); } });
})();

// ---- Drivere: hovedkortets driverside (åpnes i nettleseren) og skjermkortdriveren ----
(() => {
  async function load() {
    const s = $("#kontroll"), host = s && (s.querySelector(":scope > .grid") || s); if (!host) return;
    let d; try { d = await api("/api/x/drivers"); } catch (e) { return; }
    let c = document.getElementById("c-drivers");
    if (!c) { c = document.createElement("div"); c.className = "card"; c.id = "c-drivers"; host.appendChild(c); }
    const g = d.gpu || {};
    c.innerHTML = `<h2>🧩 Drivere</h2><div class="small">${esc(d.board || "Hovedkort")}</div><div class="dim small">${esc(d.bios || "")}</div>
      <a class="btn primary" href="${esc(d.url)}" target="_blank" rel="noopener" style="display:inline-block;margin:8px 0">🌐 Åpne driversiden</a>
      ${g.gpu ? `<div class="dim small">${esc(g.gpu)} · driver ${esc(g.driver || "?")} – ${esc(g.where || "")}</div>` : ""}`;
  }
  setTimeout(load, 3000);
})();

// ---- automatisk oppdatering av Kontrollsenter når PC-en starter (bryter, samme som på PC-en) ----
(() => {
  async function load() {
    const card = [...document.querySelectorAll("#system .card")].find((c) => (c.querySelector("h2") || {}).textContent === "PC-en");
    if (!card) return;
    let d; try { d = await api("/api/x/selfupd"); } catch (e) { return; }
    let row = document.getElementById("su-row");
    if (!row) {
      row = document.createElement("div"); row.id = "su-row";
      row.innerHTML = `<div class="row"><span style="flex:1">Oppdater Kontrollsenter automatisk når PC-en starter</span><label class="switch"><input type="checkbox" id="su-on"><i></i></label></div>
        <div class="dim small">Finnes det en ny versjon, installeres den og Kontrollsenter starter på nytt av seg selv. Venter hvis noen spiller.</div>`;
      card.appendChild(row);
      $("#su-on").onchange = (e) => act({ a: "selfupd", on: e.target.checked });
    }
    $("#su-on").checked = !!d.on;
  }
  setTimeout(load, 3000);
})();
