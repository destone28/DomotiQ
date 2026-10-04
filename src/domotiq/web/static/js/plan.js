// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// The plan of the house in SVG, drawn from data/house.json in millimetres.
// The front of the house (the driveway, where visitors stand) is at the bottom.

import { tr } from "./i18n.js";

const NS = "http://www.w3.org/2000/svg";
const X0 = -30, X1 = 720, Y0 = -100, Y1 = 390;      // floor area shown, mm

export const ICONS = {
  person: "M12 2.5a3.2 3.2 0 1 1 0 6.4 3.2 3.2 0 0 1 0-6.4zM7 21v-6.5C7 11.9 9 10.5 12 10.5s5 1.4 5 4V21h-3v-5h-4v5z",
  dog: "M4 10l2-4h3l1 2h5l3-3 2 1-1 4v6h-2v-3H9v3H7v-5L4 11z",
  cat: "M6 4l3 4h6l3-4 1 7c0 4-3 7-7 7s-7-3-7-7zM9.5 12a1 1 0 1 0 0 .1zM14.5 12a1 1 0 1 0 0 .1z",
  animal: "M4 10l2-4h3l1 2h5l3-3 2 1-1 4v6h-2v-3H9v3H7v-5L4 11z",
  car: "M3 15v-3l2-5h10l4 5h2v3h-2a2 2 0 0 1-4 0H9a2 2 0 0 1-4 0zM7 11h4V8.5H8zm6 0h4l-2.5-2.5H13z",
  object: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
};

function el(name, attrs = {}, parent) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

// floor mm -> svg units (1 unit = 1 mm)
const sx = (x) => x - X0;
const sy = (y) => Y1 - y;

function rect(r, attrs, parent) {
  const [x0, x1, y0, y1] = r;
  return el("rect", { x: sx(x0), y: sy(y1), width: x1 - x0, height: y1 - y0, ...attrs }, parent);
}

export function toFloor(svg, clientX, clientY) {
  const pt = svg.createSVGPoint();
  pt.x = clientX; pt.y = clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  return { x: p.x + X0, y: Y1 - p.y };
}

export class Plan {
  constructor(container, state, opts = {}) {
    this.opts = opts;
    this.state = state;
    this.svg = el("svg", { class: "plan", viewBox: `0 0 ${X1 - X0} ${Y1 - Y0}`, role: "img" });
    container.appendChild(this.svg);
    this.pick = new Set();
    this.drawStatic();
    this.dyn = el("g", {}, this.svg);
    this.trackLayer = el("g", {}, this.svg);
    this.update(state);
    if (opts.draggable) this.enableDrag();
  }

  drawStatic() {
    const L = this.state.layout;
    const g = el("g", {}, this.svg);
    rect(L.base, { class: "base", rx: 4 }, g);
    for (const lawn of L.lawns || []) rect(lawn, { class: "lawn" }, g);
    if (L.path) rect(L.path, { class: "path" }, g);
    this.rooms = {};
    for (const r of L.rooms) this.rooms[r.id] = rect(r.rect, { class: "room", "data-room": r.id }, g);
    this.lightGlows = {};
    const glows = el("g", {}, g);
    for (const li of L.lights) {
      const [x0, x1, y0, y1] = li.rect;
      const room = L.rooms.find(r => r.id === li.room);
      // the glow sits inside the room, near the wall light
      const [rx0, rx1, ry0, ry1] = room.rect;
      const cx = Math.min(Math.max((x0 + x1) / 2, rx0 + 28), rx1 - 28);
      const cy = Math.min(Math.max((y0 + y1) / 2, ry0 + 28), ry1 - 28);
      this.lightGlows[li.id] = el("circle", { cx: sx(cx), cy: sy(cy), r: 46, class: "glow", fill: "transparent", opacity: 0.55 }, glows);
    }
    for (const f of L.furniture) {
      const fill = f.color || "#999";
      if (f.circle) el("circle", { cx: sx(f.circle[0]), cy: sy(f.circle[1]), r: f.circle[2], class: "furn", fill }, g);
      else rect(f.rect, { class: "furn", fill, rx: 2 }, g);
    }
    for (const w of L.walls) rect(w.rect, { class: w.kind === "fence" ? "fence" : "wall" }, g);
    for (const d of L.doors) rect(d.rect, { class: "door" }, g);
    const lang = document.documentElement.lang || "it";
    for (const r of L.rooms) {
      const [x0, x1, y0, y1] = r.rect;
      const t = el("text", { x: sx(x0) + 6, y: sy(y1) + 20, class: "label" }, g);
      t.textContent = tr(r.name);
    }
    this.grill = el("g", { opacity: 0 }, g);
    const grill = L.furniture.find(f => f.id === "grill");
    if (grill) {
      const [x0, x1, y0, y1] = grill.rect;
      for (let i = 0; i < 4; i++) {
        el("path", { class: "flame", d: `M${sx(x0 + 10 + i * 13)} ${sy(y0 + 12)} q5 -18 10 0 q-5 6 -10 0z` }, this.grill);
      }
    }
  }

  update(state) {
    this.state = state;
    const s = state;
    // rooms: occupancy and alarms
    const alarmRooms = new Set((s.alerts || []).map(a => a.room).filter(Boolean));
    for (const [id, node] of Object.entries(this.rooms)) {
      const c = (s.counts || {})[id] || {};
      node.setAttribute("class", "room" + (alarmRooms.has(id) ? " alarm" : (c.persons ? " busy" : "")));
    }
    // lights
    const party = s.party;
    for (const [id, node] of Object.entries(this.lightGlows)) {
      const l = (s.lights || {})[id] || { effect: "off" };
      const on = l.effect !== "off" || party;
      node.setAttribute("fill", on ? (l.color || "#fff") : "transparent");
      node.setAttribute("class", "glow " + (party ? "party" : l.effect || ""));
      node.setAttribute("opacity", on ? String(0.25 + 0.5 * Math.min(1, (l.brightness || 60) / 100)) : "0");
    }
    this.grill.setAttribute("opacity", s.grill ? 1 : 0);
    // dynamic badges
    this.dyn.innerHTML = "";
    const L = s.layout;
    const sensors = s.sensors || {};
    const badge = (x, y, text) => {
      const g = el("g", { class: "sensor" }, this.dyn);
      const w = 16 + text.length * 10;
      el("rect", { x: sx(x) - w / 2, y: sy(y) - 13, width: w, height: 26, rx: 13 }, g);
      el("text", { x: sx(x), y: sy(y) + 5.5, "text-anchor": "middle" }, g).textContent = text;
    };
    const th = sensors.thermostat || {};
    if (th.t != null) badge(380, 60, `${th.t.toFixed(1)}°`);
    const ba = sensors.bathroom || {};
    if (ba.rh != null) badge(230, 290, `${Math.round(ba.rh)}%`);
    for (const r of L.rooms) {
      const c = (s.counts || {})[r.id];
      if (!c || !c.total || !r.indoor) continue;
      const [x0, x1, y0, y1] = r.rect;
      const cx = sx(x1) - 16, cy = sy(y1) + 16;
      el("circle", { cx, cy, r: 13, class: "count-bg" }, this.dyn);
      el("text", { x: cx, y: cy + 5.5, "text-anchor": "middle", class: "count" }, this.dyn).textContent = String(c.total);
    }
    this.drawTracks(s.tracks || []);
  }

  drawTracks(tracks) {
    const layer = this.trackLayer;
    const seen = new Set();
    const idents = Object.fromEntries((this.state.identities || []).map(i => [i.id, i]));
    for (const t of tracks) {
      seen.add(t.id);
      let g = layer.querySelector(`[data-id="${t.id}"]`);
      if (!g) {
        g = el("g", { "data-id": t.id }, layer);
        if (this.opts.onTap) g.addEventListener("click", (e) => { e.stopPropagation(); this.opts.onTap(t.id); });
      }
      const ident = idents[t.identity];
      const cat = t.category || "object";
      const name = ident ? ident.name : "";
      const key = [cat, t.color, name, t.uncertain, t.carried, this.pick.has(t.id)].join("|");
      if (g.dataset.key !== key) {
        g.dataset.key = key;
        g.innerHTML = "";
        g.setAttribute("class", "track" + (t.uncertain ? " uncertain" : "") + (t.carried ? " carried" : ""));
        const color = t.color || "#888";
        if (cat === "car") {
          el("rect", { x: -46, y: -22, width: 92, height: 44, rx: 12, class: "body", fill: color }, g);
          el("path", { d: ICONS.car, class: "ico", transform: "translate(-18,-18) scale(1.5)" }, g);
        } else {
          const r = cat === "person" ? 22 : (["dog", "cat", "animal"].includes(cat) ? 18 : 16);
          const k = r / 14;
          el("circle", { r, class: "body", fill: color }, g);
          el("path", { d: ICONS[cat] || ICONS.object, class: "ico", transform: `translate(${-12 * k},${-12 * k}) scale(${k})`, opacity: .95 }, g);
        }
        if (this.pick.has(t.id)) el("circle", { r: 34, class: "pick" }, g);
        const label = name || (t.uncertain ? "?" : "");
        if (label) el("text", { y: cat === "car" ? 42 : 40, "text-anchor": "middle", class: "name" }, g).textContent = label;
      }
      g.setAttribute("transform", `translate(${sx(t.x)},${sy(t.y)})`);
    }
    for (const g of [...layer.children]) if (!seen.has(g.dataset.id)) g.remove();
  }

  setPick(ids) {
    this.pick = new Set(ids || []);
    for (const g of this.trackLayer.children) g.dataset.key = "";
    this.drawTracks(this.state.tracks || []);
  }

  enableDrag() {
    let drag = null;
    let last = 0;
    this.svg.addEventListener("pointerdown", (e) => {
      const g = e.target.closest("[data-id]");
      if (!g) return;
      drag = { id: g.dataset.id, g };
      this.svg.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    this.svg.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const p = toFloor(this.svg, e.clientX, e.clientY);
      drag.g.setAttribute("transform", `translate(${sx(p.x)},${sy(p.y)})`);
      drag.p = p;
      const now = performance.now();
      if (now - last > 120 && this.opts.onDrag) { last = now; this.opts.onDrag(drag.id, p.x, p.y, false); }
    });
    const end = () => {
      if (drag && drag.p && this.opts.onDrag) this.opts.onDrag(drag.id, drag.p.x, drag.p.y, true);
      drag = null;
    };
    this.svg.addEventListener("pointerup", end);
    this.svg.addEventListener("pointercancel", end);
  }
}

export const BOUNDS = { X0, X1, Y0, Y1 };
