import * as THREE from "../vendor/three/three.module.js";

// Visual construction assumptions, not surveyed dimensions. Plan footprints and
// floor datums still come from nucleus-metric-data.js. Fin rhythm/materials are
// inspired by the published Nucleus exterior, not an exact facade survey.
export const shellAssumptions = Object.freeze({ topStoreyHeight: 4, wallThickness: .24,
  roofThickness: .24, parapetHeight: .4, facadeBayWidth: 2.4 });

const materials = {
  masonry: new THREE.MeshStandardMaterial({color:0xd9d4c7, roughness:.9}),
  metal: new THREE.MeshStandardMaterial({color:0x928572, roughness:.65, metalness:.25}),
  frame: new THREE.MeshStandardMaterial({color:0x414b4f, roughness:.6}),
  glass: new THREE.MeshStandardMaterial({color:0x68838c, roughness:.3, metalness:.3}),
  roof: new THREE.MeshStandardMaterial({color:0xc8c9c4, roughness:.95}),
  core: new THREE.MeshStandardMaterial({color:0xc7c3b9, roughness:.9}),
};

function panel(length,height,depth,material,x,y,z,angle=0) {
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(length,height,depth),material);
  mesh.position.set(x,y,z);
  mesh.rotation.y=angle;
  mesh.castShadow=true;
  mesh.receiveShadow=true;
  return mesh;
}

function cap(points,y,thickness,material=materials.roof) {
  const shape=new THREE.Shape(points.map(([x,z])=>new THREE.Vector2(x,-z)));
  const geometry=new THREE.ExtrudeGeometry(shape,{depth:thickness,bevelEnabled:false});
  geometry.rotateX(-Math.PI/2);
  const mesh=new THREE.Mesh(geometry,material);
  mesh.position.y=y-thickness;
  mesh.castShadow=true;
  mesh.receiveShadow=true;
  return mesh;
}

export function createArchitecture(floor,nextFloor) {
  const root=new THREE.Group();
  root.name=`Architectural_shell_${floor.id}`;
  const bottom=floor.id==='0' ? -floor.elevation_m : 0;
  const height=(nextFloor?.elevation_m ?? floor.elevation_m+shellAssumptions.topStoreyHeight)-floor.elevation_m;
  const walls=[];
  const polygon=floor.outline_m;
  const signedArea=polygon.reduce((sum,a,i)=>{
    const b=polygon[(i+1)%polygon.length]; return sum+a[0]*b[1]-b[0]*a[1];
  },0);
  polygon.forEach((a,i)=>{
    const b=polygon[(i+1)%polygon.length];
    const dx=b[0]-a[0], dz=b[1]-a[1], length=Math.hypot(dx,dz);
    const angle=-Math.atan2(dz,dx), x=(a[0]+b[0])/2, z=(a[1]+b[1])/2;
    const outward=new THREE.Vector3(dz,0,-dx).multiplyScalar(signedArea>0?1:-1).normalize();
    const wall=new THREE.Group();
    wall.userData.outward=outward;
    wall.name=`Facade_edge_${i}`;
    // Opaque glazing is a visual facade treatment. It closes the exterior rather
    // than making the entire building look like disconnected transparent plans.
    const low=floor.id==='LG' || floor.id==='0';
    const heightAboveBase=height-bottom;
    wall.add(panel(length,heightAboveBase,shellAssumptions.wallThickness,
      heightAboveBase<1 ? materials.masonry : materials.glass,x,(height+bottom)/2,z,angle));
    if(heightAboveBase>=1) {
      const band=low ? .7 : .65;
      wall.add(panel(length,band,.3,low?materials.masonry:materials.metal,x,bottom+band/2,z,angle));
      wall.add(panel(length,band,.3,low?materials.masonry:materials.metal,x,height-band/2,z,angle));
      const bays=Math.max(1,Math.ceil(length/shellAssumptions.facadeBayWidth));
      for(let n=0;n<=bays;n++) {
        const t=n/bays;
        wall.add(panel(low ? .38 : .14,heightAboveBase,low ? .42 : .48,
          low?materials.masonry:materials.metal,a[0]+dx*t,(height+bottom)/2,a[1]+dz*t,angle));
      }
      wall.add(panel(length,.055,.32,materials.frame,x,bottom+heightAboveBase*.55,z,angle));
    }
    if(!nextFloor) wall.add(panel(length,shellAssumptions.parapetHeight,.28,materials.metal,
      x,height+shellAssumptions.parapetHeight/2,z,angle));
    root.add(wall);
    walls.push(wall);
  });
  // Every volume is capped; lower caps also close exposed setbacks/terraces.
  // Hide these caps when inspecting interiors, preserving cross-floor theatres.
  const roof=cap(polygon,height-.015,shellAssumptions.roofThickness);
  roof.name=nextFloor?'Storey_ceiling_and_setback_roof':'Building_roof';
  root.add(roof);
  const skylights=new THREE.Group();
  skylights.name='Atrium_rooflights';
  if(!nextFloor) for(const opening of floor.voids_m) {
    skylights.add(cap(opening,height+.12,.12,materials.glass));
    opening.forEach((a,i)=>{
      const b=opening[(i+1)%opening.length];
      skylights.add(panel(Math.hypot(b[0]-a[0],b[1]-a[1]),.16,.12,materials.frame,
        (a[0]+b[0])/2,height+.16,(a[1]+b[1])/2,-Math.atan2(b[1]-a[1],b[0]-a[0])));
    });
    const xs=opening.map(p=>p[0]), zs=opening.map(p=>p[1]);
    for(let z=Math.min(...zs)+2;z<Math.max(...zs);z+=2) {
      skylights.add(panel(Math.max(...xs)-Math.min(...xs),.1,.08,materials.frame,
        (Math.max(...xs)+Math.min(...xs))/2,height+.16,z));
    }
  }
  root.add(skylights);
  // Continuous lift core walls make the vertical service volume legible in cutaway.
  const cores=new THREE.Group();
  cores.name='Lift_cores';
  for(const room of floor.rooms.filter(room=>room.kind==='lift')) {
    room.polygon_m.forEach((a,i)=>{
      const b=room.polygon_m[(i+1)%room.polygon_m.length];
      const mesh=panel(Math.hypot(b[0]-a[0],b[1]-a[1]),height,.15,materials.core,
        (a[0]+b[0])/2,height/2,(a[1]+b[1])/2,-Math.atan2(b[1]-a[1],b[0]-a[0]));
      mesh.userData.roomKey=`${floor.id}/${room.room_id}`;
      cores.add(mesh);
    });
  }
  root.add(cores);
  root.userData={height_m:height,assumptions:shellAssumptions};
  return {root,walls,roof,cores,skylights};
}

// Camera-facing facades are removed only in cutaway mode. Remaining facades
// keep the building's vertical enclosure readable without hiding room picking.
export function updateArchitecture(architecture,camera,centre,cutaway) {
  const towardCamera=camera.position.clone().sub(centre).setY(0).normalize();
  for(const wall of architecture.walls) wall.visible=!cutaway || wall.userData.outward.dot(towardCamera)<-.05;
  architecture.roof.visible=!cutaway;
  architecture.skylights.visible=!cutaway;
}
