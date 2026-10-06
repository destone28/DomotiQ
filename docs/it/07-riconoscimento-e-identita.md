# 7. Riconoscimento e identità

La casa riconosce persone, animali, l'auto e gli oggetti con la **visione artificiale classica**, senza addestrare un modello. Vista dal palo, la base di una statuina misura appena una dozzina di pixel alla risoluzione di analisi, il numero dei personaggi non ha limiti e i visitatori ne aggiungono di nuovi durante la fiera. Un rilevatore addestrato avrebbe bisogno di centinaia di immagini etichettate per ogni nuovo personaggio; il metodo classico registra un personaggio in pochi secondi e sta in un solo core della CPU della UNO Q.

Il **machine learning** si usa in un solo punto: quando un personaggio viene registrato con una foto, un rilevatore di oggetti **YOLOX-Nano** addestrato sul dataset COCO guarda la foto e propone che tipo di cosa è.

## Come vede la casa

La visione gira in un processo separato, così un fotogramma lento o un problema della webcam non rallentano mai la webapp o la voce; se si ferma, riparte da sola.

1. **Acquisizione.** La Logitech C270 fornisce fotogrammi MJPEG; la casa li analizza a 640 × 480, da 7 a 10 al secondo sulla scheda. Esposizione, bilanciamento del bianco e guadagno sono bloccati, così i colori non si spostano quando statuine e luci colorate vanno e vengono. I valori si trovano misurando le immagini: la casa lascia regolare la webcam in automatico sulla casa vuota, misura luminosità e colori, poi cerca i valori manuali che danno la stessa immagine, un quarto più scura. Quello che la temperatura di colore della webcam non riesce a correggere (certe luci calde e verdastre) lo corregge un guadagno fisso su ogni canale. Finché la luce non è regolata la casa non riconosce niente, e lo dice in *Diagnostica*. Se poi la luce della sala cambia molto, la webcam si riregola da sola (vedi *Niente si muove da solo*).
2. **La casa vuota.** Alla calibrazione la casa salva la mediana di 20 fotogrammi della casa vuota, arredi compresi. Tutto ciò che è diverso da questa immagine è una statuina, l'auto, un oggetto o la mano di un visitatore.
3. **Differenza nello spazio colore Lab, con correzione della luce stanza per stanza.** Le luci delle stanze della casa sono colorate, e la luce del padiglione cambia. Ogni pixel viene corretto con i guadagni della luce della sua stanza: un guadagno per canale di colore, stimato sul pavimento libero della stanza come il rapporto più frequente rispetto alla casa vuota (così una statuina o l'auto non lo falsano), e, quando sono possibili due valori, quello più vicino al fotogramma precedente. Attraverso una porta il guadagno passa gradualmente da una stanza all'altra. La casa avvisa la visione ogni volta che cambia una luce.
4. **Le ombre non contano.** Un'ombra è più scura ma mantiene il colore del pavimento.
   **Tolleranza per pixel.** Alcuni punti tremolano più di altri: i prati, i bordi dei mobili, gli angoli bui, tutta la casa se la sala è buia e la webcam alza il guadagno. Quando si salva la casa vuota la casa misura il tremolio di ogni pixel sui 20 fotogrammi e lo salva accanto all'immagine (`noise.npy`); senza quel file lo impara dalle prime immagini tranquille dopo l'avvio, poi lo aggiorna piano dove non ci sono presenze, e lo reimpara quando la webcam si riregola. Una macchia conta solo se da qualche parte supera di 5 volte il tremolio dei suoi pixel, e allora conta intera: una statuina su un prato che tremola resta com'è, una macchia fatta solo di tremolio sparisce. Con la luce del laboratorio il tremolio è sotto le soglie fisse e non cambia niente; con un'immagine due o tre volte più rumorosa toglie dal 60 al 95% delle macchie di tremolio, senza perdere statuine. Costa circa 2,5 ms per immagine.
5. **Maschere.** La visione guarda solo la base della casa: quello che c'è intorno (il banco, le mani dei visitatori prima che entrino, i telefoni) non conta. Dentro la base vengono ignorate le zone che non sono pavimento: le applique, la chioma dell'albero, il palo della webcam, la cima delle pareti, il totem del citofono e le schede sulle pareti del locale tecnico (la UNO Q, che sporge di un paio di centimetri dalla parete, e l'hub), i cui LED si accendono e spengono, ciascuna proiettata all'altezza a cui si trova davvero.
6. **Oggetti.** Dopo una pulizia morfologica, ogni macchia connessa diventa un oggetto con la sua area in mm², il suo colore mediano e un istogramma del suo colore, il suo allungamento, e i suoi punti più vicino e più lontano rispetto al punto sotto la webcam.
7. **Dove si trova (parallasse).** La webcam vede dall'alto una statuina in piedi, che quindi appare allungata in direzione opposta al punto sotto l'obiettivo: il suo punto più vicino è la punta dei piedi, quello più lontano la nuca. Abbassando la testa di tutta l'altezza della statuina si ottiene anche la posizione dei piedi, così una statuina viene piazzata correttamente anche quando i piedi sono nascosti dietro una parete. L'auto, che è una scatola più che una statuina, viene piazzata al centro di ciò che si vede. Su scene di prova sintetiche l'errore di posizione resta sotto i 12 mm. Una statuina sul letto, sul divano, su un tavolo o su una panca viene misurata dall'altezza di quel mobile: la casa capisce che ci sta sopra perché i suoi piedi, riportati a quell'altezza, cadono sul mobile. Sul tetto dell'auto invece no: una statuina posata sull'auto si confonde con l'auto. Su quale mobile sta un personaggio lo sa anche la casa, che lo dice (capitolo 8).
8. **Mani.** Una macchia grande almeno come un braccio (2500 mm² dentro la base) che entra dal bordo della base è la mano di un visitatore, tranne al portone del garage, da cui entra l'auto. Tutti i pezzi vicini alla mano ne fanno parte, qualunque sia la loro dimensione: il braccio tagliato dalla cima delle pareti e dalle applique, le dita, l'ombra. Una "mano" che resta perfettamente ferma per 8 secondi è invece un oggetto appoggiato sul bordo (un modulo, un cavo) ed entra a far parte della casa vuota.
9. **Inseguimento.** Gli oggetti vengono abbinati alle tracce del fotogramma precedente con il metodo ungherese, su una distanza che combina posizione, colore e dimensione. **Niente si muove da solo, nemmeno sulla mappa:** senza una mano passata da poco una traccia non salta oltre 30 mm, per quanto tempo sia rimasta nascosta, e la posizione di un personaggio fermo non cambia (un'ombra o una luce sulla sua macchia non lo spostano); nei secondi dopo il passaggio di una mano la posizione si aggiorna una volta, dove la mano l'ha lasciato. Un personaggio seguito che per un momento non si vede (una luce, due statuine che si toccano) resta al suo posto fino a due minuti, un personaggio noto fino a un quarto d'ora. Una macchia sconosciuta proprio accanto a un personaggio, del suo colore, è un pezzo di lui (una statuina sdraiata sopra il tronco dell'albero si vede in due).
10. **Portato in mano.** Quando una statuina sparisce sotto una mano, la sua traccia diventa *portata* e mantiene la sua identità; quando la mano se ne va, la statuina che ricompare dove la mano ha lavorato è lo stesso personaggio. Se la mano ha lasciato una sola cosa nuova, quella è il personaggio che teneva, anche sdraiato o sul letto con colori un po' diversi. Se la mano le è solo passata sopra, la statuina ritrova la sua traccia dov'era. Se è stata posata contro un'altra statuina e le due si vedono come una sola macchia, resta nascosta dietro l'altra finché non si separano. Se la mano esce senza posarla, il personaggio lascia la casa 2,5 secondi dopo.
11. **Chi è.** Ogni identità registrata ha una **firma di colore**: un istogramma degli assi di colore a\* e b\* dello spazio Lab (dove la luminosità è tenuta a parte, così un'ombra o una luce più fioca cambiano poco) più il colore mediano. Per le statuine bianche, grigie e nere la luminosità pesa di più, perché è l'unica cosa che le distingue. Le identità sono uniche, quindi l'assegnazione delle identità alle tracce si risolve per tutte insieme; un'identità viene data dopo due fotogrammi concordi. Conta anche la dimensione: l'auto non viene mai presa per una statuina né una statuina per l'auto, e una taglia molto diversa da quella imparata conta come meno somigliante. Ogni personaggio impara sulla scheda le sue **pose** (fino a sei: sdraiato, sul letto, sotto un'altra luce), ciascuna con colori, dimensione e forma, e il confronto si fa con la più simile; una posa nuova si aggiunge quando la casa è sicura del personaggio, fermo e visto intero, e subito quando qualcuno dice chi è. Una posa però mostra la stessa statuina da un altro lato, non un altro colore: deve avere i colori del personaggio, più che di chiunque altro. Una posa imparata sulla macchia sbagliata (i LED di una scheda, un altro personaggio vicino) farebbe vedere quel personaggio ovunque: la casa non la impara, e quelle imparate prima di questo controllo le dimentica all'avvio. Allo stesso modo i colori e la dimensione registrati imparano solo da una macchia che somiglia da vicino al personaggio. Il confronto di una macchia con tutte le pose di tutti i personaggi è un solo calcolo, fatto una volta per fotogramma. Un personaggio molto più simile a uno che a tutti gli altri viene riconosciuto anche con colori meno vicini, ma solo nei primi 10 secondi di una traccia nuova. **I nomi si muovono solo con le mani:** un nome non sta mai in due posti; senza una mano, chi lo tiene se lo tiene finché gli somiglia, e lo perde solo dopo otto fotogrammi in cui non gli somiglia più; e un nome non va mai a una macchia lontana dall'ultimo posto in cui quel personaggio è stato visto, a meno che una mano sia passata di lì o l'abbia preso. Un personaggio che non si vede più resta così dov'era, invece di comparire su qualche riflesso dall'altra parte della casa. **Storico:** la casa ricorda dove ogni personaggio è stato visto l'ultima volta e se una mano è passata di lì; prima di chiedere chi è una cosa nuova, se in quel punto stava un personaggio e nessuna mano lo ha toccato, è ancora lui e riprende il suo nome. Mentre una statuina è seguita con sicurezza, la sua firma si aggiorna lentamente con quello che vede la webcam.
12. **In quale stanza.** La stanza è quella sotto il punto in cui la statuina poggia, con 15 mm di tolleranza sulle porte, così una statuina su una soglia non salta avanti e indietro tra due stanze.

Il risultato è un elenco di tracce, ognuna con una posizione in millimetri, una stanza, un tipo e, quando è nota, un'identità. Il resto della casa (luci, regole, voce, webapp) lavora su questo elenco.

**A riposo.** Analizzare un fotogramma costa circa 180 ms sulla scheda. Quando la casa è ferma (nessuna mano da 25 secondi, nessuna luce della casa che cambia o è animata, niente in sospeso) la casa confronta prima ogni fotogramma, rimpicciolito a 80 × 60 e in grigi, con l'ultimo analizzato: se nessun punto è cambiato di più di 6 livelli di grigio, il fotogramma è uguale e non viene analizzato di nuovo. Il confronto costa una frazione di millisecondo, una mano lo cambia subito, e comunque almeno un fotogramma al secondo viene analizzato per intero. Così il processore resta libero per la voce. In **Diagnostica**, sulla riga della webcam, *a riposo 60% dei fotogrammi* dice quanti fotogrammi la casa ha lasciato stare (durante la festa compare *in pausa per la festa*).

**Priorità.** La visione è il lavoro continuo della scheda: quando il processore non basta per tutti, cede il passo alla voce, che gira nello stesso servizio (il suo processo ha priorità più bassa). Tra i servizi vengono prima la casa, poi la sintesi vocale, per ultimo il modello linguistico.

### Niente si muove da solo

In un plastico ogni cambiamento lo fa una mano: una statuina entra, esce o si sposta solo se qualcuno la prende. La casa usa questa regola per non vedere presenze che non ci sono.

- **Mentre una mano è sopra la casa**, e per 0,6 secondi dopo che è uscita (la sua ombra, la statuina che oscilla), la casa non conta niente di nuovo e non fa sparire nessuno. Una statuina che la mano non tiene resta dov'è: la sua traccia non salta su un'altra macchia.
- **Sulla piantina una statuina si sposta solo se una mano le arriva vicino** (entro 5 cm), anche di pochi millimetri. Senza una mano vicina restano ferme la posizione e il mobile su cui sta: un'ombra, la luce della sala, la sua macchia che a tratti si unisce a qualcosa accanto non la muovono. Su casa1 la macchia di Viola saltava di 15 mm avanti e indietro senza che nessuno la toccasse, e la piantina la seguiva. Mentre la mano lavora, la statuina segue quello che si vede. Quando la mano se ne va (dopo 0,6 secondi), il suo posto diventa la mediana delle prime 10 immagini, circa un secondo: la mediana ignora le immagini storte con l'ombra del braccio. Lo stesso vale per una statuina appena comparsa. Misurato su quattro registrazioni (`scripts/settle_bench.py`): con 10 immagini il posto fissato resta entro 2 mm da quello vero, con 8 si arriva a 6 mm, con 3 a 12 cm.
- **Dopo, le cose nuove si cercano solo dove la mano ha lavorato**, per 3 secondi, e nasce solo ciò che la mano ha portato: una cosa che era già diversa dalla casa vuota prima che la mano arrivasse non è nuova. Deve anche essere compatta (al massimo 3,5 volte più lunga che larga) e staccarsi bene dal pavimento, per colore o perché molto più scura o più chiara: le strisce che la luce disegna ai piedi delle pareti o sul bordo del divano, e le chiazze tenui, non sono presenze. Non nasce niente che stia tutto su una parete, né una cosa piccola proprio sul bordo della base.
- **Doppio controllo.** Prima di mostrare una cosa nuova sulla piantina e di chiederne il nome, la casa controlla due volte di esserne sicura. La sicurezza va da 0 a 100% e mette insieme quattro misure: quanto spesso la vede, quanto sta ferma, quanto si stacca dal pavimento, quanto è compatta. Deve superare l'80%, e di nuovo un secondo dopo, senza essere scesa sotto nel frattempo. Per due minuti, nella stanza dove qualcuno ha appena detto che non c'era nessuno (a voce, con **Non c'è niente** o con **Non c'è davvero: togli**) o dove la casa ha appena scartato un riflesso, serve il 92%, controllato a 2,5 secondi di distanza.
- **Una cosa sconosciuta che salta**, anche di pochi millimetri, o che sparisce e ricompare più volte al secondo senza una mano intorno, non è una statuina: è un riflesso o un LED. Esce dalla piantina, lì per 30 secondi non nasce niente e per due minuti in quella stanza vale il doppio controllo più severo. Non vale nelle stanze con le luci animate (la festa).
- **Una differenza senza mano intorno** (un riflesso, la luce della sala, una lampada laterale) non diventa mai una presenza. Le differenze tenui entrano a far parte della casa vuota dopo circa 3 secondi. Ciò che sembra una statuina invece non ci entra mai, così toglierla non lascia un fantasma. Fa eccezione una cosa che spicca chiaramente, compare con una mano intorno e resta per 2 secondi: è una statuina posata mentre la casa aspettava.
- **Il posto lasciato** da una statuina entrata nella casa vuota (per esempio dopo che la casa ha reimparato la casa vuota), quando torna uguale alla casa vuota salvata, non è una presenza: la casa vuota se lo riprende.
- **Quando la casa cambia la luce di una stanza**, per 2,5 secondi il suo riflesso su pareti e pavimento non viene preso per una presenza.
- **Quando cambia la luce della sala**, la casa rimisura la luce di ogni stanza e aspetta. L'immagine può restare per 5 secondi molto più buia o più chiara della casa vuota (meno di 0,55 volte o più di 1,8 volte), senza mani e senza una luce della casa appena cambiata: allora la webcam si riregola da sola su quello che vede, al massimo una volta al minuto. Calibrazione, casa vuota, presenze e nomi restano come sono, perché nessuno ha spostato niente. Se la luce va comunque oltre quello che la correzione riesce a seguire, dopo 4 secondi la casa reimpara la casa vuota dall'immagine attuale, lasciando da parte i personaggi che sta seguendo.
- **All'accensione** la casa aspetta che le luci stiano ferme (il microcontrollore le rimanda), poi riconosce i personaggi registrati che sono in casa e l'auto: solo quelli che somigliano da vicino a un personaggio e hanno la forma di una statuina, così l'alone di una lampada o i LED di un modulo non diventano qualcuno. Un personaggio nuovo che era già in casa, o uno sdraiato che somiglia meno, compare appena qualcuno lo sposta.
- **Una presenza seguita meno di 2,5 secondi** è rumore, anche se ha preso un nome: non resta sulla piantina come nascosta.
- **Allarmi solo su presenze certe.** Le regole d'allarme (capitolo 9) contano un personaggio che la casa conosce, o una cosa sconosciuta che sta lì, ferma e ben visibile, da almeno 6 secondi. Una macchia appena nata non fa suonare niente.
- **Il citofono** è escluso dall'analisi, ma il suo contorno conta come bordo della base: un braccio che si allunga verso il soggiorno passando sopra il totem resta una mano.

## Tipi di cose

Ogni identità ha un tipo: **persona**, **cane**, **gatto**, **animale** (qualsiasi altro animale domestico), **auto** o **oggetto**. Le regole possono filtrare per tipo; in una regola *animale* comprende anche cani e gatti. Gli arredi della casa sono fissi e fanno parte della casa vuota; un oggetto nuovo messo nella casa (una sedia, un pallone, una valigia) è un'identità di tipo *oggetto*.

Quando parte una registrazione, la casa propone un tipo:

- **Dalla foto**, se ne è stata scattata una: YOLOX-Nano gira sulla scheda con ONNX Runtime e cerca le 80 classi di COCO; decide il rilevamento sicuro più grande. *person* dà una persona, *dog* un cane, *cat* un gatto; *car*, *truck* e *bus* danno un'auto; *bird*, *horse*, *sheep*, *cow*, *elephant*, *bear*, *zebra*, *giraffe* e *teddy bear* danno un animale; ogni altra classe dà un oggetto, con un nome proposto (per esempio *sedia*, *pallone*, *valigia*).
- **Senza foto**, da dimensione e forma viste dall'alto: una macchia grande è un'auto, una alta e stretta una persona, una piccola, allungata e bassa un animale, tutto il resto un oggetto.

La proposta va sempre confermata da chi registra.

## Registrare un personaggio

Chiunque può registrare personaggi, animali, auto e oggetti, in tre modi.

### Dalla webapp

1. **Personaggi → + Aggiungi**, oppure tocca una statuina sconosciuta nella schermata **Casa** e poi **Registra**.
2. Scrivi il **Nome**. Se vuoi tocca **Scatta o scegli una foto**: basta una foto di fronte; compare nell'elenco e serve a indovinare il tipo. Il telefono la riduce a 1024 pixel prima di inviarla. Tocca **Avanti**.
3. *Appoggialo in un punto libero della casa: lo sto cercando…* La casa cerca qualcosa che vede ma non conosce. Se c'è esattamente un candidato lo prende; se ce n'è più di uno dice *Vedo più cose nuove: tocca quella giusta sulla piantina.*; se non ce n'è nessuno aspetta. Dopo due minuti e mezzo senza risultato ci rinuncia: *Non ho trovato niente di nuovo. Riprova.*
4. *Trovato! Che cos'è?* La casa mostra la sua ipotesi (*Mi sembra: cane*, con un nome proposto per gli oggetti), gli eventuali [avvisi](#avvisi) e i sei tipi. Scegli e tocca **Salva**.
5. *Marco è registrato. D'ora in poi lo riconosco.*

### Con il citofono

1. Un visitatore preme **Citofono** sul totem. Suona un campanello e la casa chiede "Chi è?" / "Who is it?".
2. **Un nome registrato**: "Ciao Marco, entra pure!". La prima statuina che compare dopo il campanello, nei 3 minuti successivi, sul vialetto o in una stanza della casa (non in garage), riceve quel nome, qualunque cosa la webcam l'abbia presa (una statuina sembra spesso un oggetto o un animale) e senza che la casa chieda chi è. Se il nome appartiene a qualcuno che è già dentro, la casa lo dice ("Ma Marco è già in cucina!"). Se la webcam riconosce chiaramente nella statuina che entra qualcun altro, la casa lo dice ("Ma a me sembri Sofia, non Marco!") e mantiene l'identità che vede.
3. **Un nome nuovo**: "Ho capito Marco, giusto?" Dopo un *sì*: "Piacere, Marco! Entra dalla porta." La prima statuina che compare dopo il campanello, nei 3 minuti successivi, sul vialetto o in una stanza della casa, diventa Marco, una persona, con i colori che la casa vede, senza altri passaggi e senza domande; anche se la casa le aveva dato un nome di cui non era sicura. Una statuina che la casa riconosce con certezza come qualcun altro non conta, e nemmeno una che era già in casa prima del campanello.
4. **Un nome non capito**: un secondo tentativo ("Scusa, non ho capito. Chi sei?"), poi "Non ti conosco, ma entra pure: sei un ospite."

Quando una registrazione avviata a voce è completa, la casa dice "Benvenuto, Marco! Ora ti riconosco."

### Con il tasto Parla

Tieni premuto **Parla** e di' "Aggiungi un personaggio" / "Add a character". La casa chiede "Come si chiama?", poi "In che stanza l'hai messo?", e cerca in quella stanza la statuina che non conosce:

- esattamente una: diventa subito Marco;
- ancora nessuna: "Va bene: mettilo in cucina, lo aspetto." La prima statuina sconosciuta messa in quella stanza entro due minuti e mezzo diventa Marco;
- più di una: "Vedo più di un personaggio nuovo in cucina: scegli Marco dalla webapp." Su tutti i telefoni compare una fascia *Registrazione a voce da completare*; **Scegli** apre la piantina per toccare la statuina giusta.

## Nomi

- **I nomi sono unici** in tutta la casa, senza distinzione tra maiuscole e minuscole, e vengono confrontati anche con le pronunce inglesi. Un nome già in uso viene rifiutato: *Il nome Marco è già usato: aggiungi un cognome o un soprannome.* Se le si chiede a voce di aggiungere un nome che ha già, la casa risponde "Conosco già Marco."
- **Non c'è limite** al numero di personaggi o di oggetti.
- **Dire i nomi a voce.** Per riconoscere un nome a voce, la casa ascolta solo i nomi registrati, con il vocabolario del suo modello di riconoscimento vocale. Un nome fatto di parole che il modello non conosce non si può riconoscere a voce: alla registrazione la casa lo controlla e lo segnala al passo di conferma (*Il riconoscimento vocale italiano non conosce «Zorbax»: a voce potrei non capirlo.*). Il riconoscimento inglese potrebbe non capire un nome italiano: nella scheda del personaggio compila **Pronuncia inglese (facoltativa)** con una grafia che riesca a riconoscere; la casa accetta entrambe le forme.
- Chiunque può rinominare o eliminare un personaggio dalla sua scheda. Un personaggio eliminato resta nel cestino per 24 ore e si può ripristinare da **Altro → Impostazioni → Cestino**; se nel frattempo il suo nome è stato preso, torna con " 2" dopo il nome.

## Avvisi

Alla registrazione la casa controlla cosa potrebbe rendere difficile riconoscere la nuova statuina, e lo dice al passo di conferma:

- *Il colore è molto simile al pavimento / ai prati / alle pareti: potrei non vederlo bene.* La differenza rispetto alla casa vuota è piccola, quindi alcune parti della statuina potrebbero andare perse.
- *Compare e scompare: prova a spostarlo in un punto più libero.* La statuina è stata rilevata in meno della metà dei fotogrammi da quando è comparsa.
- *Sembra uguale a Marco: li distinguerò solo seguendoli.* La sua firma di colore è quasi uguale a quella di un personaggio già registrato.

Nessuno di questi avvisi impedisce la registrazione.

## Personaggi dello stesso colore e dubbi

Due statuine dello stesso colore si distinguono solo seguendole. La continuità del movimento le tiene separate: se solo una delle due viene presa e appoggiata altrove, dev'essere per forza quella, visto che l'altra è rimasta in vista.

Quando il filo si perde (prese tutte e due insieme, le due si toccano, una ricompare lontano, oppure la casa è appena partita) la traccia diventa **incerta**. La casa allora:

- chiede su tutti i telefoni, con una domanda come "In cucina c'è Marco o Leo?", un pulsante per ogni nome e **Tutti e due**, se le statuine si toccano;
- chiede anche ad alta voce, se la sua loquacità lo permette, e subito dopo ascolta la risposta da sola, senza il tasto **Parla**: basta dire il nome, oppure "tutti e due". Vale la prima risposta, a voce o da un telefono;
- se non arriva una risposta entro 60 secondi, tiene la sua ipotesi migliore, segnata come incerta: un **?** sulla piantina, e "Marco è in cucina. Almeno credo." nelle risposte a voce.

**Un nome non sta mai in due posti.** Prima di chiedere, la casa toglie dai candidati chi è già riconosciuto da un'altra parte della casa (tranne se una mano è passata dov'era), chi è stato visto per l'ultima volta lontano da lì senza che una mano ci sia passata, chi ha una taglia troppo diversa da quella che vede (più di quattro volte più grande o più piccola di tutte le sue pose; una statuina non è mai l'auto, l'auto non è mai una statuina) e l'auto fuori dal garage se non ne è certa. Se ne resta uno solo, la casa decide da sola senza chiedere: se Rossellina è in cucina, la statuina nuova in soggiorno che somiglia a Rossellina e a Rosaria è Rosaria. Se non ne resta nessuno (Rossellina è in cucina e Rosaria in camera), quella statuina non è nessuna delle due: la casa la tratta come un nuovo arrivato e chiede chi è. Se il dubbio si scioglie mentre la domanda è aperta (Rossellina ricompare in cucina), la domanda viene ritirata dai telefoni e la casa smette di ascoltare.

La stessa regola vale per quello che la casa mostra e dice. Se due presenze arrivano con lo stesso nome (per esempio una ancora in mano e una appena posata), il nome resta a quella in vista. Un nome dato dalla webapp, a voce o dal citofono resta dove è stato dato e sparisce da dove era subito, anche nel mezzo secondo in cui la visione, che gira in un processo separato, non lo sa ancora; poi i nomi tornano a essere quelli della visione, che non li rimette più su una presenza a cui li ha tolti.

**L'auto sta in garage.** L'auto non viene mai proposta per una statuina, né per qualcosa fuori dal garage, a meno che la casa non ne sia certa: grande come un'auto, ferma e ben visibile da 10 secondi.

Sulla stessa statuina richiede al massimo ogni 30 secondi. Una risposta, una registrazione o un ingresso dal citofono **confermano** un'identità: una statuina confermata la mantiene finché la casa riesce a seguirla.

## Un nuovo arrivato

Quando è sicura che c'è qualcosa che non riconosce, la casa lo chiede subito, a voce e su tutti i telefoni insieme. Dice anche che cosa le sembra, così lo si può correggere: "In soggiorno vedo una persona nuova, giusto? Come si chiama?". A una persona chiede il nome, senza proporre quelle registrate. Per un animale, un'auto o un oggetto propone i registrati dello stesso tipo che non sono già in casa ("In giardino vedo un cane nuovo, giusto? È Fido o Birba, o come si chiama?"); per un animale non propone mai una persona. **L'auto sta in garage**: dentro una stanza della casa non chiede mai di un'auto nuova (la chiama "un oggetto"); per qualcosa grande come un'auto fuori dal garage (più spesso una luce, un'ombra o statuine ammucchiate) la casa non chiede niente, a meno di esserne certa: vista ferma e ben visibile per almeno 10 secondi.

**A voce**, senza il tasto Parla, si può rispondere con qualsiasi frase. La casa la capisce e risponde di conseguenza:

| Risposta | La casa |
|---|---|
| un nome nuovo ("Marco", "si chiama Marco", "è mio fratello Andrea") | chiede conferma del nome insieme al tipo ("Una persona di nome Marco, giusto?"), poi "Piacere, Marco!" |
| un nome già registrato ("è Viola"), anche sentito con una lettera sbagliata ("rosario" per Rosaria) | lo assegna e ne impara i colori, se gli somigliano. Se quel personaggio è in vista in un altro punto della casa, il nuovo arrivato non c'era: "Viola è già in soggiorno: allora qui ho visto male" |
| "tutti e due", "entrambi", "sia Viola che Rosaria", "Viola e Rosaria" | due statuine a contatto sono una sola macchia: le segna presenti tutte e due, una nascosta dietro l'altra finché una mano non le separa ("Ah, sono in due: Viola e Rosaria!"). Se uno dei due è in vista altrove, qui c'è solo l'altro; se i nomi non sono stati detti e la domanda non ne proponeva, chiede quali sono |
| il tipo giusto ("no, è un cane", "è un gatto e si chiama Micia") | corregge il tipo e chiede il nome, se manca |
| sì o no | dopo un sì chiede il nome, dopo un no chiede che cos'è |
| "non c'è nessuno", "è la mia mano", "è un'ombra" | dimentica quello che aveva visto: la macchia entra nella casa vuota e lì per 30 secondi non nasce niente. Per due minuti in quella stanza vale il doppio controllo più severo |
| "non lo so", "lascia perdere" | lascia la domanda ai telefoni |
| "aspetta" | aspetta e ascolta di nuovo |
| un comando o una domanda ("che ore sono?") | risponde, poi chiede di nuovo il nome |
| una battuta o altro | chiede di nuovo il nome; la seconda volta lascia stare |
| un discorso che non parla del nuovo arrivato ("...per migliorare la velocità del modello") | come una battuta: il tipo che dice il modello linguistico conta solo se la frase lo nomina |
| silenzio | chiede ancora una volta, poi lascia la domanda ai telefoni. Se due nuovi arrivati di fila non ricevono nessuna risposta, per tre minuti la casa li chiede solo sui telefoni |

Le risposte brevi e comuni le capiscono delle regole, all'istante. Le altre frasi le classifica il modello linguistico locale (capitolo 8). Sulla scheda servono da 3 a 6 secondi, e intanto la casa dice "Fammi pensare..." e i tasti respirano.

- **Dal telefono** si tocca un nome sulla domanda, **Tutti e due** quando i nomi proposti sono più di uno, oppure si sceglie **Uno già noto…** fra tutti i personaggi e gli oggetti che la casa conosce e si tocca **Questo** (il nome si sposta lì da dov'era), oppure si scrive un nome nuovo, si sceglie il tipo e si tocca **Aggiungi**. **Non c'è niente** fa dimenticare alla casa quello che aveva visto.
- Vale la prima risposta, da uno dei due canali; quando arriva, la casa smette di ascoltare.
- Se quello di cui chiede sparisce prima della risposta, la domanda viene ritirata dai telefoni e la casa smette di ascoltare.

Con un nome nuovo la casa crea il personaggio, con il tipo detto (o intuito) e i colori che vede. Con un nome già registrato aggiorna subito i colori di quel personaggio con quelli che vede in quel momento, se gli somigliano, così la volta dopo lo riconosce da sola; una risposta data sulla macchia sbagliata dà il nome ma non cambia l'aspetto del personaggio. Una registrazione in corso dalla webapp ha la precedenza: mentre aspetta il suo personaggio, la casa non fa questa domanda.

## Durante la festa

Mentre la casa fa festa le luci colorate cambiano a ogni battuta, e la webcam vede colori che non sono quelli dei personaggi. Per questo la casa **sospende il riconoscimento** dall'inizio della festa alla fine dello spettacolo di luci: le presenze restano dove erano e con il loro nome, non nasce niente di nuovo, non sparisce niente, la casa non fa domande e non annuncia spostamenti. L'immagine in **Diretta** continua ad aggiornarsi.

A festa finita la casa misura di nuovo la luce di ogni stanza, aspetta che le luci si fermino e riprende quello che vede, come all'avvio. Durante la festa qualcuno potrebbe aver spostato un personaggio, quindi per ognuno vale come se una mano fosse passata dov'era: un personaggio spostato viene ritrovato e il suo nome lo segue anche lontano da dov'era; se la casa non lo riconosce, chiede chi è.

## Correggere la casa dalla webapp

- **Chi è.** Sulla scheda di una presenza (pagina **Casa**), **Chi è?** o **È un altro: cambia** apre l'elenco di tutti i personaggi e gli oggetti che la casa conosce, con un nome nuovo in fondo. Scegliendo un personaggio già noto, il nome passa a quella presenza e lascia quella che lo aveva per errore; la casa impara quell'aspetto come una delle sue pose anche se è diverso dal solito (una luce diversa, un personaggio sdraiato), fino a una distanza di colore di 0,6 invece di 0,45, e lo ricorda dopo un riavvio. Una risposta a voce, che potrebbe riguardare la macchia sbagliata, resta più prudente.
- **Elemento non riconosciuto.** Una statuina che la casa non ha visto posare, o che ha preso per la casa vuota, non viene seguita. **Elemento non riconosciuto**, sulla pagina **Casa** (toccando il punto sulla piantina) o in **Diretta** (toccandolo nell'immagine), dice alla casa dov'è: intorno a quel punto, per circa 3 cm, la casa riprende la casa vuota com'era stata salvata, così quello che c'è torna diverso da lei, ne fa una presenza seguita da subito e chiede chi è. Lì si annullano anche i "non c'è niente" detti poco prima. Se lì non vede niente di diverso dalla casa vuota (l'elemento c'era già quando è stata salvata), basta spostarlo un poco e riprovare.

## La luce della sala

La webcam ha esposizione e colori bloccati sulla luce in cui è stata salvata la casa vuota. Quando la luce della sala cambia molto (una luce accesa o spenta), l'immagine resta più scura o più chiara della casa vuota: sotto il 70% o sopra il 143% per 5 secondi, la webcam si regola di nuovo da sola. Misurato su casa1: la luce della stanza spenta porta l'immagine al 45-57%, mentre gli scenari della casa (cinema, notte) non scendono sotto il 95%, quindi non la fanno regolare.

Mentre la webcam si regola (circa 10 secondi, senza immagini) le presenze restano dove sono sulla piantina. Prima sparivano tutte e tornavano, e la casa salutava e riaccoglieva tutti ("arrivederci Viola, a presto Mister Brown"). Se una regolazione non riporta l'immagine vicina alla casa vuota (una sala più buia di quanto la webcam riesca a seguire), la successiva aspetta il doppio, fino a un quarto d'ora: su casa1 la webcam si regolava ogni 70 secondi sempre con gli stessi valori.

Con una luce molto diversa le pareti e i bordi dei mobili cambiano aspetto e possono sembrare grandi macchie che entrano dai bordi, cioè mani. Una mano vera se ne va: "mani" che restano senza interruzione per 30 secondi non sono mani. Non impediscono più alla webcam di regolarsi; e se la luce è comunque vicina a quella della casa vuota, entrano nella casa vuota così come si vedono adesso (tranne dove c'è un personaggio). Prima la casa restava bloccata: con le "mani" sempre presenti non seguiva più gli spostamenti e scendeva a 3 immagini al secondo.

## Privacy

- **Tutto ciò che sta intorno alla casa è sfocato** in ogni immagine che lascia la scheda (il banco, i visitatori, i loro telefoni), appena la casa sa dove si trova la base.
- **Il bagno è sfocato** di serie in ogni immagine che lascia la scheda: la diretta, le istantanee, le catture per i dataset e le sequenze registrate. Si può togliere in **Impostazioni → Bagno sfocato nella diretta**. L'area sfocata è l'ingombro del bagno a livello del pavimento e alla cima delle sue pareti, più un margine, così all'interno non si vede niente, a qualsiasi altezza. L'area viene calcolata dalla calibrazione. Prima della calibrazione la casa presume che la webcam sia montata come da progetto e sfoca un'area più ampia attorno a dove dovrebbe trovarsi il bagno: calibra prima di aprire la casa ai visitatori, così la sfocatura si adatta esattamente al bagno.
- Il microfono registra solo mentre la casa ascolta; l'audio resta in memoria e non viene mai salvato.
- Niente lascia la scheda: niente internet, niente cloud. Le posizioni vengono conservate per 24 ore e gli eventi per 7 giorni.

## Dataset e registrazioni

La casa non ha bisogno di addestramento, ma si possono raccogliere immagini per altri progetti, per esempio per addestrare un rilevatore. In **Altro → Calibrazione → Dataset**:

- **Cattura** salva il fotogramma attuale; **Raffica (10)** ne salva dieci di fila. Ogni immagine (JPEG 640 × 480, bagno sfocato) riceve etichette automatiche: un riquadro attorno a ogni oggetto trovato dalla visione, con il tipo e il nome della sua traccia; le mani vengono escluse.
- **Scarica il dataset** esporta uno zip con `images/`, `coco/annotations.json` (formato COCO, categorie person, dog, cat, animal, car, object, con il nome del personaggio come attributo) e `yolo/` (`classes.txt` e un file di etichette per immagine nel formato YOLO).
- **Registra una sequenza (60 s)** salva in `var/recordings/rec-DATE-TIME/` ogni fotogramma analizzato come JPEG sfocato, un file `detections.jsonl` con gli oggetti e le tracce di ogni fotogramma, la calibrazione e il riferimento della casa vuota. Sequenze come queste servono a provare l'inseguimento su un PC: `.venv/bin/python scripts/replay.py var/recordings/rec-DATE-TIME` fa girare il codice di visione attuale sui fotogrammi registrati e stampa quello che vede accanto a quello che la casa aveva visto allora (`--video out.mp4` scrive anche i fotogrammi con le tracce disegnate).

Avanti: [voce](08-voce.md).
