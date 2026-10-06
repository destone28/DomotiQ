// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Camera calibration (4 corners, light and empty house) and dataset tools.

import { api, pageHead, toast } from "../app.js";
import { lang, t } from "../i18n.js";

export function mount(root) {
  const corners = [];
  let overlay = true;
  root.innerHTML = `
    ${pageHead(t("cal.title"), t("cal.lead"))}
    <div class="card">
      <div class="step"><b>1</b><span>${t("cal.step1")}</span></div>
      <div class="step"><b>2</b><span>${t("cal.step2")} <span id="next-corner" class="chip warn"></span></span></div>
      <div class="cal-img" id="imgbox"><img id="img" alt=""></div>
      <div class="row" style="margin-top:10px">
        <button class="btn" id="undo">↶</button>
        <button class="btn primary" id="use" disabled>${t("cal.save_corners")}</button>
        <label class="row small"><span>${t("cal.overlay")}</span><span class="switch"><input type="checkbox" id="ov" checked><span></span></span></label>
      </div>
      <div class="step"><b>3</b><span>${t("cal.step3")}</span></div>
      <div class="grid2">
        <button class="btn primary" id="adjust">${t("cal.adjust")}</button>
        <button class="btn" id="empty">${t("cal.empty")}</button>
      </div>
      <p class="muted small" id="status"></p>
    </div>
    <div class="loading" id="loading" hidden><div class="box"><div class="spinner"></div><p id="loading-text"></p></div></div>
    <h2>${t("cal.dataset")}</h2>
    <div class="card grid2">
      <button class="btn" id="cap">${t("cal.capture")}</button>
      <button class="btn" id="burst">${t("cal.burst")}</button>
      <button class="btn" id="rec">${t("cal.record")}</button>
      <a class="btn ghost" href="#" id="export">${t("cal.export")}</a>
    </div>`;
  const $ = (q) => root.querySelector(q);
  const names = t("cal.corners");
  const img = $("#img");
  const load = () => { img.src = `/api/vision/raw.jpg?overlay=${overlay ? 1 : 0}&_=${Date.now()}`; };
  const marks = () => {
    root.querySelectorAll(".cal-img .mark").forEach(m => m.remove());
    corners.forEach((p, i) => {
      const m = document.createElement("div");
      m.className = "mark";
      m.style.left = (p.u * 100) + "%";
      m.style.top = (p.v * 100) + "%";
      m.textContent = String(i + 1);
      $("#imgbox").appendChild(m);
    });
    $("#next-corner").textContent = corners.length < 4 ? `${corners.length + 1}: ${names[corners.length]}` : "✓";
    $("#use").disabled = corners.length !== 4;
  };
  img.onclick = (e) => {
    if (corners.length >= 4) return;
    const r = img.getBoundingClientRect();
    corners.push({ u: (e.clientX - r.left) / r.width, v: (e.clientY - r.top) / r.height });
    marks();
  };
  $("#undo").onclick = () => { corners.pop(); marks(); };
  $("#ov").onchange = (e) => { overlay = e.target.checked; load(); };
  // while the house works the page says so, and nothing can be pressed twice
  const WORKING = { corners: "cal.working_corners", adjust: "cal.working", empty: "cal.working_empty",
    capture: "cal.working_capture", record: "cal.working_record" };
  let busy = false;
  const cmd = async (name, body) => {
    if (busy) return null;
    busy = true;
    $("#loading-text").textContent = t(WORKING[name] || "cal.working_generic");
    $("#loading").hidden = false;
    root.querySelectorAll("button").forEach(b => { b.disabled = true; });
    try {
      const r = await api("POST", `/api/vision/${name}`, body || {});
      const msg = (lang() === "en" && r.message_en) || r.message;
      $("#status").textContent = msg || (r.ok ? "OK" : (r.error || ""));
      if (r.ok) toast(msg || t("common.done"), "success");
      else if (r.error) toast(msg || r.error, "warning");
      load();
      return r;
    } catch (e) { toast(e.message, "alarm"); return null; } finally {
      busy = false;
      $("#loading").hidden = true;
      root.querySelectorAll("button").forEach(b => { b.disabled = false; });
      marks();
    }
  };
  // the light of the webcam and the empty house go together: right after the corners, and on request
  const adjust = () => cmd("adjust");
  $("#use").onclick = async () => {
    const r = await cmd("corners", { points: corners.map(p => [p.u, p.v]) });
    if (r && r.ok) { corners.length = 0; marks(); await adjust(); }
  };
  $("#empty").onclick = () => cmd("empty");
  $("#adjust").onclick = adjust;
  $("#cap").onclick = () => cmd("capture", { count: 1 });
  $("#burst").onclick = () => cmd("capture", { count: 10 });
  $("#rec").onclick = () => cmd("record", { seconds: 60 });
  $("#export").onclick = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch("/api/dataset.zip");
      if (!res.ok) throw new Error(res.statusText);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob());
      a.download = "domotiq-dataset.zip";
      a.click();
    } catch (err) { toast(err.message, "warning"); }
  };
  marks();
  load();
  const timer = setInterval(load, 3000);
  return { unmount() { clearInterval(timer); } };
}
