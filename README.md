# GHOST (HackTheBurgh 2026)

**G**athering **H**idden **O**bservations from **S**ound & **T**ransmissions

*Hear where you are. Feel which floor. Control the room with radio.*

## What it does

GHOST works out **where a device is inside a building using only signals nobody can see**: no cameras, no GPS, no
wearables.

1. **Which floor?** A barometer reads the air pressure. Pressure falls as you go up, and the four floors of the Nucleus
   sit about 61-75 Pa apart, so we can tell them apart after zeroing once on the ground floor.
2. **Which room?** The device plays a short sonar-style chirp through its speaker and records the echoes. The echo delays
   give the distance to the ceiling, and how long the sound lingers hints at the room's size. We match that against the
   building's floor plan and rank the rooms on that floor.
3. **A call for help, or a gesture.** A small Wi-Fi sensor feels the radio waves bouncing around the room and picks up one
   deliberate hand gesture. In the demo it changes the slide; it stands in for a silent call for help.
4. **Optional stretch:** the sound of planes overhead, matched to flight data, to narrow down the area of Edinburgh.

Everything is shown on a web dashboard with a 3D model of the Nucleus. The result is a **floor and a short ranked list of
likely rooms**, not a pinpoint.

## Why it is useful

### In an emergency
- Someone who has fallen or is in trouble may not be able to say where they are. Indoors, GPS cannot tell floor 3 from the
  ground floor, and responders lose minutes searching a large building.
- Cameras everywhere would solve it, but nobody wants cameras in study rooms, bedrooms or changing rooms.
- GHOST narrows a call for help to **a floor and a short list of rooms**, using air pressure, echoes and Wi-Fi, none of which
  record images or conversations.
- The Wi-Fi part today senses a **deliberate gesture** as a silent call for help. **Automatic fall detection is a future
  step, not something we have built or tested.**

### Saving electricity and heating (a possible use, not built or measured)
- Large buildings usually heat, ventilate and light by schedule or by whole zones, whether or not a room is in use.
- Knowing which floors and rooms are actually in use would let a building system lower the heating and lighting in the empty
  ones. Because GHOST uses no cameras, it avoids the privacy objections that block many occupancy-sensing schemes.
- To get there we would need reliable room-level presence sensing (the Wi-Fi sensing part, one sensor per room), a link to
  the building management system, and a **measured** saving. We make no claim about how much would be saved.

## What works today, and what does not

| Part | Status |
|---|---|
| Floor from pressure | Surveyed all four floors with a USB barometer board (61-75 Pa apart). Built from the way up only, the way back down classified 3 of 3 floors correctly (0.1-0.3 m off). **Not yet tested live while walking between floors.** |
| Room from echoes | Tested in **one real room** (3rd-floor study room, 4 positions): ceiling height 2.45 m from the echoes against 2.45-2.5 m taped, and the right room ranked first. That floor has only two rooms in our plan, and the detector settings were adjusted on this data, so it is **not an independent test**. |
| Known limits | Walls more than about 4 m away are not detected. Room length and width from reverberation are unreliable, and the one recording in a large room picked the wrong room. Raked or bleacher floors (for example Oak, Elm and Yew) are not modelled. |
| Wi-Fi gesture | A deliberate gesture near the sensor. We do not claim tracking people, counting people or body pose. |
| Plane sounds | A prototype in `services/aircraft/`, tested on synthetic data only. |
| Simulated data | Always labelled **simulated**. Every panel shows a mode badge: live, replay, simulated or configured. |

## How it works

```
USB barometer ──► floor (services/pressure) ───────────────┐
                                                           ▼
device chirp ─► echoes ─► ceiling + reverberation ─► match vs floor plan ─► ranked rooms ─► event hub ─► dashboard + 3D model
(services/acoustics)       (assets/building/rooms.json)                       ▲
Wi-Fi sensor ─► gesture (services/wifi) ───────────────────────────────────┘
```

The floor plan, the room list and the measured ceiling heights are in `assets/building/`. Details of each part are in the
README inside its folder.

## Team and folders

| Person | Owns | Branch | Folders |
|---|---|---|---|
| Anna | Echolocation, barometer floor, room matching, 3D Nucleus model, night agent | `room-location` | `services/acoustics/`, `services/pressure/`, `web/building3d/`, `assets/building/` |
| Kameran + Elisa | Wi-Fi gestures: XIAO firmware, wiring, CSI stream, gesture detection | `wifi-gesture` | `firmware/xiao/`, `services/wifi/` |
| Shangran | Website (slides + dashboard) and the event hub | `website` | `web/`, `services/hub/`, `shared/`, `services/mock/` |
| Kameran (optional) | Plane sounds → which part of Edinburgh | `plane-location` | `services/aircraft/` |

**Start here:** [`docs/KICKOFF.md`](docs/KICKOFF.md) has the plan, interfaces, deadlines and gates.

## Setup

```bash
git clone https://github.com/pxannnna/GHOST.git && cd GHOST
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Python 3.11+ (3.12 tested; 3.10.0 breaks the latest pytest)
make test       # all tests should pass
make mock       # simulated events (terminal 1)
make web        # dashboard at http://127.0.0.1:8000/?mock=1 (terminal 2)
git checkout <your branch>
```

Real hardware:

```bash
make pressure-survey   # once per building: stand on each floor when asked
make pressure-live     # barometer board on USB -> floor (type z on the ground floor to zero)
make room-live         # floor + echoes -> ranked rooms (python -m services.acoustics.live --help)
```

Then give your AI agent `docs/KICKOFF.md` and tell it which person you are.

Machine-specific settings (serial ports, phone IP, transmitter MAC, audio devices) go in `config/local.json`, which is git-ignored.
Raw recordings go in `data/` (git-ignored); copy them to the shared drive.

## Git rules
- Work on your branch; merge small working steps to `main` often.
- Never force-push `main`. Changes to `shared/schema.py` go through Shangran.
- No credentials in git.

## Credits
- Floor plans: University of Edinburgh, *Nucleus floor plans* and *Nucleus Sensory Map* (public PDFs).
- Barometer board: StingBee StellarH7V2 running [ArduPilot](https://ardupilot.org), read over MAVLink with `pymavlink`.
- 3D view: three.js (see `web/vendor/three/LICENSE`).
