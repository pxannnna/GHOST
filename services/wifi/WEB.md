# Browser CSI motion integration

The Wi-Fi panel is embedded in step **05 Motion detection** of the existing website at http://127.0.0.1:8000/. The animation page is independent and unchanged.

## Use

1. Start the usual Hub (`.venv\Scripts\python.exe -m uvicorn services.hub.app:app --host 127.0.0.1 --port 8000`). Install the existing `pyserial` dependency if needed.
2. Close the standalone CSI window / other serial monitor so only this server owns the receiver port. Plug in the receiver.
3. Open step 05 and select **Connect receiver**. Automatic discovery targets native Espressif USB 303A:1001. With multiple devices, choose a COM port and connect again.
4. If necessary, enter the 2.4 GHz hotspot details and connect. Credentials are sent locally to the receiver and are not written to application files. The board may retain its Wi-Fi settings in NVS.
5. Keep both devices fixed, keep movement out of the calibration area, tick the confirmation and select **Start calibration**. The board runs its 30-second calibration, verifies thresholds, then resumes fresh reports.
6. **Motion detection starts automatically and continues until Stop or Disconnect.** There is no empty-room trial, walking trial, recording deadline, or detection countdown.

## Preserved detector behavior

The wire parser, rising-edge pulse logic and serial transport come from `feature/csi-standalone-demo`, commit `290ac0a`, at `services/wifi/demo/` in the sibling CSI checkout. This integration does not modify that checkout or `D:\testcsi`.

Green trace: `0.2 × Jitter`. Orange dashed reference: calibrated motion threshold. Blue dashed reference: raw recent Jitter median (not multiplied again). Chart range stays fixed at zero to three times the calibration reference, breaks at report gaps, and marks clipped values. The official board Motion flag controls a one-second green pulse on new motion episodes; graph crossings alone do not trigger it.

Only actual receiver reports feed this panel. Existing Hub mock Wi-Fi events are not used. Missing reports are unknown, not no-motion; disconnect, stale firmware status and reboot invalidate the calibration. Calibration and detection are owned by one server, so multiple browser tabs share the same session.

## Receiver recovery and firmware

Under **Device & hotspot**, **Restart receiver** performs the USB reset used after flashing, without writing or erasing flash. Try this first if the receiver does not respond after unplugging/replugging. A successful reset is reported only after `ghost-radar-1` responds. Firmware normally persists across power loss; calibration is in RAM and must be repeated.

**Install / update firmware** shows the selected COM port and asks for confirmation before replacing the program. The server releases the serial reader, validates the local package and SHA-256 hashes, runs pinned `esptool==4.13.0`, reconnects to the same physical board, and verifies its firmware identity. Progress and errors appear in the panel. Stop detection/calibration before either action. Other device controls are locked during maintenance. No firmware is installed automatically, and a successful writer exit alone is not shown as verified success.

The local package is `firmware/xiao/.artifacts/manifest.json` plus its four referenced `.bin` files. These ignored build outputs are copied from the existing standalone CSI build on this machine; they are not committed. To prepare another machine, build the pinned firmware in the CSI checkout as described in its `firmware/xiao/README.md`, then copy the manifest and referenced images into this directory. Alternatively set `GHOST_FIRMWARE_MANIFEST` to that build's manifest before starting the Hub. Install the Hub requirements and restart the Hub after adding a package. The UI disables installation when the package/dependency is unavailable.

Only the tested ESP32-C6 protocol 1 package and its bootloader, partition table, OTA metadata and application locations are accepted. The installer does not erase the whole flash or write the NVS credential partitions. A failed/interrupted write is reported as an error; reconnect the board and retry installation. Keep the Hub bound to `127.0.0.1` for this local hardware demo.

Observed recovery on 2026-11-08: COM5 enumerated but returned no serial data after reconnecting USB. A reset-only operation produced `SPI_FAST_FLASH_BOOT`, loaded the application at `0x20000`, and returned `GHOST_STATUS,1,ghost-radar-1`. No flash write was performed. This establishes that the firmware was still present in this incident; the original reason for the unresponsive state has not been established.

## API and validation

`GET /wifi/state`; `POST /wifi/device` with optional `port`; `/wifi/disconnect`; `/wifi/hotspot` with `ssid`, `password`; `/wifi/calibrate` with `confirmed:true`; `/wifi/stop`.

`POST /wifi/restart` with optional `port`; `POST /wifi/firmware` with `port` and `confirmed:true`. `/wifi/state` includes `firmware_package` availability and `maintenance` status, target port, message and bounded progress logs. Both operations run in the background; poll state until verification succeeds or an error is reported.

`python -m unittest discover -s tests -p 'test_wifi_web.py'` checks calibration acknowledgements, transition directly into continuous detection, operation beyond one minute, pulse timing, missing data, disconnect, stop and reboot handling.

`python -m unittest discover -s tests -p 'test_wifi_firmware.py'` checks package corruption/paths/ranges, confirmation, serial ownership, concurrent-request rejection, restart without flashing, failure recovery and required firmware verification. These tests mock the writer and do not flash a physical board.
