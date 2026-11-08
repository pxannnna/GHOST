import * as THREE from "../vendor/three/three.module.js";
import { OrbitControls } from "../vendor/three/OrbitControls.js";
import data from "./nucleus-metric-data.js";
import { createBuilding, zoneColours } from "./geometry.js";
import { updateArchitecture } from "./architecture.js";
import { applyRoomFocus } from "./room-focus.js";
import { createLabels, roomKey, visibleMeshes } from "./labels.js?v=red-room-1";

export function mountBuilding(container) {
  const root = document.createElement("div");
  root.className = "building-model";
  root.innerHTML = `
    <div class="model-toolbar">
      <label>Floor <select aria-label="Model floor"><option value="all">All floors</option><option value="follow">Follow estimate</option></select></label>
      <label>View <select aria-label="Model view"><option value="3d">3D perspective</option><option value="plan">Floor plan</option></select></label>
      <label>Show <select aria-label="Building display"><option value="exterior">Complete building</option><option value="cutaway">Interior cutaway</option><option value="room">Room focus</option></select></label>
      <button type="button" class="model-example">Show study room · 3</button>
      <button type="button" class="model-reset">Reset view</button>
    </div>
    <div class="model-viewport"></div>
    <div class="model-toolbar model-options">
      <label>Separate floors <input type="range" min="0" max="12" value="0" step="1" aria-label="Layer spacing"><output class="model-spacing-value">Actual elevations</output></label>
      <label>Inspect <select aria-label="Inspect room"><option value="">Choose a room</option></select></label>
    </div>
    <p class="model-layout-note"></p>
    <p class="model-detail" role="status">Select a room to inspect its location.</p>
    <section class="model-room-info" aria-label="Selected room" hidden>
      <div class="model-room-heading"><h3></h3><button type="button" class="model-clear">Clear selection</button></div>
      <dl></dl><p class="model-room-note"></p>
    </section>
    <p class="model-note">Select a room to reveal its translucent 3D walls with the floors above removed. Clear selection to return to the complete building. Drag to rotate · Scroll to zoom · Right-drag to pan.</p>`;
  container.append(root);
  const floorSelect = root.querySelector('[aria-label="Model floor"]');
  const viewSelect = root.querySelector('[aria-label="Model view"]');
  const displaySelect = root.querySelector('[aria-label="Building display"]');
  const roomSelect = root.querySelector('[aria-label="Inspect room"]');
  const spacing = root.querySelector('input');
  const viewport = root.querySelector(".model-viewport");
  const detail = root.querySelector(".model-detail");
  const roomInfo = root.querySelector(".model-room-info");
  for (const floor of data.floors) {
    floorSelect.add(new Option(`${floor.id === "0" ? "G" : floor.id} · ${floor.label}`, floor.id));
    const options = document.createElement("optgroup");
    options.label = floor.label;
    for (const room of floor.rooms) {
      options.append(new Option(room.label, `${floor.id}/${room.room_id}`));
    }
    roomSelect.append(options);
  }
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  } catch {
    viewport.textContent = "3D graphics are unavailable in this browser. Open the linked source floor plans to view the building.";
    root.querySelectorAll("select, input, button").forEach(control => { control.disabled = true; });
    return { setFloor() {}, setRoomCandidates() {}, setMode() {}, focusRoom() {}, setPresentation() {}, dispose() { root.remove(); } };
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0xfafbfd);
  renderer.domElement.setAttribute("aria-label", "Interactive Nucleus building model");
  renderer.domElement.setAttribute("role", "img");
  viewport.append(renderer.domElement);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb0b8c6, 1.2));
  const light = new THREE.DirectionalLight(0xffffff, 1.5);
  light.position.set(-40, 100, 60);
  scene.add(light);
  const model = createBuilding();
  scene.add(model.group);
  const camera = new THREE.PerspectiveCamera(35, 1, .1, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.minDistance = 8;
  controls.maxDistance = 350;
  controls.maxPolarAngle = Math.PI / 2 - .03;
  let editable = true;
  let presentationKey = null;
  let manualView = null;
  let estimate = null;
  let candidates = [];
  let candidateMode = "";
  let candidateKey = "";
  let inspected = "";
  let mode = "";
  let disposed = false;
  let cutaway = false;
  let focusFloor = null;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const pulseLow = new THREE.Color(0xffb3b3);
  const pulseHigh = new THREE.Color(0xe02030);
  let pulseFrame = null;
  let pulseRoom = "";
  let pulseStart = 0;
  function paintPulse(now) {
    const part = focusFloor && model.roomParts.get(inspected);
    if (!part) return;
    // A continuous 3.2-second breath, never a hard on/off flash.
    const strength = reducedMotion.matches ? .65 : (1-Math.cos((now-pulseStart)*Math.PI*2/3200))/2;
    part.zone.material.color.copy(pulseLow).lerp(pulseHigh,strength);
    part.zone.traverse(object => {
      if (object.isLineSegments) {
        object.material.color.setHex(0xb51224);
        object.material.transparent = true;
        object.material.opacity = .6+.4*strength;
      }
    });
    part.walls.traverse(object => {
      if (object.isMesh) object.material.opacity = .22+.43*strength;
      else if (object.isLineSegments) object.material.opacity = .55+.45*strength;
    });
  }
  function pulseTick(now) {
    pulseFrame = null;
    if (disposed || !focusFloor || !inspected || document.hidden || reducedMotion.matches) return;
    paintPulse(now);
    renderer.render(scene,camera);
    pulseFrame = requestAnimationFrame(pulseTick);
  }
  function syncPulse() {
    const key = focusFloor ? inspected : "";
    if (key !== pulseRoom) { pulseRoom = key; pulseStart = performance.now(); }
    if (pulseFrame !== null) cancelAnimationFrame(pulseFrame);
    pulseFrame = null;
    if (disposed) return;
    paintPulse(performance.now());
    if (key && !document.hidden && !reducedMotion.matches) pulseFrame = requestAnimationFrame(pulseTick);
  }
  document.addEventListener("visibilitychange",syncPulse);
  reducedMotion.addEventListener("change",syncPulse);
  const labels = createLabels(viewport, model, camera, key => { if (editable) selectRoom(key); }, id => { if (editable) selectFloor(id); });
  const render = () => {
    if (disposed) return;
    for (const floor of model.floors.values()) {
      updateArchitecture(floor.architecture, camera, controls.target, Boolean(focusFloor) || cutaway);
    }
    paintPulse(performance.now());
    renderer.render(scene, camera);
    labels.render(inspected, estimate);
  };

  function selectRoom(key) {
    inspected = key;
    roomSelect.value = key;
    if (key) {
      displaySelect.value = "room";
      floorSelect.value = "all";
      spacing.value = "0";
    } else if (displaySelect.value === "room") {
      displaySelect.value = "exterior";
    }
    update();
    frameView();
  }

  function selectFloor(id) {
    if (displaySelect.value === "room") displaySelect.value = "exterior";
    floorSelect.value = id;
    inspected = "";
    roomSelect.value = "";
    update();
    frameView();
  }

  function update() {
    const visibleFloor = floorSelect.value === "follow" ? estimate : floorSelect.value;
    const separation = Number(spacing.value);
    const assembled = visibleFloor === "all" && separation === 0;
    focusFloor = displaySelect.value === "room" && inspected ? inspected.split("/")[0] : null;
    cutaway = displaySelect.value === "cutaway" || visibleFloor !== "all" || viewSelect.value === "plan" || separation > 0;
    const ranks = new Map(candidates.map((candidate, index) => [candidate.room_id, index]));
    spacing.disabled = visibleFloor !== "all" || focusFloor !== null;
    root.querySelector(".model-spacing-value").textContent = focusFloor ? "Room focus" : visibleFloor !== "all" ? "Single floor" : separation ? `+${separation} m / level` : "Actual elevations";
    root.querySelector(".model-layout-note").textContent = visibleFloor === "all"
      ? `${assembled ? (cutaway ? "Interior cutaway at recorded elevations." : "Complete building with continuous facades and roof.") : "Exploded view; extra spacing is for viewing only."} Shell and roof details are approximate. LG = 0 m; 1 = +4.7 m; 2 = +10.7 m; 3 ≈ +16.7 m.`
      : visibleFloor === "0" ? "G lower side +0.3 m; cafe-side floor +0.7 m. Clockwise stair landings +2.9 / +3.5 m, reaching Floor 1 at +4.7 m. Split boundary and stair geometry are approximate."
        : visibleFloor === "LG" ? "LG lift exit = 0 m. Alder clearance ≈ 4.3 m, estimated from Elm's 4 m clearance at G."
          : visibleFloor === "3" ? "Floor 3 ≈ +16.7 m relative to LG: extrapolated using the 6 m First-to-Second interval, not measured."
            : "Elevations are relative to the LG lift exit. Oak entrances are flush with their floor corridors; its ceiling profile is schematic.";
    for (const [id, floor] of model.floors) {
      floor.architecture.root.visible = true;
      const elevation = floor.group.userData.elevation_m;
      floor.group.visible = visibleFloor === "all" ? elevation !== null : visibleFloor === id;
      floor.group.position.y = (elevation ?? 0) + (visibleFloor === "all" ? floor.group.userData.levelIndex * separation : 0);
      floor.slab.traverse(object => { if (object.isMesh) object.material.color.setHex(id === estimate ? 0xe4eaf9 : 0xf3f4f6); });
      floor.slab.visible = !(assembled && floor.assembledSlab);
      if (floor.assembledSlab) {
        floor.assembledSlab.visible = assembled;
        floor.assembledSlab.traverse(object => { if (object.isMesh) object.material.color.setHex(id === estimate ? 0xe4eaf9 : 0xf3f4f6); });
      }
      // Connecting stairs retain surveyed vertical rise, so hide them in exploded views.
      if (floor.stair) floor.stair.visible = visibleFloor !== "all" || assembled;
    }
    for (const part of model.roomParts.values()) {
      part.zone.userData.focus_muted = false;
      part.zone.visible = part.walls.visible = !(assembled && part.suppressInAssembly);
    }
    if (focusFloor) {
      applyRoomFocus(model, focusFloor);
      const room = model.zones.find(zone=>roomKey(zone)===inspected)?.userData;
      root.querySelector(".model-layout-note").textContent = `${room?.label ?? "Room"} · Floor ${focusFloor === "0" ? "G" : focusFloor}. Upper floors and ceiling removed. Translucent 3D room walls remain; the selected room is highlighted in red.`;
    }
    for (const [key, part] of model.roomParts) {
      const selected = Boolean(focusFloor) && key === inspected;
      part.walls.traverse(object => {
        if (object.isMesh) {
          object.material.color.setHex(selected ? 0xe02030 : 0xc7d2df);
          object.material.opacity = selected ? .38 : focusFloor ? .20 : part.zone.userData.kind === "study" ? .12 : .48;
        } else if (object.isLineSegments) {
          object.material.color.setHex(selected ? 0xb51224 : 0x9baabd);
          object.material.opacity = selected ? .95 : focusFloor ? .45 : .7;
        }
      });
    }
    for (const zone of model.zones) {
      const selected = inspected === `${zone.userData.floorId}/${zone.userData.room_id}`;
      const eligible = zone.userData.floorId === estimate || (assembled && ((zone.userData.room_id === "nuc-12-oak" && estimate === "2") || (zone.userData.room_id === "alder" && estimate === "0")));
      const rank = eligible && !focusFloor ? (ranks.get(zone.userData.room_id) ?? ranks.get(zone.userData.legacy_room_id)) : undefined;
      let colour = zoneColours[zone.userData.kind];
      if (rank !== undefined) colour = rank === 0 ? 0x5659da : 0xa2aee5;
      if (selected) colour = 0xe02030;
      zone.material.color.setHex(colour);
      zone.traverse(object => {
        if (object.isLineSegments) {
          object.material.color.setHex(0x8b97a7);
          object.material.opacity = 1;
          object.material.transparent = false;
        }
      });
    }
    const selected = model.zones.find(zone => inspected === roomKey(zone));
    roomInfo.hidden = !selected;
    if (selected) {
      const room = selected.userData;
      const floor = data.floors.find(item => item.id === room.floorId);
      const kind = { lecture:"Lecture theatre", studio:"Studio classroom", laboratory:"Teaching laboratory",
        study:"Study area", study_room:"Study room", shop:"Shop", social:"Café / social space", lift:"Lift" }[room.kind];
      const candidate = room.floorId === estimate ? candidates.find(item=>item.room_id === room.room_id || item.room_id === room.legacy_room_id) : null;
      detail.textContent = `Selected ${room.label} · Floor ${room.floorId === "0" ? "G" : room.floorId}`;
      roomInfo.querySelector("h3").textContent = room.label;
      const fields = [["Floor", `${room.floorId === "0" ? "G" : room.floorId} · ${floor.label}`], ["Use", kind]];
      fields.push([room.is_rectangular ? "Width × length" : "Plan bounds (W × L)", `${room.width_m.toFixed(2)} × ${room.length_m.toFixed(2)} m`]);
      fields.push([room.multi_level ? "Access-plan area" : "Plan area", `${room.area_m2.toFixed(2)} m²`]);
      fields.push(["Outline perimeter", `${room.perimeter_m.toFixed(2)} m`]);
      const heightLabel = room.estimated_from ? " · estimated" : " · supplied";
      fields.push([room.multi_level && room.rendered_clearance_m != null ? "Clearance at this entrance" : "Ceiling height",
        room.rendered_clearance_m == null ? "Not supplied · footprint only" : `${room.rendered_clearance_m.toFixed(2)} m${heightLabel}`]);
      fields.push(["Floor elevation", `${room.elevation_m.toFixed(2)} m relative to LG · ${room.elevation_provenance === "extrapolated_equal_storey_height" ? "extrapolated, not measured" : "barometer estimate"}`]);
      if (candidate) fields.push(["Candidate score", `${Number(candidate.score).toFixed(2)}${candidateMode ? " · " + candidateMode : ""}`]);
      const list = roomInfo.querySelector("dl");
      list.replaceChildren();
      for (const [name,value] of fields) {
        const term = document.createElement("dt"), description = document.createElement("dd");
        term.textContent = name;
        description.textContent = value;
        list.append(term, description);
      }
      const note = roomInfo.querySelector(".model-room-note");
      const notes = [];
      if (room.multi_level) notes.push("One multi-level theatre, shown on both access plans. Its internal seating rake is not reconstructed; access-plan areas must not be added together.");
      if (room.room_id === "nuc-12-oak") notes.push("Entrances match corridor elevations (+4.7 / +10.7 m). Supplied clearances imply ceiling endpoints +12.2 / +13.7 m; the connecting profile is approximate.");
      if (room.room_id === "alder") notes.push("Assumed shared ceiling +4.3 m relative to LG, using Elm's 4 m clearance at G. This is an estimate, not a measurement.");
      if (!room.is_rectangular) notes.push("Irregular outline: width and length are enclosing bounds; area follows the polygon.");
      if (room.estimated_from) notes.push(`Height estimated from ${room.estimated_from === "nuc-3-studyroom" ? "the third-floor study room" : room.estimated_from === "nuc-0-elm" ? "Elm" : room.estimated_from}.`);
      if (room.room_id === "nuc-0-shop") notes.push("Shop boundary near reception is approximately traced.");
      if (room.kind === "study" && room.ceiling_height_m != null) notes.push("This is an open-area clearance envelope, not a surveyed set of enclosing walls.");
      if (/^(?:LG|[0-3])-(?:study|lift)-/.test(room.room_id)) notes.push("Numbered for this model; not an official room number.");
      note.textContent = notes.join(" ");
      note.hidden = !note.textContent;
    } else {
      const floorLabel = data.floors.find(floor => floor.id === estimate)?.label ?? "awaiting estimate";
      const unknown = candidates.filter(candidate => !model.zones.some(zone =>
        (zone.userData.room_id === candidate.room_id || zone.userData.legacy_room_id === candidate.room_id) && zone.userData.floorId === estimate));
      detail.textContent = `Estimated floor · ${floorLabel}${mode ? " · " + mode : ""}${unknown.length ? " · Unmapped room IDs: " + unknown.map(room => room.room_id).join(", ") : ""}`;
    }
    root.querySelectorAll(".model-labels button").forEach(button => { button.disabled = !editable; });
    syncPulse();
    render();
  }

  function frameView() {
    const visible = [...model.floors.values()].filter(floor => floor.group.visible);
    const box = new THREE.Box3();
    model.group.updateMatrixWorld(true);
    for (const floor of visible) floor.group.traverseVisible(object => {
      if (!object.isMesh) return;
      object.geometry.computeBoundingBox();
      box.union(object.geometry.boundingBox.clone().applyMatrix4(object.matrixWorld));
    });
    if (box.isEmpty()) box.setFromObject(model.group);
    const centre = box.getCenter(new THREE.Vector3());
    controls.target.copy(centre);
    controls.enableRotate = viewSelect.value !== "plan";
    const direction = viewSelect.value === "plan"
      ? new THREE.Vector3(0, 1, .001) : new THREE.Vector3(.85, focusFloor || cutaway ? 1.2 : .75, 1);
    direction.normalize();
    const right = new THREE.Vector3().crossVectors(camera.up, direction).normalize();
    const up = new THREE.Vector3().crossVectors(direction, right);
    const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const tanH = tanV * camera.aspect;
    let distance = 0;
    for (const x of [box.min.x, box.max.x]) {
      for (const y of [box.min.y, box.max.y]) {
        for (const z of [box.min.z, box.max.z]) {
          const corner = new THREE.Vector3(x, y, z).sub(centre);
          const depth = corner.dot(direction);
          distance = Math.max(distance, depth + Math.abs(corner.dot(right)) / tanH,
            depth + Math.abs(corner.dot(up)) / tanV);
        }
      }
    }
    distance *= 1.12;
    controls.maxDistance = Math.max(350, distance * 2);
    camera.position.copy(centre).add(direction.multiplyScalar(distance));
    controls.update();
    render();
  }

  floorSelect.addEventListener("change", () => selectFloor(floorSelect.value));
  viewSelect.addEventListener("change", () => { update(); frameView(); });
  displaySelect.addEventListener("change", () => {
    if (displaySelect.value === "room") {
      selectRoom(inspected || "2/nuc-2-yew");
    } else {
      inspected = "";
      roomSelect.value = "";
      update(); frameView();
    }
  });
  root.querySelector(".model-example").addEventListener("click", () => {
    viewSelect.value = "3d";
    selectRoom("3/nuc-3-studyroom");
  });
  spacing.addEventListener("input", () => { update(); frameView(); });
  root.querySelector(".model-reset").addEventListener("click", frameView);
  roomSelect.addEventListener("change", () => {
    selectRoom(roomSelect.value);
  });
  root.querySelector(".model-clear").addEventListener("click", () => selectRoom(""));

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const canvas = renderer.domElement;
  function hitRoom(event) {
    const bounds = canvas.getBoundingClientRect();
    pointer.set((event.clientX-bounds.left)/bounds.width*2-1, 1-(event.clientY-bounds.top)/bounds.height*2);
    raycaster.setFromCamera(pointer, camera);
    // Include slabs and walls so a click cannot pass through an upper floor.
    const hit = raycaster.intersectObjects(visibleMeshes(model), false)[0];
    return hit?.object.userData.roomKey ?? "";
  }
  let pressed = null;
  const pointers = new Set();
  canvas.addEventListener("pointerdown", event => {
    if (!editable) return;
    pointers.add(event.pointerId);
    pressed = pointers.size === 1 && event.button === 0
      ? {id:event.pointerId, x:event.clientX, y:event.clientY, dragged:false} : null;
  });
  canvas.addEventListener("pointermove", event => {
    if (!editable) return;
    if (pressed && Math.hypot(event.clientX-pressed.x,event.clientY-pressed.y)>5) pressed.dragged = true;
    canvas.style.cursor = pointers.size ? "grabbing" : hitRoom(event) ? "pointer" : "grab";
  });
  canvas.addEventListener("pointerup", event => {
    if (!editable) return;
    if (pressed?.id === event.pointerId && !pressed.dragged && pointers.size === 1 &&
        Math.hypot(event.clientX-pressed.x,event.clientY-pressed.y)<=5) selectRoom(hitRoom(event));
    pointers.delete(event.pointerId);
    pressed = null;
    canvas.style.cursor = "grab";
  });
  canvas.addEventListener("pointercancel", event => { pointers.delete(event.pointerId); pressed = null; });
  controls.addEventListener("change", render);
  const observer = new ResizeObserver(() => {
    const width = viewport.clientWidth;
    const height = viewport.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    if (editable && manualView) render();
    else frameView();
  });
  observer.observe(viewport);
  update();
  frameView();
  return {
    setPresentation(next) {
      const key = JSON.stringify(next);
      if (key === presentationKey) return;
      presentationKey = key;
      if (editable && !next.editable) {
        manualView = {floor:floorSelect.value, view:viewSelect.value, display:displaySelect.value,
          spacing:spacing.value, inspected, position:camera.position.clone(), target:controls.target.clone()};
      }
      const enteringManual = !editable && next.editable;
      editable = next.editable;
      controls.enabled = editable;
      root.dataset.presentation = editable ? 'manual' : 'automatic';
      canvas.style.cursor = editable ? 'grab' : 'default';
      if (editable) {
        if (enteringManual && manualView) {
          floorSelect.value = manualView.floor; viewSelect.value = manualView.view;
          displaySelect.value = manualView.display; spacing.value = manualView.spacing;
          inspected = manualView.inspected; roomSelect.value = inspected;
          camera.position.copy(manualView.position); controls.target.copy(manualView.target);
          controls.enableRotate = viewSelect.value !== 'plan';
          update(); controls.update(); render();
        }
        return;
      }
      inspected = next.roomKey && model.roomParts.has(next.roomKey) ? next.roomKey : '';
      roomSelect.value = inspected;
      floorSelect.value = inspected ? 'all' : model.floors.has(next.floorId) ? next.floorId : 'all';
      displaySelect.value = inspected ? 'room' : floorSelect.value === 'all' ? 'exterior' : 'cutaway';
      viewSelect.value = '3d'; spacing.value = '0';
      update(); frameView();
    },
    focusRoom(key) {
      if (key && !model.roomParts.has(key)) return;
      if (inspected === key) return;
      viewSelect.value = "3d";
      selectRoom(key);
    },
    setFloor(floorId) {
      const normalized = floorId === "G" ? "0" : floorId;
      if (estimate === normalized) return;
      estimate = normalized;
      if (floorSelect.value === "follow" && inspected && !inspected.startsWith(`${normalized}/`)) {
        inspected = "";
        roomSelect.value = "";
      }
      update();
      if (floorSelect.value === "follow") frameView();
    },
    setRoomCandidates(next, sourceMode = "") {
      const key = JSON.stringify([next, sourceMode]);
      if (key === candidateKey) return;
      candidateKey = key;
      candidates = next;
      candidateMode = sourceMode;
      update();
    },
    setMode(next) {
      if (mode === next) return;
      mode = next;
      update();
    },
    dispose() {
      disposed = true;
      if (pulseFrame !== null) cancelAnimationFrame(pulseFrame);
      document.removeEventListener("visibilitychange",syncPulse);
      reducedMotion.removeEventListener("change",syncPulse);
      observer.disconnect();
      controls.dispose();
      labels.dispose();
      model.group.traverse(object => {
        object.geometry?.dispose();
        if (Array.isArray(object.material)) object.material.forEach(material => material.dispose());
        else object.material?.dispose();
      });
      renderer.dispose();
      root.remove();
    },
  };
}
