# DomotiQ guide

DomotiQ is a 1:20 scale smart house that runs entirely offline on a single **Arduino UNO Q 4GB**. A webcam on a pole looks down on the house and follows figurines, pets, a toy car and objects with computer vision. Rules react to what happens with lights, sounds and warnings, a voice interface answers questions in Italian and English, and any phone can open the house's own web app over the board's Wi-Fi hotspot.

This guide covers the whole project, from a factory-new board to a working house. The chapters follow the order in which you build a house.

## Chapters

1. [Prepare the UNO Q](01-prepare-uno-q.md): first password, SSH, network names, system update, access from a PC.
2. [Install the software](02-install.md): `install.sh`, the three services, the hotspot, updates.
3. [Print and assemble](03-print-and-assemble.md): the numbered STL files and how the parts go together.
4. [Wiring](04-wiring.md): the Qwiic chain through the Modulino Hub, power, relay and fan, audio, webcam.
5. [Testing and commissioning](05-testing.md): checking every part, camera calibration, first figurine, voice, phones.
6. [The web app](06-web-app.md): how to open it, every screen, who can do what, notifications and questions.
7. [Recognition and identities](07-recognition-and-identities.md): how the house sees, registering characters, privacy, datasets.
8. [Voice](08-voice.md): the buttons, languages, talkativeness, example phrases, the language model.
9. [Rules](09-rules.md): When / If / Then, every trigger, condition and action, the default rules, light layers.
10. [Attributions](10-attributions.md): licences of the project and of every third-party component.
11. [Troubleshooting](11-troubleshooting.md): symptom, cause and fix.

For everyday use there is a one-page [quick guide](quick-guide.md): switching on, preparing, buttons, phones and what to do when something goes wrong.

## At a glance

| | |
|---|---|
| Host name | `casa1` |
| User and password | `arduino`, `domotiq2026` (chosen in [chapter 1](01-prepare-uno-q.md)) |
| Wi-Fi hotspot | `DomotiQ-Casa1` (channel 1), password `domotica2026` |
| Web app | `http://10.42.1.1/` |
| Other names | `casa1.lan`, `casa1.local` |
| Project folder | `/home/arduino/domotiq` |

## Licence and credit

The source code is released under the MIT License; documentation, images, 3D printing files and the data in `data/` are released under CC BY 4.0. See [Attributions](10-attributions.md) for the details and for the licences of the components the house uses.

> Created by Emilio Destratis ([destratis.it](https://destratis.it)) in collaboration with Arduino.
