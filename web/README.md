# GHOST local demo

Run these commands from the repository root in Windows PowerShell. The browser
uses plain HTML, CSS and JavaScript served by the same process as the Hub.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn services.hub.app:app --host 127.0.0.1 --port 8000
```

Start the simulated producer in another terminal:

```powershell
.\.venv\Scripts\python.exe -m services.mock.producer
```

On Linux/macOS, use `make web` and `make mock` in separate terminals after setup.
Open <http://127.0.0.1:8000/?mock=1>. Select the **Floor**, **Room** and
**Model** slides to inspect the pressure trace, echo preview, ranked matches and
building highlight. On **Gesture**, click **Arm gesture** and **Simulate gesture**
to advance to **Results**. A repeat during the cooldown is logged as ignored.
Use the arrow keys or presenter buttons for manual navigation.

Open <http://127.0.0.1:8000/> for the same dashboard without the simulation
button. Stop the mock producer before connecting live producers. Panels label
their source mode and mark old signals stale. The WebSocket sends the current
snapshot on connection, so a newly opened or reconnected tab follows the
current slide.

`building3d/index.js` provides the PDF-based Nucleus model using a locally bundled
Three.js renderer. Select a floor, switch between 3D and plan views, adjust layer
spacing, or inspect a room. The estimated floor and known candidate IDs are
highlighted; unmapped IDs are reported rather than assigned to arbitrary rooms.
Mock rankings use the named rooms in the plan but remain synthetic.
See `building3d/README.md` for sources, limitations and regeneration, and
`docs/KICKOFF.md` §4.3 for the component interface.
