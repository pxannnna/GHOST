# Night agent queue

Copy to `docs/NIGHT_QUEUE.md` at H8. **Each owner writes their own tasks** in
their section: specific, hardware-free, testable, and in priority order.
The agent takes the first unchecked task from top to bottom, so put the most
important tasks from each person near the top of the "Interleaved order" list.

The agent finishes one task per iteration, runs `make test`, commits on
`night/agent`, ticks the box, and logs to `docs/NIGHT_LOG.md`. Tasks that
need hardware or a decision become `NEEDS-HUMAN`; tasks that fail tests twice
become `BLOCKED: <reason>`.

## Constraints (never violated)
- Branch `night/agent` only. Never touch `main`, `firmware/`, `requirements.txt`, raw files in `data/`.
- Python 3.10 compatible. No new dependencies unless a task explicitly allows it.
- Aircraft search code never reads `data/ground_truth.json`; only an evaluation script may.
- Stay inside the owner's folders listed in `docs/KICKOFF.md` §2 for each task.
- Never present configured, replay or simulated data without its mode badge.

## Data available (fill in at H8)
- Aircraft: `data/audio/<<...>>`, ADS-B `data/adsb/<<...>>`, ground truth `data/ground_truth.json`
- CSI + gesture trials: `data/csi/<<...>>`, `data/gesture/<<...>>`
- Floor walk: `data/pressure/<<...>>`
- Hub session: `data/sessions/<<...>>/events.jsonl`

## Interleaved order (the agent follows this list)
- [ ] T01 <<highest-priority task, any owner>>
- [ ] T02 <<...>>
- [ ] T03 <<...>>

## Task ideas per owner (copy the ones you want into the list above)

**Kameran (aircraft):** automatic ridge extraction; bounded timing-offset fit; locked two-event scoring; blind evaluation script writing distance error and competing regions to `docs/RESULTS.md`; unit test of the Doppler model on a synthetic track.

**Anna (3D + gesture):** gesture classifier trained with trial-level splits and held-out report; offline replay of trials through the detector to tune cooldown/thresholds; 3D model polish (floor labels, camera fly-to on `setFloor`).

**Elisa (website):** replay banner and progress; event history panel; candidate regions on the map; stale/offline styling; keyboard shortcuts; responsive layout for the projector.

**Shangran (hub/floor):** tests for schema, hub dedup/cooldown/calibration gating, floor classifier on the recorded walk; compact replay fixture in `data/fixtures/`; `README` and `docs/RUNBOOK.md`.
