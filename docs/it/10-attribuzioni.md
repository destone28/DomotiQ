# 10. Attribuzioni

DomotiQ si regge sul lavoro di molti progetti aperti. Questo capitolo elenca ogni componente di terze parti usato dalla casa, con la sua licenza e un link, e le licenze del progetto stesso.

## Il progetto

> Created by Emilio Destratis ([destratis.it](https://destratis.it)) in collaboration with Arduino.

| Parte | Licenza |
|---|---|
| Codice sorgente: `src/`, `firmware/`, `scripts/`, `tests/` | Licenza MIT, vedi [LICENSE](../../LICENSE) |
| Tutto il resto: documentazione e guide (`docs/`, i README), immagini e schemi, i file di stampa 3D in `hardware/stl/`, i dati della casa, le frasi e le regole di partenza in `data/` | Creative Commons Attribuzione 4.0 Internazionale ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.it)), vedi [LICENSE-DOCS.md](../../LICENSE-DOCS.md) |

Chi riutilizza, modifica o ridistribuisce il progetto, anche a fini commerciali, deve riportare l'attribuzione qui sopra, un link alla licenza e l'indicazione delle modifiche apportate.

Le statuine e l'auto sono modelli di terze parti e non sono in questo repository; i link e le loro licenze sono sulla pagina del progetto.

## Scheda e sistema

| Componente | Versione | Licenza | Uso |
|---|---|---|---|
| Immagine [Debian](https://www.debian.org) della Arduino UNO Q | 20251210-442, poi aggiornata | varie (Debian) | sistema operativo |
| [arduino-app-cli](https://github.com/arduino/arduino-app-cli) | 0.7.0, poi aggiornato | GPL-3.0 (strumento di sistema, non incluso) | prima configurazione, aggiornamenti di sistema, nome della scheda |
| [arduino-router](https://github.com/arduino/arduino-router) | quello del sistema | MPL-2.0 | ponte tra Linux e il microcontrollore |
| [NetworkManager](https://networkmanager.dev), [dnsmasq](https://thekelleys.org.uk/dnsmasq/doc.html), [Avahi](https://avahi.org) | quelli del sistema | GPL-2.0+ / LGPL | hotspot, DNS, nomi `.local` |
| [ALSA](https://www.alsa-project.org) (`libasound2` da trixie-backports) | 1.2.16.1 | LGPL-2.1+ | audio |

## Microcontrollore

| Componente | Versione | Licenza | Uso |
|---|---|---|---|
| [Arduino core for Zephyr](https://github.com/arduino/ArduinoCore-zephyr) (`arduino:zephyr`) | 1.0.0 | Apache-2.0 | base dello sketch |
| [Arduino_RouterBridge](https://github.com/arduino-libraries/Arduino_RouterBridge) | 0.4.3 | MPL-2.0 | chiamate e notifiche da e verso Linux |
| Configurazione predefinita del [VL53L4CD](https://www.st.com/en/imaging-and-photonics-solutions/vl53l4cd.html), dal driver ultra-lite di STMicroelectronics | valori del produttore | BSD-3-Clause | avvio del sensore Distance |

## Python sulla scheda

I pacchetti principali dell'applicazione:

| Pacchetto | Licenza | Uso |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | server web |
| [Starlette](https://github.com/Kludex/starlette) | BSD-3-Clause | server web |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | server web |
| [Uvicorn](https://uvicorn.dev) | BSD-3-Clause | server HTTP |
| [NumPy](https://numpy.org) | BSD-3-Clause | calcolo, sintesi dei suoni |
| [OpenCV](https://opencv.org) ([opencv-python-headless](https://github.com/opencv/opencv-python)) | Apache-2.0 | visione artificiale |
| [msgpack](https://github.com/msgpack/msgpack-python) | Apache-2.0 | protocollo del router |
| [segno](https://github.com/heuer/segno) | BSD-3-Clause | QR del cartello |
| [Vosk](https://alphacephei.com/vosk/) | Apache-2.0 | riconoscimento vocale |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT | categoria degli oggetti dalle foto |

Non c'è SciPy: l'assegnazione ungherese usata dall'inseguimento è scritta nel progetto.

L'elenco completo dei pacchetti installati sulla scheda, con le versioni esatte, è in `requirements.txt`. Le loro licenze:

| Pacchetto | Licenza |
|---|---|
| [annotated-doc](https://pypi.org/project/annotated-doc/), [annotated-types](https://pypi.org/project/annotated-types/), [anyio](https://pypi.org/project/anyio/), [cffi](https://pypi.org/project/cffi/), [charset-normalizer](https://pypi.org/project/charset-normalizer/), [h11](https://pypi.org/project/h11/), [httptools](https://pypi.org/project/httptools/), [pydantic_core](https://pypi.org/project/pydantic-core/), [PyYAML](https://pypi.org/project/PyYAML/), [srt](https://pypi.org/project/srt/), [typing-inspection](https://pypi.org/project/typing-inspection/), [urllib3](https://pypi.org/project/urllib3/), [watchfiles](https://pypi.org/project/watchfiles/) | MIT |
| [click](https://pypi.org/project/click/), [idna](https://pypi.org/project/idna/), [protobuf](https://pypi.org/project/protobuf/), [pycparser](https://pypi.org/project/pycparser/), [python-dotenv](https://pypi.org/project/python-dotenv/), [websockets](https://pypi.org/project/websockets/) | BSD-3-Clause |
| [flatbuffers](https://pypi.org/project/flatbuffers/), [requests](https://pypi.org/project/requests/) | Apache-2.0 |
| [packaging](https://pypi.org/project/packaging/) | Apache-2.0 o BSD-2-Clause |
| [uvloop](https://pypi.org/project/uvloop/) | MIT o Apache-2.0 |
| [certifi](https://pypi.org/project/certifi/) | MPL-2.0 |
| [tqdm](https://pypi.org/project/tqdm/) | MPL-2.0 e MIT |
| [typing_extensions](https://pypi.org/project/typing-extensions/) | PSF-2.0 |

NumPy include anche piccole parti sotto 0BSD, MIT, Zlib e CC0-1.0.

## Programmi esterni

Questi girano come programmi separati, in processi propri; il codice di DomotiQ non li include e non li importa.

| Programma | Versione | Licenza | Uso |
|---|---|---|---|
| [Piper](https://github.com/OHF-Voice/piper1-gpl) (`piper1-gpl`, pacchetto `piper-tts`) | 1.8.0 | GPL-3.0 | sintesi vocale, nel suo ambiente, come server HTTP locale |
| [Flask](https://flask.palletsprojects.com) | non fissata | BSD-3-Clause | usato dal server HTTP di Piper, nell'ambiente di Piper |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) | commit 74a7c897 | MIT | fa girare il modello linguistico; compilato sulla scheda |

Piper è GPL-3.0. DomotiQ lo esegue come programma esterno e gli parla via HTTP: si tratta di aggregazione, non di un'opera derivata, quindi il codice di DomotiQ resta sotto licenza MIT.

## Modelli e voci

| Modello | Licenza | Uso |
|---|---|---|
| [vosk-model-small-it-0.22](https://alphacephei.com/vosk/models) | Apache-2.0 | riconoscimento vocale italiano |
| [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models) | Apache-2.0 | riconoscimento vocale inglese |
| [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF), GGUF, quantizzato Q4_K_M | Apache-2.0 | comprensione delle frasi libere (sceglie un intento) |
| [YOLOX-Nano](https://github.com/Megvii-BaseDetection/YOLOX), ONNX, release 0.1.1rc0 | Apache-2.0; addestrato sul dataset [COCO](https://cocodataset.org) | proposta della categoria di un nuovo personaggio a partire da una foto |
| Voce Piper [it_IT-serena-medium](https://huggingface.co/rhasspy/piper-voices), revisione ea046e84 | CC BY 4.0 (dataset serena-synthetic-it-27h) | voce italiana |
| Voce Piper [en_US-ljspeech-medium](https://huggingface.co/rhasspy/piper-voices) | pubblico dominio ([LJ Speech](https://keithito.com/LJ-Speech-Dataset/)) | voce inglese |

## Caratteri

| Carattere | Licenza | Uso |
|---|---|---|
| [Open Sans](https://github.com/googlefonts/opensans) | SIL Open Font License 1.1 | testo della webapp e del cartello |
| [Roboto Mono](https://github.com/googlefonts/robotomono) | SIL Open Font License 1.1 | numeri e codice |

I caratteri sono serviti dalla scheda come file woff2, con le loro licenze in `src/domotiq/web/static/fonts/`.

## Strumenti di sviluppo

Usati sul PC, non installati sulla scheda:

| Strumento | Licenza | Uso |
|---|---|---|
| [pytest](https://pytest.org) | MIT | test |
| [HTTPX](https://www.python-httpx.org) | BSD-3-Clause | test delle API web |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | pulizia dei metadati delle immagini |
| [uv](https://github.com/astral-sh/uv) | MIT o Apache-2.0 | ambiente Python sul PC |
| [FreeCAD](https://www.freecad.org) | LGPL-2.1+ | CAD del diorama |

## Valutati e non usati

| Componente | Motivo |
|---|---|
| Ultralytics YOLOv5, v8, 11 | AGPL-3.0 |
| Modelli di openWakeWord | CC BY-NC-SA: niente uso commerciale |
| Voci Piper derivate da "lessac" (per esempio it_IT-paola) | il dataset esclude l'uso commerciale |
| Gemma fino alla 3n, Llama | condizioni d'uso con restrizioni |
| LFM2 | diritti commerciali limitati sopra una soglia di fatturato |
| Qwen2.5-3B | licenza solo per la ricerca |
| Edge Impulse / FOMO | addestramento su un servizio cloud |
| Brick vocali di App Lab | disponibili solo su VENTUNO Q |

Avanti: [risoluzione dei problemi](11-risoluzione-problemi.md).
