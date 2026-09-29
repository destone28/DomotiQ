# 7. Riconoscimento e identità

La casa riconosce persone, animali, l'auto e gli oggetti con la **visione artificiale classica**, senza addestrare un modello. Vista dal palo, la base di una statuina misura appena una dozzina di pixel alla risoluzione di analisi, il numero dei personaggi non ha limiti e i visitatori ne aggiungono di nuovi durante la fiera. Un rilevatore addestrato avrebbe bisogno di centinaia di immagini etichettate per ogni nuovo personaggio; il metodo classico registra un personaggio in pochi secondi e sta in un solo core della CPU della UNO Q.

Il **machine learning** si usa in un solo punto: quando un personaggio viene registrato con una foto, un rilevatore di oggetti **YOLOX-Nano** addestrato sul dataset COCO guarda la foto e propone che tipo di cosa è.

## Come vede la casa

La visione gira in un processo separato, così un fotogramma lento o un problema della webcam non rallentano mai la webapp o la voce; se si ferma, riparte da sola.

1. **Acquisizione.** La Logitech C270 fornisce fotogrammi MJPEG; la casa li analizza a 640 × 480, circa 10 al secondo. Dopo la calibrazione, esposizione, bilanciamento del bianco e guadagno sono bloccati, così i colori non si spostano quando statuine e luci colorate vanno e vengono.
2. **La casa vuota.** Alla calibrazione la casa salva la mediana di 20 fotogrammi della casa vuota, arredi compresi. Tutto ciò che è diverso da questa immagine è una statuina, l'auto, un oggetto o la mano di un visitatore.
3. **Differenza nello spazio colore Lab, con correzione della luce stanza per stanza.** Le luci delle stanze della casa sono colorate, e la luce del padiglione cambia. Ogni pixel viene corretto con i guadagni della luce della sua stanza: un guadagno per canale di colore, stimato sul pavimento libero della stanza come il rapporto più frequente rispetto alla casa vuota (così una statuina o l'auto non lo falsano), e, quando sono possibili due valori, quello più vicino al fotogramma precedente. Attraverso una porta il guadagno passa gradualmente da una stanza all'altra. La casa avvisa la visione ogni volta che cambia una luce.
4. **Le ombre non contano.** Un'ombra è più scura ma mantiene il colore del pavimento.
5. **Maschere.** Le zone che non sono pavimento vengono ignorate: le applique, la chioma dell'albero, il palo della webcam e la cima delle pareti, ciascuna proiettata all'altezza a cui si trova davvero.
6. **Oggetti.** Dopo una pulizia morfologica, ogni macchia connessa diventa un oggetto con la sua area in mm², il suo colore mediano e un istogramma del suo colore, il suo allungamento, e i suoi punti più vicino e più lontano rispetto al punto sotto la webcam.
7. **Dove si trova (parallasse).** La webcam vede dall'alto una statuina in piedi, che quindi appare allungata in direzione opposta al punto sotto l'obiettivo: il suo punto più vicino è la punta dei piedi, quello più lontano la nuca. Abbassando la testa di tutta l'altezza della statuina si ottiene anche la posizione dei piedi, così una statuina viene piazzata correttamente anche quando i piedi sono nascosti dietro una parete. L'auto, che è una scatola più che una statuina, viene piazzata al centro di ciò che si vede. Su scene di prova sintetiche l'errore di posizione resta sotto i 12 mm.
8. **Mani.** Una macchia grande che entra dal bordo dell'immagine o della base è la mano di un visitatore (tranne al portone del garage, da cui entra l'auto). Un braccio tagliato in due dalla cima di una parete viene riunito nella stessa mano.
9. **Inseguimento.** Gli oggetti vengono abbinati alle tracce del fotogramma precedente con il metodo ungherese, su una distanza che combina posizione, colore e dimensione. Una cosa che salta di più di 90 mm tra due fotogrammi non è la stessa; una traccia che non si vede per 1,5 secondi scompare.
10. **Portato in mano.** Quando una statuina sparisce sotto una mano, la sua traccia diventa *portata* e mantiene la sua identità; quando la statuina ricompare vicino alla mano, o dove la mano la lascia, è lo stesso personaggio. Una statuina tenuta in mano per più di 60 secondi viene dimenticata e riconosciuta di nuovo dal suo colore quando la si appoggia.
11. **Chi è.** Ogni identità registrata ha una **firma di colore**: un istogramma degli assi di colore a\* e b\* dello spazio Lab (dove la luminosità è tenuta a parte, così un'ombra o una luce più fioca cambiano poco) più il colore mediano. Per le statuine bianche, grigie e nere la luminosità pesa di più, perché è l'unica cosa che le distingue. Le identità sono uniche, quindi l'assegnazione delle identità alle tracce si risolve per tutte insieme; un'identità viene data dopo quattro fotogrammi concordi. Mentre una statuina è seguita con sicurezza, la sua firma si aggiorna lentamente con quello che vede la webcam.
12. **In quale stanza.** La stanza è quella sotto il punto in cui la statuina poggia, con 15 mm di tolleranza sulle porte, così una statuina su una soglia non salta avanti e indietro tra due stanze.

Il risultato è un elenco di tracce, ognuna con una posizione in millimetri, una stanza, un tipo e, quando è nota, un'identità. Il resto della casa (luci, regole, voce, webapp) lavora su questo elenco.

## Tipi di cose

Ogni identità ha un tipo: **persona**, **cane**, **gatto**, **animale** (qualsiasi altro animale domestico), **auto** o **oggetto**. Le regole possono filtrare per tipo; in una regola *animale* comprende anche cani e gatti. Gli arredi della casa sono fissi e fanno parte della casa vuota; un oggetto nuovo messo nella casa (una sedia, un pallone, una valigia) è un'identità di tipo *oggetto*.

Quando parte una registrazione, la casa propone un tipo:

- **Dalla foto**, se ne è stata scattata una: YOLOX-Nano gira sulla scheda con ONNX Runtime e cerca le 80 classi di COCO; decide il rilevamento sicuro più grande. *person* dà una persona, *dog* un cane, *cat* un gatto; *car*, *truck* e *bus* danno un'auto; *bird*, *horse*, *sheep*, *cow*, *elephant*, *bear*, *zebra*, *giraffe* e *teddy bear* danno un animale; ogni altra classe dà un oggetto, con un nome proposto (per esempio *sedia*, *pallone*, *valigia*).
- **Senza foto**, da dimensione e forma viste dall'alto: una macchia grande è un'auto, una alta e stretta una persona, una piccola, allungata e bassa un animale, tutto il resto un oggetto.

La proposta va sempre confermata da chi registra.

## Registrare un personaggio

Chiunque può registrare personaggi, animali, auto e oggetti, in tre modi.

### Dalla webapp

1. **Altro → Personaggi e oggetti → + Aggiungi**, oppure tocca una statuina sconosciuta nella schermata **Casa** e poi **Registra**.
2. Scrivi il **Nome**. Se vuoi tocca **Scatta o scegli una foto**: basta una foto di fronte; compare nell'elenco e serve a indovinare il tipo. Il telefono la riduce a 1024 pixel prima di inviarla. Tocca **Avanti**.
3. *Appoggialo in un punto libero della casa: lo sto cercando…* La casa cerca qualcosa che vede ma non conosce. Se c'è esattamente un candidato lo prende; se ce n'è più di uno dice *Vedo più cose nuove: tocca quella giusta sulla piantina.*; se non ce n'è nessuno aspetta. Dopo due minuti e mezzo senza risultato ci rinuncia: *Non ho trovato niente di nuovo. Riprova.*
4. *Trovato! Che cos'è?* La casa mostra la sua ipotesi (*Mi sembra: cane*, con un nome proposto per gli oggetti), gli eventuali [avvisi](#avvisi) e i sei tipi. Scegli e tocca **Salva**.
5. *Marco è registrato. D'ora in poi lo riconosco.*

### Con il citofono

1. Un visitatore preme **Citofono** sul totem. Suona un campanello e la casa chiede "Chi è?" / "Who is it?".
2. **Un nome registrato**: "Ciao Marco, entra pure!". La prima statuina di tipo persona che, nei 60 secondi successivi, arriva dal vialetto in soggiorno passando dalla porta d'ingresso riceve quel nome. Se il nome appartiene a qualcuno che è già dentro, la casa lo dice ("Ma Marco è già in cucina!"). Se la webcam riconosce chiaramente nella statuina che entra qualcun altro, la casa lo dice ("Mmm, a me sembri Sofia, non Marco!") e mantiene l'identità che vede.
3. **Un nome nuovo**: "Ho capito Marco, giusto?" Dopo un *sì*: "Piacere, Marco! Entra dalla porta." La prima statuina che la casa non conosce e che, nei 60 secondi successivi, entra in soggiorno dalla porta d'ingresso diventa Marco, senza altri passaggi: il tipo che la casa ha indovinato si può cambiare in seguito nella scheda del personaggio.
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
- Chiunque può rinominare o eliminare un personaggio dalla sua scheda. Un personaggio eliminato resta nel cestino per 24 ore e lo staff può ripristinarlo; se nel frattempo il suo nome è stato preso, torna con " 2" dopo il nome.

## Avvisi

Alla registrazione la casa controlla cosa potrebbe rendere difficile riconoscere la nuova statuina, e lo dice al passo di conferma:

- *Il colore è molto simile al pavimento / ai prati / alle pareti: potrei non vederlo bene.* La differenza rispetto alla casa vuota è piccola, quindi alcune parti della statuina potrebbero andare perse.
- *Compare e scompare: prova a spostarlo in un punto più libero.* La statuina è stata rilevata in meno della metà dei fotogrammi da quando è comparsa.
- *Sembra uguale a Marco: li distinguerò solo seguendoli.* La sua firma di colore è quasi uguale a quella di un personaggio già registrato.

Nessuno di questi avvisi impedisce la registrazione.

## Personaggi dello stesso colore e dubbi

Due statuine dello stesso colore si distinguono solo seguendole. La continuità del movimento le tiene separate: se solo una delle due viene presa e appoggiata altrove, dev'essere per forza quella, visto che l'altra è rimasta in vista.

Quando il filo si perde (prese tutte e due insieme, le due si toccano, una ricompare lontano, oppure la casa è appena partita) la traccia diventa **incerta**. La casa allora:

- chiede su tutti i telefoni, con una fascia come "In cucina c'è Marco o Leo?" e un pulsante per ogni nome;
- chiede anche ad alta voce, se la sua loquacità lo permette; per rispondere tieni premuto **Parla** e di' il nome;
- se non arriva una risposta entro 60 secondi, tiene la sua ipotesi migliore, segnata come incerta: un **?** sulla piantina, e "Marco è in cucina. Almeno credo." nelle risposte a voce.

Sulla stessa statuina richiede al massimo ogni 30 secondi. Una risposta, una registrazione o un ingresso dal citofono **confermano** un'identità: una statuina confermata la mantiene finché la casa riesce a seguirla.

## Privacy

- **Il bagno è sempre sfocato** in ogni immagine che lascia la scheda: la diretta, le istantanee, le catture per i dataset e le sequenze registrate. L'area sfocata è l'ingombro del bagno a livello del pavimento e alla cima delle sue pareti, più un margine, così all'interno non si vede niente, a qualsiasi altezza. L'area viene calcolata dalla calibrazione. Prima della calibrazione la casa presume che la webcam sia montata come da progetto e sfoca un'area più ampia attorno a dove dovrebbe trovarsi il bagno: calibra prima di aprire la casa ai visitatori, così la sfocatura si adatta esattamente al bagno.
- Il microfono registra solo mentre la casa ascolta; l'audio resta in memoria e non viene mai salvato.
- Niente lascia la scheda: niente internet, niente cloud. Le posizioni vengono conservate per 24 ore e gli eventi per 7 giorni.

## Dataset e registrazioni

La casa non ha bisogno di addestramento, ma lo staff può raccogliere immagini per altri progetti, per esempio per addestrare un rilevatore. In **Altro → Calibrazione → Dataset**:

- **Cattura** salva il fotogramma attuale; **Raffica (10)** ne salva dieci di fila. Ogni immagine (JPEG 640 × 480, bagno sfocato) riceve etichette automatiche: un riquadro attorno a ogni oggetto trovato dalla visione, con il tipo e il nome della sua traccia; le mani vengono escluse.
- **Scarica il dataset** esporta uno zip con `images/`, `coco/annotations.json` (formato COCO, categorie person, dog, cat, animal, car, object, con il nome del personaggio come attributo) e `yolo/` (`classes.txt` e un file di etichette per immagine nel formato YOLO).
- **Registra una sequenza (60 s)** salva in `var/recordings/rec-DATE-TIME/` ogni fotogramma analizzato come JPEG sfocato, un file `detections.jsonl` con gli oggetti e le tracce di ogni fotogramma, la calibrazione e il riferimento della casa vuota. Sequenze come queste servono a provare l'inseguimento su un PC: `.venv/bin/python scripts/replay.py var/recordings/rec-DATE-TIME` fa girare il codice di visione attuale sui fotogrammi registrati e stampa quello che vede accanto a quello che la casa aveva visto allora (`--video out.mp4` scrive anche i fotogrammi con le tracce disegnate).

Avanti: [voce](08-voce.md).
