# How Wi-Fi motion sensing works

## 1. One receiver still needs a transmitter

The phone is a Wi-Fi access point. The ESP32-C6 joins that access point and
sends repeated pings to its gateway address. Replies provide traffic from which
the receiver can obtain channel state information, or CSI. The official example
requests a 10 ms ping interval. This is a target, not a promise of 100 CSI packets
per second: scheduling, loss, filtering and processing all affect delivery.

The phone and receiver must stay fixed. Otherwise their movement changes the
radio channel too. No Internet service is required to ping the hotspot gateway.

## 2. What is measured?

Wi-Fi uses known reference symbols in a packet. The receiver knows the intended
symbols and measures how propagation changed them. In an OFDM signal this can
be expressed separately for multiple subcarriers, which are narrow frequency
components within the channel.

For subcarrier k and packet time t, write the complex channel estimate as:

```text
H_k(t) = I_k(t) + j Q_k(t)
A_k(t) = sqrt(I_k(t)^2 + Q_k(t)^2)
```

I and Q are the two components of the complex estimate. The current official
radar pipeline converts them to amplitude A. These are device-scaled values,
not calibrated power in watts or distance in metres.

Signal energy reaches the receiver by several paths: a direct path and reflected
paths from walls, furniture and people. Motion changes the combined channel.
The algorithm looks for changes in the multi-subcarrier pattern over time.

## 3. LLTF, HT-LTF and HE-LTF

These are reference-field formats, not names of machine-learning models.

| Field | Meaning in this context |
|---|---|
| LLTF | Legacy long training field |
| HT-LTF | High-throughput reference field associated with 802.11n |
| HE-LTF | High-efficiency reference field associated with 802.11ax |

The current official radar Wi-Fi profile negotiates 11n with the tested phone.
The working C6 input is HT-LTF in a 20 MHz channel. An earlier CSI capture
firmware negotiated a different format; those observations must not be assumed
to describe a new firmware connection. Read the actual metadata and configuration.

The word "training" in a Wi-Fi reference field is unrelated to empty-room
calibration. One is part of radio communication; the other records an environment
baseline for detection.

## 4. What the official library does

The pinned library selects the relevant transmitter, rebuilds valid subcarrier
data, compensates receiver gain, selects the requested LTF data, extracts
amplitudes and accumulates time windows. The current profile samples subcarriers
with a step of 5. A 200 ms processing setting is used by the official defaults.

The feature computation is provided by Espressif's precompiled
`esp_radar_motion_dec` library. Its public interfaces explain inputs and outputs,
but do not expose every internal mathematical step. Do not describe this demo as
a verified implementation of a specific PCA, FFT, neural-network or Doppler
algorithm unless that statement is independently supported.

The exposed features are:

- **Jitter:** change relative to recent feature history. Higher values indicate
  more instability in that feature representation.
- **Wander:** difference from feature records gathered during empty-room
  calibration. The implementation compares the current representation with
  stored calibration representations and uses the closest match.

Both are dimensionless indicators. A value is not a probability that a person
is present. Device movement, other environmental changes or radio artefacts may
affect them as well.

## 5. Empty-room calibration

The official API already provides `esp_radar_train_start()` and
`esp_radar_train_stop()`. The console exposes `radar --train_start` and
`radar --train_stop`. Our application chooses a 30-second calibration period,
checks the acknowledgements and verifies positive thresholds before proceeding.

Training records normal feature patterns and threshold statistics for this
placement. It does not learn named classes such as walking versus waving from
labelled examples. The thresholds and records are held in board RAM. A reboot,
new placement or major environmental change requires a new baseline.

Receiver gain compensation and empty-room calibration are separate operations.
Gain compensation attempts to reduce changes caused by receiver amplification.
Calibration establishes a reference for the physical scene.

## 6. From features to a binary decision

The unchanged official console decision logic uses a 25-result history and
examines the last 5 results. With the default settings, a candidate motion result
satisfies either:

```text
0.20 * jitter > trained_motion_threshold
OR
(0.20 * jitter > recent_jitter_median AND jitter > 0.0002)
```

At least 2 of the last 5 candidate results must qualify for the motion flag to
be 1. The presence flag compares the smoothed wander with the trained presence
threshold using its own sensitivity, 0.15 by default.

The plotted rolling motion reference is `recent_jitter_median / 0.20`.
It is not the trained fixed motion threshold. A chart containing only that line
would not show the whole decision rule; the new exported comparison includes
both references. The 5-result voting also means a flag need not match the
instantaneous jitter value at a single plotted point.

The desktop indicator reads the board's binary motion flag. A new positive
episode starts a one-second pulse. The UI does not rerun the earlier desktop
FFT-based energy detector. Pulse count is a UI count, not a count of steps or people.

## 7. Why an output gap can happen

There are several stages between a packet and a visible decision:

```text
Wi-Fi reception -> CSI extraction -> filtering -> valid time window
-> feature calculation -> decision -> USB output -> desktop display
```

At the default 200 ms processing setting, a strict timestamp-gap limit is
100 ms, with a temporary relaxed limit of 200 ms after a discontinuity. The
library can clear a window and start collecting again. Repeated short breaks
can therefore create several seconds without a radar decision even while CSI
continues to enter the processing pipeline.

No radar output means unknown activity. It does not mean zero CSI information
or a verified empty room. To locate the cause of irregular arrival, additional
raw CSI and traffic instrumentation would be needed. The demo saves radar
reports and window-reset events; it does not save raw I/Q samples.
