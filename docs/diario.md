# Diario di sviluppo

Note tecniche in ordine cronologico: cosa è stato fatto, perché, quali problemi sono emersi e come sono stati risolti. Le decisioni di progetto sono raccolte a parte in [decisioni.md](decisioni.md); strumenti, versioni e licenze in [strumenti-e-licenze.md](strumenti-e-licenze.md).

---

## 28 settembre 2026 — Analisi e verifiche

**Punto di partenza.** Il diorama v3 è definito nel CAD (`build_v3.py`, 90 pezzi numerati, report di montaggio). Il repository contiene solo la licenza. Scadenza: 7 ottobre, due case.

**Verifiche sulla piattaforma**, prima di scegliere l'architettura:

- Il connettore Qwiic della UNO Q è cablato sull'I2C4 dello STM32U585: i Modulino li vede solo il microcontrollore. Linux ci parla attraverso `arduino-router` (MessagePack-RPC su `/run/arduino-router.sock`).
- Un processo Linux che non è un'app di App Lab può ricevere le notifiche della MCU registrando il nome sul router con `$/register`.
- Il collegamento seriale fra i due lati va a 115200 baud, con messaggi di al massimo 256 byte e circa 7 ms per chiamata. Troppo poco per mandare animazioni di luce da Linux: gli effetti devono girare sulla MCU.
- Su UNO Q le brick di App Lab non offrono riconoscimento né sintesi vocale offline (esistono solo per VENTUNO Q); il Python delle app gira in Docker e installa le dipendenze da internet al primo avvio. Si usano quindi servizi systemd nativi.
- La libreria Arduino_Modulino 0.9.1 (17/9/2026) ha ancora comportamenti che su UNO Q nascondono i guasti: `begin()` con indirizzo esplicito non tocca il bus, `write()` risponde sempre `true`, il driver del VL53L4CD ritenta all'infinito. Le transazioni I2C si scrivono a mano nello sketch.
- Indirizzi dai sorgenti e dai datasheet: Hub TCA9548A 0x70, Latch Relay 0x02, Buttons 0x3E, Thermo 0x44, Distance 0x29, Pixels 0x36 (valori a 7 bit).
- Un Pixels a bianco pieno assorbe fino a 264 mA dal 3,3 V del Qwiic: cinque moduli superano il limite del connettore. Serve un limite di corrente nel firmware.
- La C270 ha fuoco fisso. Il CAD usa i 55° in diagonale del costruttore sul 16:9; una calibrazione pubblicata indica che il 720p è un ritaglio del sensore 4:3. Da misurare sulla camera vera: in 4:3 la base intera ci sta con margine.
- Il Wi-Fi (WCN3980) funziona da access point con NetworkManager, quasi certamente solo a 2,4 GHz.
- Su un telefono Android che non accetta "resta connesso", il traffico verso l'indirizzo locale passa sui dati mobili e non arriva. La finestra di accesso dei captive portal non permette la fotocamera: niente captive portal, si entra da QR.
- Senza HTTPS non ci sono service worker né notifiche di sistema, ma `<input type="file" capture>` apre la fotocamera del telefono: basta per fotografare i personaggi.

**Riconoscimento.** Una rete di rilevamento addestrata vedrebbe la base di un personaggio (25 mm) come una decina di pixel e richiederebbe centinaia di immagini etichettate. Il metodo scelto è classico: differenza dalla casa vuota, colore, tracciamento, con la correzione della parallasse per i personaggi alti. Nessun addestramento: un personaggio nuovo si registra in pochi secondi.

---

## 29 settembre 2026 — Risposte, specifica, prima scheda

**Risposte del secondo giro.** Un solo Modulino Buttons (tasti parla, citofono, lingua), licenza MIT per il software, domande libere con un modello linguistico piccolo, registrazione dei personaggi da webapp, citofono e voce, regole modificabili da chiunque con registro delle modifiche. La specifica è in [specifica.md](specifica.md).

**Preparazione di casa1.**
- Immagine di fabbrica del 10 dicembre 2025 (Debian 13, kernel 6.16, arduino-app-cli 0.7.0); l'utente `arduino` nasce senza password: la si imposta con lo script di prima configurazione dell'immagine (`/usr/local/bin/arduino-passwd`).
- Nome `casa1`, fuso orario Europe/Rome, rete Wi-Fi di sviluppo.
- **SSH non partiva**: `sshd: no hostkeys available`. Sull'immagine nuova le chiavi dell'host le genera App Lab durante la prima configurazione; senza App Lab vanno create con `ssh-keygen -A`.
- **avahi-daemon è spento di fabbrica** (lo accende la modalità di rete di App Lab): senza, `casa1.local` non si risolve.
- Accesso dal PC con una chiave dedicata (`~/.ssh/id_ed25519_domotiq`, alias `casa1` in `~/.ssh/config`).
- **`arduino-app-cli system update` va lanciato come utente `arduino`**, non con `sudo`: rifiuta di girare come root e chiama `sudo apt-get` da sé. Lanciato dentro una sessione `adb shell`, si interrompe se la sessione si chiude: meglio `systemd-run --uid=arduino`.
- **L'aggiornamento si fermava** con "alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)". L'immagine preferisce da trixie-backports (priorità 900) i profili audio, il kernel, i firmware e mesa, ma non la libreria ALSA. La nuova versione dei profili richiede la libreria di backports. Rimedio: installare da backports anche `libasound2t64`, `libasound2-data`, `libatopology2t64`, poi ripetere l'aggiornamento. Da fare anche sulla casa 2, e lo script d'installazione lo gestisce.
