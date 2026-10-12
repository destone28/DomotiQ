// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Settings of the house, time, Wi-Fi, backup, bin, system: open to everybody, like every page.

import { api, ask, esc, pageHead, toast } from "../app.js";
import { t, tr } from "../i18n.js";

const NUMBERS = [
  ["party.duration_s", "set.party_duration", 10, 60],
  ["grill.duration_s", "set.grill_duration", 5, 120],
  ["climate.hot_delta", "set.hot_delta", 0.3, 5],
  ["climate.shower_rh_delta", "set.shower_delta", 2, 30],
];

const get = (obj, path) => path.split(".").reduce((o, k) => (o || {})[k], obj);

export function mount(root) {
  const load = async () => {
    let s;
    try { s = await api("GET", "/api/settings"); } catch (e) { root.innerHTML = `<p class="empty">${t("common.error")}</p>`; return; }
    const trash = await api("GET", "/api/trash").catch(() => []);
    root.innerHTML = `
      ${pageHead(t("set.title"), t("set.lead"))}
      <div class="card"><h3 class="card-title">🏠 ${t("set.house")}</h3>
        <label class="field"><span>${t("set.house_name")} (IT)</span><input type="text" id="hn-it" value="${esc(tr({ it: s.house.name.it }))}"></label>
        <label class="field"><span>${t("set.house_name")} (EN)</span><input type="text" id="hn-en" value="${esc(s.house.name.en)}"></label>
        <label class="row spread"><span>${t("set.blur_bathroom")}</span><span class="switch"><input type="checkbox" id="blur" ${s.camera.blur_bathroom !== false ? "checked" : ""}><span></span></span></label>
        <label class="row spread"><span>${t("set.collect")}</span><span class="switch"><input type="checkbox" id="coll" ${s.camera.collect ? "checked" : ""}><span></span></span></label>
        <label class="field"><span>${t("set.collect_mb")}</span><input type="number" id="collmb" min="50" max="5000" step="50" value="${s.camera.collect_mb || 500}"></label>
        <p class="muted small">${t("set.collect_hint")}</p>
      </div>
      <div class="card"><h3 class="card-title">🎉 ${t("set.party")} · ${t("set.grill")} · ${t("set.climate")}</h3>
        ${NUMBERS.map(([path, label, min, max]) => `<label class="field"><span>${t(label)}</span>
          <input type="number" data-path="${path}" min="${min}" max="${max}" step="any" value="${get(s, path)}"></label>`).join("")}
        <button class="btn primary block" id="save">${t("common.save")}</button>
      </div>
      <div class="card"><h3 class="card-title">🔊 ${t("set.voice")}</h3>
        <label class="row spread"><span>${t("set.greet_phones")}</span><span class="switch"><input type="checkbox" id="greet" ${s.voice.greet_phones ? "checked" : ""}><span></span></span></label>
        <label class="row spread"><span>${t("set.chatty_questions")}</span><span class="switch"><input type="checkbox" id="chatq" ${s.voice.chatty_questions ? "checked" : ""}><span></span></span></label>
        <label class="field"><span>${t("set.question_every")}</span>
          <input type="number" data-path="voice.question_every_s" min="45" max="1800" step="5" value="${s.voice.question_every_s}"></label>
        <label class="row spread"><span>${t("set.wake")}</span><span class="switch"><input type="checkbox" id="wake" ${s.voice.wake_enabled ? "checked" : ""}><span></span></span></label>
        <label class="field"><span>${t("set.wake_word")}</span><input type="text" id="wake-word" maxlength="40" autocomplete="off" value="${esc(s.voice.wake_word || "")}"></label>
        <p class="muted small" id="wake-hint">${t("set.wake_hint")}</p>
        <button class="btn primary block" id="save-voice">${t("common.save")}</button>
      </div>
      <div class="card"><h3 class="card-title">🕒 ${t("set.time")}</h3>
        <p class="muted small">${new Date().toLocaleString()}</p>
        <button class="btn block" id="time">${t("set.time_now")}</button>
      </div>
      <div class="card"><h3 class="card-title">📶 ${t("set.wifi")}</h3>
        <p class="muted small">${t("set.wifi_ssid")}: <b>${esc(s.network.ssid || "—")}</b></p>
        <label class="field"><span>${t("set.wifi_password")}</span><input type="text" id="wifi" minlength="8" maxlength="63" autocomplete="off" spellcheck="false" value="${esc(s.network.password || "")}"></label>
        <p class="muted small">${t("set.wifi_hint")}</p>
        <button class="btn block" id="wifi-save">${t("common.save")}</button>
      </div>
      <div class="card"><h3 class="card-title">💾 ${t("set.backup")}</h3>
        <button class="btn block" id="dl">⬇️ ${t("set.download")}</button>
        <label class="field"><span>${t("set.restore")}</span><input type="file" id="restore" accept=".zip,application/zip"></label>
        <button class="btn block ghost" id="defaults">${t("set.defaults")}</button>
      </div>
      <div class="card"><h3 class="card-title">🗑️ ${t("set.trash")}</h3>
        <ul class="list">${trash.length ? trash.map(x => `<li><span class="grow"><span class="title">${esc(typeof x.data.name === "string" ? x.data.name : tr(x.data.name))}</span>
          <span class="sub">${esc(x.entity)} · ${new Date(x.ts * 1000).toLocaleString()} ${x.nickname ? "· " + esc(x.nickname) : ""}</span></span>
          <button class="btn small" data-restore="${x.id}">${t("set.restore_item")}</button></li>`).join("") : `<li class="empty">${t("ev.empty")}</li>`}</ul>
      </div>
      <div class="card"><h3 class="card-title">🖥️ ${t("set.system")}</h3>
        <div class="grid3"><button class="btn" data-sys="restart">${t("set.restart")}</button>
        <button class="btn" data-sys="reboot">${t("set.reboot")}</button>
        <button class="btn danger" data-sys="shutdown">${t("set.shutdown")}</button></div>
      </div>`;
    const $ = (q) => root.querySelector(q);
    $("#save").onclick = $("#save-voice").onclick = async () => {
      const body = { house: { name: { it: $("#hn-it").value, en: $("#hn-en").value } },
        camera: { blur_bathroom: $("#blur").checked,
          collect: $("#coll").checked, collect_mb: Math.max(50, Number($("#collmb").value) || 500) },
        voice: { greet_phones: $("#greet").checked, chatty_questions: $("#chatq").checked,
                 wake_enabled: $("#wake").checked, wake_word: $("#wake-word").value.trim() } };
      root.querySelectorAll("[data-path]").forEach(inp => {
        const [a, b] = inp.dataset.path.split(".");
        body[a] = body[a] || {};
        body[a][b] = Number(inp.value);
      });
      try {
        await api("PUT", "/api/settings", body);
        toast(t("common.saved"), "success");
        // how the speech recognizer will hear the word of activation, and the words it does not know
        if (body.voice.wake_enabled && body.voice.wake_word) {
          const w = await api("POST", "/api/voice/wake_check", { word: body.voice.wake_word });
          const unknown = w.unknown.length ? t("set.wake_unknown", { words: w.unknown.join(", ") }) : "";
          // a word it does not know is heard by words it knows that sound the same ("domotiq" as "domotica")
          const heard = w.heard_as && w.heard_as !== w.spoken ? t("set.wake_heard_as", { spoken: w.spoken, heard: w.heard_as })
            : t("set.wake_heard", { spoken: w.spoken });
          $("#wake-hint").textContent = heard + (unknown ? " " + unknown : "");
          if (unknown) toast(unknown, "warning", 8000);
        }
      } catch (e) { toast(e.message, "alarm"); }
    };
    $("#wifi-save").onclick = async () => {
      const password = $("#wifi").value;
      if (password.length < 8 || password.length > 63) { toast(t("set.wifi_bad"), "warning"); return; }
      if (!(await ask(t("set.wifi_confirm")))) return;
      try {
        const r = await api("POST", "/api/network", { password });
        if (!r.applied) toast(t("set.wifi_not_applied") + (r.reason ? ` (${r.reason})` : ""), "warning", 10000);
        else toast(r.restarting ? t("set.wifi_restarting") : t("common.saved"), "success", 8000);
      } catch (e) { toast(e.message, "alarm", 8000); }
    };
    $("#time").onclick = async () => {
      try { await api("POST", "/api/clock", { epoch: Date.now() / 1000 }); toast(t("time.set"), "success"); } catch (e) { toast(e.message, "alarm"); }
    };
    $("#dl").onclick = async () => {
      try {
        const res = await fetch("/api/backup.zip");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(await res.blob());
        a.download = (res.headers.get("content-disposition") || "").split('filename="')[1]?.replace('"', "") || "domotiq-backup.zip";
        a.click();
      } catch (e) { toast(e.message, "alarm"); }
    };
    $("#restore").onchange = async (e) => {
      const f = e.target.files[0];
      if (!f || !(await ask(t("set.sure")))) return;
      try { await api("POST", "/api/restore?parts=rules,identities,settings", f, { type: "application/zip" }); toast(t("common.saved"), "success"); load(); }
      catch (err) { toast(err.message, "alarm"); }
    };
    $("#defaults").onclick = async () => {
      if (!(await ask(t("set.sure")))) return;
      try { await api("POST", "/api/rules/defaults"); toast(t("common.saved"), "success"); } catch (e) { toast(e.message, "alarm"); }
    };
    root.querySelectorAll("[data-restore]").forEach(b => {
      b.onclick = async () => { try { await api("POST", `/api/trash/${b.dataset.restore}/restore`); load(); } catch (e) { toast(e.message, "alarm"); } };
    });
    root.querySelectorAll("[data-sys]").forEach(b => {
      b.onclick = async () => {
        if (!(await ask(t("set.sure")))) return;
        try { await api("POST", `/api/system/${b.dataset.sys}`); } catch (e) { toast(e.message, "alarm"); }
      };
    });
  };
  load();
  return {};
}
