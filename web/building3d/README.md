# Nucleus PDF study model

Initial layout model for Anna's building component, exposing the `mountBuilding()`
contract in `docs/KICKOFF.md` §4.3. Runs entirely locally with the web demo.

Source: [University of Edinburgh Nucleus floor plans, five pages](https://science-engineering.ed.ac.uk/sites/default/files/2024-05/Nucleus%20floor%20plans_0.pdf).
Pages correspond to LG, G (`0` in events), 1, 2 and 3. Coloured room polygons
are extracted from the PDF's vector paths; exterior envelopes and central
voids are manually simplified. There are 43 coloured zones, including lifts
and open study areas, not 43 enclosed rooms.

## Use

Choose **All floors** for an exploded view, a specific floor for inspection,
or **Follow estimate** for sensor-driven visibility. **Floor plan** looks down
on the selected level. Drag to rotate, scroll to zoom and right-drag to pan.
The room selector highlights an inspected room in amber. Estimates are blue.
Click a room surface, partition or name label to inspect it without moving the
camera. The information panel shows its name, floor, use and any current
candidate score. Click empty space or **Clear selection** to clear it. Dragging
and multi-touch gestures do not select rooms; floor plates block clicks on
hidden rooms. Floor name buttons isolate a floor. Room names follow the camera,
hide behind other floors, and avoid overlapping labels; select a floor or zoom
in to reveal more names. The room dropdown also provides keyboard access to
every zone, including small spaces whose labels cannot fit.

Known named room IDs: `alder` (LG/G), `elm` (G), `oak` (1/2), `larch` (1),
`hawthorn`, `rowan`, `yew` (2), `chemistry` (3), and `nucleus-cafe` (G).
Generic study/lift IDs in `nucleus-data.js` are provisional. Candidate IDs are
matched within the estimated floor; unknown IDs appear in a status message.
Alder and Oak are multi-level lecture theatres, shown on both access plans;
these contours should not be counted as separate physical rooms.

## Accuracy and remaining work

The PDF provides no verified metric scale or storey heights. Coordinates use
PDF points multiplied by an arbitrary display scale, and all elevations,
slab thicknesses and low partition heights are illustrative. Layer spacing is
a viewing aid. This is not a measured architectural or acoustic volume model.
Doors, glazing, full-height walls, stairs, seating, exterior facade, plant-room
details and uncoloured small rooms are not reconstructed. The lecture theatres
are shown as per-floor access regions, without their actual stepped volumes.
Horizontal alignment follows the shared lift core in the source plans.

## Regenerate data

Download the linked PDF to `data/reference/nucleus-floor-plans.pdf`. Then,
using Python with `PyMuPDF` installed, run from the repository root:

```powershell
python scripts/extract_nucleus.py data/reference/nucleus-floor-plans.pdf
```

This writes `web/building3d/nucleus-data.js`. Path indices refer to this specific
PDF revision; changed source plans require rechecking mappings and envelopes.
The browser does not require Python PDF libraries or remote CDN access.

Renderer: Three.js 0.169.0 and OrbitControls, vendored in `web/vendor/three/`
with their MIT license. Source plan attribution remains with the university;
the source PDF is not bundled in the web assets.
