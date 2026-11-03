// Router, the search bar above every section, and global click wiring. Routes: #/live[/view],
// #/library[/movie|show|downloads], #/library/show/<id>, #/sports[/league], #/remote, #/search (results).
// The last section used is remembered.

import { $, $$, applyTheme, closeSheet, store, toast } from "./core.js";
import { initPlayer, loadDevices, refreshNow, setPairHandler, setSettingsHandler, tuneTo } from "./player.js";
import { goToChannel, renderLive, showAiring, toggleFav } from "./live.js";
import { renderLibrary, renderShow, showMovie } from "./library.js";
import { renderSports, showRecap, stopSports } from "./sports.js";
import { initSettings, openSettings, wizard } from "./settings.js";
import { renderDownloads, showGet, stopDownloads } from "./get.js";
import { renderRemote, stopRemote } from "./remote.js";
import { mountSearch } from "./search.js";
import { renderResults } from "./results.js";

const SECTIONS = ["live", "library", "sports", "remote"];
let lastResults = null;

// One search for everything: live TV, games, the library, and titles to get. With AI on, it reads
// the question; a bare channel number jumps to that channel in the guide instead.
const gsearch = mountSearch($("#global-search"), {
  scope: "all", placeholder: "Search TV, movies, games",
  onResults: (res) => {
    lastResults = res;
    if (location.hash === "#/search") renderResults($("#view"), res);
    else location.hash = "#/search";
  },
  onClear: () => { lastResults = null; location.hash = `#/${store.get("section") || "live"}`; },
});
$("#global-search form").addEventListener("submit", (ev) => {
  const q = $("#global-search input").value.trim();
  if (/^\d+$/.test(q)) { ev.stopImmediatePropagation(); ev.preventDefault(); gsearch.reset(); goToChannel(q); }
}, true);

async function route() {
  let [section, a, b] = location.hash.replace(/^#\/?/, "").split("/");
  if (section === "search" && !lastResults) section = "";
  if (section !== "search" && !SECTIONS.includes(section)) {
    section = store.get("section") || "live";
    history.replaceState(null, "", `#/${section}`);
  }
  if (section !== "search") {
    store.set("section", section);
    gsearch.reset();
    lastResults = null;
  }
  $$("[data-nav]").forEach((n) => n.classList.toggle("on", n.dataset.nav === section));
  $("#global-search").hidden = section === "remote";   // the remote needs the room
  stopSports();
  stopDownloads();
  stopRemote();
  const view = $("#view");
  window.scrollTo(0, 0);
  try {
    if (section === "search") renderResults(view, lastResults);
    else if (section === "live") await renderLive(view, a || "guide");
    else if (section === "library" && a === "show" && b) await renderShow(view, b);
    else if (section === "library" && a === "downloads") await renderDownloads(view);
    else if (section === "library") await renderLibrary(view, a || store.get("lib-kind") || "movie");
    else if (section === "remote") await renderRemote(view);
    else await renderSports(view, a || "");
    if (section === "library" && (a === "movie" || a === "show") && !b) store.set("lib-kind", a);
  } catch (e) {
    view.innerHTML = '<p class="msg err"></p>';
    view.firstChild.textContent = e.message;
  }
}

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-channel],[data-rating-key],[data-airing],[data-movie],[data-show],[data-recap],[data-fav],[data-settings],[data-get]");
  if (!el) return;
  const d = el.dataset;
  if (d.channel) tuneTo({ channel: d.channel }, el);
  else if (d.ratingKey) tuneTo({ rating_key: d.ratingKey }, el);
  else if (d.airing) showAiring(d.airing).catch((e) => toast(e.message));
  else if (d.movie) showMovie(d.movie).catch((e) => toast(e.message));
  else if (d.show) { closeSheet(); location.hash = `#/library/show/${d.show}`; }
  else if (d.recap) showRecap(el);
  else if (d.fav) toggleFav(el);
  else if (d.settings) openSettings(d.settings);
  else if (d.get) { const [kind, id] = d.get.split(":"); showGet(kind, id).catch((e) => toast(e.message)); }
});

$("#open-settings").addEventListener("click", () => openSettings("tvs"));
$("#settings").addEventListener("close", async () => {
  const st = await fetch("/api/status").then((r) => r.json()).catch(() => ({}));
  const wasOff = !$("#connect-source").hidden;
  $("#connect-source").hidden = st.connected !== false;
  if (st.ai) $("#global-search input").placeholder = "Search, or ask anything";
  if (wasOff && st.connected) route();
});
window.addEventListener("hashchange", route);
// The guide switches between grid and list at the phone breakpoint.
let wasPhone = window.matchMedia("(max-width: 700px)").matches;
window.addEventListener("resize", () => {
  const phone = window.matchMedia("(max-width: 700px)").matches;
  if (phone !== wasPhone && location.hash.startsWith("#/live")) route();
  wasPhone = phone;
});

applyTheme(store.get("theme"));
setPairHandler((d) => wizard.open({ host: d.host, name: d.name, kind: d.kind, step: "pair" }));
setSettingsHandler(openSettings);
initPlayer();
initSettings();

(async () => {
  await loadDevices().catch(() => {});
  refreshNow();
  route();
  // First run: nothing works until a server is connected.
  const st = await fetch("/api/status").then((r) => r.json()).catch(() => ({}));
  if (st.ai) $("#global-search input").placeholder = "Search, or ask anything";
  $("#connect-source").hidden = st.connected !== false;
  if (st.connected === false) openSettings("source");
})();
