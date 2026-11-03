// Getting titles you don't have: the "Get it" row under library searches, the Add sheet, the
// Downloads view (#/library/downloads) and the Downloads tab in Settings (Radarr and Sonarr).
// Buttons carry data-get="movie:<tmdb id>" or "show:<tvdb id>"; main.js opens the sheet.

import { $, api, esc, openSheet, toast } from "./core.js";
import { libNav, row } from "./cards.js";

const APP = { movie: "Radarr", show: "Sonarr" };
const MONITOR = {
  all: "All episodes", future: "New episodes only", missing: "Missing episodes", existing: "Episodes already out",
  firstSeason: "First season", lastSeason: "Latest season", pilot: "Pilot only",
};
const AVAILABILITY = { announced: "As soon as it's announced", inCinemas: "When it's in cinemas", released: "When it's out on digital or disc" };

const pct = (p) => `${Math.round((p || 0) * 100)}%`;

function stateLabel(c) {
  return {
    in_plex: "In your library", downloading: `Downloading ${pct(c.progress)}`, importing: "Importing",
    imported: "Downloaded", not_released: "Not out yet", missing: "Wanted",
  }[c.state] || "";
}

function stateLine(c) {
  const app = APP[c.kind];
  return {
    in_plex: "In your library.",
    not_added: `Not in ${app} yet.`,
    downloading: `Downloading: ${pct(c.progress)}${c.timeleft && c.timeleft !== "00:00:00" ? `, ${c.timeleft} left` : ""}${c.queued_episodes > 1 ? ` (${c.queued_episodes} episodes)` : ""}.`,
    importing: c.warning ? `Downloaded, but ${app} hasn't imported it.` : `Downloaded; ${app} is moving it into place.`,
    imported: "Downloaded. It shows up here once your server scans it.",
    not_released: `Not out yet. ${app} grabs it when it's released.`,
    missing: `In ${app}, but nothing has been downloaded yet.`,
  }[c.state] || "";
}

const meta = (c) => [c.year, c.rating ? `★ ${c.rating}` : "", c.kind === "show" && c.seasons ? `${c.seasons} season${c.seasons > 1 ? "s" : ""}` : "",
  c.network].filter(Boolean).join(" · ");

export function getCard(c) {
  const label = stateLabel(c);
  return `
    <article class="poster get">
      <button class="poster-open" data-get="${esc(c.kind)}:${esc(c.id)}" aria-label="${esc(c.title)}">
        ${c.poster ? `<img src="${esc(c.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph'}))">` : '<span class="ph"></span>'}
        ${label ? `<span class="get-badge ${esc(c.state)}">${esc(label)}</span>` : ""}
        ${c.state === "downloading" ? `<span class="pbar"><span style="width:${pct(c.progress)}"></span></span>` : ""}
      </button>
      <div class="p-body"><div class="p-title">${esc(c.title)}</div><div class="p-meta">${esc(meta(c))}</div></div>
    </article>`;
}

// The row under library search results: titles from Radarr/Sonarr that aren't in Plex yet.
export async function getRow(box, text, kind, title = "Get it") {
  box.innerHTML = "";
  if (!text || text.length < 2) return;
  let r;
  try { r = await api(`/api/get/lookup?q=${encodeURIComponent(text)}&kind=${kind}`); } catch { return; }
  if (!r.configured[kind]) return;
  if (r.errors[kind]) { box.innerHTML = `<p class="hint">${esc(r.errors[kind])}</p>`; return; }
  const items = r[kind].filter((c) => c.state !== "in_plex");
  if (!items.length) return;
  box.innerHTML = row(title, `<div class="hscroll">${items.map(getCard).join("")}</div>`, { badge: APP[kind] });
}

// --- The sheet for one title ---------------------------------------------------------------------

export async function showGet(kind, id) {
  const body = openSheet('<p class="spinner">Loading…</p>');
  let d;
  try {
    d = await api(`/api/get/item?kind=${encodeURIComponent(kind)}&id=${encodeURIComponent(id)}`);
  } catch (e) {
    body.innerHTML = `<p class="msg err">${esc(e.message)}</p>`;
    return;
  }
  const c = d.item;
  const open = c.kind === "show" ? `data-show="${esc(c.rating_key)}"` : `data-rating-key="${esc(c.rating_key)}"`;
  let actions = "";
  if (c.state === "in_plex") actions = `<div class="chips"><button class="chip primary-chip" ${open}>${c.kind === "show" ? "Open show" : "▶ Play on TV"}</button></div>`;
  else if (c.state === "not_added" && d.allow_add) actions = addForm(d);
  else if (c.state === "not_added") actions = '<p class="hint">Adding is turned off in Settings → Downloads.</p>';
  else if (c.state === "missing" && d.allow_add) actions = `<div class="chips"><button class="chip primary-chip" id="get-search">Search now</button></div>`;
  else if (c.state === "downloading") actions = `<div class="meter"><span style="width:${pct(c.progress)}"></span></div>`;
  body.innerHTML = `
    <div class="detail">
      ${c.poster ? `<img class="detail-poster" src="${esc(c.poster)}" alt="" referrerpolicy="no-referrer">` : '<span class="detail-poster ph"></span>'}
      <div>
        <h2 class="sheet-title">${esc(c.title)}</h2>
        <div class="meta">${esc(meta(c))}</div>
        <p class="state-line">${esc(stateLine(c))}${c.warning ? ` <span class="msg err">${esc(c.warning)}</span>` : ""}</p>
        ${actions}
        ${c.overview ? `<p>${esc(c.overview)}</p>` : ""}
        ${c.genres?.length ? `<p class="hint">${esc(c.genres.join(", "))}</p>` : ""}
      </div>
    </div>`;
  const form = $("#get-add", body);
  if (form) wireAddForm(form, d);
  $("#get-search", body)?.addEventListener("click", async (ev) => {
    ev.target.disabled = true;
    try { toast((await api("/api/get/search", { method: "POST", body: { kind: c.kind, arr_id: c.arr_id } })).message); }
    catch (e) { toast(e.message); ev.target.disabled = false; }
  });
}

// <option>s; folders are chosen by path (what Radarr/Sonarr take), profiles and tags by id.
const options = (list, selected, label = (x) => x.name, value = (x) => x.id) =>
  list.map((x) => `<option value="${esc(value(x))}" ${String(value(x)) === String(selected) ? "selected" : ""}>${esc(label(x))}</option>`).join("");
const byPath = (x) => x.path;

function addForm(d) {
  const c = d.item;
  const def = d.defaults[c.anime ? "anime" : "normal"];
  return `
    <form id="get-add" class="stack add-form">
      <div class="row wrap">
        <label>Quality <select name="profile">${options(d.options.profiles, def.profile)}</select></label>
        <label>Folder <select name="root">${options(d.options.roots, def.root, byPath, byPath)}</select></label>
        ${c.kind === "show" ? `<label>Get <select name="monitor">${Object.entries(MONITOR).map(([k, v]) =>
          `<option value="${k}" ${k === d.monitor ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>` : ""}
      </div>
      <div class="row wrap">
        <label class="toggle"><input type="checkbox" name="anime" ${c.anime ? "checked" : ""}> Anime</label>
        <label class="toggle"><input type="checkbox" name="search" checked> Start searching now</label>
      </div>
      <div class="row"><button type="submit" class="primary">Add to ${esc(d.label)}</button></div>
    </form>`;
}

function wireAddForm(form, d) {
  const c = d.item;
  form.anime.addEventListener("change", () => {
    const def = d.defaults[form.anime.checked ? "anime" : "normal"];
    form.profile.value = def.profile;
    form.root.value = def.root;
  });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    btn.textContent = "Adding…";
    try {
      await api("/api/get/add", { method: "POST", body: {
        kind: c.kind, id: c.id, anime: form.anime.checked, root: form.root.value, profile: Number(form.profile.value),
        monitor: form.monitor?.value || "", search: form.search.checked } });
      toast(`Added to ${d.label}.${form.search.checked ? " Searching for it now." : ""}`);
      showGet(c.kind, c.id);
    } catch (e) {
      toast(e.message);
      btn.disabled = false;
      btn.textContent = `Add to ${d.label}`;
    }
  });
}

// --- The Downloads view ----------------------------------------------------------------------------

let timer = null;
export const stopDownloads = () => { clearInterval(timer); timer = null; };

export async function renderDownloads(el) {
  el.innerHTML = `${libNav("downloads")}<div id="dl-list"><p class="spinner">Loading…</p></div>`;
  const draw = async () => {
    const box = $("#dl-list");
    if (!box) return stopDownloads();
    try {
      const r = await api("/api/get/downloads");
      if (!r.configured.movie && !r.configured.show) {
        box.innerHTML = '<p class="empty">Connect Radarr or Sonarr in <button class="link-btn" data-settings="downloads">Settings → Downloads</button> to add movies and shows.</p>';
        return;
      }
      const errs = Object.entries(r.errors).map(([k, m]) => `<p class="msg err">${esc(APP[k])}: ${esc(m)}</p>`).join("");
      box.innerHTML = errs + (r.items.length ? `<ul class="dl-list">${r.items.map(dlRow).join("")}</ul>`
        : '<p class="empty">Nothing downloading, and nothing added from WhatsOn in the last 30 days.</p>');
    } catch (e) {
      box.innerHTML = `<p class="msg err">${esc(e.message)}</p>`;
    }
  };
  stopDownloads();
  await draw();
  timer = setInterval(draw, 15000);
}

function dlRow(c) {
  return `
    <li>
      <button class="dl-open" data-get="${esc(c.kind)}:${esc(c.id)}">
        ${c.poster ? `<img src="${esc(c.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}
        <span class="dl-text">
          <span class="title">${esc(c.title)}${c.year && !c.title.endsWith(`(${c.year})`) ? ` <span class="hint">(${esc(c.year)})</span>` : ""}</span>
          <span class="hint">${esc(stateLine(c))}${c.episode_labels?.length ? ` ${esc(c.episode_labels.join(", "))}` : ""}</span>
          ${c.state === "downloading" ? `<span class="meter"><span style="width:${pct(c.progress)}"></span></span>` : ""}
          ${c.warning ? `<span class="msg err">${esc(c.warning)}</span>` : ""}
        </span>
        ${c.added_here ? '<span class="badge">Added here</span>' : ""}
      </button>
    </li>`;
}

// --- Settings → Downloads ----------------------------------------------------------------------------

let dlState = null;

export async function loadDownloadsSettings() {
  dlState = await api("/api/settings/downloads");
  $("#dl-allow").checked = dlState.allow_add;
  for (const kind of ["movie", "show"]) {
    const s = dlState[kind];
    const box = $(`#dl-${kind}`);
    box.innerHTML = `
      <form class="stack card dl-form" data-kind="${kind}">
        <h3>${APP[kind]} <span class="hint">(${kind === "movie" ? "movies" : "TV shows"})</span>
          <span class="hint" data-status>${s.configured ? "· connected" : ""}</span></h3>
        <label>Address <input name="url" value="${esc(s.url)}" autocomplete="off"
          placeholder="${kind === "movie" ? "http://192.168.1.10:7878" : "http://192.168.1.10:8989"}"></label>
        <label>API key <span class="hint">${s.key.set ? `(saved ${esc(s.key.hint)}${s.key.source === "env" ? ", from the environment" : ""})` : `(in ${APP[kind]}: Settings → General)`}</span>
          <input name="key" type="password" autocomplete="off" placeholder="Paste a key to save or replace it"></label>
        <div class="row"><button type="button" data-test>Test and load options</button><span class="hint" data-result></span></div>
        <div class="stack" data-opts hidden>
          <div class="row wrap">
            <label>Folder <select name="root"></select></label>
            <label>Quality <select name="profile"></select></label>
            ${kind === "show"
              ? `<label>Get <select name="monitor">${Object.entries(MONITOR).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>`
              : `<label>Grab it <select name="min_availability">${Object.entries(AVAILABILITY).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>`}
          </div>
          <details><summary>Anime</summary>
            <p class="hint">Used when a title is anime (Japanese animation). You can switch it per title when adding.</p>
            <div class="row wrap">
              <label>Folder <select name="anime_root"></select></label>
              <label>Quality <select name="anime_profile"></select></label>
              <label>Tag <select name="anime_tag"></select></label>
            </div>
          </details>
        </div>
        <div class="row">
          ${s.key.source === "saved" ? '<button type="button" class="link-btn" data-clear>Remove saved key</button>' : "<span></span>"}
          <button type="submit" class="primary">Save</button>
        </div>
      </form>`;
    const form = $("form", box);
    if (kind === "show") form.monitor.value = s.monitor;
    else form.min_availability.value = s.min_availability;
    if (s.configured) testArr(form, true);
  }
}

async function testArr(form, quiet = false) {
  const kind = form.dataset.kind;
  const out = $("[data-result]", form);
  out.textContent = quiet ? "" : "Checking…";
  try {
    const r = await api(`/api/settings/downloads/${kind}/test`, { method: "POST", body: { url: form.url.value, key: form.key.value } });
    out.textContent = `✓ ${APP[kind]} ${r.version}`;
    fillOptions(form, r);
  } catch (e) {
    out.textContent = `✗ ${e.message}`;
  }
}

function fillOptions(form, r) {
  const s = dlState[form.dataset.kind];
  const o = r.options;
  const anime = { ...s };
  // Unset anime defaults take the app's own folder/profile/tag named "anime", if it has them.
  if (!s.anime_root && !s.anime_profile && !s.anime_tags.length) Object.assign(anime, r.suggested);
  const free = (x) => (x.free ? ` (${(x.free / 2 ** 40).toFixed(1)} TB free)` : "");
  form.root.innerHTML = options(o.roots, s.root || o.roots[0]?.path, (x) => x.path + free(x), byPath);
  form.profile.innerHTML = options(o.profiles, s.profile || o.profiles[0]?.id);
  form.anime_root.innerHTML = '<option value="">Same as above</option>' + options(o.roots, anime.anime_root, byPath, byPath);
  form.anime_profile.innerHTML = '<option value="0">Same as above</option>' + options(o.profiles, anime.anime_profile);
  form.anime_tag.innerHTML = '<option value="">No tag</option>' + options(o.tags, anime.anime_tags[0] ?? "", (t) => t.label);
  $("[data-opts]", form).hidden = false;
}

async function saveArr(form, extra = {}) {
  const kind = form.dataset.kind;
  const s = dlState[kind];
  const loaded = !$("[data-opts]", form).hidden;
  const body = {
    url: form.url.value, key: form.key.value,
    root: loaded ? form.root.value : s.root, profile: Number(loaded ? form.profile.value : s.profile),
    anime_root: loaded ? form.anime_root.value : s.anime_root,
    anime_profile: Number(loaded ? form.anime_profile.value : s.anime_profile),
    anime_tags: loaded ? (form.anime_tag.value ? [Number(form.anime_tag.value)] : []) : s.anime_tags,
    monitor: form.monitor?.value || s.monitor || "all",
    min_availability: form.min_availability?.value || s.min_availability || "released",
    ...extra,
  };
  const saved = await api(`/api/settings/downloads/${kind}`, { method: "PUT", body });
  toast(saved.configured ? `${APP[kind]} saved.` : `Saved. ${APP[kind]} needs an address and a key.`);
  await loadDownloadsSettings();
}

export function initDownloadsSettings() {
  $("#dl-allow").addEventListener("change", async (ev) => {
    try { await api("/api/settings/downloads", { method: "PUT", body: { allow_add: ev.target.checked } }); }
    catch (e) { toast(e.message); ev.target.checked = !ev.target.checked; }
  });
  const panel = $('[data-panel="downloads"]');
  panel.addEventListener("click", (ev) => {
    const form = ev.target.closest("form.dl-form");
    if (!form) return;
    if (ev.target.closest("[data-test]")) testArr(form);
    if (ev.target.closest("[data-clear]")) saveArr(form, { clear_key: true, key: "" }).catch((e) => toast(e.message));
  });
  panel.addEventListener("submit", (ev) => {
    ev.preventDefault();
    saveArr(ev.target).catch((e) => toast(e.message));
  });
}

