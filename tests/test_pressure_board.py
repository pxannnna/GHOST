import json
from types import SimpleNamespace

import pytest

pytest.importorskip("pymavlink")
from services.pressure import board, survey  # noqa: E402


class FakeConn:
    """Stands in for a pymavlink connection: yields scripted messages, records the commands we send."""
    def __init__(self, msgs, heartbeat=True):
        self.msgs, self.sent, self.heartbeat = list(msgs), [], heartbeat
        self.target_system, self.target_component = 1, 0
        self.mav = SimpleNamespace(command_long_send=lambda *args: self.sent.append(args))

    def wait_heartbeat(self, timeout=None):
        return object() if self.heartbeat else None

    def recv_match(self, type=None, blocking=True, timeout=None):
        if not blocking:
            return None                       # nothing buffered in this fake
        return self.msgs.pop(0) if self.msgs else None

    def close(self):
        pass


def pressure_msg(ms, hpa, cdeg):
    return SimpleNamespace(time_boot_ms=ms, press_abs=hpa, temperature=cdeg)


def test_decode_pressure_units():
    assert board.decode_pressure(pressure_msg(12500, 1007.236, 1350)) == (12.5, 1007.236, 13.5)


def test_find_port_prefers_the_ardupilot_board_and_the_cu_device(monkeypatch):
    ports = [SimpleNamespace(device="/dev/tty.usbmodem1101", manufacturer="ArduPilot", product="StellarH7V2", description=""),
             SimpleNamespace(device="/dev/cu.usbmodem1101", manufacturer="ArduPilot", product="StellarH7V2", description=""),
             SimpleNamespace(device="/dev/cu.Bluetooth-Incoming-Port", manufacturer=None, product=None, description="n/a")]
    monkeypatch.setattr(board.list_ports, "comports", lambda: ports)
    assert board.find_port() == "/dev/cu.usbmodem1101"
    assert board.find_port("/dev/cu.chosen") == "/dev/cu.chosen"      # an explicit choice always wins


def test_find_port_none_when_no_board(monkeypatch):
    monkeypatch.setattr(board.list_ports, "comports", lambda: [])
    monkeypatch.setattr(board.glob, "glob", lambda pattern: [])
    assert board.find_port() is None


def test_client_asks_for_pressure_at_the_requested_rate_and_reads_it():
    conn = FakeConn([pressure_msg(1000, 1007.2, 1350), pressure_msg(1200, 1007.21, 1351)])
    c = board.BoardClient("/dev/cu.fake", rate_hz=5, conn_factory=lambda p: conn).connect(settle_s=0)
    (_, _, command, _, msg_id, interval_us, *_), = conn.sent
    assert command == 511 and msg_id == 29 and interval_us == 200000    # SET_MESSAGE_INTERVAL, SCALED_PRESSURE, 5 Hz
    assert c.read() == (1.0, 1007.2, 13.5) and c.read()[1] == pytest.approx(1007.21)
    assert c.read(timeout=0.1) is None                                  # nothing more: caller can react


def test_client_raises_when_the_board_is_silent():
    conn = FakeConn([], heartbeat=False)
    with pytest.raises(board.BoardNotFound):
        board.BoardClient("/dev/cu.fake", conn_factory=lambda p: conn).connect(timeout=0.1, settle_s=0)


def test_survey_order_goes_up_and_back_down():
    assert survey.visit_order(["0", "1", "2", "3"]) == ["0", "1", "2", "3", "2", "1", "0"]
    assert survey.visit_order(["0", "1"], round_trip=False) == ["0", "1"]


def test_round_trip_cancels_linear_drift():
    """Pressure drifting down 1 Pa per visit shifts every floor equally in an up-and-down average."""
    true = {"0": 101322.0, "1": 101250.5, "2": 101191.0, "3": 101121.7}   # Pa
    order, drift, visits = survey.visit_order(list(true)), 0.0, {}
    for f in order:
        visits.setdefault(f, []).append((true[f] - drift) / 100)
        drift += 1.0
    r = survey.combine_visits(visits)
    steps = [round((r[a] - r[b]) * 100, 1) for a, b in (("0", "1"), ("1", "2"), ("2", "3"))]
    assert steps == [71.5, 59.5, 69.3]                                    # the true steps, drift gone


def test_write_survey_keeps_the_rest_of_local_json(tmp_path):
    p = tmp_path / "local.json"
    p.write_text(json.dumps({"echolocation": {"input_device": "MacBook Pro Microphone"}, "pressure": {"phone_url": "http://x"}}))
    survey.write_survey(p, {"0": 1007.1, "1": 1006.4}, "0", "test")
    out = json.loads(p.read_text())
    assert out["echolocation"]["input_device"] == "MacBook Pro Microphone" and out["pressure"]["phone_url"] == "http://x"
    assert out["pressure"]["survey"]["readings_hpa"] == {"0": 1007.1, "1": 1006.4}


class BacklogConn(FakeConn):
    """Readings pile up while nobody reads; flush() must drop them."""
    def __init__(self):
        super().__init__([])
        self.backlog = [pressure_msg(i, 1013.0, 1300) for i in range(5)]      # the old floor

    def recv_match(self, type=None, blocking=True, timeout=None):
        if self.backlog:
            return self.backlog.pop(0)
        return pressure_msg(99, 1012.0, 1300) if blocking else None            # fresh reading, new floor


def test_flush_drops_readings_buffered_while_walking():
    c = board.BoardClient("/dev/cu.fake", conn_factory=lambda p: BacklogConn()).connect(settle_s=0)
    c.flush()
    assert c.read()[1] == 1012.0


def test_survey_collect_ignores_the_old_floors_backlog():
    c = board.BoardClient("/dev/cu.fake", conn_factory=lambda p: BacklogConn()).connect(settle_s=0)
    vals = survey.collect(c, 0.2)
    assert vals and set(vals) == {1012.0}


def test_walkscore_scores_only_settled_labelled_rows(tmp_path):
    from services.pressure import walkscore
    p = tmp_path / "walk.csv"
    rows = [walkscore.COLUMNS,
            ["1", "1", "1007.2", "0", "settled", "0.0", "0"], ["2", "2", "1007.2", "0", "settled", "0.0", "0"],
            ["3", "3", "1006.9", "0", "transition", "2.0", "1"],           # walking: not scored
            ["4", "4", "1006.5", "1", "settled", "5.9", "1"], ["5", "5", "1006.5", "0", "settled", "5.0", "1"],
            ["6", "6", "1006.0", "2", "settled", "11.0", ""]]                # no true floor given: ignored
    p.write_text("\n".join(",".join(r) for r in rows))
    s = walkscore.summarize(p)
    assert s["rows"] == 6 and s["labelled"] == 5
    assert s["floors"]["0"] == {"n": 2, "settled": 2, "correct": 2, "transition": 0, "other": 0}
    assert s["floors"]["1"] == {"n": 3, "settled": 2, "correct": 1, "transition": 1, "other": 0}
    assert "overall: 3/4" in walkscore.format_summary(s)
