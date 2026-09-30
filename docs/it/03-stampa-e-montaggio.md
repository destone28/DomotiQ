# 3. Stampa e montaggio

La casa si stampa a partire da 90 file STL in `hardware/stl/`, distribuiti sotto CC BY 4.0. Il nome di ogni file comincia con un numero da 01 a 64, e **lo stesso numero è inciso sul pezzo stampato**: sulla faccia interna delle pareti, vicino al bordo inferiore, e sul lato inferiore delle pedane. I pezzi con lo stesso numero appartengono a una stessa famiglia (per esempio le quattordici chiavi da `07_Chiave_01` a `07_Chiave_14`, o i segmenti del palo da `29_Palo_2` a `29_Palo_4`).

![La casa montata con il palo della webcam](../images/render/01_assieme_con_palo.png)

Nei nomi dei file compaiono alcune abbreviazioni: *Est* esterna, *Int* interna, *Retro* parete posteriore, *Fac* facciata, *Sx* sinistra, *Dx* destra.

In questa guida il **davanti** è il lato del vialetto, dove stanno i visitatori, e **sinistra** e **destra** si intendono guardando la casa da davanti: cucina e giardino sono a sinistra, camera e garage a destra. Il repository contiene solo i file STL, senza profili per lo slicer.

## I pezzi

### Base

| N. | File | Pezzo |
|---|---|---|
| 01–06 | `01_Pedana_A1` … `06_Pedana_B3` | le sei pedane che formano la base (650 × 450 mm con il vialetto), in due file da tre |
| 07 | `07_Chiave_01` … `07_Chiave_14` | quattordici chiavi a farfalla che bloccano le pedane tra loro da sotto |
| 08 | `08_Staffa_Revodok_1`, `_2` | due staffe che tengono l'hub USB-C UGREEN Revodok nel suo alloggiamento sotto la base |

### Pareti

Le pareti sono alte 135 mm; le tre pareti di facciata sono alte 46 mm, così la webcam riesce a guardare dentro le stanze sul davanti.

| N. | File | Posizione |
|---|---|---|
| 09 | `09_Parete_Est_Sx_Cucina` | parete esterna sinistra della cucina |
| 10 | `10_Parete_Est_Dx_Camera` | parete esterna destra della camera |
| 11 | `11_Parete_Retro_Bagno` | parete posteriore del bagno |
| 12 | `12_Parete_Retro_Tecnico` | parete posteriore del locale tecnico |
| 13 | `13_Parete_Retro_Garage` | parete posteriore del garage (luce del garage) |
| 14 | `14_Parete_Est_Dx_Garage` | parete esterna destra del garage, con il portone del garage |
| 15 | `15_Parete_Retro_Cucina` | tra cucina e giardino, con la porta del giardino |
| 16 | `16_Parete_Retro_Camera` | tra camera e garage (luce della camera) |
| 17 | `17_Parete_Est_Sx_Bagno` | tra giardino e bagno |
| 18 | `18_Parete_Int_Cucina` | tra cucina e soggiorno, con una porta (luce della cucina) |
| 19 | `19_Parete_Int_Camera` | tra soggiorno e camera, con una porta (luce del soggiorno) |
| 20 | `20_Parete_Int_Bagno` | tra soggiorno e bagno, con una porta |
| 21 | `21_Parete_Int_Tecnico` | tra soggiorno e locale tecnico, con una porta |
| 22 | `22_Parete_Int_BagnoTecnico` | tra bagno e locale tecnico (luce del bagno e Thermo) |
| 23 | `23_Parete_Int_TecnicoGarage` | tra locale tecnico e garage, accanto al passaggio tra i due |
| 24 | `24_Parete_Fac_Cucina` | facciata della cucina |
| 25 | `25_Parete_Fac_Soggiorno` | facciata del soggiorno; lo spazio tra le pareti 24 e 25 è la porta d'ingresso |
| 26 | `26_Parete_Fac_Camera` | facciata della camera |

### Palo della webcam

| N. | File | Pezzo |
|---|---|---|
| 27 | `27_Palo_1` | segmento inferiore del palo, che sale dal locale tecnico |
| 28 | `28_Collare_Palo` | collare attorno al palo, all'altezza della cima delle pareti |
| 29 | `29_Palo_2`, `_3`, `_4` | i segmenti superiori del palo |
| 30 | `30_Braccio_Camera` | il braccio in cima, che termina con la culla della webcam |
| 31 | `31_Fermo_Camera` | il fermo che tiene la Logitech C270 nella culla |

### Placche per l'elettronica

| N. | File | Sostiene |
|---|---|---|
| 32 | `32_Placca_UNO_Q` | la Arduino UNO Q |
| 33 | `33_Placca_Hub`, `33_Placca_Relay` | il Modulino Hub e il Modulino Latch Relay |
| 33 | `33_Placca_Totem_Distance`, `33_Placca_Totem_Tasti1` | il sensore Distance e il modulo Buttons dentro il totem del citofono |
| 34 | `34_Placca_Thermo_Bagno` | il Thermo del bagno |
| 39 | `39_Credenza_Termostato` | la credenza del soggiorno, con sopra il Thermo del termostato |
| 40 | `40_Placca_Termostato` | la placca del Thermo del termostato, dentro la credenza |

### Luci

| N. | File | Stanza |
|---|---|---|
| 35 | `35_Applique_Pixels_Bagno`, `_Camera`, `_Cucina`, `_Soggiorno` | applique che ospitano un Modulino Pixels in bagno, camera, cucina e soggiorno |
| 36 | `36_Applique_Pixels_Garage` | applique del garage |

### Totem del citofono e casse

| N. | File | Pezzo |
|---|---|---|
| 37 | `37_Totem_Citofono` | il totem del citofono sul vialetto, con i tre tasti e il sensore Distance |
| 38 | `38_Tappo_Totem` | il tappo del totem, che ospita il microfono lavalier |
| 49 | `49_Fioriera_Cassa_Sx`, `_Dx` | le due fioriere che coprono le casse, a sinistra e a destra del totem |

### Giardino ed esterni

| N. | File | Pezzo |
|---|---|---|
| 41, 42 | `41_Griglia_Barbecue`, `42_Griglia_Coperchio` | il barbecue e il suo coperchio; dentro va la ventola |
| 43, 44 | `43_Albero_Tronco`, `44_Albero_Chioma` | tronco e chioma dell'albero |
| 45 | `45_Tavolo_Giardino` | tavolo da giardino |
| 46 | `46_Panca_Giardino_1`, `_2` | due panche |
| 47, 48 | `47_Staccionata_Sx`, `48_Staccionata_Retro` | staccionate a sinistra e sul retro del giardino |
| 50 | `50_Prato_Giardino` | prato del giardino |
| 51–53 | `51_Prato_Vialetto_Sx`, `52_…_Centro`, `53_…_Dx` | i tre prati del vialetto |

### Arredi

| N. | File | Stanza |
|---|---|---|
| 54 | `54_Arredo_Cucina_Bancone` | bancone della cucina |
| 55 | `55_Arredo_Cucina_Frigo` | frigorifero |
| 56 | `56_Arredo_Cucina_Tavolo` | tavolo della cucina |
| 57 | `57_Arredo_Divano` | divano del soggiorno |
| 58 | `58_Arredo_Tavolino` | tavolino |
| 59 | `59_Arredo_Mobile_TV` | mobile TV |
| 60 | `60_Arredo_Letto` | letto |
| 61 | `61_Arredo_Comodino_Sx`, `_Dx` | comodini |
| 62 | `62_Arredo_Bagno_WC` | WC |
| 63 | `63_Arredo_Bagno_Lavabo` | lavabo |
| 64 | `64_Arredo_Bagno_Doccia` | doccia |

## Colori

Il riconoscimento confronta ogni immagine con una foto della casa vuota, quindi non richiede colori particolari per pareti o arredi. Quello che conta è il contrasto di ciò che si muove: un personaggio di un colore molto vicino al pavimento grigio, alle pareti o ai prati si vede male, e la casa lo segnala quando lo registri (vedi il [capitolo 7](07-riconoscimento-e-identita.md#avvisi)).

La webapp disegna la piantina con i colori di riferimento salvati in `data/house.json`: bianco per bancone, frigorifero, WC e lavabo, marrone legno per tavoli, credenza e comodini, blu per divano e letto, grigio scuro per il mobile TV e il totem, rosso mattone per il barbecue, verde per l'albero e verde scuro per le fioriere. Nei render le applique sono in un materiale traslucido, così i Pixels possono illuminare attraverso.

## Montaggio

I render in `docs/images/render/` mostrano ogni passaggio.

1. **Base.** Appoggia le sei pedane capovolte, controlla i numeri incisi e premi le quattordici chiavi negli alloggiamenti a farfalla a cavallo delle giunture. Inserisci l'hub Revodok nel suo alloggiamento e bloccalo con le due staffe `08`.

   ![Le pedane viste da sotto, con le chiavi e il Revodok](../images/render/09_pedane_da_sotto.png)

2. **Prati.** Gira la base e appoggia al loro posto il prato del giardino e i tre prati del vialetto.
3. **Pareti.** Infila le pareti nelle loro scanalature, seguendo la tabella qui sopra e i numeri incisi. La porta d'ingresso è lo spazio tra le facciate della cucina e del soggiorno; il portone del garage è nella parete destra del garage.
4. **Placche e luci.** Monta i moduli sulle loro placche e i Pixels nelle applique, poi appendili alle pareti indicate sopra (quale modulo va dove è spiegato nel [capitolo 4](04-collegamenti.md)). Il Thermo del bagno e la luce del bagno condividono la parete tra bagno e locale tecnico.

   ![Bagno: Thermo e applique](../images/render/11_bagno_thermo_e_applique.png)

5. **Palo e webcam.** Pianta il segmento inferiore `27` nel locale tecnico, infilaci il collare `28`, impila i segmenti da `29_Palo_2` a `29_Palo_4` e aggiungi il braccio `30`. Metti la C270 nella culla e chiudila con il fermo `31`. Secondo i dati della casa l'obiettivo sta a 930 mm sopra il pavimento, sopra il centro della base: la calibrazione si adatta a piccole differenze, ma l'intera base deve essere inquadrata.

   ![Il palo, esploso](../images/render/14_palo_esploso.png)

6. **Totem e casse.** Monta il modulo Buttons e il sensore Distance nel totem `37`, e il microfono lavalier nel tappo `38`. Sistema le casse al loro posto sul vialetto e coprile con le fioriere `49`.

   ![Totem e fioriere sopra le casse](../images/render/06_totem_e_casse_montaggio.png)

7. **Arredi e giardino.** Sistema gli arredi, la credenza con il termostato, il barbecue con la ventola, l'albero, il tavolo, le panche e le staccionate.

Una volta calibrata la casa (vedi il [capitolo 5](05-collaudo.md#9-calibrazione-della-webcam)), gli arredi devono restare dove sono: la casa li considera parte della casa vuota. Se sposti un pezzo, salva di nuovo la casa vuota. Anche la webcam non deve muoversi; se viene urtata, la webapp chiede una nuova calibrazione.

## Personaggi, animali e l'auto

Le statuine e l'auto sono modelli di terze parti e non sono in questo repository; i link sono sulla pagina del progetto.

La casa non ha bisogno di un modello particolare, ma qualche misura aiuta a sceglierli. Per la correzione della parallasse la visione presume una persona alta circa 90 mm (1,8 m in scala 1:20), un animale di circa 35 mm e un'auto di circa 70 mm. L'auto deve passare dal portone del garage, un'apertura di circa 100 mm, e parcheggia in un'area di 180 × 80 mm dentro il garage. Le statuine funzionano meglio stampate in un solo colore, ben saturo, diverso dal pavimento, dalle pareti e dai prati.

Avanti: [collegamenti](04-collegamenti.md).
