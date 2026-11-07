"""Build a review-only room/plan mapping; never invent metric plan dimensions.

Run from the repository root: python scripts/build_nucleus_room_draft.py
Inputs: extracted PDF plan data, current pressure survey and user-supplied heights.
The output is deliberately separate from the runtime rooms.json metric contract.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Heights supplied by the user in chat. No independent measurement verification.
HEIGHTS = {
    "nuc-0-elm": 4.0, "nuc-0-shop": 3.0, "nuc-0-study": 3.0,
    "nuc-12-oak": 5.25, "nuc-1-larch": 3.0,
    "nuc-1-studyroom-sw1": 2.45, "nuc-1-studyroom-sw2": 2.45,
    "nuc-1-studyroom-se": 2.45, "nuc-2-yew": 4.0,
    "nuc-2-rowan": 3.5, "nuc-2-hawthorn": 3.5,
    "nuc-2-studyroom-se": 2.45, "nuc-3-chemlab": 2.45,
    "nuc-3-studyroom": 2.45,
}

MAPPINGS = {
    "nuc-0-elm": ("Elm", "lecture", ["0/elm"]),
    "nuc-0-shop": ("EUSA Shop", "shop", ["0/eusa-shop-draft"]),
    "nuc-0-study": ("Serviced study: multi-purpose", "study", ["0/g-serviced-study"]),
    "nuc-12-oak": ("Oak", "lecture", ["1/oak", "2/oak"]),
    "nuc-1-larch": ("Larch", "lecture", ["1/larch"]),
    "nuc-1-studyroom-sw1": ("Southwest study room 1", "study_room", ["1/1-study-8"]),
    "nuc-1-studyroom-sw2": ("Southwest study room 2", "study_room", ["1/1-study-9"]),
    "nuc-1-studyroom-se": ("First-floor southeast study room", "study_room", ["1/1-study-5"]),
    "nuc-2-yew": ("Yew", "lecture", ["2/yew"]),
    "nuc-2-rowan": ("Rowan", "studio", ["2/rowan"]),
    "nuc-2-hawthorn": ("Hawthorn", "studio", ["2/hawthorn"]),
    "nuc-2-studyroom-se": ("Second-floor southeast study room", "study_room", ["2/2-study-2"]),
    "nuc-3-chemlab": ("Chemistry teaching laboratory", "laboratory", ["3/chemistry"]),
    "nuc-3-studyroom": ("Third-floor study room", "study_room", ["3/studyroom-draft"]),
}


def main():
    text = (ROOT / "web/building3d/nucleus-data.js").read_text(encoding="utf-8")
    source = json.loads(text.split("export default ", 1)[1].strip().removesuffix(";"))
    config = json.loads((ROOT / "config/default.json").read_text(encoding="utf-8"))
    elevations = config["pressure"]["survey"]["relative_height_m"]
    regions = {}
    for floor in source["floors"]:
        for room in floor["rooms"]:
            key = f"{floor['id']}/{room['room_id']}"
            regions[key] = {
                "floor_id": floor["id"], "model_room_id": room["room_id"],
                "label": room["label"], "kind": room["kind"],
                "polygon_pdf_points": room["polygon"],
                "geometry_method": "existing_pdf_coloured_vector_path",
            }

    regions["0/eusa-shop-draft"] = {
        "floor_id": "0", "model_room_id": None, "label": "EUSA Shop", "kind": "shop",
        "polygon_pdf_points": [[648,383],[807.2,383],[807.2,590.5],[719.5,590.5],[719.5,565.2],[648,565.2]],
        "geometry_method": "manual_approximate_trace",
        "note": "Main retail space only. Southern boundary through openings is inferred; ancillary rooms and reception are excluded. Needs boundary review.",
    }
    regions["3/studyroom-draft"] = {
        "floor_id": "3", "model_room_id": None, "label": "Third-floor study room", "kind": "study_room",
        "polygon_pdf_points": [[585.4,709.8],[630.5,709.8],[630.5,768.2],[596.2,792.5],[585.4,777.3]],
        "geometry_method": "manual_approximate_trace",
        "note": "Separate enclosed study room southwest of the open study area; traced from visible partition lines.",
    }
    regions["3/3-study-1"]["requires_partition_before_runtime_use"] = ["3/studyroom-draft"]
    regions["3/3-study-1"]["note"] = "Original coloured zone spans both open study and the enclosed room. Do not count both this full zone and the new room as disjoint spaces."

    rooms = {}
    for room_id, (label, kind, refs) in MAPPINGS.items():
        floor_ids = sorted({regions[ref]["floor_id"] for ref in refs}) if refs else ["1"]
        entry = {
            "label": label, "kind": kind, "floor_ids": floor_ids,
            "plan_region_refs": refs,
            "mapping_status": "matched_by_plan_name_or_position",
            "ceiling_height_m": HEIGHTS[room_id],
            "height_provenance": "user_provided_not_independently_verified",
            "polygon_m": None, "area_m2": None, "volume_m3": None,
        }
        if room_id in {"nuc-1-studyroom-sw1", "nuc-1-studyroom-sw2", "nuc-1-studyroom-se", "nuc-2-studyroom-se"}:
            entry.update(estimated_from="nuc-3-studyroom", height_provenance="user_estimate_from_another_room")
        if "-sw" in room_id:
            entry["mapping_status"] = "identity_confirmed_by_user"
            entry["note"] = "User confirmed SW1 is the left room (1-study-8) and SW2 is the right room (1-study-9), relative to the displayed floor plan. Height remains estimated from nuc-3-studyroom."
        if room_id == "nuc-0-study":
            entry["mapping_status"] = "identity_confirmed_by_user"
            entry["note"] = "User confirmed the pictured Serviced study: multi-purpose area beside the ground-floor entrance."
        if room_id == "nuc-0-shop":
            entry["mapping_status"] = "identity_confirmed_by_user_geometry_approximate"
        if room_id == "nuc-12-oak":
            entry.update(ceiling_min_m=3.0, ceiling_max_m=7.5,
                         clearance_at_access_floor_m={"1":7.5,"2":3.0},
                         note="One multi-level room with two access-plan regions. 5.25 is the supplied average, not a uniform ceiling or a verified volume-equivalent height.")
        rooms[room_id] = entry

    floors = []
    for floor in source["floors"]:
        floor_id = floor["id"]
        next_id = str(int(floor_id)+1) if floor_id.isdigit() else "0"
        delta = round(elevations[next_id]-elevations[floor_id], 2) if floor_id in elevations and next_id in elevations else None
        floors.append({"floor_id":floor_id,"label":floor["label"],
                       "estimated_elevation_m":elevations.get(floor_id),
                       "estimated_floor_to_next_floor_m":delta,
                       "elevation_provenance":"existing_phone_barometer_survey" if floor_id in elevations else "unknown"})
    assigned = {ref for room in rooms.values() for ref in room["plan_region_refs"]}
    candidates = {ref for room in rooms.values() for ref in room.get("candidate_plan_region_refs", [])}
    output = {
        "status": "draft_for_mapping_review_not_runtime_metric_geometry",
        "source_plan": source["source"],
        "coordinate_system": {"units":"PDF points", "origin":"top-left", "x":"right", "y":"down", "meters_per_pdf_point":None,
                              "note":"Direction words in provisional IDs follow page orientation; geographic north is not verified."},
        "floors": floors, "rooms": rooms, "plan_regions": regions,
        "regions_without_supplied_height": sorted(set(regions)-assigned-candidates),
        "pending": [
            "Review approximate EUSA Shop extent, especially the open southern boundary.",
            "Trim the existing third-floor open study polygon before integrating the enclosed-room polygon; avoid overlapping room volumes.",
            "Measure a reliable horizontal reference length on each plan (or verify common scale) before deriving metric footprints, areas or volumes.",
            "LG elevation, roof elevation and remaining room clearances are unknown; floor-to-floor intervals must not substitute for ceiling heights.",
        ],
        "consistency_notes": [
            "Oak entrance clearances differ by 4.5 m; the barometric floor-1-to-floor-2 estimate is 4.97 m. The 0.47 m difference is a check item, not proof of an error: ceiling shape, entrance positions and survey uncertainty are not established.",
            "This draft covers existing coloured model regions and two traced additions; it is not a complete building room inventory.",
        ],
    }
    assert len(rooms) == 14 and len(regions) == 45
    for room in rooms.values():
        for ref in room["plan_region_refs"] + room.get("candidate_plan_region_refs", []):
            assert ref in regions
        if "estimated_from" in room:
            assert room["estimated_from"] in rooms
        assert room["polygon_m"] is None and room["area_m2"] is None
    path = ROOT / "assets/building/nucleus-room-draft.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Wrote {len(rooms)} room records, {len(regions)} plan regions and {len(floors)} floor records to {path}")


if __name__ == "__main__":
    main()
