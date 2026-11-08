# XIAO ESP32-C6 firmware for the standalone demo

The firmware is prepared from the official Espressif `esp-csi` console example
at the commit in `upstream.json`. `adapt_console.py` applies explicit changes;
the official detection library and decision expressions remain intact.

## Build on Windows

Prerequisites: Git for Windows, Python 3.12 on PATH, and Internet access.
From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File firmware/xiao/build.ps1
```

This downloads ESP-IDF v5.5.4 and its C6 tools into `.cache`, prepares the pinned
official example in `.work/project`, builds it, and writes a checksummed firmware
package to `.artifacts`. The first build can take several minutes and several GB
of disk space. This command does not flash a board.

To reuse existing installations on this development machine:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File firmware/xiao/build.ps1 `
  -IdfPath D:\Codex\Hacktheburgh\.idf `
  -ToolsPath D:\Codex\Hacktheburgh\.idf-tools `
  -Source D:\Codex\Hacktheburgh\esp-csi
```

In an already activated ESP-IDF 5.5.4 terminal, the shorter command is:

```powershell
python firmware/xiao/build.py
```

`--source <path>` reads the pinned Git commit from an existing ESP-CSI clone,
not its possibly modified working files. `--prepare-only` applies the adaptations
without compiling. Exact component versions are pinned in the generated manifest;
the resolved dependency lock is copied into the local package.

## Install

Open [the demo](../../services/wifi/README.md), select the intended device if
there is more than one, and click **Install / update firmware**. This replaces
the board's current program. File SHA-256 checks are verified before writing;
esptool is explicitly restricted to chip type `esp32c6`.

The firmware console uses native USB Serial/JTAG. The host baud setting is
115200; it does not impose the physical throughput limit of a 115200-baud UART.

## Local adaptations

- Native USB console instead of the example's external UART console.
- C6 runtime LTF selection and an HT-LTF startup profile, subcarrier step 5,
  matching the example's 11n negotiation with the tested phone hotspot.
- No duplicate network-interface recreation on disconnect. The existing Wi-Fi
  command handler owns reconnection and the ping session is stopped on disconnect.
- `ghost_status` identifies protocol version 1 / `ghost-radar-1` and reports
  uptime, Wi-Fi, training and calibration state plus thresholds.
- `GHOST_TRAIN,STARTED|DONE|ERROR,<code>` acknowledges the official training calls.
  The guided app refuses to proceed after failed training or zero thresholds.

The app reads the actual 11-field `RADAR_DADA` results. The legacy 9-field
threshold line printed on training completion is not a motion report. Training
state is in RAM and must be rebuilt after reboot or changes in device placement.

This profile is for the tested 2.4 GHz phone-hotspot setup. Successful radio
association alone does not guarantee CSI in the selected LTF format for every AP.

Upstream sources retain their SPDX/Apache-2.0 license headers in the prepared
workspace. The downloaded component code and precompiled libraries retain their
own license files. Build outputs and downloaded dependencies are not committed.
No firmware artifact has been published by this local build workflow.
