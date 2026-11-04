// Card renderers shared by the sections. Buttons carry data-* attributes that main.js wires up:
// data-channel (tune a channel), data-rating-key (play from the library), data-recap (catch me up),
// data-airing (programme details), data-show (open a show page), data-movie (movie details).

import { esc, fmtMins, fmtTime, fmtWhen, thumbUrl } from "./core.js";

export function channelChips(channels, max = 3) {
  return channels.slice(0, max).map((c, i) => `
    <button class="chip ${i === 0 ? "primary-chip" : ""}" data-channel="${esc(c.vcn)}" title="Watch on ${esc(c.title)}">
      ${c.thumb ? `<img src="${esc(c.thumb)}" alt="" loading="lazy" onerror="this.remove()">` : ""}▶ ${esc(c.vcn)} ${esc(c.title)}
    </button>`).join("");
}

const teamLine = (name, logo, score, show) => `
  <span class="team">${logo ? `<img src="${esc(logo)}" alt="" loading="lazy" onerror="this.remove()">` : ""}${esc(name)}</span>
  <b>${show ? esc(score) : ""}</b>`;

export function gameCard(g, { reason = "", highlight = false } = {}) {
  const started = g.state !== "pre";
  const when = g.state === "pre" ? fmtWhen(g.starts, 0) : esc(g.detail);
  return `
    <article class="card game ${highlight ? "highlight" : ""}">
      <div class="meta">${g.state === "in" ? '<span class="live">LIVE</span>' : ""}<span>${esc(g.league || "")}</span>
        <span>${when}</span>${!g.channels?.length && g.state !== "post" && g.networks?.length ? `<span>${esc(g.networks.join(", "))}</span>` : ""}</div>
      <div class="score">${teamLine(g.away, g.away_logo, g.away_score, started)}${teamLine(g.home, g.home_logo, g.home_score, started)}</div>
      ${reason ? `<div class="why">${esc(reason)}</div>` : ""}
      <div class="chips">${channelChips(g.channels || [])}
        ${g.state === "in" ? `<button class="chip" data-recap="${esc(g.id)}">Catch me up</button>` : ""}</div>
      <div class="recap" hidden></div>
    </article>`;
}

export function airingCard(a) {
  const ch = a.channel ? [a.channel] : a.channels || [];
  return `
    <article class="card">
      <div class="meta">${fmtWhen(a.begins, a.ends)}${a.game ? `<span>${esc(a.game.league || "")} ${esc(a.game.detail)}</span>` : ""}</div>
      <div class="title">${esc(a.game ? `${a.game.away} at ${a.game.home}` : a.title)}</div>
      ${a.subtitle ? `<div class="sub">${esc(a.subtitle)}</div>` : ""}
      ${a.reason ? `<div class="why ${a.ai ? "ai" : ""}">${a.ai ? "✦ " : ""}${esc(a.reason)}</div>` : ""}
      ${a.summary && !a.reason ? `<div class="summary">${esc(a.summary)}</div>` : ""}
      <div class="chips">${channelChips(ch)}</div>
    </article>`;
}

export function posterCard(it, { label = "", reason = "" } = {}) {
  const open = it.kind === "show" ? `data-show="${esc(it.rating_key)}"` : `data-movie="${esc(it.rating_key)}"`;
  const progress = it.kind === "show" && it.leaf_count ? Math.round((it.viewed_leaf_count / it.leaf_count) * 100) : 0;
  const meta = label || [it.year, it.kind === "movie" && it.duration ? fmtMins(it.duration) : "",
    it.kind === "show" && it.leaf_count ? `${it.leaf_count} episodes` : ""].filter(Boolean).join(" · ");
  return `
    <article class="poster">
      <button class="poster-open" ${open} aria-label="${esc(it.title)}">
        ${it.thumb ? `<img src="${thumbUrl(it.thumb)}" alt="" loading="lazy">` : '<span class="ph"></span>'}
        ${it.watched ? '<span class="tick" aria-label="Watched">✓</span>' : ""}
        ${progress && progress < 100 ? `<span class="pbar"><span style="width:${progress}%"></span></span>` : ""}
      </button>
      <div class="p-body">
        <div class="p-title">${esc(it.title)}</div>
        <div class="p-meta">${esc(meta)}</div>
        ${reason ? `<div class="why ${it.ai ? "ai" : ""}">${it.ai ? "✦ " : ""}${esc(reason)}</div>` : ""}
      </div>
    </article>`;
}

export function libNav(active) {
  const link = (k, label) => `<a href="#/library/${k}" class="chip ${active === k ? "on" : ""}">${label}</a>`;
  return `<nav class="nav2">${link("movie", "Movies")}${link("show", "TV shows")}${link("downloads", "Downloads")}</nav>`;
}

export function row(title, inner, { badge = "" } = {}) {
  return inner ? `<section class="row-section"><h2>${esc(title)}${badge ? ` <span class="badge">${esc(badge)}</span>` : ""}</h2>${inner}</section>` : "";
}

export const timeLabel = (ts) => fmtTime(ts);
