# Night agent queue

Copy to `docs/NIGHT_QUEUE.md` at H8. **Each owner writes their own tasks**:
specific, hardware-free, testable. The agent takes the first unchecked task in
the "Interleaved order" list, so put everyone's most important task near the
top.

The agent finishes one task per iteration, runs `make test`, commits on
`night/agent`, ticks the box, and logs to `docs/NIGHT_LOG.md`. Tasks that
need hardware or a decision become `NEEDS-HUMAN`; tasks that fail tests twice
become `BLOCKED: <reason>`.

## Constraints (never violated)
- Branch `night/agent` only. Never touch `main`, `firmware/`, `requirements.txt`, raw files in `data/`.
- Python 3.10 compatible. No new dependencies unless a task explicitly allows it.
- Room matching never reads the tape-measured ground truth (`data/rooms_ground_truth.json`); only an evaluation script may.
- Stay inside the owner's folders listed in `docs/KICKOFF.md` §2 for each task.
- Never present configured, replay or simulated data without its mode badge.

## Data available (fill in at H8)
- Echolocation: `data/echo/<<...>>` (sweeps per room/position), ground truth `data/rooms_ground_truth.json`
- Floor plan: `assets/building/rooms.json`
- Floor walk: `data/pressure/<<...>>`
- CSI + gesture trials: `data/csi/<<...>>`, `data/gesture/<<...>>`
- Hub session: `data/sessions/<<...>>/events.jsonl`

## Interleaved order (the agent follows this list)
- [ ] T01 <<highest-priority task, any owner>>
- [ ] T02 <<...>>
- [ ] T03 <<...>>

## Task ideas per owner (copy the ones you want into the list above)

**Anna (room finding + 3D):** robust RT60 (Schroeder) and early-reflection extraction with tests on synthetic impulse responses; predicted features per room from `rooms.json` (Sabine or `pyroomacoustics` if allowed); scoring and ranking with an evaluation script against ground truth; floor classifier tests on the recorded walk; 3D model polish (labels, camera fly-to on `setRoomCandidates`).

**Kameran + Elisa (gestures):** classifier trained with trial-level splits and a held-out report; offline replay of all trials through the detector to tune thresholds and cooldown; false-trigger analysis on negatives; tests for the CSI parser and MAC filter.

**Shangran (website + hub):** replay banner and progress; event history panel; stale/offline styling; room-candidate list with scores; keyboard shortcuts; projector layout; hub tests (dedup, cooldown, calibration gating); compact replay fixture in `data/fixtures/`; README and `docs/RUNBOOK.md`.
