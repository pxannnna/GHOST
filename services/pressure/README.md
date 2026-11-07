Owner: Anna (phone barometer -> floor). See docs/KICKOFF.md §2 and §6.

# Phone barometer → floor

Floors used: **0 = G, 1, 2, 3** (survey in `config/default.json`, 7 Nov 2026). LG is off limits and not modelled.

1. Phone: phyphox → **Pressure** experiment → ⋮ → **Allow remote access**. Note the URL.
2. Phone and laptop on the same network (phone hotspot is safest; eduroam may block it).
3. `config/local.json`: `{"pressure": {"phone_url": "http://<phone-ip>:8080"}}` (iOS: no `:8080`).
4. Stand on **G**: `python -m services.pressure.live --zero-floor 0` (or type `z` + Enter while running).
5. Walk; the terminal prints floor changes and the hub receives `pressure.sample` + `floor.estimate`.

Only pressure *differences* are used: we zero on a known floor and compare with the surveyed per-floor
differences (60–70 Pa apart). Weather moves absolute pressure by ~100 Pa/day, so **re-zero before the demo**.
Motion (stairs/lift) is detected from vertical speed → status `transition`; `uncertain` when >1.5 m from any floor.

Fallback: export a CSV from phyphox and `python -m services.pressure.live --csv walk.csv --zero-floor 0` (mode = replay).
