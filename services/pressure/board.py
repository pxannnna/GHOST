"""Air pressure from a flight-controller board plugged into the laptop (MAVLink over USB).

Tested on the StingBee StellarH7V2 running ArduPilot, which appears as a USB serial port. After a
power-up it only sends a heartbeat; we ask it for the SCALED_PRESSURE message at `rate_hz` (the
request is temporary and resets when the board is unplugged). The port number changes every time the
board is replugged, so the board is found by its USB name instead of a fixed path.

    python -m services.pressure.board          # print readings for 10 s (check the board works)
"""
from __future__ import annotations

import glob
import os
import sys
import time
from typing import Any, Callable, Iterator, Optional, Tuple

os.environ.setdefault("MAVLINK20", "1")  # the board speaks MAVLink 2; set before pymavlink is imported
from pymavlink import mavutil  # noqa: E402
from serial.tools import list_ports  # noqa: E402

SCALED_PRESSURE = 29
REREQUEST_EVERY_S = 10.0


class BoardNotFound(RuntimeError):
    pass


def find_port(preferred: Optional[str] = None) -> Optional[str]:
    """Port of the flight-controller board: the given one, else the first USB device that calls itself
    ArduPilot / StellarH7, else any usbmodem / ttyACM device. Prefers /dev/cu.* over /dev/tty.* on macOS."""
    if preferred:
        return preferred
    named = []
    for p in list_ports.comports():
        text = " ".join(str(x) for x in (p.manufacturer, p.product, p.description)).lower()
        if "ardupilot" in text or "stellarh7" in text:
            named.append(p.device)
    named.sort(key=lambda d: (not d.startswith("/dev/cu."), d))
    if named:
        return named[0]
    generic = sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*"))
    return generic[0] if generic else None


def decode_pressure(msg: Any) -> Tuple[float, float, float]:
    """(board time s, pressure hPa, temperature C) from a SCALED_PRESSURE message."""
    return msg.time_boot_ms / 1000.0, float(msg.press_abs), msg.temperature / 100.0


class BoardClient:
    def __init__(self, port: Optional[str] = None, rate_hz: float = 5.0, baud: int = 115200,
                 conn_factory: Optional[Callable[[str], Any]] = None):
        self.port, self.rate_hz, self.baud = port, rate_hz, baud
        self._factory = conn_factory or (lambda p: mavutil.mavlink_connection(p, baud=self.baud))
        self.conn: Any = None
        self._last_request = 0.0

    def connect(self, timeout: float = 10.0, settle_s: float = 1.5) -> "BoardClient":
        port = find_port(self.port)
        if not port:
            raise BoardNotFound("no flight-controller board found: plug it in and check `ls /dev/cu.*`")
        self.port = port
        self.conn = self._factory(port)
        if self.conn.wait_heartbeat(timeout=timeout) is None:
            raise BoardNotFound(f"{port}: no heartbeat from the board within {timeout:.0f} s")
        self.request_rate()
        # The board queues a few seconds of readings while nobody listens and dumps them in one burst when the
        # port opens (seen: ~17 s of two-minute-old pressure). Read and discard for `settle_s` so none are used.
        self.flush(settle_s=settle_s)
        return self

    def request_rate(self) -> None:
        interval_us = int(1e6 / self.rate_hz)
        self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component,
                                        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                        SCALED_PRESSURE, interval_us, 0, 0, 0, 0, 0)
        self._last_request = time.time()

    def read(self, timeout: float = 2.0) -> Optional[Tuple[float, float, float]]:
        """Next pressure reading, or None if nothing arrived within `timeout` seconds."""
        if time.time() - self._last_request > REREQUEST_EVERY_S:
            self.request_rate()
        msg = self.conn.recv_match(type="SCALED_PRESSURE", blocking=True, timeout=timeout)
        return None if msg is None else decode_pressure(msg)

    def flush(self, settle_s: float = 0.0) -> None:
        """Throw away readings that piled up while nobody was reading (e.g. while walking between floors).
        With `settle_s`, also keep reading and discarding for that long, to swallow a late burst."""
        port = getattr(self.conn, "port", None)
        if hasattr(port, "reset_input_buffer"):
            port.reset_input_buffer()
        while self.conn.recv_match(blocking=False) is not None:
            pass
        t_end = time.time() + settle_s
        while time.time() < t_end:
            self.conn.recv_match(blocking=True, timeout=min(0.2, max(t_end - time.time(), 0.01)))

    def close(self) -> None:
        try:
            if self.conn is not None:
                self.conn.close()
        finally:
            self.conn = None


def samples(port: Optional[str], rate_hz: float, status: Callable[[str, str], None]) -> Iterator[Tuple[float, float, float]]:
    """Yields (laptop_unix_time, board_time_s, pressure_hPa), forever. Reconnects if the cable is knocked
    or the board restarts (the port number may change), reporting the state through `status`."""
    client: Optional[BoardClient] = None
    while True:
        try:
            if client is None:
                client = BoardClient(port, rate_hz).connect()
                status("ok", f"board on {client.port}")
            r = client.read(timeout=2.0)
            if r is None:
                raise TimeoutError("no pressure message for 2 s")
            yield time.time(), r[0], r[1]
        except Exception as e:  # unplugged, restarting, busy port: keep trying
            status("offline", f"board: {e.__class__.__name__}: {e}")
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            client = None
            time.sleep(1.0)


def main() -> None:
    from shared.config import load_config
    cfg = load_config()["pressure"]
    port = cfg.get("serial_port")
    print("looking for the board...", find_port(port))
    t_end, n, vals = time.time() + 10, 0, []
    for now, t_board, hpa in samples(port, cfg.get("board_rate_hz", 5.0), lambda s, d: print(f"[{s}] {d}")):
        n += 1
        vals.append(hpa)
        if n % 5 == 1:
            print(f"{hpa:.3f} hPa   (board time {t_board:.1f} s)")
        if now > t_end:
            break
    if vals:
        import statistics
        print(f"{len(vals)} readings in 10 s, mean {statistics.mean(vals):.3f} hPa, noise {statistics.pstdev(vals) * 100:.2f} Pa")
    else:
        sys.exit("no readings")


if __name__ == "__main__":
    main()
