// Google TV / Android TV: styres med fjernkontrollen (piltaster + OK). Større tekst, tydelig fokus, og alt som kan
// trykkes på kan også nås med piltastene. Gjør ingenting på telefon og nettbrett.
(function () {
  const KS = window.KS;
  let tv = false;
  try { tv = !!(KS && KS.isTv && KS.isTv()); } catch (e) {}
  if (!tv && !/[?&]tv=1/.test(location.search)) return;
  document.documentElement.classList.add("tv");
  const css = document.createElement("style");
  css.textContent = `
    html.tv { font-size: 118%; }
    html.tv body { max-width: 1200px; margin: 0 auto; }
    html.tv :focus-visible, html.tv .tv-focus:focus { outline: 4px solid var(--acc, #5b8cff) !important; outline-offset: 3px;
      box-shadow: 0 0 0 8px color-mix(in srgb, var(--acc, #5b8cff) 30%, transparent) !important; border-radius: 12px; }
    html.tv button, html.tv select, html.tv input, html.tv a { min-height: 48px; }
    html.tv .tabs button { min-height: 64px; }`;
  (document.head || document.documentElement).appendChild(css);
  // klikkbare ting som ikke er knapper (fliser, rader, kort) får fokus, og OK trykker på dem
  function mark(root) {
    (root || document).querySelectorAll("[onclick], [data-go], [data-d], [data-play], [data-p], .tile, .ct-row, .cal-row, .theme-sw")
      .forEach((el) => {
        if (el.tabIndex < 0 && !/^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) { el.tabIndex = 0; el.classList.add("tv-focus"); }
      });
  }
  mark();
  new MutationObserver(() => mark()).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("keydown", (e) => {
    const el = document.activeElement;
    if ((e.key === "Enter" || e.keyCode === 23) && el && el.classList.contains("tv-focus")) { e.preventDefault(); el.click(); }
  });
  // første fokus: første knapp i den synlige siden, så fjernkontrollen virker med en gang
  setTimeout(() => { if (!document.activeElement || document.activeElement === document.body) {
    const f = document.querySelector("main button:not([hidden]), .tabs button, button"); if (f) f.focus(); } }, 800);
})();
