# DomotiQ: guida rapida per lo staff dello stand

Casa: casa1 / casa2 · Wi-Fi `DomotiQ-Casa1` / `DomotiQ-Casa2` · webapp `http://10.42.1.1/` / `http://10.42.2.1/`

Password del Wi-Fi: ____________________ PIN dello staff: ____________

(Scrivili a mano solo sulla copia stampata.)

## Alimentazione

- **Accensione**: collega l'alimentatore. Le luci respirano debolmente per circa 40 secondi mentre la scheda si avvia, poi si spengono: la casa è pronta. Il Wi-Fi della casa parte da solo.
- **Spegnimento a fine giornata**: webapp, **Altro → Impostazioni → Spegni la scheda** (staff), poi stacca la spina.
- **Dopo un'interruzione di corrente** la casa riparte da sola. La ventola del barbecue resta ferma.

## I tre tasti (da sinistra a destra, come li vede il visitatore)

- **Parla**: tienilo premuto, parla, rilascia. "Dov'è Marco?" · "Who's in the kitchen?" · "Fai festa!" · "Light the barbecue" · "Luce rossa in camera" · "Com'è la casa?"
- **Citofono**: suona il campanello, la casa chiede "Chi è?": di' un nome. Un personaggio conosciuto viene fatto entrare (portalo dentro dalla porta d'ingresso entro un minuto); un nome nuovo viene registrato.
- **Lingua**: italiano ⇄ inglese. Luci che lampeggiano verdi = italiano, rosse = inglese. LED acceso = inglese.

## I telefoni dei visitatori

Inquadra il QR 1 del cartello (Wi-Fi), poi il QR 2 (la casa). Se il telefono lo chiede: *Resta connesso* / *Usa senza Internet*. Android: spegni per un attimo i dati mobili. Tutti possono dare comandi, cambiare le regole e registrare personaggi.

## Registrare una statuina

**Altro → Personaggi e oggetti → + Aggiungi** → nome (e, se vuoi, una foto) → **Avanti** → appoggia la statuina in un punto libero del pavimento → scegli che cos'è → **Salva**. I nomi devono essere unici: se serve, aggiungi un cognome. Gli avvisi su colori simili al pavimento o a un altro personaggio sono consigli, non errori.

## Se qualcosa non va

| Vedi | Fai |
|---|---|
| Fascia *La webcam si è spostata: rifare la calibrazione* | Calibra (vedi sotto). |
| Oggetti fantasma, o statuine non viste, dopo che la luce del padiglione è cambiata | Svuota la casa, **Calibrazione → Regola di nuovo la luce**. |
| Un **?** su un personaggio, oppure *La casa chiede* | Tocca il nome giusto sulla fascia, oppure tieni premuto Parla e dillo. |
| La casa è muta | **Comandi**: Loquacità *Normale*, alza il Volume. Manopola delle casse al massimo. |
| "Non so che ore sono" | Apri la webapp su un telefono, oppure tieni premuto Parla: "Sono le quindici e trenta". |
| Le luci respirano debolmente e niente reagisce | Il software si sta (ri)avviando: aspetta un minuto. Poi **Impostazioni → Riavvia l'app**, poi **Riavvia la scheda**. |
| Un pallino di stato rosso in alto | La **Diagnostica** mostra quale parte. |
| Un visitatore ha rovinato una regola o eliminato un personaggio | **Eventi → Modifiche** mostra cosa è successo; **Impostazioni → Cestino → Ripristina** (24 ore); **Impostazioni → Regole di partenza** ripristina tutte le regole. |
| Festa o barbecue non partono | Sono in pausa: aspetta 30 secondi. |
| Un telefono non riesce ad aprire la pagina | Dati mobili spenti; scrivi `http://10.42.N.1/`. |

## Strumenti dello staff

**Altro → PIN dello staff → Accesso staff** (vale 12 ore su quel telefono; dopo 5 PIN sbagliati aspetta un minuto).

- **Calibrazione**: togli statuine e auto → tocca i 4 angoli della base (davanti a sinistra, davanti a destra, dietro a destra, dietro a sinistra; davanti = vialetto) → **Usa questi angoli** → controlla che le pareti disegnate coincidano con quelle vere → **Regola di nuovo la luce**. Calibra prima di aprire la casa ai visitatori: fino ad allora la sfocatura può solo indovinare dove si trova il bagno.
- **Diagnostica**: moduli, scansione I2C, **Prova audio**, **Prova microfono (3 s)**, registri.
- **Impostazioni**: luminosità e durate, PIN, password del Wi-Fi, **Usa l'ora di questo telefono**, backup, cestino, riavvio dell'app, riavvio e spegnimento della scheda.
- **Comandi → Fai dire alla casa**; **Simulazione** accesa e spenta.

Guida completa: `docs/it/` nel repository.
