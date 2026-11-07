import * as THREE from "../vendor/three/three.module.js";
import data from "./nucleus-data.js";

export const zoneColours = {
  lecture: 0xdbe7f2, studio: 0xdcebdd, laboratory: 0xf1e4ce,
  study: 0xeee5ed, social: 0xeee5ed, lift: 0xaebdce,
};

function point([x, y]) {
  return new THREE.Vector2((x - 460) * data.model_scale, -(y - 500) * data.model_scale);
}

function surface(points, depth, holes = []) {
  const shape = new THREE.Shape(points.map(point));
  shape.holes = holes.map(hole => new THREE.Path(hole.map(point)));
  const geometry = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false });
  geometry.rotateX(-Math.PI / 2);
  return geometry;
}

function outlinedMesh(geometry, colour) {
  // Unlit surfaces preserve plan colours and the event-highlight legend.
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: colour }));
  mesh.add(new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 25),
    new THREE.LineBasicMaterial({ color: 0x8b97a7 }),
  ));
  return mesh;
}

export function createBuilding() {
  const group = new THREE.Group();
  group.name = "Nucleus_PDF_study_model";
  const floors = new Map();
  const zones = [];
  data.floors.forEach((floor, index) => {
    const storey = new THREE.Group();
    storey.name = `Floor_${floor.id}`;
    storey.position.y = index * data.storey_spacing;
    storey.userData = { floorId: floor.id, levelIndex: index, sourcePage: floor.page };
    const slab = outlinedMesh(surface(floor.outline, .5, floor.voids), 0xf3f4f6);
    slab.name = "Floor_plate";
    storey.add(slab);
    for (const room of floor.rooms) {
      const mesh = outlinedMesh(surface(room.polygon, room.kind === "lift" ? 1.4 : .35), zoneColours[room.kind]);
      mesh.position.y = .52;
      mesh.name = `${floor.id}_${room.room_id}`;
      mesh.userData = { ...room, floorId: floor.id, roomKey: `${floor.id}/${room.room_id}` };
      storey.add(mesh);
      zones.push(mesh);
      // Low partition strips keep the room interiors readable from above.
      if (room.kind === "study" || room.kind === "social" || room.kind === "lift") continue;
      room.polygon.forEach((start, edge) => {
        const end = room.polygon[(edge + 1) % room.polygon.length];
        const a = point(start), b = point(end);
        const length = a.distanceTo(b);
        if (length < .02) return;
        const wall = new THREE.Mesh(
          new THREE.BoxGeometry(length, 1.2, .16),
          new THREE.MeshStandardMaterial({ color: 0xd7dde5, roughness: 1 }),
        );
        wall.position.set((a.x + b.x) / 2, 1.45, -(a.y + b.y) / 2);
        wall.rotation.y = Math.atan2(b.y - a.y, b.x - a.x);
        wall.name = `${room.room_id}_partition`;
        wall.userData.roomKey = mesh.userData.roomKey;
        storey.add(wall);
      });
    }
    group.add(storey);
    floors.set(floor.id, { group: storey, slab });
  });
  return { group, floors, zones };
}
