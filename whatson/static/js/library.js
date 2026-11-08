// Library: Movies / TV shows poster grids with sort and genres; show pages with seasons;
// suggestion rows (up next, tonight's pick, watchlist titles you don't own).

import { $, ai, aiPlaceholder, api, esc, fmtMins, openSheet, store, thumbUrl, toast } from "./core.js";
import { libNav, posterCard, row } from "./cards.js";
import { deviceParam } from "./player.js";

const hiddenNote = (m) => m.hidden_from ? `<p class="hint">Plex hides this from ${esc(m.hidden_from)}, so it may not play on this TV.</p>` : "";

const PAGE = 60;
let listState = null;
let observer = null;

export async function renderLibrary(el, kind = "movie") {
  if (kind !== "movie" && kind !== "show") kind = "movie";
  const sort = store.get(`lib-sort-${kind}`) || "added";
  el.innerHTML = `
    ${libNav(kind)}
    <div id="lib-foryou"></div>
    <div id="lib-browse">
      <div class="lib-tools">
        <select id="lib-sort" aria-label="Sort">
          <option value="added">Recently added</option><option value="title">A–Z</option>
          <option value="year">Newest</option><option value="rating">Top rated</option>
        </select>
        <label class="toggle"><input type="checkbox" id="lib-unwatched"> Unwatched</label>
      </div>
      <div id="lib-genres" class="nav2 genres"></div>
      <p id="lib-count" class="hint"></p>
      <div id="lib-grid" class="posters"></div>
      <div id="lib-more" class="spinner"></div>
    </div>`;
  $("#lib-sort").value = sort;
  listState = { kind, sort, genre: "", unwatched: false, offset: 0, total: 0, loading: false };
  $("#lib-sort").addEventListener("change", (ev) => { store.set(`lib-sort-${kind}`, ev.target.value); reset({ sort: ev.target.value }); });
  $("#lib-unwatched").addEventListener("change", (ev) => reset({ unwatched: ev.target.checked }));
  $("#lib-genres").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-genre]");
    if (!b) return;
    $("#lib-genres").querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c === b));
    reset({ genre: b.dataset.genre });
  });
  loadForYou(kind);
  api(`/api/library/genres?kind=${kind}`).then((gs) => {
    $("#lib-genres").innerHTML = `<button class="chip on" data-genre="">All</button>` +
      gs.slice(0, 14).map((g) => `<button class="chip" data-genre="${esc(g.name)}">${esc(g.name)}</button>`).join("");
  });
  observer?.disconnect();
  observer = new IntersectionObserver((entries) => { if (entries[0].isIntersecting) loadPage(); }, { rootMargin: "600px" });
  observer.observe($("#lib-more"));
  await loadPage();
}

function reset(changes) {
  Object.assign(listState, changes, { offset: 0, total: 0 });
  $("#lib-grid").innerHTML = "";
  loadPage();
}

async function loadPage() {
  const s = listState;
  if (!s || s.loading || (s.total && s.offset >= s.total)) return;
  s.loading = true;
  $("#lib-more").textContent = "Loading…";
  try {
    const q = new URLSearchParams({ kind: s.kind, sort: s.sort, genre: s.genre, unwatched: s.unwatched, offset: s.offset, limit: PAGE });
    const r = await api(`/api/library?${q}&${deviceParam()}`);
    s.total = r.total;
    s.offset += r.items.length;
    $("#lib-grid").insertAdjacentHTML("beforeend", r.items.map((it) => posterCard(it)).join(""));
    $("#lib-count").textContent = `${r.total.toLocaleString()} ${s.kind === "movie" ? "movies" : "shows"}`;
    $("#lib-more").textContent = s.offset >= s.total ? "" : " ";
  } catch (e) {
    $("#lib-more").textContent = e.message;
  } finally {
    s.loading = false;
  }
}

async function loadForYou(kind) {
  if (ai.on) $("#lib-foryou").innerHTML = aiPlaceholder("AI is picking what to watch…", "posters");
  try {
    const s = await api(`/api/suggest/library?${deviceParam()}`);
    const upNext = s.up_next.filter((u) => kind === "show" ? u.kind === "show" : u.kind === "movie" || s.up_next_source !== "trakt");
    const scroll = (items) => `<div class="hscroll">${items.map((it) => posterCard(
      { ...it, rating_key: it.rating_key }, { label: it.label, reason: it.ai ? it.reason : "" })).join("")}</div>`;
    let html = row("Up next", upNext.length ? scroll(upNext) : "", { badge: s.up_next_source === "trakt" ? "Trakt" : s.source_label });
    if (kind === "movie" && s.picks.length) {
      const [top, ...rest] = s.picks;
      html += row(s.ai ? "Tonight's pick" : "Worth a watch", `
        <div class="pick">
          <button class="poster-open" data-movie="${esc(top.rating_key)}">${top.thumb ? `<img src="${thumbUrl(top.thumb, 240)}" alt="">` : ""}</button>
          <div><div class="title">${esc(top.title)}</div><div class="meta">${esc([top.year, fmtMins(top.duration)].filter(Boolean).join(" · "))}</div>
            <div class="why ${top.ai ? "ai" : ""}">${top.ai ? "✦ " : ""}${esc(top.reason)}</div>
            <div class="chips"><button class="chip primary-chip" data-rating-key="${esc(top.rating_key)}">▶ Play</button></div></div>
        </div>${rest.length ? scroll(rest) : ""}`, { badge: s.ai ? "AI" : "" });
    }
    // Watchlist titles you don't own, with "Get it" when Radarr or Sonarr is connected for that kind.
    const missing = s.missing.filter((m) => m.kind === kind);
    if (missing.length) {
      html += row("On your watchlist, not in your library", `<ul class="missing">${missing.map((m) => `
        <li><span>${esc(m.title)}${m.year ? ` (${m.year})` : ""}</span>${getButton(m, s)}</li>`).join("")}</ul>`,
      { badge: "Trakt" });
    }
    $("#lib-foryou").innerHTML = html;
  } catch {  // optional
    const box = $("#lib-foryou");
    if (box) box.innerHTML = "";
  }
}

export async function showMovie(rk) {
  const m = await api(`/api/library/item/${encodeURIComponent(rk)}?${deviceParam()}`);
  openSheet(`
    <div class="detail">
      ${m.thumb ? `<img class="detail-poster" src="${thumbUrl(m.thumb, 300)}" alt="">` : ""}
      <div>
        <h2 class="sheet-title">${esc(m.title)}</h2>
        <div class="meta">${esc([m.year, fmtMins(m.duration), m.content_rating, m.audience_rating ? `★ ${m.audience_rating}` : ""].filter(Boolean).join(" · "))}</div>
        <div class="chips"><button class="chip primary-chip" data-rating-key="${esc(m.rating_key)}">▶ ${m.view_offset ? "Resume" : "Play"} on TV</button>
          ${m.watched ? '<span class="badge">Watched</span>' : ""}</div>
        ${hiddenNote(m)}
        ${m.summary ? `<p>${esc(m.summary)}</p>` : ""}
        ${m.genres.length ? `<p class="hint">${esc(m.genres.join(", "))}</p>` : ""}
        ${m.cast.length ? `<p class="hint">With ${esc(m.cast.join(", "))}</p>` : ""}
      </div>
    </div>`);
}

export async function renderShow(el, rk) {
  el.innerHTML = '<p class="spinner">Loading…</p>';
  const s = await api(`/api/library/item/${encodeURIComponent(rk)}?${deviceParam()}`);
  el.innerHTML = `
    <a class="back-link" href="#/library/show">← TV shows</a>
    <div class="detail show-head">
      ${s.thumb ? `<img class="detail-poster" src="${thumbUrl(s.thumb, 300)}" alt="">` : ""}
      <div>
        <h1 class="sheet-title">${esc(s.title)}</h1>
        <div class="meta">${esc([s.year, `${s.seasons?.length || 0} seasons`, s.content_rating, s.genres.slice(0, 3).join(", ")].filter(Boolean).join(" · "))}</div>
        <div class="chips"><button class="chip primary-chip" data-rating-key="${esc(s.rating_key)}">▶ Play next episode</button></div>
        ${hiddenNote(s)}
        ${s.summary ? `<p class="summary-full">${esc(s.summary)}</p>` : ""}
      </div>
    </div>
    <nav class="nav2" id="seasons">${(s.seasons || []).map((x) => `<button class="chip" data-season="${esc(x.rating_key)}">${esc(x.title)}<small> ${x.watched}/${x.episodes}</small></button>`).join("")}</nav>
    <div id="episodes"></div>`;
  const seasons = s.seasons || [];
  const first = seasons.find((x) => x.watched < x.episodes) || seasons[0];
  $("#seasons").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-season]");
    if (b) loadSeason(b.dataset.season);
  });
  if (first) loadSeason(first.rating_key);
}

async function loadSeason(rk) {
  document.querySelectorAll("#seasons .chip").forEach((c) => c.classList.toggle("on", c.dataset.season === rk));
  const box = $("#episodes");
  box.innerHTML = '<p class="spinner">Loading episodes…</p>';
  try {
    const eps = await api(`/api/library/season/${encodeURIComponent(rk)}?${deviceParam()}`);
    box.innerHTML = `<ol class="episodes">${eps.map((e) => `
      <li class="${e.watched ? "watched" : ""}">
        ${e.thumb ? `<img src="${thumbUrl(e.thumb, 200)}" alt="" loading="lazy">` : '<span class="ph"></span>'}
        <div class="ep-text"><div class="title">${esc(e.index)}. ${esc(e.title)} ${e.watched ? '<span class="tick-inline" aria-label="Watched">✓</span>' : ""}</div>
          <div class="meta">${esc([fmtMins(e.duration), e.aired].filter(Boolean).join(" · "))}</div>
          ${e.summary ? `<div class="summary">${esc(e.summary)}</div>` : ""}</div>
        <button class="icon-btn" data-rating-key="${esc(e.rating_key)}" aria-label="Play episode ${esc(e.index)}">▶</button>
      </li>`).join("")}</ol>`;
  } catch (e) {
    box.innerHTML = `<p class="msg err">${esc(e.message)}</p>`;
    toast(e.message);
  }
}

function getButton(m, s) {
  const id = m.kind === "movie" ? m.tmdb : m.tvdb;
  return s.get?.[m.kind] && id ? `<button class="chip" data-get="${esc(m.kind)}:${esc(id)}">Get it</button>` : "";
}
