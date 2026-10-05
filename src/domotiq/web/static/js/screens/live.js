// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Live view from the webcam, with the bathroom blurred by the board.

import { pageHead, store } from "../app.js";
import { t } from "../i18n.js";
import { adopt } from "./home.js";

export function mount(root) {
  let overlay = false;
  try { overlay = localStorage.getItem("domotiq.overlay") === "1"; } catch (e) { /* ignore */ }
  root.innerHTML = `
    ${pageHead(t("live.title"), t("live.lead"))}
    <div class="live"><img id="img" alt="${t("live.title")}"></div>
    <div class="row spread" style="margin-top:10px">
      <button class="btn small" id="add-unseen">➕ ${t("add.button")}</button>
      <label class="row small"><span>${t("live.names")}</span><span class="switch"><input type="checkbox" id="ov" ${overlay ? "checked" : ""}><span></span></span></label>
    </div>
    <p class="muted small" id="add-hint" hidden>${t("add.tap_picture")}</p>
    <p class="muted" id="nocam" hidden>${t("live.nocam")}</p>`;
  const nocam = root.querySelector("#nocam");
  const camOk = () => {
    const s = store.state || {};
    return (s.status && s.status.camera) || (s.sim && s.sim.enabled);
  };
  // a moment without pictures (a reconnection, the light being set) is not a webcam unplugged
  let missing = 0;
  const check = () => { missing = camOk() ? 0 : missing + 1; nocam.hidden = missing < 3; };
  check();
  const timer = setInterval(check, 1000);
  const img = root.querySelector("#img");
  let gone = false;
  const start = () => { if (!gone) img.src = `/api/stream?fps=5&overlay=${overlay ? 1 : 0}&_=${Date.now()}`; };
  start();
  root.querySelector("#ov").onchange = (e) => {
    overlay = e.target.checked;
    try { localStorage.setItem("domotiq.overlay", overlay ? "1" : "0"); } catch (err) { /* ignore */ }
    start();
  };
  img.onerror = () => setTimeout(start, 2000);
  // something the house does not follow, tapped in the picture: it becomes a presence, and the phone asks who it is
  const btn = root.querySelector("#add-unseen");
  const hint = root.querySelector("#add-hint");
  let picking = false;
  const stopPicking = () => {
    picking = false; img.classList.remove("picking"); hint.hidden = true;
    btn.textContent = "➕ " + t("add.button");
  };
  btn.onclick = () => {
    if (picking) { stopPicking(); return; }
    picking = true; img.classList.add("picking"); hint.hidden = false;
    btn.textContent = t("common.cancel");
  };
  img.addEventListener("click", (e) => {
    if (!picking) return;
    const box = img.getBoundingClientRect();
    stopPicking();
    adopt({ u: (e.clientX - box.left) / box.width, v: (e.clientY - box.top) / box.height });
  });
  // leaving the page closes the stream for good: src = "" would fire onerror, and the stream would come back
  // on an image nobody sees
  return { unmount() { gone = true; img.onerror = null; img.removeAttribute("src"); clearInterval(timer); } };
}
