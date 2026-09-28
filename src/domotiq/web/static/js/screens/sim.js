// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Simulation: drag virtual characters on the plan, move virtual sensors, press virtual buttons.

import { api, esc, isStaff, store, toast } from "../app.js";
import { t } from "../i18n.js";
import { BOUNDS, Plan } from "../plan.js";

const PALETTE = [["person", "#e03030"], ["person", "#2f6fe0"], ["person", "#e0c020"], ["dog", "#f28c28"], ["cat", "#d04fb0"], ["car", "#20a8d0"], ["object", "#7a5cff"]];

export function mount(root) {
  let plan = null;
  const render = () => {
    const sim = store.state.sim || { enabled: false, objects: [] };
    root.innerHTML = `
      <h1>${t("sim.title")}</h1>
      <div class="card">
        <label class="row spread"><span><b>${t("sim.on")}</b></span><span class="switch"><input type="checkbox" id="on" ${sim.enabled ? "checked" : ""}><span></span></span></label>
        <label class="row spread" style="margin-top:8px"><span>${t("sim.mute")}</span><span class="switch"><input type="checkbox" id="mute" ${sim.mute ? "checked" : ""}><span></span></span></label>
        ${!isStaff() ? `<p class="muted small">${t("common.staff_only")}</p>` : ""}
      </div>
      ${sim.enabled ? `
        <p class="muted small">${t("sim.hint")} ${t("sim.remove")}</p>
        <div class="plan-wrap" id="plan"></div>
        <h2>${t("sim.add")}</h2>
        <div class="pill-list" id="palette">${PALETTE.map(([c, col], i) => `<button class="chip" data-p="${i}"><span class="silhouette" style="width:18px;height:18px;background:${col}"></span>${t("cat." + c)}</button>`).join("")}</div>
        <label class="field"><span>${t("sim.add_identity")}</span><select id="ident"><option value="">—</option>
          ${store.state.identities.map(i => `<option value="${i.id}">${esc(i.name)}</option>`).join("")}</select></label>
        <h2>${t("sim.sensors")}</h2>
        <div class="card">
          ${slider("th-t", t("home.thermostat") + " °C", 15, 35, 0.1, 24)}
          ${slider("th-rh", t("home.thermostat") + " %", 20, 90, 1, 45)}
          ${slider("ba-t", t("home.bathroom") + " °C", 15, 35, 0.1, 24)}
          ${slider("ba-rh", t("home.bathroom") + " %", 20, 95, 1, 50)}
          ${slider("dist", t("sim.distance"), 0, 130, 1, 130)}
        </div>
        <h2>${t("sim.buttons")}</h2>
        <div class="grid3">
          <button class="btn hold" id="b-talk">🎤 ${t("btn.talk")}</button>
          <button class="btn" id="b-intercom">🔔 ${t("btn.intercom")}</button>
          <button class="btn" id="b-language">🌐 ${t("btn.language")}</button>
        </div>` : `<p class="muted">${t("sim.off_hint")}</p>`}`;

    const $ = (q) => root.querySelector(q);
    const toggle = async () => {
      try { await api("POST", "/api/sim/enable", { on: $("#on").checked, mute: $("#mute").checked }); }
      catch (e) { toast(e.status === 401 ? t("common.staff_only") : e.message, "warning"); render(); }
    };
    $("#on").onchange = toggle;
    $("#mute").onchange = toggle;
    if (!sim.enabled) return;

    plan = new Plan($("#plan"), store.state, {
      draggable: true,
      onDrag: async (id, x, y, end) => {
        const out = x < 0 - 20 || x > 650 + 60 || y < -80 - 15 || y > 370 + 15;
        try {
          if (end && out) await api("DELETE", `/api/sim/objects/${id}`);
          else await api("PUT", `/api/sim/objects/${id}`, { x, y });
        } catch (e) { /* object gone */ }
      },
    });
    $("#palette").onclick = async (e) => {
      const b = e.target.closest("[data-p]");
      if (!b) return;
      const [category, color] = PALETTE[+b.dataset.p];
      const pos = category === "car" ? { x: 690, y: 300 } : { x: 197, y: -40 };
      try { await api("POST", "/api/sim/objects", { category, color, ...pos }); } catch (err) { toast(err.message, "warning"); }
    };
    $("#ident").onchange = async (e) => {
      if (!e.target.value) return;
      try { await api("POST", "/api/sim/objects", { identity: e.target.value, x: 197, y: -40 }); } catch (err) { toast(err.message, "warning"); }
      e.target.value = "";
    };
    let sensTimer = null;
    const sendSensors = () => {
      clearTimeout(sensTimer);
      sensTimer = setTimeout(() => {
        const d = +$("#dist").value;
        api("POST", "/api/sim/sensor", {
          thermostat: { t: +$("#th-t").value, rh: +$("#th-rh").value },
          bathroom: { t: +$("#ba-t").value, rh: +$("#ba-rh").value },
          distance: d >= 130 ? null : d * 10,
        }).catch(() => {});
      }, 200);
    };
    root.querySelectorAll("input[type=range]").forEach(r => {
      r.oninput = () => { root.querySelector(`#${r.id}-v`).textContent = r.value; sendSensors(); };
    });
    const press = (button, pressed) => api("POST", "/api/sim/button", { button, pressed }).catch(() => {});
    const talk = $("#b-talk");
    talk.onpointerdown = (e) => { e.preventDefault(); press("talk", true); };
    talk.onpointerup = talk.onpointerleave = talk.onpointercancel = () => press("talk", false);
    $("#b-intercom").onclick = () => { press("intercom", true); setTimeout(() => press("intercom", false), 150); };
    $("#b-language").onclick = () => { press("language", true); setTimeout(() => press("language", false), 150); };
  };
  render();
  return {
    update(type) {
      if (type === "sim" || type === "staff") render();
      else if (plan && ["tracks", "lights", "counts", "alerts", "house", "sensors", "totem"].includes(type)) plan.update(store.state);
    },
  };
}

function slider(id, label, min, max, step, value) {
  return `<label class="field"><span>${label}: <b class="num" id="${id}-v">${value}</b></span>
    <input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${value}"></label>`;
}
void BOUNDS;
