# Diario di sviluppo

Note tecniche in ordine cronologico: cosa è stato fatto, perché, quali problemi sono emersi e come sono stati risolti. Le decisioni di progetto sono raccolte a parte in [decisioni.md](decisioni.md); strumenti, versioni e licenze in [strumenti-e-licenze.md](strumenti-e-licenze.md).

---

## 28 settembre 2026 — Analisi e verifiche

**Punto di partenza.** Il diorama v3 è definito nel CAD (`build_v3.py`, 90 pezzi numerati, report di montaggio). Il repository contiene solo la licenza. Scadenza: 7 ottobre.

**Verifiche sulla piattaforma**, prima di scegliere l'architettura:

- Il connettore Qwiic della UNO Q è cablato sull'I2C4 dello STM32U585: i Modulino li vede solo il microcontrollore. Linux ci parla attraverso `arduino-router` (MessagePack-RPC su `/run/arduino-router.sock`).
- Un processo Linux che non è un'app di App Lab può ricevere le notifiche della MCU registrando il nome sul router con `$/register`.
- Il collegamento seriale fra i due lati va a 115200 baud, con messaggi di al massimo 256 byte e circa 7 ms per chiamata. Troppo poco per mandare animazioni di luce da Linux: gli effetti devono girare sulla MCU.
- Su UNO Q le brick di App Lab non offrono riconoscimento né sintesi vocale offline (esistono solo per VENTUNO Q); il Python delle app gira in Docker e installa le dipendenze da internet al primo avvio. Si usano quindi servizi systemd nativi.
- La libreria Arduino_Modulino 0.9.1 (17/9/2026) ha ancora comportamenti che su UNO Q nascondono i guasti: `begin()` con indirizzo esplicito non tocca il bus, `write()` risponde sempre `true`. Le transazioni I2C si scrivono a mano nello sketch.
- Indirizzi dai sorgenti e dai datasheet: Hub TCA9548A 0x70, Latch Relay 0x02, Buttons 0x3E, Thermo 0x44, Pixels 0x36 (valori a 7 bit).
- Un Pixels a bianco pieno assorbe fino a 264 mA dal 3,3 V del Qwiic: cinque moduli superano il limite del connettore. Serve un limite di corrente nel firmware.
- La C270 ha fuoco fisso. Il CAD usa i 55° in diagonale del costruttore sul 16:9; una calibrazione pubblicata indica che il 720p è un ritaglio del sensore 4:3. Da misurare sulla camera vera: in 4:3 la base intera ci sta con margine.
- Il Wi-Fi (WCN3980) funziona da access point con NetworkManager, quasi certamente solo a 2,4 GHz.
- Su un telefono Android che non accetta "resta connesso", il traffico verso l'indirizzo locale passa sui dati mobili e non arriva. La finestra di accesso dei captive portal non permette la fotocamera: niente captive portal: si entra nella rete e si apre l'indirizzo numerico.
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
- **L'aggiornamento si fermava** con "alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)". L'immagine preferisce da trixie-backports (priorità 900) i profili audio, il kernel, i firmware e mesa, ma non la libreria ALSA. La nuova versione dei profili richiede la libreria di backports. Rimedio: installare da backports anche `libasound2t64`, `libasound2-data`, `libatopology2t64`, poi ripetere l'aggiornamento. Lo script d'installazione lo gestisce da solo sulle schede nuove.

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
- Test delle API web con il client di prova di FastAPI su una casa simulata: pagine, stato, regole con registro delle modifiche, registrazione di un personaggio virtuale (uno o due candidati), PIN con blocco dopo cinque errori, comandi, conferme, WebSocket.
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
- Dieci dirette insieme dallo stesso PC: 4,8 immagini al secondo per ciascuna, processore della scheda libero all'86 %. Con la webcam vera le immagini saranno di circa 24 KB: una decina di Mbit/s in tutto, da verificare con molti telefoni collegati.
- `hotspot.sh off` chiede la password: le regole sudo della casa permettono solo di accendere l'hotspot, non di spegnerlo. Con la casa in uso non serve.
- Riavvio completo di casa1: webapp raggiungibile dopo 40 s, voce pronta dopo 48 s; il modello linguistico finisce di leggere i suoi esempi un paio di minuti dopo, in sottofondo.
- Senza scheda audio USB all'avvio la casa restava muta fino al riavvio: ora la cerca ogni 5 secondi, e il microfono la segue.

**Microcontrollore muto dopo un riavvio (29/9, notte).** Dopo il riavvio di prova la casa non parlava più con lo sketch: il router rispondeva `method version not available`. Il servizio di sistema del router, quando si ferma, resetta il microcontrollore (GPIO 38); con la modalità Immediate lo sketch riparte subito, chiama il router che non c'è ancora, i byte vanno persi e `Bridge.begin()` resta ad aspettare una risposta che non arriverà (la libreria non ha timeout). Un reset dato a mano con il router già attivo rimette tutto a posto. La casa ora lo fa da sé: dopo il riavvio lo sketch risponde in circa 70 secondi, senza intervento. Nuovo `scripts/bench_mcu.py` per il collaudo dei moduli al banco (scansione, luci stanza per stanza, LED, relè a richiesta, tasti e sensori), e un test del client con un router finto.

**Visione sulla scheda, a vuoto (29/9, notte).** Prova del processo di visione vero sulla UNO Q con la webcam sintetica al posto della C270: calibrazione e casa vuota dalle API, poi due personaggi seguiti di stanza in stanza con i colori giusti fino alla webapp. Il generatore di immagini sintetiche è pesante (gira nello stesso processo) e limita la prova a 2 immagini al secondo: le prestazioni vere si misurano con la webcam. La calibrazione sintetica è stata cancellata dalla scheda.

**Indirizzo del Latch Relay (29/9).** Il datasheet del Modulino Latch Relay (ABX00138), aggiornato il 28/9/2026, dà come indirizzo 0x2A nella forma a 8 bit, cioè 0x15; la libreria Modulino ufficiale cerca invece 0x04, cioè 0x02, il valore usato finora dal firmware. Probabilmente dipende dal lotto: il firmware ora prova 0x02, 0x15 e 0x10 (l'indirizzo dopo un cambio con AddressChanger). Dallo stesso datasheet: il relè (HFE60, bistabile) commuta solo carichi in continua fino a 30 V, con un morsetto a vite a due poli.

**Primo cablaggio completo al banco (29/9, pomeriggio).** Tutti i Modulino collegati con cavi Qwiic delle lunghezze previste per la casa, webcam, scheda audio e casse al Revodok. Webcam, audio e modello linguistico ci sono; dei Modulino non risponde nessuno, nemmeno l'Hub, e si accende il LED verde di alimentazione di un solo Pixels su cinque. Ogni scansione del bus andava a vuoto dopo 800 ms: il driver I2C del core aspetta 500 ms prima di arrendersi, a ogni indirizzo. Il firmware ora legge i livelli di SCL e SDA (PD12 e PD13) prima di ogni transazione: SCL è a massa in modo permanente, SDA è alta. Non è un problema di programma, è un cavo o un modulo: l'Hub porta i 3,3 V a tutti i canali senza interruttori, quindi con l'Hub alimentato bene tutti i Pixels avrebbero il LED acceso; il sospetto principale è un cavo con i fili invertiti (pin 1 sul pin 4) tra la UNO Q e l'Hub o tra l'Hub e il Relay.
- Con una linea bassa il firmware non tenta più la transazione (prima ogni tentativo bloccava luci e tasti per mezzo secondo) e ogni 5 secondi prova a liberare il bus con nove impulsi su SCL e uno STOP, a mano: `i2c_recover_bus()`, chiamata finora all'avvio, sulla UNO Q non fa nulla, perché il devicetree non gli dà i pin, e in più veniva chiamata prima che il bus fosse inizializzato (l'I2C4 parte solo con `Wire1.begin()`).
- Nuovo metodo `bus` dello sketch; la casa mostra l'avviso "Il bus dei Modulino è bloccato", *Diagnostica* e `bench_mcu.py` indicano quale linea è bassa. Guide aggiornate con il controllo dei cavi.

**Collaudo al banco con tutti i moduli (29/9, sera).** Il bus bloccato veniva dalle prolunghe: i quattro Pixels sui percorsi lunghi erano allungati con cavetti Dupont e una prolunga, e con quelli la SCL restava a massa; con cavi Qwiic da 5 cm (provvisori) rispondono tutti. Prove fatte dalla scheda, senza ventola e con la webcam appoggiata sul tavolo:
- Scansione: Hub a 0x70, Latch Relay a 0x02 (l'indirizzo della libreria, non quello del datasheet), cinque Pixels, due Thermo e Buttons ai canali previsti. Il collaudo al banco non ripete più sotto ogni canale i moduli del bus principale.
- Un minuto di luci animate su tutte e cinque le stanze a 25 immagini al secondo, con i LED dei tasti che lampeggiano: nessun modulo perso, nessuna transazione rifiutata, il microcontrollore risponde sempre entro 100 ms.
- I due Thermo leggono 24-25 °C e 53-56 % ogni 2 secondi; il relè segue i comandi della casa (stato letto dal microcontrollore: 1 durante il barbecue, 0 dopo).
- Audio: la US205 teneva l'uscita a 38 % (-23 dB) e la casa non la toccava, quindi la voce era debolissima. Ora la casa, a ogni apertura della scheda, mette l'uscita a 0 dB, spegne il ritorno del microfono sulle casse e regola il guadagno del microfono. La scelta della scheda salta le schede USB senza uscita: anche la C270 è una scheda audio USB, con il solo microfono, e dopo un riavvio poteva venire prima della US205.
- Catena vocale completa senza persone: tasto "parla" simulato, frase detta dalla casa stessa nelle casse, ascoltata dal microfono a clip, riconosciuta e eseguita ("accendi la luce in cucina": confidenza 1,00, luce accesa). Anche in inglese; il modello linguistico ha ricostruito "always in the living room" come "chi c'è in soggiorno" in 2,4 s. Corretti due casi dell'analizzatore a regole: "quanti gradi ci sono in bagno" diventava un conteggio di persone, e "la cucina è vuota?" non era capito (ora vale solo per una stanza o per la casa; "il garage è vuoto?" riguarda l'auto).
- Prima istantanea della webcam: rispondeva con l'immagine "webcam non collegata" (le immagini si preparano solo quando qualcuno guarda) e poteva poi restituire un'immagine vecchia di minuti; ora aspetta un'immagine fatta dopo la richiesta. La C270 si resetta sul bus USB a ogni apertura (un messaggio del kernel a ogni avvio della casa), senza perdere il flusso.
- Una revisione del codice ha trovato un difetto vecchio del firmware: il controllo "Linux tace da 30 secondi" confrontava tempi senza segno con un istante letto prima delle sonde e dell'impulso del relè, e una chiamata arrivata in quel momento lo faceva scattare per sbaglio (ventola spenta appena accesa, luci al respiro d'attesa). Ora legge un orologio fresco e confronta con il segno; lo spegnimento del relè passa dalla coda dei comandi e viene ripetuto finché il modulo non risponde. Prova: 8630 chiamate in 60 s con il relè acceso senza falsi scatti, e relè spento dopo 35 s di silenzio vero.
- Il metodo `bus` riporta i livelli letti a bus fermo, non in un istante qualunque (durante un trasferimento le linee sono spesso basse e *Diagnostica* avrebbe dato falsi allarmi). Il conteggio dei telefoni sull'hotspot vale solo quando la scheda fa da hotspot.
- Altre tre cose trovate controllando il codice contro le prove da fare, e corrette: il firmware ora rimanda ogni 5 secondi tutte le immagini delle luci e i LED dei tasti (un Pixels che perde corrente per un attimo tornava spento, e la casa lo credeva acceso); la casa, se per più di 20 secondi non è riuscita a parlare con lo sketch, gli rimanda tutto (dopo la guardia dei 30 secondi le stanze restavano al respiro d'attesa); i controlli periodici usano un orologio che non salta, perché un'ora spostata all'indietro fermava i controlli del microcontrollore, e un telefono imposta l'ora solo finché la casa non la conosce (il telefono di un visitatore con l'orologio sbagliato la spostava per tutti).
- Prova con la casa congelata (`kill -STOP`): anche `arduino-router` resta fermo finché la casa non riparte, e systemd riavvia un servizio solo se cade, non se si blocca. Ora il ciclo principale della casa avvisa systemd ogni 10 secondi (`WatchdogSec=120`): bloccata per due minuti, la casa viene riavviata come dopo un crash.
- I reset USB della C270 visti nel pomeriggio arrivano, ognuno, un secondo prima che parta un wireplumber del desktop (a ogni accesso ssh): interroga la webcam. Con la webcam già aperta dalla casa non succede. Un motivo in più per spegnere il desktop.

## 30 settembre 2026 — Benvenuto ai telefoni e domande della casa

**Parlare senza premere Parla (30/9, notte e mattina).** Richiesta di Emilio: la casa saluta a voce chi apre la webapp per la prima volta, chiede il nome e invita a entrare con un personaggio; in modalità chiacchierona fa domande ai personaggi, nominandoli, e ascolta la risposta senza il tasto Parla (D-18). Nuovo `voice/chatter.py`:
- Il telefono dice chi è nell'indirizzo del websocket (un browser non può aggiungere intestazioni a un websocket); la casa tiene l'elenco dei telefoni visti per 7 giorni, e il saluto arriva solo a quel telefono. Una scheda chiede il nome, che si può anche dire alla casa ("Ti chiami Luca?"), poi propone **Aggiungi un personaggio**.
- Diciassette domande, scelte in base alla stanza in cui si trova il personaggio (mai bagno e locale tecnico), con risposte attese a scelta chiusa, sì/no o colore; le proposte (festa, barbecue, cinema, luce tenue) solo dopo un sì breve e chiaro.
- Due revisioni del codice hanno trovato problemi veri, tutti corretti. Il più grave era vecchio: i nomi scritti dai visitatori (anche quelli dei personaggi) finivano dentro frasi formattate con `str.format`, e un nome come `{name:>999999999}` avrebbe costruito una frase di un gigabyte; ora si sostituiscono solo i segnaposto esatti e i nomi non possono contenere parentesi graffe. Poi: **Parla** e il citofono ora interrompono il saluto e le domande (prima venivano ignorati e il comando del visitatore diventava un nome); i nomi scritti non vengono mai letti ad alta voce; un saluto o un ringraziamento a voce ogni 45 secondi al massimo; una risposta sentita mentre la casa parlava si scarta, misurando la voce davvero in uscita e non gli annunci; le domande solo con segni di visitatori negli ultimi 5 minuti e mai due volte di fila allo stesso personaggio; il testo sentito dal microfono non si registra più (solo l'esito) e non va più ai telefoni.
- Prove sulla scheda: telefono simulato salutato, scheda del nome, ascolto e riconoscimento di un nome detto dalle casse ("lo chiamo luca" → Luca); **Parla** premuto durante il saluto lo interrompe e la casa risponde al tasto; domanda a un personaggio virtuale in cucina ("Marco, ti piace questa casa?") arrivata da sola dopo mezzo minuto. In quella prova la casa ha "sentito" un "mai" con confidenza 1,00 senza che nessuno parlasse: con una lista chiusa di parole il riconoscitore adatta qualunque rumore alla parola più vicina. Ora una parola della lista vale solo se la conferma anche il riconoscimento libero dello stesso audio.
- Il volume basso della sera era la manopola delle casse al minimo: la casa ora mette l'uscita della scheda a 0 dB, quindi la manopola va al massimo e il volume si regola dalla webapp.

**Storie, ricordi e personaggi (30/9, pomeriggio e sera).** Richiesta di Emilio dopo un giro di idee. La casa racconta storie sempre diverse sui personaggi, con personalità coerenti fino al riavvio: se Marco è un medico, alla storia dopo non diventa un calciatore. Le informazioni sui personaggi si danno a voce o dalla webapp. La casa risponde a domande libere su personaggi, stanze, feste passate ("ti ricordi la festa di compleanno di Giulia del 1998?") e faccende di casa ("Luca ha pagato le bollette?"), e ogni tanto le fa anche in modalità chiacchierona. Racconta inoltre la giornata vera dei personaggi ("cosa ha fatto Marco oggi?"), ricavata dalle posizioni viste dalla webcam, in `voice/memory.py`. Tutto in italiano e in inglese.
- Prima versione: un secondo modello linguistico, Qwen3.5-0.8B, in un servizio suo (`domotiq-story`), con le storie e le frasi della modalità chiacchierona scritte in anticipo mentre nessuno chiede niente. Emilio ha segnalato una frase inglese letta con la voce italiana: ora ogni frase si legge con la voce della sua lingua, e una storia si ferma se la casa cambia lingua.
- Le misure sulla scheda (tabella in D-19): lo 0.8B è abbastanza veloce ma scrive un italiano povero; il 2B scrive meglio, ma a 1,3 token al secondo e con minuti di attesa.
- Seconda versione, quella attuale (D-19): `data/stories.json` con i pezzi in italiano e in inglese, e un motore in `voice/stories.py` che li combina. Le personalità vengono dal database e le informazioni scritte nella webapp vengono prima: un lavoro detto a voce sostituisce quello del database, e in inglese diventa il lavoro corrispondente. Per ogni personaggio la casa evita le tracce e i pezzi già usati. La vita della casa si inventa una volta e poi resta, anche dopo la risposta di un visitatore in modalità chiacchierona.
- Controlli sui pezzi:
  - scoperte e finali legati agli eventi che spiegano;
  - giorno e notte, estate e inverno che non si incontrano;
  - niente rumore "dal garage" per chi è già in garage;
  - cani che abbaiano e gatti che soffiano;
  - "ad annaffiare".

  I test generano centinaia di storie e frasi nelle due lingue, con 60 sequenze casuali diverse. Controllano che non resti nessun segnaposto e che ogni frase sia completa, e che le risposte sulla vita di casa coincidano tra italiano e inglese.
- Prova sulla scheda con due personaggi virtuali (Marco e il cane Fido):
  - la prima frase di una storia arriva dopo circa 2 secondi, il tempo di sintetizzarla;
  - "ricorda che marco fa il medico" è entrato in "Cosa sai di Marco?" e nelle storie in inglese ("works at the hospital");
  - bollette, compleanno e festa del 1998 hanno avuto le stesse risposte in italiano e in inglese.
- Problema trovato nella prova: "Marco ha pagato le bollette?" finiva al modello dei comandi, che la prendeva per "dov'è Marco"; "hai dato da mangiare al cane?" riceveva una barzelletta. Ora le domande sulla vita di casa vanno direttamente al database.
- Il riconoscimento della lingua di una frase contava "a" e "in" come inglesi, e ha fatto leggere con la voce inglese una frase italiana. Le frasi generate ora hanno la loro lingua senza doverla indovinare. Per le frasi scritte nella webapp quelle due parole non contano più.
- Il servizio `domotiq-story` è fermo e disabilitato sulla scheda, e `install.sh` non scarica più il secondo modello. La sintesi vocale torna a usare tutti e quattro i core.

**Luci confermate e cavi ricontrollati (30/9, sera).** Emilio ha confermato a occhio i colori di ogni stanza e l'ordine dei LED dei tasti: il collaudo visivo al banco è superato. Dal repository è uscita la placca del secondo modulo Buttons (`33_Placca_Totem_Tasti2`), che nel totem con un solo modulo non serve più. Ho ricontrollato i cavi Qwiic sui percorsi del CAD:
- le tratte 3-6 (Pixels di garage, camera, cucina e soggiorno) vogliono cavi da almeno 50 cm;
- la 1 (UNO Q → Hub) e la 7 (Thermo del bagno), provate al banco con cavi da 20 cm, nella casa ne richiedono almeno 28-29;
- la 8, la 9 e la 10 (35 cm) coprono il percorso con meno di 1 cm di margine.

Le lunghezze vere si misurano sulla casa montata e poi entrano nel capitolo dei collegamenti.

## 4 ottobre 2026 — Casa montata, webcam e hotspot

**Hotspot all'avvio (4/10, notte).** Con l'hardware montato nella scocca, Pixels, Buttons, Thermo e relè rispondono tutti. L'hotspot però non c'era: il 30/9 l'avevo acceso a mano, senza la modalità di avvio, e dopo il riavvio la scheda era tornata sulla Wi-Fi del laboratorio. Ora parte da solo a ogni avvio (`scripts/hotspot.sh boot`).

**Immagine nera dopo "Regola di nuovo la luce" (4/10, notte).** Dopo la calibrazione la diretta era quasi nera e la casa vuota non si era salvata. La C270, quando esposizione e bilanciamento del bianco sono in automatico, non dice i valori che sta usando: restituisce gli ultimi impostati a mano (il bilanciamento addirittura 0), e la casa bloccava quelli, cioè esposizione 36 invece di qualche centinaio e bilanciamento al minimo. Ora la casa misura le immagini:
- lascia regolare la webcam in automatico e misura luminosità e colori;
- cerca l'esposizione manuale che dà la stessa luminosità meno un quarto, e aggiunge guadagno solo se non basta;
- prova tutta la scala del bilanciamento del bianco.

Misure sulla scheda con la luce calda del laboratorio: in automatico la C270 arriva a colori neutri (blu/verde 0,97), mentre nessuna temperatura manuale ci riesce (al meglio 0,53, con il verde dominante). Per questo la casa sceglie la temperatura che lascia meno da correggere e corregge il resto in software, con un guadagno fisso su ogni canale calcolato in modo da non cambiare la luminosità. I valori bloccati con la vecchia procedura vengono scartati all'avvio. Inoltre la webcam non abbassa più da sola i fotogrammi al secondo quando l'esposizione è lunga.

**La visione sulla casa montata (4/10, mattina e pomeriggio).** Emilio ha montato l'hardware nella scocca e ha provato riconoscimento e webapp. Problemi trovati, con le immagini registrate durante le prove e riprodotte sul PC:
- **La casa non vedeva niente.** Con la calibrazione delle 10:25 la zona esclusa del palo, proiettata fino a quasi l'altezza della webcam, copriva tutta l'immagine. Il palo è già nella geometria della scena; un controllo ora ferma una maschera che copre la casa, e un test usa gli angoli veri.
- **La webcam in automatico.** La regolazione della luce non era mai partita con valori validi, quindi la webcam ricalcolava la luce a ogni mano. Ora finché la luce non è regolata la casa non riconosce niente, e la calibrazione la regola da sola dopo gli angoli.
- **Il braccio diventava molte presenze; riflessi e cambi di luce diventavano oggetti.** Nasce la regola "niente si muove da solo" (D-20). Con quella le soglie si sono potute alzare in sensibilità, misurandole sulle immagini vere: Mister Braun, marrone scuro sul pavimento grigio, prima veniva preso per un'ombra.
- **La casa ferma ad aspettare.** La schedina dei tasti, sciolta sul vialetto con il suo cavo sul bordo della base, veniva presa per una mano ferma, e per questo Viola e Rosaria in soggiorno non venivano notate. Ora una mano deve essere grande come un braccio, e una "mano" ferma per 8 secondi è un oggetto. Il totem è escluso dall'analisi, perché i LED dei tasti si accendono e spengono.
- **Lentezza.** Con l'area analizzata finalmente piena, sulla scheda un'immagine costava fino a 250 ms. Diventa da 110 a 125 ms (da 7 a 8 immagini al secondo) con questi interventi: la luce si misura una volta al secondo invece di tre, la casa vuota si aggiorna solo dove cambia, la diretta va a 5 immagini al secondo.
- **"Webcam non collegata".** La pagina della diretta leggeva lo stato della webcam una sola volta all'apertura. Ora lo segue. I reset USB della C270 coincidono con i riavvii e con gli accessi ssh (la sessione del desktop interroga la webcam), quindi da qui in avanti uso una sola connessione ssh tenuta aperta.
- **Regolazione premuta sette volte.** Senza un segnale di avanzamento non si capiva se la casa stava lavorando. Ora la pagina di calibrazione mostra una finestra con una rotellina e blocca i pulsanti fino al risultato.

La domanda "chi è?" propone anche i personaggi di cui la casa non conosce ancora i colori, e la risposta glieli insegna. Una nota per non ripetere l'errore: l'elenco dei personaggi della webapp non riporta le firme di colore, che restano solo sulla scheda; leggendolo avevo creduto che Viola, Rosaria e Mister Braun fossero senza colori, ma il file sulla scheda li ha. Dopo il riavvio la casa ha riconosciuto per nome Viola e Rosaria in soggiorno e Mister Braun in camera, e ha chiesto dell'auto in garage. Restano da sistemare a mano i moduli sciolti sul vialetto (totem da montare).

**Domande a voce senza tasto, chi è per ogni nuovo arrivato, racconto (4/10, pomeriggio).** Su richiesta di Emilio (D-20):
- dopo ogni domanda la casa ascolta da sola; la domanda è anche sui telefoni e vale la prima risposta;
- per ogni cosa nuova chiede subito chi è, con i personaggi del tipo giusto e la possibilità di dire o scrivere un nome nuovo, che diventa un personaggio con i colori visti;
- un narratore dice chi entra, esce o cambia stanza e l'auto parcheggiata.

Nella prima prova la casa ha chiesto dell'auto e ha capito "Honda Civic", ma non il "sì" di conferma. Ora la conferma si chiede una seconda volta ("Dimmi sì o no…") invece di ripartire da capo, e per un oggetto non si propongono più i nomi delle persone.

**Audio, risposte libere, falsi positivi, luce della sala (4/10, pomeriggio e sera).** Emilio ha provato a lungo con la casa montata. In ordine:
- **Audio muto.** La scheda audio US205 ogni tanto si riavvia da sola: aplay restava bloccato e il volume tornava a -23 dB. Ora la casa riconosce la scheda dal suo bus USB e scrive senza bloccarsi. Se la scheda cambia o resta ferma più di un secondo, riapre l'uscita e rimette i livelli a 0 dB.
- **Falsi positivi che saltano.** Misurato sulle registrazioni: il centro della macchia di una statuina ferma si sposta di 0,3-0,4 mm tra un fotogramma e l'altro (2 mm al massimo). Un riflesso o un LED salta di 4-11 mm, oppure sparisce e ricompare. Tre salti in un secondo e mezzo senza mani bastano a escluderlo.
- **"Chi è?" in linguaggio naturale** (D-21). La domanda dice cosa sembra alla casa e accetta qualsiasi risposta, compreso "non c'è nessuno in giardino". Nella prima prova vera Emilio ha detto "Rosaria", il riconoscimento ha sentito "rosario" e la casa ha risposto "Non vedo Rosaria." come a un comando: ora i nomi registrati si riconoscono anche con una lettera sbagliata. È comparso anche un personaggio di nome "Chi", nato da un vecchio "chi?" frainteso; Emilio l'ha poi cancellato. Ora "chi" e le altre parole che non sono nomi non si accettano più come nome.
- **Luce della sala** (D-22). Se l'immagine resta molto più buia o più chiara della casa vuota, la webcam si riregola da sola senza toccare calibrazione, casa vuota e presenze. Una differenza comparsa senza mani (una lampada, un'ombra laterale) non diventa mai una presenza.
- **Ancora presenze inesistenti** (D-22). Domande su persone in bagno e animali in soggiorno, una dopo l'altra. Una registrazione di 90 secondi, riprodotta sul PC con le firme di colore vere, ha mostrato:
  - strisce di luce ai piedi delle pareti;
  - l'estremità della lampada del soggiorno, poco fuori dalla zona esclusa, su cui la traccia di Mister Braun è saltata quando la mano lo ha preso;
  - Viola, sdraiata sul letto e non riconosciuta, finita nella casa vuota: tolta lei, il letto vuoto sembrava una persona nuova;
  - Rosaria persa perché la mano le era solo passata sopra.

  Dopo le correzioni la stessa registrazione dà zero domande inutili, e tutti e quattro i personaggi sono riconosciuti e seguiti in ogni spostamento.
- **Voce.** Il microfono ora si apre mentre la casa finisce la domanda: prima un "sì" detto subito si perdeva, e la conferma di "Honda Civic" non è mai arrivata, due volte. Mentre la casa ascolta i tre LED dei tasti sono accesi; mentre pensa, respirano. Per "Come si chiama?", che suonava come "Cme s chiama?", ho prima rallentato la voce sulle frasi brevi, ma a Emilio la voce sembrava sbagliata: ora la velocità è normale ovunque, e solo quella frase passa a Piper già in fonemi, perché la trascrizione automatica leggeva "si" come una vocale ridotta. L'ora si chiede e si ascolta senza Parla.
- **Mobili e webapp.** Una statuina sul letto, sul divano o su un tavolo viene messa sopra il mobile e non accanto. Sul tetto dell'auto no: la statuina si confonde con l'auto. Nella webapp allarmi e notifiche si chiudono.

**Webapp, luce del locale tecnico (4/10, sera).** Nella barra in basso **Personaggi** ha preso il posto di **Eventi**, che ora apre il menu **Altro**. In fondo alle pagine lunghe le ultime righe finivano sotto la barra: il corpo della pagina aveva un'altezza fissa, così lo spazio per la barra si fermava a metà del contenuto. Verificato con le schermate a misura di telefono. Il locale tecnico ha ora la sua luce: la matrice LED della UNO Q (D-23). Il firmware è stato compilato e caricato sulla scheda, e la casa la comanda come le altre luci. Resta da vedere a occhio sulla scheda come appare, perché dalla webcam la scheda si vede di taglio.

**Sera, seconda parte (4/10).** Altre prove di Emilio e altre correzioni:
- **Matrice LED.** Si accendeva solo il LED piccolo, non la matrice: `matrixSetGrayscaleBits` vuole il numero di bit dei livelli (3), non il livello massimo (7), e con 7 la matrice restava praticamente spenta. Firmware ricaricato.
- **Mister Braun sul letto salutato come uscito.** Sdraiato era più lungo della soglia di forma. Ora una statuina dai colori decisi può essere lunga fino a 6,5 volte la larghezza, e quella che la mano ha in mano si ritrova dove viene posata, qualunque forma abbia.
- **Mobili.** Sul letto e sul divano la casa lo dice; da tavoli, panche, frigo e simili fa scendere. Le frasi hanno varianti e non si ripetono due volte di seguito.
- **Viola tra cucina e giardino.** In realtà era in bagno, contro Rosaria, e sparita dentro la sua macchia. La fusione non era stata riconosciuta, e il nome libero era finito su macchie scure lontane. Ora un nome non salta da una traccia all'altra, e la fusione si riconosce anche quando la seconda statuina è piccola.
- **"Mister Blu" e la Honda Civic.** Ora conta anche la dimensione: l'auto non è mai una statuina.
- **Notifiche non chiudibili.** Nello screenshot di Emilio la barra mostrava "nav.identities": il telefono teneva i vecchi script e prendeva solo l'HTML nuovo. Ora i file della webapp si caricano sotto una versione che cambia a ogni aggiornamento, e anche le domande hanno la loro ✕.
- **Niente si muove da solo, storico, pose** (D-24). La registrazione delle 15:31 mostrava due tracce che si scambiavano di posto senza mani, e un "oggetto" chiesto in giardino che era solo un secondo pezzo di Viola, sdraiata sul tronco dell'albero. Dopo le correzioni zero domande, i quattro personaggi seguiti ovunque, e le prime pose imparate da sole: Viola e Rosaria sdraiate in giardino.

**Sera, terza parte (4/10).** Nuove richieste di Emilio:
- togliere ogni traccia del vecchio sensore del totem;
- capire "tutti e due";
- niente falsi allarmi e niente personaggi che si muovono da soli;
- un allarme disinseribile;
- niente PIN, tutto aperto a chi usa la webapp;
- una webapp più pulita.

In ordine:
- **Le misure sulla scheda** (D-25). Con 8 presenze un'immagine costava 445 ms, a casa vuota 88. Il confronto con le pose, fino a sette per personaggio, si ripeteva per ogni macchia più volte per immagine; ora è un solo calcolo. La luce delle stanze, dopo un cambio, si rimisurava a ogni immagine; ora al massimo ogni 0,3 s. La diagnostica mostra il tempo delle fasi.
- **Pose sbagliate.** Sulla scheda Viola aveva sei pose: tra queste un grigio, un nero e il marrone di Mister Braun. Mister Brown e Mister Green ne avevano con i colori l'uno dell'altro. Erano state imparate su macchie che avevano preso il nome per errore. Il nuovo controllo del colore le ha tolte all'avvio: Viola da 6 a 1, Mister Brown da 4 a 0.
- **Viola nel locale tecnico** era la scheda UNO Q: la scheda sporge di 2 cm dalla parete e la zona esclusa stava dietro di lei. Ora la copre.
- **Personaggi che si muovono da soli**: era il nome che passava da una macchia a un'altra lontana. Ora i nomi si muovono solo con le mani.
- **Un errore subito corretto.** Il nuovo segno "presenza certa" usciva come booleano di numpy, e per qualche minuto `/api/state` ha risposto 500: la webapp sulla scheda non si caricava.
- **Avvio.** Dopo i riavvii delle 20:36 e delle 20:37, a casa vuota, l'alone delle lampade e il modulo dei tasti erano diventati Mister Brown, Mister Green e una persona sul vialetto. Ora l'avvio aspetta che le luci stiano ferme e prende solo personaggi certi; dopo il riavvio successivo la casa vuota è rimasta vuota.
- **Tutti e due**, **allarme disinseribile**, **niente PIN** e **webapp uniforme**: vedi D-25, D-26 e D-27. Le schermate della guida sono rifatte con la casa simulata.

**Sera, quarta parte (4/10).** Altre richieste di Emilio, lavorate in parallelo:
- **Proposte che diventano comandi** (D-28). Tre cause: "sì" con l'accento non entrava in nessuna grammatica, le risposte naturali venivano tagliate o scartate, le proposte per chi è in tanti non si ascoltavano affatto. Ora un sì esegue la proposta e un altro comando detto nella risposta esegue quello. `llama-server` passa a tre slot: va reinstallato il suo servizio.
- **Risposte che restano** (D-29). "Rossellina, qual è il tuo piatto preferito?" → "la pizza" diventa un'informazione di Rossellina, e "cosa posso cucinare a Rossellina?" trova la risposta. Il modello linguistico sceglie solo l'argomento: scrivere le risposte da solo inventava.
- **Riconoscimento** (D-30). La tolleranza per pixel è dentro. La firma a piena risoluzione, misurata, non serve: la webcam non ha più colore di quello che già usiamo. Lungo la strada è venuto fuori un conteggio dei colori sei volte più veloce.
- **Webapp** (D-31). La pagina della casa restava indietro di un cambio nei contatori; ora segue subito ogni spostamento, e i tocchi non si perdono più. Una presenza vista per errore si toglie dalla sua scheda. Quando la casa viene aggiornata, i telefoni si ricaricano da soli.
- **Auto** (D-31). Fuori dal garage la casa non chiede di un'auto se non è certa.
- **Un vecchio errore.** La stanza "più severa" dopo un "non c'è nessuno" non lo diventava mai: due funzioni con lo stesso nome.

## 5 ottobre 2026 — Revisione e avvio del modello

**Mattina (5/10).**
- **Perché il modello ci metteva 10 minuti** (D-33). Dai log dell'accensione di ieri: il modello si carica in 11 s, poi aspettava quasi 4 minuti che la voce preparasse le sue frasi, poi leggeva le istruzioni dei comandi (174 s) e di "chi è?" (110 s), a circa 9 token al secondo. Con le quattro istruzioni di adesso sarebbero stati circa 14 minuti, a ogni accensione. Ora ogni istruzione letta si salva su disco e all'avvio successivo torna in cache in pochi secondi; la lettura non aspetta più la voce. `llama-server` passa a quattro slot ed è reinstallato su casa1: la prima lettura ha richiesto 730 s, poi un riavvio di `llama-server` le ha rimesse tutte in 3,2 s.
- **Revisione del lavoro di ieri** (D-32). Corretti, ognuno con un test: un sì che vinceva sul rifiuto della proposta ("dai, non accendere il barbecue" lo accendeva), frasi che nominano la proposta senza chiederla, domande dette con Parla prese per la risposta a una proposta, informazioni senza senso da frasi su chi risponde ("viene da Italiana"), scelte negate salvate al contrario, nomi di personaggi scambiati per colori, richieste con un nome scambiate per domande ("Marco vuole sentire la musica"), "non è Viola, è Rosaria", la diretta che restava aperta nascosta, i tocchi persi su Personaggi, il file del rumore vuoto dopo un'interruzione di corrente.
- **Riavvio con la luce spenta.** L'aggiornamento delle 9:32 è stato installato con la luce della stanza spenta: all'avvio la casa non ha riconosciuto con certezza le statuine presenti e, come previsto, le ha lasciate fuori dalla piantina. Basta spostarle con la mano perché tornino.

**Pomeriggio (5/10).** Nuove richieste di Emilio, con tasti e totem montati:
- **Un nome non sta mai in due posti** (D-34): se Rossellina è in cucina, la statuina in soggiorno che somiglia a lei e a Rosaria è Rosaria, senza domande. L'auto non viene più proposta fuori dal garage né per una statuina.
- **Chi è, dalla webapp** (D-35): sulla scheda di una presenza e nelle domande si sceglie fra tutti i personaggi noti, e la casa impara quell'aspetto. **Elemento non riconosciuto**: si tocca dov'è sulla piantina o nell'immagine e la casa lo segue.
- **Citofono** (D-36): chi si presenta prende il nome alla prima statuina che entra, anche se la webcam la prende per un oggetto.
- **Fai domande** (D-37): un pulsante in Comandi e sulla scheda di ogni personaggio; il colore preferito, il ballo e le grigliate diventano luce, festa e barbecue.
- **Luce della sala** (D-38): con la luce della stanza spenta la visione restava bloccata a vedere mani ovunque; ora si regola da sola.
- **Parola di attivazione e LED** (D-39): detta la parola scelta nella webapp, la casa ascolta come con Parla; i LED lampeggiano mentre ascolta e restano fissi mentre parla.
- **Pezzi v8** (D-40): gli STL del repository sono quelli della versione 8.
- Dopo ogni avvio dell'app Piper prepara le frasi frequenti per circa 4 minuti e intanto la visione scende a 3-4 immagini al secondo; poi torna a 7.

**Pomeriggio, seconda parte (5/10).** Altre richieste di Emilio dopo le prove al banco:
- **Ancora un nome in due posti** (D-41). Le cause erano due:
  - dalla prima versione la casa rimetteva a una presenza senza nome il nome che aveva prima, anche quando la visione lo aveva spostato altrove;
  - un dubbio tra nomi tutti già riconosciuti si chiudeva tenendo il nome dubbio.

  Ora i nomi li decide la visione, e un nome dato a mano resta dov'è stato dato. Conta anche la taglia: una statuina non è mai l'auto.
- **"Rossana è sul letto della camera" ripetuto** (D-42): ogni tremolio sul bordo del letto ripartiva come un arrivo. Ora la stessa cosa sullo stesso personaggio non si ripete per 10 minuti.
- **I nomi prima delle altre parole e risposte immediate sui personaggi** (D-43). "Raccontami cosa piace a Rossellina" risponde su Rossellina; "Mister Brown e Rossellina stanno insieme" viene capito. Le informazioni scritte nelle schede si ritrovano, anche quelle scritte come frase intera. Nessuna domanda su un personaggio aspetta più il modello linguistico.
- **Parola di attivazione** (D-44): i LED lampeggiano mentre la parola è ancora detta, e la frase che segue, anche dopo una breve pausa, è già la richiesta.
- **Frasi della voce su disco** (D-45): dopo un riavvio si rileggono invece di essere sintetizzate di nuovo.
- **Festa** (D-46): durante lo spettacolo di luci il riconoscimento è sospeso; riparte alla fine.
- **Immagini v8** (D-47): i render della versione 8 sono nel capitolo 3.
- Durante la verifica della guida è emerso un difetto, ora corretto: con la casa in inglese, un'informazione scritta in italiano come frase intera finiva dentro una frase inglese.

**Sera (5/10).** Un difetto e i sei interventi per la velocità, chiesti da Emilio:
- **"Quando?" dopo il compleanno** (D-48): a "Viola, lo sai che manca poco al tuo compleanno?" la risposta "Quando?" riceveva "Ah, interessante!". Ora una domanda detta come risposta continua il discorso e riceve la data.
- **Regole dalle frasi vere** (D-49): dal registro di casa1, 32 frasi su 128 erano finite al modello. Quasi tutte erano storpiate dal riconoscimento ("fai presto" per "fai festa") o domande che le regole non conoscevano. Ora sono regole, e la stessa richiesta non va mai due volte al modello.
- **Priorità** (D-50): misurato prima, mentre la casa diceva una frase nuova la visione scendeva da 10 a circa 3 immagini al secondo. Ora la casa viene prima della sintesi vocale e il modello per ultimo; dentro la casa la visione cede il passo alla voce.
- **Due thread per il riconoscimento vocale** (D-51), **visione a riposo** (D-52), **frasi fisse preparate sul PC** (D-53): 235 frasi in 50 secondi sul PC, copiate su casa1. Dopo il riavvio delle 17:00 le 74 frasi frequenti sono state lette dal disco in mezzo secondo.
- **Scheda grafica** (D-54): il driver Vulkan arriva alla versione 1.0 (llama.cpp ne chiede 1.2) e il backend OpenCL di llama.cpp accetta solo i driver Qualcomm e Intel. Il prodotto di matrici scritto per la prova arriva a circa 4,5 GFLOPS; due core del processore ne fanno 8-10 con la casa accesa.
- **"Dov'è l'Honda Civic?"** (D-55): il riconoscimento libero aveva sentito "dovevo music". Ora, sullo stesso audio, un riconoscimento che conosce solo i nomi registrati sente "honda civic", e la casa risponde dov'è l'auto. Tolti anche tutti i "Mmm", che la voce leggeva "emme emme emme".

**Sera, seconda parte (5/10).**
- **Parola di attivazione** (D-56): detta da sola, la casa risponde subito "Dimmi!" invece di aspettare un secondo e mezzo di silenzio e poi dire una frase lunga.
- **Il modello più veloce sul processore** (D-57), descritto a parte in `docs/accelerazione-modello.md`. Il file "Q4_K_M" è in gran parte Q5_0. Per Q5_0, Q8_0, Q4_K e Q6_K sono state scritte istruzioni per il Cortex-A53, che non ha il prodotto scalare a 8 bit; ogni passo è stato verificato contro un riferimento in doppia precisione.
  - Le moltiplicazioni di matrici sono fino a 2 volte più veloci; il modello intero legge 1,65 volte più in fretta (1,34 volte con il contesto delle istruzioni).
  - Con le 1400 parole di contesto delle istruzioni, la flash attention era il freno più grande: spegnerla ha dato +35% in lettura.
  - Insieme, le richieste vere della casa passano da 3,41 a 2,18 secondi di mediana.
- Due prove intermedie sono state scartate dopo le misure:
  - il quinto bit ricavato con operazioni vettoriali, più lento delle letture dalla tabella;
  - il contesto a 32 bit, più lento di quello a 16.
- **Riconoscimento vocale** (D-58). Il banco di prova legge le frasi della casa con tre voci sintetiche per lingua, in tre condizioni (pulita, stanza, lontano), e controlla cosa capisce la casa. Così si sono visti tre problemi:
  - "Rossellina" non poteva essere sentita dall'elenco dei nomi, perché il modello non conosce la parola;
  - Vosk scrive "dove" per "dov'è" e "come la casa" per "com'è la casa", e le regole non lo capivano;
  - l'elenco dei nomi trovava "honda" in "andato al mare".
  Ora la casa prova anche le altre frasi probabili, ascolta i nomi sconosciuti con una scrittura nota, accetta le scritture di Vosk e conta solo i nomi interi. Con la voce pulita la casa capisce il 90,8% delle frasi in italiano (prima 82,3%), e prende per comandi il 5,6% delle frasi che non lo sono (prima 13,3%).

**Mattina (6/10).**
- **I registri delle prove al banco** (D-59). Ho riletto le frasi sentite di ieri sera e di stamattina; quelle dette dalla casa le ho ricostruite trascrivendo l'audio che la casa tiene sul disco, perché il registro non le scriveva. Da oggi il registro le scrive (`said`).
- Cosa è venuto fuori:
  - "accendi il condizionatore" accendeva le luci;
  - "il colore preferito di Mister Blu è l'azzurro" era preso per una domanda;
  - il narratore ripeteva ogni minuto "scendi dalla fioriera" alle statuine sul vialetto;
  - la casa ha sentito due volte la propria voce mentre aspettava una risposta;
  - un discorso fatto vicino alla casa è stato preso per "è un'auto".
  Dopo l'aggiornamento delle 9:49, il registro (ora con le frasi dette) ha mostrato altri due casi: "Non so che ore sono" chiesto a ogni riavvio dell'applicazione e "un'auto nuova in camera". Corretti tutti, con un test per ciascuno.
- **I personaggi fermi sulla piantina** (D-60). Il database delle posizioni ha mostrato perché ieri sera tutti uscivano e rientravano. Ogni 70 secondi la webcam si regolava di nuovo, sempre con gli stessi valori, e per 9 secondi la casa non riceveva immagini: dopo 2 secondi toglieva tutti dalla piantina. In più le posizioni seguivano ogni immagine: la macchia di Viola saltava di 15 mm senza che nessuno la toccasse.
  - Ora una statuina si sposta solo se una mano le arriva entro 5 cm.
  - Dopo, il suo posto è la mediana di 10 immagini. Il numero è misurato su quattro registrazioni: con 10 l'errore resta entro 2 mm, con 8 arriva a 6.
  - Durante la regolazione della webcam le presenze restano dove sono, e le regolazioni che non servono si diradano fino a una ogni 15 minuti.
- **Scenari e luci dalla webapp** (D-61). Gli scenari ora si vedono anche a casa vuota: lo schermo del cinema in soggiorno, il caminetto del relax, la lucina della notte in bagno, e in modalità Via le stanze che si accendono a turno come se ci fosse qualcuno. Nella webapp le luci non hanno più i tasti Accendi, Spegni e Automatico: un colore accende subito, **A** restituisce la stanza alla casa, il cerchio barrato la spegne.
- **La casa impara** (D-62). "Cosa ama Rossellina?" era stato sentito "cosa ma rossellino", e la casa aveva risposto che non lo sapeva. Ora prova le frasi alternative quando la domanda è debole, e quando davvero non sa chiede "Tu lo sai?" e tiene la risposta: tra le informazioni del personaggio, o in un archivio nuovo per le domande sul mondo (meteo compreso). Su sé stessa inventa una spiegazione e dice "Penso che…".
- **Le domande sul mondo** (D-63). "Come si fa la pizza?" faceva chiedere "Di chi?". Le risposte generate sono state provate sulla scheda: il modello da 0,5B dice cose senza senso, quello da 0,8B scrive un italiano sensato ma sbaglia i fatti, il 2B non ci sta in memoria. Emilio ha scelto di unire le strade: la casa dice che deve pensarci e chiede se aspettare la risposta del modello da 0,8B (un secondo servizio, `domotiq-chat`) o sentirla dal visitatore; in entrambi i casi la tiene per la volta dopo. "Ci sei?" ora vale come "chi sei?".
- **Il pasticcio della pizza** (D-64). Il registro del pomeriggio mostra una risposta pensata senza senso, ripetuta per due frammenti ("la pizza", "pizza"). Ci sono poi due lezioni finite sotto le domande sbagliate: "lo dico io come si fa la pizza" e "come si fa la vita". Ora:
  - quello che qualcuno insegna sostituisce e vince su quello che la casa ha pensato;
  - "te lo dico io (come si fa la pizza)" e "sbagliato" correggono l'ultima risposta;
  - la casa ripete quello che ha imparato;
  - una parola sola non basta più per ripetere una risposta;
  - nella webapp c'è la pagina **Cosa ha imparato** per correggere o cancellare ogni risposta.
- **La parola di attivazione *Domotiq*** (D-65). Il riconoscimento vocale non conosce "domotiq" e la toglieva dalla grammatica: la casa non poteva sentirla. Ora la ascolta come «domotica» e la conferma con il riconoscimento libero.
  - Sul PC, con le voci di Piper, sveglia la casa 41 volte su 42.
  - Frasi qualsiasi che finiscono come lei ("il cancello è automatico") non la svegliano.
- **La luce della sala** (D-66). Il database delle posizioni della sera mostra cosa è successo alle 17:45, quando la webcam si è regolata di nuovo per la sera:
  - tutti fuori e dentro nello stesso secondo;
  - tre personaggi saltati in altre stanze;
  - una quindicina di auto e animali nati nel soggiorno.

  Le cause erano due: un istante senza presenze alla fine della regolazione, e le pareti illuminate in un altro modo prese per mani. Ora la casa si accorge del cambio di luce (subito, o quando la sera scende piano) e tiene i personaggi com'erano un attimo prima. Poi regola la webcam e reimpara la casa vuota con la luce nuova intorno a loro. Sulla casa sintetica nessun personaggio cambia, anche con una luce più buia da un lato.
- **La casa ferma dopo il buio** (D-67). La casa vuota salvata al buio alle 21:00 faceva sembrare "abbagliata" la luce normale, e dalle 23:13 la casa aspettava senza guardare. Ora il buio si misura sull'immagine stessa, e la casa vuota non si può più salvare al buio: la webapp chiede di accendere la luce.

## 7 ottobre 2026 — La rete delle statuine
- **La rete che conosce le statuine** (D-68). Dieci minuti di registrazione con tutte le statuine, luci, scenari e ombre. Da lì 7.635 ritagli etichettati, perché ogni registrazione ora salva il riquadro di ogni personaggio; poi una rete piccola addestrata sul PC. Sul blocco di tempo lasciato fuori ha il 97,4% di accuratezza, e quando è sicura non ha mai sbagliato. Nella casa è un secondo parere disattivabile: scarta le macchie che non sono statuine, tiene i nomi quando cambia la luce, dà il nome a un nuovo arrivato invece di chiederlo.
- **Verso zero falsi positivi** (D-69).
  - La rete fa da filtro anche sulle statuine prese in ritardo, e alla nascita guarda solo le macchie nuove.
  - La casa vuota non si salva con statuine sopra.
  - Un interruttore fa annunciare solo le presenze che la rete riconosce (spento finché non lo proviamo).
  - Nella webapp c'è il registro della visione, dove si conferma o si corregge quello che la casa ha visto: le risposte diventano esempi per la rete.
  - Un banco di prova rigioca le registrazioni.
  - Nella guida rapida c'è la lista di controllo per preparare la casa.
- **La raccolta continua** (D-70). Su richiesta di Emilio la casa tiene quello che vede la webcam, entro 500 MB, per addestrare meglio la rete: un'immagine ogni 5 secondi, due al secondo quando succede qualcosa. Il registro della visione è stato rivisto voce per voce, e alla nascita la rete guarda anche le macchie che toccano una statuina.
- **Le statuine dentro la casa vuota** (D-71). Confrontando i riferimenti della raccolta si è visto che a ogni riavvio, partita con un'altra luce, la casa non trovava nessuno e pochi secondi dopo reimparava la casa vuota con tutte le statuine dentro: da lì non le vedeva più e, spostate, lasciavano fantasmi. Ora all'avvio la rete riconosce i personaggi anche quando i colori non tornano, e una casa che non conosce nessuno non impara come casa vuota quello che spicca.
- **La rete addestrata di nuovo** (D-72). I ritagli di oggi sono stati rivisti uno per uno dove casa e rete non erano d'accordo: il prato e il letto vuoti presi per statuine sono diventati "niente", le statuine inglobate nella casa vuota hanno preso il loro nome. La rete nuova riconosce con sicurezza l'80% delle macchie che non sono statuine, la vecchia il 42%, senza scartare statuine vere.
- **Le correzioni della piantina insegnano alla rete** (D-73). Le presenze eliminate e i nomi dati sulla piantina della webapp vengono ritrovati nel database della casa e diventano etichette per tutto il tempo in cui quella presenza è rimasta lì. Hanno corretto anche errori che la rete aveva imparato dalla casa, come Rossellina sdraiata sul letto chiamata "Mister Blu".
- **Una soglia per ogni rete** (D-74). La rete addestrata con le correzioni è sicura in un'altra misura, quindi la soglia per scartare le macchie si misura a ogni addestramento e viaggia con la rete. Per i personaggi dai colori simili, come Rossana e Rossellina, decide la rete quando è sicura, e la casa aspetta il suo parere prima di chiedere.
- **La casa vuota con più luci** (D-75). La casa si fotografa vuota con tutte le sue luci, una dopo l'altra, e con le luci della sala che si aggiungono a mano. Quando la luce cambia, o all'avvio, confronta con la foto più simile invece di imparare da quello che vede.

## 9 ottobre 2026 — La luce della webcam
- **La luce della webcam seguita a piccoli passi** (D-76). Misurata la C270 vera con tre luci della sala: l'esposizione va a scalini e oltre i 67 ms amplifica soltanto, il guadagno invece è fine e arriva al fotogramma dopo. Ora la casa ritocca il guadagno ogni mezzo secondo, guardando il vialetto, dove le luci della casa non arrivano. Così le regolazioni complete della webcam, con i loro 10 secondi senza immagini, diventano rare.
- **La prova sulla casa vera** (D-77). Installato alle 17:37, il regolatore seguiva la luce, ma con quattro difetti. La casa imparava la casa vuota a metà dei suoi passi. Con la luce al minimo la cima dei muri sembrava "mani" e lo teneva fermo. Al buio la webcam è stata regolata da capo sei volte in mezz'ora, sempre con gli stessi valori. Soprattutto, il vialetto non risponde alle luci della sala come la casa. Ora la luce si misura sulle stanze, la casa vuota si impara dopo i passi, e al buio la regolazione completa non si ripete per niente.
- **La vista dal vivo.** Dalle 17:37 la web app riceveva un'immagine ogni 5 minuti: il blocco che le manda era finito, con D-76, dentro il salvataggio dei valori della webcam. Sistemato, con un test che fa girare tutto il processo della visione.
- **L'orologio della scheda** segna un giorno indietro (l'8/10): senza internet e senza batteria dell'orologio non ha modo di rimettersi. Le ore dei log sono giuste, la data no.

## 10 ottobre 2026 — Una guida per chiunque
- **Preparare una scheda nuova.** Sull'immagine di fabbrica la password dell'utente `arduino` si imposta al primo `sudo`: il comando indicato prima non funzionava. La guida usa la password `domotiq2026`.
- **L'accesso con chiave.** Il passo ha un comando per caso. `add-pc.sh` riconosce una scheda nuova con un nome già usato: prima `ssh` si rifiutava con *REMOTE HOST IDENTIFICATION HAS CHANGED*, ora lo script chiede se dimenticare l'identità vecchia.
- **Una guida per chiunque** (D-78). La documentazione descrive una casa sola, la guida rapida è per chi usa la casa, e `--house` è facoltativo. Il cartello da stampare è tolto: le informazioni per collegare un telefono sono nella guida.
- **Una scheda nuova installata seguendo la guida** (D-79). Tutto il percorso, dalla prima password alla casa installata, ha trovato cinque intoppi: la dipendenza ALSA, SSH spento dopo il riavvio, `release.sh` senza opzioni e senza la cartella dei modelli, e la password del Wi-Fi rimasta nella cronologia. Guida, installer e script sono corretti. L'installer accetta `--wifi`, e la guida spiega come rendere una casa uguale a un'altra e cosa togliere prima di consegnarla.

