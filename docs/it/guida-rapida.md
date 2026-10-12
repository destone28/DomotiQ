# DomotiQ: guida rapida

Casa: `casa1` · Wi-Fi `DomotiQ-Casa1` · webapp `http://10.42.1.1/`

La password del Wi-Fi è `domotica2026`, se all'installazione non ne è stata scelta un'altra; la webapp la mostra in **Altro → Impostazioni → Wi-Fi della casa**.

## Alimentazione

- **Accensione**: collega l'alimentatore. Le luci respirano debolmente per circa 40 secondi mentre la scheda si avvia, poi si spengono: la casa è pronta. Il Wi-Fi della casa parte da solo.
- **Spegnimento a fine giornata**: webapp, **Altro → Impostazioni → Spegni la scheda**, poi stacca la spina.
- **Dopo un'interruzione di corrente** la casa riparte da sola. La ventola del barbecue resta ferma.

## Prima di usare la casa

1. **Luce**: accendi la luce della casa (la striscia sopra il diorama, se c'è) prima della scheda, e lasciala sempre accesa.
2. **Accensione**: collega l'alimentatore della scheda e aspetta che le luci smettano di respirare.
3. **Casa vuota**: solo la prima volta in un posto nuovo, o se hai spostato arredi o moduli. Togli tutte le statuine e fai **Altro → Calibrazione → Regola la luce e salva la casa vuota**. Se la casa vede ancora statuine, o se è troppo buio, non salva e dice perché.
   Subito dopo, sempre a casa vuota: **Fotografa con tutte le luci della casa** (un minuto), poi accendi una alla volta le luci della sala (lampade, LED, finestre) e per ognuna **Aggiungi la luce di adesso**. Così la casa riconosce da sola le luci già viste.
4. **Statuine**: posale **a mano, una alla volta**, togliendo la mano ogni volta. La casa le annuncia per nome. Se chiede "chi è?", rispondi.
5. **Controllo**: in **Personaggi** ogni statuina ha il suo nome e la sua stanza. In **Diagnostica** non ci sono avvisi (webcam, luce, casa vuota salvata al buio).

Durante la giornata: niente luci puntate sulla casa o sulla webcam, e niente oggetti appoggiati sulla base. Se cambia la luce della sala, la casa si adatta da sola in pochi secondi.

## I tre tasti (da sinistra a destra, guardando la casa dal vialetto)

- **Parla**: tienilo premuto, parla, rilascia. "Dov'è Marco?" · "Who's in the kitchen?" · "Fai festa!" · "Light the barbecue" · "Luce rossa in camera" · "Com'è la casa?"
- **Citofono**: suona il campanello, la casa chiede "Chi è?": di' un nome. Un personaggio conosciuto viene fatto entrare (portalo dentro dalla porta d'ingresso entro un minuto); un nome nuovo viene registrato.
- **Lingua**: italiano ⇄ inglese. Luci che lampeggiano verdi = italiano, rosse = inglese. LED acceso = inglese.

I tre LED dei tasti tutti accesi: la casa ascolta, rispondi senza premere niente. LED che respirano: la casa sta pensando alla risposta.

## I telefoni

Sul telefono scegli la rete `DomotiQ-Casa1`, scrivi la password del Wi-Fi e apri `http://10.42.1.1/`. Se il telefono lo chiede: *Resta connesso* / *Usa senza Internet*. Android: spegni per un attimo i dati mobili. Tutti possono fare tutto: comandi, regole, personaggi, calibrazione e impostazioni. Ogni modifica finisce nel registro e le cose eliminate restano nel cestino per 24 ore.

## Registrare una statuina

**Personaggi → + Aggiungi** → nome (e, se vuoi, una foto) → **Avanti** → appoggia la statuina in un punto libero del pavimento → scegli che cos'è → **Salva**. I nomi devono essere unici: se serve, aggiungi un cognome. Gli avvisi su colori simili al pavimento o a un altro personaggio sono consigli, non errori.

## Se qualcosa non va

| Vedi | Fai |
|---|---|
| Fascia *La webcam si è spostata: rifare la calibrazione* | Calibra (vedi sotto). |
| Oggetti fantasma, o statuine non viste, dopo che la luce della sala è cambiata | Di solito la casa si adatta da sola in pochi secondi: i personaggi restano dov'erano e la casa confronta con la foto della casa vuota più simile, o la reimpara con la luce nuova (*Diagnostica* conta gli adattamenti). Se è una luce nuova: svuota la casa e **Calibrazione → Aggiungi la luce di adesso**. |
| La casa non riconosce un personaggio che conosce, o lo chiama col nome sbagliato | Nella domanda scegli **Uno già noto…** e tocca **Questo**; oppure tocca il personaggio sulla piantina → **Chi è?** / **È un altro: cambia** e sceglilo dall'elenco. La casa impara quell'aspetto. |
| Una statuina in casa non compare sulla piantina | **Casa → Elemento non riconosciuto**, poi tocca sulla piantina dove si trova (oppure in **Diretta**, nell'immagine), e scegli chi è. |
| Un **?** su un personaggio, oppure *La casa chiede* | Rispondi a voce subito dopo la domanda, senza Parla, con una frase qualsiasi: un nome, "no, è un cane", "non c'è nessuno", "tutti e due". Oppure tocca il nome sulla domanda o **Tutti e due**; per un nuovo arrivato puoi scrivere un nome nuovo, sceglierne il tipo e toccare **Aggiungi**, oppure toccare **Non c'è niente**. |
| La casa non nota i personaggi, e in *Diagnostica* risulta sempre una mano | Qualcosa di grande è appoggiato sul bordo della base (un modulo, un cavo): toglilo o fissalo. Dopo 8 secondi fermo la casa smette comunque di prenderlo per una mano. |
| La casa chiede di qualcuno che non c'è | Rispondi "non c'è nessuno" o tocca **Non c'è niente**: la casa lo dimentica. Se è già sulla piantina, toccalo e scegli **Non c'è davvero: togli**. Se torna nello stesso punto, cerca un modulo, un LED o un cavo da fissare, poi **Salva solo la casa vuota** a casa vuota. |
| Una notifica rossa di allarme | **Disinserisci** spegne l'allarme come un antifurto (si reinserisce dalla pagina **Casa**); la **✕** la chiude su tutti i telefoni e torna solo se l'allarme si ripresenta. Una notifica ambra è un avviso. |
| La casa è muta | **Comandi**: Loquacità *Normale*, alza il Volume. Manopola delle casse al massimo. |
| "Non so che ore sono: che ore sono adesso?" | Rispondi a voce, senza Parla: "Sono le quindici e trenta". Oppure apri la webapp su un telefono. |
| Le luci respirano debolmente e niente reagisce | Il software si sta (ri)avviando: aspetta un minuto. Poi **Impostazioni → Riavvia l'app**, poi **Riavvia la scheda**. |
| Un pallino di stato rosso in alto | La **Diagnostica** mostra quale parte. |
| Qualcuno ha rovinato una regola o eliminato un personaggio | **Eventi → Modifiche** mostra cosa è successo; **Impostazioni → Cestino → Ripristina** (24 ore); **Impostazioni → Regole di partenza** ripristina tutte le regole. |
| Festa o barbecue non partono | Sono in pausa: aspetta 30 secondi. |
| Durante la festa la piantina non segue le statuine | È voluto: con le luci colorate la casa non guarda. Riprende da sola a festa finita, appena le luci si fermano. |
| Un telefono non riesce ad aprire la pagina | Dati mobili spenti; scrivi `http://10.42.1.1/`. |

## Messa a punto (Altro)

- **Calibrazione**: togli statuine e auto → tocca i 4 angoli della base (davanti a sinistra, davanti a destra, dietro a destra, dietro a sinistra; davanti = vialetto) → **Usa questi angoli**: la casa regola da sola la luce e salva la casa vuota (circa 15 secondi, con una rotellina; non toccare la casa) → controlla che le pareti disegnate coincidano con quelle vere. Calibra prima di far usare la casa ad altri: fino ad allora la sfocatura può solo indovinare dove si trova il bagno.
- **Diagnostica**: moduli, scansione I2C, **Prova audio**, **Prova microfono (3 s)**, registri.
- **Impostazioni**: luminosità e durate, password del Wi-Fi, **Usa l'ora di questo telefono**, backup, cestino, riavvio dell'app, riavvio e spegnimento della scheda.
- **Comandi → Fai dire alla casa**; **Comandi → Fai una domanda** (la casa chiede qualcosa a un personaggio e se lo segna).
- **Impostazioni → Voce → Attivazione con la parola chiave**: detta la parola (per esempio *Casa*), i LED lampeggiano subito e, se non continui, la casa risponde "Dimmi!" e ascolta come con Parla. Si può anche dire tutto di fila: "Casa, accendi la luce in cucina".
- **Allarme**: riquadro in fondo alla pagina **Casa**, **Inserisci** / **Disinserisci**.

Guida completa: `docs/it/` nel repository.
