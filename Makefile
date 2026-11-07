PY := .venv/bin/python
SESSION ?= session-001
export SESSION_ID := $(SESSION)

.PHONY: hub web mock echo-measure room-live pressure-live wifi-live replay test

hub:            ## Shangran
	$(PY) -m uvicorn services.hub.app:app --host 127.0.0.1 --port 8000

web: hub        ## Shangran — the Hub also serves the demo at /

mock:           ## Shangran — simulated producer for all event types
	$(PY) -m services.mock.producer

echo-measure:   ## Anna — one sweep at one position: make echo-measure ROOM=demo POS=P1
	$(PY) -m services.acoustics.measure --room $(ROOM) --position $(POS)

room-live:      ## Anna — floor + echoes -> ranked rooms
	$(PY) -m services.acoustics.live

wifi-live:      ## Kameran + Elisa
	$(PY) -m services.wifi.live

pressure-live:  ## Anna — phyphox poll -> floor
	$(PY) -m services.pressure.live

replay:         ## make replay SESSION=session-001
	$(PY) -m services.hub.replay $(SESSION)

test:
	$(PY) -m pytest -q tests
