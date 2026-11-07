# Night agent queue

Copy to `docs/NIGHT_QUEUE.md` at H8 and fill in the specifics marked `<<...>>`.
The agent takes the first unchecked task, finishes it, runs `make test`,
commits on `night/agent`, ticks the box, and logs to `docs/NIGHT_LOG.md`.
Tasks that need hardware or a decision get marked `NEEDS-HUMAN`; tasks that
fail tests twice get `BLOCKED: <reason>`.

## Constraints (never violated)
- Branch `night/agent` only. Never touch `main`, `firmware/`, `requirements.txt`, raw files in `data/`.
- Python 3.10 compatible. No new dependencies.
- `services/aircraft/search.py` must never read `data/ground_truth.json`; only `scripts/evaluate_location.py` may.
- UI never shows configured/replay/simulated data without the mode badge.

## Available data (filled at H8)
- Audio: `<<data/audio/....wav>>`, start UTC `<<...>>`, recorded at `<<lat, lon>>` (also in ground_truth.json)
- ADS-B archive: `data/adsb/<<...>>.jsonl`
- Gesture trials: `data/gesture/trials.jsonl` (`<<N>>` positives, `<<M>>` min negatives)
- Floor walk: `data/pressure/floor_walk.jsonl`
- Hub session: `data/sessions/session-001/events.jsonl`

## Tasks (in priority order)

- [ ] T01 tests: `tests/test_schema.py` covering every payload type (valid + one invalid each).
- [ ] T02 tests: `tests/test_hub.py` using FastAPI TestClient: accept, reject malformed, dedup, gesture cooldown, calibration gating.
- [ ] T03 tests: `tests/test_doppler.py` — synthetic straight-line track at known altitude/speed, assert predicted curve matches closed form; assert emission-time solve converges.
- [ ] T04 aircraft: automatic ridge extraction in `services/aircraft/ridge.py` (stationary-background subtraction, coherent ridge tracking); run on the real WAV, save `data/derived/ridges.json`, plot to `docs/figures/`.
- [ ] T05 aircraft: timing-offset fit bounded by `acoustics.timing_offset_bounds_s`, shared across events; source-frequency fit per event.
- [ ] T06 aircraft: two-event locked scoring (dopplertrack method) in `search.py`; keep top-10 regions; emit `location.estimate` with `ambiguous` when top regions are >1 km apart.
- [ ] T07 aircraft: `scripts/evaluate_location.py` → distance error vs ground truth, competing fits table, written to `docs/RESULTS.md`.
- [ ] T08 gesture: `services/wifi/train.py` — features (normalised subcarrier variance, temporal diff energy, envelope shape) → logistic regression; trial-level split; report held-out recall/false positives to `docs/RESULTS.md`; save `model_version=double-sweep-v2`.
- [ ] T09 gesture: offline replay of `trials.jsonl` through the detector, confirm one event per positive, ≤1 false trigger over negatives; tune cooldown.
- [ ] T10 pressure: `tests/test_floor.py` on `floor_walk.jsonl` — settled floors classified, transitions flagged; hysteresis behaviour.
- [ ] T11 UI: replay banner + replay progress; event history panel; candidate regions drawn as circles with fit score; keyboard `n`/`1`/`2`/`3`.
- [ ] T12 UI: stale/offline styling verified against `source.status`; data-age counters.
- [ ] T13 replay fixture: compact `data/fixtures/demo-session.jsonl` (≤2 MB) that drives all three views; `make replay SESSION=fixtures/demo-session` works.
- [ ] T14 docs: `README.md` (setup, hardware connections, firmware versions, commands, calibration, modes), `docs/RUNBOOK.md`, acknowledgements with licences.
- [ ] T15 docs: `docs/RESULTS.md` consolidated: what each sensor measured, inferred, configured; known failures.
