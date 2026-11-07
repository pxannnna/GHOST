import numpy as np
import pytest

from shared.config import load_config
from services.pressure.floor import FloorEstimator
from services.pressure.phyphox import read_csv

SURVEY = load_config()["pressure"]["survey"]


def make():
    return FloorEstimator(SURVEY, pa_per_m=12.0, dwell_s=3.0, hysteresis_m=0.6)


def feed(est, t0, seconds, pa, hz=5, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    st = None
    for i in range(int(seconds * hz)):
        st = est.update(t0 + i / hz, pa + rng.normal(0, noise))
    return st, t0 + seconds


def test_uncalibrated_until_zeroed():
    est = make()
    st, _ = feed(est, 0, 4, 101300.0)
    assert st.status == "uncalibrated" and st.floor_id is None


def test_each_floor_after_zero_with_weather_offset():
    """Absolute pressure today differs from the survey day by +250 Pa; only deltas matter."""
    est = make()
    offset = 250.0
    hpa = {f: v for f, v in SURVEY["readings_hpa"].items()}
    t = 0.0
    _, t = feed(est, t, 3, hpa["0"] * 100 + offset, noise=3)
    est.zero_from_window("0")
    for f in ["1", "2", "3", "2", "0"]:
        st, t = feed(est, t, 6, hpa[f] * 100 + offset, noise=3, seed=int(f))
        assert st.floor_id == f, (f, st)
        assert st.status == "settled"


def test_zero_on_other_floor():
    est = make()
    hpa = SURVEY["readings_hpa"]
    _, t = feed(est, 0, 3, hpa["2"] * 100 - 80)
    est.zero_from_window("2")
    st, _ = feed(est, t, 6, hpa["3"] * 100 - 80)
    assert st.floor_id == "3"


def test_motion_is_transition_and_hysteresis_holds_floor():
    est = make()
    hpa = SURVEY["readings_hpa"]
    _, t = feed(est, 0, 3, hpa["0"] * 100)
    est.zero_from_window("0")
    _, t = feed(est, t, 5, hpa["0"] * 100)
    # riding the lift: pressure ramps quickly
    st = None
    for i in range(15):
        st = est.update(t + i / 5, hpa["0"] * 100 - i * 5)
    assert st.status == "transition"
    # stop just under halfway between 0 and 1: hysteresis keeps floor 0, flags uncertainty not a jump
    half = (hpa["0"] - hpa["1"]) * 100 * 0.45
    st, _ = feed(est, t + 3, 6, hpa["0"] * 100 - half)
    assert st.floor_id == "0"


def test_unknown_floor_rejected():
    with pytest.raises(ValueError):
        make().zero(101300.0, "LG")


def test_read_csv(tmp_path):
    p = tmp_path / "walk.csv"
    p.write_text('"Time (s)","Pressure (hPa)"\n0.0,1013.2\n0.2,1013.21\n')
    assert list(read_csv(p)) == [(0.0, 1013.2), (0.2, 1013.21)]
