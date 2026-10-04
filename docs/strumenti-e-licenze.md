# Strumenti, librerie, modelli e licenze

Elenco di tutto ciò che il progetto usa, con versione e licenza. Si aggiorna quando si aggiunge o si cambia qualcosa. Le versioni esatte dei pacchetti Python installati sulla scheda sono in `requirements.txt`.

## Licenze del progetto
| Parte | Licenza |
|---|---|
| Codice (`src/`, `firmware/`, `scripts/`, `tests/`) | MIT |
| Documentazione, immagini, STL, dati in `data/` | CC BY 4.0 |

## Scheda e sistema
| Componente | Versione | Licenza | Uso |
|---|---|---|---|
| Arduino UNO Q, immagine Debian 13 | 20251210-442, poi aggiornata | varie (Debian) | sistema operativo |
| arduino-app-cli | 0.7.0 → aggiornato | GPL-3.0 (strumento di sistema, non incluso) | prima configurazione, aggiornamenti |
| arduino-router | di sistema | MPL-2.0 | ponte Linux ↔ MCU |
| NetworkManager, dnsmasq, avahi | di sistema | GPL-2.0+ / LGPL | hotspot, DNS, nomi `.local` |
| ALSA (libasound2 1.2.16 da trixie-backports) | 1.2.16.1 | LGPL-2.1+ | audio |

## Microcontrollore
| Componente | Versione | Licenza | Uso |
|---|---|---|---|
| core `arduino:zephyr` | 1.0.0 | Apache-2.0 | base dello sketch |
| Arduino_RouterBridge | 0.4.3 | MPL-2.0 | chiamate e notifiche verso Linux |
| Arduino_LED_Matrix | 0.1.3 (inclusa nel core) | Apache-2.0, come il core | la matrice LED, luce del locale tecnico |

## Python sulla scheda
| Pacchetto | Licenza | Uso |
|---|---|---|
| FastAPI, Pydantic | MIT | server web |
| Starlette | BSD-3-Clause | server web |
| Uvicorn | BSD-3-Clause | server HTTP |
| NumPy | BSD-3-Clause | calcolo, sintesi audio |
| OpenCV (headless) | Apache-2.0 | visione |
| msgpack | Apache-2.0 | protocollo del router |
| segno | BSD-3-Clause | QR del cartello |
| Vosk | Apache-2.0 | riconoscimento vocale |
| ONNX Runtime | MIT | categoria degli oggetti |
| (nessun SciPy) | — | l'assegnamento ungherese del tracciamento è scritto nel progetto |

## Programmi esterni
| Programma | Licenza | Uso |
|---|---|---|
| Piper (`piper1-gpl`) 1.8.0 | GPL-3.0 | sintesi vocale; ambiente separato, server HTTP locale, non incluso nel codice |
| Flask | BSD-3-Clause | serve al server HTTP di Piper (nel suo ambiente) |
| llama.cpp (`llama-server`), commit 74a7c897 | MIT | modello linguistico; compilato sulla scheda |

## Modelli e voci
| Modello | Licenza | Uso |
|---|---|---|
| vosk-model-small-it-0.22 | Apache-2.0 | riconoscimento vocale italiano |
| vosk-model-small-en-us-0.15 | Apache-2.0 | riconoscimento vocale inglese |
| Qwen2.5-0.5B-Instruct (GGUF) | Apache-2.0 | intenti delle frasi libere |
| YOLOX-Nano (ONNX, release 0.1.1rc0) | Apache-2.0, addestrato su COCO | categoria di un oggetto nuovo |
| Voce Piper it_IT-serena-medium, revisione ea046e84 | CC BY 4.0 (dataset serena-synthetic-it-27h) | voce italiana |
| Voce Piper en_US-ljspeech-medium | pubblico dominio (LJ Speech) | voce inglese |

## Webapp
| Componente | Licenza | Uso |
|---|---|---|
| Open Sans | SIL OFL 1.1 | testo |
| Roboto Mono | SIL OFL 1.1 | numeri e codice |

## Sviluppo (non installati sulla scheda)
| Strumento | Licenza | Uso |
|---|---|---|
| pytest | MIT | test |
| httpx | BSD-3-Clause | test delle API |
| Pillow | MIT-CMU (HPND) | pulizia dei metadati delle immagini |
| uv | MIT / Apache-2.0 | ambiente Python sul PC |
| FreeCAD | LGPL-2.1+ | CAD del diorama |

## Valutati e scartati
| Componente | Motivo |
|---|---|
| Ultralytics YOLOv5/v8/11 | AGPL-3.0 |
| openWakeWord (modelli) | CC BY-NC-SA: uso commerciale escluso |
| Voci Piper derivate da "lessac" (es. it_IT-paola) | dataset con uso commerciale escluso |
| Gemma fino a 3n, Llama | termini d'uso con restrizioni |
| LFM2 | diritti commerciali limitati sopra una soglia di fatturato |
| Qwen2.5-3B | licenza di sola ricerca |
| Edge Impulse / FOMO | addestramento su servizio cloud |
| Brick di App Lab per la voce | disponibili solo su VENTUNO Q |
