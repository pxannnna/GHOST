# Invisible Signals — kickoff plan

**HackTheBurgh 2026 · The Nucleus, King's Buildings · 4 people · 24 hours**
Pitch: *"Hear where you are. Feel which floor. Control the room with radio."*

This file is the single plan we follow. It merges the team spec (v1.0), the
dopplertrack methodology, the materials Kameran has, and the floor-pressure
survey we already took. Every person works with their own AI agent during the
day; Anna's laptop runs an unattended agent loop overnight on hardware-free
tasks. Read §2 (roles) and §5 (your block) first, then come back to the rest.

---

## 1. What we are building (one paragraph)

A laptop app with three views. **Sky:** a real aircraft Doppler signature from
the DJI mic, matched against real ADS-B tracks, producing a bounded Edinburgh
location estimate with its ambiguity shown honestly. **Building:** the
prepared Nucleus floor plan with the floor chosen by the phone barometer,
calibrated against our own survey. **Radio:** a live Wi-Fi CSI trace from the
XIAO ESP32C6; one deliberate double hand-sweep advances the view. Every sensor
has a mode badge (live / replay / simulated / configured) and nothing that is
configured is ever shown as measured.

Tracks: **G-Research** (invisible → visible) is the primary target. **HRT**
(signals → probabilistic estimate → decision) is the secondary pitch. The
physical "device" is the sensing rig: XIAO puck + marked gesture zone + mic
mount, built from Kameran's parts.

---

## 2. Roles (suggested; swap by real strength at minute 5)

| Letter | Person | Owns | Hardware in hand |
|---|---|---|---|
| **A — audio/DSP** | 4th teammate (strongest Python + numerics) | `services/aircraft/`, track archive, Doppler model, grid search | DJI Mic Mini receiver → laptop |
| **B — embedded/ML** | **Kameran** | `firmware/xiao/`, `services/wifi/`, gesture data + detector, the physical rig | XIAO ESP32C6, wires, soldering kit, hotspot phone |
| **C — integration/sensors** | **Jonathan** | `services/hub/`, `shared/`, `config/`, `services/pressure/`, floor logic, replay, runbook | Phone barometer app |
| **D — UI/demo + night-agent host** | **Anna** | `web/`, `assets/floorplans/`, pitch, backup video, overnight loop | Demo laptop |

Rules: each owner stubs their producer in the first hour so nobody waits on
hardware. Person C coordinates schema changes but does not fix other modules.
Nobody edits another owner's directory without a message.

---

## 3. Materials and how each is used

| Item | Use | Setup notes |
|---|---|---|
| **Seeed XIAO ESP32C6** ([PiHut](https://thepihut.com/products/seeed-xiao-esp32c6?variant=53972794442113)) | CSI receiver, USB-serial to laptop | Default is the onboard ceramic antenna; the board also has a U.FL socket if we need the external antenna. Flash with ESP-IDF 5.x + `esp-csi`. If we have **two** XIAOs, use `csi_send` + `csi_recv` (ESP-NOW) instead of the router example: no hotspot compatibility risk. |
| **Phone hotspot** (2.4 GHz) | CSI transmitter if only one XIAO | Disable hotspot sleep, keep plugged in, fixed position 2–3 m from the XIAO. Internet not required. |
| **DJI Mic Mini** | Aircraft audio into Laptop A | Turn **off** noise cancelling and low-cut; windscreen outdoors; record 48 kHz mono WAV; keep the raw file. |
| **Phone barometer app** | Pressure → floor | Prefer **phyphox** (free, iOS/Android): *Pressure* experiment → "Allow remote access" → laptop polls `http://<phone-ip>/get?pressure`. Fallback: any app that exports CSV, read by `services/pressure/`. |
| Wires, perfboard, soldering kit, 3D printer | The rig (§6) | Keep it small: a puck for the XIAO, a stand for the mic, a tape-marked gesture zone. |

### Floor survey (already measured, 7 Nov 2026)

| Floor | Reading (hPa) | Δ from floor 0 (Pa) | Relative height at 12 Pa/m |
|---|---|---|---|
| 0 | 1013.221 | 0 | 0.0 m |
| 1 | 1012.506 | 71.5 | 5.96 m |
| 2 | 1011.910 | 131.1 | 10.93 m |
| 3 | 1011.217 | 200.4 | 16.70 m |

Floor spacing is ~60–72 Pa (5–6 m), which is far above sensor noise (~1–3 Pa),
so classification is easy **once re-zeroed**. The absolute values will drift
with the weather over 24 h, so Person C re-zeroes at floor 0 before the demo
and only the deltas are reused. These values are in `config/default.json`
under `pressure.survey`.

---

## 4. What already exists in the repo (built before kickoff)

| Path | Status | Notes |
|---|---|---|
| `shared/schema.py` | done | Event envelope + payload models for every event type in the spec, plus `aircraft.tracks` and `replay.progress`. Validation rejects malformed payloads. |
| `shared/client.py` | done | `EventClient`: non-blocking queue, retries, never stalls acquisition. |
| `shared/config.py`, `config/default.json` | done | Search bounds, collection region, configured location, floor survey. Overrides go in `config/local.json` (git-ignored). |
| `services/hub/app.py` | done, untested | FastAPI hub: `POST /events`, `GET /state`, `WS /ws`, demo controls, gesture cooldown + calibration gating, session log at `data/sessions/<id>/events.jsonl`. |
| `services/hub/replay.py` | done, untested | Deterministic replay with `replay.progress` events. |
| `.venv/`, `requirements.txt` | done | Python 3.10 venv (spec says 3.11+; code is 3.10-compatible — don't use `match` or `tomllib`). |
| `services/aircraft/`, `services/wifi/`, `services/pressure/`, `services/mock/`, `web/`, `firmware/xiao/` | empty | Owners start here. |

First thing Person C does: `make hub` and `curl localhost:8000/health`.
First thing everyone does: run `tests/` once the mock producer exists.

---

## 5. Timeline: 8 h humans → 8 h agent → 8 h humans

Hours are relative to kickoff. **Day 1 (H0–H8)** ends with every sensor
either producing a real sample or a declared fallback, and a complete,
labelled data capture for the agent to work on. **Night (H8–H16)** the agent
loop improves hardware-free code. **Day 2 (H16–H24)** is integration,
held-out evaluation, rehearsal, submission.

### Day 1 — H0 to H8 (everyone present, each with an agent)

| Hour | A (audio) | B (Kameran, embedded) | C (Jonathan, integration) | D (Anna, UI/demo) | Checkpoint |
|---|---|---|---|---|---|
| **0–1** | Confirm DJI capture path on Laptop A (`services/aircraft/capture.py`, log capture-start UTC + sample count). Start airplanes.live logger **now** (`make aircraft-log`). Confirm rate limit/terms. | Flash `esp-csi` example to XIAO, confirm serial CSI frames appear. Fix hotspot in place. | `make hub`, health check. Publish schema (`shared/schema.py`) to the group. Install phyphox on the phone, confirm `GET /get?pressure` works from the laptop. | Vite+TS shell with three views and mode badges, driven by `GET /state` + `WS /ws`. Trace Nucleus floor outline as SVG (approximate, labelled). | **H1 meeting:** real sample or named blocker from all four. Decide one-XIAO (router) vs two-XIAO (ESP-NOW). |
| **1–3** | Go outside with Laptop A + DJI; record ≥30 min continuous, note location (GPS pin) and start UTC. Ideally catch a turboprop (Loganair/Eastern). | Stream CSI to `services/wifi/capture.py`, log raw to `data/`, send `wifi.features` at 10 Hz. Verify motion visibly changes the trace. | `services/pressure/phyphox_source.py` → `pressure.sample`. Re-zero at floor 0, walk floors 0→3 by stairs, log it. `services/mock/` producer emitting schema-correct events for all types (mode=simulated). | UI consumes mock events. Sky map (Leaflet/MapLibre), spectrogram canvas, pressure trace, CSI trace. Everything labelled "SIMULATED". | **H3 gate:** if no CSI, B does firmware/hotspot only; C+D continue with mock. |
| **3–6** | Spectrogram (40–1000 Hz, long FFTs). Find a ridge by eye; manual ridge selection is fine. Implement Doppler model (`doppler.py`): emission-time solve, slant range with `ground_height_m`, `f_r = f_s / (1 + ṙ/c)`. Overlay predicted curve at the **known** recording location. | Build the rig (§6). Collect **25 positive** double-sweep trials and **≥5 min negatives** (still, typing, walking past, single sweep). Label by trial in `data/gesture/`. | Floor classifier: median filter → relative height → nearest survey level with 0.6 m hysteresis + 3 s dwell → `floor.estimate`. Hub replay tested with a saved session. | Real streams replace mocks. Status badges show stale/offline correctly (unplug test). Floor highlight on SVG. | **H6 gate:** A has one real signature with predicted curve overlaid **or** switches to manual annotation / reference replay. C has live floor or declared configured-floor fallback. |
| **6–8** | Bounded grid search (`search.py`): 200 m grid over `search_bounds`, score curves, keep top-k regions, emit `location.estimate` with status rules. Save ground truth separately (`data/ground_truth.json`, not read by search). | Template/threshold detector v1 (`gesture.py`): two energy pulses, gap 0.25–1.2 s, quiet before, 2 s cooldown → `gesture.detected`. Test live on the rig. | Integration pass: all producers → hub → UI. `make` targets work. Write `docs/RUNBOOK.md` draft. | Gesture advances the real UI. Record first evidence screenshots. Draft pitch wording with claim limits. | **H8 handover:** everything committed on `main`; `data/` captures copied to a shared drive; `docs/NIGHT_QUEUE.md` filled in; agent loop started on Anna's laptop. |

### Night — H8 to H16 (agent loop; one person on call by phone)

The agent cannot touch hardware, so the day must leave it: real audio WAVs
with ground truth, the ADS-B archive, labelled CSI trials, the floor walk log,
and one saved hub session. Tasks are in `docs/NIGHT_QUEUE.md`, ordered by
value. The loop is described in §7.

Priority order for the agent:
1. `tests/` for schema, hub, replay, Doppler model (synthetic track → known curve).
2. Aircraft: automatic ridge extraction, timing-offset fit within bounds, two-event locked scoring (dopplertrack method), evaluation script that reports distance error against `data/ground_truth.json` **without reading it during search**.
3. Gesture: train/validate a simple classifier (features → logistic regression or template matching) on `data/gesture/` with trial-level splits; write results to `docs/RESULTS.md`.
4. UI polish: replay banner, event history panel, candidate-region rendering, keyboard shortcuts.
5. `README.md`, `docs/RUNBOOK.md`, `docs/RESULTS.md`, acknowledgements and licences.
6. Replay fixture: a compact permitted session under `data/fixtures/` for the demo.

### Day 2 — H16 to H24

| Hour | A | B | C | D | Checkpoint |
|---|---|---|---|---|---|
| **16–17** | Review agent branch `night/agent`: run tests, read `docs/NIGHT_LOG.md`, merge what passes. | Same for gesture work. | Same for hub/replay/pressure. Restart the full stack from `make` targets only. | Same for UI. | Merge decisions made; nothing half-merged. |
| **17–19** | **Held-out** acoustic evaluation on a clip not used for tuning; record distance error + competing fits. If possible, one more outdoor capture. | Held-out gesture trials (10 attempts, second person) + 5-minute negative trial. Record 8/10 and false-positive counts. | Held-out floor visits after re-zero; record outcomes. Disconnect/reconnect each sensor; no duplicate advance. | Verify every display against logs. Build the pitch deck (6 slides max). | **H18 feature freeze.** |
| **19–21** | Fix only acquisition/correctness bugs. | Tune cooldown/thresholds only. | Packaging, `README` setup, restart rehearsal on the demo laptop. | Record backup video of the real system (replay parts labelled). | Complete restart from written commands succeeds. |
| **21–23** | Support rehearsal | Support rehearsal | Submission text, results sheet | Final rehearsal ×3, timing under 2 min | No dependency changes. |
| **23–24** | Buffer | Buffer | Submit | Submit | Submitted before deadline. |

---

## 6. The physical rig (Kameran, H3–H6, ~2 h)

Keep it tangible but small; the spec excludes sonar, people-tracking and 3D.

1. **CSI puck.** XIAO on a small perfboard inside a 3D-printed puck (~50 mm),
   USB-C cable out the side, a status LED on the top (GPIO → LED via 220 Ω)
   that blinks on each CSI frame and holds solid when a gesture fires. Mount
   at fixed height on a printed stand so orientation never changes after
   calibration.
2. **Transmitter stand.** A printed cradle that holds the hotspot phone (or
   the second XIAO) 2–3 m away at the same height, taped to the table.
3. **Gesture zone.** Tape a 40 × 40 cm square on the table between puck and
   transmitter, slightly toward the puck. Judges put their hand here.
4. **Mic mount.** A printed clip for the DJI Mic Mini with windscreen, for
   the outdoor captures and the table demo.
5. **Optional, only if everything else works by H6:** a printed "floor
   indicator" — four LEDs in a column driven by the laptop over the XIAO's
   serial, lighting the detected floor. It is a nice physical echo of the UI.

Print files go in `assets/hardware/`; a photo and wiring sketch go in
`docs/RUNBOOK.md`.

---

## 7. Overnight agent loop on Anna's laptop (H8–H16)

**Principle:** the agent works only on hardware-free tasks, on its own branch,
with tests as the acceptance gate, and leaves a log a human can audit in ten
minutes. It never touches `main`, `data/` raw captures, dependency versions
or anything under `firmware/`.

Setup at H8 (10 minutes):

```bash
git checkout -b night/agent
cp docs/NIGHT_QUEUE.template.md docs/NIGHT_QUEUE.md   # then fill in specifics
caffeinate -dims &                                    # keep the Mac awake
scripts/night_agent.sh                                # see script header
```

`scripts/night_agent.sh` runs `claude -p` in a loop. Each iteration gets the
same prompt: read `docs/NIGHT_QUEUE.md`, pick the first unchecked task, do it,
run `make test`, commit on `night/agent` with a message starting `night:`,
tick the task and append a 3-line entry to `docs/NIGHT_LOG.md`. If tests fail
twice on the same task it marks it `BLOCKED` with the reason and moves on.
A task that needs hardware, credentials or a human decision is marked
`NEEDS-HUMAN`. The loop stops at the time in `NIGHT_END` or when the queue is
empty.

What to leave it (checked at H8):
- `data/audio/*.wav` + `data/audio/*.json` (start UTC, location, device)
- `data/adsb/*.jsonl` (the archive from `make aircraft-log`)
- `data/ground_truth.json` (recording positions; search code must not open it)
- `data/gesture/trials.jsonl` (labelled CSI windows, trial IDs)
- `data/pressure/floor_walk.jsonl`
- `data/sessions/session-001/events.jsonl`

Morning review (H16, 30 min): `git log night/agent`, `make test`, read
`NIGHT_LOG.md`, cherry-pick or merge. Anything the agent marked `BLOCKED`
becomes a human task for Day 2.

---

## 8. Commands (owners implement; keep these names)

```
make hub              # C   uvicorn hub on :8000, SESSION_ID env selects the log
make web              # D   vite dev server on :5173
make mock             # C   all-type simulated producer for UI development
make aircraft-log     # A   airplanes.live archiver (start at H0, never stop)
make audio-live       # A   DJI capture + spectrogram + signature events
make audio-analyse WAV=... # A  offline pipeline on a recording
make wifi-live        # B   XIAO serial → features + gesture events
make pressure-live    # B/C phyphox poll → pressure + floor events
make replay SESSION=session-001
make test             # all   pytest tests/
```

---

## 9. Hard gates (do not argue with these at 3 am)

- **H1** no real sample from a sensor → its owner names the blocker in chat and stubs the producer.
- **H3** no CSI → Kameran works only on firmware/hotspot (or switches to two-XIAO ESP-NOW).
- **H6** no usable aircraft tone → A goes manual ridge + known-location overlay, or labelled reference replay.
- **H6** no phone pressure stream → configured floor, labelled; C moves to integration.
- **H8** handover is a hard stop: commit, copy data, start the loop, go to sleep.
- **H18** feature freeze.
- Never: show configured/replay as measured; turn a score into a percentage; add gesture classes; search outside the Edinburgh box; modify university networking.

---

## 10. Claim wording for the pitch (D owns, everyone obeys)

- "We **estimate** location from aircraft Doppler, bounded to Edinburgh; this run was **[live / replay]** and landed **X m** from ground truth with **N** competing regions."
- "The floor is from a phone barometer **calibrated against our survey**; absolute floors need a reference."
- "The gesture is a **deliberate double sweep** recognised from Wi-Fi CSI; held-out result **8/10**, **k** false triggers in 5 min."
- "The floor plan is a **prepared asset**, not inferred."

Acknowledge: colsto's video, `mjshiggins/dopplertrack`,
`AlanBacker/audio-flyover-geolocation`, Espressif `esp-csi`, airplanes.live.
