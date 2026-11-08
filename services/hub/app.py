"""Event hub (spec §4, §7). Owner: Shangran.

POST /events   producers submit events (validated, deduplicated, logged)
GET  /health   liveness
GET  /state    reconnect snapshot for the UI
WS   /ws       snapshot on connect, then every accepted event
POST /demo/*   presenter controls (next view, arm gesture, manual selection)

The hub is the single owner of demo state, so a gesture advances the view
exactly once no matter how many browser tabs are open.

Run:  make hub     (SESSION_ID=session-002 make hub to start a new log)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from contextlib import asynccontextmanager
from services.wifi.live.api import router as wifi_router, controller as wifi_controller
from services.acoustics.web_api import router as acoustic_router, controller as acoustic_controller
from services.pressure.web_api import router as pressure_router, controller as pressure_controller

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from shared.config import DATA_DIR, ROOT, load_config
from shared.schema import iso_from_unix, utc_now_iso, validate_event

CFG = load_config()
SESSION_ID = os.environ.get("SESSION_ID", "session-001")
VIEWS = list(CFG["demo"]["views"])
GESTURE_COOLDOWN_S = float(CFG["wifi"]["gesture"]["cooldown_s"])

@asynccontextmanager
async def lifespan(app):
    acoustic_controller.publisher = HUB.ingest
    pressure_controller.publisher = HUB.ingest
    try:
        yield
    finally:
        await acoustic_controller.shutdown()
        await wifi_controller.shutdown()
        await pressure_controller.shutdown()

app = FastAPI(title="GHOST hub", lifespan=lifespan)
app.include_router(wifi_router)
app.include_router(acoustic_router)
app.include_router(pressure_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


class Hub:
    def __init__(self) -> None:
        self.session_dir = DATA_DIR / "sessions" / SESSION_ID
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.session_dir / "events.jsonl"
        self._log = self.log_path.open("a", buffering=1)
        self.seen: Set[Tuple[str, str, int, str]] = set()
        self.seen_order: Deque[Tuple[str, str, int, str]] = deque()
        self.clients: Set[WebSocket] = set()
        self.hub_seq = 0
        self.rejected = 0
        self.accepted = 0

        b = CFG["building"]
        self.demo: Dict[str, Any] = {
            "current_view": VIEWS[0],
            "selected_building": b["label"],
            "selected_room": b.get("configured_room"),
            "selection_source": "configured",
            "gesture_armed": False,
            "last_trigger": None,
        }
        self.last_gesture_action = 0.0
        self.calibrating: Set[str] = set()
        self.floor_status: Optional[str] = None

        # Snapshot state (bounded histories)
        self.status: Dict[str, Dict[str, Any]] = {}       # key: source/component
        self.last_by_source: Dict[str, Dict[str, Any]] = {}
        self.latest: Dict[str, Dict[str, Any]] = {}       # key: event type
        self.signatures: Deque[Dict[str, Any]] = deque(maxlen=20)
        self.acoustic: Deque[Dict[str, Any]] = deque(maxlen=40)
        self.gestures: Deque[Dict[str, Any]] = deque(maxlen=30)
        self.pressure_hist: Deque[List[float]] = deque(maxlen=600)
        self.wifi_hist: Deque[List[float]] = deque(maxlen=600)
        self.replay: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------ ingest
    async def ingest(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        ev = validate_event(raw).model_dump()
        key = (ev["session_id"], ev["source"], ev["sequence"], ev["timestamp_utc"])
        if key in self.seen:
            return {"accepted": False, "duplicate": True}
        self.seen.add(key)
        self.seen_order.append(key)
        if len(self.seen_order) > 50_000:
            self.seen.discard(self.seen_order.popleft())

        received = time.time()
        record = {**ev, "received_utc": iso_from_unix(received), "received_unix": received}
        self._log.write(json.dumps(record) + "\n")
        self.accepted += 1
        self._apply(record)
        await self.broadcast({"kind": "event", "event": record})

        if ev["type"] == "gesture.detected":
            await self._on_gesture(record)
        return {"accepted": True, "duplicate": False}

    def _apply(self, r: Dict[str, Any]) -> None:
        t, p = r["type"], r["payload"]
        self.latest[t] = r
        self.last_by_source[r["source"]] = {
            "received_unix": r["received_unix"], "mode": r["mode"], "type": t}
        if t == "source.status":
            k = f"{r['source']}/{p['component']}"
            self.status[k] = {**p, "source": r["source"], "mode": r["mode"],
                              "received_unix": r["received_unix"]}
            if p["state"] == "calibrating":
                self.calibrating.add(k)
            else:
                self.calibrating.discard(k)
        elif t == "aircraft.signature":
            self.signatures.append(r)
        elif t == "acoustic.measurement":
            self.acoustic.append(r)
        elif t == "pressure.sample" and p.get("relative_height_m") is not None:
            self.pressure_hist.append([r["received_unix"], p["relative_height_m"]])
        elif t == "wifi.features":
            self.wifi_hist.append([r["received_unix"], p["motion_score"]])
        elif t == "floor.estimate":
            self.floor_status = p["status"]
        elif t == "replay.progress":
            self.replay = {**p, "received_unix": r["received_unix"]}

    # ------------------------------------------------------------ demo
    def gesture_block_reason(self) -> Optional[str]:
        if not self.demo["gesture_armed"]:
            return "not armed"
        if self.calibrating:
            return "calibration in progress: " + ", ".join(sorted(self.calibrating))
        if self.floor_status == "transition":
            return "floor transition in progress"
        if time.time() - self.last_gesture_action < GESTURE_COOLDOWN_S:
            return "cooldown"
        return None

    async def _on_gesture(self, r: Dict[str, Any]) -> None:
        reason = self.gesture_block_reason()
        if reason is None and r["payload"]["gesture"] != "next":
            reason = "unsupported gesture"
        entry = {"received_unix": r["received_unix"], "score": r["payload"]["score"],
                 "gesture": r["payload"]["gesture"], "mode": r["mode"],
                 "acted": reason is None, "ignored_reason": reason}
        self.gestures.append(entry)
        if reason is None:
            self.last_gesture_action = time.time()
            await self.advance(trigger=f"gesture ({r['mode']})", mode=r["mode"])
        await self.broadcast({"kind": "gesture_log", "entry": entry})

    async def advance(self, trigger: str, mode: str = "live") -> None:
        i = VIEWS.index(self.demo["current_view"])
        await self.set_demo(current_view=VIEWS[(i + 1) % len(VIEWS)], last_trigger=trigger, mode=mode)

    async def set_demo(self, mode: str = "live", **changes: Any) -> None:
        self.demo.update(changes)
        await self.emit_own("demo.state", dict(self.demo), mode=mode)

    async def emit_own(self, type_: str, payload: Dict[str, Any], mode: str = "live") -> None:
        ev = {"schema_version": 1, "session_id": SESSION_ID, "source": "hub", "type": type_,
              "timestamp_utc": utc_now_iso(), "sequence": self.hub_seq, "mode": mode,
              "payload": payload}
        self.hub_seq += 1
        await self.ingest(ev)

    # ------------------------------------------------------------ output
    def snapshot(self) -> Dict[str, Any]:
        return {
            "session_id": SESSION_ID,
            "server_unix": time.time(),
            "stale_after_ms": CFG["hub"]["stale_after_ms"],
            "demo": self.demo,
            "gesture_block_reason": self.gesture_block_reason(),
            "status": self.status,
            "last_by_source": self.last_by_source,
            "latest": self.latest,
            "signatures": list(self.signatures),
            "acoustic_measurements": list(self.acoustic),
            "gestures": list(self.gestures),
            "pressure_hist": list(self.pressure_hist),
            "wifi_hist": list(self.wifi_hist),
            "replay": self.replay,
            "config": {
                "views": VIEWS,
                "building": CFG["building"],
                "pressure_survey": CFG["pressure"]["survey"],
            },
            "counters": {"accepted": self.accepted, "rejected": self.rejected},
        }

    async def broadcast(self, msg: Dict[str, Any]) -> None:
        if not self.clients:
            return
        data = json.dumps({**msg, "server_unix": time.time(),
                           "gesture_block_reason": self.gesture_block_reason()})
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


HUB = Hub()


@app.post("/events", status_code=202)
async def post_event(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    try:
        return await HUB.ingest(body)
    except (ValidationError, ValueError) as e:
        HUB.rejected += 1
        raise HTTPException(status_code=422, detail=str(e)[:2000])


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "session_id": SESSION_ID, "accepted": HUB.accepted,
            "rejected": HUB.rejected, "clients": len(HUB.clients), "log": str(HUB.log_path)}


@app.get("/state")
async def state() -> Dict[str, Any]:
    return HUB.snapshot()


@app.post("/demo/next")
async def demo_next() -> Dict[str, Any]:
    await HUB.advance(trigger="manual")
    return HUB.demo


@app.post("/demo/view")
async def demo_view(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if body.get("view") not in VIEWS:
        raise HTTPException(422, f"view must be one of {VIEWS}")
    await HUB.set_demo(current_view=body["view"], last_trigger="manual")
    return HUB.demo


@app.post("/demo/armed")
async def demo_armed(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    await HUB.set_demo(gesture_armed=bool(body.get("armed")))
    return HUB.demo


@app.post("/demo/selection")
async def demo_selection(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    src = body.get("selection_source", "manual")
    if src not in ("measured", "configured", "manual"):
        raise HTTPException(422, "bad selection_source")
    await HUB.set_demo(selected_building=body.get("building", HUB.demo["selected_building"]),
                       selected_room=body.get("room", HUB.demo["selected_room"]),
                       selection_source=src)
    return HUB.demo


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    HUB.clients.add(ws)
    try:
        await ws.send_text(json.dumps({"kind": "snapshot", "state": HUB.snapshot()}))
        while True:
            # Keepalive; UI may send pings. Periodic snapshot keeps ages honest.
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=10)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"kind": "tick", "server_unix": time.time(),
                                               "gesture_block_reason": HUB.gesture_block_reason()}))
    except WebSocketDisconnect:
        pass
    finally:
        HUB.clients.discard(ws)


# Register after the API and WebSocket routes so they take precedence.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
