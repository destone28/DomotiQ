// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// The virtual house: the alarm, the plan, who is where, lights, climate, car.

import { api, ask, chooseIdentity, esc, identityName, modal, pageHead, roomName, store, toast } from "../app.js";
import { celsius, t, tr } from "../i18n.js";
import { ICONS, Plan, toFloor } from "../plan.js";

export function mount(root) {
  root.innerHTML = `
    ${pageHead(t("home.title"), t("home.lead"))}
    <div class="plan-wrap" id="plan"></div>
    <div class="row spread" style="margin:6px 4px">
      <p class="muted small grow" id="plan-hint">${t("home.tap_hint")}</p>
      <button class="btn small" id="add-unseen">➕ ${t("add.button")}</button>
    </div>
    <h2>${t("home.status")}</h2>
    <div class="status-grid" id="cards"></div>
    <h2>${t("home.who")}</h2>
    <div class="card"><ul class="list" id="who"></ul></div>
    <h2>${t("alarm.title")}</h2>
    <div class="card alarm-card" id="alarm"></div>`;
  const plan = new Plan(root.querySelector("#plan"), store.state, { onTap: (id) => showTrack(id) });
  pointToAdd(root, plan);
  const render = () => {
    renderAlarm(root.querySelector("#alarm"));
    plan.update(store.state);
    renderCards(root.querySelector("#cards"));
    renderWho(root.querySelector("#who"));
  };
  render();
  return {
    update(type) {
      if (["tracks", "lights", "sensors", "counts", "alerts", "house", "identities", "hello", "status"].includes(type)) render();
    },
  };
}

// The tracks arrive five times a second: a part of the page is drawn again only when what it shows changed, or a
// tap whose button is replaced between press and release would be lost
function changed(el, html) {
  if (el._html === html) return false;
  el._html = html;
  el.innerHTML = html;
  return true;
}

// something the house does not follow (it took it for the empty house, or never saw it put down): tapped on the plan,
// it becomes a presence, and the phone asks who it is
function pointToAdd(root, plan) {
  const btn = root.querySelector("#add-unseen");
  const hint = root.querySelector("#plan-hint");
  let picking = false;
  const stop = () => {
    picking = false;
    plan.svg.classList.remove("picking");
    hint.textContent = t("home.tap_hint");
    btn.textContent = "➕ " + t("add.button");
  };
  btn.onclick = () => {
    if (picking) { stop(); return; }
    picking = true;
    plan.svg.classList.add("picking");
    hint.textContent = t("add.tap_plan");
    btn.textContent = t("common.cancel");
  };
  plan.svg.addEventListener("click", async (e) => {
    if (!picking || e.target.closest("[data-id]")) return;
    const p = toFloor(plan.svg, e.clientX, e.clientY);
    stop();
    await adopt({ x: Math.round(p.x), y: Math.round(p.y) });
  });
}

export async function adopt(where) {
  try {
    const r = await api("POST", "/api/tracks/adopt", where);
    if (r.ok) chooseIdentity(r.track);
    else toast(t(r.error === "nothing" ? "add.nothing" : "add.not_ready"), "warning");
  } catch (e) { toast(e.message, "alarm"); }
}

// on and off like a burglar alarm: off, the rules that raise alarms stay quiet
function renderAlarm(el) {
  const s = store.state;
  const armed = (s.brief || {}).armed !== false;
  const ringing = armed && (s.alerts || []).some(a => a.rule && a.level === "alarm");
  el.className = "card alarm-card " + (ringing ? "ringing" : armed ? "on" : "off");
  if (!changed(el, `<span class="shield">${ringing ? "🚨" : "🛡️"}</span>
    <span class="grow"><span class="muted small">${t("alarm.title")}</span>
      <span class="state" style="display:block">${ringing ? t("alarm.ringing") : armed ? t("alarm.on") : t("alarm.off")}</span>
      <span class="muted small">${armed ? t("alarm.on_hint") : t("alarm.off_hint")}</span></span>
    <button class="btn ${armed ? "" : "primary"}" id="arm">${armed ? t("alarm.disarm") : t("alarm.arm")}</button>`)) return;
  el.querySelector("#arm").onclick = async () => {
    try { await api("POST", "/api/commands/alarm", { armed: !armed }); } catch (e) { toast(e.message, "alarm"); }
  };
}

function renderCards(el) {
  const s = store.state;
  const th = (s.sensors || {}).thermostat || {};
  const ba = (s.sensors || {}).bathroom || {};
  const persons = Object.entries(s.counts || {}).filter(([r]) => r !== "outside" && r !== "driveway")
    .reduce((n, [, c]) => n + (c.persons || 0), 0);
  const climate = s.climate === "hot" ? t("home.climate.hot") : s.climate === "cold" ? t("home.climate.cold") : "";
  const scene = s.scenes && s.scenes[s.scene] ? tr(s.scenes[s.scene].name) : s.scene;
  changed(el, `
    <div class="card"><div class="label">👥 ${t("home.people")}</div><div class="stat num">${persons}</div></div>
    <div class="card"><div class="label">🌡️ ${t("home.thermostat")}</div>
      <div class="stat">${th.t != null ? celsius(th.t) : "—"}</div>
      <div class="small muted">${th.rh != null ? `${t("home.humidity")} ${Math.round(th.rh)}%` : ""}${climate ? " · " + esc(climate) : ""}</div></div>
    <div class="card"><div class="label">🚿 ${t("home.bathroom")}</div>
      <div class="stat">${ba.t != null ? celsius(ba.t) : "—"}</div>
      <div class="small muted">${ba.rh != null ? `${t("home.humidity")} ${Math.round(ba.rh)}%` : ""}${s.shower ? " · " + t("home.shower") : ""}</div></div>
    <div class="card"><div class="label">🚗 ${t("home.car")}</div><div class="stat" style="font-size:18px">${esc(t("car." + (s.car || "absent")))}</div></div>
    <div class="card"><div class="label">🎬 ${t("home.scene")}</div><div class="stat" style="font-size:18px">${esc(scene)}</div></div>
    <div class="card"><div class="label">🎉 ${t("home.party")} · 🔥 ${t("home.grill")}</div><div class="pill-list" style="margin-top:6px">
      ${s.party ? `<span class="chip on">🎉 ${t("home.party")}</span>` : ""}
      ${s.grill ? `<span class="chip warn">🔥 ${t("home.grill")}</span>` : ""}
      ${!s.party && !s.grill ? `<span class="muted small">${t("home.nothing_on")}</span>` : ""}
    </div></div>`);
}

function renderWho(el) {
  const s = store.state;
  const tracks = [...(s.tracks || [])].sort((a, b) => (a.room || "").localeCompare(b.room || ""));
  if (!tracks.length) { changed(el, `<li class="empty">${t("home.nobody")}</li>`); return; }
  if (!changed(el, tracks.map(tk => {
    const name = identityName(tk.identity) || (tk.category === "person" ? t("home.guest") : t("home.unknown"));
    return `<li><button class="link" data-id="${tk.id}">
      <span class="silhouette" style="background:${esc(tk.color)}"><svg viewBox="0 0 24 24"><path d="${ICONS[tk.category] || ICONS.object}"/></svg></span>
      <span class="grow"><span class="title">${esc(name)}${tk.uncertain ? " ?" : ""}</span>
      <span class="sub">${esc(t("cat." + tk.category))} · ${esc(roomName(tk.room))}</span></span></button></li>`;
  }).join(""))) return;
  el.querySelectorAll("button[data-id]").forEach(b => { b.onclick = () => showTrack(b.dataset.id); });
}

function showTrack(id) {
  const tk = (store.state.tracks || []).find(x => x.id === id);
  if (!tk) return;
  const ident = store.state.identities.find(i => i.id === tk.identity);
  modal((card, close) => {
    const name = ident ? ident.name : (tk.category === "person" ? t("home.guest") : t("home.unknown"));
    card.innerHTML = `
      <div class="row">
        ${ident && ident.photo ? `<img class="photo" src="/api/photos/${encodeURIComponent(ident.photo)}" alt="">` :
          `<span class="silhouette" style="background:${esc(tk.color)}"><svg viewBox="0 0 24 24"><path d="${ICONS[tk.category] || ICONS.object}"/></svg></span>`}
        <div class="grow"><div class="title" style="font-size:18px">${esc(name)}</div>
        <div class="muted">${esc(t("cat." + tk.category))} · ${t("home.in")} ${esc(roomName(tk.room))}</div></div>
      </div>
      ${tk.uncertain ? `<p class="muted">${t("home.uncertain")}</p>` : ""}
      <div class="row" style="justify-content:flex-end;margin-top:12px;flex-wrap:wrap">
        <button class="btn ghost" id="remove">🗑️ ${t("home.remove")}</button>
        <button class="btn ${ident ? "" : "primary"}" id="who">👤 ${t(ident ? "home.not_this" : "home.who_is")}</button>
        <button class="btn" id="close">${t("common.close")}</button>
      </div>`;
    card.querySelector("#close").onclick = close;
    // known or new: chosen from every character the house knows, or a new name
    card.querySelector("#who").onclick = () => { close(); chooseIdentity(tk.id); };
    // seen by mistake (a reflection, a light, a module): it goes, and the house forgets it
    card.querySelector("#remove").onclick = async () => {
      close();
      if (!(await ask(t("home.remove_q", { name })))) return;
      try { await api("POST", `/api/tracks/${encodeURIComponent(tk.id)}/dismiss`, {}); toast(t("home.removed"), "success"); }
      catch (e) { if (e.status === 404) toast(t("home.gone"), "warning"); else toast(e.message, "alarm"); }
    };
  });
}
