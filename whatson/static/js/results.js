// The results page of the search bar: games, what's on TV, movies and shows you have, and (with
// Radarr/Sonarr set up) titles you could get.

import { $ } from "./core.js";
import { airingCard, gameCard, posterCard, row } from "./cards.js";
import { getRow } from "./get.js";

export function renderResults(el, res) {
  const ids = new Set(res.games.map((g) => g.id));
  const airings = res.guide.filter((a) => !(a.game && ids.has(a.game.id)));
  const movies = res.library.filter((it) => it.kind === "movie");
  const shows = res.library.filter((it) => it.kind === "show");
  const cards = (items, fn) => items.length ? `<div class="cards">${items.map((x) => fn(x)).join("")}</div>` : "";
  const posters = (items) => items.length ? `<div class="posters">${items.map((it) => posterCard(it)).join("")}</div>` : "";
  const found = res.games.length + airings.length + res.library.length;
  el.innerHTML = row("Games", cards(res.games, gameCard)) + row("On TV", cards(airings, airingCard))
    + row("Movies", posters(movies)) + row("TV shows", posters(shows))
    + (found ? "" : '<p class="empty">Nothing on TV or in your library matches that. Try fewer words.</p>')
    + '<div id="get-movie"></div><div id="get-show"></div>';
  // Titles to get, unless the question was only about live TV or only about the other kind.
  const f = res.filters || {};
  const text = f.text || "";
  if (f.scope === "guide" || f.on_now) return;
  const wants = (k) => !(f.kinds || []).length || f.kinds.includes(k) || (k === "show" && f.kinds.includes("episode"));
  if (wants("movie")) getRow($("#get-movie", el), text, "movie", "Movies to get");
  if (wants("show")) getRow($("#get-show", el), text, "show", "Shows to get");
}
