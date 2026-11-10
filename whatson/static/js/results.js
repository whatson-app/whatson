// The results page of the search bar: games, what's on TV, movies and shows you have, and (with
// Radarr/Sonarr set up) titles you could get. After an AI reading, matches for the words as typed come first.

import { $, esc } from "./core.js";
import { airingCard, gameCard, posterCard, row } from "./cards.js";
import { getRow } from "./get.js";

export function renderResults(el, res) {
  const cards = (items, fn) => items.length ? `<div class="cards">${items.map((x) => fn(x)).join("")}</div>` : "";
  const posters = (items) => items.length ? `<div class="posters">${items.map((it) => posterCard(it)).join("")}</div>` : "";
  const rows = (r) => {
    const ids = new Set(r.games.map((g) => g.id));
    const airings = r.guide.filter((a) => !(a.game && ids.has(a.game.id)));
    return row("Games", cards(r.games, gameCard)) + row("On TV", cards(airings, airingCard))
      + row("Movies", posters(r.library.filter((it) => it.kind === "movie")))
      + row("TV shows", posters(r.library.filter((it) => it.kind === "show")));
  };
  const found = (r) => r.games.length + r.guide.length + r.library.length;
  // With AI on, matches for the words as typed come first, so a misreading can't hide what was asked for.
  const groups = res.typed
    ? `<p class="group-head">Matches for “${esc(res.typed.text)}”</p>${rows(res.typed)}`
      + (found(res) ? `<p class="group-head">More from the AI's reading</p>${rows(res)}` : "")
    : rows(res);
  el.innerHTML = groups
    + (res.typed || found(res) ? "" : '<p class="empty">Nothing on TV or in your library matches that. Try fewer words.</p>')
    + '<div id="get-movie"></div><div id="get-show"></div>';
  // Titles to get, unless the question was only about live TV or only about the other kind.
  const f = res.filters || {};
  const text = f.text || "";
  if (f.scope === "guide" || f.on_now) return;
  const wants = (k) => !(f.kinds || []).length || f.kinds.includes(k) || (k === "show" && f.kinds.includes("episode"));
  if (wants("movie")) getRow($("#get-movie", el), text, "movie", "Movies to get");
  if (wants("show")) getRow($("#get-show", el), text, "show", "Shows to get");
}
