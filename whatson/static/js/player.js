// The selected TV: picker, tuning, and the now-playing bar with pause/stop.

import { $, api, confirmDialog, esc, store, thumbUrl, toast } from "./core.js";

export let devices = [];
let onNeedPair = () => {};
let onOpenSettings = () => {};
let nowTimer = null;

export const setPairHandler = (fn) => { onNeedPair = fn; };
export const setSettingsHandler = (fn) => { onOpenSettings = fn; };
export const selectedId = () => Number($("#tv").value) || null;
// Watched status and Up Next follow the selected TV's Plex user.
export const deviceParam = () => `device=${selectedId() || 0}`;

export async function loadDevices() {
  devices = await api("/api/devices");
  const sel = $("#tv");
  let saved = store.get("tv");
  if (!devices.some((d) => String(d.id) === saved)) saved = devices[0] ? String(devices[0].id) : "";
  sel.innerHTML = devices.length
    ? devices.map((d) => `<option value="${d.id}" ${String(d.id) === saved ? "selected" : ""}>${esc(d.name)}${d.paired ? "" : " (not paired)"}</option>`).join("")
    : '<option value="">No TVs yet</option>';
  return devices;
}

export function selectDevice(id) {
  store.set("tv", String(id));
  $("#tv").value = String(id);
  refreshNow();
}

// target: {channel} | {rating_key}
export async function tuneTo(target, btn) {
  const deviceId = selectedId();
  if (!deviceId) { onOpenSettings("tvs"); return toast("Add a TV first."); }
  if (btn) btn.disabled = true;
  const send = (force) => api("/api/tune", { method: "POST", body: { device_id: deviceId, ...target, force } });
  try {
    let r;
    try {
      r = await send(false);
    } catch (e) {
      if (e.code === "not_paired") {
        const d = devices.find((x) => x.id === deviceId);
        if (d && await confirmDialog(`${d.name} isn't paired any more (it may have been reset). Pair it again now?`, "Pair again")) {
          onNeedPair(d);
        }
        return;
      }
      if (e.code !== "busy") throw e;
      if (!await confirmDialog(`${e.message} Take it over?`)) return;
      r = await send(true);
    }
    toast(`Starting on ${r.device}…`);
    setTimeout(refreshNow, 6000);
    if (r.confirm) confirmStarted(deviceId, r.device, target, r.profile_user);
  } catch (e) {
    toast(e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Live TV can take 15 seconds to show as playing, so don't call it a failure sooner than this.
async function confirmStarted(deviceId, name, target, profileUser) {
  for (let i = 0; i < 5; i++) {
    await new Promise((done) => setTimeout(done, 5000));
    const n = await api(`/api/devices/${deviceId}/now`).catch(() => null);
    if (!n) return;
    if (target.channel ? n.channel?.vcn === target.channel : [n.rating_key, n.show_key].includes(target.rating_key)) return;
  }
  toast(profileUser
    ? `Couldn't confirm it started on ${name}. Check Plezy there is up to date, has a profile for ${profileUser}, and that ${profileUser} can see this title in Plex.`
    : `Couldn't confirm it started on ${name}. Check Plezy there is signed in to Jellyfin, and that the TV is linked in Settings → TVs.`, 12000);
}

function nowHtml(n) {
  const icon = { off: "⏻", unreachable: "⚠", not_paired: "⚠", idle: "⌂", app: "▣" }[n.state];
  if (icon) {
    return `<div class="now-art now-icon">${icon}</div><div class="now-text"><div class="now-title">${esc(n.title)}</div></div>`;
  }
  const art = n.channel?.thumb
    ? `<img class="now-art" src="${esc(n.channel.thumb)}" alt="">`
    : n.thumb ? `<img class="now-art" src="${thumbUrl(n.thumb, 120)}" alt="">` : '<div class="now-art now-icon">▶</div>';
  const pct = n.duration ? Math.min(100, Math.round((n.offset / n.duration) * 100)) : 0;
  const g = n.game;
  const sub = g ? `${esc(g.away)} ${esc(g.away_score)} · ${esc(g.home)} ${esc(g.home_score)} · ${esc(g.detail)}`
    : [n.subtitle, n.channel ? `${n.channel.vcn} ${n.channel.title}` : ""].filter(Boolean).map(esc).join(" · ");
  const paused = n.state === "paused";
  return `${art}
    <div class="now-text">
      <div class="now-title">${n.kind === "live" ? '<span class="live">LIVE</span> ' : ""}${esc(n.title)}</div>
      ${sub ? `<div class="now-sub">${sub}</div>` : ""}
      ${pct ? `<div class="now-bar"><div style="width:${pct}%"></div></div>` : ""}
    </div>
    <button class="icon-btn" data-key="play_pause" aria-label="${paused ? "Play" : "Pause"}">${paused ? "▶" : "⏸"}</button>
    <button class="icon-btn" data-key="stop" aria-label="Stop">⏹</button>`;
}

export async function refreshNow() {
  const bar = $("#now");
  const id = selectedId();
  clearTimeout(nowTimer);
  if (!id) { bar.hidden = true; return; }
  bar.hidden = false;
  try {
    const n = await api(`/api/devices/${id}/now`);
    bar.innerHTML = nowHtml(n);
    bar.dataset.state = n.state;
    bar.dataset.ratingKey = n.show_key || n.rating_key || "";
    bar.dataset.kind = n.kind;
  } catch {
    bar.innerHTML = '<div class="now-text"><div class="now-sub">Now playing unavailable</div></div>';
  }
  if (!document.hidden) nowTimer = setTimeout(refreshNow, 10000);
}

export function initPlayer() {
  $("#tv").addEventListener("change", (ev) => selectDevice(ev.target.value));
  $("#now").addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-key]");
    if (b) {
      b.disabled = true;
      try { await api(`/api/devices/${selectedId()}/key`, { method: "POST", body: { key: b.dataset.key } }); }
      catch (e) { toast(e.message); }
      setTimeout(refreshNow, 1500);
      b.disabled = false;
      return;
    }
    // Tapping the bar jumps to what's playing.
    const bar = ev.currentTarget;
    if (bar.dataset.kind === "live") location.hash = "#/live";
    else if (bar.dataset.ratingKey && bar.dataset.kind === "episode") location.hash = `#/library/show/${bar.dataset.ratingKey}`;
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshNow(); });
}
