"""Extract coloured room polygons from the university's five-page floor plan.

Usage: python scripts/extract_nucleus.py data/reference/nucleus-floor-plans.pdf
Requires PyMuPDF for this build step only. The browser uses the checked-in data.
"""
import json
from pathlib import Path
import sys

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://science-engineering.ed.ac.uk/sites/default/files/2024-05/Nucleus%20floor%20plans_0.pdf"
# Main building envelopes traced in PDF page coordinates. Links to neighbouring
# buildings are excluded. These are simplified outlines, not surveyed geometry.
UPPER = [[194,105],[544,105],[544,139],[598,139],[598,105],
         [867,105],[867,560],[796,560],[796,642],[863,748],
         [654,894],[585,794],[472,794],[472,900],[225,900],[225,588],[194,588]]
FIRST = UPPER[:13] + [[472,900],[225,900],[225,846],[55,846],
                     [55,742],[99,742],[99,576],[194,576]]
OUTLINES = [
    [[284,139],[498,139],[498,170],[538,170],[538,564],[416,564],
     [416,582],[200,582],[200,403],[284,403]],
    [[198,119],[810,119],[810,728],[636,850],[55,850],[55,774],
     [82,774],[82,733],[98,733],[98,577],[198,577]],
    FIRST, UPPER, UPPER,
]
# Named major spaces identified by visually checking each page.
NAMED = [
    {511: ("alder", "Alder", "lecture")},
    {520: ("elm", "Elm", "lecture"), 521: ("alder", "Alder", "lecture"),
     522: ("g-serviced-study", "Serviced study", "study"),
     523: ("nucleus-cafe", "Nucleus café", "social")},
    {11902: ("larch", "Larch", "lecture"), 11904: ("oak", "Oak", "lecture")},
    {10591: ("oak", "Oak", "lecture"), 10592: ("rowan", "Rowan", "studio"),
     10595: ("hawthorn", "Hawthorn", "studio"), 10597: ("yew", "Yew", "lecture")},
    {14182: ("chemistry", "Chemistry teaching laboratory", "laboratory")},
]


def polygon(drawing):
    points = []
    for item in drawing["items"]:
        if item[0] == "re":
            rect = item[1]
            points.extend([rect.tl, rect.tr, rect.br, rect.bl])
        elif item[0] == "l":
            if not points:
                points.append(item[1])
            points.append(item[2])
        elif item[0] == "c":
            if not points:
                points.append(item[1])
            # The only curved coloured boundary is a tiny corner on Elm.
            a, b, c, d = item[1:]
            for step in range(1, 5):
                t = step / 4
                points.append(a * (1-t)**3 + b * 3*(1-t)**2*t + c * 3*(1-t)*t*t + d * t**3)
        else:
            raise ValueError(f"Unsupported path command {item[0]}")
    result = []
    for point in points:
        rounded = [round(point.x, 2), round(point.y, 2)]
        if not result or rounded != result[-1]:
            result.append(rounded)
    if result[0] == result[-1]:
        result.pop()
    return result


def main():
    doc = pymupdf.open(sys.argv[1])
    if len(doc) != 5:
        raise ValueError("Expected the university's five-page PDF")
    floors = []
    for page_index, (floor_id, label) in enumerate([
        ("LG", "Lower ground"), ("0", "Ground"), ("1", "First"), ("2", "Second"), ("3", "Third")
    ]):
        rooms = []
        counters = {"lift": 0, "study": 0}
        for path_index, drawing in enumerate(doc[page_index].get_drawings()):
            colour = drawing["fill"]
            if not colour or min(colour) < .6 or max(colour) - min(colour) < .1:
                continue
            if path_index in NAMED[page_index]:
                room_id, room_label, kind = NAMED[page_index][path_index]
            else:
                kind = "lift" if colour[0] < .75 else "study"
                counters[kind] += 1
                room_id = f"{floor_id}-{kind}-{counters[kind]}"
                room_label = f"{'Lift' if kind == 'lift' else 'Study area'} {counters[kind]}"
            rooms.append({
                "room_id": room_id, "label": room_label, "kind": kind,
                "polygon": polygon(drawing), "source_path_index": path_index,
            })
        if not all(any(room["room_id"] == entry[0] for room in rooms)
                   for entry in NAMED[page_index].values()):
            raise ValueError(f"PDF paths changed on page {page_index + 1}")
        floors.append({
            "id": floor_id, "label": label, "page": page_index + 1,
            "outline": OUTLINES[page_index],
            "voids": [[[540,178],[600,178],[600,513],[540,513]]] if page_index >= 2 else [],
            "rooms": rooms,
        })
    data = {
        "source": SOURCE,
        "title": "The Nucleus — PDF-based study model",
        "coordinate_units": "PDF points, top-left origin; no metric scale supplied",
        "model_scale": .1,
        "storey_spacing": 9,
        "notes": [
            "Coloured room boundaries extracted from PDF vector paths.",
            "Building envelopes and central voids simplified by visual tracing.",
            "Layer heights and low partition walls are illustrative, not measured.",
            "Alder (LG/G) and Oak (1/2) are multi-level rooms shown on both access floors.",
            "Adjacent library and KB House links, stairs, furniture and facades are omitted.",
        ],
        "floors": floors,
    }
    output = ROOT / "web/building3d/nucleus-data.js"
    output.write_text("// Generated by scripts/extract_nucleus.py\nexport default " +
                      json.dumps(data, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    print(f"Extracted {sum(len(f['rooms']) for f in floors)} zones on {len(floors)} floors")


if __name__ == "__main__":
    main()
