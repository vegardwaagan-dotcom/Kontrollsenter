// Design-bryteren i mobilappen: «Klassisk» eller «Nytt design» – samme valg og samme designverdier som på PC-en
// (design.py lager design.css og design-data.js). Valget lagres i appen (KS.getDesign/setDesign), så det gjelder
// startskjermen og alle PC-ene; eldre app-versjoner bruker localStorage.
(function () {
  const D = window.KS_DESIGN || { tabs: {}, curated: [], keep: [], advanced: [] };
  const KSB = window.KS;

  function cur() {
    try { return (KSB && KSB.getDesign && KSB.getDesign()) || localStorage.getItem("ks_design") || "klassisk"; }
    catch (e) { return "klassisk"; }
  }
  const isNew = () => cur() === "ny";

  // Første gang det nye designet velges: levende bakgrunn og Aero av (rolig utseende) – tilbake ved Klassisk.
  function calm(toNew) {
    const getJ = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } };
    const setJ = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
    let aero = {};
    try { aero = JSON.parse((KSB && KSB.getAero && KSB.getAero()) || localStorage.getItem("ks_aero") || "{}"); } catch (e) {}
    const saveAero = (a) => {
      const s = JSON.stringify(a);
      try { localStorage.setItem("ks_aero", s); } catch (e) {}
      try { if (KSB && KSB.setAero) KSB.setAero(s); } catch (e) {}
    };
    if (toNew) {
      setJ("ks_design_prev", { live: getJ("ks_look_live", false), aero: !!aero.aero });
      setJ("ks_look_live", false);
      if (aero.aero) { aero.aero = false; saveAero(aero); }
    } else {
      const p = getJ("ks_design_prev", null);
      if (p) {
        setJ("ks_look_live", !!p.live);
        if (p.aero) { aero.aero = true; saveAero(aero); }
        try { localStorage.removeItem("ks_design_prev"); } catch (e) {}
      }
    }
  }

  function set(m) {
    if (m !== "ny" && m !== "klassisk") return;
    if (m === cur()) return;
    calm(m === "ny");
    try { localStorage.setItem("ks_design", m); } catch (e) {}
    try { if (KSB && KSB.setDesign) KSB.setDesign(m); } catch (e) {}
    location.reload();
  }

  window.ksDesign = { cur, isNew, set };
  document.documentElement.dataset.design = cur();

  // ---------- bryteren under Innstillinger › Utseende ----------
  function drawPicker() {
    const box = document.getElementById("ks-design");
    if (!box) return;
    const c = cur();
    box.innerHTML = [["klassisk", "Klassisk", "Slik som før"], ["ny", "Nytt design", "Ryddigere og roligere"]]
      .map(([k, n, d]) => `<button type="button" data-d="${k}" class="${k === c ? "on" : ""}"><b>${n}</b><small>${d}</small></button>`)
      .join("");
    box.querySelectorAll("button").forEach((b) => (b.onclick = () => set(b.dataset.d)));
  }
  drawPicker();
  if (!isNew()) return;

  // ---------- fanene nederst: samme navn og rekkefølge som områdene på PC-en (Chat og AI kommer til litt senere) ----------
  const ORDER = Object.keys(D.tabs);
  function tabs() {
    const nav = document.getElementById("tabs");
    if (!nav) return;
    const btns = [...nav.querySelectorAll(":scope > button[data-tab]")];
    btns.forEach((b) => {
      const n = D.tabs[b.dataset.tab];
      const s = b.querySelector("span");
      if (n && s && s.textContent !== n) s.textContent = n;
    });
    const rank = (b) => { const i = ORDER.indexOf(b.dataset.tab); return i < 0 ? 99 : i; };
    const sorted = [...btns].sort((a, b) => rank(a) - rank(b));
    if (sorted.some((b, i) => b !== btns[i])) sorted.forEach((b) => nav.appendChild(b));
  }

  // ---------- rydd innholdet: emoji bort fra overskrifter, én fremhevet knapp per kort, avanserte kort lukket ----------
  const EMO = /^\s*(?:[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2300}-\u{23FF}\u{FE0F}\u{200D}\u{20E3}]+\s*)+/u;
  const keep = (el) => !!el.closest('[id*="fam"],[id*="chat"]');

  function strip(el) {
    if (el.dataset.ksS === el.textContent || keep(el)) return;
    const before = el.textContent;
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const changed = [];
    let n;
    while ((n = w.nextNode())) {
      const v = n.nodeValue;
      if (!v.trim()) continue;
      if (!EMO.test(v)) break;
      changed.push([n, v]);
      n.nodeValue = v.replace(EMO, "");
      if (n.nodeValue.trim()) break;
    }
    if (!el.textContent.trim()) changed.forEach(([node, v]) => (node.nodeValue = v));   // bare emoji: la stå
    el.dataset.ksS = el.textContent;
    return before !== el.textContent;
  }

  function tidyCard(card) {
    const prim = card.querySelectorAll("button.primary");
    prim.forEach((b, i) => { if (i > 0) { b.classList.remove("primary"); b.classList.add("soft"); } });
    if (card.dataset.ksT || card.querySelector(":scope > .ks-adv-btn")) return;
    card.dataset.ksT = "1";
    const h = card.querySelector(":scope > h2");
    if (!h) return;
    const t = h.textContent.replace(EMO, "").trim();
    if (!D.advanced.some((a) => t.startsWith(a))) return;
    card.classList.add("ks-adv");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ks-adv-btn soft";
    b.textContent = "Vis";
    b.onclick = () => { const o = card.classList.toggle("open"); b.textContent = o ? "Skjul" : "Vis"; };
    h.after(b);
  }

  let queued = false;
  function run() {
    queued = false;
    tabs();
    document.querySelectorAll("main h2, main h3, main .label, .sheet h2, .sheet h3").forEach(strip);
    document.querySelectorAll("main .card").forEach(tidyCard);
  }
  function later() { if (!queued) { queued = true; requestAnimationFrame(run); } }
  new MutationObserver(later).observe(document.body, { childList: true, subtree: true });
  later();
})();
