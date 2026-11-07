# GHOST (HackTheBurgh 2026)

**G**athering **H**idden **O**bservations from **S**ound & **T**ransmissions

*Hear where you are. Feel which floor. Control the room with radio.*

A laptop works out which room of the Nucleus it is in, from a phone barometer
(floor) and echolocation (room size, matched against the floor plan), shown in
a 3D model. The talk's slides change with a hand gesture sensed through Wi-Fi.

**Start here:** [`docs/KICKOFF.md`](docs/KICKOFF.md) has the plan, interfaces, deadlines and gates.

| Person | Owns | Branch | Folders |
|---|---|---|---|
| Anna | Echolocation, barometer floor, room matching, 3D Nucleus model, night agent | `room-location` | `services/acoustics/`, `services/pressure/`, `web/building3d/`, `assets/building/` |
| Kameran + Elisa | Wi-Fi gestures: XIAO firmware, wiring, CSI stream, gesture detection | `wifi-gesture` | `firmware/xiao/`, `services/wifi/` |
| Shangran | Website (slides + dashboard) and the event hub | `website` | `web/`, `services/hub/`, `shared/`, `services/mock/` |
| Kameran (optional) | Plane sounds → which part of Edinburgh | `plane-location` | `services/aircraft/` |

## Setup

```bash
git clone https://github.com/pxannnna/GHOST.git && cd GHOST
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make hub        # event hub on http://127.0.0.1:8000  (check /health)
git checkout <your branch>
```

Then give your AI agent `docs/KICKOFF.md` and tell it which person you are.

Machine-specific settings (serial ports, phone IP, transmitter MAC) go in `config/local.json`, which is git-ignored.
Raw recordings go in `data/` (git-ignored); copy them to the shared drive at H8.

## Git rules
- Work on your branch; merge small working steps to `main` often.
- Never force-push `main`. Changes to `shared/schema.py` go through Shangran.
- No credentials in git.
