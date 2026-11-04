// The search box each section uses. AI (when on) reads the question into filters; the filters show
// as chips you can remove; with AI on, a one-line answer is written from the matches only.

import { $, ai, aiPlaceholder, api, esc, working } from "./core.js";

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
    <p class="search-status" role="status" hidden></p>
    <div class="chips-row" hidden></div>
    <div class="answer" hidden></div>`;
  const form = $("form", root);
  const input = $("input", root);
  const chips = $(".chips-row", root);
  const answer = $(".answer", root);
  const status = $(".search-status", root);
  const btn = $("button", form);
  let query = "";
  let filters = null;
  let latest = 0;  // Each search takes a number, so a slow answer can't overwrite a newer search.

  const setBusy = (text) => {
    status.hidden = !text;
    status.className = "search-status";
    status.innerHTML = text ? working(text) : "";
    form.classList.toggle("busy", Boolean(text));
    btn.disabled = Boolean(text);
  };

  const showAnswer = async (id) => {
    answer.hidden = true;
    if (!filters) return;
    answer.innerHTML = aiPlaceholder("AI is writing an answer…");
    answer.hidden = false;
    let text = "";
    try {
      const r = await api(`/api/answer?q=${encodeURIComponent(query)}&scope=${scope}&filters=${encodeURIComponent(JSON.stringify(filters))}`);
      text = r.answer;
    } catch { /* the answer line is optional */ }
    if (id !== latest) return;
    answer.innerHTML = text ? `<span class="spark" aria-hidden="true">✦</span> ${esc(text)}` : "";
    answer.hidden = !text;
  };

  const render = (res, id) => {
    filters = res.filters;
    const list = chipsFor(filters);
    chips.hidden = !list.length;
    chips.innerHTML = `<span class="hint">${res.ai ? "Read as" : "Showing"}</span>` +
      list.map(([k, label]) => `<button type="button" class="chip ${res.ai ? "ai" : ""}" data-chip="${esc(k)}" aria-label="Remove ${esc(label)}">${esc(label)} ✕</button>`).join("");
    onResults(res);
    if (res.ai) showAnswer(id);
  };

  // `busyText` says what's being waited for; the search itself is `load`.
  const search = async (load, busyText) => {
    const id = ++latest;
    answer.hidden = true;
    setBusy(busyText);
    try {
      const res = await load();
      if (id !== latest) return;
      setBusy("");
      render(res, id);
    } catch (e) {
      if (id !== latest) return;
      setBusy("");
      status.className = "search-status err";
      status.textContent = `Couldn't search: ${e.message}`;
      status.hidden = false;
    }
  };

  const run = async (q) => {
    query = q;
    if (!q) { latest++; setBusy(""); chips.hidden = answer.hidden = true; filters = null; return onClear(); }
    await search(() => api(`/api/search?q=${encodeURIComponent(q)}&scope=${scope}&kind=${kind}`),
      ai.on ? "AI is reading your question…" : "Searching…");
  };

  form.addEventListener("submit", (ev) => { ev.preventDefault(); run(input.value.trim()); });
  input.addEventListener("search", () => { if (!input.value) run(""); });
  chips.addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-chip]");
    if (!b || !filters) return;
    const next = without(filters, b.dataset.chip);
    const wasAi = chips.querySelector(".chip.ai") !== null;
    await search(async () => {
      const r = await api(`/api/search?scope=${scope}&kind=${kind}&filters=${encodeURIComponent(JSON.stringify(next))}`);
      r.ai = wasAi;
      return r;
    }, "Searching…");
  });
  if (initial) run(initial);
  // Empty the box without calling onClear (used when leaving the results page).
  const reset = () => { latest++; setBusy(""); input.value = ""; query = ""; filters = null; chips.hidden = answer.hidden = true; };
  return { run, reset };
}
