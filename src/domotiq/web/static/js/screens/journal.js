// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// The journal of the vision: every presence told to the house, every name given, every blob the network refused,
// with its picture, shown one at a time. Saying whether it was right (or what it really was) teaches the network
// that knows the figurines.

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
    <div class="card" id="one"><p class="muted">${t("common.loading")}</p></div>`;
  const box = root.querySelector("#one");
  // one picture at a time, the latest first: only the ones nobody has judged yet
  let todo = [], names = [], done = 0;

  // "right" only for a name still in the house: a deleted character cannot be what a crop is
  const right = (e) => said(e) && (said(e) === NOTHING || names.includes(said(e)));
  const choice = () => [...names, NOTHING].map(n =>
    `<option value="${esc(n)}">${esc(n === NOTHING ? t("jr.nothing") : n)}</option>`).join("");
  const crop = (e) => `/api/journal/${encodeURIComponent(e.id)}.jpg`;

  function render() {
    const e = todo[0];
    if (!e) {
      box.innerHTML = `<p class="empty">${t(done ? "jr.all_done" : "jr.empty")}</p>`;
      return;
    }
    box.innerHTML = `
      <p class="muted small">${t("jr.left", { n: todo.length })}</p>
      <img src="${crop(e)}" alt="" width="240" height="240"
        style="display:block;width:240px;max-width:100%;height:auto;margin:8px auto;border-radius:12px">
      <p class="title" style="text-align:center">${esc(title(e, names))}</p>
      <p class="muted small" style="text-align:center">${when(e.t)}${e.figure ? " · " + t("jr.network", { label: esc(e.figure[0] === NOTHING ? t("jr.nothing") : e.figure[0]), p: Math.round(e.figure[1] * 100) }) : ""}</p>
      ${right(e) ? `<button class="btn primary block" data-ok="1">${t("jr.right")}</button>` : ""}
      <label class="field"><span>${t("jr.is")}</span>
        <select data-fix="1"><option value="">${t("jr.choose")}</option>${choice()}</select></label>
      <button class="btn ghost block" data-skip="1">${t("jr.skip")}</button>`;
    if (todo[1]) new Image().src = crop(todo[1]);      // the next one is ready when it comes
  }

  async function label(e, value) {
    try {
      await api("POST", `/api/journal/${encodeURIComponent(e.id)}`, { label: value });
      todo = todo.filter(x => x !== e);
      done++;
      render();
    } catch (err) { toast(err.message || t("common.error"), "alarm"); }
  }

  box.onclick = (ev) => {
    const e = todo[0];
    if (!e) return;
    if (ev.target.closest("[data-ok]")) label(e, said(e));
    else if (ev.target.closest("[data-skip]")) { todo.shift(); render(); }   // still to judge next time
  };
  box.onchange = (ev) => {
    const s = ev.target.closest("[data-fix]");
    if (s && s.value && todo[0]) label(todo[0], s.value);
  };

  (async () => {
    try {
      const r = await api("GET", "/api/journal?limit=600");
      names = r.names || [];
      todo = (r.entries || []).filter(e => !e.label);
      render();
    } catch (e) { box.innerHTML = `<p class="empty">${t("common.error")}</p>`; }
  })();
  return {};
}
