# Decisioni tecniche

Ogni decisione ha la data, il contesto, la scelta e il motivo. Quando una decisione cambia, la voce vecchia resta e se ne aggiunge una nuova.

---

### D-01 — Servizi nativi invece di un'app App Lab (28/9)
**Scelta:** l'applicazione gira come servizio systemd in un ambiente Python sulla scheda; il firmware della MCU si compila e si carica dalla scheda con `arduino-cli`.
**Perché:** su UNO Q App Lab non ha riconoscimento né sintesi vocale offline; le app girano in Docker, scaricano le dipendenze al primo avvio e non ripartono da sole se si bloccano. L'approccio nativo è già collaudato su questa scheda da Amelie 2.0.

### D-02 — Linux decide, la MCU esegue (28/9)
**Scelta:** stato, regole e priorità stanno su Linux. La MCU gestisce i Modulino, disegna gli effetti di luce (party compreso), legge tasti e sensori, protegge relè e alimentazione.
**Perché:** il collegamento fra i due lati porta 256 byte a messaggio e circa 7 ms per chiamata. Un'animazione a 30 immagini al secondo non ci passa; un comando "effetto X in stanza Y" sì.

### D-03 — I2C scritto a mano (28/9)
**Scelta:** nessuna libreria Modulino nello sketch. Ogni transazione ha un'attesa limitata e un esito verificato.
**Perché:** la libreria ufficiale, su UNO Q, rende indistinguibili i moduli assenti da quelli presenti e può bloccare la MCU per sempre se il sensore di distanza non risponde.

### D-04 — Limite di corrente sui Pixels (28/9)
**Scelta:** il firmware stima la corrente di ogni fotogramma e riduce le luci oltre 450 mA totali; luminosità massima iniziale 30 %.
**Perché:** cinque Pixels a bianco pieno arriverebbero a circa 1,3 A sul 3,3 V del Qwiic (connettore da 1 A, regolatore da 2 A condiviso). Senza un misuratore di corrente i valori restano prudenti.

### D-05 — Riconoscimento senza addestramento (28/9)
**Scelta:** differenza dalla casa vuota in Lab, colore, dimensione, parallasse, tracciamento con abbinamento ungherese; un rilevatore pre-addestrato (YOLOX-Nano, Apache-2.0) solo per stimare la categoria di un oggetto nuovo.
**Perché:** i personaggi sono piccoli (circa 11 pixel di base a risoluzione di rete), il numero di identità non ha limiti e si aggiungono dal vivo. Il metodo classico registra un personaggio in secondi e sta in un core.

### D-06 — Identità di personaggi dello stesso colore (29/9)
**Scelta:** l'identità segue il personaggio anche mentre una mano lo sposta ("trasporto a mano"); quando l'abbinamento è ambiguo la casa chiede conferma sulla webapp e a voce.
**Perché:** due personaggi possono avere lo stesso colore; il colore da solo non basta, la continuità del movimento sì, e dove non basta nemmeno quella si chiede.

### D-07 — Voce (29/9)
**Scelta:** Vosk (modelli piccoli IT ed EN) a frasi chiuse per nomi e sì/no; un motore per frasi libere; Qwen2.5-0.5B tramite llama.cpp traduce le frasi libere in un intento vincolato in JSON; la risposta la compone il codice dai dati veri; Piper come programma separato per parlare.
**Perché:** le frasi libere si capiscono solo con un modello linguistico, ma un modello così piccolo può sbagliare: fargli scegliere cosa fare e mai cosa dire elimina le risposte inventate.

### D-08 — Licenza MIT per il software (29/9)
**Scelta:** codice sotto MIT, tutto il resto sotto CC-BY-4.0. Piper (GPL-3.0) si usa come programma esterno, in un ambiente separato, senza importarlo.
**Perché:** scelta dell'autore. Un programma esterno chiamato da riga di comando è aggregazione, non opera derivata: il codice resta MIT senza ambiguità.

### D-09 — Un solo Buttons (29/9)
**Scelta:** tre tasti: parla, citofono, lingua. Party, grigliata e scenari da voce e webapp.
**Perché:** con un solo Buttons non serve cambiare indirizzi, la catena del canale 6 si accorcia e il totem si semplifica.

### D-10 — Rete senza captive portal (28/9)
**Scelta:** hotspot WPA2 a 2,4 GHz per casa, sottoreti diverse (10.42.1.0/24 e 10.42.2.0/24), nomi `casaN.lan` e `casaN.local`, QR su cartello A4.
**Perché:** la finestra di accesso dei captive portal non permette la fotocamera e su iPhone si chiude cambiando app; l'indirizzo numerico funziona sempre.

### D-11 — Core della MCU (29/9)
**Scelta:** `arduino:zephyr` 0.52.0 e `Arduino_RouterBridge` 0.4.3.
**Perché:** versioni collaudate sulla stessa scheda; dalla 0.55 cambia il modo di avvio dello sketch e va verificato che riparta dopo una mancanza di corrente prima di adottarlo.

### D-12 — Libreria ALSA da backports (29/9)
**Scelta:** `libasound2t64`, `libasound2-data`, `libatopology2t64` da trixie-backports, come già i profili audio.
**Perché:** l'immagine preferisce i profili audio da backports; la loro versione attuale richiede la libreria di backports e senza di essa l'aggiornamento di sistema si ferma.

### D-13 — Core 1.0.0 in modalità Immediate (29/9, sostituisce D-11)
**Scelta:** `arduino:zephyr` 1.0.0 con `wait_linux_boot=no`, `Arduino_RouterBridge` 0.4.3.
**Perché:** l'aggiornamento di sistema installa la 1.0.0; tornare alla 0.52.0 vorrebbe dire combattere l'aggiornatore a ogni aggiornamento. La modalità Immediate fa partire lo sketch all'accensione, così il relè a ritenuta si spegne subito dopo un blackout. Da verificare con una vera interruzione di corrente sulla casa montata.

### D-14 — Visione in un processo separato (29/9)
**Scelta:** camera, elaborazione e tracciamento in un processo figlio dell'applicazione, collegato da una pipe.
**Perché:** un'immagine lenta non deve rallentare la webapp o la voce, e un errore del driver della camera non deve fermare la casa: il processo riparte da solo.

### D-15 — Correzione della luce per canale e per stanza (29/9)
**Scelta:** guadagno per ogni canale RGB di ogni stanza, stimato sul pavimento libero, con isteresi e con l'avviso della casa quando cambia una luce.
**Perché:** le luci colorate delle stanze cambiano i colori in modo diverso su pavimento grigio e arredi bianchi; un guadagno per canale è il modello giusto per una luce che moltiplica, e la stima sul pavimento libero non si lascia ingannare da un oggetto grande.

### D-16 — Esposizione bloccata con margine (29/9)
**Scelta:** "Regola di nuovo" lascia trovare alla camera esposizione e bilanciamento sulla casa vuota, poi li blocca con l'esposizione ridotta del 25 %.
**Perché:** un canale saturo non porta informazione; con il margine il pavimento sotto le luci della casa accese non satura.

### D-17 — Reset del microcontrollore dopo un riavvio di Linux (29/9)
**Scelta:** se il router risponde ma lo sketch no per qualche secondo, la casa resetta il microcontrollore dalla linea di reset (GPIO 38 del gpiochip1, la stessa che usa il servizio del router quando si ferma); al massimo tre volte, a un minuto di distanza.
**Perché:** con la modalità Immediate (D-13) lo sketch parte all'accensione, e dopo un riavvio di Linux parte prima che il nuovo router sia in ascolto: la registrazione dei suoi metodi va persa e la libreria aspetta per sempre la risposta. Tornare alla modalità predefinita toglierebbe la sicurezza del relè dopo un blackout; un secondo reset con il router pronto risolve senza toccare i servizi di sistema.

### D-18 — Benvenuto ai telefoni e domande in modalità chiacchierona (30/9)
**Scelta:** la casa saluta a voce ogni telefono che apre la webapp per la prima volta, ne chiede il nome e invita a entrare con un personaggio; in modalità chiacchierona fa di tanto in tanto una domanda a un personaggio con un nome, adatta alla stanza in cui si trova. In tutti e due i casi ascolta la risposta da sola, senza il tasto Parla. Le risposte si confrontano con poche parole attese e le reazioni sono frasi scritte, non generate dal modello linguistico; le proposte (festa, barbecue, cinema, luce) si eseguono solo dopo un sì chiaro.
**Perché:** richiesta di Emilio per rendere la casa più viva con i visitatori. Il modello linguistico della scheda sceglie solo tra comandi e scrive a 6 parole al secondo: una reazione generata sarebbe lenta e imprevedibile. Una risposta in chiacchierata passata al riconoscimento dei comandi farebbe danni ("mi piace la musica" farebbe partire la festa). In fiera arrivano gruppi con decine di telefoni: un saluto a voce ogni 45 secondi al massimo, i nomi scritti ringraziati insieme, e i telefoni dimenticati dopo 7 giorni come gli eventi. Due revisioni hanno portato altre regole: **Parla** e il citofono interrompono il saluto o la domanda (prima venivano ignorati, e la casa prendeva il comando del visitatore per un nome o una risposta); i nomi scritti sui telefoni non vengono mai letti ad alta voce (una casella per il nome permetterebbe di far dire alla casa qualunque cosa); le domande si fanno solo se ci sono segni di visitatori negli ultimi 5 minuti e si fermano dopo due senza risposta; una risposta sentita mentre la casa parlava si scarta; di quello che il microfono sente senza Parla si registra solo l'esito, e il testo riconosciuto non va più ai telefoni. La prima revisione aveva anche trovato che i nomi scritti dai visitatori finivano dentro le frasi da formattare (con `str.format` un nome come `{name:>999999999}` avrebbe costruito una frase di un gigabyte, anche con i nomi dei personaggi già esistenti): ora le frasi sostituiscono solo i segnaposto esatti e i nomi non possono contenere parentesi graffe.

### D-19 — Storie generate da un database di pezzi, non da un modello linguistico (30/9)
**Scelta:** storie, ricordi, risposte sulla vita di casa e frasi generate della modalità chiacchierona si compongono combinando i pezzi di `data/stories.json`, scritti a mano in italiano e in inglese e compatibili con qualunque nome (generazione procedurale). Anche le personalità vengono dal database e restano fino al riavvio; le informazioni date dallo staff vengono prima. Il secondo modello linguistico e il suo servizio `domotiq-story` sono stati tolti; il modello dei comandi resta com'era.
**Perché:** la prima versione faceva scrivere storie e risposte a un secondo modello sulla scheda. Le misure sulla UNO Q (quattro Cortex-A53 senza le istruzioni per il prodotto scalare, llama.cpp, quantizzazione a 4 bit):

| Modello | Italiano | Lettura (token/s) | Scrittura (token/s) |
|---|---|---|---|
| Qwen2.5-0.5B (quello dei comandi) | inutilizzabile | 8 | 5,3 |
| Qwen3.5-0.8B | povero anche con esempi nelle istruzioni | 5,7 | 2,6 |
| Qwen3.5-2B | migliore, con qualche errore di grammatica (l'inglese è buono) | 2,3 | 1,3 |

Con il 2B una storia di cinque frasi richiede minuti, più 3-4 minuti la prima volta per leggere le istruzioni. Le storie si potevano scrivere in anticipo mentre nessuno chiede niente, ma una domanda libera no: la casa doveva promettere la risposta "tra un paio di minuti". Con lo 0.8B i tempi andavano, l'italiano no (concordanze sbagliate, frasi senza senso). Emilio ha scelto di costruire le storie da un database di situazioni, luoghi, momenti, eventi e relazioni, combinati in modo generativo. Così le frasi sono corrette nelle due lingue, le risposte sono immediate e la coerenza la garantisce il codice: personalità e fatti inventati restano in memoria come riferimenti ai pezzi, quindi valgono uguali in italiano e in inglese. Il prezzo è la varietà: poche centinaia di pezzi danno milioni di combinazioni, ma dopo molte storie lo stile si riconosce.
