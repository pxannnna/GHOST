# Invisible Signals (HackTheBurgh 2026)

*Hear where you are. Feel which floor. Control the room with radio.*

**Start here:** [`docs/KICKOFF.md`](docs/KICKOFF.md) has the plan, roles, timeline and gates.

| Role | Person | Folders |
|---|---|---|
| A: aircraft audio | Elisa | `services/aircraft/` |
| B: XIAO + Wi-Fi gesture + rig | Kameran | `firmware/xiao/`, `services/wifi/`, `assets/hardware/` |
| C: hub, schema, pressure/floor | Shangran | `services/hub/`, `shared/`, `config/`, `services/pressure/`, `services/mock/` |
| D: UI, demo, night agent | Anna | `web/`, `assets/floorplans/`, `docs/` |

## Setup

```bash
git clone <repo-url> && cd invisible-signals
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make hub        # event hub on http://127.0.0.1:8000  (check /health)
```

Machine-specific settings (serial ports, phone IP) go in `config/local.json`, which is git-ignored.
Raw recordings go in `data/` (git-ignored); copy them to the shared drive at H8.

## Git rules
- Work on your branch: `audio`, `wifi`, `hub-pressure`, `ui`. Merge small changes to `main` often via PR.
- Never force-push `main`. Changes to `shared/schema.py` go through Shangran.
- No credentials in git.
