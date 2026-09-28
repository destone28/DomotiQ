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
  staff: stored("domotiq.staff") || "",
  listeners: new Set(),
};

export function setNickname(name) {
  store.nickname = (name || "").trim().slice(0, 30);
  try { localStorage.setItem("domotiq.nickname", store.nickname); } catch (e) { /* ignore */ }
}

export function setStaff(token) {
  store.staff = token || "";
  try { token ? localStorage.setItem("domotiq.staff", token) : localStorage.removeItem("domotiq.staff"); } catch (e) { /* ignore */ }
  emit("staff");
}

export function isStaff() { return !!store.staff; }

export function on(fn) { store.listeners.add(fn); return () => store.listeners.delete(fn); }
function emit(type) { for (const fn of [...store.listeners]) { try { fn(type); } catch (e) { console.error(e); } } }

// ------------------------------------------------------------------ API
export async function api(method, path, body, opts = {}) {
  const headers = { "X-Device": store.device, "X-Nickname": encodeURIComponent(store.nickname || "") };
  if (store.staff) headers["X-Staff"] = store.staff;
  let payload;
  if (body instanceof Blob || body instanceof ArrayBuffer) {
    payload = body;
    headers["Content-Type"] = opts.type || "application/octet-stream";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 401 && store.staff) setStaff("");
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
let ws = null;
let retry = 1000;
let pingTimer = null;

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    retry = 1000;
    store.online = true;
    emit("online");
    clearInterval(pingTimer);
    pingTimer = setInterval(() => { try { ws.send("ping"); } catch (e) { /* closed */ } }, 15000);
  };
  ws.onclose = () => {
    store.online = false;
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
      s.scene = msg.data.scene; s.party = msg.data.party; s.grill = msg.data.grill; s.car = msg.data.car;
      s.language = msg.data.language; s.verbosity = msg.data.verbosity;
      break;
    case "totem": s.distance = msg.data.distance; s.visitor = msg.data.visitor; break;
    case "status": s.status = msg.data; renderStatus(); break;
    case "sim": s.sim = msg.data; break;
    case "clock": s.clock = msg.data; break;
    case "registration": {
      const list = (s.registrations || []).filter(r => r.id !== msg.data.id);
      if (["waiting", "choose", "confirm"].includes(msg.data.status)) list.push(msg.data);
      s.registrations = list;
      break;
    }
    case "notify": toast(tr(msg.data.text), msg.data.level); break;
    case "say": subtitle(msg.data.text); break;
  }
  emit(msg.type);
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
  subTimer = setTimeout(() => { el.hidden = true; }, Math.max(3500, text.length * 90));
}

export function modal(build) {
  const m = document.getElementById("modal");
  const card = m.querySelector(".modal-card");
  card.innerHTML = "";
  const close = () => { m.hidden = true; card.innerHTML = ""; };
  build(card, close);
  m.hidden = false;
  m.onclick = (e) => { if (e.target === m) close(); };
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
  let html = "";
  if (!store.online) html += `<div class="banner ask"><span class="grow">${t("status.offline")}</span></div>`;
  for (const a of s.alerts || []) {
    html += `<div class="banner alarm"><span>⚠️</span><span class="grow">${esc(tr(a.name))}${a.who ? " — " + esc(a.who) : ""}${a.room ? " · " + esc(roomName(a.room)) : ""}</span></div>`;
  }
  for (const c of s.confirmations || []) {
    html += `<div class="banner ask" data-cid="${c.id}"><span class="grow">${esc(tr(c.question))}</span>` +
      c.options.map((o, i) => `<button data-i="${i}">${esc(tr(o.label))}</button>`).join("") + `</div>`;
  }
  el.innerHTML = html;
  el.querySelectorAll(".banner[data-cid] button").forEach(b => {
    b.onclick = async () => {
      const cid = b.closest(".banner").dataset.cid;
      const c = s.confirmations.find(x => x.id === cid);
      if (!c) return;
      try { await api("POST", `/api/confirm/${cid}`, { value: c.options[+b.dataset.i].value }); } catch (e) { /* answered elsewhere */ }
    };
  });
}

// ------------------------------------------------------------------ navigation
const SCREENS = {
  home: "./screens/home.js", live: "./screens/live.js", commands: "./screens/commands.js",
  events: "./screens/events.js", more: "./screens/more.js", rules: "./screens/rules.js",
  identities: "./screens/identities.js", sim: "./screens/sim.js", calibration: "./screens/calibration.js",
  diagnostics: "./screens/diagnostics.js", settings: "./screens/settings.js", about: "./screens/about.js",
};
const NAV_OF = { rules: "more", identities: "more", sim: "more", calibration: "more", diagnostics: "more", settings: "more", about: "more" };

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
