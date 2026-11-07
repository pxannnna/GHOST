# GHOST — kickoff plan

**G**athering **H**idden **O**bservations from **S**ound & **T**ransmissions

**HackTheBurgh 2026 · The Nucleus, King's Buildings · 4 people · 24 hours**
Pitch: *"Hear where you are. Feel which floor. Control the room with radio."*

This is the plan everyone follows. It fixes **what** each person delivers,
**the interfaces between people**, and **the deadlines**. It does **not** fix
how you build your part: each owner chooses their own tools and approach and
works with their own AI agent. If you change an interface (§4), tell the
person on the other side first.

---

## 1. What GHOST does

A laptop works out **which room of the Nucleus it is in**, using only
signals nobody can see, and the presentation is controlled by **hand
gestures sensed through Wi-Fi**.

1. **Which floor?** The phone barometer measures air pressure. Compared with
   our survey, it picks the floor (0–3).
2. **What shape is this room?** The laptop plays a frequency sweep through its
   speaker and records the echoes. From the room's impulse response we
   estimate how far away the walls and ceiling are and how long the room
   rings, at 3–4 positions, giving an estimated room size.
3. **Which room exactly?** We compare that estimate with every room **on that
   floor** in the Nucleus floor plan and rank the matches. The best match
   lights up in a **3D model of the Nucleus**.
4. **Control by gesture.** Throughout the talk, a deliberate hand gesture near
   the XIAO Wi-Fi sensor changes the slide on our website. A judge tries it.

### What we can honestly claim

| Capability | Claim | Do **not** claim |
|---|---|---|
| Barometer | Which floor, after calibrating against our survey | An absolute floor without a reference reading |
| Echolocation | Estimated room size and reverberation; a **ranked list** of rooms on that floor that match | An exact map of the room's outline (one speaker + one mic hear distances, not directions) |
| Room match | The best-matching room, with the runners-up shown | Certainty when two rooms have similar sizes |
| 3D model | A **prepared model** built from the floor plan | That the model was sensed or reconstructed |
| Wi-Fi | Motion near the sensor and **one deliberate gesture** | Tracking people, counting people, body pose |

Every slide shows a mode badge: **live**, **replay**, **simulated** or
**configured**. Configured or replayed data is never shown as measured.

---

## 2. Who owns what

| Person | Owns | Branch | Folders |
|---|---|---|---|
| **Anna** | **Room finding:** echolocation, phone barometer → floor, room matching against the floor plan, the **3D Nucleus model**. Hosts the overnight agent | `room-location` | `services/acoustics/`, `services/pressure/`, `web/building3d/`, `assets/building/` |
| **Kameran** | **Wi-Fi gestures**, jointly with Elisa: XIAO firmware, CSI streaming, gesture detection | `wifi-gesture` | `firmware/xiao/`, `services/wifi/` |
| **Elisa** | **Wi-Fi gestures**, jointly with Kameran: wiring and connecting the boards, data collection, gesture detection | `wifi-gesture` | `firmware/xiao/`, `services/wifi/` |
| **Shangran** | **The website:** slide deck + live dashboard, slide change on gesture, plus the event hub it talks to | `website` | `web/` (except `web/building3d/`), `services/hub/`, `shared/`, `services/mock/` |

**Kameran and Elisa** split the Wi-Fi work between themselves at H0.
Suggested split: Kameran leads firmware and the CSI stream, Elisa leads
wiring, data collection and the detector, and both test together.

**Optional stretch (Kameran):** the plane-sound idea (aircraft Doppler →
which part of Edinburgh) can open the talk **only if** gestures are reliable
by H8. Branch `plane-location`, folder `services/aircraft/`. Settings are in `config/default.json` under `aircraft_optional`.

### Branches

| Branch | Who | Contains work in |
|---|---|---|
| `main` | everyone (merge target) | the working, demo-ready version |
| `room-location` | Anna | `services/acoustics/`, `services/pressure/`, `assets/building/`, `web/building3d/` |
| `wifi-gesture` | Kameran + Elisa | `firmware/xiao/`, `services/wifi/` |
| `plane-location` | Kameran (optional) | `services/aircraft/` |
| `website` | Shangran | `web/`, `services/hub/`, `shared/`, `services/mock/` |
| `night/agent` | overnight agent | created at H8 from `main` |

Each branch only changes its own folders, so merges into `main` don't
conflict. Merge to `main` after every working step and pull `main` into your
branch often (`git pull origin main`) to pick up the others' work. Kameran and
Elisa share `wifi-gesture`: pull before you start, commit small, push often.

---

## 3. Materials

| Item | Who | Use |
|---|---|---|
| Laptop speaker + mic (or the **DJI Mic Mini**) | Anna | Echolocation sweeps. Turn off noise cancelling, voice isolation and low-cut on both the Mac and the DJI. |
| Phone barometer app (e.g. **phyphox**) | Anna | Floor. phyphox can stream to the laptop over Wi-Fi; CSV export is the fallback. |
| Seeed XIAO ESP32C6 ([PiHut](https://thepihut.com/products/seeed-xiao-esp32c6?variant=53972794442113)) | Kameran, Elisa | Wi-Fi CSI receiver over USB. **Try to get a second one** (~£6) as the transmitter (§4.3). |
| Phone hotspot (2.4 GHz) | Kameran, Elisa | Fallback transmitter if there is only one XIAO. Fixed position, plugged in, sleep off. |
| Wires, headers, soldering kit | Kameran, Elisa | Headers on the XIAO(s), an external antenna if needed. |
| Tape, tape measure (or phone measure app) | Everyone | Mark the gesture zone; measure **real room sizes** as ground truth for echolocation. |

No 3D printing. The sensors are fixed in place with tape; nothing may move
after calibration.

### Floor survey (measured 7 Nov 2026, in `config/default.json`)

| Floor | hPa | Δ from floor 0 | ≈ height |
|---|---|---|---|
| 0 | 1013.221 | 0 Pa | 0.0 m |
| 1 | 1012.506 | 71.5 Pa | 6.0 m |
| 2 | 1011.910 | 131.1 Pa | 10.9 m |
| 3 | 1011.217 | 200.4 Pa | 16.7 m |

Floors are 60–72 Pa apart, well above phone-sensor noise. Weather shifts the
absolute values over 24 h, so re-zero at floor 0 before the demo and use only
the differences. These heights also give the storey heights of the 3D model.

---

## 4. Interfaces between people (agree by H1, then keep stable)

### 4.1 Events through the hub (Shangran)
Every producer POSTs JSON events to `http://127.0.0.1:8000/events`. The
website listens on `ws://127.0.0.1:8000/ws` and fetches `GET /state` on
reconnect. Fields are defined and checked in `shared/schema.py`. The hub is
already written and tested.

| Event | Sent by | Shown by |
|---|---|---|
| `pressure.sample`, `floor.estimate` | Anna | Floor slide, 3D model |
| `acoustic.measurement` (one sweep at one position: reverberation time, reflection distances, preview) | Anna | Room slide |
| `room.estimate` (floor, estimated size, ranked candidate rooms, status) | Anna | Room slide, 3D model |
| `wifi.features` (motion score, reduced trace, packet rate) | Kameran/Elisa | Gesture slide |
| `gesture.detected` | Kameran/Elisa | Hub → `demo.state` → slide change |
| `demo.state`, `source.status`, `replay.progress` | Hub / everyone | Every slide (badges) |

`room.estimate` uses the status words `listening`, `candidate`, `supported`,
`ambiguous`, `no_match`. Scores are match scores, never shown as percentages.

**Slide changes are decided by the hub, not the website.** The hub applies a
2-second cooldown, ignores gestures while not armed or while a sensor is
calibrating, and emits `demo.state`. One gesture = one slide change, however
many tabs are open. The slide list is `demo.views` in `config/default.json`
(Shangran edits it). Keyboard and `POST /demo/next` are the fallback.

Python producers use `from shared.client import EventClient`; anything else
POSTs the JSON envelope directly.

### 4.2 Floor plan data (Anna → everyone)
Anna creates `assets/building/rooms.json`: one entry per room with at least
`room_id`, `floor_id`, `label`, `polygon_m` (outline in metres), and
`ceiling_height_m`. The 3D model and the room matcher both read this file,
so they always agree. Mark anything approximate.

### 4.3 3D model → website (Anna → Shangran)
Anna delivers a component in `web/building3d/`:

```ts
mountBuilding(container: HTMLElement, opts?: {}) => {
  setFloor(floorId: string | null): void;                       // highlight a floor
  setRoomCandidates(c: { room_id: string; score: number }[]): void; // best match strongest
  setMode(mode: "live" | "replay" | "simulated" | "configured"): void;
  dispose(): void;
}
```

Anna picks the tech (three.js, Babylon, a glTF from Blender…); Shangran picks
the web framework. Fallback if they don't fit together: an `<iframe>` with
`postMessage({floor, candidates, mode})`.

### 4.4 Wi-Fi stream → gesture detector (Kameran ↔ Elisa)
Agree a frame format at H1, e.g. `{t, mac, rssi, amplitudes[]}`, logged to
`data/csi/*.jsonl`. Labelled trials go in `data/gesture/` with a trial ID on
every window so tests are split by trial. Requirements:

- **Filter by the transmitter's MAC address** (`wifi.transmitter_mac`);
  everyone else's Wi-Fi in the building otherwise looks like motion.
- **Our own traffic at ≥50 packets/s, measured** and reported in
  `wifi.features.packet_rate_hz`. Router beacons (~10/s) are too slow.
- **Two XIAOs if possible** (`csi_send` → `csi_recv` over ESP-NOW): we then
  control channel, packet rate and MAC. Phone hotspot is the fallback.
- Classify **on the laptop**, not on the XIAO.

Recommendations (Kameran and Elisa decide): amplitude only first; subtract an
empty-room baseline and re-record it whenever the sensor moves; smooth with a
moving average or low-pass filter; a broad, deliberate gesture such as a
double sweep; DTW templates or a small classifier.

---

## 5. Suggested approach for echolocation (Anna decides)

This is a starting point, not a requirement.

1. **Measure.** Play an exponential sine sweep (e.g. 200 Hz–20 kHz, 3 s) and
   record it at 48 kHz with all audio processing off. Repeat 3 times per
   position, at 3–4 positions per room. Deconvolve the recording with the
   inverse sweep to get the **room impulse response**.
2. **Extract features.**
   - **Reverberation time (RT60)** from the decay of the impulse response
     (Schroeder backward integration). Bigger, harder rooms ring longer.
   - **Early reflection distances**: peaks in the first ~50 ms after the
     direct sound; distance = delay × 343 / 2. These include the ceiling and
     nearest walls.
   - Combine positions to estimate **length, width and height**.
3. **Predict from the floor plan.** For each room on the measured floor, use
   its size from `rooms.json` to predict the same features. Options: simple
   formulas (Sabine RT60 with an assumed absorption, wall distances from the
   positions) or a simulator such as `pyroomacoustics` (shoebox rooms).
4. **Match.** Score measured vs predicted features for every room on that
   floor; rank them; send `room.estimate` with the top candidates. Use
   `ambiguous` when the top rooms score similarly.
5. **Validate.** Measure real room sizes with a tape measure in at least
   **3 rooms** the team can access (including the demo room). Report the error
   in `docs/RESULTS.md`. Never tune on the same recording you report.
6. **Fallback.** If the physics-based match is weak, record a **fingerprint**
   (features) in each accessible room during the day and match against those.
   Label this "matched against surveyed rooms", not "matched against the
   floor plan".

**Practical notes:** a hackathon hall is loud, so repeat sweeps and average;
keep the laptop at a fixed height; the demo room will be large, which helps it
stand out from offices and labs. Getting the floor plan early is critical:
ask the venue/estates team, or photograph the fire-exit plans on each floor
and trace them to scale.

---

## 6. What each person delivers, by when

Each row says **what must exist**. Your agent plans the how. At each
stand-up, show a real artefact or name a blocker.

### Anna — room finding + 3D model

| By | Deliverable |
|---|---|
| H1 | Floor plan sourced (estates PDF or photos of fire-exit plans). Phone barometer reachable from the laptop. First sweep recorded and an impulse response visible. |
| H3 | `rooms.json` for the floors we can measure (at least the demo floor). Floor detection live: `floor.estimate` from the phone. RT60 + reflection distances from a real room. |
| H6 | **Gate:** echolocation produces a size estimate in 2+ real rooms, compared with tape-measured sizes. If not: switch to surveyed fingerprints (§5.6). 3D model showing 4 storeys with `setFloor()` working, handed to Shangran. |
| H8 | `room.estimate` live end to end (barometer floor + echoes → ranked rooms → model highlights). Recordings and room measurements copied to the shared drive. Night tasks written. |
| H16–18 | Held-out test in a room not used for tuning: correct room in the top 3? Results in `docs/RESULTS.md`. |

Fixed: matching only among rooms on the measured floor; showing runners-up;
labelling surveyed-fingerprint matches as such.

### Kameran + Elisa — Wi-Fi gestures

| By | Deliverable |
|---|---|
| H1 | XIAO flashed and printing CSI frames; split of work agreed; frame format agreed. |
| H3 | **Gate:** CSI streaming with MAC filtering at a measured ≥50 packets/s; motion visibly changes the trace; `wifi.features` reaching the hub. If no CSI by H3, both work only on firmware/transmitter until it works. |
| H6 | Sensor fixed in place, gesture zone taped. 25+ labelled positive trials and 5+ minutes of negatives (typing, walking past, single sweeps, people talking). Detector v1 sending `gesture.detected`. |
| H8 | Gesture changes the slide on the real website. Data copied to the shared drive. Night tasks written. |
| H16–18 | Held-out test: ≥8/10 gestures by someone who didn't train it, ≤1 false slide change in 5 minutes of normal activity. Results in `docs/RESULTS.md`. |

Fixed: one gesture only; if only general motion works, call it a "motion
trigger".

### Shangran — website + hub

| By | Deliverable |
|---|---|
| H0 + 10 min | `make hub` running; `/health` reachable by everyone. |
| H1 | Framework chosen; page connected to the hub WebSocket and printing events. Mock producer emitting simulated events of every type so the others aren't blocked. |
| H3 | Slide deck skeleton (intro, floor, room, model, gesture, results) changing on `demo.state` and keyboard, with mode badges and stale/offline indicators. |
| H6 | Live panels: pressure trace + floor, impulse response + RT60 + reflections, ranked room list, CSI trace + gesture log. Anna's 3D model mounted. |
| H8 | Whole talk clickable end to end with mock events; switches to live sources cleanly. Night tasks written. |
| H16–21 | Real data in every slide, replay banner, backup video, pitch under 2 minutes, rehearsed 3 times, submission. |

Fixed: slide changes come from the hub's `demo.state`; every panel shows its
mode; configured data is visibly marked.

---

## 7. Timeline: 8 h together → 8 h agent → 8 h together

| Hours | What happens |
|---|---|
| **H0–H1** | Clone, branch, `make hub`. Each person gives their agent this file and their row in §6. **H1 stand-up (10 min):** confirm §4 interfaces. |
| **H1–H8** | Build. Stand-ups at **H3, H6, H8** (2 min each: artefact or blocker). Merge to `main` after every working step. |
| **H8** | **Hard stop.** Merge, copy data to the shared drive, fill in `docs/NIGHT_QUEUE.md` (each person adds tasks), start the night loop on Anna's laptop. |
| **H8–H16** | Overnight agent works through the queue on branch `night/agent` (§8). |
| **H16–H17** | Each owner reviews the agent's work in their area and merges what passes. |
| **H17–H18** | Held-out tests: room, floor, gesture. **H18: feature freeze.** |
| **H18–H21** | Bug fixes only. Full restart rehearsal from `make` commands. Backup video. |
| **H21–H24** | Rehearse ×3, submit before the deadline. |

### Hard gates
- **H3:** no CSI → Kameran and Elisa work only on firmware/transmitter. No phone pressure stream → Anna uses the CSV fallback or a labelled configured floor.
- **H6:** echolocation can't estimate room size → Anna switches to surveyed fingerprints. No floor plan → trace the demo floor by hand from photos and tape measurements.
- **H8 (review at H16):** gesture false triggers dominate → simplify to a deliberate "motion trigger".
- **H18:** feature freeze. No new libraries, no redesigns.

---

## 8. Overnight agent on Anna's laptop (H8–H16)

The agent works only on hardware-free tasks, so Day 1 must leave it **data**:
sweep recordings with tape-measured room sizes, `rooms.json`, the floor walk,
labelled gesture trials, and one saved hub session.

```bash
git checkout -b night/agent
cp docs/NIGHT_QUEUE.template.md docs/NIGHT_QUEUE.md   # everyone adds their tasks
caffeinate -dims &
NIGHT_END="2026-11-08T07:00" scripts/night_agent.sh
```

The loop does one queue task per iteration: implement, `make test`, commit
with a `night:` prefix, tick the task, log to `docs/NIGHT_LOG.md`. It never
touches `main`, `firmware/`, dependencies or raw data, and marks tasks
`BLOCKED` or `NEEDS-HUMAN` instead of guessing. At H16 each owner reviews
`git log night/agent` for their folders and merges what passes.

---

## 9. Ground rules

- Your folder, your decisions. Touching someone else's folder: message them first.
- Merge small working steps to `main` often; never force-push `main`.
- Raw data stays out of git; copy it to the shared drive.
- Anything needed for the demo starts from the `Makefile`.
- Credentials and machine settings go in `.env` or `config/local.json` (git-ignored).
- Credit what we reuse (repos, libraries, floor plan source) in the README and on the final slide.
