# DomotiQ – Specifica v1.0

Casa intelligente in scala 1:20 che gira tutta su una Arduino UNO Q 4GB, senza internet.
Due unità identiche, consegna il 7 ottobre 2026.

Questo documento raccoglie le decisioni prese nei due giri di domande del 28 e 29 settembre e le trasforma in un progetto eseguibile. Quando nel testo compare "(Dn)", n è il numero della domanda del primo giro; "(Rn)" è un punto del secondo giro.

Stato: **bozza da approvare**.

---

## 1. Obiettivo e perimetro

### 1.1 Cosa fa la v1.0 (obbligatorio)
1. Tracciamento di persone, animali, auto e oggetti: posizione in mm, stanza, conteggi, identità, storico.
2. Regole Quando/Se/Allora modificabili da chiunque dalla webapp, con registro delle modifiche.
3. Vincoli predefiniti: locale tecnico vietato con tolleranza di 5 s, bagno al massimo 1 persona.
4. Luci che seguono le persone.
5. Clima virtuale: termostato nella credenza, umidità (doccia) nel bagno.
6. Citofono vocale, che serve anche a far entrare e registrare personaggi nuovi.
7. Domande e comandi vocali in italiano e inglese, anche in forma libera, senza risposte inventate.
8. Party: musica generata dal codice e giochi di luce.
9. Grigliata: ventola del barbecue e notifica.
10. Garage e auto.
11. Webapp completa servita dalla scheda sull'hotspot.

### 1.2 Solo se avanza tempo
Luce di cortesia notturna, buongiorno e buonanotte, allarme intruso in modalità "Via", saluto automatico al totem, pagina di benvenuto per iPhone, aggiornamento del software dalla webapp.

### 1.3 Escluso
Aggiornamenti dopo il 7 ottobre (D3), giornata accelerata (D80), riconoscimento degli arredi spostati (D53), combinazioni di tasti (D59), parola di attivazione (D63).

---

## 2. Decisioni principali

| Tema | Decisione |
|---|---|
| Runtime | Servizi systemd nativi sulla UNO Q, come Amelie; niente app App Lab (D27) |
| Linguaggi | Python 3.13 su Linux, sketch Arduino sulla MCU, webapp HTML/CSS/JavaScript senza build |
| Lingua del codice | Inglese per identificatori, commenti e commit (D115, D116); documenti di lavoro in italiano |
| Licenze | Software **MIT**; documentazione, STL e immagini **CC-BY-4.0** (D130, R3) |
| Tasti | Un solo Modulino Buttons: "parla", "citofono", "lingua" (R1) |
| Riconoscimento | Metodo classico senza addestramento: differenza dalla casa vuota, colore, tracciamento (D47) |
| Voce | Vosk per nomi e sì/no, motore libero per le frasi, Qwen2.5-0.5B per capire le frasi libere, Piper per parlare |
| Rete | Hotspot a 2,4 GHz, niente captive portal, QR su cartello A4 |
| Permessi | Chiunque, tutto: casa, diretta, comandi, regole, personaggi, allarme, calibrazione, dataset, diagnostica, impostazioni, ora (D-26) |

---

## 3. Hardware (per casa)

### 3.1 Componenti
| Componente | Modello | Note |
|---|---|---|
| Scheda | Arduino UNO Q 4GB | Debian 13, MCU STM32U585 |
| Hub USB-C | UGREEN Revodok 105 | alimenta la UNO Q in PD a 5 V / 3 A |
| Alimentatore | UGREEN 65 W, 2 USB-C + 1 USB-A | nel Revodok |
| Webcam | Logitech C270 | USB 046d:0825 |
| Scheda audio | UGREEN US205 | uscita cuffie + ingresso microfono separati |
| Microfono | Neewer lapel 3,5 mm TRS | nel totem, lo spinotto passa dalla presa della pedana 2; compatibile con l'ingresso TRS |
| Casse | Goedch USB + jack 3,5 mm | manopola al massimo, volume gestito dalla casa |
| Ventola | 5 V 40×40×10 | modello da confermare (D14) |
| Modulino | 5 Pixels, 2 Thermo, 1 Buttons, 1 Latch Relay, 1 Hub | |

### 3.2 Bus I2C
- Il Qwiic della UNO Q è l'I2C4 dello STM32U585 (`Wire1`); lo usa solo la MCU. Velocità 100 kHz (la configurazione di fabbrica è 400 kHz: il firmware la abbassa).
- Bus principale: UNO Q → Hub → Latch Relay.
- Canali dell'Hub:

| Canale | Moduli | Indirizzi (7 bit) |
|---|---|---|
| 0 | Pixels garage | 0x36 |
| 1 | Pixels camera | 0x36 |
| 2 | Pixels cucina | 0x36 |
| 3 | Pixels soggiorno | 0x36 |
| 4 | Thermo bagno | 0x44 |
| 5 | Pixels bagno | 0x36 |
| 6 | Thermo credenza → Buttons | 0x44, 0x3E |
| 7 | libero | |

- Hub: TCA9548A, indirizzo 0x70 (il negozio dice 0x71: il firmware cerca fra 0x70 e 0x77). Un solo canale aperto alla volta.
- Latch Relay: 0x02 di fabbrica. Se sulla scheda crea problemi si sposta a 0x10 con AddressChanger, e la guida lo dice.
- Nessun cambio di indirizzo per il Buttons: è uno solo.

### 3.3 Totem (versione 8)
Scocca `28`, tre tasti `29`–`31` (bianco, giallo, blu) nel coperchio con i cappucci `32`, a cui si aggancia il Buttons; il microfono lavalier sta nel totem e il suo spinotto passa dalla presa della pedana 2. Tasti visti dal visitatore, da sinistra: **parla**, **citofono**, **lingua**. I LED del Buttons sono accanto ai tasti.

### 3.4 Alimentazione dei Pixels
Ogni Pixels a bianco pieno assorbe fino a 264 mA dal 3,3 V del Qwiic; il connettore regge 1 A e il regolatore della UNO Q (2 A) è condiviso con MCU e Wi-Fi. Il firmware:
- stima la corrente di ogni fotogramma di luce (circa 11 mA per canale colore a luminosità piena, per LED);
- riduce tutte le luci in proporzione se la stima supera **450 mA** in totale;
- parte con una luminosità massima del **30 %**, regolabile dalle impostazioni.

Non c'è un misuratore USB: i valori restano prudenti.

### 3.5 Relè e ventola
Contatto normalmente aperto del Latch Relay tra il 5 V della UNO Q e la ventola. Il relè mantiene lo stato senza corrente: il firmware lo **spegne sempre all'avvio**, e anche se Linux tace per 30 s.

---

## 4. Architettura software

```
 Telefoni ──Wi-Fi──► hotspot della UNO Q (NetworkManager + dnsmasq, 10.42.N.1)
                          │
   ┌──────────────────────┴───────────────────────────────────────────────┐
   │ Linux (Debian 13)                                                     │
   │                                                                       │
   │  domotiq.service  (Python, asyncio, un processo principale)           │
   │    web        FastAPI + uvicorn, porta 80, WebSocket, diretta MJPEG   │
   │    house      stato della casa: tracce, stanze, luci, sensori         │
   │    rules      motore Quando/Se/Allora, vincoli, scenari, clima        │
   │    voice      microfono, riconoscimento, intenti, risposte            │
   │    audio      mixer unico sempre aperto, suoni, musica del party      │
   │    mcu        client del router (chiamate + notifiche)                │
   │    store      SQLite (eventi, storico, registro) + JSON (config)      │
   │                                                                       │
   │  processo di visione (figlio di domotiq.service): cattura e tracciamento │
   │  piper (processi figli, uno per lingua): sintesi vocale               │
   │  domotiq-llm.service: llama-server con Qwen2.5-0.5B                   │
   │  arduino-router (di sistema)                                          │
   └───────────────────────────────┬───────────────────────────────────────┘
                                   │ seriale 115200, MessagePack-RPC
   ┌───────────────────────────────┴───────────────────────────────────────┐
   │ MCU STM32U585 (Zephyr): sketch domotiq_mcu                            │
   │   driver I2C scritti a mano, effetti di luce, party, tasti, sensori,  │
   │   relè, limite di corrente, guardia                                   │
   └───────────────────────────────────────────────────────────────────────┘
```

Principi:
- **Linux decide, la MCU esegue.** Le regole, le priorità e lo stato stanno su Linux; la MCU disegna le luci e riporta tasti e sensori.
- **Tutto il lavoro pesante fuori dal ciclo principale**: la visione in un processo separato, la sintesi e il modello linguistico in processi esterni.
- **Un difetto non ferma la casa**: ogni pezzo riparte da solo; senza webcam la casa funziona in simulazione, senza MCU la webapp mostra le luci virtuali.

---

## 5. Firmware della MCU

### 5.1 Base
- Core `arduino:zephyr` 0.52.0 e `Arduino_RouterBridge` 0.4.3, le versioni collaudate da Amelie (D24). Si compila e si carica **dalla scheda stessa** con `arduino-cli` e `remoteocd` locale.
- Nessun uso della libreria Arduino_Modulino: ogni transazione I2C è scritta nello sketch, con attese limitate.
- All'avvio: `Wire1` a 100 kHz, sblocco del bus se una linea è bassa (nove impulsi su SCL e uno STOP, a mano), ricerca dell'Hub, relè spento, luci spente, poi "respiro" tenue su tutte le luci finché Linux non manda il primo comando.
- I gestori del Bridge scrivono solo variabili protette da un mutex; tutte le transazioni I2C avvengono nel `loop()`.

### 5.2 Ciclo
| Attività | Frequenza |
|---|---|
| lettura tasti (canale 6) | 100 Hz, antirimbalzo su 2 letture |
| Thermo (richiesta, lettura dopo 40 ms) | ogni 2 s per sensore |
| disegno effetti | 50 Hz; si scrive un Pixels solo se il suo fotogramma cambia |
| ricerca moduli mancanti | ogni 5 s |

### 5.3 Metodi esposti a Linux
Stanze: 0 garage, 1 camera, 2 cucina, 3 soggiorno, 4 bagno (l'ordine dei canali dell'Hub).

| Metodo | Parametri | Risposta |
|---|---|---|
| `version` | – | versione del protocollo (1) |
| `ping` | – | millisecondi dall'avvio |
| `light` | stanza, effetto, r, g, b, luminosità 0-100, velocità 0-100, durata ms (0 = fissa) | true |
| `party` | bpm×10, seme, durata ms, ritardo ms | true |
| `relay` | 0/1 | stato letto dal modulo |
| `leds` | maschera 3 bit, maschera lampeggio 3 bit | true |
| `limits` | luminosità massima 0-100, budget mA | true |
| `modules` | – | maschera dei moduli presenti (un bit per modulo della tabella 3.2) |
| `scan` | canale, blocco 0-3 | indirizzi che rispondono, 32 per blocco |

Effetti: `off`, `solid`, `breathe`, `blink` (≤ 3 Hz), `wave`, `rainbow`, `sparkle`, `fire`, `alarm` (rosso a 2 Hz), `cool` (onda azzurra), `warm` (bagliore arancione).

### 5.4 Notifiche verso Linux
| Notifica | Contenuto | Quando |
|---|---|---|
| `btn` | tasto 0-2, premuto 0/1 | a ogni cambio |
| `thermo` | sensore 0/1, °C×100, %UR×100 | a ogni lettura |
| `mods` | maschera moduli | a ogni cambio |

### 5.5 Party sulla MCU
Linux manda BPM, seme e ritardo di partenza; la MCU genera lo spettacolo di luce in sincronia con il proprio orologio, compensando la latenza audio (misurata una volta, circa 150 ms). Niente fotogrammi via Bridge: il collegamento porta 256 byte per messaggio e circa 7 ms per chiamata.

### 5.6 Guardia
Se da Linux non arriva nulla per 30 s: relè spento e luci in "respiro" tenue. Al primo comando si riprende.

---

## 6. Collegamento Linux ↔ MCU

- Socket `/run/arduino-router.sock`, MessagePack-RPC.
- Una connessione persistente asincrona: all'avvio si registrano i nomi delle notifiche con `[0, id, "$/register", [nome]]`; le notifiche arrivano come `[2, nome, [argomenti]]`; le chiamate sono `[0, id, metodo, [argomenti]]` → `[1, id, errore, risultato]`.
- Riconnessione automatica con nuova registrazione; se la MCU non risponde, la casa lo segnala in diagnostica e continua con luci virtuali.
- Controllo di versione del protocollo all'avvio: con una versione diversa, avviso e nessun comando.
- Simulatore della MCU per PC e test: stessi metodi, stato in memoria.

---

## 7. Mappa della casa

Un file dati, `data/house.json`, ricavato dal §4 del brief e dallo script CAD `build_v3.py`: base, stanze, pareti (con altezza: 135 mm le interne e perimetrali, 46 mm le facciate), porte e varchi, arredi, luci, sensori, totem, casse, zone escluse, posizione della camera (obiettivo in 325, 145, a 930 mm dal pavimento).

Stanze (id nel codice / nome mostrato):
`kitchen` Cucina/Kitchen, `living` Soggiorno/Living room, `bedroom` Camera/Bedroom, `bathroom` Bagno/Bathroom, `utility` Locale tecnico/Utility room, `garage` Garage, `garden` Giardino/Garden, `driveway` Vialetto/Driveway.

Lo stesso file serve alla piantina della webapp, alla visione (stanze, zone escluse, bagno da sfocare) e alle regole.

---

## 8. Visione

### 8.1 Cattura
- La C270 si trova per nome in `/dev/v4l/by-id` (l'indice `videoN` cambia a ogni avvio).
- Modalità 4:3 1280×960 MJPEG se la prova del campo visivo lo conferma, altrimenti 1280×720; elaborazione a 10 immagini al secondo, analisi a metà risoluzione.
- Controlli bloccati dopo la calibrazione: esposizione manuale, bilanciamento del bianco fisso, guadagno fisso, antisfarfallio 50 Hz, compensazione del controluce spenta, nessun calo automatico dei fotogrammi al secondo. I valori si trovano misurando le immagini (la C270 in automatico non dice quelli che usa) e quello che la temperatura di colore non corregge lo corregge un guadagno fisso per canale. Si riapplicano ogni 60 s e dopo ogni riconnessione della camera. Finché non sono regolati la casa non riconosce niente. Se l'immagine resta per 5 s molto più buia o più chiara della casa vuota (meno di 0,55 o più di 1,8 volte), senza mani e senza luci della casa appena cambiate, la camera si riregola da sola, al massimo una volta al minuto, senza toccare calibrazione, casa vuota e presenze (D-22).
- Si scartano i fotogrammi vecchi nel buffer dopo ogni cambio di impostazioni.

### 8.2 Calibrazione
1. Casa senza personaggi e senza auto, arredi al loro posto.
2. Quattro tocchi sugli angoli della base nell'immagine: omografia immagine → pavimento in mm.
3. La webapp sovrappone stanze, porte, zone escluse e bagno all'immagine: si conferma o si ripete.
4. Subito dopo gli angoli, "Regola la luce e salva la casa vuota": luce della camera e mediana di 20 fotogrammi, salvata come riferimento (circa 15 s, con un indicatore di avanzamento nella webapp). Si ripete quando cambia molto la luce della sala; "Salva solo la casa vuota" dopo aver spostato un arredo.
5. Si analizza solo la base della casa; nelle immagini che lasciano la scheda tutto ciò che sta intorno è sfocato, e il bagno di serie (si può togliere dalle impostazioni).
6. Se la camera viene urtata (i bordi fissi delle pareti non coincidono più), la diagnostica avvisa e chiede di ricalibrare.

### 8.3 Da immagine a oggetti
1. Differenza dal riferimento nello spazio colore Lab, con guadagno per stanza stimato sul pavimento grigio visibile: compensa le luci colorate della casa e i cambi di luce della sala.
2. Le ombre (più scure ma dello stesso colore) non contano.
3. Pulizia morfologica, componenti connesse, zone escluse tolte (applique, chioma, palo, schede con LED del locale tecnico, fuori base).
4. Per ogni oggetto: area in mm², colore mediano e istogramma a*b*, allungamento radiale, punti estremi.
5. **Punto d'appoggio**: per un oggetto alto, il punto dell'oggetto più vicino al punto sotto la camera, lungo la retta che lo congiunge (parallasse). Dietro una parete si usa la sommità e l'altezza stimata dell'oggetto. Sopra un arredo (letto, divano, tavoli, panche) il calcolo parte dall'altezza dell'arredo: è sopra se i piedi, riportati a quell'altezza, cadono sull'arredo.
6. **Mani e braccia**: un oggetto grande come un braccio che entra dal bordo della base è una mano, con tutti i pezzi vicini; una "mano" ferma per 8 s è un oggetto sul bordo. Le tracce che copre restano ferme ma legate a lei.
7. **Niente si muove da solo (D-20, D-22)**: mentre c'è una mano, e per 0,6 s dopo, non nasce e non sparisce niente; dopo, nasce solo ciò che la mano ha portato (diverso dalla casa vuota solo da quando la mano è arrivata), compatto (al massimo 3,5 volte più lungo che largo) e ben staccato dal pavimento. Prima di mostrarlo e chiederne il nome, doppio controllo: la sicurezza (vista, ferma, contrasto, forma) supera l'80% due volte a 1 s di distanza; 92% a 2,5 s per due minuti nelle stanze dove si è appena detto che non c'era nessuno. Una cosa sconosciuta che salta o sparisce e ricompare più volte al secondo senza mano è un riflesso: esce, e lì non nasce niente per 30 s. Una differenza senza mano non diventa una presenza: le differenze tenui entrano nella casa vuota dopo circa 3 s, ciò che sembra una statuina non ci entra mai; il posto lasciato da una statuina inglobata, quando torna uguale alla casa vuota salvata, non è una presenza. Un personaggio seguito che non si vede per un momento resta al suo posto.

### 8.4 Tracciamento e identità
- Abbinamento fra un'immagine e la successiva con il metodo ungherese, su una distanza che combina posizione, colore e dimensione.
- **Trasporto a mano (D41)**: quando un personaggio sparisce sotto una mano, la traccia passa "in mano"; quando riappare vicino alla mano (o dove la mano lo lascia) riprende la stessa identità. Così due personaggi dello stesso colore restano distinti.
- **Incertezza (D52)**: se due candidati sono plausibili (due uguali spostati insieme, uno riapparso lontano, all'accensione) la traccia diventa "incerta". La casa chiede conferma sulla webapp e, se la loquacità lo permette, a voce: "In cucina c'è Marco o Leo?". Senza risposta entro 60 s tiene l'ipotesi migliore, segnata come incerta.
- La galleria di colore di ogni identità si aggiorna lentamente quando il riconoscimento è sicuro, e subito quando qualcuno dice chi è un personaggio, ma solo da una macchia che le somiglia da vicino. Le pose devono avere i colori del personaggio, più che di chiunque altro: quelle imparate sulla macchia sbagliata si dimenticano (D-25).
- **I nomi si muovono solo con le mani (D-25)**: senza una mano recente un personaggio con un nome lo tiene finché gli somiglia, e un nome non va mai a una macchia lontana dall'ultimo posto del personaggio se nessuna mano è passata di lì.
- **Tutti e due (D-25)**: due statuine a contatto sono una sola macchia; alla risposta "tutti e due" (o con due nomi) la casa le segna presenti entrambe, una nascosta dietro l'altra.
- **Riconoscimento largo**: un personaggio sdraiato o sopra un arredo è riconosciuto anche a distanza di colore fino a 0,45 se il secondo candidato è più lontano di almeno 0,15, dopo 4 immagini concordi. Una statuina su cui la mano è solo passata ritrova la sua traccia; una posata contro un'altra resta nascosta dietro di lei.
- **Nuovo arrivato (D-20, D-21)**: per ogni cosa che la casa è sicura di non riconoscere, la domanda parte subito, a voce e sui telefoni (tranne per qualcosa grande come un'auto fuori dal garage, chiesto solo se fermo e ben visibile da 10 s; D-31), con quello che le sembra ("vedo una persona nuova, giusto?"). A una persona si chiede il nome; per animali, auto e oggetti si propongono i registrati dello stesso tipo. Ogni risposta libera viene capita (nome, tipo, sì/no, "non c'è nessuno", non lo so, comandi); un nome già presente e visibile in casa vuol dire che il nuovo arrivato non c'era. Vale la prima risposta.
- **Un nome non sta mai in due posti (D-34, D-41)**: prima di ogni dubbio o domanda si tolgono dai candidati i personaggi già riconosciuti altrove (salvo una mano passata dov'erano), quelli visti l'ultima volta lontano senza una mano passata di lì, quelli di una taglia più di quattro volte diversa da tutte le loro pose (una statuina non è mai l'auto né l'auto una statuina), e l'auto fuori dal garage se non è certa (grande come un'auto, ferma e ben visibile da 10 s). Con un solo candidato rimasto la casa decide da sola; senza candidati la statuina è un nuovo arrivato e la casa chiede chi è; una domanda ormai risolta viene ritirata. I nomi li decide la visione: la casa non rimette un nome che la visione ha tolto; un nome dato dalla webapp, a voce o dal citofono resta dove è stato dato per 3 s, mentre la visione (un altro processo) lo riceve, e intanto sparisce da ogni altra presenza; se due presenze arrivano con lo stesso nome, lo tiene quella in vista.
- **A riposo (D-52)**: dopo 25 s senza mani, con le luci ferme, un fotogramma uguale all'ultimo analizzato (miniatura 80 × 60 in grigi, nessun punto oltre 6 livelli) non viene analizzato di nuovo; almeno uno al secondo lo è sempre. Il processo della visione ha priorità più bassa della voce (nice 5).
- **Durante la festa (D-46)**: dall'inizio della festa alla fine dello spettacolo di luci la visione non guarda: le presenze restano come sono, la diretta continua. A festa finita si misura di nuovo la luce delle stanze, ogni personaggio vale come toccato da una mano, e quello che si vede si riprende come all'avvio, appena le luci si fermano.
- **Dalla webapp (D-35)**: sulla scheda di una presenza e nelle domande si sceglie chi è fra tutti i personaggi noti (il nome si sposta lì) o un nome nuovo; la casa impara quell'aspetto come posa anche se insolito (fino a 0,6). **Elemento non riconosciuto**: toccato un punto della piantina o dell'immagine, la casa riprende lì la casa vuota salvata e segue quello che c'è.
- **Citofono (D-36)**: dopo il campanello, la prima statuina che compare entro 3 minuti sul vialetto o in casa (non in garage) prende il nome detto, qualunque tipo le abbia dato la webcam, senza domande.
- **Luce della sala (D-38)**: la webcam si regola di nuovo sotto il 70% o sopra il 143% della luce della casa vuota salvata; "mani" presenti senza interruzione per 30 s non bloccano la regolazione e, con una luce vicina a quella della casa vuota, entrano nella casa vuota.
- Stanza del punto d'appoggio con isteresi di 15 mm sulle porte, così chi sta sulla soglia non "salta" fra due stanze.

### 8.5 Categoria degli sconosciuti
- Dalla foto del telefono, se c'è: rilevatore **YOLOX-Nano** (Apache-2.0, addestrato su COCO) sulla scheda. Persona → persona, dog → cane, cat → gatto, car/truck/bus → auto; le altre classi → oggetto, con un nome proposto (chair → sedia, sports ball → pallone, suitcase → valigia…).
- Senza foto: dimensione e forma viste dall'alto (l'auto è grande; persona e animale si distinguono per l'allungamento dovuto all'altezza).
- La categoria proposta si conferma sempre ("Sembra un cane: giusto?").

Posizioni sulla piantina (D-60): una statuina si sposta solo con una mano entro 5 cm; quando la mano se ne va, il suo posto è la mediana di 10 immagini, poi resta fisso, e così il mobile su cui sta. Mentre la webcam si regola le presenze restano; una regolazione che non aiuta fa aspettare il doppio alla successiva, fino a 15 minuti.

### 8.6 Avvisi di riconoscimento (D15)
Il riconoscimento non dipende dal modello dell'auto né dai colori scelti, ma segnala subito:
- colore troppo vicino al pavimento, alle pareti o ai prati;
- oggetto instabile (compare e scompare);
- due identità ormai indistinguibili.

### 8.7 Diretta e privacy
- Un solo codificatore JPEG (640 px, qualità adattiva) condiviso da tutti i telefoni, fino a 10 dirette insieme (D37); la qualità scende da sola se la rete satura.
- **Bagno sfocato** su ogni immagine che esce dalla scheda: diretta, istantanee, esportazioni. Si sfoca l'impronta del bagno a quota pavimento e a quota delle pareti, più un margine.
- Sovrapposizioni attivabili sul telefono: nomi, stanze.

### 8.8 Dataset e sequenze
- Cattura di fotogrammi singoli o a raffica, etichette automatiche (dalla differenza e dal tracciamento), correzione a mano, esportazione zip (COCO e YOLO).
- Registrazione di sequenze per i test: fotogrammi JPEG a bassa risoluzione più le rilevazioni. Nel repository solo versioni ridotte.

### 8.9 Obiettivi
10 immagini al secondo (minimo 5), luce accesa entro 1 s dall'ingresso in una stanza, un core al massimo.

---

## 9. Identità

### 9.1 Dati
Nome, alias per la pronuncia inglese (facoltativo), categoria (persona, cane, gatto, altro animale, auto, oggetto), foto facoltativa, firma di colore, galleria di viste, chi l'ha creata e quando.

- **Nomi unici in tutta la casa**, senza distinzione tra maiuscole e minuscole. Per un doppione la casa chiede un cognome o un soprannome (per gli oggetti: "C'è già una sedia: come la chiamo?").
- Nessun limite al numero di personaggi o di oggetti (D39, D46).
- Gli arredi di base sono fissi; un oggetto nuovo è un'identità di categoria "oggetto" (D53).

### 9.2 Registrazione (chiunque)
**Dalla webapp:**
1. Nome, e facoltativamente una foto dal telefono.
2. "Appoggialo nella casa": la scheda trova l'oggetto nuovo. Se ce n'è più di uno, si tocca quello giusto sulla diretta o sulla piantina.
3. Categoria stimata e confermata.
4. Salvataggio. Solo se il colore è poco distintivo: "Spostalo in un altro punto" (una volta).

**Col citofono:**
1. Tasto citofono → "din don" → "Chi è?".
2. Nome già registrato: "Ciao Marco, entra pure!", e il nome va alla prima traccia che entra dalla porta nei 60 s successivi.
3. Nome nuovo: "Ho capito Marco, giusto?" → "sì" → "Piacere, Marco! Entra dalla porta" → registra chi entra.
4. Nome non capito: un secondo tentativo, poi "Non ti conosco, ma entra pure: sei un ospite".
5. Se la webcam riconosce con sicurezza un altro personaggio, la casa lo fa notare ("Mmm, a me sembri Sofia!") e tiene l'identità vista.

**Con "parla":**
"Aggiungi un personaggio" → "Come si chiama?" → "In che stanza l'hai messo?". Se nella stanza ci sono più sconosciuti chiede quale per colore ("quello rosso o quello blu?"), oppure indica di toccarlo sulla webapp.

### 9.3 Modifica e cancellazione
Chiunque può rinominare o cancellare. Le cancellazioni vanno in un cestino per 24 ore, da cui chiunque ripristina dalle impostazioni. Ogni modifica finisce nel registro (§11.5).

---

## 10. Voce e audio

### 10.1 Dispositivi
- Uscita e microfono sulla US205, cercata per nome.
- Uscita: un solo flusso ALSA sempre aperto (come Amelie, per non perdere l'inizio delle frasi), con un mixer interno: voce, musica, effetti. La musica si abbassa quando la casa parla.
- Microfono: 16 kHz mono, acceso solo mentre si ascolta (con la parola di attivazione accesa, anche mentre la casa è libera e la aspetta); l'audio resta in memoria e non si salva mai.
- Guardia dell'audio: se la scheda sparisce o il flusso si blocca (sul forum è un problema noto), la casa riapre il dispositivo e lo segnala in diagnostica.

### 10.2 Ascolto
- Tasto **parla**: ascolta finché è premuto, senza limite di tempo (D57). Tutti e tre i LED dei tasti lampeggiano mentre la casa ascolta, respirano mentre elabora la risposta e restano accesi fissi mentre parla (D-39).
- **Parola di attivazione (D-39, D-44)**: da **Impostazioni → Voce** si accende e si sceglie una parola (per esempio "Casa"); detta quando la casa è libera, fa quello che fa il tasto Parla. Il microfono resta aperto a lungo e il riconoscimento, ristretto alla parola, la segnala dal risultato parziale, mentre è ancora detta: in quel momento i LED lampeggiano e il riconoscimento libero parte dagli ultimi 2 s di audio e continua fino a una pausa di 0,9 s, quindi la richiesta detta insieme ("Casa, accendi la luce in cucina") è pronta quando finisce. Se dopo la parola, entro 0,45 s, non segue niente di forte quanto la parola stessa, la casa risponde subito "Dimmi!" (D-56), senza aspettare il riconoscimento libero se quello della parola era sicuro, poi ascolta. Se il riconoscimento libero non ritrova la parola in una frase, la casa non risponde. I numeri si confrontano in parole ("Casa 2" = "casa due"); la webapp segnala le parole che il riconoscimento non conosce.
- Dopo ogni domanda della casa (citofono, conferme, "chi è?", dubbi, domande ai personaggi, saluto ai telefoni): ascolto automatico di circa 6 s, senza tasto, ripetuto una volta se la risposta non è chiara. Il microfono si apre mentre la casa finisce la domanda e la sua voce si scarta fino a 0,35 s dopo l'ultima parola. La stessa domanda è sui telefoni: vale la prima risposta, e una risposta dal telefono ferma l'ascolto.
- **Domande sulla vita di casa (D-48)**: a una domanda della modalità chiacchierona si può rispondere con una domanda che continua il discorso ("Quando?" dopo il compleanno, "Dove?" dopo le vacanze), con un comando o una domanda per la casa; il resto riceve una reazione.
- **Racconto (D-20, D-42)**: in modalità normale e chiacchierona una frase breve per chi entra, esce o cambia stanza e per l'auto parcheggiata, detta quando il movimento si è fermato, unendo gli eventi contemporanei e mai sopra una domanda. La stessa cosa sullo stesso personaggio (la stessa stanza, lo stesso mobile) non si ripete per 10 minuti; su un mobile si sale dopo 5 immagini concordi e si scende dopo 15.

### 10.2 bis Priorità e calcolo (D-50, D-51, D-54)
- Servizi: `domotiq` CPUWeight 200, `domotiq-tts` 150, `domotiq-llm` 50 (e nice 10); dentro `domotiq` la visione ha nice 5.
- Riconoscimento vocale su due thread: alle domande della casa l'elenco chiuso e il parlato libero ricevono lo stesso audio insieme.
- Modello sul processore (D-57): `scripts/llama/arm-nodot.patch` aggiunge a llama.cpp i prodotti scalari Q5_0, Q8_0, Q4_K e Q6_K per i core ARMv8.0 senza SDOT, due righe per due colonne anche con un numero dispari di parole; `domotiq-llm` parte con `-fa off`. Richieste della casa: mediana da 3,41 a 2,18 s. Dettagli e misure in `docs/accelerazione-modello.md`.
- Scheda grafica (Adreno 702): Vulkan 1.0 con Turnip (llama.cpp ne chiede 1.2), OpenCL 3.0 con Rusticl (llama.cpp supporta solo Adreno con il driver Qualcomm e Intel). Misurata con un prodotto di matrici in OpenCL: circa 4,5 GFLOPS contro 8-10 di due core del processore con la casa accesa. Non usata.

### 10.3 Riconoscimento
| Uso | Motore |
|---|---|
| nomi, sì/no, scelte fra pochi nomi | Vosk con i modelli piccoli IT ed EN (Apache 2.0) in modalità a frasi |
| frasi libere | FastConformer IT e Parakeet-110M EN (CC-BY-4.0) su sherpa-onnx, se la prova sulla scheda dà meno di 1,5 s per 5 s di parlato; altrimenti Vosk in modalità libera |

La registrazione di un nome controlla che Vosk lo conosca in entrambe le lingue; se no, chiede una grafia alternativa.

Riconoscimento delle richieste (D-58): per una richiesta libera Vosk tiene le 5 frasi più probabili, e la casa prende la prima che le regole capiscono. Un nome che il modello non conosce si ascolta con una scrittura che conosce ("rossellina" come "rosellina"), e alla registrazione l'avviso compare solo se non se ne trova nessuna. Dall'elenco dei nomi conta solo un nome sentito intero. Le regole accettano le frasi come le scrive Vosk ("dove" per "dov'è", "a nulla" per "annulla"). Misura con `scripts/stt_bench.py`: con la voce pulita la casa capisce il 90,8% delle frasi italiane (prima 82,3%).

### 10.4 Capire la frase
1. **Percorso rapido**: parole chiave e confronto tollerante agli errori (nomi, stanze, colori, verbi). Se la frase corrisponde con sicurezza a un comando, si esegue subito. I nomi dei personaggi pesano più delle altre parole (D-43): con un nome nella frase le richieste sui personaggi vengono prima di quelle generali ("Raccontami cosa piace a Rossellina" non è "chi sei?"); un nome storpiato si ritrova per somiglianza o per una sua parola che nessun altro nome ha; "X e Y stanno insieme" dice che una macchia è i due personaggi; per 90 s una domanda senza nome riguarda l'ultimo personaggio nominato. **Le domande sui personaggi non usano mai il modello**: parole chiave, poi le parole in comune tra domanda e informazioni, poi quello che il personaggio ama, poi le storie, altrimenti "non lo so"; il modello dà l'argomento delle informazioni scritte nella webapp solo in sottofondo. Altre regole vengono dalle frasi sentite al banco (D-49): l'elenco dei personaggi, il nome dato a voce a una presenza ("l'ospite in soggiorno è Rosaria"), "e in bagno?" dopo una domanda su una stanza, "Di chi?" a una domanda senza nome, "dov'è X" con un nome sconosciuto, e le parole della festa sentite male ("fai presto", "let's body"). Il modello non riceve due volte la stessa richiesta: le ultime 256 risposte restano in memoria.
2. **Percorso libero**: Qwen2.5-0.5B su llama-server riceve la frase e una descrizione breve della casa (stanze, nomi, comandi possibili) e deve rispondere con un JSON vincolato: `{"intent": ..., "args": {...}}`. Mentre ragiona la casa dice "Vediamo…". Le risposte a "chi è?" che le regole non capiscono passano allo stesso modello, con istruzioni proprie in un secondo slot di llama-server (D-21); quelle alle proposte della modalità chiacchierona in un terzo, che dice solo se la risposta accetta, rifiuta o nessuna delle due; l'argomento delle informazioni sui personaggi che nessuna parola chiave descrive in un quarto, chiesto in sottofondo. Gli slot letti si salvano su disco e tornano in pochi secondi a ogni avvio (D-33).
3. **La risposta la compone sempre il codice** dai dati veri della casa, con frasi preparate in IT ed EN: il modello sceglie cosa fare, non inventa cosa dire.
4. Se l'intento è incerto: "Intendi accendere la luce in cucina?".
5. Se la domanda non riguarda la casa: "Sono la casa: posso dirti chi c'è, dove, che temperatura fa, e posso accendere luci, fare festa o grigliare."

Quando non sa (D-62): su un personaggio o sul mondo chiede "Tu lo sai?" e tiene la risposta (informazione del personaggio per argomento, o `var/config/knowledge.json`) per le domande uguali o simili; su sé stessa inventa una spiegazione plausibile detta come "Penso che…".

Dalle prove al banco (D-59): "accendi il condizionatore/il riscaldamento" fa l'onda di luce del termostato; "il colore preferito di X è Y" è un'informazione su X, non una domanda; il narratore non ripete la stessa frase sullo stesso personaggio per dieci minuti se non cambia stanza; il microfono scarta la voce della casa; dopo due nuovi arrivati senza risposta la casa li chiede per tre minuti solo sui telefoni.

Intenti: dov'è X, chi c'è in una stanza, quante persone, dov'è l'auto, temperatura, umidità, che ore sono, imposta l'ora, luce accesa/spenta/colore per stanza o tutte, scenario, party, grigliata, riassunto della casa, cosa sai fare, lingua, loquacità, volume, aggiungi personaggio, sì/no/annulla, una storia, cosa ha fatto X oggi, ricorda che X…, cosa sai di X, domande su un personaggio ("cosa mangia X?", "di dove è X?") con le sue informazioni, che comprendono le risposte date alle domande della modalità chiacchierona, ricordi e domande libere sulla vita di casa.

**Storie e vita della casa (D-19).** Storie, ricordi e risposte sulla vita di casa (bollette, assicurazioni, compleanni, feste passate, spesa, faccende, animali, auto, vacanze) si generano combinando i pezzi di `data/stories.json`, scritti a mano in italiano e in inglese e compatibili con qualunque nome. Ogni personaggio riceve dal database lavoro, carattere, passione e mania, che restano fino al riavvio; le informazioni date alla casa (webapp o "ricorda che…") vengono prima. Le storie su uno stesso personaggio non si ripetono finché ci sono pezzi nuovi; una risposta inventata resta la stessa, nelle due lingue, fino al riavvio. Qui la casa inventa di proposito: il punto 3 vale per i comandi e per le domande sullo stato reale della casa.

### 10.5 Sintesi
Piper (`piper1-gpl`, GPL-3.0) **come programma separato**: un processo per lingua, sempre caricato, che riceve una frase per riga e restituisce audio grezzo. Il codice di DomotiQ resta MIT perché non incorpora Piper. Voci: `it_IT-serena-medium` (CC BY 4.0) ed `en_US-ljspeech-medium` (pubblico dominio). Le frasi fisse si preparano all'avvio e restano in memoria; ogni frase sintetizzata si salva anche su disco (`var/voice/`, un WAV per frase, al massimo 3000, via le meno usate di recente) e dopo un riavvio si rilegge invece di risintetizzarla (D-45). Le frasi fisse (oggi 239) si possono preparare in anticipo con `scripts/voice_cache.py` in `models/voice-cache/`, che la casa legge e `release.sh` copia dal PC (D-53).

### 10.6 Loquacità (D69)
| Livello | Comportamento |
|---|---|
| Silenziosa | non parla mai; restano campanello e suoni brevi; risposte solo sulla webapp |
| Normale | eventi importanti, allarmi e avvisi, citofono, risposte |
| Chiacchierona | commenta spostamenti, temperatura e umidità, propone di fare festa o di accendere il barbecue e ascolta la risposta senza il tasto Parla (D-28); ogni due minuti circa fa una domanda a un personaggio con un nome, adatta alla stanza, e ascolta la risposta senza il tasto Parla (D-18); due volte su cinque al suo posto un aneddoto, un ricordo o una domanda sulla vita di casa, generati dal database delle storie (D-19) |

Ogni frase detta compare anche come testo nella webapp.

**Benvenuto ai telefoni nuovi (D-18).** La prima volta che un telefono apre la webapp la casa lo saluta, chiede il nome (a voce, senza il tasto Parla, o scritto sul telefono) e invita a entrare in casa con un personaggio. Un saluto a voce ogni 45 secondi al massimo; più telefoni insieme, un saluto solo; i telefoni si dimenticano dopo 7 giorni. In modalità silenziosa resta solo la scheda sul telefono.

### 10.7 Lingua
Italiano all'avvio. Il tasto **lingua**, la webapp o la voce la cambiano. LED acceso = inglese. Al cambio tutte le luci lampeggiano per un secondo in verde (italiano) o in rosso (inglese) e la casa dice "Italiano" o "English" (R2).

### 10.8 Suoni
Tutti generati dal codice: campanello, bip di inizio e fine ascolto, allarme, notifica, musica del party. Nessun campione esterno.

---

## 11. Regole

### 11.1 Struttura
```json
{
  "id": "r-bathroom-max-one",
  "name": {"it": "Bagno al massimo 1", "en": "Bathroom max 1"},
  "enabled": true,
  "priority": 80,
  "cooldown_s": 10,
  "when": {"type": "count_above", "room": "bathroom", "value": 1,
           "who": {"category": "person"}, "grace_s": 2},
  "if": [],
  "then": [
    {"type": "light", "room": "bathroom", "effect": "blink", "color": "#ff8000", "duration_s": 10},
    {"type": "say", "text": {"it": "Il bagno è occupato! Aspetta il tuo turno.",
                             "en": "The bathroom is taken! Please wait your turn."}},
    {"type": "notify", "level": "warning", "text": {"it": "Due persone in bagno", "en": "Two people in the bathroom"}}
  ]
}
```

### 11.2 Quando (eventi)
entra in una stanza, esce da una stanza, resta in una stanza per N s, conteggio sopra/sotto una soglia, identità compare/scompare, ora, temperatura o umidità oltre soglia, tasto, auto arriva/parte/parcheggiata/assente, scenario attivato.

### 11.3 Se (condizioni, tutte vere)
stanza occupata o vuota, conteggio, identità presente o assente, fascia oraria, soglie di temperatura e umidità, scenario attivo, stato di griglia e auto. "Oppure" = due regole.

### 11.4 Allora (azioni)
luci (stanza o tutte, colore, effetto, luminosità, durata), suono, frase (con segnaposto `{name}`, `{room}`, `{count}`, `{temp}`), relè, notifica, scenario, attesa.

### 11.5 Chi le modifica
- Chiunque dalla webapp (D82, D93). Ogni telefono ha un identificativo automatico; alla prima modifica la webapp chiede un soprannome facoltativo.
- Registro sulla scheda: data e ora, telefono, soprannome, cosa, prima e dopo. Visibile in "Eventi → Modifiche".
- Cestino di 24 ore, ripristino dalle impostazioni.
- Esportazione e importazione in JSON.

### 11.6 Regole di partenza
| Regola | Comportamento |
|---|---|
| Luci che seguono | stanza con persone: bianco caldo a luminosità media; si spegne 3 s dopo che si svuota. Gli animali no, l'auto accende il garage |
| Tecnico vietato | chi resta nel tecnico oltre 5 s: luci di soggiorno e garage rosse lampeggianti, "Attenzione: il locale tecnico è riservato!", avviso; ripete ogni 10 s. Chi passa entro 5 s non fa scattare nulla. Identità esentabili |
| Bagno al massimo 1 | come l'esempio in 11.1; gli animali non contano |
| Doccia | umidità del bagno +8 % sulla base: onda azzurra nel bagno, "Accendo l'aspiratore", notifica; finisce entro +3 % |
| Termostato | vedi §12 |
| Auto arriva | luce del garage, "Bentornato!" |
| Auto parte | "Buon viaggio!", luce del garage spenta |
| Grigliata pronta | notifica, "La grigliata è pronta, tutti in giardino!" |
| Party affollato | 4 o più persone in soggiorno → party (disattivata) |
| Grigliata affollata | 2 o più persone in giardino per 10 s → grigliata (disattivata) |

### 11.7 Precedenza
Allarmi e vincoli → party → scenario → regole → luci che seguono. Il livello più alto attivo decide le luci di una stanza; quando finisce, torna quello sotto.

Le regole d'allarme contano solo le presenze certe: un personaggio noto (confermato o riconosciuto bene) o una cosa sconosciuta ferma e ben visibile da almeno 6 s (D-25). L'allarme si inserisce e si disinserisce come un antifurto: disinserito, le regole d'allarme non scattano e quelle in corso si spengono; reinserito, chi è già in un posto sorvegliato viene notato di nuovo (D-27). Notifica rossa per le regole che suonano l'allarme o mandano una notifica di tipo allarme, ambra per le altre.

### 11.8 Scenari
Ogni scenario si riconosce anche a casa vuota (D-61): Normale (luci che seguono), Cinema (bagliore azzurro tremolante di uno schermo in soggiorno, resto spento), Relax (caminetto in soggiorno, luce arancione che respira in camera, luci calde tenui dove c'è gente), Notte (lucina arancione in bagno, luce di cortesia molto tenue), Via (una stanza alla volta accesa per 15-30 s, come se in casa ci fosse qualcuno). Si scelgono dalla webapp o a voce; la casa ne dice il nome.

### 11.9 Sicurezza delle luci
Mai più di 3 lampeggi al secondo, in nessun effetto.

---

## 12. Clima virtuale
- **Termostato** (Thermo nella credenza). Riferimento = media degli ultimi 5 minuti. "Caldo" quando sale di 1 °C sopra il riferimento o di oltre 0,1 °C al secondo: "Fa caldo! Accendo il climatizzatore" e onda azzurra in tutte le stanze, finché non torna entro 0,5 °C. Soffiare sul sensore (umidità +10 %) ha lo stesso effetto, più in fretta. 1 °C sotto il riferimento: "Accendo il riscaldamento", luce arancione calda.
- Il dito scalda lentamente (il circuito ha inerzia): la webapp mostra la temperatura in tempo reale, così si vede che sta salendo.
- Temperature e umidità in piantina, in °C e %.

---

## 13. Party, grigliata, garage

### 13.1 Party
- 20 s (regolabile 10-60), 124 BPM, dance elettronica sintetizzata dal codice: cassa, clap, charleston, basso, accordi, melodia; variazioni casuali a ogni party.
- Luci: tutti i Pixels a tempo, lampi sotto i 3 al secondo, finale a scintille.
- "Si balla!" all'inizio, "Festa finita!" alla fine. Almeno 30 s fra due party.
- Durante il party il riconoscimento della visione è sospeso e riparte alla fine delle luci (D-46).
- Si avvia da webapp, voce o regola (non più da tasto).

### 13.2 Grigliata
Ventola 20 s (regolabile), "Accendo il barbecue!", poi "La grigliata è pronta, tutti in giardino!" e notifica. Limite di sicurezza di 120 s continui. Da webapp, voce o regola.

### 13.3 Garage e auto
Luce accesa quando entra l'auto o una persona. "Auto parcheggiata" dopo 3 s ferma nell'area del garage (x 452-632, y 262-342), luce spenta dopo 10 s. "Auto assente" dopo 10 s fuori dal garage. L'auto è seguita in tutta la casa.

---

## 14. Ora
La scheda non ha batteria per l'orologio. In ordine:
1. NTP quando la scheda ha internet (sviluppo);
2. il primo telefono che apre la webapp dopo l'avvio invia la sua ora (solo finché la casa non la conosce: un telefono con l'orologio sbagliato non deve spostarla a tutti);
3. a voce: "Sono le 15 e 30";
4. la si corregge nelle impostazioni.

Se dopo 2 minuti dall'avvio l'ora è ancora sconosciuta, la casa lo chiede una volta (salvo modalità silenziosa): "Non so che ore sono: che ore sono adesso?", e ascolta la risposta senza tasto. Fuso Europe/Rome.

---

## 15. Webapp

### 15.1 Tecnica
- HTML, CSS e JavaScript moderni, moduli ES, nessuna compilazione, nessuna libreria esterna. Tutto servito dalla scheda.
- Caratteri **Open Sans** e **Roboto Mono**, quelli dei siti Arduino, inclusi come file woff2 (licenza OFL-1.1).
- Tempo reale via WebSocket (`/ws`): all'apertura lo stato completo, poi solo i cambiamenti. Diretta MJPEG su `/api/stream`.
- Foto: `<input type="file" accept="image/*" capture="environment">`, ridotte nel telefono a 1024 px prima dell'invio. Funziona senza HTTPS.
- Nessun service worker (serve HTTPS); manifest e icona per "Aggiungi a Home".
- Lingua per telefono (italiano o inglese, di partenza quella del telefono).
- Tema chiaro e scuro automatici, verde acqua con accento arancione, grandi aree di tocco, uso a una mano.

### 15.2 Ruoli
- **Chiunque** può fare tutto (D-26): casa virtuale, diretta, comandi, eventi, regole, identità, simulazione, allarme, calibrazione, dataset, diagnostica, impostazioni (ora compresa), ripristino dal cestino. Le azioni che non si annullano chiedono conferma; ogni modifica va nel registro.

### 15.3 Schermate
Barra in basso: **Casa**, **Diretta**, **Comandi**, **Personaggi**, **Altro**. Ogni pagina comincia con titolo, una riga che dice a cosa serve e l'azione principale a destra del titolo. **Altro** è diviso in tre gruppi: *La casa* (Eventi, Regole, Simulazione), *Messa a punto* (Calibrazione, Diagnostica, Impostazioni), *Per lo stand* (Cartello, Informazioni), più il soprannome. Il Tabellone non è nel menu: si apre scrivendo `/board`.

Notifiche in cima, un colore per tipo: rosso un allarme (con **Disinserisci**), ambra un avviso, grigio la connessione persa, scheda bianca con bordo verde acqua una domanda della casa (con **Tutti e due** quando i nomi proposti sono più di uno).

1. **Casa**: piantina 2D fedele al CAD, stato della casa, chi c'è e, in fondo, il riquadro dell'allarme (inserito, disinserito, in corso; D-27). La piantina mostra:
   - stanze, pareti, porte, arredi;
   - luci col loro colore, temperature e umidità, conteggi per stanza;
   - personaggi con sagoma della categoria nel loro colore e nome, e con il segno "incerto" quando serve;
   - auto, griglia accesa, allarmi (stanza rossa) e avvisi (stanza ambra).
2. **Diretta**: immagine della webcam col bagno sfocato; nomi e stanze sovrapponibili.
3. **Regole**: elenco con interruttori; editor Quando/Se/Allora a moduli; scenari; cestino.
4. **Identità**: elenco con foto o sagoma; "Aggiungi" guidato (§9.2); rinomina, cancella.
5. **Eventi**: eventi e notifiche, frasi dette dalla casa, registro delle modifiche, storico per identità.
6. **Comandi**: party, grigliata, scenari, luci per stanza (colore ed effetto), lingua, loquacità, volume.
7. **Calibrazione**: quattro angoli, verifica delle sovrapposizioni, casa vuota, "regola di nuovo".
8. **Simulazione**: personaggi virtuali da trascinare, sensori virtuali (temperature, umidità, tasti), interruttore per silenziare luci e voce vere. Sul PC gira senza alcun hardware.
9. **Diagnostica**:
   - Modulino per canale dell'Hub e scansione I2C;
   - webcam, audio (suono di prova, registrazione di 3 s), Wi-Fi e client collegati;
   - CPU, memoria, temperatura, disco; tempo di un'immagine della visione e sue fasi;
   - registri da scaricare.
10. **Impostazioni**: nome della casa, lingua della voce, volumi, soglie, luminosità massima, rete, ora, backup e ripristino della configurazione, riavvio e spegnimento.

Pagine in più:
- **Informazioni**: cos'è il progetto, crediti, licenze delle voci e dei modelli.
- **Cartello**: A4 verticale stampabile con i due QR (rete e indirizzo) e le istruzioni in italiano e inglese.
- **Tabellone**: piantina, eventi e diretta per un monitor o tablet allo stand, senza comandi.

### 15.4 API (sintesi)
| Metodo e percorso | Uso |
|---|---|
| `GET /api/state` | stato completo |
| `WS /ws` | cambiamenti in tempo reale, richieste di conferma, sottotitoli |
| `GET /api/stream` | diretta MJPEG |
| `GET/POST/PUT/DELETE /api/rules` | regole |
| `GET/POST/PUT/DELETE /api/identities` | identità; `POST /api/identities/{id}/photo` |
| `POST /api/commands/{nome}` | party, grigliata, luci, scenario, lingua, volume, loquacità, allarme |
| `POST /api/confirm/{id}` | risposta a una richiesta di conferma (anche "tutti e due", "non c'è niente" e un personaggio già noto qualsiasi) |
| `POST /api/tracks/{id}/identity`, `POST /api/tracks/{id}/dismiss`, `POST /api/tracks/adopt` | chi è una presenza (uno già noto o uno nuovo), togliere una presenza falsa, aggiungere un elemento non riconosciuto indicato sulla piantina o nell'immagine |
| `POST /api/voice/ask`, `POST /api/voice/wake_check` | "Fai domande"; come viene sentita la parola di attivazione |
| `POST /api/time` | ora dal telefono |
| `/api/settings`, `/api/vision/...`, `/api/diagnostics`, `/api/backup.zip`, `/api/trash`, `/api/system/...` | impostazioni, calibrazione, dataset, diagnostica, backup, cestino, sistema |
| `GET /api/events` | eventi e registro |

---

## 16. Rete

| | Casa 1 | Casa 2 |
|---|---|---|
| SSID | DomotiQ-Casa1 | DomotiQ-Casa2 |
| Sicurezza | WPA2, password generata dall'installatore e stampata sul cartello | idem |
| Canale | 1 | 11 |
| Indirizzo | 10.42.1.1 | 10.42.2.1 |
| Nomi | casa1.lan, casa1.local | casa2.lan, casa2.local |

- NetworkManager in modalità condivisa; dnsmasq risponde per `casaN.lan` e fa fallire subito i nomi di iCloud Private Relay; avahi annuncia `casaN.local`.
- Niente captive portal. Il cartello dice: "Se il telefono lo chiede, scegli Resta connesso / Usa senza Internet. Android: se la pagina non si apre, spegni i dati mobili."
- Guardia del Wi-Fi: se l'access point cade, lo si riattiva e lo si segnala.
- Durante lo sviluppo la scheda sta sulla rete di casa; in M3 si prova l'hotspot, e se la scheda regge rete di casa e hotspot insieme si tengono entrambi fino alla consegna.

---

## 17. Dati e configurazione

Sulla scheda, in `/home/arduino/domotiq`:

| Percorso | Contenuto |
|---|---|
| `venv/` | ambiente Python |
| `models/` | Vosk, Piper, FastConformer/Parakeet, Qwen2.5-0.5B, YOLOX-Nano |
| `llama.cpp/` | llama-server compilato |
| `var/config/` | impostazioni, regole, scenari, identità (JSON) |
| `var/calibration/` | omografia, casa vuota, impostazioni della camera |
| `var/photos/` | foto delle identità |
| `var/domotiq.db` | SQLite: eventi (7 giorni), posizioni (24 ore), registro delle modifiche |
| `var/dataset/`, `var/recordings/` | catture e sequenze dalla pagina di calibrazione |

Backup e ripristino: un file zip dalle impostazioni, con scelta di cosa copiare; la calibrazione non si copia mai fra case (D110). Le due case sono indipendenti anche nei personaggi (D109).

---

## 18. Installazione, servizi, aggiornamenti

### 18.1 Prima installazione (con internet, una volta)
1. Preparazione della scheda (App Lab oppure `adb`): nome, password, Wi-Fi, aggiornamento, SSH. Casa 1 fatta il 29/9.
2. `git clone` in `/home/arduino/domotiq` e `bash scripts/install.sh --house 1`. Lo script:
   - fa i controlli (utente, spazio, sistema) e installa i pacchetti di sistema;
   - crea l'ambiente Python con versioni fissate;
   - scarica i modelli con controllo SHA-256 (sono anche allegati alla release);
   - compila llama.cpp con `scripts/llama/arm-nodot.patch` (istruzioni per il Cortex-A53, `docs/accelerazione-modello.md`);
   - compila e carica il firmware;
   - `arduino-app-cli properties set default none`, così nessuna app App Lab sostituisce il firmware;
   - configura l'hotspot e genera la password del Wi-Fi;
   - installa i servizi;
   - blocca i pacchetti audio e disattiva gli aggiornamenti automatici.
3. Riavvio: la casa parte da sola.

### 18.2 Servizi
| Servizio | Ruolo |
|---|---|
| `domotiq` | applicazione (con la visione come processo figlio); si riavvia da solo; porta 80 con `CAP_NET_BIND_SERVICE` |
| `domotiq-llm` | llama-server con Qwen2.5-0.5B, sempre acceso per rispondere subito |

Confinamento come Amelie (`ProtectSystem`, `NoNewPrivileges`, `PrivateTmp`).

### 18.3 Aggiornamenti
`git pull` + `install.sh` (rifà solo ciò che è cambiato), oppure `scripts/release.sh` dal PC via SSH sull'hotspot.

### 18.4 Altri PC (D136)
`scripts/add-pc.sh`, lanciato sul nuovo PC, crea una chiave e la copia sulla scheda (serve la password una volta); poi `ssh casaN`. In alternativa App Lab in modalità rete. La guida lo spiega.

### 18.5 Prima della consegna
- sudo di nuovo con password; SSH solo con chiave;
- password del Wi-Fi annotata nella guida rapida per lo stand, non nel repository.

---

## 19. Risorse previste sulla scheda
| Parte | RAM |
|---|---|
| sistema, router, servizi | ~0,6 GB |
| applicazione e web | ~0,2 GB |
| visione | ~0,25 GB |
| Vosk IT ed EN | ~0,6 GB (l'inglese si carica solo in modalità inglese) |
| motore libero | ~0,3 GB |
| Piper, due voci | ~0,25 GB |
| Qwen2.5-0.5B | ~0,6 GB |
| **Totale** | **~2,8 GB su 3,6** |

CPU: la visione occupa circa un core; riconoscimento e modello linguistico lavorano a raffica mentre si parla. Durante una risposta libera la visione può rallentare per qualche secondo.

---

## 20. Test
- **Automatici (pytest)**:
  - motore di regole e vincoli, con orologio finto;
  - tracciamento su scene sintetiche e su sequenze registrate: trasporto a mano, due personaggi uguali, porte;
  - geometria: omografia, parallasse, stanze;
  - intenti in italiano e inglese;
  - registrazione per webapp, citofono e voce;
  - configurazione, API, client della MCU contro un router finto.
- **GitHub Actions**: i test a ogni push.
- **Sulla scheda**:
  - `scripts/bench_mcu.py`: scansione, luci, tasti, sensori, relè;
  - prova audio, prova della camera, prova dell'hotspot con Android e iPhone;
  - misura di tempi e memoria.
- **Collaudo finale**, elenco in `docs/it/05-collaudo.md`, su entrambe le case.

---

## 21. Repository

```
firmware/domotiq_mcu/      sketch della MCU
src/domotiq/               applicazione (web/ = webapp)
data/                      house.json, frasi, regole e scenari di partenza
scripts/                   install, release, add-pc, systemd, strumenti di prova
scripts/llama/             patch di llama.cpp per il Cortex-A53 e strumenti per misurarla
tests/                     test e sequenze ridotte
hardware/stl/              gli STL della versione 8, numerati da 01 a 59 (84 file)
docs/it/, docs/en/         guide
docs/images/               render v8 ripuliti, schemi, schermate
docs/specifica.md          questo documento
docs/diario.md             diario di sviluppo
docs/decisioni.md          decisioni tecniche
docs/strumenti-e-licenze.md strumenti, librerie, modelli, versioni, licenze
docs/accelerazione-modello.md le istruzioni del modello per il Cortex-A53, con le misure
README.md, README.it.md    guida Project Hub (EN, IT)
LICENSE                    MIT
LICENSE-DOCS.md            CC-BY-4.0 per documentazione, STL, immagini
```

Intestazione di ogni sorgente:
```
SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
SPDX-License-Identifier: MIT
```
Commit in inglese, piccoli e frequenti, direttamente su `main`; tag `v0.1`…`v1.0`; autore e committer `Emilio Destratis <emilio.destratis@gmail.com>`.

---

## 22. Documentazione
- `README.md` in inglese e `README.it.md` in italiano, scritti per l'editor di Project Hub: un livello di titoli, niente tabelle, niente elenchi numerati o annidati, link assoluti.
- Guide in `docs/en` e `docs/it`: preparare la UNO Q, installazione, stampa e montaggio (con i numeri incisi), cablaggio, collaudo, uso della webapp, riconoscimento e identità, voce, regole, risoluzione dei problemi, attribuzioni.
- Guida rapida per lo stand, una pagina stampabile in italiano e inglese.
- Le funzioni si descrivono con i termini tecnici veri: visione artificiale, machine learning, modello linguistico (LLM), riconoscimento e sintesi vocale (R10).
- Credito: "Created by Emilio Destratis (destratis.it) in collaboration with Arduino."
- I modelli dei personaggi e dell'auto non sono nel repository: la guida li cita con i link che fornirai (D15).

---

## 23. Licenze di terze parti (previste)
| Componente | Licenza | Uso |
|---|---|---|
| FastAPI, uvicorn, starlette | MIT, BSD-3 | server web |
| NumPy, SciPy | BSD-3 | calcolo, abbinamento |
| OpenCV (headless) | Apache-2.0 | visione |
| msgpack | Apache-2.0 | router |
| Vosk + modelli piccoli IT/EN | Apache-2.0 | riconoscimento vocale |
| sherpa-onnx; FastConformer IT, Parakeet-110M EN | Apache-2.0; CC-BY-4.0 | riconoscimento libero |
| ONNX Runtime; YOLOX-Nano | MIT; Apache-2.0 | categoria degli oggetti |
| llama.cpp; Qwen2.5-0.5B-Instruct | MIT; Apache-2.0 | frasi libere |
| Piper (piper1-gpl) | GPL-3.0, programma separato | sintesi vocale |
| Voci serena (IT), ljspeech (EN) | CC BY 4.0; pubblico dominio | sintesi vocale |
| segno | BSD-3 | QR del cartello |
| Open Sans; Roboto Mono | OFL-1.1 | caratteri |
| arduino:zephyr; Arduino_RouterBridge | Apache-2.0; MPL-2.0 | firmware |

L'elenco definitivo, con le versioni, sta in `docs/strumenti-e-licenze.md` e nelle attribuzioni della guida.

---

## 24. Piano

| Fase | Date | Contenuto | Uscita |
|---|---|---|---|
| Specifica | mar 29/9 | questo documento | approvazione |
| M1 | mer 30/9 – gio 1/10 | repository, licenze, `house.json`, simulatore, motore di regole e vincoli, webapp (casa, simulazione, regole, eventi, comandi, identità), firmware e client della MCU provati su casa1, audio e suoni, musica del party | `v0.1` |
| M2 | gio 1/10 – sab 3/10 | visione sulla casa 1 montata: camera, calibrazione, casa vuota, tracciamento, trasporto a mano, identità, diretta col bagno sfocato; citofono, voce libera, modello linguistico; clima, party, grigliata, garage | `v0.2` |
| M3 | dom 4/10 – lun 5/10 | hotspot, avvio automatico, guardie, diagnostica, impostazioni, cartello; installazione da zero su casa 2 (montata lunedì 5); prestazioni; collaudo | `v0.9` |
| M4 | mar 6/10 | guida IT/EN, schermate, schema dei collegamenti, attribuzioni, release | `v1.0` |
| Consegna | mer 7/10 | | |

Diario, decisioni e licenze si aggiornano a ogni passo.

### Cose da ricordarti a tempo debito
- Link ai modelli dei personaggi e dell'auto (D15, D126): prima della guida, M4.
- Nomi esatti dei prodotti per la distinta (D126): M4.
- Modello della ventola (D14), lunghezza dei cavi Qwiic-dupont (D18): M2.
- Foto delle case finite (D123): dopo il collaudo, M4.

---

## 25. Verifiche da fare sulla scheda (rischi aperti)

| Rischio | Prova | Criterio | Piano B |
|---|---|---|---|
| Campo visivo della C270 | foto di un metro a nastro a distanza nota, in 16:9 e in 4:3 | la base intera nell'inquadratura dal palo | 4:3; ritaglio adattato |
| Latch Relay a 0x02 | scansione e comando | commuta | indirizzo 0x10 |
| Indirizzo dell'Hub | scansione 0x70-0x77 | trovato | – |
| Corrente dei Pixels | tutte bianche al limite per 10 minuti | nessun blocco del bus | abbassare budget |
| Audio USB | 30 minuti di voce e musica | nessuna interruzione | guardia che riapre |
| Hotspot con rete di casa | access point e client insieme | entrambi funzionano | solo hotspot |
| Motore vocale libero | 20 frasi IT e EN | < 1,5 s per 5 s di parlato, errori accettabili | Vosk libero |
| Modello linguistico | 20 domande | risposta < 8 s, intento giusto ≥ 90 % | solo percorso rapido |
| YOLOX sulle foto dei personaggi | foto dei personaggi veri | categoria giusta nella maggior parte | chiedere la categoria |
| Personaggi uguali | due dello stesso colore spostati a mano | identità conservate o richiesta di conferma | – |
