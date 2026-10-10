// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// The journal of the vision: every presence told to the house, every name given, every blob the network refused,
// with its picture. Saying whether it was right (or what it really was) teaches the network that knows the figurines.

import { api, esc, pageHead, toast } from "../app.js";
import { t } from "../i18n.js";

const NOTHING = "niente";

function when(ts) {
  return new Date(ts * 1000).toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function title(e, names) {
  if (e.kind === "scartata") return t("jr.refused");
  const name = e.name ? e.name + (names.includes(e.name) ? "" : ` (${t("jr.gone")})`) : t("jr.nameless");
  return e.kind === "nome" ? t("jr.named", { name }) : t("jr.new", { name });
}

// what the house said: a name, or "niente" for what the network refused
const said = (e) => (e.kind === "scartata" ? NOTHING : e.name);

export function mount(root) {
  root.innerHTML = `
    ${pageHead(t("jr.title"), t("jr.lead"))}
    <div class="card"><ul class="list" id="list"><li class="muted">${t("common.loading")}</li></ul></div>`;
  const list = root.querySelector("#list");
  let entries = [], names = [];

  // "right" only for a name still in the house: a deleted character cannot be what a crop is
  const right = (e) => said(e) && (said(e) === NOTHING || names.includes(said(e)));
  const choice = (e) => [...names, NOTHING].map(n =>
    `<option value="${esc(n)}" ${e.label && e.label.label === n ? "selected" : ""}>${esc(n === NOTHING ? t("jr.nothing") : n)}</option>`).join("");

  function render() {
    list.innerHTML = entries.length ? entries.map((e, i) => `<li>
      <img src="/api/journal/${encodeURIComponent(e.id)}.jpg" alt="" width="64" height="64" style="border-radius:8px;flex:none" loading="lazy">
      <span class="grow"><span class="title">${esc(title(e, names))}</span>
        <span class="sub">${when(e.t)}${e.figure ? " · " + t("jr.network", { label: esc(e.figure[0] === NOTHING ? t("jr.nothing") : e.figure[0]), p: Math.round(e.figure[1] * 100) }) : ""}</span>
        <span class="sub">${e.label ? "✓ " + esc(e.label.label === NOTHING ? t("jr.nothing") : e.label.label) : ""}</span>
        <span class="row" style="margin-top:6px">
          ${right(e) ? `<button class="btn small" data-ok="${i}">${t("jr.right")}</button>` : ""}
          <select data-fix="${i}" aria-label="${t("jr.is")}"><option value="">${t("jr.is")}</option>${choice(e)}</select>
        </span></span></li>`).join("")
      : `<li class="empty">${t("jr.empty")}</li>`;
  }

  async function label(e, value) {
    try {
      await api("POST", `/api/journal/${encodeURIComponent(e.id)}`, { label: value });
      e.label = { label: value };
      toast(t("jr.saved"), "success");
      render();
    } catch (err) { toast(err.message || t("common.error"), "alarm"); }
  }

  list.onclick = (ev) => {
    const b = ev.target.closest("[data-ok]");
    if (b) { const e = entries[+b.dataset.ok]; label(e, said(e)); }
  };
  list.onchange = (ev) => {
    const s = ev.target.closest("[data-fix]");
    if (s && s.value) label(entries[+s.dataset.fix], s.value);
  };

  (async () => {
    try {
      const r = await api("GET", "/api/journal?limit=200");
      entries = r.entries || [];
      names = r.names || [];
      render();
    } catch (e) { list.innerHTML = `<li class="empty">${t("common.error")}</li>`; }
  })();
  return {};
}
