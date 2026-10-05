// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// The web app shell: state from the house, navigation, notifications.

import { lang, setLang, t, tr } from "./i18n.js";

// ------------------------------------------------------------------ identity of this phone
function stored(key, make) {
  try {
    let v = localStorage.getItem(key);
    if (!v && make) { v = make(); localStorage.setItem(key, v); }
    return v;
  } catch (e) { return make ? make() : null; }
}
function randomId() {
  const a = new Uint8Array(8);
  (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach((_, i) => { a[i] = Math.random() * 256; });
  return "p-" + Array.from(a, b => b.toString(16).padStart(2, "0")).join("");
}

export const store = {
  state: null,
  online: false,
  device: stored("domotiq.device", randomId),
  nickname: stored("domotiq.nickname") || "",
  listeners: new Set(),
};

export function setNickname(name) {
  store.nickname = (name || "").trim().slice(0, 30);
  try { localStorage.setItem("domotiq.nickname", store.nickname); } catch (e) { /* ignore */ }
}

export function on(fn) { store.listeners.add(fn); return () => store.listeners.delete(fn); }
function emit(type) { for (const fn of [...store.listeners]) { try { fn(type); } catch (e) { console.error(e); } } }

// ------------------------------------------------------------------ API
export async function api(method, path, body, opts = {}) {
  const headers = { "X-Device": store.device, "X-Nickname": encodeURIComponent(store.nickname || "") };
  let payload;
  if (body instanceof Blob || body instanceof ArrayBuffer) {
    payload = body;
    headers["Content-Type"] = opts.type || "application/octet-stream";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { method, headers, body: payload });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch (e) { /* not json */ }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res;
}

// ------------------------------------------------------------------ websocket
// the version of the files this page was loaded with (in the address of this very script): after an update of
// the house the phone reloads by itself, instead of going on with the old pages
const LOADED = (import.meta.url.match(/\/static\/v([0-9a-f]+)\//) || [])[1] || null;
let ws = null;
let retry = 1000;
let pingTimer = null;

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  // the phone says who it is in the address: a websocket cannot carry headers
  const who = `device=${encodeURIComponent(store.device)}&nick=${encodeURIComponent(store.nickname || "")}`;
  ws = new WebSocket(`${proto}://${location.host}/ws?${who}`);
  ws.onopen = () => {
    retry = 1000;
    store.online = true;
    emit("online");
    clearInterval(pingTimer);
    pingTimer = setInterval(() => { try { ws.send("ping"); } catch (e) { /* closed */ } }, 15000);
  };
  ws.onclose = () => {
    store.online = false;
    listening(false);
    emit("online");
    clearInterval(pingTimer);
    setTimeout(connect, retry);
    retry = Math.min(retry * 2, 10000);
  };
  ws.onmessage = (m) => {
    let msg;
    try { msg = JSON.parse(m.data); } catch (e) { return; }
    handle(msg);
  };
}

function handle(msg) {
  const s = store.state;
  switch (msg.type) {
    case "hello":
      if (LOADED && msg.data.static_version && msg.data.static_version !== LOADED) {
        location.reload();
        return;
      }
      store.state = msg.data;
      syncClock();
      emit("hello");
      return;
    case "pong":
      return;
  }
  if (!s) return;
  switch (msg.type) {
    case "tracks": s.tracks = msg.data; break;
    case "lights": s.lights = msg.data; break;
    case "sensors": Object.assign(s, msg.data); break;
    case "counts": s.counts = msg.data; break;
    case "alerts": s.alerts = msg.data; renderBanners(); break;
    case "confirmations": s.confirmations = msg.data; renderBanners(); break;
    case "identities": s.identities = msg.data; break;
    case "rules": s.rules = msg.data; break;
    case "house":
      Object.assign(s.brief, msg.data);
      s.armed = msg.data.armed;
      if (msg.event === "armed") renderBanners();
      s.scene = msg.data.scene; s.party = msg.data.party; s.grill = msg.data.grill; s.car = msg.data.car;
      s.language = msg.data.language; s.verbosity = msg.data.verbosity;
      break;
    case "status": s.status = msg.data; renderStatus(); break;
    case "sim": s.sim = msg.data; break;
    case "clock": s.clock = msg.data; break;
    case "follow": s.follow = msg.data.on; break;
    case "registration": {
      const list = (s.registrations || []).filter(r => r.id !== msg.data.id);
      if (["waiting", "choose", "confirm"].includes(msg.data.status)) list.push(msg.data);
      s.registrations = list;
      renderBanners();
      break;
    }
    case "notify": toast(tr(msg.data.text), msg.data.level); break;
    case "say": subtitle(msg.data.text); break;
    case "listening": listening(!!msg.data.on); break;
    case "welcome": welcome(msg.data); break;
  }
  emit(msg.type);
}

// ------------------------------------------------------------------ welcome of a new phone
// The house greets aloud a phone that opens the web app for the first time and asks the name:
// it can be said aloud (the house then sends it here) or typed on this card.
let queuedWelcome = null;

function welcome(d) {
  const open = !document.getElementById("modal").hidden;
  if (d.stage === "named") {
    if (!d.name || d.name === store.nickname) return;     // typed on this phone: the card is already there
    setNickname(d.name);
  }
  if (d.stage === "ask" && document.querySelector('#modal [data-welcome="ask"]')) return;  // already open
  if (open && !document.querySelector("#modal [data-welcome]")) { queuedWelcome = d; return; }  // after the other card
  if (d.stage === "ask" && !store.nickname) return askName(!!d.listening);
  invite(d.name || store.nickname);
}

function askName(listening) {
  modal((card, close) => {
    card.innerHTML = `<h2 style="margin-top:0" data-welcome="ask">👋 ${t("welcome.title")}</h2>
      <p>${t(listening ? "welcome.ask_voice" : "welcome.ask")}</p>
      <label class="field"><span>${t("welcome.name")}</span><input type="text" id="wname" maxlength="30" autocomplete="given-name"></label>
      <div class="row" style="justify-content:flex-end;margin-top:12px">
        <button class="btn" data-a="later">${t("welcome.later")}</button>
        <button class="btn primary" data-a="ok">${t("common.ok")}</button></div>`;
    const input = card.querySelector("#wname");
    const send = async () => {
      const name = input.value.trim();
      if (!name) { input.focus(); return; }
      try {
        await api("POST", "/api/welcome", { name });
        setNickname(name);
        close();
        invite(name);
      } catch (e) { toast(e.message, "alarm"); }
    };
    card.querySelector('[data-a=ok]').onclick = send;
    card.querySelector('[data-a=later]').onclick = () => {
      close();
      api("POST", "/api/welcome", { later: true }).catch(() => {});   // the house stops asking
    };
    input.onkeydown = (e) => { if (e.key === "Enter") send(); };
  }, { sticky: true });
}

function invite(name) {
  modal((card, close) => {
    card.innerHTML = `<h2 style="margin-top:0" data-welcome="invite">${name ? t("welcome.hi", { name: esc(name) }) : "👋 " + t("welcome.title")}</h2>
      <p>${t("welcome.invite")}</p>
      <div class="row" style="justify-content:flex-end;margin-top:12px">
        <button class="btn" data-a="later">${t("welcome.later")}</button>
        <button class="btn primary" data-a="add">+ ${t("welcome.add")}</button></div>`;
    card.querySelector('[data-a=later]').onclick = close;
    card.querySelector('[data-a=add]').onclick = () => { close(); go("identities", { add: "1" }); };
  });
}

// while the house listens without the Talk button (a name, the answer to a question)
function listening(on) {
  const el = document.getElementById("listening");
  if (!el) return;
  el.textContent = "🎙️ " + t("listen.on");
  el.hidden = !on;
}

async function syncClock() {
  const c = store.state && store.state.clock;
  if (!c) return;
  const drift = Math.abs(Date.now() / 1000 - c.now);
  if (!c.known || drift > 60) {
    try {
      const r = await api("POST", "/api/time", { epoch: Date.now() / 1000 });
      if (r.changed) toast(t("time.set"));
    } catch (e) { /* not important */ }
  }
}

// ------------------------------------------------------------------ feedback
export function toast(text, level = "info", ms = 4000) {
  if (!text) return;
  const el = document.createElement("div");
  el.className = `toast ${level}`;
  el.textContent = text;
  // a tap closes it before its time
  const close = document.createElement("button");
  close.className = "close";
  close.textContent = "✕";
  close.setAttribute("aria-label", t("common.close"));
  el.appendChild(close);
  el.onclick = () => el.remove();
  document.getElementById("toasts").appendChild(el);
  if (level === "alarm" && navigator.vibrate) { try { navigator.vibrate([200, 100, 200]); } catch (e) { /* ignore */ } }
  setTimeout(() => el.remove(), ms);
}

let subTimer = null;
function subtitle(text) {
  const el = document.getElementById("subtitle");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(subTimer);
  subTimer = setTimeout(() => { el.hidden = true; }, Math.min(15000, Math.max(3500, text.length * 90)));
}

export function modal(build, { sticky = false } = {}) {
  const m = document.getElementById("modal");
  const card = m.querySelector(".modal-card");
  card.innerHTML = "";
  const close = () => {
    m.hidden = true; card.innerHTML = "";
    if (queuedWelcome) { const d = queuedWelcome; queuedWelcome = null; setTimeout(() => welcome(d), 300); }
  };
  build(card, close);
  m.hidden = false;
  // a sticky card does not close on a tap outside (on a phone that is also how the keyboard is hidden)
  m.onclick = (e) => { if (e.target === m && !sticky) close(); };
  return close;
}

export function ask(question) {
  return new Promise((resolve) => {
    modal((card, close) => {
      card.innerHTML = `<p style="font-weight:600">${esc(question)}</p>
        <div class="row" style="justify-content:flex-end"><button class="btn" data-a="no">${t("common.cancel")}</button>
        <button class="btn danger" data-a="yes">${t("common.ok")}</button></div>`;
      card.querySelector('[data-a=no]').onclick = () => { close(); resolve(false); };
      card.querySelector('[data-a=yes]').onclick = () => { close(); resolve(true); };
    });
  });
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function roomName(id) {
  if (!id) return "";
  if (id === "outside") return lang() === "it" ? "fuori" : "outside";
  const r = store.state && store.state.layout.rooms.find(x => x.id === id);
  return r ? tr(r.name) : id;
}

export function identityName(id) {
  const i = store.state && store.state.identities.find(x => x.id === id);
  return i ? i.name : "";
}

function renderStatus() {
  const s = store.state;
  const el = document.getElementById("status-dots");
  if (!s) return;
  const st = s.status || {};
  const parts = [["mcu", st.mcu], ["camera", st.camera], ["audio", st.audio]];
  el.innerHTML = parts.map(([k, ok]) => `<i class="${ok ? "ok" : "bad"}" title="${t("status." + k)}"></i>`).join("") +
    (st.simulation ? `<i class="sim" title="${t("status.sim")}"></i>` : "");
  el.title = parts.map(([k, ok]) => `${t("status." + k)}: ${ok ? "OK" : "—"}`).join(" · ");
}

export function renderBanners() {
  const el = document.getElementById("banners");
  const s = store.state;
  if (!s) { el.innerHTML = ""; return; }
  const close = `<button class="close" data-close="1" aria-label="${esc(t("common.close"))}">✕</button>`;
  let html = "";
  if (!store.online) html += `<div class="banner offline"><span class="ico">📡</span><span class="grow">${t("status.offline")}</span></div>`;
  // red an alarm, amber a warning; an alarm of the rules can be switched off from here, like a burglar alarm
  for (const a of s.alerts || []) {
    const loud = a.level === "alarm";
    const where = [a.who, a.room ? roomName(a.room) : ""].filter(Boolean).join(" · ");
    html += `<div class="banner ${loud ? "alarm" : "warning"}"><span class="ico">${loud ? "🚨" : "⚠️"}</span>` +
      `<span class="grow">${esc(tr(a.name))}${where ? `<small>${esc(where)}</small>` : ""}</span>` +
      (a.rule && (s.brief || {}).armed !== false ? `<button data-disarm="1">${esc(t("alarm.disarm"))}</button>` : "") +
      `<button class="close" data-alert="${esc(a.key)}" aria-label="${esc(t("common.close"))}">✕</button></div>`;
  }
  for (const r of s.registrations || []) {
    if (r.origin !== "web" && r.status === "choose") {
      html += `<div class="banner ask"><div class="head"><span class="ico">✨</span><span class="grow">` +
        `<span class="kicker">${esc(t("reg.from_voice"))}</span>${esc(r.name)}</span></div>` +
        `<div class="opts"><button class="pri" data-reg="${esc(r.id)}">${esc(t("reg.choose"))}</button></div></div>`;
    }
  }
  for (const c of s.confirmations || []) {
    // a question of the house: a registered one, all of them together, a new name with what it really is,
    // or nothing there at all
    const cats = ["person", "dog", "cat", "animal", "car", "object"];
    html += `<div class="banner ask" data-cid="${c.id}"><div class="head"><span class="ico">❓</span>` +
      `<span class="grow"><span class="kicker">${esc(t("ask.title"))}</span>${esc(tr(c.question))}</span>${close}</div>` +
      `<div class="opts">` +
      c.options.map((o, i) => `<button class="pri" data-i="${i}">${esc(tr(o.label))}</button>`).join("") +
      // two figurines touching are one blob: "both of them" is an answer too
      (c.options.length >= 2 ? `<button data-both="1">${esc(t(c.options.length > 2 ? "ask.all" : "ask.both"))}</button>` : "") +
      (c.who ? `<button class="quiet" data-nothing="1">${esc(t("ask.nothing"))}</button>` : "") +
      `</div>` +
      (c.allow_name ? `<div class="new"><input class="newname" maxlength="40" placeholder="${esc(t("ask.new_name"))}">` +
        (c.who ? `<select class="newcat">${cats.map(k => `<option value="${k}"${k === c.category ? " selected" : ""}>${esc(t("cat." + k))}</option>`).join("")}</select>` : "") +
        `<button class="pri" data-new="1">${esc(t("ask.add"))}</button></div>` : "") +
      `</div>`;
  }
  el.innerHTML = html;
  el.querySelectorAll("button[data-reg]").forEach(b => { b.onclick = () => go("identities", { reg: b.dataset.reg }); });
  // an alarm closed on one phone disappears on all of them
  el.querySelectorAll("button[data-alert]").forEach(b => {
    b.onclick = async () => {
      b.closest(".banner").remove();
      try { await api("POST", `/api/alerts/${encodeURIComponent(b.dataset.alert)}/dismiss`, {}); } catch (e) { /* gone already */ }
    };
  });
  el.querySelectorAll("button[data-disarm]").forEach(b => {
    b.onclick = async () => {
      try { await api("POST", "/api/commands/alarm", { armed: false }); } catch (e) { toast(e.message, "alarm"); }
    };
  });
  el.querySelectorAll(".banner[data-cid] button").forEach(b => {
    b.onclick = async () => {
      const banner = b.closest(".banner");
      const cid = banner.dataset.cid;
      const c = s.confirmations.find(x => x.id === cid);
      if (!c) return;
      let value;
      if (b.dataset.close) {
        // closed on one phone: the question goes away everywhere
        banner.remove();
        try { await api("POST", `/api/confirm/${cid}/close`, {}); } catch (e) { /* answered meanwhile */ }
        return;
      }
      if (b.dataset.nothing) {
        value = { nothing: true };
      } else if (b.dataset.both) {
        value = { together: c.options.map(o => o.value) };
      } else if (b.dataset.new) {
        const name = banner.querySelector(".newname").value.trim();
        if (!name) { banner.querySelector(".newname").focus(); return; }
        const cat = banner.querySelector(".newcat");
        value = cat ? { name, category: cat.value } : { name };
      } else {
        value = c.options[+b.dataset.i].value;
      }
      // the first answer wins, aloud or from any phone: a late one is simply ignored
      try { await api("POST", `/api/confirm/${cid}`, { value }); } catch (e) { /* answered elsewhere */ }
    };
  });
  el.querySelectorAll(".banner input.newname").forEach(inp => {
    inp.onkeydown = (e) => { if (e.key === "Enter") inp.closest(".banner").querySelector("button[data-new]").click(); };
  });
}

// a page starts with its title, a line about it and its main action
export function pageHead(title, lead, actions = "") {
  return `<header class="page-head"><div class="title-row"><h1>${title}</h1>` +
    (actions ? `<div class="actions">${actions}</div>` : "") + `</div>` +
    (lead ? `<p class="lead">${lead}</p>` : "") + `</header>`;
}

// ------------------------------------------------------------------ navigation
const SCREENS = {
  home: "./screens/home.js", live: "./screens/live.js", commands: "./screens/commands.js",
  events: "./screens/events.js", more: "./screens/more.js", rules: "./screens/rules.js",
  identities: "./screens/identities.js", sim: "./screens/sim.js", calibration: "./screens/calibration.js",
  diagnostics: "./screens/diagnostics.js", settings: "./screens/settings.js", about: "./screens/about.js",
};
const NAV_OF = { rules: "more", events: "more", sim: "more", calibration: "more", diagnostics: "more", settings: "more", about: "more" };

let current = null;

export function go(name, params) {
  const hash = "#/" + name + (params ? "?" + new URLSearchParams(params) : "");
  if (location.hash !== hash) location.hash = hash; else show();
}

async function show() {
  const [name, query] = (location.hash.replace(/^#\//, "") || "home").split("?");
  const key = SCREENS[name] ? name : "home";
  const params = Object.fromEntries(new URLSearchParams(query || ""));
  if (current && current.unmount) current.unmount();
  current = null;
  const main = document.getElementById("screen");
  main.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  document.querySelectorAll("nav.bottom button").forEach(b => {
    b.setAttribute("aria-current", b.dataset.go === (NAV_OF[key] || key) ? "page" : "false");
  });
  if (!store.state) return;
  const mod = await import(SCREENS[key]);
  main.innerHTML = "";
  current = mod.mount(main, params) || {};
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function translateStatic() {
  document.querySelectorAll("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
  document.getElementById("lang-toggle").textContent = lang().toUpperCase();
  const s = store.state;
  if (s) document.getElementById("house-name").textContent = tr(s.house && s.house.name);
}

// ------------------------------------------------------------------ start
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-go]");
  if (b) { e.preventDefault(); go(b.dataset.go); }
});
document.getElementById("lang-toggle").onclick = () => {
  setLang(lang() === "it" ? "en" : "it");
  translateStatic();
  show();
};
window.addEventListener("hashchange", show);

on((type) => {
  if (type === "hello") { translateStatic(); renderStatus(); renderBanners(); show(); return; }
  if (type === "online") renderBanners();
  if (current && current.update) {
    try { current.update(type); } catch (e) { console.error(e); }
  }
});

setLang(lang());
translateStatic();
connect();
