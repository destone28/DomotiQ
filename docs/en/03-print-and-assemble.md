# 3. Print and assemble

The house is printed from 90 STL files in `hardware/stl/`, released under CC BY 4.0. Each file name starts with a number from 01 to 64, and **the same number is engraved on the printed part**: on the inside face of the walls, near the bottom edge, and on the underside of the platforms. Parts that share a number belong to one family (for example the fourteen keys `07_Chiave_01` to `07_Chiave_14`, or the pole segments `29_Palo_2` to `29_Palo_4`).

![The assembled house with the camera pole](../images/render/01_assieme_con_palo.png)

The file names are in Italian. A few words help: *Pedana* platform, *Chiave* key, *Staffa* bracket, *Parete* wall, *Est* outer, *Int* inner, *Retro* back, *Fac* facade, *Sx* left, *Dx* right, *Palo* pole, *Placca* plate, *Tasti* buttons, *Tappo* cap, *Credenza* sideboard, *Griglia* barbecue, *Coperchio* lid, *Albero* tree, *Chioma* canopy, *Tronco* trunk, *Panca* bench, *Staccionata* fence, *Fioriera* planter, *Cassa* speaker, *Prato* lawn, *Vialetto* driveway, *Arredo* furniture.

In this guide, **front** is the driveway side, where visitors stand, and **left** and **right** are seen from the front: the kitchen and the garden are on the left, the bedroom and the garage on the right. The repository contains the STL files only, without slicer profiles.

## The parts

### Base

| No. | Files | Part |
|---|---|---|
| 01–06 | `01_Pedana_A1` … `06_Pedana_B3` | the six platforms that form the base (650 × 450 mm with the driveway), in two rows of three |
| 07 | `07_Chiave_01` … `07_Chiave_14` | fourteen bow-tie keys that lock the platforms together from below |
| 08 | `08_Staffa_Revodok_1`, `_2` | two brackets that hold the UGREEN Revodok USB-C hub in its pocket under the base |

### Walls

Walls are 135 mm high; the three facade walls are 46 mm high, so the camera can look into the front rooms.

| No. | File | Position |
|---|---|---|
| 09 | `09_Parete_Est_Sx_Cucina` | outer left wall of the kitchen |
| 10 | `10_Parete_Est_Dx_Camera` | outer right wall of the bedroom |
| 11 | `11_Parete_Retro_Bagno` | back wall of the bathroom |
| 12 | `12_Parete_Retro_Tecnico` | back wall of the utility room |
| 13 | `13_Parete_Retro_Garage` | back wall of the garage (garage light) |
| 14 | `14_Parete_Est_Dx_Garage` | outer right wall of the garage, with the garage gate |
| 15 | `15_Parete_Retro_Cucina` | between kitchen and garden, with the garden door |
| 16 | `16_Parete_Retro_Camera` | between bedroom and garage (bedroom light) |
| 17 | `17_Parete_Est_Sx_Bagno` | between garden and bathroom |
| 18 | `18_Parete_Int_Cucina` | between kitchen and living room, with a door (kitchen light) |
| 19 | `19_Parete_Int_Camera` | between living room and bedroom, with a door (living room light) |
| 20 | `20_Parete_Int_Bagno` | between living room and bathroom, with a door |
| 21 | `21_Parete_Int_Tecnico` | between living room and utility room, with a door |
| 22 | `22_Parete_Int_BagnoTecnico` | between bathroom and utility room (bathroom light and Thermo) |
| 23 | `23_Parete_Int_TecnicoGarage` | between utility room and garage, beside the passage between them |
| 24 | `24_Parete_Fac_Cucina` | facade of the kitchen |
| 25 | `25_Parete_Fac_Soggiorno` | facade of the living room; the gap between walls 24 and 25 is the front door |
| 26 | `26_Parete_Fac_Camera` | facade of the bedroom |

### Camera pole

| No. | Files | Part |
|---|---|---|
| 27 | `27_Palo_1` | bottom segment of the pole, rising from the utility room |
| 28 | `28_Collare_Palo` | collar around the pole at the height of the wall tops |
| 29 | `29_Palo_2`, `_3`, `_4` | the upper segments of the pole |
| 30 | `30_Braccio_Camera` | the arm at the top, ending in the cradle of the webcam |
| 31 | `31_Fermo_Camera` | the retainer that holds the Logitech C270 in the cradle |

### Plates for the electronics

| No. | Files | Holds |
|---|---|---|
| 32 | `32_Placca_UNO_Q` | the Arduino UNO Q |
| 33 | `33_Placca_Hub`, `33_Placca_Relay` | the Modulino Hub and the Modulino Latch Relay |
| 33 | `33_Placca_Totem_Distance`, `33_Placca_Totem_Tasti1`, `_Tasti2` | the Distance sensor and the Buttons module inside the intercom totem |
| 34 | `34_Placca_Thermo_Bagno` | the Thermo of the bathroom |
| 39 | `39_Credenza_Termostato` | the living room sideboard, with the Thermo of the thermostat on top |
| 40 | `40_Placca_Termostato` | the plate of the thermostat Thermo in the sideboard |

### Lights

| No. | Files | Room |
|---|---|---|
| 35 | `35_Applique_Pixels_Bagno`, `_Camera`, `_Cucina`, `_Soggiorno` | wall lights holding a Modulino Pixels in the bathroom, bedroom, kitchen and living room |
| 36 | `36_Applique_Pixels_Garage` | wall light of the garage |

### Intercom totem and speakers

| No. | Files | Part |
|---|---|---|
| 37 | `37_Totem_Citofono` | the intercom totem on the driveway, with the three buttons and the Distance sensor |
| 38 | `38_Tappo_Totem` | the cap of the totem, which holds the lavalier microphone |
| 49 | `49_Fioriera_Cassa_Sx`, `_Dx` | the two planters that cover the speakers, left and right of the totem |

### Garden and outdoor

| No. | Files | Part |
|---|---|---|
| 41, 42 | `41_Griglia_Barbecue`, `42_Griglia_Coperchio` | the barbecue and its lid; the fan goes inside |
| 43, 44 | `43_Albero_Tronco`, `44_Albero_Chioma` | tree trunk and canopy |
| 45 | `45_Tavolo_Giardino` | garden table |
| 46 | `46_Panca_Giardino_1`, `_2` | two benches |
| 47, 48 | `47_Staccionata_Sx`, `48_Staccionata_Retro` | fences on the left and at the back of the garden |
| 50 | `50_Prato_Giardino` | garden lawn |
| 51–53 | `51_Prato_Vialetto_Sx`, `52_…_Centro`, `53_…_Dx` | the three lawns of the driveway |

### Furniture

| No. | File | Room |
|---|---|---|
| 54 | `54_Arredo_Cucina_Bancone` | kitchen counter |
| 55 | `55_Arredo_Cucina_Frigo` | fridge |
| 56 | `56_Arredo_Cucina_Tavolo` | kitchen table |
| 57 | `57_Arredo_Divano` | living room sofa |
| 58 | `58_Arredo_Tavolino` | coffee table |
| 59 | `59_Arredo_Mobile_TV` | TV stand |
| 60 | `60_Arredo_Letto` | bed |
| 61 | `61_Arredo_Comodino_Sx`, `_Dx` | nightstands |
| 62 | `62_Arredo_Bagno_WC` | toilet |
| 63 | `63_Arredo_Bagno_Lavabo` | sink |
| 64 | `64_Arredo_Bagno_Doccia` | shower |

## Colours

The recognition compares every image with a picture of the empty house, so it does not need particular colours for walls or furniture. What matters is the contrast of what moves: a figurine whose colour is very close to the grey floor, to the walls or to the lawns is hard to see, and the house warns about it when you register it (see [chapter 7](07-recognition-and-identities.md#warnings)).

The web app draws the plan with the reference colours stored in `data/house.json`: white for counter, fridge, toilet and sink, wood brown for tables, sideboard and nightstands, blue for sofa and bed, dark grey for the TV stand and the totem, brick red for the barbecue, green for the tree and dark green for the planters. The renders show the wall lights in a translucent material, so the Pixels can shine through.

## Assembly

The renders in `docs/images/render/` show every step.

1. **Base.** Lay the six platforms upside down, check the engraved numbers, and press the fourteen keys into the bow-tie pockets across the joints. Fit the Revodok hub into its pocket and lock it with the two brackets `08`.

   ![The platforms from below, with the keys and the Revodok](../images/render/09_pedane_da_sotto.png)

2. **Lawns.** Turn the base over and lay the garden lawn and the three driveway lawns in their places.
3. **Walls.** Insert the walls into their grooves, following the table above and the engraved numbers. The front door is the gap between the facades of kitchen and living room; the garage gate is in the right wall of the garage.
4. **Plates and lights.** Mount the modules on their plates and the Pixels in the wall lights, then hang them on the walls listed above (see [chapter 4](04-wiring.md) for which module goes where). The bathroom Thermo and the bathroom light share the wall between bathroom and utility room.

   ![Bathroom: Thermo and wall light](../images/render/11_bagno_thermo_e_applique.png)

5. **Pole and camera.** Stand the bottom segment `27` in the utility room, slide the collar `28` onto it, stack the segments `29_Palo_2` to `29_Palo_4`, and add the arm `30`. Put the C270 in the cradle and close it with the retainer `31`. The house data puts the lens 930 mm above the floor, above the centre of the base: the calibration adapts to small differences, but the whole base must be in view.

   ![The pole, exploded](../images/render/14_palo_esploso.png)

6. **Totem and speakers.** Mount the Buttons and the Distance sensor in the totem `37` and the lavalier microphone in the cap `38`. Set the speakers in their places on the driveway and cover them with the planters `49`.

   ![Totem and planters over the speakers](../images/render/06_totem_e_casse_montaggio.png)

7. **Furniture and garden.** Place the furniture, the sideboard with the thermostat, the barbecue with the fan, tree, table, benches and fences.

Once the house is calibrated (see [chapter 5](05-testing.md#9-camera-calibration)), the furniture must stay where it is: the house takes it as part of the empty house. If you move a piece, save the empty house again. The camera must not move either; if it gets bumped, the web app asks for a new calibration.

## Figurines, pets and the car

The figurines and the car are third-party models and are not in this repository; see the project page for links.

The house does not need a particular model, but a few numbers help to choose them. For the parallax correction the vision assumes a person about 90 mm tall (1.8 m at 1:20), a pet about 35 mm and the car about 70 mm. The car must pass through the garage gate, an opening of about 100 mm, and parks in an area of 180 × 80 mm inside the garage. Figurines work best printed in a single, clearly saturated colour that differs from the floor, the walls and the lawns.

Next: [wiring](04-wiring.md).
