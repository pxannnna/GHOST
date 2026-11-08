"""Read the phone barometer through phyphox's remote-access REST API.

On the phone: phyphox -> "Pressure" experiment -> menu -> Allow remote access.
It shows a URL like http://192.168.1.23:8080 (Android) or http://192.168.1.23
(iOS). Put that in config/local.json as pressure.phone_url. Phone and laptop
must be on the same network (a phone hotspot works; eduroam often blocks it).

Buffers in the stock Pressure experiment: `pressure` (hPa) and `p_time` (s).
API: https://phyphox.org/docs/remote-interface/api-reference/
"""
from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


class PhyphoxClient:
    def __init__(self, url: str, pressure_buf: str = "pressure", time_buf: str = "p_time", timeout: float = 2.0):
        self.url = url.rstrip("/")
        self.p, self.t = pressure_buf, time_buf
        self.timeout = timeout
        self.last_t: Optional[float] = None

    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.url}{path}", timeout=self.timeout) as r:
            return json.loads(r.read())

    def start(self) -> None:
        self._get("/control?cmd=start")

    def read_new(self) -> Tuple[List[Tuple[float, float]], bool]:
        """New (phone_time_s, pressure_hPa) samples since the last call, and whether measuring."""
        if self.last_t is None:
            q = f"/get?{self.p}=full&{self.t}=full"
        else:
            q = f"/get?{self.p}={self.last_t}|{self.t}&{self.t}={self.last_t}"
        d = self._get(q)
        if d.get("result") is False:
            raise RuntimeError(f"phyphox rejected request: {d}")
        ts = d["buffer"][self.t]["buffer"]
        ps = d["buffer"][self.p]["buffer"]
        out = [(float(t), float(p)) for t, p in zip(ts, ps) if t is not None and p is not None]
        if out:
            self.last_t = out[-1][0]
        return out, bool(d.get("status", {}).get("measuring", False))


def read_csv(path: Path) -> Iterator[Tuple[float, float]]:
    """phyphox CSV export: columns 'Time (s)' and 'Pressure (hPa)' (comma or tab, any order)."""
    text = Path(path).read_text()
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    rows = csv.reader(text.splitlines(), dialect)
    header = [h.strip().strip('"').lower() for h in next(rows)]
    ti = next(i for i, h in enumerate(header) if h.startswith("time"))
    pi = next(i for i, h in enumerate(header) if "pressure" in h or "hpa" in h)
    for r in rows:
        if len(r) > max(ti, pi) and r[ti].strip():
            yield float(r[ti]), float(r[pi])
