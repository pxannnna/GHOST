Owner: Anna (echolocation: sweeps, impulse response, room matching). See docs/KICKOFF.md §2 and §6.

# Echolocation → which room (Plan B: physics vs the floor plan)

```
phone barometer ──► floor (services/pressure)
                        │  only rooms on this floor
Mac speaker ─ sweep ─► DJI mic ─► impulse response ─► RT60 + reflections ─► match.py ─► room.estimate
                                                                              ▲
                                       assets/building/rooms.json (floor plan)┘
```

| File | What |
|---|---|
| `sweep.py` | Exponential sine sweep, deconvolution, alignment on the direct sound (the DJI is wireless: latency is unknown and varies) |
| `features.py` | RT60 (Schroeder, 500/1k/2k Hz, direct sound excluded), early reflections (spreading-compensated) |
| `audio_io.py` | Play on Mac speakers, record on the DJI, devices picked by name |
| `measure.py` | One position: N sweeps → IR → features → `data/echo/…` + `acoustic.measurement` |
| `match.py` | Predict each room's RT60 / ceiling / nearest wall from `rooms.json`, score, rank, status |
| `live.py` | Floor from the hub + positions → `room.estimate` after every position |
| `rooms.py`, `build_rooms.py` | Room geometry; builds `rooms.json` from the PDF trace + on-site measurements |
| `simulate.py` | Image-source + diffuse-tail simulator for tests and `--simulate` (mode = simulated) |

## How the match works (what we can claim)
Per room on the measured floor, three terms (squared z-scores → `score = exp(-cost/2)`, not a probability):
1. **RT60** vs Eyring's prediction from the room's volume/surface and an absorption per room kind.
2. **Ceiling height**: a reflection distance that repeats at every position is the ceiling (walls change, the ceiling doesn't). Compared with the room's ceiling height/range.
3. **Nearest wall**: the first lateral echo per position vs nearest-wall distances predicted from the room *polygon*.

Status: `listening` (nothing yet) → `candidate` (1 position, or floor not settled) → `supported` / `ambiguous` (top two close) / `no_match`.

Known limits (found in simulation, check on real data):
- In flat rooms RT60 barely depends on floor area (V/S ≈ H/2), so **Rowan vs Hawthorn** (both ~4 m high) are hard; measured ceiling heights and the wall term separate them. Expect `ambiguous` there.
- Wall-to-wall **spans** (pair-sums of echoes) are computed but **not scored** (`matching.use_spans: false`): unreliable in simulation. Turn on only if real data supports it.
- The estimated length/width is rough (RT60-based); the floor-area min/max range is reported alongside.

## Day-1 protocol
1. DJI: noise cancelling **off**, low-cut **off**; receiver in the Mac. Mac: Mic Mode **Standard**, volume fixed (note the level).
   `python -m services.acoustics.measure --list-devices` → names in `config/local.json` if they differ from `"DJI"` / `"MacBook Pro Speakers"`.
2. Laptop on a table, DJI clipped **~10 cm** from the speaker grille (set `speaker_mic_m`), table height → `--mic-height`.
3. **≥1 m from walls**, 3–4 positions spread across the room, nobody moving within 1 m.
4. Check one sweep: `make echo-measure ROOM=nuc-2-rowan POS=P1` → RT60 should be 0.4–2 s, SNR > 40 dB, no CLIPPED warning.
5. Live: `make pressure-live` (other terminal) then `make room-live`; Enter at each position.
6. For validation always pass `--room <room_id>` so recordings are labelled (the matcher never sees it).

Simulated demo without hardware: `python -m services.acoustics.live --simulate nuc-2-yew --floor 2 --auto 4`.
