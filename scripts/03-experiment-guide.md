# Run and interpret an experiment

## Before opening the application

Use one fixed phone hotspot and one fixed ESP32-C6 receiver. Mark their positions
and your walking route. Record approximate separation, height, antenna orientation,
room layout and whether other people are nearby. Keep these consistent across
the paired empty and walking tests.

Use a USB data cable and close other serial readers. Keep the phone hotspot on
2.4 GHz with WPA2 enabled. Disable any hotspot auto-off setting that would stop
the session. You do not need to connect the laptop's Wi-Fi to this hotspot;
the board uses the hotspot and the laptop reads USB.

## The complete application path

1. Open `GHOST_csi/services/wifi/launch-demo.cmd`.
2. Wait for automatic USB discovery. Select the intended board if several appear.
3. If firmware setup is required, click Install / update firmware, confirm the
   port and wait for restart. Do not unplug during installation.
4. Enter hotspot settings and connect. Wait for verified firmware and fresh
   radar results. Connecting to Wi-Fi and receiving compatible CSI are distinct
   milestones; the app needs both before calibration.
5. Fix the devices. Leave the area. Confirm the empty-area checkbox and start.
6. Watch the five-second preparation countdown. Remain outside throughout the
   30-second calibration and the following 60-second empty trial.
7. When the empty trial finishes, prepare beside the route and click the walking
   countdown button. Do not start until the window says START WALKING.
8. Walk naturally back and forth for the full recording. Do not touch either
   device. Stop when the window says STOP WALKING.
9. Open results. Keep the window running to try the one-second green indicator.

The firmware used by the guided demo has a new status handshake. The firmware
used in earlier manual trials does not have that handshake, even though its
official detector already worked. A first-run installation prompt is expected.

## What to compare

| Quantity | What it can tell you | What it cannot establish |
|---|---|---|
| Jitter median | Typical recent channel-feature variation | Walking speed or gesture identity |
| Smoothed wander | Difference from the calibrated empty reference | A guaranteed person count or stable stationary-person detection |
| Motion report fraction | How often received decisions are positive | Accuracy or the exact fraction of time moving |
| Presence report fraction | How often the baseline-comparison decision is positive | General occupancy accuracy |
| Maximum report gap | Longest interval without a result | The precise upstream cause of the gap |
| Green pulse count | Number of visible UI events | Number of steps, waves or people |

Look for consistent separation between the two conditions, not just one large
peak. A useful next repeat would use the same placement and protocol. A later
generalization test can deliberately change distance or orientation, but each
new placement needs its own baseline and should be labelled separately.

## Distinguish failures

- **No device:** USB cable, enumeration, power or driver problem.
- **Port busy:** another process owns the serial port.
- **Wrong firmware:** the guided-demo status handshake is missing or incompatible.
- **No hotspot association:** check credentials, band and phone settings.
- **No usable radar results:** CSI mode, traffic or the processing window may be
  unsuitable even if Wi-Fi is connected.
- **Calibration failure:** do not accept the subsequent data as calibrated.
- **Output gaps:** leave them marked as unknown. Do not fill them with zeros.
- **Empty-room triggers:** check whether a person or device moved, then consider
  environmental changes and radio/processing variation.

If you accidentally move the phone, stop the experiment and repeat calibration
and both conditions. Do not compare walking after the move with an empty trial
from before the move.

## What was already observed before this guided application

The earlier manually controlled official-radar trials produced the following
descriptive results in one placement:

| Metric | Empty room | Walking |
|---|---:|---:|
| Motion report fraction | 1.4% | 41.1% |
| Presence report fraction | 0% | 100% |
| Median jitter | 0.000993 | 0.012972 |
| Longest report gap | 5.05 s | 0.161 s |

Those records are in the sibling `wifi-csi-prep/data/radar/empty-02` and
`walking-02` folders. They support trying the guided demonstration; they do not
validate the new application's entire setup/installation workflow or establish
repeatable accuracy. The earlier `empty-01` trial was flagged as confounded
after the operator reported moving the phone.

## Local deliverable boundaries

The teaching notes stay in `GHOST_csi_teaching`, outside Git. The project's basic
run README, code and firmware build instructions are in `GHOST_csi`. Recordings
and generated firmware are local ignored files. Nothing has been pushed and no
pull request has been opened. Review the code and your test results before
deciding what should eventually be committed to the feature branch.
