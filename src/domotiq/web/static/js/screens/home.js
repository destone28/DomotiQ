// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// The virtual house: the plan, who is where, lights, climate, car, alarms.

import { esc, go, identityName, modal, roomName, store } from "../app.js";
import { t, tr } from "../i18n.js";
import { ICONS, Plan } from "../plan.js";

export function mount(root) {
  root.innerHTML = `
    <div class="plan-wrap" id="plan"></div>
    <p class="muted small" style="margin:6px 4px">${t("home.tap_hint")}</p>
    <div class="grid2 wide" id="cards"></div>
    <div class="card"><h3 style="margin-top:0">${t("nav.home")}</h3><ul class="list" id="who"></ul></div>`;
  const plan = new Plan(root.querySelector("#plan"), store.state, { onTap: (id) => showTrack(id) });
  const render = () => {
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

function renderCards(el) {
  const s = store.state;
  const th = (s.sensors || {}).thermostat || {};
  const ba = (s.sensors || {}).bathroom || {};
  const persons = Object.entries(s.counts || {}).filter(([r]) => r !== "outside" && r !== "driveway")
    .reduce((n, [, c]) => n + (c.persons || 0), 0);
  const climate = s.climate === "hot" ? t("home.climate.hot") : s.climate === "cold" ? t("home.climate.cold") : "";
  const scene = s.scenes && s.scenes[s.scene] ? tr(s.scenes[s.scene].name) : s.scene;
  el.innerHTML = `
    <div class="card"><div class="muted small">${t("home.people")}</div><div class="stat num">${persons}</div></div>
    <div class="card"><div class="muted small">${t("home.thermostat")}</div>
      <div class="stat num">${th.t != null ? th.t.toFixed(1) + "°" : "—"}</div>
      <div class="small muted">${th.rh != null ? Math.round(th.rh) + "%" : ""} ${esc(climate)}</div></div>
    <div class="card"><div class="muted small">${t("home.bathroom")}</div>
      <div class="stat num">${ba.rh != null ? Math.round(ba.rh) + "%" : "—"}</div>
      <div class="small muted">${s.shower ? t("home.shower") : ""}</div></div>
    <div class="card"><div class="muted small">${t("home.car")}</div><div class="stat" style="font-size:18px">${esc(t("car." + (s.car || "absent")))}</div></div>
    <div class="card"><div class="muted small">${t("home.scene")}</div><div class="stat" style="font-size:18px">${esc(scene)}</div></div>
    <div class="card"><div class="pill-list">
      ${s.party ? `<span class="chip on">🎉 ${t("home.party")}</span>` : ""}
      ${s.grill ? `<span class="chip warn">🔥 ${t("home.grill")}</span>` : ""}
      ${!s.party && !s.grill ? `<span class="muted small">—</span>` : ""}
    </div></div>`;
}

function renderWho(el) {
  const s = store.state;
  const tracks = [...(s.tracks || [])].sort((a, b) => (a.room || "").localeCompare(b.room || ""));
  if (!tracks.length) { el.innerHTML = `<li class="empty">${t("home.nobody")}</li>`; return; }
  el.innerHTML = tracks.map(tk => {
    const name = identityName(tk.identity) || (tk.category === "person" ? t("home.guest") : t("home.unknown"));
    return `<li><button class="link" data-id="${tk.id}">
      <span class="silhouette" style="background:${esc(tk.color)}"><svg viewBox="0 0 24 24"><path d="${ICONS[tk.category] || ICONS.object}"/></svg></span>
      <span class="grow"><span class="title">${esc(name)}${tk.uncertain ? " ?" : ""}</span>
      <span class="sub">${esc(t("cat." + tk.category))} · ${esc(roomName(tk.room))}</span></span></button></li>`;
  }).join("");
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
      <div class="row" style="justify-content:flex-end;margin-top:12px">
        ${!ident ? `<button class="btn primary" id="reg">${t("home.register")}</button>` : ""}
        <button class="btn" id="close">${t("common.close")}</button>
      </div>`;
    card.querySelector("#close").onclick = close;
    const reg = card.querySelector("#reg");
    if (reg) reg.onclick = () => { close(); go("identities", { add: "1", track: tk.id }); };
  });
}
