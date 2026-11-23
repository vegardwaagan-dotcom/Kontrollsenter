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
    <div id="cal-cd" class="cal-cd" hidden></div>
    <div id="cal-grid" class="cal-grid"></div><div id="cal-info" class="cal-info"></div>
    <div id="cal-items"></div><button class="soft full-w" id="cal-add">＋ Ny hendelse</button>
    <details><summary>🏖️ Ferieplanlegger</summary><div id="cal-vac"></div></details>
    <div class="row"><input id="cal-q" class="search" placeholder="Søk i kalenderen …"></div><div id="cal-hits"></div>
    <div class="label">Neste røde dager</div><div id="cal-up"></div>
    <details><summary id="cal-ysum">Røde dager i året</summary><div id="cal-year"></div></details></div>`);
  const fam = document.getElementById("c-family");
  if (fam && fam.parentElement) fam.parentElement.appendChild(card); else document.querySelector("main").appendChild(card);
  const diary = h(`<div class="card" id="c-diary"><h2>📔 Dagbok</h2>
    <p class="dim small">Hver i familien har sin egen dagbok med egen kode (4–6 sifre). Kryptert – glemt kode kan ikke hentes tilbake.</p>
    <div id="dg-body"></div></div>`);
  card.parentElement.appendChild(diary);
  // ---------- hendelser fra PC-en (delt med huset på NAS-en) ----------
  let PC = {}, PCmeta = null;
  async function loadPC() {
    if (typeof token === "undefined" || !token || typeof X !== "function") return;
    try { const d = await X("kal", `y=${Y}&m=${M + 1}`); PC = Object.assign(PC, d.items || {}); PCmeta = d; render(); } catch (e) {}
  }
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  function pcItems(d) { return (PC[iso(d)] || []).filter((x) => !["red", "moon"].includes(x.kind)); }

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
        const pi = pcItems(d).filter((x) => x.kind !== "school");
        const school = (PC[iso(d)] || []).some((x) => x.kind === "school");
        const dots = pi.slice(0, 3).map((x) => `<b style="color:${x.color || "#888"}">●</b>`).join("");
        g += `<button class="cal-day${d.getMonth() !== M ? " out" : ""}${isRed(d) ? " red" : ""}${hol ? " hol" : ""}${school ? " school" : ""}${key(d) === key(t) ? " today" : ""}${key(d) === key(sel) ? " sel" : ""}" data-d="${d.getFullYear()}-${d.getMonth()}-${d.getDate()}" title="${esc(n)}">${d.getDate()}${dots ? `<i>${dots}</i>` : n && !hol ? "<i>●</i>" : ""}</button>`;
      }
    }
    $("#cal-grid").innerHTML = g;
    const n = Math.round((sel - t) / 864e5), nm = nameOf(sel), hol = !!red(sel.getFullYear())[key(sel)];
    $("#cal-info").innerHTML = `<b>${WDL[(sel.getDay() + 6) % 7].replace(/^./, (x) => x.toUpperCase())} ${sel.getDate()}. ${MND[sel.getMonth()]} ${sel.getFullYear()}</b> · uke ${week(sel)} · ` +
      (n === 0 ? "i dag" : n === 1 ? "i morgen" : n === -1 ? "i går" : n > 0 ? `om ${n} dager` : `for ${-n} dager siden`) +
      (nm ? `<br><span class="${hol ? "cal-red" : ""}">${esc(nm)}</span>` : sel.getDay() === 0 ? "<br>Søndag (rød dag)" : "");
    const its = (PC[iso(sel)] || []).filter((x) => x.kind !== "red" || true);
    $("#cal-items").innerHTML = its.map((x) => `<div class="cal-it${x.done ? " done" : ""}"><span style="color:${x.color || "#888"}">●</span> ${esc(x.icon || "")} ${esc(x.title)}${x.time ? ` <span class="dim">${esc(x.time)}</span>` : ""}` +
      (x.src === "egen" ? `${["todo", "routine"].includes(x.kind) ? `<button class="soft small" data-done="${esc(x.id)}" data-on="${x.done ? 0 : 1}">${x.done ? "↺" : "✓"}</button>` : ""}<button class="soft small" data-edit="${esc(x.id)}">✏️</button>` : "") + "</div>").join("");
    $("#cal-cd").hidden = !(PCmeta && PCmeta.countdown); if (PCmeta) $("#cal-cd").textContent = "⏳ " + PCmeta.countdown;
    if (PCmeta) $("#cal-vac").innerHTML = (PCmeta.vacation || []).map((v) => `<div class="cal-row"><span>${esc(v.name)}</span><span>${v.took} ${v.took === 1 ? "dag" : "dager"} fri → ${v.len} dager</span><span class="dim">${v.from.slice(8)}.${+v.from.slice(5, 7)}–${v.to.slice(8)}.${+v.to.slice(5, 7)}</span></div>`).join("");
    card.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => editEvent(((PCmeta || {}).events || []).find((e) => e.id === b.dataset.edit))));
    card.querySelectorAll("[data-done]").forEach((b) => (b.onclick = async () => { await act({ a: "kaldone", id: b.dataset.done, day: iso(sel), on: b.dataset.on === "1" }, true); loadPC(); }));
    const up = []; let y = t.getFullYear();
    while (up.length < 8 && y < t.getFullYear() + 3) { Object.entries(red(y)).forEach(([k, nmx]) => { const [a, b, c] = k.split("-").map(Number); const d = new Date(a, b - 1, c); if (d >= t && up.length < 8) up.push([d, nmx]); }); y++; }
    $("#cal-up").innerHTML = up.map(([d, nmx]) => { const k = Math.round((d - t) / 864e5); return row(d, nmx, k === 0 ? "i dag" : k === 1 ? "i morgen" : `om ${k} d`); }).join("");
    $("#cal-ysum").textContent = "Røde dager i " + Y;
    $("#cal-year").innerHTML = Object.entries(red(Y)).map(([k, nmx]) => { const [a, b, c] = k.split("-").map(Number); const d = new Date(a, b - 1, c);
      return row(d, nmx + ([1, 5].includes(d.getDay()) ? " 🏖️" : ""), WDL[(d.getDay() + 6) % 7]); }).join("") + '<p class="dim small">🏖️ = langhelg</p>';
    card.querySelectorAll("[data-d],[data-go]").forEach((b) => (b.onclick = () => {
      const [a, m, d] = (b.dataset.d || b.dataset.go).split("-").map(Number); sel = new Date(a, m, d); Y = a; M = m; render(); }));
  }
  const go = (dm) => { const d = new Date(Y, M + dm, 1); Y = d.getFullYear(); M = d.getMonth(); render(); loadPC(); };
  function editEvent(ev) {
    ev = ev || {}; const kinds = (PCmeta && PCmeta.kinds) || { event: ["📌", "Hendelse"] }, cols = (PCmeta && PCmeta.colors) || ["#5b8cff"];
    const reps = [["", "Ikke gjenta"], ["weekly", "Hver uke"], ["days:14", "Hver 2. uke"], ["monthly", "Hver måned"], ["months:3", "Hver 3. måned"], ["yearly", "Hvert år"]];
    const rems = [[-1, "Ingen påminnelse"], [0, "Når det starter"], [15, "15 min før"], [30, "30 min før"], [60, "1 time før"], [1440, "Dagen før"]];
    ctSheet(ev.id ? "Endre hendelse" : "Ny hendelse",
      `<input id="ev-t" class="search" placeholder="Hva skjer?" value="${esc(ev.title || "")}">
       <select id="ev-k" class="search">${Object.entries(kinds).map(([k, v]) => `<option value="${k}"${(ev.kind || "event") === k ? " selected" : ""}>${v[0]} ${esc(v[1])}</option>`).join("")}</select>
       <div class="row"><input id="ev-d" type="date" class="search" value="${esc(ev.date || iso(sel))}"><input id="ev-h" type="time" class="search" value="${esc(ev.time || "")}"></div>
       <select id="ev-r" class="search">${reps.map(([k, n]) => `<option value="${k}"${(ev.repeat || "") === k ? " selected" : ""}>${n}</option>`).join("")}</select>
       <select id="ev-m" class="search">${rems.map(([k, n]) => `<option value="${k}"${(ev.remind ?? 30) === k ? " selected" : ""}>${n}</option>`).join("")}</select>
       <div class="row ev-cols">${cols.map((c) => `<button class="ev-col${(ev.color || cols[0]) === c ? " on" : ""}" data-c="${c}" style="background:${c}"></button>`).join("")}</div>
       <input id="ev-n" class="search" placeholder="Notat (valgfritt)" value="${esc(ev.note || "")}">
       <div class="row"><button class="primary" id="ev-ok">Lagre</button>${ev.id ? '<button class="soft" id="ev-del">🗑️ Slett</button>' : ""}</div>
       <p class="dim small">Lagres på NAS-en – alle i huset ser det.</p>`, (bg, close) => {
        let col = ev.color || cols[0];
        bg.querySelectorAll("[data-c]").forEach((b) => (b.onclick = () => { col = b.dataset.c; bg.querySelectorAll("[data-c]").forEach((x) => x.classList.toggle("on", x === b)); }));
        bg.querySelector("#ev-ok").onclick = async () => {
          try { await api("/api/action", { a: "kaladd", id: ev.id, title: bg.querySelector("#ev-t").value, kind: bg.querySelector("#ev-k").value,
            date: bg.querySelector("#ev-d").value, time: bg.querySelector("#ev-h").value, repeat: bg.querySelector("#ev-r").value,
            remind: +bg.querySelector("#ev-m").value, color: col, note: bg.querySelector("#ev-n").value, done: ev.done }); close(); PC = {}; loadPC(); }
          catch (e) { toast("✗ " + e.message); }
        };
        const del = bg.querySelector("#ev-del");
        if (del) del.onclick = async () => { if (await confirmDlg("Slette hendelsen?")) { await act({ a: "kaldel", id: ev.id }, true); close(); PC = {}; loadPC(); } };
      });
  }
  $("#cal-add").onclick = () => { if (typeof token === "undefined" || !token) { toast("Koble til en PC for å legge til hendelser"); return; } editEvent(null); };
  $("#cal-q").addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    try { const r = await X("kalsok", "q=" + encodeURIComponent(e.target.value));
      $("#cal-hits").innerHTML = r.hits.map((x) => { const [a, b, c] = x.d.split("-").map(Number); return row(new Date(a, b - 1, c), x.title + (x.time ? " " + x.time : ""), ""); }).join("") || '<p class="dim small">Ingen treff</p>';
      card.querySelectorAll("#cal-hits [data-go]").forEach((b) => (b.onclick = () => { const [a, m, d] = b.dataset.go.split("-").map(Number); sel = new Date(a, m, d); Y = a; M = m; render(); loadPC(); }));
    } catch (err) { toast("✗ " + err.message); }
  });
  // ---------- dagbok (åpnes med koden – PC-en dekrypterer og glemmer koden) ----------
  let dgTok = null, dgMoods = [];
  async function dgPeople() {
    if (typeof token === "undefined" || !token) { $("#dg-body").innerHTML = '<p class="dim small">Koble til en PC hjemme for å bruke dagboken.</p>'; return; }
    let r; try { r = await X("dagbok"); } catch (e) { $("#dg-body").innerHTML = '<p class="dim small">PC-en må oppdateres for dagboken.</p>'; return; }
    dgMoods = r.moods || [];
    $("#dg-body").innerHTML = '<div class="dg-people">' + r.people.map((p) => `<button class="soft" data-p="${esc(p.id)}" data-n="${esc(p.name)}">📔<br>${esc(p.name)}</button>`).join("") +
      '</div><button class="soft" id="dg-new">＋ Ny dagbok</button>';
    $$("#dg-body [data-p]").forEach((b) => (b.onclick = () => pinPad(b.dataset.n, async (pin) => {
      const res = JSON.parse((await api("/api/action", { a: "dagbok_open", id: b.dataset.p, pin: pin })).msg); dgTok = res.tok; dgShow(); })));
    $("#dg-new").onclick = () => {
      const nm = prompt("Navnet ditt"); if (!nm) return;
      pinPad("Velg kode (4–6 sifre)", async (pin) => {
        setTimeout(() => pinPad("Samme kode en gang til", async (p2) => {
          if (p2 !== pin) throw new Error("Kodene er ikke like – trykk Ny dagbok og prøv igjen");
          const res = JSON.parse((await api("/api/action", { a: "dagbok_create", name: nm, pin: pin })).msg);
          dgTok = res.tok; dgShow();
        }), 300);
      });
    };
  }
  function pinPad(title, onPin) {
    let pin = "";
    ctSheet("🔒 " + esc(title), `<div class="pin-dots" id="pin-dots"></div><p class="dim small" id="pin-msg"></p><div class="pin-pad">` +
      [1, 2, 3, 4, 5, 6, 7, 8, 9, "⌫", 0, "✓"].map((k) => `<button class="soft" data-k="${k}">${k}</button>`).join("") + "</div>", (bg, close) => {
        const show = () => (bg.querySelector("#pin-dots").textContent = "●".repeat(pin.length) || "– – – –");
        show();
        bg.querySelectorAll("[data-k]").forEach((b) => (b.onclick = async () => {
          const k = b.dataset.k;
          if (k === "⌫") pin = pin.slice(0, -1);
          else if (k === "✓") {
            if (pin.length < 4) { bg.querySelector("#pin-msg").textContent = "Koden må ha 4–6 sifre"; return; }
            bg.querySelector("#pin-msg").textContent = "Sjekker …";
            try { await onPin(pin); close(); } catch (e) { pin = ""; show(); bg.querySelector("#pin-msg").textContent = "✗ " + e.message; if (KS && KS.vibrate) KS.vibrate(); }
            return;
          } else if (pin.length < 6) pin += k;
          show();
        }));
      });
  }
  async function dgShow() {
    let d; try { d = JSON.parse((await api("/api/action", { a: "dagbok_list", tok: dgTok })).msg); } catch (e) { dgTok = null; toast(e.message); dgPeople(); return; }
    const es = (d.entries || []).slice().reverse();
    $("#dg-body").innerHTML = `<div class="row between"><b>📔 ${esc(d.name)}</b><button class="soft small" id="dg-lock">🔒 Lås</button></div>
      <div class="dg-moods">${dgMoods.map((m) => `<button class="soft small" data-m="${m}">${m}</button>`).join("")}</div>
      <textarea id="dg-text" rows="4" placeholder="Hvordan var dagen?"></textarea><button class="primary" id="dg-save">💾 Lagre</button>
      <div class="label">Tidligere (${es.length})</div>` + es.slice(0, 100).map((e) => `<div class="dg-e"><small class="dim">${esc(e.day)}</small><div>${esc((e.mood ? e.mood + " " : "") + e.text)}</div><button class="soft small" data-del="${esc(e.id)}">🗑️</button></div>`).join("");
    let mood = "";
    $$("#dg-body [data-m]").forEach((b) => (b.onclick = () => { mood = b.dataset.m; $$("#dg-body [data-m]").forEach((x) => x.classList.toggle("on", x === b)); }));
    $("#dg-save").onclick = async () => { try { await api("/api/action", { a: "dagbok_write", tok: dgTok, text: $("#dg-text").value, mood: mood }); dgShow(); } catch (e) { toast("✗ " + e.message); } };
    $("#dg-lock").onclick = async () => { await act({ a: "dagbok_lock", tok: dgTok }, true); dgTok = null; dgPeople(); };
    $$("#dg-body [data-del]").forEach((b) => (b.onclick = async () => { if (await confirmDlg("Slette innlegget?")) { await act({ a: "dagbok_delete", tok: dgTok, eid: b.dataset.del }, true); dgShow(); } }));
  }
  document.addEventListener("visibilitychange", () => { if (document.hidden && dgTok) { act({ a: "dagbok_lock", tok: dgTok }, true); dgTok = null; dgPeople(); } });
  setTimeout(() => { loadPC(); dgPeople(); }, 1500);
  $("#cal-prev").onclick = () => go(-1); $("#cal-next").onclick = () => go(1);
  $("#cal-today").onclick = () => { sel = today(); Y = sel.getFullYear(); M = sel.getMonth(); render(); };
  $("#cal-ym").onclick = () => go(-12); $("#cal-yp").onclick = () => go(12); $("#cal-y10").onclick = () => go(120);
  let sx = 0;                                              // sveip til siden for å bla
  $("#cal-grid").addEventListener("touchstart", (e) => (sx = e.touches[0].clientX), { passive: true });
  $("#cal-grid").addEventListener("touchend", (e) => { const dx = e.changedTouches[0].clientX - sx; if (Math.abs(dx) > 60) go(dx < 0 ? 1 : -1); }, { passive: true });
  render();
})();
