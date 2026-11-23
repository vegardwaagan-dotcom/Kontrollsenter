// ---------- Chat-fanen (28): rom og servere, bobler, bilder, avstemninger, hurtigsvar ----------
const chatSec = h(`<section id="chattab" class="page" hidden>
  <div class="card ct-gate" id="ct-gate" hidden><div class="ct-gate-in">
    <div style="font-size:42px">🔒</div><h2>Installer Tailscale først</h2>
    <p class="dim">Chatten går over Tailscale – et gratis, privat nettverk mellom PC-ene og vennene dine. Installer det
    på PC-en (og logg inn), så virker chatten her også.</p>
    <button id="ct-ts" class="primary">Installer Tailscale på PC-en</button>
    <button id="ct-ts-check" class="soft">Sjekk igjen</button><p id="ct-ts-msg" class="dim small"></p></div></div>
  <div class="card chat-card" id="ct-card">
    <div class="row between"><select id="ct-room" class="search"></select><button id="ct-ref" class="soft small">↻</button></div>
    <div id="ct-msgs" class="ct-msgs"></div>
    <div class="row"><select id="ct-quick" class="ct-qsel" aria-label="Hurtigsvar"></select>
      <input id="ct-text" maxlength="2000" placeholder="Skriv en melding …" enterkeyhint="send">
      <button id="ct-send" class="primary">Send</button></div>
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
function ctTime(t) {
  const d = new Date(t * 1000), two = (n) => String(n).padStart(2, "0");
  const today = new Date().toDateString() === d.toDateString();
  return (today ? "" : two(d.getDate()) + "." + two(d.getMonth() + 1) + " ") + two(d.getHours()) + ":" + two(d.getMinutes());
}
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
async function ctLoad() {
  try {
    const d = await X("chatroom", "room=" + encodeURIComponent(ctRoom));
    ctMe = { id: d.me_id, name: d.me };
    const box = $("#ct-msgs");
    box.innerHTML = (d.messages || []).map((m) => {
      if (String(m.from || "").startsWith("🤖")) return `<div class="ct-sys">${esc(m.text)}</div>`;
      const mine = m.from_id ? m.from_id === ctMe.id : (m.pc === ctMe.name || m.from === ctMe.name);
      let extra = "";
      if (m.attach && m.attach.kind === "image") extra += `<img class="ct-img${m.kind === "sticker" ? " st" : ""}" src="${ctFile(m.attach)}" loading="lazy">`;
      else if (m.attach && m.attach.kind === "audio") extra += `<audio controls src="${ctFile(m.attach)}"></audio>`;
      else if (m.attach) extra += `<a class="soft small" href="${ctFile(m.attach)}">📎 ${esc(m.attach.name)}</a>`;
      const poll = m.poll || m.event;
      if (poll) {
        const votes = m.votes || m.rsvp || {};
        extra += '<div class="ct-poll">' + (poll.options || []).map((o, i) => { const w = votes[String(i)] || [];
          return `<button class="soft small" data-vote="${i}" data-mid="${esc(m.id)}">${esc(o)} · ${w.length}</button>`; }).join("") + "</div>";
      }
      const re = m.reactions ? '<div class="ct-re">' + Object.entries(m.reactions).map(([e, w]) => `<span>${e} ${w.length}</span>`).join("") + "</div>" : "";
      const links = (String(m.text || "").match(/https?:\/\/\S+/g) || []).slice(0, 2).map((u) =>
        `<a class="soft small" href="${esc(u)}" target="_blank">${u.includes("/api/clipfile") ? "🎬 Se klippet" : "🔗 Åpne lenke"}</a>`).join("");
      return `<div class="ct-msg${mine ? " me" : ""}"><small>${mine ? "" : esc(m.from) + " · "}${ctTime(m.t || 0)}${m.e2e ? " 🔒" : ""}</small>` +
        (m.deleted ? '<div class="ct-b dim">(slettet)</div>' : (m.text ? `<div class="ct-b">${esc(m.text)}</div>` : "")) + extra + re + links + "</div>";
    }).join("") || '<p class="dim small">Ingen meldinger her ennå – si hei! 👋</p>';
    box.scrollTop = 1e9;
    box.querySelectorAll("[data-vote]").forEach((b) => (b.onclick = async () => {
      await act({ a: "chatvote", room: ctRoom, mid: b.dataset.mid, idx: +b.dataset.vote }, true); ctLoad(); }));
  } catch (e) { $("#ct-status").textContent = "Chat: " + e.message; }
}
async function ctSend(text) {
  text = (text || "").trim(); if (!text) return;
  $("#ct-status").textContent = "Sender …";
  try { const r = await api("/api/action", { a: "chat2", room: ctRoom, text: text }); $("#ct-status").textContent = r.msg || "Sendt"; }
  catch (e) { $("#ct-status").textContent = "✗ " + e.message; }
  ctLoad();
}
$("#ct-room").onchange = () => { ctRoom = $("#ct-room").value; setPref("ct_room", ctRoom); ctLoad(); };
$("#ct-ref").onclick = () => { ctRooms(); ctLoad(); };
$("#ct-send").onclick = () => { ctSend($("#ct-text").value); $("#ct-text").value = ""; };
$("#ct-text").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#ct-send").onclick(); });
$("#ct-quick").onchange = (e) => { const v = e.target.value; if (v) ctSend(v); e.target.value = ""; };
$("#ct-ts").onclick = async () => { $("#ct-ts-msg").textContent = "Installerer på PC-en …";
  try { const r = await api("/api/action", { a: "panel", do: "appinstall", key: "tailscale" }); $("#ct-ts-msg").textContent = r.msg || "Startet – logg inn i Tailscale på PC-en"; }
  catch (e) { $("#ct-ts-msg").textContent = "✗ " + e.message; } };
$("#ct-ts-check").onclick = () => ctRooms();
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
