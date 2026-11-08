# SIMULATED rooms: what the echo method should look like elsewhere

**Everything in this folder is computer-generated, not measured.** Every picture carries a
"SIMULATED DATA" banner. The recordings behind it are in `data/echo/sim-<room>/` (git-ignored) and
are marked `"mode": "simulated"`. Regenerate with `python -m services.acoustics.sim_gallery`.

## What this is for, and what it is not
- **For:** showing what the echo traces, the "same distance at every position" view and the decay
  curves look like for other kinds of room, with the true wall and ceiling positions marked
  (triangles), which we can only know because it is a simulation.
- **Not:** evidence that the method works in these rooms. The simulation and the matcher use the same
  physics, so some success is built in. Only measurements in the real rooms can show that.

## How the simulation was made realistic
A first, clean simulation (crisp echoes, no clutter) looked nothing like the real study-room recordings,
so `simulate.field_ir` was calibrated against them (7 Nov 2026, 4 positions, laptop at 0.45 m):

| Property | Real study room | Simulation |
|---|---|---|
| Median echo level vs direct sound at about 1 / 2 / 4 / 8 m (the "floor" between echoes) | -49 / -55 / -59 / -63 dB | -48 / -52 / -56 / -61 dB (3 rooms; the 2 m value was up to 4 dB higher in the small room) |
| Ceiling echo level | about -43 dB (about 11 dB above that floor) | set to match |
| Echoes from the laptop body, screen and table | two spikes at 0.36 and 0.47 m | three spikes at 0.36, 0.47 and 0.55 m |

Each room is approximated as a **flat-floor box** (the room's bounding box and its measured ceiling
height). Real Elm, Larch and Yew have raked or bleacher floors, so the real ceiling distance changes
with position there; the box does not capture that.

## The five rooms (4 simulated positions each, laptop at 0.6 m)

| Room | Simulated as (m) | True ceiling | Ceiling measured | Matcher result |
|---|---|---|---|---|
| Study room (2nd floor SE) | 4.6 x 4.4 x 2.45 | 2.45 | 3.05 (wrong) | supported, right room first |
| Rowan studio | 13.1 x 11.2 x 3.5 | 3.5 | 3.5 | ambiguous, right room first |
| Elm lecture theatre | 14.5 x 14.0 x 4.0 | 4.0 | 4.01 | supported, right room first |
| Larch lecture theatre | 21.7 x 17.4 x 3.0 | 3.0 | 3.0 | supported, right room first |
| Chemistry lab | 23.5 x 20.1 x 2.45 | 2.45 | 2.45 | no_match, wrong room first |

## The pictures in each room folder
| File | Shows |
|---|---|
| `0_ideal_vs_realistic.png` | **Start here.** The same room and position twice. Top: an *idealised* trace (no noise, no laptop clutter) where every surface is an obvious spike at its true distance, marked by a coloured band (floor, ceiling, walls). Bottom: the *realistic* trace, where almost all of that disappears into the background. Unlabelled spikes in the top panel are echoes that bounce off two or more surfaces. |
| `5_where_it_hits.png` | A side view of the room with the sound's path to the ceiling, floor and side walls, and the realistic echo trace against time with each surface's arrival time marked. |
| `2_echo_traces.png` | Realistic echo traces for all four positions, with the true surface positions shaded. |
| `3_agreement.png` | The four positions stacked: is there an echo at the same distance from every position? |
| `4_decay.png` | How fast the sound dies away. |
| `1_recording.png` | (first room only) the raw sweep recording and its spectrogram. |

`simulated_rooms.json` holds the extracted echoes, the true surface distances and the matcher output.

**How to read the labels.** Each surface shows how many dB its strongest echo rises above the typical background
and "beats N%": the share of spots *with no surface* that it is louder than. In a noisy trace even an empty spot
reaches about +7 dB, so only echoes that beat 90% or more are called **CLEAR** (solid box). Everything else is
labelled "not above noise" (dashed box). `5_where_it_hits.png` shows the first position of each room, not the best one.

## What the plots show (20 simulated positions)
Surfaces the detector reported within 0.12 m of their true distance, against a baseline where the same
true distances are shifted by 0.3-1.0 m (the detector reports 12 echoes per position, so some chance hits are expected):

| Surface | Found | By chance |
|---|---|---|
| Ceiling | 14 / 20 | about 10 / 20 |
| Walls up to 2 m away | 7 / 8 | about 3 / 8 |
| Walls 2-4 m away | 21 / 22 | about 13 / 22 |
| Walls more than 4 m away | 3 / 50 | about 4 / 50 (not detected) |

- **At a single position the echoes are weak.** The ceiling and walls rise only about 6-11 dB above the background and
  mostly do not beat 90% of surface-free spots, so the realistic plots label them "not above noise". Combining the
  four positions helps for the ceiling in some rooms (`3_agreement.png`) but is not clear-cut.
- **The detector finds more than the plots label as clear**, because it also uses repeats across positions and corrects
  for distance. It reported ceilings and nearby walls above chance, as in the real study room, but only a few dB above the floor.
- **Walls more than about 4 m away are not detected at all.** In big rooms the far walls are invisible, so room
  size has to come from the ceiling height and the reverberation instead.
- **The floor-to-ceiling double bounce** arrives at a distance equal to the room height, one mic-height
  beyond the real ceiling echo, and was mistaken for it in three of five rooms. The matcher now prefers the
  closer echo when it is as well supported. This fix was made on this simulation, so it needs real data to confirm.
- **Measured reverberation times came out 40-60% below the formula's prediction in all five simulated rooms**
  (for example Elm 0.36 s against 0.60 s, chemistry lab 0.67 s against 1.25 s). The one real big-room recording
  (Yew, 0.27 s against 0.60 s) looks the same, but the real study room did not (0.36 s against 0.40 s), so the
  simulation does not reproduce the real small room's reverberation. The decay curve has a steep first part and
  the fit reads only that part, so treat reverberation time as unreliable until more real rooms are measured.
