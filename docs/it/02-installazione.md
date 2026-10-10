# 2. Installare il software

DomotiQ gira sulla UNO Q come servizi systemd nativi, non come app di App Lab: sulla UNO Q App Lab non offre riconoscimento né sintesi vocale offline, e le sue app girano in Docker, scaricano le dipendenze al primo avvio e non si riavviano da sole. Un solo script, `scripts/install.sh`, installa tutto: pacchetti di sistema, ambienti Python, modelli, il server del modello linguistico, il firmware del microcontrollore, le impostazioni della casa, i servizi e l'hotspot.

## Prima di cominciare

- La scheda è preparata come nel [capitolo 1](01-preparare-uno-q.md): password, nome, Wi-Fi con internet, SSH, aggiornamento del sistema.
- La scheda ha internet. Serve una volta sola, per pacchetti e modelli; gli aggiornamenti successivi si possono copiare da un PC senza internet (vedi [Aggiornamenti](#aggiornamenti)).
- In `/home/arduino` ci sono circa 2,9 GB liberi (modelli circa 1,4 GB, ambienti Python circa 500 MB, compilatori e llama.cpp circa 600 MB, più un margine).
- Hai tempo: la sola compilazione di `llama-server` richiede una ventina di minuti.

## Scaricare il codice e lanciare l'installer

Entra come `arduino` (`ssh casa1`) e clona il repository in `/home/arduino/domotiq`, la cartella che i servizi si aspettano:

```bash
git clone https://github.com/destone28/DomotiQ ~/domotiq
cd ~/domotiq && bash scripts/install.sh --wifi domotica2026
```

In questa guida la password del Wi-Fi della casa è `domotica2026`; senza `--wifi` l'installer ne sceglie una a caso.

Se sulla scheda manca `git`, installalo prima con `sudo apt-get install -y git`.

Se la scheda non può scaricare il repository (per esempio perché non è pubblico), copialo dal PC che ne ha una copia. Sulla scheda serve `rsync` (`sudo apt-get install -y rsync`); poi, dalla cartella del repository sul PC:

```bash
bash scripts/release.sh casa1 --install --wifi domotica2026
```

Dopo `--install` si scrivono le opzioni dell'installer, le stesse della tabella qui sotto.

Lo script chiede la password di `sudo` (`domotiq2026`, quella del [capitolo 1](01-preparare-uno-q.md)) una sola volta, e solo se `sudo` la richiede, e la mantiene valida fino alla fine. Ogni passo salta quello che è già fatto, quindi rilanciarlo non fa danni, ed è anche il modo per aggiornare una casa già installata.

### Opzioni

| Opzione | Significato |
|---|---|
| `--house N` | Numero della casa, da 1 a 254; senza, la casa è la 1. Imposta il nome (`casaN`), la rete Wi-Fi (`DomotiQ-CasaN`), il canale (1, 11 o 6) e l'indirizzo (`10.42.N.1`). Le esecuzioni successive lo leggono dalle impostazioni salvate. |
| `--wifi PASSWORD` | La password del Wi-Fi della casa, da 8 a 63 caratteri. Senza, l'installer la sceglie a caso la prima volta e poi la tiene. |
| `--hotspot MODE` | `now`, `boot` o `no`. Predefinito `boot`: l'hotspot viene configurato e parte al prossimo avvio. Vedi [L'hotspot](#lhotspot). |
| `--no-llm` | Salta llama.cpp e il modello linguistico. La casa capisce allora solo le frasi del suo analizzatore interno. |
| `--skip-firmware` | Non ricompila e non ricarica il firmware del microcontrollore. |

## Cosa fa ogni passo

Lo script stampa dei passi numerati. Quando un'opzione fa saltare un passo, i numeri successivi scalano.

1. **Controlli.** Deve girare come utente `arduino`; avvisa se il progetto non è in `/home/arduino/domotiq` o se il sistema non è Debian 13; controlla lo spazio libero, la connessione a internet e di quale casa si tratta.
2. **Pacchetti di sistema.** Installa la libreria ALSA da `trixie-backports` (la correzione descritta nel [capitolo 1](01-preparare-uno-q.md#se-laggiornamento-si-ferma-su-una-dipendenza-alsa)), poi `python3-venv`, `python3-dev`, `build-essential`, `cmake`, `git`, `curl`, `rsync`, `unzip`, `alsa-utils`, `v4l-utils`, `iw`, `sqlite3`, `avahi-daemon`, `dnsmasq-base` e `libgomp1`, e attiva `avahi-daemon` e `ssh` a ogni avvio. L'immagine di fabbrica non ha né un compilatore né cmake, che servono a llama.cpp.
3. **Ambiente Python dell'applicazione.** `venv/` con le versioni esatte elencate in `requirements.txt`. Un ambiente rotto o copiato da un'altra parte viene rifatto.
4. **Sintesi vocale.** Un ambiente separato, `piper-venv/`, con `piper-tts` 1.8.0 e Flask. Piper è GPL-3.0 e gira come programma a sé: l'applicazione gli parla via HTTP sull'interfaccia di loopback e non lo importa mai.
5. **Modelli.** Vengono scaricati in `models/` e verificati con le somme SHA-256 di `scripts/models.sha256`: le voci Piper `it_IT-serena-medium` (a una revisione fissa) e `en_US-ljspeech-medium`, i modelli Vosk `vosk-model-small-it-0.22` e `vosk-model-small-en-us-0.15`, YOLOX-Nano (`yolox_nano.onnx`) e, se non c'è `--no-llm`, `qwen2.5-0.5b-instruct-q4_k_m.gguf` (i comandi) e `Qwen_Qwen3.5-0.8B-Q4_0.gguf` (le risposte libere alle domande sul mondo, servizio `domotiq-chat`). Un file già presente con il checksum giusto non viene riscaricato.
6. **llama.cpp.** Scarica llama.cpp al commit provato sulla UNO Q (`74a7c897`), applica le istruzioni scritte per il suo processore (`scripts/llama/arm-nodot.patch`, vedi [Accelerare il modello](../accelerazione-modello.md)) e compila `llama-server` (una ventina di minuti). Il passo viene saltato quando lo stesso commit è già compilato con la stessa patch, o con `--no-llm`.
7. **Firmware del microcontrollore.** Installa il core `arduino:zephyr` 1.0.0 e la libreria `Arduino_RouterBridge` 0.4.3, compila `firmware/domotiq_mcu` con la modalità di avvio "Immediate" (`wait_linux_boot=no`) e lo carica con il `remoteocd` locale, che non chiede password. Viene ricaricato solo quando cambiano lo sketch, il core, la libreria o le opzioni della scheda. Alla fine `arduino-app-cli properties set default none` fa sì che nessuna app di App Lab sostituisca il firmware all'avvio. Per fare lo stesso a mano, vedi `firmware/domotiq_mcu/README.md`.
8. **Impostazioni della casa.** Imposta il nome host `casaN` e il fuso orario Europe/Rome; crea la password del Wi-Fi (se non esiste ancora); scrive numero della casa, nomi e rete in `var/config/settings.json`.
9. **Servizi.** Installa `domotiq`, `domotiq-tts` e `domotiq-llm` in `/etc/systemd/system`, una regola `sudoers` e un limite per journald (200 MB, 7 giorni di log). Disattiva i timer automatici di `apt` e blocca `alsa-ucm-conf`, `libasound2t64` e il kernel in uso: mentre la casa è in uso niente deve aggiornare il sistema.
10. **Hotspot.** Crea o aggiorna il profilo dell'hotspot, poi applica `--hotspot` (`now`, `boot` o `no`).
11. **Avvio.** Riavvia i servizi e stampa un riepilogo.

Il riepilogo è simile a questo:

```
DomotiQ casa1 is installed.
  Wi-Fi:    DomotiQ-Casa1   password: domotica2026
  Address:  http://10.42.1.1/   (on the hotspot)   http://casa1.local/
```

Una password scelta dall'installer è fatta di tre gruppi di quattro caratteri, presi da un alfabeto senza i caratteri che si confondono facilmente: `i`, `l`, `o`, `0` e `1`. Annotala: serve a ogni telefono che entra nella rete della casa. Si ritrova anche nella webapp, in **Altro → Impostazioni → Wi-Fi della casa**. Non scriverla nel repository.

## Dove si trovano le cose

Tutto sta dentro `/home/arduino/domotiq`:

| Percorso | Contenuto |
|---|---|
| `venv/` | ambiente Python dell'applicazione |
| `piper-venv/` | ambiente separato di Piper |
| `models/` | voci Piper, modelli Vosk, YOLOX-Nano, Qwen2.5-0.5B, Qwen3.5-0.8B |
| `llama.cpp/` | sorgenti di llama.cpp e il `llama-server` compilato |
| `var/config/` | `settings.json`, `rules.json`, `identities.json` |
| `var/calibration/` | calibrazione della webcam, riferimento della casa vuota, impostazioni della webcam bloccate |
| `var/photos/` | foto dei personaggi |
| `var/domotiq.db` | SQLite: eventi (7 giorni), posizioni (24 ore), registro delle modifiche, cestino |
| `var/dataset/`, `var/recordings/` | catture e sequenze registrate dalla pagina di calibrazione |
| `var/firmware/` | l'ultima compilazione del firmware |

`var/` è la memoria della casa. Appartiene a quella scheda ed è escluso dal repository.

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

La casa ha la sua rete Wi-Fi, servita dalla scheda con NetworkManager in modalità condivisa:

| | |
|---|---|
| SSID | `DomotiQ-Casa1` |
| Sicurezza | WPA2, password `domotica2026` (opzione `--wifi`) |
| Banda e canale | 2,4 GHz, canale 1 |
| Indirizzo della casa | `10.42.1.1` |
| Nomi | `casa1.lan`, `casa1.local` |

Con `--house N` diventano `DomotiQ-CasaN`, `10.42.N.1` e `casaN`, e il canale passa fra 1, 11 e 6.

Il DNS dell'hotspot risponde per `casaN.lan` (e per `domotiq.lan`) e fa fallire subito i nomi di iCloud Private Relay, così gli iPhone non restano ad aspettarli. Non c'è un captive portal, ed è una scelta voluta: la finestra del captive portal dei telefoni non permette di usare la fotocamera, e su iPhone si chiude quando si cambia app. I telefoni entrano nella rete con la password del Wi-Fi e aprono l'indirizzo numerico, che funziona sempre.

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

**Da un PC, senza internet sulla scheda** (per esempio attraverso l'hotspot). Dalla cartella del repository sul PC:

```bash
bash scripts/release.sh casa1              # copy code, web app and data, restart domotiq
bash scripts/release.sh casa1 --install    # then run install.sh on the board (needs internet on the board)
```

`release.sh` copia la cartella di lavoro del PC in `~/domotiq` sulla scheda con `rsync` via SSH (usando l'alias `casa1` creato da `add-pc.sh`), poi riavvia `domotiq`. Lascia fuori quello che git ignora e quello che appartiene alla scheda: `.git`, `venv`, `piper-venv`, `models`, `var` e `llama.cpp`. Per questo la scheda non ha bisogno di git. La copia rispecchia il PC: un file di codice modificato solo sulla scheda viene sovrascritto o cancellato. Fa eccezione `models/voice-cache/`, le frasi fisse della voce preparate in anticipo: se c'è sul PC, viene copiata anche quella.

**Le frasi della voce preparate in anticipo.** Le frasi fisse (oggi 239) si sintetizzano una volta con `scripts/voice_cache.py` e si copiano sulla casa, così la prima accensione non aspetta Piper:

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

## Una casa uguale a un'altra

Per avere una casa che si comporta come una che hai già, dopo l'installazione:

1. Dalla webapp della casa che hai, **Altro → Impostazioni → Scarica il backup**; dalla webapp della casa nuova, **Ripristina da un backup** con quel file. Porta regole, personaggi con colori e pose, e impostazioni; mai la rete, il nome della casa o le impostazioni della webcam. Ripristinalo prima di registrare personaggi sulla casa nuova, perché li sostituisce.
2. Copia la rete delle statuine (`models/vision/figures.onnx` e `figures.json`, [capitolo 7](07-riconoscimento-e-identita.md)) e le risposte imparate (`var/config/knowledge.json`), poi riavvia la casa: `sudo systemctl restart domotiq`.
3. La calibrazione della webcam non si copia: angoli, casa vuota e foto con le luci si fanno sulla casa nuova ([capitolo 5](05-collaudo.md)), perché dipendono da dove sta la sua webcam e da com'è arredata.
4. Se la casa nuova ha statuine sue, anche dello stesso modello, i colori che il backup porta sono quelli delle statuine dell'altra casa, sotto la sua luce: la casa nuova non riconoscerebbe le sue, o le scambierebbe. Nella scheda di ogni personaggio (**Personaggi**) tocca **Impara di nuovo l'aspetto**, poi di' alla casa chi è ogni statuina, toccandola sulla piantina o rispondendo alle sue domande.
5. La rete delle statuine conosce i mobili della casa su cui è stata addestrata. Su una casa arredata in un altro modo (un divano arancione, altre griglie) all'inizio vede statuine in qualche mobile: accendi la raccolta continua, correggi il registro della visione e addestrala di nuovo con le immagini della casa nuova e le foto della sua casa vuota ([capitolo 7](07-riconoscimento-e-identita.md#la-rete-che-conosce-le-statuine)).

## Prima che la casa lasci il laboratorio

1. Fai partire l'hotspot a ogni avvio: `bash scripts/hotspot.sh boot`, poi riavvia.
2. Togli dalla scheda la rete Wi-Fi del laboratorio, con la sua password, e la cronologia dei comandi, che può contenerla:

   ```bash
   sudo nmcli connection delete "YOUR-NETWORK"
   rm -f ~/.bash_history && history -c
   ```

3. **Se la casa resta a te**, da ogni PC che deve mantenere l'accesso lancia una volta `bash scripts/add-pc.sh casaN` (copia una chiave sulla scheda), poi sulla scheda lascia entrare in SSH solo con la chiave:

   ```bash
   cd ~/domotiq && bash scripts/lockdown.sh
   ```

   Elenca le chiavi che potranno ancora entrare e si rifiuta di proseguire se non ce n'è nessuna; `bash scripts/lockdown.sh --undo` riammette le password. `sudo` continua a chiedere la password dell'utente `arduino`, tranne per i pochi comandi che servono alla webapp (riavvio del servizio, riavvio, spegnimento, hotspot). Con la password `domotiq2026` del capitolo 1 questo passo è indispensabile: quella password è scritta in questa guida.
4. **Se consegni la casa a qualcun altro**, non lasciare sulla scheda le chiavi dei tuoi PC: `rm -f ~/.ssh/authorized_keys`. SSH accetta allora solo la password di `arduino`: chi riceve la casa aggiunge i suoi PC con `add-pc.sh` e poi fa il passo 3.
5. Se durante la preparazione hai dato all'utente `arduino` un `sudo` senza password, togli quella regola: `sudo` deve chiedere la password.
6. Annota la password del Wi-Fi per chi userà la casa, mai nel repository.

La password si può cambiare in qualsiasi momento da **Altro → Impostazioni** nella webapp, oppure sulla scheda:

```bash
cd ~/domotiq
PYTHONPATH=src venv/bin/python -m domotiq.admin wifi "una-password-nuova"
```

Il comando riavvia la casa perché legga il valore nuovo, e riavvia anche l'hotspot, se è acceso.

Avanti: [stampa e montaggio](03-stampa-e-montaggio.md).
