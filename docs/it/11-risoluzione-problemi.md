# 11. Risoluzione dei problemi

Ogni voce riporta il sintomo, la causa probabile e la soluzione. Due strumenti aiutano in quasi tutti i casi:

- **Altro → Diagnostica** nella webapp: lo stato di scheda, microcontrollore, moduli, webcam, audio, voce e orologio.
- Il log dell'applicazione, via SSH:

  ```bash
  journalctl -u domotiq -f
  systemctl status domotiq domotiq-tts domotiq-llm --no-pager
  ```

## Scheda e accesso

### SSH non risponde su una scheda nuova, o smette di rispondere dopo un riavvio
**Causa.** Su un'immagine di fabbrica le chiavi host di SSH non esistono (le crea App Lab durante la sua prima configurazione); il log dice `sshd: no hostkeys available`. In più il servizio non è attivato all'avvio: se è stato solo fatto ripartire, dopo il primo riavvio (per esempio quello dopo l'aggiornamento del sistema) la porta 22 rifiuta la connessione.

**Soluzione.** Da una `adb shell`: `sudo ssh-keygen -A` e `sudo systemctl enable --now ssh`.

### *REMOTE HOST IDENTIFICATION HAS CHANGED* collegandosi a una scheda
**Causa.** Il PC si ricorda l'identità di un'altra scheda con lo stesso nome: una scheda nuova o reinstallata che si chiama come una già vista.

**Soluzione.** `bash scripts/add-pc.sh casaN` lo riconosce e chiede se dimenticare l'identità vecchia; a mano: `ssh-keygen -R casaN.local` (o l'indirizzo usato), poi di nuovo `add-pc.sh`. Se il messaggio compare con una scheda che non è cambiata, non dimenticare niente: qualcuno potrebbe fingersi la scheda.

### `casa1.local` non si risolve
**Causa.** Sull'immagine di fabbrica `avahi-daemon` è spento. Alcuni telefoni e PC non risolvono affatto i nomi `.local`.

**Soluzione.** `sudo systemctl enable --now avahi-daemon` (lo fa anche l'installer). Sull'hotspot usa `http://10.42.N.1/` oppure `casaN.lan`; l'indirizzo numerico funziona sempre.

### L'aggiornamento del sistema si ferma su una dipendenza ALSA
**Causa.** `alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)`: l'immagine prende i profili audio da `trixie-backports`, ma non la libreria ALSA di cui hanno bisogno.

**Soluzione.**

```bash
sudo apt-get install -y -t trixie-backports libasound2t64 libasound2-data libatopology2t64 alsa-ucm-conf
arduino-app-cli system update
```

### `arduino-app-cli system update` si rifiuta di partire, o si ferma a metà
**Causa.** Deve girare come utente `arduino`, non con `sudo` (chiama da solo `sudo apt-get`). Se lo lanci dentro `adb shell`, si ferma quando la sessione adb si chiude.

**Soluzione.** Lancialo come `arduino` da una sessione SSH, oppure staccato con `systemd-run --uid=arduino`.

### Durante l'aggiornamento del sistema la scheda non risponde più in rete
**Causa.** Alla fine l'aggiornamento scarica le immagini Docker di App Lab (cinque, qualche centinaio di MB: DomotiQ non le usa). Sulla scheda nuova, per una ventina di minuti, il PC non riusciva più nemmeno a fare ping.

**Soluzione.** Aspetta: con il cavo USB `adb shell` funziona e si può seguire il log. Quando ha finito, riavvia come dice il capitolo 1.

### SSH cade quando parte l'hotspot
**Causa.** È previsto: la scheda sta o sul Wi-Fi del laboratorio o sul suo hotspot.

**Soluzione.** Collega il PC a `DomotiQ-CasaN` e usa `ssh arduino@10.42.N.1` (oppure `bash scripts/add-pc.sh casaN 10.42.N.1` per avere un alias). `bash scripts/hotspot.sh off` riporta la scheda sul Wi-Fi del laboratorio.

## Installazione e aggiornamenti

### `install.sh` si ferma ai controlli
- *run this as the user arduino*: entra come `arduino`, non come root.
- *at least N MB free are needed*: libera spazio in `/home/arduino` (vedi `df -h /home/arduino`).
- *no internet*: la prima installazione scarica pacchetti e modelli; collega la scheda a una rete con internet.
- *the number of the house goes from 1 to 254*: `--house` vuole un numero da 1 a 254; senza, la casa è la 1.

### *checksum mismatch* per un modello
**Causa.** Un download si è interrotto o è stato alterato.

**Soluzione.** Rilancia `install.sh`: un file con il checksum sbagliato viene scaricato di nuovo.

### Il passo del firmware non riesce
**Causa.** *remoteocd or the OpenOCD configuration not found* vuol dire che il core `arduino:zephyr` non è installato come previsto; *loading the firmware failed* vuol dire che il caricamento sul microcontrollore non è andato a buon fine.

**Soluzione.** Controlla che `arduino-cli core list` mostri `arduino:zephyr` 1.0.0 e rilancia `install.sh`. La procedura manuale è in `firmware/domotiq_mcu/README.md`.

### Dopo `release.sh` il firmware o i nuovi pacchetti non sono cambiati
**Causa.** Senza `--install`, `release.sh` copia solo i file e riavvia `domotiq`.

**Soluzione.** Usa `bash scripts/release.sh casaN --install` (la scheda ha bisogno di internet), oppure lancia `install.sh` sulla scheda.

### L'audio ha smesso di funzionare dopo un aggiornamento manuale del sistema
**Causa.** L'installer blocca `alsa-ucm-conf`, `libasound2t64` e il kernel in uso e disattiva gli aggiornamenti automatici, perché niente cambi mentre la casa è in uso.

**Soluzione.** Non aggiornare il sistema di una casa che funziona. Se l'hai fatto, ripeti la correzione ALSA qui sopra e riavvia.

## Microcontrollore e moduli

### Il pallino *Microcontrollore* è rosso
**Subito dopo un riavvio di Linux** è normale per circa mezzo minuto. Lo sketch parte all'accensione senza aspettare Linux (così il relè del barbecue si spegne subito dopo un blackout); quando Linux si riavvia, il router resetta il microcontrollore mentre si ferma, e lo sketch riparte prima che il nuovo router sia in ascolto. La casa si accorge che il router risponde ma lo sketch no, resetta di nuovo il microcontrollore dalla sua linea di reset, e il pallino diventa verde circa 70 secondi dopo il riavvio. Il log dice *the microcontroller does not answer: resetting it*. Ci prova tre volte, a un minuto di distanza.

**Causa, se resta rosso.** Linux non riesce a parlare con lo sketch: `arduino-router` non è in funzione, il firmware non è caricato, un'app di App Lab lo ha sostituito all'avvio, oppure il firmware parla un'altra versione del protocollo (il log dice *the MCU speaks protocol N, expected 1: reload the firmware*).

**Soluzione.**

```bash
systemctl status arduino-router --no-pager
arduino-app-cli properties set default none
cd ~/domotiq && bash scripts/install.sh
```

L'installer (che ha bisogno di internet) ricarica il firmware quando serve; senza internet, segui la compilazione e il caricamento manuali descritti in `firmware/domotiq_mcu/README.md`. Senza il microcontrollore la casa continua a funzionare e la webapp mostra le luci solo sulla piantina.

### Tutte le luci respirano debolmente e non reagiscono
**Causa.** Il microcontrollore sta aspettando Linux: la scheda si sta ancora avviando, oppure l'applicazione tace da 30 secondi (si è fermata o si è bloccata). In questo stato il relè è spento.

**Soluzione.** Aspetta che l'avvio finisca. Un'applicazione che cade riparte dopo 2 secondi; una bloccata viene riavviata da systemd dopo 2 minuti. Quando torna a parlare con il microcontrollore, la casa gli rimanda luci e LED da sola. Se dopo 3 minuti respirano ancora, controlla `systemctl status domotiq`.

### Un modulo è rosso in *Diagnostica*
**Causa.** Un cavo Qwiic allentato, il modulo sul canale sbagliato dell'Hub, oppure un modulo che non risponde.

**Soluzione.** Lancia **Scansione I2C** e confronta con la tabella del [capitolo 5](05-collaudo.md#3-microcontrollore-e-moduli). Ogni canale dell'Hub deve mostrare gli indirizzi dei suoi moduli: 0x36 per un Pixels, 0x44 per un Thermo, 0x3E per il Buttons. Il Latch Relay può essere a 0x02, a 0x15 o a 0x10 e l'Hub ovunque tra 0x70 e 0x77: vanno bene tutti. Un modulo ricollegato ricompare entro 5 secondi.

### Tutti i moduli sono rossi e c'è l'avviso "Il bus dei Modulino è bloccato"
**Causa.** Una delle due linee del bus Qwiic (SCL o SDA) è tenuta a massa, e finché resta così nessun modulo può rispondere. Quasi sempre è un cavo con i fili invertiti: i cavi JST-SH a 4 poli si vendono anche in versione "inversa" (pin 1 collegato al pin 4), che sul Qwiic mette la massa di un modulo sulla linea dei dati. Sul tratto principale (UNO Q → Hub → Relay) blocca subito tutto; su un canale dell'Hub blocca il bus appena il firmware apre quel canale. Un segno tipico: i LED verdi di alimentazione dei moduli dopo quel cavo restano spenti o fiochi. Più di rado è un connettore danneggiato.

**Soluzione.** Stacca l'alimentazione e controlla i cavi: affianca i due connettori dello stesso cavo, girati nello stesso modo; in un cavo Qwiic giusto i colori dei fili sono nello stesso ordine su tutti e due. Con fili tutti dello stesso colore usa un tester in continuità: il pin più a sinistra di un connettore deve suonare con il pin più a sinistra dell'altro. Se i cavi sono giusti, con la casa accesa stacca dall'Hub un cavo alla volta: l'avviso sparisce entro 5 secondi da quando togli quello guasto. La riga sopra i moduli in *Diagnostica* e `scripts/bench_mcu.py` mostrano lo stato di SCL e SDA.

### La casa dice che il termostato o il sensore non risponde
**Causa.** Nessuna lettura da quel Thermo (canale 6 per la credenza, canale 4 per il bagno). La casa lo dice con "Il termostato non risponde." o "Il sensore non risponde.".

**Soluzione.** Controlla il modulo in *Diagnostica* e il suo cavo.

### I tasti fanno la cosa sbagliata
**Causa.** Il modulo Buttons è montato al contrario.

**Soluzione.** **Impostazioni → Tasti montati al contrario**.

## Luci, relè e ventola

### Le luci sono più deboli del previsto, e si abbassano quando se ne accendono di più
**Causa.** Il firmware protegge la linea a 3,3 V del connettore Qwiic: la luminosità è limitata al 30 % e tutte le luci vengono ridotte quando la corrente stimata supera i 450 mA.

**Soluzione.** È voluto. I valori si possono alzare in **Impostazioni** (*Luminosità massima (%)*, *Limite di corrente dei Pixels (mA)*), ma il connettore è dimensionato per 1 A e il regolatore della scheda è condiviso: prova i nuovi valori per 10 minuti prima di usarli (vedi il [capitolo 4](04-collegamenti.md#alimentazione-dei-pixels)).

### Una luce accesa dal telefono si è spenta da sola
**Causa.** Le luci manuali durano due minuti, poi la stanza torna alla casa (luci che seguono le persone, scenario, regole).

**Soluzione.** È il comportamento normale; per una luce che deve restare accesa, usa una regola.

### La ventola non parte
**Causa.** Il barbecue è in pausa (30 secondi dopo il precedente: "Il barbecue è già acceso, o si sta raffreddando."), il Latch Relay manca, oppure la ventola non è sul contatto normalmente aperto.

**Soluzione.** Controlla il relè in *Diagnostica* e i collegamenti nel [capitolo 4](04-collegamenti.md#relè-e-ventola).

### La ventola ha girato dopo un'interruzione di corrente
**Causa.** Il relè bistabile mantiene la sua posizione senza alimentazione; il firmware lo spegne all'accensione solo se è stato compilato in modalità "Immediate".

**Soluzione.** Carica il firmware con `install.sh`, che lo compila con `wait_linux_boot=no`.

## Webcam e riconoscimento

### Fascia *La webcam si è spostata: rifare la calibrazione*
**Causa.** Le pareti nell'immagine non coincidono più con la casa vuota: il palo o la webcam sono stati urtati.

**Soluzione.** Ripeti la calibrazione ([capitolo 5](05-collaudo.md#9-calibrazione-della-webcam)).

### Il pallino *Webcam* è rosso, oppure *La webcam non è collegata.*
**Causa.** La C270 è scollegata o non viene trovata.

**Soluzione.** Controlla il cavo USB e `ls /dev/v4l/by-id/`. Se la casa sceglie la webcam sbagliata, scrivi il percorso `by-id` in `var/config/settings.json` sotto `"camera": {"device": "…"}` e riavvia `domotiq`.

### La diretta mostra un disegno con la scritta *SIMULAZIONE - SIMULATION*
**Causa.** La simulazione è attiva: la casa ignora la webcam.

**Soluzione.** **Altro → Simulazione** e spegnila.

### Non viene riconosciuto niente, oppure la *Diagnostica* dice *da calibrare*
**Causa.** Mancano gli angoli o la casa vuota.

**Soluzione.** Calibra ([capitolo 5](05-collaudo.md#9-calibrazione-della-webcam)).

### Avviso *La casa vuota è stata salvata al buio*
**Causa.** La casa vuota è stata salvata con la sala al buio (prima che la webapp lo rifiutasse): con la luce accesa tutto sembra diverso da quella.

**Soluzione.** Togli le statuine e, con la luce accesa, fai **Calibrazione → Regola la luce e salva la casa vuota**; poi rimettile a mano.

### La luce della webcam cambia da sola, o resta *al limite*
**Causa.** Mentre la casa guarda, il guadagno della webcam segue la luce della sala a piccoli passi, misurando la luce delle stanze rispetto alla casa vuota in uso. In *Diagnostica → Luce della webcam*, "al limite della webcam" vuol dire che il guadagno è già al massimo (sala troppo buia) o al minimo con l'esposizione più corta (sala molto illuminata).

**Soluzione.**
- **Ritocchi frequenti, o tanti cambi di verso nell'ultima ora:** una luce della sala che sfarfalla o che cambia di continuo.
- **In pausa per "stanze coperte":** mani, personaggi o oggetti coprono gran parte delle stanze; quando si tolgono riprende da sola.
- **Al limite al buio:** accendi una luce. Se la regolazione completa è già stata fatta al buio, la casa non la rifà: darebbe gli stessi valori, con 10 secondi senza immagini.
- **Dopo aver cambiato del tutto l'illuminazione della sala:** rifai **Calibrazione → Regola la luce e salva la casa vuota**.
- **Per tornare al comportamento di prima:** `camera.follow_light: false` in `var/config/settings.json`.

### Avviso *La webcam vede quasi buio*
**Causa.** Da più di cinque secondi l'immagine è troppo scura (grigio medio sotto 25 su 255): la sala è troppo buia (su casa1 di sera, con la luce della stanza spenta, la webcam arrivava a 9-17 su 50 anche al guadagno massimo) oppure qualcosa copre la webcam.

**Soluzione.** Accendi una luce, o togli quello che copre la webcam. Nel frattempo i personaggi restano dove erano e la casa non impara niente da quell'immagine. Quando la luce torna, la casa si adatta da sola.

### Avviso *La webcam vede tutta la casa diversa*
**Causa.** Per più di cinque secondi oltre un terzo della casa appare diverso dalla casa vuota: la luce della sala è cambiata molto, qualcosa copre la webcam, oppure la webcam è stata urtata.

**Soluzione.** Controlla la webcam e la sua inquadratura; poi, con la casa vuota, **Altro → Calibrazione → Regola la luce e salva la casa vuota** (oppure **Salva solo la casa vuota**, se la luce non è cambiata). L'avviso sparisce da solo quando l'immagine torna normale.

### Compaiono oggetti fantasma, o quelli veri non vengono visti, dopo che la luce della sala è cambiata
**Causa.** L'esposizione bloccata e il riferimento della casa vuota non corrispondono più alla luce della sala.

**Soluzione.** Di solito la casa si arrangia. Si accorge del cambio di luce e tiene i personaggi come erano un attimo prima. Se serve riregola subito la webcam, senza perdere la calibrazione. Poi reimpara la casa vuota con la luce nuova, tranne intorno ai personaggi. In *Diagnostica* il contatore degli adattamenti sale di uno. Se non basta, svuota la casa e tocca **Regola la luce e salva la casa vuota**.

### La casa non nota i personaggi che metto
**Causa.** La casa crede che ci sia una mano sopra la casa e aspetta che se ne vada (in *Diagnostica* risulta una mano anche quando nessuno tocca la casa). Succede se sul bordo della base è appoggiato qualcosa di grande: un modulo, un cavo, il braccio di un visitatore.

**Soluzione.** Togli o fissa quello che è sul bordo. Una "mano" ferma per 8 secondi la casa la considera comunque un oggetto e la fa entrare nella casa vuota; un personaggio posato nel frattempo compare 2 secondi dopo.

### Animali o oggetti che non ci sono, soprattutto sul vialetto
**Causa.** Il braccio di chi gioca sposta moduli o cavi sciolti, e ogni spostamento è un cambiamento vero rispetto alla casa vuota.

**Soluzione.** Monta il totem e fissa i cavi lungo le pareti, poi a casa vuota **Altro → Calibrazione → Salva solo la casa vuota**.

### La casa chiede di qualcuno che non c'è
**Causa.** Qualcosa che la mano ha spostato o lasciato (un'ombra, un riflesso, un cavo) ha superato il doppio controllo della casa.

**Soluzione.** Rispondi "non c'è nessuno" (o "è la mia mano", "è un'ombra"), oppure tocca **Non c'è niente** sul telefono. La casa dimentica quello che aveva visto, lì per 30 secondi non nasce niente e per due minuti in quella stanza è più severa. Se succede spesso nello stesso punto, guarda la diretta: può essere un modulo, un LED o un cavo da fissare o da coprire.

### La webapp dice *La webcam non è collegata*
**Causa.** Per qualche secondo la casa non ha ricevuto immagini: un riavvio, un reset USB della C270 (succede a ogni apertura, e quando la sessione del desktop della scheda la interroga, per esempio a ogni accesso ssh).

**Soluzione.** La scritta sparisce da sola quando le immagini tornano. Se resta, controlla il cavo della webcam e la *Diagnostica*; spegnere il desktop della scheda evita i reset dovuti agli accessi ssh.

### Oggetti fantasma dove è stato spostato un arredo
**Causa.** Gli arredi fanno parte della casa vuota.

**Soluzione.** Rimettilo a posto, oppure svuota la casa e tocca **Salva solo la casa vuota**.

### Una statuina non viene vista, o continua a sparire
**Causa.** Il suo colore è troppo vicino al pavimento, alle pareti o ai prati; oppure si trova dove la visione non guarda: sotto un'applique, sotto la chioma dell'albero, accanto al palo, sulla cima di una parete, fuori dalla base.

**Soluzione.** Spostala in un punto più libero, oppure usa una statuina di un altro colore. La registrazione avvisa in questi casi.

### Un personaggio noto viene preso per un nuovo arrivato
**Causa.** Visto adesso, il suo colore è diverso da quando è stato registrato: un'altra luce, il personaggio sdraiato, su uno sfondo colorato. La casa lo riconosce lo stesso se gli somiglia molto più che a chiunque altro.

**Soluzione.** Alla domanda rispondi con il suo nome: la casa lo assegna e ne aggiorna subito i colori, così la volta dopo lo riconosce da sola. Se quel personaggio è già in vista in un altro punto della casa, la casa conclude che il nuovo arrivato non c'era.

### Un personaggio ha un **?**, oppure la casa continua a chiedere chi è chi
**Causa.** Due statuine di colore simile, prese insieme o a contatto: la casa non riesce a distinguerle dal colore.

**Soluzione.** Rispondi alla domanda su un telefono o a voce. Con colori diversi non succede.

### Una statuina ha perso il suo nome dopo essere stata tenuta in mano
**Causa.** È stata tenuta in mano per più di 60 secondi, quindi la casa ha smesso di seguirla.

**Soluzione.** Appoggiala: viene riconosciuta di nuovo dal suo colore, oppure la casa chiede.

### L'area sfocata non coincide con il bagno
**Causa.** La webcam non è ancora calibrata: fino ad allora la casa sfoca un'area ampia dove dovrebbe trovarsi il bagno se la webcam fosse montata come da progetto. Se il palo o la culla della webcam sono girati, quell'area finisce nel posto sbagliato.

**Soluzione.** Calibra prima di aprire la casa ai visitatori: da quel momento la sfocatura segue il bagno vero.

## Audio e voce

### Il pallino *Audio* è rosso, oppure la casa è muta
**Causa.** La scheda audio USB manca o non viene trovata, il volume è a 0, la casa è impostata su *Silenziosa*, oppure il servizio di sintesi vocale è fermo.

**Soluzione.** Controlla con `aplay -l` che ci sia una scheda audio USB, poi **Comandi → Volume** e **Loquacità**, e `systemctl status domotiq-tts`. La casa usa la prima scheda audio USB che può suonare; per forzare un altro dispositivo, aggiungi `Environment=DOMOTIQ_AUDIO=plughw:CARD=<name>,DEV=0` con `sudo systemctl edit domotiq` e riavvia il servizio. Se la scheda sparisce o si riavvia da sola mentre la casa è accesa (la US205 ogni tanto lo fa, e torna con il volume basso), la casa se ne accorge entro un paio di secondi, la riapre e rimette i livelli a 0 dB; in *Diagnostica* il contatore *restarts* dell'audio sale di uno. Se succede spesso, controlla che la scheda sia ben inserita e alimenta le casse da un'altra presa USB. Anche senza nessuna scheda audio, la casa continua a scrivere come sottotitoli quello che direbbe.

### La casa non si sente per qualche minuto dopo l'accensione, poi sì
**Causa.** Una webcam che si riavvia sul bus USB quando viene aperta disturba la scheda audio collegata allo stesso hub. L'uscita della casa continua a prendere il suono, ma non si sente niente, finché dopo qualche minuto si blocca e viene riaperta. Il 10/10 è successo a ogni accensione su una scheda appena montata, la cui C270 si riavviava a ogni apertura; l'altra casa, con una webcam che non si riavvia, si sentiva subito.

**Soluzione.** Quando la webcam risulta aperta, la casa riapre l'uscita audio (nel log: *audio output opened again: the webcam was opened*). In più rilegge ogni 10 secondi i livelli della scheda audio e li rimette se qualcuno li ha cambiati. Su una casa installata prima, aggiorna il software (`release.sh casaN`). Se succede ancora, collega la scheda audio a un'altra porta dell'hub.

### La prima frase in inglese è lenta
**Causa.** La voce inglese viene caricata al primo utilizzo.

**Soluzione.** È normale; all'avvio la casa prepara le sue frasi frequenti.

### La casa non sente niente
**Causa.** Il lavalier non è nell'ingresso microfono della US205, oppure è troppo lontano dalla bocca di chi parla.

**Soluzione.** **Diagnostica → Prova microfono (3 s)**: un livello vicino a zero vuol dire che non arriva segnale. Controlla la spina, e parla vicino al tappo del totem tenendo premuto **Parla** per tutta la frase.

### "Non ho capito." per frasi che dovrebbero funzionare
**Causa.** Una frase capita male, oppure il modello linguistico non è disponibile.

**Soluzione.** Controlla che la lingua della casa sia quella in cui si sta parlando (LED di Lingua acceso = inglese). In **Diagnostica**, alla riga *Voce*, compare *LLM* con un pallino verde quando il modello linguistico risponde; altrimenti `systemctl status domotiq-llm`. Se la casa è stata installata con `--no-llm`, capisce solo le sue frasi fisse.

### Un nome non viene mai riconosciuto a voce
**Causa.** Il modello di riconoscimento vocale non conosce le parole del nome.

**Soluzione.** Scegli un nome comune, oppure, per il riconoscimento inglese, compila **Pronuncia inglese (facoltativa)** nella scheda del personaggio.

## Telefoni e hotspot

### Un telefono entra nel Wi-Fi ma la pagina non si apre
**Causa.** L'hotspot non ha internet, e il telefono manda il traffico sui dati mobili (tipico su Android), oppure aspetta che la rete dimostri di essere online.

**Soluzione.** Quando il telefono lo chiede, scegli *Resta connesso* o *Usa senza Internet*. Su Android, spegni per un attimo i dati mobili. Apri esattamente `http://10.42.N.1/`, con `http://`.

### L'hotspot `DomotiQ-CasaN` non si vede
**Causa.** La scheda è ancora sul Wi-Fi del laboratorio, oppure l'hotspot non è partito.

**Soluzione.** `bash scripts/hotspot.sh status`, poi `bash scripts/hotspot.sh on`; `bash scripts/hotspot.sh boot` lo fa partire a ogni avvio. È una rete a 2,4 GHz.

### *Connessione con la casa persa: riprovo…*
**Causa.** Il telefono è uscito dalla copertura del Wi-Fi, oppure la scheda si sta riavviando.

**Soluzione.** Aspetta: la webapp si ricollega da sola.

## Orologio

### La casa chiede "Non so che ore sono: che ore sono adesso?"
**Causa.** La scheda non ha una batteria per l'orologio e, senza internet, non può rimettere l'ora da sola; dall'avvio nessun telefono ha aperto la webapp.

**Soluzione.** Rispondi subito a voce, senza premere niente ("sono le tre e mezza"), apri la webapp da un telefono (imposta l'ora), oppure usa **Impostazioni → Usa l'ora di questo telefono** ([capitolo 8](08-voce.md#impostare-lora-a-voce)). In **Diagnostica**, alla riga *Orologio*, si vede da dove arriva l'ora. Le regole con *è un certo orario* hanno bisogno di un'ora nota.

## Webapp e allarme

### Un allarme suona e non c'è nessuno
**Causa.** Le regole d'allarme contano solo presenze certe: un personaggio che la casa conosce, o una cosa ferma e ben visibile da almeno 6 secondi. Se suona lo stesso, la casa vede davvero qualcosa in quel punto: un LED, un riflesso, un modulo appoggiato.

**Soluzione.** **Disinserisci** l'allarme dalla notifica rossa o dal riquadro della pagina **Casa**: le regole d'allarme stanno zitte finché non lo reinserisci. Poi rispondi "non c'è nessuno" alla domanda della casa, se c'è, e cerca cosa c'è in quel punto (in **Diretta**, con **Nomi e stanze**); se è un oggetto fisso, toglilo o fissalo e salva la casa vuota.

### L'allarme non suona più
**Causa.** È disinserito: il riquadro **Allarme** nella pagina **Casa** dice *Disinserito*.

**Soluzione.** Tocca **Inserisci**.

## Regole e personaggi

### Una regola non scatta
**Causa.** È disattivata; la sua pausa tra due esecuzioni non è finita; una condizione è falsa; il campo *Chi* esclude quello che si è mosso (le regole di partenza contano solo le persone, non gli animali); una regola a orario con l'ora sconosciuta.

**Soluzione.** Controlla la regola nell'editor, e in **Eventi** guarda cosa ha visto la casa.

### Una regola o un personaggio è stato eliminato per sbaglio
**Soluzione.** **Impostazioni → Cestino → Ripristina**, entro 24 ore. Un personaggio ripristinato il cui nome è stato preso nel frattempo riceve " 2" dopo il nome. **Impostazioni → Regole di partenza** riporta le regole originali (sostituisce tutte quelle attuali).

### *Il nome Marco è già usato*
**Causa.** I nomi sono unici nella casa, senza distinzione tra maiuscole e minuscole, pronunce inglesi comprese.

**Soluzione.** Aggiungi un cognome o un soprannome.

### *Non ho trovato niente di nuovo. Riprova.*
**Causa.** Durante la registrazione non è comparsa nessuna statuina sconosciuta entro due minuti e mezzo, oppure era troppo vicina a qualcos'altro.

**Soluzione.** Appoggia la statuina in un punto libero del pavimento, lontano da pareti e arredi, e ricomincia.

### La festa non parte
**Causa.** C'è già una festa in corso, oppure non è finita la pausa di 30 secondi dopo l'ultima (*Già in corso o in pausa, riprova tra poco*).

**Soluzione.** Aspetta un momento.
