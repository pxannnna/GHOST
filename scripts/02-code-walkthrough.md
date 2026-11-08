# Follow the implementation

All paths below are relative to `../GHOST_csi`.

## Start at the launcher

`services/wifi/launch-demo.cmd` calls `setup-demo.ps1`. The PowerShell script
creates a local Python environment, installs `requirements-demo.lock.txt`,
checks imports and opens `pythonw -m services.wifi.demo`.

The dependency environment is separate from the firmware compiler environment.
You need the ESP-IDF toolchain only to build firmware. Running and installing
an already built firmware package needs the desktop environment and esptool.

## Firmware provenance and adaptation

`firmware/xiao/upstream.json` identifies the ESP-CSI commit, ESP-IDF 5.5.4,
ESP-Radar 0.3.4 and component versions. `build.py` reads the pinned Git commit
using `git archive`, rather than copying an arbitrary working tree. Sources
are prepared under the ignored `.work/project` directory.

`adapt_console.py` applies exact, checked replacements. If the expected source
does not match, preparation fails rather than silently patching a different
version. The changes are:

1. Use the XIAO's native USB Serial/JTAG console.
2. Include C6 in the runtime reference-field selection branch.
3. Select HT-LTF and subcarrier step 5 at startup.
4. Remove duplicate network-interface reinitialization on Wi-Fi disconnection.
   The existing reconnect handler retains responsibility for association.
5. Add an identification/status command and explicit training acknowledgements.

The feature computation library and the console's motion/presence decision
expressions are not rewritten. The 30-second timer, recording schedule and
one-second green light belong to the desktop application.

`build.py` packages the bootloader, partition table, OTA initializer and app
image. Each image receives a SHA-256 checksum in `.artifacts/manifest.json`.
The UI checks these hashes before passing explicit addresses to esptool.
This is an integrity check, not a cryptographic publisher-signature system.

## Wire protocol

`services/wifi/demo/protocol.py` is the authority for desktop parsing.

```text
GHOST_STATUS,protocol,firmware_id,uptime_ms,wifi,training,calibrated,presence_threshold,motion_threshold
GHOST_TRAIN,STARTED|DONE|ERROR,result_code
RADAR_DADA,sequence,device_ms,wander,wander_average,presence_threshold_scaled,presence,jitter,jitter_median,rolling_motion_reference,motion
```

`RADAR_DADA` is spelled that way in the upstream example. Its real report has
11 fields, including the marker. An upstream printed header and the separate
training-threshold line use a different shape. The parser deliberately rejects
the 9-field threshold line as a normal report. It also rejects malformed flags
and non-finite numeric values.

The firmware ID `ghost-radar-1` and protocol version 1 identify this guided-demo
interface. A generic official console can emit radar reports but cannot confirm
the guided workflow's calibration status. It therefore requires an update.

## Device discovery and serial ownership

`transport.py` runs a background worker. It discovers native Espressif USB
devices by VID/PID, asks the operator to choose if there is more than one, and
remembers the selected physical identity where Windows exposes one.

The worker owns the serial connection. GUI callbacks send requests through a
queue rather than blocking on I/O. DTR and RTS are disabled before opening to
avoid deliberately resetting the board. The firmware installation operation
first closes the port, then invokes esptool, then allows discovery to resume.

Only one program can own the COM port. Close earlier recorders, demos and VS
Code serial monitors. The app does not terminate unrelated programs for you.

## Experiment state machine

`workflow.py` defines the experiment independently of Tk and USB:

```text
idle -> countdown_empty -> await_start -> calibrating
-> await_stop -> wait_status -> settling -> empty
-> waiting_walk -> countdown_walk -> walking -> complete
```

An error, disconnect or device-clock restart invalidates the experiment's
calibration. A new experiment must start from empty-room setup. Partial files
remain available for diagnosis; they are not presented as a completed comparison.

The calibration timer starts after the board acknowledges training. Recording
does not begin merely because 30 seconds elapsed: the board must acknowledge
completion and report valid thresholds. Walking uses the same baseline as the
empty trial, without retraining between conditions.

`app.py` joins this state machine to the UI. It owns the readiness confirmations,
countdowns, audible cues, green indicator, live trace and result links. The
empty-room confirmation describes a physical condition only a person can verify.

## Recording and interpretation

`results.py` creates a fresh output folder per attempt. CSV rows preserve board
timestamps and host-relative arrival times. Phase changes and window resets go
to a separate event log. Hotspot credentials and raw console echoes are excluded.

The comparison uses device timestamps to measure report gaps. Plotted lines
break at gaps above 200 ms rather than connecting missing intervals. Statistics
include medians and positive-report fractions, without treating correlated
frames as independent experiments.

The result files are descriptive. No labelled supervised classifier is fitted,
and the demo does not claim accuracy, a velocity estimate or recognition of a
particular gesture. The Hub and web application are not required or modified.

## Checks and their limits

`services/wifi/tests/test_demo.py` covers wire parsing, one-second pulse timing,
credential command boundaries, supported USB filtering, the timed workflow,
failed calibration, disconnection, reboot, firmware hash checks and saved records.
The tests use synthetic inputs and do not prove radio sensitivity.

Compiling the firmware proves build compatibility with the pinned toolchain.
Inspecting the desktop UI proves that the window can render. A human-run
experiment is still required to validate the complete hardware workflow.
