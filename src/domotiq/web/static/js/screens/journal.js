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
  // one picture at a time, the latest first: only the ones nobody has judged yet; one tap answers and goes on
  let todo = [], names = [], done = 0, shownAt = 0;
  const back = [];                    // the pictures answered or skipped, to go back and change an answer

  // "right" only for a name still in the house: a deleted character cannot be what a crop is
  const right = (e) => said(e) && (said(e) === NOTHING || names.includes(said(e)));
  const crop = (e) => `/api/journal/${encodeURIComponent(e.id)}.jpg`;

  function render() {
    const e = todo[0];
    shownAt = Date.now();
    if (!e) {
      box.innerHTML = `<p class="empty">${t(done ? "jr.all_done" : "jr.empty")}</p>` +
        (back.length ? `<button class="btn ghost block" data-back="1">↶ ${t("jr.back")}</button>` : "");
      return;
    }
    const ok = right(e);
    const nothing = !(ok && said(e) === NOTHING);                   // "Giusto" already says there is nothing
    const others = names.filter(n => !(ok && n === said(e)));        // "Giusto" already says that name
    box.innerHTML = `
      <p class="muted small">${t("jr.left", { n: todo.length })}</p>
      <img src="${crop(e)}" alt="" width="180" height="180"
        style="display:block;width:180px;max-width:100%;height:auto;margin:6px auto;border-radius:12px">
      <p class="title" style="text-align:center">${esc(title(e, names))}</p>
      <p class="muted small" style="text-align:center">${when(e.t)}${e.figure ? " · " + t("jr.network", { label: esc(e.figure[0] === NOTHING ? t("jr.nothing") : e.figure[0]), p: Math.round(e.figure[1] * 100) }) : ""}</p>
      ${e.label ? `<p class="muted small" style="text-align:center">✓ ${t("jr.answered", { label: esc(e.label.label === NOTHING ? t("jr.no_one") : e.label.label) })}</p>` : ""}
      <div class="${ok && nothing ? "grid2" : ""}" style="margin:10px 0">
        ${ok ? `<button class="btn primary block" data-label="${esc(said(e))}">✓ ${t("jr.right")}: ${esc(said(e) === NOTHING ? t("jr.no_one").toLowerCase() : said(e))}</button>` : ""}
        ${nothing ? `<button class="btn block" data-label="${NOTHING}">${t("jr.no_one")}</button>` : ""}
      </div>
      ${others.length ? `<p class="muted small">${t("jr.is")}</p>
      <div class="grid3" style="margin-bottom:10px">${others.map(n =>
        `<button class="btn small" data-label="${esc(n)}">${esc(n)}</button>`).join("")}</div>` : ""}
      <div class="${back.length ? "grid2" : ""}">
        ${back.length ? `<button class="btn ghost block" data-back="1">↶ ${t("jr.back")}</button>` : ""}
        <button class="btn ghost block" data-skip="1">${t("jr.skip")}</button>
      </div>`;
    if (todo[1]) new Image().src = crop(todo[1]);      // the next one is ready when it comes
  }

  // the answer is saved while the next picture is already shown; if it fails, the picture comes back
  async function label(e, value) {
    const before = e.label;
    e.label = { label: value };
    todo.shift(); back.push(e); done++;
    render();
    try {
      await api("POST", `/api/journal/${encodeURIComponent(e.id)}`, { label: value });
    } catch (err) {
      e.label = before;
      back.splice(back.indexOf(e), 1); todo.unshift(e); done--;
      render();
      toast(err.message || t("common.error"), "alarm");
    }
  }

  box.onclick = (ev) => {
    const b = ev.target.closest("button");
    if (!b || Date.now() - shownAt < 350) return;        // a double tap must not answer the next picture too
    if (b.dataset.back) { todo.unshift(back.pop()); render(); return; }
    const e = todo[0];
    if (!e) return;
    if (b.dataset.skip) { todo.shift(); back.push(e); render(); }   // still to judge next time
    else if (b.dataset.label) label(e, b.dataset.label);
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
