# Echolocation plots: 3rd-floor study room

Real recordings (MacBook speakers + built-in mic, laptop on a chair at 0.45 m), 4 positions, 3 sweeps each, 7 Nov 2026.
Ceiling 2.45-2.5 m (taped). Regenerate with `python -m services.acoustics.plot --room nuc-3-studyroom`
(needs the recordings in `data/echo/`, which are not in git).

| File | Shows |
|---|---|
| `1_recording.png` | What the microphone heard during one sweep: the chirp rising 200 Hz to 20 kHz. The faint parallel lines above it are the small speaker's own distortion (discarded); the haze below is the room ringing on. |
| `2_echo_traces.png` | One echo trace per position: loudness against distance to the reflecting surface. Dashed line = where the ceiling echo should be (ceiling height minus mic height = 2.05 m). Dots = echoes the tool picked. Beyond ~1 m the trace is mostly noise with small bumps: no clean separate echoes in a room this small. |
| `3_agreement.png` | Positions stacked. A vertical stripe = an echo at the same distance from every position, which is what a ceiling does (walls move). All four positions agree at 2.04 m (matches the expected ceiling echo) and 2.20 m (unexplained, possibly the laptop's own screen). |
| `4_decay.png` | How fast the sound dies away (reverberation, 1 kHz band). The four curves nearly coincide, so the measurement is repeatable. The sharp drop at the end is where background noise is reached. |

## What this does and does not show
- Ceiling height estimated from the repeated echo: 2.45-2.48 m against 2.45-2.5 m taped.
- One small room only. The detector thresholds were adjusted after seeing this data, so this is **not** an independent test.
- Wall distances and room length/width are **not** validated by these recordings.
