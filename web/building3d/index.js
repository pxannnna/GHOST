import * as THREE from "../vendor/three/three.module.js";
import { OrbitControls } from "../vendor/three/OrbitControls.js";
import data from "./nucleus-data.js";
import { createBuilding, zoneColours } from "./geometry.js";
import { createLabels, roomKey, visibleMeshes } from "./labels.js";

export function mountBuilding(container) {
  const root = document.createElement("div");
  root.className = "building-model";
  root.innerHTML = `
    <div class="model-toolbar">
      <label>Floor <select aria-label="Model floor"><option value="all">All floors</option><option value="follow">Follow estimate</option></select></label>
      <label>View <select aria-label="Model view"><option value="3d">3D perspective</option><option value="plan">Floor plan</option></select></label>
      <button type="button" class="model-reset">Reset view</button>
    </div>
    <div class="model-viewport"></div>
    <div class="model-toolbar model-options">
      <label>Layer spacing <input type="range" min="0" max="18" value="8" step="1" aria-label="Layer spacing"></label>
      <label>Inspect <select aria-label="Inspect room"><option value="">Choose a room</option></select></label>
    </div>
    <p class="model-detail" role="status">Select a room to inspect its location.</p>
    <section class="model-room-info" aria-label="Selected room" hidden>
      <div class="model-room-heading"><h3></h3><button type="button" class="model-clear">Clear selection</button></div>
      <dl></dl><p class="model-room-note"></p>
    </section>
    <p class="model-note">Click a room or its name to inspect. Drag to rotate · Scroll to zoom · Right-drag to pan. Select a floor or zoom in to see more labels. Heights and scale are illustrative.</p>`;
  container.append(root);
  const floorSelect = root.querySelector('[aria-label="Model floor"]');
  const viewSelect = root.querySelector('[aria-label="Model view"]');
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
    return { setFloor() {}, setRoomCandidates() {}, setMode() {}, dispose() { root.remove(); } };
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
  controls.minDistance = 25;
  controls.maxDistance = 350;
  controls.maxPolarAngle = Math.PI / 2 - .03;
  let estimate = null;
  let candidates = [];
  let candidateMode = "";
  let candidateKey = "";
  let inspected = "";
  let mode = "";
  let disposed = false;
  const labels = createLabels(viewport, model, camera, selectRoom, selectFloor);
  const render = () => {
    if (disposed) return;
    renderer.render(scene, camera);
    labels.render(inspected, estimate);
  };

  function selectRoom(key) {
    inspected = key;
    roomSelect.value = key;
    update();
  }

  function selectFloor(id) {
    floorSelect.value = id;
    inspected = "";
    roomSelect.value = "";
    update();
    frameView();
  }

  function update() {
    const visibleFloor = floorSelect.value === "follow" ? estimate : floorSelect.value;
    const ranks = new Map(candidates.map((candidate, index) => [candidate.room_id, index]));
    for (const [id, floor] of model.floors) {
      floor.group.visible = visibleFloor === "all" || visibleFloor === id;
      floor.group.position.y = floor.group.userData.levelIndex * (data.storey_spacing + Number(spacing.value));
      floor.slab.material.color.setHex(id === estimate ? 0xe4eaf9 : 0xf3f4f6);
    }
    for (const zone of model.zones) {
      const selected = inspected === `${zone.userData.floorId}/${zone.userData.room_id}`;
      const rank = zone.userData.floorId === estimate ? ranks.get(zone.userData.room_id) : undefined;
      let colour = zoneColours[zone.userData.kind];
      if (rank !== undefined) colour = rank === 0 ? 0x5659da : 0xa2aee5;
      if (selected) colour = 0xd79b46;
      zone.material.color.setHex(colour);
    }
    const selected = model.zones.find(zone => inspected === roomKey(zone));
    roomInfo.hidden = !selected;
    if (selected) {
      const room = selected.userData;
      const floor = data.floors.find(item => item.id === room.floorId);
      const kind = { lecture:"Lecture theatre", studio:"Studio classroom", laboratory:"Teaching laboratory",
        study:"Study area", social:"Café / social space", lift:"Lift" }[room.kind];
      const candidate = room.floorId === estimate ? candidates.find(item=>item.room_id === room.room_id) : null;
      detail.textContent = `Selected ${room.label} · Floor ${room.floorId === "0" ? "G" : room.floorId}`;
      roomInfo.querySelector("h3").textContent = room.label;
      const fields = [["Floor", `${room.floorId === "0" ? "G" : room.floorId} · ${floor.label}`], ["Use", kind]];
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
      note.textContent = ["alder", "oak"].includes(room.room_id)
        ? "Multi-level lecture theatre, shown on both access floors."
        : /^(?:LG|[0-3])-(?:study|lift)-/.test(room.room_id)
          ? "Numbered for this model; this is not an official room number." : "";
      note.hidden = !note.textContent;
    } else {
      const floorLabel = data.floors.find(floor => floor.id === estimate)?.label ?? "awaiting estimate";
      const unknown = candidates.filter(candidate => !model.zones.some(zone =>
        zone.userData.room_id === candidate.room_id && zone.userData.floorId === estimate));
      detail.textContent = `Estimated floor · ${floorLabel}${mode ? " · " + mode : ""}${unknown.length ? " · Unmapped room IDs: " + unknown.map(room => room.room_id).join(", ") : ""}`;
    }
    render();
  }

  function frameView() {
    const visible = [...model.floors.values()].filter(floor => floor.group.visible);
    const box = new THREE.Box3();
    for (const floor of visible) box.expandByObject(floor.group);
    if (box.isEmpty()) box.setFromObject(model.group);
    const centre = box.getCenter(new THREE.Vector3());
    controls.target.copy(centre);
    controls.enableRotate = viewSelect.value !== "plan";
    const direction = viewSelect.value === "plan"
      ? new THREE.Vector3(0, 1, .001) : new THREE.Vector3(.85, 1.2, 1);
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
  viewSelect.addEventListener("change", frameView);
  spacing.addEventListener("input", () => { update(); frameView(); });
  root.querySelector(".model-reset").addEventListener("click", frameView);
  roomSelect.addEventListener("change", () => {
    if (roomSelect.value) floorSelect.value = roomSelect.value.split("/")[0];
    selectRoom(roomSelect.value);
    frameView();
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
    pointers.add(event.pointerId);
    pressed = pointers.size === 1 && event.button === 0
      ? {id:event.pointerId, x:event.clientX, y:event.clientY, dragged:false} : null;
  });
  canvas.addEventListener("pointermove", event => {
    if (pressed && Math.hypot(event.clientX-pressed.x,event.clientY-pressed.y)>5) pressed.dragged = true;
    canvas.style.cursor = pointers.size ? "grabbing" : hitRoom(event) ? "pointer" : "grab";
  });
  canvas.addEventListener("pointerup", event => {
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
    frameView();
  });
  observer.observe(viewport);
  update();
  frameView();
  return {
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
