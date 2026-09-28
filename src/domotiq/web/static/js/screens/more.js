// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Everything else: rules, characters, simulation, staff pages, sign, about.

import { api, esc, isStaff, setNickname, setStaff, store, toast } from "../app.js";
import { t } from "../i18n.js";

export function mount(root) {
  const render = () => {
    const staff = isStaff();
    const item = (go, icon, label, lock) => `<li><button class="link" ${lock && !staff ? "disabled" : ""} data-go="${go}">
      <span style="font-size:22px">${icon}</span><span class="grow"><span class="title">${label}</span>
      ${lock ? `<span class="sub">${t("common.staff_only")}</span>` : ""}</span><span>›</span></button></li>`;
    root.innerHTML = `
      <h1>${t("more.title")}</h1>
      <div class="card"><ul class="list">
        ${item("rules", "📏", t("more.rules"))}
        ${item("identities", "🧍", t("more.identities"))}
        ${item("sim", "🕹️", t("more.sim"))}
      </ul></div>
      <div class="card"><ul class="list">
        ${item("calibration", "🎯", t("more.calibration"), true)}
        ${item("diagnostics", "🩺", t("more.diagnostics"), true)}
        ${item("settings", "⚙️", t("more.settings"), true)}
      </ul></div>
      <div class="card"><ul class="list">
        <li><a class="link row" href="/sign" target="_blank" style="text-decoration:none;color:inherit;width:100%"><span style="font-size:22px">🪧</span><span class="grow title">${t("more.sign")}</span><span>›</span></a></li>
        <li><a class="link row" href="/board" target="_blank" style="text-decoration:none;color:inherit;width:100%"><span style="font-size:22px">📺</span><span class="grow title">${t("more.board")}</span><span>›</span></a></li>
        ${item("about", "ℹ️", t("more.about"))}
      </ul></div>
      <div class="card">
        <label class="field"><span>${t("more.nickname")}</span><input type="text" id="nick" maxlength="30" value="${esc(store.nickname)}"></label>
        <p class="muted small">${t("more.nickname_hint")}</p>
      </div>
      <div class="card" id="staff-box">
        ${staff ? `<button class="btn block" id="logout">🔓 ${t("more.staff_out")}</button>` : `
          <label class="field"><span>${t("staff.pin")}</span><input type="password" inputmode="numeric" id="pin" maxlength="8" autocomplete="off"></label>
          <button class="btn primary block" id="login">🔒 ${t("more.staff_in")}</button>`}
      </div>`;
    root.querySelector("#nick").onchange = (e) => setNickname(e.target.value);
    const login = root.querySelector("#login");
    if (login) {
      const go = async () => {
        try {
          const r = await api("POST", "/api/staff/login", { pin: root.querySelector("#pin").value });
          setStaff(r.token);
          render();
        } catch (e) {
          toast(e.status === 429 ? t("staff.locked") : t("staff.wrong"), "alarm");
        }
      };
      login.onclick = go;
      root.querySelector("#pin").onkeydown = (e) => { if (e.key === "Enter") go(); };
    }
    const logout = root.querySelector("#logout");
    if (logout) logout.onclick = async () => { try { await api("POST", "/api/staff/logout"); } catch (e) { /* ignore */ } setStaff(""); render(); };
  };
  render();
  return { update(type) { if (type === "staff") render(); } };
}
