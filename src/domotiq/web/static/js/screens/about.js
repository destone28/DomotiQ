// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
// What the project is, who made it, and whose work it uses.

import { pageHead, store } from "../app.js";
import { lang, t } from "../i18n.js";

const TEXT = {
  it: `<p><b>DomotiQ</b> è una casa intelligente che gira tutta su una sola <b>Arduino UNO Q</b>, senza internet.
  Una webcam guarda la casa dall'alto e riconosce persone, animali, l'auto e gli oggetti che sposti; la casa accende le luci
  dove c'è gente, fa rispettare le sue regole, risponde al citofono, ascolta le domande e fa festa.</p>
  <p>Linux, sulla UNO Q, vede e ragiona: visione artificiale, regole, riconoscimento e sintesi vocale, un piccolo modello
  linguistico, questa pagina web. Il microcontrollore della stessa scheda accende le luci Modulino, legge tasti e sensori
  e comanda la ventola del barbecue.</p>`,
  en: `<p><b>DomotiQ</b> is a smart home that runs entirely on a single <b>Arduino UNO Q</b>, with no internet.
  A webcam looks at the house from above and recognizes people, pets, the car and the objects you move; the house turns
  the lights on where people are, enforces its rules, answers the doorbell, listens to questions and throws parties.</p>
  <p>Linux, on the UNO Q, sees and thinks: computer vision, rules, speech recognition and synthesis, a small language
  model, this web page. The microcontroller on the same board drives the Modulino lights, reads buttons and sensors
  and switches the barbecue fan.</p>`,
};

export function mount(root) {
  root.innerHTML = `
    ${pageHead(t("about.title"))}
    <div class="card">${TEXT[lang()]}</div>
    <div class="card small">
      <p><b>Created by Emilio Destratis</b> (destratis.it) in collaboration with Arduino.</p>
      <p>Software: MIT. Documentation, 3D print files, images: CC BY 4.0.</p>
      <p>Voices: Piper (GPL-3.0, separate program) with <i>it_IT-serena-medium</i> (CC BY 4.0, dataset serena-synthetic-it-27h)
      and <i>en_US-ljspeech-medium</i> (public domain, LJ Speech). Speech recognition: Vosk (Apache-2.0).
      Language model: Qwen2.5-0.5B-Instruct (Apache-2.0) on llama.cpp (MIT). Object categories: YOLOX-Nano (Apache-2.0).
      Fonts: Open Sans and Roboto Mono (SIL OFL 1.1). Full list in the project guide.</p>
      <p class="muted">DomotiQ ${store.state.version}</p>
    </div>`;
}
