// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Staff: what the board sees of itself.

import { api, esc, go, isStaff, toast } from "../app.js";
import { t } from "../i18n.js";

const MODULE_NAMES = {
  hub: "Hub", relay: "Latch Relay", pixels_garage: "Pixels · garage", pixels_bedroom: "Pixels · camera / bedroom",
  pixels_kitchen: "Pixels · cucina / kitchen", pixels_living: "Pixels · soggiorno / living", thermo_bathroom: "Thermo · bagno / bathroom",
  pixels_bathroom: "Pixels · bagno / bathroom", thermo_thermostat: "Thermo · credenza / sideboard", buttons: "Buttons", distance: "Distance",
};

function dur(s) {
  if (s == null) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h} h ${m} min`;
}

export function mount(root) {
  if (!isStaff()) { go("more"); return {}; }
  root.innerHTML = `<h1>${t("diag.title")}</h1><div id="body"><p class="muted">${t("common.loading")}</p></div>
    <div class="grid2" style="margin-top:10px">
      <button class="btn" id="scan">${t("diag.scan")}</button>
      <button class="btn" id="sound">${t("diag.sound")}</button>
      <button class="btn" id="mic">${t("diag.mic")}</button>
      <button class="btn ghost" id="logs">${t("diag.logs")}</button>
    </div><pre class="card mono small" id="out" hidden style="white-space:pre-wrap"></pre>`;
  const $ = (q) => root.querySelector(q);
  const load = async () => {
    try {
      const d = await api("GET", "/api/staff/diagnostics");
      const mods = Object.entries(d.mcu.modules || {}).map(([k, ok]) =>
        `<li><span>${ok ? "🟢" : "🔴"}</span><span class="grow">${esc(MODULE_NAMES[k] || k)}</span></li>`).join("");
      const cam = d.camera || {};
      $("#body").innerHTML = `
        <div class="card"><h3 style="margin-top:0">${t("diag.system")}</h3><dl class="kv">
          <dt>Host</dt><dd>${esc(d.hostname)} · DomotiQ ${esc(d.version)}</dd>
          <dt>Uptime</dt><dd>${dur(d.uptime_s)} (app ${dur(d.app_uptime_s)})</dd>
          <dt>CPU</dt><dd class="num">${d.cpu.load.join(" / ")} · ${d.cpu.temperature != null ? d.cpu.temperature.toFixed(1) + " °C" : "—"}</dd>
          <dt>RAM</dt><dd class="num">${d.memory.available_mb} / ${d.memory.total_mb} MB (${d.memory.used_pct}%)</dd>
          <dt>Disk</dt><dd class="num">${d.disk.free_mb} MB</dd>
          <dt>Wi-Fi</dt><dd>${d.wifi_clients ?? "—"}</dd>
          <dt>Clock</dt><dd>${esc(d.clock.source)} · ${new Date(d.clock.now * 1000).toLocaleString()}</dd>
          <dt>Audio</dt><dd>${d.audio.ok ? "🟢" : "🔴"} ${esc(d.audio.device || "")}</dd>
          <dt>Voice</dt><dd>${d.voice.ok ? "🟢" : "🔴"} ${esc(d.voice.stt || "")} ${d.voice.llm ? "· LLM 🟢" : ""}</dd>
          <dt>Camera</dt><dd>${cam.available ? "🟢" : "🔴"} ${esc(cam.device || "")} ${cam.fps ? cam.fps.toFixed(1) + " fps" : ""} ${cam.calibrated === false ? "· not calibrated" : ""}</dd>
        </dl></div>
        <div class="card"><h3 style="margin-top:0">${t("diag.modules")} ${d.mcu.ok ? "🟢" : "🔴"} ${d.mcu.version != null ? "v" + d.mcu.version : ""}</h3><ul class="list">${mods}</ul></div>`;
    } catch (e) { $("#body").innerHTML = `<p class="muted">${t("common.error")}</p>`; }
  };
  const out = (text) => { $("#out").hidden = false; $("#out").textContent = text; };
  $("#scan").onclick = async () => {
    try {
      const r = await api("POST", "/api/staff/diagnostics/scan");
      out(Object.entries(r).map(([ch, a]) => `ch${ch}: ${Array.isArray(a) ? a.map(x => "0x" + x.toString(16)).join(" ") || "—" : a}`).join("\n"));
    } catch (e) { toast(e.message, "alarm"); }
  };
  $("#sound").onclick = () => api("POST", "/api/staff/diagnostics/sound").catch(e => toast(e.message, "alarm"));
  $("#mic").onclick = async () => {
    try { const r = await api("POST", "/api/staff/diagnostics/mic"); out(JSON.stringify(r, null, 2)); }
    catch (e) { toast(e.message, "alarm"); }
  };
  $("#logs").onclick = async () => {
    try {
      const res = await fetch("/api/staff/logs", { headers: { "X-Staff": localStorage.getItem("domotiq.staff") || "" } });
      out(await res.text());
    } catch (e) { toast(e.message, "alarm"); }
  };
  load();
  const timer = setInterval(load, 5000);
  return { unmount() { clearInterval(timer); } };
}
