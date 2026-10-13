# DomotiQ – una casa intelligente su una sola Arduino UNO Q

**Emilio Destratis** · [destratis.it](https://destratis.it) · Progetto Arduino

![Il diorama DomotiQ con il palo della webcam](https://raw.githubusercontent.com/destone28/DomotiQ/main/docs/images/render/01_casa_completa.png)

DomotiQ è una casa intelligente in scala 1:20. Una webcam su un palo guarda la casa dall'alto e riconosce chi c'è e in quale stanza: personaggi, animali, un'auto giocattolo e qualsiasi oggetto tu ci metta dentro. La casa fa rispettare le sue regole (nessuno nel locale tecnico, in bagno uno alla volta), reagisce alla doccia, all'auto che torna a casa o al barbecue, fa partire una festa con musica composta da sé, e parla: puoi farle domande in italiano o in inglese, suonare il citofono e presentarle personaggi nuovi a voce.

Tutto gira su una Arduino UNO Q 4GB, senza internet. I telefoni entrano nel Wi-Fi della casa e diventano telecomando, finestra sulla webcam e strumento per scrivere le regole.

English version: [README.md](https://github.com/destone28/DomotiQ/blob/main/README.md)

# Cosa fa

- Segue persone, animali, l'auto e gli oggetti con la visione artificiale: posizione in millimetri, stanza, conteggi, identità e storico.
- Scenari (normale, relax, cinema, notte, via), che si scelgono a voce o con una regola, luci per stanza ed effetti disegnati dal microcontrollore. Le luci che seguono le persone ci sono, ma sono spente di serie perché il loro bagliore confonde la webcam.
- Regole Quando/Se/Allora che chiunque può cambiare dalla webapp, con il registro di chi ha cambiato cosa.
- Vincoli di partenza: locale tecnico vietato dopo 5 secondi, bagno per una persona alla volta.
- Un clima virtuale: un termostato che si scalda con un dito e un bagno la cui umidità sale quando qualcuno "fa la doccia" (basta soffiare sul sensore).
- Un citofono vocale che fa entrare i personaggi e registra quelli nuovi.
- Domande e comandi a voce in italiano e in inglese, anche con frasi libere; alle domande sulla casa risponde con il suo stato reale.
- Storie, ricordi e risposte sulla vita di casa (bollette, compleanni, feste passate), generati sulla scheda da un database locale di pezzi in italiano e in inglese, con personaggi che mantengono la loro personalità fino al riavvio.
- Una festa con musica elettronica generata dal codice e giochi di luce, e un barbecue con una ventola vera.
- Un garage che vede arrivare e parcheggiare l'auto.
- Una webapp completa servita dalla scheda sul suo hotspot, con il bagno sfocato nella diretta (di serie).

# Componenti usati in questo progetto

## Hardware

- Arduino UNO Q 4GB.
- Modulino: cinque Pixels, due Thermo, un Buttons, un Latch Relay, un Hub.
- Webcam Logitech C270 sul palo stampato.
- Hub USB-C UGREEN Revodok 105 e alimentatore UGREEN da 65 W.
- Scheda audio USB UGREEN US205, microfono lavalier con spina TRS da 3,5 mm, casse alimentate da USB con jack da 3,5 mm.
- Una ventola da 5 V e 40 mm per il barbecue, comandata dal Latch Relay.
- La casa stampata in 3D: i file STL numerati sono nella cartella hardware, e ogni pezzo ha il suo numero inciso.
- Statuine, animali e un'auto giocattolo: modelli di terze parti, non inclusi; il [capitolo 3](https://github.com/destone28/DomotiQ/blob/main/docs/it/03-stampa-e-montaggio.md) dà le misure che funzionano.

## Strumenti

- Una stampante 3D.
- Un PC con `adb` (Android platform tools) e un cavo USB-C, per la prima configurazione della scheda.
- Una rete Wi-Fi con internet, per l'aggiornamento del sistema e per l'installazione. Dopo, la casa funziona senza internet.

# Come funziona

La UNO Q ha due cervelli. Il processore Qualcomm fa girare Debian Linux e prende le decisioni; il microcontrollore STM32U585 governa il bus Qwiic e pilota tutti i Modulino (cinque Pixels, due Thermo, Buttons, Latch Relay e l'Hub che divide il bus in canali). I due si parlano attraverso il router della scheda con MessagePack-RPC: Linux decide, il microcontrollore esegue e riferisce tasti e sensori. Gli effetti di luce e l'animazione della festa girano sul microcontrollore, così restano fluidi qualunque cosa stia facendo Linux, e una guardia spegne la ventola se Linux tace.

Su Linux un'applicazione Python (FastAPI, asyncio) tiene lo stato della casa, fa girare il motore delle regole, la voce e la webapp. La visione gira in un processo separato, la sintesi vocale e i modelli linguistici in servizi propri: un passaggio lento non blocca mai il resto.

## Visione artificiale

Il riconoscimento si basa sulla visione artificiale classica: un personaggio nuovo si registra in pochi secondi, senza addestrare un modello.

- Quattro tocchi sugli angoli della base nella webapp danno la geometria fra immagine e pavimento; la posizione della camera, nota dal modello CAD, corregge la parallasse dei personaggi alti.
- Ogni fotogramma si confronta con l'immagine della casa vuota nello spazio colore CIELAB, dopo aver corretto la luce stanza per stanza e canale per canale: le luci colorate della casa e quelle della sala non creano fantasmi. Le ombre non contano.
- Ogni personaggio ha una firma di colore. Le tracce si seguono da un fotogramma all'altro con il metodo ungherese; le identità si abbinano per colore, e due personaggi dello stesso colore si distinguono seguendoli. Quando una mano ne prende uno, la casa non lo perde, e chiede quando non può esserne sicura.
- Una piccola rete neurale, che addestri sul PC con le registrazioni della tua casa, dà un secondo parere su ogni macchia: quale personaggio è, oppure "niente". Senza il file della rete la casa funziona con il solo metodo classico.
- Quando un personaggio si registra con una foto dal telefono, un rilevatore YOLOX-Nano (machine learning, addestrato sul dataset COCO) gira sulla scheda e propone la categoria: persona, cane, gatto, altro animale, auto o oggetto.

## Voce e modello linguistico

Il totem del citofono ha tre tasti: parla (si tiene premuto mentre si parla), citofono e lingua. Il riconoscimento vocale è Vosk, senza internet, con grammatiche ristrette per i nomi e per le risposte sì/no. Un analizzatore a regole, veloce, capisce le richieste più comuni; le frasi libere vanno a un piccolo modello linguistico di grandi dimensioni (LLM: Qwen2.5-0.5B-Instruct con llama.cpp) che gira sulla scheda e sceglie soltanto cosa fare in un elenco fisso di intenti. Le risposte sulla casa si compongono sempre dal suo stato vero, quindi lì la casa non può inventare nulla. Alle domande sul mondo ("Perché il cielo è blu?") la casa chiede se vuoi aspettare: se sì, un secondo modello, Qwen3.5-0.8B, scrive la risposta in 20-50 secondi; è piccolo, e sui fatti può sbagliare. Piper pronuncia le risposte con una voce italiana e una inglese.

## La webapp

I telefoni entrano nell'hotspot della casa (`DomotiQ-Casa1`) con la sua password e aprono `http://10.42.1.1/`. Tutti possono fare tutto, senza PIN: vedere la casa, guardare la diretta, dare comandi, leggere gli eventi, modificare le regole, registrare personaggi, inserire e disinserire l'allarme, calibrare la webcam, leggere la diagnostica e cambiare le impostazioni. Ogni modifica resta nel registro e le cose eliminate nel cestino per 24 ore.

![Casa, diretta, personaggi e regole sul telefono](https://raw.githubusercontent.com/destone28/DomotiQ/main/docs/images/screens/it/home.png)

# Costruiscila passo per passo

La guida completa è in [docs/it](https://github.com/destone28/DomotiQ/blob/main/docs/it/index.md). I capitoli seguono l'ordine in cui costruisci la casa:

1. **Prepara la scheda**: password, SSH, nome di rete, aggiornamento del sistema, accesso dal PC. [Capitolo 1](https://github.com/destone28/DomotiQ/blob/main/docs/it/01-preparare-uno-q.md)
2. **Installa il software** con un solo comando sulla scheda, quando la scheda ha internet:

   ```
   git clone https://github.com/destone28/DomotiQ ~/domotiq
   cd ~/domotiq && bash scripts/install.sh
   ```

   Opzioni, servizi, hotspot e aggiornamenti: [capitolo 2](https://github.com/destone28/DomotiQ/blob/main/docs/it/02-installazione.md).
3. **Stampa e monta la casa**: i file STL numerati, i colori e l'ordine di montaggio. [Capitolo 3](https://github.com/destone28/DomotiQ/blob/main/docs/it/03-stampa-e-montaggio.md)
4. **Fai i collegamenti**: la catena Qwiic attraverso il Modulino Hub, l'alimentazione, relè e ventola, l'audio, la webcam. [Capitolo 4](https://github.com/destone28/DomotiQ/blob/main/docs/it/04-collegamenti.md)
5. **Collauda e calibra**: verifica ogni parte, calibra la webcam, registra il primo personaggio, prova la voce e i telefoni. [Capitolo 5](https://github.com/destone28/DomotiQ/blob/main/docs/it/05-collaudo.md)
6. **Usa la casa**:
   - [Usare la webapp](https://github.com/destone28/DomotiQ/blob/main/docs/it/06-webapp.md)
   - [Riconoscimento e identità](https://github.com/destone28/DomotiQ/blob/main/docs/it/07-riconoscimento-e-identita.md)
   - [Voce](https://github.com/destone28/DomotiQ/blob/main/docs/it/08-voce.md)
   - [Regole](https://github.com/destone28/DomotiQ/blob/main/docs/it/09-regole.md)

Per tutti i giorni c'è la [guida rapida](https://github.com/destone28/DomotiQ/blob/main/docs/it/guida-rapida.md) di una pagina; se qualcosa non va, la [risoluzione dei problemi](https://github.com/destone28/DomotiQ/blob/main/docs/it/11-risoluzione-problemi.md). Le licenze di ogni componente sono nelle [attribuzioni](https://github.com/destone28/DomotiQ/blob/main/docs/it/10-attribuzioni.md).

## Prova senza hardware

La casa gira in simulazione su qualsiasi PC, con personaggi virtuali da mettere sulla piantina:

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m domotiq --simulate
```

Poi apri http://localhost:8080 nel browser; i personaggi virtuali si aggiungono dalla pagina http://localhost:8080/#/sim.

# Il repository

- src/domotiq: l'applicazione (stato della casa, regole, visione, voce, audio, webapp).
- firmware/domotiq_mcu: lo sketch del microcontrollore.
- data/house.json: la mappa della casa, condivisa da visione, regole e webapp.
- data/stories.json: i pezzi che la casa combina in storie, ricordi e risposte, in italiano e in inglese.
- hardware/stl: i file di stampa numerati.
- scripts: installazione, hotspot, copia dal PC alla scheda, frasi della voce preparate in anticipo, addestramento della rete delle statuine, schermate.
- tests: test del nucleo, della voce, della visione (su immagini sintetiche) e delle API web.
- docs: guide in italiano e in inglese, immagini, l'elenco di strumenti e licenze.

# Licenze

Il codice sorgente è rilasciato con licenza MIT, vedi [LICENSE](https://github.com/destone28/DomotiQ/blob/main/LICENSE). Documentazione, immagini, file di stampa 3D e dati della casa sono rilasciati con licenza Creative Commons Attribuzione 4.0, vedi [LICENSE-DOCS.md](https://github.com/destone28/DomotiQ/blob/main/LICENSE-DOCS.md). Componenti, modelli e voci di terze parti mantengono le loro licenze, elencate nelle [attribuzioni](https://github.com/destone28/DomotiQ/blob/main/docs/it/10-attribuzioni.md). I modelli dei personaggi e dell'auto sono progetti di terze parti e non sono inclusi.
