// ---------- AI-fanen: samme AI som på PC-en (Claude, Codex, Gemini, lokal) – samtalene, svar ord for ord,
// «hva AI-en gjorde», Godta/Avbryt, bilder, tale inn (telefonens talegjenkjenning) og opplesning ----------
const aiSec = h(`<section id="aitab" class="page" hidden>
  <div class="card ai-card">
    <select id="ai-conv" class="search ai-full"></select>
    <div class="ai-bar"><select id="ai-tool" class="search"></select><button id="ai-new" class="soft" title="Ny samtale">＋</button><button id="ai-more" class="soft">⋯</button></div>
    <div id="ai-quota" class="dim small"></div>
    <div id="ai-msgs" class="ai-msgs"></div>
    <div id="ai-chips" class="row" hidden></div>
    <div class="row ai-in"><button id="ai-att" class="soft small" title="Legg ved bilde">📎</button>
      <textarea id="ai-text" rows="1" placeholder="Spør om hva som helst …"></textarea>
      <button id="ai-mic" class="soft small" title="Snakk">🎙️</button><button id="ai-send" class="primary">↑</button></div>
    <input type="file" id="ai-file" accept="image/*" hidden>
    <p id="ai-status" class="dim small"></p>
  </div></section>`);
{ const anchor = document.getElementById("chattab") || document.getElementById("system");
  if (anchor) anchor.parentElement.insertBefore(aiSec, anchor.nextSibling); }
{ const nav = document.getElementById("tabs"); if (nav) {
  const b = document.createElement("button"); b.dataset.tab = "ai";
  b.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2-2.2-.8 2.2-.8z"/></svg><span>AI</span>';
  b.onclick = () => setTab("ai");
  nav.insertBefore(b, nav.querySelector('[data-tab="system"]'));
} }
let aiSt = null, aiCid = pref("ai_cid", ""), aiJob = null, aiImgs = [], aiTimer = null;
const aiCol = (t) => ((aiSt && aiSt.tools.find((x) => x.id === t)) || {}).color || "#888";
const aiName = (t) => ((aiSt && aiSt.tools.find((x) => x.id === t)) || {}).name || "AI";
function aiMd(t) {                                        // ```kode``` i egne bokser med «Kopier»
  return String(t || "").split("```").map((p, i) => {
    if (i % 2 === 0) return `<div class="ai-p">${esc(p.trim())}</div>`;
    let lang = ""; const nl = p.indexOf("\n");
    if (nl > 0 && /^[\w-]+$/.test(p.slice(0, nl).trim())) { lang = p.slice(0, nl).trim(); p = p.slice(nl + 1); }
    return `<div class="ai-code"><div class="row between"><small>${esc(lang || "kode")}</small><button class="soft small" data-copy="${esc(p)}">📋 Kopier</button></div><pre>${esc(p.replace(/\n$/, ""))}</pre></div>`;
  }).join("");
}
function aiBubble(m) {
  if (m.role === "user") return `<div class="ai-row me"><div class="ai-b me">${esc(m.text)}</div></div>`;
  const tools = (m.tools || []).map((t) => `<div class="ai-tool">${esc(t)}</div>`).join("");
  return `<div class="ai-row"><small class="ai-who" style="color:${aiCol(m.tool)}">${esc(aiName(m.tool))}</small>${tools}` +
    `<div class="ai-b" style="border-left-color:${aiCol(m.tool)}">${aiMd(m.text) || "• • •"}</div>` +
    `<div class="ai-act"><button class="soft small" data-say="1">🔊</button><button class="soft small" data-copy="${esc(m.text || "")}">📋</button></div></div>`;
}
function aiWire(box) {
  box.querySelectorAll("[data-copy]").forEach((b) => (b.onclick = () => { navigator.clipboard && navigator.clipboard.writeText(b.dataset.copy).then(() => toast("Kopiert"), () => toast("Kunne ikke kopiere")); }));
  box.querySelectorAll("[data-say]").forEach((b) => (b.onclick = () => {
    const t = b.closest(".ai-row").querySelector(".ai-b").innerText;
    if (KS && KS.speak) KS.speak(t); else if (window.speechSynthesis) { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(t); u.lang = "nb-NO"; speechSynthesis.speak(u); }
  }));
  box.querySelectorAll("[data-sugg]").forEach((b) => (b.onclick = () => {
    if (b.dataset.fill) { $("#ai-text").value = b.dataset.fill; $("#ai-text").focus(); return; }   // «Spør om spillet»
    $("#ai-text").value = b.dataset.sugg; aiSend(); }));
}
async function aiLoadState() {
  try { aiSt = await X("ai"); } catch (e) { $("#ai-status").textContent = "AI: " + e.message; return; }
  $("#ai-tool").innerHTML = aiSt.tools.map((t) => `<option value="${t.id}"${t.id === aiSt.tool ? " selected" : ""}>${esc(t.name)}${t.ok ? "" : " (ikke klar på PC-en)"}</option>`).join("");
  $("#ai-conv").innerHTML = '<option value="">✨ Ny samtale</option>' + aiSt.convs.map((c) =>
    `<option value="${esc(c.id)}">${c.pinned ? "📌 " : ""}${c.emoji ? c.emoji + " " : ""}${esc(c.title)}</option>`).join("");
  $("#ai-conv").value = aiSt.convs.some((c) => c.id === aiCid) ? aiCid : "";
  const q = (aiSt.quota || {})[aiSt.tool] || {};
  $("#ai-quota").textContent = q.five_hour != null ? `⏱️ ${Math.round(q.five_hour * 100)} % (5 t) · ${Math.round((q.seven_day || 0) * 100)} % (uke)` : "";
}
async function aiLoadConv() {
  const box = $("#ai-msgs");
  if (!aiCid) {
    box.innerHTML = '<h3 class="ai-hi">Hva kan jeg hjelpe med?</h3><div class="ai-sugg">' + ((aiSt && aiSt.suggestions) || []).map((s) =>
      `<button class="soft" data-sugg="${esc(s.text)}"${s.fill ? ` data-fill="${esc(s.fill)}"` : ""}><span>${s.emoji}</span>${esc(s.text)}</button>`).join("") + "</div>";
    aiWire(box); return;
  }
  try { const c = await X("aiconv", "id=" + encodeURIComponent(aiCid)); box.innerHTML = (c.messages || []).map(aiBubble).join(""); aiWire(box); box.scrollTop = 1e9; }
  catch (e) { $("#ai-status").textContent = "✗ " + e.message; }
}
async function aiSend() {
  if (aiJob) { await act({ a: "aistop", job: aiJob }, true); return; }
  const q = $("#ai-text").value.trim(); if (!q) return;
  $("#ai-text").value = "";
  const box = $("#ai-msgs"); if (!aiCid) box.innerHTML = "";
  box.insertAdjacentHTML("beforeend", aiBubble({ role: "user", text: q }) +
    `<div class="ai-row" id="ai-live"><small class="ai-who" style="color:${aiCol($("#ai-tool").value)}">${esc(aiName($("#ai-tool").value))}</small><div id="ai-live-tools"></div><div class="ai-b" style="border-left-color:${aiCol($("#ai-tool").value)}">• • •</div></div>`);
  box.scrollTop = 1e9;
  let r;
  try { r = JSON.parse((await api("/api/action", { a: "aiask", text: q, cid: aiCid, tool: $("#ai-tool").value, images: aiImgs })).msg); }
  catch (e) { $("#ai-status").textContent = "✗ " + e.message; return; }
  aiImgs = []; aiChips();
  aiCid = r.cid; setPref("ai_cid", aiCid); aiJob = r.job; $("#ai-send").textContent = "■";
  const shown = new Set();
  const poll = async () => {
    let j; try { j = await X("aijob", "id=" + aiJob); } catch (e) { setTimeout(poll, 1500); return; }
    const live = document.querySelector("#ai-live .ai-b");
    if (live) live.innerHTML = aiMd(j.text) || "• • •";
    $("#ai-live-tools").innerHTML = (j.tools || []).map((t) => `<div class="ai-tool">${esc(t)}</div>`).join("");
    (j.confirm || []).forEach((c) => {                     // AI-en vil endre noe: Godta / Avbryt her også
      if (shown.has(c.id)) return; shown.add(c.id);
      box.insertAdjacentHTML("beforeend", `<div class="ai-ask" data-q="${c.id}">🤖 AI-en vil: ${esc(c.what)}<div class="row"><button class="primary small" data-ok="1">Godta</button><button class="soft small" data-ok="0">Avbryt</button></div></div>`);
      box.querySelectorAll(`[data-q="${c.id}"] button`).forEach((b) => (b.onclick = async () => {
        b.closest(".ai-ask").querySelectorAll("button").forEach((x) => (x.disabled = true));
        await act({ a: "aiconfirm", id: c.id, ok: b.dataset.ok === "1" }, true);
        b.closest(".ai-ask").insertAdjacentHTML("beforeend", `<small>${b.dataset.ok === "1" ? "✓ Godtatt" : "✗ Avbrutt"}</small>`);
      }));
      if (KS && KS.vibrate) KS.vibrate();
    });
    box.scrollTop = 1e9;
    if (!j.done) { setTimeout(poll, 700); return; }
    aiJob = null; $("#ai-send").textContent = "↑";
    if (pref("ai_speak", false) && KS && KS.speak) KS.speak(j.text);
    aiLoadState(); aiLoadConv();
  };
  poll();
}
function aiChips() {
  $("#ai-chips").hidden = !aiImgs.length;
  $("#ai-chips").innerHTML = aiImgs.map((d, i) => `<button class="soft small" data-rm="${i}"><img src="${d}" style="height:28px;border-radius:6px"> ✕</button>`).join("");
  $("#ai-chips").querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => { aiImgs.splice(+b.dataset.rm, 1); aiChips(); }));
}
$("#ai-send").onclick = aiSend;
$("#ai-text").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); aiSend(); } });
$("#ai-text").addEventListener("input", (e) => { e.target.style.height = "auto"; e.target.style.height = Math.min(140, e.target.scrollHeight) + "px"; });
$("#ai-conv").onchange = () => { aiCid = $("#ai-conv").value; setPref("ai_cid", aiCid); aiLoadConv(); };
$("#ai-new").onclick = () => { aiCid = ""; setPref("ai_cid", ""); $("#ai-conv").value = ""; aiLoadConv(); $("#ai-text").focus(); };
$("#ai-tool").onchange = () => act({ a: "aiset", tool: $("#ai-tool").value }, true).then(aiLoadState);
$("#ai-att").onclick = () => $("#ai-file").click();
$("#ai-file").onchange = (e) => {
  const f = e.target.files[0]; e.target.value = ""; if (!f) return;
  const img = new Image(), rd = new FileReader();                 // skaler ned (maks 1280 px) før det sendes
  rd.onload = () => { img.onload = () => { const k = Math.min(1, 1280 / Math.max(img.width, img.height)), c = document.createElement("canvas");
    c.width = img.width * k; c.height = img.height * k; c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    aiImgs.push(c.toDataURL("image/jpeg", 0.85)); aiChips(); }; img.src = rd.result; };
  rd.readAsDataURL(f);
};
$("#ai-mic").onclick = () => {                              // telefonens egen talegjenkjenning (norsk)
  if (KS && KS.listen) { $("#ai-status").textContent = "🎙️ Snakk nå …"; KS.listen("nb-NO"); return; }
  toast("Tale virker i Android-appen (0.99.19 eller nyere)");
};
window.ksHeard = (text, err) => {
  if (err) { $("#ai-status").textContent = "✗ " + err; return; }
  $("#ai-status").textContent = "";
  if (tab === "chat") { $("#ct-text").value = ($("#ct-text").value + " " + text).trim(); return; }
  $("#ai-text").value = ($("#ai-text").value + " " + text).trim();
  if (pref("ai_voice_send", true)) aiSend();
};
$("#ai-more").onclick = () => {
  const ps = (aiSt && aiSt.personas) || [];
  ctSheet("AI", `<div class="label">Personlighet</div><div class="ct-dndb">` + ps.map((p) => `<button class="soft small${p.id === aiSt.persona ? " on" : ""}" data-p="${p.id}">${p.emoji} ${esc(p.name)}</button>`).join("") + "</div>" +
    `<div class="row"><span>Spør meg før AI-en endrer noe</span><label class="switch"><input type="checkbox" id="ai-cf"${aiSt && aiSt.confirm ? " checked" : ""}><i></i></label></div>` +
    `<div class="row"><span>Les opp alle svar</span><label class="switch"><input type="checkbox" id="ai-sp"${pref("ai_speak", false) ? " checked" : ""}><i></i></label></div>` +
    `<div class="row"><span>Send med en gang etter tale</span><label class="switch"><input type="checkbox" id="ai-vs"${pref("ai_voice_send", true) ? " checked" : ""}><i></i></label></div>` +
    (aiCid ? `<button class="soft full" id="ai-pin">📌 Fest / løsne samtalen</button><button class="soft full" id="ai-del">🗑️ Slett samtalen</button>` : ""), (bg, close) => {
      bg.querySelectorAll("[data-p]").forEach((b) => (b.onclick = async () => { await act({ a: "aiset", persona: b.dataset.p }, true); close(); aiLoadState(); }));
      bg.querySelector("#ai-cf").onchange = (e) => act({ a: "aiset", confirm: e.target.checked }, true).then(aiLoadState);
      bg.querySelector("#ai-sp").onchange = (e) => setPref("ai_speak", e.target.checked);
      bg.querySelector("#ai-vs").onchange = (e) => setPref("ai_voice_send", e.target.checked);
      const pin = bg.querySelector("#ai-pin"), del = bg.querySelector("#ai-del");
      if (pin) pin.onclick = async () => { const c = aiSt.convs.find((x) => x.id === aiCid) || {}; await act({ a: "aipin", id: aiCid, pinned: !c.pinned }, true); close(); aiLoadState(); };
      if (del) del.onclick = async () => { if (!(await confirmDlg("Slette samtalen?"))) return; await act({ a: "aidelete", id: aiCid }, true); aiCid = ""; close(); aiLoadState(); aiLoadConv(); };
    });
};
window.ksAiAsk = (text) => { setTab("ai"); aiCid = ""; setTimeout(() => { $("#ai-text").value = text; aiSend(); }, 400); };
{ const _st4 = setTab; setTab = function (t) {                  // eslint-disable-line no-global-assign
  _st4(t);
  $("#aitab").hidden = t !== "ai" || !token;
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  if (t === "ai") aiLoadState().then(aiLoadConv);
}; }
