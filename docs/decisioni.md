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

### D-25 — I nomi si muovono solo con le mani; pose del colore giusto; allarmi su presenze certe (4/10)
**Scelta:**
- **Nomi.** Senza una mano recente, un personaggio con un nome lo tiene finché gli somiglia; un nome non va mai a una macchia lontana più di 5 cm dall'ultimo posto del personaggio, se nessuna mano è passata di lì o l'ha preso.
- **Pose.** Una posa deve avere i colori del personaggio registrato (distanza fino a 0,45) più che di chiunque altro (di almeno 0,05). Le pose che non lo rispettano si dimenticano all'avvio. Colori e dimensione registrati imparano solo da macchie che somigliano da vicino; una risposta data sulla macchia sbagliata dà il nome ma non cambia l'aspetto del personaggio.
- **Avvio.** La casa aspetta che le luci stiano ferme, poi prende solo personaggi che somigliano da vicino e hanno la forma di una statuina. Una presenza seguita meno di 2,5 s è rumore, anche con un nome.
- **Allarmi.** Contano solo un personaggio noto o una cosa sconosciuta ferma e ben visibile da 6 s.
- **Tutti e due.** Due statuine a contatto sono una macchia: "tutti e due" (o due nomi) le segna presenti entrambe, una nascosta dietro l'altra.
- **Velocità.** Il confronto con tutte le pose di tutti i personaggi è un solo calcolo per immagine, e la luce delle stanze si rimisura al massimo ogni 0,3 s dopo un cambio.
- La zona esclusa della scheda UNO Q copre la scheda vera, che sporge di 2 cm dalla parete.

**Perché:** dopo le prove della sera Emilio vedeva personaggi muoversi da soli sulla mappa e falsi allarmi nel locale tecnico e in bagno. Sulla scheda, con 8 presenze, un'immagine costava 445 ms (2,3 al secondo): a quel ritmo funzionano male anche le regole che contano le immagini. Il nome di Viola era sulla scheda UNO Q, e Viola aveva imparato come pose un grigio, un nero e il marrone di Mister Braun. All'avvio, a casa vuota, l'alone delle lampade e il modulo dei tasti diventavano personaggi. Dopo le correzioni: tra 100 e 120 ms per immagine, con il riconoscimento sotto i 3 ms; a casa vuota, dopo un riavvio, nessuna presenza. La registrazione delle 15:31 dà ancora zero domande, con i quattro personaggi seguiti.

### D-26 — Niente staff e niente PIN (4/10)
**Scelta:** tutte le pagine e tutte le API sono aperte a chiunque usi la webapp: calibrazione, dataset, diagnostica, impostazioni (Wi-Fi compreso), backup, cestino, riavvio e spegnimento. Restano il registro delle modifiche, il cestino di 24 ore e la conferma prima delle azioni che non si annullano. Niente PIN all'installazione, niente `--pin` e niente `admin pin`. Le API dello staff (`/api/staff/...`) diventano `/api/...`.
**Perché:** lo ha chiesto Emilio. Il prezzo: un visitatore collegato al Wi-Fi della casa può anche ricalibrare la webcam, cambiare la password del Wi-Fi o spegnere la scheda. Per questo quelle azioni chiedono conferma.

### D-27 — Allarme inseribile come un antifurto; webapp uniforme (4/10)
**Scelta:**
- **Allarme.** Si inserisce e si disinserisce dalla pagina della casa o dalla notifica rossa (`/api/commands/alarm`). Disinserito, le regole d'allarme non scattano e quelle in corso si spengono con le loro luci; reinserito, chi è già in un posto sorvegliato viene notato di nuovo. Lo stato resta dopo un riavvio.
- **Webapp.** Ogni pagina comincia con titolo, una riga e l'azione principale; il menu Altro ha tre gruppi (la casa, messa a punto, stand). Le notifiche hanno un colore per tipo: rosso allarme, ambra avviso, grigio connessione, scheda bianca per le domande. Sulla piantina la stanza è rossa per un allarme e ambra per un avviso.

**Perché:** richieste di Emilio, per poter spegnere l'allarme come si fa con un antifurto e per una webapp più pulita, in cui allarmi, avvisi e domande si distinguono a colpo d'occhio.

### D-28 — Le proposte della casa diventano comandi (4/10)
**Scelta:** le proposte della modalità chiacchierona ("Ti va un po' di musica?", "Accendo il barbecue?") e quelle per chi è in tanti ("Siete in tanti in soggiorno: facciamo festa?") si ascoltano senza tasto e si capiscono in `voice/offers.py`.
- Regole veloci riconoscono sì, no, non so, oppure un altro comando della casa detto nella risposta.
- Solo quando le regole non decidono, il modello linguistico dice sì, no o altro, con una grammatica che non gli permette altro. Le sue istruzioni stanno in un terzo slot di `llama-server` (`-np 3`, contesto 6144).
- Un sì esegue la proposta; un altro comando esegue quello. Se la risposta non è chiara la casa richiede una volta, e per 30 secondi la proposta si può accettare anche con Parla.
- Corretto anche il controllo del vocabolario del riconoscimento vocale: le parole con l'accento ("sì", "perché", "macché") venivano tolte da tutte le grammatiche, comprese quelle del citofono e di "chi è?".

**Perché:** lo ha chiesto Emilio, e le proposte di fatto non partivano. Le cause erano tre:
- "sì" non arrivava mai alla grammatica e veniva capito solo a metà;
- le risposte naturali venivano ridotte alle parole della grammatica, o scartate perché più lunghe di cinque parole;
- le proposte per chi è in tanti non si ascoltavano affatto.

Su risposte sintetizzate con tre voci per lingua, l'interpretazione passa dal 56 all'88% in italiano e dal 58 al 92% in inglese, senza azioni sbagliate. Le frasi dette vicino alla casa che non sono risposte fanno partire qualcosa come prima: 2 su 495, le stesse.

### D-29 — Le risposte sui personaggi diventano informazioni (4/10)
**Scelta:** una risposta della modalità chiacchierona che dice qualcosa di duraturo su un personaggio diventa una sua informazione (`voice/facts.py`). È scritta come si direbbe dopo il nome, nella lingua della conversazione, e si legge anche nell'altra; la webapp la mostra in *Chi è*. Ogni domanda tiene una riga sola, che una risposta nuova sostituisce.

Alle domande su quello che sa ("Cosa mangia Rossellina?", "Cosa posso cucinare a Rossellina?", "What does Rossellina like to eat?"):
- le parole chiave delle due lingue dicono l'argomento della domanda e di ogni informazione;
- quando non bastano, il modello linguistico sceglie l'argomento tra quelli possibili, con una grammatica;
- la risposta è l'informazione stessa dopo il nome; se di quell'argomento non sa niente, la casa lo dice.

**Perché:** richiesta di Emilio, che voleva il modello linguistico per rispondere al meglio. Su 164 domande di prova (6 personaggi, in italiano e in inglese, 34 senza risposta salvata) questo metodo ne sbaglia una sola, e le altre mancate sono un onesto "non lo so". Usato in altri modi, il modello andava molto peggio:
- scegliere l'informazione per numero: dal 18 al 48% di risposte giuste;
- scrivere la risposta: dal 43 al 62%, con informazioni inventate e aggettivi accordati al personaggio ("è golosa").

Le risposte salvate restano sul disco della scheda (`identities.json`) e chiunque può correggerle o cancellarle nella webapp. Le risposte sulla vita di casa (bollette, spesa, faccende) restano solo in memoria fino al riavvio, come prima.

### D-30 — Tolleranza per pixel; la firma a piena risoluzione provata e lasciata (4/10)
**Scelta:**
- **Tolleranza per pixel.** Il tremolio di ogni pixel si impara con la casa vuota, si salva in `noise.npy` e si aggiorna piano. Una macchia trovata con le soglie fisse conta solo se da qualche parte supera di 5 volte il tremolio dei suoi pixel (almeno un blocco di 3×3), e allora conta intera.
- **Colori più veloci.** L'istogramma dei colori di una macchia si conta in un modo sei volte più veloce, con gli stessi risultati.
- **Firma a piena risoluzione non adottata.** È stata costruita e misurata, poi lasciata da parte.

**Perché:** scelte di Emilio tra le proposte, ma la firma a piena risoluzione non serve:
- la C270 registra il colore già a circa 640×480 (filtro dei colori del sensore e compressione MJPEG), quindi l'immagine piena non aggiunge colore;
- sulle prove sintetiche la distanza tra colori simili non è migliorata e il riconoscimento è rimasto uguale;
- sulla scheda costava 35 ms in più per immagine con 10 statuine, contro i 5 previsti.

Viola e Mister Blu si confondono perché i loro colori medi distano 5,6 punti, mezza casella dell'istogramma: è una questione di caselle, non di pixel. La tolleranza per pixel non cambia niente con la luce del laboratorio, dove il tremolio sta sotto le soglie fisse. Con un'immagine due o tre volte più rumorosa toglie dal 60 al 95% delle macchie di tremolio, senza perdere statuine e senza domande in più, per circa 2,5 ms per immagine. Il conteggio più veloce fa risparmiare da 7 a 9 ms per immagine con 10 statuine.

### D-31 — Presenze da togliere, auto solo in garage, contatori in tempo reale (4/10)
**Scelta:**
- **Togliere una presenza.** Dalla sua scheda, **Non c'è davvero: togli** la toglie dalla casa e la visione la dimentica: anche il posto del suo nome, così il personaggio vero non resta legato a quel punto. La stanza diventa più severa per due minuti.
- **L'auto sta in garage.** Fuori dal garage la casa chiede di un'auto, o di qualcosa grande come un'auto, solo se ne è certa: ferma e ben visibile da 10 secondi.
- **Stanza più severa.** La stanza in cui si è detto "non c'è nessuno", o dove si è scartato un riflesso, ora diventa davvero più severa: due funzioni con lo stesso nome lo impedivano dall'inizio.
- **Contatori.** La casa aggiorna i conteggi prima di avvisare i telefoni, e la pagina della casa ridisegna una parte solo quando cambia. I numeri della piantina contano le persone, come la scheda.
- **Ricarica automatica.** Dopo un aggiornamento della casa i telefoni si ricaricano da soli.
- **Ritocchi chiesti da Emilio:** l'allarme in fondo alla pagina della casa, temperature in °C e umidità scritta per esteso, il tabellone fuori dal menu, niente scala nelle Informazioni, niente riga sul bagno nella diretta.

**Perché:** richieste di Emilio. I contatori erano sempre indietro di un cambio, fin dalla prima versione: i telefoni ricevevano i conteggi di prima. Con la pagina ridisegnata cinque volte al secondo, 13 tocchi su 20 andavano persi. Il telefono di Emilio mostrava ancora il menu vecchio perché non si era ricaricato dopo l'aggiornamento.

### D-32 — Revisione: rifiuti, frasi su chi risponde, richieste con un nome (5/10)
**Scelta:** il lavoro del 4/10 è stato rivisto con frasi e situazioni vere, e ogni problema trovato è stato riprodotto prima di correggerlo:
- **Proposte.** Un sì non vale più se la proposta stessa è rifiutata ("sì, ma niente musica", "dai, non accendere il barbecue", "please don't light the barbecue"). "Not a good idea", "don't do it", "let's go home" sono no; "odio la musica" e "spegni la tv" (al film) anche. Una frase che nomina la proposta senza chiederla ("ieri abbiamo fatto festa", "la musica è troppo alta") non la esegue più: la valuta il modello. Un complimento con una parola di assenso ("you're great") non è un sì. "Spegni tutte le luci" spegne tutta la casa, non solo la stanza della proposta. Con **Parla**, nei 30 secondi dopo una proposta, una domanda ("c'è qualcuno in cucina?") non viene più presa per la risposta. Prima che il modello sia pronto non gli si chiede niente.
- **Informazioni sui personaggi.** Niente informazioni da frasi su chi risponde: "sono italiana" diventava "viene da Italiana", "sono vegetariano" "adora mangiare vegetariano". Una scelta o un colore negati non si salvano al contrario ("non la pizza, la pasta" è la pasta; "non mi piace il rosso" non è un colore). I nomi dei personaggi (Bianca, Viola, Celeste) non fanno di un'informazione una risposta sui colori; "fa il tifo per la Juve" e "è un amante della musica" non sono lavori; "viene spesso a trovarci" e "la cucina italiana" non dicono da dove viene; "grande" non è famiglia. Una richiesta che nomina un personaggio resta una richiesta ("Marco vuole sentire la musica", "musica per Marco"), e "Marco è sul divano?" chiede dov'è adesso. Quando il modello trova l'argomento ma non c'è un'informazione, la casa dice che non lo sa invece di rispondere a un'altra domanda, e non chiede al modello due volte la stessa cosa. Il modello etichetta un'informazione scritta solo se è sicuro almeno al 90%. Una riga scritta nella webapp come "viene da una famiglia di musicisti" resta com'è e non viene tradotta.
- **Tutti e due.** "Non è Viola, è Rosaria" è Rosaria; "né Viola né Rosaria" e "non sono tutti e due" non danno nessun nome.
- **Visione.** Un file del rumore vuoto (corrente staccata mentre si salvava) non blocca più la visione, e il file si scrive a parte e poi si rinomina. Dopo una nuova regolazione della webcam il rumore si reimpara anche dopo un riavvio. Il controllo dei salti dell'auto guarda davvero gli ultimi 10 secondi: ne vedeva solo 1,5.
- **Webapp.** Lasciando la Diretta la sua immagine si chiude davvero: prima restava aperta, nascosta, a 5 immagini al secondo, una in più a ogni visita. I tocchi su **Personaggi** non si perdono più. Se la presenza da togliere è già sparita compare "Non c'è più". **Impostazioni** non scorre più di lato a 320 px.
- **Documenti** allineati: guide rapide, installazione, specifica, collaudo, regole, README.

**Perché:** due problemi erano gravi: con una parola di assenso nella frase la casa accendeva il barbecue anche a chi diceva di non farlo. Ogni correzione ha un test.

### D-33 — Il modello pronto in pochi secondi (5/10)
**Scelta:**
- `llama-server` passa a quattro slot (`-np 4`, contesto 8192): anche le domande sui personaggi hanno uno slot loro.
- Dopo la prima lettura ogni slot si salva in `/var/lib/domotiq-llm` (`--slot-save-path`), e agli avvii successivi torna in cache da lì. Si rilegge solo se cambiano le istruzioni o il modello.
- La lettura parte insieme alla preparazione delle frasi della voce, non dopo; e se `llama-server` riparte, la casa rimette le istruzioni da sola.

**Perché:** domanda di Emilio sull'attesa di 10 minuti. Misurato sulla scheda all'accensione del 4/10: 11 s per caricare il modello, poi quasi 4 minuti di attesa mentre la voce preparava le sue frasi, poi 174 s per le istruzioni dei comandi (1.525 token) e 110 s per quelle di "chi è?" (1.073 token), a circa 9 token al secondo. Con le quattro istruzioni (5.458 token) sarebbero stati circa 14 minuti. Anche dopo un semplice riavvio dell'app il modello risultava pronto solo dopo la voce, 2-4 minuti più tardi, pur avendo già tutto in cache. Sul PC il ripristino dei quattro slot richiede circa 10 ms l'uno e le risposte sono identiche a quelle della prima lettura; i file occupano 67 MB. Su casa1 la prima lettura ha richiesto 730 s (324 s per i comandi, letti mentre la voce preparava le frasi); dopo un riavvio di `llama-server` le quattro istruzioni sono tornate in 3,2 s, e una domanda costa come prima circa 3 s.

### D-34 — Un nome non sta mai in due posti; l'auto non è un'ipotesi fuori dal garage (5/10)
**Scelta:**
- Prima di un dubbio o di una domanda, i candidati perdono chi è già riconosciuto da un'altra parte della casa (salvo una mano passata dov'era), chi è stato visto per l'ultima volta lontano senza una mano passata di lì e l'auto, se la presenza è fuori dal garage e la casa non è certa che sia un'auto (grande come un'auto, ferma e ben visibile da 10 s).
- Se resta un solo candidato la casa decide da sola; se il dubbio si scioglie mentre la domanda è aperta, la domanda viene ritirata dai telefoni e la casa smette di ascoltare.
- Il posto di un nome su cui la casa è in dubbio non vale più come "ultimo posto" di quel personaggio.

**Perché:** richiesta di Emilio. Nei log delle 11:39–11:46: "In camera c'è Viola o Honda Civic o Mister Blu?" e "In giardino c'è Honda Civic o Mister Blu?" (l'auto proposta per una statuina, anche dopo "Honda Civic ora è in garage"), e "In soggiorno c'è Rossellina o Rosaria?" con Rossellina in cucina. I candidati si calcolavano su tutti i personaggi di colore simile, anche quelli già riconosciuti altrove; per l'auto il limite di grandezza lasciava passare le macchie tra 2500 e 6000 mm². Senza l'ultimo punto, due gemelli spostati insieme si davano a vicenda il "posto" e il dubbio si scioglieva a caso.

### D-35 — Chi è, deciso dalla webapp; un elemento non riconosciuto si indica (5/10)
**Scelta:**
- Sulla scheda di una presenza e nelle domande della casa si sceglie chi è fra tutti i personaggi e gli oggetti noti, o si scrive un nome nuovo. Un nome già noto si sposta lì da dov'era.
- Scelto dalla webapp, l'aspetto di quella presenza diventa una posa del personaggio anche se diverso dal solito (distanza di colore fino a 0,6 invece di 0,45, senza il controllo di somiglianza con gli altri), segnata come "insegnata" e tenuta anche dopo un riavvio. Una risposta a voce resta prudente.
- **Elemento non riconosciuto**: toccando un punto della piantina o dell'immagine, la casa riprende lì (28 pixel di raggio, circa 3 cm) la casa vuota com'era salvata, annulla i "non c'è niente" detti lì, fa una presenza di quello che vede e non chiede chi è, perché lo chiede la webapp. In simulazione mette una statuina virtuale.

**Perché:** richiesta di Emilio: personaggi noti non riconosciuti, e un nome già usato non si poteva più dare; un elemento nuovo non sempre visto. Una statuina comparsa senza una mano viene presa per luce ed entra nella casa vuota: riprendere la casa vuota salvata solo intorno al punto indicato la fa ricomparire senza toccare il resto.

### D-36 — Chi suona al citofono è il primo che entra (5/10)
**Scelta:** dopo il campanello, la prima statuina che compare entro 3 minuti sul vialetto o in una stanza della casa (non in garage) prende il nome detto, qualunque tipo le abbia dato la webcam e anche se la casa le aveva dato un nome di cui non era sicura; la casa non chiede chi è. Un nome nuovo diventa una persona. Non contano le statuine già in casa prima del campanello, né una riconosciuta con certezza come qualcun altro.

**Perché:** alle 11:41 Emilio si è presentato al citofono ("Piacere, Emilio! Entra dalla porta.") e la casa ha chiesto "Mi sembra di vedere un oggetto nuovo in soggiorno: è così?". La regola accettava solo statuine di tipo persona, solo in soggiorno, entro 60 secondi e senza alcun nome: la webcam l'aveva presa per un oggetto.

### D-37 — Fai domande; le risposte che diventano azioni (5/10)
**Scelta:**
- **Fai una domanda** in **Comandi** (a un personaggio a caso tra quelli in casa) e sulla scheda di ogni personaggio (a lui, anche se non è in casa): una domanda subito, preferendo quelle a cui non ha ancora risposto, in qualsiasi stanza e modalità tranne quella silenziosa.
- Due domande nuove: "ti piace ballare?" e "ti piacciono le grigliate?".
- Le azioni: il colore preferito colora la luce della stanza in cui entra (scenario Normale; si spegne dalle impostazioni) e serve a "accendi la luce preferita di Marco", che lo chiede se non lo sa; a chi ama ballare la casa propone una festa quando è in soggiorno con qualcuno, a chi ama le grigliate il barbecue quando è in giardino, al massimo una proposta ogni 10 minuti per tipo, in modalità chiacchierona.

**Perché:** richiesta di Emilio, con le sue scelte: "a caso o a scelta" e "luce, festa, barbecue".

### D-38 — La luce della sala non blocca più la visione (5/10)
**Scelta:** la webcam si regola di nuovo quando l'immagine resta sotto il 70% o sopra il 143% della luce della casa vuota salvata (prima 55% e 180%, rispetto alla casa vuota del momento). "Mani" viste senza interruzione per 30 secondi non bloccano più la regolazione; se la luce è comunque vicina a quella della casa vuota, entrano nella casa vuota così come si vedono, tranne dove c'è un personaggio.

**Perché:** scelta di Emilio dopo le misure su casa1. Con la luce della stanza spenta l'immagine era al 45-57% della casa vuota: le pareti sembravano 5-13 "mani", la visione restava ferma a 3-4 immagini al secondo e non seguiva più gli spostamenti, perché la soglia del 55% non scattava e la regolazione aspettava comunque che non ci fossero mani. Gli scenari della casa portano l'immagine al 95-99%, quindi il 70% non li tocca. Sul PC il tempo per immagine non è cambiato (19,2-19,7 ms sulla registrazione delle 15:31).

### D-39 — Parola di attivazione; LED dei tasti (5/10)
**Scelta:**
- Da **Impostazioni → Voce** si accende e si sceglie una parola. Detta mentre la casa è libera, fa quello che fa il tasto Parla: "Dimmi, di cosa hai bisogno?", poi ascolta; se la richiesta segue la parola nella stessa frase ("Casa, che ore sono?") la casa risponde subito.
- La parola si confronta in parole: i numeri diventano parole nelle due lingue ("Casa 2" = "casa due", "House 21" = "house twenty one"); la webapp dice come verrà sentita e quali parole il riconoscimento non conosce.
- L'ascolto della parola cede il microfono a tutto il resto, e non parte mentre la casa parla, per 1,2 secondi dopo, durante conversazioni e domande, né in modalità silenziosa.
- I LED dei tasti lampeggiano mentre la casa ascolta, restano fissi mentre parla e respirano mentre pensa; mentre aspetta la parola restano come sempre.

**Perché:** richiesta di Emilio. Il microfono acceso mentre la casa aspetta la parola è scritto nella guida; l'audio non viene salvato. Una parola comune può svegliare la casa per sbaglio: la guida consiglia una parola rara.

### D-40 — I pezzi della versione 8 (5/10)
**Scelta:** in `hardware/stl` ci sono gli 84 file della versione 8, numerati da 01 a 59 nell'ordine di montaggio (muri uniti in 7 pezzi, totem con scocca, tre tasti e coperchio, staffe della scheda audio e fermacavi). Il capitolo 3 ha le tabelle nuove con il colore di stampa; la specifica descrive il totem nuovo. Le immagini del capitolo restano quelle della versione precedente, con una nota: `render_v8.py` non c'è ancora nella cartella del progetto.

**Perché:** indicazione di Emilio: per i pezzi da stampare fa fede la v8.

### D-41 — Un nome mai due volte, nemmeno nella casa (5/10)
**Scelta:**
- I nomi delle presenze li decide la visione. La casa non rimette più a una presenza il nome che aveva prima quando la visione la manda senza nome.
- Un nome dato dalla webapp, a voce o dal citofono resta sulla presenza per 3 secondi, finché la visione (un altro processo) non lo riceve, e in quei secondi sparisce da ogni altra presenza.
- Se due presenze arrivano con lo stesso nome, lo tiene quella in vista (non in mano, non nascosta).
- Un dubbio tra nomi tutti riconosciuti altrove non tiene più il nome dubbio come certo: la statuina diventa un nuovo arrivato e la casa chiede chi è.
- Un nome non va a una macchia più di quattro volte più grande o più piccola di tutte le pose di quel personaggio, e una statuina non è mai l'auto (né l'auto una statuina), anche nei dubbi tra due personaggi dello stesso colore.

**Perché:** Emilio ha visto di nuovo un personaggio già riconosciuto riconosciuto una seconda volta. Le cause trovate sono due:
- Dalla prima versione della casa, nata per la simulazione, una presenza mandata senza nome riprendeva il nome di prima. Quando la visione spostava un nome su un'altra presenza (una correzione dalla webapp, un nome perso dopo otto immagini diverse), il nome restava anche sulla prima.
- Un dubbio i cui candidati erano tutti già riconosciuti altrove si chiudeva lasciando il nome dubbio come certo.

Il dubbio "Honda Civic o Mister Blu?" veniva invece da due personaggi dello stesso colore confrontati senza la taglia.

### D-42 — Il racconto non si ripete (5/10)
**Scelta:**
- Per ogni personaggio la casa ricorda l'ultima cosa detta (stanza e mobile) e non la ripete per 10 minuti finché il personaggio resta lì.
- La visione dice che un personaggio è salito su un mobile dopo 5 immagini concordi (prima 3) e che ne è sceso dopo 15.

**Perché:** "Rossana è sul letto della camera" si ripeteva. Ogni volta che il bordo del letto o un'ombra facevano cambiare il mobile per 3 immagini, oppure la casa ritrovava il nome, il racconto ripartiva come per un arrivo.

### D-43 — I nomi prima di tutto; risposte sui personaggi immediate (5/10)
**Scelta:**
- **Le richieste sui personaggi vengono prima.** Con un nome nella frase, quelle sul personaggio (cosa sai di lui, cosa gli piace, dov'è, la sua luce preferita, "stanno insieme") passano davanti a quelle generali (com'è la casa, cosa sai fare, chi sei).
- **I nomi storpiati si ritrovano.** Un nome si ritrova se gli somiglia almeno all'82% o se ne contiene una parola tutta sua. Le parole comuni a molti nomi (*Mister*, *Signora*, i colori, le stanze) da sole non bastano.
- **"X e Y stanno insieme"** dice che una macchia è i due personaggi; con un nome solo la casa chiede chi è l'altro.
- **Le domande senza nome.** Per 90 secondi una domanda senza nome ("che lavoro fa?") riguarda l'ultimo personaggio nominato.
- **Le risposte alle sue domande.** Vale la parola dell'elenco solo se il riconoscimento libero la conferma o le somiglia, oppure se è molto sicura (almeno 0,8) e la risposta è corta. Altrimenti vale il riconoscimento libero, che capisce anche le risposte non previste.
- **Nessun modello nelle domande sui personaggi.** Le cerca, nell'ordine:
  - le parole chiave;
  - le parole in comune tra domanda e informazioni (le prime cinque lettere delle parole di almeno quattro);
  - quello che il personaggio ama;
  - le storie;
  - altrimenti "non lo so".
  Il modello resta solo per dare in sottofondo l'argomento alle informazioni scritte nella webapp.
- **Le informazioni scritte come frase intera** ("il suo piatto preferito è la carbonara") si dicono come sono, nella loro lingua. Anche il colore preferito si legge da una riga scritta nella webapp.
- **"Cosa sai di X?"** comincia da dove si trova.

**Perché:** richieste di Emilio:
- "Raccontami cosa piace a Rossellina" faceva partire la descrizione della casa.
- Le informazioni scritte nelle schede non venivano ritrovate.
- Le risposte non previste e quelle con due personaggi non erano capite.
- Le domande sui personaggi richiedevano secondi, mentre i comandi delle luci erano immediati. Ogni chiamata del modello costa da 3 a 10 secondi sulla scheda, e le domande sui personaggi ne facevano anche due.

### D-44 — La parola di attivazione sentita subito (5/10)
**Scelta:**
- **Ascolto continuo.** Mentre aspetta la parola, il microfono resta aperto per tratti di 60 secondi (prima 6). Il riconoscimento ristretto alla parola riceve l'audio ogni 100 ms e la casa ne guarda il risultato parziale.
- **LED e preascolto.** Appena il risultato parziale contiene la parola, la casa si prende il turno e i LED lampeggiano. Il riconoscimento libero parte dagli ultimi 2 secondi di audio e continua in diretta fino a una pausa di 0,9 secondi; se dopo la parola non viene detto niente, si ferma dopo 1,5 secondi e la casa chiede "Dimmi…".
- **Controllo.** Il riconoscimento libero deve ritrovare la parola; altrimenti la casa non risponde. Fa eccezione la parola detta da sola, sentita con una confidenza di almeno 0,6.
- **Una parola sola** dopo il nome è una richiesta solo se l'analizzatore la capisce.

**Perché:** richiesta di Emilio: i LED si accendevano tardi, e la frase detta subito dopo la parola non veniva quasi mai sentita (solo le richieste corte come "che ore sono"). Prima, ogni tratto di ascolto finiva alla prima pausa di 0,6 secondi, quindi bastava una breve pausa dopo la parola per perdere la richiesta. Poi tutto l'audio veniva riconosciuto di nuovo da capo, e i LED si accendevano solo dopo "Dimmi…". In più la confidenza usata per decidere era la media di tutte le parole, comprese quelle fuori dalla parola: una frase lunga detta subito dopo poteva abbassarla sotto la soglia.

### D-45 — Le frasi della voce restano su disco (5/10)
**Scelta:**
- Ogni frase sintetizzata da Piper si salva in `var/voice/` come il WAV ricevuto, con un nome ricavato dalla voce e dal testo.
- All'avvio le frasi frequenti si rileggono da lì, e a Piper si chiede solo una frase breve, per sapere che risponde.
- Si tengono al massimo 3000 frasi; si cancellano quelle non dette da più tempo.

**Perché:** richiesta di Emilio. A ogni avvio Piper preparava le frasi frequenti per circa 4 minuti, e intanto la visione scendeva a 3-4 immagini al secondo.

### D-46 — Durante la festa il riconoscimento aspetta (5/10)
**Scelta:**
- Dall'inizio della festa alla fine dello spettacolo di luci la visione non guarda le immagini: le presenze restano come sono e la diretta continua.
- Alla fine si misura di nuovo la luce delle stanze e ogni personaggio vale come toccato da una mano. Quello che si vede si riprende come all'avvio, appena le luci si fermano.
- Un nome può passare da una presenza nascosta, dove è passata una mano, a quella che lo porta altrove.

**Perché:** richiesta di Emilio: le luci colorate della festa confondono il riconoscimento.

### D-47 — Le immagini della guida dalla versione 8 (5/10)
**Scelta:** i 14 render di `render_v8.py` sono in `docs/images/render/`, senza i metadati delle immagini; i render della versione precedente sono tolti. Il capitolo 3 li usa nei passaggi del montaggio, con la pianta dall'alto, le pareti, le sezioni del totem, della fioriera e del palo e le viste dall'altezza di un adulto e di un bambino. La nota sulle immagini vecchie (D-40) non c'è più.

**Perché:** il render della versione 8 è pronto.

### D-48 — Le risposte alle domande sulla vita di casa (5/10)
**Scelta:**
- A una domanda della modalità chiacchierona sulla vita di casa (compleanno, bollette, assicurazioni, spesa, faccende, vacanze), una risposta che non è sì o no viene capita:
  - una domanda che nomina un argomento della vita di casa ("Chi ha pagato il gas?") ha la sua risposta;
  - un comando o una domanda per la casa ("che ore sono?") viene eseguito;
  - una domanda che continua il discorso ("Quando?", "Dove?", "Chi?") riguarda l'argomento appena detto ("Quando?" dopo il compleanno dà la data, la stessa che la casa dice dopo un no).
- Il resto riceve "Ah, interessante!" come prima.

**Perché:** segnalazione di Emilio: a "Viola, lo sai che manca poco al tuo compleanno?" la risposta "Quando?" riceveva "Ah, interessante!". Prima si capivano solo sì e no.

### D-49 — Regole dalle frasi sentite al banco; memoria delle risposte del modello (5/10)
**Scelta:**
- Dal registro di casa1 (dal 29/9: 128 frasi capite, 32 dal modello) le frasi finite al modello sono diventate regole, ciascuna con un test:
  - le parole della festa sentite male ("fai presto", "facciamo presto", "let's body");
  - "cosa posso chiederti" (aiuto);
  - l'elenco dei personaggi ("chi sono i personaggi che conosci");
  - "dov'è X" con un nome sconosciuto ("Non conosco nessuno che si chiama Emilio");
  - il nome detto a voce per una presenza ("l'ospite che in soggiorno si chiama Rosaria");
  - "e in bagno?" dopo una domanda su una stanza;
  - "Di chi?" a una domanda su un personaggio senza nome e senza un personaggio nominato poco prima;
  - "dove vuole andare X" come domanda sulle vacanze.
- Il modello non riceve due volte la stessa richiesta: le ultime 256 risposte restano in memoria (con temperatura 0 risponderebbe lo stesso), e a una frase già chiesta non si dice "Vediamo…".

**Perché:** intervento 1 della lista proposta a Emilio. Le frasi vere mostrano che il modello riceveva soprattutto frasi storpiate dal riconoscimento e domande che le regole non conoscevano; ognuna costava da 3 a 10 secondi.

### D-50 — Priorità tra i servizi (5/10)
**Scelta:**
- `domotiq` CPUWeight 200, `domotiq-tts` 150, `domotiq-llm` 50 (con il nice 10 che aveva già).
- Dentro `domotiq` il processo della visione si dà nice 5: cede il passo al riconoscimento vocale e alla parola di attivazione, che girano nel processo principale.
- Le unità vanno reinstallate sulla scheda.

**Perché:** intervento 2. Misurato su casa1 prima del cambio: mentre la casa sintetizzava e diceva una frase nuova, la visione scendeva da 10 a circa 3 immagini al secondo e il tempo per immagine passava da 220 a circa 450 ms. La voce deve rispondere subito; un'immagine in ritardo conta meno.

### D-51 — Due thread per il riconoscimento vocale (5/10)
**Scelta:** alle domande della casa l'audio va insieme al riconoscimento a elenco e a quello libero, su due thread. Il risultato libero è pronto alla fine della frase, invece di ripartire da capo dopo.

**Perché:** intervento 3. Prima il riconoscimento libero dello stesso audio partiva solo dopo quello a elenco, e la risposta non prevista ("direi di sì") aspettava il doppio.

### D-52 — La visione a riposo (5/10)
**Scelta:**
- Dopo 25 secondi senza mani, con le luci della casa ferme e niente in sospeso, un fotogramma uguale all'ultimo analizzato non viene analizzato di nuovo.
- Uguale vuol dire: nella miniatura 80 × 60 in grigi, nessun punto cambiato di più di 6 livelli.
- Almeno un fotogramma al secondo viene analizzato comunque.
- In Diagnostica si vede la quota dei fotogrammi lasciati stare.

**Perché:** intervento 4. Un fotogramma costa circa 180 ms sulla scheda (122 di segmentazione), il confronto una frazione di millisecondo. Una mano cambia la miniatura subito, e le nascite dopo una mano avvengono entro 20 secondi, quindi i 25 secondi non le toccano.

### D-53 — Le frasi fisse della voce preparate in anticipo (5/10)
**Scelta:**
- `scripts/voice_cache.py` prende dal codice le frasi fisse:
  - le frequenti;
  - le varianti senza spazi da riempire;
  - le risposte scritte nelle due lingue.
  In tutto sono 235. Le sintetizza nella stessa forma della cache della voce, in `models/voice-cache/`.
- La casa legge anche quella cartella; `release.sh` la copia dal PC alla scheda.
- La cartella è preparata sul PC con Piper 1.8.0 e le stesse voci verificate con `scripts/models.sha256`.

**Perché:** intervento 5. Sul PC le 235 frasi richiedono 50 secondi, sulla scheda circa 13 minuti di processore. Una casa nuova le dice subito dalla prima accensione.

### D-54 — La scheda grafica, provata (5/10)
**Scelta:** nessun uso della scheda grafica per ora.

**Misure su casa1 (Adreno 702, Mesa 26.1.6):**
- **Vulkan:** il driver Turnip offre Vulkan 1.0, mentre llama.cpp chiede 1.2 e rifiuta il dispositivo.
- **OpenCL:** Rusticl offre OpenCL 3.0 (1 unità di calcolo a 844 MHz, fp16). Il backend OpenCL di llama.cpp però supporta solo Adreno con il driver Qualcomm e Intel.
- **Prodotto di matrici in OpenCL scritto per la prova:**
  - circa 2,3 GFLOPS nella versione semplice;
  - 4,2-4,6 GFLOPS calcolando 16 risultati per thread (gruppi di lavoro al massimo di 16 elementi per i registri).
- **Processore, con la casa accesa:** 4,4-5,6 GFLOPS con un core e 8-10 con due (OpenBLAS); con quattro scende a 3,5-4,2, perché i core servono anche alla casa.

**Perché:** intervento 6. Usarla vorrebbe dire scrivere a mano i calcoli del modello per la scheda grafica, e renderebbero quanto un core del processore. La possibilità di far lavorare insieme processore e scheda grafica resta da valutare con Emilio, dopo l'eventuale accelerazione del modello sul processore.

### D-55 — I nomi sentiti da un riconoscimento che conosce solo loro; niente "Mmm" (5/10)
**Scelta:**
- **Un secondo riconoscimento.** Con Parla e con la parola di attivazione, sul secondo thread un riconoscimento ristretto ai nomi registrati (più "[unk]") ascolta lo stesso audio mentre il riconoscimento libero trascrive.
- **Quando si usa.** Solo se la frase libera non contiene nomi e le regole non la capiscono. Con "dove" o "cerca" diventa "dov'è" quel nome; altrimenti il nome si aggiunge alla frase e la frase si capisce di nuovo.
- **Niente "Mmm" né "Hmm".** Nessuna frase della casa li contiene più; un'interiezione fatta solo di m e h viene tolta prima della sintesi.

**Perché:** segnalazioni di Emilio:
- "Ambrogio, dov'è l'Honda Civic?" riceveva "Mmm, di questo non mi hanno detto niente...". Nel registro il riconoscimento libero aveva trascritto "dovevo music"; il modello vocale italiano conosce sia "honda" sia "civic", quindi l'elenco dei nomi le può sentire.
- Piper leggeva "Mmm" come "emme emme emme".

### D-56 — Dopo la parola di attivazione la casa risponde subito (5/10)
**Scelta:**
- **Mezzo secondo per continuare.** Se dopo la parola, entro 0,45 secondi, non segue niente di forte almeno quanto il 40% della parola, la casa dice subito una frase brevissima già in memoria ("Dimmi!", "Sì, dimmi!", "Eccomi!") e ascolta.
- **Niente attesa della conferma.** La conferma del riconoscimento libero non si aspetta più quando la parola è stata sentita con sicurezza (almeno 0,6).
- **LED continui.** I LED lampeggiano dalla parola alla risposta senza spegnersi.
- **Frase detta di seguito.** "Ambrogio, accendi la luce" detto di seguito resta una richiesta sola.

**Perché:** richiesta di Emilio. Prima la casa aspettava 1,5 secondi di silenzio, poi il risultato del riconoscimento libero, poi diceva "Dimmi, di cosa hai bisogno?", che dura circa due secondi. Chi chiamava la casa non sapeva quando parlare e ripeteva la domanda. Il confronto con il volume della parola distingue la sua coda, che si spegne, dalla frase che comincia.

### D-57 — Le istruzioni del modello scritte per il Cortex-A53; flash attention spenta (5/10)
**Scelta:**
- `scripts/llama/arm-nodot.patch` aggiunge a llama.cpp i prodotti scalari per i core ARMv8.0 con NEON e senza SDOT: Q5_0, Q8_0, Q4_K e Q6_K.
  - Prodotti sommati a 16 bit e allargati una volta.
  - Il quinto bit di Q5_0 caricato dalla tabella direttamente nei registri.
  - Le scale dei formati K applicate alle somme parziali.
  - Due righe per due colonne, anche con un numero dispari di parole.
- `install.sh` applica la patch al commit provato e ricompila quando la patch cambia.
- Il servizio `domotiq-llm` parte con `-fa off`. I file delle istruzioni salvate hanno un nome nuovo (`SLOTS_LAYOUT`), perché la memoria del contesto è disposta in un altro modo.
- Su processori con SDOT, I8MM o SVE llama.cpp resta com'era.

**Perché:** richiesta di Emilio, con miglioramenti da misurare. Misure su casa1 con la casa accesa (dettagli in `docs/accelerazione-modello.md`):
- **Moltiplicazioni di matrici del modello:**
  - da 1,07 a 1,40 volte con una parola;
  - da 1,23 a 2,01 volte con 17 o 64 parole.
  I risultati sono uguali entro gli arrotondamenti (verificati contro un riferimento in doppia precisione).
- **Modello intero** (llama-bench, le due librerie alternate): lettura 1,65 volte più veloce senza contesto e 1,34 volte con 1400 parole di contesto, scrittura con il contesto 1,20 volte. La scrittura senza contesto dipende soprattutto dalla memoria: con la casa accesa la differenza resta nel rumore della misura.
- **Richieste della casa con le frasi vere:** mediana da 3,41 a 2,18 secondi. Ogni parola letta passa da 223 a 146 ms, ogni parola scritta da 295 a 188 ms.
- **Prima lettura delle quattro istruzioni:** da 730 a 546 secondi.

La flash attention si è rivelata più lenta su questo processore quando il contesto è lungo, come le 1550 parole delle istruzioni dei comandi; il contesto a 32 bit è più lento ancora. Il modello è in gran parte Q5_0 e non Q4_K: la dimensione 896 non è multipla di 256.

### D-58 — Riconoscimento vocale: le frasi più probabili, i nomi che il modello non conosce, le frasi come le scrive Vosk (5/10)
**Scelta:**
- **Le frasi più probabili.** Per una richiesta libera (tasto Parla, o dopo "Dimmi!") Vosk tiene le 5 frasi più probabili. Se le regole non capiscono la prima, o vi trovano un nome che la casa non conosce, provano le altre. In questa modalità Vosk non dà la sicurezza parola per parola: la sicurezza della frase è quanto la migliore è più probabile delle altre. La frase detta insieme alla parola di attivazione resta com'era: è la stessa trascrizione che deve ritrovare la parola.
- **I nomi che il modello non conosce.** Prima un nome come "Rossellina" usciva in silenzio dagli elenchi di parole, perché il modello italiano non lo conosce, e il riconoscimento dei nomi non poteva sentirlo. Ora entra con una scrittura che il modello conosce: una doppia scritta singola ("rosellina"), o la parola divisa in due. Il risultato riporta il nome. Le scritture si calcolano all'avvio e quando cambiano i personaggi; alla registrazione l'avviso compare solo se non se ne trova nessuna. La parola di attivazione resta com'è, perché il riconoscimento libero la deve scrivere uguale.
- **L'elenco dei nomi.**
  - Un nome conta solo se lo sente intero: "honda", uscito da "oggi sono andato al mare", non è più l'Honda Civic.
  - L'elenco si consulta anche quando la frase chiede di un nome che la casa non conosce: "dov'è misteri" diventa Mister Green.
- **Le frasi come le scrive Vosk.** Le regole accettano:
  - "dove" per "dov'è" e "come" per "com'è";
  - "a nulla" per "annulla", "buon giorno", "buona notte", "cos'ha fatto";
  - "spegne" e "spendi la luce", "accende" e "accedi ... luce", "feste", "a basso volume";
  - una parola persa nel rumore: "chi in cucina", "ti c'è in camera da letto", "se qualcuno in giardino".
- "Quanti anni hai" non è più una domanda su quante persone ci sono.

**Perché:** richiesta di Emilio ("migliora anche il riconoscimento vocale del testo"). La misura usa `scripts/stt_bench.py`:
- le frasi della casa con i nomi di casa1: 83 in italiano e 24 in inglese, comprese 10 e 4 che non sono comandi;
- tre voci Piper per lingua, due velocità;
- tre condizioni: voce pulita; stanza simulata (riverbero 0,35 s, rumore a 18 dB, livello basso); lontano (riverbero 0,6 s, rumore a 9 dB);
- 1926 registrazioni in tutto, ascoltate con il codice della casa.

Il risultato conta quante volte la casa capisce la stessa cosa che capirebbe dalla frase scritta (senza il contesto della conversazione e senza il modello linguistico):

| | Prima | Ora |
|---|---|---|
| Italiano, voce pulita | 82,3% | 90,8% |
| Italiano, stanza | 50,2% | 61,6% |
| Italiano, lontano | 21,5% | 24,9% |
| Italiano, frasi con i nomi (tutte le condizioni) | 43,4% | 49,4% |
| Italiano, frasi che non sono comandi prese per un comando | 13,3% | 5,6% |
| Inglese, voce pulita / stanza / lontano | 86,1 / 75,0 / 49,3% | 88,9 / 84,0 / 60,4% |
| Inglese, frasi che non sono comandi prese per un comando | 8,3% | 4,2% |

Con la voce pulita gli errori in italiano scendono da 17,7% a 9,2%. Le voci sintetiche e la stanza simulata non sono il pubblico di una fiera: i valori assoluti dal vivo saranno diversi, il confronto tra prima e ora vale.

**Scartati, dopo le stesse misure:**
- **Un secondo riconoscimento con il solo vocabolario della casa**, usato quando la frase non vuol dire niente. Capiva qualche comando in più, ma prendeva per comandi il 28% delle frasi che non lo sono.
- **Una soglia di sicurezza sui nomi dell'elenco.** Toglieva più nomi giusti che comandi sbagliati.

### D-59 — Le prove al banco del 5 e 6/10: climatizzatore a voce, informazioni dette così, il narratore e la voce della casa (6/10)
**Scelta:** dai registri di casa1 (frasi sentite e decisioni). Le frasi dette dalla casa sono state ricostruite trascrivendo l'audio che la casa tiene sul disco.
- **Climatizzatore e riscaldamento a voce.** "Accendi il condizionatore" accendeva le luci e diceva "Fatto."; "condizionatore" da solo riceveva "Questa proprio non la so". Ora un'intenzione `climate` (condizionatore, climatizzatore, clima, aria condizionata, riscaldamento, termosifoni, stufa) fa quello che fa il termostato: un'onda azzurra (o arancione) in tutte le stanze per due minuti, "Accendo il climatizzatore."; "spegni" la ferma, anche quella del termostato.
- **Informazioni dette così come sono.** "Il colore preferito di Mister Blu è l'azzurro" era preso per una domanda ("questo non lo so ancora"). Ora "il/la ... (preferito) di NOME è ..." e "NAME's favourite ... is ..." diventano informazioni del personaggio, se parlano di qualcosa che le informazioni dicono (un argomento) o di un preferito. Il colore prende il posto della risposta a "qual è il tuo colore preferito?", il lavoro si scrive "fa il pompiere". Con "?", con due nomi o con un'altra domanda resta una domanda.
- **Il narratore.** Ieri sera "Mister Brown, scendi dalla fioriera" e "a presto, Mister Brown" si sono sentiti ogni minuto per un quarto d'ora: le statuine sul vialetto comparivano e sparivano al bordo dell'inquadratura. Ora la stessa frase sullo stesso personaggio non si ripete per dieci minuti, se nel frattempo non è passato da una stanza a un'altra.
- **La voce della casa non è una risposta.** Due volte la casa ha sentito la propria voce mentre aspettava una risposta ("rossellina ora in giardino guarda chi c'è nel locale tecnico mister blu", "per favore"): una frase del narratore, partita poco prima, suonava dopo la domanda. Ora il microfono scarta quello che sente mentre la casa parla (e 0,35 s dopo), e una domanda aspetta che finisca la frase già partita.
- **Il dialogo sul nuovo arrivato.** Un discorso fatto vicino alla casa ("si sta allenando per migliorare la velocità del modello") è stato preso per "è un'auto": il modello linguistico aveva detto "kind car" con 0,54. Ora il tipo che dice il modello conta solo se la frase lo nomina. Se due nuovi arrivati di fila non ricevono nessuna risposta, per tre minuti la casa li chiede solo sui telefoni: ieri sera le domande sono state 25 in tre ore, quasi tutte senza risposta.
- **Altro:**
  - "Com'è la casa?" diceva "7 persone" e ne nominava 5: ora aggiunge "e altre 2 persone";
  - una o due parole che le regole non capiscono e che il modello giudica "altro" ("domani") ricevono "Non ho capito", non una risposta inventata;
  - "ristorante" è una domanda sul cibo ("se devo andare al ristorante con Rossellina");
  - la parola di un nome sentita da sola ("brown" in "le misure brown") non conta più come colore;
  - il registro di sistema riporta anche le frasi dette dalla casa (`said`);
  - l'ora impostata vale finché la scheda resta accesa (`var/config/clock.json` con l'identificativo dell'avvio della scheda): dopo il riavvio dell'applicazione la casa chiedeva di nuovo "Non so che ore sono";
  - dentro una stanza la casa non chiede mai di "un'auto nuova" (dopo il riavvio l'aveva chiesto per la camera): la chiama "un oggetto".

**Perché:** richiesta di Emilio ("ricontrolla gli ultimi log di frasi dette e ricevute e sistema le frasi"). Ogni caso ha un test in `tests/test_exchanges.py`.

### D-60 — I personaggi fermi sulla piantina: si spostano solo con una mano vicina (6/10)
**Scelta:**
- **Solo con una mano vicina.** La posizione di una statuina sulla piantina cambia, anche di un millimetro, solo se una mano è entro 5 cm da lei (`HAND_NEAR_MM`, cercata nei pixel della mano) o la sta portando. Prima bastava una mano in qualsiasi punto della casa, o un cambio di luce, perché tutte le statuine seguissero la propria macchia.
- **La mediana dopo la mano.** Quando la mano se ne va (dopo 0,6 s), il posto diventa la mediana delle prime 10 posizioni viste (`SETTLE_FRAMES`) e resta fisso. Il mobile su cui sta (letto, fioriera) si decide insieme, contando quello visto più volte in quelle immagini; senza una mano non cambia. Lo stesso vale per una statuina appena comparsa.
- **Le presenze durante la regolazione della webcam.** Mentre la webcam si regola (circa 9 s senza immagini) il processo della visione lo dice, e la casa tiene le presenze dove sono; prima le toglieva dopo 2 s.
- **Le regolazioni inutili si diradano.** Una regolazione che non riporta l'immagine vicina alla casa vuota fa aspettare il doppio alla successiva, fino a 15 minuti.

**Perché:** richiesta di Emilio. Nel database delle posizioni di casa1 (un campione al secondo) per la sera del 5/10:
- **Tutti sparivano ogni 70 s.** Tutte le presenze sparivano insieme per 8-9 s, proprio durante le regolazioni della webcam ("the light of the hall changed", sempre con gli stessi valori: esposizione 625, guadagno 64). Il narratore salutava tutti e poi li riaccoglieva.
- **Le posizioni saltavano.** Il centro della macchia di Viola, in cucina, saltava tra x = 47 e x = 62 mm, quello di Mister Green, sul vialetto vicino alla fioriera, di 30 mm, e la piantina li seguiva.

**Quante immagini.** `scripts/settle_bench.py` su quattro registrazioni di casa1 (10 minuti a 9 immagini al secondo e tre più brevi), 21 periodi di quiete: distanza tra la mediana delle prime N immagini dopo la mano e il posto in cui la statuina resta poi ferma.

| N | mediana | 90% | 95% | massimo |
|---|---|---|---|---|
| 1 | 0,9 mm | 22 mm | 121 mm | 150 mm |
| 3 | 0,6 mm | 19 mm | 22 mm | 121 mm |
| 5 | 0,5 mm | 1,9 mm | 2,9 mm | 11 mm |
| 8 | 0,4 mm | 1,1 mm | 2,1 mm | 6,4 mm |
| **10** | **0,3 mm** | **0,9 mm** | **1,5 mm** | **2,0 mm** |
| 15 | 0,2 mm | 0,7 mm | 0,9 mm | 1,3 mm |

Le prime immagini dopo la mano possono essere molto storte (l'ombra del braccio, la statuina che oscilla). Con 10 la mediana le scarta tutte e l'errore non supera mai 2 mm, a fronte di una statuina larga 20-30 mm. Oltre, il guadagno è sotto il millimetro e il posto arriva più tardi. Le immagini vengono analizzate comunque, quindi il costo di calcolo è nullo: conta solo il tempo, circa 1,1 s a 9 immagini al secondo.

**Risultato** (le stesse registrazioni, prima e dopo):
- **Spostamenti senza una mano vicina.** Nella registrazione lunga sono scesi da 338 a 41 mm, e quelli rimasti cadono tutti nel secondo in cui il posto si fissa; nella breve da 117 a 51 mm. Le statuine col posto già fissato si sono mosse in tutto di 1,5 mm in 10 minuti.
- **Riconoscimento.** Chi è riconosciuto, dove e quando è identico a prima.

### D-61 — Scenari che si riconoscono a colpo d'occhio; le luci della webapp senza tasti (6/10)
**Scelta:**
- **Ogni scenario ha un aspetto suo anche a casa vuota.**
  - **Normale:** le luci seguono le persone.
  - **Cinema:** il bagliore azzurro e tremolante di uno schermo in soggiorno (effetto *Scintille*), il resto spento.
  - **Relax:** un caminetto in soggiorno (*Fuoco*) e una luce arancione che respira in camera.
  - **Notte:** una lucina arancione all'8% in bagno.
  - **Via:** una stanza alla volta si accende per 15-30 secondi, come se in casa ci fosse qualcuno (`simulate` in `scenes.py`, `House._simulate_presence`). La regola dell'intruso resta.
- **Le luci della webapp senza tasti.** Spariscono **Accendi**, **Spegni** e **Automatico**: ogni scelta arriva subito alla casa.
  - Un colore accende la luce.
  - Due cerchi in più fra i colori: **A** restituisce la stanza alla casa, il cerchio barrato la spegne.
  - Effetto e luminosità cambiano la luce già accesa; la luminosità arriva dopo 250 ms di pausa.
  - Scegliendo una stanza i controlli mostrano com'è la sua luce in quel momento.

**Perché:** richiesta di Emilio. Prima, senza statuine in casa, Normale, Relax, Notte e Via erano tutti spenti, e Cinema si distingueva solo per una luce blu tenue.

### D-62 — Quando non sa, la casa chiede e impara; su sé stessa immagina (6/10)
**Scelta:**
- **Sui personaggi.** Alla domanda su un personaggio a cui le sue informazioni non rispondono, la casa dice che non lo sa e chiede "Tu lo sai?", poi ascolta senza Parla.
  - La risposta diventa un'informazione scritta in base all'argomento della domanda (`facts.learned_line`). Esempi: "ama il gelato" per le cose che ama, "ascolta il rock" per la musica, "viene da Napoli" per la provenienza, "fa la maestra" per il lavoro.
  - Cibo, provenienza e colore usano le stesse frasi delle domande della modalità chiacchierona, così una risposta nuova prende il posto della vecchia.
  - Una risposta senza un argomento delle informazioni resta com'è, legata al personaggio, in `var/config/knowledge.json`.
- **Sul mondo.** Una domanda libera a cui niente risponde (il meteo, una curiosità) segue lo stesso schema e va nello stesso archivio. Due domande sono la stessa se condividono metà delle parole che contano, oppure se parlano entrambe del meteo. Quello che riguarda oggi o domani vale un giorno.
- **Su sé stessa.** Per le stanze, i mobili o "tu" la casa inventa una spiegazione plausibile, introdotta da "Penso che…", la tiene e la ripete uguale. Il tono dipende dalla domanda: perché, chi, quando, dove, quanto, come.
- **Cosa non insegna niente.** "Non lo so", "boh", il silenzio o un comando non insegnano niente. Una risposta sentita con meno del 50% di sicurezza non viene tenuta.
- **Una frase sentita male recupera l'argomento.** "Cosa ama Rossellina" era stato sentito "cosa ma rossellino": le regole lo avevano preso per "dov'è Rossellina", poi per una domanda su Rossellina senza argomento. Ora, quando la lettura della frase migliore è così debole, la casa prova le altre frasi probabili e prende quella che dice di più sullo stesso personaggio.

**Perché:** richiesta di Emilio. "Ambrogio, cosa ama Rossellina?" aveva avuto come risposta "Di Rossellina questo non lo so ancora", mentre la casa sapeva che ama i cartoni animati della Disney e ballare: la parola "ama" era stata sentita "ma". In più, per tutto quello che non sapeva, la casa non imparava niente.

### D-63 — Le domande sul mondo: la casa chiede se aspettare la sua risposta o sentirla dal visitatore (6/10)
**Scelta:**
- **La domanda.** Per una domanda che non riguarda la casa, i suoi personaggi o le sue funzioni, la casa dice subito che deve pensarci e chiede: "Preferisci aspettare qualche secondo, o me lo dici tu?".
- **Aspettare.** "Aspetto", "sì", "pensaci tu" o il silenzio fanno scrivere la risposta da zero a Qwen3.5-0.8B (Apache-2.0). Gira in un secondo llama-server (`domotiq-chat`, porta 8082, un posto, 3 thread, priorità bassa) con istruzioni in inglese e due esempi in italiano. Campionamento: temperatura 0,3, top-k 20, top-p 0,85, penalità di ripetizione 1,15, al massimo 90 token. Il testo viene pulito: niente pensieri, simboli o emoji, al massimo tre frasi intere.
- **La risposta dell'utente.** "Te lo dico io", oppure la risposta stessa, la fanno tenere.
- **Il resto.** "Lascia stare" o "non lo so" lasciano perdere; un comando viene eseguito.
- **Le volte successive.** La risposta, pensata o detta, va in `knowledge.json` e alla domanda uguale o simile arriva subito.
- **Due errori di ascolto corretti.** "Come si fa la pizza?" non fa più chiedere "Di chi?": "come si" e "si fa" chiedono come si fa una cosa, non chi la fa. "Ci sei?" e "chi se" valgono come "chi sei?".

**Perché:** richiesta di Emilio, che ha scelto di unire le due strade, aspettare il modello o insegnare. Le prove sulla scheda, a casa accesa, alle stesse domande:
- **Qwen2.5-0.5B (il modello dei comandi):** 7-25 s, ma frasi senza senso anche con istruzioni ed esempi ("Si toglie le tazze d'acqua e ci si lascia un po' di zucchero per farla salata").
- **Qwen3.5-0.8B:** 20-50 s, italiano sensato ma fatti spesso sbagliati (Leonardo "del XIII secolo").
- **Qwen3.5-2B:** non ci sta in memoria insieme al resto.

Un quinto posto nel server dei comandi avrebbe invalidato i quattro salvati: llama.cpp rifiuta lo stato salvato con un altro numero di posti (*n_stream mismatch*). Il modello da 0,8B occupa circa 700 MB in più.

### D-64 — Quello che qualcuno insegna vale più di quello che la casa ha pensato; le risposte si correggono (6/10)
**Scelta:**
- **Chi vince.** Fra le risposte imparate per una domanda, quella detta da qualcuno vince su quella pensata dal modello o immaginata dalla casa, anche se è più vecchia.
- **Insegnare sostituisce.** Una risposta detta da qualcuno prende il posto di tutte le risposte alla stessa domanda (o a una simile) sullo stesso personaggio, o su nessuno. Una risposta pensata prende il posto solo di quelle pensate o immaginate prima.
- **"Te lo dico io", anche più tardi.** "Te lo dico io come si fa la pizza" è una lezione, non una domanda nuova: la casa dice "Dimmi pure!", ascolta e tiene la risposta per "come si fa la pizza". Senza la domanda vale per l'ultima risposta che la casa ha dato da quello che ha imparato; se non ce n'è, la casa chiede "Su che cosa? Fammi prima la domanda.".
- **"Sbagliato".** Entro 3 minuti da una risposta presa da quello che ha imparato, "sbagliato", "hai sbagliato", "non è vero", "non è così" o "non è giusto" fanno chiedere "Scusa! Qual è la risposta giusta?". La risposta detta nella stessa frase ("non è vero, ci vuole acqua e farina") vale subito. Con altro detto in mezzo, o più tardi, "sbagliato" non corregge niente.
- **La casa ripete quello che ha imparato.** "Corretto! Se mi chiedono come si fa la pizza, risponderò: …". Lo stesso vale per una risposta insegnata quando la casa l'ha chiesta. Una parola sentita male si corregge subito con un altro "sbagliato".
- **Una parola o due non bastano.** "Pizza" o "la pizza" non ripetono più la risposta a "come si fa la pizza": servono almeno tre parole, o un argomento riconosciuto come il meteo ("domani piove?").
- **Domande diverse restano diverse.** "Dove si compra la pizza?" non è "come si fa la pizza?": quando le due domande cominciano con una parola diversa (come, dove, quando, chi, perché, quanto, quale, cosa), non sono la stessa domanda.
- **I nomi non contano come argomento.** Il nome di un personaggio non conta come argomento della domanda, nemmeno sentito un po' male ("rossellino").
- **La pagina "Cosa ha imparato".** Nella webapp, in **Altro**, c'è una pagina con tutte le risposte imparate. Per ognuna mostra la domanda, la risposta, se è stata detta, pensata o immaginata, e quando. Si possono correggere la risposta e la domanda sentita male ("come si fa la vita"), oppure cancellarle. Una risposta corretta diventa una risposta detta da qualcuno. Ogni modifica va nel registro delle modifiche. API: `GET /api/knowledge`, `PUT` e `DELETE /api/knowledge/{id}`.
- **Le informazioni dei personaggi.** Restano correggibili dalla loro scheda, come prima.

**Perché:** richiesta di Emilio ("risolvi il disastro"). Il registro di casa1 del pomeriggio del 6/10:
- **16:08.** "Come si fa la pizza?", la risposta pensata dal modello da 0,8B era senza senso ("C'è un po' di tempo per preparare le uova…"). È stata detta e tenuta.
- **16:10.** "La pizza" e poi "pizza", frammenti sentiti per caso, l'hanno fatta ripetere.
- **16:10:56.** "Lo dico io come si fa la pizza" è stata presa per una domanda nuova. La risposta giusta è finita sotto quella domanda, mentre quella sbagliata restava sotto "come si fa la pizza" e continuava a vincere perché più vicina alla domanda.
- **16:11:31.** Riprovando, "come si fa la vita" (sentito male) ha tenuto una terza risposta.

Emilio ha chiesto anche di poter correggere una risposta generata male.

### D-65 — Una parola di attivazione che il riconoscimento non conosce si ascolta con una grafia che conosce (6/10)
**Scelta:**
- **La grafia.** La parola di attivazione si ascolta con le parole che il modello conosce e suonano uguali, come già i nomi dei personaggi: *Domotiq* si ascolta come «domotica».
- **Le grafie provate.** Alle grafie di prima (lettere doppie scritte singole, parola divisa in due) si aggiungono quelle "come suona": *q*, *k* e *ck* come *c*, *w* come *v*, *y* come *i*, *x* come *s*, *j* come *i*, *ph* come *f*, *th* come *t*. Poi una vocale in fondo, se la parola finisce con una consonante, e la parola divisa in due.
- **La conferma.** Il riconoscimento libero non scrive mai una parola che non conosce. Per una parola ascoltata così vale la sua grafia, o una o più parole che suonano quasi uguali (lettere simili almeno al 70%: «domotiche», «domo tic»).
- **Detta da sola.** Anche la parola detta da sola si conferma con il riconoscimento libero, mentre una parola conosciuta come «Ambrogio» risponde subito come prima.
- **La webapp.** Dice come la casa sentirà la parola ("che il riconoscimento vocale non conosce e sente come «domotica»"). Avvisa solo per le parole senza nessuna grafia conosciuta.

**Perché:** Emilio ha messo *Domotiq* come parola di attivazione alle 17:00 e la casa non l'ha più sentita. Il modello italiano non conosce "domotiq", quindi Vosk la toglieva dalla grammatica, che restava vuota. La webapp lo aveva segnalato ("non conosce: domotiq"), ma la parola non poteva funzionare in nessun modo.

Misure sul PC, con il modello della scheda e le tre voci italiane di Piper a due velocità:
- **Le grafie possibili.** «domotica», «domotico» e «domo tic» svegliano tutte la casa 41 volte su 42. La conferma della parola detta da sola è decisiva. Senza, 10 frasi qualsiasi su 156 che finiscono come lei ("il cancello è automatico", "un film romantico") la svegliavano. Con la conferma nessuna, a parte "la domotica è il futuro", che contiene di fatto la parola.
- **"Ambrogio".** Nella stessa prova sveglia la casa 24 volte su 24 e con le frasi qualsiasi una volta su 156, come prima.

### D-66 — Quando cambia la luce della sala, i personaggi restano com'erano e la casa vuota si reimpara con la luce nuova (6/10)
**Scelta:**
- **Accorgersene.** La casa si accorge da sola di un cambio della luce della sala. I segnali:
  - la luminosità dell'immagine cambia di oltre il 12% in 2 secondi;
  - la luminosità resta per 3 secondi oltre il 15% lontana da quella in cui la casa vuota è stata imparata l'ultima volta;
  - gran parte della casa cambia senza mani;
  - le "mani" coprono oltre il 45% della casa e la luminosità è cambiata di almeno l'8% (un braccio vero la cambia appena: una mano vera presa per la luce verrebbe ignorata);
  - la luce va oltre quello che la correzione delle stanze segue;
  - la webcam viene regolata di nuovo.

  Non conta subito dopo un cambio delle luci della casa, né durante la ricerca dei personaggi all'avvio: lì la casa vuota non si può reimparare, perché vi entrerebbero personaggi non ancora trovati.
- **L'ultimo stato prima del cambio.** Da quel momento le presenze restano esattamente com'erano: stessi nomi, stessi posti, niente nasce, niente sparisce, nessun fotogramma viene guardato. Le prese in mano e le mani vicine degli ultimi 5 secondi erano la luce, e si annullano.
- **La luminosità.** Se l'immagine è fuori dal 70-143% della casa vuota, la webcam si regola subito, senza i 5 secondi senza mani. Se non si può regolare, la casa aspetta al massimo 3 secondi.
- **La mappa.** Quando la luminosità è ferma (entro il 2% per un secondo, almeno 2 secondi dopo il cambio), la casa vuota si reimpara dalla mediana degli ultimi 5 fotogrammi. I fotogrammi sono riportati alla luce in cui era stata salvata: la luce di ogni stanza viene misurata di nuovo su tutto il pavimento libero. Intorno a ogni presenza la casa vuota resta com'era. Un secondo dopo le presenze si ritrovano al loro posto, poi la casa riprende a guardare. Con una luce che non sta mai ferma, la casa vuota si reimpara comunque dopo 30 secondi.
- **Webcam coperta o sala troppo buia.** Un'immagine sotto un terzo della luminosità della casa vuota, o abbagliata, non si impara mai. Le presenze restano e la webapp avvisa: "La webcam vede quasi buio: la sala è troppo buia o la webcam è coperta. Accendi una luce; intanto i personaggi restano dove erano". Su casa1 alle 18:40-18:59, con la sala al buio, la webcam arrivava a 9-17 su 50 anche al guadagno massimo. Viola compariva e spariva in cinque stanze diverse, e tutti uscivano insieme.
- **Dopo il buio.** Se durante il cambio la webcam ha visto quasi buio, quando la luce torna la casa vuota non impara quello che spicca chiaramente (potrebbe essere una statuina posata al buio). Poi la casa riguarda cosa c'è, come dopo una festa: prende i personaggi che conosce bene, ovunque siano ora, e l'auto.
- **Webcam urtata.** Prima di imparare, la casa controlla che pareti e mobili siano dove li ha la casa vuota (lo stesso confronto dei bordi dell'avviso "la webcam si è spostata"). Se non ci sono, non impara niente: altrimenti terrebbe l'immagine sbagliata e non chiederebbe più di ricalibrare. Le presenze restano e l'avviso compare subito.
- **La fine della regolazione.** Le presenze tenute durante la regolazione della webcam restano fino al primo fotogramma.
- **Diagnostica.** Mostra quando la luce sta cambiando e quante volte la casa si è adattata.

**Perché:** richiesta di Emilio: quando cambia la luce la casa deve accorgersene e regolare da sola luminosità e mappa, tenendo l'ultimo stato salvato prima del cambio, per evitare false apparizioni o sparizioni dei personaggi dovute a ombre e luci diverse.

Il registro e il database delle posizioni di casa1 mostrano la sera del 6/10. Alle 17:45 la webcam si è regolata di nuovo, con il guadagno al massimo:
- **17:45:46.** Tutti e sette i personaggi sono usciti e rientrati nello stesso secondo. Alla fine dei 10 secondi di regolazione l'ultimo fotogramma era vecchio e la casa ha ricevuto per un istante un elenco vuoto.
- **17:46:16.** Trenta secondi dopo, le pareti illuminate diversamente dalla casa vuota, viste come "mani" ferme, sono entrate nella casa vuota. Intanto avevano "preso in mano" i personaggi: Mister Brown, Mister Green e Viola sono saltati in altre stanze, Rossellina e Giallo Galli sono usciti e ricomparsi altrove.
- **17:46:40-17:48:28.** Nel soggiorno sono nate una quindicina di auto e animali dove erano state le "mani".

Sulla casa sintetica, con la luce della sala che cala in modo disuguale (più buia da un lato) e la webcam regolata di nuovo:
- **Prima.** Compariva una presenza sconosciuta per 6 secondi; con un calo più forte, per 56 secondi, e la webcam non si regolava mai.
- **Ora.** Nessuna presenza cambia o nasce e la webcam viene chiesta subito. Vale anche per la sera che scende piano in un minuto e mezzo, mentre una mano dopo l'adattamento porta ancora le statuine.

### D-67 — Il buio si misura sull'immagine, e la casa vuota non si salva al buio (6/10)
**Scelta:**
- **Buio e abbagliamento.** Si giudicano sulla luminosità vera dell'immagine (grigio medio nella casa, 0-255), non sul confronto con la casa vuota salvata: sotto 25 la sala è troppo buia o la webcam è coperta, sopra 235 è abbagliata. Su casa1 con la luce della stanza accesa l'immagine sta a 55-65, al buio a 9-17.
- **Salvare la casa vuota al buio.** "Salva la casa vuota" e "Regola la luce e salva la casa vuota" rifiutano un'immagine sotto 25 con il messaggio "La casa è troppo buia per salvare la casa vuota: accendi la luce della sala e riprova." (e una abbagliata con un messaggio suo).
- **Una casa vuota già salvata al buio.** La casa si adatta lo stesso, non regola la webcam su di essa e avvisa: "La casa vuota è stata salvata al buio: togli le statuine e, con la luce accesa, rifai Calibrazione → Regola la luce e salva la casa vuota".

**Perché:** alle 21:00 del 6/10 la casa vuota è stata salvata con la stanza al buio (grigio medio 13). Quando la luce è tornata, l'immagine era 3,5 volte più chiara di quella casa vuota e l'adattamento di D-66 l'ha presa per una webcam abbagliata. Dalle 23:13 la casa ha aspettato senza imparare niente, con i personaggi fermi. Dalle 20:01 si erano accumulati 30 adattamenti e 16 regolazioni della webcam.

### D-68 — Una rete che conosce le statuine della casa dà un secondo parere (7/10)
**Scelta:**
- **La rete.** Una piccola rete convoluzionale, pesi nostri addestrati da zero sul PC con PyTorch: quattro blocchi, circa 200 mila pesi, ritagli di 48 × 48 pixel. Classi: gli 8 personaggi di casa1 più "niente". È esportata in ONNX e la usa l'onnxruntime già sulla scheda (`vision/figures.py`), circa 10 ms a ritaglio con un thread.
- **I dati.**
  - **La registrazione.** 10 minuti registrati sulla scheda il 7/10 alle 00:00. Prima con la luce della sala, poi con poca luce e una lampada laterale, poi con gli scenari della casa, poi con le ombre di chi sta vicino e con mani e cavi senza statuine. Le statuine sono state spostate in stanze e posizioni diverse, anche sdraiate e sui mobili.
  - **Il riquadro della macchia.** Ogni registrazione ora salva, per ogni personaggio, il riquadro della macchia a cui la casa l'ha abbinato. Le registrazioni vecchie davano solo il posto sulla piantina, che è fisso e visto dall'alto. Abbinandolo alla macchia più vicina, le etichette venivano sbagliate: un mobile preso per Mister Brown, Viola presa per "niente".
  - **"niente".** Sono le macchie di nessun personaggio, in fotogrammi in cui tutti i personaggi hanno il loro riquadro e senza un personaggio nello stesso punto entro 10 secondi: pareti con il riflesso delle luci della casa, moduli, bordi, prato.
  - **I numeri.** 7.635 ritagli; il bagno, sfocato nelle registrazioni, è escluso.
- **L'addestramento.**
  - Luce, contrasto, gamma, bilanciamento del bianco, ombre a gradiente, luci colorate, rotazione, sfocatura, rumore e compressione JPEG vengono variati.
  - Un primo modello ha trovato 29 etichette di cui era sicurissimo del contrario. Guardate una per una, aveva ragione lui (Giallo Galli sdraiato sul letto preso per "niente", Mister Blu preso per Viola): sono state tolte e il modello è stato addestrato di nuovo.
- **Nella casa, solo quando serve e disattivabile** (Impostazioni → Statuine riconosciute anche dalla rete):
  - **Macchie nuove.** Una macchia nuova che la rete vede come "niente" almeno al 90% non nasce. Non vale mentre si registra un personaggio nuovo, che la rete non conosce.
  - **Tenere il nome.** Un personaggio che non somiglia più ai suoi colori tiene il nome finché la rete lo vede almeno all'80%.
  - **Dare il nome.** Un nuovo arrivato prende il nome di un personaggio libero, invece della domanda "chi è?", quando la rete ne è sicura al 95% due volte di fila.
  - **Diagnostica.** Conta i tre casi.
- **I programmi.** Quelli per rifare tutto stanno in `scripts/figures/` (ritagli, anteprima, addestramento). La rete è un file per casa in `models/vision/`, non nel repository.

**Perché:** richiesta di Emilio, che ha scelto l'addestramento sul PC in locale e il collegamento già stanotte se i numeri fossero stati buoni. Gli esempi di visione di App Lab e i loro modelli pronti, misurati sulla scheda, non vedono le statuine dall'alto. YOLOX-Nano non trova niente sull'immagine intera, in 270-350 ms; MobileNetV2 chiama "lavastoviglie" un personaggio. Un modello piccolo come quello delle persone di App Lab (18 ms) dimostrava invece che una rete leggera è sostenibile.

I numeri sono misurati su un blocco di tempo della registrazione lasciato fuori dall'addestramento: 1.521 ritagli che la rete non ha mai visto.
- **Accuratezza:** 97,4%. Giallo Galli, Honda Civic, Mister Brown, Mister Green, Rossana e Rossellina al 100%, Viola all'88%, Mister Blu al 70% (si confondono tra loro, blu e viola), "niente" al 98%.
- **Quando è sicura:** almeno al 90% lo è sull'88% dei ritagli, e lì ha avuto ragione 1.338 volte su 1.338.
- **Le soglie:**
  - nessuna delle 1.313 statuine vere supera 0,84 di "niente", mentre l'80% dei "niente" veri supera 0,9;
  - a 0,95 i nomi dati sarebbero stati 972, nessuno sbagliato;
  - il 97% delle statuine vede il proprio nome almeno a 0,8.

### D-69 — Verso zero falsi positivi: controlli, consenso, registro della visione (7/10)
**Scelta:**
- **Il veto della rete anche in ritardo.** La rete guarda anche le statuine prese "in ritardo", cioè posate mentre la casa aspettava. Prima un falso positivo poteva entrare da lì.
- **Solo le macchie nuove.** Alla nascita la rete guarda solo le macchie che non coprono già una statuina seguita: prima classificava e "scartava" a ogni fotogramma anche le macchie delle statuine già note.
- **La casa vuota con statuine sopra.** "Salva la casa vuota" e "Regola la luce e salva la casa vuota" rifiutano se la casa vede ancora presenze: "Sulla casa vedo ancora: Viola. Toglile e riprova." La webapp chiede se salvare comunque, per qualcosa che non è una statuina.
- **Il consenso della rete.** È un interruttore, spento di serie. Una presenza nuova viene annunciata solo quando la rete vi ha visto una statuina due volte di fila, almeno al 50%. Non vale mentre si registra un personaggio, né senza la rete.
- **Il registro della visione (`var/journal`).**
  - **Cosa tiene:** ogni presenza nuova annunciata, ogni nome dato e ogni macchia scartata dalla rete, con un ritaglio di 96 pixel. Le ultime 600 voci, con la sfocatura di quello che sta fuori dalla casa (e del bagno, se attiva). Lo stesso nome o la stessa macchia scartata si scrivono una volta al minuto al massimo.
  - **La pagina:** Altro → Registro della visione permette di dire "giusto" o "era…" (un personaggio o "niente").
  - **Le etichette:** finiscono in `var/journal/labels.json` e `build_crops.py --journal` le aggiunge all'addestramento.
- **Il banco di prova (`scripts/vision_bench.py`).** Rigioca le registrazioni nella visione di oggi, con o senza rete e consenso, e confronta con quello che la casa aveva detto; con `--journal` salva i ritagli.
- **L'apertura dello stand.** Una lista di controllo nella guida rapida dello staff: luce, accensione, casa vuota, statuine posate a mano una alla volta, controllo.

**Perché:** richiesta di Emilio, che vuole un riconoscimento affidabile e senza falsi positivi.

La replica della registrazione del 7/10 con la rete accesa:
- **Le macchie scartate.** Sono 11 macchie distinte, tutte non-statuine: pareti, bordi di porte con il riflesso rosa dei LED, angoli di moduli, un pezzo di tappeto. Nessuna statuina vera è stata scartata.
- **Il confronto con la serata dal vivo.** La replica, che parte da zero senza i nomi confermati a mano e le pose imparate quella sera, dà nomi diversi da quelli dal vivo anche senza rete (Rossana e Rossellina, Mister Blu e Viola). Il confronto misura quindi una versione contro l'altra, non la verità.
- **Il consenso.** Resta spento finché non è stato provato con la luce dello stand.

### D-70 — Raccolta continua delle immagini e revisione del registro (7/10)
**Scelta:**
- **La raccolta continua (`var/collect`).** È un interruttore in Impostazioni, spento di serie, con lo spazio da dedicarle (500 MB di serie).
  - **Cosa tiene:** quello che vede la webcam, con l'esterno sfocato (e il bagno, se attivo), in cartelle di 10 minuti nel formato delle registrazioni: fotogrammi e `detections.jsonl` con il riquadro di ogni personaggio. Servono così come sono per i ritagli della rete.
  - **Quanto spesso:** un fotogramma ogni 5 secondi quando non succede niente, uno ogni mezzo secondo quando succede qualcosa (mani, luce che cambia, una presenza nuova o senza nome nel suo primo minuto, una statuina in mano, un dubbio).
  - **Lo spazio:** oltre lo spazio scelto si cancellano le cartelle più vecchie; *Diagnostica* mostra i MB usati.
- **Le macchie che toccano una statuina.** Alla nascita la rete guarda ogni macchia che non sia quasi la stessa di una statuina già seguita (sovrapposizione fino a 0,6). Prima bastava toccarne una per non passare dalla rete: l'angolo di una parete accanto a Mister Blu sdraiato era nato 14 volte.
- **Il veto anche dopo la nascita.** Una macchia nata, che la rete guardandola di nuovo prima dell'annuncio vede come "niente" almeno al 90%, non viene annunciata.
- **Il registro rivisto.** Le 103 voci del registro della visione del 7/10 sono state guardate una per una: 97 etichette, 69 "niente" e 28 personaggi, correggendo i nomi sbagliati della casa.

**Perché:** richiesta di Emilio: raccogliere di continuo quello che vede la webcam, entro uno spazio sulla scheda, per migliorare la rete delle statuine, e fare in autonomia il lavoro del registro della visione.

### D-71 — Un avvio con un'altra luce non impara più le statuine come casa vuota (7/10)
**Scelta:**
- **La ricerca all'avvio con la rete.** All'avvio la casa prende quello che la rete vede come un personaggio almeno all'80%, anche quando i colori, in un'altra luce, non sono quelli registrati. Prima prendeva solo quello che somigliava da vicino ai colori registrati.
- **All'avvio la rete ha l'ultima parola.** Con la rete, la ricerca dell'avvio non prende una macchia che la rete vede come "niente", anche se ha i colori di un personaggio. Alle 16:16, con la casa vuota, erano nati così Mister Green, Mister Brown e Viola: macchie della luce diversa da quella della casa vuota salvata.
- **Nessuna presenza nota, come dopo il buio.** Se la casa non conosce nessuna presenza quando reimpara la casa vuota in una luce nuova, fa come dopo il buio: quello che spicca (un altro colore, più scuro, o una statuina per la rete) non entra nella casa vuota, e la casa riguarda cosa c'è.
- **La rete guarda prima dell'annuncio.** Con la rete accesa, una presenza nuova viene annunciata solo dopo che la rete l'ha guardata (al più un fotogramma dopo). Prima una macchia riconosciuta subito dai colori poteva essere annunciata prima del suo parere.
- **"La mano ha lasciato qualcosa".** Quando una mano prende un personaggio e lascia qualcosa di nuovo, quel nome non va più a una macchia che la rete ha appena visto come "niente". Alle 15:11 era stato annunciato così un "Mister Blu" su un pavimento vuoto.

**Perché:**
- **Cosa si vedeva.** I riferimenti salvati dalla raccolta continua (uno ogni 10 minuti) mostravano statuine e la Honda Civic dentro la casa vuota alle 14:46, alle 14:56 e alle 15:06.
- **Cosa era successo.** A ogni riavvio (14:45 e 15:10, due aggiornamenti) la casa era partita con una luce diversa da quella della casa vuota salvata alle 12:55. La ricerca dei personaggi non aveva trovato nessuno, perché i colori non tornavano, e 7-8 secondi dopo la casa aveva reimparato la casa vuota "con 0 presenze", cioè con tutte le statuine dentro.
- **Le conseguenze.** Da lì la casa non le vedeva più, e quando venivano spostate lasciavano presenze fantasma dove erano state: "Rossellina" e "Viola" su un pavimento vuoto, la rete sicura al 94% che lì non ci fosse niente.
- **La prova.** Un test riproduce il caso, con una luce 1,6 volte quella della casa vuota: prima la casa trovava 0 statuine su 3, ora 3. Un secondo passaggio controlla che la casa vuota imparata non le contenga.

### D-72 — La rete addestrata di nuovo con i dati di oggi, rivisti (7/10)
**Scelta:**
- **I dati.** Ai 7.635 ritagli della notte si aggiungono quelli di oggi: la registrazione delle 14:38, la raccolta continua fino alle 15:20 e le voci del registro. In tutto 2.995 ritagli.
- **La revisione.** Le etichette della casa sono state controllate con la rete della notte. I 485 ritagli su cui casa e rete erano in disaccordo sono stati guardati uno per uno:
  - quasi tutti i "Mister Green" sul prato e i "Giallo Galli" sul letto erano prato e letto vuoti, e sono diventati "niente";
  - molti "niente" erano statuine vere, inglobate nella casa vuota (D-71), e hanno preso il loro nome: Mister Brown, Rossana e Rossellina sdraiati, Mister Green sul prato;
  - i ritagli incerti, quasi tutti tra Mister Blu e Viola, sono stati tolti.
- **Anche gli accordi.** Sono stati controllati anche i ritagli su cui casa e rete erano d'accordo, raggruppati per aspetto. Ne restano 2.715.
- **Il registro della visione.** 186 voci etichettate in più ("Revisione").

**I numeri.** Il blocco di tempo lasciato fuori sono i ritagli più recenti di oggi, 1.306, mai visti dalla rete nuova:
- **Accuratezza:** 95,6% (la rete della notte 95,4%).
- **Errori gravi:** nessuna statuina scartata, nessun nome sbagliato tra quelli dati al 95%.
- **I "niente" riconosciuti con sicurezza:** almeno al 90% l'80% dei "niente" (la rete della notte il 42%), quindi molte più macchie fantasma fermate prima di nascere.

Sul blocco della notte la rete nuova dà "Mister Blu" a ritagli etichettati Viola o Rossellina: anche la rete della notte, che pure li aveva visti in addestramento, dice Mister Blu. Sono etichette sbagliate dalla casa quella notte. Mister Blu e Viola restano la coppia più debole. Sulla scheda la rete della notte resta come `figures-run2.*`.

**Perché:** richiesta di Emilio: controllare tutto quello che è stato imparato e migliorare il riconoscimento dei personaggi.

### D-73 — Le correzioni fatte sulla piantina diventano esempi per la rete (7/10)
**Scelta:**
- **Ritrovare le correzioni.** `scripts/figures/web_fixes.py` ritrova nel database della casa le correzioni fatte sulla piantina della webapp: presenze eliminate e presenze a cui è stato dato un nome. Le posizioni registrate una volta al secondo dicono di quale traccia si trattava e per quanto tempo è rimasta in quel punto.
- **Applicarle ai ritagli.** `build_crops.py --fixes` le applica a tutti i ritagli di quella traccia in quel punto:
  - una presenza eliminata è "niente";
  - una presenza a cui è stato dato un nome è quel personaggio, anche nei momenti in cui la casa la chiamava in un altro modo o non la chiamava.
- **Prima le correzioni a mano.** Un nome dato a mano non viene tolto dai controlli automatici delle etichette.
- **La traccia negli eventi.** Gli eventi "elimina" e "nome" della webapp ora registrano anche la traccia, per ritrovarle senza ricostruirle. Ogni ritaglio porta la traccia e il riquadro da cui viene.

**Perché:** richiesta di Emilio: riaddestrare tutto sulla base dei movimenti e delle correzioni fatte a mano sulla piantina.
- **Le correzioni del 7/10.** Erano 32 (19 nomi e 13 presenze eliminate), quasi tutte ritrovate (28 tracce), comprese quelle fatte di notte durante la registrazione.
- **Chi aveva ragione.** Alle 00:08 Emilio aveva chiamato "Rossellina" una statuina rosa sdraiata sul letto arancione. La casa prima la chiamava "Mister Blu", e le reti addestrate su quelle etichette la chiamavano ancora Mister Blu: avevano imparato l'errore della casa.
- **Le altre correzioni.** Lo stesso vale per Viola sul prato. Le presenze eliminate nel pomeriggio erano fantasmi rimasti dove una statuina era stata spostata: il pezzo di vita in cui la statuina c'era davvero resta con il suo nome.
- **Il periodo delle statuine inglobate.** Insieme alla revisione per gruppi di ritagli simili, tra le 15:10 e le 16:16 circa 4.000 ritagli di pavimento, pareti, prato e strisce luminose a cui la casa aveva dato un nome sono diventati "niente".
