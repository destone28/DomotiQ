# 5. Collaudo e messa in servizio

Segui questo capitolo dopo il montaggio e i collegamenti, e di nuovo ogni volta che la casa cambia posto. Ogni passo dice cosa fare e cosa dovresti vedere. Quando qualcosa non torna, il capitolo sulla [risoluzione dei problemi](11-risoluzione-problemi.md) riporta le cause probabili.

Ti serve un telefono o un PC collegato alla stessa rete della scheda: la tua rete Wi-Fi (`http://casa1.local/`) o l'hotspot della casa (`http://10.42.1.1/`).

## 1. Accensione

Accendi l'alimentatore. Ecco cosa succede:

1. Il microcontrollore parte subito: relè spento, luci spente, poi una luce tenue che **respira** in ogni stanza mentre Linux si avvia (circa 40 secondi).
2. Quando l'applicazione è pronta, prende il controllo delle luci: se in casa non c'è nessuno, si spengono.

Controlla i servizi da una sessione SSH:

```bash
systemctl status domotiq domotiq-tts domotiq-llm --no-pager
journalctl -u domotiq -f
```

## 2. Aprire la webapp

Apri l'indirizzo della casa in un browser. In alto a destra, accanto al nome della casa, tre pallini mostrano lo stato di **Microcontrollore**, **Webcam** e **Audio** (verde = funziona). Tutte le pagine sono aperte a chiunque: **Calibrazione**, **Diagnostica** e **Impostazioni** stanno in **Altro → Messa a punto**.

## 3. Microcontrollore e moduli

Apri **Altro → Diagnostica**.

- La scheda **Modulino** mostra un pallino verde e `v1`, la versione del protocollo del firmware. Un pallino rosso vuol dire che Linux non riesce a parlare con il microcontrollore.
- Sotto, ogni modulo ha un pallino verde o rosso: Hub, Latch Relay, i cinque Pixels (garage, camera, cucina, soggiorno, bagno), i due Thermo (bagno, credenza) e Buttons.
- **Scansione I2C** elenca gli indirizzi che rispondono su ogni canale dell'Hub. Oltre all'Hub (0x70–0x77) e al Latch Relay (0x02, 0x15 o 0x10), che stanno sul bus principale e rispondono su tutti i canali, ci si aspetta:

  | Canale | Atteso |
  |---|---|
  | ch0, ch1, ch2, ch3, ch5 | 0x36 (Pixels) |
  | ch4 | 0x44 (Thermo) |
  | ch6 | 0x44, 0x3e (Thermo, Buttons) |
  | ch7 | niente |

## 4. Luci

In **Comandi → Luci** scegli una stanza e tocca un colore: la luce si accende subito. Ripeti per tutte e sei le stanze (nel locale tecnico la luce è la matrice LED della UNO Q, con il colore sul LED RGB accanto), poi scegli *Tutte le stanze* e tocca **A** per restituire le luci alla casa. Una luce accesa a mano resta accesa per due minuti; il cerchio barrato tiene una stanza al buio per un minuto.

## 5. Tasti e LED

- **Lingua**: tutte le luci lampeggiano di verde (italiano) o di rosso (inglese) per circa un secondo, la casa dice "Italiano" o "English", e il LED del tasto Lingua resta acceso mentre la casa parla inglese. Premilo di nuovo per tornare all'italiano.
- **Parla**: tienilo premuto. Un bip, i tre LED si accendono mentre la casa ascolta, un altro bip quando lo rilasci; mentre la casa pensa alla risposta i LED respirano.
- **Citofono**: suona un campanello e la casa chiede "Chi è?" / "Who is it?"; il suo LED lampeggia durante la conversazione. Se per due volte non dici niente, la casa ti fa entrare come ospite.

## 6. Termostato e bagno

Nella schermata **Casa** le schede del termostato e del bagno mostrano la temperatura in °C e, sotto, l'umidità.

- Appoggia un dito sul Thermo della credenza: la temperatura sale lentamente, perché la scheda del sensore ha una sua inerzia termica. Soffiarci sopra è più rapido: l'umidità fa un balzo, il termostato passa a **caldo**, la casa dice "Fa caldo! Accendo il climatizzatore." e un'onda azzurra (effetto *Aria fresca*) scorre in tutte le stanze per un massimo di due minuti, o finché la lettura non torna normale.
- Soffia sul Thermo del bagno: quando l'umidità sale di 8 punti sopra la sua media recente parte la regola della doccia ("Accendo l'aspiratore del bagno.", luce fresca in bagno, notifica *Doccia in corso*).

Le soglie sono relative alla media degli ultimi 5 minuti, quindi dopo l'accensione lascia ai sensori qualche minuto.

## 7. Ventola del barbecue

In **Comandi** tocca **Barbecue**. La casa dice "Accendo il barbecue!", la ventola gira per 20 secondi, poi "La grigliata è pronta, tutti in giardino!". **Spegni barbecue** la ferma subito.

Poi prova un'interruzione di corrente: avvia il barbecue e stacca l'alimentazione mentre la ventola gira. Quando la corrente torna, la ventola deve restare ferma.

## 8. Audio e microfono

In **Diagnostica**:

- **Prova audio** fa suonare un campanello breve e dice "Prova dell'audio: mi senti?". La manopola delle casse deve essere al massimo; il livello si regola con **Comandi → Volume**.
- **Prova microfono (3 s)** registra tre secondi: parla verso il tappo del totem. Il risultato mostra il livello, il picco e il testo riconosciuto. Un livello vicino a zero vuol dire che all'ingresso del microfono non arriva nessun suono.

## 9. Calibrazione della webcam

La calibrazione dice alla casa dove si trova la base nell'immagine. Finché non è fatta la casa non vede niente, e nella diretta la sfocatura del bagno è solo approssimativa (vedi il [capitolo 7](07-riconoscimento-e-identita.md#privacy)): calibra prima di usare la diretta.

Apri **Altro → Calibrazione**.

1. **Togli personaggi e auto dalla casa (gli arredi restano).** Lascia gli arredi esattamente dove resteranno.
2. **Tocca i 4 angoli della base, nell'ordine indicato**: davanti a sinistra, davanti a destra, dietro a destra, dietro a sinistra. Il davanti è il bordo del vialetto; la sinistra è il lato di cucina e giardino. Un'etichetta indica l'angolo successivo; ↶ toglie l'ultimo. Tocca **Usa questi angoli**. Se i quattro punti non formano un contorno plausibile della base, la casa li rifiuta: toccali di nuovo, in ordine.
3. **Controlla la sovrapposizione.** Con *Sovrapposizione* attiva, l'immagine mostra il contorno della base, le stanze, le porte in verde, le pareti disegnate alla loro altezza reale e le zone escluse scurite (applique, chioma dell'albero, palo). Le pareti disegnate devono coincidere con quelle nell'immagine. Se non coincidono, tocca di nuovo gli angoli.
4. **La luce e la casa vuota.** Subito dopo gli angoli la casa regola da sola la luce della webcam e salva la casa vuota; una finestra con una rotellina mostra che sta lavorando, e i pulsanti restano bloccati fino al messaggio *Casa vuota salvata*. Non toccare la casa in quei 15 secondi. Per qualche secondo la webcam regola da sola esposizione e bilanciamento del bianco, e la casa misura la luminosità e i colori che ottiene. Poi cerca i valori manuali che danno la stessa immagine, un quarto più scura (così il pavimento sotto le luci colorate della casa non si satura), e li blocca. Con alcune luci, come certe lampade calde e verdastre, nessuna temperatura della webcam dà colori neutri: quello che resta lo corregge la casa con un guadagno fisso su ogni colore. Alla fine salva la casa vuota, cioè la mediana di 20 fotogrammi. In tutto ci vogliono circa 15 secondi, e la casa deve essere vuota.

In seguito:

- **Salva solo la casa vuota** prende un nuovo riferimento senza toccare le impostazioni della webcam, per esempio dopo aver spostato un arredo.
- **Regola la luce e salva la casa vuota** serve quando la luce della sala cambia molto. I cambiamenti lenti vengono seguiti automaticamente sul pavimento libero.
- Se la webcam viene urtata, la webapp mostra *La webcam si è spostata: rifare la calibrazione*: ripeti tutta la procedura.

Ora in **Diagnostica**, alla riga *Webcam*, compaiono i fotogrammi al secondo (da 7 a 10) e il tempo di elaborazione, senza *da calibrare* né *luce da regolare*.

## 10. Il primo personaggio

1. **Personaggi → + Aggiungi.** Scrivi un nome, se vuoi scatta una foto, tocca **Avanti**.
2. Metti il personaggio in un punto libero della casa. La casa lo trova e chiede che cos'è, proponendo un tipo; tocca quello giusto e **Salva**.
3. Nella schermata **Casa** il personaggio compare con il suo nome. Spostalo in un'altra stanza: sulla piantina passa in quella stanza. Le luci che seguono le persone sono spente di serie ([capitolo 9](09-regole.md#priorità-e-livelli-delle-luci)), quindi la luce della stanza resta com'è.
4. Prendilo in mano e appoggialo in un'altra stanza: mantiene il suo nome.

Il [capitolo 7](07-riconoscimento-e-identita.md) spiega nel dettaglio la registrazione e i suoi avvisi.

## 11. Voce

Tieni premuto **Parla** e chiedi, in italiano, "Dov'è Marco?" (con il nome che hai registrato); rilascia e aspetta la risposta. Passa all'inglese con il tasto Lingua e chiedi "Where is Marco?".

Poi chiedi qualcosa che le frasi fisse non coprono, per esempio "Quanta gente c'è in cucina?". La casa dice "Vediamo…" / "Let me see…" e passa la frase al modello linguistico. In **Diagnostica**, alla riga *Voce*, compare *LLM* con un pallino verde quando il server del modello linguistico è disponibile.

## 12. Citofono e regole

- Premi **Citofono**, di' il nome del personaggio registrato e, entro 60 secondi, porta quella statuina dal vialetto in soggiorno passando dalla porta d'ingresso: prende quel nome.
- Metti due personaggi di tipo persona in bagno: dopo 2 secondi il bagno lampeggia di arancione e la casa dice "Il bagno è occupato! Aspetta il tuo turno."
- Lascia un personaggio di tipo persona nel locale tecnico per più di 5 secondi: luci rosse di allarme in soggiorno e in garage, "Attenzione: il locale tecnico è riservato!", e una fascia rossa sui telefoni finché non esce.
- Fai entrare l'auto dal portone del garage: "Bentornato a casa!". Lasciala ferma nell'area di parcheggio per 3 secondi: conta come parcheggiata, e la scheda **Auto** della schermata **Casa** lo dice. Con le luci che seguono le persone accese (sono spente di serie) si accende anche la luce del garage, che si spegne 10 secondi dopo il parcheggio.
- **Comandi → Festa!**: "Si balla!", 20 secondi di musica e luci, "Festa finita!".

## 13. Hotspot e telefoni

1. Passa la scheda al suo hotspot (`bash scripts/hotspot.sh on`, oppure riavvia se hai installato con il valore predefinito `--hotspot boot`).
2. Con un telefono Android e un iPhone: entra nella rete `DomotiQ-Casa1` con la password del Wi-Fi (è nel riepilogo dell'installazione e in **Altro → Impostazioni → Wi-Fi della casa**), poi apri `http://10.42.1.1/` (se hai installato con `--house N`, la rete è `DomotiQ-CasaN` e l'indirizzo `http://10.42.N.1/`). Se il telefono lo chiede, scegli *Resta connesso* o *Usa senza Internet*. Su Android, se la pagina non si apre, spegni per un attimo i dati mobili.
3. In **Diagnostica**, alla riga *Wi-Fi*, compare il numero di dispositivi collegati all'hotspot. Apri **Diretta** su più telefoni contemporaneamente per controllare che il flusso video regga.

## 14. Orologio

La UNO Q non ha una batteria per l'orologio e, senza internet, non può rimettere l'ora da sola. Dopo un riavvio, il primo telefono che apre la webapp imposta l'ora della casa (un messaggio dice *Ora della casa impostata da questo telefono*). In **Diagnostica**, alla riga *Orologio*, si vede da dove arriva l'ora. Per impostarla a voce vedi il [capitolo 8](08-voce.md#impostare-lora-a-voce).

## Provare senza statuine

La casa intera gira anche su un PC, in simulazione e senza nessun hardware: si avvia con `--simulate` (vedi il [capitolo 6](06-webapp.md#provare-la-webapp-su-un-pc)). Al posto della webcam ci sono statuine virtuali: toccando **Elemento non riconosciuto** e poi un punto della piantina se ne mette una lì. Luci, voce e regole reagiscono come con le statuine vere. Finché la simulazione è attiva la casa ignora la webcam; per tornare alla casa vera basta riavviarla normalmente, senza `--simulate`.

Avanti: [la webapp](06-webapp.md).
