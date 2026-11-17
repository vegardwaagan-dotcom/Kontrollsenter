// Kontrollsenter – familie, knappebord, søk, egne widgets, dashbord, offline, batterisparing, hjemmenett,
// sikkerhet, oppstartsprogrammer, Hue, ytelse per spill, prestasjoner, Wrapped, tilbud og sikkerhetskopi.
"use strict";
const h = (html) => { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstElementChild; };
const sw = (id) => `<label class="switch"><input type="checkbox" id="${id}"><i></i></label>`;
const lvl = { ok: "✅", warn: "⚠️", bad: "❌" };

// ---------- kortene ----------
const famGrid = h(`<div class="grid" id="fam-grid">
  <div class="card accent" id="c-family"><h2>Familie</h2>
    <div id="fam-pcs"></div>
    <details><summary>Ranking</summary><div id="fam-rank" class="kvgrid"></div></details>
    <div class="label">Chat</div><div id="chat" class="events chat"></div>
    <select id="chat-to" class="search"><option value="">Til denne PC-en</option><option value="*">Til alle PC-ene</option></select>
    <div class="row"><input id="chat-text" maxlength="500" placeholder="Skriv en melding …"><button id="chat-send" class="primary">Send</button></div>
    <div class="row wrap"><button id="dinner" class="warn">🍽️ Middag!</button></div>
    <div class="row full-only"><span><b>Familiekontroll</b><br><span class="dim small">Kode for å lukke Kontrollsenter på PC-en</span></span>${sw("fl-on")}</div>
    <details class="full-only"><summary>Belønning og leggetid</summary>
      <div class="label">Ekstra spilletid i dag</div>
      <div class="chips" id="bonus"><button data-m="15">+15 min</button><button data-m="30">+30 min</button><button data-m="60">+1 time</button></div>
      <div class="row"><span>La andre i huset se skjermen til denne PC-en</span>${sw("wa-on")}</div>
      <div class="row"><span>Leggetid (PC-en slås av)</span>${sw("bt-on")}</div>
      <div class="row"><span>Søn–tor</span><input type="time" id="bt-wd" class="num-in"></div>
      <div class="row"><span>Fre–lør</span><input type="time" id="bt-we" class="num-in"></div>
      <button id="bt-save" class="soft">Lagre leggetid</button></details></div>
  <div class="card"><h2>Ytelse per spill</h2><div id="perf"></div><div id="driver" class="dim small"></div></div>
  <div class="card"><h2>Prestasjoner</h2><div id="ach" class="chips"></div></div>
  <div class="card"><h2>Måneden i tall</h2><div id="wrapped" class="kvgrid"></div></div>
  <div class="card"><h2>Tilbud på ønskelisten</h2>
    <div class="row"><span>Varsle om tilbud (Steam)</span>${sw("wl-on")}</div>
    <div id="wl" class="dim small"></div><button id="wl-check" class="soft">Sjekk nå</button></div>
</div>`);
$("#spill").insertBefore(famGrid, $("#spill .grid"));

// ---------- spill på telefonen (Sunshine + Moonlight) og RustDesk ----------
const streamCard = h(`<div class="card accent" id="c-stream"><h2>Spill på telefonen</h2>
  <p class="dim small">Se og spill det som skjer på PC-en her på telefonen – også spillet som kjører nå. Sunshine på PC-en sender bildet, Moonlight-appen viser det.</p>
  <div class="row between"><b id="st-state">Sjekker …</b><button id="st-start" class="soft">Start Sunshine</button></div>
  <div class="row wrap"><button id="st-moon" class="primary">▶ Åpne Moonlight</button></div>
  <details><summary>Første gang: par telefonen</summary>
    <ol class="steps"><li>Åpne Moonlight. PC-en dukker opp av seg selv hjemme – borte: legg til Tailscale-adressen under.</li>
      <li>Trykk på PC-en. Moonlight viser en kode med 4 sifre.</li><li>Skriv koden her og trykk «Par».</li><li>Velg «Desktop» for hele skjermen.</li></ol>
    <div id="st-addr" class="dim small sel"></div>
    <div class="row"><input id="st-pin" inputmode="numeric" maxlength="4" placeholder="PIN fra Moonlight"><button id="st-pair" class="primary">Par</button></div>
    <p class="dim small" id="st-login"></p></details></div>`);
$("#spill").insertBefore(streamCard, $("#spill").firstChild);
const rustCard = h(`<div class="card" id="c-rust"><h2>RustDesk – fjernhjelp</h2>
  <p class="dim small">Styr PC-en med mus og tastatur fra telefonen – eller la noen hjelpe deg. Bruk ID-en og passordet som vises i RustDesk på PC-en.</p>
  <div class="row between"><div><div class="dim small">ID</div><b id="rd-id" class="num sel">–</b></div><button id="rd-copy" class="soft">Kopier</button></div>
  <div class="row wrap"><button id="rd-open" class="primary">Åpne RustDesk</button><button id="rd-pc" class="soft full-only">Start RustDesk på PC-en</button></div></div>`);
async function loadStream() {
  try {
    const s = await X("stream");
    $("#st-state").textContent = !s.installed ? "Sunshine er ikke installert på PC-en" : s.running ? "● Sunshine kjører – klar" : "○ Sunshine er av";
    $("#st-state").className = s.running ? "ok" : "";
    $("#st-start").hidden = !s.installed || s.running;
    $("#st-addr").innerHTML = (s.addresses || []).map((a) => `${esc(a.kind)}: <b>${esc(a.ip)}</b>`).join("<br>");
    $("#st-login").textContent = s.has_login ? "" : "Paring herfra krever at innloggingen til Sunshine er lagt inn på PC-en (Strømming → Innlogging).";
    const rd = s.rustdesk || {};
    $("#rd-id").textContent = rd.id || (rd.installed ? "–" : "ikke installert på PC-en");
  } catch (e) { $("#st-state").textContent = e.message; }
}
const MOON = "com.limelight", RUST = "com.carriez.flutter_hbb";
$("#st-moon").onclick = () => { if (KS && KS.openApp) { if (!KS.openApp(MOON)) toast("Installer Moonlight fra Google Play"); } else location.href = "https://moonlight-stream.org"; };
rustCard.querySelector("#rd-open").onclick = () => { if (KS && KS.openApp) { if (!KS.openApp(RUST)) toast("Installer RustDesk fra Google Play"); } else location.href = "https://rustdesk.com"; };
$("#st-start").onclick = async () => { await act({ a: "stream", do: "start" }); setTimeout(loadStream, 22000); };
$("#st-pair").onclick = async () => { const p = $("#st-pin").value.trim(); if (p.length !== 4) return toast("Koden har 4 sifre"); $("#st-pin").value = ""; await act({ a: "streampin", pin: p }); };
rustCard.querySelector("#rd-pc").onclick = () => act({ a: "rustdesk" });
rustCard.querySelector("#rd-copy").onclick = () => { try { navigator.clipboard.writeText($("#rd-id").textContent); toast("Kopiert"); } catch (e) {} };

const batCard = h(`<div class="card" id="c-bat" data-k="batteries"><h2>Batterier</h2><div id="bats"></div>
  <div id="bat-hint" class="row" hidden><span class="dim small">Hodesett vises når HeadsetControl er installert på PC-en.</span><button id="bat-inst" class="soft full-only">Installer</button></div></div>`);
{ const tl = $("#tiles"); batCard.dataset.ord = "-50"; if (tl) tl.insertBefore(batCard, tl.querySelector(':scope > [data-k="temps"]')); }
const BICON = { mouse: "🖱️", keyboard: "⌨️", headset: "🎧", gamepad: "🎮", speaker: "🔊" };
function renderBatteries(b) {
  if (!b) return;
  const ds = b.devices || [];
  $("#bats").innerHTML = ds.map((d) => {
    const p = d.pct, chg = !!d.charging, full = !!d.full, low = p != null && p <= 20 && !chg && !full;
    const txt = chg ? "Lader" + (p != null ? " · " + p + " %" : "") : full ? "Fulladet" + (p != null ? " · " + p + " %" : "")
      : p == null ? "av" : p + " %";
    const w = p != null ? p : full ? 100 : chg ? 100 : 0;
    return `<div class="row between bat-row${chg ? " charging" : ""}"><span>${BICON[d.kind] || "🔋"} ${esc(d.name)}</span><span class="row">
      ${chg || full ? `<span class="bolt${chg ? " on" : ""}" title="${chg ? "Lader" : "Fulladet"}">${chg ? "⚡" : "🔌"}</span>` : ""}
      <span class="batbar"><i style="width:${w}%" class="${chg || full ? "chg" : low ? "low" : ""}${chg && p == null ? " unknown" : ""}"></i></span>
      <b class="num ${chg || full ? "t-ok" : low ? "t-bad" : ""}">${esc(txt)}</b></span></div>`;
  }).join("") || `<p class="dim small">Ingen trådløse enheter med batteri (av eller i dvale?).</p>`;
  $("#bat-hint").hidden = b.headsetcontrol || ds.some((d) => d.kind === "headset");
}
$("#bat-inst").onclick = () => { toast("Installerer på PC-en – godkjenn passordet der"); act({ a: "headsetinstall" }); };

const deck = h(`<div class="card" id="c-deck"><div class="row between"><h2>Knappebord</h2><button id="deck-edit" class="link">Endre</button></div>
  <div id="deck" class="deck"></div><div id="deck-pick" class="chips" hidden></div></div>`);
$("#mer").insertBefore(deck, $("#mer").firstChild);

const toolGrid = h(`<div class="grid" id="tool-grid">
  <div class="card"><h2>Skjermen live</h2><p class="dim small">Se PC-skjermen som jevn video – bare visning.</p><button id="live-go" class="primary wide">📺 Se skjermen live</button></div>
  <div class="card"><h2>Hjemmenett</h2><div id="lan"></div><button id="lan-refresh" class="soft">Oppdater</button></div>
  <div class="card"><h2>Sikkerhetssjekk</h2><div id="sec"></div><button id="sec-go" class="soft">Sjekk</button></div>
  <div class="card full-only"><h2>Oppstartsprogrammer</h2><div id="startup"></div></div>
  <div class="card"><h2>Hue-lys</h2><div id="hue"></div>
    <div class="row wrap"><input type="color" id="hue-color" value="#ff8800"><button id="hue-set" class="soft">Bruk farge</button>
      <button id="hue-on" class="soft">På</button><button id="hue-off" class="soft">Av</button><button id="hue-pair" class="soft">Koble til</button></div></div>
  <div class="card"><h2>Selvtest og feilrapport</h2><div id="selftest"></div>
    <div class="row wrap"><button id="st-go" class="soft">Kjør selvtest</button></div>
    <input id="rep-note" maxlength="2000" placeholder="Hva er galt? (valgfritt)"><button id="rep-go" class="soft">Send feilrapport til NAS-en</button></div>
</div>`);
$("#mer").appendChild(toolGrid);
$("#tool-grid").prepend(rustCard);

const setGrid = h(`<div class="grid" id="set-grid">
  <div class="card full-only"><h2>Sikkerhetskopi av innstillingene</h2>
    <button id="bk-go" class="soft">Ta kopi nå (NAS)</button>
    <select id="bk-list" class="search"></select><button id="bk-restore" class="warn">Gjenopprett valgt</button>
    <div class="row"><span>Oppdater Kontrollsenter av seg selv kl. 04</span>${sw("au-on")}</div>
    <p class="dim small">Starter den nye versjonen ikke, rulles den tilbake automatisk.</p></div>
  <div class="card"><h2>Panelet</h2>
    <div class="row"><span>Batterisparing (henter sjeldnere)</span>${sw("eco")}</div>
    <div class="row"><span>Dashbord (nettbrett på veggen)</span>${sw("dash")}</div>
    <details><summary>Vis og skjul kort</summary><div id="widgets"></div></details></div>
</div>`);
$("#system").appendChild(setGrid);

// søk (øverst)
const sbtn = h(`<button id="btn-search" class="icon" title="Søk"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/></svg></button>`);
$("#btn-second").before(sbtn);
const sbox = h(`<div id="search" class="dlg" hidden><div class="card narrow"><input id="search-q" placeholder="Søk etter funksjon …"><div id="search-res" class="list"></div>
  <div class="row end"><button id="search-close" class="soft">Lukk</button></div></div></div>`);
document.body.appendChild(sbox);

// ---------- familie ----------
async function loadFamily() {
  try {
    const f = await X("family");
    if (!gamesCache) { try { gamesCache = (await api("/api/games")).games; } catch (e) { gamesCache = []; } }
    const mine = new Map((gamesCache || []).map((g) => [g.name, g.appid]));
    $("#fam-pcs").innerHTML = f.pcs.map((p) => {
      const join = (p.game && mine.has(p.game) && p.name !== pcName ? `<button class="soft small" data-join="${esc(mine.get(p.game))}">Bli med</button>` : "")
        + (p.watch && !p.off ? ` <button class="${p.game ? "primary" : "soft"} small full-only" data-watch="${esc(p.name)}" data-game="${esc(p.game || "")}">📺 Se på</button>` : "");
      return `<div class="row between"><div><b>${esc(p.name)}</b><div class="dim small">${p.off ? "Av" : p.game ? "🎮 " + esc(p.game) : "Ingen spill"} · i dag ${hours(p.today || 0)}</div></div>${join}</div>`;
    }).join("") || `<p class="dim">Ingen andre PC-er har delt status ennå.</p>`;
    $$("[data-join]").forEach((b) => (b.onclick = () => act({ a: "game", appid: b.dataset.join })));
    $$("[data-watch]").forEach((b) => (b.onclick = () => openWatch(b.dataset.watch, b.dataset.game)));
    const cur = $("#chat-to").value;
    $("#chat-to").innerHTML = `<option value="">Til denne PC-en</option><option value="*">Til alle PC-ene</option>` +
      f.pcs.filter((p) => p.name && p.name !== pcName).map((p) => `<option>${esc(p.name)}</option>`).join("");
    $("#chat-to").value = cur;
    $("#fam-rank").innerHTML = Object.entries(f.ranking).filter(([, v]) => v.length).map(([k, v]) =>
      `<div><div class="label">${esc(k)}</div>${v.slice(0, 4).map(([n, x], i) => `<div>${["🥇", "🥈", "🥉", ""][i] || ""} ${esc(n)} <span class="dim">${esc(x)}</span></div>`).join("")}</div>`).join("");
  } catch (e) { $("#fam-pcs").textContent = "Familie: " + e.message; }
  loadChat();
  try {
    const c = await X("features");
    $("#bt-on").checked = !!c.bedtime.enabled; $("#bt-wd").value = c.bedtime.weekday; $("#bt-we").value = c.bedtime.weekend;
    $("#wl-on").checked = !!c.wishlist; $("#au-on").checked = !!c.auto_update;
    const me = f.pcs.find((p) => p.name === pcName); $("#wa-on").checked = !me || me.watch !== false;
    try { $("#fl-on").checked = !!(await X("familylock")).on; } catch (e) {}
  } catch (e) {}
}
async function loadChat() {
  try {
    const m = (await X("chat")).messages;
    $("#chat").innerHTML = m.slice(-30).map((x) => `<div class="ev${x.urgent ? " warn" : ""}"><b>${esc(x.from)}</b> ${esc(x.text)} <span class="dim small">${hhmm(x.t)}</span></div>`).join("") || `<p class="dim small">Ingen meldinger ennå.</p>`;
    $("#chat").scrollTop = 1e6;
  } catch (e) {}
}
// meldinger som ikke kom fram (PC-en utenfor rekkevidde) sendes når den svarer igjen
let chatQueue = pref("chatq", []);
async function sendChat(body) {
  try { const r = await api("/api/action", body); toast(r.ok ? r.msg : "Feil: " + r.msg); loadChat(); }
  catch (e) { chatQueue.push(body); setPref("chatq", chatQueue); toast("Sendes når PC-en svarer"); }
}
async function flushChat() {
  if (!chatQueue.length) return;
  const q = chatQueue; chatQueue = []; setPref("chatq", []);
  for (const b of q) await sendChat(b);
}
$("#chat-send").onclick = () => { const t = $("#chat-text").value.trim(); if (t) { sendChat({ a: "chat", text: t, to: $("#chat-to").value || undefined }); $("#chat-text").value = ""; } };
$("#chat-text").onkeydown = (e) => e.key === "Enter" && $("#chat-send").onclick();
$("#dinner").onclick = () => sendChat({ a: "dinner", to: $("#chat-to").value || "*" });
$$("#bonus button").forEach((b) => (b.onclick = () => act({ a: "bonus", minutes: +b.dataset.m })));
$("#fl-on").onchange = async () => {
  if ($("#fl-on").checked) {
    const pin = prompt("Velg kode (4–8 sifre) for familiekontroll på PC-en:");
    if (!pin || !/^\d{4,8}$/.test(pin)) { $("#fl-on").checked = false; if (pin) toast("Koden må være 4–8 sifre"); return; }
    const r = await act({ a: "familylock", on: true, pin });
    if (!r || !r.ok) $("#fl-on").checked = false;
  } else await act({ a: "familylock", on: false });
};
$("#wa-on").onchange = () => act({ a: "watchallow", on: $("#wa-on").checked }, true);
$("#bt-save").onclick = () => act({ a: "bedtime", enabled: $("#bt-on").checked, weekday: $("#bt-wd").value, weekend: $("#bt-we").value });
$("#wl-on").onchange = () => act({ a: "feature", key: "wishlist", on: $("#wl-on").checked }, true);
$("#au-on").onchange = () => act({ a: "feature", key: "auto_update", on: $("#au-on").checked }, true);

async function loadGameExtras() {
  try {
    const p = await X("perf");
    $("#perf").innerHTML = p.games.slice(0, 12).map((g) => `<div class="row between"><div><b>${esc(g.game)}</b><div class="dim small">${g.sessions} økter · ${g.hours} t${g.kr ? " · " + g.kr + " kr" : ""}</div></div>
      <div class="num">${g.fps ? g.fps + " FPS" : "–"}${g.low ? `<span class="dim small"> (1 % ${g.low})</span>` : ""}${g.cpu ? `<div class="dim small">CPU maks ${Math.round(g.cpu)} °C</div>` : ""}</div></div>`).join("") || `<p class="dim small">Ingen spilløkter registrert ennå.</p>`;
    $("#driver").textContent = p.driver && p.driver.driver ? `${p.driver.gpu}: driver ${p.driver.driver} – ${p.driver.where}` : "";
  } catch (e) {}
  try {
    const a = (await X("achievements")).items;
    $("#ach").innerHTML = a.map((x) => `<span class="ach${x.done ? " on" : ""}" title="${x.done ? hhmm(x.t) : "Ikke ennå"}">${x.done ? "" : "🔒 "}${esc(x.name)}</span>`).join("");
  } catch (e) {}
  try {
    const w = await X("wrapped");
    const rows = [["Spilt", (w.hours ?? 0) + " t"], ["Økter", w.sessions ?? 0], ["Klipp", w.clips ?? 0], ["Strøm", w.kwh != null ? `${w.kwh} kWh (${w.kr} kr)` : "–"],
      ["Varmeste CPU", w.hottest ? Math.round(w.hottest) + " °C" : "–"], ...(w.top || []).map(([g, t], i) => [`#${i + 1}`, `${g} – ${t} t`])];
    $("#wrapped").innerHTML = rows.map(([k, v]) => `<div><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("");
  } catch (e) {}
}
$("#wl-check").onclick = async () => {
  $("#wl").textContent = "Sjekker Steam …";
  try { const s = (await X("wishlist")).sales; $("#wl").innerHTML = s.map((x) => `<div>−${x.pct} % <b>${esc(x.name)}</b> ${esc(x.price || "")}</div>`).join("") || "Ingen tilbud akkurat nå (eller ønskelisten er privat)."; }
  catch (e) { $("#wl").textContent = e.message; }
};

// ---------- knappebord (Stream Deck) ----------
const DECK = {
  gamemode: ["🎮", "Spillmodus", () => act({ a: "gamemode", on: !(last && last.gamemode) })],
  clip: ["🎬", "Lagre klipp", () => act({ a: "clip" })],
  shot: ["📸", "Skjermbilde", () => act({ a: "clipshot" })],
  rec: ["⏺", "Opptak", () => act({ a: "cliprecord" })],
  mute: ["🔇", "Demp av/på", () => api("/api/extra").then((e) => act({ a: "volume", mute: !(e.audio && e.audio.mute) })).catch((e) => toast(e.message))],
  play: ["⏯", "Spill/pause", () => act({ a: "media", cmd: "PlayPause" }, true)],
  next: ["⏭", "Neste spor", () => act({ a: "media", cmd: "Next" }, true)],
  lock: ["🔒", "Lås", () => act({ a: "system", do: "lock" })],
  sleep: ["🌙", "Hvilemodus", async () => (await confirmDlg("Sette PC-en i hvilemodus?")) && act({ a: "system", do: "sleep" })],
  dinner: ["🍽️", "Middag!", () => sendChat({ a: "dinner" })],
  rgboff: ["💡", "RGB av", () => act({ a: "rgb", mode: "off" })],
  hueoff: ["🛋️", "Hue av", () => act({ a: "hue", on: false })],
  fans: ["🌀", "Vifter maks", () => act({ a: "fans", value: 100 })],
  fanauto: ["🍃", "Vifter auto", () => act({ a: "fans", value: "auto" })],
};
let deckKeys = pref("deck", ["gamemode", "clip", "shot", "mute", "play", "lock", "dinner", "fanauto"]);
// av/på-snarveier: lilla når de er på
const DECK_ON = {
  gamemode: (s) => !!s.gamemode,
  mute: () => lastMute,
  fans: (s) => !!(s.fans && fanAllOn(s.fans, "100")),
  fanauto: (s) => !!(s.fans && fanAllOn(s.fans, "auto")),
};
function deckState(s) {
  if (held("deck")) return;
  $$("#deck button").forEach((b) => { const f = DECK_ON[b.dataset.d]; b.classList.toggle("on", !!(f && s && f(s))); });
}
function renderDeck() {
  $("#deck").innerHTML = deckKeys.filter((k) => DECK[k]).map((k) => `<button data-d="${k}"><span class="qi">${DECK[k][0]}</span><span class="ql">${DECK[k][1]}</span></button>`).join("");
  $$("#deck button").forEach((b) => (b.onclick = () => { if (KS && KS.vibrate) KS.vibrate();
    if (DECK_ON[b.dataset.d]) { holdFor("deck", 4000); b.classList.toggle("on", !b.classList.contains("on")); }
    DECK[b.dataset.d][2](); }));
  if (typeof last !== "undefined" && last) deckState(last);
  $("#deck-pick").innerHTML = Object.entries(DECK).map(([k, v]) => `<button data-k="${k}" class="${deckKeys.includes(k) ? "on" : ""}">${v[0]} ${v[1]}</button>`).join("");
  $$("#deck-pick button").forEach((b) => (b.onclick = () => {
    const k = b.dataset.k; deckKeys = deckKeys.includes(k) ? deckKeys.filter((x) => x !== k) : [...deckKeys, k];
    setPref("deck", deckKeys); renderDeck();
  }));
}
$("#deck-edit").onclick = () => { $("#deck-pick").hidden = !$("#deck-pick").hidden; $("#deck-edit").textContent = $("#deck-pick").hidden ? "Endre" : "Ferdig"; };
renderDeck();

// ---------- skjermen live (bare visning, hvert 2. sekund) ----------

// ---------- hjemmenett, sikkerhet, oppstart, Hue, selvtest ----------
async function loadLan() {
  try {
    const d = (await X("lan")).devices;
    const unk = d.filter((x) => !x.name).length;
    $("#lan").innerHTML = `<details><summary>${d.length} enheter${unk ? ` (${unk} uten navn)` : ""}</summary>` + d.map((x) => `<div class="row between"><div><b>${esc(x.name || "Ukjent enhet")}</b><div class="dim small">${esc(x.ip)} · ${esc(x.mac)}</div></div>
      <button class="soft small full-only" data-mac="${esc(x.mac)}">Gi navn</button></div>`).join("") + "</details>";
    $$("[data-mac]").forEach((b) => (b.onclick = async () => { const n = prompt("Navn på enheten:"); if (n) { await act({ a: "lanname", mac: b.dataset.mac, name: n }); loadLan(); } }));
  } catch (e) { $("#lan").textContent = e.message; }
}
$("#lan-refresh").onclick = loadLan;
$("#sec-go").onclick = async () => {
  $("#sec").textContent = "Sjekker …";
  try { $("#sec").innerHTML = (await X("security")).items.map((x) => `<div><b>${lvl[x.level] || ""} ${esc(x.title)}</b><div class="dim small">${esc(x.detail)}</div></div>`).join(""); }
  catch (e) { $("#sec").textContent = e.message; }
};
async function loadStartup() {
  try {
    const it = (await X("startup")).items;
    $("#startup").innerHTML = it.map((x, i) => `<div class="row between"><span>${esc(x.name)}</span><label class="switch"><input type="checkbox" data-su="${i}" ${x.on ? "checked" : ""}><i></i></label></div>`).join("") || `<p class="dim small">Ingen.</p>`;
    $$("[data-su]").forEach((c) => (c.onchange = () => act({ a: "startup", id: it[+c.dataset.su].id, on: c.checked })));
  } catch (e) {}
}
async function loadHue() {
  try {
    const hu = await X("hue");
    $("#hue-pair").hidden = hu.paired;
    $("#hue").innerHTML = hu.paired ? hu.lights.map((l) => `<span class="badge">${l.on ? "💡" : "⚫"} ${esc(l.name)}</span>`).join(" ") : `<p class="dim small">Trykk på knappen på Hue-broen, så «Koble til».</p>`;
  } catch (e) {}
}
$("#hue-pair").onclick = async () => { await act({ a: "huepair" }); loadHue(); };
$("#hue-set").onclick = () => act({ a: "hue", color: $("#hue-color").value }, true);
$("#hue-on").onclick = () => act({ a: "hue", on: true }, true);
$("#hue-off").onclick = () => act({ a: "hue", on: false }, true);
$("#st-go").onclick = async () => {
  try { $("#selftest").innerHTML = (await X("selftest")).items.map((x) => `<div>${x.ok ? "✅" : "❌"} ${esc(x.name)}</div>`).join(""); }
  catch (e) { $("#selftest").textContent = e.message; }
};
$("#rep-go").onclick = () => act({ a: "report", note: $("#rep-note").value });

// ---------- sikkerhetskopi ----------
async function loadBackups() {
  try { $("#bk-list").innerHTML = (await X("backups")).backups.map((b) => `<option>${esc(b)}</option>`).join("") || "<option value=''>Ingen kopier ennå</option>"; } catch (e) {}
}
$("#bk-go").onclick = async () => { await act({ a: "setbackup" }); loadBackups(); };
$("#bk-restore").onclick = async () => {
  const n = $("#bk-list").value; if (!n) return;
  if (await confirmDlg(`Gjenopprette innstillingene fra «${n}»? Dagens innstillinger tas vare på.`)) act({ a: "restore", name: n });
};

// ---------- egne widgets: skjul kort du ikke bruker ----------
let hidden = new Set(pref("hidden_cards", []));
const cardKey = (c) => (c.querySelector("h2") || {}).textContent || "";
function applyWidgets() {
  $$("main .card").forEach((c) => { const k = cardKey(c); if (k) c.classList.toggle("user-hidden", hidden.has(k)); });
}
function renderWidgets() {
  const keys = [...new Set($$("main .card h2").map((x) => x.textContent).filter((k) => k && k !== "Panelet"))];
  $("#widgets").innerHTML = keys.map((k, i) => `<div class="row between"><span>${esc(k)}</span><label class="switch"><input type="checkbox" data-w="${i}" ${hidden.has(k) ? "" : "checked"}><i></i></label></div>`).join("");
  $$("[data-w]").forEach((c) => (c.onchange = () => { const k = keys[+c.dataset.w]; c.checked ? hidden.delete(k) : hidden.add(k); setPref("hidden_cards", [...hidden]); applyWidgets(); }));
}

// ---------- søk ----------
const TABNAME = { oversikt: "Hjem", kontroll: "Styr", spill: "Spill", mer: "Verktøy", system: "Innstillinger" };
$("#btn-search").onclick = () => { $("#search").hidden = false; $("#search-q").value = ""; $("#search-res").innerHTML = ""; $("#search-q").focus(); };
$("#search-close").onclick = () => ($("#search").hidden = true);
$("#search-q").oninput = () => {
  const q = $("#search-q").value.trim().toLowerCase(); if (!q) { $("#search-res").innerHTML = ""; return; }
  const hits = [];
  for (const sec of Object.keys(TABNAME)) {
    $$(`#${sec} .card`).forEach((c) => {
      const t = c.textContent.toLowerCase();
      if (t.includes(q)) hits.push([sec, c, cardKey(c) || c.textContent.trim().slice(0, 40)]);
    });
  }
  $("#search-res").innerHTML = hits.slice(0, 20).map(([s, , n], i) => `<button class="soft wide" data-hit="${i}">${esc(n)} <span class="dim small">· ${TABNAME[s]}</span></button>`).join("") || `<p class="dim">Ingen treff.</p>`;
  $$("[data-hit]").forEach((b) => (b.onclick = () => {
    const [s, c] = hits[+b.dataset.hit]; $("#search").hidden = true; setTab(s);
    c.classList.remove("user-hidden"); c.querySelectorAll("details").forEach((d) => (d.open = true));
    setTimeout(() => { c.scrollIntoView({ behavior: "smooth", block: "start" }); c.classList.add("flash"); setTimeout(() => c.classList.remove("flash"), 1500); }, 80);
  }));
};

// ---------- dashbord, batterisparing og offline ----------
function applyDash() {
  const on = pref("dash", false);
  document.body.classList.toggle("dash", on);
  if (KS && KS.keepAwake) KS.keepAwake(on);
  $("#dash").checked = on;
}
$("#dash").onchange = () => { setPref("dash", $("#dash").checked); applyDash(); if ($("#dash").checked) setTab("oversikt"); };
$("#eco").checked = pref("eco", false);
const applyEco = () => document.body.classList.toggle("eco", !!(pref("eco", false) || window.ksLowBattery));
$("#eco").onchange = () => { setPref("eco", $("#eco").checked); applyEco(); };
applyEco();
document.addEventListener("dblclick", () => { if (document.body.classList.contains("dash")) { setPref("dash", false); applyDash(); } });

let lastPoll = 0;
const famPoll = poll;
poll = async function () {                           // eslint-disable-line no-global-assign
  const eco = pref("eco", false) || (navigator.getBattery && window.ksLowBattery);
  if (eco && Date.now() - lastPoll < 10000) return;
  lastPoll = Date.now();
  await famPoll();
  if (last) renderBatteries(last.batteries);
  if (failures === 0 && last) {
    try { localStorage.setItem("ks_last_" + pcName, JSON.stringify({ t: Date.now(), s: last })); } catch (e) {}
    $("#offline") && ($("#offline").hidden = true);
    flushChat();
  } else if (failures > 2) showOffline();
};
function showOffline() {
  let c = null; try { c = JSON.parse(localStorage.getItem("ks_last_" + pcName) || "null"); } catch (e) {}
  if (!c) return;
  if (!$("#offline")) $("header").after(h(`<div id="offline" class="upd"></div>`));
  $("#offline").hidden = false;
  $("#offline").textContent = "Frakoblet – viser sist kjente verdier fra " + new Date(c.t).toLocaleString("nb-NO", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  if (!last) { try { renderOverview(c.s); } catch (e) {} }
}
if (navigator.getBattery) navigator.getBattery().then((b) => { const f = () => { window.ksLowBattery = !b.charging && b.level < 0.2; applyEco(); }; f(); b.onlevelchange = f; b.onchargingchange = f; }).catch(() => {});

// ---------- «Se på»: skjermen til en PC i huset, live (bare visning) ----------
document.body.appendChild(h(`<div id="watchv" class="watchv" hidden><img id="watch-img" alt="">
  <div class="watch-top"><b id="watch-t"></b><span id="watch-s" class="dim small"></span><button id="watch-x" class="icon">✕</button></div></div>`));
function openWatch(name, game) {
  $("#watchv").hidden = false;
  $("#watch-t").textContent = "📺 " + name + (game ? " – " + game : "");
  $("#watch-s").textContent = "Kobler til … (første gang må delingen godkjennes på PC-en)";
  const img = $("#watch-img");
  img.onload = () => ($("#watch-s").textContent = "Bare visning · snu telefonen for stort bilde");
  img.onerror = () => ($("#watch-s").textContent = "Fikk ikke vist skjermen – er deling slått på der?");
  img.src = `/api/watch?k=${encodeURIComponent(token)}` + (name && name !== pcName ? `&pc=${encodeURIComponent(name)}` : "");
  if (KS && KS.keepAwake) KS.keepAwake(true);
}
function closeWatch() {
  $("#watch-img").src = ""; $("#watchv").hidden = true;
  if (KS && KS.keepAwake && !pref("dash", false)) KS.keepAwake(false);
}
$("#watch-x").onclick = closeWatch;
window.ksBack = () => {
  if (!$("#watchv").hidden) { closeWatch(); return true; }
  if (!$("#search").hidden) { $("#search").hidden = true; return true; }
  if (!$("#dlg").hidden) { $("#dlg").hidden = true; return true; }
  return false;
};
$("#watchv").ondblclick = () => { try { document.fullscreenElement ? document.exitFullscreen() : $("#watchv").requestFullscreen(); } catch (e) {} };
document.addEventListener("visibilitychange", () => { if (document.hidden && !$("#watchv").hidden) closeWatch(); });
// hurtigknapp på Hjem: velg PC å se på (velgeren fra picker.js)
const watchSel = document.createElement("select");
watchSel.id = "watch-sel"; watchSel.dataset.title = "Se på skjermen til …"; watchSel.style.display = "none";
document.body.appendChild(watchSel);
const qWatch = h(`<button data-q="watch"><span class="qi">📺</span><span class="ql">Se på</span><span class="qs" id="q-watch">Andre PC-er</span></button>`);
$("#quick").prepend(qWatch);
qWatch.onclick = async () => {
  try {
    const f = await X("family");
    const now = Date.now() / 1000;
    watchSel.innerHTML = '<option value="" disabled selected hidden>Velg PC</option>' + f.pcs.map((p) => {
      const on = !p.off && now - (p.time || 0) < 900;
      const why = !on ? "Av" : p.watch ? (p.game ? "🎮 " + p.game : "Ingen spill nå") : "Trenger Kontrollsenter 0.16+ (start den på nytt)";
      return `<option value="${esc(p.name)}" data-icon="${p.name === pcName ? "🖥️" : on ? "💻" : "⚫"}" data-sub="${esc(why)}"${on && p.watch ? "" : " disabled"}>${esc(p.name)}${p.name === pcName ? " (denne)" : ""}</option>`;
    }).join("");
    watchSel.onchange = () => { const p = f.pcs.find((x) => x.name === watchSel.value); if (p) openWatch(p.name, p.game); };
    const btn = watchSel.nextElementSibling;               // vent til velgeren har sett de nye valgene
    if (btn && btn.classList.contains("picker")) setTimeout(() => { btn.disabled = false; btn.click(); }, 0);
  } catch (e) { toast("Se på: " + e.message); }
};

// «Skjermen live» i Verktøy bruker samme strøm (jevn video i stedet for et bilde hvert par sekunder)
$("#live-go").onclick = () => openWatch(pcName, last && last.game);

// ---------- statistikken: foldet sammen til du vil se alt ----------
(() => {
  const st = $("#stats"); if (!st) return;
  st.classList.add("folded");
  const more = h(`<button id="stats-more" class="link">Vis all statistikk</button>`);
  st.after(more);
  more.onclick = () => { const c = st.classList.toggle("folded"); more.textContent = c ? "Vis all statistikk" : "Vis mindre"; };
})();

// ---------- oppdater Kontrollsenter på PC-en fra telefonen ----------
$("#pc-upd").onclick = async () => {
  if (!(await confirmDlg("Oppdatere Kontrollsenter på PC-en fra NAS-en? Det starter på nytt av seg selv."))) return;
  toast("Oppdaterer PC-en …");
  await act({ a: "pcupdate" });
};
fetch("/api/hello").then((r) => r.json()).then((h) => ($("#pc-ver").textContent = h.version || "–")).catch(() => {});

// ---------- World of Warcraft: oversikt, bagsøk, quests, yrker, gull, låser, utstyr (med av/på) ----------
const wpGold = (c) => { c = Math.max(0, Math.round(c || 0)); const g = Math.floor(c / 10000), s = Math.floor(c % 10000 / 100);
  return g ? `${g} g ${s} s` : `${s} s ${c % 100} k`; };
const wpDur = (h) => (h >= 24 ? Math.round(h / 24) + " d" : Math.round(h) + " t");
const wpLeft = (t) => { const s = t - Date.now() / 1000; return s <= 0 ? "nå" : s > 86400 ? `${Math.floor(s / 86400)} d ${Math.floor(s % 86400 / 3600)} t` : `${Math.floor(s / 3600)} t ${Math.floor(s % 3600 / 60)} min`; };
let wpItems = [];
window.renderWowPlus = (w) => {
  const card = $("#wp-card");
  if (!card) return;
  card.hidden = !w;
  if (!w) return;
  $("#wp-on").checked = !!w.on;
  $("#wp-body").hidden = !w.on;
  $("#wp-feats").innerHTML = w.names.map((f) => `<div class="row"><span>${esc(f.name)}<br><small class="dim">${esc(f.desc)}</small></span>
    <label class="switch"><input type="checkbox" data-wpf="${f.key}" ${w.features[f.key] ? "checked" : ""} ${w.on ? "" : "disabled"}><i></i></label></div>`).join("");
  $$("[data-wpf]").forEach((x) => (x.onchange = async () => { await act({ a: "wowplus", feature: x.dataset.wpf, on: x.checked }); loadStats(); }));
  const alts = w.features.alts ? (w.alts || []) : [];
  $("#wp-alts").innerHTML = alts.length ? `<h3>Karakterene</h3>` + alts.map((c) => `<div class="row between wp-alt">
      <span><b>${esc(c.name)}</b> <span class="dim">${c.level || ""} ${esc(c.cls || "")}</span><br>
        <small class="dim">${esc(c.zone || "")}${c.gold != null ? " · " + wpGold(c.gold) : ""}${c.durability != null && c.durability <= 30 ? ` · <span class="warn nowrap">🔧 ${c.durability} %</span>` : ""}</small></span>
      <span class="r">${c.rested != null ? `<b>${c.rested} %</b> <small class="dim">uthvilt</small><br><small class="dim">${c.full_h ? "fullt om " + wpDur(c.full_h) : "fullt uthvilt"}${c.resting ? " · 🛏️" : ""}</small>` : '<small class="dim">uthvilt: logg ut/reload</small>'}</span></div>`).join("") : "";
  wpItems = w.items || [];
  $("#wp-bagbox").hidden = !w.features.bags;
  wpSearch();
};
function wpSearch() {
  const q = ($("#wp-q").value || "").trim().toLowerCase();
  if (!q) { $("#wp-res").innerHTML = `<p class="dim small">${wpItems.length ? wpItems.length + " ting registrert. Banken leses når du åpner den i spillet." : "Ingenting registrert ennå – logg ut eller skriv /reload i WoW."}</p>`; return; }
  const hits = wpItems.filter((x) => x[2].toLowerCase().includes(q)).slice(0, 60);
  $("#wp-res").innerHTML = hits.length ? kv(hits.map((x) => [`${x[2]}`, `${x[3]} · ${x[0]} (${x[1].toLowerCase()})`])) : '<p class="dim small">Fant ingenting.</p>';
}
$("#wp-q").oninput = wpSearch;
$("#wp-on").onchange = async () => { await act({ a: "wowplus", on: $("#wp-on").checked }); loadStats(); };

window.wowPlusHtml = (o) => {
  const P = o.plus;
  if (!P) return "";
  let h = "";
  if (P.rested) h += `<h3>Uthvilt</h3>${kv([["Uthvilt XP nå", P.rested.pct + " % av en level"], ["Fullt uthvilt", P.rested.full_h ? "om " + wpDur(P.rested.full_h) : "nå"], ["Logget ut", P.rested.resting ? "på vertshus / i by 🛏️" : "ute i verden (går tregere)"]])}`;
  if (P.zone) h += kv([["Sist sett", P.zone]]);
  if (P.durability != null) h += kv([["Utstyr (dårligste del)", P.durability + " %" + (P.durability <= 20 ? " – reparer!" : "")]]);
  if (P.profs && P.profs.length) h += `<h3>Yrker</h3>` + P.profs.map((p) => `<div class="wp-prof"><div class="row between"><span>${esc(p.name)}</span><span>${p.rank} / ${p.max}${p.capped && p.max < 300 ? " – lær neste nivå" : ""}${p.per_day ? ` · ${p.per_day}/døgn` : ""}</span></div>
      <div class="bar"><i style="width:${Math.min(100, p.rank / Math.max(1, p.max) * 100)}%"></i></div></div>`).join("");
  if (P.quests && P.quests.length) h += `<h3>Questloggen (${P.quests.length})</h3>` + P.quests.map((q) => `<details class="wp-q"><summary>${q.done ? "✅" : "📜"} [${q.level || "?"}] ${esc(q.title)} <small class="dim">${esc(q.zone || "")}</small></summary>
      ${q.obj.length ? q.obj.map((x) => `<div class="small ${x.startsWith("+") ? "dim" : ""}">${esc(x.replace(/^[+-] /, x.startsWith("+") ? "✓ " : "• "))}</div>`).join("") : '<div class="small dim">Ingen mål å telle</div>'}</details>`).join("");
  if (P.locks) h += `<h3>Raid- og dungeon-låser</h3>` + (P.locks.length ? kv(P.locks.map((l) => [l.name, "nullstilles om " + wpLeft(l.reset_at)])) : '<p class="dim small">Ingen låser nå.</p>');
  if (P.gold && P.gold.length > 1) h += `<h3>Gull over tid</h3><canvas id="wp-gold" style="height:160px"></canvas>`;
  return h;
};
window.wowSheetHtml = (S) => {
  if (!S) return `<p class="dim">Egenskapene leses av addonen når du logger inn, logger ut eller skriver /reload i WoW.</p>`;
  let h = "";
  if (S.spec) h += `<div class="wp-spec"><b>${esc(S.spec)}</b>${S.talents.length ? ` <span class="dim">· ${S.talents.map((t) => t.points).join(" / ")}</span>` : ""}${S.why ? `<p class="dim small">${esc(S.why)}</p>` : ""}</div>`;
  h += `<h3>Råd</h3>` + S.tips.map((t) => `<div class="wp-tip">💡 ${esc(t)}</div>`).join("");
  if (S.prio.length) h += `<h3>Prioriter i denne rekkefølgen</h3><ol class="wp-prio">${S.prio.map((p) => `<li>${esc(p)}</li>`).join("")}</ol>`;
  h += `<h3>Egenskaper</h3>${kv(S.rows)}`;
  if (S.res.length) h += `<h3>Motstand</h3>${kv(S.res)}`;
  if (S.talents.length) h += `<h3>Talenter</h3>${kv(S.talents.map((t) => [t.name || "?", t.points + " poeng"]).concat(S.unspent ? [["Ubrukte poeng", S.unspent]] : []))}`;
  if (S.updated) h += `<p class="dim small">Lest ${new Date(S.updated * 1000).toLocaleString("nb-NO")}</p>`;
  return h;
};
window.wowPlusAfter = (o) => {
  const cv = $("#wp-gold");
  if (!cv || !o.plus || !o.plus.gold) return;
  const pts = o.plus.gold.slice(-14).map(([t, g]) => [new Date(t * 1000).toLocaleDateString("nb-NO", { day: "numeric", month: "numeric" }), g / 10000]);
  bars(cv, pts, "g");
};

// ---------- vakt: noe er bredere enn skjermen → si fra til PC-en (feilloggen) så det kan rettes ----------
let wideSent = {};
function checkWide() {
  const W = document.documentElement.clientWidth, bad = [];
  document.querySelectorAll("main *").forEach((e) => {
    const r = e.getBoundingClientRect();
    if (r.width > 0 && r.right > W + 2 && !e.closest(".quick") && !e.closest("[hidden]") && !e.closest(".statsbody.folded"))
      bad.push(`${e.tagName.toLowerCase()}${e.id ? "#" + e.id : ""}.${String(e.className || "").split(" ")[0]} (${Math.round(r.right)}px) «${(e.textContent || "").trim().slice(0, 60)}»`);
  });
  if (bad.length && !wideSent[tab]) {
    wideSent[tab] = 1;
    api("/api/action", { a: "uilog", tab, width: W, items: bad.slice(0, 8) }).catch(() => {});
  }
}

// ---------- kobling til fanene ----------
const famSetTab = setTab;
setTab = function (t) {                              // eslint-disable-line no-global-assign
  famSetTab(t);
  if (t === "spill") { loadFamily(); loadGameExtras(); loadStream(); }
  if (t === "mer") { loadLan(); loadStartup(); loadHue(); loadStream(); }
  if (t === "system") { loadBackups(); renderWidgets(); loadFamily(); }
  applyWidgets();
  setTimeout(checkWide, 2500);
};
$$("#tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
setInterval(() => tab === "spill" && !document.hidden && loadChat(), 15000);
applyDash(); applyWidgets();
if (tab === "spill") { loadFamily(); loadGameExtras(); }
