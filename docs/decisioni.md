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
**Perché:** la libreria ufficiale, su UNO Q, rende indistinguibili i moduli assenti da quelli presenti e non limita l'attesa delle transazioni.

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

### D-20 — Niente si muove da solo; domande a voce senza tasto e racconto degli eventi (4/10)
**Scelta:** la visione accetta una presenza nuova solo dove una mano ha appena lavorato, quando la mano è uscita da 0,6 secondi e la cosa è stabile da un secondo. Una differenza dalla casa vuota senza mano intorno entra nella casa vuota dopo circa 3 secondi; fa eccezione una cosa ben visibile comparsa entro 20 secondi da una mano. Una "mano" ferma per 8 secondi è un oggetto sul bordo. Ogni domanda della casa si ascolta senza il tasto Parla e intanto compare sui telefoni: vale la prima risposta. Per ogni cosa nuova la casa chiede subito chi è, accettando anche un nome nuovo. Un narratore dice chi entra, esce o cambia stanza.
**Perché:** con la casa montata la visione vedeva presenze che non c'erano: il braccio diventava molte persone e animali, i riflessi delle luci diventavano oggetti, i moduli sciolti sul vialetto diventavano animali. In un plastico però ogni cambiamento lo fa una mano, e la regola elimina tutti questi casi senza abbassare la sensibilità; anzi, ha permesso di renderla più alta, quanto serve per vedere una statuina marrone scuro sul pavimento grigio con la luce del laboratorio. Il prezzo è un'attesa di circa 1,5 secondi tra la mano che si toglie e la presenza annunciata. C'è anche un rischio: una cosa cambiata senza che la casa veda la mano finisce nella casa vuota. Lo limitano la "mano ferma" di 8 secondi e la regola dei 20 secondi. Le domande senza tasto e il racconto sono richieste di Emilio: alla fiera nessuno sa che per rispondere va tenuto premuto Parla.

### D-21 — "Chi è?" capisce qualsiasi risposta: regole, poi il modello linguistico locale (4/10)
**Scelta:** la domanda su un nuovo arrivato dice che cosa sembra alla casa ("vedo una persona nuova, giusto?"). A una persona chiede il nome; per animali, auto e oggetti propone solo i registrati dello stesso tipo. La risposta può essere qualsiasi frase, e la casa la capisce in due passi. Prima delle regole riconoscono all'istante le risposte brevi e comuni: un nome, il tipo, sì e no, "non c'è nessuno", "non lo so", un comando della casa. Il resto va a Qwen2.5-0.5B, lo stesso modello dei comandi, che ha solo il compito di dire che tipo di risposta è, con l'uscita vincolata da una grammatica. Il tipo e i nomi registrati la casa li legge nella frase, e un nome proposto dal modello conta solo se è nella frase. Le istruzioni di questo compito stanno in un secondo slot di llama-server (`-np 2`, contesto 4096). Un nome già presente e visibile in un'altra stanza vuol dire che il nuovo arrivato non c'era.
**Perché:** Emilio vuole che alla fiera si possa rispondere come viene, anche "non c'è nessuno in giardino", e che la casa risponda di conseguenza. Il modello piccolo da solo sbagliava circa un terzo delle frasi difficili ("macché persona, è il mio cane Fido" → persona). Con le regole davanti e il controllo sulla frase, su 113 risposte di prova (79 scritte per tararle, 34 nuove) la casa le capisce tutte, e solo circa una su dodici arriva al modello. Sulla scheda il modello impiega da 3 a 6 secondi, per questo resta l'ultima risorsa. Con un solo slot le istruzioni dei comandi e quelle delle risposte si sarebbero scacciate a vicenda dalla cache, e rileggerle costa minuti.

### D-22 — Presenza sicura prima di chiedere; la luce della sala seguita senza perdere niente (4/10)
**Scelta:** oltre a D-20:
- nasce solo ciò che è diverso dalla casa vuota da quando la mano è arrivata, compatto (al massimo 3,5 volte più lungo che largo) e ben staccato dal pavimento;
- prima di mostrarlo e chiederne il nome, doppio controllo: la sicurezza (vista quasi sempre, ferma, contrasto, forma) supera l'80% due volte a un secondo di distanza, il 92% nelle stanze dove si è appena detto che non c'era nessuno;
- una cosa sconosciuta che salta o lampeggia più volte al secondo senza mani è un riflesso;
- ciò che sembra una statuina non entra mai nella casa vuota;
- un personaggio sdraiato o sul letto è riconosciuto anche con colori meno simili, se molto più vicino a lui che agli altri;
- la webcam si riregola da sola quando l'immagine resta molto più buia o più chiara della casa vuota, senza toccare calibrazione, casa vuota e presenze.
**Perché:** le prove di Emilio con la casa montata mostravano ancora presenze inesistenti: domande su persone in bagno e animali in soggiorno, una dopo l'altra. Una registrazione di 90 secondi, riprodotta sul PC con le firme vere, ha mostrato le cause:
- strisce di luce ai piedi delle pareti e sul bordo del divano;
- l'estremità della lampada del soggiorno, poco fuori dalla sua zona esclusa;
- soprattutto Viola: sdraiata sul letto e non riconosciuta, era entrata nella casa vuota, e quando la mano l'ha tolta il letto vuoto è sembrato una persona nuova.

Con le nuove regole la stessa registrazione dà zero domande inutili, e tutti e quattro i personaggi sono riconosciuti e seguiti in ogni spostamento. Il prezzo è circa un secondo in più prima che un nuovo arrivato venga annunciato.

### D-23 — La luce del locale tecnico è la matrice LED della UNO Q (4/10)
**Scelta:** il locale tecnico, dove la UNO Q è appesa alla parete, ha come luce la matrice di 13 × 8 LED della scheda. Per Linux è la luce 5, comandata come le altre: effetti, luminosità, festa, luci che seguono le persone. La matrice ha un solo colore e 8 livelli di luminosità, quindi il colore richiesto si vede sul LED RGB della scheda accanto a lei (LED3, regolabile), che segue lo stesso effetto.
**Perché:** lo ha chiesto Emilio: la stanza era l'unica interna senza luce, e la matrice è già lì, senza un modulo in più né cavi. La vede anche la webcam, per questo la scheda è tra le zone escluse dall'analisi.

### D-24 — Nomi stabili, posizioni ferme, storico e pose imparate sulla scheda (4/10)
**Scelta:**
- **Niente si muove da solo, nemmeno sulla mappa.** Senza una mano recente una traccia non salta oltre 30 mm e la posizione di un personaggio fermo non cambia.
- **Un nome non salta.** Non passa da una traccia all'altra finché chi lo tiene non smette di somigliargli per otto fotogrammi; il riconoscimento con colori meno vicini vale solo nei primi 10 secondi di una traccia nuova.
- **Conta la dimensione.** L'auto non è mai una statuina, né una statuina l'auto.
- **Storico.** Ogni personaggio ha il suo ultimo posto e il segno se una mano ci è passata: prima di chiedere di una cosa nuova, chi stava lì senza essere toccato riprende il suo nome.
- **Pose.** Ogni personaggio impara sulla scheda fino a sei pose (colori, dimensione, forma) mentre la casa è sicura di lui, e subito quando qualcuno dice chi è.
- **Mani che posano.** La sola cosa nuova lasciata dalle mani è il personaggio che tenevano; un pezzo di macchia accanto a un personaggio, del suo colore, è suo.

**Perché:** le prove di Emilio della sera hanno mostrato:
- Viola che saltava tra cucina e giardino mentre era in bagno contro Rosaria: il suo nome, rimasto libero, finiva su macchie lontane;
- Mister Braun salutato quando l'ha messo sul letto (sdraiato era più lungo della soglia di forma);
- "Mister Blu" scambiato per la Honda Civic, blu anche lei.

Nella registrazione delle 15:31, poi, due tracce si scambiavano di posto senza nessuna mano. Con queste regole la registrazione dà zero domande e i quattro personaggi sono seguiti e riconosciuti in ogni spostamento. Le pose sono la forma di apprendimento sul posto che la scheda regge senza un modello neurale: confrontare con le pose note costa una frazione di millisecondo per macchia, mentre una rete per le immagini avrebbe chiesto dati etichettati e un processore più libero.
