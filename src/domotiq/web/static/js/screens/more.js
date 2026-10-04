// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Everything else, in three groups: the house, setting it up, the stand. Open to everybody.

import { esc, pageHead, setNickname, store } from "../app.js";
import { t } from "../i18n.js";

const item = (go, icon, label, sub) => `<li><button class="link" data-go="${go}">
  <span class="ico">${icon}</span><span class="grow"><span class="title">${label}</span>${sub ? `<span class="sub">${sub}</span>` : ""}</span>
  <span class="chev">›</span></button></li>`;
const link = (href, icon, label, sub) => `<li><a class="link" href="${href}" target="_blank" rel="noopener">
  <span class="ico">${icon}</span><span class="grow"><span class="title">${label}</span>${sub ? `<span class="sub">${sub}</span>` : ""}</span>
  <span class="chev">↗</span></a></li>`;

export function mount(root) {
  root.innerHTML = `
    ${pageHead(t("more.title"), t("more.lead"))}
    <h2>${t("more.house")}</h2>
    <div class="card menu"><ul class="list">
      ${item("events", "📜", t("more.events"), t("more.events_sub"))}
      ${item("rules", "📏", t("more.rules"), t("more.rules_sub"))}
      ${item("sim", "🕹️", t("more.sim"), t("more.sim_sub"))}
    </ul></div>
    <h2>${t("more.setup")}</h2>
    <div class="card menu"><ul class="list">
      ${item("calibration", "🎯", t("more.calibration"), t("more.calibration_sub"))}
      ${item("diagnostics", "🩺", t("more.diagnostics"), t("more.diagnostics_sub"))}
      ${item("settings", "⚙️", t("more.settings"), t("more.settings_sub"))}
    </ul></div>
    <h2>${t("more.stand")}</h2>
    <div class="card menu"><ul class="list">
      ${link("/sign", "🪧", t("more.sign"), t("more.sign_sub"))}
      ${link("/board", "📺", t("more.board"), t("more.board_sub"))}
      ${item("about", "ℹ️", t("more.about"))}
    </ul></div>
    <h2>${t("more.you")}</h2>
    <div class="card">
      <label class="field" style="margin-top:0"><span>${t("more.nickname")}</span><input type="text" id="nick" maxlength="30" value="${esc(store.nickname)}"></label>
      <p class="muted small" style="margin-bottom:0">${t("more.nickname_hint")}</p>
    </div>`;
  root.querySelector("#nick").onchange = (e) => setNickname(e.target.value);
  return {};
}
