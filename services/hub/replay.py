"""Deterministic session replay (spec §7, §12). Owner: Person C.

Re-posts a saved session's producer events to the running hub with
mode="replay" and session_id="replay-of-<id>". Original timestamp_utc values
are preserved; pacing follows the original *receipt* gaps (÷ --speed).
Hub-generated events (demo.state etc.) are skipped: the hub regenerates them.

    make replay SESSION=session-001
    python -m services.hub.replay session-001 --speed 4 --only wifi,aircraft
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from shared.client import EventClient
from shared.config import DATA_DIR


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--only", default="", help="comma-separated sources to include")
    args = ap.parse_args()

    path = DATA_DIR / "sessions" / args.session / "events.jsonl"
    if not path.exists():
        sys.exit(f"no such session log: {path}")
    only = {s for s in args.only.split(",") if s}
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["source"] == "hub" or r["type"] in ("demo.state", "replay.progress"):
            continue
        if only and r["source"] not in only:
            continue
        events.append(r)
    events.sort(key=lambda r: r["received_unix"])
    if not events:
        sys.exit("nothing to replay")

    replay_id = f"replay-of-{args.session}"
    progress = EventClient("hub", mode="replay", session_id=replay_id)
    clients = {}
    t0 = events[0]["received_unix"]
    start = time.time()
    total = len(events)
    print(f"replaying {total} events from {path} at {args.speed}x")
    for i, r in enumerate(events):
        due = start + (r["received_unix"] - t0) / args.speed
        delay = due - time.time()
        if delay > 0:
            time.sleep(delay)
        c = clients.get(r["source"])
        if c is None:
            c = clients[r["source"]] = EventClient(r["source"], mode="replay",
                                                   session_id=replay_id, validate=False)
        c.emit(r["type"], r["payload"], timestamp_utc=r["timestamp_utc"])
        if i % 25 == 0 or i == total - 1:
            progress.emit("replay.progress", {"replay_of": args.session, "position": i + 1,
                                              "total": total, "finished": i == total - 1})
    for c in list(clients.values()) + [progress]:
        c.close(timeout=5)
    print("replay finished")


if __name__ == "__main__":
    main()
