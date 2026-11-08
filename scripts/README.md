# GHOST CSI learning notes

These English teaching notes are local material, deliberately stored outside
the `GHOST_csi` Git repository. They are not part of a future feature-branch upload.
The short operational READMEs remain inside the repository.

Read in this order:

1. [How Wi-Fi motion sensing works](01-principles.md)
2. [Follow the implementation](02-code-walkthrough.md)
3. [Run and interpret an experiment](03-experiment-guide.md)

The local project is `../GHOST_csi`. Launch it with
`../GHOST_csi/services/wifi/launch-demo.cmd`. No coding assistant is required
during installation, calibration, recording or live indication.

The setup targets Windows, one Seeed XIAO ESP32-C6 and one 2.4 GHz WPA2 phone
hotspot. It implements an environmental motion demonstration, not person
identification, gesture classification, room tracking or a calibrated speed sensor.
