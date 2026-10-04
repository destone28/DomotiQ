// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Quick controls: party, barbecue, scenes, lights, language and voice.

import { api, esc, pageHead, store, toast } from "../app.js";
import { t, tr } from "../i18n.js";

const COLORS = ["#ffaa5a", "#ffffff", "#ff2010", "#ff8000", "#ffd020", "#20e040", "#20d0ff", "#2050ff", "#a030ff", "#ff40a0"];
const EFFECTS = ["solid", "breathe", "blink", "wave", "rainbow", "sparkle", "fire"];

async function cmd(name, body) {
  try {
    const r = await api("POST", `/api/commands/${name}`, body || {});
    if (r && r.ok === false) toast(t("cmd.busy"), "warning");
  } catch (e) { toast(e.message || t("common.error"), "alarm"); }
}

export function mount(root) {
  const s = store.state;
  let room = "all", color = COLORS[0], effect = "solid", brightness = 60;
  const rooms = s.layout.lights.map(l => l.room);
  root.innerHTML = `
    ${pageHead(t("cmd.title"), t("cmd.lead"))}
    <div class="grid2">
      <button class="btn big accent" id="party"><span class="ico">🎉</span>${t("cmd.party")}</button>
      <button class="btn big" id="grill"><span class="ico">🔥</span><span id="grill-label"></span></button>
    </div>
    <h2>${t("cmd.scenes")}</h2>
    <div class="pill-list" id="scenes"></div>
    <h2>${t("cmd.lights")}</h2>
    <div class="card">
      <label class="field"><span>${t("cmd.room")}</span><select id="room">
        <option value="all">${t("common.all_rooms")}</option>
        ${rooms.map(r => `<option value="${r}">${esc(roomName(s, r))}</option>`).join("")}
      </select></label>
      <div class="field"><span class="muted small">${t("cmd.color")}</span><div class="swatches" id="colors"></div></div>
      <label class="field"><span>${t("cmd.effect")}</span><select id="effect">
        ${EFFECTS.map(e => `<option value="${e}">${t("effect." + e)}</option>`).join("")}</select></label>
      <label class="field"><span>${t("cmd.brightness")}</span><input type="range" min="5" max="100" value="60" id="bri"></label>
      <div class="grid3">
        <button class="btn primary" id="on">${t("cmd.light_on")}</button>
        <button class="btn" id="off">${t("cmd.light_off")}</button>
        <button class="btn ghost" id="auto">${t("cmd.light_auto")}</button>
      </div>
      <label class="row spread" style="margin-top:12px"><span>${t("cmd.follow")}</span>
        <span class="switch"><input type="checkbox" id="follow" ${store.state.follow !== false ? "checked" : ""}><span></span></span></label>
    </div>
    <h2>${t("cmd.voice")}</h2>
    <div class="card">
      <div class="field"><span class="muted small">${t("cmd.language")}</span>
        <div class="pill-list"><button class="chip" data-lang="it">Italiano</button><button class="chip" data-lang="en">English</button></div></div>
      <div class="field"><span class="muted small">${t("cmd.verbosity")}</span>
        <div class="pill-list">${["silent", "normal", "chatty"].map(v => `<button class="chip" data-verb="${v}">${t("cmd." + v)}</button>`).join("")}</div></div>
      <label class="field"><span>${t("cmd.volume")}</span><input type="range" min="0" max="100" id="vol"></label>
      <button class="btn block" id="bell">🔔 ${t("cmd.intercom")}</button>
      <div id="say-box" style="margin-top:12px">
        <label class="field"><span>${t("cmd.say")}</span>
          <input type="text" id="say" maxlength="200" placeholder="${t("cmd.say_ph")}"></label>
        <button class="btn" id="say-go">${t("cmd.say_go")}</button>
      </div>
    </div>`;

  const $ = (q) => root.querySelector(q);
  $("#colors").innerHTML = COLORS.map(c => `<button data-c="${c}" style="background:${c}" aria-label="${c}"></button>`).join("");
  const selColor = () => $("#colors").querySelectorAll("button").forEach(b => b.classList.toggle("sel", b.dataset.c === color));
  selColor();
  $("#colors").onclick = (e) => { const b = e.target.closest("button"); if (b) { color = b.dataset.c; selColor(); } };
  $("#room").onchange = (e) => { room = e.target.value; };
  $("#effect").onchange = (e) => { effect = e.target.value; };
  $("#bri").oninput = (e) => { brightness = +e.target.value; };
  $("#on").onclick = () => cmd("light", { room, color, effect, brightness });
  $("#off").onclick = () => cmd("lights_off", { room });
  $("#auto").onclick = () => cmd("lights_auto", { room });
  $("#follow").onchange = (e) => cmd("follow", { on: e.target.checked });
  $("#party").onclick = () => cmd("party");
  $("#grill").onclick = () => cmd(store.state.grill ? "grill_stop" : "grill");
  $("#bell").onclick = () => cmd("intercom");
  $("#say-go").onclick = () => { const v = $("#say").value.trim(); if (v) { cmd("say", { text: v }); $("#say").value = ""; } };
  root.querySelectorAll("[data-lang]").forEach(b => { b.onclick = () => cmd("language", { language: b.dataset.lang }); });
  root.querySelectorAll("[data-verb]").forEach(b => { b.onclick = () => cmd("verbosity", { verbosity: b.dataset.verb }); });
  let volTimer = null;
  $("#vol").oninput = (e) => { clearTimeout(volTimer); volTimer = setTimeout(() => cmd("volume", { volume: +e.target.value }), 250); };

  const render = () => {
    const st = store.state;
    $("#grill-label").textContent = st.grill ? t("cmd.grill_stop") : t("cmd.grill");
    $("#party").disabled = !!st.party;
    $("#scenes").innerHTML = (st.scene_order || Object.keys(st.scenes)).map(id =>
      `<button class="chip ${st.scene === id ? "on" : ""}" data-scene="${id}">${esc(tr(st.scenes[id].name))}</button>`).join("");
    $("#scenes").querySelectorAll("[data-scene]").forEach(b => { b.onclick = () => cmd("scene", { scene: b.dataset.scene }); });
    const b = st.brief || {};
    root.querySelectorAll("[data-lang]").forEach(x => x.classList.toggle("on", x.dataset.lang === b.language));
    root.querySelectorAll("[data-verb]").forEach(x => x.classList.toggle("on", x.dataset.verb === b.verbosity));
    if (document.activeElement !== $("#vol")) $("#vol").value = b.volume ?? 70;
  };
  render();
  return { update(type) { if (["house", "hello"].includes(type)) render(); } };
}

function roomName(s, id) {
  const r = s.layout.rooms.find(x => x.id === id);
  return r ? tr(r.name) : id;
}
