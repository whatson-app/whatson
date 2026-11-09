// The selected TV: picker, tuning, and the now-playing bar with pause/stop. Tapping the bar opens a card about
// what's on: the listing, or for a game the live score, a catch-up and the latest plays from ESPN.

import { $, ai, aiPlaceholder, api, confirmDialog, esc, fmtMins, openSheet, closeSheet, store, thumbUrl, toast, working } from "./core.js";

export let devices = [];
let onNeedPair = () => {};
let onOpenSettings = () => {};
let nowTimer = null;
let nowShown = null;  // what the bar shows, for the card. Not on the bar itself: data-rating-key there means Play.

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
    nowShown = n;
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
    if (nowShown && ["playing", "paused", "buffering"].includes(nowShown.state)) openNowCard(nowShown);
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshNow(); });
}

// --- What's on: the card behind the bar --------------------------------------------------------------

const ESPN_CREDIT = '<p class="credit">Scores and plays from <a href="https://www.espn.com" target="_blank" rel="noopener">ESPN</a></p>';

// A small remote under the card: back 10 s, play/pause, back to live (live TV), volume, and the full remote.
function miniRemote(n) {
  const paused = n.state === "paused";
  return `
    <div class="mini-remote" aria-label="Remote">
      <button class="icon-btn" data-card-key="rewind" aria-label="Back 10 seconds" title="Back 10 seconds">↺10</button>
      <button class="icon-btn" data-card-key="play_pause" aria-label="${paused ? "Play" : "Pause"}">${paused ? "▶" : "⏸"}</button>
      ${n.kind === "live" && n.channel ? `<button class="chip" data-card-live="${esc(n.channel.vcn)}">Back to live</button>` : ""}
      <span class="vol" role="group" aria-label="Volume">
        <button class="icon-btn" data-card-key="volume_down" aria-label="Volume down">−</button>
        <button class="icon-btn" data-card-key="volume_mute" aria-label="Mute">🔇</button>
        <button class="icon-btn" data-card-key="volume_up" aria-label="Volume up">+</button>
      </span>
    </div>
    <a class="link-btn full-remote" href="#/remote" data-close-sheet>Full remote →</a>`;
}

function nowCardHtml(n) {
  return nowCardBody(n) + miniRemote(n) + (n.game ? ESPN_CREDIT : "");
}

function nowCardBody(n) {
  const g = n.game;
  const pct = n.duration ? Math.min(100, Math.round((n.offset / n.duration) * 100)) : 0;
  const progress = pct ? `<div class="now-bar card-bar"><div style="width:${pct}%"></div></div>` : "";
  const channel = n.channel ? `${esc(n.channel.vcn)} ${esc(n.channel.title)}` : "";
  if (g) {
    const team = (name, logo, score) => `<span class="team">${logo ? `<img src="${esc(logo)}" alt="" onerror="this.remove()">` : ""}${esc(name)}</span><b>${esc(score)}</b>`;
    return `
      <div class="meta">${g.state === "in" ? '<span class="live">LIVE</span> ' : ""}${esc(g.league)} · ${esc(g.detail)}${channel ? ` · ${channel}` : ""}</div>
      <h2 class="sheet-title">${esc(g.away)} at ${esc(g.home)}</h2>
      <div class="score score-big">${team(g.away, g.away_logo, g.away_score)}${team(g.home, g.home_logo, g.home_score)}</div>
      <div class="chips">
        ${g.state === "in" ? `<button class="chip" data-now-recap="${esc(g.id)}">Catch me up</button>` : ""}
        <button class="chip" data-now-plays="${esc(g.id)}">Latest plays</button>
        ${g.espn_url ? `<a class="chip" href="${esc(g.espn_url)}" target="_blank" rel="noopener">Game on ESPN ↗</a>` : ""}
      </div>
      <div class="recap" id="now-recap" hidden></div>`;
  }
  if (n.kind === "live") {
    return `
      <div class="meta"><span class="live">LIVE</span>${channel ? ` ${channel}` : ""}</div>
      <h2 class="sheet-title">${esc(n.title)}</h2>
      ${n.subtitle ? `<div class="sub">${esc(n.subtitle)}</div>` : ""}
      ${progress}
      ${n.summary ? `<p>${esc(n.summary)}</p>` : ""}
      ${n.airing_id ? `<div class="chips"><button class="chip" data-airing="${esc(n.airing_id)}">Times and channels</button></div>` : ""}`;
  }
  const isShow = n.kind === "episode" && n.show_key;
  const left = n.duration ? fmtMins(Math.max(0, n.duration - n.offset)) : "";
  return `
    <div class="now-card">
      ${n.thumb ? `<img class="now-poster" src="${thumbUrl(n.thumb, 240)}" alt="">` : ""}
      <div>
        <div class="meta">${n.state === "paused" ? "Paused" : "Playing"}${left ? ` · ${left} left` : ""}</div>
        <h2 class="sheet-title">${esc(n.title)}</h2>
        ${n.subtitle ? `<div class="sub">${esc(n.subtitle)}</div>` : ""}
        ${progress}
        <div class="chips">${isShow ? `<button class="chip" data-show="${esc(n.show_key)}">Open the show</button>`
          : n.rating_key && n.kind === "movie" ? `<button class="chip" data-movie="${esc(n.rating_key)}">About this movie</button>` : ""}</div>
      </div>
    </div>`;
}

async function fillFromEspn(gameId, plays) {
  const box = $("#now-recap");
  if (!box) return;
  box.hidden = false;
  box.innerHTML = !plays && ai.on ? aiPlaceholder("AI is catching you up…") : `<div class="ai-line">${working("Loading from ESPN…")}</div>`;
  try {
    const r = await api(`/api/sports/recap?game_id=${encodeURIComponent(gameId)}`);
    box.innerHTML = !plays && r.recap ? `<span class="spark" aria-hidden="true">✦</span> ${esc(r.recap)}`
      : r.plays.length ? `<ul>${r.plays.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : "No plays yet.";
  } catch (e) {
    box.textContent = e.message;
  }
}

async function cardKey(btn) {
  btn.disabled = true;
  try { await api(`/api/devices/${selectedId()}/key`, { method: "POST", body: { key: btn.dataset.cardKey } }); }
  catch (e) { toast(e.message); }
  btn.disabled = false;
  if (btn.dataset.cardKey === "play_pause") setTimeout(refreshNow, 1500);
}

// Plezy has no key for "jump to live", but WhatsOn's live links start at the live edge, so tune the same channel
// again. It's what this TV is already showing, so there's no takeover to ask about.
async function backToLive(btn) {
  btn.disabled = true;
  try {
    await api("/api/tune", { method: "POST", body: { device_id: selectedId(), channel: btn.dataset.cardLive, force: true } });
    toast("Back to live…");
    setTimeout(refreshNow, 6000);
  } catch (e) { toast(e.message); }
  btn.disabled = false;
}

// The card's remote presses must not open a new connection to the TV: a fresh remote connection can stall the picture
// for a moment in Plezy during live TV. The Remote tab avoids that by polling the TV; the card does the same while it's
// open, so the server keeps its connection (held for 2 minutes after each use) warm.
let warmTimer = null;
function keepTvWarm() {
  const sheet = $("#sheet");
  const ping = () => {
    if (!sheet.open) { clearInterval(warmTimer); warmTimer = null; return; }
    api(`/api/remote/${selectedId()}`).catch(() => {});
  };
  clearInterval(warmTimer);
  ping();
  warmTimer = setInterval(ping, 30000);
}

function openNowCard(n) {
  const body = openSheet(nowCardHtml(n));
  if (selectedId()) keepTvWarm();
  body.querySelectorAll("[data-card-key]").forEach((b) => b.addEventListener("click", () => cardKey(b)));
  body.querySelector("[data-card-live]")?.addEventListener("click", (ev) => backToLive(ev.currentTarget));
  body.querySelector("[data-close-sheet]")?.addEventListener("click", () => closeSheet());
  body.querySelector("[data-now-recap]")?.addEventListener("click", (ev) => fillFromEspn(ev.currentTarget.dataset.nowRecap, false));
  body.querySelector("[data-now-plays]")?.addEventListener("click", (ev) => fillFromEspn(ev.currentTarget.dataset.nowPlays, true));
}
