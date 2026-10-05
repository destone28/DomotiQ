# 2. Installare il software

DomotiQ gira sulla UNO Q come servizi systemd nativi, non come app di App Lab: sulla UNO Q App Lab non offre riconoscimento né sintesi vocale offline, e le sue app girano in Docker, scaricano le dipendenze al primo avvio e non si riavviano da sole. Un solo script, `scripts/install.sh`, installa tutto: pacchetti di sistema, ambienti Python, modelli, il server del modello linguistico, il firmware del microcontrollore, le impostazioni della casa, i servizi e l'hotspot.

## Prima di cominciare

- La scheda è preparata come nel [capitolo 1](01-preparare-uno-q.md): password, nome, Wi-Fi con internet, SSH, aggiornamento del sistema.
- La scheda ha internet. Serve una volta sola, per pacchetti e modelli; gli aggiornamenti successivi si possono copiare da un PC senza internet (vedi [Aggiornamenti](#aggiornamenti)).
- In `/home/arduino` ci sono circa 2,3 GB liberi (modelli circa 800 MB, ambienti Python circa 500 MB, compilatori e llama.cpp circa 600 MB, più un margine).
- Hai tempo: la sola compilazione di `llama-server` richiede una ventina di minuti.

## Scaricare il codice e lanciare l'installer

Entra come `arduino` (`ssh casa1`) e clona il repository in `/home/arduino/domotiq`, la cartella che i servizi si aspettano:

```bash
git clone https://github.com/destone28/DomotiQ ~/domotiq
cd ~/domotiq && bash scripts/install.sh --house 1
```

Se sulla scheda manca `git`, installalo prima con `sudo apt-get install -y git`.

Lo script chiede la password di `sudo` una sola volta (e solo se `sudo` la richiede) e la mantiene valida fino alla fine. Ogni passo salta quello che è già fatto, quindi rilanciarlo non fa danni, ed è anche il modo per aggiornare una casa già installata.

### Opzioni

| Opzione | Significato |
|---|---|
| `--house N` | Numero della casa, `1` o `2`. Imposta il nome (`casaN`), la rete Wi-Fi (`DomotiQ-CasaN`), il canale e l'indirizzo (`10.42.N.1`). Serve la prima volta; le esecuzioni successive lo leggono dalle impostazioni salvate. |
| `--hotspot MODE` | `now`, `boot` o `no`. Predefinito `boot`: l'hotspot viene configurato e parte al prossimo avvio. Vedi [L'hotspot](#lhotspot). |
| `--no-llm` | Salta llama.cpp e il modello linguistico. La casa capisce allora solo le frasi del suo analizzatore interno. |
| `--skip-firmware` | Non ricompila e non ricarica il firmware del microcontrollore. |

## Cosa fa ogni passo

Lo script stampa dei passi numerati. Quando un'opzione fa saltare un passo, i numeri successivi scalano.

1. **Controlli.** Deve girare come utente `arduino`; avvisa se il progetto non è in `/home/arduino/domotiq` o se il sistema non è Debian 13; controlla lo spazio libero, la connessione a internet e di quale casa si tratta.
2. **Pacchetti di sistema.** Installa la libreria ALSA da `trixie-backports` (la correzione descritta nel [capitolo 1](01-preparare-uno-q.md#se-laggiornamento-si-ferma-su-una-dipendenza-alsa)), poi `python3-venv`, `python3-dev`, `build-essential`, `cmake`, `git`, `curl`, `rsync`, `unzip`, `alsa-utils`, `v4l-utils`, `iw`, `sqlite3`, `avahi-daemon`, `dnsmasq-base` e `libgomp1`, e attiva `avahi-daemon`. L'immagine di fabbrica non ha né un compilatore né cmake, che servono a llama.cpp.
3. **Ambiente Python dell'applicazione.** `venv/` con le versioni esatte elencate in `requirements.txt`. Un ambiente rotto o copiato da un'altra parte viene rifatto.
4. **Sintesi vocale.** Un ambiente separato, `piper-venv/`, con `piper-tts` 1.8.0 e Flask. Piper è GPL-3.0 e gira come programma a sé: l'applicazione gli parla via HTTP sull'interfaccia di loopback e non lo importa mai.
5. **Modelli.** Vengono scaricati in `models/` e verificati con le somme SHA-256 di `scripts/models.sha256`: le voci Piper `it_IT-serena-medium` (a una revisione fissa) e `en_US-ljspeech-medium`, i modelli Vosk `vosk-model-small-it-0.22` e `vosk-model-small-en-us-0.15`, YOLOX-Nano (`yolox_nano.onnx`) e, se non c'è `--no-llm`, `qwen2.5-0.5b-instruct-q4_k_m.gguf`. Un file già presente con il checksum giusto non viene riscaricato.
6. **llama.cpp.** Scarica llama.cpp al commit provato sulla UNO Q (`74a7c897`), applica le istruzioni scritte per il suo processore (`scripts/llama/arm-nodot.patch`, vedi [Accelerare il modello](../accelerazione-modello.md)) e compila `llama-server` (una ventina di minuti). Il passo viene saltato quando lo stesso commit è già compilato con la stessa patch, o con `--no-llm`.
7. **Firmware del microcontrollore.** Installa il core `arduino:zephyr` 1.0.0 e la libreria `Arduino_RouterBridge` 0.4.3, compila `firmware/domotiq_mcu` con la modalità di avvio "Immediate" (`wait_linux_boot=no`) e lo carica con il `remoteocd` locale, che non chiede password. Viene ricaricato solo quando cambiano lo sketch, il core, la libreria o le opzioni della scheda. Alla fine `arduino-app-cli properties set default none` fa sì che nessuna app di App Lab sostituisca il firmware all'avvio. Per fare lo stesso a mano, vedi `firmware/domotiq_mcu/README.md`.
8. **Impostazioni della casa.** Imposta il nome host `casaN` e il fuso orario Europe/Rome; crea la password del Wi-Fi (se non esiste ancora); scrive numero della casa, nomi e rete in `var/config/settings.json`.
9. **Servizi.** Installa `domotiq`, `domotiq-tts` e `domotiq-llm` in `/etc/systemd/system`, una regola `sudoers` e un limite per journald (200 MB, 7 giorni di log). Disattiva i timer automatici di `apt` e blocca `alsa-ucm-conf`, `libasound2t64` e il kernel in uso: in fiera niente deve aggiornare il sistema.
10. **Hotspot.** Crea o aggiorna il profilo dell'hotspot, poi applica `--hotspot` (`now`, `boot` o `no`).
11. **Avvio.** Riavvia i servizi e stampa un riepilogo.

Il riepilogo è simile a questo (la password viene scelta a caso per ogni casa):

```
DomotiQ casa1 is installed.
  Wi-Fi:    DomotiQ-Casa1   password: abcd-efgh-jkmn
  Address:  http://10.42.1.1/   (on the hotspot)   http://casa1.local/
  Sign to print: http://10.42.1.1/sign
```

La password del Wi-Fi è fatta di tre gruppi di quattro caratteri, presi da un alfabeto senza i caratteri che si confondono facilmente: `i`, `l`, `o`, `0` e `1`. Scrivi la password sulla copia stampata della [guida rapida per lo staff dello stand](guida-rapida-staff.md).

## Dove si trovano le cose

Tutto sta dentro `/home/arduino/domotiq`:

| Percorso | Contenuto |
|---|---|
| `venv/` | ambiente Python dell'applicazione |
| `piper-venv/` | ambiente separato di Piper |
| `models/` | voci Piper, modelli Vosk, YOLOX-Nano, Qwen2.5-0.5B |
| `llama.cpp/` | sorgenti di llama.cpp e il `llama-server` compilato |
| `var/config/` | `settings.json`, `rules.json`, `identities.json` |
| `var/calibration/` | calibrazione della webcam, riferimento della casa vuota, impostazioni della webcam bloccate |
| `var/photos/` | foto dei personaggi |
| `var/domotiq.db` | SQLite: eventi (7 giorni), posizioni (24 ore), registro delle modifiche, cestino |
| `var/dataset/`, `var/recordings/` | catture e sequenze registrate dalla pagina di calibrazione |
| `var/firmware/` | l'ultima compilazione del firmware |

`var/` è la memoria della casa. Non si copia mai da una casa all'altra ed è escluso dal repository.

## I tre servizi

| Servizio | Cosa fa girare |
|---|---|
| `domotiq` | L'applicazione (`python -m domotiq`): webapp sulla porta 80, regole, voce, audio, collegamento con il microcontrollore, con la visione come processo figlio. Si riavvia da solo. Può occupare la porta 80 e impostare l'orologio, nient'altro. |
| `domotiq-tts` | Il server HTTP di Piper su `127.0.0.1:5010`, con le voci in `models/piper`. |
| `domotiq-llm` | `llama-server` con Qwen2.5-0.5B-Instruct su `127.0.0.1:8081`, sempre caricato perché le domande libere ricevano una risposta rapida, con una priorità di CPU più bassa di visione e voce. Le istruzioni lette si salvano in `/var/lib/domotiq-llm` e agli avvii successivi tornano in pochi secondi invece di circa 10 minuti ([capitolo 8](08-voce.md)). Con `--no-llm` non viene attivato. |

`domotiq` parte dopo `arduino-router` (il servizio di sistema che collega Linux e il microcontrollore) e dopo `domotiq-tts`. Tutti e tre si riavviano automaticamente se si fermano, e tutti e tre partono all'avvio: dopo un riavvio la casa riparte da sola.

Comandi utili:

```bash
systemctl status domotiq domotiq-tts domotiq-llm --no-pager
journalctl -u domotiq -f                 # follow the application log
sudo systemctl restart domotiq           # restart the application
```

Anche le impostazioni della webapp possono riavviare l'applicazione, riavviare o spegnere la scheda (vedi il [capitolo 6](06-webapp.md#impostazioni)).

## L'hotspot

In fiera ogni casa ha la sua rete Wi-Fi, servita dalla scheda con NetworkManager in modalità condivisa:

| | Casa 1 | Casa 2 |
|---|---|---|
| SSID | `DomotiQ-Casa1` | `DomotiQ-Casa2` |
| Sicurezza | WPA2, password casuale scelta dall'installer | uguale |
| Banda e canale | 2,4 GHz, canale 1 | 2,4 GHz, canale 11 |
| Indirizzo della casa | `10.42.1.1` | `10.42.2.1` |
| Nomi | `casa1.lan`, `casa1.local` | `casa2.lan`, `casa2.local` |

Il DNS dell'hotspot risponde per `casaN.lan` (e per `domotiq.lan`) e fa fallire subito i nomi di iCloud Private Relay, così gli iPhone non restano ad aspettarli. Non c'è un captive portal, ed è una scelta voluta: la finestra del captive portal dei telefoni non permette di usare la fotocamera, e su iPhone si chiude quando si cambia app. I telefoni entrano nella rete inquadrando il QR del cartello e aprono l'indirizzo numerico, che funziona sempre.

La scheda sta o sul Wi-Fi del laboratorio o sul suo hotspot. Passare all'hotspot fa cadere la connessione al laboratorio, e con lei la tua sessione SSH.

L'opzione dell'installer sceglie il punto di partenza:

- `--hotspot boot` (predefinito): l'hotspot parte da solo a ogni avvio. Gli altri profili Wi-Fi smettono di connettersi automaticamente, così all'avvio non gli fanno concorrenza.
- `--hotspot now`: passa subito all'hotspot.
- `--hotspot no`: lo configura ma lascia la scheda sul Wi-Fi del laboratorio.

In seguito puoi passare dall'uno all'altro con `scripts/hotspot.sh`:

```bash
bash scripts/hotspot.sh on        # switch to the hotspot now (Wi-Fi client connections drop)
bash scripts/hotspot.sh off       # back to the Wi-Fi of the lab
bash scripts/hotspot.sh boot      # the hotspot starts by itself at every boot
bash scripts/hotspot.sh status    # state of wlan0 and the active connections
```

`off` permette anche agli altri profili Wi-Fi di tornare a connettersi automaticamente. Con la scheda sul suo hotspot, raggiungila da un PC collegato a `DomotiQ-CasaN` con `ssh arduino@10.42.N.1`, oppure aggiungi un alias con `bash scripts/add-pc.sh casaN 10.42.N.1`.

## Aggiornamenti

Ci sono due modi per aggiornare una casa già installata.

**Sulla scheda, con internet.** Scarica il codice nuovo e rilancia l'installer; rifà solo quello che è cambiato e si ricorda il numero della casa:

```bash
cd ~/domotiq && git pull && bash scripts/install.sh
```

**Da un PC, senza internet sulla scheda** (per esempio attraverso l'hotspot, in fiera). Dalla cartella del repository sul PC:

```bash
bash scripts/release.sh casa1              # copy code, web app and data, restart domotiq
bash scripts/release.sh casa1 --install    # then run install.sh on the board (needs internet on the board)
```

`release.sh` copia la cartella di lavoro del PC in `~/domotiq` sulla scheda con `rsync` via SSH (usando l'alias `casa1` creato da `add-pc.sh`), poi riavvia `domotiq`. Lascia fuori quello che git ignora e quello che appartiene alla scheda: `.git`, `venv`, `piper-venv`, `models`, `var` e `llama.cpp`. Per questo la scheda non ha bisogno di git. La copia rispecchia il PC: un file di codice modificato solo sulla scheda viene sovrascritto o cancellato. Fa eccezione `models/voice-cache/`, le frasi fisse della voce preparate in anticipo: se c'è sul PC, viene copiata anche quella.

**Le frasi della voce preparate in anticipo.** Le frasi fisse (oggi 239) si sintetizzano una volta con `scripts/voice_cache.py` e si danno a ogni casa, così la prima accensione non aspetta Piper:

```bash
venv/bin/python scripts/voice_cache.py                   # sulla scheda, con il suo Piper (circa 13 minuti)
python scripts/voice_cache.py --url http://127.0.0.1:5010/synthesize   # su un PC (ambiente Python del repository)
```

Lo script scrive in `models/voice-cache/` solo le frasi che mancano e con `--list` le elenca soltanto. Sul PC basta avviare il server di Piper come fa il servizio `domotiq-tts` (stessa versione e stesse voci di `install.sh`).

Senza `--install`, una modifica al firmware viene copiata ma non caricata sul microcontrollore, e i nuovi pacchetti Python, i modelli e i servizi di `scripts/systemd` (per esempio `domotiq-llm.service`, che ora tiene quattro slot, `-np 4`, e li salva in `/var/lib/domotiq-llm`, o le priorità `CPUWeight` dei tre servizi) non vengono installati: quando cambiano queste cose, usa `--install` (oppure `install.sh` sulla scheda). Per un servizio soltanto, anche senza internet, basta questo sulla scheda (chiede la password di `arduino`):

```bash
cd ~/domotiq && sudo install -m644 scripts/systemd/domotiq-llm.service /etc/systemd/system/ \
  && sudo systemctl daemon-reload && sudo systemctl restart domotiq-llm
```

## Installare la seconda casa

La seconda casa si installa esattamente come la prima, con il suo numero:

```bash
cd ~/domotiq && bash scripts/install.sh --house 2
```

La casa 2 riceve il nome host `casa2`, la rete `DomotiQ-Casa2` sul canale 11 e l'indirizzo `10.42.2.1`, così le due case possono stare una accanto all'altra.

Le due case sono indipendenti. La calibrazione della webcam appartiene a ciascuna casa e non si copia mai (un backup nemmeno la contiene), e i personaggi si registrano casa per casa. Regole e impostazioni si possono copiare con un backup preso dalle impostazioni della casa 1 (vedi il [capitolo 6](06-webapp.md#impostazioni)); un backup non porta mai con sé la rete, il nome della casa o le impostazioni della webcam. Un ripristino dalla webapp sostituisce insieme regole, personaggi e impostazioni, quindi ripristina il backup sulla casa 2 prima di registrarne i personaggi.

## Prima che la casa lasci il laboratorio

1. Da ogni PC che deve mantenere l'accesso, lancia una volta `bash scripts/add-pc.sh casaN` (copia una chiave sulla scheda).
2. Sulla scheda, lascia entrare in SSH solo con la chiave:

   ```bash
   cd ~/domotiq && bash scripts/lockdown.sh
   ```

   Elenca le chiavi che potranno ancora entrare e si rifiuta di proseguire se non ce n'è nessuna; `bash scripts/lockdown.sh --undo` riammette le password. `sudo` continua a chiedere la password dell'utente `arduino`, tranne per i pochi comandi che servono alla webapp (riavvio del servizio, riavvio, spegnimento, hotspot).
3. Fai partire l'hotspot a ogni avvio (`bash scripts/hotspot.sh boot`, poi riavvia) e stampa il cartello da `/sign`.
4. Scrivi la password del Wi-Fi sulla copia della [guida rapida](guida-rapida-staff.md) che resta allo stand, mai nel repository.

La password si può cambiare in qualsiasi momento da **Altro → Impostazioni** nella webapp, oppure sulla scheda:

```bash
cd ~/domotiq
PYTHONPATH=src venv/bin/python -m domotiq.admin wifi "una-password-nuova"
```

Il comando riavvia la casa perché legga il valore nuovo, e riavvia anche l'hotspot, se è acceso.

Avanti: [stampa e montaggio](03-stampa-e-montaggio.md).
