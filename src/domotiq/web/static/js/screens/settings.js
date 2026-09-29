// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Staff: settings, PIN, time, backup, bin, system.

import { api, ask, esc, go, isStaff, toast } from "../app.js";
import { t, tr } from "../i18n.js";

const NUMBERS = [
  ["lights.max_brightness", "set.max_brightness", 5, 100],
  ["lights.current_budget_ma", "set.budget", 100, 1000],
  ["lights.follow_brightness", "set.follow_brightness", 5, 100],
  ["lights.follow_off_delay_s", "set.follow_delay", 0, 60],
  ["party.duration_s", "set.party_duration", 10, 60],
  ["grill.duration_s", "set.grill_duration", 5, 120],
  ["climate.hot_delta", "set.hot_delta", 0.3, 5],
  ["climate.shower_rh_delta", "set.shower_delta", 2, 30],
];

const get = (obj, path) => path.split(".").reduce((o, k) => (o || {})[k], obj);

export function mount(root) {
  if (!isStaff()) { go("more"); return {}; }
  const load = async () => {
    let s;
    try { s = await api("GET", "/api/staff/settings"); } catch (e) { go("more"); return; }
    const trash = await api("GET", "/api/staff/trash").catch(() => []);
    root.innerHTML = `
      <h1>${t("set.title")}</h1>
      <div class="card"><h3 style="margin-top:0">${t("set.house")}</h3>
        <label class="field"><span>${t("set.house_name")} (IT)</span><input type="text" id="hn-it" value="${esc(tr({ it: s.house.name.it }))}"></label>
        <label class="field"><span>${t("set.house_name")} (EN)</span><input type="text" id="hn-en" value="${esc(s.house.name.en)}"></label>
        <label class="row spread"><span>${t("set.buttons_reversed")}</span><span class="switch"><input type="checkbox" id="rev" ${s.buttons.reversed ? "checked" : ""}><span></span></span></label>
      </div>
      <div class="card"><h3 style="margin-top:0">${t("set.lights")} · ${t("set.party")} · ${t("set.grill")} · ${t("set.climate")}</h3>
        ${NUMBERS.map(([path, label, min, max]) => `<label class="field"><span>${t(label)}</span>
          <input type="number" data-path="${path}" min="${min}" max="${max}" step="any" value="${get(s, path)}"></label>`).join("")}
        <label class="field"><span>${t("set.follow_color")}</span><input type="color" id="fcol" value="${esc(s.lights.follow_color)}"></label>
        <button class="btn primary block" id="save">${t("common.save")}</button>
      </div>
      <div class="card"><h3 style="margin-top:0">PIN · ${t("set.time")}</h3>
        <label class="field"><span>${t("set.pin")}</span><input type="password" inputmode="numeric" id="pin" maxlength="8" autocomplete="new-password"></label>
        <button class="btn block" id="pin-save">${t("common.save")}</button>
        <p class="muted small" style="margin-top:12px">${new Date().toLocaleString()}</p>
        <button class="btn block" id="time">${t("set.time_now")}</button>
      </div>
      <div class="card"><h3 style="margin-top:0">${t("set.wifi")}</h3>
        <p class="muted small">${t("set.wifi_ssid")}: <b>${esc(s.network.ssid || "—")}</b></p>
        <label class="field"><span>${t("set.wifi_password")}</span><input type="text" id="wifi" minlength="8" maxlength="63" autocomplete="off" spellcheck="false" value="${esc(s.network.password || "")}"></label>
        <p class="muted small">${t("set.wifi_hint")}</p>
        <button class="btn block" id="wifi-save">${t("common.save")}</button>
      </div>
      <div class="card"><h3 style="margin-top:0">${t("set.backup")}</h3>
        <button class="btn block" id="dl">⬇️ ${t("set.download")}</button>
        <label class="field"><span>${t("set.restore")}</span><input type="file" id="restore" accept=".zip,application/zip"></label>
        <button class="btn block ghost" id="defaults">${t("set.defaults")}</button>
      </div>
      <div class="card"><h3 style="margin-top:0">${t("set.trash")}</h3>
        <ul class="list">${trash.length ? trash.map(x => `<li><span class="grow"><span class="title">${esc(typeof x.data.name === "string" ? x.data.name : tr(x.data.name))}</span>
          <span class="sub">${esc(x.entity)} · ${new Date(x.ts * 1000).toLocaleString()} ${x.nickname ? "· " + esc(x.nickname) : ""}</span></span>
          <button class="btn small" data-restore="${x.id}">${t("set.restore_item")}</button></li>`).join("") : `<li class="empty">${t("ev.empty")}</li>`}</ul>
      </div>
      <div class="card"><h3 style="margin-top:0">${t("set.system")}</h3>
        <div class="grid3"><button class="btn" data-sys="restart">${t("set.restart")}</button>
        <button class="btn" data-sys="reboot">${t("set.reboot")}</button>
        <button class="btn danger" data-sys="shutdown">${t("set.shutdown")}</button></div>
      </div>`;
    const $ = (q) => root.querySelector(q);
    $("#save").onclick = async () => {
      const body = { house: { name: { it: $("#hn-it").value, en: $("#hn-en").value } }, buttons: { reversed: $("#rev").checked },
        lights: { follow_color: $("#fcol").value } };
      root.querySelectorAll("[data-path]").forEach(inp => {
        const [a, b] = inp.dataset.path.split(".");
        body[a] = body[a] || {};
        body[a][b] = Number(inp.value);
      });
      try { await api("PUT", "/api/staff/settings", body); toast(t("common.saved"), "success"); } catch (e) { toast(e.message, "alarm"); }
    };
    $("#pin-save").onclick = async () => {
      try { await api("POST", "/api/staff/pin", { pin: $("#pin").value }); toast(t("set.pin_changed"), "success"); $("#pin").value = ""; }
      catch (e) { toast(e.message, "alarm"); }
    };
    $("#wifi-save").onclick = async () => {
      const password = $("#wifi").value;
      if (password.length < 8 || password.length > 63) { toast(t("set.wifi_bad"), "warning"); return; }
      if (!(await ask(t("set.wifi_confirm")))) return;
      try {
        const r = await api("POST", "/api/staff/network", { password });
        toast(r.restarting ? t("set.wifi_restarting") : t("common.saved"), "success", 8000);
      } catch (e) { toast(e.message, "alarm"); }
    };
    $("#time").onclick = async () => {
      try { await api("POST", "/api/staff/time", { epoch: Date.now() / 1000 }); toast(t("time.set"), "success"); } catch (e) { toast(e.message, "alarm"); }
    };
    $("#dl").onclick = async () => {
      try {
        const res = await fetch("/api/staff/backup.zip", { headers: { "X-Staff": localStorage.getItem("domotiq.staff") || "" } });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(await res.blob());
        a.download = (res.headers.get("content-disposition") || "").split('filename="')[1]?.replace('"', "") || "domotiq-backup.zip";
        a.click();
      } catch (e) { toast(e.message, "alarm"); }
    };
    $("#restore").onchange = async (e) => {
      const f = e.target.files[0];
      if (!f || !(await ask(t("set.sure")))) return;
      try { await api("POST", "/api/staff/restore?parts=rules,identities,settings", f, { type: "application/zip" }); toast(t("common.saved"), "success"); load(); }
      catch (err) { toast(err.message, "alarm"); }
    };
    $("#defaults").onclick = async () => {
      if (!(await ask(t("set.sure")))) return;
      try { await api("POST", "/api/staff/rules/defaults"); toast(t("common.saved"), "success"); } catch (e) { toast(e.message, "alarm"); }
    };
    root.querySelectorAll("[data-restore]").forEach(b => {
      b.onclick = async () => { try { await api("POST", `/api/staff/trash/${b.dataset.restore}/restore`); load(); } catch (e) { toast(e.message, "alarm"); } };
    });
    root.querySelectorAll("[data-sys]").forEach(b => {
      b.onclick = async () => {
        if (!(await ask(t("set.sure")))) return;
        try { await api("POST", `/api/staff/system/${b.dataset.sys}`); } catch (e) { toast(e.message, "alarm"); }
      };
    });
  };
  load();
  return {};
}
