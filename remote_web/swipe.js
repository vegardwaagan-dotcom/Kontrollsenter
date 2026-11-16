// Kontrollsenter – bytt fane ved å dra fingeren bortover skjermen, eller dra langs fanelinjen (trykk virker som før).
"use strict";
(() => {
  const tabsEl = document.getElementById("tabs");
  if (!tabsEl) return;
  const order = () => [...tabsEl.querySelectorAll("button[data-tab]")].filter((b) => b.offsetParent !== null);
  const curPage = () => document.getElementById(tab);
  const blocked = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      if (e.matches("input, textarea, select, canvas, video, .quick, .sheet, .dlg, .tabs, [data-noswipe]")) return true;
      const cs = getComputedStyle(e);
      if (/(auto|scroll)/.test(cs.overflowX) && e.scrollWidth > e.clientWidth + 2) return true;
    }
    return !!document.querySelector(".sheet-back:not([hidden]), #dlg:not([hidden])");
  };

  // ---------- sveip på innholdet ----------
  let sx = 0, sy = 0, dx = 0, mode = null, page = null;
  document.addEventListener("touchstart", (ev) => {
    mode = null; page = null;
    if (ev.touches.length !== 1 || window.innerWidth >= 900) return;
    const t = ev.touches[0];
    if (t.clientX < 24 || t.clientX > window.innerWidth - 24 || blocked(ev.target)) return;   // Androids tilbake-gest
    sx = t.clientX; sy = t.clientY; dx = 0; mode = "?";
  }, { passive: true });
  document.addEventListener("touchmove", (ev) => {
    if (!mode) return;
    const t = ev.touches[0], mx = t.clientX - sx, my = t.clientY - sy;
    if (mode === "?") {
      if (Math.abs(mx) < 12 && Math.abs(my) < 12) return;
      mode = Math.abs(mx) > Math.abs(my) * 1.4 ? "x" : null;      // loddrett = vanlig skrolling
      if (!mode) return;
      page = curPage();
      if (page) page.style.transition = "none";
    }
    dx = mx;
    const list = order(), i = list.findIndex((b) => b.dataset.tab === tab);
    const edge = (dx > 0 && i <= 0) || (dx < 0 && i >= list.length - 1);           // ingen fane den veien
    if (page) {
      const d = edge ? dx * 0.15 : dx * 0.45;
      page.style.transform = `translateX(${d}px)`;
      page.style.opacity = String(1 - Math.min(0.5, Math.abs(d) / window.innerWidth));
    }
  }, { passive: true });
  const end = () => {
    if (mode !== "x") { mode = null; return; }
    mode = null;
    const list = order(), i = list.findIndex((b) => b.dataset.tab === tab);
    const go = Math.abs(dx) > Math.min(90, window.innerWidth * 0.22) ? (dx < 0 ? i + 1 : i - 1) : i;
    const p = page; page = null;
    if (go !== i && go >= 0 && go < list.length) {
      const from = dx < 0 ? 1 : -1;
      if (p) { p.style.transition = ""; p.style.transform = ""; p.style.opacity = ""; }
      setTab(list[go].dataset.tab);
      if (navigator.vibrate) try { navigator.vibrate(8); } catch (e) {}
      const np = curPage();
      if (np && !document.body.classList.contains("eco")) {
        np.animate([{ transform: `translateX(${from * 60}px)`, opacity: 0.3 }, { transform: "none", opacity: 1 }],
          { duration: 220, easing: "cubic-bezier(.2,.8,.2,1)" });
      }
    } else if (p) {
      p.style.transition = "transform .2s ease, opacity .2s ease";
      p.style.transform = ""; p.style.opacity = "";
      setTimeout(() => (p.style.transition = ""), 220);
    }
  };
  document.addEventListener("touchend", end, { passive: true });
  document.addEventListener("touchcancel", end, { passive: true });

  // ---------- dra langs fanelinjen: linsen følger fingeren ----------
  let drag = null;
  const lens = () => tabsEl.querySelector(".lens");
  const under = (x) => order().find((b) => { const r = b.getBoundingClientRect(); return x >= r.left && x <= r.right; });
  tabsEl.addEventListener("pointerdown", (ev) => {
    if (ev.pointerType === "mouse" || window.innerWidth >= 900) return;
    drag = { x: ev.clientX, moved: false, id: ev.pointerId };
  });
  tabsEl.addEventListener("pointermove", (ev) => {
    if (!drag || ev.pointerId !== drag.id) return;
    if (!drag.moved && Math.abs(ev.clientX - drag.x) < 10) return;
    if (!drag.moved) { drag.moved = true; try { tabsEl.setPointerCapture(ev.pointerId); } catch (e) {} }
    const L = lens(), a = tabsEl.getBoundingClientRect(), b = under(ev.clientX);
    if (L && b) {
      const r = b.getBoundingClientRect();
      const x = Math.max(0, Math.min(a.width - r.width, ev.clientX - a.left - r.width / 2));
      L.style.transition = "none";
      L.style.transform = `translate(${x}px, ${r.top - a.top}px) scale(1.08)`;
    }
    if (b && !b.classList.contains("hover")) {
      order().forEach((o) => o.classList.toggle("hover", o === b));
      if (navigator.vibrate) try { navigator.vibrate(5); } catch (e) {}
    }
  });
  const stop = (ev) => {
    if (!drag || ev.pointerId !== drag.id) return;
    const moved = drag.moved; drag = null;
    order().forEach((o) => o.classList.remove("hover"));
    const L = lens();
    if (L) L.style.transition = "";
    if (!moved) return;                                   // vanlig trykk – håndteres av klikket
    const b = under(ev.clientX);
    if (b && b.dataset.tab !== tab) setTab(b.dataset.tab);
    else window.dispatchEvent(new Event("resize"));       // legg linsen tilbake på riktig fane
    const swallow = (e) => { e.stopPropagation(); e.preventDefault(); };
    tabsEl.addEventListener("click", swallow, { capture: true, once: true });
    setTimeout(() => tabsEl.removeEventListener("click", swallow, { capture: true }), 300);
  };
  tabsEl.addEventListener("pointerup", stop);
  tabsEl.addEventListener("pointercancel", stop);
})();
