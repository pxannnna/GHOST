"""Generate the calibrated Nucleus model and a complete dimensions CSV.

All horizontal coordinates use the user-approved constant 0.07027 m/PDF point.
Run after build_nucleus_room_draft.py and after reviewing plan corrections:
    python scripts/build_nucleus_metric.py

No external Python packages are required. Heights are copied with provenance;
unknown heights remain null unless an explicit modelling assumption is supplied. Irregular-room length/width
are bounding-box extents, not a claim that the footprint is rectangular.
"""
from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCALE = 0.07027
ORIGIN = [460, 500]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def metric_polygon(points):
    return [[round((x - ORIGIN[0]) * SCALE, 8),
             round((y - ORIGIN[1]) * SCALE, 8)] for x, y in points]


def ring_area(points):
    return abs(sum(a[0] * b[1] - a[1] * b[0]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2


def ring_edges(points):
    return [math.hypot(b[0] - a[0], b[1] - a[1])
            for a, b in zip(points, points[1:] + points[:1])]


def dimensions(polygon, holes):
    xs = [point[0] for point in polygon]
    zs = [point[1] for point in polygon]
    width, length = max(xs) - min(xs), max(zs) - min(zs)
    area = ring_area(polygon) - sum(ring_area(hole) for hole in holes)
    edges = ring_edges(polygon)
    hole_edges = [ring_edges(hole) for hole in holes]
    rectangular = (not holes and len(polygon) == 4 and
                   math.isclose(area, width * length, rel_tol=1e-10, abs_tol=1e-8))
    return {
        "width_m": width, "length_m": length,
        "area_m2": area, "perimeter_m": sum(edges) + sum(map(sum, hole_edges)),
        "edge_lengths_m": edges, "hole_edge_lengths_m": hole_edges,
        "bounds_m": [min(xs), min(zs), max(xs), max(zs)],
        "is_rectangular": rectangular,
        "dimension_basis": "PDF-axis bounding box; width along x, length along page-down z",
        "area_basis": "calibrated plan polygon minus explicit holes",
    }


def build_data(source, draft, corrections, survey):
    regions = copy.deepcopy(draft["plan_regions"])
    for key, override in corrections.get("regions", {}).items():
        if key not in regions:
            raise ValueError(f"Unknown corrected region: {key}")
        regions[key].update(override)
    room_by_region = {}
    for room_id, room in draft["rooms"].items():
        for key in room["plan_region_refs"]:
            if key in room_by_region:
                raise ValueError(f"Region mapped twice: {key}")
            room_by_region[key] = (room_id, room)
    elevations = {key: value["elevation_m"] for key, value in survey["floors"].items()}
    floors = []
    for source_floor in source["floors"]:
        floor_id = source_floor["id"]
        override = corrections.get("floors", {}).get(floor_id, {})
        outline = override.get("outline_pdf_points", source_floor["outline"])
        voids = override.get("voids_pdf_points", source_floor["voids"])
        outline_m = metric_polygon(outline)
        voids_m = [metric_polygon(hole) for hole in voids]
        floor = {
            "id": floor_id, "label": source_floor["label"], "page": source_floor["page"],
            "elevation_m": elevations.get(floor_id),
            "elevation_provenance": survey["floors"][floor_id]["provenance"],
            "outline_m": outline_m, "voids_m": voids_m,
            "outline_pdf_points": outline, "voids_pdf_points": voids,
            "geometry_notes": [override["note"]] if override.get("note") else [],
            **dimensions(outline_m, voids_m), "rooms": [],
        }
        if floor_id == "0":
            # Two complementary plates, sharing the provisional split boundary.
            a, b, c = survey["ground_split"]["boundary_pdf_points"]
            south = [a, b, c, [55,850], [55,774], [82,774], [82,733], [98,733]]
            north = outline[:3] + [c, b, a] + outline[9:]
            floor["slab_regions"] = [
                {"polygon_m": metric_polygon(north), "elevation_m": elevations["0"]},
                {"polygon_m": metric_polygon(south), "elevation_m": survey["ground_split"]["south_elevation_m"]},
            ]
            floor["geometry_notes"].append(survey["ground_split"]["note"])
        if floor_id == "1":
            floor["stair_opening_m"] = metric_polygon([[473,602],[548,602],[548,740],[473,740]])
            floor["geometry_notes"].append("Central atrium stair opening approximately traced; stair route is schematic.")
        for key, region in regions.items():
            if region["floor_id"] != floor_id:
                continue
            legacy_id = region.get("model_room_id") or key.split("/", 1)[1]
            room_id, supplied = room_by_region.get(key, (legacy_id, {}))
            supplied = copy.deepcopy(supplied)
            if legacy_id == "alder":
                supplied.update(ceiling_height_m=survey["alder"]["ceiling_elevation_m"]-elevations[floor_id],
                                height_provenance=survey["alder"]["provenance"],
                                estimated_from=survey["alder"]["estimated_from"],
                                note=survey["alder"]["note"])
            polygon_pdf = region["polygon_pdf_points"]
            holes_pdf = region.get("holes_pdf_points", [])
            polygon_m = metric_polygon(polygon_pdf)
            holes_m = [metric_polygon(hole) for hole in holes_pdf]
            multi_level = legacy_id in {"oak", "alder"} or room_id == "nuc-12-oak"
            notes = [region["note"]] if region.get("note") else []
            if supplied.get("note"):
                notes.append(supplied["note"])
            if multi_level:
                notes.append("One physical multi-level theatre is represented on both access plans; do not sum the per-floor contour areas or volumes.")
            if not supplied.get("ceiling_height_m"):
                notes.append("Ceiling height is unknown; retain a footprint without inventing a measured room height.")
            elif supplied.get("estimated_from"):
                notes.append(f"Ceiling height is estimated from {supplied['estimated_from']}, not independently measured in this room.")
            room = {
                "room_id": room_id, "legacy_room_id": legacy_id,
                "source_region_ref": key,
                "label": supplied.get("label", region["label"]),
                "kind": supplied.get("kind", region["kind"]),
                "polygon_m": polygon_m, "holes_m": holes_m,
                "polygon": polygon_pdf, "holes_pdf_points": holes_pdf,
                "geometry_method": region["geometry_method"],
                "mapping_status": supplied.get("mapping_status", "model_only_provisional_id"),
                "ceiling_height_m": supplied.get("ceiling_height_m"),
                "height_provenance": supplied.get("height_provenance", "unknown"),
                "multi_level": multi_level,
                "physical_room_id": room_id,
                "notes": notes,
                "elevation_m": survey["ground_split"]["south_elevation_m"] if floor_id == "0" and room_id in survey["ground_split"]["south_room_ids"] else elevations[floor_id],
                "elevation_provenance": survey["floors"][floor_id]["provenance"],
                **dimensions(polygon_m, holes_m),
            }
            for field in ("estimated_from", "clearance_at_access_floor_m", "ceiling_min_m", "ceiling_max_m"):
                if field in supplied:
                    room[field] = supplied[field]
            room["access_clearance_m"] = supplied.get("clearance_at_access_floor_m", {}).get(floor_id, room["ceiling_height_m"])
            if room_id == "nuc-12-oak":
                room["ceiling_profile_m"] = {"low_elevation_m": elevations["1"]+7.5, "high_elevation_m": elevations["2"]+3.0,
                                             "provenance": "schematic_profile_from_access_clearances"}
                room["notes"].append(survey["oak"]["note"])
            # Even known net heights yield only a prism approximation, not a surveyed
            # acoustic volume. Multi-level theatres intentionally have no volume.
            height = room["ceiling_height_m"]
            room["volume_m3"] = None
            room["estimated_prism_volume_m3"] = room["area_m2"] * height if height is not None and not multi_level else None
            room["volume_basis"] = "No measured volume; optional prism estimate ignores furniture, ceiling variations and openings."
            floor["rooms"].append(room)
        floors.append(floor)
    return {
        "title": "The Nucleus — Yew-calibrated metric model",
        "units": "m", "model_scale": SCALE, "coordinate_origin_pdf": ORIGIN,
        "coordinate_axes": {"x":"PDF right", "y":"vertical elevation", "z":"PDF down"},
        "source": source["source"],
        "elevation_survey": survey,
        "central_stair": {**survey["central_stair"], "points": [
            {**point, "position_m": metric_polygon([point["pdf"]])[0]} for point in survey["central_stair"]["points"]]},
        "calibration": {
            "room_id":"nuc-2-yew", "measured_internal_length_m":14.5,
            "measured_internal_width_m":11.5, "applied_m_per_pdf_point":SCALE,
            "method":"single user-approved isotropic scale for every floor plan",
            "all_pdf_pages_same_scale":"confirmed_by_user",
            "note":"The user accepted the approximately 1% per-axis residual. The room geometry uses this constant without anisotropic rescaling to the measured endpoints.",
        },
        "notes": [
            "All plan dimensions, including every outline edge, are derived from the same fixed 0.07027 m/PDF point scale.",
            "Widths and lengths are axis-aligned bounds; irregular rooms retain complete polygons and per-edge dimensions.",
            "Floor elevations use LG as zero. Third floor is extrapolated; Alder and the central staircase include explicit geometric assumptions.",
            "Oak and Alder have per-access plan regions, not independent stacked rooms. No room areas or volumes are summed across their access floors.",
            "Original floor envelopes, voids and manual room boundaries are simplified. This is a calibrated model of the available plan regions, not a complete surveyed building inventory.",
        ],
        "geometry_corrections": corrections.get("validation", {}),
        "floors": floors,
    }


def validate(data):
    all_rooms = [room for floor in data["floors"] for room in floor["rooms"]]
    assert len(data["floors"]) == 5
    assert len(all_rooms) == 45, len(all_rooms)
    assert sum(room["ceiling_height_m"] is not None for room in all_rooms) == 17
    for floor in data["floors"]:
        ids = [room["room_id"] for room in floor["rooms"]]
        assert len(set(ids)) == len(ids), floor["id"]
        for entry, polygon, holes in [(floor, floor["outline_m"], floor["voids_m"])] + [
                (room, room["polygon_m"], room["holes_m"]) for room in floor["rooms"]]:
            assert len(polygon) >= 3 and entry["area_m2"] > 0
            assert all(math.isfinite(v) for ring in [polygon, *holes] for point in ring for v in point)
            assert len(entry["edge_lengths_m"]) == len(polygon)
            assert all(edge > 0 for edge in entry["edge_lengths_m"])
            assert math.isclose(entry["area_m2"], ring_area(polygon) - sum(ring_area(h) for h in holes))
    yew = next(room for room in all_rooms if room["room_id"] == "nuc-2-yew")
    assert math.isclose(yew["width_m"], 165.36 * SCALE, abs_tol=1e-8)
    assert math.isclose(yew["length_m"], 204.24 * SCALE, abs_tol=1e-8)
    assert all(room["estimated_prism_volume_m3"] is None for room in all_rooms if room["multi_level"])
    assert data["floors"][0]["elevation_m"] == 0
    return yew


def write_csv(data, path):
    fields = ["record_type", "floor_id", "room_id", "label", "kind", "width_m", "length_m",
              "area_m2", "perimeter_m", "ceiling_height_m", "access_clearance_m", "elevation_m",
              "height_provenance", "estimated_from", "multi_level", "is_rectangular",
              "dimension_basis", "outer_edge_lengths_m", "hole_edge_lengths_m", "notes"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for floor in data["floors"]:
            for entry in [floor, *floor["rooms"]]:
                is_floor = entry is floor
                row = {key:entry.get(key, "") for key in fields}
                row.update(record_type="floor" if is_floor else "plan_region", floor_id=floor["id"],
                           room_id="" if is_floor else entry["room_id"], elevation_m=entry["elevation_m"],
                           outer_edge_lengths_m=" | ".join(f"{value:.4f}" for value in entry["edge_lengths_m"]),
                           hole_edge_lengths_m=json.dumps([[round(v,4) for v in edges] for edges in entry["hole_edge_lengths_m"]]),
                           notes="; ".join(entry.get("geometry_notes" if is_floor else "notes", [])))
                for key in ("width_m", "length_m", "area_m2", "perimeter_m"):
                    row[key] = f"{entry[key]:.4f}"
                writer.writerow(row)


def main():
    source_text = (ROOT / "web/building3d/nucleus-data.js").read_text(encoding="utf-8")
    source = json.loads(source_text.split("export default ", 1)[1].strip().removesuffix(";"))
    draft = read_json(ROOT / "assets/building/nucleus-room-draft.json")
    corrections = read_json(ROOT / "assets/building/nucleus-plan-corrections.json")
    survey = read_json(ROOT / "assets/building/nucleus-elevation-survey.json")
    data = build_data(source, draft, corrections, survey)
    yew = validate(data)
    serialized = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (ROOT / "assets/building/nucleus-metric.json").write_text(serialized, encoding="utf-8")
    (ROOT / "web/building3d/nucleus-metric-data.js").write_text(
        "// Generated by scripts/build_nucleus_metric.py; do not edit manually.\nexport default " + serialized.rstrip() + ";\n", encoding="utf-8")
    write_csv(data, ROOT / "assets/building/nucleus-dimensions.csv")
    print(f"Generated 5 floors, 45 plan regions and 50 CSV records at {SCALE} m/PDF point.")
    print(f"Yew: {yew['width_m']:.8f} x {yew['length_m']:.8f} m; area {yew['area_m2']:.8f} m2.")


if __name__ == "__main__":
    main()
