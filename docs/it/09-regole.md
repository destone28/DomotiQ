# 9. Regole

Il comportamento della casa è scritto sotto forma di regole: **Quando** succede qualcosa, **Se** certe condizioni sono vere, **Allora** esegui queste azioni. La casa parte con un gruppo di regole di partenza, e chiunque può modificarle, disattivarle o scriverne di nuove dalla webapp, in **Altro → Regole**.

## La struttura di una regola

| Campo | Significato |
|---|---|
| **Nome** (IT) e (EN) | il nome, nelle due lingue |
| **Priorità** | da 1 a 98: il livello delle luci della regola; un numero più alto vince su uno più basso (vedi [Priorità e livelli delle luci](#priorità-e-livelli-delle-luci)) |
| **Pausa tra due esecuzioni (s)** | dopo essere stata eseguita, la regola ignora lo stesso evento per questo numero di secondi |
| **Attiva** | la regola è in funzione |
| **È un allarme (resta attivo finché dura)** | vedi [Allarmi](#allarmi) |
| **Quando** | esattamente un evento |
| **Se** | un numero qualsiasi di condizioni, che devono essere tutte vere; se non ce n'è nessuna l'editor mostra *Sempre* |
| **Allora** | una o più azioni, eseguite in ordine |

Non esiste un "oppure": per reagire a due situazioni diverse, scrivi due regole.

Le regole sono semplice JSON, salvato sulla scheda in `var/config/rules.json`. Questa è la regola di partenza del bagno:

```json
{
  "id": "r-bathroom-max",
  "name": {"it": "Bagno al massimo 1", "en": "Bathroom for one"},
  "priority": 95, "alert": true, "cooldown_s": 0,
  "when": {"type": "count_above", "room": "bathroom", "value": 1, "grace_s": 2,
           "repeat_s": 15, "who": {"category": "person"}},
  "then": [
    {"type": "light", "room": "bathroom", "effect": "blink", "color": "#ff8000", "brightness": 80},
    {"type": "say", "text": {"it": "Il bagno è occupato! Aspetta il tuo turno.",
                             "en": "The bathroom is taken! Please wait your turn."}},
    {"type": "notify", "level": "warning",
     "text": {"it": "{count} persone in bagno", "en": "{count} people in the bathroom"}}
  ]
}
```

### Chi

Molti eventi e condizioni hanno un campo **Chi** con due scelte: il tipo (*chiunque*, *persona*, *animale*, *cane*, *gatto*, *auto*, *oggetto*) e il personaggio (*chiunque* oppure uno dei personaggi registrati). *animale* comprende cani, gatti e ogni altro animale domestico. Il formato delle regole accetta anche un elenco di personaggi da escludere, `"who": {"category": "person", "except": ["<character id>"]}`, che l'editor non mostra. Se il personaggio scelto viene eliminato, la regola resta com'era e non scatta più per lui: nell'elenco delle regole e nell'editor compare ⚠️ *personaggio eliminato*, così salvandola non diventa una regola per chiunque senza volerlo. Ripristinando il personaggio dal cestino la regola torna a funzionare.

## Quando: gli eventi

| Evento (come nell'editor) | Campi | Scatta quando |
|---|---|---|
| **entra in una stanza** | Stanza, Chi | qualcuno che corrisponde a *Chi* entra nella stanza. Come stanza si può scegliere anche *Tutte le stanze della casa* (cucina, soggiorno, camera, bagno, locale tecnico, garage) oppure *Qualsiasi zona*. |
| **esce da una stanza** | Stanza, Chi | lo stesso, uscendo. |
| **resta in una stanza** | Stanza, Secondi, Ripeti ogni (s, 0 = no), Chi | qualcuno resta nella stanza più di *Secondi*; scatta di nuovo ogni *Ripeti ogni* secondi finché resta. Chi esce in tempo non fa scattare niente. |
| **in una stanza sono più di** | Stanza, Valore, Conferma dopo (s), Ripeti ogni, Chi | il numero di cose corrispondenti nella stanza supera *Valore* e resta così per *Conferma dopo* secondi. Scatta di nuovo solo dopo che il numero è sceso, oppure ogni *Ripeti ogni* secondi. |
| **in una stanza sono meno di** | Stanza, Valore, Conferma dopo (s), Chi | lo stesso, sotto il valore. |
| **compare un personaggio** | Chi | un personaggio registrato compare in vista. |
| **scompare un personaggio** | Chi | un personaggio registrato non si vede più da nessuna parte. |
| **è un certo orario** | Ore | l'orologio della casa arriva a quell'ora (HH:MM), ogni giorno. Serve un'ora nota (vedi il [capitolo 8](08-voce.md#impostare-lora-a-voce)). |
| **un sensore supera** / **un sensore scende sotto** | Sensore, Misura, Valore | il sensore del termostato (credenza) o del bagno oltrepassa il valore, in temperatura (°C) o umidità (%). Scatta una volta, e di nuovo solo dopo che la lettura è tornata indietro di 0,3 °C o del 2 %. |
| **il termostato cambia** | Stato: caldo, freddo, normale | il clima virtuale cambia stato (vedi sotto). |
| **la doccia** | Stato: inizia, finisce | l'umidità del bagno sale di 8 punti sopra la sua media recente (inizia), oppure torna entro 3 punti (finisce). |
| **si preme un tasto** | Tasto: Parla, Citofono, Lingua | quel tasto del totem viene premuto. Il tasto continua comunque a fare il suo lavoro normale. |
| **l'auto** | Stato: arriva, parcheggiata, parte, assente | l'auto entra in garage, sta ferma per 3 secondi nell'area di parcheggio, esce dal garage, oppure ne è fuori da 10 secondi. |
| **cambia scenario** | Scenario | la casa passa a quello scenario. |
| **il barbecue** | Stato: inizia, pronto | la ventola parte, oppure la grigliata è pronta (la ventola ha finito). |
| **la festa** | Stato: inizia, finita | una festa comincia o finisce. |

**Il clima virtuale.** Il Thermo nella credenza è un termostato che si scalda con un dito. Il suo riferimento è la media degli ultimi 5 minuti. Passa a **caldo** quando la temperatura sale di 1 °C sopra il riferimento, o sale più in fretta di 0,1 °C al secondo, o quando l'umidità fa un balzo di 10 punti (qualcuno ci soffia sopra, il che è più rapido di un dito); a **freddo** quando scende di 1 °C sotto il riferimento; di nuovo a **normale** quando torna entro 0,5 °C. La soglia del caldo e l'aumento di umidità della doccia (sotto) si cambiano in **Altro → Impostazioni**, nel riquadro **Festa · Barbecue · Clima**, e valgono subito; le altre soglie stanno nella sezione `"climate"` di `var/config/settings.json`.

## Se: le condizioni

| Condizione | Campi | Vera quando |
|---|---|---|
| **la stanza è occupata** | Stanza, Chi | nella stanza c'è almeno una cosa corrispondente |
| **la stanza è vuota** | Stanza, Chi | nella stanza non c'è nessuna cosa corrispondente |
| **il numero in una stanza** | Stanza, Confronto, Valore, Chi | il conteggio soddisfa il confronto scelto (`>`, `>=`, `<`, `<=`, `=`) |
| **un personaggio è in casa** | Personaggio | il personaggio è in vista |
| **un personaggio non c'è** | Personaggio | il personaggio non è in vista |
| **l'ora è tra** | Dalle, Alle | l'ora è nell'intervallo; un intervallo può scavalcare la mezzanotte (dalle 20:00 alle 07:00) |
| **un sensore** | Sensore, Misura, Confronto, Valore | la lettura attuale soddisfa il confronto scelto |
| **lo scenario è** | Scenario | lo scenario attuale è quello |
| **il barbecue è** | Acceso | il barbecue è acceso (o spento) |
| **l'auto è** | Stato | l'auto è in quello stato |
| **il termostato è** | Stato | il clima virtuale è caldo, freddo o normale |

## Allora: le azioni

| Azione | Campi | Cosa fa |
|---|---|---|
| **accendi una luce** | Stanza (o *Tutte le stanze*), Colore, Effetto, Luminosità, Durata (s) | accende i Pixels della stanza. La luminosità è relativa al massimo della casa. In una regola normale la luce dura *Durata* secondi, 30 se il campo resta vuoto; in una regola di allarme lascialo vuoto e la luce dura quanto l'allarme. |
| **spegni le luci di questa regola** | Regola | toglie le luci accese da questa regola, o da un'altra regola a scelta (la regola di partenza *Termostato: normale* toglie le luci di *Termostato: caldo* e *Termostato: freddo*) |
| **suona** | Suono: campanello breve, campanello, allarme, bip, notifica | fa sentire un suono |
| **di' una frase** | Testo in italiano, Testo in inglese, Parla anche in modalità | la casa dice il testo nella sua lingua del momento. *Normale* viene detto in modalità Normale e Chiacchierona, *Chiacchierona* solo in modalità Chiacchierona. In modalità Silenziosa compare solo come sottotitolo. |
| **manda una notifica** | Tipo: informazione, buona notizia, avviso, allarme; testi | un messaggio su tutti i telefoni e negli eventi; *allarme* fa anche vibrare i telefoni |
| **cambia scenario** | Scenario | cambia scenario |
| **fai festa** | | avvia una festa (se non ce n'è una in corso o in pausa) |
| **accendi il barbecue** | | fa girare la ventola del barbecue per la durata impostata |
| **aspetta** | Secondi | fa una pausa prima dell'azione successiva (fino a 10 minuti) |

Il formato delle regole accetta anche l'azione `{"type": "relay", "on": true, "duration_s": 20}`, che l'editor non mostra: fa girare la ventola come il barbecue (con gli stessi limiti di durata), ma senza annunciarlo e senza la grigliata pronta.

I testi possono contenere questi campi tra graffe, riempiti a partire dall'evento:

| Campo | Diventa |
|---|---|
| `{name}` | il nome del personaggio, oppure "qualcuno" |
| `{room}` | il nome della stanza ("Cucina") |
| `{room_in}` | la stanza come luogo ("in cucina", "in the kitchen") |
| `{count}` | il conteggio che ha fatto scattare la regola |
| `{temp}`, `{rh}` | temperatura e umidità del sensore |
| `{time}` | l'ora attuale |

**Effetti**: *Fisso*, *Respiro*, *Lampeggio*, *Onda*, *Arcobaleno*, *Scintille*, *Fuoco*, *Allarme* (lampeggio rosso a 2 Hz), *Aria fresca* (un'onda azzurra), *Tepore* (un bagliore arancione). Nessun effetto lampeggia più di 3 volte al secondo.

## Allarmi

Una regola segnata come **È un allarme (resta attivo finché dura)**:

- disegna le sue luci sul livello degli allarmi, sopra tutto tranne il lampeggio della lingua;
- mostra una notifica su tutti i telefoni: **rossa** (allarme) se la regola suona l'allarme o manda una notifica di tipo *allarme*, **ambra** (avviso) altrimenti; sulla piantina la stanza è rossa o ambra allo stesso modo;
- viene registrata negli eventi come avviso;
- dura quanto la situazione che l'ha fatta scattare: quando la persona esce dalla stanza, o il conteggio torna indietro, luci e notifica se ne vanno.

Questo si adatta a **resta in una stanza** e a **in una stanza sono più di / meno di**, le cui situazioni hanno una fine. Con qualsiasi altro evento (qualcuno entra in una stanza, un tasto, un orario) niente dice quando la situazione è finita, quindi l'allarme finisce da solo dopo 30 secondi.

**Solo presenze certe.** Le regole d'allarme contano soltanto le presenze di cui la casa è sicura: un personaggio che conosce (confermato o riconosciuto bene), oppure una cosa sconosciuta che sta lì, ferma e ben visibile, da almeno 6 secondi. Una macchia appena nata, un riflesso o una statuina ancora in mano non fanno suonare niente; se la presenza diventa certa mentre è ancora nel posto sorvegliato, l'allarme scatta in quel momento. Le altre regole e le luci che seguono le persone lavorano su tutto ciò che la casa vede.

**Inserito e disinserito.** L'allarme della casa si inserisce e si disinserisce come un antifurto, dal riquadro **Allarme** della pagina **Casa** o dal pulsante **Disinserisci** della notifica rossa (capitolo 6). Disinserito, nessuna regola d'allarme scatta e quelle in corso si spengono subito, con le loro luci; le altre regole vanno avanti. Reinserito, chi è già in un posto sorvegliato viene notato di nuovo, come se fosse appena entrato. Lo stato resta anche dopo un riavvio.

**Con le luci dell'allarme.** Le luci di un allarme lampeggiano, e il loro bagliore cambia i colori delle stanze vicine. Mentre una luce della casa è animata (un allarme, l'onda del climatizzatore, uno scenario), la visione non cambia idea: i personaggi restano dove erano e con il loro nome, nessun nome passa a un bagliore, e la casa non si adatta a una "luce della sala" che è solo quella dell'allarme. Così l'allarme resta finché la statuina è nel posto sorvegliato, e finisce quando una mano la porta via. In modalità *Silenziosa* le frasi dell'allarme compaiono solo scritte; sirena, luci e notifiche ci sono sempre.

## Priorità e livelli delle luci

Ogni luce ha una pila di livelli. Il livello attivo più alto decide cosa mostra la luce; quando scade o viene tolto, torna visibile il livello sottostante. Dal basso:

| Livello | Priorità |
|---|---|
| luci che seguono le persone | 10 |
| scenario | 30 |
| regole | la priorità della regola (1–98), 50 di serie |
| luci accese o spente da **Comandi** o a voce | 55 |
| l'onda del climatizzatore o del riscaldamento chiesta a voce | 60 |
| regole di allarme | 95 |
| il lampeggio della lingua (verde o rosso per un secondo) | 99 |

Durante una festa il microcontrollore gestisce da solo lo spettacolo di luci, a tempo con la musica; quando la festa finisce la casa ridisegna ogni luce a partire dai suoi livelli.

**Luci che seguono le persone.** Sono spente di serie, e la webapp non ha un interruttore per accenderle: il loro bagliore sui muri e sul pavimento confonde la webcam. Per accenderle, in `var/config/settings.json` metti `"follow": true` nella sezione `"lights"` e riavvia `domotiq`.

Quando sono accese, una stanza con almeno una persona riceve una luce bianca calda (`#fff2e0`) al 60 % (del massimo della casa), un solo colore per tutti; si spegne 3 secondi dopo che l'ultima persona è uscita. Gli animali non accendono le luci. In garage conta anche l'auto: la luce resta accesa mentre l'auto arriva e finché non è parcheggiata da 10 secondi. Il giardino e il vialetto non hanno luce; la luce del locale tecnico è la matrice LED della UNO Q. Colore, luminosità e ritardo stanno nella stessa sezione (`follow_color`, `follow_brightness`, `follow_off_delay_s`), insieme a `follow_favourite`, spento di serie, che nello scenario Normale dà alla stanza il colore preferito di chi entra.

## Scenari

| Scenario | Luci |
|---|---|
| **Normale** | le luci seguono le persone, spente di serie (vedi sopra); quando sono accese, all'avvio aspettano 15 secondi dopo la prima presenza vista, mentre la webcam cerca le statuine |
| **Cinema** | in soggiorno il bagliore azzurro e tremolante di uno schermo (*Scintille*), tutte le altre stanze spente, anche dove c'è gente |
| **Relax** | in soggiorno un caminetto (*Fuoco*), in camera una luce arancione che respira; con le luci che seguono le persone accese, dove c'è gente luci calde e tenui |
| **Notte** | tutto spento tranne una lucina arancione in bagno; con le luci che seguono le persone accese, chi si alza trova una luce di cortesia arancione molto tenue |
| **Via** | la casa vuota sembra abitata: una stanza alla volta (cucina, soggiorno, camera o bagno) si accende per 15-30 secondi, poi un'altra. La regola di partenza *Intruso con la casa in modalità Via* sorveglia la casa |

Gli scenari si scelgono a voce ("Scenario cinema", "Good night") o con una regola, e la casa dice il nome del nuovo scenario.

## Le regole di partenza

| Regola | Quando | Allora | All'inizio |
|---|---|---|---|
| **Locale tecnico vietato** (allarme) | una persona resta nel locale tecnico più di 5 s (si ripete ogni 10 s) | soggiorno e garage lampeggiano di rosso, suono di allarme, "Attenzione: il locale tecnico è riservato!", notifica di allarme "{name} è nel locale tecnico" | attiva |
| **Bagno al massimo 1** (allarme) | più di 1 persona in bagno per 2 s (si ripete ogni 15 s) | il bagno lampeggia di arancione, "Il bagno è occupato! Aspetta il tuo turno.", avviso "{count} persone in bagno" | attiva |
| **Doccia** | la doccia inizia | onda azzurra in bagno per un massimo di 3 minuti, "Accendo l'aspiratore del bagno.", notifica "Doccia in corso" | attiva |
| **Doccia finita** | la doccia finisce | toglie le luci di *Doccia* | attiva |
| **Termostato: caldo** | il termostato passa a caldo | onda azzurra ovunque per un massimo di 2 minuti, "Fa caldo! Accendo il climatizzatore.", notifica con la temperatura | attiva |
| **Termostato: freddo** | il termostato passa a freddo | bagliore arancione caldo ovunque per un massimo di 2 minuti, "Fa freddo: accendo il riscaldamento." | attiva |
| **Termostato: normale** | il termostato torna normale | toglie le luci di *Termostato: caldo* e *Termostato: freddo*; in modalità Chiacchierona "La temperatura è tornata normale." | attiva |
| **Auto arrivata** | l'auto arriva | "Bentornato a casa!", notifica "L'auto è in garage" | attiva |
| **Auto partita** | l'auto parte | "Buon viaggio!", notifica "L'auto è uscita dal garage" | attiva |
| **Grigliata pronta** | la grigliata è pronta | "La grigliata è pronta, tutti in giardino!", notifica | attiva |
| **Intruso con la casa in modalità Via** | una persona entra in una qualsiasi stanza della casa, se lo scenario è Via | tutte le luci lampeggiano di rosso per 10 s, suono di allarme, "Intruso in casa! {name} è {room_in}.", notifica di allarme | attiva |
| **Festa in soggiorno** | più di 3 persone in soggiorno per 3 s | avvia una festa | disattivata |
| **Grigliata in compagnia** | più di 1 persona in giardino per 10 s | accende il barbecue | disattivata |

Chi conta: le regole di partenza che riguardano le persone usano il tipo *persona*, quindi gli animali non fanno mai scattare l'allarme del locale tecnico o del bagno. La luce del garage per l'auto viene dalle luci che seguono le persone (spente di serie), non da una regola.

## Chi può cambiare le regole

- **Chiunque**, dalla webapp. La prima volta la webapp chiede un soprannome facoltativo, che compare nel registro delle modifiche.
- **Ogni modifica viene registrata** sulla scheda: ora, identificativo del telefono, soprannome, cosa è stato creato, modificato, attivato o disattivato, eliminato o ripristinato, con la regola prima e dopo. Si legge in **Eventi → Modifiche**.
- **Le regole eliminate finiscono nel cestino** per 24 ore e si ripristinano da **Impostazioni → Cestino**.
- **Regole di partenza** (in **Impostazioni → Backup**) sostituisce tutte le regole con quelle con cui la casa è partita. Anche questo ripristino viene registrato.
- Le regole viaggiano nello zip del **backup**, che si può scaricare e ripristinare (vedi il [capitolo 6](06-webapp.md#impostazioni)).

Avanti: [attribuzioni](10-attribuzioni.md).
