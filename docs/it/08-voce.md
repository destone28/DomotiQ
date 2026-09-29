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
| **Normale** | Risposte, citofono, allarmi e avvisi, e gli eventi importanti delle regole. |
| **Chiacchierona** | Come Normale, più i commenti: chi va dove ("Marco è in cucina.", al massimo ogni 20 secondi), le proposte ("Siete in tanti in soggiorno: facciamo festa?" con tre o più persone in soggiorno, "Che bella giornata in giardino: accendo il barbecue?" con due o più persone in giardino, al massimo ogni 10 minuti) e le frasi che le regole segnano come chiacchierone, come "La temperatura è tornata normale." |

Si imposta da **Comandi → Loquacità**, oppure a voce: "Stai zitta" / "Be quiet", "Parla di più" / "Talk more", "Parla normale" / "Normal mode". Ogni frase che la casa dice compare anche come sottotitolo sui telefoni e in **Eventi → Detto dalla casa**.

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
| Annullare | Annulla · Lascia stare | Cancel · Never mind |

Colori: rosso/red, verde/green, blu/blue, giallo/yellow, arancione/orange, viola/purple, rosa/pink, bianco/white, azzurro/cyan, caldo/warm. Le stanze si possono chiamare in più modi: *soggiorno*, *salotto* o *sala*; *camera* o *camera da letto*; *locale tecnico* o *tecnico*; *living room*, *lounge*; e così via.

Qualche dettaglio:

- "Buonanotte" / "Good night" passa allo scenario Notte e augura la buonanotte; "Buongiorno" / "Good morning" torna allo scenario Normale e augura il buongiorno.
- Una luce accesa a voce resta accesa per due minuti; "spegni" la tiene al buio per un minuto; poi la stanza torna alla casa.
- Il volume cambia a passi di 15 (su 100).
- A una festa o a una grigliata chiesta troppo presto la casa risponde "Un attimo di pausa, poi rifacciamo festa!" oppure "Il barbecue è già acceso, o si sta raffreddando."

Ecco come suonano le risposte: "Marco è in cucina." / "Marco is in the kitchen.", "In cucina ci sono Marco e un cane.", "In casa ci sono 2 persone.", "In soggiorno ci sono 24.3 gradi.", "L'auto è parcheggiata in garage." Quando la casa non è sicura di una statuina aggiunge "Almeno credo." / "I think.".

## Domande libere e il modello linguistico

Una frase che l'analizzatore non capisce ("Quanta gente c'è in cucina?", una richiesta con parole insolite, una frase storpiata dal riconoscimento) passa al **modello linguistico**. Mentre lavora, la casa dice "Vediamo…" / "Let me see…".

Il modello è **Qwen2.5-0.5B-Instruct** (quantizzato a 4 bit, in formato GGUF), un piccolo modello linguistico fatto girare da `llama-server` di llama.cpp nel servizio `domotiq-llm`, sulla scheda, senza internet. Riceve istruzioni fisse con le stanze, i comandi della casa e qualche esempio, poi i nomi dei personaggi registrati e la frase. La sua uscita è vincolata mentre viene prodotta, così può scrivere soltanto un comando della casa con i suoi argomenti, in poche parole: *where_is Marco*, *who_in kitchen*, *lights_on bedroom purple*, *scene relax*, oppure *other* per tutto ciò che non riguarda la casa. I comandi coprono le stesse richieste della tabella qui sopra (dov'è, chi c'è, quanti, temperatura, umidità, ora, luci, scenari, festa, barbecue, l'auto, il riepilogo della casa, aiuto, lingua, volume, chi sei, aggiungere un personaggio, una barzelletta). Un nome può essere solo quello di uno dei personaggi registrati. Le istruzioni sono sempre lo stesso testo, che `llama-server` tiene nella sua cache, quindi ogni domanda aggiunge da leggere solo poche parole.

**Il modello sceglie cosa fare; non scrive mai quello che dice la casa.** La risposta viene poi composta dallo stesso codice che risponde alle frasi fisse, a partire dallo stato reale della casa, con frasi preparate in italiano e in inglese. Così la casa non può inventare niente: se il modello capisce male, il caso peggiore è una risposta corretta a un'altra domanda.

A una domanda che non riguarda la casa risponde: "Sono la casa: posso dirti chi c'è e dove, che temperatura fa, e posso accendere luci, fare festa o grigliare." / "I'm the house: I can tell you who's here and where, the temperature, and I can turn on lights, throw a party or light the barbecue." A una frase che nessuno ha capito risponde "Non ho capito. Prova a chiedermi: dov'è Marco? Oppure: fai festa!".

Senza il modello linguistico (installato con `--no-llm`, o con il suo servizio fermo) le frasi fisse qui sopra continuano a funzionare.

## Riconoscimento vocale

I modelli Vosk sono `vosk-model-small-it-0.22` e `vosk-model-small-en-us-0.15` (Apache-2.0). La casa li usa in due modi:

- **Un elenco chiuso di frasi** per i nomi, il sì/no e le opzioni di una domanda: il modello accetta solo quelle parole, il che lo rende veloce (meno di mezzo secondo per un nome sulla scheda) e molto difficile da ingannare;
- **Parlato libero** per domande e comandi, trasformato poi in un intento.

Il microfono è acceso solo mentre la casa ascolta, a 16 kHz mono; l'audio resta in memoria e non viene mai salvato.

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
