# GHOST (HackTheBurgh 2026)

**G**athering **H**idden **O**bservations from **S**ound & **T**ransmissions

*Hear where you are. Feel which floor. Control the room with radio.*

**Start here:** [`docs/KICKOFF.md`](docs/KICKOFF.md) has the plan, interfaces, deadlines and gates.

| Person | Owns | Branch | Folders |
|---|---|---|---|
| Kameran | Plane sounds → location | `audio` | `services/aircraft/` |
| Anna | 3D Nucleus model, gesture recognition, night agent | `building-3d`, `gesture` | `web/building3d/`, `assets/building/`, `services/wifi/` |
| Elisa | Website: slides + live dashboard; helps with gestures | `web` | `web/` |
| Shangran | Hub, schema, XIAO bring-up, barometer floor, integration, rig | `hub` | `services/hub/`, `shared/`, `config/`, `services/pressure/`, `services/mock/`, `firmware/xiao/`, `assets/hardware/` |

## Setup

```bash
git clone https://github.com/pxannnna/invisible-signals.git && cd invisible-signals
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make hub        # event hub on http://127.0.0.1:8000  (check /health)
git checkout <your branch>
```

Then give your AI agent `docs/KICKOFF.md` and tell it which person you are.

Machine-specific settings (serial ports, phone IP) go in `config/local.json`, which is git-ignored.
Raw recordings go in `data/` (git-ignored); copy them to the shared drive at H8.

## Git rules
- Work on your branch; merge small working steps to `main` often via PR.
- Never force-push `main`. Changes to `shared/schema.py` go through Shangran.
- No credentials in git.
