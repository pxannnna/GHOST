"""Publish synthetic signals for the core demo. Run beside the Hub."""
from __future__ import annotations

import argparse
import math
import time

from shared.client import EventClient
from shared.config import load_config


def main() -> None:
    config = load_config()
    survey = config["pressure"]["survey"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", default="2", choices=survey["readings_hpa"])
    args = parser.parse_args()
    floor = args.floor
    height = survey["relative_height_m"][floor]
    pressure = survey["readings_hpa"][floor] * 100
    # Real plan labels, synthetic rankings: no surveyed room dimensions implied.
    rooms = {
        "0": [("alder", "Alder"), ("elm", "Elm")],
        "1": [("oak", "Oak"), ("larch", "Larch")],
        "2": [("hawthorn", "Hawthorn"), ("rowan", "Rowan"), ("yew", "Yew")],
        "3": [("chemistry", "Chemistry teaching laboratory")],
    }
    candidates = [
        {"room_id": room_id, "label": label, "score": score}
        for (room_id, label), score in zip(rooms[floor], [0.92, 0.67, 0.38])
    ]
    client = EventClient("mock", mode="simulated")
    sample = 0
    print(f"Sending simulated floor {floor}, room and Wi-Fi signals to {client.hub_url}.", flush=True)
    try:
        while True:
            wave = math.sin(sample / 6)
            client.emit("pressure.sample", {
                "pressure_pa": round(pressure + 2 * wave, 2),
                "relative_height_m": round(height - wave / 6, 2),
            })
            client.emit("wifi.features", {
                "motion_score": round(0.23 + 0.13 * wave, 2),
                "csi_trace": [round(math.sin(i / 4 + sample / 3) * math.cos(i / 11), 4)
                              for i in range(64)],
                "packet_rate_hz": 74 + sample % 8,
                "sample_age_ms": 0,
            })
            if sample % 4 == 0:
                measurement_id = f"mock-{sample}"
                client.status("demo sensors", "ok", "Synthetic pressure, echoes and Wi-Fi")
                client.emit("floor.estimate", {
                    "floor_id": floor, "reference_floor": survey["reference_floor"],
                    "calibration_id": "mock-survey", "status": "settled",
                })
                client.emit("acoustic.measurement", {
                    "measurement_id": measurement_id, "position_label": "Synthetic sweep",
                    "rt60_s": 0.68, "reflection_distances_m": [2.6, 3.8, 5.1],
                    "impulse_response_preview": [round(math.sin(i * 1.9) * math.exp(-i / 14), 4)
                                                 for i in range(80)],
                })
                client.emit("room.estimate", {
                    "status": "supported", "floor_id": floor, "method": "synthetic echo match",
                    "estimated_dims_m": {"length": 8.2, "width": 5.6, "height": 3.1},
                    "candidates": candidates, "supporting_measurement_ids": [measurement_id],
                })
            sample += 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
