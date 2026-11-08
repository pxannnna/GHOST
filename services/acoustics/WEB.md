# Local browser room measurement

Step **03 Room identification** uses real audio from the computer running the Hub. The browser's Start measurement button calls the local backend; playback and synchronous recording use `sounddevice` in a cancellable worker process, not the browser microphone. Run the Hub on the same computer as the microphone and speakers, bound to `127.0.0.1`.

## Use

1. Install the repository requirements, start the Hub and open step 03.
2. The search defaults to floor 3 for the current study-room measurements. You can still select G, 1, 2, 3 or All floors. This is a **manual filter**, not a barometer measurement. LG is not in Anna's 14-room matching database.
3. Choose microphone and speaker. On Windows the panel lists WASAPI devices and captures in exclusive mode, which worked substantially better than MME on the tested Lenovo. Close competing audio apps if capture fails. Check microphone height and speaker/microphone separation (0.75 m and 0.10 m are defaults, not automatically measured).
4. Start measurement. Three sweeps at the same location count as **one position**. Default playback gain is 0.10; UI maximum is 0.30. System volume also affects actual loudness.
5. Move to a different position within the same room at the same height, confirm movement, then measure again. Audio settings remain locked until New room / reset positions. Eight accepted positions are allowed per session. Cancellation stops the capture process and excludes its result.
6. Change the floor to re-rank existing accepted measurements without playing audio. New room / reset positions clears the session's analysis but retains local recordings.

The panel uses PNG figures generated from the saved recordings with Anna's plotting helpers: coloured echo traces by position (0–8 m), position agreement (two or more accepted positions), reverberation decay, and the latest recording's waveform/spectrogram. Each image opens full-size. `plot.py` stays unchanged; `web_plots.py` supplies the browser adapter and the earlier study-room figure's coloured trace layout. No historical example image is presented as a current measurement. Peak markers are tentative reflections, not confirmed surfaces. Rankings use accepted positions only. Clipping or low amplitude in any sweep, SNR under 40 dB, or missing RT60 excludes that position; its trace remains visible for inspection, while comparison figures use accepted positions. These quality gates help reject unusable input, but do not guarantee a correct room classification. A no-match result must not be presented as a confirmed location.

After ranking, the session writes its figures under ignored `web/acoustic-plots/<session>/<capture>/`, served by the existing local static server. This adds no audio endpoint and uploads nothing. Figure generation failures do not discard the measurement. To regenerate an existing set without recording: `python -m services.acoustics.web_plots data/echo/web-<session>/P2_<timestamp>`. The browser reads a manifest tied to the measurement ID, written after all figures finish. Plots use the saved microphone height and speaker–mic spacing.

Ceiling annotations update automatically after ranking or changing the floor filter. The adapter looks up the top candidate's `ceiling_height_m` in the building database; for Study room this is 2.45 m. Each dashed reference subtracts that recording's microphone height (2.45 − 0.75 = 1.70 m). The figure caption names the candidate. No-match or empty rankings remove the reference. This is a candidate-derived expected echo, not a detected surface or additional evidence. The matcher never reads the session's ignored `plot_reference.json`. Figure revisions invalidate cached PNGs; generation failures preserve measurements and ranking.

## Provenance and integration

The Web branch now contains Anna's original `room-location` history through `3869ce3` via a normal merge, including her USB barometer backend. Pressure hardware is not connected to the Web UI by this integration. Browser and Windows audio adaptations are a separate Web commit; the room matcher, original plot module and building database retain her implementation.

Acoustic modules and room geometry were imported from Anna's `room-location` commit `7c4d09d41e77eabbe2eb16343826ceb92bd9d163`. Her matching algorithm is unchanged: RT60, repeated ceiling echo and nearest-wall evidence compared with the floor-plan database. Scores are not probabilities. The integration adds a progress callback and per-sweep capture checks to `measure.py`; `audio_io.py` now rejects failed duplex capture instead of using `sd.rec` followed by `sd.play` (the latter stops the former).

Only the `echolocation` section was imported into `config/default.json`. The website's existing 3D model, pressure configuration and CSI detector remain separate. Measurements emit live `acoustic.measurement` and `room.estimate` events into the Hub, while the dedicated `/acoustics/state` is authoritative for the room panel and its model display, so mock events cannot overwrite real measurement results.

Raw audio, metadata and worker jobs are stored under ignored `data/echo/web-<session>/` and `data/echo-web-jobs/`. No audio is uploaded. Sessions are in memory and reset when the server restarts; saved files persist. Only one capture can run at a time across browser tabs. Server shutdown stops an active capture. Measurements do not automatically start on navigation or reload.

Step 06 presents the actual top candidate and focuses its room in the building model. It uses the accepted-position metrics, keeps no-match and ambiguous states visible, and does not substitute the study room when another room wins. Pressure provenance and the manual acoustic search floor are shown separately. Motion status is read from the live receiver service; stale or disconnected data cannot produce a positive movement result. Each evidence row links back to its measurement step.

API: `GET /acoustics/devices`, `GET /acoustics/state`; `POST /acoustics/measure`, `/floor`, `/cancel`, `/reset`. Recording settings are validated before starting. A selected device is checked again by name and interface inside the worker. Errors, quality rejections and cancellation are shown explicitly.

Validation: `python -m pytest tests/test_acoustics.py tests/test_acoustics_web.py tests/test_wifi_web.py tests/test_wifi_firmware.py`. Unit tests do not play audio; browser acceptance testing uses a manually initiated real sweep.
