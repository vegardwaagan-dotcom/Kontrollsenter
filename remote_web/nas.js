// NAS-disken i appen: bla i NAS-en gjennom PC-en (virker også borte via Tailscale), last ned, last opp, ordne.
(() => {
  const esc2 = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const human = (n) => { const u = ["B", "kB", "MB", "GB", "TB"]; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return (i ? n.toFixed(1) : n) + " " + u[i]; };
  const card = document.createElement("div");
  card.className = "card"; card.id = "c-nas";
  card.innerHTML = '<h2>NAS-disken</h2><p class="dim small" id="nas-where">Trykk for å se NAS-en</p>'
    + '<div class="row"><select id="nas-share"></select><button class="soft small" id="nas-up" aria-label="Opp">⬆️</button>'
    + '<button class="soft small" id="nas-new">＋ Mappe</button><label class="soft small btn-like" id="nas-upl">⤴ Last opp<input type="file" id="nas-file" multiple hidden></label></div>'
    + '<div class="dim small" id="nas-path"></div><div id="nas-login" hidden><input id="nas-user" placeholder="Brukernavn på NAS-en">'
    + '<input id="nas-pw" type="password" placeholder="Passord"><button class="primary small" id="nas-login-go">Logg inn</button></div>'
    + '<div id="nas-list" class="list"></div><div class="dim small" id="nas-msg"></div>';
  const host = document.querySelector("#kontroll .grid") || document.querySelector("#kontroll");
  if (!host) return;
  host.appendChild(card);
  const $n = (s) => card.querySelector(s);
  let share = "", path = "", loaded = false;

  async function shares() {
    let r; try { r = await api("/api/nas/shares"); } catch (e) { $n("#nas-where").textContent = "✗ " + e.message; return; }
    $n("#nas-where").textContent = r.where === "hjemme" ? "● NAS-en er tilkoblet (hjemme)" : r.where === "tailscale"
      ? "● NAS-en er tilkoblet gjennom Tailscale" : "○ PC-en når ikke NAS-en nå";
    const names = r.shares.map((s) => s.name).sort((a, b) => (a !== r.default) - (b !== r.default) || a.localeCompare(b));
    share = share || r.default;
    $n("#nas-share").innerHTML = names.map((x) => '<option' + (x === share ? " selected" : "") + ">" + esc2(x) + "</option>").join("");
    if (r.where) go("");
  }
  async function go(p) {
    path = p; $n("#nas-path").textContent = "📁 " + share + (p ? " › " + p.split("/").join(" › ") : "");
    $n("#nas-msg").textContent = "Henter …";
    let r; try { r = await api("/api/nas/list?share=" + encodeURIComponent(share) + "&path=" + encodeURIComponent(p)); }
    catch (e) {
      $n("#nas-list").innerHTML = ""; $n("#nas-msg").textContent = "✗ " + e.message;
      $n("#nas-login").hidden = !/logg inn|passord/i.test(e.message); return;
    }
    $n("#nas-login").hidden = true;
    $n("#nas-msg").textContent = r.items.length ? "" : "Mappa er tom";
    $n("#nas-list").innerHTML = r.items.map((it, i) => '<div class="row between nas-it" data-i="' + i + '"><span>' + (it.dir ? "📁 " : "📄 ")
      + "<b>" + esc2(it.name) + "</b>" + (it.dir ? "" : ' <small class="dim">' + human(it.size) + "</small>") + "</span>"
      + '<button class="soft small" data-more="' + i + '">⋯</button></div>').join("");
    card.querySelectorAll(".nas-it").forEach((row) => {
      const it = r.items[+row.dataset.i], full = (p ? p + "/" : "") + it.name;
      row.onclick = (e) => { if (e.target.dataset.more !== undefined) return; it.dir ? go(full) : download(full, it.name); };
      row.querySelector("[data-more]").onclick = () => more(full, it);
    });
  }
  function fileUrl(full) {
    return location.origin + "/api/nas/file?share=" + encodeURIComponent(share) + "&path=" + encodeURIComponent(full) + "&k=" + encodeURIComponent(token);
  }
  function download(full, name) {
    if (window.KS && KS.download) { KS.download(fileUrl(full), name); toast("Lastes ned til telefonen: " + name); }
    else window.open(fileUrl(full), "_blank");
  }
  async function more(full, it) {
    const choice = prompt((it.dir ? "Mappe: " : "Fil: ") + it.name + "\nSkriv nytt navn – eller «slett» for å slette:", it.name);
    if (choice === null || choice.trim() === it.name) return;
    let r;
    if (choice.trim().toLowerCase() === "slett") {
      if (!(await confirmDlg("Slette «" + it.name + "» fra NAS-en? Det kan ikke angres."))) return;
      r = await act({ a: "nas", do: "delete", share, path: full, dir: it.dir });
    } else r = await act({ a: "nas", do: "rename", share, path: full, name: choice.trim() });
    if (r && r.msg) toast(r.msg);
    go(path);
  }
  async function upload(files) {
    for (const [n, f] of [...files].entries()) {
      $n("#nas-msg").textContent = "Laster opp " + (n + 1) + "/" + files.length + ": " + f.name + " …";
      try {
        const r = await fetch("/api/nas/upload?share=" + encodeURIComponent(share) + "&path=" + encodeURIComponent(path) + "&name=" + encodeURIComponent(f.name),
          { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/octet-stream" }, body: f });
        const j = await r.json();
        if (!r.ok || j.ok === false) throw new Error(j.error || r.statusText);
      } catch (e) { $n("#nas-msg").textContent = "✗ " + f.name + ": " + e.message; return; }
    }
    toast(files.length > 1 ? files.length + " filer lastet opp" : files[0].name + " er lastet opp");
    go(path);
  }
  $n("#nas-share").onchange = () => { share = $n("#nas-share").value; go(""); };
  $n("#nas-up").onclick = () => go(path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");
  $n("#nas-new").onclick = async () => {
    const name = prompt("Navnet på den nye mappa:"); if (!name || !name.trim()) return;
    const r = await act({ a: "nas", do: "mkdir", share, path, name: name.trim() }); if (r && r.msg) toast(r.msg); go(path);
  };
  $n("#nas-file").onchange = () => { const fs = $n("#nas-file").files; if (fs && fs.length) upload(fs); $n("#nas-file").value = ""; };
  $n("#nas-login-go").onclick = async () => {
    const r = await act({ a: "nas", do: "login", share, user: $n("#nas-user").value.trim(), password: $n("#nas-pw").value });
    $n("#nas-pw").value = ""; if (r && r.msg) toast(r.msg); go("");
  };
  // hentes første gang kortet vises
  new IntersectionObserver((es) => { if (!loaded && es.some((e) => e.isIntersecting)) { loaded = true; shares(); } }).observe(card);
})();
