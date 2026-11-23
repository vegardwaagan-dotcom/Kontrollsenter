// Liquid Glass og Aero i Android-appen – samme valg som på PC-en (liquid.py).
// Gjennomsiktig: sidens flater blir glass i temaets farger, og appen viser bakgrunnsbildet på telefonen bak seg
// (uskarpt på Android 12+). Valgene lagres i appen (KS.getAero/setAero), så de gjelder startskjermen og alle PC-ene.
(function () {
  const KS = window.KS;
  const DEF = { aero: false, clear: 50, blur: true, own: false, tint: "#7aa2ff" };
  const VARS = ["--bg", "--bg2", "--card", "--ga", "--acc", "--c1", "--grad", "--glass-solid", "--glass-full"];
  // lag som ligger over resten av siden (spillvisningen, topplinjen) blir frostet glass som nesten dekker –
  // ellers skinner siden under gjennom og teksten blir uleselig
  const css = document.createElement("style");
  css.textContent = `:root[data-glass] .second { background: var(--glass-full) !important;
      -webkit-backdrop-filter: none !important; backdrop-filter: none !important; }
    :root[data-glass] .top, :root[data-glass] .tabs {
      background: var(--glass-solid) !important; -webkit-backdrop-filter: blur(26px) saturate(160%);
      backdrop-filter: blur(26px) saturate(160%); }
    :root[data-glass] .card { box-shadow: inset 0 1px 0 rgba(255,255,255,.22), 0 10px 30px -14px rgba(0,0,0,.5);
      border-color: rgba(255,255,255,.16); }`;
  (document.head || document.documentElement).appendChild(css);
  function cfg() {
    let c = {};
    try { c = JSON.parse((KS && KS.getAero && KS.getAero()) || localStorage.getItem("ks_aero") || "{}"); } catch (e) {}
    return Object.assign({}, DEF, c);
  }
  function save(c) {
    const s = JSON.stringify(c);
    try { localStorage.setItem("ks_aero", s); } catch (e) {}
    try { if (KS && KS.setAero) KS.setAero(s); } catch (e) {}
  }
  function look() {
    try { return (KS && KS.getLook && KS.getLook()) || localStorage.getItem("ks_look") || "standard"; } catch (e) { return "standard"; }
  }
  function rgb(v) {
    v = (v || "").trim();
    let m = /^#([0-9a-f]{6})/i.exec(v);
    if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
    m = /rgba?\(([^)]+)\)/.exec(v);
    if (m) return m[1].split(",").slice(0, 3).map((x) => parseInt(x, 10));
    return null;
  }
  const mix = (a, b, k) => a.map((x, i) => Math.round(x * (1 - k) + b[i] * k));
  function apply() {
    const root = document.documentElement, st = root.style, c = cfg(), lk = look();
    const liquid = lk === "liquid", on = liquid || !!c.aero;
    const own = st.getPropertyValue("--bg") && lk === "eget";      // eget tema setter fargene selv (applyOwn)
    if (!own) VARS.forEach((v) => st.removeProperty(v));
    root.toggleAttribute("data-glass", on);
    try { if (KS && KS.setGlassWindow) KS.setGlassWindow(on, on && c.blur ? 40 + Math.round(c.clear / 2) : 0); } catch (e) {}
    if (!on) return;
    const cs = getComputedStyle(root);
    const tint = rgb(liquid || c.own ? c.tint : cs.getPropertyValue("--ga")) || [122, 162, 255];
    const dark = root.dataset.theme !== "light";
    const bg = rgb(cs.getPropertyValue("--bg")) || (dark ? [18, 19, 32] : [244, 245, 250]);
    const side = rgb(cs.getPropertyValue("--bg2")) || bg;
    const a = Math.max(0.05, 1 - Math.min(95, Math.max(0, +c.clear)) / 100);
    const base = liquid ? mix([12, 14, 22], tint, 0.3) : mix(bg, tint, 0.18);
    st.setProperty("--bg", `rgba(${base},${a.toFixed(3)})`);
    st.setProperty("--glass-full", `rgba(${base},0.97)`);
    st.setProperty("--glass-solid", `rgba(${base},${Math.max(0.9, a).toFixed(3)})`);
    st.setProperty("--bg2", `rgba(${mix(side, tint, 0.18)},${Math.min(0.95, a + 0.12).toFixed(3)})`);
    st.setProperty("--card", dark ? `rgba(255,255,255,${(0.05 + a * 0.06).toFixed(3)})` : `rgba(255,255,255,${(0.25 + a * 0.2).toFixed(3)})`);
    if (liquid || c.own) {
      const t = `rgb(${tint})`;
      ["--ga", "--acc", "--c1"].forEach((v) => st.setProperty(v, t));
      st.setProperty("--grad", `linear-gradient(135deg, ${t} 0%, rgba(${tint},.6) 100%)`);
    }
  }
  // innstillingene (Mer → Utseende): bygges inn i et element med id="ks-aero"
  function ui() {
    const box = document.getElementById("ks-aero"); if (!box) return;
    const c = cfg();
    box.innerHTML = `
      <div class="row"><span>Gjennomsiktig vindu (Aero)<br><small class="dim">Glass i temaets farger – bakgrunnsbildet skinner gjennom</small></span><label class="switch"><input type="checkbox" id="gl-aero"><i></i></label></div>
      <div class="row"><span>Gjennomsiktighet <b id="gl-pct"></b></span><input type="range" id="gl-clear" min="0" max="95" step="5" style="flex:1;max-width:55%"></div>
      <div class="row"><span>Uskarphet bak (Android 12+)</span><label class="switch"><input type="checkbox" id="gl-blur"><i></i></label></div>
      <div class="row"><span>Egen farge på glasset</span><label class="switch"><input type="checkbox" id="gl-own"><i></i></label><input type="color" id="gl-tint" style="width:42px;height:32px;border:0;background:none"></div>
      <p class="dim small">«Liquid Glass»-temaet er alltid gjennomsiktig og bruker fargen over.</p>`;
    const $ = (id) => document.getElementById(id);
    $("gl-aero").checked = c.aero; $("gl-clear").value = c.clear; $("gl-blur").checked = c.blur;
    $("gl-own").checked = c.own; $("gl-tint").value = c.tint; $("gl-pct").textContent = c.clear + " %";
    const upd = () => {
      const n = { aero: $("gl-aero").checked, clear: +$("gl-clear").value, blur: $("gl-blur").checked,
                  own: $("gl-own").checked, tint: $("gl-tint").value };
      $("gl-pct").textContent = n.clear + " %";
      save(n); apply();
    };
    ["gl-aero", "gl-blur", "gl-own", "gl-tint"].forEach((id) => ($(id).onchange = upd));
    $("gl-clear").oninput = upd;
    if (!(KS && KS.setGlassWindow)) box.insertAdjacentHTML("beforeend", '<p class="dim small">Gjennomsiktig vindu krever Android-appen (0.99.14 eller nyere).</p>');
  }
  window.ksAero = { apply, ui, cfg };
  apply();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ui); else ui();
})();
