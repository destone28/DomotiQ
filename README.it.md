# DomotiQ – una casa intelligente su una sola Arduino UNO Q

![Il diorama DomotiQ con il palo della webcam](https://raw.githubusercontent.com/destone28/DomotiQ/main/docs/images/render/01_assieme_con_palo.png)

DomotiQ è una casa intelligente in scala 1:20 costruita per le fiere Arduino. Una webcam su un palo guarda la casa dall'alto e riconosce chi c'è e in quale stanza: personaggi, animali, un'auto giocattolo e qualsiasi oggetto un visitatore ci metta dentro. Le luci seguono le persone di stanza in stanza, la casa fa rispettare le sue regole (nessuno nel locale tecnico, in bagno uno alla volta), reagisce alla doccia, all'auto che torna a casa o al barbecue, fa partire una festa con musica composta da sé, e parla: i visitatori le fanno domande in italiano o in inglese, suonano il citofono e presentano personaggi nuovi a voce.

Tutto gira su una Arduino UNO Q 4GB, senza internet. I visitatori entrano nel Wi-Fi della casa con un QR e usano il telefono come telecomando, come finestra sulla webcam e per scrivere le regole.

Realizzato da Emilio Destratis (destratis.it) in collaborazione con Arduino.

English version: [README.md](https://github.com/destone28/DomotiQ/blob/main/README.md)

# Cosa fa

- Segue persone, animali, l'auto e gli oggetti con la visione artificiale: posizione in millimetri, stanza, conteggi, identità e storico.
- Luci che seguono le persone, scenari (normale, relax, cinema, notte, via) ed effetti disegnati dal microcontrollore.
- Regole Quando/Se/Allora che chiunque può cambiare dalla webapp, con il registro di chi ha cambiato cosa.
- Vincoli di partenza: locale tecnico vietato dopo 5 secondi, bagno per una persona alla volta.
- Un clima virtuale: un termostato che si scalda con un dito e un bagno la cui umidità sale quando qualcuno "fa la doccia" (basta soffiare sul sensore).
- Un citofono vocale che fa entrare i personaggi e registra quelli nuovi.
- Domande e comandi a voce in italiano e in inglese, anche con frasi libere; alle domande sulla casa risponde con il suo stato reale.
- Storie, ricordi e risposte sulla vita di casa (bollette, compleanni, feste passate), generati sulla scheda da un database locale di pezzi in italiano e in inglese, con personaggi che mantengono la loro personalità fino al riavvio.
- Una festa con musica elettronica generata dal codice e giochi di luce, e un barbecue con una ventola vera.
- Un garage che vede arrivare e parcheggiare l'auto.
- Una webapp completa servita dalla scheda sul suo hotspot, con il bagno sempre sfocato nella diretta.

# Come funziona

La UNO Q ha due cervelli. Il processore Qualcomm fa girare Debian Linux e prende le decisioni; il microcontrollore STM32U585 governa il bus Qwiic e pilota tutti i Modulino (cinque Pixels, due Thermo, Buttons, Latch Relay e l'Hub che divide il bus in canali). I due si parlano attraverso il router della scheda con MessagePack-RPC: Linux decide, il microcontrollore esegue e riferisce tasti e sensori. Gli effetti di luce e l'animazione della festa girano sul microcontrollore, così restano fluidi qualunque cosa stia facendo Linux, e una guardia spegne la ventola se Linux tace.

Su Linux un'applicazione Python (FastAPI, asyncio) tiene lo stato della casa, fa girare il motore delle regole, la voce e la webapp. La visione gira in un processo separato, la sintesi vocale e il modello linguistico in servizi propri: un passaggio lento non blocca mai il resto.

# Visione artificiale

Il riconoscimento usa la visione artificiale classica, senza addestramento: un personaggio nuovo si registra in pochi secondi.

- Quattro tocchi sugli angoli della base nella webapp danno la geometria fra immagine e pavimento; la posizione della camera, nota dal modello CAD, corregge la parallasse dei personaggi alti.
- Ogni fotogramma si confronta con l'immagine della casa vuota nello spazio colore Lab, dopo aver corretto la luce stanza per stanza e canale per canale: le luci colorate della casa e quelle della sala non creano fantasmi. Le ombre non contano.
- Ogni personaggio ha una firma di colore. Le tracce si seguono da un fotogramma all'altro con il metodo ungherese; le identità si abbinano per colore, e due personaggi dello stesso colore si distinguono seguendoli. Quando la mano di un visitatore ne prende uno, la casa non lo perde, e chiede quando non può esserne sicura.
- Quando un personaggio si registra con una foto dal telefono, un rilevatore YOLOX-Nano (machine learning, addestrato sul dataset COCO) gira sulla scheda e propone la categoria: persona, cane, gatto, altro animale, auto o oggetto.

# Voce e modello linguistico

Il totem ha tre tasti: parla (si tiene premuto mentre si parla), citofono e lingua. Il riconoscimento vocale è Vosk, senza internet, con grammatiche ristrette per i nomi e per le risposte sì/no. Un analizzatore a regole, veloce, capisce le richieste più comuni; le frasi libere vanno a un piccolo modello linguistico di grandi dimensioni (LLM: Qwen2.5-0.5B-Instruct con llama.cpp) che gira sulla scheda e sceglie soltanto cosa fare in un elenco fisso di intenti. Le risposte si compongono sempre dallo stato vero della casa, quindi la casa non può inventare nulla. Piper pronuncia le risposte con una voce italiana e una inglese.

# La webapp

I telefoni entrano nell'hotspot della casa (DomotiQ-Casa1 o DomotiQ-Casa2) dal QR sul cartello A4 e aprono la pagina della casa. Tutti possono vedere la casa, guardare la diretta, dare comandi, leggere gli eventi, modificare le regole e registrare personaggi. Gli strumenti dello staff (calibrazione, raccolta del dataset, diagnostica, impostazioni) chiedono un PIN.

![Casa, diretta, personaggi e regole sul telefono](https://raw.githubusercontent.com/destone28/DomotiQ/main/docs/images/screens/it/home.png)

# Hardware per una casa

- Arduino UNO Q 4GB.
- Modulino: cinque Pixels, due Thermo, un Buttons, un Latch Relay, un Hub.
- Webcam Logitech C270 sul palo stampato.
- Hub USB-C UGREEN Revodok 105 e alimentatore UGREEN da 65 W.
- Scheda audio USB UGREEN US205, microfono lavalier con spina TRS da 3,5 mm, casse alimentate da USB con jack da 3,5 mm.
- Una ventola da 5 V e 40 mm per il barbecue, comandata dal Latch Relay.
- La casa stampata in 3D: i file STL numerati sono nella cartella hardware, e ogni pezzo ha il suo numero inciso.

# Costruiscila anche tu

- Preparare la scheda: [docs/it/01-preparare-uno-q.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/01-preparare-uno-q.md)
- Installare il software: [docs/it/02-installazione.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/02-installazione.md)
- Stampa e montaggio: [docs/it/03-stampa-e-montaggio.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/03-stampa-e-montaggio.md)
- Collegamenti: [docs/it/04-collegamenti.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/04-collegamenti.md)
- Collaudo e calibrazione: [docs/it/05-collaudo.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/05-collaudo.md)
- Usare la webapp: [docs/it/06-webapp.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/06-webapp.md)
- Riconoscimento e identità: [docs/it/07-riconoscimento-e-identita.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/07-riconoscimento-e-identita.md)
- Voce: [docs/it/08-voce.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/08-voce.md)
- Regole: [docs/it/09-regole.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/09-regole.md)
- Attribuzioni: [docs/it/10-attribuzioni.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/10-attribuzioni.md)
- Risoluzione dei problemi: [docs/it/11-risoluzione-problemi.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/11-risoluzione-problemi.md)
- Guida rapida per lo staff dello stand: [docs/it/guida-rapida-staff.md](https://github.com/destone28/DomotiQ/blob/main/docs/it/guida-rapida-staff.md)

L'installazione completa è un solo comando sulla scheda, quando la scheda ha internet:

```
git clone https://github.com/destone28/DomotiQ ~/domotiq
cd ~/domotiq && bash scripts/install.sh --house 1
```

Niente hardware a portata di mano? La casa gira in simulazione su qualsiasi PC, con personaggi virtuali da trascinare sulla piantina:

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m domotiq.app --simulate
```

Poi si apre http://localhost:8080 nel browser.

# Il repository

- src/domotiq: l'applicazione (stato della casa, regole, visione, voce, audio, webapp).
- firmware/domotiq_mcu: lo sketch del microcontrollore.
- data/house.json: la mappa della casa, condivisa da visione, regole e webapp.
- data/stories.json: i pezzi che la casa combina in storie, ricordi e risposte, in italiano e in inglese.
- hardware/stl: i file di stampa numerati.
- scripts: installazione, hotspot, copia su una scheda, schermate.
- tests: test del nucleo, della voce, della visione (su immagini sintetiche) e delle API web.
- docs: guide in inglese e in italiano, specifica, diario di sviluppo, decisioni, strumenti e licenze.

# Licenze

Il codice sorgente è rilasciato con licenza MIT, vedi [LICENSE](https://github.com/destone28/DomotiQ/blob/main/LICENSE). Documentazione, immagini, file di stampa 3D e dati della casa sono rilasciati con licenza Creative Commons Attribuzione 4.0, vedi [LICENSE-DOCS.md](https://github.com/destone28/DomotiQ/blob/main/LICENSE-DOCS.md). Componenti, modelli e voci di terze parti mantengono le loro licenze, elencate nelle [attribuzioni](https://github.com/destone28/DomotiQ/blob/main/docs/it/10-attribuzioni.md). I modelli dei personaggi e dell'auto sono progetti di terze parti e non sono inclusi.
