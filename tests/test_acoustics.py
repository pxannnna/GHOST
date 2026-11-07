import json

import numpy as np
import pytest

from shared.schema import validate_event, utc_now_iso
from services.acoustics import features as F
from services.acoustics.build_rooms import build
from services.acoustics.match import (DEFAULT_MATCHING, PositionMeasurement, combine, eyring_rt60,
                                      rank)
from services.acoustics.rooms import Room, load_rooms, polygon_area, rooms_on_floor
from services.acoustics.simulate import hybrid_ir, shoebox_ir, simulate_recording
from services.acoustics.sweep import ir_from_recordings, make_sweep
from shared.config import ROOT

FS = 48000


@pytest.fixture(scope="module")
def sweep():
    return make_sweep(FS, 200, 20000, 3.0)


# ------------------------------------------------------------------ sweep + IR
def test_deconvolution_recovers_delayed_impulse_despite_latency(sweep):
    ir = np.zeros(int(0.5 * FS))
    ir[0] = 1.0
    ir[int(0.010 * FS)] = 0.5          # reflection 10 ms after direct
    recs = [simulate_recording(ir, sweep, latency_s=lat, noise_rms=1e-4, tail_s=3.0, seed=i)
            for i, lat in enumerate((0.013, 0.041, 0.027))]   # wireless mic: latency varies
    h = ir_from_recordings(recs, sweep)
    d = int(np.argmax(np.abs(h)))
    seg = np.abs(h[d + 48: d + 2000])
    assert abs((np.argmax(seg) + 48) - 480) <= 2           # 10 ms = 480 samples after direct


@pytest.mark.parametrize("rt", [0.4, 0.9, 1.8])
def test_rt60_on_exponential_decay(rt):
    rng = np.random.default_rng(1)
    t = np.arange(int(2.5 * FS)) / FS
    h = rng.normal(0, 1, len(t)) * 10 ** (-3 * t / rt) * 0.05 + rng.normal(0, 1e-5, len(t))
    h[int(0.005 * FS)] = 1.0           # loud direct sound (mic next to speaker)
    f = F.extract(h, FS)
    assert f.rt60_s == pytest.approx(rt, rel=0.08)


def test_reflections_find_shoebox_surfaces(sweep):
    dims, src = (10, 8, 4), (2.5, 3.5, 1.0)
    mic = (2.6, 3.5, 1.0)
    ir = shoebox_ir(dims, src, mic, 0.2, FS, length_s=0.3)
    recs = [simulate_recording(ir, sweep, latency_s=0.02, noise_rms=3e-4, tail_s=1.0, seed=0)]
    h = ir_from_recordings(recs, sweep, length_s=0.3)
    found = [r.distance_m for r in F.extract(h, FS, speaker_mic_m=0.1).reflections]
    for surface in (1.0, 2.5, 3.0, 3.5):           # floor, x-wall, ceiling, y-wall
        assert min(abs(d - surface) for d in found) < 0.1, (surface, found)


# ------------------------------------------------------------------ rooms
def test_rooms_json_is_in_sync_with_trace():
    trace = json.loads((ROOT / "assets/building/trace_nucleus.json").read_text())
    meas = json.loads((ROOT / "assets/building/measurements.json").read_text())
    committed = json.loads((ROOT / "assets/building/rooms.json").read_text())
    assert build(trace, meas)["rooms"] == committed["rooms"], \
        "rooms.json is stale: run `python -m services.acoustics.build_rooms`"


def test_rooms_load_and_floors():
    rooms = load_rooms()
    ids = {r.room_id for r in rooms}
    assert {"nuc-2-rowan", "nuc-2-hawthorn", "nuc-2-yew", "nuc-12-oak", "nuc-1-larch", "nuc-0-elm"} <= ids
    assert {r.room_id for r in rooms_on_floor(rooms, "2")} >= {"nuc-2-rowan", "nuc-12-oak"}
    assert "nuc-12-oak" in {r.room_id for r in rooms_on_floor(rooms, "1")}
    assert not any("LG" in r.floor_ids for r in rooms)
    assert "nuc-0-alder" not in ids                      # LG theatre: off limits
    assert not any(r.kind in ("open_area", "corridor") for r in rooms)   # rooms only
    for r in rooms:
        assert r.area_m2 > 10 and r.ceiling_range_m[0] <= r.ceiling_height_m <= r.ceiling_range_m[1]
    oak = next(r for r in rooms if r.room_id == "nuc-12-oak")
    assert oak.ceiling_range_m == (3.0, 7.5)


def test_measured_scale_and_ceiling_override():
    trace = json.loads((ROOT / "assets/building/trace_nucleus.json").read_text())
    meas = {"scale_reference": {"length_pt": 100, "length_m": 15.0},
            "rooms": {"nuc-2-rowan": {"ceiling_height_m": 3.3},
                      "nuc-2-studyroom-se": {"ceiling_height_m": 2.45, "estimated_from": "nuc-3-studyroom"}}}
    out = build(trace, meas)
    by_id = {r["room_id"]: r for r in out["rooms"]}
    rowan = by_id["nuc-2-rowan"]
    assert out["scale_m_per_pt"] == 0.15
    assert rowan["ceiling_height_m"] == 3.3 and rowan["ceiling_source"] == "measured"
    pt = next(r for r in trace["rooms"] if r["room_id"] == "nuc-2-rowan")["polygon_pt"]
    assert polygon_area(rowan["polygon_m"]) == pytest.approx(polygon_area(pt) * 0.15 ** 2, rel=1e-3)
    assert by_id["nuc-2-studyroom-se"]["ceiling_source"].startswith("estimated")
    assert by_id["nuc-2-studyroom-se"]["approximate"]


# ------------------------------------------------------------------ matching
def _room(rid, L, W, H, kind="studio"):
    return Room(rid, "2", ["2"], rid, kind, [(0, 0), (L, 0), (L, W), (0, W)], H, (H, H))


def _pos(rt, dists, mid):
    return PositionMeasurement(mid, rt, dists, 0.75)


def test_ceiling_found_as_repeated_distance():
    c = combine([_pos(0.8, [0.75, 2.1, 3.25], "a"), _pos(0.8, [3.24, 4.4], "b"), _pos(0.8, [1.6, 3.26], "c")])
    assert c.ceiling_distance_m == pytest.approx(3.25, abs=0.02)
    assert c.height_m == pytest.approx(4.0, abs=0.02)
    assert c.nearest_walls_m == [2.1, 4.4, 1.6]


def test_rank_picks_matching_room_and_reports_status():
    small, big = _room("small", 8, 6, 3.0), _room("big", 25, 20, 8.0, "lecture_theatre")
    rt_big = eyring_rt60(25 * 20 * 8, 2 * 500 + 90 * 8, 0.28)
    pos = [_pos(rt_big, [3.0, 7.25], "a"), _pos(rt_big * 1.05, [7.25, 5.0], "b")]
    out = rank(pos, [small, big])
    assert out["candidates"][0]["room_id"] == "big"
    assert out["status"] == "supported"
    one = rank(pos[:1], [small, big])
    assert one["status"] == "candidate"            # 1 position is never 'supported'
    assert rank([], [small, big])["status"] == "listening"


def test_identical_rooms_are_ambiguous():
    a, b = _room("a", 10, 8, 4), _room("b", 10.2, 8, 4)
    rt = eyring_rt60(320, 2 * 80 + 36 * 4, 0.22)
    out = rank([_pos(rt, [3.25, 2.0], "1"), _pos(rt, [3.25, 3.0], "2")], [a, b])
    assert out["status"] == "ambiguous"


def test_far_off_room_is_no_match():
    out = rank([_pos(4.0, [9.0], "1"), _pos(4.0, [9.0], "2")], [_room("tiny", 4, 3, 2.5)])
    assert out["status"] == "no_match"


def test_room_estimate_payload_passes_schema():
    rooms = rooms_on_floor(load_rooms(), "2")
    out = rank([_pos(0.8, [3.25, 2.0], "m1"), _pos(0.85, [3.25, 4.0], "m2")], rooms, DEFAULT_MATCHING)
    out.update(floor_id="2", floor_source="measured")
    validate_event({"session_id": "t", "source": "acoustics", "type": "room.estimate",
                    "timestamp_utc": utc_now_iso(), "sequence": 0, "mode": "simulated", "payload": out})


def test_simulated_end_to_end_ranks_true_room_top3(sweep):
    """Hybrid simulation of Elm vs the other rooms on G (shoebox approximation)."""
    rooms = load_rooms()
    elm = next(r for r in rooms if r.room_id == "nuc-0-elm")
    L, W = elm.bbox_dims()
    H = elm.ceiling_height_m
    positions = []
    for k, (x, y) in enumerate([(3.0, 4.0), (9.0, 5.5), (5.0, 11.0)]):
        ir = hybrid_ir((L, W, H), (x, y, 0.75), (x + 0.1, y, 0.75), 0.28, FS, length_s=2.5, seed=k)
        rec = simulate_recording(ir, sweep, latency_s=0.02 + 0.01 * k, noise_rms=2e-3, tail_s=3.0, seed=k)
        f = F.extract(ir_from_recordings([rec], sweep), FS, speaker_mic_m=0.1, max_distance_m=25)
        positions.append(PositionMeasurement(f"p{k}", f.rt60_s, [r.distance_m for r in f.reflections], 0.75,
                                             reflection_strengths_db=[r.strength_db for r in f.reflections]))
    out = rank(positions, rooms_on_floor(rooms, "0"))
    top3 = [c["room_id"] for c in out["candidates"][:3]]
    assert "nuc-0-elm" in top3
    assert out["measured"]["height_m"] == pytest.approx(H, abs=0.2)


def test_corridor_is_rejected_not_forced_into_a_room(sweep):
    """GHOST locates you inside ROOMS. A corridor must come back as no_match."""
    rooms = rooms_on_floor(load_rooms(), "2")
    positions = []
    for k, x in enumerate((4.0, 11.0, 19.0, 26.0)):
        ir = hybrid_ir((30, 2.5, 3.0), (x, 1.25, 0.75), (x + 0.1, 1.25, 0.75), 0.15, FS, length_s=2.5, seed=k)
        rec = simulate_recording(ir, sweep, latency_s=0.02, noise_rms=2e-3, tail_s=3.0, seed=k)
        f = F.extract(ir_from_recordings([rec], sweep), FS, speaker_mic_m=0.1, max_distance_m=25)
        positions.append(PositionMeasurement(f"c{k}", f.rt60_s, [r.distance_m for r in f.reflections], 0.75))
    out = rank(positions, rooms)
    assert out["status"] == "no_match"
    assert out["non_room"]["best"] == "corridor"


def test_scale_from_taped_room_reproduces_its_size():
    """Scale set from Yew's taped 14.5 x 11.5 m: Yew must come out at that size (+-2%)."""
    trace = json.loads((ROOT / "assets/building/trace_nucleus.json").read_text())
    out = build(trace, {"scale_reference": {"room_id": "nuc-2-yew", "length_m": 14.5, "width_m": 11.5}})
    yew = next(r for r in out["rooms"] if r["room_id"] == "nuc-2-yew")
    xs, ys = [p[0] for p in yew["polygon_m"]], [p[1] for p in yew["polygon_m"]]
    L, W = sorted([max(xs) - min(xs), max(ys) - min(ys)], reverse=True)
    assert L == pytest.approx(14.5, rel=0.02) and W == pytest.approx(11.5, rel=0.02)
    assert out["scale_source"].startswith("measured")
