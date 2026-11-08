# Nucleus metric model

The interactive model uses **0.07027 metres per PDF point**, uniformly in both
horizontal axes on every floor. Calibration comes from the user's internal Yew
measurements of 14.5 x 11.5 m; the user accepted the roughly 1% per-axis residual.
Yew renders at 14.3519448 x 11.6198472 m. No per-axis stretching is applied.

Source: [University of Edinburgh Nucleus floor plans](https://science-engineering.ed.ac.uk/sites/default/files/2024-05/Nucleus%20floor%20plans_0.pdf).
The model implements the component contract in `docs/KICKOFF.md` section 4.3.

## Data and coverage

- `nucleus-data.js` retains the original PDF-coordinate extraction for reproducibility.
- `nucleus-metric-data.js` is the generated browser dataset; `assets/building/nucleus-metric.json` contains the same data.
- `assets/building/nucleus-dimensions.csv` lists 5 floor envelopes and 45 plan regions, with width, length, area, perimeter and every boundary segment length.
- Width and length are bounds along the PDF axes. Irregular regions retain their full polygon; their areas are not width multiplied by length.
- Fourteen supplied room IDs map to 15 access-floor regions with supplied or explicitly estimated clearance. Alder adds two estimated access clearances, using Elm as the reference. Other areas and lifts retain null clearance.
- EUSA Shop is added as a manually traced main retail area; its boundary near reception remains approximate.
- The third-floor study room is partitioned from the original open-study polygon, with no overlap and conserved total area.
- SW1 is the left first-floor study room and SW2 is the right one, as confirmed by the user. `nuc-0-study` is Serviced study: multi-purpose.

Coordinates use metres with the PDF point (460,500) as the shared horizontal
origin. World x points right on the page, z down the page, and y upward.
Floor elevations use the confirmed LG lift exit as zero: LG 0, G +0.3,
First +4.7, Second +10.7 and Third +16.7 m. The cafe-side G floor is +0.7 m.
The seven original photo readings and their confirmed locations are retained in
`assets/building/nucleus-elevation-survey.json`. The phone was held at a consistent
height. Third is extrapolated from the 6 m First-to-Second interval, not measured.
This model survey is independent of the older pressure-service calibration in
`config/default.json`; this geometry update does not recalibrate the sensor service.

G has two complementary floor plates. Their boundary is approximately placed
from the plan because exact measurement-point coordinates were not supplied.
The cafe uses the higher side; entrance-side study and other G rooms use the lower
side. A schematic clockwise central staircase connects +0.7, +2.9, +3.5 and
+4.7 m. Platform positions, stair width and tread count are inferred; these are
not architectural construction dimensions. A corresponding atrium opening is
approximately traced in the First floor. Connecting stairs are hidden in exploded
views so they do not falsely appear to connect artificially separated floors.

## Viewing and selection

**Show Yew** demonstrates **Room focus**: hide floors above Second and remove
ceiling caps, retaining translucent 3D room envelopes and the camera-facing cutaway
of the exterior. Yew has a soft amber floor, tinted walls and stronger edges.
Lower floors retain the layered cutaway appearance, not a solid opaque base.
The selected room gently pulses over a 3.2-second cycle: floor colour, translucent
walls and outline intensity vary continuously. The animation stops when selection
is cleared, the tab is hidden or the component is disposed; reduced-motion settings
use a steady highlight. Only the 3D scene is redrawn per animation frame.
No artificial storey separation is added. Selecting
any room through the dropdown or label uses the same presentation at that room's
floor. Room heights remain unchanged; lower cross-floor envelopes that would
protrude above the target floor are suppressed. Candidate colours and lower-room
labels are muted while the inspected room is highlighted. **Clear
selection** returns to the complete building. The normal floor selector remains
available for isolated-floor views. This changes presentation only, not geometry
measurements or ceiling values.

The default **Complete building** view encloses each storey with continuous
facades up to the next floor, plus ceiling/roof caps over setbacks and the top
floor. **Interior cutaway** removes camera-facing facades and roofs while keeping
the rear walls and continuous lift cores. Selecting an individual floor or a plan
view also opens the shell for room inspection. Room net clearances are not stretched
to fill the structural storey height.

The shell in `architecture.js` is schematic. Its white masonry base, muted metal
fins and glazing treatment are informed by the published
[Curtins Nucleus project](https://www.curtins.com/experience/nucleus-building-university-of-edinburgh/)
and the [University's exterior photograph](https://biology.ed.ac.uk/staff/buildings-facilities-technical-services/infrastructure-projects/current-projects/nucleus-building).
It is newly generated from the existing plan outlines, not a downloaded or surveyed
as-built facade model. Assumptions: 0.24 m facade/roof thickness, 2.4 m facade bay
spacing, 0.4 m top parapet, and a 4 m top storey envelope (roof approximately +20.7 m
relative to LG). The skylight follows the plan's central void. These construction
dimensions are for appearance only and do not replace measured internal room sizes.

**All floors** shows LG through 3, assembled at their recorded elevations by default.
**Separate floors** starts at zero and optionally adds display-only separation;
set it to zero to see the recorded elevations. Single-floor views ignore this
slider. LG is included in the assembled stack and the floor selector. **Floor plan** looks down from above.

Room envelopes use supplied clear heights with open tops and zero-thickness
boundary planes, preserving internal plan dimensions. Unknown-height regions
remain footprints. The drawing-only floor plate thickness is 0.12 m below the
floor elevation; it is not measured slab thickness. Open study-area envelopes
are clearance guides, not surveyed enclosing walls.

Click a room surface, envelope or name label to inspect it in amber; estimates
are blue. The information card shows bounds, polygon area, perimeter, clearance,
elevation and any current candidate score. It contains no PDF page number.
Click empty space or **Clear selection** to clear it. Labels follow the camera,
avoid overlaps and hide behind floors. The dropdown provides access to every
zone even when its label does not fit. Dragging rotates without selecting.

Canonical `nuc-*` IDs are used by the mock producer and model. Legacy IDs are
accepted when highlighting older event streams. `setRoomCandidates` accepts an
optional second argument with the room event's source mode.

## Cross-floor rooms and limits

Oak (`nuc-12-oak`) is one physical room with access plans on floors 1 and 2.
The supplied access clearances are 7.5 and 3.0 m; the reference mean of 5.25 m
remains in the dataset. Both entrances are flush with their corridors, confirmed
by the user. With the new floor elevations their ceiling endpoints are +12.2 and
+13.7 m. The lower envelope interpolates a schematic ceiling profile between
these heights across its width; this horizontal placement is an assumption,
not a surveyed roof slope. At zero separation, the upper
Oak shell is suppressed and the upper slab has an opening, avoiding a duplicate
solid room. The lower access envelope is retained; this is not a reconstruction
of the stepped floor or the complete upper seating footprint.

Alder is similarly shared between LG and G. Following the user's instruction,
its G entrance uses Elm's 4 m clearance. An assumed shared ceiling at +4.3 m
gives LG a 4.3 m clearance. Both values are marked estimated from Elm. The G
slab has an opening and its duplicate Alder envelope is hidden in assembled view.
No cross-floor room areas or volumes are summed. Metric data includes only optional
prism volume estimates for other known-height regions, never measured volumes.
Doors, surveyed facade details, detailed stairs, furniture, measured slab thicknesses, surveyed
ceiling profiles and uncoloured ancillary rooms are not reconstructed.

## Regeneration and verification

From the repository root:

```powershell
# Only needed when re-extracting the original source PDF; requires PyMuPDF:
python scripts/extract_nucleus.py data/reference/nucleus-floor-plans.pdf
# These two steps use only the Python standard library:
python scripts/build_nucleus_room_draft.py
python scripts/build_nucleus_metric.py
python -m unittest tests.test_nucleus_metric
node tests/nucleus-geometry.mjs
```

The draft builder retains the supplied heights and ID decisions. Reviewed
geometric changes are in `assets/building/nucleus-plan-corrections.json`.
The metric builder validates counts, references, positive finite dimensions and
Yew's calibrated bounds before writing both datasets and the dimensions CSV.

Renderer: locally vendored Three.js 0.169.0 and OrbitControls with their MIT
license in `web/vendor/three/`. The browser needs no remote CDN or PDF library.
