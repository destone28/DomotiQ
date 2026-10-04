// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// Live view from the webcam, with the bathroom blurred by the board.

import { pageHead, store } from "../app.js";
import { t } from "../i18n.js";

export function mount(root) {
  let overlay = false;
  try { overlay = localStorage.getItem("domotiq.overlay") === "1"; } catch (e) { /* ignore */ }
  root.innerHTML = `
    ${pageHead(t("live.title"), t("live.lead"))}
    <div class="live"><img id="img" alt="${t("live.title")}"></div>
    <div class="row spread" style="margin-top:10px">
      <span class="muted small" style="flex:1">${t("live.privacy")}</span>
      <label class="row small"><span>${t("live.names")}</span><span class="switch"><input type="checkbox" id="ov" ${overlay ? "checked" : ""}><span></span></span></label>
    </div>
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
  const start = () => { img.src = `/api/stream?fps=5&overlay=${overlay ? 1 : 0}&_=${Date.now()}`; };
  start();
  root.querySelector("#ov").onchange = (e) => {
    overlay = e.target.checked;
    try { localStorage.setItem("domotiq.overlay", overlay ? "1" : "0"); } catch (err) { /* ignore */ }
    start();
  };
  img.onerror = () => setTimeout(start, 2000);
  return { unmount() { img.src = ""; clearInterval(timer); } };
}
