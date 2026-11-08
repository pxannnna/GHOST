Owner: Anna (floor plans, rooms.json, 3D model files). See docs/KICKOFF.md §2 and §6.

# Nucleus floor plan → rooms.json

**Scope: enclosed rooms only.** Corridors, the atrium, café, open study zones, plant and staff rooms are
deliberately not in `rooms.json`; the matcher also scores a generic *corridor* model and answers `no_match`
when that fits better than every room. Alder (the LG theatre) is off limits and excluded.

**Sources** (credit on the final slide), University of Edinburgh, public PDFs retrieved 7 Nov 2026:
- *Nucleus floor plans*: room outlines, taken from the coloured room fills (vector PDF):
  https://science-engineering.ed.ac.uk/sites/default/files/2024-05/Nucleus%20floor%20plans_0.pdf
- *Nucleus Sensory Map*: first scale estimate.

| File | Edit? | What |
|---|---|---|
| `trace_nucleus.json` | rarely | Room outlines in PDF points, room kind, seats |
| `measurements.json` | **yes** | Ceiling heights (measured 7 Nov; study rooms on 1/2 estimated = 3rd-floor study room), scale wall |
| `rooms.json` | no (generated) | `python -m services.acoustics.build_rooms` — read by the matcher (and later the 3D model) |

Every room says where its numbers came from (`ceiling_source`, `outline_source`, `scale_source`, `approximate`).

## Still to do on site
- [ ] **Scale**: tape Rowan's west (corridor-side) wall, corner to corner → `scale_reference.length_m`. Until then the scale (0.0775 m/pt) is estimated from seat counts, so all lengths/areas are approximate.
- [ ] Study-room ceilings on floors 1 and 2 (currently assumed 2.45 m like the 3rd floor).
- [ ] Door-sign numbers of the study rooms and the serviced study room.
- [ ] Length × width of 3+ validation rooms (incl. the demo room) for `docs/RESULTS.md`.

Then `python -m services.acoustics.build_rooms`.
