# Diario di sviluppo

Note tecniche in ordine cronologico: cosa è stato fatto, perché, quali problemi sono emersi e come sono stati risolti. Le decisioni di progetto sono raccolte a parte in [decisioni.md](decisioni.md); strumenti, versioni e licenze in [strumenti-e-licenze.md](strumenti-e-licenze.md).

---

## 28 settembre 2026 — Analisi e verifiche

**Punto di partenza.** Il diorama v3 è definito nel CAD (`build_v3.py`, 90 pezzi numerati, report di montaggio). Il repository contiene solo la licenza. Scadenza: 7 ottobre, due case.

**Verifiche sulla piattaforma**, prima di scegliere l'architettura:

- Il connettore Qwiic della UNO Q è cablato sull'I2C4 dello STM32U585: i Modulino li vede solo il microcontrollore. Linux ci parla attraverso `arduino-router` (MessagePack-RPC su `/run/arduino-router.sock`).
- Un processo Linux che non è un'app di App Lab può ricevere le notifiche della MCU registrando il nome sul router con `$/register`.
- Il collegamento seriale fra i due lati va a 115200 baud, con messaggi di al massimo 256 byte e circa 7 ms per chiamata. Troppo poco per mandare animazioni di luce da Linux: gli effetti devono girare sulla MCU.
- Su UNO Q le brick di App Lab non offrono riconoscimento né sintesi vocale offline (esistono solo per VENTUNO Q); il Python delle app gira in Docker e installa le dipendenze da internet al primo avvio. Si usano quindi servizi systemd nativi.
- La libreria Arduino_Modulino 0.9.1 (17/9/2026) ha ancora comportamenti che su UNO Q nascondono i guasti: `begin()` con indirizzo esplicito non tocca il bus, `write()` risponde sempre `true`, il driver del VL53L4CD ritenta all'infinito. Le transazioni I2C si scrivono a mano nello sketch.
- Indirizzi dai sorgenti e dai datasheet: Hub TCA9548A 0x70, Latch Relay 0x02, Buttons 0x3E, Thermo 0x44, Distance 0x29, Pixels 0x36 (valori a 7 bit).
- Un Pixels a bianco pieno assorbe fino a 264 mA dal 3,3 V del Qwiic: cinque moduli superano il limite del connettore. Serve un limite di corrente nel firmware.
- La C270 ha fuoco fisso. Il CAD usa i 55° in diagonale del costruttore sul 16:9; una calibrazione pubblicata indica che il 720p è un ritaglio del sensore 4:3. Da misurare sulla camera vera: in 4:3 la base intera ci sta con margine.
- Il Wi-Fi (WCN3980) funziona da access point con NetworkManager, quasi certamente solo a 2,4 GHz.
- Su un telefono Android che non accetta "resta connesso", il traffico verso l'indirizzo locale passa sui dati mobili e non arriva. La finestra di accesso dei captive portal non permette la fotocamera: niente captive portal, si entra da QR.
- Senza HTTPS non ci sono service worker né notifiche di sistema, ma `<input type="file" capture>` apre la fotocamera del telefono: basta per fotografare i personaggi.

**Riconoscimento.** Una rete di rilevamento addestrata vedrebbe la base di un personaggio (25 mm) come una decina di pixel e richiederebbe centinaia di immagini etichettate. Il metodo scelto è classico: differenza dalla casa vuota, colore, tracciamento, con la correzione della parallasse per i personaggi alti. Nessun addestramento: un personaggio nuovo si registra in pochi secondi.

---

## 29 settembre 2026 — Risposte, specifica, prima scheda

**Risposte del secondo giro.** Un solo Modulino Buttons (tasti parla, citofono, lingua), licenza MIT per il software, domande libere con un modello linguistico piccolo, registrazione dei personaggi da webapp, citofono e voce, regole modificabili da chiunque con registro delle modifiche. La specifica è in [specifica.md](specifica.md).

**Preparazione di casa1.**
- Immagine di fabbrica del 10 dicembre 2025 (Debian 13, kernel 6.16, arduino-app-cli 0.7.0); l'utente `arduino` nasce senza password: la si imposta con lo script di prima configurazione dell'immagine (`/usr/local/bin/arduino-passwd`).
- Nome `casa1`, fuso orario Europe/Rome, rete Wi-Fi di sviluppo.
- **SSH non partiva**: `sshd: no hostkeys available`. Sull'immagine nuova le chiavi dell'host le genera App Lab durante la prima configurazione; senza App Lab vanno create con `ssh-keygen -A`.
- **avahi-daemon è spento di fabbrica** (lo accende la modalità di rete di App Lab): senza, `casa1.local` non si risolve.
- Accesso dal PC con una chiave dedicata (`~/.ssh/id_ed25519_domotiq`, alias `casa1` in `~/.ssh/config`).
- **`arduino-app-cli system update` va lanciato come utente `arduino`**, non con `sudo`: rifiuta di girare come root e chiama `sudo apt-get` da sé. Lanciato dentro una sessione `adb shell`, si interrompe se la sessione si chiude: meglio `systemd-run --uid=arduino`.
- **L'aggiornamento si fermava** con "alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)". L'immagine preferisce da trixie-backports (priorità 900) i profili audio, il kernel, i firmware e mesa, ma non la libreria ALSA. La nuova versione dei profili richiede la libreria di backports. Rimedio: installare da backports anche `libasound2t64`, `libasound2-data`, `libatopology2t64`, poi ripetere l'aggiornamento. Da fare anche sulla casa 2, e lo script d'installazione lo gestisce.

**Firmware della MCU (29/9, notte).**
- L'aggiornamento di sistema ha portato arduino-app-cli 0.13.0, arduino-cli 1.5.1, il kernel 7.0 e il core `arduino:zephyr` **1.0.0** (non più 0.52.0 come in Amelie). Invece di tornare indietro si usa la 1.0.0: è ciò che il sistema reinstallerebbe comunque a ogni aggiornamento.
- Il core 1.0.0 ha tre modi di avvio dello sketch: *Wait for Linux* (predefinito), *Immediate*, *Wait for App*. Si usa **Immediate**: il Latch Relay resta chiuso senza corrente, e dopo un blackout la ventola del barbecue ripartirebbe per i circa 40 secondi del boot di Linux. Con Immediate lo sketch la spegne subito.
- Caricamento dalla scheda: `remoteocd upload -f flash_sketch.cfg <loader Zephyr>.elf <sketch>.elf-zsk.bin`. Lo script OpenOCD riscrive il loader solo se è diverso, poi lo sketch a 0x8100000. Nessuna password.
- Prima compilazione riuscita: 116 KB di flash (14 %), 54 KB di RAM (20 %). Prova del Bridge da Linux con un client MessagePack sul socket del router: `$/register`, `version` = 1, `ping`, `light` (8 argomenti), `relay` rispondono; `modules` = 0 perché non c'è ancora nessun Modulino collegato.
- Il socket `/run/arduino-router.sock` ha permessi 0666: qualsiasi processo della scheda può parlare con la MCU.
- La scansione I2C chiesta da Linux la esegue il thread di I/O, unico padrone del bus: dal thread del Bridge avrebbe potuto cambiare il canale dell'Hub a metà di un'altra transazione.
- Sulla scheda mancavano `rsync` e il modulo Python `msgpack`: installati da apt.

**Voce (29/9).**
- La voce italiana `it_IT-serena-medium` sul ramo principale del repository delle voci Piper era diversa da quella provata in Amelie: si scarica una revisione fissata (`ea046e84`), controllata con SHA-256.
- Piper (GPL-3.0) gira come programma a sé nel suo ambiente, con il suo server HTTP (`python -m piper.http_server`): la casa gli manda il testo e riceve il WAV. Sulla scheda una frase italiana si sintetizza in 0,6–0,7 s; la prima frase inglese ha richiesto 11,9 s perché la voce si carica al primo uso: la casa la "scalda" all'avvio.
- Vosk piccolo italiano: 1,8 s per 1,5 s di parlato in modalità libera, 0,47 s per riconoscere un nome con la grammatica ristretta. Il modello inglese piccolo ha capito male una frase sintetizzata ("who is in the kitchen"): le frasi non riconosciute dall'analizzatore passano al modello linguistico.
- Un solo flusso `aplay` sempre aperto a 22050 Hz, con un miscelatore che somma voce, effetti e musica: niente clic fra un suono e l'altro e nessun ritardo di apertura della scheda audio.

**Visione (29/9).** Scritta e collaudata al PC su immagini sintetiche, in attesa della casa montata.
- Un generatore di immagini disegna la casa vista dal palo con la stessa geometria della camera vera: pareti, arredi, personaggi, auto, mani, luci colorate delle stanze, ombre, rumore. Per le occlusioni basta un buffer delle altezze: lungo un raggio di una camera che guarda in basso il punto più vicino è sempre il più alto.
- Correggere la luce con un guadagno unico in Lab non basta: sotto una luce colorata un arredo bianco satura in un canale e il pavimento no. Si corregge ogni canale RGB separatamente, stanza per stanza, con il rapporto più frequente misurato sul pavimento libero. Un canale saturo si tratta come limite inferiore.
- L'auto parcheggiata copre due terzi del garage: il rapporto più frequente sarebbe il suo. Rimedi: si escludono i punti dove l'immagine precedente vedeva già qualcosa, si preferisce il rapporto più vicino a quello dell'immagine precedente, e la casa avvisa la visione quando cambia una luce di una stanza.
- Sulle soglie delle porte la luce di due stanze si mescola: il guadagno passa gradualmente dall'una all'altra attraverso lo spessore del muro. Le sommità dei muri sono escluse: niente ci può stare sopra.
- Un braccio che attraversa i muretti della facciata viene diviso in due pezzi: un pezzo grande vicino a una mano è la stessa mano.
- Posizione di un personaggio: il punto più vicino al centro sono i piedi, il più lontano la testa; riportata a terra con l'altezza, la testa dà anche la posizione dei piedi quando sono nascosti dietro un muro. Scarto sulle scene sintetiche: sotto 12 mm.
- Due personaggi uguali: se uno solo viene preso in mano e posato, è per forza lui (l'altro è rimasto in vista); se vengono presi tutti e due, la casa chiede chi è chi.
- Per figurine bianche, grigie o nere la luminosità pesa di più nel confronto dei colori: è l'unica cosa che le distingue.
- Niente SciPy sulla scheda: l'assegnamento ungherese è scritto nel progetto (una sessantina di righe, confrontato con la ricerca esaustiva).
- YOLOX-Nano sulle immagini di prova di Ubuntu: gatto, persona, tazza, aereo, uccello, libro riconosciuti, 35–50 ms al PC.

**Spazio su casa1.** La partizione di sistema ha 2 GB liberi su 9,8; `/home/arduino` è una partizione a parte con 15 GB. Docker contiene 2,3 GB di immagini di App Lab che la casa non usa.

**Installazione su casa1.** Il primo tentativo di compilare llama.cpp non era partito: l'immagine non ha né compilatore né cmake. Li installa `install.sh` (pacchetti `build-essential` e `cmake`).

**Webapp e funzioni in più (29/9, notte).**
- Test delle API web con il client di prova di FastAPI su una casa simulata: pagine, stato, regole con registro delle modifiche, registrazione di un personaggio virtuale (uno o due candidati), PIN dello staff con blocco dopo cinque errori, comandi, conferme, WebSocket.
- Uno script apre la casa in simulazione con qualche personaggio e fotografa ogni schermata con Chrome senza finestra, a misura di telefono, in italiano e in inglese: servono alle guide. La lingua si legge al caricamento della pagina, quindi dopo averla impostata la pagina va ricaricata.
- Dal riepilogo delle regole mancava quale regola spegne le luci di un'altra ("Termostato: normale" spegne quelle di "caldo" e "freddo"): ora lo dice, e l'editor permette di sceglierla.
- Dalle funzioni "se avanza tempo": buongiorno e buonanotte a voce (con scenario e saluto), allarme intruso quando la casa è in modalità Via (una regola di partenza, con la nuova stanza speciale "tutte le stanze della casa"), luce di cortesia nello scenario Notte (le luci seguono le persone, arancioni e al 12 %).
- La correzione della luce ora usa una tabella di OpenCV per i guadagni dei pixel e tratta a parte solo le soglie delle porte: da 38 a 30 ms per fotogramma al PC.
- La webcam spostata diventa un avviso per tutti e compare in diagnostica.

**Frasi libere sulla scheda (29/9, notte).**
- Il modello linguistico sulla scheda legge circa 11 token al secondo e ne scrive 6. Con un'uscita in JSON una domanda costava da 3 a 15 secondi; ora il modello risponde con un comando di poche parole ("who_in kitchen") vincolato da una grammatica GBNF, e le istruzioni con gli esempi sono sempre lo stesso testo all'inizio della conversazione, che llama-server tiene in cache: dopo la prima lettura (circa 1400 token, due minuti, una volta a ogni avvio) una domanda costa 2-4 secondi.
- Un modello da 0,5 miliardi di parametri ripete le risposte degli ultimi esempi che ha visto: con gli esempi nel messaggio di sistema indovinava 15 frasi di prova su 45, con gli esempi come turni di conversazione in ordine mescolato 30. La catena completa (analizzatore a regole, poi il modello) arriva a 43 su 45 sulle frasi di prova; su 32 frasi nuove mai viste 18 sono giuste al primo colpo, e nessuna risposta è inventata.
- Per non fare la cosa sbagliata: le domande partono subito (al peggio si ottiene la risposta giusta a un'altra domanda), le azioni proposte dal modello la casa le chiede prima a voce, salvo che il modello sia molto sicuro. Un nome registrato detto senza stanza vuol dire "dov'è".
- L'analizzatore a regole ha preso molte parole nuove (vapore, festeggiare, serie TV, salsicce, troppa luce, affollato...). "Sì", "no" e "annulla" valgono solo come risposte brevi: "si gela in camera" non è un sì.
- Barzellette fisse sulla casa, in italiano e in inglese.

**Prestazioni della visione sulla scheda.** Prima versione: 186 ms per fotogramma, circa 5 al secondo. Ora 82 ms di mediana: la luce si rimisura tre volte al secondo (o subito quando la casa cambia una luce), le immagini dei guadagni restano in memoria, il confronto con la casa vuota si fa in Lab a 8 bit (OpenCV lo converte con tabelle, molto più in fretta che in virgola mobile) e con funzioni native. La webcam viene letta come MJPEG grezzo e decodificata direttamente a metà risoluzione: 7 ms invece di 15 più 3 di ridimensionamento. Una codifica JPEG per la diretta costa 14 ms.

**Hotspot e riavvio (29/9, notte).**
- Prova dell'hotspot senza perdere la scheda: comandi via USB (adb), mentre la seconda scheda Wi-Fi del PC si collega all'hotspot e la prima resta sulla rete del laboratorio. `DomotiQ-Casa1` compare sul canale 1; collegamento e indirizzo (10.42.1.250) in pochi secondi; la webapp risponde in 0,18 s; il DNS della casa risponde per `casa1.lan` e `domotiq.lan` con 10.42.1.1 e fa fallire subito i nomi di iCloud Private Relay.
- Dieci dirette insieme dallo stesso PC: 4,8 immagini al secondo per ciascuna, processore della scheda libero all'86 %. Con la webcam vera le immagini saranno di circa 24 KB: una decina di Mbit/s in tutto, da verificare con i telefoni in fiera.
- `hotspot.sh off` chiede la password: le regole sudo della casa permettono solo di accendere l'hotspot, non di spegnerlo. In fiera non serve.
- Riavvio completo di casa1: webapp raggiungibile dopo 40 s, voce pronta dopo 48 s; il modello linguistico finisce di leggere i suoi esempi un paio di minuti dopo, in sottofondo.
- Senza scheda audio USB all'avvio la casa restava muta fino al riavvio: ora la cerca ogni 5 secondi, e il microfono la segue.
