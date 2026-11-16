// Kontrollsenter – elegante velgere. Hver <select> får en pen knapp, og valgene åpnes i et ark som glir opp
// nedenfra (grupper, bilder/ikoner, undertekst, hake på valgt og søk i lange lister). <select> beholdes skjult
// som kilden til sannhet, så all eksisterende kode (value, onchange, innerHTML) virker som før.
"use strict";
(() => {
  const ESC = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CHEV = '<svg class="pk-chev" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5"/></svg>';
  const TICK = '<svg class="pk-tick" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

  const back = document.createElement("div");
  back.className = "sheet-back"; back.hidden = true;
  back.innerHTML = `<div class="sheet" role="dialog" aria-modal="true"><div class="grab"></div>
    <div class="sheet-head"><b id="sheet-t"></b><button class="icon" id="sheet-x" aria-label="Lukk">✕</button></div>
    <input id="sheet-q" placeholder="Søk …" hidden><div id="sheet-list" class="sheet-list"></div></div>`;
  document.body.appendChild(back);
  const list = back.querySelector("#sheet-list"), q = back.querySelector("#sheet-q");
  let current = null;

  const media = (o) => {
    if (!o) return "";
    if (o.dataset.img) return `<span class="pk-img"><img src="${ESC(o.dataset.img)}" alt="" loading="lazy" onerror="this.parentNode.textContent='${ESC(o.dataset.icon || "🎮")}'"></span>`;
    if (o.dataset.icon) return `<span class="pk-ic">${ESC(o.dataset.icon)}</span>`;
    return "";
  };
  function titleFor(sel) {
    if (sel.dataset.title) return sel.dataset.title;
    const row = sel.closest(".row"); const lab = row && row.querySelector("span");
    if (lab && lab.textContent.trim()) return lab.textContent.trim();
    const card = sel.closest(".card"); const h = card && card.querySelector("h2");
    return h ? h.textContent.trim() : "Velg";
  }
  function close() {
    back.classList.remove("open");
    setTimeout(() => { back.hidden = true; list.innerHTML = ""; }, 220);
    current = null;
  }
  function open(sel) {
    current = sel;
    back.querySelector("#sheet-t").textContent = titleFor(sel);
    const opts = Array.from(sel.options);
    q.hidden = opts.length < 9; q.value = "";
    let html = "";
    for (const node of sel.children) {
      if (node.tagName === "OPTGROUP") {
        html += `<div class="sheet-group">${ESC(node.label)}</div>`;
        for (const o of node.children) html += row(o);
      } else html += row(node);
    }
    list.innerHTML = html || '<p class="dim small" style="padding:12px">Ingenting å velge ennå.</p>';
    list.querySelectorAll("[data-v]").forEach((b) => (b.onclick = () => {
      if (b.dataset.v !== sel.value) { sel.value = b.dataset.v; sel.dispatchEvent(new Event("change", { bubbles: true })); }
      close();
    }));
    back.hidden = false;
    requestAnimationFrame(() => back.classList.add("open"));
    const on = list.querySelector(".on"); if (on) on.scrollIntoView({ block: "center" });
  }
  function row(o) {
    if (o.disabled && !o.value) return "";
    const on = o.selected;
    return `<button class="sheet-row${on ? " on" : ""}" data-v="${ESC(o.value)}" data-q="${ESC((o.textContent + " " + (o.dataset.sub || "")).toLowerCase())}">
      ${media(o)}<span class="pk-t"><b>${ESC(o.textContent)}</b>${o.dataset.sub ? `<small>${ESC(o.dataset.sub)}</small>` : ""}</span>${on ? TICK : ""}</button>`;
  }
  q.oninput = () => {
    const s = q.value.trim().toLowerCase();
    list.querySelectorAll(".sheet-row").forEach((r) => (r.hidden = s && !r.dataset.q.includes(s)));
    list.querySelectorAll(".sheet-group").forEach((g) => {
      let n = g.nextElementSibling, any = false;
      while (n && !n.classList.contains("sheet-group")) { if (!n.hidden) any = true; n = n.nextElementSibling; }
      g.hidden = !any;
    });
  };
  back.onclick = (e) => { if (e.target === back) close(); };
  back.querySelector("#sheet-x").onclick = close;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && current) close(); });
  // Android: tilbakeknappen lukker arket (appen kaller window.ksBack() hvis den finnes)
  const prevBack = window.ksBack;
  window.ksBack = () => { if (current) { close(); return true; } return prevBack ? prevBack() : false; };

  const valueDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
  function enhance(sel) {
    if (sel.dataset.pk) return;
    sel.dataset.pk = "1";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "picker" + (sel.classList.contains("num-in") ? " compact" : "");
    sel.after(btn);
    sel.classList.add("pk-native");
    const draw = () => {
      const o = sel.options[sel.selectedIndex];
      btn.innerHTML = `${media(o)}<span class="pk-t"><b>${ESC(o ? o.textContent : "Velg …")}</b>${o && o.dataset.sub && !btn.classList.contains("compact") ? `<small>${ESC(o.dataset.sub)}</small>` : ""}</span>${CHEV}`;
      btn.disabled = sel.disabled || !sel.options.length;
    };
    Object.defineProperty(sel, "value", { configurable: true, get() { return valueDesc.get.call(this); },
      set(v) { valueDesc.set.call(this, v); draw(); } });
    new MutationObserver(draw).observe(sel, { childList: true, subtree: true, attributes: true, characterData: true });
    sel.addEventListener("change", draw);
    btn.onclick = () => open(sel);
    draw();
  }
  const scan = (root) => (root.querySelectorAll ? root.querySelectorAll("select") : []).forEach(enhance);
  scan(document);
  new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => {
    if (n.nodeType !== 1) return;
    if (n.tagName === "SELECT") enhance(n); else scan(n);
  }))).observe(document.body, { childList: true, subtree: true });
})();
