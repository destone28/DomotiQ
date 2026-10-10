# 10. Attributions

DomotiQ stands on the work of many open projects. This chapter lists every third-party component the house uses, with its licence and a link, and the licences of the project itself.

## The project

> Created by Emilio Destratis ([destratis.it](https://destratis.it)) in collaboration with Arduino.

| Part | Licence |
|---|---|
| Source code: `src/`, `firmware/`, `scripts/`, `tests/` | MIT License, see [LICENSE](../../LICENSE) |
| Everything else: documentation and guides (`docs/`, the READMEs), images and diagrams, the 3D printing files in `hardware/stl/`, the house data, phrases and default rules in `data/` | Creative Commons Attribution 4.0 International ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)), see [LICENSE-DOCS.md](../../LICENSE-DOCS.md) |

Anyone who reuses, adapts or redistributes the project, also commercially, must give the attribution above, link to the licence and indicate if changes were made.

The figurines and the car are third-party models and are not in this repository; see the project page for links and for their licences.

## Board and system

| Component | Version | Licence | Use |
|---|---|---|---|
| [Debian](https://www.debian.org) image of the Arduino UNO Q | 20251210-442, then updated | various (Debian) | operating system |
| [arduino-app-cli](https://github.com/arduino/arduino-app-cli) | 0.7.0, then updated | GPL-3.0 (system tool, not included) | first setup, system updates, board name |
| [arduino-router](https://github.com/arduino/arduino-router) | from the system | MPL-2.0 | bridge between Linux and the microcontroller |
| [NetworkManager](https://networkmanager.dev), [dnsmasq](https://thekelleys.org.uk/dnsmasq/doc.html), [Avahi](https://avahi.org) | from the system | GPL-2.0+ / LGPL | hotspot, DNS, `.local` names |
| [ALSA](https://www.alsa-project.org) (`libasound2` from trixie-backports) | 1.2.16.1 | LGPL-2.1+ | audio |

## Microcontroller

| Component | Version | Licence | Use |
|---|---|---|---|
| [Arduino core for Zephyr](https://github.com/arduino/ArduinoCore-zephyr) (`arduino:zephyr`) | 1.0.0 | Apache-2.0 | base of the sketch |
| [Arduino_RouterBridge](https://github.com/arduino-libraries/Arduino_RouterBridge) | 0.4.3 | MPL-2.0 | calls and notifications to and from Linux |

## Python on the board

The main packages of the application:

| Package | Licence | Use |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | web server |
| [Starlette](https://github.com/Kludex/starlette) | BSD-3-Clause | web server |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | web server |
| [Uvicorn](https://uvicorn.dev) | BSD-3-Clause | HTTP server |
| [NumPy](https://numpy.org) | BSD-3-Clause | computation, sound synthesis |
| [OpenCV](https://opencv.org) ([opencv-python-headless](https://github.com/opencv/opencv-python)) | Apache-2.0 | computer vision |
| [msgpack](https://github.com/msgpack/msgpack-python) | Apache-2.0 | protocol of the router |
| [Vosk](https://alphacephei.com/vosk/) | Apache-2.0 | speech recognition |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT | object category from photos |

There is no SciPy: the Hungarian assignment used by the tracking is written in the project.

The complete list of packages installed on the board, with the exact versions, is in `requirements.txt`. Their licences:

| Package | Licence |
|---|---|
| [annotated-doc](https://pypi.org/project/annotated-doc/), [annotated-types](https://pypi.org/project/annotated-types/), [anyio](https://pypi.org/project/anyio/), [cffi](https://pypi.org/project/cffi/), [charset-normalizer](https://pypi.org/project/charset-normalizer/), [h11](https://pypi.org/project/h11/), [httptools](https://pypi.org/project/httptools/), [pydantic_core](https://pypi.org/project/pydantic-core/), [PyYAML](https://pypi.org/project/PyYAML/), [srt](https://pypi.org/project/srt/), [typing-inspection](https://pypi.org/project/typing-inspection/), [urllib3](https://pypi.org/project/urllib3/), [watchfiles](https://pypi.org/project/watchfiles/) | MIT |
| [click](https://pypi.org/project/click/), [idna](https://pypi.org/project/idna/), [protobuf](https://pypi.org/project/protobuf/), [pycparser](https://pypi.org/project/pycparser/), [python-dotenv](https://pypi.org/project/python-dotenv/), [websockets](https://pypi.org/project/websockets/) | BSD-3-Clause |
| [flatbuffers](https://pypi.org/project/flatbuffers/), [requests](https://pypi.org/project/requests/) | Apache-2.0 |
| [packaging](https://pypi.org/project/packaging/) | Apache-2.0 or BSD-2-Clause |
| [uvloop](https://pypi.org/project/uvloop/) | MIT or Apache-2.0 |
| [certifi](https://pypi.org/project/certifi/) | MPL-2.0 |
| [tqdm](https://pypi.org/project/tqdm/) | MPL-2.0 and MIT |
| [typing_extensions](https://pypi.org/project/typing-extensions/) | PSF-2.0 |

NumPy also bundles small parts under 0BSD, MIT, Zlib and CC0-1.0.

## External programs

These run as separate programs, in their own processes; the code of DomotiQ does not include or import them.

| Program | Version | Licence | Use |
|---|---|---|---|
| [Piper](https://github.com/OHF-Voice/piper1-gpl) (`piper1-gpl`, package `piper-tts`) | 1.8.0 | GPL-3.0 | speech synthesis, in its own environment, as a local HTTP server |
| [Flask](https://flask.palletsprojects.com) | not pinned | BSD-3-Clause | used by Piper's HTTP server, in Piper's environment |
| [SVOX Pico](https://android.googlesource.com/platform/external/svox/) (`pico2wave`, Debian package `libttspico-utils`) | 1.0+git20130326-14.1 | Apache-2.0 (the voice data: declared Apache-2.0, redistributable, without sources; that is why Debian keeps them in *non-free*) | the fast voice, as a separate program |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) | commit 74a7c897 | MIT | runs the language model; built on the board |

Piper is GPL-3.0. DomotiQ runs it as an external program and talks to it over HTTP, which is aggregation, not a derivative work, so the code of DomotiQ stays under the MIT License.

## Models and voices

| Model | Licence | Use |
|---|---|---|
| [vosk-model-small-it-0.22](https://alphacephei.com/vosk/models) | Apache-2.0 | Italian speech recognition |
| [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models) | Apache-2.0 | English speech recognition |
| [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF), GGUF, quantized Q4_K_M | Apache-2.0 | understanding free sentences (chooses an intent) |
| [YOLOX-Nano](https://github.com/Megvii-BaseDetection/YOLOX), ONNX, release 0.1.1rc0 | Apache-2.0; trained on the [COCO](https://cocodataset.org) dataset | proposing the category of a new character from a photo |
| Piper voice [it_IT-serena-medium](https://huggingface.co/rhasspy/piper-voices), revision ea046e84 | CC BY 4.0 (dataset serena-synthetic-it-27h) | Italian voice |
| Piper voice [en_US-ljspeech-medium](https://huggingface.co/rhasspy/piper-voices) | public domain ([LJ Speech](https://keithito.com/LJ-Speech-Dataset/)) | English voice |

## Fonts

| Font | Licence | Use |
|---|---|---|
| [Open Sans](https://github.com/googlefonts/opensans) | SIL Open Font License 1.1 | text of the web app |
| [Roboto Mono](https://github.com/googlefonts/robotomono) | SIL Open Font License 1.1 | numbers and code |

The fonts are served by the board as woff2 files, with their licences in `src/domotiq/web/static/fonts/`.

## Development tools

Used on the PC, not installed on the board:

| Tool | Licence | Use |
|---|---|---|
| [pytest](https://pytest.org) | MIT | tests |
| [HTTPX](https://www.python-httpx.org) | BSD-3-Clause | tests of the web API |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | cleaning image metadata |
| [uv](https://github.com/astral-sh/uv) | MIT or Apache-2.0 | Python environment on the PC |
| [FreeCAD](https://www.freecad.org) | LGPL-2.1+ | CAD of the diorama |

## Considered and not used

| Component | Reason |
|---|---|
| Ultralytics YOLOv5, v8, 11 | AGPL-3.0 |
| openWakeWord models | CC BY-NC-SA: no commercial use |
| Piper voices derived from "lessac" (for example it_IT-paola) | dataset excludes commercial use |
| Gemma up to 3n, Llama | terms of use with restrictions |
| LFM2 | commercial rights limited above a revenue threshold |
| Qwen2.5-3B | research-only licence |
| Edge Impulse / FOMO | training on a cloud service |
| App Lab voice bricks | available only on VENTUNO Q |

Next: [troubleshooting](11-troubleshooting.md).
