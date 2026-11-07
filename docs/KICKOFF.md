# Invisible Signals — kickoff plan

**HackTheBurgh 2026 · The Nucleus, King's Buildings · 4 people · 24 hours**
Pitch: *"Hear where you are. Feel which floor. Control the room with radio."*

This is the plan everyone follows. It fixes **what** each person delivers,
**the interfaces between people**, and **the deadlines**. It deliberately does
**not** fix how you build your part: each owner decides their own tools,
libraries and approach, and works with their own AI agent. If you change an
interface (§4), tell the person on the other side first.

---

## 1. The demo we are building toward

A presentation that runs on our own website. The audience sees, in order:

1. **Sky.** A recording of aircraft noise, its Doppler curve, the real ADS-B
   track it matches, and the resulting **estimate of where in Edinburgh we
   are**, with the remaining ambiguity shown.
2. **Building.** A **3D model of the Nucleus**, built from the floor plan.
   The phone barometer picks the **floor**, which lights up in the model.
3. **Radio.** A live Wi-Fi signal trace from the XIAO. The presenter makes a
   **hand gesture** and the slide changes. Then a judge tries it.

The **gesture-driven slide change** is the signature moment. Every slide
change in the talk is done by gesture, with a keyboard fallback.

### What each sensor can honestly claim

| Capability | What we can claim | What we must not claim |
|---|---|---|
| Plane sounds | Estimate the **recording location** within a bounded Edinburgh search, with competing regions | Room-level or person-level position |
| Barometer | **Which floor**, after calibrating against our survey | Absolute floor without a reference reading |
| Wi-Fi (one XIAO + one transmitter) | **Motion** near the link and **one deliberate gesture** | Tracking where people are in the room, counting people, body pose |
| 3D model | A **prepared model** of the Nucleus from its floor plan | That the model was sensed or reconstructed |

Every view shows a mode badge: **live**, **replay**, **simulated** or
**configured**. Configured or replayed data is never presented as measured.

---

## 2. Who owns what

| Person | Owns | Helps with | Branch | Folders |
|---|---|---|---|---|
| **Kameran** | **Plane sounds → location.** Recording, ADS-B archive, Doppler matching, Edinburgh search, results | Lends the XIAO and DJI mic; rig hardware advice | `audio` | `services/aircraft/` |
| **Anna** | **3D Nucleus model** and **gesture recognition** (from the CSI stream to a `gesture.detected` event). Hosts the overnight agent | — | `building-3d`, `gesture` | `web/building3d/`, `assets/building/`, `services/wifi/` |
| **Elisa** | **The website**: slide deck + live dashboard, driven by hub events; slide change on gesture | **Gesture:** data collection, labelling, testing with different people | `web` | `web/` (except `web/building3d/`) |
| **Shangran** | **Everything that connects the parts:** hub + schema, XIAO bring-up and CSI streaming, phone barometer → floor, replay, runbook, the physical rig | Whoever is blocked | `hub` | `services/hub/`, `shared/`, `config/`, `services/pressure/`, `services/mock/`, `firmware/xiao/`, `assets/hardware/` |

How the gesture work splits: **Shangran** gets CSI frames flowing from the XIAO
to the laptop (firmware, hotspot, serial). **Anna** turns that stream into a
reliable gesture detector. **Elisa** collects and labels trials with Anna, and
makes the website react to the gesture.

---

## 3. Materials

| Item | Who holds it | Use |
|---|---|---|
| Seeed XIAO ESP32C6 ([PiHut](https://thepihut.com/products/seeed-xiao-esp32c6?variant=53972794442113)) | Shangran (from Kameran) | Wi-Fi CSI receiver over USB. If there are two, a send/receive pair avoids the hotspot entirely. |
| Phone hotspot, 2.4 GHz | Shangran | CSI transmitter. Fixed position, plugged in, sleep off. |
| DJI Mic Mini | Kameran | Aircraft recordings. Noise cancelling and low-cut **off**. Keep raw files. |
| Phone barometer app | Shangran | Floor. phyphox can stream to the laptop; CSV export is the fallback. |
| Wires, soldering kit, 3D printer | Shangran (Kameran advises) | XIAO puck, transmitter cradle, mic clip, taped gesture zone. |

### Floor survey (measured 7 Nov 2026, in `config/default.json`)

| Floor | hPa | Δ from floor 0 | ≈ height |
|---|---|---|---|
| 0 | 1013.221 | 0 Pa | 0.0 m |
| 1 | 1012.506 | 71.5 Pa | 6.0 m |
| 2 | 1011.910 | 131.1 Pa | 10.9 m |
| 3 | 1011.217 | 200.4 Pa | 16.7 m |

Floors are 60–72 Pa apart, well above phone-sensor noise. Weather shifts the
absolute values over 24 h, so re-zero at floor 0 before the demo and use only
the differences. Floor heights also tell Anna how tall to make each storey of
the 3D model.

### References
- Aircraft method: [colsto's video](https://www.youtube.com/watch?v=UytYrhYLOKI), [mjshiggins/dopplertrack](https://github.com/mjshiggins/dopplertrack), [AlanBacker/audio-flyover-geolocation](https://github.com/AlanBacker/audio-flyover-geolocation). The dopplertrack methodology (prop/jet filtering by ICAO type, 200 m grid, slant distance with a DEM, emission-time Doppler, locked two-event scoring) is a good template.
- Flight data: [airplanes.live API](https://airplanes.live/api-guide) (no key, 1 req/s) or [OpenSky](https://openskynetwork.github.io/opensky-api/rest.html). Neither gives free history: **start logging at H0**.
- Wi-Fi: [espressif/esp-csi](https://github.com/espressif/esp-csi), [XIAO ESP32C6 guide](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/).

---

## 4. Interfaces between people (agree by H1, then keep stable)

These are the only things you must not change on your own.

### 4.1 Events through the hub (Shangran owns)
Every producer POSTs events to the hub (`http://127.0.0.1:8000/events`); the
website listens on `ws://127.0.0.1:8000/ws` and can fetch `GET /state` on
reconnect. The envelope and payload fields are defined in `shared/schema.py`
and checked on arrival. The hub is already written and tested.

| Event | Sent by | Used by |
|---|---|---|
| `aircraft.tracks`, `aircraft.signature`, `location.estimate` | Kameran | Elisa (Sky slide) |
| `pressure.sample`, `floor.estimate` | Shangran | Elisa, Anna (floor highlight) |
| `wifi.features` | Shangran's CSI streamer (or Anna's detector) | Elisa (Radio slide), Anna |
| `gesture.detected` | Anna | Hub → `demo.state` → Elisa (slide change) |
| `demo.state`, `source.status`, `replay.progress` | Hub / every producer | Elisa |

The hub decides slide changes, not the website: it applies the 2-second
cooldown, ignores gestures while not armed or while calibrating, and emits
`demo.state`. This means a gesture changes the slide once, however many
browser tabs are open. The website also offers manual controls
(`POST /demo/next`, keyboard) as a fallback.

To use Python helpers: `from shared.client import EventClient`. To produce
from another language, POST the JSON envelope directly.

### 4.2 3D model → website (Anna ↔ Elisa)
Anna delivers a self-contained component in `web/building3d/` that Elisa
mounts in a slide. Minimum contract:

```ts
mountBuilding(container: HTMLElement, opts?: {}) => {
  setFloor(floorId: "0" | "1" | "2" | "3" | null): void;   // highlight; null = none
  setMode(mode: "live" | "replay" | "simulated" | "configured"): void;
  dispose(): void;
}
```

Anna picks the tech (three.js, Babylon, a glTF exported from Blender…).
Elisa picks the web framework. If Elisa's stack can't import Anna's module
directly, the fallback is an `<iframe>` with `postMessage({floor, mode})`.

### 4.3 CSI stream → gesture detector (Shangran ↔ Anna)
Shangran delivers raw CSI frames on the laptop, in a format both agree at H1
(e.g. a serial reader that yields `{t, rssi, amplitudes[]}` per frame, plus a
logger that saves them to `data/csi/*.jsonl`). Anna's detector consumes that
and emits `gesture.detected`. Labelled trials go in `data/gesture/` with a
trial ID on every window, so splits can be done by trial.

---

## 5. What each person delivers, by when

Each row says **what must exist**, not how to build it. Your agent can plan
the how. Report at each checkpoint with a real artefact or a named blocker.

### Kameran — plane sounds → location

| By | Deliverable |
|---|---|
| H0 + 10 min | ADS-B logger running and saving to `data/adsb/` (never stop it). |
| H1 | DJI audio reaching the laptop with UTC start time logged. |
| H3 | ≥30 min outdoor recording with the exact recording position stored **separately** in `data/ground_truth.json`. |
| H6 | **Gate:** one real aircraft signature on a spectrogram with the predicted Doppler curve overlaid, at the known location. If no usable tone: manual ridge marking, or a clearly labelled reference replay. |
| H8 | Search over the Edinburgh box producing `location.estimate` events (even if rough), data copied to the shared drive, night tasks written. |
| H16–18 | Blind evaluation on a clip **not used for tuning**: distance error and competing regions, in `docs/RESULTS.md`. |

Your decisions: provider, FFT settings, ridge method, scoring method, how far
to automate. Fixed: the Edinburgh search box in `config/default.json`, never
reading ground truth inside the search, and labelling replay as replay.

### Anna — 3D Nucleus model + gesture recognition

| By | Deliverable |
|---|---|
| H1 | Floor plan sourced (university estates PDF, photos of fire-exit plans, or a traced outline); tech choice made; agree the CSI frame format with Shangran. |
| H3 | 3D model with 4 storeys at survey heights, rotating in a browser, `setFloor()` working against mock events. |
| H6 | Model handed to Elisa through the §4.2 contract. Gesture detector v1 running on the live CSI stream, sending `gesture.detected`. |
| H8 | 25+ labelled positive trials and 5+ min of negatives (with Elisa); detector tuned; night tasks written. |
| H16–18 | Held-out test: ≥8/10 gestures by a **second person**, ≤1 false slide change in 5 min of normal activity. Results in `docs/RESULTS.md`. |

Your decisions: modelling tool and level of detail, the gesture itself (it
must be deliberate and distinctive, e.g. a double sweep), features,
classifier. Fixed: one gesture class only, a score is not a percentage, and
if only general motion works it is called a "motion trigger".

### Elisa — website (slides + live dashboard)

| By | Deliverable |
|---|---|
| H1 | Framework chosen; page connected to the hub WebSocket and showing incoming events. |
| H3 | Slide deck skeleton (title, Sky, Building, Radio, results, thank you) changing on `demo.state` and on the keyboard, with mode badges and stale/offline indicators. |
| H6 | Live charts: Doppler curve (observed vs predicted), Edinburgh map with tracks and candidate regions, pressure trace, CSI motion trace. Anna's 3D model mounted. |
| H8 | Full talk clickable end to end with mock events; gesture data collection with Anna done; night tasks written. |
| H16–20 | Real data in every slide, replay banner, backup video recorded, pitch under 2 minutes, rehearsed 3 times. |

Your decisions: framework, slide design, charts library, which events to
show. Fixed: slide changes come from the hub's `demo.state`, every sensor
shows its mode, and configured data is visibly marked.

### Shangran — hub, XIAO bring-up, floor, integration

| By | Deliverable |
|---|---|
| H0 + 10 min | `make hub` running, `/health` reachable by everyone on the same network. |
| H1 | XIAO flashed and printing CSI frames; frame format agreed with Anna. Phone barometer reachable from the laptop. Mock producer started so Elisa has data. |
| H3 | CSI streaming and logging at a measured packet rate; `wifi.features` reaching the hub. Floor walk 0→3 by stairs recorded. **Gate:** no CSI by H3 → only firmware/hotspot work until it works. |
| H6 | `floor.estimate` events with hysteresis and dwell; replay of a saved session works. Rig printed and fixed in place. |
| H8 | Everything merged into `main`; `data/` copied to the shared drive; night agent started with Anna. |
| H16–21 | Unplug/replug tests (other parts keep running, no duplicate slide changes), full restart from `make` commands, `README` + `docs/RUNBOOK.md`, submission. |

Your decisions: firmware variant (router vs two-board ESP-NOW), pressure
transport, floor algorithm, rig design. Fixed: the event contract unless all
owners agree.

---

## 6. Timeline: 8 h together → 8 h agent → 8 h together

| Hours | What happens |
|---|---|
| **H0–H1** | Clone, branch, run `make hub`. Each person sets up their agent with this file and their row in §5. Kameran starts ADS-B logging. **H1 stand-up (10 min):** confirm the §4 interfaces. |
| **H1–H8** | Build. Stand-ups at **H3, H6, H8**: 2 minutes each, show an artefact or name a blocker. Merge to `main` after every working step, not at the end. |
| **H8** | **Hard stop.** Merge, copy data to the shared drive, fill in `docs/NIGHT_QUEUE.md` (each person adds their own tasks), start the night loop on Anna's laptop, sleep. |
| **H8–H16** | Overnight agent works through the queue on branch `night/agent` (§7). |
| **H16–H17** | Each owner reviews the agent's work in their area and merges what passes. |
| **H17–H18** | Held-out evaluations (aircraft, gesture, floor). **H18: feature freeze.** |
| **H18–H21** | Bug fixes only. Full restart rehearsal. Backup video. |
| **H21–H24** | Rehearse ×3, submit before the deadline. |

### Hard gates
- **H3:** no CSI stream → Shangran works only on firmware/hotspot; Anna builds the detector on recorded or simulated data meanwhile.
- **H6:** no aircraft tone → Kameran switches to manual ridge or labelled replay. No phone pressure stream → labelled configured floor.
- **H10 (next morning check):** gesture false triggers dominate → simplify to a deliberate motion trigger.
- **H18:** feature freeze. No new libraries, no redesigns after this.

---

## 7. Overnight agent on Anna's laptop (H8–H16)

The agent can only work on things that don't need hardware, so Day 1 must
leave it **data**: the aircraft recordings + ADS-B archive + ground truth,
labelled gesture trials, the floor walk, and one saved hub session.

At H8:
```bash
git checkout -b night/agent
cp docs/NIGHT_QUEUE.template.md docs/NIGHT_QUEUE.md   # everyone adds their tasks
caffeinate -dims &
NIGHT_END="2026-11-08T07:00" scripts/night_agent.sh
```

The script runs the agent in a loop, one queue task per iteration: implement,
run `make test`, commit with a `night:` prefix, tick the task, log what it did
in `docs/NIGHT_LOG.md`. It never touches `main`, `firmware/`, dependencies or
raw data, and marks tasks `BLOCKED` or `NEEDS-HUMAN` rather than guessing.

At H16 each owner reviews `git log night/agent` for their folders and merges
what passes.

---

## 8. Ground rules

- Your folder, your decisions. Touching someone else's folder: message them first.
- Merge small working steps to `main` often via PR; never force-push `main`.
- Raw data stays out of git; copy it to the shared drive.
- Commands live in the `Makefile`; anything needed for the demo must start from it.
- Credentials go in `.env` or `config/local.json` (both git-ignored).
- Credit what we reuse (videos, repos, APIs) in the README and on the final slide.
