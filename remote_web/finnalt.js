// «Finn alt» i appen: 🔎 øverst åpner en oversikt over alle fanene, kategoriene og kortene – med søk.
// Trykk på noe for å gå rett dit (riktig fane og kategori, og kortet blinker).
(() => {
  const norm = (s) => (s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/ø/g, "o").replace(/æ/g, "ae");
  const escH = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let idx = [], view = null;

  function open() {
    idx = window.ksFindIndex ? window.ksFindIndex() : [];
    if (!view) {
      view = document.createElement("div");
      view.id = "findall";
      view.innerHTML = '<div class="fa-head"><input id="fa-q" type="search" placeholder="Søk – f.eks. «vifte», «lyd», «kalender», «DLSS»" '
        + 'autocomplete="off"><button id="fa-x" class="icon" aria-label="Lukk">✕</button></div><div id="fa-sub" class="dim small"></div><div id="fa-list"></div>';
      document.body.appendChild(view);
      view.querySelector("#fa-x").onclick = close;
      view.querySelector("#fa-q").oninput = render;
      view.querySelector("#fa-q").onkeydown = (e) => { if (e.key === "Enter") { const f = view.querySelector("[data-i]"); if (f) f.click(); } if (e.key === "Escape") close(); };
      view.addEventListener("click", (e) => {
        const b = e.target.closest("[data-i]"); if (!b) return;
        const it = idx[+b.dataset.i]; close(); if (it) window.ksGoCard(it);
      });
    }
    view.hidden = false;
    document.body.classList.add("fa-open");
    const q = view.querySelector("#fa-q"); q.value = ""; render();
    setTimeout(() => q.focus(), 50);
    history.pushState({ fa: 1 }, "");
  }
  function close() {
    if (!view || view.hidden) return;
    view.hidden = true; document.body.classList.remove("fa-open");
  }
  window.addEventListener("popstate", close);              // tilbake-knappen lukker oversikten

  // tittel-treff først, så ord i knapper og navn, så resten av teksten
  const rank = (e, q) => norm(e.title).includes(q[0]) ? 0 : norm(e.words).includes(q[0]) ? 1 : 2;

  function render() {
    const q = norm(view.querySelector("#fa-q").value).split(/\s+/).filter(Boolean);
    const list = view.querySelector("#fa-list"), sub = view.querySelector("#fa-sub");
    if (q.length) {
      const hits = idx.map((e, i) => [e, i]).filter(([e]) => {
        const hay = norm(e.title + " " + e.words + " " + e.catName + " " + e.tabName + " " + (e.el.textContent || "").slice(0, 3000));
        return q.every((w) => hay.includes(w));
      }).sort((a, b) => rank(a[0], q) - rank(b[0], q));
      sub.textContent = hits.length ? hits.length + " treff – trykk for å gå dit" : "Fant ingenting – prøv et annet ord";
      list.innerHTML = '<div class="fa-hits">' + hits.map(([e, i]) => '<button class="fa-hit" data-i="' + i + '"><b>' + escH(e.title)
        + '</b><small class="dim">' + escH([e.tabName, e.catName].filter(Boolean).join(" → ")) + '</small></button>').join("") + "</div>";
      return;
    }
    const tabs = {};
    idx.forEach((e, i) => { ((tabs[e.tabName] = tabs[e.tabName] || {})[e.catName] = tabs[e.tabName][e.catName] || []).push([e, i]); });
    sub.textContent = idx.length + " kort og funksjoner i appen. Trykk for å gå dit, eller søk.";
    list.innerHTML = Object.entries(tabs).map(([t, cats]) => '<div class="card fa-tab"><h2>' + escH(t) + "</h2>"
      + Object.entries(cats).map(([c, items]) => (c ? '<div class="fa-cat">' + escH(c) + "</div>" : "")
        + '<div class="fa-chips">' + items.map(([e, i]) => '<button class="soft small" data-i="' + i + '">' + escH(e.title) + "</button>").join("") + "</div>").join("")
      + "</div>").join("");
  }

  // 🔎-knappen i toppen (den gamle søkeknappen åpner nå «Finn alt»)
  const old = document.getElementById("btn-search");
  const top = document.querySelector("header.top");
  if (old) { old.onclick = open; old.title = "Finn alt"; }
  else if (top) {
    const b = document.createElement("button");
    b.id = "btn-find"; b.className = "icon"; b.title = "Finn alt";
    b.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>';
    b.onclick = open;
    const before = document.getElementById("btn-second");
    top.insertBefore(b, before || null);
  }
  window.ksOpenFind = open;
})();
