// The search box each section uses. AI (when on) reads the question into filters; the filters show
// as chips you can remove; with AI on, a one-line answer is written from the matches only.

import { $, api, esc } from "./core.js";

function chipsFor(f) {
  const out = [];
  if (f.text) out.push(["text", `“${f.text}”`]);
  if (f.on_now) out.push(["on_now", "On now"]);
  if (f.within_minutes) out.push(["within_minutes", `Next ${Math.round(f.within_minutes / 60)} h`]);
  if (f.max_minutes) out.push(["max_minutes", `Under ${f.max_minutes >= 60 ? `${Math.round(f.max_minutes / 6) / 10} h` : `${f.max_minutes} min`}`]);
  if (f.audience && f.audience !== "any") out.push(["audience", f.audience === "kids" ? "Kids" : "Family"]);
  (f.kinds || []).forEach((k, i) => out.push([`kinds:${i}`, { movie: "Movies", episode: "Shows", show: "Shows", sports: "Sports" }[k] || k]));
  (f.genres || []).forEach((g, i) => out.push([`genres:${i}`, g[0].toUpperCase() + g.slice(1)]));
  if (f.year_from || f.year_to) {
    const a = f.year_from, b = f.year_to;
    out.push(["years", a && b ? (b - a === 9 && a % 10 === 0 ? `${a}s` : `${a}–${b}`) : a ? `Since ${a}` : `Before ${b + 1}`]);
  }
  return out;
}

function without(f, key) {
  const n = structuredClone(f);
  const [field, idx] = key.split(":");
  if (field === "years") { n.year_from = null; n.year_to = null; return n; }
  if (idx !== undefined) n[field].splice(Number(idx), 1);
  else n[field] = field === "audience" ? "any" : field === "on_now" ? false : field === "text" ? "" : null;
  return n;
}

export function mountSearch(root, { scope, kind = "", placeholder, onResults, onClear, initial = "" }) {
  root.innerHTML = `
    <form class="search" role="search">
      <input type="search" autocomplete="off" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}" value="${esc(initial)}">
      <button type="submit">Search</button>
    </form>
    <div class="chips-row" hidden></div>
    <p class="answer" hidden></p>`;
  const form = $("form", root);
  const input = $("input", root);
  const chips = $(".chips-row", root);
  const answer = $(".answer", root);
  let query = "";
  let filters = null;

  const showAnswer = async () => {
    answer.hidden = true;
    if (!filters) return;
    try {
      const r = await api(`/api/answer?q=${encodeURIComponent(query)}&scope=${scope}&filters=${encodeURIComponent(JSON.stringify(filters))}`);
      if (r.answer) { answer.innerHTML = `<span class="spark" aria-hidden="true">✦</span> ${esc(r.answer)}`; answer.hidden = false; }
    } catch { /* the answer line is optional */ }
  };

  const render = (res) => {
    filters = res.filters;
    const list = chipsFor(filters);
    chips.hidden = !list.length;
    chips.innerHTML = `<span class="hint">${res.ai ? "Read as" : "Showing"}</span>` +
      list.map(([k, label]) => `<button type="button" class="chip ${res.ai ? "ai" : ""}" data-chip="${esc(k)}" aria-label="Remove ${esc(label)}">${esc(label)} ✕</button>`).join("");
    onResults(res);
    if (res.ai) showAnswer();
  };

  const run = async (q) => {
    query = q;
    if (!q) { chips.hidden = answer.hidden = true; filters = null; return onClear(); }
    const btn = $("button", form);
    btn.disabled = true;
    try {
      render(await api(`/api/search?q=${encodeURIComponent(q)}&scope=${scope}&kind=${kind}`));
    } finally {
      btn.disabled = false;
    }
  };

  form.addEventListener("submit", (ev) => { ev.preventDefault(); run(input.value.trim()); });
  input.addEventListener("search", () => { if (!input.value) run(""); });
  chips.addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-chip]");
    if (!b || !filters) return;
    const next = without(filters, b.dataset.chip);
    const r = await api(`/api/search?scope=${scope}&kind=${kind}&filters=${encodeURIComponent(JSON.stringify(next))}`);
    r.ai = chips.querySelector(".chip.ai") !== null;
    render(r);
  });
  if (initial) run(initial);
  // Empty the box without calling onClear (used when leaving the results page).
  const reset = () => { input.value = ""; query = ""; filters = null; chips.hidden = answer.hidden = true; };
  return { run, reset };
}
