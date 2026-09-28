# Decisioni tecniche

Ogni decisione ha la data, il contesto, la scelta e il motivo. Quando una decisione cambia, la voce vecchia resta e se ne aggiunge una nuova.

---

### D-01 — Servizi nativi invece di un'app App Lab (28/9)
**Scelta:** l'applicazione gira come servizio systemd in un ambiente Python sulla scheda; il firmware della MCU si compila e si carica dalla scheda con `arduino-cli`.
**Perché:** su UNO Q App Lab non ha riconoscimento né sintesi vocale offline; le app girano in Docker, scaricano le dipendenze al primo avvio e non ripartono da sole se si bloccano. L'approccio nativo è già collaudato su questa scheda da Amelie 2.0.

### D-02 — Linux decide, la MCU esegue (28/9)
**Scelta:** stato, regole e priorità stanno su Linux. La MCU gestisce i Modulino, disegna gli effetti di luce (party compreso), legge tasti e sensori, protegge relè e alimentazione.
**Perché:** il collegamento fra i due lati porta 256 byte a messaggio e circa 7 ms per chiamata. Un'animazione a 30 immagini al secondo non ci passa; un comando "effetto X in stanza Y" sì.

### D-03 — I2C scritto a mano (28/9)
**Scelta:** nessuna libreria Modulino nello sketch. Ogni transazione ha un'attesa limitata e un esito verificato.
**Perché:** la libreria ufficiale, su UNO Q, rende indistinguibili i moduli assenti da quelli presenti e può bloccare la MCU per sempre se il sensore di distanza non risponde.

### D-04 — Limite di corrente sui Pixels (28/9)
**Scelta:** il firmware stima la corrente di ogni fotogramma e riduce le luci oltre 450 mA totali; luminosità massima iniziale 30 %.
**Perché:** cinque Pixels a bianco pieno arriverebbero a circa 1,3 A sul 3,3 V del Qwiic (connettore da 1 A, regolatore da 2 A condiviso). Senza un misuratore di corrente i valori restano prudenti.

### D-05 — Riconoscimento senza addestramento (28/9)
**Scelta:** differenza dalla casa vuota in Lab, colore, dimensione, parallasse, tracciamento con abbinamento ungherese; un rilevatore pre-addestrato (YOLOX-Nano, Apache-2.0) solo per stimare la categoria di un oggetto nuovo.
**Perché:** i personaggi sono piccoli (circa 11 pixel di base a risoluzione di rete), il numero di identità non ha limiti e si aggiungono dal vivo. Il metodo classico registra un personaggio in secondi e sta in un core.

### D-06 — Identità di personaggi dello stesso colore (29/9)
**Scelta:** l'identità segue il personaggio anche mentre una mano lo sposta ("trasporto a mano"); quando l'abbinamento è ambiguo la casa chiede conferma sulla webapp e a voce.
**Perché:** due personaggi possono avere lo stesso colore; il colore da solo non basta, la continuità del movimento sì, e dove non basta nemmeno quella si chiede.

### D-07 — Voce (29/9)
**Scelta:** Vosk (modelli piccoli IT ed EN) a frasi chiuse per nomi e sì/no; un motore per frasi libere; Qwen2.5-0.5B tramite llama.cpp traduce le frasi libere in un intento vincolato in JSON; la risposta la compone il codice dai dati veri; Piper come programma separato per parlare.
**Perché:** le frasi libere si capiscono solo con un modello linguistico, ma un modello così piccolo può sbagliare: fargli scegliere cosa fare e mai cosa dire elimina le risposte inventate.

### D-08 — Licenza MIT per il software (29/9)
**Scelta:** codice sotto MIT, tutto il resto sotto CC-BY-4.0. Piper (GPL-3.0) si usa come programma esterno, in un ambiente separato, senza importarlo.
**Perché:** scelta dell'autore. Un programma esterno chiamato da riga di comando è aggregazione, non opera derivata: il codice resta MIT senza ambiguità.

### D-09 — Un solo Buttons (29/9)
**Scelta:** tre tasti: parla, citofono, lingua. Party, grigliata e scenari da voce e webapp.
**Perché:** con un solo Buttons non serve cambiare indirizzi, la catena del canale 6 si accorcia e il totem si semplifica.

### D-10 — Rete senza captive portal (28/9)
**Scelta:** hotspot WPA2 a 2,4 GHz per casa, sottoreti diverse (10.42.1.0/24 e 10.42.2.0/24), nomi `casaN.lan` e `casaN.local`, QR su cartello A4.
**Perché:** la finestra di accesso dei captive portal non permette la fotocamera e su iPhone si chiude cambiando app; l'indirizzo numerico funziona sempre.

### D-11 — Core della MCU (29/9)
**Scelta:** `arduino:zephyr` 0.52.0 e `Arduino_RouterBridge` 0.4.3.
**Perché:** versioni collaudate sulla stessa scheda; dalla 0.55 cambia il modo di avvio dello sketch e va verificato che riparta dopo una mancanza di corrente prima di adottarlo.

### D-12 — Libreria ALSA da backports (29/9)
**Scelta:** `libasound2t64`, `libasound2-data`, `libatopology2t64` da trixie-backports, come già i profili audio.
**Perché:** l'immagine preferisce i profili audio da backports; la loro versione attuale richiede la libreria di backports e senza di essa l'aggiornamento di sistema si ferma.

### D-13 — Core 1.0.0 in modalità Immediate (29/9, sostituisce D-11)
**Scelta:** `arduino:zephyr` 1.0.0 con `wait_linux_boot=no`, `Arduino_RouterBridge` 0.4.3.
**Perché:** l'aggiornamento di sistema installa la 1.0.0; tornare alla 0.52.0 vorrebbe dire combattere l'aggiornatore a ogni aggiornamento. La modalità Immediate fa partire lo sketch all'accensione, così il relè a ritenuta si spegne subito dopo un blackout. Da verificare con una vera interruzione di corrente sulla casa montata.
