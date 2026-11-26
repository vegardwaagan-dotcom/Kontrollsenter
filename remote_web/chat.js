// ---------- Chat-fanen (28): rom og servere, bobler, bilder, avstemninger, hurtigsvar ----------
const chatSec = h(`<section id="chattab" class="page" hidden>
  <div class="card ct-gate" id="ct-gate" hidden><div class="ct-gate-in">
    <div style="font-size:42px">🔒</div><h2>Installer Tailscale først</h2>
    <p class="dim">Chatten går over Tailscale – et gratis, privat nettverk mellom PC-ene og vennene dine. Installer det
    på PC-en (og logg inn), så virker chatten her også.</p>
    <button id="ct-ts" class="primary">Installer Tailscale på PC-en</button>
    <button id="ct-ts-check" class="soft">Sjekk igjen</button><p id="ct-ts-msg" class="dim small"></p></div></div>
  <div class="card chat-card" id="ct-card">
    <div class="row ct-head"><select id="ct-room" class="search"></select><button id="ct-cam" class="soft small" title="Bruk mobilen som webkamera for PC-en">📷</button><button id="ct-more" class="soft small" title="Visning, Ikke forstyrr, status">⋯</button><button id="ct-ref" class="soft small">↻</button></div>
    <div id="ct-dnd" class="ct-dnd" hidden></div>
    <button id="ct-pin" class="ct-pinbar" hidden></button>
    <div id="ct-play" class="ct-playing" hidden></div>
    <div class="ct-wrap"><div id="ct-msgs" class="ct-msgs"></div><button id="ct-jump" class="primary ct-jump" hidden>↓ Nye meldinger</button></div>
    <div id="ct-reply" class="ct-replybar" hidden><span id="ct-reply-t"></span><button id="ct-reply-x" class="soft small">✕</button></div>
    <div id="ct-rec" class="ct-rec" hidden><span class="ct-dot"></span><span id="ct-rec-t">0 s</span><span id="ct-rec-w" class="ct-recw"></span><button id="ct-rec-x" class="soft small">Avbryt</button></div>
    <div class="row ct-inrow"><button id="ct-att" class="soft small" title="Bilde eller fil">📎</button>
      <select id="ct-quick" class="ct-qsel" aria-label="Hurtigsvar"></select>
      <input id="ct-text" maxlength="2000" placeholder="Skriv en melding … ( / for kommandoer)" enterkeyhint="send">
      <button id="ct-mic" class="soft small" title="Talemelding">🎙️</button>
      <button id="ct-send" class="primary ct-sendb" aria-label="Send">↑</button></div>
    <input type="file" id="ct-file" hidden>
    <p id="ct-status" class="dim small"></p>
  </div></section>`);
{ const anchor = document.getElementById("system"); if (anchor) anchor.parentElement.insertBefore(chatSec, anchor.nextSibling); }
{ const nav = document.getElementById("tabs"); if (nav) {
  const b = document.createElement("button"); b.dataset.tab = "chat";
  b.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V6a1 1 0 0 1 1-1z"/></svg><span>Chat</span><i id="ct-badge" class="ct-badge" hidden></i>';
  b.onclick = () => setTab("chat");
  nav.insertBefore(b, nav.querySelector('[data-tab="system"]'));
} }
const QUICK = ["Kommer! 🏃", "5 min til ⏳", "Lagrer nå 💾", "👍", "😂", "🎉"];
$("#ct-quick").innerHTML = '<option value="">⚡</option>' + QUICK.map((q) => `<option value="${esc(q)}">${esc(q)}</option>`).join("");
let ctRoom = pref("ct_room", "alle"), ctMe = { id: "", name: "" }, ctTimer = null;
function ctGate(ts) {                                   // uten Tailscale: bare «Installer Tailscale først»
  $("#ct-gate").hidden = !!ts.running; $("#ct-card").hidden = !ts.running;
  if (!ts.running) $("#ct-ts-msg").textContent = ts.installed ? "Tailscale er installert på PC-en, men ikke pålogget – åpne Tailscale og logg inn." : "";
  return !!ts.running;
}
async function ctRooms() {
  try {
    const all = await X("chatrooms");
    if (!ctGate(all.tailscale || { running: true })) return;
    const r = all.rooms || [];
    const unread = r.reduce((a, x) => a + (x.unread || 0), 0);
    const bd = $("#ct-badge"); if (bd) { bd.hidden = !unread; bd.textContent = unread > 9 ? "9+" : unread; }
    const sel = $("#ct-room");
    const groups = { "Direkte": r.filter((x) => !x.id.startsWith("s:")), "Servere": r.filter((x) => x.id.startsWith("s:")) };
    sel.innerHTML = Object.entries(groups).filter(([, v]) => v.length).map(([g, v]) => `<optgroup label="${g}">` +
      v.map((x) => `<option value="${esc(x.id)}">${esc(x.icon)} ${esc(x.name)}${x.unread ? " (" + x.unread + ")" : ""}</option>`).join("") + "</optgroup>").join("");
    if (r.some((x) => x.id === ctRoom)) sel.value = ctRoom; else { ctRoom = sel.value; }
  } catch (e) { $("#ct-status").textContent = "Chat: " + e.message; }
}
function ctFile(att) { return "/api/chatfile?k=" + encodeURIComponent(token) + "&sha=" + encodeURIComponent(att.sha) + "&name=" + encodeURIComponent(att.name); }
// ---------- samme utseende som på PC-en: grupperte bobler, profilbilder, datoskiller, store emojier ----------
const CT_BG = { "": "none", nordlys: "radial-gradient(ellipse at 10% 0%,#2ef2b34d,transparent 60%),radial-gradient(ellipse at 100% 30%,#7c5cff47,transparent 60%)",
  solnedgang: "linear-gradient(180deg,#ff8a3d38,#ff3d7f2e 60%,#3a1c7133)", hav: "linear-gradient(200deg,#00c2ff38,#3a5bff29 70%)",
  galakse: "radial-gradient(ellipse at 80% 10%,#c86bff4d,transparent 55%),radial-gradient(ellipse at 10% 90%,#ff5fa238,transparent 55%)",
  skog: "linear-gradient(160deg,#5bd68a33,transparent 70%)", lava: "radial-gradient(ellipse at 50% 120%,#ff4d1a59,transparent 65%)" };
const CT_BG_NAMES = { "": "Ingen", nordlys: "Nordlys", solnedgang: "Solnedgang", hav: "Dyphav", galakse: "Galakse", skog: "Skog", lava: "Lava" };
const PAL = ["#ff6b6b", "#ff9f43", "#feca57", "#1dd1a1", "#48dbfb", "#54a0ff", "#5f27cd", "#c56cf0", "#ff6bcb", "#10ac84", "#2e86de", "#ee5253"];
let ctData = null, ctSeen = {}, ctReply = null, ctPrev = {}, ctShownRoom = null;
function ctColor(n) { return (ctData && ctData.colors && ctData.colors[n]) || PAL[[...String(n || "?")].reduce((a, c) => a + c.charCodeAt(0), 0) % PAL.length]; }
function ctInit(n) { const p = String(n || "?").trim().split(/[\s\-_.]+/).filter(Boolean); return p.length > 1 ? (p[0][0] + p[1][0]).toUpperCase() : (p[0] || "?").slice(0, 2).toUpperCase(); }
function ctEmojiOnly(t) { t = String(t || "").replace(/\s/g, ""); if (!t || t.length > 24) return 0;
  if (!/^(?:\p{Extended_Pictographic}|\p{Emoji_Modifier}|️|‍|[\u{1F1E6}-\u{1F1FF}])+$/u.test(t)) return 0;
  const n = [...t.matchAll(/\p{Extended_Pictographic}/gu)].length; return n >= 1 && n <= 3 ? n : 0; }
function ctDay(t) {
  const d = new Date(t * 1000), now = new Date(), start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((start(now) - start(d)) / 864e5);
  if (days === 0) return "I dag"; if (days === 1) return "I går";
  const wd = ["Søndag", "Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag"][d.getDay()];
  const mo = ["jan.", "feb.", "mars", "april", "mai", "juni", "juli", "aug.", "sep.", "okt.", "nov.", "des."][d.getMonth()];
  return `${wd} ${d.getDate()}. ${mo}` + (d.getFullYear() !== now.getFullYear() ? " " + d.getFullYear() : "");
}
const two = (n) => String(n).padStart(2, "0");
function ctHM(t) { const d = new Date(t * 1000); return two(d.getHours()) + ":" + two(d.getMinutes()); }
function ctMine(m) { const d = ctData || {}; return m.from_id ? m.from_id === ctMe.id : (m.pc === d.me_pc || m.from === d.me_pc || m.from === ctMe.name); }
function ctWave(w) { return '<span class="ct-wave">' + (w || []).map((v) => `<i style="height:${15 + 85 * v / 9}%"></i>`).join("") + "</span>"; }
function ctBubble(m, mine, by) {
  let txt = m.deleted ? "(slettet)" : String(m.text || "");
  const att = m.attach || null, big = !m.deleted && ctEmojiOnly(txt);
  let html = "";
  if (m.reply && by[m.reply]) html += `<div class="ct-q">↪ ${esc(by[m.reply].from)}: ${esc(String(by[m.reply].text || "").slice(0, 60))}</div>`;
  const auto = att && ((att.kind === "audio" && txt.startsWith("🎙️")) || (att.kind === "image" && (txt === "🖼️ Bilde" || !txt)));
  if (!auto && txt) html += `<div class="${big ? "ct-emoji" : "ct-b"}">${esc(txt)}</div>`;
  if (att && att.kind === "image") html += `<img class="ct-img${m.kind === "sticker" ? " st" : ""}" src="${ctFile(att)}" loading="lazy">`;
  else if (att && att.kind === "audio") html += `<div class="ct-voice"><button class="ct-play" data-src="${ctFile(att)}">▶</button>${ctWave(att.wave || [3,5,2,6,4,7,3,5,2,4,6,3,5,2,4,3,6,2,4,3])}<small>${att.secs ? Math.floor(att.secs / 60) + ":" + two(Math.round(att.secs % 60)) : ""}</small></div>`;
  else if (att) html += `<a class="soft small" href="${ctFile(att)}">📎 ${esc(att.name)}</a>`;
  const poll = m.poll || m.event;
  if (poll) { const votes = m.votes || m.rsvp || {};
    html += '<div class="ct-poll">' + (poll.options || []).map((o, i) => `<button class="soft small" data-vote="${i}" data-mid="${esc(m.id)}">${esc(o)} · ${(votes[String(i)] || []).length}</button>`).join("") + "</div>"; }
  if (m.play && !mine) html += `<button class="primary small" data-join="${esc(m.play.game)}">🎮 Bli med i ${esc(m.play.game)}</button>`;
  if (!m.deleted) (txt.match(/https?:\/\/\S+/g) || []).slice(0, 2).forEach((u) => {
    html += u.includes("/api/clipfile") ? `<a class="soft small" href="${esc(u)}" target="_blank">🎬 Se klippet</a>` : `<a class="ct-link" data-url="${esc(u)}" href="${esc(u)}" target="_blank">🔗 ${esc(u.slice(0, 50))}</a>`; });
  if (m.reactions) html += '<div class="ct-re">' + Object.entries(m.reactions).map(([e, w]) => `<span data-react="${e}" data-mid="${esc(m.id)}">${e} ${w.length}</span>`).join("") + "</div>";
  return html;
}
async function ctLoad() {
  try {
    const d = await X("chatroom2", "room=" + encodeURIComponent(ctRoom));
    ctData = d; ctMe = { id: d.me_id, name: d.me };
    const box = $("#ct-msgs"), msgs = d.messages || [], by = {};
    msgs.forEach((m) => (by[m.id] = m));
    const same = ctShownRoom === ctRoom, seen = same ? (ctSeen[ctRoom] || new Set()) : null;
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 60;
    box.classList.toggle("compact", !!pref("ct_compact", false));
    box.style.backgroundImage = CT_BG[(pref("ct_bg", {}) || {})[ctRoom] || ""] || "none";
    let out = "", lastDay = "", prev = null, newDone = !!same;
    const mark = same ? (ctPrev[ctRoom] || 0) : (d.newmark || 0);
    for (const [mi, m] of msgs.entries()) {
      const t = m.t || 0, day = ctDay(t);
      if (day !== lastDay) { out += `<div class="ct-day"><span>${day}</span></div>`; lastDay = day; prev = null; }
      if (String(m.from || "").startsWith("🤖")) { out += `<div class="ct-sys">${esc(m.text)}</div>`; prev = null; continue; }
      const mine = ctMine(m);
      if (!mine && mark && t > mark && !newDone) { out += '<div class="ct-new" id="ct-newline"><span>NYE MELDINGER</span></div>'; newDone = true; prev = null; }
      const who = m.from_id || m.pc || m.from, cont = prev && prev[0] === who && t - prev[1] < 300; prev = [who, t];
      const av = (d.avatars && m.from_id && d.avatars[m.from_id]) || "", pres = d.presence && m.from_id ? d.presence[m.from_id] : "";
      const dot = pres === "🟢" ? "on" : pres === "🎮" ? "game" : "";
      const fresh = seen && !seen.has(m.id) ? " ct-in" : "";
      out += `<div class="ct-row${mine ? " me" : ""}${cont ? " cont" : ""}${fresh}" data-mid="${esc(m.id)}" data-i="${mi}">` +
        (mine ? "" : cont ? '<span class="ct-av sp"></span>' : `<span class="ct-av${av ? " emo" : ""}" style="--c:${ctColor(m.from)}">${esc(av || ctInit(m.from))}${dot ? `<i class="${dot}"></i>` : ""}</span>`) +
        `<div class="ct-msg${mine ? " me" : ""}">` +
        (cont ? "" : `<small>${mine ? "" : `<b style="color:${ctColor(m.from)}">${esc(m.from)}</b> `}${ctHM(t)}${m.edited ? " · redigert" : ""}${m.pinned ? " 📌" : ""}${m.e2e ? " 🔒" : ""}</small>`) +
        ctBubble(m, mine, by) + "</div></div>";
    }
    const mineMsgs = msgs.filter((m) => ctMine(m) && !m.deleted);
    if (ctRoom.startsWith("p:") && mineMsgs.length && mineMsgs[mineMsgs.length - 1] === msgs[msgs.length - 1]) {
      const last = mineMsgs[mineMsgs.length - 1];
      out += `<div class="ct-receipt">${d.seen_by >= last.t ? "✓✓ Lest " + ctHM(d.seen_by) : "✓ Sendt"}</div>`;
    }
    box.innerHTML = out || '<p class="dim small">Ingen meldinger her ennå – si hei! 👋</p>';
    ctSeen[ctRoom] = new Set(msgs.map((m) => m.id)); ctPrev[ctRoom] = Date.now() / 1000;
    // festet, spiller nå, Ikke forstyrr
    const pins = msgs.filter((m) => m.pinned && !m.deleted);
    $("#ct-pin").hidden = !pins.length;
    if (pins.length) { const l = pins[pins.length - 1]; $("#ct-pin").textContent = `📌 ${l.from}: ${String(l.text || "").slice(0, 70)}` + (pins.length > 1 ? `  (+${pins.length - 1})` : "");
      $("#ct-pin").onclick = () => ctSheet("📌 Festet", pins.slice().reverse().map((m) => `<div class="card small"><b>${esc(m.from)}</b> · ${ctHM(m.t)}<br>${esc(m.text || "")}</div>`).join("")); }
    $("#ct-play").hidden = !(d.playing || []).length;
    $("#ct-play").innerHTML = (d.playing || []).map((p) => `<button class="soft small" data-join="${esc(p.game)}">🎮 ${esc(p.name)} · ${esc(p.game)}${p.since ? " · " + ctDur(Date.now() / 1000 - p.since) : ""}</button>`).join("");
    $("#ct-dnd").hidden = !d.dnd; $("#ct-dnd").textContent = d.dnd ? "🚫 " + d.dnd : "";
    // hopp / bunn
    const nl = document.getElementById("ct-newline");
    if (!same && nl) { box.scrollTop = Math.max(0, nl.offsetTop - 40); $("#ct-jump").hidden = box.scrollTop + box.clientHeight >= box.scrollHeight - 40; $("#ct-jump").textContent = "↓ Til bunnen"; }
    else if (same && !atBottom && seen && msgs.some((m) => !seen.has(m.id))) { $("#ct-jump").hidden = false; $("#ct-jump").textContent = "↓ Nye meldinger"; }
    else { box.scrollTop = 1e9; $("#ct-jump").hidden = true; }
    ctShownRoom = ctRoom;
    ctWire(box, by, msgs);
  } catch (e) { $("#ct-status").textContent = "Chat: " + e.message; }
}
function ctDur(s) { const m = Math.floor(s / 60); return m >= 60 ? `${Math.floor(m / 60)} t ${m % 60} min` : `${m} min`; }
const LP = {};
function ctWire(box, by, msgs) {
  box.querySelectorAll("[data-vote]").forEach((b) => (b.onclick = async () => { await act({ a: "chatvote", room: ctRoom, mid: b.dataset.mid, idx: +b.dataset.vote }, true); ctLoad(); }));
  box.querySelectorAll("[data-react]").forEach((b) => (b.onclick = () => ctEv(b.dataset.mid, "react", { emoji: b.dataset.react })));
  document.querySelectorAll("[data-join]").forEach((b) => (b.onclick = () => act({ a: "chat2", room: ctRoom, text: "/spill " + b.dataset.join }, true)));
  box.querySelectorAll(".ct-play").forEach((b) => (b.onclick = () => { const a = new Audio(b.dataset.src); b.textContent = "⏸"; a.onended = () => (b.textContent = "▶"); a.play(); }));
  box.querySelectorAll(".ct-link").forEach(async (a) => {                    // lenkekort med bilde
    const u = a.dataset.url; let pv = LP[u];
    if (pv === undefined) { try { pv = LP[u] = await X("linkprev", "url=" + encodeURIComponent(u)); } catch (e) { pv = LP[u] = { ok: false }; } }
    if (pv && pv.ok) a.outerHTML = `<a class="ct-card" href="${esc(u)}" target="_blank">${pv.site ? `<small>${esc(pv.site)}</small>` : ""}<b>${esc(pv.title || u)}</b>${pv.desc ? `<span>${esc(pv.desc)}</span>` : ""}${pv.image ? `<img src="${pv.image}" loading="lazy">` : ""}</a>`;
  });
  box.querySelectorAll(".ct-row").forEach((row) => {                        // hold inne / høyreklikk: meny
    const m = (msgs || [])[+row.dataset.i] || by[row.dataset.mid]; if (!m) return;
    let tm = null;
    const open = (e) => { e && e.preventDefault(); ctMenu(m); };
    row.addEventListener("contextmenu", open);
    row.addEventListener("touchstart", () => { tm = setTimeout(() => { tm = null; if (KS && KS.vibrate) KS.vibrate(); ctMenu(m); }, 480); }, { passive: true });
    ["touchend", "touchmove", "touchcancel"].forEach((ev) => row.addEventListener(ev, () => tm && clearTimeout(tm), { passive: true }));
  });
}
function ctSheet(title, html, after) {
  document.querySelectorAll(".ct-sheet").forEach((x) => x.remove());
  const bg = h(`<div class="sheet-back ct-sheet"><div class="sheet"><div class="row between"><b>${title}</b><button class="soft small ct-x">✕</button></div><div class="ct-sheet-in">${html}</div></div></div>`);
  document.body.appendChild(bg); setTimeout(() => bg.classList.add("open"), 20);
  const close = () => bg.remove();
  bg.onclick = (e) => { if (e.target === bg) close(); }; bg.querySelector(".ct-x").onclick = close;
  if (after) after(bg, close);
  return close;
}
function ctMenu(m) {
  const mine = ctMine(m);
  const items = [["↪ Svar", () => { ctReply = m; $("#ct-reply").hidden = false; $("#ct-reply-t").textContent = `↪ Svarer ${m.from}: ${String(m.text || "").slice(0, 50)}`; $("#ct-text").focus(); }],
    ["📋 Kopier", () => { ksCopy(m.text || "").then((ok) => toast(ok ? "Kopiert" : "Kunne ikke kopiere")); }],
    [m.pinned ? "📌 Løsne" : "📌 Fest", () => ctEv(m.id, "pin", { on: !m.pinned })],
    ["🤖 Spør AI om denne", () => { if (window.ksAiAsk) window.ksAiAsk("Forklar kort: " + (m.text || "")); }]];
  if (mine) items.push(["✏️ Rediger", async () => { const t = prompt("Rediger meldingen", m.text || ""); if (t) ctEv(m.id, "edit", { text: t }); }],
    ["🗑️ Slett", async () => { if (await confirmDlg("Slette meldingen?")) ctEv(m.id, "delete", {}); }]);
  ctSheet(esc(String(m.text || "Melding").slice(0, 40)),
    '<div class="ct-reacts">' + ["👍", "😂", "❤️", "😮", "🎉", "🔥"].map((e) => `<button class="soft" data-e="${e}">${e}</button>`).join("") + "</div>" +
    items.map(([l], i) => `<button class="soft full" data-i="${i}">${l}</button>`).join(""),
    (bg, close) => {
      bg.querySelectorAll("[data-e]").forEach((b) => (b.onclick = () => { close(); ctEv(m.id, "react", { emoji: b.dataset.e }); }));
      bg.querySelectorAll("[data-i]").forEach((b) => (b.onclick = () => { close(); items[+b.dataset.i][1](); }));
    });
}
async function ctEv(mid, type, extra) {
  try { await api("/api/action", Object.assign({ a: "chatev", room: ctRoom, mid: mid, type: type }, extra)); } catch (e) { toast("✗ " + e.message); }
  setTimeout(ctLoad, 250);
}
async function ctSend(text) {
  text = (text || "").trim(); if (!text) return;
  $("#ct-status").textContent = "Sender …";
  const body = { a: "chat2", room: ctRoom, text: text };
  if (ctReply) { body.reply = ctReply.id; ctReply = null; $("#ct-reply").hidden = true; }
  try {
    const r = await api("/api/action", body); const msg = r.msg || "Sendt";
    if (msg.startsWith("GIF:")) { $("#ct-status").textContent = ""; ctGif(msg.slice(4)); }
    else { $("#ct-status").textContent = msg.length > 160 ? "" : msg; if (text.startsWith("/hjelp")) ctSheet("Kommandoer", `<pre class="small">${esc(msg)}</pre>`); }
  } catch (e) { $("#ct-status").textContent = "✗ " + e.message; }
  ctLoad();
}
async function ctGif(q) {
  let r; try { r = await X("gifs", "q=" + encodeURIComponent(q || "hei")); } catch (e) { toast("✗ " + e.message); return; }
  if (!r.key) {
    const k = prompt("GIF-søket bruker Tenor (gratis). Lag en nøkkel på developers.google.com/tenor og lim den inn:");
    if (k) { await act({ a: "tenorkey", key: k }, true); ctGif(q); } return;
  }
  ctSheet("GIF", `<input id="gif-q" class="search" value="${esc(q || "")}" placeholder="Søk …"><div class="ct-gifs">` +
    r.results.map((g) => `<img src="${esc(g.tiny)}" data-big="${esc(g.big)}" loading="lazy">`).join("") + "</div>", (bg, close) => {
      bg.querySelectorAll("[data-big]").forEach((im) => (im.onclick = async () => { close(); $("#ct-status").textContent = "Sender GIF …";
        try { await api("/api/action", { a: "chatgif", room: ctRoom, url: im.dataset.big }); } catch (e) { toast("✗ " + e.message); } ctLoad(); }));
      bg.querySelector("#gif-q").addEventListener("keydown", (e) => { if (e.key === "Enter") { close(); ctGif(e.target.value); } });
    });
}
// vedlegg og talemeldinger
$("#ct-att").onclick = () => $("#ct-file").click();
$("#ct-file").onchange = async (e) => {
  const f = e.target.files[0]; e.target.value = ""; if (!f) return;
  if (f.size > 8 * 1048576) { toast("Maks 8 MB"); return; }
  $("#ct-status").textContent = "Sender " + f.name + " …";
  const data = await new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1]); r.readAsDataURL(f); });
  try { const r = await api("/api/chatup", { room: ctRoom, name: f.name, data: data }); $("#ct-status").textContent = r.msg || "Sendt"; }
  catch (err) { $("#ct-status").textContent = "✗ " + err.message; }
  ctLoad();
};
let ctRecS = null;
function ctWave(levels) {                     // 40 søyler (0–9) fra lydnivåene under opptaket
  const n = 40, step = Math.max(1, levels.length / n), wave = [];
  for (let i = 0; i < n; i++) { const c = levels.slice(Math.floor(i * step), Math.floor((i + 1) * step)); wave.push(Math.round(Math.min(1, Math.max(0, ...c, 0) * 1.6) * 9)); }
  return wave;
}
async function ctSendVoice(name, data, levels, secs) {
  $("#ct-status").textContent = "Sender talemelding …";
  try { await api("/api/chatup", { room: ctRoom, name: name, data: data, kind: "audio", wave: ctWave(levels), secs: secs }); $("#ct-status").textContent = "Sendt ✓"; }
  catch (e) { $("#ct-status").textContent = "✗ " + e.message; }
  ctLoad();
}
// Android-appen: sidene kommer over http fra PC-en, og der finnes ikke navigator.mediaDevices – appen tar opp selv
window.ksRecPermission = (ok) => { if (ok) $("#ct-mic").click(); else toast("Appen fikk ikke bruke mikrofonen – gi lov under Innstillinger › Apper"); };
function ctRecNative() {
  const r = KS.recStart();
  if (r === "perm") return;                   // appen spør om lov – opptaket starter når du sier ja
  if (r !== "ok") { toast("Fikk ikke startet opptaket"); return; }
  const levels = [], t0 = Date.now();
  $("#ct-rec").hidden = false; $("#ct-mic").textContent = "⏹️";
  const iv = setInterval(() => { const pk = Math.min(1, (KS.recLevel() || 0) / 32767); levels.push(pk);
    $("#ct-rec-t").textContent = Math.round((Date.now() - t0) / 1000) + " s"; $("#ct-rec-w").style.width = Math.min(100, pk * 100) + "%"; }, 100);
  ctRecS = { stop: (ok) => {
    clearInterval(iv); $("#ct-rec").hidden = true; $("#ct-mic").textContent = "🎙️"; ctRecS = null;
    const secs = (Date.now() - t0) / 1000, keep = !!ok && secs >= 0.7;
    const data = KS.recStop(keep);
    if (!keep) return;
    if (!data) { toast("Opptaket ble tomt – prøv igjen"); return; }
    ctSendVoice("tale.m4a", data, levels, secs);
  } };
}
$("#ct-mic").onclick = async () => {
  if (ctRecS) { ctRecS.stop(true); return; }
  if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
    if (KS && KS.recStart) { ctRecNative(); return; }
    toast(KS ? "Talemeldinger krever nyeste versjon av appen – oppdater den" : "Talemeldinger virker bare i appen eller på https");
    return;
  }
  let stream; try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch (e) { toast("Fikk ikke bruke mikrofonen – gi appen lov under Innstillinger"); return; }
  const rec = new MediaRecorder(stream), chunks = [], levels = [], t0 = Date.now();
  const ac = new AudioContext(), an = ac.createAnalyser(); ac.createMediaStreamSource(stream).connect(an); an.fftSize = 512;
  const buf = new Uint8Array(an.fftSize);
  const iv = setInterval(() => { an.getByteTimeDomainData(buf); let pk = 0; buf.forEach((v) => (pk = Math.max(pk, Math.abs(v - 128)))); levels.push(pk / 128);
    $("#ct-rec-t").textContent = Math.round((Date.now() - t0) / 1000) + " s"; $("#ct-rec-w").style.width = Math.min(100, pk / 1.28) + "%"; }, 100);
  rec.ondataavailable = (e) => chunks.push(e.data);
  let send = true;
  rec.onstop = async () => {
    clearInterval(iv); stream.getTracks().forEach((t) => t.stop()); ac.close(); $("#ct-rec").hidden = true; $("#ct-mic").textContent = "🎙️"; ctRecS = null;
    const secs = (Date.now() - t0) / 1000; if (!send || secs < 0.7) return;
    const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
    const data = await new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1]); r.readAsDataURL(blob); });
    ctSendVoice("tale.webm", data, levels, secs);
  };
  rec.start(); $("#ct-rec").hidden = false; $("#ct-mic").textContent = "⏹️";
  ctRecS = { stop: (ok) => { send = ok; rec.stop(); } };
};
$("#ct-rec-x").onclick = () => ctRecS && ctRecS.stop(false);
$("#ct-reply-x").onclick = () => { ctReply = null; $("#ct-reply").hidden = true; };
$("#ct-jump").onclick = () => { const b = $("#ct-msgs"); b.scrollTop = 1e9; $("#ct-jump").hidden = true; };
$("#ct-msgs").addEventListener("scroll", () => { const b = $("#ct-msgs"); if (b.scrollTop + b.clientHeight >= b.scrollHeight - 40) $("#ct-jump").hidden = true; });
$("#ct-more").onclick = () => {
  const bgs = pref("ct_bg", {}) || {};
  ctSheet("Chat", `<div class="label">Bakgrunn i denne samtalen</div><div class="ct-bgs">` +
    Object.keys(CT_BG).map((k) => `<button class="soft${(bgs[ctRoom] || "") === k ? " on" : ""}" data-bg="${k}" style="background-image:${CT_BG[k]}">${CT_BG_NAMES[k]}</button>`).join("") + "</div>" +
    `<div class="row"><span>Kompakt visning</span><label class="switch"><input type="checkbox" id="ct-cmp"${pref("ct_compact", false) ? " checked" : ""}><i></i></label></div>` +
    `<div class="label">Ikke forstyrr</div><div class="ct-dndb">` + [["1", "1 t"], ["2", "2 t"], ["8", "8 t"], ["-1", "Til i morgen"], ["0", "Av"]].map(([v, l]) => `<button class="soft small" data-dnd="${v}">${l}</button>`).join("") + "</div>" +
    `<div class="label">Status</div><div class="row"><input id="ct-st" class="search" placeholder="F.eks. «På skolen til 15»"><button class="soft small" id="ct-st-ok">Lagre</button></div>` +
    `<button class="soft full" id="ct-missed">✨ Hva har jeg gått glipp av?</button><button class="soft full" id="ct-gifb">🎞️ GIF …</button><button class="soft full" id="ct-help">❓ Kommandoer (/hjelp)</button>`, (bg, close) => {
      bg.querySelectorAll("[data-bg]").forEach((b) => (b.onclick = () => { const o = pref("ct_bg", {}) || {}; o[ctRoom] = b.dataset.bg; setPref("ct_bg", o); close(); ctLoad(); }));
      bg.querySelector("#ct-cmp").onchange = (e) => { setPref("ct_compact", e.target.checked); ctLoad(); };
      bg.querySelectorAll("[data-dnd]").forEach((b) => (b.onclick = async () => { close(); const r = await api("/api/action", { a: "chatdnd", hours: +b.dataset.dnd }); toast(r.msg); ctLoad(); }));
      bg.querySelector("#ct-st-ok").onclick = async () => { await act({ a: "chatstatus", text: bg.querySelector("#ct-st").value }, true); close(); toast("Status lagret"); };
      bg.querySelector("#ct-gifb").onclick = () => { close(); ctGif(""); };
      bg.querySelector("#ct-missed").onclick = async () => {
        close(); toast("✨ AI-en leser samtalen …");
        const r = await api("/api/action", { a: "aimissed", room: ctRoom }).catch((e) => ({ ok: false, msg: e.message }));
        if (!r.ok) return toast("Feil: " + r.msg);
        for (let i = 0; i < 60; i++) { await new Promise((res) => setTimeout(res, 2000));
          const j = await api("/api/x/aimissed?id=" + r.msg).catch(() => ({}));
          if (j.done) { ctSheet("Hva har jeg gått glipp av?", `<div style="white-space:pre-line">${esc(j.text)}</div>`, () => {}); return; } }
        toast("AI-en brukte for lang tid");
      };
      bg.querySelector("#ct-help").onclick = () => { close(); ctSend("/hjelp"); };
    });
};
$("#ct-room").onchange = () => { ctRoom = $("#ct-room").value; setPref("ct_room", ctRoom); ctLoad(); };
$("#ct-ref").onclick = () => { ctRooms(); ctLoad(); };
$("#ct-send").onclick = () => { ctSend($("#ct-text").value); $("#ct-text").value = ""; };
$("#ct-text").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#ct-send").onclick(); });
$("#ct-quick").onchange = (e) => { const v = e.target.value; if (v) ctSend(v); e.target.value = ""; };
$("#ct-ts").onclick = async () => { $("#ct-ts-msg").textContent = "Installerer på PC-en …";
  try { const r = await api("/api/action", { a: "panel", do: "appinstall", key: "tailscale" }); $("#ct-ts-msg").textContent = r.msg || "Startet – logg inn i Tailscale på PC-en"; }
  catch (e) { $("#ct-ts-msg").textContent = "✗ " + e.message; } };
$("#ct-ts-check").onclick = () => ctRooms();
$("#ct-cam").onclick = async () => {                     // mobilen som webkamera (kamera-skjerm i Android-appen)
  if (!window.KS) { toast("Mobilkamera virker bare i Android-appen"); return; }
  if (typeof KS.camera !== "function") {                // eldre app uten kamera-skjermen
    if (KS.update && await confirmDlg("Mobilkamera krever den nye versjonen av appen. Oppdatere nå?")) {
      KS.update(location.origin + "/api/apk");
    } else toast("Oppdater appen for å bruke mobilkameraet");
    return;
  }
  try { await X("phonecam"); }                          // PC-en må ha 0.90 eller nyere (og være startet på nytt)
  catch (e) { toast("PC-en kjører en eldre Kontrollsenter – start Kontrollsenter på nytt på PC-en og prøv igjen"); return; }
  toast("Åpner kameraet …");
  KS.camera(token);
};
{ const _st3 = setTab; setTab = function (t) {                  // eslint-disable-line no-global-assign
  _st3(t);
  $("#chattab").hidden = t !== "chat" || !token;
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  clearInterval(ctTimer);
  if (t === "chat") { ctRooms().then(ctLoad); ctTimer = setInterval(() => { ctLoad(); ctRooms(); }, 8000); }
}; }
window.ksOpenChat = (room) => { ctRoom = room; setPref("ct_room", room); setTab("chat"); };
// åpnet fra et chat-varsel: «#chat:<rom>»
if (location.hash.startsWith("#chat:")) { ctRoom = decodeURIComponent(location.hash.slice(6)); setTimeout(() => setTab("chat"), 600); }
setInterval(() => { if (token && tab !== "chat") ctRooms(); }, 60000);
setTimeout(() => token && ctRooms(), 3000);
