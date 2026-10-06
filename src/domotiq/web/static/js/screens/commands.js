// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Quick controls: party, barbecue, scenes, lights, language and voice.

import { api, esc, pageHead, store, toast } from "../app.js";
import { t, tr } from "../i18n.js";

const COLORS = ["#ffaa5a", "#ffffff", "#ff2010", "#ff8000", "#ffd020", "#20e040", "#20d0ff", "#2050ff", "#a030ff", "#ff40a0"];
const EFFECTS = ["solid", "breathe", "blink", "wave", "rainbow", "sparkle", "fire"];

const ASK_ERRORS = { busy: "askq.err_busy", nobody: "askq.err_nobody", silent: "askq.err_silent",
  no_mic: "askq.err_no_mic", unknown: "askq.err_unknown", no_voice: "askq.err_no_voice" };

// "Fai domande": the house asks a character a question now (one picked at random among those in the house, or this
// one), hears the answer without Talk and keeps it, to use it later (its colour, a party, the barbecue)
export async function askQuestion(identity) {
  try {
    const r = await api("POST", "/api/voice/ask", identity ? { identity } : {});
    if (r.ok) toast(t("askq.asked", { name: r.name }), "success");
    else toast(t(ASK_ERRORS[r.error] || "askq.err_busy"), "warning");
  } catch (e) { toast(e.message || t("common.error"), "alarm"); }
}

async function cmd(name, body) {
  try {
    const r = await api("POST", `/api/commands/${name}`, body || {});
    if (r && r.ok === false) toast(t("cmd.busy"), "warning");
  } catch (e) { toast(e.message || t("common.error"), "alarm"); }
}

export function mount(root) {
  const s = store.state;
  // every choice reaches the house at once: a colour turns the light on, "auto" gives it back to the house, "off"
  // turns it off; the effect and the brightness change the light already on
  let room = "all", color = "auto", effect = "solid", brightness = 60;
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
      <p class="muted small">${t("cmd.lights_lead")}</p>
      <label class="field"><span>${t("cmd.effect")}</span><select id="effect">
        ${EFFECTS.map(e => `<option value="${e}">${t("effect." + e)}</option>`).join("")}</select></label>
      <label class="field"><span>${t("cmd.brightness")}</span><input type="range" min="5" max="100" value="60" id="bri"></label>
      <label class="row spread" style="margin-top:12px"><span>${t("cmd.follow")}</span>
        <span class="switch"><input type="checkbox" id="follow" ${store.state.follow !== false ? "checked" : ""}><span></span></span></label>
    </div>
    <h2>${t("askq.title")}</h2>
    <div class="card">
      <p class="muted small">${t("askq.lead")}</p>
      <button class="btn block primary" id="askq">❓ ${t("askq.button")}</button>
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
  $("#colors").innerHTML =
    `<button data-c="auto" class="auto" title="${t("cmd.swatch_auto")}" aria-label="${t("cmd.swatch_auto")}">A</button>` +
    `<button data-c="off" class="off" title="${t("cmd.swatch_off")}" aria-label="${t("cmd.swatch_off")}"></button>` +
    COLORS.map(c => `<button data-c="${c}" style="background:${c}" aria-label="${c}"></button>`).join("");
  const selColor = () => $("#colors").querySelectorAll("button").forEach(b => b.classList.toggle("sel", b.dataset.c === color));
  const lit = () => color !== "auto" && color !== "off";
  const apply = () => {
    if (color === "auto") cmd("lights_auto", { room });
    else if (color === "off") cmd("lights_off", { room });
    else cmd("light", { room, color, effect, brightness });
  };
  // the room chosen shows how its light is now: lit by hand (its colour), off by hand, or left to the house
  const showRoom = () => {
    const light = room === "all" ? null : s.layout.lights.find(l => l.room === room);
    const now = light && store.state.lights ? store.state.lights[light.id] : null;
    if (now) {
      if (now.source !== "manual") color = "auto";
      else if (now.effect === "off") color = "off";
      else {
        color = now.color;
        effect = EFFECTS.includes(now.effect) ? now.effect : "solid";
        brightness = now.brightness;
      }
    }
    $("#effect").value = effect;
    $("#bri").value = brightness;
    selColor();
  };
  showRoom();
  $("#colors").onclick = (e) => { const b = e.target.closest("button"); if (b) { color = b.dataset.c; selColor(); apply(); } };
  $("#room").onchange = (e) => { room = e.target.value; showRoom(); };
  $("#effect").onchange = (e) => { effect = e.target.value; if (lit()) apply(); };
  let briTimer = null;
  $("#bri").oninput = (e) => {
    brightness = +e.target.value;
    clearTimeout(briTimer);
    if (lit()) briTimer = setTimeout(apply, 250);
  };
  $("#follow").onchange = (e) => cmd("follow", { on: e.target.checked });
  $("#party").onclick = () => cmd("party");
  $("#grill").onclick = () => cmd(store.state.grill ? "grill_stop" : "grill");
  $("#bell").onclick = () => cmd("intercom");
  $("#askq").onclick = () => askQuestion(null);
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
  return {
    update(type) {
      if (["house", "hello"].includes(type)) render();
      // a light that went back to the house (two minutes are up) shows it, unless the brightness is being moved
      if (type === "lights" && room !== "all" && document.activeElement !== $("#bri")) showRoom();
    },
  };
}

function roomName(s, id) {
  const r = s.layout.rooms.find(x => x.id === id);
  return r ? tr(r.name) : id;
}
