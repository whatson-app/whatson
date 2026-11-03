// Sports: your teams and leagues pinned on top with live scores, close games worth switching to,
// everything else folded below; a page per followed league; "Catch me up" recaps.

import { $, api, esc, fmtWhen } from "./core.js";
import { gameCard, row } from "./cards.js";

let timer = null;
const leagueSlug = (lg) => lg.replace(/\//g, "~");
const slugLeague = (s) => s.replace(/~/g, "/");

export async function renderSports(el, sub = "") {
  clearTimeout(timer);
  const follows = await api("/api/sports/foryou").catch(() => null);
  const leagues = follows?.followed_leagues || [];
  el.innerHTML = `
    <nav class="nav2"><a href="#/sports" class="chip ${!sub ? "on" : ""}">For you</a>
      ${leagues.map((l) => `<a href="#/sports/${leagueSlug(l.league)}" class="chip ${sub === leagueSlug(l.league) ? "on" : ""}">${esc(l.label)}</a>`).join("")}
      <button class="chip" data-settings="sports">+ Teams and leagues</button></nav>
    <div id="sp-body"></div>`;
  const draw = async () => {
    if (!document.body.contains(el) || !$("#sp-body")) return;
    if (sub) await drawLeague(slugLeague(sub));
    else drawForYou(await api("/api/sports/foryou"));
    timer = setTimeout(draw, 20000);
  };
  if (sub) await drawLeague(slugLeague(sub)); else if (follows) drawForYou(follows);
  timer = setTimeout(draw, 20000);
}

export const stopSports = () => clearTimeout(timer);

function teamCard(t) {
  if (t.live) return gameCard(t.live, { highlight: true });
  const last = t.last ? `<div class="meta">Last: ${esc(t.last.away)} ${esc(t.last.away_score)} – ${esc(t.last.home)} ${esc(t.last.home_score)} · ${esc(t.last.detail)}</div>` : "";
  const next = t.next;
  return `
    <article class="card game">
      <div class="team-head">${t.team.logo ? `<img src="${esc(t.team.logo)}" alt="" loading="lazy">` : ""}<b>${esc(t.team.name)}</b><span class="hint">${esc(t.team.league)}</span></div>
      ${last}
      ${next ? `<div class="next">Next: ${esc(next.away)} at ${esc(next.home)} · ${fmtWhen(next.starts, 0)}${next.networks?.length ? ` · ${esc(next.networks.join(", "))}` : ""}</div>
        <div class="chips">${next.channels?.length ? next.channels.slice(0, 2).map((c) => `<button class="chip" data-channel="${esc(c.vcn)}">▶ ${esc(c.vcn)} ${esc(c.title)}</button>`).join("") : ""}</div>` : '<div class="hint">No upcoming game listed.</div>'}
    </article>`;
}

function drawForYou(d) {
  const body = $("#sp-body");
  if (!body) return;
  const open = body.querySelector("details")?.open;
  const recaps = new Map([...body.querySelectorAll(".recap:not([hidden])")].map((r) => [r.closest("[data-game]")?.dataset.game, r.innerHTML]));
  const cards = (gs, opts) => `<div class="cards">${gs.map((g) => gameCard(g, opts?.(g))).join("")}</div>`;
  let html = "";
  if (!d.teams.length && !d.followed_leagues.length) {
    html += `<div class="card empty-card"><b>Follow your teams and leagues</b><p class="hint">They'll be pinned here with live scores and where to watch.</p>
      <button class="primary" data-settings="sports">Choose teams</button></div>`;
  }
  html += row("Your teams", d.teams.length ? `<div class="cards">${d.teams.map(teamCard).join("")}</div>` : "");
  html += row("Worth switching to", d.worth.length ? cards(d.worth, (g) => ({ reason: g.reason })) : "");
  html += row("Your leagues", d.leagues.length ? cards(d.leagues) : "");
  html += d.others.length ? `<details class="elsewhere" ${open ? "open" : ""}><summary>${d.others.length} more games live or starting soon</summary>${cards(d.others)}</details>` : "";
  body.innerHTML = html || '<p class="empty">No games right now.</p>';
  tagGames(body, recaps);
}

async function drawLeague(league) {
  const games = await api(`/api/sports/league?league=${encodeURIComponent(league)}`);
  const body = $("#sp-body");
  if (!body) return;
  const recaps = new Map([...body.querySelectorAll(".recap:not([hidden])")].map((r) => [r.closest("[data-game]")?.dataset.game, r.innerHTML]));
  const by = (st) => games.filter((g) => g.state === st);
  body.innerHTML = row("Live", by("in").length ? `<div class="cards">${by("in").map((g) => gameCard(g)).join("")}</div>` : "")
    + row("Coming up", by("pre").length ? `<div class="cards">${by("pre").map((g) => gameCard(g)).join("")}</div>` : "")
    + row("Final", by("post").length ? `<div class="cards">${by("post").map((g) => gameCard(g)).join("")}</div>` : "")
    || '<p class="empty">No games today or tomorrow.</p>';
  tagGames(body, recaps);
}

// Keep "Catch me up" text across the 20-second refresh.
function tagGames(body, recaps) {
  body.querySelectorAll("[data-recap]").forEach((b) => {
    const card = b.closest(".card");
    card.dataset.game = b.dataset.recap;
    const kept = recaps.get(b.dataset.recap);
    if (kept) { const r = card.querySelector(".recap"); r.innerHTML = kept; r.hidden = false; }
  });
}

export async function showRecap(btn) {
  const card = btn.closest(".card");
  const box = card.querySelector(".recap");
  box.hidden = false;
  box.textContent = "Catching up…";
  try {
    const r = await api(`/api/sports/recap?game_id=${encodeURIComponent(btn.dataset.recap)}`);
    box.innerHTML = r.recap ? `<span class="spark" aria-hidden="true">✦</span> ${esc(r.recap)}`
      : `<ul>${r.plays.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
  } catch (e) {
    box.textContent = e.message;
  }
}
