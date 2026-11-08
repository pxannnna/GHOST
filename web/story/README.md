# GHOST animated story

Open http://127.0.0.1:8000/story/ with the existing local Hub running. This standalone page does not connect to or modify Hub state. The original dashboard files are unchanged.

Play runs a 120-second illustrated scenario: Europe (0), Edinburgh (12), King's Buildings (24), Nucleus exterior (37), pressure / second floor (54), chirp / ranked rooms (74), Wi-Fi motion (96). The final sequence holds a baseline until 100 s, shows motion until 108 s, then concludes with a demonstration help request and candidate rooms.

Pause, restart, timeline scrubbing, chapter selection, arrow navigation, playback speed and fullscreen are available. Hidden tabs pause. Reduced-motion preferences replace pulses/walking with static illustrations.

The scene reuses the existing Nucleus geometry without changing the dashboard renderer. City/campus streets are schematic, not a surveyed map. Aircraft geographic localization, pressure, echoes and motion in this page are a narrative illustration, not live inference. No real emergency service is contacted.

Sources: Natural Earth 1:110m land polygons (public domain), bundled in land.geojson from https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson ; campus context https://science-engineering.ed.ac.uk/nucleus-building/about/location ; existing project building model and survey.

Validation: node --check web/story/story.js; browser review of all seven chapters, playback/pause, seek/restart and console. Separate narrative, interaction and visual reviews informed the final version.
