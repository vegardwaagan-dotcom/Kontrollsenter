// Kontrollsenter – flytende glass: glasslinse som glir til valgt fane, og av/på-bryter (Innstillinger → Utseende).
"use strict";
(() => {
  const get = () => { try { return JSON.parse(localStorage.getItem("ks_glass") ?? "true"); } catch (e) { return true; } };
  const apply = (on) => document.body.classList.toggle("glass", !!on);
  apply(get());
  const sw = document.getElementById("glass");
  if (sw) { sw.checked = get(); sw.onchange = () => { try { localStorage.setItem("ks_glass", JSON.stringify(sw.checked)); } catch (e) {} apply(sw.checked); move(); }; }

  const tabs = document.getElementById("tabs");
  if (!tabs) return;
  const lens = document.createElement("span");
  lens.className = "lens";
  tabs.prepend(lens);
  let last = null;
  function move() {
    const on = tabs.querySelector("button.on");
    if (!on || !document.body.classList.contains("glass")) { lens.style.opacity = "0"; return; }
    const a = tabs.getBoundingClientRect(), b = on.getBoundingClientRect();
    if (last && last !== on) {                         // en liten «dråpe»-bevegelse mens linsen flytter seg
      lens.classList.remove("wobble"); void lens.offsetWidth; lens.classList.add("wobble");
    }
    last = on;
    lens.style.opacity = "1";
    lens.style.transform = `translate(${b.left - a.left}px, ${b.top - a.top}px)`;
    lens.style.width = b.width + "px"; lens.style.height = b.height + "px";
  }
  new MutationObserver(move).observe(tabs, { subtree: true, attributes: true, attributeFilter: ["class"] });
  window.addEventListener("resize", move);
  setTimeout(move, 50);
})();
