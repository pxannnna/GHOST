Owner: Anna (barometer -> floor). See docs/KICKOFF.md §2 and §6.

# Barometer -> floor

Floors used: **0 = G, 1, 2, 3** (survey in `config/default.json`, 7 Nov 2026, taken with a phone). LG is off limits and not modelled.

## With the USB board (default): the pressure is read by the laptop
A flight-controller board with a barometer (tested: StingBee StellarH7V2, already running ArduPilot, no flashing needed)
is plugged into the laptop. It shows up as a USB serial port; `board.py` finds it by its USB name (the port number changes
every time it is replugged), asks it for the pressure message at 5 Hz and reads it. The request is temporary and resets
when the board is unplugged.

1. Plug the board in. Check it works: `.venv/bin/python -m services.pressure.board` prints readings for 10 s
   (expect about 1000-1020 hPa and noise well under 1 Pa).
2. **Re-survey the floors with this board** (different sensors differ slightly in scale):
   `make pressure-survey`. Carry the laptop with the board plugged in, stand still on each floor when asked
   (G, 1, 2, 3, 2, 1, G, 20 s each). Going up and back down cancels slow weather drift. The result goes into
   `config/local.json` (git-ignored) and overrides the committed phone survey.
3. Stand on G: `make pressure-live` then type `z` + Enter (or start with `--zero-floor 0`). Walk; the terminal prints floor
   changes and the hub receives `pressure.sample` + `floor.estimate`.

## Testing on different floors: telling the program where you really are
- **Survey (`make pressure-survey`)** asks for each floor by name; you answer by pressing Enter on that floor.
- **A live test walk:** run `make pressure-live`, zero on G with `z`, then at each floor stand still until the printed
  floor settles and type `t0`, `t1`, `t2` or `t3` + Enter (the floor you are really on). Every reading is logged to
  `data/pressure/walks/walk_<time>.csv` with that label. Type `q` at the end: it prints how often the detector had the
  right floor. Re-score any walk later with `python -m services.pressure.walkscore [file]`.
- Echo tests are told the floor with `--floor N` (`services.acoustics.live --floor 3 --room <label>`).

Notes: let the board warm up a few minutes before zeroing; keep it out of draughts (drone boards usually have foam over the
barometer); it must be on the same floor as the laptop, so carry them together. Readings that pile up in the USB buffer
while nothing is reading are discarded when the board connects and before each survey recording.

## With the phone (alternative)
phyphox -> **Pressure** experiment -> menu -> Allow remote access, then
`config/local.json`: `{"pressure": {"phone_url": "http://<phone-ip>:8080"}}` (iOS: no `:8080`) and run with
`python -m services.pressure.live --source phyphox`. Phone and laptop must be on the same network.
CSV fallback: `python -m services.pressure.live --csv walk.csv --zero-floor 0` (mode = replay).

## How the floor is chosen
Only pressure *differences* are used: we zero on a known floor and compare with the surveyed per-floor differences
(60-70 Pa apart). Weather moves absolute pressure by about 100 Pa a day, so **re-zero before the demo**.
Motion (stairs/lift) is detected from vertical speed -> status `transition`; `uncertain` when more than 1.5 m from any floor.
