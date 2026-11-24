// =====================================================================================================
// Ryddig app: hver fane er delt i kategorier (velges med rullehjulet øverst), og kort som hører sammen
// ligger sammen. PC-panelene («Alt fra PC-en») flyttes til fanen og kategorien de hører til.
// =====================================================================================================
(() => {
  // [nøkkel, navn, [kort: id, «t:tittel» (starten av overskriften) eller «pn:panel»]]
  const CATS = {
    kontroll: [
      ["pc", "🖥️ PC-en", ["c-gamemode", "c-power", "c-fans", "c-rgb", "c-msi"]],
      ["helse", "🤫 Stille, strøm og stresstest", ["c-pcquiet", "c-budget", "c-stress"]],
      ["lyd", "🔊 Lyd og skjerm", ["c-audio", "c-disp", "c-spk", "c-avprof"]],
      ["tester", "🧪 Tester", ["c-tests"]],
      ["verktoy", "🔧 PC-verktøy", ["c-drivers", "pn:pctools", "pn:apps", "pn:gpu", "pn:nvidia", "t:Programmer", "t:Oppstartsprogrammer",
        "t:Sikkerhetssjekk", "t:Selvtest"]],
      ["historikk", "📈 Historikk og strøm", ["t:Historikk", "t:Strømkostnad", "t:Tidslinje"]],
      ["nett", "🌐 Nett og NAS", ["t:Nettverk", "t:Hjemmenett", "t:NAS"]],
      ["fjern", "🕹️ Fjernstyring", ["c-touchpad", "c-extra-screens", "c-deck", "t:Send til PC", "t:Skjermen live", "t:Skjermbilde", "c-rust"]],
      ["discord", "💬 Discord", ["c-discord"]],
    ],
    spill: [
      ["spill", "🎮 Spillene", ["pn:games", "stats-card", "t:Spilletid", "t:Ytelse per spill", "t:Måneden",
        "t:CS2", "wp-card", "t:World of", "t:Tilbud"]],
      ["klipp", "🎬 Klipp", ["c-clips"]],
      ["prest", "🏆 Prestasjoner", ["c-ach", "t:Prestasjoner"]],
      ["vr", "🥽 VR og strømming", ["c-vr", "c-stream"]],
      ["lan", "🏆 Spillkveld og nett", ["c-tourney", "c-net"]],
      ["aar", "🎁 Spillår og plass", ["c-wrapped", "c-compare", "c-storage"]],
    ],
    mer: [
      ["kalender", "📅 Kalender og dagbok", ["c-cal", "c-diary"]],
      ["familie", "👨‍👩‍👧 Familie", ["c-family", "c-goals", "c-shop", "c-plan", "c-week", "c-safe", "c-sleep"]],
      ["hverdag", "🍽️ Hverdagen", ["c-meals", "c-pkgs"]],
      ["beskjed", "📢 Beskjed og minnevegg", ["c-say", "c-mem"]],
      ["hjem", "🏠 Scener og smarthus", ["c-scenes", "t:Hue", "pn:radio", "pn:presence"]],
      ["venner", "👥 Venner og PC-er", ["c-friends", "pn:homepcs"]],
    ],
    system: [
      ["utseende", "🎨 Utseende", ["c-fx", "t:Utseende"]],
      ["varsler", "🔔 Varsler", ["nf-phone-card", "nf-pc-card", "c-push"]],
      ["app", "⚙️ PC-en og appen", ["t:PC-en", "t:Sikkerhet", "t:Appen", "t:Sikkerhetskopi", "t:Panelet", "pn:version"]],
    ],
  };
  // panel → fane (hurtigkommandoene ligger på Hjem, rett under hurtigknappene)
  const PANEL_TAB = { commands: "oversikt", family: "mer", updates: "oversikt", assistant: "oversikt", games: "spill", homepcs: "mer", radio: "mer", presence: "mer",
    pctools: "kontroll", apps: "kontroll", gpu: "kontroll", nvidia: "kontroll", version: "system" };

  const titleOf = (c) => ((c.querySelector(":scope > h2, :scope > .row h2, h2") || {}).textContent || "").trim();
  function catOf(tab, c) {
    const id = c.id || "", pn = c.dataset.pn ? "pn:" + c.dataset.pn : "", t = titleOf(c);
    for (const [key, , keys] of CATS[tab] || []) {
      for (const k of keys) {
        if (k === id || k === pn || (k.startsWith("t:") && t.startsWith(k.slice(2)))) return key;
      }
    }
    return "annet";
  }
  const container = (tab) => { const s = $("#" + tab); return s && (s.querySelector(":scope > .grid") || s); };
  const cardsIn = (tab) => {
    const s = $("#" + tab); if (!s) return [];
    return [...s.querySelectorAll(".card")].filter((c) => !c.parentElement.closest(".card") && !c.closest(".cat-bar"));
  };
  const curCat = (tab) => pref("cat_" + tab, (CATS[tab] || [[null]])[0][0]);

  // ---- kategorivelgeren (rullehjulet) øverst i fanen ----
  function bar(tab) {
    const s = $("#" + tab); if (!s || !CATS[tab]) return null;
    let b = s.querySelector(":scope > .cat-bar");
    if (!b) {
      b = document.createElement("div");
      b.className = "cat-bar";
      b.innerHTML = '<button class="cat-prev" aria-label="Forrige">‹</button><select class="cat-sel" data-title="Vis"></select><button class="cat-next" aria-label="Neste">›</button>';
      s.insertBefore(b, s.firstChild);
      const sel = b.querySelector("select");
      sel.onchange = () => { setPref("cat_" + tab, sel.value); apply(tab, true); };
      const step = (d) => { const o = [...sel.options].filter((x) => !x.hidden); const i = o.findIndex((x) => x.value === sel.value);
        const n = o[(i + d + o.length) % o.length]; if (n) { sel.value = n.value; sel.onchange(); } };
      b.querySelector(".cat-prev").onclick = () => step(-1);
      b.querySelector(".cat-next").onclick = () => step(1);
      // sveip til venstre/høyre på kategorilinjen
      let x0 = null; b.addEventListener("touchstart", (e) => (x0 = e.touches[0].clientX), { passive: true });
      b.addEventListener("touchend", (e) => { if (x0 == null) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 50) step(dx < 0 ? 1 : -1); x0 = null; });
    }
    return b;
  }

  let busy = false;
  // kort som hører til en kategori i en annen fane flyttes dit (f.eks. Kalender og Familie → Hjemmet)
  function relocate() {
    Object.keys(CATS).forEach((tab) => {
      cardsIn(tab).forEach((c) => {
        if (catOf(tab, c) !== "annet") return;
        const to = Object.keys(CATS).find((t2) => t2 !== tab && catOf(t2, c) !== "annet");
        const box = to && container(to);
        if (box && c.parentElement !== box) box.appendChild(c);
      });
    });
  }
  function apply(tab, anim) {
    if (!CATS[tab]) return;
    busy = true;
    relocate();
    const b = bar(tab), sel = b.querySelector("select");
    const cards = cardsIn(tab);
    const counts = {};
    cards.forEach((c) => { const k = catOf(tab, c); c.dataset.cat = k; if (!c.hidden) counts[k] = (counts[k] || 0) + 1; });
    const cats = [...CATS[tab].map(([k, n]) => [k, n]), ["annet", "📦 Annet"]].filter(([k]) => counts[k]);
    let cur = curCat(tab);
    if (!cats.some(([k]) => k === cur)) cur = (cats[0] || [""])[0];
    const html = cats.map(([k, n]) => '<option value="' + k + '"' + (k === cur ? " selected" : "") + '>' + n + "  (" + counts[k] + ")</option>").join("");
    if (sel.innerHTML !== html) sel.innerHTML = html;
    sel.value = cur;
    b.hidden = cats.length < 2;
    cards.forEach((c) => c.classList.toggle("cat-off", cats.length >= 2 && c.dataset.cat !== cur));
    if (anim && window.fxEnter) { try { fxEnter(tab); } catch (e) {} }
    if (anim) window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => (busy = false), 0);
  }

  // ---- PC-panelene til riktig fane ----
  window.ksPlacePanels = () => {
    $$(".card.pn").forEach((c) => {
      const tab = PANEL_TAB[c.dataset.pn] || "mer";
      if (tab === "oversikt") {
        const q = $("#quick");
        if (q && q.nextElementSibling !== c) q.parentElement.insertBefore(c, q.nextSibling);
      } else {
        const box = container(tab);
        if (box && c.parentElement !== box) {                      // øverst i kategorien sin (etter velgeren)
          let first = box.firstElementChild;
          while (first && first.classList.contains("cat-bar")) first = first.nextElementSibling;
          box.insertBefore(c, first);
        }
      }
    });
    const w = $("#pc-panels"); if (w) w.hidden = true;           // overskriften «Alt fra PC-en» trengs ikke lenger
    Object.keys(CATS).forEach((t) => apply(t));
  };

  // ---- hold orden når kort dukker opp senere ----
  Object.keys(CATS).forEach((tab) => {
    const s = $("#" + tab); if (!s) return;
    let tid = 0;
    new MutationObserver(() => { if (busy) return; clearTimeout(tid); tid = setTimeout(() => apply(tab), 120); })
      .observe(s, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    apply(tab);
  });
  // panelene lastes for alle faner (de ligger nå spredt)
  setTimeout(() => { try { loadPanels(); } catch (e) {} }, 2500);
  const _st = setTab;
  setTab = function (t) { _st(t); if (CATS[t]) apply(t); if (t !== "mer") { try { loadPanels(); } catch (e) {} } };  // eslint-disable-line no-global-assign
})();
