// The Remote tab: d-pad, playback, volume, typing, opening apps, and direct control of Jellyfin apps.
// Keys go to the TV picked at the top. Holding a d-pad or volume key repeats it.

import { $, api, esc, openSheet, closeSheet, toast } from "./core.js";
import { refreshNow, selectedId } from "./player.js";

let view = null;
let timer = null;
let st = null;
let control = "tv";   // "tv" or "jellyfin:<session id>"
let busy = false;

const REPEAT_AFTER = 400;
const REPEAT_EVERY = 140;

export function stopRemote() {
  clearTimeout(timer);
  timer = null;
  view = null;
}

export async function renderRemote(el) {
  view = el;
  el.innerHTML = `<div class="remote"><p class="hint">Connecting to the TV…</p></div>`;
  await load();
}

async function load() {
  clearTimeout(timer);
  if (!view) return;
  const id = selectedId();
  if (!id) {
    view.innerHTML = `<div class="remote"><p class="msg">Add a TV first.</p><button class="primary" data-settings="tvs">Add a TV</button></div>`;
    return;
  }
  try {
    st = await api(`/api/remote/${id}`);
  } catch (e) {
    st = { error: e.message, reachable: false, apps: [], controls: [] };
  }
  if (!view) return;
  if (control !== "tv" && !st.controls.some((c) => c.id === control)) control = "tv";
  draw();
  if (!document.hidden) timer = setTimeout(load, 5000);
}

// Line icons (24×24, drawn in currentColor) so every phone shows the same thing; emoji vary by font.
const P = {
  power: '<path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/>',
  back: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  home: '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  type: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  prev: '<path d="M6 5v14"/><path d="M19 5 9 12l10 7z" fill="currentColor"/>',
  rew: '<path d="M11 6 3 12l8 6zM21 6l-8 6 8 6z" fill="currentColor"/>',
  playpause: '<path d="M3 5l9 7-9 7z" fill="currentColor"/><path d="M16 5v14M20 5v14"/>',
  ff: '<path d="M13 6l8 6-8 6zM3 6l8 6-8 6z" fill="currentColor"/>',
  next: '<path d="M18 5v14"/><path d="M5 5l10 7-10 7z" fill="currentColor"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor"/>',
  play: '<path d="M7 5l12 7-12 7z" fill="currentColor"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  mute: '<path d="M3 9h4l5-4v14l-5-4H3z" fill="currentColor"/><path d="m16 9 5 6M21 9l-5 6"/>',
  sound: '<path d="M3 9h4l5-4v14l-5-4H3z" fill="currentColor"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  input: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 7v6M9.5 10.5 12 13l2.5-2.5"/>',
  captions: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10.5 10.2a2.2 2.2 0 1 0 0 3.6M17.5 10.2a2.2 2.2 0 1 0 0 3.6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
  settings: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>', left: '<path d="m15 6-6 6 6 6"/>', right: '<path d="m9 6 6 6-6 6"/>',
  del: '<path d="M21 5H9l-6 7 6 7h12z"/><path d="m12 9 6 6M18 9l-6 6"/>',
};
const ic = (name) => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name]}</svg>`;
// A key: icon plus an optional caption under it. `label` is also what screen readers hear.
const key = (k, icon, label, cls = "", caption = true) =>
  `<button class="rk ${cls}" data-rkey="${k}" aria-label="${esc(label)}">${ic(icon)}${caption ? `<small>${esc(label)}</small>` : ""}</button>`;
const fmt = (ms) => {
  const s = Math.floor((ms || 0) / 1000), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(s % 60).padStart(2, "0")}`;
};

function appIcon(a) {
  return `<span class="app-ic" style="background:${esc(a.color)}">${esc(a.badge || a.name.slice(0, 2))}</span>`;
}

function draw() {
  const r = view.querySelector(".remote") || view.appendChild(Object.assign(document.createElement("div"), { className: "remote" }));
  if (!st.reachable || !st.paired) {
    r.innerHTML = `<p class="msg err">${esc(st.error || "Can't reach the TV.")}</p>
      <div class="row"><button data-settings="tvs">TV settings</button><button class="primary" id="rm-retry">Try again</button></div>`;
    r.querySelector("#rm-retry").onclick = load;
    return;
  }
  const v = st.volume;
  const jf = st.controls.find((c) => c.id === control);
  const shown = st.apps.filter((a) => a.shown);
  const off = st.is_on === false;
  r.classList.toggle("off", off);
  r.innerHTML = `
    <div class="rm-top">
      <button class="rk power ${off ? "" : "is-on"}" data-rkey="POWER" aria-label="Power">${ic("power")}<small>${off ? "Turn on" : "Power"}</small></button>
      <span class="rm-state">${off ? "TV is off" : esc(st.app_name || "")}</span>
      ${key("TV_INPUT", "input", "Input", "mini")}${key("SETTINGS", "settings", "Settings", "mini")}
    </div>
    <div class="rm-body" ${off ? "inert" : ""}>
    ${st.controls.length ? `<div class="rm-ctl"><span class="hint">Control</span>
      <button class="chip ${control === "tv" ? "on" : ""}" data-ctl="tv">TV remote</button>
      ${st.controls.map((c) => `<button class="chip ${control === c.id ? "on" : ""}" data-ctl="${esc(c.id)}">${esc(c.label)}</button>`).join("")}
    </div>` : ""}
    <div class="rm-apps" role="list">
      ${shown.map((a) => `<button class="rm-app" role="listitem" data-app="${esc(a.id)}" title="Open ${esc(a.name)}">${appIcon(a)}<span>${esc(a.name)}</span></button>`).join("")}
      <button class="rm-app" data-edit-apps><span class="app-ic edit">✎</span><span>Edit</span></button>
    </div>
    ${jf ? jfPanel(jf) : ""}
    <div class="rm-dpad ${jf ? "small" : ""}">
      ${key("DPAD_UP", "up", "Up", "up hold", false)}${key("DPAD_LEFT", "left", "Left", "left hold", false)}
      <button class="rk ok" data-rkey="DPAD_CENTER" aria-label="OK">OK</button>
      ${key("DPAD_RIGHT", "right", "Right", "right hold", false)}${key("DPAD_DOWN", "down", "Down", "down hold", false)}
    </div>
    <div class="rm-row">${key("BACK", "back", "Back")}${key("HOME", "home", "Home")}${key("MENU", "menu", "Menu")}
      <button class="rk" id="rm-type" aria-label="Type">${ic("type")}<small>Type</small></button></div>
    <form id="rm-kb" class="row rm-kb" hidden>
      <input name="t" maxlength="200" autocomplete="off" placeholder="Type, then Send" aria-label="Text to type on the TV">
      ${key("DEL", "del", "Delete", "", false)}<button class="primary" type="submit">Send</button>
    </form>
    ${jf ? "" : `<div class="rm-row">${key("MEDIA_PREVIOUS", "prev", "Previous", "", false)}${key("MEDIA_REWIND", "rew", "Rewind", "hold", false)}
      ${key("MEDIA_PLAY_PAUSE", "playpause", "Play / pause", "accent", false)}${key("MEDIA_FAST_FORWARD", "ff", "Fast forward", "hold", false)}
      ${key("MEDIA_NEXT", "next", "Next", "", false)}${key("MEDIA_STOP", "stop", "Stop", "", false)}</div>`}
    <div class="rm-rockers">
      <div class="rocker">${key("VOLUME_UP", "plus", "Volume up", "hold", false)}<span>VOL</span>${key("VOLUME_DOWN", "minus", "Volume down", "hold", false)}</div>
      <div class="rm-mid">
        <button class="rk ${v?.muted ? "on" : ""}" data-rkey="VOLUME_MUTE" aria-label="Mute">${ic(v?.muted ? "mute" : "sound")}<small>${v?.muted ? "Muted" : "Mute"}</small></button>
        ${v && v.max ? `<div class="rm-lvl" aria-label="Volume ${v.level} of ${v.max}"><i style="width:${Math.round((v.level / v.max) * 100)}%"></i></div>
          <span class="hint rm-lvln">${v.level} / ${v.max}</span>` : ""}
        <div class="rm-row">${key("CAPTIONS", "captions", "Captions", "", false)}${key("INFO", "info", "Info", "", false)}</div>
      </div>
      <div class="rocker">${key("CHANNEL_UP", "plus", "Channel up", "", false)}<span>CH</span>${key("CHANNEL_DOWN", "minus", "Channel down", "", false)}</div>
    </div>
    </div>`;
  wire(r);
}

function jfPanel(c) {
  const dis = c.controllable ? "" : "disabled";
  return `<div class="card rm-jf">
    <div class="title">${esc(c.title || "Nothing playing")}</div>${c.subtitle ? `<div class="sub">${esc(c.subtitle)}</div>` : ""}
    ${c.duration ? `<div class="rm-seek"><span>${fmt(c.position)}</span><input type="range" min="0" max="${c.duration}" value="${c.position}" data-seek ${dis} aria-label="Position"><span>${fmt(c.duration)}</span></div>` : ""}
    <div class="rm-row">
      <button class="rk" data-jf="Seek" data-delta="-10000" ${dis} aria-label="Back 10 seconds">${ic("rew")}<small>−10 s</small></button>
      <button class="rk accent" data-jf="PlayPause" ${dis} aria-label="${c.paused ? "Play" : "Pause"}">${ic(c.paused ? "play" : "pause")}</button>
      <button class="rk" data-jf="Seek" data-delta="30000" ${dis} aria-label="Forward 30 seconds">${ic("ff")}<small>+30 s</small></button>
      <button class="rk" data-jf="Stop" ${dis} aria-label="Stop">${ic("stop")}</button>
      <button class="rk" data-jf="NextTrack" ${dis} aria-label="Next">${ic("next")}</button>
    </div>
    ${c.controllable ? "" : `<p class="hint">This app doesn't allow remote control. The TV buttons below still work.</p>`}
  </div>`;
}

async function send(k, direction = "SHORT") {
  try {
    await api(`/api/remote/${selectedId()}/key`, { method: "POST", body: { key: k, direction } });
  } catch (e) { toast(e.message); throw e; }
}

function wire(r) {
  // Press-and-hold: one press now, then repeats while held. Taps fire once.
  r.querySelectorAll("[data-rkey]").forEach((b) => {
    let hold = null, held = false;
    const stop = () => { clearTimeout(hold); hold = null; held = false; };
    b.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      navigator.vibrate?.(8);
      send(b.dataset.rkey).catch(() => stop());
      if (!b.classList.contains("hold")) return;
      held = true;
      const again = async () => {
        if (!held) return;
        try { await send(b.dataset.rkey); } catch { return stop(); }
        if (held) hold = setTimeout(again, REPEAT_EVERY);
      };
      hold = setTimeout(again, REPEAT_AFTER);
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach((e) => b.addEventListener(e, stop));
    // Pointer presses are handled above; a click with detail 0 is the keyboard (Enter/Space).
    b.addEventListener("click", (ev) => { ev.preventDefault(); if (ev.detail === 0) send(b.dataset.rkey).catch(() => {}); });
    if (/^VOLUME|MEDIA_PLAY|MEDIA_STOP|POWER/.test(b.dataset.rkey)) b.addEventListener("pointerup", () => setTimeout(soon, 600));
  });
  r.querySelectorAll("[data-ctl]").forEach((b) => b.addEventListener("click", () => { control = b.dataset.ctl; draw(); }));
  r.querySelectorAll("[data-app]").forEach((b) => b.addEventListener("click", () => launch(b)));
  r.querySelector("[data-edit-apps]").addEventListener("click", editApps);
  r.querySelector("#rm-type").addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    const f = r.querySelector("#rm-kb");
    f.hidden = !f.hidden;
    if (!f.hidden) f.t.focus();
  });
  r.querySelector("#rm-kb").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const t = ev.target.t.value;
    if (!t) return;
    try {
      await api(`/api/remote/${selectedId()}/text`, { method: "POST", body: { text: t } });
      ev.target.t.value = "";
    } catch (e) { toast(e.message); }
  });
  r.querySelectorAll("[data-jf]").forEach((b) => b.addEventListener("click", () =>
    jfCommand(b.dataset.jf, { delta: b.dataset.delta ? Number(b.dataset.delta) : undefined })));
  r.querySelector("[data-seek]")?.addEventListener("change", (ev) => jfCommand("Seek", { position: Number(ev.target.value) }));
  // Keep the screen from redrawing under a finger.
  r.addEventListener("pointerdown", () => { clearTimeout(timer); timer = setTimeout(load, 5000); });
}

function soon() {
  clearTimeout(timer);
  timer = setTimeout(load, 300);
  refreshNow();
}

async function jfCommand(command, extra) {
  if (busy) return;
  busy = true;
  try {
    await api(`/api/remote/${selectedId()}/control`, { method: "POST", body: { target: control, command, ...extra } });
    setTimeout(soon, 500);
  } catch (e) { toast(e.message); } finally { busy = false; }
}

async function launch(b) {
  if (busy) return;
  busy = true;
  b.classList.add("opening");
  const name = b.querySelector("span:last-child").textContent;
  toast(`Opening ${name}…`);
  try {
    const r = await api(`/api/remote/${selectedId()}/launch`, { method: "POST", body: { app: b.dataset.app } });
    toast(r.opened ? `${r.name} is open.` : r.by_link
      ? `${r.name} didn't come up. Is it installed on this TV?`
      : `This TV won't open ${r.name} remotely. Open it from the TV's home screen.`);
    soon();
  } catch (e) { toast(e.message); } finally { busy = false; b.classList.remove("opening"); }
}

function editApps() {
  const id = selectedId();
  const list = () => `
    <h2 class="sheet-title">Apps on this TV</h2>
    <p class="hint">A TV can't tell WhatsOn which apps it has, so tick the ones you use. Apps WhatsOn has seen
      open on this TV are listed with when. Apps without a link may not open remotely on Google TV.</p>
    <div class="rm-applist">${st.apps.map((a) => `
      <label class="rm-appline">${appIcon(a)}
        <span class="grow"><b>${esc(a.name)}</b><small class="hint">${a.seen_at ? `seen ${new Date(a.seen_at * 1000).toLocaleDateString([], { month: "short", day: "numeric" })}` : "not seen yet"}${a.by_link ? "" : " · no link"}</small></span>
        <input type="checkbox" data-pkg="${esc(a.package)}" ${a.shown ? "checked" : ""}>
      </label>`).join("")}</div>
    <div class="row"><button class="primary" id="rm-apps-done">Done</button></div>`;
  const body = openSheet(list());
  body.addEventListener("change", async (ev) => {
    const cb = ev.target.closest("[data-pkg]");
    if (!cb) return;
    try {
      st.apps = await api(`/api/remote/${id}/apps`, { method: "PUT", body: { package: cb.dataset.pkg, shown: cb.checked } });
    } catch (e) { toast(e.message); cb.checked = !cb.checked; }
  });
  body.querySelector("#rm-apps-done").addEventListener("click", () => { closeSheet(); if (view) draw(); });
}

document.addEventListener("visibilitychange", () => { if (view && !document.hidden) load(); });
$("#tv").addEventListener("change", () => { if (view) { control = "tv"; load(); } });
