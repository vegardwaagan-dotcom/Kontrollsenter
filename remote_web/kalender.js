// ---------- Kalender med norske røde dager (samme som Hjemmet › Kalender på PC-en) ----------
// Regnes ut på telefonen (påsken med Gauss/Meeus), så den virker for alle år – også uten kontakt med PC-en.
(() => {
  const MND = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "desember"];
  const WD = ["man", "tir", "ons", "tor", "fre", "lør", "søn"], WDL = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"];
  const key = (d) => d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  const add = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  function easter(y) {
    const a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
    const g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4;
    const l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
    const mo = Math.floor((h + l - 7 * m + 114) / 31), da = ((h + l - 7 * m + 114) % 31) + 1;
    return new Date(y, mo - 1, da);
  }
  const cache = {};
  function red(y) {
    if (cache[y]) return cache[y];
    const e = easter(y), r = {};
    [[new Date(y, 0, 1), "Nyttårsdag"], [add(e, -3), "Skjærtorsdag"], [add(e, -2), "Langfredag"], [e, "1. påskedag"],
     [add(e, 1), "2. påskedag"], [new Date(y, 4, 1), "Arbeidernes dag"], [new Date(y, 4, 17), "Grunnlovsdagen"],
     [add(e, 39), "Kristi himmelfartsdag"], [add(e, 49), "1. pinsedag"], [add(e, 50), "2. pinsedag"],
     [new Date(y, 11, 25), "1. juledag"], [new Date(y, 11, 26), "2. juledag"]].forEach(([d, n]) => (r[key(d)] = n));
    return (cache[y] = r);
  }
  function nthSun(y, m, n) { const f = new Date(y, m, 1); return add(f, ((7 - f.getDay()) % 7) + 7 * (n - 1)); }
  function special(y) {
    const e = easter(y), r = {};
    [[new Date(y, 1, 14), "Valentinsdagen"], [nthSun(y, 1, 2), "Morsdag"], [add(e, -49), "Fastelavnssøndag"],
     [add(e, -7), "Palmesøndag"], [new Date(y, 5, 23), "Sankthansaften"], [nthSun(y, 10, 2), "Farsdag"],
     [new Date(y, 11, 24), "Julaften"], [new Date(y, 11, 31), "Nyttårsaften"]].forEach(([d, n]) => (r[key(d)] = n));
    return r;
  }
  const isRed = (d) => d.getDay() === 0 || !!red(d.getFullYear())[key(d)];
  const nameOf = (d) => red(d.getFullYear())[key(d)] || special(d.getFullYear())[key(d)] || "";
  function week(d) { const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); const n = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - n); const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1)); return Math.ceil(((t - y0) / 864e5 + 1) / 7); }
  const today = () => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), n.getDate()); };
  let Y = today().getFullYear(), M = today().getMonth(), sel = today();

  const card = h(`<div class="card" id="c-cal"><h2>📅 Kalender</h2>
    <p class="dim small">Norske røde dager er markert med rødt. Bla så langt fram i tid du vil.</p>
    <div class="cal-nav"><button class="soft" id="cal-prev">‹</button><b id="cal-title"></b><button class="soft" id="cal-next">›</button></div>
    <div class="cal-jump"><button class="soft small" id="cal-today">I dag</button><button class="soft small" id="cal-ym">−1 år</button><button class="soft small" id="cal-yp">+1 år</button><button class="soft small" id="cal-y10">+10 år</button></div>
    <div id="cal-grid" class="cal-grid"></div><div id="cal-info" class="cal-info"></div>
    <div class="label">Neste røde dager</div><div id="cal-up"></div>
    <details><summary id="cal-ysum">Røde dager i året</summary><div id="cal-year"></div></details></div>`);
  const fam = document.getElementById("c-family");
  if (fam && fam.parentElement) fam.parentElement.appendChild(card); else document.querySelector("main").appendChild(card);

  function row(d, n, right) {
    return `<button class="cal-row" data-go="${d.getFullYear()}-${d.getMonth()}-${d.getDate()}"><span class="cal-red">${d.getDate()}. ${MND[d.getMonth()].slice(0, 3)}${d.getFullYear() !== Y ? " " + d.getFullYear() : ""}</span><span>${esc(n)}</span><span class="dim">${right}</span></button>`;
  }
  function render() {
    $("#cal-title").textContent = MND[M][0].toUpperCase() + MND[M].slice(1) + " " + Y;
    const first = new Date(Y, M, 1), start = add(first, -((first.getDay() + 6) % 7)), t = today();
    let g = '<span class="cal-wd">uke</span>' + WD.map((w, i) => `<span class="cal-wd${i === 6 ? " cal-red" : ""}">${w}</span>`).join("");
    for (let r = 0; r < 6; r++) {
      const ws = add(start, r * 7); if (r > 3 && ws.getMonth() !== M) break;
      g += `<span class="cal-wk">${week(ws)}</span>`;
      for (let c = 0; c < 7; c++) {
        const d = add(ws, c), n = nameOf(d), hol = !!red(d.getFullYear())[key(d)];
        g += `<button class="cal-day${d.getMonth() !== M ? " out" : ""}${isRed(d) ? " red" : ""}${hol ? " hol" : ""}${key(d) === key(t) ? " today" : ""}${key(d) === key(sel) ? " sel" : ""}" data-d="${d.getFullYear()}-${d.getMonth()}-${d.getDate()}" title="${esc(n)}">${d.getDate()}${n && !hol ? "<i>●</i>" : ""}</button>`;
      }
    }
    $("#cal-grid").innerHTML = g;
    const n = Math.round((sel - t) / 864e5), nm = nameOf(sel), hol = !!red(sel.getFullYear())[key(sel)];
    $("#cal-info").innerHTML = `<b>${WDL[(sel.getDay() + 6) % 7].replace(/^./, (x) => x.toUpperCase())} ${sel.getDate()}. ${MND[sel.getMonth()]} ${sel.getFullYear()}</b> · uke ${week(sel)} · ` +
      (n === 0 ? "i dag" : n === 1 ? "i morgen" : n === -1 ? "i går" : n > 0 ? `om ${n} dager` : `for ${-n} dager siden`) +
      (nm ? `<br><span class="${hol ? "cal-red" : ""}">${esc(nm)}</span>` : sel.getDay() === 0 ? "<br>Søndag (rød dag)" : "");
    const up = []; let y = t.getFullYear();
    while (up.length < 8 && y < t.getFullYear() + 3) { Object.entries(red(y)).forEach(([k, nmx]) => { const [a, b, c] = k.split("-").map(Number); const d = new Date(a, b - 1, c); if (d >= t && up.length < 8) up.push([d, nmx]); }); y++; }
    $("#cal-up").innerHTML = up.map(([d, nmx]) => { const k = Math.round((d - t) / 864e5); return row(d, nmx, k === 0 ? "i dag" : k === 1 ? "i morgen" : `om ${k} d`); }).join("");
    $("#cal-ysum").textContent = "Røde dager i " + Y;
    $("#cal-year").innerHTML = Object.entries(red(Y)).map(([k, nmx]) => { const [a, b, c] = k.split("-").map(Number); const d = new Date(a, b - 1, c);
      return row(d, nmx + ([1, 5].includes(d.getDay()) ? " 🏖️" : ""), WDL[(d.getDay() + 6) % 7]); }).join("") + '<p class="dim small">🏖️ = langhelg</p>';
    card.querySelectorAll("[data-d],[data-go]").forEach((b) => (b.onclick = () => {
      const [a, m, d] = (b.dataset.d || b.dataset.go).split("-").map(Number); sel = new Date(a, m, d); Y = a; M = m; render(); }));
  }
  const go = (dm) => { const d = new Date(Y, M + dm, 1); Y = d.getFullYear(); M = d.getMonth(); render(); };
  $("#cal-prev").onclick = () => go(-1); $("#cal-next").onclick = () => go(1);
  $("#cal-today").onclick = () => { sel = today(); Y = sel.getFullYear(); M = sel.getMonth(); render(); };
  $("#cal-ym").onclick = () => go(-12); $("#cal-yp").onclick = () => go(12); $("#cal-y10").onclick = () => go(120);
  let sx = 0;                                              // sveip til siden for å bla
  $("#cal-grid").addEventListener("touchstart", (e) => (sx = e.touches[0].clientX), { passive: true });
  $("#cal-grid").addEventListener("touchend", (e) => { const dx = e.changedTouches[0].clientX - sx; if (Math.abs(dx) > 60) go(dx < 0 ? 1 : -1); }, { passive: true });
  render();
})();
