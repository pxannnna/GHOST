import { modelPresentation } from "./model-presentation.mjs?v=1";
import { mountPressure } from "./pressure.js?v=pressure-auto-3";
import { mountAcoustics } from "./acoustics.js?v=anna-20261108-auto";
import { mountWifi } from "./wifi.js?v=study-20261108-1";
import { mountBuilding } from "./building3d/index.js?v=auto-model-1";
import { sessionResult } from "./session-result.mjs";

const slides = {
  intro: ["Introduction", "Indoor sensing", "A USB barometer narrows the search to one floor. A laptop listens for echoes to rank the rooms on that floor. Wi-Fi detects movement."],
  floor: ["Floor detection", "Floor detection", "Air pressure falls as we go up. A calibrated reference helps choose which floor to search."],
  room: ["Room identification", "Room identification", "A speaker plays a sweep and the microphone catches the reflections. The echoes help rank the rooms on the estimated floor."],
  model: ["Building model", "Building model", "The building view marks the estimated floor and the strongest room candidate."],
  gesture: ["Motion detection", "Wi-Fi motion detection", ""],
  results: ["Results", "From signals to a room", "A floor, a room, and movement within it. Review the measurements together, then return to any step to test again."],
};
const measurementTitles = {
  intro: "How the demo works", floor: "Pressure measurements", room: "Acoustic measurements",
  model: "Estimated position", gesture: "Calibration & continuous detection", results: "Session results",
};
const byId = id => document.getElementById(id);
const text = (id, value) => { byId(id).textContent = value; };
const format = (value, decimals, unit = "") => Number.isFinite(value) ? value.toFixed(decimals) + unit : "—";
const panes = [...document.querySelectorAll("[data-view]")];
let wifiState = null;
mountWifi(document.getElementById("wifi-panel"), state => { wifiState = state; render(); });
const simulate = byId("simulate");
simulate.hidden = !new URLSearchParams(location.search).has("mock");

let online = false;
let busy = false;
let demo = { current_view: "intro" };
let latest = {};
let statuses = {};
let views = [];
let building;
let floorLabels = {};
let blockReason = "not armed";
let staleAfterMs = 5000;
let clockOffsetMs = 0;
let accepted = 0;
let events = [];
let gestures = [];
let pressureHistory = [];
let replay = null;
let sequence = 0;
let renderedView = null;
let acousticState = null;
let pressureState = null;
mountAcoustics(byId("acoustics-panel"), state => { acousticState = state; render(); });
mountPressure(byId("pressure-panel"), state => { pressureState = state; render(); });
const mockSession = `web-mock-${Date.now()}-${Math.random().toString(36).slice(2)}`;

function cap(list, size) {
  if (list.length > size) list.length = size;
}

function signalLabel(event) {
  if (!event) return "Awaiting data";
  const age = Date.now() + clockOffsetMs - event.received_unix * 1000;
  const state = Object.values(statuses).find(status =>
    status.source === event.source && status.mode === event.mode &&
    status.received_unix >= event.received_unix &&
    ["offline", "error", "stale", "calibrating"].includes(status.state))?.state;
  const condition = !online ? "offline" : state ?? (age > staleAfterMs ? "stale" : "");
  return condition ? `${event.mode} · ${condition}` : event.mode;
}

function badge(id, event) {
  const node = byId(id);
  node.textContent = signalLabel(event);
  node.dataset.mode = event?.mode ?? "";
}

function trace(id, values, minimumSpan = .001) {
  const data = values.filter(Number.isFinite);
  const min = Math.min(...data);
  const max = Math.max(...data);
  const middle = (max + min) / 2;
  const span = Math.max(max - min, minimumSpan);
  const points = data.map((value, index) =>
    `${(index * 480 / Math.max(data.length - 1, 1)).toFixed(1)},${(45 - 70 * (value - middle) / span).toFixed(1)}`);
  byId(id).querySelector("polyline").setAttribute("points", points.join(" "));
}

function showList(id, entries, empty, render) {
  const list = byId(id);
  if (!entries.length) {
    const item = document.createElement("li");
    item.textContent = empty;
    list.replaceChildren(item);
    return;
  }
  list.replaceChildren(...entries.map((entry, index) => {
    const item = document.createElement("li");
    render(item, entry, index);
    return item;
  }));
}

function renderEvents() {
  text("event-count", `${accepted} accepted`);
  showList("event-log", events, "Waiting for Hub events…", (item, event) => {
    const name = document.createElement("strong");
    name.textContent = event.type;
    const time = new Date(event.timestamp_utc).toLocaleTimeString();
    item.append(`${time}  `, name, `  ·  ${event.source} / ${event.mode}`);
  });
}

function render() {
  const active = demo.current_view;
  byId("building-view").hidden = active === "gesture";
  byId("description").hidden = active === "gesture";
  byId("measurements").hidden = ["gesture", "room", "results"].includes(active);
  const [label, title, description] = slides[active] ?? [active, active, ""];
  const viewNumber = views.indexOf(active) + 1;
  text("title", viewNumber > 0 ? `${viewNumber}. ${title}` : title);
  text("description", description);
  const ordinal = index => String(index).padStart(2, "0");
  text("chapter", `Demonstration / ${label}`);
  text("measurements", measurementTitles[active] ?? "Measurements");
  text("measurements-link", measurementTitles[active] ?? "Measurements");
  for (const pane of panes) pane.hidden = pane.dataset.view !== active;
  if (renderedView !== active) {
    if (renderedView !== null) window.scrollTo({ top: 0, behavior: "instant" });
    renderedView = active;
  }

  const livePressure = pressureState?.fresh;
  const floor = livePressure && pressureState.estimate ? {mode:'live', source:'pressure', received_unix:(Date.now()+clockOffsetMs)/1000, payload:pressureState.estimate} : null;
  const pressure = livePressure ? {mode:'live', source:'pressure', received_unix:(Date.now()+clockOffsetMs)/1000, payload:{pressure_pa:pressureState.pressure_hpa*100}} : null;
  const echo = latest["acoustic.measurement"];
  const room = latest["room.estimate"];
  const wifi = latest["wifi.features"];
  const localEcho = acousticState && ["room", "model", "results"].includes(active);
  const floorId = localEcho ? acousticState.floor_id : floor?.payload.floor_id ?? null;
  const floorName = floorId === null ? "—" : floorLabels[floorId] ?? `Floor ${floorId}`;
  const candidates = localEcho ? acousticState.result?.candidates ?? [] : room?.payload.candidates ?? [];
  const top = candidates[0];
  const topName = top?.label ?? top?.room_id ?? "—";
  const sameFloor = localEcho || (floorId !== null && room?.payload.floor_id === floorId);
  const slideEvent = { floor, room, model: floor, gesture: wifi, results: room ?? floor }[active];
  byId("slide-mode").hidden = ["intro", "gesture", "room", "results"].includes(active);
  badge("slide-mode", slideEvent);

  text("floor-value", floorName);
  text("pressure-value", format(pressure?.payload.pressure_pa / 100, 2, " hPa"));
  text("pressure-mode", livePressure ? "live · USB barometer" : pressureState?.stage ?? "disconnected");
  text("floor-status", floor ? `Floor estimate · ${floor.payload.status}` : pressureState?.message ?? "Connect the pressure board to begin.");
  trace("pressure-trace", pressureState?.history_hpa ?? [], .03);
  text("model-floor", localEcho && floorId === null ? "All floors · manual search" : floorName);
  text("model-room", sameFloor ? topName : "—");
  if (localEcho) text("model-mode", "Live audio · manual floor filter");
  else badge("model-mode", floor);
  building?.setFloor(floorId);
  building?.setRoomCandidates(localEcho && sameFloor && floorId !== null && (!localEcho || acousticState.result?.status !== "no_match") ? candidates : [], localEcho ? "live" : room?.mode);
  if (localEcho) building?.setMode("live");
  else if (floor) building?.setMode(floor.mode);

  text("motion-score", format(wifi?.payload.motion_score, 2));
  text("packet-rate", format(wifi?.payload.packet_rate_hz, 0, " Hz"));
  text("wifi-mode", signalLabel(wifi));
  trace("wifi-trace", wifi?.payload.csi_trace ?? []);
  showList("gesture-log", gestures, "No gestures received yet.", (item, entry) => {
    const result = entry.acted ? "advanced" : `ignored · ${entry.ignored_reason}`;
    item.textContent = `${entry.gesture} · ${entry.mode} · score ${format(entry.score, 2)} · ${result}`;
  });
  const summary = sessionResult(acousticState, wifiState);
  text("result-room", summary.title);
  text("result-status", summary.status);
  text("result-floor", summary.floor == null ? "The Nucleus" : `Floor ${summary.floor === "0" ? "G" : summary.floor} · The Nucleus`);
  text("result-score", summary.score);
  text("result-rt60", summary.rt60);
  text("result-snr", summary.snr);
  text("result-scope", summary.scope);
  // Pressure evidence remains independent of the manually selected acoustic floor.
  text("result-pressure", floor?.mode === "live" ? `${floor.payload.floor_id == null ? "No floor estimate" : floorLabels[floor.payload.floor_id] ?? `Floor ${floor.payload.floor_id}`} · ${floor.payload.status} · live` : "Awaiting live pressure measurement");
  text("result-motion", summary.motion);
  text("result-note", summary.note);
  text("result-acoustic", summary.count ? `${summary.count} accepted position${summary.count === 1 ? "" : "s"} · ${summary.status}` : "Awaiting measurement");
  building?.setPresentation(modelPresentation(active, pressureState, acousticState));
  if (active === 'floor') text('model-mode', floor?.payload.status === 'settled' ? 'Detected floor · live' : 'Awaiting stable floor measurement');
  if (active === 'room') text('model-mode', summary.top ? `${summary.status} · ${summary.title}` : 'Awaiting room measurement');
  if (active === "results") text("model-mode", summary.top ? "Acoustic result" : "Awaiting acoustic result");

  const progress = byId("replay");
  progress.hidden = !replay;
  if (replay) progress.textContent = `Replay · ${replay.replay_of} · ${replay.position}/${replay.total}`;
  renderControls();
}

function renderControls() {
  const enabled = online && !busy && views.includes(demo.current_view);
  for (const button of byId("steps").children) {
    button.disabled = !enabled;
    button.setAttribute("aria-current", button.dataset.target === demo.current_view ? "step" : "false");
  }
  for (const button of document.querySelectorAll("[data-retest]")) button.disabled = !enabled;
  for (const id of ["previous", "next", "arm", "simulate"]) byId(id).disabled = !enabled;
  text("arm", demo.gesture_armed ? "Disarm gesture" : "Arm gesture");
  byId("arm").setAttribute("aria-pressed", String(demo.gesture_armed));
  text("gesture-status", demo.gesture_armed ? blockReason ?? "Gesture ready" : "Gesture disarmed");
}

function receive(message) {
  if (message.kind === "snapshot") {
    const state = message.state;
    online = true;
    clockOffsetMs = state.server_unix * 1000 - Date.now();
    staleAfterMs = state.stale_after_ms;
    demo = state.demo;
    blockReason = state.gesture_block_reason;
    latest = state.latest;
    statuses = state.status;
    accepted = state.counters.accepted;
    replay = state.replay;
    gestures = state.gestures.slice(-5).reverse();
    events = Object.values(latest).sort((a, b) => b.received_unix - a.received_unix).slice(0, 6);
    pressureHistory = [latest["pressure.sample"]?.payload.pressure_pa].filter(Number.isFinite);
    views = state.config.views;
    const floors = state.config.building.floors;
    floorLabels = Object.fromEntries(floors.map(floor => [floor.id, floor.label]));
    building?.dispose();
    building = mountBuilding(byId("building"), { floors });
    text("building-label", demo.selected_building ?? state.config.building.label);
    text("session", state.session_id);
    byId("steps").replaceChildren(...views.map((id, index) => {
      const button = document.createElement("button");
      const number = document.createElement("span");
      number.textContent = String(index + 1).padStart(2, "0");
      button.dataset.target = id;
      button.append(number, slides[id]?.[0] ?? id);
      button.addEventListener("click", () => control("/demo/view", { view: id }));
      return button;
    }));
    text("connection", "Hub connected");
    byId("connection").dataset.online = "true";
  } else {
    clockOffsetMs = message.server_unix * 1000 - Date.now();
    blockReason = message.gesture_block_reason;
    if (message.kind === "event") {
      const event = message.event;
      const prior = latest[event.type];
      latest[event.type] = event;
      accepted += 1;
      events.unshift(event);
      cap(events, 6);
      if (event.type === "demo.state") {
        demo = event.payload;
        if (demo.selected_building) text("building-label", demo.selected_building);
      }
      if (event.type === "source.status") {
        statuses[`${event.source}/${event.payload.component}`] = {
          ...event.payload, source: event.source, mode: event.mode, received_unix: event.received_unix,
        };
      }
      if (event.type === "replay.progress") replay = event.payload;
      if (event.type === "pressure.sample") {
        if (prior?.source !== event.source || prior?.mode !== event.mode || prior?.session_id !== event.session_id) {
          pressureHistory = [];
        }
        if (Number.isFinite(event.payload.pressure_pa)) {
          pressureHistory.push(event.payload.pressure_pa);
          if (pressureHistory.length > 100) pressureHistory.shift();
        }
      }
    } else if (message.kind === "gesture_log") {
      gestures.unshift(message.entry);
      cap(gestures, 5);
    }
  }
  render();
  if (message.kind === "snapshot" || message.kind === "event") renderEvents();
}

function connect() {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${scheme}//${location.host}/ws`);
  socket.addEventListener("message", ({ data }) => receive(JSON.parse(data)));
  socket.addEventListener("close", () => {
    online = false;
    byId("connection").dataset.online = "false";
    text("connection", "Hub offline · retrying");
    render();
    setTimeout(connect, 1500);
  });
}

async function control(path, payload) {
  if (!online || busy) return;
  busy = true;
  const error = byId("control-error");
  error.hidden = true;
  renderControls();
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: payload ? { "Content-Type": "application/json" } : undefined,
      body: payload ? JSON.stringify(payload) : undefined,
    });
    if (!response.ok) throw new Error(`Hub returned ${response.status}`);
  } catch (cause) {
    error.textContent = `Presenter control failed: ${cause.message}`;
    error.hidden = false;
  } finally {
    busy = false;
    renderControls();
  }
}

function previous() {
  const index = views.indexOf(demo.current_view);
  if (index !== -1) control("/demo/view", { view: views[(index - 1 + views.length) % views.length] });
}

byId("previous").addEventListener("click", previous);
for (const button of document.querySelectorAll("[data-retest]")) button.addEventListener("click", () => control("/demo/view", { view: button.dataset.retest }));
byId("next").addEventListener("click", () => control("/demo/next"));
byId("arm").addEventListener("click", () => control("/demo/armed", { armed: !demo.gesture_armed }));
simulate.addEventListener("click", () => control("/events", {
  schema_version: 1,
  session_id: mockSession,
  source: "mock",
  type: "gesture.detected",
  timestamp_utc: new Date().toISOString(),
  sequence: sequence++,
  mode: "simulated",
  payload: { gesture: "next", score: .91, model_version: "web-mock-v1", window_ms: 1500 },
}));
document.addEventListener("keydown", event => {
  if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
      event.target.closest("input, textarea, select, [contenteditable]")) return;
  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    if (!online) return;
    event.preventDefault();
    if (event.key === "ArrowRight") control("/demo/next");
    else previous();
  }
});

connect();
setInterval(render, 1000);

const sectionLinks = [...document.querySelectorAll(".page-index a")];
const sectionObserver = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    for (const link of sectionLinks) {
      if (link.hash === `#${entry.target.id}`) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    }
  }
}, { rootMargin: "-70px 0px -60% 0px" });
for (const link of sectionLinks) sectionObserver.observe(document.querySelector(link.hash));
