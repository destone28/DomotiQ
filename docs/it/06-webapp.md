# 6. La webapp

Ogni casa serve la propria webapp direttamente dalla scheda. Non ha bisogno di internet né di installare niente: la apre qualsiasi browser di un telefono collegato al Wi-Fi della casa. È fatta di semplice HTML, CSS e JavaScript senza librerie esterne, è in italiano e in inglese, e ha un tema chiaro e uno scuro che seguono le impostazioni del telefono. Lo stato della casa arriva in tempo reale attraverso un WebSocket, quindi quello che vedi cambia non appena qualcosa si muove nella casa.

## Aprirla

- **In fiera**: inquadra i due QR del cartello accanto alla casa. Il primo fa entrare nel Wi-Fi `DomotiQ-CasaN`, il secondo apre `http://10.42.N.1/`. Funzionano anche i nomi `http://casaN.lan/` e `http://casaN.local/`, ma l'indirizzo numerico funziona sempre.
- **In laboratorio**: `http://casaN.local/`, con la scheda sul tuo Wi-Fi.
- Sui telefoni la pagina si può aggiungere alla schermata Home; da lì si apre come un'app.
- La prima volta che un telefono la apre, la casa lo saluta a voce e compare una scheda che chiede il nome e invita ad aggiungere un personaggio (vedi il [capitolo 8](08-voce.md#parlare-senza-premere-parla)).
- La webapp usa il semplice `http://`. Non ci sono notifiche di sistema (richiederebbero HTTPS); le foto si scattano con la fotocamera del telefono attraverso il normale selettore dei file, che funziona anche senza HTTPS.

## Chi può fare cosa

| Tutti | Staff (PIN) |
|---|---|
| Casa, Diretta, Comandi, Eventi | Calibrazione |
| Regole: creare, modificare, attivare e disattivare, eliminare | Diagnostica |
| Personaggi e oggetti: registrare, rinominare, eliminare | Impostazioni, compresi ora, backup, cestino e spegnimento |
| Rispondere alle domande della casa | Attivare e disattivare la simulazione |
| Cartello da stampare, Tabellone per lo stand, Informazioni | Far dire una frase alla casa |

Il **PIN dello staff** viene scelto quando si installa la casa ed è pensato per essere lo stesso nelle due case. Scrivilo in **Altro → PIN dello staff** e tocca **Accesso staff**. Dopo cinque tentativi sbagliati il telefono deve aspettare un minuto (*Troppi tentativi: aspetta un minuto*); dopo dieci tentativi sbagliati da qualsiasi telefono in dieci minuti, gli accessi si fermano per tutti per un minuto, poi due, quattro, fino a un quarto d'ora, così il PIN non si indovina per tentativi (chi è già entrato continua a lavorare, e il PIN si può sempre cambiare dalla scheda). L'accesso staff dura 12 ore su quel telefono, finché non tocchi **Esci dallo staff** o finché l'applicazione non si riavvia. A tutti gli altri le pagine dello staff mostrano *Solo per lo staff*.

Tutti possono cambiare le regole e i personaggi, ed è voluto: questa è una casa per giocare. Ogni modifica viene registrata con l'ora, il telefono e un soprannome facoltativo, le cose eliminate restano in un cestino per 24 ore, e lo staff può ripristinarle (vedi [Regole](09-regole.md#chi-può-cambiare-le-regole)).

## Cosa hanno in comune tutte le schermate

- **Barra in alto**: il nome della casa, tre pallini di stato (**Microcontrollore**, **Webcam**, **Audio**: verdi quando funzionano, rossi quando no; mentre la simulazione è attiva compare un quarto pallino) e il pulsante **IT / EN**, che cambia la lingua della webapp solo su questo telefono. La prima volta la webapp sceglie la lingua del telefono. La lingua in cui parla la casa è un'impostazione diversa, in **Comandi**.
- **Barra in basso**: **Casa**, **Diretta**, **Comandi**, **Personaggi** (personaggi e oggetti), **Altro**. **Eventi** è la prima voce di **Altro**. Ogni pagina scorre fino in fondo, sopra la barra.
- **Fasce di allarme**: mentre una regola di allarme è attiva (qualcuno nel locale tecnico, troppe persone in bagno, un intruso), una fascia rossa in cima a ogni schermata riporta il nome della regola, chi e dove; sulla piantina la stanza è contornata di rosso. La **✕** chiude la fascia su tutti i telefoni: torna solo se l'allarme finisce e si ripresenta. Le notifiche brevi si chiudono con un tocco.
- **Domande della casa**: quando la casa non è sicura, una fascia fa una domanda, per esempio "In cucina c'è Marco o Leo?", con un pulsante per ogni risposta. Può rispondere qualsiasi telefono; vale la prima risposta e la fascia sparisce ovunque. La casa fa la domanda anche ad alta voce e ascolta la risposta da sola, senza il tasto Parla; vale la prima risposta, a voce o da un telefono. Quando chiede chi è un nuovo arrivato, la fascia ha anche un campo per scrivere un nome nuovo, con il pulsante **Aggiungi** (vedi il [capitolo 7](07-riconoscimento-e-identita.md#un-nuovo-arrivato)).
- **Sottotitoli**: tutto quello che la casa dice compare come sottotitolo in fondo a ogni telefono, anche quando la casa è impostata su *Silenziosa*.
- **Notifiche**: brevi messaggi compaiono in basso (un personaggio registrato, la grigliata pronta, la notifica di una regola). Le notifiche di allarme fanno anche vibrare il telefono, dove il browser lo permette.
- **Connessione persa**: se il telefono perde la casa, una fascia dice *Connessione con la casa persa: riprovo…* e la webapp si ricollega da sola.
- **Orologio**: quando la casa non conosce l'ora, il primo telefono che apre la webapp la imposta (*Ora della casa impostata da questo telefono*). Quando la conosce, i telefoni dei visitatori non la toccano più (uno con l'orologio sbagliato la sposterebbe per tutti): la corregge lo staff con **Usa l'ora di questo telefono**, oppure la si dice a voce.
- **Soprannome**: la prima volta che modifichi una regola o registri un personaggio, la webapp chiede *Come ti chiami? (facoltativo, compare nel registro)*. Puoi cambiarlo in **Altro → Il tuo soprannome**. Ogni telefono ha anche un identificativo automatico.

## Casa

<img src="../images/screens/it/home.png" alt="Casa" width="260">

La casa virtuale: una piantina ricavata dal modello CAD, con in basso il vialetto, dove stanno i visitatori.

- Stanze, pareti, porte e arredi; ogni luce di stanza brilla con il suo colore e il suo effetto del momento.
- La temperatura del termostato (sulla credenza) e l'umidità del bagno; un contatore per ogni stanza in cui c'è qualcuno.
- Ogni personaggio con la sagoma del suo tipo (persona, cane, gatto, animale, auto, oggetto), nel suo colore e con il suo nome; un **?** segna un personaggio su cui la casa non è sicura.
- L'auto, le fiamme sul barbecue quando è acceso, un pallino sul totem quando qualcuno è al citofono, i contorni rossi delle stanze in allarme.

Sotto la piantina, delle schede riassumono la casa: le persone presenti, **Termostato** (temperatura, umidità, *Climatizzatore acceso* o *Riscaldamento acceso*), **Bagno** (umidità, *Doccia in corso*), **Auto** (*appena arrivata*, *parcheggiata*, *appena uscita*, *non c'è*), **Scenario**, ed etichette per **Festa**, **Barbecue** e *Qualcuno al citofono*.

In fondo, l'elenco di tutto ciò che la casa vede, con nome (oppure *Ospite* per una persona sconosciuta, *Sconosciuto* per qualsiasi altra cosa), tipo e stanza. Tocca un personaggio, sulla piantina o nell'elenco, per aprire la sua scheda: foto o sagoma, tipo, stanza e, quando c'è un dubbio, *Non sono sicura di chi sia*. Un personaggio sconosciuto ha un pulsante **Registra** che avvia la registrazione con quella statuina già scelta.

## Diretta

<img src="../images/screens/it/live.png" alt="Diretta" width="260">

*Diretta dalla webcam*: l'immagine della webcam, circa 5 fotogrammi al secondo. L'interruttore **Nomi e stanze** scrive il nome e la stanza sopra ogni personaggio. Sulla scheda, prima che l'immagine arrivi a qualsiasi telefono, viene sfocato tutto ciò che sta intorno alla casa e, di serie, il bagno (vedi **Impostazioni**).

Quando la webcam manca per più di qualche secondo la schermata dice *La webcam non è collegata.*, e la scritta sparisce da sola quando torna; mentre la simulazione è attiva mostra un disegno della casa con la scritta *SIMULAZIONE - SIMULATION*.

## Comandi

<img src="../images/screens/it/commands.png" alt="Comandi" width="260">

- **Festa!**: 20 secondi di musica da ballare composta dal codice stesso della casa, con uno spettacolo di luci su tutti i Pixels. Prima della festa successiva c'è una pausa di 30 secondi.
- **Barbecue** / **Spegni barbecue**: avvia o ferma la ventola del barbecue.
- **Scenari**: Normale, Cinema, Relax, Notte, Via (vedi il [capitolo 9](09-regole.md#scenari)).
- **Luci**: scegli una stanza o *Tutte le stanze*, un colore tra dieci, un effetto (*Fisso*, *Respiro*, *Lampeggio*, *Onda*, *Arcobaleno*, *Scintille*, *Fuoco*) e una luminosità, poi **Accendi**, **Spegni** o **Automatico**. Una luce accesa da qui dura due minuti, **Spegni** tiene la stanza al buio per un minuto, e **Automatico** restituisce subito la stanza alla casa. L'interruttore **Luci che seguono le persone** attiva o disattiva per tutta la casa le luci che seguono chi si muove.
- **Voce della casa**: **Lingua della casa** (Italiano, English), **Loquacità** (Silenziosa, Normale, Chiacchierona), **Volume**, **Suona il campanello** (avvia la conversazione del citofono come se si fosse premuto il tasto del totem).
- **Fai dire alla casa** (*Solo per lo staff*): scrivi una frase e la casa la pronuncia.

Quando un comando non si può eseguire in quel momento (una festa è già in corso, o in pausa), un messaggio dice *Già in corso o in pausa, riprova tra poco*.

## Eventi

<img src="../images/screens/it/events.png" alt="Eventi" width="260">

Quattro schede:

- **Eventi**: chi è entrato o uscito da quale stanza (persone, animali e l'auto), l'auto, le regole scattate, le notifiche, termostato e doccia, i cambi di scenario e di lingua, i nuovi personaggi, barbecue, festa, e ogni comando arrivato da un telefono, con il soprannome.
- **Detto dalla casa**: ogni frase che la casa ha detto.
- **Modifiche**: il registro delle modifiche. Chi (soprannome oppure *Un telefono*) ha creato, modificato, eliminato o ripristinato quale regola o personaggio, ha cambiato le impostazioni o la calibrazione, con l'ora e l'identificativo del telefono.
- **Storico**: per ogni personaggio, le stanze in cui è passato nelle ultime 24 ore.

La casa conserva gli eventi per 7 giorni e le posizioni per 24 ore.

## Altro

### Regole

<img src="../images/screens/it/rules.png" alt="Regole" width="260">

L'elenco delle regole, ognuna con un interruttore per attivarla o disattivarla, e il pulsante **+ Nuova regola**. Toccando una regola si apre l'editor Quando / Se / Allora. Tutto sulle regole è nel [capitolo 9](09-regole.md).

### Personaggi e oggetti

<img src="../images/screens/it/identities.png" alt="Personaggi e oggetti" width="260">

L'elenco dei personaggi, degli animali, delle auto e degli oggetti registrati, con foto o sagoma, tipo, e dove si trovano adesso (*Ora: Cucina*, oppure *Non lo vedo*). **+ Aggiungi** avvia la registrazione guidata; toccandone uno si apre la sua scheda, dove puoi cambiare **Nome**, **Tipo**, **Pronuncia inglese (facoltativa)** e **Chi è (per le storie)** (una cosa per riga, come la si direbbe dopo il nome: *fa il medico*, *ama il jazz*, *ha paura dei ragni*; la casa le usa nelle storie e nelle risposte, vedi il [capitolo 8](08-voce.md#storie-ricordi-e-domande-libere)), oppure eliminarlo con **Elimina** (resta nel cestino per 24 ore). Vedi il [capitolo 7](07-riconoscimento-e-identita.md).

### Simulazione

<img src="../images/screens/it/sim.png" alt="Simulazione" width="260">

Personaggi virtuali da trascinare sulla piantina al posto delle statuine vere, sensori virtuali (temperatura e umidità del termostato e del bagno, distanza dal citofono) e i tre tasti del totem (**Parla** si tiene premuto come sul totem). Chiunque può aprire la pagina; per attivare o disattivare la simulazione serve il PIN dello staff. **Luci e voce vere in silenzio** tiene tranquilla la casa vera mentre fai le prove. Finché la simulazione è attiva, la casa ignora la webcam. Per togliere un personaggio virtuale, trascinalo fuori dalla casa.

### Calibrazione

<img src="../images/screens/it/calibration.png" alt="Calibrazione" width="260">

*Solo per lo staff.* I quattro angoli della base (dopo **Usa questi angoli** la casa regola da sola la luce e salva la casa vuota), il controllo della sovrapposizione, **Regola la luce e salva la casa vuota** e **Salva solo la casa vuota**. Mentre la casa lavora, una finestra con una rotellina dice cosa sta facendo e i pulsanti restano bloccati, così un'operazione non parte due volte; alla fine compare il risultato (vedi il [capitolo 5](05-collaudo.md#9-calibrazione-della-webcam)). In fondo ci sono gli strumenti per i dataset: **Cattura**, **Raffica (10)**, **Registra una sequenza (60 s)** e **Scarica il dataset** (vedi il [capitolo 7](07-riconoscimento-e-identita.md#dataset-e-registrazioni)).

### Diagnostica

*Solo per lo staff.* Si aggiorna ogni pochi secondi:

- **Scheda**: nome host e versione, tempo di attività, carico e temperatura della CPU, memoria, disco libero, numero di client Wi-Fi, orologio e provenienza dell'ora, dispositivo audio, voce (riconoscimento vocale e modello linguistico), webcam (dispositivo, fotogrammi al secondo, tempo di elaborazione, *da calibrare*, *spostata, rifare la calibrazione*).
- **Modulino**: lo stato del collegamento con il microcontrollore, la versione del protocollo del firmware, e un pallino verde o rosso per ogni modulo.
- Pulsanti: **Scansione I2C** (gli indirizzi che rispondono su ogni canale dell'Hub), **Prova audio**, **Prova microfono (3 s)**, **Scarica i registri** (mostra le ultime 500 righe del log dell'applicazione e le salva in un file).

### Impostazioni

<img src="../images/screens/it/settings.png" alt="Impostazioni" width="260">

*Solo per lo staff.*

- **Casa**: il nome della casa in italiano e in inglese; **Tasti montati al contrario**, per un totem montato al rovescio; **Bagno sfocato nella diretta**, acceso di serie.
- **Luci · Festa · Barbecue · Clima**: *Luminosità massima (%)*, *Limite di corrente dei Pixels (mA)*, *Luminosità delle luci che seguono*, *Spegnimento dopo (s)*, *Colore delle luci che seguono*, la *Durata (s)* della festa (10–60), *Durata della ventola (s)* (5–120), *Caldo: aumento sul riferimento (°C)*, *Doccia: aumento di umidità (%)*. Poi **Salva**. Luminosità e limite di corrente arrivano subito al microcontrollore.
- **Voce**: **Saluta i telefoni nuovi**, **Domande ai personaggi (modalità chiacchierona)** e *Una domanda ogni (s)* (vedi il [capitolo 8](08-voce.md#parlare-senza-premere-parla)).
- **PIN · Ora**: *PIN attuale* e *Nuovo PIN (4-8 cifre)*; un PIN nuovo chiude tutte le altre sessioni dello staff. **Usa l'ora di questo telefono** imposta l'orologio della casa.
- **Wi-Fi della casa**: il nome della rete e la *Password del Wi-Fi* (da 8 a 63 caratteri), confermata con il *PIN attuale*. **Salva** la scrive nell'hotspot; se l'hotspot è acceso riparte dopo un paio di secondi e tutti i telefoni, compreso quello dello staff, vanno ricollegati con la password nuova. Il cartello da stampare si aggiorna da solo: ristampalo.
- **Backup**: **Scarica il backup** (uno zip con regole, personaggi con le loro foto e impostazioni; mai la rete, il nome della casa, il PIN o la calibrazione della webcam), **Ripristina da un backup** (sostituisce regole, personaggi e impostazioni), **Regole di partenza** (sostituisce tutte le regole con quelle con cui la casa è partita).
- **Cestino**: regole e personaggi eliminati nelle ultime 24 ore, ognuno con **Ripristina**.
- **Sistema**: **Riavvia l'app**, **Riavvia la scheda**, **Spegni la scheda**, ognuno dopo *Sei sicuro?*.

### Cartello da stampare

<img src="../images/screens/sign.png" alt="Il cartello da stampare" width="360">

Una pagina A4 verticale, pronta da stampare, con il nome della casa e due QR: **1 Collegati alla rete** (con SSID e password scritti sotto) e **2 Apri la casa** (con l'indirizzo). Una nota in italiano e in inglese spiega cosa fare se il telefono si lamenta perché manca internet, e come usare i tasti del totem. Si apre su `/sign`.

### Tabellone per lo stand

`/board`: la piantina, la diretta, l'ultima frase detta e gli ultimi eventi, per un monitor o un tablet allo stand. Non ha comandi.

### Informazioni

Che cos'è il progetto, la riga dei crediti e le licenze di voci e modelli.

## Provare la webapp su un PC

L'intera casa gira su un PC in simulazione, senza nessun hardware. Da una copia del repository:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m domotiq --simulate
```

Poi apri `http://localhost:8080/`. La casa tiene i suoi dati in `var/` dentro la cartella del repository. Finché non si imposta un PIN, il PIN dello staff è `0000`; sulla scheda l'installer ne imposta sempre uno.

## Per i maker: le API

| Metodo e percorso | Uso |
|---|---|
| `GET /api/state` | lo stato completo |
| `WS /ws` | lo stato completo alla connessione, poi ogni cambiamento, le domande e i sottotitoli |
| `GET /api/stream` | diretta (MJPEG) |
| `GET/POST/PUT/DELETE /api/rules` | regole |
| `GET/PUT/DELETE /api/identities` | personaggi |
| `POST /api/commands/{name}` | party, grill, grill_stop, scene, light, lights_off, lights_auto, language, verbosity, volume, follow, intercom, say |
| `POST /api/confirm/{id}` | risposta a una domanda della casa |
| `POST /api/time` | ora da un telefono |
| `POST /api/staff/login` | dal PIN al token di sessione |
| `GET /api/events` | eventi |

Avanti: [riconoscimento e identità](07-riconoscimento-e-identita.md).
