// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Events, what the house said, the change log and the history of each character.

import { api, esc, identityName, roomName, store } from "../app.js";
import { t, tr } from "../i18n.js";

const ICON = { room_enter: "➡️", room_exit: "⬅️", car: "🚗", rule: "📏", notify: "🔔", say: "🔊", climate: "🌡️",
  shower: "🚿", scene: "🎬", registered: "✨", grill: "🔥", party: "🎉", command: "👆", language: "🌐" };

function time(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function describe(ev) {
  const d = ev.data || {};
  const name = d.name || identityName(d.identity) || t("cat." + (d.category || "person"));
  switch (ev.type) {
    case "room_enter": return t("ev.room_enter", { name, room: roomName(d.room) });
    case "room_exit": return t("ev.room_exit", { name, room: roomName(d.room) });
    case "car": return t("ev.car", { state: t("car." + d.state) });
    case "rule": return t("ev.rule", { name: tr(d.name) });
    case "notify": return tr(d.text);
    case "say": return "“" + (d.text || "") + "”";
    case "climate": return t("ev.climate", { state: t("st." + d.state) });
    case "shower": return t("ev.shower", { state: t("st." + d.state) });
    case "scene": return t("ev.scene", { scene: tr((store.state.scenes[d.scene] || {}).name) || d.scene });
    case "registered": return t("ev.registered", { name: d.name });
    case "grill": return t("ev.grill", { state: t("st." + d.state) });
    case "party": return t("ev.party", { state: t("st." + d.state) });
    case "command": return t("ev.command", { name: d.name }) + (d.nickname ? ` · ${d.nickname}` : "");
    case "language": return t("ev.language", { language: d.language });
    default: return ev.type;
  }
}

export function mount(root) {
  let tab = "events";
  root.innerHTML = `
    <h1>${t("ev.title")}</h1>
    <div class="pill-list" id="tabs">
      ${["events", "said", "changes", "history"].map(k => `<button class="chip" data-tab="${k}">${t("ev." + k)}</button>`).join("")}
    </div>
    <div class="card"><ul class="list" id="list"></ul></div>`;
  const list = root.querySelector("#list");

  async function load() {
    root.querySelectorAll("[data-tab]").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
    list.innerHTML = `<li class="muted">${t("common.loading")}</li>`;
    try {
      if (tab === "events" || tab === "said") {
        const types = tab === "said" ? "say" : "room_enter,room_exit,car,rule,notify,climate,shower,scene,registered,grill,party,command,language";
        const rows = await api("GET", `/api/events?limit=150&types=${types}`);
        list.innerHTML = rows.length ? rows.map(ev => `<li><span>${ICON[ev.type] || "•"}</span>
          <span class="grow"><span class="title" style="font-weight:${ev.level === "info" ? 400 : 700}">${esc(describe(ev))}</span>
          <span class="sub mono">${time(ev.ts)}</span></span></li>`).join("") : `<li class="empty">${t("ev.empty")}</li>`;
      } else if (tab === "changes") {
        const rows = await api("GET", "/api/audit?limit=150");
        list.innerHTML = rows.length ? rows.map(a => {
          const who = a.nickname || t("audit.someone");
          const thing = a.after && a.after.name ? (typeof a.after.name === "string" ? a.after.name : tr(a.after.name))
            : a.before && a.before.name ? (typeof a.before.name === "string" ? a.before.name : tr(a.before.name)) : (a.entity_id || "");
          return `<li><span>✏️</span><span class="grow"><span class="title">${esc(who)} ${t("audit." + a.action)} ${t("audit." + a.entity)} ${esc(thing)}</span>
            <span class="sub mono">${time(a.ts)} · ${esc(a.device || "")}</span></span></li>`;
        }).join("") : `<li class="empty">${t("ev.empty")}</li>`;
      } else {
        const idents = store.state.identities;
        if (!idents.length) { list.innerHTML = `<li class="empty">${t("id.empty")}</li>`; return; }
        const parts = await Promise.all(idents.map(async i => {
          const h = await api("GET", `/api/history/${i.id}?hours=24`);
          const steps = h.rooms.slice(-12).map(r => `${time(r.ts).slice(0, 5)} ${esc(roomName(r.room))}`).join(" → ");
          return `<li><span class="silhouette" style="background:${esc(i.color)}"></span><span class="grow">
            <span class="title">${esc(i.name)}</span><span class="sub">${steps || t("ev.empty")}</span></span></li>`;
        }));
        list.innerHTML = parts.join("");
      }
    } catch (e) {
      list.innerHTML = `<li class="empty">${t("common.error")}</li>`;
    }
  }
  root.querySelector("#tabs").onclick = (e) => { const b = e.target.closest("[data-tab]"); if (b) { tab = b.dataset.tab; load(); } };
  load();
  let timer = null;
  return {
    update(type) {
      if (["notify", "say", "rule_fired", "house", "registration"].includes(type) && tab !== "history") {
        clearTimeout(timer); timer = setTimeout(load, 800);
      }
    },
    unmount() { clearTimeout(timer); },
  };
}
