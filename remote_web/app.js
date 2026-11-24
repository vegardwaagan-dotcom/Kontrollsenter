// Kontrollsenter – kontrollpanel for mobil og nettbrett. Snakker med Kontrollsenter på PC-en (/api/…).
"use strict";
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const KS = window.KS || null;                 // Android-appen: KS.home() går tilbake til PC-listen
let token = localStorage.getItem("ks_token") || "";
let pcName = "";                               // nøkkelen lagres i appen per PC – virker hjemme og via Tailscale
const saveToken = (t) => { token = t; try { localStorage.setItem("ks_token", t); } catch (e) {}
  if (KS && KS.setToken && pcName) KS.setToken(pcName, t); };
let tab = "oversikt", last = null, hold = {}, failures = 0, histRange = 3600, gamesCache = null;

// ---------- hjelpere ----------
function toast(t) {
  const el = $("#toast"); el.textContent = t; el.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (el.hidden = true), 2600);
}
function confirmDlg(text) {
  return new Promise((res) => {
    $("#dlg-t").textContent = text; $("#dlg").hidden = false;
    const done = (v) => { $("#dlg").hidden = true; res(v); };
    $("#dlg-yes").onclick = () => done(true); $("#dlg-no").onclick = () => done(false);
  });
}
// offline: siste svar for hver side lagres, og vises (med en linje øverst) når PC-en ikke svarer
function offlineBar(t) {
  let b = document.getElementById("offline-bar");
  if (!t) { if (b) b.remove(); return; }
  if (!b) { b = document.createElement("div"); b.id = "offline-bar";
    b.style.cssText = "position:fixed;left:8px;right:8px;top:calc(env(safe-area-inset-top) + 4px);z-index:9997;padding:6px 12px;border-radius:12px;background:#c88800;color:#fff;font-size:13px;text-align:center";
    document.body.append(b); }
  b.textContent = "📴 PC-en svarer ikke – viser det som var kl. " + new Date(t).toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
}
async function api(path, body) {
  const opt = { headers: { Authorization: "Bearer " + token } };
  if (body !== undefined) { opt.method = "POST"; opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const ctl = new AbortController(); const tm = setTimeout(() => ctl.abort(), 8000); opt.signal = ctl.signal;
  const ck = "ks_c:" + (pcName || "") + ":" + path;
  let r;
  try {
    r = await fetch(path, opt);
  } catch (e) {                                       // nettverksfeil: bruk det vi har lagret (bare lesing)
    clearTimeout(tm);
    if (body === undefined) { try { const c = JSON.parse(localStorage.getItem(ck) || "null"); if (c) { offlineBar(c.t); return c.j; } } catch (x) {} }
    throw e;
  }
  try {
    if (r.status === 401) { showPair(); throw new Error("ikke paret"); }
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    offlineBar(0);
    if (body === undefined) { try { const txt = JSON.stringify({ t: Date.now(), j }); if (txt.length < 150000) localStorage.setItem(ck, txt); } catch (x) {} }
    return j;
  } finally { clearTimeout(tm); }
}
async function act(body, quiet) {
  try {
    const r = await api("/api/action", body);
    if (!quiet || !r.ok) toast(r.ok ? r.msg : "Feil: " + (r.msg || "ukjent"));
    setTimeout(poll, 400);
    return r;
  } catch (e) { toast("Feil: " + e.message); }
}
const held = (k) => (hold[k] || 0) > Date.now();
const holdFor = (k, ms = 4000) => (hold[k] = Date.now() + ms);
const fmtB = (n) => { if (n == null) return "–"; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < 4) { n /= 1024; i++; } return (i < 2 ? n.toFixed(0) : n.toFixed(1)) + " " + u[i]; };
const fmtR = (n) => fmtB(n) + "/s";
const tcls = (t) => (t >= 85 ? "t-bad" : t >= 70 ? "t-warn" : "t-ok");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtUp = (s) => { const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return (d ? d + " d " : "") + (h ? h + " t " : "") + m + " min"; };

// ---------- faner ----------
function setTab(t) {
  tab = t;
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  ["oversikt", "kontroll", "spill", "mer", "system"].forEach((id) => ($("#" + id).hidden = id !== t || !token));
  if (t === "kontroll") loadHistory();
  window.scrollTo(0, 0);
  if (t === "spill") loadGames();
  if (t === "kontroll") pollExtra();
  try { sessionStorage.setItem("ks_tab", t); } catch (e) {}
}
$$("#tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));

// ---------- paring ----------
function showPair() {
  saveToken(""); localStorage.removeItem("ks_token");
  $$(".page").forEach((p) => (p.hidden = true)); $("#tabs").hidden = true; $("#pair").hidden = false;
  if (!$("#pair-name").value) $("#pair-name").value = (KS && KS.model && KS.model()) || (/Android/.test(navigator.userAgent) ? "Android-enhet" : "Nettleser");
  $("#pair-code").focus();
}
$("#pair-go").onclick = async () => {
  const code = $("#pair-code").value.replace(/\D/g, "");
  if (code.length !== 6) { $("#pair-msg").textContent = "Koden har 6 siffer"; return; }
  $("#pair-msg").textContent = "Parer …";
  try {
    const r = await fetch("/api/pair", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, device: $("#pair-name").value }) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "feilet");
    pcName = j.name || pcName; saveToken(j.token);
    $("#pair").hidden = true; $("#tabs").hidden = false; setTab("oversikt"); poll();
    toast("Paret med " + j.name + " ✓");
  } catch (e) { $("#pair-msg").textContent = e.message; }
};
$("#pair-code").addEventListener("keydown", (e) => e.key === "Enter" && $("#pair-go").click());
$("#unpair").onclick = async () => { if (await confirmDlg("Glemme paringen på denne enheten?")) showPair(); };

// ---------- oversikt ----------
function gauge(pct, color) {
  const r = 52, c = 2 * Math.PI * r, arc = c * 0.75, v = Math.max(0, Math.min(1, pct / 100));
  return `<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--card2)" stroke-width="11"
    stroke-dasharray="${arc} ${c}" stroke-linecap="round"/><circle cx="60" cy="60" r="${r}" fill="none" stroke="${color}"
    stroke-width="11" stroke-dasharray="${arc * v} ${c}" stroke-linecap="round"/></svg>`;
}
const colFor = (p, warn = 70, bad = 85) => (p >= bad ? "var(--bad)" : p >= warn ? "var(--warn)" : "var(--ok)");
function tile(name, pct, val, sub, color, k) {
  return { k, html: `<div class="name">${esc(name)}</div><div class="gauge">${gauge(pct, color)}<div class="v">${esc(val)}</div></div><div class="sub">${esc(sub)}</div>` };
}
const ksHist = { cpu: [], gpu: [] };
function spark(arr, color) {
  if (arr.length < 2) return "";
  const n = arr.length - 1, pts = arr.map((v, i) => `${(100 * i / n).toFixed(1)},${(22 - 20 * Math.min(1, (v || 0) / 100)).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 100 24" preserveAspectRatio="none"><polyline points="0,24 ${pts} 100,24" fill="${color}" opacity=".18"/><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
}
function itile(name, icon, val, sub, k) {
  return { k, html: `<div class="name">${esc(name)}</div><div class="iv"><span class="ii">${icon}</span><b>${esc(val)}</b></div><div class="sub">${esc(sub)}</div>` };
}
function renderOverview(s) {
  const t = [];
  const c = s.cpu || {};
  t.push(tile("CPU", c.load || 0, Math.round(c.load || 0) + " %",
    [c.temp != null ? Math.round(c.temp) + " °C" : null, c.freq ? c.freq.toFixed(2) + " GHz" : null].filter(Boolean).join(" · "), "var(--c1)", "cpu"));
  if (s.gpu) t.push(tile("GPU", s.gpu.util || 0, Math.round(s.gpu.util || 0) + " %",
    [s.gpu.temp != null ? Math.round(s.gpu.temp) + " °C" : null, s.gpu.power != null ? Math.round(s.gpu.power) + " W" : null].filter(Boolean).join(" · "), "var(--c2)", "gpu"));
  if (s.mem) { const p = (100 * s.mem[0]) / s.mem[1]; t.push(tile("Minne", p, Math.round(p) + " %", fmtB(s.mem[0]) + " av " + fmtB(s.mem[1]), colFor(p, 80, 92), "mem")); }
  const hot = Math.max(...(s.temps || []).map((x) => x[2]), c.temp || 0, (s.gpu && s.gpu.temp) || 0);
  if (hot > 0) t.push(tile("Varmest", hot, Math.round(hot) + "°", "høyeste temperatur", colFor(hot), "hot"));
  if (s.watts) t.push(tile("Strøm", Math.min(100, s.watts / 6), s.watts + " W", "anslått forbruk", "var(--c3)", "watt"));
  if (s.home) { const p = (100 * s.home[0]) / s.home[1]; t.push(tile("Disk", p, Math.round(p) + " %", fmtB(s.home[1] - s.home[0]) + " ledig", colFor(p, 80, 90), "disk")); }
  if (s.net) { const short = fmtB(s.net[0]).replace(/(\d+)\.\d (MB|GB|KB)/, (m, a, u) => (+a >= 10 ? a : m.split(" ")[0]) + " " + u);
    t.push(tile("Nett", Math.min(100, (s.net[0] / 12.5e6) * 100), short, "↓ " + fmtR(s.net[0]) + " · ↑ " + fmtR(s.net[1]), "var(--c1)", "net")); }
  if (s.battery && s.battery.length) t.push(tile("Batteri", s.battery[0], Math.round(s.battery[0]) + " %", s.battery[1] || "", colFor(100 - s.battery[0], 70, 85), "bat"));
  const c0 = s.cpu || {};
  ksHist.cpu.push(c0.load || 0); ksHist.cpu.splice(0, ksHist.cpu.length - 60);
  if (s.gpu) { ksHist.gpu.push(s.gpu.util || 0); ksHist.gpu.splice(0, ksHist.gpu.length - 60); }
  t.forEach((x) => { if (x.k === "cpu") x.html += spark(ksHist.cpu, "var(--c1)"); if (x.k === "gpu") x.html += spark(ksHist.gpu, "var(--c2)"); });
  const I = s.info || {};
  if (I.ping) t.push(itile("Ping", "📶", I.ping.ms != null ? I.ping.ms + " ms" : "–", I.ping.ms != null ? "til internett" : "ingen kontakt", "ping"));
  if (s.net) t.push(itile("Nedlasting", "⬇️", fmtR(s.net[0]), "↑ " + fmtR(s.net[1]), "down"));
  if (I.play_s != null) t.push(itile("Spilt i dag", "🎮", Math.floor(I.play_s / 3600) + " t " + Math.floor(I.play_s % 3600 / 60) + " min", s.game ? "▶ " + s.game : "ingen spill nå", "play"));
  if (I.price) t.push(itile("Strømpris", "⚡", I.price.now != null ? I.price.now.toFixed(2) + " kr" : "–", I.price.now != null ? "per kWh · billigst kl. " + (I.price.cheapest_at || "–") : "får ikke hentet", "price"));
  if (I.weather) t.push(itile("Været", I.weather.icon || "🌡️", I.weather.temp != null ? I.weather.temp + "°" : "–", I.weather.temp != null ? (I.weather.place || "").split(",")[0] + " · " + (I.weather.text || "") : "velg sted på PC-en", "weather"));
  if (I.cal) { const e = (I.cal.events || [])[0]; t.push(itile("Neste avtale", "📅", e ? e.title : "–", e ? e.when : (I.cal.error ? "legg inn kalender på PC-en" : "ingen avtaler"), "cal")); }
  if (window.dashTiles) dashTiles(t);
  if (window.dashGame) dashGame(!!s.game);
  const rows = (s.temps || []).slice();          // PC-en tar allerede med NVIDIA-temperaturen
  $("#temps").innerHTML = rows.map(([d, l, v]) => `<div><span class="d">${esc(d)}</span><span class="l">${esc(l)}</span><span class="num ${tcls(v)}">${Math.round(v)} °C</span></div>`).join("") || '<span class="dim">Ingen temperaturer</span>';
  const info = [["PC", s.name], ["Maskin", s.model], ["System", s.distro], ["Kontrollsenter", s.version], ["Oppetid", fmtUp(s.uptime || 0)],
    ["Spill nå", s.game || "–"], s.gpu ? ["Skjermkort", s.gpu.name] : null, s.gpu && s.gpu.mem_total ? ["VRAM", (s.gpu.mem_used / 1024).toFixed(1) + " / " + (s.gpu.mem_total / 1024).toFixed(1) + " GB"] : null].filter(Boolean);
  $("#info").innerHTML = info.map(([k, v]) => `<div><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("");
}

// ---------- kontroll ----------
function renderControls(s) {
  // strømmodus
  $("#c-power").hidden = !s.power;
  if (s.power && !held("power")) {
    $("#power").innerHTML = s.power.modes.map(([k, n]) => `<button data-k="${esc(k)}" class="${k === s.power.active ? "on" : ""}">${esc(n)}</button>`).join("");
    $$("#power button").forEach((b) => (b.onclick = () => { holdFor("power"); $$("#power button").forEach((x) => x.classList.toggle("on", x === b)); act({ a: "power", mode: b.dataset.k }); }));
  }
  // vifter
  const f = s.fans;
  $("#c-fans").hidden = !f;
  if (f && !held("fans")) {
    $$("#fan-all button").forEach((b) => b.classList.toggle("on", fanAllOn(f, b.dataset.v)));
    $("#fans").innerHTML = f.rows.map((r) => `<div class="fan" data-k="${esc(r.key)}"><div class="h"><span>${esc(r.name)}</span><span class="dim num">${esc(r.rpm)}</span></div>
      <div class="r"><label class="switch"><input type="checkbox" class="fa" ${r.value === "auto" ? "checked" : ""}><i></i></label><span class="small dim">Auto</span>
      <input type="range" min="${r.min}" max="100" value="${r.value === "auto" ? 50 : r.value}" ${r.value === "auto" ? "disabled" : ""}><span class="num">${r.value === "auto" ? "auto" : r.value + " %"}</span></div></div>`).join("");
    $$("#fans .fan").forEach((el) => {
      const key = el.dataset.k, sl = el.querySelector("input[type=range]"), au = el.querySelector(".fa"), lab = el.querySelector(".r .num");
      au.onchange = () => { holdFor("fans"); sl.disabled = au.checked; lab.textContent = au.checked ? "auto" : sl.value + " %"; act({ a: "fans", key, value: au.checked ? "auto" : +sl.value }, true); };
      sl.oninput = () => { holdFor("fans"); lab.textContent = sl.value + " %"; };
      sl.onchange = () => { holdFor("fans"); act({ a: "fans", key, value: +sl.value }, true); };
    });
  }
  // overlay
  $("#c-ov").hidden = s.overlay == null;
  if (s.overlay != null && !held("ov")) $("#ov").checked = s.overlay;
  $("#c-msi").hidden = !s.msi;
}
// én knapp for alle viftene er «på» når alle viftene står slik (Kurve når kurven styrer)
function fanAllOn(f, v) {
  if (v === "curve") return !!f.curve;
  return !f.curve && f.rows.length > 0 && f.rows.every((r) => String(r.value) === v);
}
$$("#fan-all button").forEach((b) => (b.onclick = () => { holdFor("fans", 1500); const v = b.dataset.v;
  $$("#fan-all button").forEach((x) => x.classList.toggle("on", x === b)); act({ a: "fans", value: /^\d+$/.test(v) ? +v : v }); }));
$("#ov").onchange = () => { holdFor("ov"); act({ a: "overlay", on: $("#ov").checked }); };

// lyd
let volTimer = 0;
$("#vol").oninput = () => { holdFor("vol"); $("#vol-v").textContent = $("#vol").value + " %";
  clearTimeout(volTimer); volTimer = setTimeout(() => act({ a: "volume", volume: +$("#vol").value }, true), 150); };
$("#mute").onclick = () => { holdFor("vol"); const m = !$("#mute").classList.contains("on"); $("#mute").classList.toggle("on", m); $("#mute-x").style.display = m ? "" : "none"; act({ a: "volume", mute: m }, true); };

// RGB
const SW = ["#ff0000", "#ff7a00", "#ffd000", "#00ff40", "#00e5ff", "#0050ff", "#a020ff", "#ffffff"];
$("#swatches").innerHTML = SW.map((c) => `<button style="background:${c}" data-c="${c}"></button>`).join("");
$$("#swatches button").forEach((b) => (b.onclick = () => { $("#rgb-color").value = b.dataset.c; act({ a: "rgb", mode: "color", color: b.dataset.c }); }));
$("#rgb-set").onclick = () => act({ a: "rgb", mode: "color", color: $("#rgb-color").value });
$("#rgb-off").onclick = () => act({ a: "rgb", mode: "off" });
$("#rgb-restore").onclick = () => act({ a: "rgb", mode: "restore" });

// MSI
$("#msi-boost").onchange = () => { holdFor("msi", 8000); act({ a: "msi", boost: $("#msi-boost").checked }); };
let lastMute = false;
function renderExtra(x) {
  const a = x.audio;
  $("#c-audio").hidden = !a || a.ok === false;
  if (a && a.ok !== false && !held("vol")) {
    $("#vol").value = a.volume; $("#vol-v").textContent = a.volume + " %"; $("#audio-dev").textContent = a.device || "";
    $("#mute").classList.toggle("on", !!a.mute); $("#mute-x").style.display = a.mute ? "" : "none";
  }
  if (a && a.ok !== false) { lastMute = !!a.mute; if (typeof deckState === "function" && last) deckState(last); }
  const m = x.msi;
  if (!m) return;
  if (m.ok === false) { $("#msi-msg").textContent = m.error || ""; return; }
  $("#msi-msg").textContent = "";
  if (held("msi")) return;
  $("#msi-sc").innerHTML = m.scenarios.map(([k, n]) => `<button data-k="${esc(k)}" class="${k === m.scenario ? "on" : ""}">${esc(n)}</button>`).join("");
  $$("#msi-sc button").forEach((b) => (b.onclick = () => { holdFor("msi", 8000); $$("#msi-sc button").forEach((x) => x.classList.toggle("on", x === b)); act({ a: "msi", scenario: b.dataset.k }); }));
  $("#msi-ch").innerHTML = m.charges.map((c) => `<button data-c="${c}" class="${c === m.charge ? "on" : ""}">${c} %</button>`).join("");
  $$("#msi-ch button").forEach((b) => (b.onclick = () => { holdFor("msi", 8000); $$("#msi-ch button").forEach((x) => x.classList.toggle("on", x === b)); act({ a: "msi", charge: +b.dataset.c }); }));
  $("#msi-boost").checked = !!m.boost;
}

// ---------- historikk ----------
$$("#range button").forEach((b) => (b.onclick = () => { histRange = +b.dataset.s; $$("#range button").forEach((x) => x.classList.toggle("on", x === b)); loadHistory(); }));
function chart(cv, rows, idx, colors, max) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement);
  const vals = rows.flatMap((r) => idx.map((i) => r[i])).filter((v) => v != null);
  const top = max || Math.max(10, Math.ceil((Math.max(...vals, 0) * 1.1) / 10) * 10);
  g.strokeStyle = css.getPropertyValue("--line"); g.fillStyle = css.getPropertyValue("--dim"); g.font = "12px system-ui"; g.lineWidth = 1;
  for (let k = 0; k <= 4; k++) { const y = 6 + ((h - 26) * k) / 4; g.beginPath(); g.moveTo(34, y); g.lineTo(w, y); g.stroke(); g.fillText(Math.round(top - (top * k) / 4), 0, y + 4); }
  if (rows.length < 2) return;
  const t0 = rows[0][0], t1 = rows[rows.length - 1][0];
  idx.forEach((i, n) => {
    g.strokeStyle = css.getPropertyValue(colors[n]); g.lineWidth = 2; g.beginPath(); let started = false;
    rows.forEach((r) => { if (r[i] == null) { started = false; return; }
      const x = 34 + ((w - 36) * (r[0] - t0)) / Math.max(1, t1 - t0), y = 6 + (h - 26) * (1 - r[i] / top);
      if (!started) { g.moveTo(x, y); started = true; } else g.lineTo(x, y); });
    g.stroke();
  });
  g.fillStyle = css.getPropertyValue("--dim");
  const lab = (t) => new Date(t * 1000).toLocaleString("nb-NO", histRange > 86400 ? { weekday: "short", hour: "2-digit" } : { hour: "2-digit", minute: "2-digit" });
  g.fillText(lab(t0), 34, h - 4); const e = lab(t1); g.fillText(e, w - g.measureText(e).width, h - 4);
}
async function loadHistory() {
  try {
    const r = await api("/api/history?s=" + histRange);
    chart($("#h-temp"), r.rows, [1, 2], ["--c1", "--c2"]);
    chart($("#h-load"), r.rows, [3, 4], ["--c1", "--c2"], 100);
    chart($("#h-watt"), r.rows, [5], ["--c3"]);
  } catch (e) { toast("Historikk: " + e.message); }
}

// ---------- spillstatistikk ----------
const nfmt = (v) => (typeof v === "number" ? v.toLocaleString("nb-NO") : esc(v));
const kv = (rows) => `<div class="kvgrid">${rows.map(([k, v]) => `<div><b>${esc(k)}</b><span>${nfmt(v)}</span></div>`).join("")}</div>`;
let statItems = [], wowTab = "s";
async function loadStats() {
  try {
    const d = await api("/api/gamestats");
    const multi = (d.accounts || []).length > 1;
    statItems = [];
    const CLS = { warrior: "⚔️", paladin: "🛡️", hunter: "🏹", rogue: "🗡️", priest: "✨", shaman: "⚡", mage: "🔮", warlock: "💀",
      druid: "🌿", "death knight": "❄️", monk: "🥋", "demon hunter": "😈", evoker: "🐉" };
    const realm = (r) => String(r || "").replace(/^CAMWOW\s+EU\d*\s*/i, "").trim();
    const groups = [];
    const wow = (d.wow || []).map((c) => {
      const it = { name: c.char || c.title, kind: "wow", o: c, icon: CLS[String(c.cls || "").toLowerCase()] || "🗡️",
        sub: [c.level ? "Level " + c.level : "", [c.race, c.cls].filter(Boolean).join(" "), realm(c.realm)].filter(Boolean).join(" · ") };
      statItems.push(it); return it;
    });
    if ((d.wow_hints || []).length) { const it = { name: "Venter på tall fra WoW", kind: "hint", o: d.wow_hints, icon: "⏳", sub: "Logg ut eller skriv /reload i spillet" }; statItems.push(it); wow.push(it); }
    if (wow.length) groups.push(["World of Warcraft", wow]);
    const rank = (g) => (g.highlights.length ? 0 : g.stats.length ? 1 : 2);   // mest statistikk først
    (d.accounts || []).forEach((a) => {
      const items = a.games.filter((g) => g.stats.length || g.highlights.length || g.playtime_min)
        .sort((x, y) => rank(x) - rank(y) || (y.playtime_min || 0) - (x.playtime_min || 0)).map((g) => {
          const h = (g.playtime_min || 0) / 60;
          const it = { name: g.name, kind: "steam", o: g, icon: g.appid === "730" ? "🎯" : "🎮",
            img: /^\d+$/.test(g.appid) ? `https://cdn.cloudflare.steamstatic.com/steam/apps/${g.appid}/capsule_184x69.jpg` : "",
            sub: [h >= 1 ? h.toFixed(h >= 10 ? 0 : 1) + " timer" : Math.round(h * 60) + " min", g.stats.length ? g.stats.length + " tall" : ""].filter(Boolean).join(" · ") };
          statItems.push(it); return it;
        });
      if (items.length) groups.push([multi ? "Steam · " + a.name : "Steam", items]);
    });
    const keep = $("#stats-sel").value;
    const opt = (it) => `<option value="${statItems.indexOf(it)}" data-icon="${esc(it.icon)}" data-sub="${esc(it.sub || "")}"${it.img ? ` data-img="${esc(it.img)}"` : ""}>${esc(it.name)}</option>`;
    $("#stats-sel").dataset.title = "Velg spill eller figur";
    $("#stats-sel").innerHTML = groups.map(([g, items]) => `<optgroup label="${esc(g)}">${items.map(opt).join("")}</optgroup>`).join("") || "<option>Ingen statistikk ennå</option>";
    if (keep !== "" && statItems[+keep]) $("#stats-sel").value = keep;
    renderStats();
    if (window.renderWowPlus) window.renderWowPlus(d.wowplus);
  } catch (e) { $("#stats").innerHTML = `<p class="dim">${esc(e.message)}</p>`; }
}
function renderStats() {
  const it = statItems[+$("#stats-sel").value];
  if (!it) { $("#stats").innerHTML = '<p class="dim">Spill litt, så dukker statistikken opp her. WoW: logg ut eller skriv /reload.</p>'; return; }
  const o = it.o;
  if (it.kind === "hint") { $("#stats").innerHTML = it.o.map((h) => `<p>• ${esc(h)}</p>`).join(""); return; }
  if (it.kind === "wow") {
    const sheet = o.plus && o.plus.sheet !== undefined;
    const tabs = sheet ? `<div class="seg" id="wt-tabs"><button data-wt="s" class="${wowTab === "s" ? "on" : ""}">Statistikk</button><button data-wt="k" class="${wowTab === "k" ? "on" : ""}">Egenskaper og talenter</button></div>` : "";
    $("#stats").innerHTML = tabs + `<div id="wt-s" ${sheet && wowTab === "k" ? "hidden" : ""}><p class="dim">${esc([o.realm, o.flavor ? "WoW " + o.flavor : ""].filter(Boolean).join(" · ") || o.sub)}</p>${kv(o.rows)}`
      + (o.kills_by.length ? `<h3>Drept mest</h3>${kv(o.kills_by)}` : "")
      + (o.killers.length ? `<h3>Drept av</h3>${kv(o.killers)}` : "")
      + (o.session ? `<h3>Siste økt</h3>${kv(o.session)}` : "")
      + (window.wowPlusHtml ? window.wowPlusHtml(o) : "") + "</div>"
      + (sheet ? `<div id="wt-k" ${wowTab === "k" ? "" : "hidden"}>${window.wowSheetHtml ? window.wowSheetHtml(o.plus.sheet) : ""}</div>` : "")
      + `<p class="dim small">Nye karakterer dukker opp når du har logget inn med dem og logget ut eller skrevet /reload.</p>`
      + (o.key ? `<button class="link" id="wow-hide">Fjern ${esc(o.char || "karakteren")} fra listen (slettet i spillet)</button>` : "");
    if (window.wowPlusAfter) window.wowPlusAfter(o);
    $$("#wt-tabs button").forEach((b) => (b.onclick = () => {
      wowTab = b.dataset.wt;
      $$("#wt-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      $("#wt-s").hidden = wowTab !== "s"; $("#wt-k").hidden = wowTab !== "k";
    }));
    const hb = $("#wow-hide");
    if (hb) hb.onclick = async () => {
      if (!(await confirmDlg(`Fjerne ${o.char} fra WoW-statistikken? Den kommer tilbake hvis du spiller med den igjen.`))) return;
      await act({ a: "wowhide", key: o.key });
      loadStats();
    };
  } else {
    const sub = [(o.playtime_min / 60).toFixed(1) + " timer spilt"];
    if (o.achievements[1]) sub.push(`${o.achievements[0]} / ${o.achievements[1]} prestasjoner`);
    if (o.last_played) sub.push("sist spilt " + new Date(o.last_played * 1000).toLocaleDateString("nb-NO"));
    $("#stats").innerHTML = `<p class="dim">${esc(sub.join(" · "))}</p>` + (o.highlights.length ? kv(o.highlights) : "")
      + (o.stats.length ? `<details><summary>All statistikk fra spillet (${o.stats.length})</summary>${kv(o.stats)}</details>` : "");
  }
}
$("#stats-sel").onchange = renderStats;
// oppdater statistikken for alle spill (WoW, Steam, CS2) – henter ferske tall fra PC-en
$("#stats-ref").onclick = async () => {
  const b = $("#stats-ref");
  if (b.classList.contains("spin")) return;
  b.classList.add("spin");
  try {
    await loadStats();
    if (typeof loadGoals === "function") await loadGoals();
    toast("Statistikken er oppdatert");
  } finally { setTimeout(() => b.classList.remove("spin"), 400); }
};
function renderLive(c) {
  $("#live").hidden = !c;
  if (!c) return;
  const rows = c.mine ? [["Kills", c.kills], ["Dødsfall", c.deaths], ["Assists", c.assists], ["Headshots", `${c.hs} (${c.hs_pct || "–"})`],
    ["Skade", c.dmg], ["ADR", c.adr], ["MVP", c.mvps], ["Liv / rustning", `${c.health} / ${c.armor}`], ["Penger", "$" + c.money],
    ["Våpen", c.weapon ? `${c.weapon} ${c.ammo ?? ""}/${c.ammo_max ?? ""}` : "–"]] : [["Du ser på en annen spiller", ""]];
  $("#live").innerHTML = `<h2>🔴 CS2 live · ${esc(c.map)} · ${esc(c.mode)} · runde ${c.round}</h2>
    <div class="score">CT ${c.ct ?? 0} – ${c.t ?? 0} T</div>${kv(rows)}`;
}

// ---------- spill ----------
async function loadGames() {
  loadStats();
  if (!gamesCache) { try { gamesCache = (await api("/api/games")).games; } catch (e) { toast(e.message); return; } }
  renderGames();
}
function renderGames() {
  const q = $("#game-q").value.toLowerCase();
  const list = (gamesCache || []).filter((g) => g.name.toLowerCase().includes(q));
  $("#games").innerHTML = list.map((g) => `<div class="game"><div><b>${esc(g.name)}</b><span class="dim small">${fmtB(g.size)}</span></div><button class="primary" data-id="${esc(g.appid)}">Spill</button></div>`).join("")
    || '<p class="dim">Fant ingen Steam-spill på PC-en.</p>';
  $$("#games button").forEach((b) => (b.onclick = () => act({ a: "game", appid: b.dataset.id })));
}
$("#game-q").oninput = renderGames;

// ---------- system ----------
$$("[data-sys]").forEach((b) => (b.onclick = async () => {
  if (b.dataset.confirm && !(await confirmDlg(b.dataset.confirm))) return;
  act(b.dataset.sys === "show" ? { a: "show" } : { a: "system", do: b.dataset.sys });
}));

// ---------- henting ----------
async function poll() {
  if (!token || document.hidden) return;
  try {
    const s = await api("/api/status");
    last = s; failures = 0;
    $("#conn").className = "dot ok";
    $("#pc-name").textContent = s.name || "PC";
    $("#paired-pc").textContent = s.name || "PC";
    $("#pc-sub").textContent = [s.model, s.game ? "🎮 " + s.game : null].filter(Boolean).join(" · ");
    renderOverview(s); renderControls(s); renderLive(s.cs2);
  } catch (e) {
    failures++;
    $("#conn").className = "dot " + (failures > 2 ? "bad" : "");
    if (failures > 2) $("#pc-sub").textContent = "Får ikke kontakt med PC-en – er den på og koblet til hjemmenettet?";
  }
}
async function pollExtra() {
  if (!token || document.hidden) return;
  try { renderExtra(await api("/api/extra")); } catch (e) { /* vises ved neste forsøk */ }
}
if (KS) { $("#btn-pcs").hidden = false; $("#btn-pcs").onclick = () => KS.home(); }

// ---------- oppdatering av Android-appen (NAS-en via PC-en) ----------
const appCode = () => (KS && KS.versionCode ? Number(KS.versionCode()) : 0);
window.ksUpdateStatus = (m) => { $("#upd-t").textContent = m; $("#upd-msg").textContent = m; toast(m); };
async function checkAppUpdate(force) {
  if (!KS) { $("#app-ver").textContent = "Åpnet i nettleser – appen finnes for Android"; return; }
  $("#app-ver").textContent = "Versjon " + (KS.version ? KS.version() : "?");
  try {
    const r = await (await fetch("/api/appupdate" + (force ? "?force=1" : ""), { cache: "no-store" })).json();
    const have = appCode();
    if (r.code && (!KS.versionCode || r.code > have)) {
      $("#upd").hidden = false;
      if (KS.update) {
        $("#upd-t").textContent = `Ny versjon av appen: ${r.version}`;
        $("#upd-go").hidden = false;
        $("#upd-go").onclick = () => KS.update(location.origin + "/api/apk");
      } else {           // eldre app uten oppdateringsfunksjon: installer den nye én gang manuelt
        $("#upd-t").textContent = `Ny app ${r.version}: åpne ${location.origin}/api/apk i nettleseren og installer den (bare denne ene gangen)`;
        $("#upd-go").hidden = true;
      }
      $("#upd-msg").textContent = `Versjon ${r.version} er tilgjengelig`;
    } else {
      $("#upd").hidden = true;
      $("#upd-msg").textContent = force ? "Appen er oppdatert ✓" : "";
    }
  } catch (e) { if (force) $("#upd-msg").textContent = "Kunne ikke sjekke: " + e.message; }
}
$("#upd-check").onclick = () => { $("#upd-msg").textContent = "Sjekker NAS-en …"; checkAppUpdate(true); };
if (KS && KS.githubLatest) {                 // appen: hent nyeste versjon rett fra GitHub
  $("#upd-gh").hidden = false;
  $("#upd-gh").onclick = async () => {
    $("#upd-msg").textContent = "Sjekker GitHub …";
    await new Promise((ok) => setTimeout(ok, 30));
    let r = {}; try { r = JSON.parse(KS.githubLatest()); } catch (e) { r = { error: e.message }; }
    if (r.error) { $("#upd-msg").textContent = "GitHub: " + r.error; return; }
    if (r.code > appCode()) { $("#upd-msg").textContent = `Laster ned ${r.version} fra GitHub …`; KS.update(r.url); }
    else $("#upd-msg").textContent = `Appen er oppdatert ✓ (nyeste på GitHub: ${r.version})`;
  };
}
setInterval(() => checkAppUpdate(false), 30 * 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) checkAppUpdate(false); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) { poll(); pollExtra(); } });
window.addEventListener("resize", () => tab === "kontroll" && loadHistory());
setInterval(() => poll(), 2000);
setInterval(() => tab === "kontroll" && pollExtra(), 8000);

(async function start() {
  try { const h = await (await fetch("/api/hello")).json(); $("#pc-name").textContent = h.name; pcName = h.name; } catch (e) {}
  if (KS && KS.getToken && pcName) {
    const t = KS.getToken(pcName);
    if (t) token = t; else if (token) KS.setToken(pcName, token);   // flytt eldre nøkkel inn i appen
  }
  if (!token) return showPair();
  let t = "oversikt"; try { t = sessionStorage.getItem("ks_tab") || t; } catch (e) {}
  setTab(t); poll(); pollExtra(); checkAppUpdate(false);
})();

// ---- glidere: skrolling skal ikke endre verdien ----
// Fingeren må dra sidelengs før glideren endres. Går den opp/ned, er det skrolling – verdien blir som den var.
(() => {
  let g = null;
  const rangeOf = (t) => t && t.closest && t.closest('input[type="range"]');
  document.addEventListener("touchstart", (e) => {
    const r = rangeOf(e.target); if (!r) { g = null; return; }
    const t = e.touches[0]; g = { r, x: t.clientX, y: t.clientY, v: r.value, ok: false };
  }, { capture: true, passive: true });
  document.addEventListener("touchmove", (e) => {
    if (!g || g.ok) return;
    const t = e.touches[0], dx = Math.abs(t.clientX - g.x), dy = Math.abs(t.clientY - g.y);
    if (dx > 10 && dx > dy * 1.3) g.ok = true;                 // tydelig sidelengs: nå får glideren lov
    else if (dy > 6) g.r.value = g.v;                          // skrolling: hold verdien
  }, { capture: true, passive: true });
  const block = (e) => { if (g && e.target === g.r && !g.ok) { e.stopImmediatePropagation(); g.r.value = g.v; } };
  document.addEventListener("input", block, true);
  document.addEventListener("change", block, true);
  document.addEventListener("touchend", () => { if (g && !g.ok) g.r.value = g.v; setTimeout(() => (g = null), 0); },
    { capture: true, passive: true });
  // TV-fjernkontrollen: opp/ned over en glider flytter fokus videre i stedet for å endre verdien
  document.addEventListener("keydown", (e) => {
    const r = rangeOf(e.target); if (!r || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
    e.preventDefault();
    const me = r.getBoundingClientRect(), down = e.key === "ArrowDown";
    const all = [...document.querySelectorAll("button, a[href], input, select, textarea, [tabindex]")]
      .filter((x) => x !== r && x.offsetParent && x.tabIndex >= 0 && !x.disabled);
    let best = null, bd = 1e9;
    for (const x of all) { const b = x.getBoundingClientRect(), dy = down ? b.top - me.bottom : me.top - b.bottom;
      if (dy < -2) continue; const d = dy * 3 + Math.abs((b.left + b.right) / 2 - (me.left + me.right) / 2);
      if (d < bd) { bd = d; best = x; } }
    if (best) { best.focus(); best.scrollIntoView({ block: "nearest" }); }
  }, true);
})();
