"use strict";

/* Cellarium – Oberfläche. Ohne Token (z. B. auf GitHub Pages) läuft sie als Demo mit demo.json. */

const $ = (s, el = document) => el.querySelector(s);
const LOCAL = ["127.0.0.1", "localhost"].includes(location.hostname);
const TOKEN = (() => {
  // Das Token kommt einmalig im URL-Fragment; für Neuladen merkt sich das Fenster es in der Sitzung
  const t = new URLSearchParams(location.hash.slice(1)).get("t");
  try {
    if (t) sessionStorage.setItem("cellarium.t", t);
    return t || sessionStorage.getItem("cellarium.t");
  } catch { return t; }
})();
const DEMO = !TOKEN && !LOCAL;

const SOURCES = {
  steam: { label: "Steam", c: "#66c0f4" },
  lutris: { label: "Lutris", c: "#ff9f43" },
  faugus: { label: "Faugus", c: "#4fdba6" },
  umu: { label: "umu", c: "#c084fc" },
  heroic: { label: "Heroic", c: "#ffd166" },
  bottles: { label: "Bottles", c: "#5ea9ff" },
  wine: { label: "Wine", c: "#ff7aa2" },
};

let state = { prefixes: [], runners: [], scanning: true, measuring: 0, home: "" };
const ui = { filter: "all", sort: localGet("sort") || "size", q: "", open: null, loaded: false };

function localGet(k) { try { return localStorage.getItem("cellarium." + k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem("cellarium." + k, v); } catch { /* egal */ } }

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
const rtf = new Intl.RelativeTimeFormat("de", { numeric: "auto" });

function bytes(n) {
  if (n == null) return null;
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1000 && i < u.length - 1) { n /= 1000; i++; }
  return `${nf.format(n >= 100 ? Math.round(n) : n)} ${u[i]}`;
}
function ago(ts) {
  if (!ts) return "nie";
  const s = (ts * 1000 - Date.now()) / 1000;
  for (const [unit, sec] of [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]]) {
    if (Math.abs(s) >= sec) return rtf.format(Math.round(s / sec), unit);
  }
  return "gerade eben";
}
const tilde = (p) => (state.home && p.startsWith(state.home) ? "~" + p.slice(state.home.length) : p);
const nameOf = (p) => p.label || p.autoName;
const orphan = (p) => !p.refs.length && !p.isDefault;
const apps = (p) => p.programs.filter((x) => !x.runtime);
const icon = (id, cls = "i") => `<svg class="${cls}"><use href="#i-${id}"/></svg>`;
const byId = (id) => state.prefixes.find((p) => p.id === id);

// ---------- Daten ----------

async function api(path, body) {
  const res = await fetch(`/api/${path}`, {
    method: body ? "POST" : "GET",
    headers: { "X-Cellarium-Token": TOKEN, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Fehler ${res.status}`);
  return data;
}

async function load() {
  if (DEMO) {
    if (!ui.loaded) {
      state = await (await fetch("demo.json")).json();
      // Zeiten relativ zu heute halten, damit „zuletzt benutzt“ nicht mit der Zeit veraltet
      const shift = Date.now() / 1000 - state.scannedAt;
      state.prefixes.forEach((p) => p.lastUsed && (p.lastUsed += shift));
    }
  } else {
    state = await api("state");
  }
  ui.loaded = true;
  render();
}

let pollTimer;
function schedule() {
  clearTimeout(pollTimer);
  if (DEMO) return;
  const busy = state.scanning || state.measuring > 0;
  pollTimer = setTimeout(async () => {
    try { await load(); } catch (e) { toast("Verbindung zur App verloren – ist sie noch offen?", true); }
    schedule();
  }, busy ? 1500 : 6000);
}

// ---------- Ableitungen ----------

function visible() {
  const q = ui.q.trim().toLowerCase();
  let list = state.prefixes.filter((p) => {
    if (ui.filter === "hidden") return p.hidden;
    if (p.hidden) return false;
    if (ui.filter === "orphan") return orphan(p);
    if (ui.filter === "running") return p.running > 0;
    if (ui.filter !== "all") return p.source === ui.filter;
    return true;
  });
  if (q) {
    list = list.filter((p) => [nameOf(p), p.path, p.version, ...p.refs.map((r) => r.title), ...p.programs.map((x) => x.name)]
      .some((s) => (s || "").toLowerCase().includes(q)));
  }
  const sorters = {
    size: (a, b) => (b.size ?? -1) - (a.size ?? -1),
    used: (a, b) => (b.lastUsed ?? 0) - (a.lastUsed ?? 0),
    name: (a, b) => nameOf(a).localeCompare(nameOf(b), "de"),
  };
  return list.sort(sorters[ui.sort]);
}

function hints() {
  const out = [];
  const live = state.prefixes.filter((p) => !p.hidden);
  const orph = live.filter(orphan);
  if (orph.length) {
    const size = orph.reduce((s, p) => s + (p.size || 0), 0);
    out.push({ icon: "unlink", text: `${orph.length} Prefix${orph.length > 1 ? "e" : ""} ohne Launcher${size ? ` – zusammen ${bytes(size)}` : ""}`, act: () => setFilter("orphan") });
  }
  const seen = new Map();
  for (const p of live) for (const a of apps(p)) {
    const k = a.name.toLowerCase();
    if (!seen.has(k)) seen.set(k, { name: a.name, ids: new Set() });
    seen.get(k).ids.add(p.id);
  }
  [...seen.values()].filter((v) => v.ids.size > 1).sort((a, b) => b.ids.size - a.ids.size).slice(0, 3)
    .forEach((v) => out.push({ icon: "twins", text: `„${v.name}“ steckt in ${v.ids.size} Prefixen`, act: () => setQuery(v.name) }));
  for (const p of live.filter((p) => p.nestedIn)) {
    const parent = byId(p.nestedIn);
    if (parent) out.push({ icon: "layers", info: true, text: `„${nameOf(p)}“ liegt innerhalb von „${nameOf(parent)}“`, act: () => openSheet(p.id) });
  }
  const noRunner = live.filter((p) => !p.runner);
  if (noRunner.length && !DEMO) out.push({ icon: "alert", text: `Für ${noRunner.length} Prefix${noRunner.length > 1 ? "e" : ""} fehlt der passende Runner`, act: () => openSheet(noRunner[0].id) });
  return out.slice(0, 6);
}

// ---------- Darstellung ----------

function render() {
  $("#demo-banner").hidden = !DEMO;
  $("#rescan").classList.toggle("spin", !!state.scanning);
  renderStats();
  renderHints();
  renderFilters();
  renderGrid();
  if (ui.open) renderSheet();
}

function renderStats() {
  const live = state.prefixes.filter((p) => !p.hidden);
  const total = live.reduce((s, p) => s + (p.size || 0), 0);
  const orph = live.filter(orphan);
  const running = live.filter((p) => p.running > 0);
  const proton = live.filter((p) => p.kind === "proton").length;
  $("#stats").innerHTML = [
    ["Prefixe", live.length || (state.scanning ? "…" : 0), `${proton} Proton · ${live.length - proton} Wine`],
    ["Belegt", bytes(total) || "…", state.measuring ? `misst noch ${state.measuring} …` : "auf der Platte"],
    ["Ohne Launcher", orph.length, orph.length ? `${bytes(orph.reduce((s, p) => s + (p.size || 0), 0))} aufräumbar?` : "alles zugeordnet"],
    ["Läuft gerade", running.length, running.length ? running.map(nameOf).join(", ") : "nichts aktiv", running.length ? "var(--ok)" : null],
  ].map(([label, value, sub, dot]) => `
    <div class="stat glass">
      <div class="label">${dot ? `<span class="dot" style="background:${dot}"></span>` : ""}${esc(label)}</div>
      <div class="value">${esc(value)}</div>
      <div class="sub">${esc(sub)}</div>
    </div>`).join("");
}

function renderHints() {
  const list = hints();
  const el = $("#hints");
  el.innerHTML = list.map((h, i) => `<button class="hint glass ${h.info ? "info" : ""}" data-i="${i}">${icon(h.icon)}<span>${esc(h.text)}</span></button>`).join("");
  el.querySelectorAll(".hint").forEach((b) => b.addEventListener("click", () => list[+b.dataset.i].act()));
}

function renderFilters() {
  const live = state.prefixes.filter((p) => !p.hidden);
  const count = (fn) => live.filter(fn).length;
  const chips = [["all", "Alle", live.length]];
  for (const [k, s] of Object.entries(SOURCES)) {
    const n = count((p) => p.source === k);
    if (n) chips.push([k, s.label, n, s.c]);
  }
  chips.push(["|"]);
  chips.push(["orphan", "Ohne Launcher", count(orphan), "var(--warn)"]);
  const run = count((p) => p.running > 0);
  if (run) chips.push(["running", "Läuft", run, "var(--ok)"]);
  const hid = state.prefixes.length - live.length;
  if (hid) chips.push(["hidden", "Ausgeblendet", hid]);
  $("#filters").innerHTML = chips.map(([k, label, n, c]) => k === "|" ? `<span class="sep"></span>` :
    `<button class="chip ${ui.filter === k ? "on" : ""}" data-f="${k}" ${c ? `style="--c:${c}"` : ""}>${c ? `<span class="sw"></span>` : ""}${esc(label)}<span class="n">${n}</span></button>`).join("");
}

function card(p, i, maxSize) {
  const src = SOURCES[p.source] || SOURCES.wine;
  const a = apps(p);
  const badges = [];
  if (p.running) badges.push(`<span class="badge live">läuft</span>`);
  if (orphan(p)) badges.push(`<span class="badge warn">${icon("unlink")}ohne Launcher</span>`);
  if (p.nestedIn) badges.push(`<span class="badge">${icon("layers")}verschachtelt</span>`);
  if (p.isDefault) badges.push(`<span class="badge">Standard</span>`);
  const pct = p.size && maxSize ? Math.max(2, (p.size / maxSize) * 100) : 0;
  const meta = [p.version || (p.kind === "wine" ? "Wine" : "Proton"), p.arch === "win32" ? "32-bit" : "", `benutzt ${ago(p.lastUsed)}`].filter(Boolean);
  return `
  <article class="card glass ${ui.open === p.id ? "active" : ""} ${p.hidden ? "dim" : ""}" data-id="${p.id}" tabindex="0" style="--k:${i}">
    <div class="card-top"><span class="src" style="--c:${src.c}">${src.label}</span>${badges.join("")}</div>
    <h3 title="${esc(nameOf(p))}">${esc(nameOf(p))}</h3>
    <div class="path" title="${esc(p.path)}"><bdi>${esc(tilde(p.path))}</bdi></div>
    <div class="size">${p.size == null ? `<b class="measuring">misst …</b>` : `<b>${bytes(p.size)}</b>`}<div class="bar"><i data-w="${pct}"></i></div></div>
    <div class="meta">${meta.map((m) => `<span>${esc(m)}</span>`).join("")}</div>
    <div class="progs">${a.length ? a.slice(0, 3).map((x) => `<span class="tag" title="${esc(x.name)}">${esc(x.name)}</span>`).join("") + (a.length > 3 ? `<span class="tag more">+${a.length - 3}</span>` : "")
      : `<span class="tag none">keine Programme eingetragen</span>`}</div>
  </article>`;
}

let lastGridKey = "";
let lastView = "";
function renderGrid() {
  const grid = $("#grid");
  if (!ui.loaded || (state.scanning && !state.prefixes.length)) {
    grid.innerHTML = Array.from({ length: 6 }, () => `<div class="skeleton"></div>`).join("");
    $("#empty").hidden = true;
    return;
  }
  const list = visible();
  const maxSize = Math.max(0, ...state.prefixes.map((p) => p.size || 0));
  // Nur neu aufbauen, wenn sich etwas geändert hat – sonst ruckeln Hover und Animationen bei jedem Abruf
  const key = JSON.stringify([ui.filter, ui.sort, ui.q, ui.open, list.map((p) => [p.id, p.size, p.running, p.label, p.hidden, p.lastUsed, p.refs.length])]);
  if (key !== lastGridKey) {
    const view = JSON.stringify([ui.filter, ui.sort, ui.q]);
    const fresh = view !== lastView; // Einflug-Animation nur bei neuer Ansicht, nicht bei jedem Abruf
    lastView = view;
    grid.innerHTML = list.map((p, i) => card(p, fresh ? i : 0, maxSize)).join("");
    if (!fresh) grid.querySelectorAll(".card").forEach((c) => (c.style.animation = "none"));
    requestAnimationFrame(() => grid.querySelectorAll(".bar i").forEach((b) => (b.style.width = b.dataset.w + "%")));
    lastGridKey = key;
  }
  const empty = $("#empty");
  empty.hidden = list.length > 0;
  empty.textContent = ui.q ? `Nichts gefunden für „${ui.q}“.` : "Hier ist nichts.";
}

// ---------- Detail ----------

function runnerOptions(p) {
  const r = state.runners;
  const auto = r.find((x) => x.id === p.runner);
  const group = (kind, title) => {
    const items = r.filter((x) => x.kind === kind);
    return items.length ? `<optgroup label="${title}">${items.map((x) => `<option value="${esc(x.id)}" ${p.runnerOverride === x.id ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</optgroup>` : "";
  };
  return `<option value="">Automatisch${auto && !p.runnerOverride ? ` – ${esc(auto.label)}` : ""}</option>${group("proton", "Proton")}${group("wine", "Wine")}`;
}

function renderSheet(force = false) {
  const sheet = $("#sheet");
  const p = byId(ui.open);
  if (!p) return closeSheet();
  if (!force && sheet.contains(document.activeElement) && document.activeElement !== sheet) {
    // Während getippt wird, nur die lebenden Werte auffrischen
    const s = sheet.querySelector("[data-live=size]");
    if (s) s.textContent = p.size == null ? "misst …" : bytes(p.size);
    return;
  }
  const src = SOURCES[p.source] || SOURCES.wine;
  const a = apps(p);
  const rt = p.programs.filter((x) => x.runtime);
  const runner = state.runners.find((x) => x.id === p.runner);
  const mismatch = runner && runner.kind !== p.kind;
  const children = (p.contains || []).map(byId).filter(Boolean);
  const parent = p.nestedIn && byId(p.nestedIn);
  const prog = (x) => `<div class="row"><div class="t">${esc(x.name)}${x.publisher ? `<small>${esc(x.publisher)}</small>` : ""}</div><div class="r">${esc(x.version)}</div></div>`;

  sheet.innerHTML = `
  <div class="sheet-inner">
    <div class="sheet-head">
      <div class="grow">
        <div class="card-top"><span class="src" style="--c:${src.c}">${src.label}</span>${p.running ? `<span class="badge live">läuft · ${p.running} Prozess${p.running > 1 ? "e" : ""}</span>` : ""}${orphan(p) ? `<span class="badge warn">${icon("unlink")}ohne Launcher</span>` : ""}</div>
        <input class="name-input" id="label" value="${esc(nameOf(p))}" placeholder="${esc(p.autoName)}" title="Eigenen Namen vergeben" spellcheck="false">
        <div class="pathline"><code>${esc(tilde(p.path))}</code><button class="btn mini" id="copy" title="Pfad kopieren">${icon("copy")}</button></div>
      </div>
      <button class="btn icon-btn" id="close" title="Schließen (Esc)">${icon("x")}</button>
    </div>

    <div class="section">
      <div class="actions">
        <button class="btn action primary" data-a="open">${icon("folder")}Ordner</button>
        <button class="btn action primary" data-a="run">${icon("play")}Programm starten</button>
        <button class="btn action primary" data-a="winecfg">${icon("sliders")}winecfg</button>
        <button class="btn action" data-a="winetricks">${icon("wrench")}winetricks</button>
        <button class="btn action" data-a="regedit">${icon("db")}Registry</button>
        <button class="btn action" data-a="uninstaller">${icon("package")}Deinstallieren</button>
      </div>
      ${p.running ? `<button class="btn" style="width:100%;margin-top:8px" data-a="kill">${icon("power")}Alle Wine-Prozesse in diesem Prefix beenden</button>` : ""}
    </div>

    <div class="section">
      <h4>Eckdaten</h4>
      <div class="facts">
        <div class="fact"><div class="k">Größe</div><div class="v" data-live="size">${p.size == null ? "misst …" : bytes(p.size)}</div></div>
        <div class="fact"><div class="k">Zuletzt benutzt</div><div class="v" title="${p.lastUsed ? new Date(p.lastUsed * 1000).toLocaleString("de-DE") : ""}">${esc(ago(p.lastUsed))}</div></div>
        <div class="fact"><div class="k">${p.kind === "proton" ? "Angelegt mit" : "Typ"}</div><div class="v">${esc(p.version || (p.kind === "proton" ? "Proton" : "Wine"))}</div></div>
        <div class="fact"><div class="k">Architektur</div><div class="v">${esc(p.arch || "?")}</div></div>
        <div class="fact wide"><div class="k">Runner für Aktionen</div>
          <select id="runner" ${DEMO ? "disabled" : ""}>${runnerOptions(p)}</select>
          ${!runner && !DEMO ? `<div class="note">Kein passender Runner gefunden – bitte einen wählen.</div>` : ""}
          ${mismatch ? `<div class="note">Achtung: ${p.kind === "proton" ? "Proton-Prefix mit Wine" : "Wine-Prefix mit Proton"} – das aktualisiert den Prefix auf diese Version.</div>` : ""}
        </div>
      </div>
    </div>

    <div class="section">
      <h4>Launcher <span>${p.refs.length || "–"}</span></h4>
      <div class="list">${p.refs.length ? p.refs.map((r) => `<div class="row"><div class="t">${esc(r.title)}${r.detail ? `<small>${esc(r.detail)}</small>` : ""}</div><div class="r">${esc(r.launcher)}</div></div>`).join("")
        : `<div class="row"><div class="t" style="color:var(--muted)">${p.isDefault ? "Standard-Prefix von Wine (~/.wine) – wird ohne Launcher benutzt." : "Kein Launcher kennt diesen Prefix. Vermutlich ein Überbleibsel – oder von Hand angelegt."}</div></div>`}
      ${parent ? `<div class="row link" data-go="${parent.id}"><div class="t">Liegt in „${esc(nameOf(parent))}“</div><div class="r">öffnen →</div></div>` : ""}
      ${children.map((c) => `<div class="row link" data-go="${c.id}"><div class="t">Enthält „${esc(nameOf(c))}“<small>zählt in die Größe mit hinein</small></div><div class="r">öffnen →</div></div>`).join("")}
      </div>
    </div>

    <div class="section">
      <h4>Installierte Programme <span>${a.length}</span></h4>
      <div class="list">
        ${a.length ? a.map(prog).join("") : `<div class="row"><div class="t" style="color:var(--muted)">Keine Programme in der Registry eingetragen. Portable Spiele tauchen hier nicht auf.</div></div>`}
        ${rt.length ? `<details class="runtime"><summary>${rt.length} Laufzeitbibliothek${rt.length > 1 ? "en" : ""}</summary>${rt.map(prog).join("")}</details>` : ""}
      </div>
    </div>

    ${p.winetricks.length ? `<div class="section"><h4>winetricks <span>${p.winetricks.length}</span></h4><div class="progs">${p.winetricks.map((v) => `<span class="tag">${esc(v)}</span>`).join("")}</div></div>` : ""}

    <div class="section">
      <h4>Notiz</h4>
      <textarea id="notes" placeholder="Wofür ist der Prefix, was ist kaputt, was ist wichtig …">${esc(p.notes)}</textarea>
      <label class="toggle"><input type="checkbox" id="hidden" ${p.hidden ? "checked" : ""}>${icon("eye-off")} In der Übersicht ausblenden</label>
    </div>

    <div class="danger-zone">
      <p>Verschiebt ${p.compatRoot && p.compatRoot !== p.path ? "den ganzen Ordner (inkl. Proton-Daten)" : "den Prefix"} in den Papierkorb – wiederherstellbar.</p>
      <button class="btn outline-danger" id="trash" ${p.running ? "disabled title='Läuft noch'" : ""}>${icon("trash")}Papierkorb</button>
    </div>
  </div>`;

  $("#close", sheet).onclick = closeSheet;
  $("#copy", sheet).onclick = () => navigator.clipboard.writeText(p.path).then(() => toast("Pfad kopiert."), () => toast(p.path));
  sheet.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => act(p, b.dataset.a, b)));
  sheet.querySelectorAll("[data-go]").forEach((r) => (r.onclick = () => openSheet(r.dataset.go)));
  const label = $("#label", sheet);
  label.onchange = () => saveMeta(p, { label: label.value.trim() === p.autoName ? "" : label.value.trim() });
  label.onkeydown = (e) => e.key === "Enter" && label.blur();
  $("#notes", sheet).onchange = (e) => saveMeta(p, { notes: e.target.value });
  $("#hidden", sheet).onchange = (e) => saveMeta(p, { hidden: e.target.checked });
  $("#runner", sheet).onchange = (e) => saveMeta(p, { runner: e.target.value }, true);
  $("#trash", sheet).onclick = () => confirmTrash(p);
}

function openSheet(id) {
  ui.open = id;
  renderSheet(true);
  $("#sheet").classList.add("open");
  $("#sheet").setAttribute("aria-hidden", "false");
  $("#sheet").scrollTop = 0;
  $("#scrim").hidden = false;
  renderGrid();
}
function closeSheet() {
  ui.open = null;
  $("#sheet").classList.remove("open");
  $("#sheet").setAttribute("aria-hidden", "true");
  $("#scrim").hidden = true;
  renderGrid();
}

// ---------- Aktionen ----------

async function act(p, action, btn) {
  if (DEMO) return toast("In der Demo geht das nicht – installier Cellarium, dann schon.");
  btn && (btn.disabled = true);
  try {
    const res = await api(`prefix/${p.id}/action`, { action });
    toast(res.message);
    setTimeout(load, 1500);
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn && (btn.disabled = false);
  }
}

async function saveMeta(p, changes, rerender = false) {
  if (DEMO) {
    Object.assign(p, changes.runner !== undefined ? { runnerOverride: changes.runner } : changes);
  } else {
    try {
      await api(`prefix/${p.id}/meta`, changes);
      await load();
    } catch (e) {
      return toast(e.message, true);
    }
  }
  if ("hidden" in changes) toast(changes.hidden ? "Ausgeblendet – zu finden unter „Ausgeblendet“." : "Wieder sichtbar.");
  lastGridKey = "";
  render();
  if (rerender) renderSheet(true);
}

function confirmTrash(p) {
  const dlg = $("#confirm");
  const target = (p.compatRoot || p.path).split("/").pop();
  const children = (p.contains || []).map(byId).filter(Boolean);
  $("#confirm-text").textContent = `${tilde(p.compatRoot || p.path)}${p.size ? ` (${bytes(p.size)})` : ""} wandert in den Papierkorb.` +
    (children.length ? ` Darin liegt auch: ${children.map(nameOf).join(", ")}.` : "") +
    (p.refs.length ? ` ${p.refs.map((r) => r.launcher).join(", ")} findet das Spiel danach nicht mehr.` : "");
  $("#confirm-name").textContent = target;
  const input = $("#confirm-input");
  const go = $("#confirm-go");
  input.value = "";
  go.disabled = true;
  input.oninput = () => (go.disabled = input.value.trim() !== target);
  dlg.onclose = async () => {
    if (dlg.returnValue !== "ok") return;
    if (DEMO) return toast("In der Demo wird nichts gelöscht.");
    try {
      const res = await api(`prefix/${p.id}/action`, { action: "trash", confirm: p.path });
      toast(res.message);
      closeSheet();
      await load();
    } catch (e) {
      toast(e.message, true);
    }
  };
  dlg.showModal();
  input.focus();
}

function toast(text, err = false) {
  const el = document.createElement("div");
  el.className = `toast glass ${err ? "err" : ""}`;
  el.textContent = text;
  $("#toasts").append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, err ? 5000 : 2800);
}

function setFilter(f) { ui.filter = ui.filter === f && f !== "all" ? "all" : f; render(); }
function setQuery(q) { ui.q = q; $("#q").value = q; render(); }

// ---------- Ereignisse ----------

$("#filters").addEventListener("click", (e) => { const b = e.target.closest("[data-f]"); if (b) setFilter(b.dataset.f); });
$("#grid").addEventListener("click", (e) => { const c = e.target.closest(".card"); if (c) openSheet(c.dataset.id); });
$("#grid").addEventListener("keydown", (e) => { const c = e.target.closest(".card"); if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openSheet(c.dataset.id); } });
$("#grid").addEventListener("pointermove", (e) => {
  const c = e.target.closest(".card");
  if (!c) return;
  const r = c.getBoundingClientRect();
  c.style.setProperty("--mx", `${e.clientX - r.left}px`);
  c.style.setProperty("--my", `${e.clientY - r.top}px`);
});
$("#q").addEventListener("input", (e) => { ui.q = e.target.value; renderGrid(); });
$("#sort").value = ui.sort;
$("#sort").addEventListener("change", (e) => { ui.sort = e.target.value; localSet("sort", ui.sort); renderGrid(); });
$("#scrim").addEventListener("click", closeSheet);
$("#rescan").addEventListener("click", async () => {
  if (DEMO) return toast("Die Demo hat nichts zu scannen.");
  try { await api("rescan", {}); state.scanning = true; render(); schedule(); } catch (e) { toast(e.message, true); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && ui.open && !$("#confirm").open) closeSheet();
  if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $("#q").focus(); }
});

const DEEP = new URLSearchParams(location.hash.slice(1)).get("p") || new URLSearchParams(location.search).get("p");
if (TOKEN) history.replaceState(null, "", location.pathname); // Token nicht in der Adresszeile stehen lassen
render();
if (LOCAL && !TOKEN) {
  ui.loaded = true;
  state.scanning = false;
  render();
  $("#empty").hidden = false;
  $("#empty").textContent = "Kein Zugangsschlüssel – bitte Cellarium über das Startmenü oder den Befehl „cellarium“ öffnen.";
} else {
  load().then(() => { if (DEEP && byId(DEEP)) openSheet(DEEP); schedule(); }, (e) => { toast(DEMO ? "Demo-Daten fehlen." : e.message, true); schedule(); });
}
