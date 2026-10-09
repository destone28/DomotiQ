// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Everything else, in two groups: the house and setting it up. Open to everybody.

import { esc, pageHead, setNickname, store } from "../app.js";
import { t } from "../i18n.js";

const item = (go, icon, label, sub) => `<li><button class="link" data-go="${go}">
  <span class="ico">${icon}</span><span class="grow"><span class="title">${label}</span>${sub ? `<span class="sub">${sub}</span>` : ""}</span>
  <span class="chev">›</span></button></li>`;

export function mount(root) {
  root.innerHTML = `
    ${pageHead(t("more.title"), t("more.lead"))}
    <h2>${t("more.house")}</h2>
    <div class="card menu"><ul class="list">
      ${item("events", "📜", t("more.events"), t("more.events_sub"))}
      ${item("rules", "📏", t("more.rules"), t("more.rules_sub"))}
      ${item("knowledge", "🧠", t("more.knowledge"), t("more.knowledge_sub"))}
      ${item("sim", "🕹️", t("more.sim"), t("more.sim_sub"))}
      ${item("about", "ℹ️", t("more.about"))}
    </ul></div>
    <h2>${t("more.setup")}</h2>
    <div class="card menu"><ul class="list">
      ${item("calibration", "🎯", t("more.calibration"), t("more.calibration_sub"))}
      ${item("diagnostics", "🩺", t("more.diagnostics"), t("more.diagnostics_sub"))}
      ${item("journal", "🔎", t("more.journal"), t("more.journal_sub"))}
      ${item("settings", "⚙️", t("more.settings"), t("more.settings_sub"))}
    </ul></div>
    <h2>${t("more.you")}</h2>
    <div class="card">
      <label class="field" style="margin-top:0"><span>${t("more.nickname")}</span><input type="text" id="nick" maxlength="30" value="${esc(store.nickname)}"></label>
      <p class="muted small" style="margin-bottom:0">${t("more.nickname_hint")}</p>
    </div>`;
  root.querySelector("#nick").onchange = (e) => setNickname(e.target.value);
  return {};
}
