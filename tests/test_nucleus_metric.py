"""Regression checks for the fixed-scale plan conversion and room partition."""
import csv
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def area(points):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points, points[1:]+points[:1])))/2


def inside(point, polygon):
    x, y = point
    result = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if (a[1]>y) != (b[1]>y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            result = not result
    return result


class MetricPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read_json("assets/building/nucleus-metric.json")
        cls.rooms = {(floor["id"],room["room_id"]):room
                     for floor in cls.data["floors"] for room in floor["rooms"]}

    def test_same_scale_on_every_floor_and_room(self):
        self.assertEqual(self.data["model_scale"], .07027)
        for floor in self.data["floors"]:
            for entry, raw, metric in [(floor,floor["outline_pdf_points"],floor["outline_m"])] + [
                    (room,room["polygon"],room["polygon_m"]) for room in floor["rooms"]]:
                for (x,y),(mx,mz) in zip(raw,metric):
                    self.assertAlmostEqual(mx,(x-460)*.07027,places=7)
                    self.assertAlmostEqual(mz,(y-500)*.07027,places=7)
                self.assertGreater(entry["area_m2"],0)
                self.assertTrue(all(math.isfinite(v) and v>0 for v in entry["edge_lengths_m"]))
        yew=self.rooms["2","nuc-2-yew"]
        self.assertAlmostEqual(yew["width_m"],11.6198472,places=7)
        self.assertAlmostEqual(yew["length_m"],14.3519448,places=7)
        self.assertAlmostEqual(yew["area_m2"],yew["width_m"]*yew["length_m"],places=7)

    def test_third_floor_partition_has_no_duplicate_area(self):
        draft=read_json("assets/building/nucleus-room-draft.json")
        original=draft["plan_regions"]["3/3-study-1"]["polygon_pdf_points"]
        open_plan=self.rooms["3","3-study-1"]["polygon"]
        enclosed=self.rooms["3","nuc-3-studyroom"]["polygon"]
        self.assertAlmostEqual(area(original),area(open_plan)+area(enclosed),places=5)
        for row in range(60):
            for col in range(60):
                x=585+(col+.37)*(857-585)/60
                y=656+(row+.43)*(891-656)/60
                self.assertEqual(int(inside((x,y),open_plan))+int(inside((x,y),enclosed)),
                                 int(inside((x,y),original)))

    def test_confirmed_identity_and_height_provenance(self):
        left=self.rooms["1","nuc-1-studyroom-sw1"]
        right=self.rooms["1","nuc-1-studyroom-sw2"]
        self.assertLess(left["bounds_m"][0],right["bounds_m"][0])
        self.assertEqual(left["estimated_from"],"nuc-3-studyroom")
        self.assertEqual(self.rooms["0","nuc-0-study"]["legacy_room_id"],"g-serviced-study")
        self.assertEqual(self.rooms["0","nuc-0-shop"]["mapping_status"],"identity_confirmed_by_user_geometry_approximate")
        self.assertEqual(sum(room["ceiling_height_m"] is not None for room in self.rooms.values()),17)

    def test_no_fabricated_unknown_height_or_cross_floor_volume(self):
        self.assertEqual(self.data["floors"][0]["elevation_m"],0)
        for room in self.rooms.values():
            if room["multi_level"] or room["ceiling_height_m"] is None:
                self.assertIsNone(room["estimated_prism_volume_m3"])
        self.assertEqual(self.rooms["1","nuc-12-oak"]["access_clearance_m"],7.5)
        self.assertEqual(self.rooms["2","nuc-12-oak"]["access_clearance_m"],3)

    def test_altitude_survey_preserves_readings_and_estimates(self):
        floors={floor['id']:floor for floor in self.data['floors']}
        self.assertEqual({key:f['elevation_m'] for key,f in floors.items()},
                         {'LG':0,'0':.3,'1':4.7,'2':10.7,'3':16.7})
        self.assertEqual(floors['3']['elevation_provenance'],'extrapolated_equal_storey_height')
        survey=self.data['elevation_survey']
        self.assertTrue(survey['phone_height_consistent'])
        self.assertEqual(len(survey['readings']),7)
        self.assertEqual([p['elevation_m'] for p in self.data['central_stair']['points']],[.7,2.9,3.5,4.7])
        self.assertAlmostEqual(self.rooms['0','alder']['ceiling_height_m'],self.rooms['0','nuc-0-elm']['ceiling_height_m'])
        self.assertEqual(self.rooms['LG','alder']['height_provenance'],'estimated_from_elm')
        for level in ['LG','0']:
            r=self.rooms[level,'alder']
            self.assertAlmostEqual(r['elevation_m']+r['ceiling_height_m'],4.3)
        for level in ['1','2']:
            self.assertEqual(self.rooms[level,'nuc-12-oak']['elevation_m'],floors[level]['elevation_m'])

    def test_ground_split_preserves_area_and_assigns_cafe_height(self):
        floor=next(f for f in self.data['floors'] if f['id']=='0')
        plates=[p['polygon_m'] for p in floor['slab_regions']]
        self.assertAlmostEqual(sum(area(p) for p in plates),floor['area_m2'],places=6)
        for row in range(50):
            for col in range(50):
                point=(-29+(col+.37)*55/50,-27+(row+.43)*52/50)
                self.assertEqual(sum(int(inside(point,p)) for p in plates),int(inside(point,floor['outline_m'])))
        self.assertEqual(self.rooms['0','nucleus-cafe']['elevation_m'],.7)
        self.assertEqual(self.rooms['0','nuc-0-shop']['elevation_m'],.3)

    def test_csv_covers_every_floor_region_and_boundary(self):
        with (ROOT/"assets/building/nucleus-dimensions.csv").open(encoding="utf-8-sig",newline="") as handle:
            rows=list(csv.DictReader(handle))
        self.assertEqual(len(rows),50)
        self.assertEqual({(r["floor_id"],r["room_id"]) for r in rows if r["record_type"]=="plan_region"},set(self.rooms))
        for row in rows:
            self.assertTrue(row["outer_edge_lengths_m"])


if __name__ == "__main__":
    unittest.main()
