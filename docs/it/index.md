# Guida di DomotiQ

DomotiQ è una casa intelligente in scala 1:20 che funziona interamente offline su una sola **Arduino UNO Q 4GB**. Una webcam su un palo guarda la casa dall'alto e, con la visione artificiale, segue personaggi, animali, un'auto giocattolo e oggetti. Le luci delle stanze seguono le persone, le regole reagiscono a quello che succede, un'interfaccia vocale risponde alle domande in italiano e in inglese, e il telefono di ogni visitatore può aprire la webapp della casa attraverso l'hotspot Wi-Fi della scheda.

Questa guida copre tutto il progetto, da una scheda nuova di fabbrica fino a una casa che funziona allo stand di una fiera. I capitoli seguono l'ordine in cui si costruisce una casa.

## Capitoli

1. [Preparare la UNO Q](01-preparare-uno-q.md): prima password, SSH, nomi di rete, aggiornamento del sistema, accesso da un PC.
2. [Installare il software](02-installazione.md): `install.sh`, i tre servizi, l'hotspot, gli aggiornamenti, la seconda casa.
3. [Stampa e montaggio](03-stampa-e-montaggio.md): i file STL numerati e come si montano i pezzi.
4. [Collegamenti](04-collegamenti.md): la catena Qwiic attraverso il Modulino Hub, l'alimentazione, relè e ventola, l'audio, la webcam.
5. [Collaudo e messa in servizio](05-collaudo.md): la verifica di ogni parte, la calibrazione della webcam, il primo personaggio, la voce, i telefoni.
6. [La webapp](06-webapp.md): tutte le schermate, chi può fare cosa, il cartello, le notifiche e le domande.
7. [Riconoscimento e identità](07-riconoscimento-e-identita.md): come vede la casa, la registrazione dei personaggi, la privacy, i dataset.
8. [Voce](08-voce.md): i tasti, le lingue, la loquacità, frasi di esempio, il modello linguistico.
9. [Regole](09-regole.md): Quando / Se / Allora, tutti gli eventi, le condizioni e le azioni, le regole di partenza, i livelli delle luci.
10. [Attribuzioni](10-attribuzioni.md): le licenze del progetto e di ogni componente di terze parti.
11. [Risoluzione dei problemi](11-risoluzione-problemi.md): sintomo, causa e soluzione.

Per chi sta allo stand c'è una [guida rapida per lo staff](guida-rapida-staff.md) di una sola pagina, pensata per essere stampata.

## In breve

| | Casa 1 | Casa 2 |
|---|---|---|
| Nome host | `casa1` | `casa2` |
| Hotspot Wi-Fi | `DomotiQ-Casa1` (canale 1) | `DomotiQ-Casa2` (canale 11) |
| Webapp | `http://10.42.1.1/` | `http://10.42.2.1/` |
| Altri nomi | `casa1.lan`, `casa1.local` | `casa2.lan`, `casa2.local` |
| Cartella del progetto | `/home/arduino/domotiq` | `/home/arduino/domotiq` |

## Licenza e attribuzione

Il codice sorgente è distribuito sotto licenza MIT; documentazione, immagini, file di stampa 3D e i dati in `data/` sono distribuiti sotto CC BY 4.0. I dettagli, insieme alle licenze dei componenti che la casa usa, sono in [Attribuzioni](10-attribuzioni.md).

> Created by Emilio Destratis ([destratis.it](https://destratis.it)) in collaboration with Arduino.
