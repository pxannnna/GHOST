PY := .venv/bin/python
SESSION ?= session-001
export SESSION_ID := $(SESSION)

.PHONY: hub web mock echo-measure room-live pressure-live pressure-survey wifi-live replay test

hub:            ## Shangran
	$(PY) -m uvicorn services.hub.app:app --host 127.0.0.1 --port 8000

web:            ## Shangran
	cd web && npm run dev

mock:           ## Shangran — simulated producer for all event types
	$(PY) -m services.mock.producer

echo-measure:   ## Anna — one sweep at one position: make echo-measure ROOM=demo POS=P1
	$(PY) -m services.acoustics.measure --room $(ROOM) --position $(POS)

room-live:      ## Anna — floor + echoes -> ranked rooms
	$(PY) -m services.acoustics.live

wifi-live:      ## Kameran + Elisa
	$(PY) -m services.wifi.live

pressure-live:  ## Anna — barometer board (USB) -> floor
	$(PY) -m services.pressure.live

pressure-survey: ## Anna — re-survey the four floors with the board (stand on each floor when asked)
	$(PY) -m services.pressure.survey

replay:         ## make replay SESSION=session-001
	$(PY) -m services.hub.replay $(SESSION)

test:
	$(PY) -m pytest -q tests
