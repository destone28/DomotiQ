// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Characters, pets, cars and objects: the list, and the guided registration.

import { api, ask, esc, modal, roomName, setNickname, store, toast } from "../app.js";
import { t, tr } from "../i18n.js";
import { ICONS, Plan } from "../plan.js";

const CATS = ["person", "dog", "cat", "animal", "car", "object"];

async function resizePhoto(file) {
  // make a 1024 px JPEG on the phone before sending it over the hotspot
  const img = await new Promise((resolve, reject) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = reject;
    i.src = URL.createObjectURL(file);
  });
  const scale = Math.min(1, 1024 / Math.max(img.width, img.height));
  const c = document.createElement("canvas");
  c.width = Math.round(img.width * scale);
  c.height = Math.round(img.height * scale);
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
  URL.revokeObjectURL(img.src);
  return new Promise(resolve => c.toBlob(resolve, "image/jpeg", 0.85));
}

function where(identity) {
  const tk = (store.state.tracks || []).find(x => x.identity === identity);
  return tk ? t("id.where", { room: roomName(tk.room) }) : t("id.not_seen");
}

export function mount(root, params) {
  let wizard = null;
  const renderList = () => {
    const ids = store.state.identities || [];
    root.innerHTML = `
      <div class="row spread"><h1>${t("id.title")}</h1><button class="btn primary small" id="add">+ ${t("id.add")}</button></div>
      <div class="card"><ul class="list">${ids.length ? ids.map(i => `
        <li><button class="link" data-id="${i.id}">
          ${i.photo ? `<img class="photo" src="/api/photos/${encodeURIComponent(i.photo)}" alt="">` :
            `<span class="silhouette" style="background:${esc(i.color)}"><svg viewBox="0 0 24 24"><path d="${ICONS[i.category] || ICONS.object}"/></svg></span>`}
          <span class="grow"><span class="title">${esc(i.name)}</span>
          <span class="sub">${esc(t("cat." + i.category))} · ${esc(where(i.id))}</span></span><span>›</span></button></li>`).join("")
        : `<li class="empty">${t("id.empty")}</li>`}</ul></div>`;
    root.querySelector("#add").onclick = () => startWizard();
    root.querySelectorAll("[data-id]").forEach(b => { b.onclick = () => editIdentity(b.dataset.id); });
  };

  const startWizard = (track, session) => { wizard = new Wizard(root, track, () => { wizard = null; renderList(); }, session); };

  const pending = params && params.reg && (store.state.registrations || []).find(r => r.id === params.reg);
  if (pending) startWizard(null, pending);
  else if (params && params.add) startWizard(params.track); else renderList();
  return {
    update(type) {
      if (wizard) wizard.update(type);
      else if (["identities", "tracks", "hello"].includes(type)) renderList();
    },
  };
}

class Wizard {
  constructor(root, track, done, session) {
    this.root = root;
    this.track = track;
    this.done = done;
    this.session = session || null;
    this.photo = null;
    this.plan = null;
    if (this.session) this.show(); else this.step1();       // a registration started at the intercom or by voice
  }

  step1() {
    this.root.innerHTML = `
      <button class="btn small ghost" id="back">‹ ${t("common.back")}</button>
      <h1>${t("id.add")}</h1>
      <div class="card">
        <label class="field"><span>${t("id.name")}</span><input type="text" id="name" maxlength="40" autocomplete="off"></label>
        <label class="field"><span>${t("id.photo")}</span>
          <input type="file" id="photo" accept="image/*" capture="environment" hidden>
          <button class="btn block ghost" id="shoot">📷 ${t("id.take_photo")}</button></label>
        <img id="preview" class="photo" style="width:96px;height:96px" hidden alt="">
        <p class="muted small">${t("id.photo_hint")}</p>
        <button class="btn primary block" id="next">${t("id.start")}</button>
      </div>`;
    const $ = (q) => this.root.querySelector(q);
    $("#back").onclick = () => this.cancel();
    $("#shoot").onclick = () => $("#photo").click();
    $("#photo").onchange = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      try {
        const blob = await resizePhoto(f);
        const r = await api("POST", "/api/photos", blob, { type: "image/jpeg" });
        this.photo = r.photo;
        $("#preview").src = URL.createObjectURL(blob);
        $("#preview").hidden = false;
      } catch (err) { toast(t("common.error"), "alarm"); }
    };
    $("#next").onclick = async () => {
      const name = $("#name").value.trim();
      if (!name) { $("#name").focus(); return; }
      if (!store.nickname) { const n = prompt(t("rules.nickname_ask"), ""); if (n) setNickname(n); }
      try {
        this.session = await api("POST", "/api/register", { name, photo: this.photo });
        if (this.track && this.session.status !== "confirm") {
          try { this.session = await api("POST", `/api/register/${this.session.id}/pick`, { track: this.track }); } catch (err) { /* pick later */ }
        }
        this.show();
      } catch (err) {
        if (err.status === 409) toast(t("id.taken", { name }), "warning", 6000);
        else toast(err.message || t("common.error"), "alarm");
      }
    };
    $("#name").focus();
  }

  show() {
    const s = this.session;
    if (!s) return;
    if (s.status === "done") { toast(t("id.done", { name: s.name }), "success", 6000); this.done(); return; }
    if (s.status === "expired") { toast(t("id.expired"), "warning"); this.done(); return; }
    if (s.status === "cancelled") { this.done(); return; }
    this.root.innerHTML = `
      <h1>${esc(s.name)}</h1>
      <div class="card" id="msg"></div>
      <div class="plan-wrap" id="plan"></div>
      <div class="row" style="justify-content:space-between;margin-top:12px">
        <button class="btn" id="cancel">${t("common.cancel")}</button>
        <span></span>
      </div>`;
    const msg = this.root.querySelector("#msg");
    this.plan = new Plan(this.root.querySelector("#plan"), store.state, {
      onTap: async (id) => {
        if (this.session.status !== "choose" && this.session.status !== "waiting") return;
        try { this.session = await api("POST", `/api/register/${this.session.id}/pick`, { track: id }); this.show(); }
        catch (err) { toast(err.message, "warning"); }
      },
    });
    this.root.querySelector("#cancel").onclick = () => this.cancel();
    if (s.status === "waiting") {
      msg.innerHTML = `<div class="step"><b>1</b><span>${t("id.waiting")}</span></div>`;
      this.plan.setPick((store.state.tracks || []).filter(x => !x.identity).map(x => x.id));
    } else if (s.status === "choose") {
      msg.innerHTML = `<div class="step"><b>2</b><span>${t("id.choose")}</span></div>`;
      this.plan.setPick(s.candidates);
    } else if (s.status === "confirm") {
      this.plan.setPick([s.track]);
      const guess = s.category_guess || "person";
      const label = s.label_name && guess === "object" ? ` (${esc(tr(s.label_name))})` : "";
      const warn = (s.warnings || []).map(w => `<p class="small warn-text">⚠️ ${esc(tr(w))}</p>`).join("");
      msg.innerHTML = `<div class="step"><b>3</b><span>${t("id.confirm")}<br><span class="muted">${t("id.guess", { cat: t("cat." + guess) })}${label}</span></span></div>
        ${warn}
        <div class="pill-list" id="cats">${CATS.map(c => `<button class="chip ${c === guess ? "on" : ""}" data-cat="${c}">${t("cat." + c)}</button>`).join("")}</div>
        <button class="btn primary block" style="margin-top:12px" id="ok">${t("common.save")}</button>`;
      let cat = guess;
      msg.querySelectorAll("[data-cat]").forEach(b => {
        b.onclick = () => { cat = b.dataset.cat; msg.querySelectorAll("[data-cat]").forEach(x => x.classList.toggle("on", x === b)); };
      });
      msg.querySelector("#ok").onclick = async () => {
        try {
          await api("POST", `/api/register/${s.id}/confirm`, { category: cat });
          toast(t("id.done", { name: s.name }), "success", 6000);
          this.done();
        } catch (err) { toast(err.message, "alarm"); }
      };
    }
  }

  async cancel() {
    if (this.session) { try { await api("DELETE", `/api/register/${this.session.id}`); } catch (e) { /* gone */ } }
    this.done();
  }

  update(type) {
    if (type === "registration" && this.session) {
      const mine = (store.state.registrations || []).find(r => r.id === this.session.id);
      if (mine && (mine.status !== this.session.status || JSON.stringify(mine.candidates) !== JSON.stringify(this.session.candidates))) {
        this.session = mine;
        this.show();
      }
    }
    if (type === "tracks" && this.plan) {
      this.plan.update(store.state);
      if (this.session && this.session.status === "waiting") this.plan.setPick((store.state.tracks || []).filter(x => !x.identity).map(x => x.id));
    }
  }
}

function editIdentity(id) {
  const i = store.state.identities.find(x => x.id === id);
  if (!i) return;
  modal((card, close) => {
    card.innerHTML = `
      <h2 style="margin-top:0">${esc(i.name)}</h2>
      ${i.photo ? `<img src="/api/photos/${encodeURIComponent(i.photo)}" style="width:100%;max-height:240px;object-fit:contain;border-radius:12px" alt="">` : ""}
      <label class="field"><span>${t("id.name")}</span><input type="text" id="name" value="${esc(i.name)}"></label>
      <label class="field"><span>${t("id.category")}</span><select id="cat">${CATS.map(c => `<option value="${c}" ${c === i.category ? "selected" : ""}>${t("cat." + c)}</option>`).join("")}</select></label>
      <label class="field"><span>${t("id.alias")}</span><input type="text" id="alias" value="${esc(i.alias_en || "")}"></label>
      <label class="field"><span>${t("id.facts")}</span><textarea id="facts" rows="4" maxlength="900" placeholder="${esc(t("id.facts_ph"))}">${esc((i.facts || []).join("\n"))}</textarea></label>
      <p class="muted small">${t("id.facts_hint")}</p>
      <div class="row" style="justify-content:space-between">
        <button class="btn danger" id="del">${t("common.delete")}</button>
        <div class="row"><button class="btn" id="close">${t("common.close")}</button><button class="btn primary" id="save">${t("common.save")}</button></div>
      </div>`;
    card.querySelector("#close").onclick = close;
    card.querySelector("#save").onclick = async () => {
      try {
        await api("PUT", `/api/identities/${id}`, {
          name: card.querySelector("#name").value, category: card.querySelector("#cat").value,
          alias_en: card.querySelector("#alias").value || null,
          facts: card.querySelector("#facts").value.split("\n").map(s => s.trim()).filter(Boolean),
        });
        close();
      } catch (e) { toast(e.status === 409 ? t("id.taken", { name: card.querySelector("#name").value }) : e.message, "warning"); }
    };
    card.querySelector("#del").onclick = async () => {
      if (!(await ask(t("id.delete_q", { name: i.name })))) return;
      try { await api("DELETE", `/api/identities/${id}`); close(); } catch (e) { toast(e.message, "alarm"); }
    };
  });
}
