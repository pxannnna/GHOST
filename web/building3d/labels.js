import * as THREE from "../vendor/three/three.module.js";
import data from "./nucleus-metric-data.js";

export const roomKey = zone => `${zone.userData.floorId}/${zone.userData.room_id}`;

export function visibleMeshes(model) {
  const meshes = [];
  for (const floor of model.floors.values()) {
    if (floor.group.visible) floor.group.traverseVisible(object => { if (object.isMesh) meshes.push(object); });
  }
  return meshes;
}

// Place the label inside a broad part of each polygon, including L-shaped rooms.
function interiorPoint(polygon, height) {
  const xs = polygon.map(p => p[0]), ys = polygon.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  let best = polygon[0], clearance = -1;
  for (let row = 0; row < 24; row++) for (let col = 0; col < 24; col++) {
    const x = minX + (col + .5) / 24 * (maxX - minX);
    const y = minY + (row + .5) / 24 * (maxY - minY);
    let inside = false, distance = Infinity;
    polygon.forEach((a, i) => {
      const b = polygon[(i + 1) % polygon.length];
      if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const t = Math.max(0, Math.min(1, ((x-a[0])*dx + (y-a[1])*dy) / (dx*dx + dy*dy || 1)));
      distance = Math.min(distance, Math.hypot(x-a[0]-t*dx, y-a[1]-t*dy));
    });
    if (inside && distance > clearance) { best = [x,y]; clearance = distance; }
  }
  return new THREE.Vector3(best[0], height, best[1]);
}

export function createLabels(viewport, model, camera, selectRoom, selectFloor) {
  const layer = document.createElement("div");
  layer.className = "model-labels";
  layer.setAttribute("aria-label", "Building labels");
  viewport.append(layer);
  const leader = document.createElement("div");
  leader.className = "model-room-leader";
  leader.setAttribute("aria-hidden", "true");
  leader.hidden = true;
  layer.append(leader);
  const makeButton = (text, className, action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = text;
    button.addEventListener("click", action);
    layer.append(button);
    return button;
  };
  const floorLabels = data.floors.map(floor => {
    const name = `${floor.id === "0" ? "G" : floor.id} · ${floor.label}`;
    const button = makeButton(name, "model-floor-label", () => selectFloor(floor.id));
    button.setAttribute("aria-label", `Show floor ${name}`);
    return { floor: model.floors.get(floor.id), button, id: floor.id };
  });
  const roomLabels = model.zones.map(zone => {
    const key = roomKey(zone);
    const button = makeButton(zone.userData.label, "model-room-label", () => selectRoom(key));
    button.setAttribute("aria-label", `Inspect ${zone.userData.label}, floor ${zone.userData.floorId === "0" ? "G" : zone.userData.floorId}`);
    return { zone, key, button, anchor: interiorPoint(zone.userData.polygon_m, zone.userData.label_height_m) };
  });
  const ray = new THREE.Raycaster();
  const overlaps = (a,b) => a.x < b.x+b.w+4 && a.x+a.w+4 > b.x && a.y < b.y+b.h+4 && a.y+a.h+4 > b.y;
  return {
    render(selected, estimate) {
      const width = viewport.clientWidth, height = viewport.clientHeight;
      const occupied = [];
      leader.hidden = true;
      floorLabels.forEach(entry => { entry.button.hidden = !entry.floor.group.visible; });
      const projectedFloors = floorLabels.filter(entry => entry.floor.group.visible).map(entry => {
        const anchor = new THREE.Vector3(0, 1, 0);
        entry.floor.group.localToWorld(anchor);
        anchor.project(camera);
        return { ...entry, y: (1-anchor.y)*height/2 };
      }).sort((a,b) => a.y-b.y);
      let lastY = -30;
      for (const [index, entry] of projectedFloors.entries()) {
        const remaining = projectedFloors.length - index - 1;
        const y = Math.max(lastY+29, Math.min(height-30-remaining*29, Math.max(8, entry.y-12)));
        entry.button.style.transform = `translate(8px, ${y}px)`;
        entry.button.dataset.estimated = String(entry.id === estimate);
        occupied.push({x:8,y,w:entry.button.offsetWidth,h:entry.button.offsetHeight});
        lastY = y;
      }
      const meshes = visibleMeshes(model);
      const priority = entry => entry.key === selected ? 0 : ["study", "lift"].includes(entry.zone.userData.kind) ? 2 : 1;
      for (const entry of [...roomLabels].sort((a,b) => priority(a)-priority(b))) {
        const {zone, button, key} = entry;
        button.hidden = true;
        button.setAttribute("aria-pressed", String(key === selected));
        if (!zone.parent.visible || !zone.visible || zone.userData.focus_muted) continue;
        const anchor = entry.anchor.clone();
        const world = zone.parent.localToWorld(anchor);
        const projected = world.clone().project(camera);
        if (Math.abs(projected.x)>1 || Math.abs(projected.y)>1 || Math.abs(projected.z)>1) continue;
        const direction = world.clone().sub(camera.position);
        const distance = direction.length();
        ray.set(camera.position, direction.normalize());
        const obstruction = ray.intersectObjects(meshes, false)[0];
        if (obstruction && obstruction.distance < distance-.15) continue;
        button.hidden = false;
        let box = { x:(projected.x+1)*width/2-button.offsetWidth/2,
          y:(1-projected.y)*height/2-button.offsetHeight/2, w:button.offsetWidth, h:button.offsetHeight };
        if (key === selected) {
          // Keep both the selected label and neighbouring labels off the room.
          // A callout points to its footprint instead of covering its small walls.
          const part = model.roomParts.get(key);
          const bounds = new THREE.Box3().setFromObject(part.walls.children.length ? part.walls : zone);
          const points = [];
          for (const x of [bounds.min.x,bounds.max.x]) for (const y of [bounds.min.y,bounds.max.y]) for (const z of [bounds.min.z,bounds.max.z]) {
            const p = new THREE.Vector3(x,y,z).project(camera);
            points.push({x:(p.x+1)*width/2,y:(1-p.y)*height/2});
          }
          const left = Math.min(...points.map(p=>p.x)), right = Math.max(...points.map(p=>p.x));
          const top = Math.min(...points.map(p=>p.y)), bottom = Math.max(...points.map(p=>p.y));
          const roomBox = {x:left-8,y:top-8,w:right-left+16,h:bottom-top+16};
          occupied.push(roomBox);
          const choices = [
            {x:right+28,y:(top+bottom-box.h)/2},
            {x:left-box.w-28,y:(top+bottom-box.h)/2},
            {x:(left+right-box.w)/2,y:top-box.h-28},
            {x:(left+right-box.w)/2,y:bottom+28},
          ].map(p=>({...box,...p}));
          const placement = choices.find(p=>p.x>=2 && p.y>=2 && p.x+p.w<=width-2 && p.y+p.h<=height-2 && !occupied.some(other=>overlaps(p,other)));
          if (placement) {
            box = placement;
            const floorPoint = entry.anchor.clone();
            floorPoint.y = zone.position.y+.03;
            zone.parent.localToWorld(floorPoint).project(camera);
            const ax = (floorPoint.x+1)*width/2, ay = (1-floorPoint.y)*height/2;
            const bx = Math.max(box.x,Math.min(box.x+box.w,ax));
            const by = Math.max(box.y,Math.min(box.y+box.h,ay));
            leader.style.width = `${Math.hypot(bx-ax,by-ay)}px`;
            leader.style.transform = `translate(${ax}px, ${ay}px) rotate(${Math.atan2(by-ay,bx-ax)}rad)`;
            leader.hidden = false;
          }
        }
        if (box.x<2 || box.y<2 || box.x+box.w>width-2 || box.y+box.h>height-2 || occupied.some(other=>overlaps(box,other))) {
          button.hidden = true;
          continue;
        }
        button.style.transform = `translate(${box.x}px, ${box.y}px)`;
        occupied.push(box);
      }
    },
    dispose() { layer.remove(); },
  };
}
