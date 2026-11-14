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
  if (th === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = th;
  $$("#theme button").forEach((b) => b.classList.toggle("on", b.dataset.v === th));
  document.body.classList.toggle("simple", !!pref("simple", false));
  $("#simple").checked = !!pref("simple", false);
  $("#auto-second").checked = !!pref("auto_second", true);
  $("#bio").checked = !!pref("bio", true);
  $("#bio-note").textContent = KS && KS.authenticate ? "" : "Krever Android-appen (versjon 0.9 eller nyere).";
  applyLang();
}
$$("#theme button").forEach((b) => (b.onclick = () => { setPref("theme", b.dataset.v); applyLook(); if (KS && KS.setTheme) KS.setTheme(b.dataset.v); }));
$("#simple").onchange = () => { setPref("simple", $("#simple").checked); applyLook(); };
$("#auto-second").onchange = () => setPref("auto_second", $("#auto-second").checked);
$("#bio").onchange = () => setPref("bio", $("#bio").checked);

const EN = {
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
};
const NB = {};
function applyLang() {
  const en = pref("lang", "nb") === "en";
  $$("#lang button").forEach((b) => b.classList.toggle("on", b.dataset.v === (en ? "en" : "nb")));
  document.documentElement.lang = en ? "en" : "nb";
  $$("h2, button, .label, #tabs button").forEach((el) => {
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
    const bad = h.items.filter((i) => i.level !== "ok");
    $("#health-sum").textContent = bad.length ? `${bad.length} ting bør sjekkes` : "Alt ser bra ut ✓";
    $("#health-items").innerHTML = bad.map((i) => `<p class="small"><b>${i.level === "error" ? "❌" : "⚠️"} ${esc(i.title)}</b><br><span class="dim">${esc(String(i.detail).slice(0, 200))}</span></p>`).join("");
  } catch (e) { $("#health-sum").textContent = e.message; }
}
$("#health-refresh").onclick = () => { $("#health-sum").textContent = "Sjekker …"; loadHealth(true); };
$("#health-open").onclick = () => act({ a: "syscheck" });

// ---------- spillmodus (14) og avslåing (20) ----------
$("#gm-on").onchange = () => { holdFor("gm", 6000); act({ a: "gamemode", on: $("#gm-on").checked, color: $("#gm-color").value }); };
$$("[data-timer]").forEach((b) => (b.onclick = () => {
  const v = b.dataset.timer;
  act({ a: "timer", minutes: /^\d+$/.test(v) ? +v : null, when_idle: v === "idle" });
}));
function renderExtraStatus(s) {
  if (!held("gm")) $("#gm-on").checked = !!s.gamemode;
  const t = s.timer || {};
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
      return `<div class="kvgrid"><div><b>${esc(x.key)}</b><span>level ${x.target} innen ${by}</span></div>
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

// ---------- kobling til fanene ----------
const baseSetTab = setTab;
setTab = function (t) {                              // eslint-disable-line no-global-assign
  baseSetTab(t);
  $("#mer").hidden = t !== "mer" || !token;
  if (t === "mer") { loadEvents(); loadEnergy(); loadNetwork(); loadMedia(); loadProcs(); loadNas(); }
  if (t === "spill") { loadPlaytime(); loadCs2(); loadGoals(); }
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
