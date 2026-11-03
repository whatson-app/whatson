// Live TV: suggestion rows, a guide grid (desktop) or now/next list (phone), favorites.

import { $, $$, api, esc, fmtTime, fmtWhen, isPhone, openSheet, toast } from "./core.js";
import { airingCard, channelChips, row } from "./cards.js";

const VIEWS = [["guide", "Guide"], ["favorites", "Favorites"], ["sports", "Sports"], ["movie", "Movies"], ["episode", "Shows"]];
const PX_PER_MIN = 4;
let guideData = null;
let pendingJump = "";

export async function renderLive(el, sub = "guide") {
  if (!VIEWS.some(([k]) => k === sub)) sub = "guide";
  el.innerHTML = `
    <nav class="nav2">${VIEWS.map(([k, l]) => `<a href="#/live/${k}" class="chip ${k === sub ? "on" : ""}">${l}</a>`).join("")}</nav>
    <div id="live-foryou"></div>
    <div id="live-guide" class="guide-wrap"><p class="spinner">Loading the guide…</p></div>`;
  if (sub === "guide") loadForYou();
  await loadGuide(sub);
  if (pendingJump) { jumpTo(pendingJump); pendingJump = ""; }
}

/** A bare channel number typed in the search bar: jump to that row of the guide. */
export function goToChannel(vcn) {
  if (location.hash.startsWith("#/live") && $("#live-guide")) return jumpTo(vcn);
  pendingJump = vcn;
  location.hash = "#/live/guide";
}

async function loadForYou() {
  try {
    const s = await api("/api/suggest/live");
    const scroll = (items) => `<div class="hscroll">${items.map(airingCard).join("")}</div>`;
    $("#live-foryou").innerHTML =
      row(s.ai ? "On now, picked for you" : "On now for you", s.picks.length ? scroll(s.picks) : "", { badge: s.ai ? "AI" : "" });
  } catch { /* suggestions are optional */ }
}

async function loadGuide(view) {
  const hours = isPhone() ? 2 : 4;
  guideData = await api(`/api/guide?hours=${hours}&view=${view === "guide" ? "all" : view}`);
  const box = $("#live-guide");
  if (!guideData.channels.length) {
    box.innerHTML = view === "favorites"
      ? '<p class="empty">Star channels in the guide to pin them here.</p>' : '<p class="empty">Nothing in the guide for this view.</p>';
    return;
  }
  box.innerHTML = isPhone() ? listHtml(guideData) : gridHtml(guideData);
  if (!isPhone()) {
    const scroller = $(".guide", box);
    scroller.scrollLeft = Math.max(0, ((guideData.now - guideData.start) / 60) * PX_PER_MIN - 120);
  }
}

const star = (c) => `<button class="star ${c.fav ? "on" : ""}" data-fav="${esc(c.id)}" aria-pressed="${c.fav}" aria-label="${c.fav ? "Unfavorite" : "Favorite"} ${esc(c.title)}">${c.fav ? "★" : "☆"}</button>`;

function gridHtml(d) {
  const width = ((d.end - d.start) / 60) * PX_PER_MIN;
  const ticks = [];
  for (let t = d.start; t < d.end; t += 1800) ticks.push(`<span style="left:${((t - d.start) / 60) * PX_PER_MIN}px">${fmtTime(t)}</span>`);
  const nowX = ((d.now - d.start) / 60) * PX_PER_MIN;
  const rows = d.channels.map((c) => {
    const blocks = c.airings.map((a) => {
      const left = Math.max(0, ((a.begins - d.start) / 60) * PX_PER_MIN);
      const right = Math.min(width, ((a.ends - d.start) / 60) * PX_PER_MIN);
      const live = a.begins <= d.now && d.now < a.ends;
      const g = a.game;
      const label = g ? `${g.away} ${g.state !== "pre" ? g.away_score : ""} · ${g.home} ${g.state !== "pre" ? g.home_score : ""}` : a.title;
      return `<button class="block ${live ? "on-now" : ""} k-${esc(a.kind)}" style="left:${left}px;width:${Math.max(2, right - left - 2)}px"
        data-airing="${a.id}" title="${esc(a.title)}${a.subtitle ? " — " + esc(a.subtitle) : ""}">
        <span>${esc(label)}</span>${g && g.state === "in" ? `<small>${esc(g.detail)}</small>` : a.subtitle ? `<small>${esc(a.subtitle)}</small>` : ""}</button>`;
    }).join("");
    return `<div class="g-row" data-vcn="${esc(c.vcn)}">
      <div class="g-ch">${star(c)}<button class="g-tune" data-channel="${esc(c.vcn)}" title="Watch ${esc(c.title)}">
        ${c.thumb ? `<img src="${esc(c.thumb)}" alt="" loading="lazy" onerror="this.remove()">` : ""}<span>${esc(c.vcn)}</span><small>${esc(c.title)}</small></button></div>
      <div class="g-line" style="width:${width}px">${blocks || '<span class="g-empty">No listing</span>'}</div></div>`;
  }).join("");
  return `<div class="guide"><div class="g-head"><div class="g-ch"></div><div class="g-times" style="width:${width}px">${ticks.join("")}</div></div>
    <div class="g-body"><div class="g-nowline" style="left:calc(var(--chw) + ${nowX}px)"></div>${rows}</div></div>`;
}

function listHtml(d) {
  return `<div class="nn-list">${d.channels.map((c) => {
    const cur = c.airings.find((a) => a.begins <= d.now && d.now < a.ends);
    const next = c.airings.find((a) => a.begins >= (cur ? cur.ends : d.now));
    const g = cur?.game;
    return `<div class="nn-row" data-vcn="${esc(c.vcn)}">
      ${star(c)}
      <button class="nn-main" ${cur ? `data-airing="${cur.id}"` : ""}>
        <span class="nn-ch">${c.thumb ? `<img src="${esc(c.thumb)}" alt="" loading="lazy" onerror="this.remove()">` : ""}${esc(c.vcn)}</span>
        <span class="nn-text"><span class="nn-title">${esc(g ? `${g.away} ${g.away_score} · ${g.home} ${g.home_score}` : cur?.title || "No listing")}</span>
        <small>${next ? `Next ${fmtTime(next.begins)} ${esc(next.title)}` : esc(c.title)}</small></span>
      </button>
      <button class="icon-btn" data-channel="${esc(c.vcn)}" aria-label="Watch ${esc(c.title)}">▶</button>
    </div>`;
  }).join("")}</div>`;
}

function jumpTo(vcn) {
  const target = $(`[data-vcn="${CSS.escape(vcn)}"]`);
  if (!target) return toast(`Channel ${vcn} isn't in this view.`);
  target.scrollIntoView({ block: "center", behavior: "smooth" });
  target.classList.add("flash");
  setTimeout(() => target.classList.remove("flash"), 1600);
}

export async function showAiring(id) {
  const a = await api(`/api/airing/${id}`);
  openSheet(`
    <div class="meta">${fmtWhen(a.begins, a.ends)} · ${esc(a.channel.vcn)} ${esc(a.channel.title)}</div>
    <h2 class="sheet-title">${esc(a.title)}</h2>
    ${a.subtitle ? `<div class="sub">${esc(a.subtitle)}</div>` : ""}
    ${a.summary ? `<p>${esc(a.summary)}</p>` : ""}
    <div class="chips">${channelChips([a.channel])}</div>
    ${a.also.length ? `<h3>Also on</h3><ul class="also">${a.also.map((x) => `<li>${fmtWhen(x.begins, x.ends)} · ${esc(x.vcn)} ${esc(x.ch)}</li>`).join("")}</ul>` : ""}`);
}

export async function toggleFav(btn) {
  const id = btn.dataset.fav;
  const on = !btn.classList.contains("on");
  try {
    await api(`/api/favorites/channels/${encodeURIComponent(id)}`, { method: on ? "POST" : "DELETE" });
    $$(`[data-fav="${CSS.escape(id)}"]`).forEach((b) => {
      b.classList.toggle("on", on); b.textContent = on ? "★" : "☆"; b.setAttribute("aria-pressed", String(on));
    });
  } catch (e) { toast(e.message); }
}
