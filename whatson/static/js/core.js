// Shared helpers: DOM, API, toasts, dialogs, formatting.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

export async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "X-WhatsOn": "1", ...(opts.body ? { "Content-Type": "application/json" } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // Errors come back as {detail: "text"} or {detail: {code, message, ...}}.
    const d = data.detail;
    const msg = typeof d === "string" ? d : d?.message || (Array.isArray(d) ? d[0]?.msg : "") || res.statusText;
    const err = new Error(msg);
    err.status = res.status;
    err.code = typeof d === "object" && d ? d.code : undefined;
    err.data = d;
    throw err;
  }
  return data;
}

export function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 3500);
}

export function confirmDialog(text, okLabel = "Take over") {
  $("#confirm-text").textContent = text;
  $("#confirm-ok").textContent = okLabel;
  return new Promise((resolve) => {
    const d = $("#confirm");
    d.addEventListener("close", () => resolve(d.returnValue === "ok"), { once: true });
    d.showModal();
  });
}

// A bottom sheet / dialog for details (programme, movie, episode).
export function openSheet(html) {
  const d = $("#sheet");
  $("#sheet-body").innerHTML = html;
  if (!d.open) d.showModal();
  return $("#sheet-body");
}
export const closeSheet = () => $("#sheet").close();

export const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
export function fmtWhen(begins, ends, now = Date.now() / 1000) {
  if (begins <= now && now < ends) return `<span class="live">LIVE</span> until ${fmtTime(ends)}`;
  const d = new Date(begins * 1000);
  const today = new Date().toDateString() === d.toDateString();
  const day = today ? "" : d.toLocaleDateString([], { weekday: "short" }) + " ";
  return `${day}${fmtTime(begins)}${ends ? `–${fmtTime(ends)}` : ""}`;
}
export const fmtMins = (ms) => {
  const m = Math.round((ms || 0) / 60000);
  return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`;
};
export const thumbUrl = (path, width = 300) =>
  path ? `/api/thumb?path=${encodeURIComponent(path)}&width=${width}` : "";

export const isPhone = () => window.matchMedia("(max-width: 700px)").matches;

// Debounce helper for search-as-you-type boxes.
export function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
