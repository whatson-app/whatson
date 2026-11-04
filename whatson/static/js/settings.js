// Settings: Source (Plex or Jellyfin), Plex (sign-in or pasted token), TVs (+ pairing wizard), Sports (leagues and teams),
// AI search (+ model dropdown), Downloads (Radarr/Sonarr, in get.js), Jellyfin.

import { $, $$, api, applyTheme, confirmDialog, debounce, esc, store, toast } from "./core.js";
import { devices, loadDevices, selectDevice } from "./player.js";
import { initDownloadsSettings, loadDownloadsSettings } from "./get.js";

export function openSettings(tab = "tvs") {
  for (const b of $$("[data-tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  for (const p of $$("[data-panel]")) p.hidden = p.dataset.panel !== tab;
  ({ source: loadSource, plex: loadPlex, tvs: renderDevices, ai: loadAI, sports: loadSportsSettings, downloads: loadDownloadsSettings, jellyfin: loadJellyfin, appearance: loadAppearance })[tab]?.()?.catch?.((e) => toast(e.message));
  if (!$("#settings").open) {
    $("#settings").showModal();
    api("/api/status").then((s) => { $("#app-version").textContent = `WhatsOn ${s.version}`; }).catch(() => {});
  }
}

// --- Source ---------------------------------------------------------------------------------------

async function loadSource() {
  const s = await api("/api/settings/source");
  const note = {
    plex: s.plex ? "Connected" : "Not connected yet",
    jellyfin: !s.jellyfin ? "Not connected yet" : s.jellyfin_user ? `Connected, as ${s.jellyfin_user}` : "Connected. Choose a user next.",
  };
  $("#src-choices").innerHTML = [["plex", "Plex"], ["jellyfin", "Jellyfin"]].map(([id, label]) => `
    <button class="choice" data-source="${id}" aria-pressed="${s.source === id}">
      <span>${label}<small>${esc(note[id])}</small></span>
      ${s.source === id ? '<span class="badge">in use</span>' : ""}
    </button>`).join("");
  return s;
}

async function pickSource(id) {
  const s = await loadSource();
  const ready = id === "plex" ? s.plex : s.jellyfin && s.jellyfin_user;
  if (!ready) return openSettings(id);   // its own tab connects it; pick it here afterwards
  if (s.source === id) return;
  const label = id === "plex" ? "Plex" : "Jellyfin";
  if (!await confirmDialog(`Use ${label} for the guide and library? Your favorite channels are cleared.`, `Use ${label}`)) return;
  await api("/api/settings/source", { method: "PUT", body: { source: id } });
  await loadSource();
  toast(`Loading the guide and library from ${label}…`);
}

// --- Jellyfin -------------------------------------------------------------------------------------

async function loadJellyfinUsers(selected) {
  const users = await api("/api/settings/jellyfin/users");
  $("#jf-user").innerHTML = `${selected ? "" : '<option value="">Choose a user</option>'}` +
    users.map((u) => `<option value="${esc(u.id)}" ${u.id === selected ? "selected" : ""}>${esc(u.name)}</option>`).join("");
}

async function loadJellyfin() {
  const j = await api("/api/settings/jellyfin");
  const f = $("#jf-form");
  f.url.value = j.url || "";
  f.key.value = "";
  f.key.placeholder = j.configured ? "Saved (leave blank to keep)" : "Jellyfin → Dashboard → API Keys";
  $("#jf-forget").hidden = !j.configured;
  const st = $("#jf-status");
  st.className = `msg ${j.configured ? "ok" : ""}`;
  st.textContent = j.configured ? `Connected to ${j.server_name || j.url}` : "Not connected";
  $("#jf-user-box").hidden = !j.configured;
  if (j.configured) await loadJellyfinUsers(j.user_id);
}

// --- Plex -----------------------------------------------------------------------------------------

const PLEX_HOW = { signin: "signed in with Plex", token: "pasted token", env: "from PLEX_URL / PLEX_TOKEN" };
let plexPoll = null;

async function loadPlex() {
  const p = await api("/api/settings/plex");
  $("#px-connected").hidden = !p.configured;
  $("#px-setup").hidden = p.configured;
  $("#px-server").textContent = p.server_name || p.url;
  $("#px-how").textContent = [PLEX_HOW[p.source], p.account].filter(Boolean).join(" · ");
  $("#px-disconnect").hidden = p.source === "env";
  $("#px-manual-box").open = false;
}

async function startPlexSignin() {
  const box = $("#px-flow");
  // Open the window now, while the click still counts, or the browser blocks the pop-up.
  const win = window.open("", "plex-signin", "width=520,height=700");
  try {
    const s = await api("/api/settings/plex/signin", { method: "POST" });
    if (win) win.location = s.auth_url;
    box.hidden = false;
    box.innerHTML = `<p>Approve WhatsOn in the Plex window.${win ? "" : ` Your browser blocked it: <a href="${esc(s.auth_url)}" target="_blank" rel="noopener">open the Plex sign-in</a>.`}</p>
      <p class="hint">Waiting for Plex…</p>`;
    clearInterval(plexPoll);
    const started = Date.now();
    plexPoll = setInterval(async () => {
      if (Date.now() - started > 10 * 60 * 1000) { clearInterval(plexPoll); box.innerHTML = '<p class="msg err">The sign-in timed out. Try again.</p>'; return; }
      const r = await api(`/api/settings/plex/signin/${s.pin_id}`).catch((e) => ({ status: "error", message: e.message }));
      if (r.status === "pending") return;
      clearInterval(plexPoll);
      if (r.status === "error") { box.innerHTML = `<p class="msg err">${esc(r.message)}</p>`; return; }
      showServers(s.pin_id, r);
    }, 2000);
  } catch (e) {
    win?.close();
    toast(e.message);
  }
}

function showServers(pinId, r) {
  const box = $("#px-flow");
  if (!r.servers.length) { box.innerHTML = `<p class="msg err">Signed in as ${esc(r.account)}, but this account has no Plex servers.</p>`; return; }
  box.innerHTML = `<p>Signed in as <b>${esc(r.account)}</b>. Which server?</p>
    <div class="choice-list">${r.servers.map((s) => `
      <button data-plex-server="${esc(s.id)}">${esc(s.name)}<span class="hint">${s.owned ? "yours" : "shared with you"}${s.presence ? "" : " · offline"}</span></button>`).join("")}</div>`;
  box.onclick = async (ev) => {
    const b = ev.target.closest("[data-plex-server]");
    if (!b) return;
    b.disabled = true;
    box.querySelector(".msg")?.remove();
    b.insertAdjacentHTML("afterend", '<p class="hint msg">Finding a way to reach it…</p>');
    try {
      await api("/api/settings/plex/server", { method: "POST", body: { pin_id: pinId, server_id: b.dataset.plexServer } });
      box.hidden = true;
      box.onclick = null;
      await loadPlex();
      toast("Plex connected. Loading the guide and library…");
    } catch (e) {
      box.querySelector(".msg").outerHTML = `<p class="msg err">${esc(e.message)}</p>`;
      b.disabled = false;
    }
  };
}

// --- TVs ------------------------------------------------------------------------------------------

async function renderDevices() {
  await loadDevices();
  // Only worth asking while Jellyfin is the source: it's how WhatsOn sees what a TV is playing.
  const { source } = await api("/api/settings/source");
  const plezys = source === "jellyfin" ? await api("/api/settings/jellyfin/devices").catch(() => []) : [];
  const link = (d) => source !== "jellyfin" ? "" : `
    <label class="d-meta">Plezy on Jellyfin
      <select data-jf-link="${d.id}">
        <option value="">Match by name</option>
        ${plezys.map((p) => `<option value="${esc(p.id)}" ${p.id === d.jellyfin_device ? "selected" : ""}>${esc(p.name)}${p.user ? ` (${esc(p.user)})` : ""}</option>`).join("")}
      </select>
    </label>`;
  $("#device-list").innerHTML = devices.length ? devices.map((d) => `
    <div class="device" data-id="${d.id}">
      <div><div class="d-name">${esc(d.name)}</div>
        <div class="d-meta">${esc(d.host)} · ${d.paired ? "paired" : "not paired"}</div>${link(d)}</div>
      <div class="d-actions">
        <button data-act="check">Check</button>
        <button data-act="rename">Rename</button>
        <button data-act="pair">${d.paired ? "Re-pair" : "Pair"}</button>
        <button data-act="remove" aria-label="Remove ${esc(d.name)}">✕</button>
      </div>
    </div>`).join("") : '<p class="hint">No TVs yet. Add one to tune from anywhere in the app.</p>';
}

async function deviceAction(id, act, btn) {
  const d = devices.find((x) => x.id === id);
  if (act === "pair") { $("#settings").close(); return wizard.open({ host: d.host, name: d.name, kind: d.kind, step: "pair" }); }
  btn.disabled = true;
  try {
    if (act === "remove") {
      if (!await confirmDialog(`Remove ${d.name}? You'd need to pair it again to use it.`, "Remove")) return;
      await api(`/api/devices/${id}`, { method: "DELETE" });
    } else if (act === "rename") {
      const name = prompt("New name", d.name);
      if (!name || name.trim() === d.name) return;
      await api(`/api/devices/${id}`, { method: "PATCH", body: { name } });
    } else if (act === "check") {
      $("#status-line").textContent = `Checking ${d.name}…`;
      const s = await api(`/api/devices/${id}/status`);
      $("#status-line").textContent = !s.reachable ? `${d.name}: ${s.reason || "not reachable"}`
        : `${d.name}: ${s.is_on ? "on" : "off"}${s.current_app ? `, showing ${s.current_app}` : ""}${s.busy ? ` (in use: ${s.reason})` : ", free to tune"}`;
    }
    await renderDevices();
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
  }
}

// --- Sports -----------------------------------------------------------------------------------------

async function loadSportsSettings() {
  const leagues = await api("/api/sports/leagues");
  const follows = await api("/api/follows");
  const teams = follows.filter((f) => f.kind === "team");
  $("#sp-leagues").innerHTML = leagues.map((l) => `
    <label class="check"><input type="checkbox" data-league="${esc(l.league)}" ${l.followed ? "checked" : ""}> ${esc(l.label)}</label>`).join("");
  $("#sp-team-league").innerHTML = leagues.map((l) => `<option value="${esc(l.league)}">${esc(l.label)}</option>`).join("");
  $("#sp-my-teams").innerHTML = teams.length ? teams.map((t) => `
    <span class="chip">${t.logo ? `<img src="${esc(t.logo)}" alt="">` : ""}${esc(t.name)}<small>${esc(leagues.find((l) => l.league === t.league)?.label || "")}</small>
      <button class="x" data-unfollow-team="${esc(t.team_id)}" data-league="${esc(t.league)}" aria-label="Unfollow ${esc(t.name)}">✕</button></span>`).join("")
    : '<span class="hint">No teams yet.</span>';
  searchTeams();
}

let teamCache = {};
const searchTeams = debounce(async () => {
  const league = $("#sp-team-league").value;
  const q = $("#sp-team-q").value.trim().toLowerCase();
  const box = $("#sp-team-results");
  if (!league) return;
  try {
    teamCache[league] ||= await api(`/api/sports/teams?league=${encodeURIComponent(league)}`);
    const hits = teamCache[league].filter((t) => !q || `${t.name} ${t.abbr}`.toLowerCase().includes(q)).slice(0, 30);
    box.innerHTML = hits.map((t) => `
      <button class="choice slim" data-follow-team='${esc(JSON.stringify({ league, team_id: t.id, name: t.name, abbr: t.abbr, logo: t.logo }))}' ${t.followed ? "disabled" : ""}>
        <span class="team">${t.logo ? `<img src="${esc(t.logo)}" alt="" loading="lazy">` : ""}${esc(t.name)}</span>
        <span class="badge">${t.followed ? "following" : "+ follow"}</span></button>`).join("") || '<p class="hint">No teams match.</p>';
  } catch (e) {
    box.innerHTML = `<p class="msg err">${esc(e.message)}</p>`;
  }
});

async function followTeam(data) {
  await api("/api/follows", { method: "POST", body: { kind: "team", ...data } });
  teamCache = {};
  await loadSportsSettings();
  toast(`Following ${data.name}.`);
}

// --- Appearance ------------------------------------------------------------------------------------

function loadAppearance() {
  const theme = store.get("theme") || "system";
  for (const r of $$('input[name="theme"]')) r.checked = r.value === theme;
}

// --- AI search --------------------------------------------------------------------------------------

let aiState = null;

function renderAIFields() {
  const form = $("#ai-form");
  const p = form.provider.value;
  form.querySelector("[data-ai-fields]").hidden = p === "none";
  $("#ai-base-url").hidden = p !== "openai";
  if (p === "none" || !aiState) return;
  const local = p === "openai" && form.base_url.value.trim();
  // Saved keys are tied to the server URL they were saved for.
  const k = form.base_url.value.trim() === aiState.base_url ? aiState.keys[p] || {} : {};
  $("#ai-key-state").textContent = k.set ? (k.source === "env" ? `(from .env ${k.hint})` : `(saved ${k.hint})`)
    : local ? "(optional for local servers)" : "(none saved)";
  $("#ai-clear-key").hidden = !(k.set && k.source === "saved");
  const def = aiState.default_models[p];
  const sel = form.model_pick;
  if (!sel.dataset.provider || sel.dataset.provider !== p) {
    sel.dataset.provider = p;
    const current = p === aiState.provider ? aiState.model : "";
    sel.innerHTML = `${def ? `<option value="">Default (${esc(def)})</option>` : '<option value="">Choose a model</option>'}
      ${current ? `<option value="${esc(current)}" selected>${esc(current)}</option>` : ""}<option value="__other">Other…</option>`;
    form.model.value = current;
  }
  form.model.hidden = sel.value !== "__other";
}

async function loadAI() {
  aiState = await api("/api/settings/ai");
  const form = $("#ai-form");
  form.provider.value = aiState.provider;
  form.base_url.value = aiState.base_url;
  form.key.value = "";
  delete form.model_pick.dataset.provider;
  $("#ai-active").textContent = aiState.active ? "● AI search is on" : "AI search is off";
  renderAIFields();
}

async function loadModels() {
  const form = $("#ai-form");
  const p = form.provider.value;
  const btn = $("#ai-load-models");
  btn.disabled = true; btn.textContent = "Loading…";
  try {
    const { models } = await api("/api/settings/ai/models", { method: "POST", body: { provider: p, base_url: form.base_url.value, key: form.key.value } });
    const def = aiState.default_models[p];
    const current = form.model_pick.value === "__other" ? form.model.value : form.model_pick.value;
    form.model_pick.innerHTML = `${def ? `<option value="">Default (${esc(def)})</option>` : '<option value="">Choose a model</option>'}
      ${models.map((m) => `<option value="${esc(m.id)}" ${m.id === current ? "selected" : ""}>${esc(m.name)}${m.note ? ` — ${esc(m.note)}` : ""}</option>`).join("")}
      <option value="__other">Other…</option>`;
    if (current && !models.some((m) => m.id === current)) { form.model_pick.value = "__other"; form.model.value = current; }
    form.model.hidden = form.model_pick.value !== "__other";
    toast(`${models.length} models available.`);
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false; btn.textContent = "Load models";
  }
}

async function saveAI(extra = {}) {
  const form = $("#ai-form");
  const p = form.provider.value;
  const model = form.model_pick.value === "__other" ? form.model.value : form.model_pick.value;
  const body = { provider: p, model, base_url: form.base_url.value, keys: {}, clear_keys: [], ...extra };
  if (form.key.value.trim() && p !== "none") body.keys[p] = form.key.value.trim();
  aiState = await api("/api/settings/ai", { method: "PUT", body });
  form.key.value = "";
  $("#ai-active").textContent = aiState.active ? "● AI search is on" : "AI search is off";
  renderAIFields();
  return aiState;
}

// --- Pairing wizard ---------------------------------------------------------------------------------
// type → find → pair → test → name. Nothing is saved until pairing succeeds; re-pairing starts at "pair".

export const wizard = {
  kind: "androidtv", host: "", name: "", deviceId: null, busy: false,
  STEPS: ["type", "find", "pair", "test", "name"],

  async open({ step = "type", host = "", name = "", kind = "androidtv" } = {}) {
    Object.assign(this, { host, name, kind, deviceId: null });
    $("#wz-title").textContent = host ? `Pair ${name || host}` : "Add a TV";
    $("#wizard").showModal();
    if (step === "pair") return this.startPairing(host);
    this.show("type");
    const types = await api("/api/tv-types");
    $("#wz-types").innerHTML = types.map((t) => `
      <button class="choice" data-kind="${esc(t.kind)}" ${t.available ? "" : "disabled"}>
        <span>${esc(t.label)}${t.kind === "androidtv" ? "<small>Chromecast with Google TV, NVIDIA Shield, Google TV sets</small>" : ""}</span>
        ${t.available ? "" : '<span class="badge">coming later</span>'}
      </button>`).join("");
  },

  show(step) {
    for (const s of $$("[data-wz]")) s.hidden = s.dataset.wz !== step;
    const i = this.STEPS.indexOf(step);
    $$(".steps li").forEach((li, j) => { li.className = j < i ? "done" : j === i ? "current" : ""; });
    for (const el of $$(".wz-tv-name")) el.textContent = this.name || this.host;
    const focus = $(`[data-wz="${step}"] input:not([type=hidden])`);
    if (focus) setTimeout(() => focus.focus(), 50);
  },

  async find() {
    this.show("find");
    const box = $("#wz-found");
    box.innerHTML = '<p class="spinner">Looking for TVs on your network…</p>';
    try {
      const found = await api(`/api/discover?kind=${encodeURIComponent(this.kind)}`);
      box.innerHTML = found.length ? found.map((f) => `
        <button class="choice" data-host="${esc(f.host)}" data-name="${esc(f.name)}">
          <span>${esc(f.name)}<small>${esc(f.host)}</small></span>
          ${f.paired ? '<span class="badge">already added</span>' : ""}
        </button>`).join("")
        : '<p class="hint">No TVs answered. Make sure the TV is on, then scan again or enter its IP address below.</p>';
      $("#wz-manual").open = !found.length;
    } catch (e) {
      box.innerHTML = `<p class="msg err">${esc(e.message)}</p>`;
    }
  },

  async startPairing(host, name = this.name) {
    this.host = host;
    this.name = name;
    this.show("pair");
    const msg = $("#wz-pair-msg");
    const form = $("#wz-code-form");
    const lead = $("#wz-pair-lead");
    form.code.value = "";
    form.hidden = lead.hidden = true;  // only ask for a code once the TV has shown one
    $("#wz-new-code").hidden = true;
    msg.className = "msg"; msg.textContent = `Asking ${this.name || host} for a code…`;
    try {
      const r = await api("/api/pair/start", { method: "POST", body: { host, kind: this.kind } });
      if (!this.name) this.name = r.name;
      this.show("pair");
      form.hidden = lead.hidden = false;
      $("#wz-new-code").hidden = false;
      form.code.focus();
      msg.textContent = "";
    } catch (e) {
      msg.className = "msg err";
      msg.textContent = e.code === "unreachable" ? `${e.message} Go back to pick another TV or check the address.` : e.message;
    }
  },

  async submitCode() {
    if (this.busy) return;
    const form = $("#wz-code-form");
    const msg = $("#wz-pair-msg");
    const code = form.code.value.trim().toUpperCase();
    if (!/^[0-9A-F]{6}$/.test(code)) {
      msg.className = "msg err"; msg.textContent = "The code is 6 characters: digits 0-9 and letters A-F.";
      return;
    }
    this.busy = true;
    form.querySelector("button").disabled = true;
    msg.className = "msg"; msg.textContent = "Pairing…";
    try {
      const r = await api("/api/pair/finish", { method: "POST", body: { host: this.host, code, name: this.name, kind: this.kind } });
      this.deviceId = r.id;
      await loadDevices();
      selectDevice(r.id);
      this.show("test");
      $("#wz-test-msg").className = "msg"; $("#wz-test-msg").textContent = "";
    } catch (e) {
      msg.className = "msg err";
      form.code.value = "";
      msg.textContent = {
        wrong_code: e.data?.restarted ? "That code didn't match. The TV is showing a new code now; type that one."
          : "That code didn't match. Press “Show a new one” and try again.",
        cancelled: "The pairing screen closed on the TV (cancelled or timed out). Press “Show a new one”.",
        expired: "That attempt timed out. Press “Show a new one”.",
      }[e.code] || e.message;
    } finally {
      this.busy = false;
      form.querySelector("button").disabled = false;
    }
  },

  async runTest(force = false) {
    const msg = $("#wz-test-msg");
    const btn = $("#wz-run-test");
    btn.disabled = true;
    msg.className = "msg"; msg.textContent = "Opening Plezy on the TV…";
    try {
      const r = await api(`/api/devices/${this.deviceId}/test`, { method: "POST", body: { force } });
      if (r.plezy) {
        msg.className = "msg ok"; msg.textContent = "✓ Plezy opened. This TV is ready.";
        btn.textContent = "Next"; btn.dataset.next = "1";
      } else {
        msg.className = "msg err";
        msg.innerHTML = `Plezy didn't come to the front${r.current_app ? ` (the TV shows ${esc(r.current_app)})` : ""}.
          Install <a href="https://github.com/edde746/plezy" target="_blank" rel="noopener">Plezy</a> on the TV and sign in, then try again.`;
        btn.textContent = "Try again";
      }
    } catch (e) {
      if (e.code === "busy" && await confirmDialog(`${e.message} The test opens Plezy and will interrupt it. Go ahead?`, "Open Plezy")) {
        btn.disabled = false;
        return this.runTest(true);
      }
      msg.className = "msg err"; msg.textContent = e.message;
    } finally {
      btn.disabled = false;
    }
  },

  async finish(name) {
    if (name && name !== this.name) await api(`/api/devices/${this.deviceId}`, { method: "PATCH", body: { name } });
    await loadDevices();
    selectDevice(this.deviceId);
    $("#wizard").close();
    toast(`${name || this.name} is ready. Pick something to watch.`);
  },
};

// --- Wiring ------------------------------------------------------------------------------------------

export function initSettings() {
  initDownloadsSettings();
  $("#settings").addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.tab) openSettings(b.dataset.tab);
    else if (b.dataset.source) pickSource(b.dataset.source).catch((e) => toast(e.message));
    else if (b.dataset.act) deviceAction(Number(b.closest(".device").dataset.id), b.dataset.act, b);
    else if (b.dataset.followTeam) followTeam(JSON.parse(b.dataset.followTeam)).catch((e) => toast(e.message));
    else if (b.dataset.unfollowTeam) {
      api(`/api/follows?kind=team&league=${encodeURIComponent(b.dataset.league)}&team_id=${encodeURIComponent(b.dataset.unfollowTeam)}`, { method: "DELETE" })
        .then(() => { teamCache = {}; return loadSportsSettings(); }).catch((e) => toast(e.message));
    }
  });
  $('[data-panel="appearance"]').addEventListener("change", (ev) => {
    store.set("theme", ev.target.value);
    applyTheme(ev.target.value);
  });
  $("#add-tv").addEventListener("click", () => { $("#settings").close(); wizard.open(); });
  $("#device-list").addEventListener("change", (ev) => {
    const id = ev.target.dataset.jfLink;
    if (id) api(`/api/devices/${id}/jellyfin`, { method: "PUT", body: { device: ev.target.value } }).then(loadDevices).catch((e) => toast(e.message));
  });
  $("#jf-user").addEventListener("change", (ev) => {
    if (ev.target.value) api("/api/settings/jellyfin/user", { method: "PUT", body: { user_id: ev.target.value } })
      .then(() => toast("Saved. Now choose Jellyfin in Settings → Source if you want it for the guide and library."))
      .catch((e) => toast(e.message));
  });

  $("#jf-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = ev.submitter || ev.target.querySelector("[type=submit]");
    btn.disabled = true;
    try {
      await api("/api/settings/jellyfin", { method: "PUT", body: { url: ev.target.url.value, key: ev.target.key.value } });
      await loadJellyfin();
    } catch (e) { $("#jf-status").className = "msg err"; $("#jf-status").textContent = e.message; } finally { btn.disabled = false; }
  });
  $("#jf-forget").addEventListener("click", async () => {
    try { await api("/api/settings/jellyfin", { method: "DELETE" }); await loadJellyfin(); } catch (e) { toast(e.message); }
  });

  $("#px-signin").addEventListener("click", startPlexSignin);
  $("#px-switch").addEventListener("click", startPlexSignin);
  $("#px-disconnect").addEventListener("click", async () => {
    if (!await confirmDialog("Disconnect Plex? The guide and library stop updating until you connect again.", "Disconnect")) return;
    try { await api("/api/settings/plex", { method: "DELETE" }); await loadPlex(); } catch (e) { toast(e.message); }
  });
  $("#px-manual").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = ev.target.querySelector("button");
    btn.disabled = true;
    try {
      await api("/api/settings/plex/manual", { method: "PUT", body: { url: ev.target.url.value, token: ev.target.token.value } });
      ev.target.reset();
      await loadPlex();
      toast("Plex connected. Loading the guide and library…");
    } catch (e) { toast(e.message); } finally { btn.disabled = false; }
  });

  $("#sp-leagues").addEventListener("change", async (ev) => {
    const lg = ev.target.dataset.league;
    if (!lg) return;
    try {
      if (ev.target.checked) await api("/api/follows", { method: "POST", body: { kind: "league", league: lg } });
      else await api(`/api/follows?kind=league&league=${encodeURIComponent(lg)}`, { method: "DELETE" });
    } catch (e) { toast(e.message); }
  });
  $("#sp-team-league").addEventListener("change", searchTeams);
  $("#sp-team-q").addEventListener("input", searchTeams);


  const aiForm = $("#ai-form");
  aiForm.addEventListener("change", (ev) => {
    if (ev.target.name === "provider") { delete aiForm.model_pick.dataset.provider; renderAIFields(); }
    if (ev.target.name === "model_pick") aiForm.model.hidden = ev.target.value !== "__other";
  });
  aiForm.base_url.addEventListener("input", () => renderAIFields());
  $("#ai-load-models").addEventListener("click", loadModels);
  aiForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      const s = await saveAI();
      const p = s.provider;
      toast(s.active ? "Saved. AI search is on."
        : p === "none" ? "Saved. AI search is off."
        : s.key_required && !s.keys[p]?.set ? "Saved, but AI search stays off until a key is added."
        : "Saved, but AI search stays off until a model is chosen.");
    } catch (e) { toast(e.message); }
  });
  $("#ai-clear-key").addEventListener("click", async () => {
    const p = aiForm.provider.value;
    if (!await confirmDialog(`Remove the saved ${p} key?`, "Remove")) return;
    try { await saveAI({ clear_keys: [p] }); toast("Key removed."); } catch (e) { toast(e.message); }
  });
  $("#ai-test").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const out = $("#ai-result");
    const btn = ev.target.querySelector("button");
    out.hidden = false; out.textContent = "Asking…"; btn.disabled = true;
    try {
      const r = await api("/api/settings/ai/test", { method: "POST", body: { query: ev.target.query.value } });
      out.textContent = r.ok ? `✓ ${r.ms} ms\n${r.note}\n\n${JSON.stringify(r.filters, null, 2)}` : `✗ ${r.error}`;
    } catch (e) {
      out.textContent = `✗ ${e.message}`;
    } finally {
      btn.disabled = false;
    }
  });

  // Wizard
  $("#wz-types").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-kind]");
    if (b && !b.disabled) { wizard.kind = b.dataset.kind; wizard.find(); }
  });
  $("#wz-found").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-host]");
    if (b) wizard.startPairing(b.dataset.host, b.dataset.name);
  });
  $("#wz-rescan").addEventListener("click", () => wizard.find());
  $("#wz-manual-form").addEventListener("submit", (ev) => { ev.preventDefault(); wizard.startPairing(ev.target.host.value.trim(), ""); });
  $("#wz-code-form").addEventListener("submit", (ev) => { ev.preventDefault(); wizard.submitCode(); });
  $("#wz-code-form").code.addEventListener("input", (ev) => {
    ev.target.value = ev.target.value.toUpperCase().replace(/[^0-9A-F]/g, "").slice(0, 6);
    if (ev.target.value.length === 6) wizard.submitCode();
  });
  $("#wz-new-code").addEventListener("click", () => wizard.startPairing(wizard.host));
  $("#wz-back").addEventListener("click", () => wizard.find());
  $("#wz-run-test").addEventListener("click", (ev) => {
    if (ev.currentTarget.dataset.next) { wizard.show("name"); $("#wz-name-form").name.value = wizard.name; return; }
    wizard.runTest();
  });
  $("#wz-skip-test").addEventListener("click", () => { wizard.show("name"); $("#wz-name-form").name.value = wizard.name; });
  $("#wz-name-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try { await wizard.finish(ev.target.name.value.trim()); } catch (e) { toast(e.message); }
  });
  $("#wizard").addEventListener("close", () => {
    const b = $("#wz-run-test");
    b.textContent = "Open Plezy on the TV"; delete b.dataset.next;
    loadDevices().catch(() => {});
  });
}
