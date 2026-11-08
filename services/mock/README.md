# Simulated signals

Run `python -m services.mock.producer` beside the Hub to publish simulated
pressure, floor, echo, room and Wi-Fi events. Use `--floor 0` (or another
surveyed floor) to change the mock result. The default is floor 2.

The web demo at `/?mock=1` has a button that sends a simulated
`gesture.detected` event on demand, so you can test arming and cooldown.
See [local demo instructions](../../web/README.md).
