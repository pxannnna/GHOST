# Standalone Wi-Fi motion demo

This Windows application uses one XIAO ESP32-C6 receiver and one 2.4 GHz phone
hotspot. The board runs official ESP-Radar 0.3.4. The application guides calibration,
records empty-room and walking trials, saves a comparison, and flashes a green
indicator for one second on a new positive motion episode.

This is a motion demo, not a gesture classifier. It runs independently of the
GHOST web application and event hub. It does not emit `gesture.detected` events.

## Requirements

- Windows 10/11 and Python 3.12 from python.org, including Tcl/Tk.
- XIAO ESP32-C6, an attached antenna as appropriate for the board, and a USB data cable.
- A stationary 2.4 GHz WPA2 phone hotspot. Keep it enabled throughout the experiment.
- Internet access for the first dependency installation. Normal operation uses
  the local hotspot; Internet access through the hotspot is not required.
- A local firmware package at `firmware/xiao/.artifacts/manifest.json`.
  See [firmware setup](../../firmware/xiao/README.md) if it is missing.

## Start

Double-click **`services/wifi/launch-demo.cmd`** in File Explorer. It creates the
Python environment if necessary, installs the pinned dependencies, and opens
the window. PowerShell script permission is scoped to that launcher process.

Alternatively, from the repository root in a VS Code terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File services/wifi/setup-demo.ps1 -Launch
```

For a foreground console with tracebacks:

```powershell
.\.venv\Scripts\python.exe -m services.wifi.demo
```

## First run and experiment

1. Close other serial monitors and the earlier CSI demo. Plug in the board.
   The app detects native Espressif USB devices (`303A:1001`); it does not assume
   a COM number. With multiple devices, select the intended one.
2. If the window says **Firmware setup required**, click **Install / update
   firmware**. Confirm the selected port and wait for installation and restart.
   The installer verifies file hashes and targets only the ESP32-C6 chip type.
3. Enter the hotspot name and password, then click **Connect hotspot**. Wait
   for verified firmware, a connected hotspot, and fresh radar reports.
   Credentials are not written to application files. The ESP-IDF Wi-Fi driver
   may retain network settings in board NVS. Quotes, backslashes and control
   characters are not supported in hotspot credentials by this demo.
4. Fix the phone and board in place. Everyone should leave the test area.
   Tick the empty-area confirmation and click **Start calibration + empty test**.
5. Follow the **5-second countdown**, **30-second calibration**, and automatic
   **60-second empty recording**. Stay away until **Empty test complete**.
6. Prepare beside the area and click **Ready: start walking countdown**. Wait
   for the countdown to finish, the sound, and **START WALKING**. Walk naturally
   between the devices for 60 seconds. Stop when **STOP WALKING** appears.
7. Click **Open results** for the comparison. The green indicator continues in
   live mode using the same calibration. It lights for one second when motion
   changes from negative to positive; positive reports do not extend a pulse.

Calibration and timers are automatic after your readiness confirmations. The
application cannot verify that the room is physically empty or move people.
Sound depends on Windows audio settings; always watch the on-screen prompt.

## Saved files

Every experiment gets a new UTC-named folder under `data/wifi/demo/`:

- `empty.csv`, `walking.csv`: official radar reports, not raw CSI samples.
- `session.json`: timing, firmware ID, thresholds and completion/abort state.
- `events.jsonl`: phase changes and window-reset diagnostics, without raw console echoes.
- `summary.json`, `comparison.png`, `report.html`: descriptive comparison.

Missing results mean unknown activity. Report fractions are not accuracy or a
percentage of elapsed time. One pair of trials does not establish performance
across rooms or people. Output gaps and the unchanged official decision rule
can make the live motion flag intermittent.

Raw captures, generated firmware, toolchains and the Python environment are
git-ignored. No credentials or personal recordings belong in a code commit.

## Recovery

| Situation | Action |
|---|---|
| Board not detected | Check the data cable. Look for an Espressif USB Serial/JTAG device in Device Manager. |
| Port is busy | Close the old demo, VS Code serial monitor, and any CSI recorder. The app retries. |
| Several boards | Select the intended port before installing firmware. |
| Installation cannot connect | Hold BOOT while plugging the board in, release it, select the reappearing device and retry. |
| Hotspot connection fails | Check SSID, password, 2.4 GHz and WPA2; click Connect hotspot again. |
| Calibration fails or times out | Fix the connection and repeat the empty-room setup. A failed calibration never starts a trial. |
| No radar output | Keep the hotspot enabled. A gap is shown as waiting, not as no motion. |
| Phone or board moved | Stop and start a new calibration and both trials. |
| Unplug or reboot | Device discovery resumes. Reconnect the hotspot as needed and repeat calibration; an interrupted trial is saved as invalid. |
| Plot export fails | CSV files remain saved. Check the console or `data/wifi/demo/app-*.err.log`. |

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s services/wifi/tests -v
```

These checks use deterministic synthetic inputs. They are not live-radio
validation. The firmware build and a human-run empty/walking experiment are
separate checks. The current implementation keeps the official detection
algorithm and adds a guided UI, protocol checks, recording and recovery.
