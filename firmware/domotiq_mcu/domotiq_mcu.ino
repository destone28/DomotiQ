// SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
// SPDX-License-Identifier: MIT
/*
 * DomotiQ — microcontroller firmware (STM32U585 of the Arduino UNO Q)
 *
 * The Qwiic connector of the UNO Q is wired to I2C4 of the STM32U585
 * (`Wire1` here): every Modulino belongs to this sketch. Linux talks to it
 * through arduino-router with the Bridge library: it calls the methods below
 * and receives the notifications this sketch sends.
 *
 * Linux decides, the MCU executes. Linux says "effect X in room Y" and the
 * sketch draws it at 25 frames per second; the serial link to Linux carries
 * 256 bytes per message at 115200 baud, far too little for animation frames.
 *
 * ── Bus layout ──────────────────────────────────────────────────────────────
 *   UNO Q ── Hub (TCA9548A, 0x70..0x77) ── Latch Relay (0x02, 0x15 or 0x10, main bus)
 *   Hub ch0 Pixels garage     ch1 Pixels bedroom   ch2 Pixels kitchen
 *       ch3 Pixels living     ch4 Thermo bathroom  ch5 Pixels bathroom
 *       ch6 Thermo sideboard → Buttons (0x3E)
 *   Every Pixels sits at the factory address 0x36 on its own channel.
 *
 * ── The light of the utility room ───────────────────────────────────────────
 * It is the 13 × 8 LED matrix of the UNO Q itself (light 5 for Linux). The
 * matrix has one colour and 8 levels: it takes the effects and the
 * brightness of the other lights, and their colour shows on the RGB LED3
 * next to it.
 *
 * ── No Modulino library ────────────────────────────────────────────────────
 * On the UNO Q core, Arduino_Modulino reports modules as present without
 * touching the bus and returns true from every write. Every transaction here
 * is written by hand, bounded in time, and a module counts as present only
 * after it answered.
 *
 * ── Threads ─────────────────────────────────────────────────────────────────
 * `io_thread` owns the bus from power-up: it switches the latching relay
 * off, breathes the lights while Linux boots, and then runs lights,
 * buttons and sensors. Bridge handlers run on the Bridge thread and only
 * write the shared state under `state_lock` (never call the Bridge from a
 * handler: it deadlocks). Notifications go through a queue and are sent
 * from loop().
 *
 * Arduino generates prototypes above the first function of a .ino file,
 * so all types and globals are declared first.
 */

#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>
#include <Wire.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>

// ============================================================ constants
static const int PROTOCOL = 1;

static const uint8_t ADDR_PIXELS = 0x36;
static const uint8_t ADDR_THERMO = 0x44;
static const uint8_t ADDR_BUTTONS = 0x3E;
// The Latch Relay answers at 0x02 in the Modulino library (0x04 in 8-bit form), at 0x15 in the
// datasheet of September 2026 (0x2A in 8-bit form), at 0x10 if moved with AddressChanger:
// the firmware looks at all three.
static const uint8_t ADDR_RELAY[] = {0x02, 0x15, 0x10};
static const uint8_t HUB_FIRST = 0x70, HUB_LAST = 0x77;

static const uint8_t N_LIGHTS = 5;
static const uint8_t N_LED = 8;
// light index (as Linux numbers them) -> hub channel
static const uint8_t LIGHT_CH[N_LIGHTS] = {0, 1, 2, 3, 5};
static const uint8_t CH_THERMO[2] = {6, 4};      // 0 sideboard (thermostat), 1 bathroom
static const uint8_t CH_TOTEM = 6;               // the buttons of the totem

// module bits, in the order of domotiq.mcu.MODULES
enum {
  M_HUB = 0, M_RELAY, M_PX_GARAGE, M_PX_BEDROOM, M_PX_KITCHEN, M_PX_LIVING,
  M_THERMO_BATH, M_PX_BATH, M_THERMO_STAT, M_BUTTONS
};
static const uint8_t LIGHT_BIT[N_LIGHTS] = {M_PX_GARAGE, M_PX_BEDROOM, M_PX_KITCHEN, M_PX_LIVING, M_PX_BATH};
static const uint8_t THERMO_BIT[2] = {M_THERMO_STAT, M_THERMO_BATH};
static const uint8_t MATRIX_LIGHT = 5;           // the LED matrix of the board, as Linux numbers it
static const uint8_t MX_W = 13, MX_H = 8, MX_TOP = 7;   // 8 levels, 0..7
static const uint8_t MX_BITS = 3;                // the matrix takes the number of bits, not the top level

enum { FX_OFF = 0, FX_SOLID, FX_BREATHE, FX_BLINK, FX_WAVE, FX_RAINBOW, FX_SPARKLE, FX_FIRE,
       FX_ALARM, FX_COOL, FX_WARM, FX_BOOT = 100 };

static const uint32_t FRAME_MS = 40;             // 25 frames per second
static const uint32_t BUTTON_MS = 10;
static const uint32_t THERMO_PERIOD_MS = 2000;
static const uint32_t THERMO_WAIT_MS = 40;
static const uint32_t PROBE_MS = 5000;
static const uint32_t LINUX_SILENT_MS = 30000;
static const float MA_PER_CHANNEL = 11.0f;       // LC8822 at full 5-bit brightness

// ============================================================ shared state
struct LightCmd {
  uint8_t effect = FX_BOOT;
  uint8_t r = 255, g = 150, b = 60;
  uint8_t bri = 30;          // 0-100 relative to max_bri
  uint8_t speed = 50;
  uint32_t duration = 0;     // ms, 0 = until changed
  uint32_t started = 0;
};

struct PartyCmd {
  bool pending = false;
  uint32_t bpm10 = 1240, seed = 1, duration = 0, delay = 0;
};

struct PartyBeat {           // the party show at one moment: Pixels and matrix follow the same beat
  uint32_t beat_ms, t, beat, in_beat, pattern;
  uint8_t hue;
  bool finale;
};

struct Event {
  uint8_t kind;              // 1 btn, 3 thermo, 4 mods
  int32_t a, b, c;
};

static K_MUTEX_DEFINE(state_lock);
static K_MUTEX_DEFINE(bus_lock);
K_MSGQ_DEFINE(events, sizeof(Event), 32, 4);

static LightCmd req_light[N_LIGHTS];
static bool req_light_dirty[N_LIGHTS];
static LightCmd req_matrix;
static bool req_matrix_dirty = false;
static PartyCmd req_party;
static int8_t req_relay = 0;               // 0 off at boot, 1 on, -1 nothing pending
static uint8_t req_leds = 0, req_blink = 0;
static bool req_leds_dirty = true;
static uint8_t max_bri = 30;               // 0-100
static uint16_t budget_ma = 450;
static volatile uint32_t last_linux_ms = 0;
static volatile bool linux_seen = false;
static volatile bool bridge_ready = false;

static volatile uint32_t modules_mask = 0;
static volatile int relay_state = -1;
static uint8_t hub_addr = 0;
static uint8_t relay_addr = 0;
static int8_t hub_channel = -1;

// io thread private state
static LightCmd cur_light[N_LIGHTS];
static uint8_t frame[N_LIGHTS][N_LED][3];
static uint8_t sent_frame[N_LIGHTS][N_LED][4];
static bool sent_valid[N_LIGHTS];
static bool party_on = false;
static uint32_t party_start = 0, party_end = 0, party_bpm10 = 1240, party_seed = 1;
static LightCmd cur_matrix;
static uint8_t mx[MX_W * MX_H], mx_sent[MX_W * MX_H];
static bool mx_valid = false;
static uint8_t led3[3], led3_sent[3];
static bool led3_valid = false;
static uint8_t btn_raw[3], btn_stable[3], btn_count[3];
static int thermo_phase[2] = {0, 0};
static uint32_t thermo_at[2] = {0, 0};

static uint32_t fx_seed = 0x2545F491u;
static uint32_t fx_rand() {
  fx_seed ^= fx_seed << 13; fx_seed ^= fx_seed >> 17; fx_seed ^= fx_seed << 5;
  return fx_seed;
}

// scan requests from Linux, executed by the io thread (the only bus owner)
static K_SEM_DEFINE(scan_done, 0, 1);
static volatile int scan_channel = -1, scan_block = -1;
static volatile uint32_t scan_result = 0;

static K_THREAD_STACK_DEFINE(io_stack, 4096);
static struct k_thread io_thread_data;

// ============================================================ bus health
// SCL and SDA of I2C4 are PD12 and PD13 (pinctrl-0 of i2c4 in the UNO Q
// devicetree). The input register of the port shows their levels even while
// the I2C peripheral drives them.
static const struct device *const bus_port = DEVICE_DT_GET(DT_NODELABEL(gpiod));
static const uint8_t PIN_SCL = 12, PIN_SDA = 13;
static volatile bool bus_stuck = false;
static volatile uint8_t bus_levels = 3;      // SCL and SDA at the last check, taken with the bus idle
static volatile uint16_t bus_refused = 0;    // transactions not attempted because a line was low
static volatile uint8_t bus_unsticks = 0;    // attempts to free the bus

static uint8_t bus_lines() {                 // bit 0 SCL high, bit 1 SDA high
  gpio_port_value_t v = 0;
  if (gpio_port_get_raw(bus_port, &v) != 0) return 3;
  return (uint8_t)(((v >> PIN_SCL) & 1u) | (((v >> PIN_SDA) & 1u) << 1));
}

// Between two transactions both lines are high. With one held low (a
// reversed Qwiic cable, a module without power, a target stuck halfway
// through a byte) every transaction would wait the 500 ms timeout of the
// driver and freeze lights and buttons: it fails at once instead, and the io
// thread tries to free the bus every few seconds.
static bool bus_idle() {
  uint8_t l = bus_lines();
  if (l != 3) { k_busy_wait(50); l = bus_lines(); }
  bus_levels = l;
  bus_stuck = l != 3;
  if (bus_stuck && bus_refused < 0xFFFF) bus_refused++;
  return !bus_stuck;
}

// The standard way out: up to nine clocks on SCL let a target that was
// sending a byte finish it and release SDA, then a STOP. i2c_recover_bus()
// would do it, but the UNO Q devicetree gives the driver no GPIOs for it, so
// it is done here by hand; Wire1.begin() gives the pins back to the I2C
// peripheral and setClock() restarts it.
static void bus_unstick() {
  k_mutex_lock(&bus_lock, K_FOREVER);
  if (bus_unsticks < 0xFF) bus_unsticks++;
  gpio_pin_configure(bus_port, PIN_SDA, GPIO_INPUT);
  gpio_pin_configure(bus_port, PIN_SCL, GPIO_OUTPUT_HIGH | GPIO_OPEN_DRAIN);
  k_busy_wait(10);
  for (uint8_t i = 0; i < 9 && !(bus_lines() & 2); i++) {
    gpio_pin_set_raw(bus_port, PIN_SCL, 0); k_busy_wait(5);
    gpio_pin_set_raw(bus_port, PIN_SCL, 1); k_busy_wait(5);
  }
  if (bus_lines() == 3) {                    // STOP: SDA rises while SCL is high
    gpio_pin_configure(bus_port, PIN_SDA, GPIO_OUTPUT_LOW | GPIO_OPEN_DRAIN);
    k_busy_wait(5);
    gpio_pin_set_raw(bus_port, PIN_SDA, 1);
    k_busy_wait(5);
  }
  Wire1.begin();
  Wire1.setClock(100000);
  hub_channel = -1;
  bus_idle();
  k_mutex_unlock(&bus_lock);
}

// ============================================================ bus helpers
static bool bus_write(uint8_t addr, const uint8_t *data, uint8_t len) {
  k_mutex_lock(&bus_lock, K_FOREVER);
  if (!bus_idle()) { k_mutex_unlock(&bus_lock); return false; }
  Wire1.beginTransmission(addr);
  for (uint8_t i = 0; i < len; i++) Wire1.write(data[i]);
  bool ok = Wire1.endTransmission() == 0;
  k_mutex_unlock(&bus_lock);
  return ok;
}

static bool bus_read(uint8_t addr, uint8_t *out, uint8_t len) {
  k_mutex_lock(&bus_lock, K_FOREVER);
  if (!bus_idle()) { k_mutex_unlock(&bus_lock); return false; }
  bool ok = (int)Wire1.requestFrom((int)addr, (int)len) == (int)len;
  if (ok) for (uint8_t i = 0; i < len; i++) out[i] = (uint8_t)Wire1.read();
  k_mutex_unlock(&bus_lock);
  return ok;
}

static bool bus_probe(uint8_t addr) {
  k_mutex_lock(&bus_lock, K_FOREVER);
  if (!bus_idle()) { k_mutex_unlock(&bus_lock); return false; }
  Wire1.beginTransmission(addr);
  bool ok = Wire1.endTransmission() == 0;
  k_mutex_unlock(&bus_lock);
  return ok;
}

// Open one hub channel (or none with ch < 0). Only one channel is ever
// open: every channel has its own pull-ups, and all eight together would
// load the bus beyond what the pins can sink.
static bool hub_select(int8_t ch) {
  if (!hub_addr) return ch < 0;
  if (ch == hub_channel) return true;
  uint8_t mask = ch < 0 ? 0 : (uint8_t)(1 << ch);
  bool ok = bus_write(hub_addr, &mask, 1);
  hub_channel = ok ? ch : -1;
  return ok;
}

static void set_module(uint8_t bit, bool present) {
  uint32_t before = modules_mask;
  uint32_t after = present ? (before | (1u << bit)) : (before & ~(1u << bit));
  if (after != before) {
    modules_mask = after;
    Event ev = {4, (int32_t)after, 0, 0};
    k_msgq_put(&events, &ev, K_NO_WAIT);
  }
}

// ============================================================ relay
static bool relay_command(bool on) {
  if (!relay_addr) return false;
  hub_select(-1);
  uint8_t cmd[3] = {(uint8_t)(on ? 1 : 0), 0, 0};
  bool ok = bus_write(relay_addr, cmd, 3);
  if (ok) {
    relay_state = on ? 1 : 0;
    k_msleep(120);            // the module pulses the coil for 50 ms and blocks meanwhile
  }
  return ok;
}

static void relay_find() {
  hub_select(-1);
  relay_addr = 0;
  for (uint8_t i = 0; i < sizeof(ADDR_RELAY) && !relay_addr; i++)
    if (bus_probe(ADDR_RELAY[i])) relay_addr = ADDR_RELAY[i];
  set_module(M_RELAY, relay_addr != 0);
}

static void hub_find() {
  hub_addr = 0;
  hub_channel = -1;
  for (uint8_t a = HUB_FIRST; a <= HUB_LAST; a++) {
    if (bus_probe(a)) {
      uint8_t zero = 0;
      if (bus_write(a, &zero, 1)) { hub_addr = a; break; }
    }
  }
  set_module(M_HUB, hub_addr != 0);
}

// ============================================================ pixels
static inline uint8_t scale8(uint8_t v, uint16_t s) { return (uint8_t)(((uint16_t)v * s) >> 8); }

static void hue_to_rgb(uint8_t h, uint8_t *r, uint8_t *g, uint8_t *b) {
  uint8_t region = h / 43, rem = (uint8_t)((h - region * 43) * 6);
  uint8_t q = 255 - rem, t = rem;
  switch (region) {
    case 0: *r = 255; *g = t; *b = 0; break;
    case 1: *r = q; *g = 255; *b = 0; break;
    case 2: *r = 0; *g = 255; *b = t; break;
    case 3: *r = 0; *g = q; *b = 255; break;
    case 4: *r = t; *g = 0; *b = 255; break;
    default: *r = 255; *g = 0; *b = q; break;
  }
}

static uint8_t tri(uint32_t t, uint32_t period) {  // 0..255..0 triangle wave
  uint32_t p = t % period;
  uint32_t half = period / 2;
  return (uint8_t)(p < half ? (p * 255) / half : ((period - p) * 255) / half);
}

static uint32_t rng(uint32_t *s) {                 // xorshift, for repeatable party shows
  uint32_t x = *s;
  x ^= x << 13; x ^= x >> 17; x ^= x << 5;
  *s = x ? x : 0x9E3779B9u;
  return *s;
}

static void render_light(uint8_t li, uint32_t now) {
  const LightCmd &c = cur_light[li];
  uint32_t t = now - c.started;
  uint8_t (*px)[3] = frame[li];
  uint16_t speed = c.speed ? c.speed : 50;
  for (uint8_t i = 0; i < N_LED; i++) { px[i][0] = c.r; px[i][1] = c.g; px[i][2] = c.b; }
  switch (c.effect) {
    case FX_OFF:
      memset(px, 0, N_LED * 3);
      break;
    case FX_SOLID:
      break;
    case FX_BOOT:
    case FX_BREATHE: {
      uint32_t period = c.effect == FX_BOOT ? 3200 : 5200 - speed * 36;   // 1.6 .. 5.2 s
      uint16_t k = 60 + (tri(t, period) * 196) / 255;
      for (uint8_t i = 0; i < N_LED; i++) for (uint8_t j = 0; j < 3; j++) px[i][j] = scale8(px[i][j], k);
      break;
    }
    case FX_BLINK:
    case FX_ALARM: {
      // never faster than 3 flashes per second, for people sensitive to flashing light
      uint32_t period = c.effect == FX_ALARM ? 500 : (1400 - speed * 10 < 340 ? 340 : 1400 - speed * 10);
      if ((t % period) >= period / 2) memset(px, 0, N_LED * 3);
      break;
    }
    case FX_WAVE:
    case FX_COOL: {
      uint32_t period = 2600 - speed * 18;
      for (uint8_t i = 0; i < N_LED; i++) {
        uint16_t k = 50 + (tri(t + i * (period / N_LED), period) * 206) / 255;
        for (uint8_t j = 0; j < 3; j++) px[i][j] = scale8(px[i][j], k);
      }
      break;
    }
    case FX_RAINBOW: {
      uint8_t base = (uint8_t)((t * (speed + 10)) / 400);
      for (uint8_t i = 0; i < N_LED; i++) hue_to_rgb((uint8_t)(base + i * 32), &px[i][0], &px[i][1], &px[i][2]);
      break;
    }
    case FX_SPARKLE:
      for (uint8_t i = 0; i < N_LED; i++) {
        uint16_t k = (fx_rand() % 100) < 12 ? 255 : 70;
        for (uint8_t j = 0; j < 3; j++) px[i][j] = scale8(px[i][j], k);
      }
      break;
    case FX_FIRE:
      for (uint8_t i = 0; i < N_LED; i++) {
        uint8_t flicker = 120 + (fx_rand() % 136);
        px[i][0] = scale8(255, flicker);
        px[i][1] = scale8(70 + (fx_rand() % 60), flicker);
        px[i][2] = 0;
      }
      break;
    case FX_WARM: {
      uint16_t k = 150 + (tri(t, 4000) * 105) / 255;
      for (uint8_t i = 0; i < N_LED; i++) for (uint8_t j = 0; j < 3; j++) px[i][j] = scale8(px[i][j], k);
      break;
    }
    default:
      break;
  }
}

// The party show: patterns change every four beats, flashes only on beats
// (at 124 BPM that is about 2 per second, below the 3 per second limit).
static PartyBeat party_beat(uint32_t now) {
  PartyBeat p;
  p.beat_ms = 600000u / (party_bpm10 ? party_bpm10 : 1240);
  p.t = now - party_start;
  p.beat = p.t / p.beat_ms;
  p.in_beat = p.t % p.beat_ms;
  uint32_t seed = party_seed ^ ((p.beat / 4) * 2654435761u);
  p.pattern = rng(&seed) % 5;
  p.hue = (uint8_t)(rng(&seed));
  p.finale = party_end - now < 2000;
  return p;
}

static void render_party(uint32_t now) {
  PartyBeat pb = party_beat(now);
  uint32_t beat_ms = pb.beat_ms, t = pb.t, beat = pb.beat, in_beat = pb.in_beat, pattern = pb.pattern;
  uint8_t hue = pb.hue;
  bool finale = pb.finale;
  for (uint8_t li = 0; li < N_LIGHTS; li++) {
    for (uint8_t i = 0; i < N_LED; i++) {
      uint8_t r, g, b;
      if (finale) {
        hue_to_rgb((uint8_t)(fx_rand()), &r, &g, &b);
        uint16_t k = (fx_rand() % 100) < 30 ? 255 : 40;
        r = scale8(r, k); g = scale8(g, k); b = scale8(b, k);
      } else if (pattern == 0) {             // chase around the house
        uint8_t pos = (uint8_t)((t / (beat_ms / 8)) % (N_LIGHTS * N_LED));
        bool lit = (li * N_LED + i) % 8 == pos % 8;
        hue_to_rgb((uint8_t)(hue + li * 40), &r, &g, &b);
        if (!lit) { r /= 6; g /= 6; b /= 6; }
      } else if (pattern == 1) {             // beat flash, one colour per room
        hue_to_rgb((uint8_t)(hue + li * 51), &r, &g, &b);
        uint16_t k = in_beat < beat_ms / 3 ? 255 : 50;
        r = scale8(r, k); g = scale8(g, k); b = scale8(b, k);
      } else if (pattern == 2) {             // rainbow wheel
        hue_to_rgb((uint8_t)(hue + (t / 6) + i * 32 + li * 20), &r, &g, &b);
      } else if (pattern == 3) {             // alternate rooms on every beat
        hue_to_rgb(hue, &r, &g, &b);
        if (((beat + li) & 1) == 0) { r /= 8; g /= 8; b /= 8; }
      } else {                               // pulse
        hue_to_rgb((uint8_t)(hue + beat * 16), &r, &g, &b);
        uint16_t k = 255 - (in_beat * 200) / beat_ms;
        r = scale8(r, k); g = scale8(g, k); b = scale8(b, k);
      }
      frame[li][i][0] = r; frame[li][i][1] = g; frame[li][i][2] = b;
    }
  }
}

// ============================================================ the LED matrix
// The same effects as the Pixels, in levels 0..MX_TOP; `env` (0-255) is how
// bright the colour LED is at this moment.
static void render_matrix(uint32_t now) {
  const LightCmd &c = cur_matrix;
  uint32_t t = now - c.started;
  uint16_t speed = c.speed ? c.speed : 50;
  uint8_t top = (uint8_t)(((uint16_t)c.bri * MX_TOP + 50) / 100);
  if (top == 0 && c.bri > 0) top = 1;
  uint16_t env = 255;
  uint8_t r = c.r, g = c.g, b = c.b;
  for (uint8_t y = 0; y < MX_H; y++) {
    for (uint8_t x = 0; x < MX_W; x++) {
      uint16_t k = 255;
      switch (c.effect) {
        case FX_OFF:
          k = 0;
          break;
        case FX_BOOT:
        case FX_BREATHE: {
          uint32_t period = c.effect == FX_BOOT ? 3200 : 5200 - speed * 36;
          k = 60 + (tri(t, period) * 196) / 255;
          break;
        }
        case FX_BLINK:
        case FX_ALARM: {
          uint32_t period = c.effect == FX_ALARM ? 500 : (1400 - speed * 10 < 340 ? 340 : 1400 - speed * 10);
          if ((t % period) >= period / 2) k = 0;
          break;
        }
        case FX_WAVE:
        case FX_COOL: {
          uint32_t period = 2600 - speed * 18;
          k = 50 + (tri(t + x * (period / MX_W), period) * 206) / 255;
          break;
        }
        case FX_RAINBOW:                 // one colour only: bands moving across, the LED goes round the colours
          k = 40 + (tri((t * (speed + 10)) / 40 + (x + y) * 40, 1024) * 215) / 255;
          break;
        case FX_SPARKLE:
          k = (fx_rand() % 100) < 12 ? 255 : 70;
          break;
        case FX_FIRE:                    // brighter at the bottom, flickering
          k = (uint16_t)((120 + (fx_rand() % 136)) * (3 + y)) / 10;
          if (k > 255) k = 255;
          break;
        case FX_WARM:
          k = 150 + (tri(t, 4000) * 105) / 255;
          break;
        default:
          break;
      }
      mx[y * MX_W + x] = (uint8_t)((top * k + 127) / 255);
      if (x == 0 && y == 0) env = k;
    }
  }
  if (c.effect == FX_RAINBOW) hue_to_rgb((uint8_t)((t * (speed + 10)) / 400), &r, &g, &b);
  if (c.effect == FX_FIRE) { r = 255; g = 90; b = 0; env = 160 + (fx_rand() % 96); }
  uint16_t lv = (uint16_t)((uint32_t)env * c.bri / 100);
  led3[0] = scale8(r, lv); led3[1] = scale8(g, lv); led3[2] = scale8(b, lv);
}

static void render_party_matrix(uint32_t now) {
  PartyBeat p = party_beat(now);
  uint8_t r, g, b;
  hue_to_rgb((uint8_t)(p.hue + p.beat * 16), &r, &g, &b);
  uint16_t env = 255;
  for (uint8_t y = 0; y < MX_H; y++) {
    for (uint8_t x = 0; x < MX_W; x++) {
      uint8_t v;
      if (p.finale) {
        v = (fx_rand() % 100) < 30 ? MX_TOP : 1;
      } else if (p.pattern == 0) {       // a column running across
        v = x == (p.t / (p.beat_ms / 8)) % MX_W ? MX_TOP : 1;
      } else if (p.pattern == 1) {       // flash on the beat
        v = p.in_beat < p.beat_ms / 3 ? MX_TOP : 1;
      } else if (p.pattern == 2) {       // bands
        v = (uint8_t)(tri(p.t / 2 + (x + y) * 40, 512) * MX_TOP / 255);
      } else if (p.pattern == 3) {       // a chessboard that turns over on every beat
        v = ((x + y + p.beat) & 1) ? MX_TOP : 0;
      } else {                           // pulse
        v = (uint8_t)((MX_TOP * (255 - (p.in_beat * 200) / p.beat_ms)) / 255);
      }
      mx[y * MX_W + x] = v;
    }
  }
  if (p.pattern == 1) env = p.in_beat < p.beat_ms / 3 ? 255 : 50;
  if (p.pattern == 4) env = 255 - (p.in_beat * 200) / p.beat_ms;
  led3[0] = scale8(r, env); led3[1] = scale8(g, env); led3[2] = scale8(b, env);
}

static void flush_matrix() {
  if (!mx_valid || memcmp(mx, mx_sent, sizeof(mx)) != 0) {
    matrixGrayscaleWrite(mx);
    memcpy(mx_sent, mx, sizeof(mx));
    mx_valid = true;
  }
  if (!led3_valid || memcmp(led3, led3_sent, sizeof(led3)) != 0) {
    analogWrite(LED3_R, led3[0]);
    analogWrite(LED3_G, led3[1]);
    analogWrite(LED3_B, led3[2]);
    memcpy(led3_sent, led3, sizeof(led3));
    led3_valid = true;
  }
}

// Write the frames, within the power budget, only where they changed.
static void flush_lights() {
  uint8_t bri5 = (uint8_t)(((uint16_t)max_bri * 31 + 50) / 100);
  // per light brightness requested by Linux, combined with the cap
  uint8_t b5[N_LIGHTS];
  float ma = 0;
  for (uint8_t li = 0; li < N_LIGHTS; li++) {
    uint8_t rel = party_on ? 100 : cur_light[li].bri;
    b5[li] = (uint8_t)(((uint16_t)bri5 * rel + 50) / 100);
    if (b5[li] == 0 && rel > 0 && bri5 > 0) b5[li] = 1;
    float sum = 0;
    for (uint8_t i = 0; i < N_LED; i++) sum += frame[li][i][0] + frame[li][i][1] + frame[li][i][2];
    ma += sum / 255.0f * MA_PER_CHANNEL * b5[li] / 31.0f;
  }
  uint16_t k = 256;
  if (ma > budget_ma && ma > 0) k = (uint16_t)(256.0f * budget_ma / ma);
  for (uint8_t li = 0; li < N_LIGHTS; li++) {
    if (!(modules_mask & (1u << LIGHT_BIT[li]))) continue;
    uint8_t out[N_LED * 4];
    for (uint8_t i = 0; i < N_LED; i++) {
      out[i * 4 + 0] = 0xE0 | (b5[li] & 0x1F);
      out[i * 4 + 1] = scale8(frame[li][i][2], k);   // blue
      out[i * 4 + 2] = scale8(frame[li][i][1], k);   // green
      out[i * 4 + 3] = scale8(frame[li][i][0], k);   // red
    }
    if (sent_valid[li] && memcmp(out, sent_frame[li], sizeof(out)) == 0) continue;
    if (hub_select(LIGHT_CH[li]) && bus_write(ADDR_PIXELS, out, sizeof(out))) {
      memcpy(sent_frame[li], out, sizeof(out));
      sent_valid[li] = true;
    } else {
      sent_valid[li] = false;
      set_module(LIGHT_BIT[li], false);
    }
  }
}

static void probe_lights() {
  for (uint8_t li = 0; li < N_LIGHTS; li++) {
    bool present = hub_select(LIGHT_CH[li]) && bus_probe(ADDR_PIXELS);
    if (present && !(modules_mask & (1u << LIGHT_BIT[li]))) sent_valid[li] = false;
    set_module(LIGHT_BIT[li], present);
  }
}

// ============================================================ buttons
static void poll_buttons() {
  if (!(modules_mask & (1u << M_BUTTONS))) return;
  uint8_t d[4];
  if (!hub_select(CH_TOTEM) || !bus_read(ADDR_BUTTONS, d, 4)) { set_module(M_BUTTONS, false); return; }
  for (uint8_t i = 0; i < 3; i++) {
    uint8_t v = d[1 + i] ? 1 : 0;
    if (v == btn_raw[i]) {
      if (btn_count[i] < 2) btn_count[i]++;
    } else {
      btn_raw[i] = v;
      btn_count[i] = 0;
    }
    if (btn_count[i] == 2 && btn_stable[i] != v) {   // two equal readings in a row
      btn_stable[i] = v;
      Event ev = {1, i, v, 0};
      k_msgq_put(&events, &ev, K_NO_WAIT);
    }
  }
}

static uint32_t led_last = 0;
static bool led_phase = false;

static void write_leds(uint32_t now) {
  if (!(modules_mask & (1u << M_BUTTONS))) return;
  uint8_t mask, blink;
  bool dirty;
  k_mutex_lock(&state_lock, K_FOREVER);
  mask = req_leds; blink = req_blink; dirty = req_leds_dirty; req_leds_dirty = false;
  k_mutex_unlock(&state_lock);
  if (blink && now - led_last >= 250) { led_last = now; led_phase = !led_phase; dirty = true; }
  if (!dirty) return;
  uint8_t out[3];
  for (uint8_t i = 0; i < 3; i++) {
    bool on = (mask >> i) & 1;
    if ((blink >> i) & 1) on = led_phase;
    out[i] = on ? 1 : 0;              // only 0 or 1: other bytes are commands to the module
  }
  if (hub_select(CH_TOTEM)) bus_write(ADDR_BUTTONS, out, 3);
}

// ============================================================ thermo (HS3003)
static void poll_thermo(uint8_t n, uint32_t now) {
  if (!(modules_mask & (1u << THERMO_BIT[n]))) return;
  if (thermo_phase[n] == 0) {
    if (now - thermo_at[n] < THERMO_PERIOD_MS) return;
    // measurement request: the address alone, or with one zero byte
    if (hub_select(CH_THERMO[n]) && (bus_write(ADDR_THERMO, nullptr, 0) || bus_write(ADDR_THERMO, (const uint8_t *)"\0", 1))) {
      thermo_phase[n] = 1;
      thermo_at[n] = now;
    } else {
      set_module(THERMO_BIT[n], false);
      thermo_at[n] = now;
    }
  } else if (now - thermo_at[n] >= THERMO_WAIT_MS) {
    uint8_t d[4];
    thermo_phase[n] = 0;
    thermo_at[n] = now;
    if (!hub_select(CH_THERMO[n]) || !bus_read(ADDR_THERMO, d, 4)) { set_module(THERMO_BIT[n], false); return; }
    if ((d[0] >> 6) != 0) return;                   // stale data: wait for the next one
    uint16_t rh_raw = ((uint16_t)(d[0] & 0x3F) << 8) | d[1];
    uint16_t t_raw = (((uint16_t)d[2] << 8) | d[3]) >> 2;
    int32_t rh = (int32_t)((uint32_t)rh_raw * 10000U / 16383U);          // % x100
    int32_t tc = (int32_t)((uint32_t)t_raw * 16500U / 16383U) - 4000;     // °C x100
    Event ev = {3, n, tc, rh};
    k_msgq_put(&events, &ev, K_NO_WAIT);
  }
}

static void probe_totem_and_thermo() {
  for (uint8_t n = 0; n < 2; n++) set_module(THERMO_BIT[n], hub_select(CH_THERMO[n]) && bus_probe(ADDR_THERMO));
  if (hub_select(CH_TOTEM)) {
    bool had = modules_mask & (1u << M_BUTTONS);
    set_module(M_BUTTONS, bus_probe(ADDR_BUTTONS));
    if (!had && (modules_mask & (1u << M_BUTTONS))) req_leds_dirty = true;
  }
}

// ============================================================ io thread
static void do_scan();
static void io_thread(void *, void *, void *) {
  uint32_t next_frame = 0, next_button = 0, next_probe = 0;
  bool first = true;
  for (;;) {
    uint32_t now = k_uptime_get_32();

    if (first || now >= next_probe) {
      next_probe = now + PROBE_MS;
      if (bus_stuck || bus_lines() != 3) bus_unstick();
      // A module that lost power for a moment comes back dark, and a probe
      // may not have seen it missing: every frame and the LEDs go out again.
      k_mutex_lock(&state_lock, K_FOREVER);
      for (uint8_t li = 0; li < N_LIGHTS; li++) sent_valid[li] = false;
      req_leds_dirty = true;
      k_mutex_unlock(&state_lock);
      if (first || !hub_addr) hub_find();
      if (first || !relay_addr) relay_find();
      probe_lights();
      probe_totem_and_thermo();
      first = false;
    }

    // relay requests (the boot request switches it off)
    int8_t rr;
    k_mutex_lock(&state_lock, K_FOREVER);
    rr = req_relay; req_relay = -1;
    k_mutex_unlock(&state_lock);
    if (rr >= 0 && !relay_command(rr == 1)) {
      k_mutex_lock(&state_lock, K_FOREVER);
      if (req_relay < 0) req_relay = rr;     // try again on the next pass
      k_mutex_unlock(&state_lock);
    }

    // Linux silent for too long: fan off, lights back to the waiting breath.
    // The Bridge thread updates last_linux_ms at any moment, also after `now`
    // was read (the probes and the relay pulse take time): read it first, then
    // a fresh clock, and compare with a signed difference. The fan goes off
    // through req_relay, which is tried again until the module takes it.
    uint32_t seen = last_linux_ms;
    uint32_t t_now = k_uptime_get_32();
    if (linux_seen && (int32_t)(t_now - seen) > (int32_t)LINUX_SILENT_MS) {
      linux_seen = false;
      k_mutex_lock(&state_lock, K_FOREVER);
      req_relay = 0;
      k_mutex_unlock(&state_lock);
      for (uint8_t li = 0; li < N_LIGHTS; li++) { cur_light[li] = LightCmd(); cur_light[li].started = t_now; }
      cur_matrix = LightCmd();
      cur_matrix.started = t_now;
      party_on = false;
    }

    if (scan_channel >= 0) do_scan();

    if (now >= next_button) {
      next_button = now + BUTTON_MS;
      poll_buttons();
      write_leds(now);
    }
    poll_thermo(0, now);
    poll_thermo(1, now);

    if (now >= next_frame) {
      next_frame = now + FRAME_MS;
      PartyCmd p;
      k_mutex_lock(&state_lock, K_FOREVER);
      for (uint8_t li = 0; li < N_LIGHTS; li++) {
        if (req_light_dirty[li]) {
          cur_light[li] = req_light[li];
          cur_light[li].started = now;
          req_light_dirty[li] = false;
        }
      }
      if (req_matrix_dirty) {
        cur_matrix = req_matrix;
        cur_matrix.started = now;
        req_matrix_dirty = false;
      }
      p = req_party;
      req_party.pending = false;
      k_mutex_unlock(&state_lock);
      if (p.pending) {
        party_bpm10 = p.bpm10;
        party_seed = p.seed ? p.seed : 1;
        party_start = now + p.delay;
        party_end = party_start + p.duration;
        party_on = true;
      }
      if (party_on && now >= party_end) party_on = false;
      for (uint8_t li = 0; li < N_LIGHTS; li++) {
        LightCmd &c = cur_light[li];
        if (c.duration && now - c.started >= c.duration) { c.effect = FX_OFF; c.duration = 0; }
      }
      if (cur_matrix.duration && now - cur_matrix.started >= cur_matrix.duration) {
        cur_matrix.effect = FX_OFF;
        cur_matrix.duration = 0;
      }
      if (party_on && now >= party_start) {
        render_party(now);
        render_party_matrix(now);
      } else {
        for (uint8_t li = 0; li < N_LIGHTS; li++) render_light(li, now);
        render_matrix(now);
      }
      flush_lights();
      flush_matrix();
    }
    k_msleep(2);
  }
}

// ============================================================ Bridge handlers
// They only touch the shared state: never the bus (except scan, under the
// bus lock) and never the Bridge itself.
static void seen_linux() { last_linux_ms = k_uptime_get_32(); linux_seen = true; }

int version() { seen_linux(); return PROTOCOL; }

int ping() { seen_linux(); return (int)(k_uptime_get_32() & 0x7FFFFFFF); }

bool light(int index, int effect, int r, int g, int b, int bri, int speed, int duration_ms) {
  seen_linux();
  if (index < 0 || (index >= N_LIGHTS && index != MATRIX_LIGHT)) return false;
  k_mutex_lock(&state_lock, K_FOREVER);
  LightCmd &c = index == MATRIX_LIGHT ? req_matrix : req_light[index];
  c.effect = (uint8_t)effect; c.r = (uint8_t)r; c.g = (uint8_t)g; c.b = (uint8_t)b;
  c.bri = (uint8_t)constrain(bri, 0, 100); c.speed = (uint8_t)constrain(speed, 0, 100);
  c.duration = duration_ms > 0 ? (uint32_t)duration_ms : 0;
  if (index == MATRIX_LIGHT) req_matrix_dirty = true;
  else req_light_dirty[index] = true;
  k_mutex_unlock(&state_lock);
  return true;
}

bool party(int bpm10, int seed, int duration_ms, int delay_ms) {
  seen_linux();
  k_mutex_lock(&state_lock, K_FOREVER);
  req_party.pending = true;
  req_party.bpm10 = (uint32_t)constrain(bpm10, 600, 2000);
  req_party.seed = (uint32_t)seed;
  req_party.duration = (uint32_t)constrain(duration_ms, 1000, 120000);
  req_party.delay = (uint32_t)constrain(delay_ms, 0, 2000);
  k_mutex_unlock(&state_lock);
  return true;
}

int relay(int on) {
  seen_linux();
  k_mutex_lock(&state_lock, K_FOREVER);
  req_relay = on ? 1 : 0;
  k_mutex_unlock(&state_lock);
  return on ? 1 : 0;
}

int relay_now() { seen_linux(); return relay_state; }

bool leds(int mask, int blink) {
  seen_linux();
  k_mutex_lock(&state_lock, K_FOREVER);
  req_leds = (uint8_t)(mask & 7); req_blink = (uint8_t)(blink & 7); req_leds_dirty = true;
  k_mutex_unlock(&state_lock);
  return true;
}

bool limits(int max_brightness, int budget) {
  seen_linux();
  k_mutex_lock(&state_lock, K_FOREVER);
  max_bri = (uint8_t)constrain(max_brightness, 0, 100);
  budget_ma = (uint16_t)constrain(budget, 50, 1500);
  for (uint8_t li = 0; li < N_LIGHTS; li++) sent_valid[li] = false;
  k_mutex_unlock(&state_lock);
  return true;
}

int modules() { seen_linux(); return (int)modules_mask; }

// State of the Qwiic bus: bit 0 SCL high, bit 1 SDA high (both seen at the
// last check, made with the bus idle: a live reading would often catch a
// transfer), bit 2 the last check found a line held low, bits 8-15 attempts to free the
// bus, bits 16-30 transactions refused because of a low line.
int bus() {
  seen_linux();
  uint32_t refused = bus_refused > 0x7FFF ? 0x7FFF : bus_refused;
  return (int)(bus_levels | (bus_stuck ? 4u : 0u) | ((uint32_t)bus_unsticks << 8) | (refused << 16));
}

// Which addresses answer on a hub channel (8 = main bus), 32 per block.
// The io thread does it, because it is the only owner of the bus.
int scan(int channel, int block) {
  seen_linux();
  if (block < 0 || block > 3) return 0;
  k_sem_reset(&scan_done);
  scan_block = block;
  scan_channel = channel;
  if (k_sem_take(&scan_done, K_MSEC(800)) != 0) return -1;
  return (int)scan_result;
}

static void do_scan() {
  int channel = scan_channel, block = scan_block;
  if (channel < 0 || block < 0) return;
  scan_channel = -1;
  uint32_t found = 0;
  hub_select(channel < 8 ? (int8_t)channel : -1);
  for (uint8_t i = 0; i < 32; i++) {
    uint8_t a = (uint8_t)(block * 32 + i);
    if (a < 0x01 || a > 0x77) continue;
    if (bus_probe(a)) found |= (1u << i);
  }
  scan_result = found;
  k_sem_give(&scan_done);
}

// ============================================================ setup / loop
void setup() {
  Wire1.begin();                     // I2C4 has deferred init: this is where it starts
  Wire1.setClock(100000);            // Modulino run at 100 kHz; the UNO Q default is 400 kHz
  if (bus_lines() != 3) bus_unstick();
  for (uint8_t li = 0; li < N_LIGHTS; li++) { cur_light[li].started = 0; req_light_dirty[li] = false; }
  cur_matrix.started = 0;
  matrixBegin();                     // the light of the utility room
  matrixSetGrayscaleBits(MX_BITS);
  req_relay = 0;                     // the latching relay may still be closed from before a power cut
  k_thread_create(&io_thread_data, io_stack, K_THREAD_STACK_SIZEOF(io_stack),
                  io_thread, NULL, NULL, NULL, 7, 0, K_NO_WAIT);

  Bridge.begin();                    // waits until arduino-router opens the serial line
  Bridge.provide("version", version);
  Bridge.provide("ping", ping);
  Bridge.provide("light", light);
  Bridge.provide("party", party);
  Bridge.provide("relay", relay);
  Bridge.provide("relay_state", relay_now);
  Bridge.provide("leds", leds);
  Bridge.provide("limits", limits);
  Bridge.provide("modules", modules);
  Bridge.provide("scan", scan);
  Bridge.provide("bus", bus);
  bridge_ready = true;
  Event ev = {4, (int32_t)modules_mask, 0, 0};
  k_msgq_put(&events, &ev, K_NO_WAIT);
}

void loop() {
  Event ev;
  while (k_msgq_get(&events, &ev, K_NO_WAIT) == 0) {
    switch (ev.kind) {
      case 1: Bridge.notify("btn", (int)ev.a, (int)ev.b); break;
      case 3: Bridge.notify("thermo", (int)ev.a, (int)ev.b, (int)ev.c); break;
      case 4: Bridge.notify("mods", (int)ev.a); break;
    }
  }
  delay(5);
}
