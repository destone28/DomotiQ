# 8. Voce

La casa ascolta e parla in **italiano e in inglese**, interamente offline. I visitatori usano i tre tasti del totem: tengono premuto **Parla** per fare una domanda o dare un comando, premono **Citofono** per suonare il campanello e presentarsi, e premono **Lingua** per passare dall'italiano all'inglese e viceversa.

La catena vocale ha quattro parti:

- **Riconoscimento vocale**: Vosk, con i modelli piccoli italiano e inglese, sulla scheda.
- **Comprensione**: un analizzatore a regole, veloce, per le frasi più comuni; le frasi che non capisce passano a un piccolo modello linguistico, Qwen2.5-0.5B-Instruct su llama.cpp, che sceglie soltanto cosa fare.
- **Risposte**: sempre composte dal codice a partire dallo stato reale della casa.
- **Sintesi vocale**: Piper, con una voce italiana e una inglese.

## I tasti

Visti dal visitatore, da sinistra:

| Tasto | Cosa fa | Il suo LED |
|---|---|---|
| **Parla** | Tienilo premuto e parla; rilascialo quando hai finito. Un bip segna l'inizio e la fine. Non c'è fretta: la casa ascolta finché il tasto resta premuto (fino a due minuti). Premere Parla mentre la casa sta parlando la interrompe. | acceso mentre la casa ascolta |
| **Citofono** | Suona un campanello e la casa chiede "Chi è?" / "Who is it?". Di' un nome, senza premere niente: dopo la domanda la casa ascolta per 5 secondi. Vedi [il citofono](07-riconoscimento-e-identita.md#con-il-citofono). | lampeggia durante la conversazione |
| **Lingua** | Passa dall'italiano all'inglese e viceversa. Tutte le luci lampeggiano per circa un secondo, **verdi per l'italiano** e **rosse per l'inglese**, e la casa dice "Italiano" o "English". | acceso mentre la casa parla inglese |

La casa parte in italiano. La lingua si può cambiare anche dalla webapp, in **Comandi → Lingua della casa**, oppure a voce ("Parla inglese", "Speak Italian"). È la lingua in cui la casa parla e ascolta; ogni telefono sceglie per conto suo la lingua della webapp.

Durante la conversazione del citofono e la registrazione a voce, la casa ascolta da sola per qualche secondo dopo ognuna delle sue domande ("Chi è?", "Ho capito Marco, giusto?", "In che stanza l'hai messo?"). Per rispondere alle sue domande su chi è chi ("In cucina c'è Marco o Leo?"), tieni premuto **Parla** e di' il nome.

## Loquacità

| Livello | Comportamento |
|---|---|
| **Silenziosa** | Non parla mai. Restano il campanello e i suoni brevi; le risposte e tutto il resto che la casa direbbe compaiono solo come sottotitoli nella webapp. |
| **Normale** | Risposte, citofono, allarmi e avvisi, gli eventi importanti delle regole, le domande della casa e una frase per chi entra, esce o cambia stanza (vedi *Il racconto della casa* più sotto). |
| **Chiacchierona** | Come Normale, più i commenti: le proposte ("Siete in tanti in soggiorno: facciamo festa?" con tre o più persone in soggiorno, "Che bella giornata in giardino: accendo il barbecue?" con due o più persone in giardino, al massimo ogni 10 minuti) le frasi che le regole segnano come chiacchierone, come "La temperatura è tornata normale.", e le **domande ai personaggi** (sotto). |

Si imposta da **Comandi → Loquacità**, oppure a voce: "Stai zitta" / "Be quiet", "Parla di più" / "Talk more", "Parla normale" / "Normal mode". Ogni frase che la casa dice compare anche come sottotitolo sui telefoni e in **Eventi → Detto dalla casa**.

## Parlare senza premere Parla

Dopo **ogni** sua domanda la casa ascolta da sola per qualche secondo, senza il tasto Parla: il saluto a un telefono nuovo, le domande ai personaggi, "chi è?" per un nuovo arrivato, i dubbi tra due personaggi, le conferme. Se la risposta non è chiara la chiede una seconda volta, e intanto la stessa domanda compare sui telefoni: vale la prima risposta, a voce o dall'app, e appena arriva la casa smette di ascoltare. Mentre ascolta: il LED di **Parla** si accende e sui telefoni compare *La casa ti ascolta…*. Se mentre ascolta la casa dice qualcos'altro (una regola, un avviso), la risposta viene scartata: potrebbe essere la sua stessa voce. **Parla** e il **citofono** vengono sempre prima: premerli interrompe il saluto o la domanda, e la casa ascolta il tasto.

**Un telefono nuovo.** La prima volta che un telefono apre la webapp, la casa lo saluta: "Ciao! Si è appena collegato un telefono nuovo. Come ti chiami?". Il nome si può dire a voce (la casa chiede conferma: "Ti chiami Luca?") oppure scrivere nella scheda che compare sul telefono; poi la casa invita a entrare con un personaggio, e il telefono propone **Aggiungi un personaggio**. Il nome diventa il soprannome del telefono, quello che compare nel registro delle modifiche.
- Ogni telefono viene salutato una volta sola, anche dopo un riavvio; un telefono che si ricollega dallo stesso indirizzo con un'altra pagina (l'icona sulla schermata Home, una finestra anonima, `casaN.lan`) è lo stesso telefono. La casa dimentica i telefoni (e i nomi) dopo 7 giorni.
- Se si collegano più telefoni insieme, un solo saluto per tutti, e al massimo un saluto a voce (o un ringraziamento) ogni 45 secondi: gli altri telefoni ricevono solo la scheda.
- I nomi **scritti** sui telefoni non vengono mai letti ad alta voce (una casella per il nome permetterebbe di far dire alla casa qualunque cosa): la casa ringrazia senza il nome, il telefono lo mostra. I nomi detti a voce sì, perché vengono dalle parole che il modello vocale conosce.
- **Più tardi** sulla scheda vale per quel telefono: la casa non lo chiede più. Se la scheda si perde (pagina ricaricata, telefono bloccato), torna una volta sola al ricollegamento.
- In modalità **Silenziosa** la casa non parla e non ascolta: resta la scheda sul telefono.
- Si spegne da **Impostazioni → Voce → Saluta i telefoni nuovi**.

**Le domande ai personaggi** (solo in modalità **Chiacchierona**). Più o meno ogni due minuti, se ci sono visitatori (qualcosa è successo in casa negli ultimi 5 minuti: una statuina spostata, un tasto, un telefono), c'è un personaggio con un nome e la casa è libera, la casa gli fa una domanda adatta alla stanza in cui si trova, e ascolta la risposta:
- in cucina: "Marco, cosa cuciniamo stasera: pizza o pasta?", "hai fame?";
- in soggiorno: "ti va un po' di musica?" (con un sì parte la festa), "guardiamo un film?" (con un sì, scenario cinema), "preferisci il divano o la poltrona?";
- in camera: "hai dormito bene?", "ti abbasso le luci per riposare?" (con un sì la luce diventa tenue);
- in garage: "dove andiamo con la macchina: al mare o in montagna?";
- in giardino: "accendo il barbecue?" (con un sì parte la ventola), "ti piace il mio giardino?";
- dovunque: "ti piace questa casa?", "sei più da mattina o da sera?", "da dove vieni?", "qual è il tuo colore preferito?" (la luce della stanza prende quel colore);
- agli animali: "vuoi fare una passeggiata?", "hai fame?".

La risposta si confronta con poche parole attese (sì, no, pizza, pasta, i colori...) e non viene mai eseguita come un comando libero: in una chiacchierata "mi piace la musica" non deve far partire la festa. Le proposte si eseguono solo dopo un sì breve e chiaro ("perché no" vale sì, "non lo so" no, "dai" nemmeno), e la casa non propone quello che adesso non può fare (il barbecue già acceso, una festa appena finita, il cinema già in corso). Senza risposta: "Niente? Sarà per la prossima volta, Marco." la prima volta, poi silenzio; dopo due domande senza risposta la casa aspetta un nuovo segno di visitatori. Mai in bagno né nel locale tecnico, mai due volte di fila allo stesso personaggio (con uno solo in casa aspetta che ne arrivi un altro), e non durante una festa, una conversazione, una registrazione o una domanda della casa. Si regolano da **Impostazioni → Voce**: *Domande ai personaggi* e *Una domanda ogni (s)* (almeno 45, di solito 120; il momento esatto varia di un quarto in più o in meno).

**Il racconto della casa.** In modalità **Normale** e **Chiacchierona** la casa dice in poche parole cosa succede: "Ecco Viola in soggiorno!", "Viola va in cucina.", "Luca entra in casa.", "Mister Braun esce sul vialetto.", "Ciao Rosaria, a presto!", "L'auto è parcheggiata in garage." (l'arrivo e la partenza dell'auto li dicono le regole: "Bentornato a casa!", "Buon viaggio!"). Aspetta che il movimento si sia fermato per un secondo, così una statuina che attraversa una stanza al volo non viene annunciata; quello che succede insieme lo dice in una volta sola; non parla sopra una domanda né mentre qualcuno parla con lei. Un nuovo arrivato che non conosce non viene annunciato: la casa chiede chi è.

## Cosa puoi dire

Gli esempi qui sotto vengono capiti direttamente dall'analizzatore a regole. Tollera gli errori di riconoscimento nei nomi e non richiede frasi esatte: le parole che contano sono i verbi, le stanze, i colori e i nomi dei personaggi. Un nome registrato detto da solo ("Luna") vale come "dov'è Luna?".

| Richiesta | Italiano | Inglese |
|---|---|---|
| Dove si trova qualcuno | Dov'è Marco? · Dove si trova Sofia? | Where is Marco? |
| Chi c'è in una stanza | Chi c'è in cucina? · C'è qualcuno in garage? | Who's in the living room? · Is anyone in the garage? |
| Quanti | Quante persone ci sono in casa? · Quanti animali ci sono? | How many people are in the bathroom? · How many pets are there? |
| Temperatura | Che temperatura c'è? · Temperatura in bagno | What is the temperature? |
| Umidità | Quanta umidità c'è in bagno? | How humid is the bathroom? |
| Ora | Che ore sono? | What time is it? |
| Impostare l'ora | Sono le tre e mezza · Sono le quindici e trenta | It's half past three · It's ten to seven pm |
| Accendere le luci | Accendi la luce in cucina · Luce rossa in camera | Turn on the kitchen light · Make the bedroom red |
| Spegnere le luci | Spegni la luce in bagno · Spegni tutto | Turn off the lights in the garage |
| Scenari | Scenario cinema · Scenario relax · Modalità via · Buonanotte · Buongiorno | Cinema mode · Relax scene · Away mode · Good night · Good morning |
| Festa | Fai festa · Balliamo | Let's dance · Party |
| Barbecue | Accendi il barbecue · Spegni il barbecue | Light the barbecue · Turn off the barbecue |
| L'auto | Dov'è la macchina? | Where is the car? |
| Tutta la casa | Com'è la casa? · Cosa succede? | How is the house? · What's happening? |
| Aiuto | Cosa sai fare? | What can you do? |
| Chi è la casa | Chi sei? | Who are you? |
| Una barzelletta | Raccontami una barzelletta · Fammi ridere | Tell me a joke · Make me laugh |
| Lingua | Parla inglese · Parla italiano | Speak English · Speak Italian |
| Loquacità | Stai zitta · Parla di più · Parla normale | Be quiet · Talk more · Normal mode |
| Volume | Alza il volume · Abbassa la musica | Louder · Turn it down |
| Nuovo personaggio | Aggiungi un personaggio | Add a character |
| Una storia | Raccontami una storia · Una storia su Marco e Giulia · Una storia sulla cucina · Un'altra storia | Tell me a story · A story about Marco and Giulia · A story about the kitchen · Another story |
| La giornata | Cosa ha fatto Marco oggi? · Dov'è stato Luca? · Chi è stato in cucina oggi? · Quante feste abbiamo fatto oggi? | What did Marco do today? · Where has Luca been? · Who has been in the kitchen today? · How many parties today? |
| Un personaggio | Ricorda che Marco fa il medico · Cosa sai di Marco? · Chi è Giulia? | Remember that Marco is a doctor · What do you know about Marco? · Who is Giulia? |
| Ricordi e domande libere | Ti ricordi la festa di compleanno di Giulia del 1998? · Luca ha pagato le bollette? · Quando scade l'assicurazione dell'auto? | Do you remember Giulia's birthday party in 1998? · Did Luca pay the bills? · When does the car insurance expire? |
| Annullare | Annulla · Lascia stare | Cancel · Never mind |

Colori: rosso/red, verde/green, blu/blue, giallo/yellow, arancione/orange, viola/purple, rosa/pink, bianco/white, azzurro/cyan, caldo/warm. Le stanze si possono chiamare in più modi: *soggiorno*, *salotto* o *sala*; *camera* o *camera da letto*; *locale tecnico* o *tecnico*; *living room*, *lounge*; e così via.

Qualche dettaglio:

- "Buonanotte" / "Good night" passa allo scenario Notte e augura la buonanotte; "Buongiorno" / "Good morning" torna allo scenario Normale e augura il buongiorno.
- Una luce accesa a voce resta accesa per due minuti; "spegni" la tiene al buio per un minuto; poi la stanza torna alla casa.
- Il volume cambia a passi di 15 (su 100).
- A una festa o a una grigliata chiesta troppo presto la casa risponde "Un attimo di pausa, poi rifacciamo festa!" oppure "Il barbecue è già acceso, o si sta raffreddando."

Ecco come suonano le risposte: "Marco è in cucina." / "Marco is in the kitchen.", "In cucina ci sono Marco e un cane.", "In casa ci sono 2 persone.", "In soggiorno ci sono 24.3 gradi.", "L'auto è parcheggiata in garage." Quando la casa non è sicura di una statuina aggiunge "Almeno credo." / "I think.".

## Il modello linguistico dei comandi

Una frase che l'analizzatore non capisce ("Quanta gente c'è in cucina?", una richiesta con parole insolite, una frase storpiata dal riconoscimento) passa a **Qwen2.5-0.5B-Instruct** (quantizzato a 4 bit, in formato GGUF), fatto girare da `llama-server` di llama.cpp nel servizio `domotiq-llm`. Mentre lavora, la casa dice "Vediamo…" / "Let me see…". Riceve istruzioni fisse con le stanze, i comandi della casa e qualche esempio, poi i nomi dei personaggi registrati e la frase. La sua uscita è vincolata mentre viene prodotta, così può scrivere soltanto un comando della casa con i suoi argomenti: *where_is Marco*, *who_in kitchen*, *lights_on bedroom purple*, oppure *other* per tutto il resto. Le istruzioni sono sempre lo stesso testo, che `llama-server` tiene nella sua cache. **Questo modello sceglie cosa fare e non scrive mai quello che dice la casa**: la risposta si compone dallo stato reale della casa, con frasi preparate in italiano e in inglese, quindi non può inventare. Lo stesso vale per la giornata dei personaggi ("Cosa ha fatto Marco oggi?"): la risposta viene da quello che la webcam ha visto davvero, non da un modello.

## Storie, ricordi e domande libere

Le storie, i ricordi ("Ti ricordi la festa di compleanno di Giulia del 1998?") e le risposte sulla vita di casa ("Luca ha pagato le bollette?", "Quando scade l'assicurazione dell'auto?") la casa le genera sulla scheda combinando i pezzi di un database locale, `data/stories.json`, scritto a mano in italiano e in inglese: momenti ("Una sera d'inverno"), attività per ogni stanza, eventi, reazioni, relazioni tra personaggi, scoperte, finali, personalità (lavori, caratteri, passioni e manie, anche per cani e gatti), dettagli della vita di casa (bollette, assicurazioni, faccende, spesa, torte, vacanze) e le tracce di sei tipi di storia (da soli, al lavoro, in coppia, lo scherzo sospetto, la festa a sorpresa, la stanza). È generazione procedurale: la casa sceglie a caso tra i pezzi che stanno bene insieme e li incastra nella traccia. Poche centinaia di pezzi danno milioni di storie diverse, pronte in un millesimo di secondo, e ogni frase è corretta perché ogni pezzo è scritto per andare d'accordo con qualunque nome: in italiano nessun aggettivo o participio si riferisce a un personaggio, in inglese niente *he* o *she*. Qui la casa inventa, ed è voluto:

- **Pezzi che stanno insieme.** Una scoperta o un finale può essere legato agli eventi che spiega (il pacco senza nome era un regalo per la casa); gli altri pezzi condividono un'etichetta con l'evento (buio, rumore, acqua, festa…). Giorno e notte, estate e inverno non si incontrano mai nella stessa storia; il rumore "dal garage" non lo sente chi è già in garage; i cani abbaiano e i gatti soffiano.
- **Personalità.** La prima volta che serve, un personaggio riceve dal database un lavoro, un carattere, una passione e una mania, diversi da quelli degli altri. Restano gli stessi fino al riavvio della casa: se Marco è un medico, nelle storie successive resta un medico; al riavvio si riparte da capo. Quello che lo staff ha detto alla casa viene prima (nella webapp, in *Chi è*, una cosa per riga, oppure a voce: "Ricorda che Marco fa il medico"). Un'informazione che è un lavoro prende il posto del lavoro, e nelle storie in inglese diventa il lavoro corrispondente del database ("works at the hospital"); le altre entrano nelle storie scritte nella loro lingua ("Marco, che ama il jazz, …"). "Cosa sai di Marco?" risponde con le informazioni date e con la personalità; un'informazione scritta nell'altra lingua si legge con la voce di quella lingua.
- **Sempre una storia nuova.** Per ogni personaggio (o stanza) la casa ricorda le tracce e i pezzi già usati e sceglie tra gli altri finché non li ha usati tutti.
- **La vita della casa.** Alla prima domanda la risposta si inventa dal database, poi resta: la stessa domanda riceve la stessa risposta, anche nell'altra lingua, fino al riavvio. La casa sa rispondere su bollette (tutte o una sola: luce, gas, acqua, internet; chi le ha pagate e quando, oppure quando scadono), assicurazione dell'auto e della casa, compleanni, feste passate (con il nome e l'anno, anche di qualcuno che non conosce, oppure "la festa di Natale del 2005": la stanza, la torta, cosa successe e chi c'era), spesa, faccende (spazzatura, piatti, bucato, aspirapolvere, piante), la pappa degli animali, l'auto, le vacanze e i ricordi di un personaggio. A una domanda che non riguarda la casa risponde che è una casa e del resto del mondo non sa niente.
- **Detta frase per frase.** Mentre una frase suona si sintetizza la successiva, ognuna con la voce della sua lingua, e la stanza di cui parla si accende. **Parla** interrompe la storia; anche un cambio di lingua la ferma.

In modalità **Chiacchierona**, circa due volte su cinque al posto di una domanda della lista la casa dice qualcosa su un personaggio presente: un aneddoto, la sua mania ("Lo sapevate che Marco parla alle piante?"), un ricordo con la data ("Vi ricordate la festa di Marco del 2004?") oppure una domanda sulla vita di casa ("Marco, hai pagato la bolletta della luce?"), seguita dalla risposta a un sì o a un no. Quello che dice il visitatore diventa la vita della casa: dopo un sì, a "Marco ha pagato la bolletta della luce?" la casa risponde di sì.

Storie, ricordi e domande libere non usano nessun modello linguistico, quindi funzionano anche con un'installazione `--no-llm`. All'inizio le scriveva un secondo modello sulla scheda: le misure e il perché del cambio sono nella decisione D-19 (`docs/decisioni.md`).

## Riconoscimento vocale

I modelli Vosk sono `vosk-model-small-it-0.22` e `vosk-model-small-en-us-0.15` (Apache-2.0). La casa li usa in due modi:

- **Un elenco chiuso di frasi** per i nomi, il sì/no e le opzioni di una domanda: il modello accetta solo quelle parole, il che lo rende veloce (meno di mezzo secondo per un nome sulla scheda) e molto difficile da ingannare;
- **Parlato libero** per domande e comandi, trasformato poi in un intento.

Il microfono è acceso solo mentre la casa ascolta, a 16 kHz mono: mentre Parla è premuto, dopo "Chi è?" e per qualche secondo dopo il saluto a un telefono nuovo o una domanda della modalità chiacchierona. L'audio resta in memoria e non viene mai salvato; di quello che la casa sente senza Parla resta nel registro solo l'esito (sì, no, un'opzione), mai il testo, e il testo riconosciuto non viene mandato ai telefoni. La risposta di un visitatore a una domanda sulla vita di casa (modalità chiacchierona) resta nella memoria del narratore, per le storie successive, fino al riavvio: non viene scritta su disco.

## Sintesi vocale

Piper (`piper1-gpl`, GPL-3.0) gira come programma separato nel servizio `domotiq-tts`, e la casa gli manda le frasi via HTTP sull'interfaccia di loopback. Le voci sono `it_IT-serena-medium` (CC BY 4.0) e `en_US-ljspeech-medium` (pubblico dominio). Numeri e unità di misura vengono pronunciati come si deve ("24.3 °C" diventa "24 virgola 3 gradi" in italiano e "24 point 3 degrees" in inglese). Le frasi frequenti ("Chi è?", "Vediamo…", "Si balla!"…) vengono sintetizzate all'avvio e tenute in memoria, così partono subito anche quando il processore è impegnato.

Tutti gli altri suoni (campanello, campanello breve, i bip di Parla, allarme, notifica) e la musica della festa sono sintetizzati dal codice stesso della casa: nessun campione registrato. La musica della festa è dance in cassa dritta a 124 BPM, con kick, clap, hi-hat, basso, accordi e una melodia che cambiano a ogni festa, a tempo con lo spettacolo di luci del microcontrollore. Quando la casa parla, la musica si abbassa sotto la voce.

## Impostare l'ora a voce

La UNO Q non ha una batteria per l'orologio. Se due minuti dopo l'avvio l'ora è ancora sconosciuta, la casa dice una volta (a meno che non sia Silenziosa): "Non so che ore sono: premi Parla e dimmelo."

Tieni premuto **Parla** e di' l'ora:

- In italiano: "Sono le quindici e trenta", "Sono le tre e mezza", "Sono le tre e venticinque", "Sono le dieci e un quarto", "Sono le tre e tre quarti", "Sono le otto meno venti", "Sono le sette meno un quarto", "È l'una e dieci". Va bene qualsiasi minuto, in lettere o in cifre; "del pomeriggio" o "di sera" aggiungono dodici ore.
- In inglese: "It's half past three", "It's quarter to five", "It's twenty past six", "It's ten to seven pm", "It's five twenty", "Set the clock at three thirty". "pm", "afternoon" o "evening" aggiungono dodici ore.

La casa conferma: "D'accordo, sono le 15 e 30." / "All right, it's 15:30." Anche il primo telefono che apre la webapp imposta l'orologio, e lo staff può impostarlo da **Impostazioni → Usa l'ora di questo telefono**.

Avanti: [regole](09-regole.md).
