PY := .venv/bin/python
SESSION ?= session-001
export SESSION_ID := $(SESSION)

.PHONY: hub web mock aircraft-log audio-live audio-analyse wifi-live pressure-live replay test

hub:            ## Person C
	$(PY) -m uvicorn services.hub.app:app --host 127.0.0.1 --port 8000

web:            ## Person D
	cd web && npm run dev

mock:           ## Person C — simulated producer for all event types
	$(PY) -m services.mock.producer

aircraft-log:   ## Person A — start at H0 and never stop
	$(PY) -m services.aircraft.tracklog

audio-live:     ## Person A
	$(PY) -m services.aircraft.live

audio-analyse:  ## Person A — make audio-analyse WAV=data/audio/x.wav
	$(PY) -m services.aircraft.analyse $(WAV)

wifi-live:      ## Person B
	$(PY) -m services.wifi.live

pressure-live:  ## Person B/C — phyphox poll
	$(PY) -m services.pressure.live

replay:         ## make replay SESSION=session-001
	$(PY) -m services.hub.replay $(SESSION)

test:
	$(PY) -m pytest -q tests
