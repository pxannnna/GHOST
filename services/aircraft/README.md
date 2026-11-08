Owner: Kameran, OPTIONAL stretch only after gestures work (plane sounds -> part of Edinburgh). See docs/KICKOFF.md §2 and §6. The owner decides how to build this.

Run everything below from this folder (`cd services/aircraft`). The repository's `.venv` works; a separate virtual environment is optional. This code lives here because docs/KICKOFF.md puts plane sounds in `services/aircraft/`.

# GHOST aircraft identification core

Experimental matching of aircraft Doppler predictions to audio spectrograms.
This is the identification code, without recordings, API credentials, generated
images or presentation-only heatmaps.

## Run

Requires Python 3.10+ and NumPy.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m aircraft_audio.identify --demo
```

## Identification method

For each candidate receiver and flight trajectory:

1. Convert geographic positions to WGS84 Earth-centred coordinates.
2. Solve emission time from `t_received = t_emitted + distance(t_emitted) / c`.
3. Calculate the received frequency factor `1 / (1 + range_rate / c)`.
4. Fit one constant emitted tone to the predicted curve on alternating training
   blocks. The curve cannot jump independently between bright frequency bins.
5. Score sustained spectral contrast and check the remaining time blocks.
6. Reject candidates that fail duration, curvature, support and negative-control
   checks. Constant-frequency and time-reversed curves are negative controls.

The example runner checks trajectory coverage, a maximum slant range and whether
the straight sound path intersects the Earth. It ranks aircraft/receiver pairs
by their training score; `accepted` is a separate heuristic consistency flag.

## Use recorded spectra

```bash
.venv/bin/python -m aircraft_audio.identify \
  --spectrum event.npz --flights flights.json --grid grid.json --output result.json
```

`event.npz` contains:

- `frequency`: uniformly spaced frequency centres, Hz, shape `[F]`.
- `times`: increasing FFT-window-centre times, seconds relative to `utc_start`, `[T]`.
- `db`: finite power spectrogram in dB, `[F,T]`.
- `utc_start`: scalar Unix UTC timestamp for the recording origin.

Use enough consecutive audio to show the curve (typically minutes). The included
scorer requires substantial frequency change and curvature; weak or incomplete
events may correctly produce no accepted result.

`flights.json` is an object mapping aircraft IDs to arrays of records:

```json
{"aircraft-id": [
  {"time_position": 1794110000, "latitude": 55.9, "longitude": -3.1, "altitude_m": 11000},
  {"time_position": 1794110005, "latitude": 55.901, "longitude": -3.11, "altitude_m": 11000}
]}
```

The snippet illustrates the schema; real trajectories need dense coverage of the
whole sound-emission interval. `altitude_m` must be **WGS84 ellipsoid height**.
Convert barometric/MSL heights before use. Large trajectory gaps are unsupported.
`grid.json` is an array such as `[[55.92,-3.18],[55.93,-3.17]]`. The default common
receiver height is 100 m; sound speed is 343 m/s and the range gate is 40 km.
These are assumptions exposed as Python function arguments, not measured values.

Call `aircraft_audio.identify.rank_candidates(...)` directly for application use.
Generate/refine a candidate grid externally and supply all relevant aircraft.

## Files

- `geometry.py`: coordinate transforms, trajectory models, retarded-time Doppler.
- `sustained_match.py`: fixed-shape scoring and validation controls.
- `model_score.py`: local spectral contrast and template helpers.
- `intensity_match.py`: frequency interpolation and brightness-based comparison.
- `detection.py`: optional audio-only tonal-ridge proposals, **not** aircraft IDs.
- `identify.py`: portable grid/aircraft ranking API and command-line example.

## Limits

This is a prototype, not a validated real-world geolocation system. Scores are
descriptive spectral contrast, not calibrated probabilities. The tests establish
synthetic behavior only. This export does not collect live ADS-B, capture audio,
perform an exhaustive UK search, jointly solve multiple events, estimate terrain
height or model wind/refraction/building transmission. It does not assume that a
bright ridge in the real recordings was necessarily produced by an aircraft.
Recording/trajectory UTC alignment and independently verified audio evidence are
essential before interpreting any location result.
