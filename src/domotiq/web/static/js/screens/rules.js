// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// When / If / Then rules: the list, and an editor built from a small schema.

import { api, ask, esc, pageHead, setNickname, store, toast } from "../app.js";
import { t, tr } from "../i18n.js";

// field kinds: room, rooms+all, who, identity, num, text2 (it/en), color, effect, time, sensor,
// quantity, state:<list>, button, scene, op, sound, level, verbosity, bool
const TRIGGERS = {
  enter_room: [["room", "room+"], ["who", "who"]],
  exit_room: [["room", "room+"], ["who", "who"]],
  dwell: [["room", "room"], ["seconds", "num", 5], ["repeat_s", "num", 0], ["who", "who"]],
  count_above: [["room", "room"], ["value", "num", 1], ["grace_s", "num", 2], ["repeat_s", "num", 0], ["who", "who"]],
  count_below: [["room", "room"], ["value", "num", 1], ["grace_s", "num", 0], ["who", "who"]],
  identity_appear: [["who", "who"]],
  identity_disappear: [["who", "who"]],
  time: [["at", "time", "08:00"]],
  sensor_above: [["sensor", "sensor"], ["quantity", "quantity"], ["value", "num", 28]],
  sensor_below: [["sensor", "sensor"], ["quantity", "quantity"], ["value", "num", 18]],
  climate: [["state", "state:hot,cold,normal"]],
  shower: [["state", "state:start,stop"]],
  button: [["button", "button"]],
  car: [["state", "state:arrived,parked,departed,absent"]],
  scene: [["scene", "scene"]],
  grill: [["state", "state:started,ready"]],
  party: [["state", "state:started,ended"]],
};
const CONDITIONS = {
  room_occupied: [["room", "room"], ["who", "who"]],
  room_empty: [["room", "room"], ["who", "who"]],
  count: [["room", "room"], ["op", "op"], ["value", "num", 1], ["who", "who"]],
  identity_present: [["identity", "identity"]],
  identity_absent: [["identity", "identity"]],
  time_between: [["from", "time", "20:00"], ["to", "time", "07:00"]],
  sensor: [["sensor", "sensor"], ["quantity", "quantity"], ["op", "op"], ["value", "num", 25]],
  scene_is: [["scene", "scene"]],
  grill_is: [["on", "bool", true]],
  car_is: [["state", "state:arrived,parked,departed,absent"]],
  climate_is: [["state", "state:hot,cold,normal"]],
};
const ACTIONS = {
  light: [["room", "rooms"], ["color", "color", "#ffaa5a"], ["effect", "effect", "solid"], ["brightness", "num", 60], ["duration_s", "num", 30]],
  light_off: [["rule", "rule"]],
  sound: [["name", "sound", "chime"]],
  say: [["text", "text2"], ["verbosity", "verbosity", "normal"]],
  notify: [["level", "level", "info"], ["text", "text2"]],
  scene: [["scene", "scene"]],
  party: [],
  grill: [],
  wait: [["seconds", "num", 2]],
};

function defaults(schema) {
  const o = {};
  for (const [key, kind, def] of schema) {
    if (def !== undefined) o[key] = def;
    else if (kind === "room" || kind === "room+") o[key] = "living";
    else if (kind === "rooms") o[key] = "all";
    else if (kind === "sensor") o[key] = "thermostat";
    else if (kind === "quantity") o[key] = "t";
    else if (kind === "button") o[key] = "talk";
    else if (kind === "scene") o[key] = "normal";
    else if (kind === "op") o[key] = ">";
    else if (kind === "text2") o[key] = { it: "", en: "" };
    else if (kind.startsWith("state:")) o[key] = kind.slice(6).split(",")[0];
    else if (kind === "identity") o[key] = (store.state.identities[0] || {}).id || "";
  }
  return o;
}

function summary(rule) {
  const w = rule.when || {};
  let s = t("tr." + w.type);
  if (w.room) s += " · " + roomLabel(w.room);
  if (w.value !== undefined && w.type.startsWith("count")) s += " " + w.value;
  if (w.seconds !== undefined) s += ` · ${w.seconds} s`;
  if (w.state) s += " · " + t("st." + w.state);
  if (w.at) s += " · " + w.at;
  return s + " → " + (rule.then || []).map(a => action(rule, a)).join(", ");
}

function action(rule, a) {
  if (a.type === "light_off" && a.rule && a.rule !== rule.id) {
    const other = (store.state.rules || []).find(r => r.id === a.rule);
    return t("ac.light_off_of", { name: other ? tr(other.name) : a.rule });
  }
  return t("ac." + a.type);
}

function roomLabel(id) {
  if (id === "all") return t("common.all_rooms");
  if (id === "indoor") return t("common.indoor_rooms");
  if (id === "any") return t("common.any_room");
  const r = store.state.layout.rooms.find(x => x.id === id);
  return r ? tr(r.name) : id;
}

export function mount(root, params) {
  const renderList = () => {
    const rules = store.state.rules || [];
    root.innerHTML = `
      ${pageHead(t("rules.title"), t("rules.lead"), `<button class="btn primary small" id="new">+ ${t("rules.new")}</button>`)}
      <div class="card"><ul class="list">${rules.map(r => `
        <li><span class="switch"><input type="checkbox" data-toggle="${r.id}" ${r.enabled ? "checked" : ""}><span></span></span>
        <button class="link grow" data-edit="${r.id}"><span class="grow"><span class="title">${r.alert ? "⚠️ " : ""}${esc(tr(r.name))}</span>
        <span class="sub">${esc(summary(r))}</span></span></button></li>`).join("")}</ul></div>`;
    root.querySelector("#new").onclick = () => edit(null);
    root.querySelectorAll("[data-edit]").forEach(b => { b.onclick = () => edit(b.dataset.edit); });
    root.querySelectorAll("[data-toggle]").forEach(c => {
      c.onchange = async () => {
        await ensureNickname();
        try { await api("POST", `/api/rules/${c.dataset.toggle}/enabled`, { enabled: c.checked }); }
        catch (e) { toast(e.message, "alarm"); c.checked = !c.checked; }
      };
    });
  };

  const edit = (id) => {
    const original = id ? (store.state.rules || []).find(r => r.id === id) : null;
    const rule = original ? JSON.parse(JSON.stringify(original)) : {
      name: { it: "", en: "" }, enabled: true, priority: 50, cooldown_s: 10, alert: false,
      when: { type: "enter_room", ...defaults(TRIGGERS.enter_room) }, if: [], then: [{ type: "say", ...defaults(ACTIONS.say) }],
    };
    editing = true;
    renderEditor(root, rule, !!original, () => { editing = false; renderList(); });
  };

  let editing = false;
  if (params && params.edit) edit(params.edit); else renderList();
  return { update(type) { if (type === "rules" && !editing) renderList(); } };
}

async function ensureNickname() {
  if (store.nickname) return;
  const name = prompt(t("rules.nickname_ask"), "");
  if (name) setNickname(name);
}

function field(key, kind, value) {
  const s = store.state;
  const lbl = t("f." + ({ repeat_s: "repeat", grace_s: "grace", duration_s: "duration", at: "at" }[key] || key));
  const opt = (v, label, sel) => `<option value="${esc(v)}" ${sel ? "selected" : ""}>${esc(label)}</option>`;
  let input;
  if (kind === "room" || kind === "rooms" || kind === "room+") {
    const rooms = s.layout.rooms.map(r => opt(r.id, tr(r.name), value === r.id));
    const extra = kind === "rooms" ? opt("all", t("common.all_rooms"), value === "all")
      : kind === "room+" ? opt("indoor", t("common.indoor_rooms"), value === "indoor") + opt("any", t("common.any_room"), value === "any") : "";
    input = `<select data-k="${key}">${extra}${rooms.join("")}</select>`;
  } else if (kind === "who") {
    const w = value || {};
    const cats = ["any", "person", "animal", "dog", "cat", "car", "object"];
    input = `<div class="grid2"><select data-k="${key}.category">${cats.map(c => opt(c, t("cat." + c), (w.category || "any") === c)).join("")}</select>
      <select data-k="${key}.identity">${opt("", t("common.everyone"), !w.identity)}${s.identities.map(i => opt(i.id, i.name, w.identity === i.id)).join("")}</select></div>`;
  } else if (kind === "identity") {
    input = `<select data-k="${key}">${s.identities.map(i => opt(i.id, i.name, value === i.id)).join("")}</select>`;
  } else if (kind === "num") {
    input = `<input type="number" data-k="${key}" value="${value ?? ""}" step="any">`;
  } else if (kind === "time") {
    input = `<input type="time" data-k="${key}" value="${esc(value || "")}">`;
  } else if (kind === "text2") {
    const v = value || {};
    return `<label class="field"><span>${t("f.text_it")}</span><input type="text" data-k="${key}.it" value="${esc(v.it || "")}"></label>
      <label class="field"><span>${t("f.text_en")}</span><input type="text" data-k="${key}.en" value="${esc(v.en || "")}"></label>
      <p class="muted small">{name} {room} {room_in} {count} {temp} {rh} {time}</p>`;
  } else if (kind === "color") {
    input = `<input type="color" data-k="${key}" value="${esc(value || "#ffffff")}">`;
  } else if (kind === "effect") {
    input = `<select data-k="${key}">${["solid", "breathe", "blink", "wave", "rainbow", "sparkle", "fire", "alarm", "cool", "warm"]
      .map(e => opt(e, t("effect." + e), value === e)).join("")}</select>`;
  } else if (kind === "sensor") {
    input = `<select data-k="${key}">${["thermostat", "bathroom"].map(x => opt(x, t("s." + x), value === x)).join("")}</select>`;
  } else if (kind === "quantity") {
    input = `<select data-k="${key}">${["t", "rh"].map(x => opt(x, t("q." + x), value === x)).join("")}</select>`;
  } else if (kind === "op") {
    input = `<select data-k="${key}">${[">", ">=", "<", "<=", "="].map(x => opt(x, x, value === x)).join("")}</select>`;
  } else if (kind === "button") {
    input = `<select data-k="${key}">${["talk", "intercom", "language"].map(x => opt(x, t("btn." + x), value === x)).join("")}</select>`;
  } else if (kind === "scene") {
    input = `<select data-k="${key}">${Object.keys(s.scenes).map(x => opt(x, tr(s.scenes[x].name), value === x)).join("")}</select>`;
  } else if (kind === "sound") {
    input = `<select data-k="${key}">${["chime", "bell", "alarm", "beep", "notify"].map(x => opt(x, t("snd." + x), value === x)).join("")}</select>`;
  } else if (kind === "level") {
    input = `<select data-k="${key}">${["info", "success", "warning", "alarm"].map(x => opt(x, t("lvl." + x), value === x)).join("")}</select>`;
  } else if (kind === "verbosity") {
    input = `<select data-k="${key}">${["normal", "chatty"].map(x => opt(x, t("cmd." + x), value === x)).join("")}</select>`;
  } else if (kind === "rule") {
    input = `<select data-k="${key}">${opt("", t("f.this_rule"), !value)}${(s.rules || []).map(r => opt(r.id, tr(r.name), value === r.id)).join("")}</select>`;
  } else if (kind === "bool") {
    input = `<span class="switch"><input type="checkbox" data-k="${key}" ${value ? "checked" : ""}><span></span></span>`;
  } else if (kind.startsWith("state:")) {
    input = `<select data-k="${key}">${kind.slice(6).split(",").map(x => opt(x, t("st." + x), value === x)).join("")}</select>`;
  }
  return `<label class="field"><span>${lbl}</span>${input}</label>`;
}

function readFields(node, target, schema) {
  for (const [key, kind] of schema) {
    if (kind === "who") {
      const cat = node.querySelector(`[data-k="${key}.category"]`).value;
      const ident = node.querySelector(`[data-k="${key}.identity"]`).value;
      const w = {};
      if (cat !== "any") w.category = cat;
      if (ident) w.identity = ident;
      if (Object.keys(w).length) target[key] = w; else delete target[key];
    } else if (kind === "text2") {
      target[key] = { it: node.querySelector(`[data-k="${key}.it"]`).value, en: node.querySelector(`[data-k="${key}.en"]`).value };
    } else if (kind === "bool") {
      target[key] = node.querySelector(`[data-k="${key}"]`).checked;
    } else {
      const inp = node.querySelector(`[data-k="${key}"]`);
      if (!inp) continue;
      if (kind === "num") {
        if (inp.value === "") delete target[key]; else target[key] = Number(inp.value);
      } else if (kind === "rule") {
        if (inp.value) target[key] = inp.value; else delete target[key];
      } else target[key] = inp.value;
    }
  }
}

function renderEditor(root, rule, existing, done) {
  const part = (cls, title, items, catalog, kindLabel, addLabel) => `
    <div class="rule-part ${cls}"><h3>${title}</h3>
      ${items.map((it, i) => `<div class="rule-item" data-part="${cls}" data-i="${i}">
        <div class="row spread"><select data-type>${Object.keys(catalog).map(k => `<option value="${k}" ${it.type === k ? "selected" : ""}>${t(kindLabel + "." + k)}</option>`).join("")}</select>
        ${cls !== "when" ? `<button class="btn small ghost" data-del>✕</button>` : ""}</div>
        ${catalog[it.type].map(([k, kind]) => field(k, kind, it[k])).join("")}
      </div>`).join("") || `<p class="muted small">${t("rules.no_cond")}</p>`}
      ${addLabel ? `<button class="btn small" data-add="${cls}">+ ${addLabel}</button>` : ""}
    </div>`;
  root.innerHTML = `
    <button class="btn small ghost" id="back">‹ ${t("common.back")}</button>
    <h1>${existing ? tr(rule.name) : t("rules.new")}</h1>
    <div class="card">
      <label class="field"><span>${t("rules.name")} (IT)</span><input type="text" id="name-it" value="${esc(rule.name.it || "")}"></label>
      <label class="field"><span>${t("rules.name")} (EN)</span><input type="text" id="name-en" value="${esc(rule.name.en || "")}"></label>
      <div class="grid2">
        <label class="field"><span>${t("rules.priority")}</span><input type="number" id="prio" min="1" max="98" value="${rule.priority}"></label>
        <label class="field"><span>${t("rules.cooldown")}</span><input type="number" id="cool" min="0" value="${rule.cooldown_s}"></label>
      </div>
      <label class="row spread"><span>${t("rules.enabled")}</span><span class="switch"><input type="checkbox" id="en" ${rule.enabled ? "checked" : ""}><span></span></span></label>
      <label class="row spread" style="margin-top:8px"><span>${t("rules.alert")}</span><span class="switch"><input type="checkbox" id="al" ${rule.alert ? "checked" : ""}><span></span></span></label>
    </div>
    ${part("when", t("rules.when"), [rule.when], TRIGGERS, "tr", null)}
    ${part("if", t("rules.if"), rule.if, CONDITIONS, "co", t("rules.add_cond"))}
    ${part("then", t("rules.then"), rule.then, ACTIONS, "ac", t("rules.add_action"))}
    <div class="row" style="justify-content:space-between;margin-top:14px">
      ${existing ? `<button class="btn danger" id="del">${t("common.delete")}</button>` : "<span></span>"}
      <button class="btn primary" id="save">${t("common.save")}</button>
    </div>`;

  const collect = () => {
    rule.name = { it: root.querySelector("#name-it").value.trim(), en: root.querySelector("#name-en").value.trim() };
    rule.priority = Number(root.querySelector("#prio").value || 50);
    rule.cooldown_s = Number(root.querySelector("#cool").value || 0);
    rule.enabled = root.querySelector("#en").checked;
    rule.alert = root.querySelector("#al").checked;
    root.querySelectorAll(".rule-item").forEach(node => {
      const partName = node.dataset.part, i = +node.dataset.i;
      const target = partName === "when" ? rule.when : rule[partName][i];
      const catalog = partName === "when" ? TRIGGERS : partName === "if" ? CONDITIONS : ACTIONS;
      readFields(node, target, catalog[target.type]);
    });
  };
  const rerender = () => { collect(); renderEditor(root, rule, existing, done); };

  root.querySelector("#back").onclick = done;
  root.querySelectorAll(".rule-item [data-type]").forEach(sel => {
    sel.onchange = () => {
      collect();
      const node = sel.closest(".rule-item");
      const partName = node.dataset.part, i = +node.dataset.i;
      const catalog = partName === "when" ? TRIGGERS : partName === "if" ? CONDITIONS : ACTIONS;
      const fresh = { type: sel.value, ...defaults(catalog[sel.value]) };
      if (partName === "when") rule.when = fresh; else rule[partName][i] = fresh;
      renderEditor(root, rule, existing, done);
    };
  });
  root.querySelectorAll("[data-del]").forEach(b => {
    b.onclick = () => {
      collect();
      const node = b.closest(".rule-item");
      rule[node.dataset.part].splice(+node.dataset.i, 1);
      renderEditor(root, rule, existing, done);
    };
  });
  root.querySelectorAll("[data-add]").forEach(b => {
    b.onclick = () => {
      collect();
      if (b.dataset.add === "if") rule.if.push({ type: "room_occupied", ...defaults(CONDITIONS.room_occupied) });
      else rule.then.push({ type: "light", ...defaults(ACTIONS.light) });
      renderEditor(root, rule, existing, done);
    };
  });
  root.querySelector("#save").onclick = async () => {
    collect();
    if (!rule.name.it && !rule.name.en) { toast(t("rules.name") + "?", "warning"); return; }
    await ensureNickname();
    try {
      if (existing) await api("PUT", `/api/rules/${rule.id}`, rule);
      else await api("POST", "/api/rules", rule);
      toast(t("common.saved"), "success");
      done();
    } catch (e) { toast(e.message, "alarm"); }
  };
  const del = root.querySelector("#del");
  if (del) del.onclick = async () => {
    if (!(await ask(t("set.sure")))) return;
    await ensureNickname();
    try { await api("DELETE", `/api/rules/${rule.id}`); toast(t("rules.deleted")); done(); }
    catch (e) { toast(e.message, "alarm"); }
  };
  void rerender;
}
