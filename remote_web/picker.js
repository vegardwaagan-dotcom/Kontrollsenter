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
    const plain = opts.filter((o) => !o.hidden && !(o.disabled && !o.value));
    if (plain.length >= 2 && plain.length <= 60 && !opts.some((o) => o.dataset.img) && !sel.querySelector("optgroup")) {
      return openWheel(sel, plain);
    }
    back.classList.remove("wheel-mode");
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
  // ---- rullehjul (som den gamle iPhone-velgeren, med glass) ----
  const WH = 44;
  function openWheel(sel, opts) {
    back.classList.add("wheel-mode");
    q.hidden = true;
    let idx = Math.max(0, opts.findIndex((o) => o.selected));
    list.innerHTML = '<div class="wheel"><div class="wband"></div><div class="wscroll">' + '<div class="wpad"></div>'
      + opts.map((o, i) => '<div class="witem" data-i="' + i + '">' + ESC(o.textContent) + '</div>').join("")
      + '<div class="wpad"></div></div></div><button type="button" class="wdone">Velg</button>';
    const sc = list.querySelector(".wscroll"), items = Array.from(list.querySelectorAll(".witem"));
    let last = idx, raf = 0, endT = 0;
    const paint = () => {
      raf = 0;
      const mid = sc.scrollTop + sc.clientHeight / 2;
      items.forEach((el, i) => {
        const d = (i * WH + WH / 2 + sc.clientHeight / 2 - WH / 2 - mid) / WH;
        const ang = Math.max(-80, Math.min(80, d * 21));
        const op = Math.max(0.12, Math.cos(ang * Math.PI / 180) ** 2.2);
        el.style.transform = "perspective(420px) rotateX(" + (-ang) + "deg) scale(" + (1 - Math.min(0.18, Math.abs(d) * 0.05)) + ")";
        el.style.opacity = String(op);
        el.classList.toggle("on", Math.abs(d) < 0.5);
      });
      const cur = Math.round(sc.scrollTop / WH);
      if (cur !== last) { last = cur; try { if (window.KS && KS.vibrate) KS.vibrate(); else if (navigator.vibrate) navigator.vibrate(4); } catch (e) {} }
    };
    sc.onscroll = () => { if (!raf) raf = requestAnimationFrame(paint); clearTimeout(endT); endT = setTimeout(() => { idx = Math.round(sc.scrollTop / WH); }, 120); };
    const commit = () => {
      const i = Math.max(0, Math.min(opts.length - 1, Math.round(sc.scrollTop / WH)));
      const v = opts[i].value;
      if (v !== sel.value) { sel.value = v; sel.dispatchEvent(new Event("change", { bubbles: true })); }
      close();
    };
    items.forEach((el) => (el.onclick = () => {
      const i = +el.dataset.i;
      if (Math.round(sc.scrollTop / WH) === i) commit(); else sc.scrollTo({ top: i * WH, behavior: "smooth" });
    }));
    list.querySelector(".wdone").onclick = commit;
    // musehjul: ett hakk = ett valg (styreplate/mus med jevn rulling summeres til ett valg om gangen)
    let acc = 0, accT = 0;
    sc.onwheel = (e) => {
      e.preventDefault();
      const px = e.deltaMode === 1 ? e.deltaY * 40 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
      if (Date.now() - accT > 250) acc = 0;
      accT = Date.now();
      acc += px;
      const notch = Math.abs(px) >= 50 ? Math.abs(px) : 60;      // vanlig hjul gir ~100 px per hakk
      if (Math.abs(acc) < notch * 0.5) return;
      const dir = acc > 0 ? 1 : -1;
      acc = 0;
      const cur = Math.round(sc.scrollTop / WH);
      const nxt = Math.max(0, Math.min(opts.length - 1, cur + dir));
      sc.scrollTo({ top: nxt * WH, behavior: "smooth" });
    };
    back.hidden = false;
    requestAnimationFrame(() => { back.classList.add("open"); sc.scrollTop = idx * WH; paint(); });
  }
  function row(o) {
    if (o.disabled && !o.value) return "";
    const on = o.selected && !o.hidden;
    return `<button class="sheet-row${on ? " on" : ""}"${o.disabled ? " disabled" : ""} data-v="${ESC(o.value)}" data-q="${ESC((o.textContent + " " + (o.dataset.sub || "")).toLowerCase())}">
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
