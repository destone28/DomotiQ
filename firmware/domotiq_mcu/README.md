# DomotiQ microcontroller firmware

`domotiq_mcu.ino` runs on the **STM32U585** of the Arduino UNO Q. The Qwiic connector of the board belongs to this microcontroller (`Wire1`, I²C4), so every Modulino is driven from here; Linux talks to the sketch through `arduino-router` with the Bridge library.

## Build and upload (on the board)

`scripts/install.sh` does it. By hand, on the UNO Q:

```bash
arduino-cli lib install Arduino_RouterBridge@0.4.3
arduino-cli compile -b arduino:zephyr:unoq:wait_linux_boot=no --output-dir /tmp/domotiq-build firmware/domotiq_mcu
P=~/.arduino15/packages/arduino
$P/tools/remoteocd/*/remoteocd upload \
  -f $P/hardware/zephyr/1.0.0/variants/arduino_uno_q_stm32u585xx/flash_sketch.cfg \
  $P/hardware/zephyr/1.0.0/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf \
  /tmp/domotiq-build/domotiq_mcu.ino.elf-zsk.bin
```

Uploading from the board itself uses the local OpenOCD and needs no password. Tested with core `arduino:zephyr` 1.0.0 and `Arduino_RouterBridge` 0.4.3.

**Startup mode "Immediate"** (`wait_linux_boot=no`): the sketch starts at power-up instead of waiting for Linux. The Latch Relay keeps its contact without power; if the barbecue fan was on during a power cut, the sketch switches it off within milliseconds instead of after the 40 seconds Linux needs to boot.

## Modules

| Hub channel | Module | Address |
|---|---|---|
| main bus | Modulino Hub (TCA9548A) | 0x70–0x77, searched at boot |
| main bus | Modulino Latch Relay | 0x02 or 0x15 (factory, depending on the batch), or 0x10 |
| 0 | Pixels, garage | 0x36 |
| 1 | Pixels, bedroom | 0x36 |
| 2 | Pixels, kitchen | 0x36 |
| 3 | Pixels, living room | 0x36 |
| 4 | Thermo, bathroom | 0x44 |
| 5 | Pixels, bathroom | 0x36 |
| 6 | Thermo (sideboard thermostat) → Buttons → Distance | 0x44, 0x3E, 0x29 |

Only one hub channel is open at a time. Modules are searched at power-up and every 5 seconds, so a module plugged in later shows up by itself. A module counts as present only after it answered on the bus.

## Methods called by Linux

| Method | Parameters | Returns |
|---|---|---|
| `version` | – | protocol version (1) |
| `ping` | – | milliseconds since start |
| `light` | light 0-4, effect, r, g, b, brightness 0-100, speed 0-100, duration ms (0 = until changed) | true |
| `party` | BPM × 10, seed, duration ms, start delay ms | true |
| `relay` | 0 / 1 | the requested state |
| `relay_state` | – | last state commanded (−1 unknown) |
| `leds` | mask of the 3 button LEDs, blink mask | true |
| `limits` | maximum brightness 0-100, current budget mA | true |
| `modules` | – | bitmask, in the order of `domotiq.mcu.MODULES` |
| `scan` | hub channel (8 = main bus), block 0-3 | addresses that answer, 32 per block |

Lights: 0 garage, 1 bedroom, 2 kitchen, 3 living room, 4 bathroom. Effects: 0 off, 1 solid, 2 breathe, 3 blink, 4 wave, 5 rainbow, 6 sparkle, 7 fire, 8 alarm, 9 cool, 10 warm. No effect flashes more than 3 times per second.

## Notifications sent to Linux

| Name | Arguments | When |
|---|---|---|
| `btn` | button 0-2, pressed 0/1 | on every change, after two equal readings (buttons are read 100 times per second) |
| `dist` | millimetres, −1 = nothing in front | on changes above 10 mm, at most 10 per second |
| `thermo` | sensor (0 sideboard, 1 bathroom), °C × 100, %RH × 100 | every 2 seconds per sensor |
| `mods` | module bitmask | when a module appears or disappears |

Linux receives them after registering the names with `$/register` on the router socket.

## Safety

- **Power budget.** Each Pixels can draw up to 264 mA at full white from the 3.3 V of the Qwiic line. The firmware estimates the current of every frame and scales all lights down when it exceeds the budget (450 mA by default), on top of the maximum brightness (30 % by default).
- **Relay.** Off at power-up, and off when Linux has been silent for 30 seconds; the lights then go back to the waiting breath.
- **Stuck bus.** Before every transaction the firmware reads the levels of SCL (PD12) and SDA (PD13). With a line held low it does not start the transaction, which would otherwise wait the 500 ms timeout of the driver and freeze lights and buttons; every 5 seconds it tries to free the bus with nine clocks on SCL and a STOP, done by hand because the UNO Q devicetree gives `i2c_recover_bus()` no GPIOs to do it. The `bus` method reports the state (bit 0 SCL high, bit 1 SDA high, both seen at the last check with the bus idle, bit 2 held low at that check, bits 8-15 attempts to free it, bits 16-30 refused transactions); the house raises an alert and *Diagnostics* shows it. A line held low for good is almost always hardware: a Qwiic cable with reversed wires, a damaged connector, a module that is not powered.

The default configuration of the VL53L4CD comes from the ultra-lite driver by STMicroelectronics (BSD-3-Clause).
