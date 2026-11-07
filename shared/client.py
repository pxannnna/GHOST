"""Producer-side event client.

`EventClient.emit()` never blocks acquisition: events go onto a bounded queue
and a background thread POSTs them to the hub with retries. If the hub is down
the producer keeps running; oldest queued events are dropped when the queue is
full (and the drop count is reported in source.status detail).
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from shared.schema import utc_now_iso, validate_event

DEFAULT_HUB = os.environ.get("HUB_URL", "http://127.0.0.1:8000")


class EventClient:
    def __init__(self, source: str, mode: str = "live", session_id: Optional[str] = None,
                 hub_url: str = DEFAULT_HUB, max_queue: int = 2000, validate: bool = True):
        self.source = source
        self.mode = mode
        self.session_id = session_id or os.environ.get("SESSION_ID", "session-001")
        self.hub_url = hub_url.rstrip("/")
        self.validate = validate
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=max_queue)
        self.dropped = 0
        self.sent = 0
        self.hub_ok = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"emit-{source}", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------- public
    def emit(self, type_: str, payload: Dict[str, Any], timestamp_utc: Optional[str] = None,
             mode: Optional[str] = None) -> Dict[str, Any]:
        with self._seq_lock:
            seq = self._seq
            self._seq += 1
        ev = {
            "schema_version": 1,
            "session_id": self.session_id,
            "source": self.source,
            "type": type_,
            "timestamp_utc": timestamp_utc or utc_now_iso(),
            "sequence": seq,
            "mode": mode or self.mode,
            "payload": payload,
        }
        if self.validate:
            validate_event(ev)  # fail loudly in the producer during development
        try:
            self._q.put_nowait(ev)
        except queue.Full:
            try:
                self._q.get_nowait()
                self.dropped += 1
            except queue.Empty:
                pass
            self._q.put_nowait(ev)
        return ev

    def status(self, component: str, state: str, detail: str = "",
               last_sample_age_ms: Optional[float] = None) -> None:
        if self.dropped:
            detail = f"{detail} (hub queue dropped {self.dropped})".strip()
        self.emit("source.status", {
            "component": component, "state": state, "detail": detail,
            "last_sample_age_ms": last_sample_age_ms,
        })

    def close(self, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while not self._q.empty() and time.time() < deadline:
            time.sleep(0.05)
        self._stop.set()

    # ------------------------------------------------------------- worker
    def _run(self) -> None:
        backoff = 0.25
        pending: Optional[Dict[str, Any]] = None
        while not self._stop.is_set():
            if pending is None:
                try:
                    pending = self._q.get(timeout=0.2)
                except queue.Empty:
                    continue
            try:
                self._post(pending)
                self.sent += 1
                self.hub_ok = True
                pending = None
                backoff = 0.25
            except urllib.error.HTTPError as e:
                # 4xx = our bug (malformed); don't retry forever.
                body = e.read().decode(errors="replace")[:300]
                print(f"[{self.source}] hub rejected {pending['type']}: {e.code} {body}")
                pending = None
            except (urllib.error.URLError, OSError, TimeoutError):
                self.hub_ok = False
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)

    def _post(self, ev: Dict[str, Any]) -> None:
        req = urllib.request.Request(
            f"{self.hub_url}/events", data=json.dumps(ev).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=2.0) as r:
            r.read()
