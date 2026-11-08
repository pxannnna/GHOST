import * as THREE from "../vendor/three/three.module.js";
import data from "./nucleus-metric-data.js";
import { createArchitecture } from "./architecture.js";

export const zoneColours = {
  lecture: 0xdbe7f2, studio: 0xdcebdd, laboratory: 0xf1e4ce,
  study: 0xeee5ed, study_room: 0xeee5ed, social: 0xeee5ed, shop: 0xe8dfcf, lift: 0xaebdce,
};

function point([x, z]) {
  return new THREE.Vector2(x, -z);
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

function plates(floor, extraHoles = []) {
  const result = new THREE.Group();
  const regions = floor.slab_regions ?? [{ polygon_m: floor.outline_m, elevation_m: floor.elevation_m }];
  for (const [index, region] of regions.entries()) {
    // Openings lie on the main/northern plate, never on the cafe split plate.
    const holes = index === 0 ? [...floor.voids_m, ...(floor.stair_opening_m ? [floor.stair_opening_m] : []), ...extraHoles] : [];
    const slab = outlinedMesh(surface(region.polygon_m, .12, holes), 0xf3f4f6);
    slab.position.y = region.elevation_m-floor.elevation_m-.12;
    result.add(slab);
  }
  return result;
}

function staircase(floor) {
  const result = new THREE.Group();
  result.name = "Central_stair_schematic";
  result.userData.provenance = "schematic_plan_positions_and_tread_count";
  const spec = data.central_stair;
  const landing = spec.landing_size_m;
  for (const [i, point] of spec.points.entries()) {
    const [x,z] = point.position_m;
    const platform = outlinedMesh(new THREE.BoxGeometry(landing,.12,landing), 0xd8dee8);
    platform.position.set(x,point.elevation_m-floor.elevation_m-.06,z);
    platform.name = point.label;
    result.add(platform);
    if (!i) continue;
    const previous = spec.points[i-1];
    const [px,pz] = previous.position_m;
    const dx=x-px, dz=z-pz, distance=Math.hypot(dx,dz);
    const count=Math.ceil((point.elevation_m-previous.elevation_m)/.18);
    const run=distance-landing;
    for (let step=1;step<=count;step++) {
      const along=landing/2+(step-.5)*run/count;
      const tread=outlinedMesh(new THREE.BoxGeometry(spec.width_m,.12,run/count),0xe0e5ed);
      tread.position.set(px+dx*along/distance,
        previous.elevation_m+(point.elevation_m-previous.elevation_m)*step/count-floor.elevation_m-.06,
        pz+dz*along/distance);
      tread.rotation.y=Math.atan2(dx,dz);
      result.add(tread);
    }
  }
  return result;
}

function envelopeWall(a, b, bottom, heightA, heightB) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position",new THREE.Float32BufferAttribute([
    a[0],bottom,a[1], b[0],bottom,b[1], b[0],bottom+heightB,b[1],
    a[0],bottom,a[1], b[0],bottom+heightB,b[1], a[0],bottom+heightA,a[1],
  ],3));
  geometry.computeVertexNormals();
  return geometry;
}

export function createBuilding() {
  const group = new THREE.Group();
  group.name = "Nucleus_metric_clearance_model";
  const floors = new Map();
  const zones = [];
  const roomParts = new Map();
  data.floors.forEach((floor, floorIndex) => {
    const storey = new THREE.Group();
    storey.name = `Floor_${floor.id}`;
    storey.position.y = floor.elevation_m ?? 0;
    storey.userData = { floorId: floor.id, levelIndex: floor.id === "LG" ? -1 : Number(floor.id), elevation_m: floor.elevation_m };
    // Visual slab thickness is below the surveyed floor elevation.
    const slab = plates(floor);
    slab.name = "Floor_plate";
    storey.add(slab);
    // Do not insert a second solid floor through Oak in the assembled building.
    const upperTheatre = floor.rooms.find(room => (floor.id === "2" && room.room_id === "nuc-12-oak") || (floor.id === "0" && room.room_id === "alder"));
    let assembledSlab = null;
    if (upperTheatre) {
      assembledSlab = plates(floor, [upperTheatre.polygon_m]);
      assembledSlab.visible = false;
      assembledSlab.name = "Floor_plate_shared_theatre_opening";
      storey.add(assembledSlab);
    }
    const stair = floor.id === data.central_stair.floor_id ? staircase(floor) : null;
    if (stair) storey.add(stair);
    for (const room of floor.rooms) {
      const key = `${floor.id}/${room.room_id}`;
      const clearance = room.clearance_at_access_floor_m?.[floor.id] ?? room.ceiling_height_m;
      const offset = room.elevation_m-floor.elevation_m;
      const mesh = outlinedMesh(surface(room.polygon_m, .025, room.holes_m), zoneColours[room.kind] ?? 0xeee5ed);
      mesh.position.y = offset+.005;
      mesh.name = key;
      mesh.userData = { ...room, floorId: floor.id, roomKey: key,
        rendered_clearance_m: clearance, label_height_m: offset+(clearance == null ? .18 : clearance + .15) };
      storey.add(mesh);
      zones.push(mesh);
      const walls = new THREE.Group();
      walls.name = `${key}_clearance_envelope`;
      if (clearance != null) {
        for (const polygon of [room.polygon_m, ...(room.holes_m ?? [])]) {
          polygon.forEach((a, edge) => {
            const b = polygon[(edge + 1) % polygon.length];
            const length = Math.hypot(b[0]-a[0], b[1]-a[1]);
            if (length < .001) return;
            // Zero-thickness, open-top envelopes preserve internal dimensions.
            const ceilingHeight = p => room.room_id === "nuc-12-oak" && floor.id === "1"
              ? room.ceiling_profile_m.low_elevation_m-room.elevation_m +
                (p[0]-room.bounds_m[0])/room.width_m*(room.ceiling_profile_m.high_elevation_m-room.ceiling_profile_m.low_elevation_m)
              : clearance;
            const wall = new THREE.Mesh(envelopeWall(a,b,offset,ceilingHeight(a),ceilingHeight(b)),
              new THREE.MeshBasicMaterial({ color: 0xc7d2df, side: THREE.DoubleSide,
                transparent: true, opacity: room.kind === "study" ? .12 : .48, depthWrite: false }));
            wall.userData.roomKey = key;
            wall.add(new THREE.LineSegments(new THREE.EdgesGeometry(wall.geometry),
              new THREE.LineBasicMaterial({ color: 0x9baabd, transparent:true, opacity:.7 })));
            walls.add(wall);
          });
        }
      }
      storey.add(walls);
      roomParts.set(key, { zone: mesh, walls, suppressInAssembly: room === upperTheatre });
    }
    const architecture = createArchitecture(floor,data.floors[floorIndex+1]);
    storey.add(architecture.root);
    group.add(storey);
    floors.set(floor.id, { group: storey, slab, assembledSlab, stair, architecture });
  });
  return { group, floors, zones, roomParts };
}
