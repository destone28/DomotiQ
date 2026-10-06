// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// What the house learned when it did not know: what it was told, what it imagined about itself, what it thought (the
// free answers model). A wrong answer, or a question heard wrong, is corrected here: from then on it is what was told.

import { api, ask, esc, modal, pageHead, toast } from "../app.js";
import { t } from "../i18n.js";

const kind = (i) => i.generated ? "thought" : i.invented ? "imagined" : "told";

function when(ts) {
  return new Date(ts * 1000).toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function mount(root) {
  root.innerHTML = `
    ${pageHead(t("kn.title"), t("kn.lead"))}
    <div class="card"><ul class="list" id="list"><li class="muted">${t("common.loading")}</li></ul></div>`;
  const list = root.querySelector("#list");
  let items = [];

  async function load() {
    try { items = await api("GET", "/api/knowledge"); }
    catch (e) { list.innerHTML = `<li class="empty">${t("common.error")}</li>`; return; }
    list.innerHTML = items.length ? items.map((i, n) => `<li>
      <span class="grow"><span class="title">${esc(i.q)}${i.name ? ` · ${esc(i.name)}` : ""}</span>
        <span class="sub">${esc(i.a)}</span>
        <span class="sub">${t("kn." + kind(i))} · ${when(i.at)}${i.until ? " · " + t("kn.today") : ""}</span></span>
      <button class="btn small" data-edit="${n}">${t("common.edit")}</button></li>`).join("")
      : `<li class="empty">${t("kn.empty")}</li>`;
  }

  function edit(item) {
    modal((card, close) => {
      card.innerHTML = `
        <h2 style="margin-top:0">${t("kn.edit")}</h2>
        <label class="field"><span>${t("kn.question")}</span><input type="text" id="q" maxlength="200" value="${esc(item.q)}"></label>
        <label class="field"><span>${t("kn.answer")}</span><textarea id="a" rows="4" maxlength="300">${esc(item.a)}</textarea></label>
        <p class="muted small">${t("kn.edit_hint")}</p>
        <div class="row spread">
          <button class="btn danger" id="del">${t("kn.forget")}</button>
          <div class="row"><button class="btn" id="close">${t("common.close")}</button><button class="btn primary" id="save">${t("common.save")}</button></div>
        </div>`;
      card.querySelector("#close").onclick = close;
      card.querySelector("#save").onclick = async () => {
        const answer = card.querySelector("#a").value.trim();
        if (!answer) { card.querySelector("#a").focus(); return; }
        try {
          await api("PUT", `/api/knowledge/${item.id}`, { question: card.querySelector("#q").value.trim(), answer });
          close();
          toast(t("kn.saved"), "success");
          load();
        } catch (e) { toast(e.message || t("common.error"), "alarm"); }
      };
      card.querySelector("#del").onclick = async () => {
        if (!(await ask(t("kn.forget_q", { q: item.q })))) return;
        try { await api("DELETE", `/api/knowledge/${item.id}`); load(); } catch (e) { toast(e.message, "alarm"); }
      };
    }, { sticky: true });
  }

  list.onclick = (e) => { const b = e.target.closest("[data-edit]"); if (b) edit(items[+b.dataset.edit]); };
  load();
  return {};
}
