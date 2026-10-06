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
  - il registro di sistema riporta anche le frasi dette dalla casa (`said`).

**Perché:** richiesta di Emilio ("ricontrolla gli ultimi log di frasi dette e ricevute e sistema le frasi"). Ogni caso ha un test in `tests/test_exchanges.py`.
